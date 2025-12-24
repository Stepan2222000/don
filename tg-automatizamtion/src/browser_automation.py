"""
Browser Automation module for Telegram Automation System (ASYNC VERSION)

Launches Donut Browser profiles using nodecar CLI (emulates "Launch" button).
Provides Playwright async integration for browser control.
"""

import subprocess
import json
import time
import platform
import os
from pathlib import Path
from typing import Optional
from playwright.async_api import async_playwright, Browser, Page, Playwright

from .profile_manager import DonutProfile
from .logger import get_logger
from .config import get_config


class QRCodePageDetectedError(Exception):
    """Raised when QR code login page is detected (session expired)."""
    pass


def _parse_proxy_url(proxy_url: str) -> dict:
    """
    Parse proxy URL into Playwright proxy config format.

    Playwright requires separate username/password fields, not embedded in URL.

    Args:
        proxy_url: Proxy URL like "http://user:pass@host:port"

    Returns:
        Dict with server, username, password keys for Playwright
    """
    from urllib.parse import urlparse

    parsed = urlparse(proxy_url)

    # Build server URL without credentials
    server = f"{parsed.scheme}://{parsed.hostname}:{parsed.port}"

    config = {"server": server}

    if parsed.username:
        config["username"] = parsed.username
    if parsed.password:
        config["password"] = parsed.password

    return config


async def _check_qr_code_page(page: Page, logger) -> bool:
    """
    Check if current page is QR code login page (session expired).

    QR code page selectors based on Telegram Web K:
    - .page-signQR.active - QR code sign-in page with active class
    - #auth-pages - Authentication pages container (visible)
    - .qr-description - QR code description text

    Args:
        page: Playwright Page object (async)
        logger: Logger instance

    Returns:
        True if QR code page detected, False otherwise
    """
    qr_selectors = [
        ".page-signQR.active",
        "#auth-pages:not([style*='display: none'])",
        ".qr-description",
    ]

    for selector in qr_selectors:
        try:
            locator = page.locator(selector)
            if await locator.count() > 0 and await locator.first.is_visible():
                logger.warning(f"QR code page detected (selector: {selector})")
                return True
        except Exception:
            pass

    return False


async def _verify_telegram_loaded(page: Page, logger) -> tuple[bool, list[str]]:
    """
    Verify that Telegram UI has loaded properly.

    Checks for presence AND visibility of critical UI elements to detect white/blank page.

    Args:
        page: Playwright Page object (async)
        logger: Logger instance

    Returns:
        Tuple of (is_loaded, missing_elements):
            - is_loaded: True if all critical elements present and visible, False if white page
            - missing_elements: List of descriptions of missing/invisible elements
    """
    missing_elements = []

    # Critical elements that must be present on loaded Telegram page
    # Based on analysis of tg-automatizamtion/htmls/main.html
    elements_to_check = {
        "#page-chats": "Main page container",
        "#main-columns": "Main columns",
        "input.input-search-input": "Search input field",
    }

    logger.debug("Verifying Telegram page loaded...")

    for selector, description in elements_to_check.items():
        locator = page.locator(selector)
        element_count = await locator.count()

        # Check if element exists
        if element_count == 0:
            logger.debug(f"Checking {description} ({selector}): NOT FOUND")
            missing_elements.append(f"{description} ({selector}) - not found")
            continue

        # Check if element is visible
        is_visible = await locator.first.is_visible()
        logger.debug(f"Checking {description} ({selector}): {'VISIBLE' if is_visible else 'NOT VISIBLE'}")

        if not is_visible:
            missing_elements.append(f"{description} ({selector}) - not visible")

    is_loaded = len(missing_elements) == 0

    if is_loaded:
        logger.debug("✓ All critical elements found and visible - Telegram loaded successfully")
    else:
        logger.warning(f"✗ White page detected - missing/invisible elements: {', '.join(missing_elements)}")

    return is_loaded, missing_elements


