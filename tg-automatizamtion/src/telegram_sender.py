"""
Telegram Sender module for Telegram Automation System (ASYNC VERSION)

Provides automation for Telegram Web (web.telegram.org/k) using Playwright async API.
Uses reliable selectors from SELECTORS.md documentation.
"""

from typing import Dict, Optional, Any
import re
from playwright.async_api import Page, TimeoutError as PlaywrightTimeout

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

    # Payment/Stars indicators
    STARS_BUTTON = "button:has-text('Stars'):not(.hide)"
    PAY_BUTTON = "button:has-text('Pay'):not(.hide)"
    STARS_POPUP = "div.popup:has-text('Stars')"


class TelegramSender:
    """Telegram Web automation for sending messages (ASYNC)."""

    def __init__(self, page: Page):
        """
        Initialize Telegram sender.

        Args:
            page: Playwright Page object (async, already on Telegram Web)
        """
        self.page = page
        self.config = get_config()
        self.logger = get_logger()
        self.last_error_type = None  # Track last error type for worker.py
        self.last_wait_duration = None  # Track wait duration for Slow Mode

    def _parse_wait_time(self, text: str) -> Optional[int]:
        """
        Parse wait time from string like '51:03', '1h 20m', '5s'.

        Args:
            text: Text containing time information

        Returns:
            Total seconds to wait or None if parsing failed
        """
        try:
            # Clean up text: remove newlines and extra spaces
            clean_text = re.sub(r'\s+', ' ', text).strip()
            self.logger.debug(f"Parsing time from text (cleaned): '{clean_text}' (original length: {len(text)})")

            # Try MM:SS format (e.g. 51:03)
            match = re.search(r'(?:in|через)\s*(\d+):(\d+)', clean_text, re.IGNORECASE)
            if match:
                minutes, seconds = map(int, match.groups())
                total = minutes * 60 + seconds
                self.logger.debug(f"Parsed MM:SS: {minutes}m {seconds}s = {total}s")
                return total

            # Try HH:MM:SS format
            match = re.search(r'(?:in|через)\s*(\d+):(\d+):(\d+)', clean_text, re.IGNORECASE)
            if match:
                hours, minutes, seconds = map(int, match.groups())
                total = hours * 3600 + minutes * 60 + seconds
                self.logger.debug(f"Parsed HH:MM:SS: {hours}h {minutes}m {seconds}s = {total}s")
                return total

            # Try text format (1h 20m, 5s, etc)
            total_seconds = 0
            found = False

            # Hours
            h_match = re.search(r'(\d+)\s*(?:h|ч|hours?|часов?)', clean_text, re.IGNORECASE)
            if h_match:
                total_seconds += int(h_match.group(1)) * 3600
                found = True

            # Minutes
            m_match = re.search(r'(\d+)\s*(?:m|м|min|minutes?|минут?)', clean_text, re.IGNORECASE)
            if m_match:
                total_seconds += int(m_match.group(1)) * 60
                found = True

            # Seconds
            s_match = re.search(r'(\d+)\s*(?:s|с|sec|seconds?|секунд?)', clean_text, re.IGNORECASE)
            if s_match:
                total_seconds += int(s_match.group(1))
                found = True

            if found:
                self.logger.debug(f"Parsed text format: {total_seconds}s")
                return total_seconds

            # Try looking for isolated MM:SS at the end of string if no other match
            simple_time = re.search(r'(\d+):(\d+)(?:\.|$)', clean_text)
            if simple_time:
                 minutes, seconds = map(int, simple_time.groups())
                 total = minutes * 60 + seconds
                 self.logger.debug(f"Parsed simple MM:SS: {minutes}m {seconds}s = {total}s")
                 return total

            return None

        except Exception as e:
            self.logger.error(f"Error parsing time string: {e}")
            return None

    async def _check_slow_mode_text(self) -> Optional[int]:
        """
        Check for Slow Mode text on page and parse wait time (ASYNC).

        Returns:
            Seconds to wait or None if not found
        """
        try:
            # Look for notification containing Slow Mode text
            # Using a broad locator to catch toasts, tooltips, or general messages
            locator = self.page.locator("text=/Slow Mode is active|Медленный режим активен/")

            if await locator.count() > 0:
                # Get the text from the element
                # We use first visible or just first
                element = locator.first
                if await element.is_visible():
                    text = await element.inner_text()
                    self.logger.warning(f"Found Slow Mode notification: '{text}'")
                    return self._parse_wait_time(text)

            return None

        except Exception as e:
            self.logger.debug(f"Error checking slow mode text: {e}")
            return None

    async def close_popups(self) -> bool:
        """
        Close any Telegram popups that might intercept pointer events (ASYNC).

        Used in search_chat() to ensure search interface is not blocked.
        NOT used in send_message() to allow Stars detection.

        Returns:
            True if popup was found and closed, False otherwise
        """
        try:
            # Close all active popups (including Stars)
            popup_selectors = [
                "div.popup.popup-stars.active",  # Stars popup with active class
                "div.popup:has-text('Stars')",   # Any popup mentioning Stars
                "div.popup.active",              # Any active popup
            ]

            for selector in popup_selectors:
                popup = self.page.locator(selector).first
                if await popup.count() > 0:
                    self.logger.debug(f"Found popup with selector: {selector}")

                    # Try to find and click close button
                    close_button = popup.locator("button.popup-close, button[aria-label='Close']").first
                    if await close_button.count() > 0:
                        await close_button.click(timeout=3000)
                        await self.page.wait_for_timeout(500)
                        self.logger.info("Closed popup successfully")
                        return True
                    else:
                        # Try pressing Escape key as fallback
                        await self.page.keyboard.press("Escape")
                        await self.page.wait_for_timeout(500)
                        self.logger.info("Closed popup using Escape key")
                        return True

            # No popup found
            return False

        except Exception as e:
            self.logger.debug(f"Error closing popup: {e}")
            # Try Escape key as final fallback
            try:
                await self.page.keyboard.press("Escape")
                await self.page.wait_for_timeout(300)
            except:
                pass
            return False

    async def click_with_retry(
        self,
        locator,
        element_name: str,
        max_retries: int = 3,
        timeout: int = 5000,
        force: bool = True,
        wait_after: int = 500
    ) -> bool:
        """
        Click element with retry logic and proper wait strategies (ASYNC).

        Args:
            locator: Playwright locator object
            element_name: Name for logging purposes
            max_retries: Maximum number of click attempts
            timeout: Timeout for each click attempt in ms
            force: Use force click to bypass actionability checks
            wait_after: Wait time after successful click in ms

        Returns:
            True if click succeeded, False otherwise
        """
        for attempt in range(max_retries):
            try:
                # Wait for element to be visible and attached
                await locator.wait_for(state="visible", timeout=timeout)
                await locator.wait_for(state="attached", timeout=timeout)

                # Perform click
                await locator.click(timeout=timeout, force=force)

                # Wait for click to register
                await self.page.wait_for_timeout(wait_after)

                self.logger.debug(f"Successfully clicked {element_name} (attempt {attempt + 1}/{max_retries})")
                return True

            except PlaywrightTimeout as e:
                if attempt < max_retries - 1:
                    self.logger.warning(
                        f"Click on {element_name} failed (attempt {attempt + 1}/{max_retries}): {e}. Retrying..."
                    )
                    await self.page.wait_for_timeout(1000)  # Wait before retry
                else:
                    self.logger.error(
                        f"Click on {element_name} failed after {max_retries} attempts: {e}"
                    )
                    return False

            except Exception as e:
                if attempt < max_retries - 1:
                    self.logger.warning(
                        f"Unexpected error clicking {element_name} (attempt {attempt + 1}/{max_retries}): {e}. Retrying..."
                    )
                    await self.page.wait_for_timeout(1000)
                else:
                    self.logger.error(
                        f"Unexpected error clicking {element_name} after {max_retries} attempts: {e}"
                    )
                    return False

        return False

    async def search_chat(self, chat_username: str, retry: int = 0, max_retries: int = 2) -> bool:
        """
        Search for chat by username with retry logic (ASYNC).

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
        await self._save_debug_snapshot(f"search_start_{chat_username.replace('@', '')}")

        # Close any popups that might intercept clicks
        await self.close_popups()

        try:
            # Find search input - wait for it to be visible first
            search_input = self.page.locator(TelegramSelectors.SEARCH_INPUT)

            try:
                await search_input.wait_for(state="visible", timeout=10000)
            except PlaywrightTimeout:
                self.logger.warning(f"Search input not visible yet")
                if retry < max_retries:
                    self.logger.info(f"Retrying search after additional wait...")
                    await self.page.wait_for_timeout(5000)
                    return await self.search_chat(chat_username, retry + 1, max_retries)
                return False

            # Clear existing search (if button is visible)
            try:
                clear_button = self.page.locator(TelegramSelectors.SEARCH_CLEAR_BUTTON)
                if await clear_button.is_visible():
                    await clear_button.click(timeout=2000)
                    await self.page.wait_for_timeout(500)
            except Exception:
                # Button not visible (search is already empty), continue
                pass

            # Click search input to focus
            await search_input.click(timeout=5000)
            await self.page.wait_for_timeout(500)  # Increased from 300ms

            # Enter username - use fill for reliability
            await search_input.fill(chat_username)

            # Trigger input event manually
            await search_input.dispatch_event('input')
            await self._save_debug_snapshot(f"search_input_filled_{chat_username.replace('@', '')}")

            # Wait longer for search results to load (5 seconds)
            await self.page.wait_for_timeout(5000)

            self.logger.debug(f"Waiting for search results for: {chat_username}")

            # ========================================
            # STEP 1: FIRST check if actual search results exist
            # This must be checked BEFORE "No results" UI detection
            # Because "Global search" can have results while "Messages" shows "No results"
            # ========================================
            search_results_selector = "#search-container .search-super-content-chats .chatlist a.chatlist-chat[data-peer-id]"

            try:
                # Quick check for existing results without timeout
                chat_elements = await self.page.locator(search_results_selector).all()
                self.logger.debug(f"[SEARCH] Found {len(chat_elements)} chat elements in search results")

                if len(chat_elements) > 0:
                    self.logger.debug(f"[SEARCH] ✓ Chat found: {chat_username} ({len(chat_elements)} results)")
                    await self._save_debug_snapshot(f"search_results_found_{chat_username.replace('@', '')}")
                    return True

                # ========================================
                # STEP 2: No results found - NOW check for "No results" UI
                # This avoids false positives when "Messages" shows "No results"
                # but "Global search" has actual chat results
                # ========================================
                self.logger.debug(f"[SEARCH] No chat elements found, checking for 'No results' UI...")

                no_results_detected = False
                try:
                    # Check for "No results" indicators in search container
                    no_results_selectors = [
                        '.no-results',  # Generic no-results class
                        'text="No results"',  # English text
                        'text="Попробуйте поискать"',  # Russian text "Try a different search term"
                        'text="Try a different search term"',  # English alternative
                        '#search-container .empty-search',  # Empty search state
                    ]

                    for selector in no_results_selectors:
                        if await self.page.locator(selector).count() > 0:
                            self.logger.debug(f"[SEARCH] 'No results' UI detected (selector: {selector})")
                            no_results_detected = True
                            break

                    if no_results_detected:
                        self.logger.info(f"[SEARCH] ✗ Chat {chat_username} does not exist - 'No results' confirmed. Skipping retries.")
                        await self._save_debug_snapshot(f"search_no_results_{chat_username.replace('@', '')}")
                        return False

                except Exception as e:
                    self.logger.debug(f"[SEARCH] Error checking for 'No results' UI: {e}")
                    # Continue with timeout logic if check fails

                # ========================================
                # STEP 3: No results AND no "No results" UI - wait with timeout
                # This handles cases where results are still loading
                # ========================================
                self.logger.debug(f"[SEARCH] No results yet and no 'No results' UI - waiting with timeout...")

                try:
                    await self.page.wait_for_selector(
                        search_results_selector,
                        timeout=self.config.timeouts.search_timeout * 1000
                    )

                    # Check again after timeout
                    chat_elements = await self.page.locator(search_results_selector).all()
                    self.logger.debug(f"[SEARCH] After timeout: found {len(chat_elements)} chat elements")

                    if len(chat_elements) > 0:
                        self.logger.debug(f"[SEARCH] ✓ Chat found after timeout: {chat_username}")
                        return True
                    else:
                        self.logger.debug(f"[SEARCH] ✗ Chat not found after timeout: {chat_username}")
                        await self._save_debug_snapshot(f"search_timeout_{chat_username.replace('@', '')}")
                        return False

                except PlaywrightTimeout:
                    self.logger.debug(f"[SEARCH] Timeout waiting for search results: {chat_username}")

                    # Retry if available
                    if retry < max_retries:
                        self.logger.info(f"[SEARCH] Retrying search after timeout (attempt {retry + 2}/{max_retries + 1})...")
                        await self.page.wait_for_timeout(3000)
                        return await self.search_chat(chat_username, retry + 1, max_retries)

                    self.logger.warning(f"[SEARCH] ✗ All retries exhausted for {chat_username}")
                    return False

            except Exception as e:
                self.logger.error(f"[SEARCH] Unexpected error during search: {e}")
                # Don't retry on unexpected errors during the check itself
                return False

        except Exception as e:
            self.logger.error(f"Error searching chat {chat_username}: {e}")

            # Retry on error if available
            if retry < max_retries:
                self.logger.info(f"Retrying search after error...")
                await self.page.wait_for_timeout(3000)
                return await self.search_chat(chat_username, retry + 1, max_retries)

            return False

    async def open_chat(self, chat_username: str) -> bool:
        """
        Open chat after search (ASYNC).

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
                await self.page.wait_for_selector(chat_selector, timeout=3000)
            except PlaywrightTimeout:
                self.logger.error(f"Chat element not found: {chat_username}")
                return False

            chat_element = self.page.locator(chat_selector).first

            # Check if element exists
            if await chat_element.count() == 0:
                self.logger.error(f"Chat element count is 0: {chat_username}")
                return False

            # Click the chat element with retry logic
            self.logger.debug(f"Clicking chat element for: {chat_username}")
            await self._save_debug_snapshot(f"open_chat_click_start_{chat_username.replace('@', '')}")

            # Use retry logic for clicking chat element
            for retry in range(3):
                # Click with force and proper waits
                click_success = await self.click_with_retry(
                    chat_element,
                    element_name=f"chat element ({chat_username})",
                    max_retries=1,  # Single attempt per outer retry
                    timeout=5000,
                    force=True,
                    wait_after=1000  # Increased from 500ms to 1000ms
                )

                if not click_success:
                    if retry < 2:
                        self.logger.warning(f"Chat click failed, retrying... (attempt {retry + 2}/3)")
                        await self.page.wait_for_timeout(1000)
                        continue
                    else:
                        self.logger.error(f"Failed to click chat element after 3 attempts")
                        return False

                # Wait for topbar to appear (indicates chat opened)
                try:
                    await self.page.wait_for_selector(
                        TelegramSelectors.TOPBAR,
                        timeout=5000
                    )
                    self.logger.debug(f"Chat opened successfully: {chat_username}")
                    await self._save_debug_snapshot(f"open_chat_success_{chat_username.replace('@', '')}")
                    return True

                except PlaywrightTimeout:
                    if retry < 2:
                        self.logger.warning(
                            f"Chat didn't open (topbar not found), retrying click... (attempt {retry + 2}/3)"
                        )
                        await self.page.wait_for_timeout(1000)
                    else:
                        self.logger.error(f"Failed to open chat after 3 attempts: {chat_username}")
                        return False

            return False

        except Exception as e:
            self.logger.error(f"Error opening chat {chat_username}: {e}")
            return False

    async def check_chat_restrictions(self) -> Dict[str, Any]:
        """
        Check for chat restrictions (frozen account, need to join, etc.) (ASYNC).

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
            await self._save_debug_snapshot("restrictions_check_start")
            # Check 1: Account frozen - TEMPORARILY DISABLED
            # frozen = self.page.locator(TelegramSelectors.FROZEN_TEXT)
            # if await frozen.count() > 0:
            #     restrictions['can_send'] = False
            #     restrictions['account_frozen'] = True
            #     restrictions['reason'] = 'account_frozen'
            #     self.logger.warning("Account is frozen by Telegram")
            #     return restrictions

            # Check 2: Join channel if needed
            join_btn = self.page.locator(TelegramSelectors.JOIN_BUTTON)
            if await join_btn.count() > 0 and await join_btn.first.is_visible():
                self.logger.info("JOIN button detected, attempting to join channel...")
                await self._save_debug_snapshot("restrictions_join_detected")

                # Use retry logic for JOIN button click
                join_success = False
                for retry in range(3):
                    try:
                        # Get first JOIN button locator
                        join_locator = join_btn.first

                        # Click with retry logic
                        click_success = await self.click_with_retry(
                            join_locator,
                            element_name="JOIN button",
                            max_retries=1,  # Single attempt per outer retry
                            timeout=5000,
                            force=True,  # Use force to avoid auto-scroll issues
                            wait_after=1000
                        )

                        if not click_success:
                            if retry < 2:
                                self.logger.warning(f"JOIN button click failed, retrying... (attempt {retry + 2}/3)")
                                await self.page.wait_for_timeout(1000)
                                continue
                            else:
                                self.logger.error("Failed to click JOIN button after 3 attempts")
                                restrictions['can_send'] = False
                                restrictions['reason'] = 'join_failed' # Changed from need_to_join
                                await self._save_debug_snapshot("restrictions_join_failed_click")
                                return restrictions

                        # Wait for button to disappear (successful join)
                        try:
                            await self.page.wait_for_selector(
                                TelegramSelectors.JOIN_BUTTON,
                                state="hidden",
                                timeout=10000
                            )
                            self.logger.info("Successfully joined channel")
                            await self._save_debug_snapshot("restrictions_join_success")

                            # Wait for UI to stabilize after joining
                            await self.page.wait_for_timeout(3000)

                            # Mark as successful and exit retry loop
                            join_success = True
                            break

                        except PlaywrightTimeout:
                            # Button didn't disappear - join may have failed
                            if retry < 2:
                                self.logger.warning(
                                    f"JOIN button still visible after click, retrying... (attempt {retry + 2}/3)"
                                )
                                await self.page.wait_for_timeout(1500)
                            else:
                                self.logger.error("JOIN button did not disappear after 3 attempts - join failed")
                                restrictions['can_send'] = False
                                restrictions['reason'] = 'join_failed' # Changed from need_to_join
                                return restrictions

                    except Exception as e:
                        if retry < 2:
                            self.logger.error(f"Error clicking JOIN button (attempt {retry + 1}/3): {e}. Retrying...")
                            await self.page.wait_for_timeout(1500)
                        else:
                            self.logger.error(f"Error clicking JOIN button after 3 attempts: {e}")
                            restrictions['can_send'] = False
                            restrictions['reason'] = 'join_failed' # Changed from need_to_join
                            return restrictions

                # Check if join was successful
                if not join_success:
                    restrictions['can_send'] = False
                    restrictions['reason'] = 'join_failed'
                    return restrictions

                # Continue with other checks (button is gone now)

            # Check 3: Premium required
            premium_btn = self.page.locator(TelegramSelectors.PREMIUM_BUTTON)
            if await premium_btn.count() > 0:
                restrictions['can_send'] = False
                restrictions['reason'] = 'premium_required'
                self.logger.debug("Premium subscription required")
                return restrictions

            # Check 3.5: Paid message (Telegram Stars required)
            # Check multiple indicators for reliability
            stars_btn = self.page.locator(TelegramSelectors.STARS_BUTTON)
            pay_btn = self.page.locator(TelegramSelectors.PAY_BUTTON)
            stars_popup = self.page.locator(TelegramSelectors.STARS_POPUP)

            if await stars_btn.count() > 0 or await pay_btn.count() > 0 or await stars_popup.count() > 0:
                restrictions['can_send'] = False
                restrictions['reason'] = 'paid_message_required'
                self.logger.debug("Paid message (Telegram Stars) required")
                return restrictions

            # Check 4: User blocked
            unblock_btn = self.page.locator(TelegramSelectors.UNBLOCK_BUTTON)
            if await unblock_btn.count() > 0:
                restrictions['can_send'] = False
                restrictions['reason'] = 'user_blocked'
                self.logger.debug("User is blocked")
                return restrictions

            # Check 5: Message input available
            message_input = self.page.locator(TelegramSelectors.MESSAGE_INPUT)
            if await message_input.count() == 0:
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

    async def _save_debug_snapshot(self, stage: str, force: bool = False) -> None:
        """
        Save a comprehensive debug snapshot (Screenshot + HTML) to the trash folder (ASYNC).

        Args:
            stage: Name of the current stage/event
            force: Whether to force save even if screenshots are disabled (default: False)
        """
        # Only save if enabled or forced (User requested "detailed logging... saved to separate folder")
        # We will treat this as a temporary "Deep Debug" mode requested by user.
        try:
            import os
            import datetime

            # Create trash directory
            trash_dir = "logs/debug_trash"
            os.makedirs(trash_dir, exist_ok=True)

            timestamp = datetime.datetime.now().strftime("%H%M%S_%f")[:9] # HHMMSS_mmm
            prefix = f"{timestamp}_{stage}"

            # 1. Save HTML
            try:
                html_path = os.path.join(trash_dir, f"{prefix}.html")
                html_content = await self.page.content()
                with open(html_path, "w", encoding="utf-8") as f:
                    f.write(html_content)
            except Exception as e:
                self.logger.error(f"Failed to save HTML snapshot for {stage}: {e}")

            # 2. Save Screenshot
            try:
                png_path = os.path.join(trash_dir, f"{prefix}.png")
                await self.page.screenshot(path=png_path)
            except Exception as e:
                self.logger.error(f"Failed to save Screenshot snapshot for {stage}: {e}")

            self.logger.debug(f"[SNAPSHOT] Saved {stage} to {trash_dir}")

        except Exception as e:
            self.logger.error(f"Critical error in _save_debug_snapshot: {e}")

    async def send_message(self, message_text: str) -> bool:
        """
        Send message in opened chat with Deep Debugging (ASYNC).

        Args:
            message_text: Message to send

        Returns:
            True if message sent successfully
        """
        self.logger.info(f"[SEND] Starting send process. Message len: {len(message_text)}")
        await self._save_debug_snapshot("01_start")

        self.last_wait_duration = None
        self.last_error_type = None

        try:
            # 1. Verify Chat Open
            self.logger.debug(f"[SEND] Waiting for topbar...")
            try:
                await self.page.wait_for_selector(TelegramSelectors.TOPBAR, timeout=5000)
                await self._save_debug_snapshot("02_topbar_found")
            except PlaywrightTimeout:
                self.logger.error("[SEND] Topbar not found (Chat not open?)")
                await self._save_debug_snapshot("02_topbar_missing", force=True)
                return False

            # 2. Find Input
            message_input = self.page.locator(TelegramSelectors.MESSAGE_INPUT).first
            if await message_input.count() == 0:
                self.logger.error("[SEND] Message input not found")
                await self._save_debug_snapshot("03_input_missing", force=True)
                return False

            await self._save_debug_snapshot("03_input_found")

            # 3. Pre-Type Checks (Stars & Slow Mode)
            self.logger.debug(f"[SEND] Performing pre-type checks...")

            # Check Stars in placeholder
            try:
                placeholder = await message_input.get_attribute('placeholder') or ""
                if '⭐' in placeholder or 'Stars' in placeholder:
                    self.logger.warning(f"[SEND] ✗ Stars detected in placeholder: '{placeholder}'")
                    await self._save_debug_snapshot("04_stars_detected_pre", force=True)
                    return False
            except Exception as e:
                self.logger.error(f"[SEND] Error checking placeholder: {e}")

            # Check Slow Mode (Preventive)
            slow_wait = await self._check_slow_mode_text()
            if slow_wait:
                self.logger.warning(f"[SEND] ✗ Slow Mode active before typing. Wait: {slow_wait}s")
                self.last_error_type = 'slow_mode_active'
                self.last_wait_duration = slow_wait
                await self._save_debug_snapshot("04_slow_mode_pre", force=True)
                return False

            # 4. Focus Input
            self.logger.debug(f"[SEND] Focusing input...")
            if not await self.click_with_retry(message_input, "message input", max_retries=3, force=True):
                self.logger.error("[SEND] Failed to click input")
                await self._save_debug_snapshot("05_focus_failed", force=True)
                return False

            await self._save_debug_snapshot("05_input_focused")

            # 5. Type Message
            self.logger.debug(f"[SEND] Typing message...")
            await self.page.evaluate("""(text) => {
                const el = document.querySelector('.input-message-input[contenteditable="true"]');
                if (el) el.textContent = text;
            }""", message_text)
            await message_input.dispatch_event('input')
            await self.page.wait_for_timeout(500)

            await self._save_debug_snapshot("06_message_typed")

            # 6. Post-Type Checks
            self.logger.debug(f"[SEND] Performing post-type checks...")

            # Check Stars again (Modal might appear)
            try:
                placeholder = await message_input.get_attribute('placeholder') or ""
                text = await message_input.inner_text() or ""
                if '⭐' in placeholder or 'Message for ⭐' in text:
                    self.logger.warning(f"[SEND] ✗ Stars detected after typing")
                    await self._save_debug_snapshot("07_stars_detected_post", force=True)
                    return False
            except: pass

            # Check Restrictions
            restrictions = await self.check_chat_restrictions()
            if not restrictions['can_send']:
                self.logger.warning(f"[SEND] ✗ Restriction detected: {restrictions['reason']}")
                await self._save_debug_snapshot(f"07_restriction_{restrictions['reason']}", force=True)
                return False

            # 7. Find Send Button
            self.logger.debug(f"[SEND] Waiting for Send button...")
            send_button = self.page.locator(TelegramSelectors.SEND_BUTTON)
            try:
                await send_button.wait_for(state='visible', timeout=3000)
                box = await send_button.bounding_box()
                self.logger.debug(f"[SEND] Button visible at {box}")
                await self._save_debug_snapshot("08_button_visible")
            except PlaywrightTimeout:
                # Check Slow Mode again
                slow_wait = await self._check_slow_mode_text()
                if slow_wait:
                    self.logger.warning(f"[SEND] ✗ Slow Mode hidden button. Wait: {slow_wait}s")
                    self.last_error_type = 'slow_mode_active'
                    self.last_wait_duration = slow_wait
                    await self._save_debug_snapshot("08_slow_mode_hidden_btn", force=True)
                    return False

                self.logger.error("[SEND] Send button missing")
                await self._save_debug_snapshot("08_button_missing", force=True)
                return False

            # 8. Click Send
            self.logger.debug(f"[SEND] Clicking Send...")
            try:
                await send_button.click(timeout=3000, force=True)
                await self.page.wait_for_timeout(500)
            except Exception as e:
                self.logger.warning(f"[SEND] Click failed: {e}")

            await self._save_debug_snapshot("09_clicked")

            # 9. Verify & Retry
            try:
                current_text = await message_input.inner_text()
                if not current_text or not current_text.strip():
                    self.logger.info("[SEND] ✓ Sent successfully (Standard)")
                    await self._save_debug_snapshot("10_success_standard")
                    return True

                self.logger.warning(f"[SEND] Text remains: '{current_text[:20]}...'. Retrying with JS...")
                await self._save_debug_snapshot("09_click_failed_retry_js", force=True)

                # JS Click Retry
                await self.page.evaluate("""
                    const btn = document.querySelector('button.btn-send');
                    if (btn) {
                        btn.click();
                        btn.dispatchEvent(new MouseEvent('mousedown', {bubbles: true}));
                        btn.dispatchEvent(new MouseEvent('mouseup', {bubbles: true}));
                        btn.dispatchEvent(new MouseEvent('click', {bubbles: true}));
                    }
                """)
                await self.page.wait_for_timeout(1000)

                # Final Verify
                current_text = await message_input.inner_text()
                if not current_text or not current_text.strip():
                    self.logger.info("[SEND] ✓ Sent successfully (JS)")
                    await self._save_debug_snapshot("10_success_js")
                    return True

                self.logger.error(f"[SEND] ✗ Failed to send. Text stuck.")
                await self._save_debug_snapshot("10_failed_final", force=True)

                # SOFT FAIL: Clear the input to prevent blocking next tasks
                self.logger.warning("[SEND] Clearing stuck text from input...")
                try:
                    # Use force=True to bypass intercepting elements (like Join button or Mute banner)
                    await message_input.click(force=True)
                    await self.page.keyboard.press("Meta+A")
                    await self.page.keyboard.press("Backspace")
                    self.logger.info("[SEND] Input cleared.")
                except Exception as e:
                    self.logger.error(f"[SEND] Failed to clear input: {e}")

                return False

            except Exception as e:
                self.logger.error(f"[SEND] Error verifying: {e}")
                return False

        except Exception as e:
            self.logger.error(f"Error sending message: {e}")
            return False

    async def save_screenshot(self, screenshot_type: str, description: str) -> Optional[str]:
        """
        Save screenshot for debugging/error logging (ASYNC).

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
            await self.page.screenshot(
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
