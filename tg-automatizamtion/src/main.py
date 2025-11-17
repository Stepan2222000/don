"""
Main CLI module for Telegram Automation System

Provides command-line interface for managing profiles, tasks, and automation.
"""

import argparse
import sys
import json
import asyncio
import signal
import time
from pathlib import Path
from typing import List, Optional

from .config import load_config, create_default_config, get_config, load_groups, DEFAULT_CONFIG_PATH
from .database import init_database, get_database
from .logger import init_logger, get_logger
from .profile_manager import init_profile_manager, get_profile_manager
from .task_queue import get_task_queue

# Project root is parent of src/
PROJECT_ROOT = Path(__file__).parent.parent


class WorkerManager:
    """Manages multiple worker processes."""

    def __init__(self, profile_ids: List[str], group_id: str):
        """
        Initialize worker manager.

        Args:
            profile_ids: List of profile UUIDs to run as workers
            group_id: Campaign group ID
        """
        self.profile_ids = profile_ids
        self.group_id = group_id
        self.workers = {}  # profile_id -> Process
        self.stop_requested = False

        # Auto-restart configuration
        self.restart_counts = {}  # profile_id -> current restart count
        self.last_restart_times = {}  # profile_id -> timestamp of last restart
        self.max_restart_attempts = 5  # Maximum restart attempts before giving up
        self.restart_delay = 30  # Base delay in seconds (exponential backoff)
        self.restart_cooldown = 3600  # Reset restart count after 1 hour of stable work

    async def start_single_worker(self, profile_id: str):
        """
        Start a single worker process for profile.

        This is the core worker launch logic, used by both initial start and restart.

        Args:
            profile_id: Profile UUID

        Returns:
            Process object
        """
        logger = get_logger()
        logger.info(f"Starting worker for profile: {profile_id}, group: {self.group_id}")

        process = await asyncio.create_subprocess_exec(
            sys.executable, "-m", "src.worker",
            "--profile-id", profile_id,
            "--group-id", self.group_id,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=PROJECT_ROOT
        )

        self.workers[profile_id] = process
        return process

    async def start_worker(self, profile_id: str):
        """
        Start worker process for profile (wrapper for start_single_worker).

        Args:
            profile_id: Profile UUID

        Returns:
            Process object
        """
        return await self.start_single_worker(profile_id)

    def _should_restart_worker(self, profile_id: str, exit_code: int) -> bool:
        """
        Determine if worker should be restarted based on exit code and restart history.

        Args:
            profile_id: Profile UUID
            exit_code: Process exit code

        Returns:
            True if worker should be restarted, False otherwise
        """
        logger = get_logger()

        # Don't restart if shutdown requested
        if self.stop_requested:
            logger.debug(f"Not restarting worker {profile_id}: shutdown requested")
            return False

        # Don't restart on success (exit code 0)
        if exit_code == 0:
            logger.debug(f"Not restarting worker {profile_id}: completed successfully (exit code 0)")
            return False

        # Don't restart on banned account (exit code 3)
        if exit_code == 3:
            logger.warning(f"Not restarting worker {profile_id}: account banned (exit code 3)")
            return False

        # Check restart cooldown period
        current_time = time.time()
        last_restart_time = self.last_restart_times.get(profile_id, 0)
        time_since_last_restart = current_time - last_restart_time

        # Reset restart count if enough time has passed (stable work)
        if time_since_last_restart > self.restart_cooldown:
            logger.debug(f"Resetting restart count for {profile_id} (stable work for {time_since_last_restart:.0f}s)")
            self.restart_counts[profile_id] = 0

        # Get current restart count
        restart_count = self.restart_counts.get(profile_id, 0)

        # Check if restart limit exceeded
        if restart_count >= self.max_restart_attempts:
            logger.error(
                f"Not restarting worker {profile_id}: restart limit exceeded "
                f"({restart_count}/{self.max_restart_attempts})"
            )
            return False

        # Can restart
        logger.info(f"Worker {profile_id} will be restarted (attempt {restart_count + 1}/{self.max_restart_attempts})")
        return True

    def _calculate_restart_delay(self, attempt: int) -> int:
        """
        Calculate restart delay with exponential backoff.

        Args:
            attempt: Current restart attempt number (0-indexed)

        Returns:
            Delay in seconds
        """
        # Exponential backoff: 30s, 60s, 120s, 240s, 300s (capped at 5 minutes)
        delay = min(self.restart_delay * (2 ** attempt), 300)
        return delay

    async def monitor_worker(self, profile_id: str, process):
        """
        Monitor worker and handle exit with auto-restart logic.

        Args:
            profile_id: Profile UUID
            process: Initial process object
        """
        logger = get_logger()
        current_process = process

        # Auto-restart loop
        while True:
            # Check if shutdown requested before any restart logic
            if self.stop_requested:
                logger.info(f"Shutdown requested, stopping monitor for worker {profile_id}")
                break

            # Wait for process to complete
            stdout, stderr = await current_process.communicate()
            exit_code = current_process.returncode

            # Log exit
            if exit_code != 0:
                logger.error(f"Worker {profile_id} exited with code {exit_code}")
                if stderr:
                    stderr_text = stderr.decode().strip()
                    if stderr_text:
                        logger.error(f"Worker {profile_id} stderr:\n{stderr_text}")
            else:
                logger.info(f"Worker {profile_id} finished successfully")

            # Check if should restart
            if not self._should_restart_worker(profile_id, exit_code):
                # Don't restart - exit monitor loop
                break

            # Get current restart count
            restart_count = self.restart_counts.get(profile_id, 0)

            # Calculate delay with exponential backoff
            delay = self._calculate_restart_delay(restart_count)
            logger.info(f"Restarting worker {profile_id} in {delay}s (attempt {restart_count + 1}/{self.max_restart_attempts})")

            # Wait before restart
            await asyncio.sleep(delay)

            # Check if shutdown was requested during delay
            if self.stop_requested:
                logger.info(f"Shutdown requested, not restarting worker {profile_id}")
                break

            # Increment restart count and update timestamp
            self.restart_counts[profile_id] = restart_count + 1
            self.last_restart_times[profile_id] = time.time()

            # Restart worker
            try:
                logger.info(f"Restarting worker {profile_id}...")
                current_process = await self.start_single_worker(profile_id)
            except Exception as e:
                logger.error(f"Failed to restart worker {profile_id}: {e}")
                break

        # Worker monitor loop exited
        logger.info(f"Monitor stopped for worker {profile_id}")

    async def start_all(self):
        """Start all workers."""
        tasks = []
        for profile_id in self.profile_ids:
            process = await self.start_worker(profile_id)
            task = asyncio.create_task(self.monitor_worker(profile_id, process))
            tasks.append(task)

        # Wait for all workers to finish
        await asyncio.gather(*tasks)

    async def stop_all(self):
        """Stop all workers."""
        logger = get_logger()
        logger.info("Stopping all workers...")

        # Set stop flag to prevent auto-restart
        self.stop_requested = True

        for profile_id, process in self.workers.items():
            if process.returncode is None:  # Still running
                logger.info(f"Terminating worker: {profile_id}")
                process.terminate()
                try:
                    await asyncio.wait_for(process.wait(), timeout=5.0)
                except asyncio.TimeoutError:
                    logger.warning(f"Worker {profile_id} did not stop, killing...")
                    process.kill()

        logger.info("All workers stopped")