async def _load_telegram_with_retry(page: Page, url: str, logger, max_retries: int = 3) -> None:
    """
    Load Telegram with retry logic and white page detection.

    If white/blank page is detected, will reload the page and retry.
    Takes screenshots of failed attempts for debugging.

    Args:
        page: Playwright Page object (async)
        url: URL to load (should be https://web.telegram.org/k)
        logger: Logger instance
        max_retries: Maximum number of reload attempts (default: 3)

    Raises:
        RuntimeError: If Telegram fails to load after all retry attempts
    """
    from pathlib import Path

    for attempt in range(max_retries):
        attempt_num = attempt + 1
        logger.info(f"Loading Telegram (attempt {attempt_num}/{max_retries})...")

        # Navigate to URL
        await page.goto(url, timeout=30000)

        # Wait for page to load - multiple load states for reliability
        await page.wait_for_load_state("domcontentloaded", timeout=30000)
        await page.wait_for_load_state("networkidle", timeout=30000)

        # Additional wait for React to render UI (increased from 5s to 15s)
        logger.debug("Waiting for React UI to render...")
        await page.wait_for_timeout(15000)

        # CHECK FOR QR CODE PAGE FIRST (session expired)
        # This should NOT be retried - user needs to re-login manually
        if await _check_qr_code_page(page, logger):
            logger.error("Session expired - QR code login page detected")
            # Save screenshot for debugging
            try:
                screenshot_dir = Path("logs/screenshots")
                screenshot_dir.mkdir(parents=True, exist_ok=True)
                screenshot_path = screenshot_dir / "qr_code_page_detected.png"
                await page.screenshot(path=str(screenshot_path))
                logger.info(f"QR code screenshot saved: {screenshot_path}")
            except Exception as e:
                logger.error(f"Failed to save QR screenshot: {e}")
            # Raise specific exception (not retry)
            raise QRCodePageDetectedError("Profile session expired - QR code login required")

        # Verify Telegram UI loaded (check for critical elements)
        is_loaded, missing_elements = await _verify_telegram_loaded(page, logger)

        if is_loaded:
            # Additional stabilization wait after successful check
            logger.debug("Elements verified, waiting for UI stabilization...")
            await page.wait_for_timeout(5000)
            logger.info(f"✓ Telegram loaded successfully on attempt {attempt_num}")
            return

        # White page detected
        logger.warning(f"✗ White/blank page detected on attempt {attempt_num}/{max_retries}")
        logger.warning(f"Missing elements: {', '.join(missing_elements)}")

        # Save screenshot for debugging
        try:
            screenshot_dir = Path("logs/screenshots")
            screenshot_dir.mkdir(parents=True, exist_ok=True)
            screenshot_path = screenshot_dir / f"white_page_attempt_{attempt_num}.png"

            await page.screenshot(path=str(screenshot_path))
            logger.info(f"Screenshot saved: {screenshot_path}")
        except Exception as e:
            logger.error(f"Failed to save screenshot: {e}")

        # If not last attempt, reload and retry
        if attempt_num < max_retries:
            logger.info(f"Reloading page for retry {attempt_num + 1}...")
            await page.reload(timeout=30000)
            await page.wait_for_timeout(5000)
        else:
            # All attempts exhausted
            raise RuntimeError(
                f"Failed to load Telegram after {max_retries} attempts. "
                f"White/blank page persists. Missing elements: {', '.join(missing_elements)}"
            )


