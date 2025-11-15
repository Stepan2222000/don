#!/usr/bin/env python3
"""
Script for managing campaign groups.

Usage:
    # Interactive mode
    python scripts/manage_groups.py

    # CLI mode
    python scripts/manage_groups.py create <group_id>
    python scripts/manage_groups.py list
    python scripts/manage_groups.py show <group_id>
    python scripts/manage_groups.py delete <group_id>
    python scripts/manage_groups.py add-profiles <group_id> <profile_name1> [<profile_name2> ...]
    python scripts/manage_groups.py add-messages <group_id> <message1> [<message2> ...]
    python scripts/manage_groups.py set-setting <group_id> <key> <value>
"""

import argparse
import sys
import json
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.config import load_groups, CampaignGroup, GroupsData
from src.profile_manager import get_profile_by_name
from interactive_utils import (
    show_header, show_menu, get_choice, get_input,
    show_groups, show_profiles, validate_group_exists,
    validate_not_empty, get_multiline_input, confirm
)


def create_group(group_id: str, groups_path: str = "data/groups.json"):
    """Create a new campaign group."""
    try:
        groups_data = load_groups(groups_path)
    except FileNotFoundError:
        groups_data = GroupsData(groups=[])

    # Check if group already exists
    if groups_data.get_group(group_id):
        print(f"Error: Group '{group_id}' already exists.")
        return False

    # Create new group
    new_group = CampaignGroup(id=group_id)
    groups_data.add_group(new_group)
    groups_data.save_to_file(groups_path)

    print(f"✓ Created group: {group_id}")
    return True


def list_groups(groups_path: str = "data/groups.json"):
    """List all campaign groups."""
    try:
        groups_data = load_groups(groups_path)
    except FileNotFoundError:
        print("No groups file found. Create a group first.")
        return

    if not groups_data.groups:
        print("No groups found.")
        return

    print("\nCampaign Groups:")
    print("=" * 80)
    for group in groups_data.groups:
        print(f"\nGroup ID: {group.id}")
        print(f"  Profiles: {len(group.profiles)}")
        print(f"  Messages: {len(group.messages)}")
        print(f"  Settings: {len(group.settings)} custom setting(s)")
        if group.settings:
            for key, value in group.settings.items():
                print(f"    - {key}: {value}")


def show_group(group_id: str, groups_path: str = "data/groups.json"):
    """Show detailed information about a group."""
    try:
        groups_data = load_groups(groups_path)
    except FileNotFoundError:
        print("No groups file found.")
        return

    group = groups_data.get_group(group_id)
    if not group:
        print(f"Error: Group '{group_id}' not found.")
        return

    print(f"\nGroup: {group.id}")
    print("=" * 80)

    print(f"\nProfiles ({len(group.profiles)}):")
    if group.profiles:
        for profile_id in group.profiles:
            print(f"  - {profile_id}")
    else:
        print("  (none)")

    print(f"\nMessages ({len(group.messages)}):")
    if group.messages:
        for i, msg in enumerate(group.messages, 1):
            print(f"  {i}. {msg[:100]}{'...' if len(msg) > 100 else ''}")
    else:
        print("  (none)")

    print(f"\nCustom Settings ({len(group.settings)}):")
    if group.settings:
        print(json.dumps(group.settings, indent=2))
    else:
        print("  (none - using defaults from config.yaml)")


def delete_group(group_id: str, groups_path: str = "data/groups.json"):
    """Delete a campaign group."""
    try:
        groups_data = load_groups(groups_path)
    except FileNotFoundError:
        print("No groups file found.")
        return

    if groups_data.remove_group(group_id):
        groups_data.save_to_file(groups_path)
        print(f"✓ Deleted group: {group_id}")
        print("Warning: Tasks and messages in database for this group are not deleted.")
    else:
        print(f"Error: Group '{group_id}' not found.")


def add_profiles(group_id: str, profile_names: list, groups_path: str = "data/groups.json"):
    """Add profiles to a group."""
    try:
        groups_data = load_groups(groups_path)
    except FileNotFoundError:
        print("No groups file found.")
        return

    group = groups_data.get_group(group_id)
    if not group:
        print(f"Error: Group '{group_id}' not found.")
        return

    # Look up profiles and get their IDs
    added = 0
    for name in profile_names:
        profile = get_profile_by_name(name)
        if profile:
            if profile.profile_id not in group.profiles:
                group.profiles.append(profile.profile_id)
                print(f"✓ Added profile: {name} ({profile.profile_id})")
                added += 1
            else:
                print(f"  Profile already in group: {name}")
        else:
            print(f"✗ Profile not found: {name}")

    if added > 0:
        groups_data.add_group(group)  # Update group
        groups_data.save_to_file(groups_path)
        print(f"\n✓ Added {added} profile(s) to group {group_id}")


def add_messages(group_id: str, messages: list, groups_path: str = "data/groups.json"):
    """Add messages to a group."""
    try:
        groups_data = load_groups(groups_path)
    except FileNotFoundError:
        print("No groups file found.")
        return

    group = groups_data.get_group(group_id)
    if not group:
        print(f"Error: Group '{group_id}' not found.")
        return

    for msg in messages:
        if msg not in group.messages:
            group.messages.append(msg)
            print(f"✓ Added message: {msg[:50]}...")

    groups_data.add_group(group)  # Update group
    groups_data.save_to_file(groups_path)
    print(f"\n✓ Added {len(messages)} message(s) to group {group_id}")


