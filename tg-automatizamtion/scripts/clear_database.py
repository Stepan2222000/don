#!/usr/bin/env python3
"""
Clear Database Script (async version for PostgreSQL)

Clears all data from database tables while preserving schema.
Useful for starting fresh campaigns.
"""

import asyncio
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.config import load_config, DEFAULT_CONFIG_PATH
from src.database import init_database


async def async_clear_database(confirm: bool = True):
    """
    Clear all data from database tables (async).

    Args:
        confirm: Ask for confirmation before clearing
    """
    print("=" * 60)
    print("DATABASE CLEAR: Remove all data from tables")
    print("=" * 60)
    print()

    try:
        config = load_config(DEFAULT_CONFIG_PATH)
    except FileNotFoundError:
        print("❌ Config file not found")
        print("   Please create config first with: python -m src.main init")
        return False

    db = await init_database(config.database)

    try:
        # Get list of all tables and their row counts
        tables_info = []
        tables = [
            'screenshots',
            'send_log',
            'task_attempts',
            'tasks',
            'messages',
            'profile_daily_stats',
            'proxy_assignments',
            'profiles'
        ]

        async with db._pool.acquire() as conn:
            for table in tables:
                try:
                    count = await conn.fetchval(f"SELECT COUNT(*) FROM {table}")
                    tables_info.append((table, count))
                except Exception:
                    pass  # Table might not exist

        if not tables_info:
            print("No tables found in database.")
            return True

        print(f"Found {len(tables_info)} tables:")
        for table, count in tables_info:
            print(f"  - {table}: {count} rows")

        print()

        # Ask for confirmation
        if confirm:
            response = input("⚠️  Are you sure you want to DELETE ALL DATA? (yes/no): ")
            if response.lower() != 'yes':
                print("❌ Cancelled")
                return False

        print()
        print("Clearing tables...")

        # Clear tables in correct order (to handle foreign keys)
        tables_to_clear = [
            'screenshots',
            'send_log',
            'task_attempts',
            'tasks',
            'messages',
            'profile_daily_stats',
            'proxy_assignments',
            'profiles'
        ]

        cleared_count = 0
        async with db._pool.acquire() as conn:
            for table in tables_to_clear:
                try:
                    result = await conn.execute(f"DELETE FROM {table}")
                    # Parse result like 'DELETE 5'
                    rows_deleted = int(result.split()[-1]) if result else 0
                    print(f"  ✓ Cleared {table}: {rows_deleted} rows deleted")
                    cleared_count += 1
                except Exception as e:
                    print(f"  ⚠ Skipped {table}: {e}")

        print()
        print("=" * 60)
        print(f"✅ Successfully cleared {cleared_count} tables!")
        print("=" * 60)
        print()
        print("Database is now empty and ready for new data.")
        print("You can now:")
        print("  1. Import new chats: python -m src.main import-chats data/chats.txt --group group_1")
        print("  2. Sync messages: python scripts/sync_group_messages.py --all")
        print("  3. Add profiles: python -m src.main add-profile ProfileName")
        print()
        return True

    except Exception as e:
        print(f"❌ Error clearing database: {e}")
        return False
    finally:
        await db.close()


def clear_database(confirm: bool = True):
    """Clear all data from database tables."""
    return asyncio.run(async_clear_database(confirm))


def main():
    """Main entry point."""
    try:
        if clear_database(confirm=True):
            sys.exit(0)
        else:
            sys.exit(1)
    except Exception as e:
        print(f"❌ Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
