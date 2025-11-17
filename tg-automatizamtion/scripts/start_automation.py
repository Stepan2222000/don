#!/usr/bin/env python3
"""
Script to start Telegram automation for a campaign group.

Usage:
    # Interactive mode
    python scripts/start_automation.py

    # CLI mode
    python scripts/start_automation.py <group_id>
    python scripts/start_automation.py <group_id> --workers 2
    python scripts/start_automation.py <group_id> --all-profiles
"""

import argparse
import asyncio
import signal
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.config import load_config, load_groups
from src.database import init_database
from src.logger import init_logger, get_logger
from src.profile_manager import init_profile_manager, get_profile_manager
from src.task_queue import get_task_queue
from src.main import WorkerManager
from interactive_utils import (
    show_header, show_menu, get_choice, get_input,
    show_groups, validate_group_exists, list_groups, confirm
)


def start_group(group_id: str, workers: int = None, all_profiles: bool = False):
    """
    Start automation for a specific group.

    Args:
        group_id: Campaign group ID
        workers: Number of workers (None = all group profiles)
        all_profiles: Use all available profiles instead of group profiles
    """
    # Load groups
    try:
        groups_data = load_groups()
    except FileNotFoundError:
        print("Error: No groups file found. Create groups first with 'python scripts/manage_groups.py'", file=sys.stderr)
        return False

    # Get group
    group = groups_data.get_group(group_id)
    if not group:
        print(f"Error: Group '{group_id}' not found.", file=sys.stderr)
        return False

    # Load config and init
    config = load_config()

    # Merge group settings with base config
    config = group.get_merged_config(config)

    db = init_database(config.database.path)
    logger = init_logger(
        log_dir="logs",
        level=config.logging.level,
        log_format=config.logging.format
    )
    init_profile_manager()
    task_queue = get_task_queue()

    # Reset any stale tasks from previous crashes (for this group)
    logger.info(f"Resetting stale tasks for group '{group_id}'...")
    stale_count = task_queue.reset_stale_tasks(group_id=group_id)
    if stale_count > 0:
        logger.info(f"Reset {stale_count} stale tasks")

    # Get profiles for this group
    if all_profiles:
        # Use all active profiles from database
        profiles = db.get_active_profiles()
        logger.info("Using all available profiles (--all-profiles flag)")
    else:
        # Use profiles from group configuration
        profile_manager = get_profile_manager()
        profiles = []
        for profile_identifier in group.profiles:
            # Try to find by UUID first, then by name
            profile = profile_manager.get_profile_by_id(profile_identifier)
            if not profile:
                profile = profile_manager.get_profile_by_name(profile_identifier)

            if profile:
                # Check if profile is in database and active
                db_profile = db.get_profile_by_id(profile.profile_id)

                if db_profile:
                    # Profile exists in database
                    if db_profile.get('is_active', True):
                        profiles.append({'profile_id': profile.profile_id, 'profile_name': profile.profile_name})
                    else:
                        logger.warning(f"Profile {profile.profile_name} ({profile.profile_id}) is inactive in database")
                else:
                    # Profile not in database - add it automatically
                    logger.info(f"Auto-adding profile to database: {profile.profile_name}")
                    try:
                        profile_manager.validate_profile(profile)
                        db.add_profile(profile.profile_id, profile.profile_name)
                        profiles.append({'profile_id': profile.profile_id, 'profile_name': profile.profile_name})
                        logger.info(f"✓ Profile added: {profile.profile_name} ({profile.profile_id})")
                    except ValueError as e:
                        logger.error(f"Failed to add profile {profile.profile_name}: {e}")
            else:
                logger.warning(f"Profile '{profile_identifier}' from group not found in Donut Browser")

    if not profiles:
        print(f"Error: No active profiles for group '{group_id}'.", file=sys.stderr)
        return False

    # Limit workers if specified
    if workers:
        profiles = profiles[:workers]

    profile_ids = [p['profile_id'] for p in profiles]

    print(f"\n╔══════════════════════════════════════════════════════════════╗")
    print(f"║  Starting automation for group: {group_id:<31}║")
    print(f"║  Workers: {len(profile_ids):<52}║")
    print(f"╚══════════════════════════════════════════════════════════════╝")
    print(f"\nProfiles: {', '.join([p['profile_name'] for p in profiles])}\n")

    # Create worker manager
    manager = WorkerManager(profile_ids, group_id)

    # Setup signal handler for graceful shutdown
    def signal_handler(sig, frame):
        print("\n\nReceived interrupt signal. Stopping workers...")
        asyncio.create_task(manager.stop_all())

    signal.signal(signal.SIGINT, signal_handler)

    # Run workers
    try:
        asyncio.run(manager.start_all())
        print("\n✓ All workers finished successfully")
        return True
    except KeyboardInterrupt:
        print("\n\nStopped by user")
        return False
    except Exception as e:
        print(f"\nError: {e}", file=sys.stderr)
        logger.error(f"Fatal error: {e}", exc_info=True)
        return False


def interactive_mode():
    """Interactive mode for starting automation."""
    show_header("Запуск автоматизации рассылок")

    # Show available groups
    groups = list_groups()
    if not groups:
        print("Нет доступных групп.")
        print("Создайте группу с помощью: python scripts/manage_groups.py")
        return

    # Show menu
    show_menu([
        (1, "Запустить группу"),
        (0, "Выход")
    ])

    # Get user choice
    choice = get_choice("Ваш выбор: ", ["0", "1"])

    if choice == "0":
        print("Выход.")
        return

    if choice == "1":
        # Show available groups
        show_groups()

        # Get group ID
        group_id = get_input("Введите ID группы", validator=validate_group_exists)

        # Load group to show profiles
        groups_data = load_groups()
        group = groups_data.get_group(group_id)

        print(f"\nПрофили группы '{group_id}':")
        for profile_name in group.profiles:
            print(f"  - {profile_name}")
        print()

        # Ask for number of workers
        workers_input = get_input(
            f"Количество воркеров (Enter = все {len(group.profiles)} профилей)",
            allow_empty=True
        )
        workers = int(workers_input) if workers_input else None

        # Ask for all-profiles flag
        use_all_profiles = confirm("Использовать все доступные профили вместо профилей группы?", default=False)

        # Confirm start
        print(f"\n{'='*60}")
        print(f"Группа: {group_id}")
        print(f"Воркеров: {workers if workers else f'все ({len(group.profiles)})'}")
        print(f"Все профили: {'да' if use_all_profiles else 'нет'}")
        print(f"{'='*60}\n")

        if not confirm("Запустить автоматизацию?", default=True):
            print("Отменено.")
            return

        # Start automation
        start_group(group_id, workers=workers, all_profiles=use_all_profiles)


def main():
    # Check if running in interactive mode (no arguments)
    if len(sys.argv) == 1:
        interactive_mode()
        return

    # CLI mode with arguments
    parser = argparse.ArgumentParser(description="Start Telegram automation for a campaign group")
    parser.add_argument('group_id', help='Campaign group ID to run')
    parser.add_argument('--workers', type=int, help='Number of workers (default: all group profiles)')
    parser.add_argument('--all-profiles', action='store_true', help='Use all available profiles instead of group profiles')

    args = parser.parse_args()

    if start_group(args.group_id, workers=args.workers, all_profiles=args.all_profiles):
        sys.exit(0)
    else:
        sys.exit(1)


if __name__ == '__main__':
    main()
