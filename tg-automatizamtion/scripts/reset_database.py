#!/usr/bin/env python3
"""
Script to reset database with new schema (PostgreSQL version).

Usage:
    # Interactive mode (with confirmation)
    python scripts/reset_database.py

    # Force mode (no confirmation, for automation)
    python scripts/reset_database.py --force
"""

import sys
import asyncio
import argparse
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.config import load_config
from src.database import init_database
from interactive_utils import show_header, confirm

# Determine project root and paths
PROJECT_ROOT = Path(__file__).parent.parent
DEFAULT_SCHEMA_PATH = PROJECT_ROOT / "db" / "schema_postgresql.sql"


async def async_reset_database(skip_confirm: bool = False):
    """Delete all data and recreate tables with schema (async)."""
    if not skip_confirm:
        show_header("⚠️  ВНИМАНИЕ: Сброс базы данных  ⚠️")
        print("Эта операция удалит ВСЕ данные из базы данных:")
        print("  - Все задачи (чаты)")
        print("  - Все сообщения")
        print("  - Всю статистику")
        print("  - Все логи отправок")
        print("  - Все профили")
        print("  - Все прокси")
        print()

        if not confirm("Вы ДЕЙСТВИТЕЛЬНО хотите удалить все данные и пересоздать базу?"):
            print("Операция отменена.")
            return False

        # Double check
        print()
        confirmation = input("Введите 'DELETE' (заглавными буквами) для подтверждения: ")
        if confirmation != "DELETE":
            print("Операция отменена.")
            return False

    try:
        config = load_config()
    except FileNotFoundError:
        print("Error: config.yaml not found. Please create it first.")
        return False

    schema_path = DEFAULT_SCHEMA_PATH

    if not schema_path.exists():
        print(f"Error: Schema file not found: {schema_path}")
        return False

    print(f"\nConnecting to PostgreSQL: {config.database.postgresql.host}:{config.database.postgresql.port}...")
    db = await init_database(config.database)

    try:
        # Read schema file
        with open(schema_path, 'r', encoding='utf-8') as f:
            schema_sql = f.read()

        # Drop all tables first (in correct order due to foreign keys)
        print("Dropping existing tables...")
        tables_to_drop = [
            'screenshots',
            'send_log',
            'task_attempts',
            'tasks',
            'messages',
            'profile_daily_stats',
            'proxy_assignments',
            'profiles'
        ]

        # Also drop views
        views_to_drop = [
            'profile_stats',
            'task_progress',
            'group_stats'
        ]

        async with db._pool.acquire() as conn:
            # Drop views first
            for view in views_to_drop:
                try:
                    await conn.execute(f"DROP VIEW IF EXISTS {view} CASCADE")
                    print(f"  ✓ Dropped view: {view}")
                except Exception as e:
                    print(f"  ⚠ Could not drop view {view}: {e}")

            # Drop tables
            for table in tables_to_drop:
                try:
                    await conn.execute(f"DROP TABLE IF EXISTS {table} CASCADE")
                    print(f"  ✓ Dropped table: {table}")
                except Exception as e:
                    print(f"  ⚠ Could not drop table {table}: {e}")

            # Execute schema to recreate tables
            print("\nRecreating schema...")
            # Split schema into statements and execute each
            statements = [s.strip() for s in schema_sql.split(';') if s.strip()]
            for stmt in statements:
                if stmt:
                    try:
                        await conn.execute(stmt)
                    except Exception as e:
                        # Some statements might fail (like CREATE INDEX IF NOT EXISTS on existing index)
                        # This is expected in some cases
                        if 'already exists' not in str(e).lower():
                            print(f"  ⚠ Warning: {e}")

        print(f"\n✓ Database recreated successfully!")
        print("\nNext steps:")
        print("1. Add profiles: python scripts/manage_groups.py")
        print("2. Load chats: python scripts/manage_tasks.py")
        print("3. Sync messages: python scripts/sync_group_messages.py")

        return True

    except Exception as e:
        print(f"Error resetting database: {e}")
        return False
    finally:
        await db.close()


def reset_database(skip_confirm: bool = False):
    """Delete and recreate database with new schema."""
    return asyncio.run(async_reset_database(skip_confirm))


def main():
    parser = argparse.ArgumentParser(description="Reset database with new schema")
    parser.add_argument('--force', action='store_true', help='Skip confirmation (use with caution!)')

    args = parser.parse_args()

    if reset_database(skip_confirm=args.force):
        sys.exit(0)
    else:
        sys.exit(1)


if __name__ == '__main__':
    main()
