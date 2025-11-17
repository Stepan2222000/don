"""
Worker module for Telegram Automation System

Main worker loop that processes tasks from queue.
Each worker runs in a separate process with its own browser instance.
"""

import time
import argparse
import sys
from typing import Optional

from .config import load_config, get_config, DEFAULT_CONFIG_PATH
from .database import init_database, get_database
from .logger import init_logger, get_logger
from .profile_manager import get_profile_manager, init_profile_manager, DonutProfile
from .browser_automation import BrowserAutomation, BrowserAutomationSimplified
from .telegram_sender import TelegramSender
from .task_queue import get_task_queue
from .error_handler import ErrorHandler


class Worker:
    """Worker process for automated message sending."""

    def __init__(self, profile: DonutProfile, group_id: str, use_simplified: bool = True):
        """
        Initialize worker.

        Args:
            profile: DonutProfile to use for automation
            group_id: Campaign group ID to process tasks for
            use_simplified: Use simplified browser automation (faster)
        """
        self.profile = profile
        self.group_id = group_id
        self.use_simplified = use_simplified
        self.config = get_config()
        self.logger = get_logger()
        self.db = get_database()
        self.task_queue = get_task_queue()

        # Browser components (initialized in run())
        self.browser_automation = None
        self.telegram = None
        self.error_handler = None

        # Track current task for cleanup on interruption
        self.current_task_id = None

        # Track exit status
        self.exit_code = 0  # 0 = success, 1 = error
        self.exit_reason = "completed"  # Reason for exit

    def run(self):
        """
        Main worker loop.

        Process:
        1. Launch browser
        2. Navigate to Telegram
        3. Loop: Get task → Process → Record result → Delay
        4. Close browser when done
        """
        self.logger.log_worker_start(self.profile.profile_name, self.profile.profile_id)

        try:
            # Launch browser
            self.logger.info(f"Launching browser for profile: {self.profile.profile_name}")

            if self.use_simplified:
                self.browser_automation = BrowserAutomationSimplified()
            else:
                self.browser_automation = BrowserAutomation()

            page = self.browser_automation.launch_browser(
                self.profile,
                url=self.config.telegram.url
            )

            # Initialize Telegram sender and error handler
            self.telegram = TelegramSender(page)
            self.error_handler = ErrorHandler(
                self.profile.profile_id,
                self.profile.profile_name,
                page
            )

            # Browser automation now handles page loading and white page detection
            # No additional checks needed here
            self.logger.info(f"Worker ready: {self.profile.profile_name}")

            # Main processing loop
            while True:
                # Get next task from queue
                task = self.task_queue.get_next_incomplete_task(self.group_id, self.profile.profile_id)

                if task is None:
                    self.logger.info("No more tasks available. Worker finishing.")
                    break

                # Track current task for cleanup
                self.current_task_id = task['id']

                # Process task
                success = self._process_task(task)

                # Clear current task after processing
                self.current_task_id = None

                if success is None:
                    # Worker should stop (account frozen)
                    break

                # Calculate delay between messages
                if success:
                    delay = self.task_queue.calculate_delay()
                    self.logger.info(f"Waiting {delay:.1f} seconds before next message...")
                    time.sleep(delay)
                else:
                    # Small delay even on failure
                    time.sleep(2)

        except KeyboardInterrupt:
            self.logger.warning("Worker interrupted by user (Ctrl+C)")
            self.exit_code = 0  # Graceful shutdown
            self.exit_reason = "interrupted"
        except Exception as e:
            self.logger.log_worker_error(self.profile.profile_name, e)
            self.exit_code = 1  # Error exit
            self.exit_reason = "error"
        finally:
            # Cleanup current task if interrupted
            if self.current_task_id is not None:
                self.logger.info(f"Resetting interrupted task: {self.current_task_id}")
                try:
                    self.db.reset_task_status(self.current_task_id)
                except Exception as e:
                    self.logger.error(f"Failed to reset task status: {e}")

            # Cleanup browser
            if self.browser_automation:
                self.logger.info(f"Closing browser for profile: {self.profile.profile_name}")
                self.browser_automation.close_browser()

            # Cleanup database connection
            try:
                self.db.close()
            except Exception as e:
                self.logger.error(f"Failed to close database connection: {e}")

            self.logger.log_worker_stop(
                self.profile.profile_name,
                self.profile.profile_id,
                reason=self.exit_reason
            )

        return self.exit_code

    def _process_task(self, task: dict) -> Optional[bool]:
        """
        Process a single task.

        Args:
            task: Task dictionary from database

        Returns:
            True if success, False if failed, None if worker should stop
        """
        chat_username = task['chat_username']
        self.logger.log_task_start(chat_username, self.profile.profile_name)

        try:
            # Step 1: Search for chat
            chat_found = self.telegram.search_chat(chat_username)

            if not chat_found:
                # Chat not found - block task
                self.error_handler.handle_chat_not_found(task)
                self.logger.log_task_complete(chat_username, success=False)
                return False

            # Step 2: Open chat
            chat_opened = self.telegram.open_chat(chat_username)

            if not chat_opened:
                # Failed to open chat
                self.error_handler.handle_unexpected_error(
                    task,
                    Exception("Failed to open chat")
                )
                self.logger.log_task_complete(chat_username, success=False)
                return False

            # Step 3: Check chat restrictions
            restrictions = self.telegram.check_chat_restrictions()

            # Check for account frozen - TEMPORARILY DISABLED
            # if restrictions.get('account_frozen'):
            #     # Critical: Account is frozen - stop worker
            #     self.error_handler.handle_account_frozen(task)
            #     return None  # Signal to stop worker

            # Check if can send
            if not restrictions.get('can_send'):
                # Cannot send due to restrictions
                reason = restrictions.get('reason', 'unknown')
                self.error_handler.handle_send_restriction(task, reason)
                self.logger.log_task_complete(chat_username, success=False)
                return False

            # Step 4: Get random message
            message = self.task_queue.get_random_message(self.group_id)

            # Step 5: Send message
            sent = self.telegram.send_message(message)

            if not sent:
                # Failed to send
                self.error_handler.handle_unexpected_error(
                    task,
                    Exception("Failed to send message")
                )
                self.logger.log_task_complete(chat_username, success=False)
                return False

            # Step 6: Record success
            self.task_queue.mark_task_success(
                task_id=task['id'],
                profile_id=self.profile.profile_id,
                message_text=message
            )

            # Log success
            self.logger.log_success(
                self.profile.profile_name,
                chat_username,
                message
            )

            self.logger.log_task_complete(chat_username, success=True)
            return True

        except Exception as e:
            # Unexpected error
            self.error_handler.handle_unexpected_error(task, e)
            self.logger.log_task_complete(chat_username, success=False)
            return False


