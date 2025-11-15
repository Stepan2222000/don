"""
Task Queue module for Telegram Automation System

Manages task queue with atomic operations for concurrent workers.
Implements fair task distribution and cycle balancing.
"""

import random
from typing import Optional, Dict, Any
from datetime import datetime, timedelta

from .database import get_database
from .logger import get_logger
from .config import get_config


class TaskQueue:
    """Task queue manager with atomic operations."""

    def __init__(self):
        """Initialize task queue."""
        self.db = get_database()
        self.config = get_config()
        self.logger = get_logger()

    def get_next_incomplete_task(self, profile_id: str) -> Optional[Dict[str, Any]]:
        """
        Atomically get next incomplete task for worker.

        Uses UPDATE + RETURNING for atomicity to prevent race conditions
        between multiple workers.

        Prioritization:
        1. Tasks with fewer completed cycles (balancing)
        2. Tasks that haven't been attempted recently (fairness)

        Args:
            profile_id: Worker profile ID

        Returns:
            Task dictionary or None if no tasks available
        """
        try:
            # Check if profile has reached hourly limit
            profile = self.db.get_profile_by_id(profile_id)
            if profile:
                # Handle None value for new profiles
                messages_sent = profile['messages_sent_current_hour'] or 0
                if messages_sent >= self.config.limits.max_messages_per_hour:
                    self.logger.info(
                        f"Profile {profile_id} reached hourly limit "
                        f"({messages_sent}/{self.config.limits.max_messages_per_hour})"
                    )
                    return None

            with self.db.transaction() as conn:
                # Use UPDATE + RETURNING for atomic operation
                cursor = conn.execute(
                    """
                    UPDATE tasks
                    SET
                        status = 'in_progress',
                        assigned_profile_id = :profile_id,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = (
                        SELECT id FROM tasks
                        WHERE
                            is_blocked = 0
                            AND completed_cycles < total_cycles
                            AND (next_available_at IS NULL OR next_available_at <= CURRENT_TIMESTAMP)
                            AND (status = 'pending' OR (status = 'in_progress' AND assigned_profile_id = :profile_id))
                        ORDER BY
                            completed_cycles ASC,               -- Priority: fewer cycles done
                            last_attempt_at ASC NULLS FIRST     -- Then: not attempted recently
                        LIMIT 1
                    )
                    RETURNING *
                    """,
                    {"profile_id": profile_id}
                )

                row = cursor.fetchone()
                if row:
                    task = dict(row)
                    self.logger.debug(
                        f"Task acquired: {task['chat_username']} "
                        f"(cycle {task['completed_cycles'] + 1}/{task['total_cycles']}) "
                        f"by profile {profile_id}"
                    )
                    return task
                else:
                    self.logger.debug(f"No tasks available for profile {profile_id}")
                    return None

        except Exception as e:
            self.logger.error(f"Error getting next task: {e}")
            return None

    def calculate_delay(self) -> float:
        """
        Calculate delay between messages based on config.

        Applies randomness to avoid detection patterns.

        Returns:
            Delay in seconds
        """
        max_per_hour = self.config.limits.max_messages_per_hour
        randomness = self.config.limits.delay_randomness

        # Base delay = 3600 seconds / messages per hour
        base_delay = 3600.0 / max_per_hour

        # Apply randomness (±20% by default)
        random_factor = random.uniform(1.0 - randomness, 1.0 + randomness)
        actual_delay = base_delay * random_factor

        self.logger.debug(f"Calculated delay: {actual_delay:.1f}s (base: {base_delay:.1f}s)")
        return actual_delay

    def get_random_message(self) -> str:
        """
        Get random message from active messages.

        Returns:
            Random message text
        """
        messages = self.db.get_active_messages()

        if not messages:
            raise RuntimeError("No active messages available. Please import messages first.")

        message = random.choice(messages)
        self.logger.debug(f"Selected random message: {message[:50]}...")
        return message

    def mark_task_success(
        self,
        task_id: int,
        profile_id: str,
        message_text: str
    ):
        """
        Mark task attempt as successful.

        Updates task counters and creates attempt record.

        Args:
            task_id: Task ID
            profile_id: Profile that completed the task
            message_text: Message that was sent
        """
        try:
            task = self.db.get_task_by_id(task_id)
            if not task:
                self.logger.error(f"Task {task_id} not found")
                return

            cycle_number = task['completed_cycles'] + 1

            # Record attempt
            self.db.add_task_attempt(
                task_id=task_id,
                profile_id=profile_id,
                cycle_number=cycle_number,
                status='success',
                message_text=message_text
            )

            # Update task counters
            self.db.increment_task_success(task_id)
            self.db.increment_completed_cycles(task_id)

            # Update message usage
            self.db.increment_message_usage(message_text)

            # Update profile stats
            self.db.update_profile_stats(profile_id)

            # Log to send_log
            self.db.log_send(
                task_id=task_id,
                profile_id=profile_id,
                chat_username=task['chat_username'],
                message_text=message_text,
                status='success'
            )

            # Check if task is completed
            updated_task = self.db.get_task_by_id(task_id)
            if updated_task['completed_cycles'] >= updated_task['total_cycles']:
                self.logger.info(f"Task completed: {task['chat_username']}")
            else:
                # Set next available time for cycle delay
                cycle_delay_seconds = self.config.limits.cycle_delay_minutes * 60
                self.db.set_task_next_available(task_id, cycle_delay_seconds)
                self.logger.debug(
                    f"Task {task['chat_username']} will be available again in {cycle_delay_seconds}s"
                )

        except Exception as e:
            self.logger.error(f"Error marking task success: {e}")

    def mark_task_failed(
        self,
        task_id: int,
        profile_id: str,
        error_type: str,
        error_message: Optional[str] = None,
        should_block: bool = False,
        block_reason: Optional[str] = None
    ):
        """
        Mark task attempt as failed.

        Args:
            task_id: Task ID
            profile_id: Profile that attempted the task
            error_type: Type of error (chat_not_found, need_to_join, etc.)
            error_message: Detailed error message
            should_block: Whether to block task permanently
            block_reason: Reason for blocking
        """
        try:
            task = self.db.get_task_by_id(task_id)
            if not task:
                self.logger.error(f"Task {task_id} not found")
                return

            cycle_number = task['completed_cycles'] + 1

            # Record attempt
            self.db.add_task_attempt(
                task_id=task_id,
                profile_id=profile_id,
                cycle_number=cycle_number,
                status='failed',
                error_type=error_type,
                error_message=error_message
            )

            # Update task counters
            self.db.increment_task_failed(task_id)
            self.db.increment_completed_cycles(task_id)

            # Log to send_log
            self.db.log_send(
                task_id=task_id,
                profile_id=profile_id,
                chat_username=task['chat_username'],
                message_text=None,
                status='failed',
                error_type=error_type,
                error_details=error_message
            )

            # Block task if needed
            if should_block:
                self.db.block_task(task_id, block_reason or error_type)
                self.logger.warning(
                    f"Task blocked: {task['chat_username']} - {block_reason or error_type}"
                )

        except Exception as e:
            self.logger.error(f"Error marking task failed: {e}")

    def get_queue_stats(self) -> Dict[str, Any]:
        """
        Get current queue statistics.

        Returns:
            Dictionary with queue statistics
        """
        try:
            stats = self.db.get_task_stats()

            # Calculate percentages
            total = stats.get('total', 0)
            if total > 0:
                stats['pending_percent'] = (stats.get('pending', 0) / total) * 100
                stats['completed_percent'] = (stats.get('completed', 0) / total) * 100
                stats['blocked_percent'] = (stats.get('blocked', 0) / total) * 100
            else:
                stats['pending_percent'] = 0
                stats['completed_percent'] = 0
                stats['blocked_percent'] = 0

            return stats

        except Exception as e:
            self.logger.error(f"Error getting queue stats: {e}")
            return {}

    def reset_stale_tasks(self, timeout_minutes: int = 30) -> int:
        """
        Reset tasks that have been in progress for too long.

        This handles cases where workers crashed without releasing tasks.

        Args:
            timeout_minutes: Minutes after which task is considered stale

        Returns:
            Number of reset tasks
        """
        try:
            with self.db.transaction() as conn:
                cutoff_time = datetime.now() - timedelta(minutes=timeout_minutes)

                cursor = conn.execute(
                    """
                    UPDATE tasks
                    SET status = 'pending',
                        assigned_profile_id = NULL
                    WHERE status = 'in_progress'
                      AND updated_at < ?
                    RETURNING chat_username
                    """,
                    (cutoff_time,)
                )

                reset_tasks = [row[0] for row in cursor.fetchall()]

                if reset_tasks:
                    self.logger.warning(
                        f"Reset {len(reset_tasks)} stale tasks: {', '.join(reset_tasks)}"
                    )

                return len(reset_tasks)

        except Exception as e:
            self.logger.error(f"Error resetting stale tasks: {e}")
            return 0


# Global task queue instance
_task_queue_instance: Optional[TaskQueue] = None


def get_task_queue() -> TaskQueue:
    """Get global task queue instance."""
    global _task_queue_instance
    if _task_queue_instance is None:
        _task_queue_instance = TaskQueue()
    return _task_queue_instance
