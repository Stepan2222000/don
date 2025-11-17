#!/usr/bin/env python3
"""
Script for viewing profile statistics.

Usage:
    # Interactive mode
    python scripts/profile_stats.py

    # CLI mode
    python scripts/profile_stats.py all [--days N]
    python scripts/profile_stats.py show <profile_name> [--days N]
"""

import argparse
import sys
from pathlib import Path
from datetime import datetime

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.config import load_config
from src.database import init_database
from src.profile_manager import get_profile_by_name, get_all_profiles, print_profiles_table
from interactive_utils import (
    show_header, show_menu, get_choice, get_input, show_profiles
)


def show_all_stats(days: int = 1):
    """Show daily statistics for all profiles."""
    try:
        config = load_config()
    except FileNotFoundError:
        print("Error: config.yaml not found. Run: python -m src.main init")
        return

    db = init_database(config.database.absolute_path)

    # Get stats
    stats = db.get_all_profiles_daily_stats(days=days)

    if not stats:
        print(f"No statistics found for the last {days} day(s)")
        return

    print(f"\nProfile Statistics (last {days} day(s))")
    print("=" * 100)
    print(f"{'Profile Name':<30} {'Date':<12} {'Messages':<10} {'Success':<10} {'Failed':<10} {'Success Rate':<12}")
    print("=" * 100)

    for stat in stats:
        success_rate = 0
        if stat['messages_sent'] > 0:
            success_rate = (stat['successful_sends'] / stat['messages_sent']) * 100

        print(f"{stat['profile_name']:<30} {stat['date']:<12} {stat['messages_sent']:<10} "
              f"{stat['successful_sends']:<10} {stat['failed_sends']:<10} {success_rate:<11.1f}%")

    # Summary
    total_messages = sum(s['messages_sent'] for s in stats)
    total_success = sum(s['successful_sends'] for s in stats)
    total_failed = sum(s['failed_sends'] for s in stats)

    print("=" * 100)
    print(f"{'TOTAL':<30} {'':<12} {total_messages:<10} {total_success:<10} {total_failed:<10} "
          f"{(total_success / total_messages * 100) if total_messages > 0 else 0:<11.1f}%")


def show_profile_stats(profile_name: str, days: int = 7):
    """Show detailed statistics for a specific profile."""
    profile = get_profile_by_name(profile_name)
    if not profile:
        print(f"Error: Profile '{profile_name}' not found.")
        print("\nAvailable profiles:")
        print_profiles_table()
        return

    try:
        config = load_config()
    except FileNotFoundError:
        print("Error: config.yaml not found. Run: python -m src.main init")
        return

    db = init_database(config.database.absolute_path)

    # Get stats
    stats = db.get_profile_daily_stats(profile.profile_id, days=days)

    if not stats:
        print(f"No statistics found for profile '{profile_name}' in the last {days} day(s)")
        return

    print(f"\nStatistics for profile: {profile_name}")
    print(f"Profile ID: {profile.profile_id}")
    print(f"Period: last {days} day(s)")
    print("=" * 80)
    print(f"{'Date':<12} {'Messages Sent':<15} {'Successful':<15} {'Failed':<15} {'Success Rate':<15}")
    print("=" * 80)

    total_messages = 0
    total_success = 0
    total_failed = 0

    for stat in stats:
        success_rate = 0
        if stat['messages_sent'] > 0:
            success_rate = (stat['successful_sends'] / stat['messages_sent']) * 100

        print(f"{stat['date']:<12} {stat['messages_sent']:<15} {stat['successful_sends']:<15} "
              f"{stat['failed_sends']:<15} {success_rate:<14.1f}%")

        total_messages += stat['messages_sent']
        total_success += stat['successful_sends']
        total_failed += stat['failed_sends']

    print("=" * 80)
    overall_success_rate = (total_success / total_messages * 100) if total_messages > 0 else 0
    print(f"{'TOTAL':<12} {total_messages:<15} {total_success:<15} {total_failed:<15} {overall_success_rate:<14.1f}%")

    # Calculate daily average
    days_with_activity = len(stats)
    if days_with_activity > 0:
        avg_messages = total_messages / days_with_activity
        print(f"\nDaily Average: {avg_messages:.1f} messages/day")


def interactive_mode():
    """Interactive mode for viewing profile statistics."""
    show_header("Статистика профилей")

    # Show menu
    show_menu([
        (1, "Показать статистику всех профилей (all)"),
        (2, "Показать статистику конкретного профиля (show)"),
        (0, "Выход")
    ])

    # Get user choice
    choice = get_choice("Ваш выбор: ", ["0", "1", "2"])

    if choice == "0":
        print("Выход.")
        return

    if choice == "1":
        # Show all profiles stats
        days = get_input("Количество дней", default="1")
        try:
            days_int = int(days)
            show_all_stats(days_int)
        except ValueError:
            print("Ошибка: введите число")

    elif choice == "2":
        # Show specific profile stats
        show_profiles()
        profile_name = get_input("Введите имя профиля")
        days = get_input("Количество дней", default="7")
        try:
            days_int = int(days)
            show_profile_stats(profile_name, days_int)
        except ValueError:
            print("Ошибка: введите число")


def main():
    # Check if running in interactive mode (no arguments)
    if len(sys.argv) == 1:
        interactive_mode()
        return

    # CLI mode with arguments
    parser = argparse.ArgumentParser(description="View profile statistics")
    subparsers = parser.add_subparsers(dest='command', help='Commands')

    # Show all profiles
    all_parser = subparsers.add_parser('all', help='Show statistics for all profiles')
    all_parser.add_argument('--days', type=int, default=1, help='Number of days to show (default: 1)')

    # Show specific profile
    show_parser = subparsers.add_parser('show', help='Show statistics for a specific profile')
    show_parser.add_argument('profile_name', help='Profile name')
    show_parser.add_argument('--days', type=int, default=7, help='Number of days to show (default: 7)')

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    if args.command == 'all':
        show_all_stats(args.days)
    elif args.command == 'show':
        show_profile_stats(args.profile_name, args.days)


if __name__ == '__main__':
    main()
