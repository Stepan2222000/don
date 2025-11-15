#!/usr/bin/env python3
"""
Script to sync messages from groups.json to database.

Usage:
    # Interactive mode
    python scripts/sync_group_messages.py

    # CLI mode
    python scripts/sync_group_messages.py <group_id>
    python scripts/sync_group_messages.py --all
"""

import argparse
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.config import load_config, load_groups
from src.database import init_database
from interactive_utils import (
    show_header, show_menu, get_choice, get_input,
    show_groups, validate_group_exists
)


def sync_messages(group_id: str):
    """Sync messages from JSON to database for a group."""
    try:
        groups_data = load_groups()
    except FileNotFoundError:
        print("Error: No groups file found.")
        return False

    group = groups_data.get_group(group_id)
    if not group:
        print(f"Error: Group '{group_id}' not found.")
        return False

    if not group.messages:
        print(f"No messages in group '{group_id}' JSON config.")
        return True

    # Load config and database
    try:
        config = load_config()
    except FileNotFoundError:
        print("Error: config.yaml not found. Run: python -m src.main init")
        return False

    db = init_database(config.database.path)

    # Clear existing messages for this group
    db.clear_group_messages(group_id)

    # Import messages
    count = db.import_messages(group_id, group.messages)

    print(f"✓ Synced {count} message(s) to database for group '{group_id}'")
    return True


def sync_all_groups():
    """Sync messages for all groups."""
    try:
        groups_data = load_groups()
    except FileNotFoundError:
        print("Error: No groups file found.")
        return False

    success = True
    for group in groups_data.groups:
        if not sync_messages(group.id):
            success = False

    return success


def interactive_mode():
    """Interactive mode for syncing messages."""
    show_header("Синхронизация сообщений из groups.json в БД")

    # Show menu
    show_menu([
        (1, "Синхронизировать конкретную группу"),
        (2, "Синхронизировать все группы"),
        (0, "Выход")
    ])

    # Get user choice
    choice = get_choice("Ваш выбор: ", ["0", "1", "2"])

    if choice == "0":
        print("Выход.")
        return

    if choice == "1":
        # Sync specific group
        show_groups()
        group_id = get_input("Введите ID группы", validator=validate_group_exists)
        sync_messages(group_id)

    elif choice == "2":
        # Sync all groups
        sync_all_groups()


def main():
    # Check if running in interactive mode (no arguments)
    if len(sys.argv) == 1:
        interactive_mode()
        return

    # CLI mode with arguments
    parser = argparse.ArgumentParser(description="Sync messages from groups.json to database")
    parser.add_argument('group_id', nargs='?', help='Group ID to sync (or --all)')
    parser.add_argument('--all', action='store_true', help='Sync all groups')

    args = parser.parse_args()

    if args.all:
        if sync_all_groups():
            sys.exit(0)
        else:
            sys.exit(1)
    elif args.group_id:
        if sync_messages(args.group_id):
            sys.exit(0)
        else:
            sys.exit(1)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == '__main__':
    main()
