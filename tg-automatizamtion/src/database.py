"""
Database module for Telegram Automation System

Provides PostgreSQL and SQLite database operations.
Manages profiles, tasks, messages, and logging.
"""

import os
from pathlib import Path
from typing import Optional, List, Dict, Any
from contextlib import contextmanager
from datetime import datetime
import threading

# Try to import psycopg2 for PostgreSQL
try:
    import psycopg2
    import psycopg2.extras
    PSYCOPG2_AVAILABLE = True
except ImportError:
    PSYCOPG2_AVAILABLE = False

# SQLite is always available
import sqlite3


class Database:
    """Database manager with PostgreSQL and SQLite support."""

    def __init__(self, config):
        """
        Initialize database connection.

        Args:
            config: DatabaseConfig instance from config.py
        """
        self.config = config
        self._local = threading.local()

        if config.is_postgresql:
            if not PSYCOPG2_AVAILABLE:
                raise ImportError("psycopg2 not installed. Run: pip install psycopg2-binary")
            self._db_type = "postgresql"
            self._pg_config = config.postgresql
        else:
            self._db_type = "sqlite"
            self._sqlite_path = config.sqlite.absolute_path
            os.makedirs(os.path.dirname(self._sqlite_path), exist_ok=True)

        # Initialize database schema
        self._initialize_database()

    def _get_connection(self):
        """Get thread-local database connection."""
        if not hasattr(self._local, 'connection') or self._local.connection is None:
            if self._db_type == "postgresql":
                self._local.connection = psycopg2.connect(
                    host=self._pg_config.host,
                    port=self._pg_config.port,
                    database=self._pg_config.database,
                    user=self._pg_config.user,
                    password=self._pg_config.password
                )
                self._local.connection.autocommit = False
            else:
                self._local.connection = sqlite3.connect(
                    self._sqlite_path,
                    check_same_thread=False,
                    timeout=30.0
                )
                self._local.connection.row_factory = sqlite3.Row
                self._local.connection.execute("PRAGMA foreign_keys=ON")

        return self._local.connection

    def _get_cursor(self, conn):
        """Get cursor with appropriate row factory."""
        if self._db_type == "postgresql":
            return conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        return conn.cursor()

    def _placeholder(self) -> str:
        """Get placeholder for parameterized queries."""
        return "%s" if self._db_type == "postgresql" else "?"

    def _initialize_database(self):
        """Initialize database schema."""
        if self._db_type == "postgresql":
            schema_path = Path(__file__).parent.parent / 'db' / 'schema_postgresql.sql'
        else:
            schema_path = Path(__file__).parent.parent / 'db' / 'schema.sql'

        if not schema_path.exists():
            raise FileNotFoundError(f"Schema file not found: {schema_path}")

        with open(schema_path, 'r', encoding='utf-8') as f:
            schema_sql = f.read()

        conn = self._get_connection()

        if self._db_type == "postgresql":
            cursor = conn.cursor()
            # Split by semicolon and execute each statement
            statements = [s.strip() for s in schema_sql.split(';') if s.strip()]
            for statement in statements:
                if statement and not statement.startswith('--'):
                    try:
                        cursor.execute(statement)
                    except psycopg2.errors.DuplicateTable:
                        conn.rollback()
                        continue
                    except psycopg2.errors.DuplicateObject:
                        conn.rollback()
                        continue
            conn.commit()
        else:
            conn.executescript(schema_sql)
            conn.commit()

    @contextmanager
    def transaction(self, mode: str = 'DEFERRED'):
        """Context manager for database transactions."""
        conn = self._get_connection()
        try:
            if self._db_type == "sqlite" and mode != 'DEFERRED':
                conn.execute(f"BEGIN {mode}")
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise

    def close(self):
        """Close thread-local database connection."""
        if hasattr(self._local, 'connection') and self._local.connection:
            try:
                self._local.connection.close()
                self._local.connection = None
            except Exception as e:
                print(f"Warning: Error closing database connection: {e}")

    def _row_to_dict(self, row) -> Optional[Dict[str, Any]]:
        """Convert row to dictionary."""
        if row is None:
            return None
        if self._db_type == "postgresql":
            return dict(row)
        return dict(row)

    def _rows_to_list(self, rows) -> List[Dict[str, Any]]:
        """Convert rows to list of dictionaries."""
        return [self._row_to_dict(row) for row in rows]

    # ========================================
    # Profiles operations
    # ========================================

    def add_profile(self, profile_id: str, profile_name: str) -> int:
        """Add profile to database."""
        ph = self._placeholder()
        with self.transaction() as conn:
            cursor = self._get_cursor(conn)
            if self._db_type == "postgresql":
                cursor.execute(f"""
                    INSERT INTO profiles (profile_id, profile_name)
                    VALUES ({ph}, {ph})
                    ON CONFLICT(profile_id) DO UPDATE SET
                        profile_name = EXCLUDED.profile_name,
                        updated_at = CURRENT_TIMESTAMP
                    RETURNING id
                """, (profile_id, profile_name))
            else:
                cursor.execute(f"""
                    INSERT INTO profiles (profile_id, profile_name)
                    VALUES ({ph}, {ph})
                    ON CONFLICT(profile_id) DO UPDATE SET
                        profile_name = excluded.profile_name,
                        updated_at = CURRENT_TIMESTAMP
                    RETURNING id
                """, (profile_id, profile_name))
            return cursor.fetchone()[0] if self._db_type == "sqlite" else cursor.fetchone()['id']

    def get_active_profiles(self) -> List[Dict[str, Any]]:
        """Get all active profiles."""
        conn = self._get_connection()
        cursor = self._get_cursor(conn)
        cursor.execute("""
            SELECT * FROM profiles
            WHERE is_active = TRUE AND is_blocked = FALSE AND is_logged_out = FALSE
            ORDER BY profile_name
        """)
        return self._rows_to_list(cursor.fetchall())

    def get_profile_by_id(self, profile_id: str) -> Optional[Dict[str, Any]]:
        """Get profile by profile_id."""
        ph = self._placeholder()
        conn = self._get_connection()
        cursor = self._get_cursor(conn)
        cursor.execute(f"SELECT * FROM profiles WHERE profile_id = {ph}", (profile_id,))
        return self._row_to_dict(cursor.fetchone())

    def block_profile(self, profile_id: str):
        """Mark profile as blocked."""
        ph = self._placeholder()
        with self.transaction() as conn:
            cursor = self._get_cursor(conn)
            cursor.execute(f"""
                UPDATE profiles
                SET is_blocked = TRUE, is_active = FALSE, updated_at = CURRENT_TIMESTAMP
                WHERE profile_id = {ph}
            """, (profile_id,))

    def mark_profile_logged_out(self, profile_id: str):
        """Mark profile as logged out."""
        ph = self._placeholder()
        with self.transaction() as conn:
            cursor = self._get_cursor(conn)
            cursor.execute(f"""
                UPDATE profiles
                SET is_logged_out = TRUE, is_active = FALSE, updated_at = CURRENT_TIMESTAMP
                WHERE profile_id = {ph}
            """, (profile_id,))

    def update_profile_stats(self, profile_id: str):
        """Update profile statistics after sending message."""
        ph = self._placeholder()
        with self.transaction() as conn:
            cursor = self._get_cursor(conn)
            if self._db_type == "postgresql":
                # Reset hour counter if needed
                cursor.execute(f"""
                    UPDATE profiles
                    SET messages_sent_current_hour = 0,
                        hour_reset_time = CURRENT_TIMESTAMP
                    WHERE profile_id = {ph}
                      AND (hour_reset_time IS NULL
                           OR hour_reset_time + INTERVAL '1 hour' <= CURRENT_TIMESTAMP)
                """, (profile_id,))
            else:
                cursor.execute(f"""
                    UPDATE profiles
                    SET messages_sent_current_hour = 0,
                        hour_reset_time = CURRENT_TIMESTAMP
                    WHERE profile_id = {ph}
                      AND (hour_reset_time IS NULL
                           OR datetime(hour_reset_time, '+1 hour') <= datetime('now'))
                """, (profile_id,))

            # Increment messages sent
            cursor.execute(f"""
                UPDATE profiles
                SET messages_sent_current_hour = messages_sent_current_hour + 1,
                    last_message_time = CURRENT_TIMESTAMP,
                    updated_at = CURRENT_TIMESTAMP
                WHERE profile_id = {ph}
            """, (profile_id,))

    # ========================================
    # Tasks operations
    # ========================================

    def import_chats(self, group_id: str, chat_usernames: List[str], total_cycles: int = 1) -> int:
        """Import chats as tasks."""
        ph = self._placeholder()
        count = 0
        with self.transaction() as conn:
            cursor = self._get_cursor(conn)
            for username in chat_usernames:
                if not username.startswith('@'):
                    username = f'@{username}'

                if self._db_type == "postgresql":
                    cursor.execute(f"""
                        INSERT INTO tasks (group_id, chat_username, total_cycles)
                        VALUES ({ph}, {ph}, {ph})
                        ON CONFLICT(group_id, chat_username) DO UPDATE SET
                            total_cycles = EXCLUDED.total_cycles
                    """, (group_id, username, total_cycles))
                else:
                    cursor.execute(f"""
                        INSERT INTO tasks (group_id, chat_username, total_cycles)
                        VALUES ({ph}, {ph}, {ph})
                        ON CONFLICT(group_id, chat_username) DO UPDATE SET
                            total_cycles = excluded.total_cycles
                    """, (group_id, username, total_cycles))
                count += 1
        return count

    def get_task_by_id(self, task_id: int) -> Optional[Dict[str, Any]]:
        """Get task by ID."""
        ph = self._placeholder()
        conn = self._get_connection()
        cursor = self._get_cursor(conn)
        cursor.execute(f"SELECT * FROM tasks WHERE id = {ph}", (task_id,))
        return self._row_to_dict(cursor.fetchone())

    def block_task(self, task_id: int, reason: str):
        """Mark task as blocked."""
        ph = self._placeholder()
        with self.transaction() as conn:
            cursor = self._get_cursor(conn)
            cursor.execute(f"""
                UPDATE tasks
                SET is_blocked = TRUE,
                    block_reason = {ph},
                    status = 'blocked',
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = {ph}
            """, (reason, task_id))

    def increment_task_success(self, task_id: int):
        """Increment success counter."""
        ph = self._placeholder()
        with self.transaction() as conn:
            cursor = self._get_cursor(conn)
            cursor.execute(f"""
                UPDATE tasks
                SET success_count = success_count + 1,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = {ph}
            """, (task_id,))

    def increment_task_failed(self, task_id: int):
        """Increment failed counter."""
        ph = self._placeholder()
        with self.transaction() as conn:
            cursor = self._get_cursor(conn)
            cursor.execute(f"""
                UPDATE tasks
                SET failed_count = failed_count + 1,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = {ph}
            """, (task_id,))

    def increment_completed_cycles(self, task_id: int):
        """Increment completed cycles counter."""
        ph = self._placeholder()
        with self.transaction() as conn:
            cursor = self._get_cursor(conn)
            cursor.execute(f"""
                UPDATE tasks
                SET completed_cycles = completed_cycles + 1,
                    last_attempt_at = CURRENT_TIMESTAMP,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = {ph}
                RETURNING completed_cycles, total_cycles
            """, (task_id,))
            row = cursor.fetchone()
            if row:
                completed = row['completed_cycles'] if self._db_type == "postgresql" else row[0]
                total = row['total_cycles'] if self._db_type == "postgresql" else row[1]
                if completed >= total:
                    cursor.execute(f"UPDATE tasks SET status = 'completed' WHERE id = {ph}", (task_id,))

    def set_task_next_available(self, task_id: int, delay_seconds: int):
        """Set when task will be available again."""
        ph = self._placeholder()
        with self.transaction() as conn:
            cursor = self._get_cursor(conn)
            if self._db_type == "postgresql":
                cursor.execute(f"""
                    UPDATE tasks
                    SET next_available_at = CURRENT_TIMESTAMP + INTERVAL '{delay_seconds} seconds',
                        status = 'pending',
                        assigned_profile_id = NULL
                    WHERE id = {ph}
                """, (task_id,))
            else:
                cursor.execute(f"""
                    UPDATE tasks
                    SET next_available_at = datetime('now', '+' || {ph} || ' seconds'),
                        status = 'pending',
                        assigned_profile_id = NULL
                    WHERE id = {ph}
                """, (delay_seconds, task_id))

    def reset_task_status(self, task_id: int):
        """Reset task status to pending."""
        ph = self._placeholder()
        with self.transaction() as conn:
            cursor = self._get_cursor(conn)
            cursor.execute(f"""
                UPDATE tasks
                SET status = 'pending',
                    assigned_profile_id = NULL
                WHERE id = {ph}
            """, (task_id,))

    def get_task_stats(self) -> Dict[str, int]:
        """Get overall task statistics."""
        conn = self._get_connection()
        cursor = self._get_cursor(conn)
        cursor.execute("""
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN status = 'pending' THEN 1 ELSE 0 END) as pending,
                SUM(CASE WHEN status = 'in_progress' THEN 1 ELSE 0 END) as in_progress,
                SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) as completed,
                SUM(CASE WHEN status = 'blocked' THEN 1 ELSE 0 END) as blocked,
                SUM(success_count) as total_success,
                SUM(failed_count) as total_failed
            FROM tasks
        """)
        return self._row_to_dict(cursor.fetchone()) or {}

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
        error_message: Optional[str] = None,
        run_id: Optional[str] = None
    ) -> int:
        """Record task attempt."""
        ph = self._placeholder()
        with self.transaction() as conn:
            cursor = self._get_cursor(conn)
            cursor.execute(f"""
                INSERT INTO task_attempts (
                    task_id, profile_id, run_id, cycle_number, status,
                    message_text, error_type, error_message
                )
                VALUES ({ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph})
                RETURNING id
            """, (task_id, profile_id, run_id, cycle_number, status,
                 message_text, error_type, error_message))
            row = cursor.fetchone()
            return row['id'] if self._db_type == "postgresql" else row[0]

    def get_task_attempts_count_by_run(
        self,
        task_id: int,
        run_id: str,
        status: Optional[str] = None
    ) -> int:
        """Get count of task attempts for specific run_id."""
        ph = self._placeholder()
        conn = self._get_connection()
        cursor = self._get_cursor(conn)
        if status:
            cursor.execute(f"""
                SELECT COUNT(*) as cnt FROM task_attempts
                WHERE task_id = {ph} AND run_id = {ph} AND status = {ph}
            """, (task_id, run_id, status))
        else:
            cursor.execute(f"""
                SELECT COUNT(*) as cnt FROM task_attempts
                WHERE task_id = {ph} AND run_id = {ph}
            """, (task_id, run_id))
        row = cursor.fetchone()
        return row['cnt'] if self._db_type == "postgresql" else row[0]

    # ========================================
    # Messages operations
    # ========================================

    def import_messages(self, group_id: str, messages: List[str]) -> int:
        """Import messages for sending."""
        ph = self._placeholder()
        count = 0
        with self.transaction() as conn:
            cursor = self._get_cursor(conn)
            for text in messages:
                cursor.execute(f"""
                    INSERT INTO messages (group_id, text)
                    VALUES ({ph}, {ph})
                """, (group_id, text))
                count += 1
        return count

    def get_active_messages(self, group_id: str) -> List[str]:
        """Get all active messages for a group."""
        ph = self._placeholder()
        conn = self._get_connection()
        cursor = self._get_cursor(conn)
        cursor.execute(f"SELECT text FROM messages WHERE group_id = {ph} AND is_active = TRUE", (group_id,))
        rows = cursor.fetchall()
        if self._db_type == "postgresql":
            return [row['text'] for row in rows]
        return [row[0] for row in rows]

    def increment_message_usage(self, message_text: str):
        """Increment usage counter for message."""
        ph = self._placeholder()
        with self.transaction() as conn:
            cursor = self._get_cursor(conn)
            cursor.execute(f"""
                UPDATE messages
                SET usage_count = usage_count + 1
                WHERE text = {ph}
            """, (message_text,))

    # ========================================
    # Send log operations
    # ========================================

    def log_send(
        self,
        group_id: str,
        task_id: Optional[int],
        profile_id: str,
        chat_username: str,
        message_text: Optional[str],
        status: str,
        error_type: Optional[str] = None,
        error_details: Optional[str] = None
    ) -> int:
        """Log send attempt."""
        ph = self._placeholder()
        with self.transaction() as conn:
            cursor = self._get_cursor(conn)
            cursor.execute(f"""
                INSERT INTO send_log (
                    group_id, task_id, profile_id, chat_username,
                    message_text, status, error_type, error_details
                )
                VALUES ({ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph})
                RETURNING id
            """, (group_id, task_id, profile_id, chat_username,
                 message_text, status, error_type, error_details))
            row = cursor.fetchone()
            return row['id'] if self._db_type == "postgresql" else row[0]

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
        ph = self._placeholder()
        with self.transaction() as conn:
            cursor = self._get_cursor(conn)
            cursor.execute(f"""
                INSERT INTO screenshots (log_id, screenshot_type, file_name, description)
                VALUES ({ph}, {ph}, {ph}, {ph})
                RETURNING id
            """, (log_id, screenshot_type, file_name, description))
            row = cursor.fetchone()
            return row['id'] if self._db_type == "postgresql" else row[0]

    def cleanup_old_screenshots(self, days: int):
        """Delete screenshot records older than N days."""
        ph = self._placeholder()
        with self.transaction() as conn:
            cursor = self._get_cursor(conn)
            if self._db_type == "postgresql":
                cursor.execute(f"""
                    DELETE FROM screenshots
                    WHERE created_at < CURRENT_TIMESTAMP - INTERVAL '{days} days'
                """)
            else:
                cursor.execute(f"""
                    DELETE FROM screenshots
                    WHERE created_at < datetime('now', '-' || {ph} || ' days')
                """, (days,))

    # ========================================
    # Group operations
    # ========================================

    def clear_group_tasks(self, group_id: str):
        """Clear all tasks for a group."""
        ph = self._placeholder()
        with self.transaction() as conn:
            cursor = self._get_cursor(conn)
            cursor.execute(f"DELETE FROM tasks WHERE group_id = {ph}", (group_id,))

    def clear_group_messages(self, group_id: str):
        """Clear all messages for a group."""
        ph = self._placeholder()
        with self.transaction() as conn:
            cursor = self._get_cursor(conn)
            cursor.execute(f"DELETE FROM messages WHERE group_id = {ph}", (group_id,))

    def get_group_stats(self, group_id: str) -> Dict[str, Any]:
        """Get statistics for a group."""
        ph = self._placeholder()
        conn = self._get_connection()
        cursor = self._get_cursor(conn)
        cursor.execute(f"SELECT * FROM group_stats WHERE group_id = {ph}", (group_id,))
        return self._row_to_dict(cursor.fetchone()) or {}

    def get_all_groups(self) -> List[str]:
        """Get list of all group IDs."""
        conn = self._get_connection()
        cursor = self._get_cursor(conn)
        cursor.execute("""
            SELECT DISTINCT group_id FROM tasks
            UNION
            SELECT DISTINCT group_id FROM messages
        """)
        rows = cursor.fetchall()
        if self._db_type == "postgresql":
            return [row['group_id'] for row in rows]
        return [row[0] for row in rows]

    # ========================================
    # Profile statistics operations
    # ========================================

    def update_profile_daily_stats(self, profile_id: str, success: bool = True):
        """Update daily statistics for profile."""
        ph = self._placeholder()
        with self.transaction() as conn:
            cursor = self._get_cursor(conn)
            today = datetime.now().date().isoformat()

            if self._db_type == "postgresql":
                cursor.execute(f"""
                    INSERT INTO profile_daily_stats (profile_id, date, messages_sent, successful_sends, failed_sends)
                    VALUES ({ph}, {ph}, 1, {ph}, {ph})
                    ON CONFLICT(profile_id, date) DO UPDATE SET
                        messages_sent = profile_daily_stats.messages_sent + 1,
                        successful_sends = profile_daily_stats.successful_sends + {ph},
                        failed_sends = profile_daily_stats.failed_sends + {ph},
                        updated_at = CURRENT_TIMESTAMP
                """, (profile_id, today, 1 if success else 0, 0 if success else 1,
                     1 if success else 0, 0 if success else 1))
            else:
                cursor.execute(f"""
                    INSERT INTO profile_daily_stats (profile_id, date, messages_sent, successful_sends, failed_sends)
                    VALUES ({ph}, {ph}, 1, {ph}, {ph})
                    ON CONFLICT(profile_id, date) DO UPDATE SET
                        messages_sent = messages_sent + 1,
                        successful_sends = successful_sends + {ph},
                        failed_sends = failed_sends + {ph},
                        updated_at = CURRENT_TIMESTAMP
                """, (profile_id, today, 1 if success else 0, 0 if success else 1,
                     1 if success else 0, 0 if success else 1))

    def get_profile_daily_stats(self, profile_id: str, days: int = 7) -> List[Dict[str, Any]]:
        """Get daily statistics for profile."""
        ph = self._placeholder()
        conn = self._get_connection()
        cursor = self._get_cursor(conn)
        if self._db_type == "postgresql":
            cursor.execute(f"""
                SELECT * FROM profile_daily_stats
                WHERE profile_id = {ph}
                  AND date >= CURRENT_DATE - INTERVAL '{days} days'
                ORDER BY date DESC
            """, (profile_id,))
        else:
            cursor.execute(f"""
                SELECT * FROM profile_daily_stats
                WHERE profile_id = {ph}
                  AND date >= date('now', '-' || {ph} || ' days')
                ORDER BY date DESC
            """, (profile_id, days))
        return self._rows_to_list(cursor.fetchall())

    def get_all_profiles_daily_stats(self, days: int = 1) -> List[Dict[str, Any]]:
        """Get daily statistics for all profiles."""
        ph = self._placeholder()
        conn = self._get_connection()
        cursor = self._get_cursor(conn)
        if self._db_type == "postgresql":
            cursor.execute(f"""
                SELECT
                    pds.*,
                    p.profile_name
                FROM profile_daily_stats pds
                JOIN profiles p ON p.profile_id = pds.profile_id
                WHERE pds.date >= CURRENT_DATE - INTERVAL '{days} days'
                ORDER BY pds.date DESC, p.profile_name
            """)
        else:
            cursor.execute(f"""
                SELECT
                    pds.*,
                    p.profile_name
                FROM profile_daily_stats pds
                JOIN profiles p ON p.profile_id = pds.profile_id
                WHERE pds.date >= date('now', '-' || {ph} || ' days')
                ORDER BY pds.date DESC, p.profile_name
            """, (days,))
        return self._rows_to_list(cursor.fetchall())

    # ========================================
    # Utility methods
    # ========================================

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


# Global database instance
_db_instance: Optional[Database] = None


def get_database() -> Database:
    """Get global database instance."""
    global _db_instance
    if _db_instance is None:
        raise RuntimeError("Database not initialized. Call init_database() first.")
    return _db_instance


def init_database(config) -> Database:
    """
    Initialize global database instance.

    Args:
        config: DatabaseConfig instance from config.py
    """
    global _db_instance
    _db_instance = Database(config)
    return _db_instance
