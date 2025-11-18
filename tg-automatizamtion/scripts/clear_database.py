#!/usr/bin/env python3
"""
Clear Database Script

Clears all data from database tables while preserving schema.
Useful for starting fresh campaigns.
"""

import sqlite3
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.config import load_config, DEFAULT_CONFIG_PATH


def clear_database(db_path: str, confirm: bool = True):
    """
    Clear all data from database tables.

    Args:
        db_path: Path to SQLite database file
        confirm: Ask for confirmation before clearing
    """
    print("=" * 60)
    print("DATABASE CLEAR: Remove all data from tables")
    print("=" * 60)
    print()

    # Check if database exists
    if not Path(db_path).exists():
        print(f"❌ Database not found: {db_path}")
        sys.exit(1)

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        # Get list of all tables
        cursor.execute("""
            SELECT name FROM sqlite_master
            WHERE type='table'
            AND name NOT LIKE 'sqlite_%'
            ORDER BY name
        """)
        tables = [row[0] for row in cursor.fetchall()]

        if not tables:
            print("No tables found in database.")
            return

        print(f"Found {len(tables)} tables:")
        for table in tables:
            cursor.execute(f"SELECT COUNT(*) FROM {table}")
            count = cursor.fetchone()[0]
            print(f"  - {table}: {count} rows")

        print()

        # Ask for confirmation
        if confirm:
            response = input("⚠️  Are you sure you want to DELETE ALL DATA? (yes/no): ")
            if response.lower() != 'yes':
                print("❌ Cancelled")
                sys.exit(0)

        print()
        print("Clearing tables...")

        # Disable foreign key constraints temporarily
        cursor.execute("PRAGMA foreign_keys=OFF")

        # Clear tables in correct order (to handle foreign keys)
        tables_to_clear = [
            'screenshots',
            'send_log',
            'task_attempts',
            'tasks',
            'messages',
            'profile_daily_stats',
            'profiles',
            'groups'
        ]

        cleared_count = 0
        for table in tables_to_clear:
            if table in tables:
                cursor.execute(f"DELETE FROM {table}")
                rows_deleted = cursor.rowcount
                print(f"  ✓ Cleared {table}: {rows_deleted} rows deleted")
                cleared_count += 1

        # Re-enable foreign key constraints
        cursor.execute("PRAGMA foreign_keys=ON")

        # Vacuum to reclaim space
        print()
        print("Optimizing database...")
        cursor.execute("VACUUM")

        conn.commit()

        print()
        print("=" * 60)
        print(f"✅ Successfully cleared {cleared_count} tables!")
        print("=" * 60)
        print()
        print("Database is now empty and ready for new data.")
        print("You can now:")
        print("  1. Import new chats: python -m src.main import-chats data/chats.txt")
        print("  2. Import messages: python -m src.main import-messages data/messages.json")
        print("  3. Add profiles: python -m src.main add-profile ProfileName")
        print()

    except Exception as e:
        print(f"❌ Error clearing database: {e}")
        conn.rollback()
        sys.exit(1)
    finally:
        conn.close()


def main():
    """Main entry point."""
    try:
        # Load config to get database path
        config = load_config(DEFAULT_CONFIG_PATH)
        db_path = config.database.absolute_path

        # Clear database with confirmation
        clear_database(db_path, confirm=True)

    except FileNotFoundError:
        print("❌ Config file not found")
        print("   Please create config first with: python -m src.main init")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
