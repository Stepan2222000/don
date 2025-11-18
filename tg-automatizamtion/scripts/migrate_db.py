#!/usr/bin/env python3
"""
Database Migration Script

Migrates existing database to add run_id column to task_attempts table.
Safe to run multiple times (idempotent).
"""

import sqlite3
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.config import load_config, DEFAULT_CONFIG_PATH


def migrate_database(db_path: str):
    """
    Apply migration to add run_id column.

    Args:
        db_path: Path to SQLite database file
    """
    print(f"Migrating database: {db_path}")

    # Check if database exists
    if not Path(db_path).exists():
        print(f"❌ Database not found: {db_path}")
        print("   Please create database first with: python -m src.main init")
        sys.exit(1)

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        # Check if run_id column already exists
        cursor.execute("PRAGMA table_info(task_attempts)")
        columns = [row[1] for row in cursor.fetchall()]

        if 'run_id' in columns:
            print("✓ Migration already applied (run_id column exists)")
            return

        print("Applying migration...")

        # Read and execute migration SQL
        migration_path = Path(__file__).parent.parent / 'db' / 'migrate_add_run_id.sql'
        with open(migration_path, 'r') as f:
            migration_sql = f.read()

        cursor.executescript(migration_sql)
        conn.commit()

        print("✓ Migration completed successfully")
        print("  - Added run_id column to task_attempts")
        print("  - Created indexes for efficient queries")

    except Exception as e:
        print(f"❌ Migration failed: {e}")
        conn.rollback()
        sys.exit(1)
    finally:
        conn.close()


def main():
    """Main entry point."""
    print("=" * 60)
    print("DATABASE MIGRATION: Add run_id for per-session tracking")
    print("=" * 60)
    print()

    try:
        # Load config to get database path
        config = load_config(DEFAULT_CONFIG_PATH)
        db_path = config.database.absolute_path

        # Apply migration
        migrate_database(db_path)

        print()
        print("=" * 60)
        print("Migration completed successfully!")
        print("=" * 60)
        print()
        print("You can now use the new per-session cycle tracking feature.")
        print("Each 'python -m src.main start' will create a new session.")
        print()

    except FileNotFoundError:
        print("❌ Config file not found")
        print("   Please create config first with: python -m src.main init")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
