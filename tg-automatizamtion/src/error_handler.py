"""
Error Handler module for Telegram Automation System

Handles 4 main error scenarios:
1. Chat not found
2. Account frozen (profile blocked by Telegram)
3. Cannot send message (need to join, premium required, etc.)
4. Network/unexpected errors
"""

from typing import Dict, Any, Optional
from playwright.sync_api import Page

from .config import get_config
from .database import get_database
from .logger import get_logger
from .task_queue import get_task_queue
from .telegram_sender import TelegramSender


class ErrorHandler:
    """Handles various error scenarios during automation."""

    def __init__(self, profile_id: str, profile_name: str, page: Page):
        """
        Initialize error handler.

        Args:
            profile_id: Profile UUID
            profile_name: Profile display name
            page: Playwright Page for screenshots
        """
        self.profile_id = profile_id
        self.profile_name = profile_name
        self.page = page
        self.config = get_config()
        self.db = get_database()
        self.logger = get_logger()
        self.task_queue = get_task_queue()
        self.telegram = TelegramSender(page)

    def handle_chat_not_found(self, task: Dict[str, Any]):
        """
        Handle Scenario 1: Chat not found.

        Actions:
        1. Save screenshot
        2. Log to failed_chats.log
        3. Record failed attempt
        4. Block task permanently
        5. Log to send_log

        Args:
            task: Task dictionary
        """
        chat_username = task['chat_username']

        self.logger.log_chat_not_found(self.profile_name, chat_username)

        # Save screenshot (warning level)
        screenshot_path = self.telegram.save_screenshot('warning', f'chat_not_found_{chat_username}')

        # Save screenshot metadata to database if taken
        if screenshot_path:
            log_id = self.db.log_send(
                task_id=task['id'],
                profile_id=self.profile_id,
                chat_username=chat_username,
                message_text=None,
                status='failed',
                error_type='chat_not_found',
                error_details=f"Chat {chat_username} not found in search results"
            )

            self.db.add_screenshot(
                log_id=log_id,
                screenshot_type='warning',
                file_name=screenshot_path.split('/')[-1],
                description=f"Chat not found: {chat_username}"
            )

        # Mark task as failed and block it
        self.task_queue.mark_task_failed(
            task_id=task['id'],
            profile_id=self.profile_id,
            error_type='chat_not_found',
            error_message=f"Chat {chat_username} not found in search results",
            should_block=True,
            block_reason='chat_not_found'
        )

        self.logger.info(f"Task blocked (chat not found): {chat_username}")

    def handle_account_frozen(self, task: Optional[Dict[str, Any]] = None) -> bool:
        """
        Handle Scenario 2: Account frozen by Telegram.

        Actions:
        1. Save screenshot
        2. Log error to main.log
        3. Block profile in database
        4. Log to send_log
        5. Return True to signal worker should stop

        Args:
            task: Current task (optional, if available)

        Returns:
            True (worker should stop)
        """
        self.logger.error(f"Profile {self.profile_name} is frozen by Telegram")

        # Save screenshot (error level)
        screenshot_path = self.telegram.save_screenshot('error', 'account_frozen')

        # Block profile in database
        self.db.block_profile(self.profile_id)

        # Log to send_log
        log_id = self.db.log_send(
            task_id=task['id'] if task else None,
            profile_id=self.profile_id,
            chat_username=task['chat_username'] if task else 'N/A',
            message_text=None,
            status='failed',
            error_type='account_frozen',
            error_details="Account is frozen by Telegram"
        )

        # Save screenshot metadata
        if screenshot_path:
            self.db.add_screenshot(
                log_id=log_id,
                screenshot_type='error',
                file_name=screenshot_path.split('/')[-1],
                description=f"Account frozen: {self.profile_name}"
            )

        self.logger.critical(f"Worker stopped: profile {self.profile_name} is blocked")
        return True  # Signal to stop worker

    def handle_send_restriction(
        self,
        task: Dict[str, Any],
        restriction_reason: str,
        error_details: Optional[str] = None
    ):
        """
        Handle Scenario 3: Cannot send message (restrictions).

        Possible reasons:
        - need_to_join: Need to join channel/group
        - premium_required: Premium subscription required
        - user_blocked: User is blocked
        - input_not_available: Input field not accessible

        Actions:
        1. Save screenshot (warning level)
        2. Log to failed_send.log
        3. Record failed attempt
        4. Increment completed cycles
        5. If last cycle, mark as completed

        Args:
            task: Task dictionary
            restriction_reason: Reason code
            error_details: Additional details (optional)
        """
        chat_username = task['chat_username']

        # Map reason to user-friendly message
        reason_messages = {
            'need_to_join': 'Cannot send - need to join channel',
            'premium_required': 'Cannot send - Premium subscription required',
            'user_blocked': 'Cannot send - user is blocked',
            'input_not_available': 'Cannot send - message input not available'
        }

        error_msg = reason_messages.get(restriction_reason, restriction_reason)
        self.logger.log_send_error(self.profile_name, chat_username, error_msg, error_details)

        # Save screenshot
        screenshot_path = self.telegram.save_screenshot('warning', f'{restriction_reason}_{chat_username}')

        # Save screenshot metadata if taken
        if screenshot_path:
            log_id = self.db.log_send(
                task_id=task['id'],
                profile_id=self.profile_id,
                chat_username=chat_username,
                message_text=None,
                status='failed',
                error_type=restriction_reason,
                error_details=error_details or error_msg
            )

            self.db.add_screenshot(
                log_id=log_id,
                screenshot_type='warning',
                file_name=screenshot_path.split('/')[-1],
                description=f"{restriction_reason}: {chat_username}"
            )

        # Mark as failed but don't block (might work in next cycle or with another profile)
        self.task_queue.mark_task_failed(
            task_id=task['id'],
            profile_id=self.profile_id,
            error_type=restriction_reason,
            error_message=error_details or error_msg,
            should_block=False  # Don't block, might work later
        )

        self.logger.debug(f"Task failed (restriction): {chat_username} - {restriction_reason}")

    def handle_unexpected_error(
        self,
        task: Dict[str, Any],
        exception: Exception
    ):
        """
        Handle Scenario 4: Unexpected/network errors.

        Actions:
        1. Save screenshot
        2. Log error to main.log
        3. Record failed attempt
        4. Check retry limit - block if exceeded
        5. Continue to next task or block permanently

        Args:
            task: Task dictionary
            exception: The exception that occurred
        """
        chat_username = task['chat_username']
        error_type = type(exception).__name__
        error_message = str(exception)

        # Get current failed count and check if should block
        current_failed_count = task.get('failed_count', 0)
        max_attempts = self.config.retry.max_attempts_before_block
        should_block = (current_failed_count + 1) >= max_attempts

        if should_block:
            self.logger.error(
                f"Max retries exceeded for {chat_username} ({current_failed_count + 1}/{max_attempts}): "
                f"{error_type}: {error_message}"
            )
            # Log to failed_chats.log
            self.logger.log_blocked_after_retries(
                self.profile_name,
                chat_username,
                current_failed_count + 1,
                f"{error_type}: {error_message}"
            )
        else:
            self.logger.error(
                f"Unexpected error for {chat_username} (attempt {current_failed_count + 1}/{max_attempts}): "
                f"{error_type}: {error_message}"
            )

        # Save screenshot (error level)
        screenshot_path = self.telegram.save_screenshot(
            'error',
            f'unexpected_{chat_username}_{error_type}'
        )

        # Save screenshot metadata if taken
        if screenshot_path:
            log_id = self.db.log_send(
                task_id=task['id'],
                profile_id=self.profile_id,
                chat_username=chat_username,
                message_text=None,
                status='failed',
                error_type='exception',
                error_details=f"{error_type}: {error_message}"
            )

            self.db.add_screenshot(
                log_id=log_id,
                screenshot_type='error',
                file_name=screenshot_path.split('/')[-1],
                description=f"Unexpected error: {chat_username} - {error_type}"
            )

        # Mark as failed and block if retry limit exceeded
        self.task_queue.mark_task_failed(
            task_id=task['id'],
            profile_id=self.profile_id,
            error_type='exception',
            error_message=f"{error_type}: {error_message}",
            should_block=should_block,
            block_reason='max_retries_exceeded' if should_block else None
        )

        if should_block:
            self.logger.info(f"Task blocked after {max_attempts} failed attempts: {chat_username}")
        else:
            self.logger.debug(f"Task failed (exception): {chat_username}")

    def handle_network_timeout(
        self,
        task: Dict[str, Any],
        operation: str,
        timeout_seconds: int
    ):
        """
        Handle network timeout errors.

        Args:
            task: Task dictionary
            operation: Operation that timed out (e.g., "search", "send")
            timeout_seconds: Timeout value in seconds
        """
        chat_username = task['chat_username']

        self.logger.error(
            f"Timeout during {operation} for {chat_username} (timeout: {timeout_seconds}s)"
        )

        # Save screenshot
        screenshot_path = self.telegram.save_screenshot(
            'error',
            f'timeout_{operation}_{chat_username}'
        )

        # Save screenshot metadata if taken
        if screenshot_path:
            log_id = self.db.log_send(
                task_id=task['id'],
                profile_id=self.profile_id,
                chat_username=chat_username,
                message_text=None,
                status='failed',
                error_type='timeout',
                error_details=f"Timeout during {operation} ({timeout_seconds}s)"
            )

            self.db.add_screenshot(
                log_id=log_id,
                screenshot_type='error',
                file_name=screenshot_path.split('/')[-1],
                description=f"Timeout: {operation} - {chat_username}"
            )

        # Mark as failed but don't block
        self.task_queue.mark_task_failed(
            task_id=task['id'],
            profile_id=self.profile_id,
            error_type='timeout',
            error_message=f"Timeout during {operation} ({timeout_seconds}s)",
            should_block=False
        )

        self.logger.debug(f"Task failed (timeout): {chat_username} - {operation}")
