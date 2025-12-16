"""
Database module for Telegram Automation System

Provides async PostgreSQL database operations using asyncpg.
Manages profiles, tasks, messages, and logging.
"""

import asyncio
from pathlib import Path
from typing import Optional, List, Dict, Any
from contextlib import asynccontextmanager
from datetime import datetime

import asyncpg


class AsyncDatabase:
    """Async database manager with asyncpg and connection pool."""

    def __init__(self, config):
        """
        Initialize database connection.

        Args:
            config: DatabaseConfig instance from config.py
        """
        self.config = config
        self._pool: Optional[asyncpg.Pool] = None
        self._pg_config = config.postgresql

    async def connect(self):
        """Create connection pool and initialize schema."""
        self._pool = await asyncpg.create_pool(
            host=self._pg_config.host,
            port=self._pg_config.port,
            database=self._pg_config.database,
            user=self._pg_config.user,
            password=self._pg_config.password,
            min_size=2,
            max_size=10,
            command_timeout=60
        )
        await self._initialize_database()

    async def close(self):
        """Close connection pool."""
        if self._pool:
            await self._pool.close()
            self._pool = None

    async def _initialize_database(self):
        """Initialize database schema."""
        schema_path = Path(__file__).parent.parent / 'db' / 'schema_postgresql.sql'

        if not schema_path.exists():
            raise FileNotFoundError(f"Schema file not found: {schema_path}")

        with open(schema_path, 'r', encoding='utf-8') as f:
            schema_sql = f.read()

        async with self._pool.acquire() as conn:
            # Split by semicolon and execute each statement
            statements = [s.strip() for s in schema_sql.split(';') if s.strip()]
            for statement in statements:
                if statement and not statement.startswith('--'):
                    try:
                        await conn.execute(statement)
                    except asyncpg.exceptions.DuplicateTableError:
                        continue
                    except asyncpg.exceptions.DuplicateObjectError:
                        continue

    @asynccontextmanager
    async def transaction(self):
        """Async context manager for database transactions."""
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                yield conn

    # ========================================
    # Profiles operations
    # ========================================

    async def add_profile(self, profile_id: str, profile_name: str) -> int:
        """Add profile to database."""
        async with self._pool.acquire() as conn:
            return await conn.fetchval('''
                INSERT INTO profiles (profile_id, profile_name)
                VALUES ($1, $2)
                ON CONFLICT(profile_id) DO UPDATE SET
                    profile_name = EXCLUDED.profile_name,
                    updated_at = CURRENT_TIMESTAMP
                RETURNING id
            ''', profile_id, profile_name)

    async def get_active_profiles(self) -> List[Dict[str, Any]]:
        """Get all active profiles."""
        async with self._pool.acquire() as conn:
            rows = await conn.fetch('''
                SELECT * FROM profiles
                WHERE is_active = TRUE AND is_blocked = FALSE AND is_logged_out = FALSE
                ORDER BY profile_name
            ''')
            return [dict(r) for r in rows]

    async def get_profile_by_id(self, profile_id: str) -> Optional[Dict[str, Any]]:
        """Get profile by profile_id."""
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM profiles WHERE profile_id = $1",
                profile_id
            )
            return dict(row) if row else None

    async def block_profile(self, profile_id: str):
        """Mark profile as blocked."""
        async with self._pool.acquire() as conn:
            await conn.execute('''
                UPDATE profiles
                SET is_blocked = TRUE, is_active = FALSE, updated_at = CURRENT_TIMESTAMP
                WHERE profile_id = $1
            ''', profile_id)

    async def mark_profile_logged_out(self, profile_id: str):
        """Mark profile as logged out."""
        async with self._pool.acquire() as conn:
            await conn.execute('''
                UPDATE profiles
                SET is_logged_out = TRUE, is_active = FALSE, updated_at = CURRENT_TIMESTAMP
                WHERE profile_id = $1
            ''', profile_id)

    async def update_profile_stats(self, profile_id: str):
        """Update profile statistics after sending message."""
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                # Reset hour counter if needed
                await conn.execute('''
                    UPDATE profiles
                    SET messages_sent_current_hour = 0,
                        hour_reset_time = CURRENT_TIMESTAMP
                    WHERE profile_id = $1
                      AND (hour_reset_time IS NULL
                           OR hour_reset_time + INTERVAL '1 hour' <= CURRENT_TIMESTAMP)
                ''', profile_id)

                # Increment messages sent
                await conn.execute('''
                    UPDATE profiles
                    SET messages_sent_current_hour = messages_sent_current_hour + 1,
                        last_message_time = CURRENT_TIMESTAMP,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE profile_id = $1
                ''', profile_id)

    async def get_profile_messages_current_hour(self, profile_id: str) -> int:
        """Get number of messages sent by profile in current hour."""
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow('''
                SELECT messages_sent_current_hour, hour_reset_time
                FROM profiles WHERE profile_id = $1
            ''', profile_id)
            if not row:
                return 0
            # Check if hour has passed
            if row['hour_reset_time'] is None:
                return 0
            # asyncpg returns datetime objects
            from datetime import timezone
            now = datetime.now(timezone.utc)
            reset_time = row['hour_reset_time']
            if hasattr(reset_time, 'tzinfo') and reset_time.tzinfo is None:
                reset_time = reset_time.replace(tzinfo=timezone.utc)
            if (now - reset_time).total_seconds() >= 3600:
                return 0
            return row['messages_sent_current_hour'] or 0

    # ========================================
    # Tasks operations
    # ========================================

    async def import_chats(self, group_id: str, chat_usernames: List[str], total_cycles: int = 1) -> int:
        """Import chats as tasks."""
        count = 0
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                for username in chat_usernames:
                    if not username.startswith('@'):
                        username = f'@{username}'

                    await conn.execute('''
                        INSERT INTO tasks (group_id, chat_username, total_cycles)
                        VALUES ($1, $2, $3)
                        ON CONFLICT(group_id, chat_username) DO UPDATE SET
                            total_cycles = EXCLUDED.total_cycles
                    ''', group_id, username, total_cycles)
                    count += 1
        return count

    async def get_task_by_id(self, task_id: int) -> Optional[Dict[str, Any]]:
        """Get task by ID."""
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow("SELECT * FROM tasks WHERE id = $1", task_id)
            return dict(row) if row else None

    async def block_task(self, task_id: int, reason: str):
        """Mark task as blocked."""
        async with self._pool.acquire() as conn:
            await conn.execute('''
                UPDATE tasks
                SET is_blocked = TRUE,
                    block_reason = $1,
                    status = 'blocked',
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = $2
            ''', reason, task_id)

    async def increment_task_success(self, task_id: int):
        """Increment success counter."""
        async with self._pool.acquire() as conn:
            await conn.execute('''
                UPDATE tasks
                SET success_count = success_count + 1,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = $1
            ''', task_id)

    async def increment_task_failed(self, task_id: int):
        """Increment failed counter."""
        async with self._pool.acquire() as conn:
            await conn.execute('''
                UPDATE tasks
                SET failed_count = failed_count + 1,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = $1
            ''', task_id)

    async def increment_completed_cycles(self, task_id: int):
        """Increment completed cycles counter."""
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow('''
                UPDATE tasks
                SET completed_cycles = completed_cycles + 1,
                    last_attempt_at = CURRENT_TIMESTAMP,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = $1
                RETURNING completed_cycles, total_cycles
            ''', task_id)
            if row and row['completed_cycles'] >= row['total_cycles']:
                await conn.execute(
                    "UPDATE tasks SET status = 'completed' WHERE id = $1",
                    task_id
                )

    async def set_task_next_available(self, task_id: int, delay_seconds: int):
        """Set when task will be available again."""
        # Validate delay_seconds is an integer to prevent SQL injection
        delay_seconds = int(delay_seconds)
        async with self._pool.acquire() as conn:
            await conn.execute('''
                UPDATE tasks
                SET next_available_at = CURRENT_TIMESTAMP + make_interval(secs => $1),
                    status = 'pending',
                    assigned_profile_id = NULL
                WHERE id = $2
            ''', delay_seconds, task_id)

    async def reset_task_status(self, task_id: int):
        """Reset task status to pending."""
        async with self._pool.acquire() as conn:
            await conn.execute('''
                UPDATE tasks
                SET status = 'pending',
                    assigned_profile_id = NULL
                WHERE id = $1
            ''', task_id)

    async def get_task_stats(self) -> Dict[str, int]:
        """Get overall task statistics."""
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow('''
                SELECT
                    COUNT(*) as total,
                    SUM(CASE WHEN status = 'pending' THEN 1 ELSE 0 END) as pending,
                    SUM(CASE WHEN status = 'in_progress' THEN 1 ELSE 0 END) as in_progress,
                    SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) as completed,
                    SUM(CASE WHEN status = 'blocked' THEN 1 ELSE 0 END) as blocked,
                    SUM(success_count) as total_success,
                    SUM(failed_count) as total_failed
                FROM tasks
            ''')
            return dict(row) if row else {}

    async def get_pending_tasks_count(self, group_id: str) -> int:
        """Get count of pending tasks for a group."""
        async with self._pool.acquire() as conn:
            return await conn.fetchval('''
                SELECT COUNT(*) FROM tasks
                WHERE group_id = $1
                  AND status = 'pending'
                  AND is_blocked = FALSE
                  AND (next_available_at IS NULL OR next_available_at <= CURRENT_TIMESTAMP)
            ''', group_id)

    async def get_next_task(
        self,
        group_id: str,
        profile_id: str,
        run_id: str,
        max_cycles: int
    ) -> Optional[Dict[str, Any]]:
        """
        Atomically get and assign next available task.
        Returns None if no tasks available.
        """
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                # First, find a suitable task
                row = await conn.fetchrow('''
                    SELECT t.* FROM tasks t
                    WHERE t.group_id = $1
                      AND t.status = 'pending'
                      AND t.is_blocked = FALSE
                      AND (t.next_available_at IS NULL OR t.next_available_at <= CURRENT_TIMESTAMP)
                      AND NOT EXISTS (
                          SELECT 1 FROM task_attempts ta
                          WHERE ta.task_id = t.id
                            AND ta.run_id = $2
                            AND ta.status = 'success'
                      )
                      AND (
                          SELECT COUNT(*) FROM task_attempts ta
                          WHERE ta.task_id = t.id AND ta.run_id = $2
                      ) < $3
                    ORDER BY t.last_attempt_at ASC NULLS FIRST, t.id ASC
                    LIMIT 1
                    FOR UPDATE SKIP LOCKED
                ''', group_id, run_id, max_cycles)

                if not row:
                    return None

                task_id = row['id']

                # Assign the task
                await conn.execute('''
                    UPDATE tasks
                    SET status = 'in_progress',
                        assigned_profile_id = $1,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = $2
                ''', profile_id, task_id)

                return dict(row)

    # ========================================
    # Task attempts operations
    # ========================================

    async def add_task_attempt(
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
        async with self._pool.acquire() as conn:
            return await conn.fetchval('''
                INSERT INTO task_attempts (
                    task_id, profile_id, run_id, cycle_number, status,
                    message_text, error_type, error_message
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                RETURNING id
            ''', task_id, profile_id, run_id, cycle_number, status,
                message_text, error_type, error_message)

    async def get_task_attempts_count_by_run(
        self,
        task_id: int,
        run_id: str,
        status: Optional[str] = None
    ) -> int:
        """Get count of task attempts for specific run_id."""
        async with self._pool.acquire() as conn:
            if status:
                return await conn.fetchval('''
                    SELECT COUNT(*) FROM task_attempts
                    WHERE task_id = $1 AND run_id = $2 AND status = $3
                ''', task_id, run_id, status)
            else:
                return await conn.fetchval('''
                    SELECT COUNT(*) FROM task_attempts
                    WHERE task_id = $1 AND run_id = $2
                ''', task_id, run_id)

    # ========================================
    # Messages operations
    # ========================================

    async def import_messages(self, group_id: str, messages: List[str]) -> int:
        """Import messages for sending."""
        count = 0
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                for text in messages:
                    await conn.execute('''
                        INSERT INTO messages (group_id, text)
                        VALUES ($1, $2)
                    ''', group_id, text)
                    count += 1
        return count

    async def get_active_messages(self, group_id: str) -> List[str]:
        """Get all active messages for a group."""
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT text FROM messages WHERE group_id = $1 AND is_active = TRUE",
                group_id
            )
            return [row['text'] for row in rows]

    async def increment_message_usage(self, message_text: str):
        """Increment usage counter for message."""
        async with self._pool.acquire() as conn:
            await conn.execute('''
                UPDATE messages
                SET usage_count = usage_count + 1
                WHERE text = $1
            ''', message_text)

    # ========================================
    # Send log operations
    # ========================================

    async def log_send(
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
        async with self._pool.acquire() as conn:
            return await conn.fetchval('''
                INSERT INTO send_log (
                    group_id, task_id, profile_id, chat_username,
                    message_text, status, error_type, error_details
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                RETURNING id
            ''', group_id, task_id, profile_id, chat_username,
                message_text, status, error_type, error_details)

    # ========================================
    # Screenshots operations
    # ========================================

    async def add_screenshot(
        self,
        log_id: Optional[int],
        screenshot_type: str,
        file_name: str,
        description: Optional[str] = None
    ) -> int:
        """Record screenshot metadata."""
        async with self._pool.acquire() as conn:
            return await conn.fetchval('''
                INSERT INTO screenshots (log_id, screenshot_type, file_name, description)
                VALUES ($1, $2, $3, $4)
                RETURNING id
            ''', log_id, screenshot_type, file_name, description)

    async def cleanup_old_screenshots(self, days: int):
        """Delete screenshot records older than N days."""
        # Validate days is an integer to prevent SQL injection
        days = int(days)
        async with self._pool.acquire() as conn:
            await conn.execute('''
                DELETE FROM screenshots
                WHERE created_at < CURRENT_TIMESTAMP - make_interval(days => $1)
            ''', days)

    # ========================================
    # Group operations
    # ========================================

    async def clear_group_tasks(self, group_id: str):
        """Clear all tasks for a group."""
        async with self._pool.acquire() as conn:
            await conn.execute("DELETE FROM tasks WHERE group_id = $1", group_id)

    async def clear_group_messages(self, group_id: str):
        """Clear all messages for a group."""
        async with self._pool.acquire() as conn:
            await conn.execute("DELETE FROM messages WHERE group_id = $1", group_id)

    async def get_group_stats(self, group_id: str) -> Dict[str, Any]:
        """Get statistics for a group."""
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM group_stats WHERE group_id = $1",
                group_id
            )
            return dict(row) if row else {}

    async def get_all_groups(self) -> List[str]:
        """Get list of all group IDs."""
        async with self._pool.acquire() as conn:
            rows = await conn.fetch('''
                SELECT DISTINCT group_id FROM tasks
                UNION
                SELECT DISTINCT group_id FROM messages
            ''')
            return [row['group_id'] for row in rows]

    # ========================================
    # Profile statistics operations
    # ========================================

    async def update_profile_daily_stats(self, profile_id: str, success: bool = True):
        """Update daily statistics for profile."""
        today = datetime.now().date()
        async with self._pool.acquire() as conn:
            await conn.execute('''
                INSERT INTO profile_daily_stats (profile_id, date, messages_sent, successful_sends, failed_sends)
                VALUES ($1, $2, 1, $3, $4)
                ON CONFLICT(profile_id, date) DO UPDATE SET
                    messages_sent = profile_daily_stats.messages_sent + 1,
                    successful_sends = profile_daily_stats.successful_sends + $3,
                    failed_sends = profile_daily_stats.failed_sends + $4,
                    updated_at = CURRENT_TIMESTAMP
            ''', profile_id, today, 1 if success else 0, 0 if success else 1)

    async def get_profile_daily_stats(self, profile_id: str, days: int = 7) -> List[Dict[str, Any]]:
        """Get daily statistics for profile."""
        # Validate days is an integer to prevent SQL injection
        days = int(days)
        async with self._pool.acquire() as conn:
            rows = await conn.fetch('''
                SELECT * FROM profile_daily_stats
                WHERE profile_id = $1
                  AND date >= CURRENT_DATE - make_interval(days => $2)
                ORDER BY date DESC
            ''', profile_id, days)
            return [dict(r) for r in rows]

    async def get_all_profiles_daily_stats(self, days: int = 1) -> List[Dict[str, Any]]:
        """Get daily statistics for all profiles."""
        # Validate days is an integer to prevent SQL injection
        days = int(days)
        async with self._pool.acquire() as conn:
            rows = await conn.fetch('''
                SELECT
                    pds.*,
                    p.profile_name
                FROM profile_daily_stats pds
                JOIN profiles p ON p.profile_id = pds.profile_id
                WHERE pds.date >= CURRENT_DATE - make_interval(days => $1)
                ORDER BY pds.date DESC, p.profile_name
            ''', days)
            return [dict(r) for r in rows]

    # ========================================
    # Proxy operations
    # ========================================

    async def get_proxy_for_profile(self, profile_id: str) -> Optional[str]:
        """Get assigned proxy for profile."""
        async with self._pool.acquire() as conn:
            return await conn.fetchval('''
                SELECT proxy_url FROM proxy_assignments
                WHERE profile_id = $1 AND is_healthy = TRUE AND is_blocked = FALSE
            ''', profile_id)

    async def assign_proxy(self, proxy_url: str, profile_id: str):
        """Assign proxy to profile."""
        async with self._pool.acquire() as conn:
            await conn.execute('''
                INSERT INTO proxy_assignments (proxy_url, profile_id, assigned_at)
                VALUES ($1, $2, CURRENT_TIMESTAMP)
                ON CONFLICT(proxy_url) DO UPDATE SET
                    profile_id = $2,
                    assigned_at = CURRENT_TIMESTAMP
            ''', proxy_url, profile_id)

    async def release_proxy(self, profile_id: str):
        """Release proxy from profile."""
        async with self._pool.acquire() as conn:
            await conn.execute('''
                UPDATE proxy_assignments
                SET profile_id = NULL
                WHERE profile_id = $1
            ''', profile_id)

    async def get_available_proxy(self) -> Optional[str]:
        """Get available (unassigned, healthy) proxy."""
        async with self._pool.acquire() as conn:
            return await conn.fetchval('''
                SELECT proxy_url FROM proxy_assignments
                WHERE profile_id IS NULL
                  AND is_healthy = TRUE
                  AND is_blocked = FALSE
                ORDER BY last_rotation_at ASC NULLS FIRST
                LIMIT 1
            ''')

    async def mark_proxy_unhealthy(self, proxy_url: str):
        """Mark proxy as unhealthy."""
        async with self._pool.acquire() as conn:
            await conn.execute('''
                UPDATE proxy_assignments
                SET is_healthy = FALSE
                WHERE proxy_url = $1
            ''', proxy_url)

    async def mark_proxy_blocked(self, proxy_url: str):
        """Mark proxy as blocked."""
        async with self._pool.acquire() as conn:
            await conn.execute('''
                UPDATE proxy_assignments
                SET is_blocked = TRUE, is_healthy = FALSE
                WHERE proxy_url = $1
            ''', proxy_url)

    async def get_all_proxies(self) -> List[Dict[str, Any]]:
        """Get all proxies with their status."""
        async with self._pool.acquire() as conn:
            rows = await conn.fetch('''
                SELECT * FROM proxy_assignments
                ORDER BY created_at
            ''')
            return [dict(r) for r in rows]

    async def sync_proxies_from_file(self, proxies: List[str]) -> int:
        """Sync proxies from list to database."""
        count = 0
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                for proxy_url in proxies:
                    await conn.execute('''
                        INSERT INTO proxy_assignments (proxy_url)
                        VALUES ($1)
                        ON CONFLICT(proxy_url) DO NOTHING
                    ''', proxy_url)
                    count += 1
        return count

    # ========================================
    # Utility methods
    # ========================================

    async def __aenter__(self):
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()


# Global database instance
_db_instance: Optional[AsyncDatabase] = None


async def init_database(config) -> AsyncDatabase:
    """
    Initialize global database instance.

    Args:
        config: DatabaseConfig instance from config.py
    """
    global _db_instance
    _db_instance = AsyncDatabase(config)
    await _db_instance.connect()
    return _db_instance


def get_database() -> AsyncDatabase:
    """Get global database instance."""
    global _db_instance
    if _db_instance is None:
        raise RuntimeError("Database not initialized. Call await init_database() first.")
    return _db_instance


async def close_database():
    """Close global database instance."""
    global _db_instance
    if _db_instance:
        await _db_instance.close()
        _db_instance = None
