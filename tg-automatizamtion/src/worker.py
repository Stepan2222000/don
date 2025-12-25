"""
Worker module for Telegram Automation System (async version)

Main async worker loop that processes tasks from queue.
Each worker runs with its own browser instance.
"""

import asyncio
import argparse
import signal
import sys
from typing import Optional

# Global reference for signal handler
_current_worker = None
_shutdown_requested = False

from .config import load_config, get_config
from .database import init_database, get_database, close_database, AsyncDatabase
from .logger import init_logger, get_logger
from .profile_manager import get_profile_manager, init_profile_manager, DonutProfile
from .browser_automation import BrowserAutomationSimplified, QRCodePageDetectedError
from .telegram_sender import TelegramSender
from .task_queue import init_task_queue, AsyncTaskQueue
from .error_handler import AsyncErrorHandler
from .proxy_manager import init_proxy_manager, AsyncProxyManager


class AsyncWorker:
    """Async worker process for automated message sending."""

    def __init__(
        self,
        profile: DonutProfile,
        group_id: str,
        db: AsyncDatabase,
        task_queue: AsyncTaskQueue,
        proxy_manager: AsyncProxyManager,
        use_simplified: bool = True,
        run_id: Optional[str] = None
    ):
        """
        Initialize worker.

        Args:
            profile: DonutProfile to use for automation
            group_id: Campaign group ID to process tasks for
            db: AsyncDatabase instance
            task_queue: AsyncTaskQueue instance
            proxy_manager: AsyncProxyManager instance
            use_simplified: Use simplified browser automation (faster)
            run_id: Optional session ID for per-session cycle tracking
        """
        self.profile = profile
        self.group_id = group_id
        self.use_simplified = use_simplified
        self.run_id = run_id
        self.config = get_config()
        self.logger = get_logger()
        self.db = db
        self.task_queue = task_queue
        self.proxy_manager = proxy_manager

        # Browser components (initialized in run())
        self.browser_automation = None
        self.telegram = None
        self.error_handler = None

        # Proxy tracking
        self.current_proxy_url = None

        # Track current task for cleanup on interruption
        self.current_task_id = None

        # Track exit status
        self.exit_code = 0  # 0 = success, 1 = error
        self.exit_reason = "completed"  # Reason for exit

    async def run(self):
        """
        Main async worker loop.

        Process:
        1. Launch browser
        2. Navigate to Telegram
        3. Loop: Get task → Process → Record result → Delay
        4. Close browser when done
        """
        self.logger.log_worker_start(self.profile.profile_name, self.profile.profile_id)

        try:
            # Check if proxy should be disabled globally or for this profile
            proxy_disabled = (
                not self.config.proxy.enabled or
                self.profile.profile_id.lower() in [p.lower() for p in self.config.proxy.disabled_profiles]
            )

            # Get proxy for profile (only if not disabled)
            proxy = None
            if not proxy_disabled:
                proxy = await self.proxy_manager.get_or_assign_proxy(self.profile.profile_id)
                if proxy:
                    self.current_proxy_url = proxy.url
                    self.logger.info(f"Using proxy: {proxy.host}:{proxy.port}")
                else:
                    self.logger.warning("No proxy assigned to profile")
            else:
                if not self.config.proxy.enabled:
                    self.logger.info("Proxy disabled in config - running without proxy")
                else:
                    self.logger.info(f"Proxy disabled for profile: {self.profile.profile_id}")

            # Launch browser
            self.logger.info(f"Launching browser for profile: {self.profile.profile_name}")

            self.browser_automation = BrowserAutomationSimplified()

            page = await self.browser_automation.launch_browser(
                self.profile,
                url=self.config.telegram.url,
                proxy_override=proxy.playwright_url if proxy else None,
                disable_proxy=proxy_disabled
            )

            # Initialize Telegram sender and error handler
            self.telegram = TelegramSender(page)
            self.error_handler = AsyncErrorHandler(
                self.profile.profile_id,
                self.profile.profile_name,
                page,
                self.group_id,
                self.db,
                self.task_queue,
                self.run_id
            )

            self.logger.info(f"Worker ready: {self.profile.profile_name}")

            # Main processing loop
            while True:
                # Get next task from queue
                task = await self.task_queue.get_next_incomplete_task(
                    self.group_id,
                    self.profile.profile_id,
                    self.run_id
                )

                if task is None:
                    self.logger.info("No more tasks available. Worker finishing.")
                    break

                # Track current task for cleanup
                self.current_task_id = task['id']

                # Process task
                success = await self._process_task(task)

                # Clear current task after processing
                self.current_task_id = None

                if success is None:
                    # Worker should stop (account frozen)
                    break

                # Calculate delay between messages
                if success:
                    delay = self.task_queue.calculate_delay()
                    self.logger.info(f"Waiting {delay:.1f} seconds before next message...")
                    await asyncio.sleep(delay)
                else:
                    # Small delay even on failure
                    await asyncio.sleep(2)

        except QRCodePageDetectedError as e:
            # Session expired - QR code page detected
            self.logger.error(f"Session expired for {self.profile.profile_name}: {e}")
            # Mark profile as logged out in database
            await self.db.mark_profile_logged_out(self.profile.profile_id)
            self.exit_code = 4  # Session expired exit code (don't restart)
            self.exit_reason = "session_expired"
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
                    await self.db.reset_task_status(self.current_task_id)
                except Exception as e:
                    self.logger.error(f"Failed to reset task status: {e}")

            # Cleanup browser
            if self.browser_automation:
                self.logger.info(f"Closing browser for profile: {self.profile.profile_name}")
                await self.browser_automation.close_browser()

            self.logger.log_worker_stop(
                self.profile.profile_name,
                self.profile.profile_id,
                reason=self.exit_reason
            )

        return self.exit_code

    async def _process_task(self, task: dict) -> Optional[bool]:
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
            chat_found = await self.telegram.search_chat(chat_username)

            if not chat_found:
                # Chat not found - block task
                await self.error_handler.handle_chat_not_found(task)
                self.logger.log_task_complete(chat_username, success=False)
                return False

            # Step 2: Open chat
            chat_opened = await self.telegram.open_chat(chat_username)

            if not chat_opened:
                # Failed to open chat
                await self.error_handler.handle_unexpected_error(
                    task,
                    Exception("Failed to open chat")
                )
                self.logger.log_task_complete(chat_username, success=False)
                return False

            # Step 3: Check chat restrictions
            restrictions = await self.telegram.check_chat_restrictions()

            # Check if can send
            if not restrictions.get('can_send'):
                # Cannot send due to restrictions
                reason = restrictions.get('reason', 'unknown')
                await self.error_handler.handle_send_restriction(task, reason)
                self.logger.log_task_complete(chat_username, success=False)
                return False

            # Step 4: Get random message
            message = await self.task_queue.get_random_message(self.group_id)

            # Step 5: Send message
            sent = await self.telegram.send_message(message)

            if not sent:
                # Failed to send - check error type
                error_type = self.telegram.last_error_type

                if error_type == 'slow_mode_active':
                    # Slow Mode restriction detected
                    wait_duration = self.telegram.last_wait_duration

                    if wait_duration:
                        # Reschedule task
                        buffer_seconds = 30
                        total_wait = wait_duration + buffer_seconds
                        self.logger.warning(f"Slow Mode active. Rescheduling task for {total_wait}s")

                        # Set next available time (reschedule)
                        await self.db.set_task_next_available(task['id'], total_wait)

                        # Log event
                        await self.db.log_send(
                            group_id=self.group_id,
                            task_id=task['id'],
                            profile_id=self.profile.profile_id,
                            chat_username=chat_username,
                            message_text=None,
                            status='rescheduled',
                            error_type='slow_mode_wait',
                            error_details=f"Rescheduled for {total_wait}s"
                        )
                    else:
                        # Fallback if no time parsed
                        await self.error_handler.handle_send_restriction(
                            task,
                            restriction_reason='slow_mode_active',
                            error_details="Slow Mode active - time-based cooldown"
                        )
                else:
                    # Other send failure (unexpected error)
                    await self.error_handler.handle_unexpected_error(
                        task,
                        Exception("Failed to send message")
                    )

                self.logger.log_task_complete(chat_username, success=False)
                return False

            # Step 6: Record success
            await self.task_queue.mark_task_success(
                task_id=task['id'],
                profile_id=self.profile.profile_id,
                message_text=message,
                run_id=self.run_id
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
            await self.error_handler.handle_unexpected_error(task, e)
            self.logger.log_task_complete(chat_username, success=False)
            return False


async def async_main(args):
    """Async worker main function."""
    db = None
    try:
        # Load configuration
        config = load_config(args.config)

        # Initialize database
        db = await init_database(config.database)

        # Initialize logger
        init_logger(
            log_dir="logs",
            level=config.logging.level,
            log_format=config.logging.format
        )

        logger = get_logger()

        # Initialize task queue and proxy manager
        task_queue = init_task_queue(db)
        proxy_manager = init_proxy_manager(db)

        # Initialize and get profile manager
        init_profile_manager()
        profile_manager = get_profile_manager()
        profile = profile_manager.get_profile_by_id(args.profile_id)

        if not profile:
            logger.error(f"Profile not found: {args.profile_id}")
            return 1

        # Validate profile
        try:
            profile_manager.validate_profile(profile)
        except ValueError as e:
            logger.error(f"Profile validation failed: {e}")
            return 1

        # Create and run worker
        global _current_worker
        worker = AsyncWorker(
            profile=profile,
            group_id=args.group_id,
            db=db,
            task_queue=task_queue,
            proxy_manager=proxy_manager,
            use_simplified=args.simplified,
            run_id=args.run_id
        )
        _current_worker = worker  # Store for signal handler
        exit_code = await worker.run()
        return exit_code

    except KeyboardInterrupt:
        print("\nWorker stopped by user")
        return 0
    except Exception as e:
        print(f"Fatal error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 1
    finally:
        # Close database connection
        if db:
            await db.close()


def _handle_shutdown_signal(signum, frame):
    """Handle SIGTERM/SIGINT for graceful shutdown with video save."""
    global _shutdown_requested, _current_worker
    signal_name = 'SIGTERM' if signum == signal.SIGTERM else 'SIGINT'
    print(f"\n[SHUTDOWN] Received {signal_name}, saving video and closing browser...")
    _shutdown_requested = True

    # Try to close browser synchronously to save video
    if _current_worker and _current_worker.browser_automation:
        try:
            # Create new event loop for cleanup if needed
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(_current_worker.browser_automation.close_browser())
            loop.close()
            print("[SHUTDOWN] Browser closed, video saved!")
        except Exception as e:
            print(f"[SHUTDOWN] Error closing browser: {e}")

    sys.exit(0)


def main():
    """Worker entry point (for subprocess execution)."""
    # Register signal handlers for graceful shutdown (saves video)
    signal.signal(signal.SIGTERM, _handle_shutdown_signal)
    signal.signal(signal.SIGINT, _handle_shutdown_signal)

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
        default=True,
        help="Use simplified browser automation"
    )
    parser.add_argument(
        '--run-id',
        default=None,
        help="Session ID for per-session cycle tracking"
    )

    args = parser.parse_args()
    exit_code = asyncio.run(async_main(args))
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
