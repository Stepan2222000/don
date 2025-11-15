"""
Browser Automation module for Telegram Automation System

Launches Donut Browser profiles using nodecar CLI (emulates "Launch" button).
Provides Playwright integration for browser control.
"""

import subprocess
import json
import time
import platform
from pathlib import Path
from typing import Optional
from playwright.sync_api import sync_playwright, Browser, Page, PlaywrightContextManager

from .profile_manager import DonutProfile
from .logger import get_logger


class BrowserAutomation:
    """Browser automation using nodecar CLI and Playwright."""

    def __init__(self, nodecar_path: Optional[str] = None):
        """
        Initialize browser automation.

        Args:
            nodecar_path: Path to nodecar binary (not used anymore, kept for compatibility).
        """
        # Note: nodecar is no longer used, we use Playwright directly (see launch_browser)
        self.nodecar_path = None  # Not needed
        self.playwright: Optional[PlaywrightContextManager] = None
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

    def launch_browser(self, profile: DonutProfile, url: str = "https://web.telegram.org/k") -> Page:
        """
        Launch browser with profile using nodecar CLI.

        This emulates clicking the "Launch" button in Donut Browser UI.

        Args:
            profile: DonutProfile to launch
            url: URL to open (default: Telegram Web)

        Returns:
            Playwright Page object

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

            # Connect to browser with Playwright
            self.playwright = sync_playwright().start()

            # Prepare proxy config
            proxy_config = {"server": profile.proxy} if profile.proxy else None

            # Launch persistent context with fingerprint
            self.context = self.playwright.firefox.launch_persistent_context(
                user_data_dir=str(profile.browser_data_path),
                executable_path=profile.executable_path,
                headless=False,
                proxy=proxy_config,
                env=env_vars,
            )

            # Get existing page or create new one
            if self.context.pages:
                self.page = self.context.pages[0]
            else:
                self.page = self.context.new_page()

            # Navigate to URL if needed
            if self.page.url != url:
                logger.log_telegram_navigation(profile.profile_name)
                self.page.goto(url, timeout=30000)
                # Wait for page to load - multiple load states for reliability
                self.page.wait_for_load_state("domcontentloaded", timeout=30000)
                self.page.wait_for_load_state("networkidle", timeout=30000)
                # Additional wait for React to render UI
                logger.debug("Waiting for React UI to render...")
                self.page.wait_for_timeout(5000)

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
        if not fingerprint:
            return {}

        # Convert fingerprint to JSON string
        fingerprint_json = json.dumps(fingerprint)

        # Split into chunks if needed (Camoufox uses multiple env vars for large configs)
        chunk_size = 32000  # 32KB chunks
        chunks = []
        for i in range(0, len(fingerprint_json), chunk_size):
            chunks.append(fingerprint_json[i:i + chunk_size])

        # Create env vars
        env_vars = {}
        for i, chunk in enumerate(chunks, start=1):
            env_vars[f"CAMOU_CONFIG_{i}"] = chunk

        return env_vars

    def close_browser(self):
        """Close browser and cleanup."""
        logger = get_logger()

        try:
            if self.page:
                self.page.close()
                self.page = None

            if self.context:
                self.context.close()
                self.context = None

            if self.playwright:
                self.playwright.stop()
                self.playwright = None

            logger.debug("Browser closed successfully")

        except Exception as e:
            logger.error(f"Error closing browser: {e}")

    def get_page(self) -> Page:
        """Get current page."""
        if not self.page:
            raise RuntimeError("Browser not launched. Call launch_browser() first.")
        return self.page

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close_browser()


class BrowserAutomationSimplified:
    """
    Simplified browser automation for workers.

    Uses Playwright directly without nodecar CLI.
    Faster startup but requires manual fingerprint configuration.
    """

    def __init__(self):
        """Initialize simplified browser automation."""
        self.playwright: Optional[PlaywrightContextManager] = None
        self.context = None
        self.page: Optional[Page] = None

    def launch_browser(self, profile: DonutProfile, url: str = "https://web.telegram.org/k") -> Page:
        """
        Launch browser with Playwright directly.

        Args:
            profile: DonutProfile to launch
            url: URL to open

        Returns:
            Playwright Page object
        """
        logger = get_logger()
        logger.log_browser_launch(profile.profile_name)

        # Parse fingerprint
        fingerprint_config = json.loads(profile.fingerprint) if profile.fingerprint else {}

        # Prepare environment variables for Camoufox fingerprint
        # Camoufox expects fingerprint in CAMOU_CONFIG_* env vars
        env_vars = self._prepare_fingerprint_env(fingerprint_config)

        # Start Playwright
        self.playwright = sync_playwright().start()

        # Launch persistent context with fingerprint
        proxy_config = {"server": profile.proxy} if profile.proxy else None

        self.context = self.playwright.firefox.launch_persistent_context(
            user_data_dir=str(profile.browser_data_path),
            executable_path=profile.executable_path,
            headless=False,
            proxy=proxy_config,
            env=env_vars,
        )

        # Get or create page
        if self.context.pages:
            self.page = self.context.pages[0]
        else:
            self.page = self.context.new_page()

        # Navigate to URL
        logger.log_telegram_navigation(profile.profile_name)
        self.page.goto(url, timeout=30000)
        # Wait for page to load - multiple load states for reliability
        self.page.wait_for_load_state("domcontentloaded", timeout=30000)
        self.page.wait_for_load_state("networkidle", timeout=30000)
        # Additional wait for React to render UI
        logger.debug("Waiting for React UI to render...")
        self.page.wait_for_timeout(5000)

        logger.info(f"Browser launched successfully: {profile.profile_name}")
        return self.page

    def _prepare_fingerprint_env(self, fingerprint: dict) -> dict:
        """
        Prepare environment variables for Camoufox fingerprint.

        Camoufox expects fingerprint configuration in CAMOU_CONFIG_* env vars.
        Large configs are split into chunks.
        """
        if not fingerprint:
            return {}

        # Convert fingerprint to JSON string
        fingerprint_json = json.dumps(fingerprint)

        # Split into chunks if needed (Camoufox uses multiple env vars for large configs)
        chunk_size = 32000  # 32KB chunks
        chunks = []
        for i in range(0, len(fingerprint_json), chunk_size):
            chunks.append(fingerprint_json[i:i + chunk_size])

        # Create env vars
        env_vars = {}
        for i, chunk in enumerate(chunks, start=1):
            env_vars[f"CAMOU_CONFIG_{i}"] = chunk

        return env_vars

    def close_browser(self):
        """Close browser and cleanup."""
        logger = get_logger()

        try:
            if self.page:
                self.page.close()
                self.page = None

            if self.context:
                self.context.close()
                self.context = None

            if self.playwright:
                self.playwright.stop()
                self.playwright = None

            logger.debug("Browser closed successfully")

        except Exception as e:
            logger.error(f"Error closing browser: {e}")

    def get_page(self) -> Page:
        """Get current page."""
        if not self.page:
            raise RuntimeError("Browser not launched. Call launch_browser() first.")
        return self.page

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close_browser()