class BrowserAutomation:
    """Browser automation using nodecar CLI and Playwright (ASYNC)."""

    def __init__(self, nodecar_path: Optional[str] = None):
        """
        Initialize browser automation.

        Args:
            nodecar_path: Path to nodecar binary (not used anymore, kept for compatibility).
        """
        # Note: nodecar is no longer used, we use Playwright directly (see launch_browser)
        self.nodecar_path = None  # Not needed
        self.playwright: Optional[Playwright] = None
        self.browser: Optional[Browser] = None
        self.context = None
        self.page: Optional[Page] = None

    def _find_nodecar(self) -> str:
        """Find nodecar binary automatically."""
        # Detect platform and architecture
        system = platform.system().lower()
        machine = platform.machine().lower()

        # Map to nodecar binary names
        if system == "darwin":
            if "arm" in machine or "aarch64" in machine:
                binary_name = "nodecar-aarch64-apple-darwin"
            else:
                binary_name = "nodecar-x86_64-apple-darwin"
        elif system == "linux":
            if "arm" in machine or "aarch64" in machine:
                binary_name = "nodecar-aarch64-unknown-linux-gnu"
            else:
                binary_name = "nodecar-x86_64-unknown-linux-gnu"
        else:
            raise RuntimeError(f"Unsupported platform: {system}")

        # Try to find in donutbrowser project
        possible_paths = [
            # Development build
            Path(__file__).parent.parent.parent / "donutbrowser" / "src-tauri" / "binaries" / binary_name,
            # Installed location (if exists)
            Path.home() / ".local" / "bin" / "nodecar",
            Path("/usr/local/bin/nodecar"),
        ]

        for path in possible_paths:
            if path.exists():
                return str(path)

        raise FileNotFoundError(
            f"Nodecar binary not found. Tried:\n" +
            "\n".join(f"  - {p}" for p in possible_paths) +
            "\n\nPlease specify nodecar_path manually."
        )

    async def launch_browser(
        self,
        profile: DonutProfile,
        url: str = "https://web.telegram.org/k",
        proxy_override: Optional[str] = None,
        disable_proxy: bool = False
    ) -> Page:
        """
        Launch browser with profile using nodecar CLI (ASYNC).

        This emulates clicking the "Launch" button in Donut Browser UI.

        Args:
            profile: DonutProfile to launch
            url: URL to open (default: Telegram Web)
            proxy_override: Optional proxy URL to use instead of profile's proxy
                           Format: "http://user:pass@host:port"
            disable_proxy: If True, ignore all proxy settings (proxy_override and profile.proxy)

        Returns:
            Playwright Page object (async)

        Raises:
            RuntimeError: If launch fails
        """
        logger = get_logger()
        logger.log_browser_launch(profile.profile_name)

        try:
            # NOTE: Using Playwright direct launch (not nodecar CLI)
            # For nodecar integration, use BrowserAutomationSimplified

            # Parse fingerprint for Playwright
            fingerprint_config = json.loads(profile.fingerprint) if profile.fingerprint else {}
            env_vars = self._prepare_fingerprint_env(fingerprint_config)

            # Connect to browser with Playwright (async)
            self.playwright = await async_playwright().start()

            # Prepare proxy config - if disabled, ignore all proxy settings
            if disable_proxy:
                proxy_config = None
                logger.info("Proxy disabled - running without proxy")
            else:
                # proxy_override takes precedence over profile.proxy
                proxy_url = proxy_override if proxy_override else profile.proxy
                proxy_config = _parse_proxy_url(proxy_url) if proxy_url else None
                if proxy_override:
                    logger.info(f"Using proxy override: {proxy_override.split('@')[-1] if '@' in proxy_override else proxy_override}")

            # Launch persistent context with fingerprint (async)
            config = get_config()
            self.context = await self.playwright.firefox.launch_persistent_context(
                user_data_dir=str(profile.browser_data_path),
                executable_path=profile.executable_path,
                headless=config.telegram.headless,
                proxy=proxy_config,
                env=env_vars,
            )

            # Get existing page or create new one
            if self.context.pages:
                self.page = self.context.pages[0]
            else:
                self.page = await self.context.new_page()

            # Navigate to URL with retry logic for white page detection
            if self.page.url != url:
                logger.log_telegram_navigation(profile.profile_name)
                # Use new retry logic with white page detection (async)
                await _load_telegram_with_retry(self.page, url, logger, max_retries=3)

            logger.info(f"Browser launched successfully: {profile.profile_name}")
            return self.page

        except subprocess.TimeoutExpired:
            raise RuntimeError(f"Browser launch timeout for profile: {profile.profile_name}")
        except Exception as e:
            logger.error(f"Failed to launch browser: {e}")
            raise

    def _prepare_fingerprint_env(self, fingerprint: dict) -> dict:
        """
        Prepare environment variables for Camoufox fingerprint.

        Camoufox expects fingerprint configuration in CAMOU_CONFIG_* env vars.
        Large configs are split into chunks.
        """
        # Start with system environment (includes DISPLAY for Xvfb)
        env_vars = os.environ.copy()

        # Ensure DISPLAY is set for headless servers
        if 'DISPLAY' not in env_vars:
            env_vars['DISPLAY'] = ':99'

        if not fingerprint:
            return env_vars

        # Convert fingerprint to JSON string
        fingerprint_json = json.dumps(fingerprint)

        # Split into chunks if needed (Camoufox uses multiple env vars for large configs)
        chunk_size = 32000  # 32KB chunks
        chunks = []
        for i in range(0, len(fingerprint_json), chunk_size):
            chunks.append(fingerprint_json[i:i + chunk_size])

        # Add Camoufox env vars
        for i, chunk in enumerate(chunks, start=1):
            env_vars[f"CAMOU_CONFIG_{i}"] = chunk

        return env_vars

    async def close_browser(self):
        """Close browser and cleanup (ASYNC)."""
        logger = get_logger()

        try:
            if self.page:
                await self.page.close()
                self.page = None

            if self.context:
                await self.context.close()
                self.context = None

            if self.playwright:
                await self.playwright.stop()
                self.playwright = None

            logger.debug("Browser closed successfully")

        except Exception as e:
            logger.error(f"Error closing browser: {e}")

    def get_page(self) -> Page:
        """Get current page."""
        if not self.page:
            raise RuntimeError("Browser not launched. Call launch_browser() first.")
        return self.page

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close_browser()


