#!/usr/bin/env python3
"""
Script for managing tasks (chats) in campaign groups.

Usage:
    # Interactive mode
    python scripts/manage_tasks.py

    # CLI mode
    python scripts/manage_tasks.py load <group_id> <file.txt>
    python scripts/manage_tasks.py clear <group_id>
    python scripts/manage_tasks.py stats <group_id>
"""

import argparse
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.config import load_config, load_groups
from src.database import init_database, get_database
from interactive_utils import (
    show_header, show_menu, get_choice, get_input,
    show_groups, validate_file_exists, validate_group_exists, confirm
)

# Determine project root and data path
PROJECT_ROOT = Path(__file__).parent.parent
DEFAULT_CHATS_FILE = PROJECT_ROOT / "data" / "chats.txt"


def load_tasks(group_id: str, file_path: str):
    """Load tasks from file into group."""
    try:
        groups_data = load_groups()
    except FileNotFoundError:
        print("Error: No groups file found. Create a group first.")
        return

    group = groups_data.get_group(group_id)
    if not group:
        print(f"Error: Group '{group_id}' not found.")
        return

    # Read chats from file
    chat_file = Path(file_path)
    if not chat_file.exists():
        print(f"Error: File not found: {file_path}")
        return

    with open(chat_file, 'r', encoding='utf-8') as f:
        chats = [line.strip() for line in f if line.strip() and not line.strip().startswith('#')]

    if not chats:
        print(f"Error: No chats found in {file_path}")
        return

    # Load config and initialize database
    try:
        config = load_config()
    except FileNotFoundError:
        print("Error: config.yaml not found. Run: python -m src.main init")
        return

    db = init_database(config.database.absolute_path)

    # Import chats into database
    count = db.import_chats(group_id, chats, total_cycles=1)

    print(f"✓ Loaded {count} chat(s) into group '{group_id}'")


def clear_tasks(group_id: str, skip_confirm: bool = False):
    """Clear all tasks from group."""
    try:
        groups_data = load_groups()
    except FileNotFoundError:
        print("Error: No groups file found.")
        return

    group = groups_data.get_group(group_id)
    if not group:
        print(f"Error: Group '{group_id}' not found.")
        return

    # Confirm (only in CLI mode)
    if not skip_confirm:
        confirm_input = input(f"Are you sure you want to clear all tasks from group '{group_id}'? (yes/no): ")
        if confirm_input.lower() != 'yes':
            print("Cancelled.")
            return

    # Load config and initialize database
    try:
        config = load_config()
    except FileNotFoundError:
        print("Error: config.yaml not found. Run: python -m src.main init")
        return

    db = init_database(config.database.absolute_path)

    # Clear tasks
    db.clear_group_tasks(group_id)

    print(f"✓ Cleared all tasks from group '{group_id}'")


def show_stats(group_id: str):
    """Show statistics for group."""
    try:
        groups_data = load_groups()
    except FileNotFoundError:
        print("Error: No groups file found.")
        return

    group = groups_data.get_group(group_id)
    if not group:
        print(f"Error: Group '{group_id}' not found.")
        return

    # Load config and initialize database
    try:
        config = load_config()
    except FileNotFoundError:
        print("Error: config.yaml not found. Run: python -m src.main init")
        return

    db = init_database(config.database.absolute_path)

    # Get stats
    stats = db.get_group_stats(group_id)

    if not stats:
        print(f"No statistics found for group '{group_id}'")
        return

    print(f"\nStatistics for group: {group_id}")
    print("=" * 80)
    print(f"Total tasks:       {stats.get('total_tasks', 0)}")
    print(f"Pending:           {stats.get('pending_tasks', 0)}")
    print(f"In progress:       {stats.get('in_progress_tasks', 0)}")
    print(f"Completed:         {stats.get('completed_tasks', 0)}")
    print(f"Blocked:           {stats.get('blocked_tasks', 0)}")
    print(f"\nSuccessful sends:  {stats.get('total_successful_sends', 0)}")
    print(f"Failed sends:      {stats.get('total_failed_sends', 0)}")
    print(f"\nMessage templates: {stats.get('message_templates_count', 0)}")


def interactive_mode():
    """Interactive mode for managing tasks."""
    show_header("Управление задачами (чатами) в группах")

    # Show menu
    show_menu([
        (1, "Загрузить чаты из файла (load)"),
        (2, "Очистить все чаты группы (clear)"),
        (3, "Показать статистику группы (stats)"),
        (0, "Выход")
    ])

    # Get user choice
    choice = get_choice("Ваш выбор: ", ["0", "1", "2", "3"])

    if choice == "0":
        print("Выход.")
        return

    # Show available groups
    show_groups()

    if choice == "1":
        # Load tasks
        group_id = get_input(
            "Введите ID группы",
            validator=validate_group_exists
        )
        # Always use data/chats.txt
        file_path = str(DEFAULT_CHATS_FILE)
        print(f"Используется файл: {file_path}")
        load_tasks(group_id, file_path)

    elif choice == "2":
        # Clear tasks
        group_id = get_input(
            "Введите ID группы",
            validator=validate_group_exists
        )
        if confirm(f"Вы уверены, что хотите очистить все чаты из группы '{group_id}'?"):
            clear_tasks(group_id, skip_confirm=True)
        else:
            print("Операция отменена.")

    elif choice == "3":
        # Show stats
        group_id = get_input(
            "Введите ID группы",
            validator=validate_group_exists
        )
        show_stats(group_id)


def main():
    # Check if running in interactive mode (no arguments)
    if len(sys.argv) == 1:
        interactive_mode()
        return

    # CLI mode with arguments
    parser = argparse.ArgumentParser(description="Manage tasks in campaign groups")
    subparsers = parser.add_subparsers(dest='command', help='Commands')

    # Load tasks
    load_parser = subparsers.add_parser('load', help='Load tasks from file')
    load_parser.add_argument('group_id', help='Group ID')
    load_parser.add_argument('file', help='Path to file with chat usernames')

    # Clear tasks
    clear_parser = subparsers.add_parser('clear', help='Clear all tasks from group')
    clear_parser.add_argument('group_id', help='Group ID')

    # Show stats
    stats_parser = subparsers.add_parser('stats', help='Show group statistics')
    stats_parser.add_argument('group_id', help='Group ID')

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    if args.command == 'load':
        load_tasks(args.group_id, args.file)
    elif args.command == 'clear':
        clear_tasks(args.group_id)
    elif args.command == 'stats':
        show_stats(args.group_id)


if __name__ == '__main__':
    main()
