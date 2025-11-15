"""
Telegram Sender module for Telegram Automation System

Provides automation for Telegram Web (web.telegram.org/k) using Playwright.
Uses reliable selectors from SELECTORS.md documentation.
"""

from typing import Dict, Optional, Any
from playwright.sync_api import Page, TimeoutError as PlaywrightTimeout

from .logger import get_logger
from .config import get_config


# ========================================
# Telegram Web Selectors (⭐⭐⭐⭐⭐ Most Reliable)
# ========================================

class TelegramSelectors:
    """CSS selectors for Telegram Web K version."""

    # Search
    SEARCH_INPUT = "input.input-search-input"
    SEARCH_CLEAR_BUTTON = "button.input-search-clear"

    # Chat list
    CHAT_ELEMENT = "a.chatlist-chat[data-peer-id]"
    CHAT_TITLE = "span.peer-title"
    TOPBAR = ".topbar"

    # Message input
    MESSAGE_INPUT = "div.input-message-input[contenteditable='true']"
    SEND_BUTTON = "button.btn-send"

    # Error indicators
    FROZEN_TEXT = ".chat-input-frozen-text"
    JOIN_BUTTON = "button:has-text('JOIN'):not(.hide)"
    PREMIUM_BUTTON = "button:has-text('Premium'):not(.hide)"
    UNBLOCK_BUTTON = "button:has-text('Unblock'):not(.hide)"