def cmd_init(args):
    """Initialize database and create default config."""
    print("Initializing Telegram Automation System...")

    # Create default config if doesn't exist
    config_path = Path(DEFAULT_CONFIG_PATH)
    if not config_path.exists():
        print(f"Creating default configuration: {config_path}")
        create_default_config()
    else:
        print(f"Configuration file already exists: {config_path}")

    # Load config
    config = load_config()

    # Initialize database
    print(f"Initializing database: {config.database.absolute_path}")
    init_database(config.database.absolute_path)

    print("\n✓ Initialization complete!")
    print("\nNext steps:")
    print("  1. Edit config.yaml to adjust settings")
    print("  2. Import chats: python -m src.main import-chats data/chats.txt")
    print("  3. Import messages: python -m src.main import-messages data/messages.json")
    print("  4. Add profiles: python -m src.main add-profile <profile_name>")
    print("  5. Start automation: python -m src.main start")


def cmd_import_chats(args):
    """Import chats from file."""
    chats_file = Path(args.file)

    if not chats_file.exists():
        print(f"Error: File not found: {chats_file}", file=sys.stderr)
        sys.exit(1)

    # Load config and init
    config = load_config(args.config)
    db = init_database(config.database.absolute_path)

    # Read chats from file
    chats = []
    with open(chats_file, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#'):
                chats.append(line)

    if not chats:
        print("Error: No chats found in file", file=sys.stderr)
        sys.exit(1)

    # Import to database
    print(f"Importing {len(chats)} chats...")
    count = db.import_chats(chats, total_cycles=config.limits.max_cycles)

    print(f"✓ Imported {count} chats successfully")


def cmd_import_messages(args):
    """Import messages from JSON file."""
    messages_file = Path(args.file)

    if not messages_file.exists():
        print(f"Error: File not found: {messages_file}", file=sys.stderr)
        sys.exit(1)

    # Load config and init
    config = load_config(args.config)
    db = init_database(config.database.absolute_path)

    # Read messages from JSON
    with open(messages_file, 'r', encoding='utf-8') as f:
        messages = json.load(f)

    if not isinstance(messages, list):
        print("Error: Messages file must contain a JSON array", file=sys.stderr)
        sys.exit(1)

    if not messages:
        print("Error: No messages found in file", file=sys.stderr)
        sys.exit(1)

    # Import to database
    print(f"Importing {len(messages)} messages...")
    count = db.import_messages(messages)

    print(f"✓ Imported {count} messages successfully")


def cmd_add_profile(args):
    """Add profile to automation."""
    # Load config and init
    config = load_config(args.config)
    db = init_database(config.database.absolute_path)
    profile_manager = init_profile_manager()

    # Get profile by name or ID
    profile_names = args.profiles

    try:
        profiles = profile_manager.find_profiles_by_names(profile_names)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    # Add to database
    for profile in profiles:
        try:
            profile_manager.validate_profile(profile)
            db.add_profile(profile.profile_id, profile.profile_name)
            print(f"✓ Added profile: {profile.profile_name} ({profile.profile_id})")
        except ValueError as e:
            print(f"✗ Skipped {profile.profile_name}: {e}", file=sys.stderr)


def cmd_list_profiles(args):
    """List available profiles."""
    profile_manager = init_profile_manager()

    if args.db_only:
        # List profiles in database
        config = load_config(args.config)
        db = init_database(config.database.absolute_path)
        profiles = db.get_active_profiles()

        print(f"\nProfiles in database ({len(profiles)}):\n")
        print(f"{'Name':<20} {'ID':<36} {'Active':<8} {'Blocked':<8}")
        print("-" * 75)

        for profile in profiles:
            print(
                f"{profile['profile_name']:<20} "
                f"{profile['profile_id']:<36} "
                f"{'Yes' if profile['is_active'] else 'No':<8} "
                f"{'Yes' if profile['is_blocked'] else 'No':<8}"
            )
    else:
        # List all Donut Browser profiles
        profile_manager.print_profiles_table()


def cmd_start(args):
    """Start automation with workers."""
    # Load groups
    try:
        groups_data = load_groups()
    except FileNotFoundError:
        print("Error: No groups file found. Create groups first with 'python scripts/manage_groups.py'", file=sys.stderr)
        sys.exit(1)

    # Get group
    group = groups_data.get_group(args.group)
    if not group:
        print(f"Error: Group '{args.group}' not found.", file=sys.stderr)
        sys.exit(1)

    # Load config and init
    config = load_config(args.config)

    # Merge group settings with base config
    config = group.get_merged_config(config)

    db = init_database(config.database.absolute_path)
    logger = init_logger(
        log_dir="logs",
        level=config.logging.level,
        log_format=config.logging.format
    )
    init_profile_manager()
    task_queue = get_task_queue()

    # Reset any stale tasks from previous crashes (for this group)
    logger.info(f"Resetting stale tasks for group '{args.group}'...")
    stale_count = task_queue.reset_stale_tasks(group_id=args.group)
    if stale_count > 0:
        logger.info(f"Reset {stale_count} stale tasks")

    # Get profiles for this group
    if args.all_profiles:
        # Use all active profiles from database
        profiles = db.get_active_profiles()
        logger.info(f"Using all available profiles (--all-profiles flag)")
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
        print(f"Error: No active profiles for group '{args.group}'.", file=sys.stderr)
        sys.exit(1)

    # Limit workers if specified
    if args.workers:
        profiles = profiles[:args.workers]

    profile_ids = [p['profile_id'] for p in profiles]

    print(f"\n╔══════════════════════════════════════════════════════════════╗")
    print(f"║  Starting automation for group: {args.group:<31}║")
    print(f"║  Workers: {len(profile_ids):<52}║")
    print(f"╚══════════════════════════════════════════════════════════════╝")
    print(f"\nProfiles: {', '.join([p['profile_name'] for p in profiles])}\n")

    # Create worker manager
    manager = WorkerManager(profile_ids, args.group)

    # Run workers
    try:
        asyncio.run(manager.start_all())
    except KeyboardInterrupt:
        print("\n\nShutdown requested (Ctrl+C)...")
        print("Stopping all workers gracefully...")
        # Graceful shutdown of workers
        asyncio.run(manager.stop_all())
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        sys.exit(1)

    print("\n✓ Automation completed")


def cmd_status(args):
    """Show automation status."""
    # Load config and init
    config = load_config(args.config)
    init_logger(level=config.logging.level, log_format=config.logging.format)
    db = init_database(config.database.absolute_path)
    task_queue = get_task_queue()

    # Get queue stats
    stats = task_queue.get_queue_stats()

    print("\n" + "=" * 60)
    print("AUTOMATION STATUS")
    print("=" * 60)

    print(f"\nTasks Overview:")
    print(f"  Total tasks:     {stats.get('total', 0)}")
    print(f"  Pending:         {stats.get('pending', 0)} ({stats.get('pending_percent', 0):.1f}%)")
    print(f"  In Progress:     {stats.get('in_progress', 0)}")
    print(f"  Completed:       {stats.get('completed', 0)} ({stats.get('completed_percent', 0):.1f}%)")
    print(f"  Blocked:         {stats.get('blocked', 0)} ({stats.get('blocked_percent', 0):.1f}%)")

    print(f"\nResults:")
    print(f"  Total Success:   {stats.get('total_success', 0)}")
    print(f"  Total Failed:    {stats.get('total_failed', 0)}")

    # Profile stats
    profiles = db.get_active_profiles()
    if profiles:
        print(f"\nActive Profiles ({len(profiles)}):")
        for profile in profiles:
            status = "BLOCKED" if profile['is_blocked'] else "Active"
            print(f"  - {profile['profile_name']}: {status}")

    print("\n" + "=" * 60 + "\n")


def cmd_stop(args):
    """Stop all workers."""
    print("Note: Workers stop automatically when tasks are done.")
    print("To force stop, use Ctrl+C while automation is running.")


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Telegram Automation System",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    parser.add_argument(
        '--config',
        default=None,
        help="Path to config.yaml file (default: auto-detected)"
    )

    subparsers = parser.add_subparsers(dest='command', help='Available commands')

    # init command
    parser_init = subparsers.add_parser('init', help='Initialize database and config')

    # import-chats command
    parser_import_chats = subparsers.add_parser('import-chats', help='Import chats from file')
    parser_import_chats.add_argument('file', help='Path to chats file (one @username per line)')

    # import-messages command
    parser_import_messages = subparsers.add_parser('import-messages', help='Import messages from JSON')
    parser_import_messages.add_argument('file', help='Path to messages JSON file')

    # add-profile command
    parser_add_profile = subparsers.add_parser('add-profile', help='Add profile(s) for automation')
    parser_add_profile.add_argument('profiles', nargs='+', help='Profile name(s) to add')

    # list-profiles command
    parser_list_profiles = subparsers.add_parser('list-profiles', help='List available profiles')
    parser_list_profiles.add_argument('--db-only', action='store_true', help='Show only profiles in database')

    # start command
    parser_start = subparsers.add_parser('start', help='Start automation')
    parser_start.add_argument('--group', type=str, required=True, help='Campaign group ID to run')
    parser_start.add_argument('--workers', type=int, help='Number of workers (default: all group profiles)')
    parser_start.add_argument('--all-profiles', action='store_true', help='Use all available profiles instead of group profiles')

    # status command
    parser_status = subparsers.add_parser('status', help='Show automation status')

    # stop command
    parser_stop = subparsers.add_parser('stop', help='Stop automation')

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    # Route to command handlers
    commands = {
        'init': cmd_init,
        'import-chats': cmd_import_chats,
        'import-messages': cmd_import_messages,
        'add-profile': cmd_add_profile,
        'list-profiles': cmd_list_profiles,
        'start': cmd_start,
        'status': cmd_status,
        'stop': cmd_stop,
    }

    handler = commands.get(args.command)
    if handler:
        try:
            handler(args)
        except Exception as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
