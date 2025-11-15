"""
Database module for Telegram Automation System

Provides SQLite database operations with WAL mode for concurrent access.
Manages profiles, tasks, messages, and logging.
"""

import sqlite3
import os
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple
from contextlib import contextmanager
from datetime import datetime, timedelta
import threading


class Database:
    """SQLite database manager with WAL mode and transaction support."""

    def __init__(self, db_path: str):
        """
        Initialize database connection.

        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = db_path
        self._local = threading.local()  # Thread-local storage for connections

        # Ensure database directory exists
        os.makedirs(os.path.dirname(db_path), exist_ok=True)

        # Initialize database if needed
        self._initialize_database()

    def _get_connection(self) -> sqlite3.Connection:
        """Get thread-local database connection."""
        if not hasattr(self._local, 'connection'):
            self._local.connection = sqlite3.connect(
                self.db_path,
                check_same_thread=False,
                timeout=30.0
            )
            self._local.connection.row_factory = sqlite3.Row
            # Enable foreign keys
            self._local.connection.execute("PRAGMA foreign_keys=ON")
        return self._local.connection

    def _initialize_database(self):
        """Initialize database from schema.sql if not exists."""
        schema_path = Path(__file__).parent.parent / 'db' / 'schema.sql'

        if not schema_path.exists():
            raise FileNotFoundError(f"Schema file not found: {schema_path}")

        with open(schema_path, 'r', encoding='utf-8') as f:
            schema_sql = f.read()

        conn = self._get_connection()
        conn.executescript(schema_sql)
        conn.commit()

    @contextmanager
    def transaction(self):
        """Context manager for database transactions."""
        conn = self._get_connection()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise

    def close(self):
        """Close thread-local database connection."""
        if hasattr(self._local, 'connection'):
            try:
                self._local.connection.close()
                delattr(self._local, 'connection')
            except Exception as e:
                # Log but don't raise - cleanup should be best-effort
                print(f"Warning: Error closing database connection: {e}")

    # ========================================
    # Profiles operations
    # ========================================

    def add_profile(self, profile_id: str, profile_name: str) -> int:
        """
        Add profile to database.

        Args:
            profile_id: UUID of Donut Browser profile
            profile_name: Display name of profile

        Returns:
            Profile database ID
        """
        with self.transaction() as conn:
            cursor = conn.execute(
                """
                INSERT INTO profiles (profile_id, profile_name)
                VALUES (?, ?)
                ON CONFLICT(profile_id) DO UPDATE SET
                    profile_name = excluded.profile_name,
                    updated_at = CURRENT_TIMESTAMP
                RETURNING id
                """,
                (profile_id, profile_name)
            )
            return cursor.fetchone()[0]

    def get_active_profiles(self) -> List[Dict[str, Any]]:
        """Get all active profiles."""
        conn = self._get_connection()
        cursor = conn.execute(
            """
            SELECT * FROM profiles
            WHERE is_active = 1 AND is_blocked = 0
            ORDER BY profile_name
            """
        )
        return [dict(row) for row in cursor.fetchall()]

    def get_profile_by_id(self, profile_id: str) -> Optional[Dict[str, Any]]:
        """Get profile by profile_id."""
        conn = self._get_connection()
        cursor = conn.execute(
            "SELECT * FROM profiles WHERE profile_id = ?",
            (profile_id,)
        )
        row = cursor.fetchone()
        return dict(row) if row else None

    def block_profile(self, profile_id: str):
        """Mark profile as blocked by Telegram."""
        with self.transaction() as conn:
            conn.execute(
                """
                UPDATE profiles
                SET is_blocked = 1, is_active = 0, updated_at = CURRENT_TIMESTAMP
                WHERE profile_id = ?
                """,
                (profile_id,)
            )

    def update_profile_stats(self, profile_id: str):
        """Update profile statistics after sending message."""
        with self.transaction() as conn:
            # Reset hour counter if needed (MUST be done BEFORE incrementing)
            conn.execute(
                """
                UPDATE profiles
                SET messages_sent_current_hour = 0,
                    hour_reset_time = CURRENT_TIMESTAMP
                WHERE profile_id = ?
                  AND (hour_reset_time IS NULL
                       OR datetime(hour_reset_time, '+1 hour') <= datetime('now'))
                """,
                (profile_id,)
            )

            # Increment messages sent (AFTER reset check)
            conn.execute(
                """
                UPDATE profiles
                SET messages_sent_current_hour = messages_sent_current_hour + 1,
                    last_message_time = CURRENT_TIMESTAMP,
                    updated_at = CURRENT_TIMESTAMP
                WHERE profile_id = ?
                """,
                (profile_id,)
            )

    # ========================================
    # Tasks operations
    # ========================================

    def import_chats(self, chat_usernames: List[str], total_cycles: int = 1) -> int:
        """
        Import chats as tasks.

        Args:
            chat_usernames: List of @username strings
            total_cycles: Number of cycles to complete

        Returns:
            Number of imported chats
        """
        count = 0
        with self.transaction() as conn:
            for username in chat_usernames:
                # Ensure @ prefix
                if not username.startswith('@'):
                    username = f'@{username}'

                conn.execute(
                    """
                    INSERT INTO tasks (chat_username, total_cycles)
                    VALUES (?, ?)
                    ON CONFLICT(chat_username) DO UPDATE SET
                        total_cycles = excluded.total_cycles
                    """,
                    (username, total_cycles)
                )
                count += 1
        return count

    def get_task_by_id(self, task_id: int) -> Optional[Dict[str, Any]]:
        """Get task by ID."""
        conn = self._get_connection()
        cursor = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,))
        row = cursor.fetchone()
        return dict(row) if row else None

    def block_task(self, task_id: int, reason: str):
        """Mark task as blocked permanently."""
        with self.transaction() as conn:
            conn.execute(
                """
                UPDATE tasks
                SET is_blocked = 1,
                    block_reason = ?,
                    status = 'blocked',
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (reason, task_id)
            )

    def increment_task_success(self, task_id: int):
        """Increment success counter for task."""
        with self.transaction() as conn:
            conn.execute(
                """
                UPDATE tasks
                SET success_count = success_count + 1,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (task_id,)
            )

    def increment_task_failed(self, task_id: int):
        """Increment failed counter for task."""
        with self.transaction() as conn:
            conn.execute(
                """
                UPDATE tasks
                SET failed_count = failed_count + 1,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (task_id,)
            )

    def increment_completed_cycles(self, task_id: int):
        """Increment completed cycles counter."""
        with self.transaction() as conn:
            cursor = conn.execute(
                """
                UPDATE tasks
                SET completed_cycles = completed_cycles + 1,
                    last_attempt_at = CURRENT_TIMESTAMP,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                RETURNING completed_cycles, total_cycles
                """,
                (task_id,)
            )
            row = cursor.fetchone()
            if row and row[0] >= row[1]:
                # Mark as completed if all cycles done
                conn.execute(
                    "UPDATE tasks SET status = 'completed' WHERE id = ?",
                    (task_id,)
                )

    def set_task_next_available(self, task_id: int, delay_seconds: int):
        """Set when task will be available again."""
        with self.transaction() as conn:
            conn.execute(
                """
                UPDATE tasks
                SET next_available_at = datetime('now', '+' || ? || ' seconds'),
                    status = 'pending',
                    assigned_profile_id = NULL
                WHERE id = ?
                """,
                (delay_seconds, task_id)
            )

    def reset_task_status(self, task_id: int):
        """Reset task status to pending (cleanup after worker interruption)."""
        with self.transaction() as conn:
            conn.execute(
                """
                UPDATE tasks
                SET status = 'pending',
                    assigned_profile_id = NULL
                WHERE id = ?
                """,
                (task_id,)
            )

    def get_task_stats(self) -> Dict[str, int]:
        """Get overall task statistics."""
        conn = self._get_connection()
        cursor = conn.execute(
            """
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN status = 'pending' THEN 1 ELSE 0 END) as pending,
                SUM(CASE WHEN status = 'in_progress' THEN 1 ELSE 0 END) as in_progress,
                SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) as completed,
                SUM(CASE WHEN status = 'blocked' THEN 1 ELSE 0 END) as blocked,
                SUM(success_count) as total_success,
                SUM(failed_count) as total_failed
            FROM tasks
            """
        )
        row = cursor.fetchone()
        return dict(row) if row else {}

    # ========================================
    # Task attempts operations
    # ========================================

    def add_task_attempt(
        self,
        task_id: int,
        profile_id: str,
        cycle_number: int,
        status: str,
        message_text: Optional[str] = None,
        error_type: Optional[str] = None,
        error_message: Optional[str] = None
    ) -> int:
        """Record task attempt."""
        with self.transaction() as conn:
            cursor = conn.execute(
                """
                INSERT INTO task_attempts (
                    task_id, profile_id, cycle_number, status,
                    message_text, error_type, error_message
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                RETURNING id
                """,
                (task_id, profile_id, cycle_number, status,
                 message_text, error_type, error_message)
            )
            return cursor.fetchone()[0]

    # ========================================
    # Messages operations
    # ========================================

    def import_messages(self, messages: List[str]) -> int:
        """
        Import messages for sending.

        Args:
            messages: List of message texts

        Returns:
            Number of imported messages
        """
        count = 0
        with self.transaction() as conn:
            for text in messages:
                conn.execute(
                    """
                    INSERT INTO messages (text)
                    VALUES (?)
                    """,
                    (text,)
                )
                count += 1
        return count

    def get_active_messages(self) -> List[str]:
        """Get all active messages."""
        conn = self._get_connection()
        cursor = conn.execute(
            "SELECT text FROM messages WHERE is_active = 1"
        )
        return [row[0] for row in cursor.fetchall()]

    def increment_message_usage(self, message_text: str):
        """Increment usage counter for message."""
        with self.transaction() as conn:
            conn.execute(
                """
                UPDATE messages
                SET usage_count = usage_count + 1
                WHERE text = ?
                """,
                (message_text,)
            )

    # ========================================
    # Send log operations
    # ========================================

    def log_send(
        self,
        task_id: Optional[int],
        profile_id: str,
        chat_username: str,
        message_text: Optional[str],
        status: str,
        error_type: Optional[str] = None,
        error_details: Optional[str] = None
    ) -> int:
        """Log send attempt."""
        with self.transaction() as conn:
            cursor = conn.execute(
                """
                INSERT INTO send_log (
                    task_id, profile_id, chat_username,
                    message_text, status, error_type, error_details
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                RETURNING id
                """,
                (task_id, profile_id, chat_username,
                 message_text, status, error_type, error_details)
            )
            return cursor.fetchone()[0]

    # ========================================
    # Screenshots operations
    # ========================================

    def add_screenshot(
        self,
        log_id: Optional[int],
        screenshot_type: str,
        file_name: str,
        description: Optional[str] = None
    ) -> int:
        """Record screenshot metadata."""
        with self.transaction() as conn:
            cursor = conn.execute(
                """
                INSERT INTO screenshots (log_id, screenshot_type, file_name, description)
                VALUES (?, ?, ?, ?)
                RETURNING id
                """,
                (log_id, screenshot_type, file_name, description)
            )
            return cursor.fetchone()[0]

    def cleanup_old_screenshots(self, days: int):
        """Delete screenshot records older than N days."""
        with self.transaction() as conn:
            conn.execute(
                """
                DELETE FROM screenshots
                WHERE created_at < datetime('now', '-' || ? || ' days')
                """,
                (days,)
            )

    # ========================================
    # Utility methods
    # ========================================

    def close(self):
        """Close database connection."""
        if hasattr(self._local, 'connection'):
            self._local.connection.close()
            delattr(self._local, 'connection')

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


# Global database instance (will be initialized by config)
_db_instance: Optional[Database] = None


def get_database() -> Database:
    """Get global database instance."""
    global _db_instance
    if _db_instance is None:
        raise RuntimeError("Database not initialized. Call init_database() first.")
    return _db_instance


def init_database(db_path: str) -> Database:
    """Initialize global database instance."""
    global _db_instance
    _db_instance = Database(db_path)
    return _db_instance