def set_setting(group_id: str, key: str, value: str, groups_path: str = "data/groups.json"):
    """Set a custom setting for a group."""
    try:
        groups_data = load_groups(groups_path)
    except FileNotFoundError:
        print("No groups file found.")
        return

    group = groups_data.get_group(group_id)
    if not group:
        print(f"Error: Group '{group_id}' not found.")
        return

    # Try to parse value as JSON for nested settings
    try:
        parsed_value = json.loads(value)
    except json.JSONDecodeError:
        # If not valid JSON, try to parse as int/float/bool/string
        if value.lower() == 'true':
            parsed_value = True
        elif value.lower() == 'false':
            parsed_value = False
        elif value.isdigit():
            parsed_value = int(value)
        else:
            try:
                parsed_value = float(value)
            except ValueError:
                parsed_value = value

    # Handle nested keys (e.g., "limits.max_messages_per_hour")
    if '.' in key:
        parts = key.split('.')
        if parts[0] not in group.settings:
            group.settings[parts[0]] = {}
        group.settings[parts[0]][parts[1]] = parsed_value
        print(f"✓ Set {key} = {parsed_value}")
    else:
        group.settings[key] = parsed_value
        print(f"✓ Set {key} = {parsed_value}")

    groups_data.add_group(group)  # Update group
    groups_data.save_to_file(groups_path)


def interactive_mode():
    """Interactive mode for managing campaign groups."""
    show_header("Управление группами рассылок")

    # Show menu
    show_menu([
        (1, "Создать группу (create)"),
        (2, "Показать все группы (list)"),
        (3, "Показать детали группы (show)"),
        (4, "Удалить группу (delete)"),
        (5, "Добавить профили в группу (add-profiles)"),
        (6, "Добавить сообщения в группу (add-messages)"),
        (7, "Изменить настройку группы (set-setting)"),
        (0, "Выход")
    ])

    # Get user choice
    choice = get_choice("Ваш выбор: ", ["0", "1", "2", "3", "4", "5", "6", "7"])

    if choice == "0":
        print("Выход.")
        return

    if choice == "1":
        # Create group
        group_id = get_input("Введите ID новой группы", validator=validate_not_empty)
        create_group(group_id)

    elif choice == "2":
        # List groups
        list_groups()

    elif choice == "3":
        # Show group details
        show_groups()
        group_id = get_input("Введите ID группы", validator=validate_group_exists)
        show_group(group_id)

    elif choice == "4":
        # Delete group
        show_groups()
        group_id = get_input("Введите ID группы", validator=validate_group_exists)
        if confirm(f"Вы уверены, что хотите удалить группу '{group_id}'?"):
            delete_group(group_id)
        else:
            print("Операция отменена.")

    elif choice == "5":
        # Add profiles
        show_groups()
        group_id = get_input("Введите ID группы", validator=validate_group_exists)
        show_profiles()
        print("\nВведите имена профилей (по одному на строку):")
        profile_names = get_multiline_input("")
        if profile_names:
            add_profiles(group_id, profile_names)
        else:
            print("Не указано ни одного профиля.")

    elif choice == "6":
        # Add messages
        show_groups()
        group_id = get_input("Введите ID группы", validator=validate_group_exists)
        print("\nВведите тексты сообщений (по одному на строку):")
        messages = get_multiline_input("")
        if messages:
            add_messages(group_id, messages)
        else:
            print("Не указано ни одного сообщения.")

    elif choice == "7":
        # Set setting
        show_groups()
        group_id = get_input("Введите ID группы", validator=validate_group_exists)

        print("\nПримеры настроек:")
        print("  limits.max_messages_per_hour")
        print("  limits.max_cycles")
        print("  telegram.headless")
        print("  timeouts.search_timeout")
        print()

        key = get_input("Введите ключ настройки", validator=validate_not_empty)
        value = get_input("Введите значение", validator=validate_not_empty)
        set_setting(group_id, key, value)


def main():
    # Check if running in interactive mode (no arguments)
    if len(sys.argv) == 1:
        interactive_mode()
        return

    # CLI mode with arguments
    parser = argparse.ArgumentParser(description="Manage campaign groups")
    subparsers = parser.add_subparsers(dest='command', help='Commands')

    # Create group
    create_parser = subparsers.add_parser('create', help='Create a new group')
    create_parser.add_argument('group_id', help='Group ID')

    # List groups
    subparsers.add_parser('list', help='List all groups')

    # Show group
    show_parser = subparsers.add_parser('show', help='Show group details')
    show_parser.add_argument('group_id', help='Group ID')

    # Delete group
    delete_parser = subparsers.add_parser('delete', help='Delete a group')
    delete_parser.add_argument('group_id', help='Group ID')

    # Add profiles
    add_profiles_parser = subparsers.add_parser('add-profiles', help='Add profiles to group')
    add_profiles_parser.add_argument('group_id', help='Group ID')
    add_profiles_parser.add_argument('profiles', nargs='+', help='Profile names')

    # Add messages
    add_messages_parser = subparsers.add_parser('add-messages', help='Add messages to group')
    add_messages_parser.add_argument('group_id', help='Group ID')
    add_messages_parser.add_argument('messages', nargs='+', help='Message texts')

    # Set setting
    set_setting_parser = subparsers.add_parser('set-setting', help='Set custom setting')
    set_setting_parser.add_argument('group_id', help='Group ID')
    set_setting_parser.add_argument('key', help='Setting key (e.g., limits.max_messages_per_hour)')
    set_setting_parser.add_argument('value', help='Setting value')

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    if args.command == 'create':
        create_group(args.group_id)
    elif args.command == 'list':
        list_groups()
    elif args.command == 'show':
        show_group(args.group_id)
    elif args.command == 'delete':
        delete_group(args.group_id)
    elif args.command == 'add-profiles':
        add_profiles(args.group_id, args.profiles)
    elif args.command == 'add-messages':
        add_messages(args.group_id, args.messages)
    elif args.command == 'set-setting':
        set_setting(args.group_id, args.key, args.value)


if __name__ == '__main__':
    main()