class TelegramSender:
    """Telegram Web automation for sending messages."""

    def __init__(self, page: Page):
        """
        Initialize Telegram sender.

        Args:
            page: Playwright Page object (already on Telegram Web)
        """
        self.page = page
        self.config = get_config()
        self.logger = get_logger()

    def search_chat(self, chat_username: str, retry: int = 0, max_retries: int = 2) -> bool:
        """
        Search for chat by username with retry logic.

        Args:
            chat_username: Chat username (with or without @)
            retry: Current retry attempt (internal)
            max_retries: Maximum number of retry attempts

        Returns:
            True if chat found, False otherwise
        """
        # Ensure @ prefix
        if not chat_username.startswith('@'):
            chat_username = f'@{chat_username}'

        retry_suffix = f" (attempt {retry + 1}/{max_retries + 1})" if retry > 0 else ""
        self.logger.debug(f"Searching for chat: {chat_username}{retry_suffix}")

        try:
            # Find search input - wait for it to be visible first
            search_input = self.page.locator(TelegramSelectors.SEARCH_INPUT)

            try:
                search_input.wait_for(state="visible", timeout=10000)
            except PlaywrightTimeout:
                self.logger.warning(f"Search input not visible yet")
                if retry < max_retries:
                    self.logger.info(f"Retrying search after additional wait...")
                    self.page.wait_for_timeout(5000)
                    return self.search_chat(chat_username, retry + 1, max_retries)
                return False

            # Clear existing search (if button is visible)
            try:
                clear_button = self.page.locator(TelegramSelectors.SEARCH_CLEAR_BUTTON)
                if clear_button.is_visible():
                    clear_button.click(timeout=2000)
                    self.page.wait_for_timeout(500)
            except Exception:
                # Button not visible (search is already empty), continue
                pass

            # Click search input to focus
            search_input.click()
            self.page.wait_for_timeout(300)

            # Enter username - use fill for reliability
            search_input.fill(chat_username)

            # Trigger input event manually
            search_input.dispatch_event('input')

            # Wait longer for search results to load (5 seconds)
            self.page.wait_for_timeout(5000)

            self.logger.debug(f"Waiting for search results for: {chat_username}")

            # Wait for search results in search container
            # Search results appear in #search-container, not in main chatlist
            search_results_selector = "#search-container .search-super-content-chats .chatlist a.chatlist-chat[data-peer-id]"

            try:
                self.page.wait_for_selector(
                    search_results_selector,
                    timeout=self.config.timeouts.search_timeout * 1000
                )

                # Verify the chat is actually visible in search results
                chat_elements = self.page.locator(search_results_selector).all()
                self.logger.debug(f"Found {len(chat_elements)} chat elements in search results")

                if len(chat_elements) > 0:
                    self.logger.debug(f"Chat found: {chat_username}")
                    return True
                else:
                    self.logger.debug(f"Chat not found: {chat_username}")
                    return False

            except PlaywrightTimeout:
                self.logger.debug(f"Timeout waiting for search results: {chat_username}")
                # Log DOM state for debugging
                search_container = self.page.locator("#search-container")
                is_visible = search_container.is_visible() if search_container.count() > 0 else False
                self.logger.debug(f"Search container visible: {is_visible}")

                # Retry if available
                if retry < max_retries:
                    self.logger.info(f"Retrying search after timeout...")
                    self.page.wait_for_timeout(3000)
                    return self.search_chat(chat_username, retry + 1, max_retries)

                return False

        except Exception as e:
            self.logger.error(f"Error searching chat {chat_username}: {e}")

            # Retry on error if available
            if retry < max_retries:
                self.logger.info(f"Retrying search after error...")
                self.page.wait_for_timeout(3000)
                return self.search_chat(chat_username, retry + 1, max_retries)

            return False

    def open_chat(self, chat_username: str) -> bool:
        """
        Open chat after search.

        Args:
            chat_username: Chat username

        Returns:
            True if chat opened successfully
        """
        # Ensure @ prefix
        if not chat_username.startswith('@'):
            chat_username = f'@{chat_username}'

        self.logger.debug(f"Opening chat: {chat_username}")

        try:
            # Find chat element by username in subtitle WITHIN search results container
            # In search results, username appears in div.row-subtitle, not span.peer-title
            chat_selector = f"#search-container .search-super-content-chats .chatlist a.chatlist-chat[data-peer-id]:has(div.row-subtitle:has-text('{chat_username}'))"

            self.logger.debug(f"Looking for chat with selector: {chat_selector}")

            # Wait for element to be visible
            try:
                self.page.wait_for_selector(chat_selector, timeout=3000)
            except PlaywrightTimeout:
                self.logger.error(f"Chat element not found: {chat_username}")
                return False

            chat_element = self.page.locator(chat_selector).first

            # Check if element exists
            if chat_element.count() == 0:
                self.logger.error(f"Chat element count is 0: {chat_username}")
                return False

            # Click the chat element directly
            self.logger.debug(f"Clicking chat element for: {chat_username}")
            chat_element.click()
            self.page.wait_for_timeout(500)

            # Wait for topbar to appear (indicates chat opened)
            try:
                self.page.wait_for_selector(
                    TelegramSelectors.TOPBAR,
                    timeout=5000
                )
                self.logger.debug(f"Chat opened: {chat_username}")
                return True

            except PlaywrightTimeout:
                self.logger.error(f"Failed to open chat: {chat_username}")
                return False

        except Exception as e:
            self.logger.error(f"Error opening chat {chat_username}: {e}")
            return False

    def check_chat_restrictions(self) -> Dict[str, Any]:
        """
        Check for chat restrictions (frozen account, need to join, etc.).

        Returns:
            Dict with:
                - can_send: bool - Whether message can be sent
                - account_frozen: bool - Whether account is frozen
                - reason: str - Reason if can't send (None if can send)
        """
        restrictions = {
            'can_send': True,
            'account_frozen': False,
            'reason': None
        }

        try:
            # Check 1: Account frozen - TEMPORARILY DISABLED
            # frozen = self.page.locator(TelegramSelectors.FROZEN_TEXT)
            # if frozen.count() > 0:
            #     restrictions['can_send'] = False
            #     restrictions['account_frozen'] = True
            #     restrictions['reason'] = 'account_frozen'
            #     self.logger.warning("Account is frozen by Telegram")
            #     return restrictions

            # Check 2: Join channel if needed
            join_btn = self.page.locator(TelegramSelectors.JOIN_BUTTON)
            if join_btn.count() > 0:
                self.logger.info("JOIN button detected, attempting to join channel...")

                try:
                    # Click JOIN button with force to avoid auto-scroll issues
                    join_btn.first.click(force=True)
                    self.logger.debug("Clicked JOIN button")

                    # Wait for button to disappear (successful join)
                    try:
                        self.page.wait_for_selector(
                            TelegramSelectors.JOIN_BUTTON,
                            state="hidden",
                            timeout=10000
                        )
                        self.logger.info("Successfully joined channel")

                        # Wait for UI to stabilize after joining
                        self.page.wait_for_timeout(3000)

                        # Continue with other checks (don't return, button is gone now)

                    except PlaywrightTimeout:
                        # Button didn't disappear - join failed
                        self.logger.error("JOIN button did not disappear - join may have failed")
                        restrictions['can_send'] = False
                        restrictions['reason'] = 'need_to_join'
                        return restrictions

                except Exception as e:
                    self.logger.error(f"Error clicking JOIN button: {e}")
                    restrictions['can_send'] = False
                    restrictions['reason'] = 'need_to_join'
                    return restrictions

            # Check 3: Premium required
            premium_btn = self.page.locator(TelegramSelectors.PREMIUM_BUTTON)
            if premium_btn.count() > 0:
                restrictions['can_send'] = False
                restrictions['reason'] = 'premium_required'
                self.logger.debug("Premium subscription required")
                return restrictions

            # Check 4: User blocked
            unblock_btn = self.page.locator(TelegramSelectors.UNBLOCK_BUTTON)
            if unblock_btn.count() > 0:
                restrictions['can_send'] = False
                restrictions['reason'] = 'user_blocked'
                self.logger.debug("User is blocked")
                return restrictions

            # Check 5: Message input available
            message_input = self.page.locator(TelegramSelectors.MESSAGE_INPUT)
            if message_input.count() == 0:
                restrictions['can_send'] = False
                restrictions['reason'] = 'input_not_available'
                self.logger.debug("Message input not available")
                return restrictions

            # All checks passed
            self.logger.debug("No restrictions found, can send message")
            return restrictions

        except Exception as e:
            self.logger.error(f"Error checking restrictions: {e}")
            restrictions['can_send'] = False
            restrictions['reason'] = 'check_error'
            return restrictions

    def send_message(self, message_text: str) -> bool:
        """
        Send message in opened chat.

        Args:
            message_text: Message to send

        Returns:
            True if message sent successfully
        """
        self.logger.debug(f"Sending message: {message_text[:50]}...")

        try:
            # Wait for topbar (chat should be open)
            self.page.wait_for_selector(TelegramSelectors.TOPBAR, timeout=5000)

            # Find message input
            message_input = self.page.locator(TelegramSelectors.MESSAGE_INPUT).first

            # Check if input is available
            if message_input.count() == 0:
                self.logger.error("Message input not found")
                return False

            # Click on input to focus
            message_input.click()
            self.page.wait_for_timeout(300)

            # Enter message using JavaScript (most reliable for contenteditable)
            # Pass message as argument to prevent injection
            self.page.evaluate(
                """(messageText) => {
                    const input = document.querySelector('.input-message-input[contenteditable="true"]');
                    if (input) {
                        input.textContent = messageText;
                    }
                }""",
                message_text
            )

            # Trigger input event
            message_input.dispatch_event('input')
            self.page.wait_for_timeout(500)

            # Wait for send button to appear
            send_button = self.page.locator(TelegramSelectors.SEND_BUTTON)
            try:
                send_button.wait_for(state='visible', timeout=3000)
            except PlaywrightTimeout:
                self.logger.error("Send button did not appear")
                return False

            # Click send button
            send_button.click()
            self.page.wait_for_timeout(1000)

            self.logger.debug("Message sent successfully")
            return True

        except Exception as e:
            self.logger.error(f"Error sending message: {e}")
            return False

    def save_screenshot(self, screenshot_type: str, description: str) -> Optional[str]:
        """
        Save screenshot for debugging/error logging.

        Args:
            screenshot_type: Type (error/warning/debug)
            description: Description for filename

        Returns:
            Path to screenshot file or None if screenshots disabled
        """
        if not self.config.screenshots.enabled:
            return None

        # Check if we should take this type of screenshot
        if screenshot_type == 'error' and not self.config.screenshots.on_error:
            return None
        if screenshot_type == 'warning' and not self.config.screenshots.on_warning:
            return None
        if screenshot_type == 'debug' and not self.config.screenshots.on_debug:
            return None

        try:
            # Generate file path
            screenshot_path = self.logger.get_screenshot_path(screenshot_type, description)

            # Take screenshot
            self.page.screenshot(
                path=screenshot_path,
                full_page=self.config.screenshots.full_page,
                type=self.config.screenshots.format,
                quality=self.config.screenshots.quality if self.config.screenshots.format == 'jpeg' else None
            )

            self.logger.debug(f"Screenshot saved: {screenshot_path}")
            return screenshot_path

        except Exception as e:
            self.logger.error(f"Error saving screenshot: {e}")
            return None