def main():
    """Worker entry point (for subprocess execution)."""
    parser = argparse.ArgumentParser(description="Telegram Automation Worker")
    parser.add_argument(
        '--profile-id',
        required=True,
        help="Profile UUID to use for automation"
    )
    parser.add_argument(
        '--group-id',
        required=True,
        help="Campaign group ID to process tasks for"
    )
    parser.add_argument(
        '--config',
        default=None,
        help="Path to config.yaml file (default: auto-detected)"
    )
    parser.add_argument(
        '--simplified',
        action='store_true',
        help="Use simplified browser automation"
    )

    args = parser.parse_args()

    try:
        # Load configuration
        config = load_config(args.config)

        # Initialize database
        init_database(config.database.absolute_path)

        # Initialize logger
        init_logger(
            log_dir="logs",
            level=config.logging.level,
            log_format=config.logging.format
        )

        logger = get_logger()

        # Initialize and get profile manager
        init_profile_manager()
        profile_manager = get_profile_manager()
        profile = profile_manager.get_profile_by_id(args.profile_id)

        if not profile:
            logger.error(f"Profile not found: {args.profile_id}")
            sys.exit(1)

        # Validate profile
        try:
            profile_manager.validate_profile(profile)
        except ValueError as e:
            logger.error(f"Profile validation failed: {e}")
            sys.exit(1)

        # Create and run worker
        worker = Worker(profile, args.group_id, use_simplified=args.simplified)
        exit_code = worker.run()
        sys.exit(exit_code)

    except KeyboardInterrupt:
        print("\nWorker stopped by user")
        sys.exit(0)
    except Exception as e:
        print(f"Fatal error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
