"""
Task Queue module for Telegram Automation System

Manages async task queue with atomic operations for concurrent workers.
Implements fair task distribution and cycle balancing.
"""

import random
from typing import Optional, Dict, Any
from datetime import datetime, timedelta

from .database import get_database, AsyncDatabase
from .logger import get_logger
from .config import get_config


class AsyncTaskQueue:
    """Async task queue manager with atomic operations."""

    def __init__(self, db: AsyncDatabase):
        """Initialize task queue with database instance."""
        self.db = db
        self.config = get_config()
        self.logger = get_logger()

    async def get_next_incomplete_task(
        self,
        group_id: str,
        profile_id: str,
        run_id: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Atomically get next incomplete task for worker from a specific group.

        Uses FOR UPDATE SKIP LOCKED for atomicity to prevent race conditions
        between multiple workers.

        Args:
            group_id: Campaign group ID
            profile_id: Worker profile ID
            run_id: Optional session ID for per-session cycle counting

        Returns:
            Task dictionary or None if no tasks available
        """
        try:
            # Check if profile has reached hourly limit
            messages_sent = await self.db.get_profile_messages_current_hour(profile_id)
            if messages_sent >= self.config.limits.max_messages_per_hour:
                self.logger.info(
                    f"Profile {profile_id} reached hourly limit "
                    f"({messages_sent}/{self.config.limits.max_messages_per_hour})"
                )
                return None

            # Use database method for atomic task acquisition
            task = await self.db.get_next_task(
                group_id=group_id,
                profile_id=profile_id,
                run_id=run_id or '',
                max_cycles=self.config.limits.max_cycles
            )

            if task:
                if run_id:
                    # Count attempts in this session
                    session_attempts = await self.db.get_task_attempts_count_by_run(
                        task['id'], run_id, status='success'
                    )
                    cycle_display = f"session cycle {session_attempts + 1}/{self.config.limits.max_cycles}"
                else:
                    cycle_display = f"cycle {task['completed_cycles'] + 1}/{task['total_cycles']}"

                self.logger.debug(
                    f"Task acquired: {task['chat_username']} "
                    f"(group: {group_id}, {cycle_display}) "
                    f"by profile {profile_id}"
                )
                return task
            else:
                self.logger.debug(f"No tasks available for profile {profile_id} in group {group_id}")
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

    async def get_random_message(self, group_id: str) -> str:
        """
        Get random message from active messages for a specific group.

        Args:
            group_id: Campaign group ID

        Returns:
            Random message text
        """
        messages = await self.db.get_active_messages(group_id)

        if not messages:
            raise RuntimeError(f"No active messages available for group {group_id}. Please import messages first.")

        message = random.choice(messages)
        self.logger.debug(f"Selected random message for group {group_id}: {message[:50]}...")
        return message

    async def mark_task_success(
        self,
        task_id: int,
        profile_id: str,
        message_text: str,
        run_id: Optional[str] = None
    ):
        """
        Mark task attempt as successful.

        Updates task counters and creates attempt record.

        Args:
            task_id: Task ID
            profile_id: Profile that completed the task
            message_text: Message that was sent
            run_id: Optional session ID for per-session tracking
        """
        try:
            task = await self.db.get_task_by_id(task_id)
            if not task:
                self.logger.error(f"Task {task_id} not found")
                return

            group_id = task['group_id']

            # Calculate cycle number based on run_id or global counter
            if run_id:
                # Session-based: count attempts in this session
                cycle_number = await self.db.get_task_attempts_count_by_run(
                    task_id, run_id, status='success'
                ) + 1
            else:
                # Legacy: use global completed_cycles
                cycle_number = task['completed_cycles'] + 1

            # Record attempt
            await self.db.add_task_attempt(
                task_id=task_id,
                profile_id=profile_id,
                cycle_number=cycle_number,
                status='success',
                message_text=message_text,
                run_id=run_id
            )

            # Update task counters
            await self.db.increment_task_success(task_id)
            await self.db.increment_completed_cycles(task_id)

            # Update message usage
            await self.db.increment_message_usage(message_text)

            # Update profile stats (hourly counter)
            await self.db.update_profile_stats(profile_id)

            # Update profile daily stats
            await self.db.update_profile_daily_stats(profile_id, success=True)

            # Log to send_log
            await self.db.log_send(
                group_id=group_id,
                task_id=task_id,
                profile_id=profile_id,
                chat_username=task['chat_username'],
                message_text=message_text,
                status='success'
            )

            # Check if task is completed for this session or globally
            if run_id:
                # Session-based: check if reached max_cycles for this session
                session_attempts = await self.db.get_task_attempts_count_by_run(
                    task_id, run_id, status='success'
                )
                if session_attempts >= self.config.limits.max_cycles:
                    self.logger.info(
                        f"Task completed for this session: {task['chat_username']} "
                        f"({session_attempts}/{self.config.limits.max_cycles})"
                    )
                else:
                    # Set next available time for cycle delay
                    cycle_delay_seconds = self.config.limits.cycle_delay_minutes * 60
                    await self.db.set_task_next_available(task_id, cycle_delay_seconds)
                    self.logger.debug(
                        f"Task {task['chat_username']} will be available again in {cycle_delay_seconds}s"
                    )
            else:
                # Legacy: check global completed_cycles
                updated_task = await self.db.get_task_by_id(task_id)
                if updated_task['completed_cycles'] >= updated_task['total_cycles']:
                    self.logger.info(f"Task completed: {task['chat_username']}")
                else:
                    # Set next available time for cycle delay
                    cycle_delay_seconds = self.config.limits.cycle_delay_minutes * 60
                    await self.db.set_task_next_available(task_id, cycle_delay_seconds)
                    self.logger.debug(
                        f"Task {task['chat_username']} will be available again in {cycle_delay_seconds}s"
                    )

        except Exception as e:
            self.logger.error(f"Error marking task success: {e}")

    async def mark_task_failed(
        self,
        task_id: int,
        profile_id: str,
        error_type: str,
        error_message: Optional[str] = None,
        should_block: bool = False,
        block_reason: Optional[str] = None,
        run_id: Optional[str] = None
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
            run_id: Optional session ID for per-session tracking
        """
        try:
            task = await self.db.get_task_by_id(task_id)
            if not task:
                self.logger.error(f"Task {task_id} not found")
                return

            group_id = task['group_id']

            # Calculate cycle number based on run_id or global counter
            if run_id:
                # Session-based: count all attempts in this session
                cycle_number = await self.db.get_task_attempts_count_by_run(
                    task_id, run_id
                ) + 1
            else:
                # Legacy: use global completed_cycles
                cycle_number = task['completed_cycles'] + 1

            # Record attempt
            await self.db.add_task_attempt(
                task_id=task_id,
                profile_id=profile_id,
                cycle_number=cycle_number,
                status='failed',
                error_type=error_type,
                error_message=error_message,
                run_id=run_id
            )

            # Update task counters
            await self.db.increment_task_failed(task_id)
            await self.db.increment_completed_cycles(task_id)

            # Update profile daily stats
            await self.db.update_profile_daily_stats(profile_id, success=False)

            # Log to send_log
            await self.db.log_send(
                group_id=group_id,
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
                await self.db.block_task(task_id, block_reason or error_type)
                self.logger.warning(
                    f"Task blocked: {task['chat_username']} - {block_reason or error_type}"
                )
            else:
                # If not blocked, add a small backoff delay to prevent immediate retry loop
                backoff_seconds = 300  # 5 minutes backoff
                await self.db.set_task_next_available(task_id, backoff_seconds)
                self.logger.debug(
                    f"Task {task['chat_username']} failed (not blocked), backing off for {backoff_seconds}s"
                )

        except Exception as e:
            self.logger.error(f"Error marking task failed: {e}")

    async def get_queue_stats(self) -> Dict[str, Any]:
        """
        Get current queue statistics.

        Returns:
            Dictionary with queue statistics
        """
        try:
            stats = await self.db.get_task_stats()

            # Calculate percentages
            total = stats.get('total', 0) or 0
            if total > 0:
                stats['pending_percent'] = ((stats.get('pending') or 0) / total) * 100
                stats['completed_percent'] = ((stats.get('completed') or 0) / total) * 100
                stats['blocked_percent'] = ((stats.get('blocked') or 0) / total) * 100
            else:
                stats['pending_percent'] = 0
                stats['completed_percent'] = 0
                stats['blocked_percent'] = 0

            return stats

        except Exception as e:
            self.logger.error(f"Error getting queue stats: {e}")
            return {}

    async def reset_stale_tasks(self, timeout_minutes: int = 30, group_id: Optional[str] = None) -> int:
        """
        Reset tasks that have been in progress for too long.

        This handles cases where workers crashed without releasing tasks.

        Args:
            timeout_minutes: Minutes after which task is considered stale
            group_id: Optional group ID to filter tasks

        Returns:
            Number of reset tasks
        """
        try:
            async with self.db.transaction() as conn:
                cutoff_time = datetime.now() - timedelta(minutes=timeout_minutes)

                if group_id:
                    result = await conn.fetch('''
                        UPDATE tasks
                        SET status = 'pending',
                            assigned_profile_id = NULL
                        WHERE status = 'in_progress'
                          AND group_id = $1
                          AND updated_at < $2
                        RETURNING chat_username
                    ''', group_id, cutoff_time)
                else:
                    result = await conn.fetch('''
                        UPDATE tasks
                        SET status = 'pending',
                            assigned_profile_id = NULL
                        WHERE status = 'in_progress'
                          AND updated_at < $1
                        RETURNING chat_username
                    ''', cutoff_time)

                reset_tasks = [row['chat_username'] for row in result]

                if reset_tasks:
                    self.logger.warning(
                        f"Reset {len(reset_tasks)} stale tasks: {', '.join(reset_tasks)}"
                    )

                return len(reset_tasks)

        except Exception as e:
            self.logger.error(f"Error resetting stale tasks: {e}")
            return 0


# Global task queue instance
_task_queue_instance: Optional[AsyncTaskQueue] = None


def get_task_queue() -> AsyncTaskQueue:
    """Get global task queue instance."""
    global _task_queue_instance
    if _task_queue_instance is None:
        db = get_database()
        _task_queue_instance = AsyncTaskQueue(db)
    return _task_queue_instance


def init_task_queue(db: AsyncDatabase) -> AsyncTaskQueue:
    """Initialize global task queue with database instance."""
    global _task_queue_instance
    _task_queue_instance = AsyncTaskQueue(db)
    return _task_queue_instance