class BrowserAutomationSimplified:
    """
    Simplified browser automation for workers (ASYNC).

    Uses Playwright directly without nodecar CLI.
    Faster startup but requires manual fingerprint configuration.
    """

    def __init__(self):
        """Initialize simplified browser automation."""
        self.playwright: Optional[Playwright] = None
        self.context = None
        self.page: Optional[Page] = None
        self.video_path: Optional[str] = None  # Путь к записанному видео

    async def launch_browser(
        self,
        profile: DonutProfile,
        url: str = "https://web.telegram.org/k",
        proxy_override: Optional[str] = None,
        disable_proxy: bool = False
    ) -> Page:
        """
        Launch browser with Playwright directly (ASYNC).

        Args:
            profile: DonutProfile to launch
            url: URL to open
            proxy_override: Optional proxy URL to use instead of profile's proxy
                           Format: "http://user:pass@host:port"
            disable_proxy: If True, ignore all proxy settings (proxy_override and profile.proxy)

        Returns:
            Playwright Page object (async)
        """
        logger = get_logger()
        logger.log_browser_launch(profile.profile_name)

        # Parse fingerprint
        fingerprint_config = json.loads(profile.fingerprint) if profile.fingerprint else {}

        # Prepare environment variables for Camoufox fingerprint
        # Camoufox expects fingerprint in CAMOU_CONFIG_* env vars
        env_vars = self._prepare_fingerprint_env(fingerprint_config)

        # Start Playwright (async)
        self.playwright = await async_playwright().start()

        # Launch persistent context with fingerprint
        # If proxy disabled, ignore all proxy settings
        if disable_proxy:
            proxy_config = None
            logger.info("Proxy disabled - running without proxy")
        else:
            # proxy_override takes precedence over profile.proxy
            proxy_url = proxy_override if proxy_override else profile.proxy
            proxy_config = _parse_proxy_url(proxy_url) if proxy_url else None
            if proxy_override:
                logger.info(f"Using proxy override: {proxy_override.split('@')[-1] if '@' in proxy_override else proxy_override}")
        config = get_config()

        # Prepare video recording if enabled
        video_dir = self._prepare_video_dir(profile.profile_id)
        video_size = {"width": config.video.width, "height": config.video.height} if video_dir else None

        if video_dir:
            logger.info(f"Video recording enabled: {video_dir}")

        self.context = await self.playwright.firefox.launch_persistent_context(
            user_data_dir=str(profile.browser_data_path),
            executable_path=profile.executable_path,
            headless=config.telegram.headless,
            proxy=proxy_config,
            env=env_vars,
            record_video_dir=video_dir,
            record_video_size=video_size,
        )

        # Get or create page
        if self.context.pages:
            self.page = self.context.pages[0]
        else:
            self.page = await self.context.new_page()

        # Navigate to URL with retry logic for white page detection (async)
        logger.log_telegram_navigation(profile.profile_name)
        # Use new retry logic with white page detection
        await _load_telegram_with_retry(self.page, url, logger, max_retries=3)

        logger.info(f"Browser launched successfully: {profile.profile_name}")
        return self.page

    def _prepare_fingerprint_env(self, fingerprint: dict) -> dict:
        """
        Prepare environment variables for Camoufox fingerprint.

        Camoufox expects fingerprint configuration in CAMOU_CONFIG_* env vars.
        Large configs are split into chunks.
        """
        # Start with system environment (includes DISPLAY for Xvfb)
        env_vars = os.environ.copy()

        # Ensure DISPLAY is set for headless servers
        if 'DISPLAY' not in env_vars:
            env_vars['DISPLAY'] = ':99'

        if not fingerprint:
            return env_vars

        # Convert fingerprint to JSON string
        fingerprint_json = json.dumps(fingerprint)

        # Split into chunks if needed (Camoufox uses multiple env vars for large configs)
        chunk_size = 32000  # 32KB chunks
        chunks = []
        for i in range(0, len(fingerprint_json), chunk_size):
            chunks.append(fingerprint_json[i:i + chunk_size])

        # Add Camoufox env vars
        for i, chunk in enumerate(chunks, start=1):
            env_vars[f"CAMOU_CONFIG_{i}"] = chunk

        return env_vars

    def _prepare_video_dir(self, profile_id: str) -> Optional[str]:
        """
        Prepare video recording directory for profile session.

        Creates directory structure: {output_dir}/{profile_id}/{timestamp}/

        Args:
            profile_id: Profile UUID

        Returns:
            Absolute path to video directory, or None if video disabled
        """
        from datetime import datetime
        from .config import PROJECT_ROOT

        config = get_config()

        if not config.video.enabled:
            return None

        # Generate timestamp for session folder
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        # Build path: logs/videos/{profile_id}/{timestamp}/
        video_dir = Path(config.video.output_dir) / profile_id / timestamp

        # Resolve to absolute path from PROJECT_ROOT
        if not video_dir.is_absolute():
            video_dir = PROJECT_ROOT / video_dir

        # Create directory
        video_dir.mkdir(parents=True, exist_ok=True)

        return str(video_dir)

    async def close_browser(self):
        """Close browser and cleanup (ASYNC)."""
        logger = get_logger()

        try:
            # Получить путь к видео до закрытия (видео сохраняется при закрытии контекста)
            if self.page and self.page.video:
                try:
                    self.video_path = await self.page.video.path()
                    logger.info(f"Video saved: {self.video_path}")
                except Exception as e:
                    logger.warning(f"Could not get video path: {e}")

            if self.page:
                await self.page.close()
                self.page = None

            if self.context:
                await self.context.close()
                self.context = None

            if self.playwright:
                await self.playwright.stop()
                self.playwright = None

            logger.debug("Browser closed successfully")

        except Exception as e:
            logger.error(f"Error closing browser: {e}")

    def get_page(self) -> Page:
        """Get current page."""
        if not self.page:
            raise RuntimeError("Browser not launched. Call launch_browser() first.")
        return self.page

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close_browser()
