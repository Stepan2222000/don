#!/usr/bin/env python3
"""
Script to reset database with new schema.

Usage:
    # Interactive mode (with confirmation)
    python scripts/reset_database.py

    # Force mode (no confirmation, for automation)
    python scripts/reset_database.py --force
"""

import sys
import argparse
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.config import load_config
import sqlite3
from interactive_utils import show_header, confirm

# Determine project root and paths
PROJECT_ROOT = Path(__file__).parent.parent
DEFAULT_SCHEMA_PATH = PROJECT_ROOT / "db" / "schema.sql"

def reset_database(skip_confirm: bool = False):
    """Delete and recreate database with new schema."""
    if not skip_confirm:
        show_header("⚠️  ВНИМАНИЕ: Сброс базы данных  ⚠️")
        print("Эта операция удалит ВСЕ данные из базы данных:")
        print("  - Все задачи (чаты)")
        print("  - Все сообщения")
        print("  - Всю статистику")
        print("  - Все логи отправок")
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

    db_path = Path(config.database.path)
    schema_path = DEFAULT_SCHEMA_PATH

    if not schema_path.exists():
        print(f"Error: Schema file not found: {schema_path}")
        return False

    # Delete old database files
    for suffix in ['', '-shm', '-wal']:
        old_file = Path(str(db_path) + suffix)
        if old_file.exists():
            old_file.unlink()
            print(f"✓ Deleted: {old_file}")

    # Create new database
    conn = sqlite3.connect(str(db_path))

    # Read and execute schema
    with open(schema_path, 'r', encoding='utf-8') as f:
        schema_sql = f.read()

    conn.executescript(schema_sql)
    conn.commit()
    conn.close()

    print(f"\n✓ Database recreated successfully: {db_path}")
    print("\nNext steps:")
    print("1. Add profiles: python scripts/manage_groups.py")
    print("2. Load chats: python scripts/manage_tasks.py")
    print("3. Sync messages: python scripts/sync_group_messages.py")

    return True


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
