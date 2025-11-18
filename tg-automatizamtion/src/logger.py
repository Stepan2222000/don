"""
Logging module for Telegram Automation System

Provides structured logging to multiple files:
- main.log: General application logs
- success.log: Successful message sends
- failed_chats.log: Chats not found
- failed_send.log: Send errors
"""

import logging
import os
from pathlib import Path
from typing import Optional
from datetime import datetime

# Determine project root directory (parent of src/)
PROJECT_ROOT = Path(__file__).parent.parent
DEFAULT_LOG_DIR = PROJECT_ROOT / "logs"


class TelegramAutomationLogger:
    """Multi-file logger for Telegram automation."""

    def __init__(self, log_dir: str = None, level: str = "INFO", log_format: Optional[str] = None):
        """
        Initialize logger with multiple handlers.

        Args:
            log_dir: Directory for log files
            level: Logging level (DEBUG, INFO, WARNING, ERROR)
            log_format: Log message format
        """
        if log_dir is None:
            log_dir = str(DEFAULT_LOG_DIR)
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)

        # Create screenshots subdirectories
        (self.log_dir / "screenshots" / "errors").mkdir(parents=True, exist_ok=True)
        (self.log_dir / "screenshots" / "warnings").mkdir(parents=True, exist_ok=True)
        (self.log_dir / "screenshots" / "debug").mkdir(parents=True, exist_ok=True)

        self.level = getattr(logging, level.upper())
        self.log_format = log_format or "%(asctime)s | %(name)s | %(levelname)s | %(message)s"

        # Initialize loggers
        self.main_logger = self._create_logger("main", "main.log")
        self.success_logger = self._create_logger("success", "success.log", level=logging.INFO)
        self.failed_chats_logger = self._create_logger("failed_chats", "failed_chats.log", level=logging.WARNING)
        self.failed_send_logger = self._create_logger("failed_send", "failed_send.log", level=logging.WARNING)

    def _create_logger(self, name: str, filename: str, level: Optional[int] = None) -> logging.Logger:
        """Create a logger with file handler."""
        logger = logging.getLogger(f"tg_automation.{name}")
        logger.setLevel(level or self.level)
        logger.propagate = False

        # Remove existing handlers
        logger.handlers.clear()

        # File handler
        file_handler = logging.FileHandler(
            self.log_dir / filename,
            encoding='utf-8'
        )
        file_handler.setLevel(level or self.level)
        file_handler.setFormatter(logging.Formatter(self.log_format))
        logger.addHandler(file_handler)

        # Console handler for main logger
        if name == "main":
            console_handler = logging.StreamHandler()
            console_handler.setLevel(level or self.level)
            console_handler.setFormatter(logging.Formatter(self.log_format))
            logger.addHandler(console_handler)

        return logger

    # ========================================
    # Main logger methods
    # ========================================

    def info(self, message: str):
        """Log info message to main log."""
        self.main_logger.info(message)

    def debug(self, message: str):
        """Log debug message to main log."""
        self.main_logger.debug(message)

    def warning(self, message: str):
        """Log warning message to main log."""
        self.main_logger.warning(message)

    def error(self, message: str):
        """Log error message to main log."""
        self.main_logger.error(message)

    def critical(self, message: str):
        """Log critical message to main log."""
        self.main_logger.critical(message)

    # ========================================
    # Success logger methods
    # ========================================

    def log_success(self, profile_name: str, chat_username: str, message_text: str):
        """
        Log successful message send.

        Format: "Profile: profile_name | Chat: @username | Message: \"text\""
        """
        log_message = f'Profile: {profile_name} | Chat: {chat_username} | Message: "{message_text}"'
        self.success_logger.info(log_message)

    # ========================================
    # Failed chats logger methods
    # ========================================

    def log_chat_not_found(self, profile_name: str, chat_username: str):
        """
        Log chat not found error.

        Format: "Profile: profile_name | Chat: @username | Error: Chat not found"
        """
        log_message = f'Profile: {profile_name} | Chat: {chat_username} | Error: Chat not found'
        self.failed_chats_logger.warning(log_message)

    def log_blocked_after_retries(
        self,
        profile_name: str,
        chat_username: str,
        attempts: int,
        last_error: str
    ):
        """
        Log chat blocked after exceeding retry limit.

        Format: "Profile: profile_name | Chat: @username | Error: Blocked after N attempts | Last error: details"
        """
        log_message = (
            f'Profile: {profile_name} | Chat: {chat_username} | '
            f'Error: Blocked after {attempts} failed attempts | '
            f'Last error: {last_error}'
        )
        self.failed_chats_logger.warning(log_message)

    # ========================================
    # Failed send logger methods
    # ========================================

    def log_send_error(
        self,
        profile_name: str,
        chat_username: str,
        error_type: str,
        error_details: Optional[str] = None
    ):
        """
        Log message send error.

        Format: "Profile: profile_name | Chat: @username | Error: error_type [details]"
        """
        log_message = f'Profile: {profile_name} | Chat: {chat_username} | Error: {error_type}'
        if error_details:
            log_message += f' | Details: {error_details}'
        self.failed_send_logger.warning(log_message)

    # ========================================
    # Worker-specific methods
    # ========================================

    def log_worker_start(self, profile_name: str, profile_id: str):
        """Log worker process start."""
        self.info(f"Worker started: {profile_name} ({profile_id})")

    def log_worker_stop(self, profile_name: str, profile_id: str, reason: str = "completed"):
        """Log worker process stop."""
        self.info(f"Worker stopped: {profile_name} ({profile_id}) - {reason}")

    def log_worker_error(self, profile_name: str, error: Exception):
        """Log worker error."""
        self.error(f"Worker {profile_name} failed: {type(error).__name__}: {str(error)}")

    # ========================================
    # Browser operation logging
    # ========================================

    def log_browser_launch(self, profile_name: str):
        """Log browser launch."""
        self.info(f"Launching browser for profile: {profile_name}")

    def log_browser_close(self, profile_name: str):
        """Log browser close."""
        self.info(f"Closing browser for profile: {profile_name}")

    def log_telegram_navigation(self, profile_name: str):
        """Log Telegram Web navigation."""
        self.info(f"Navigating to Telegram Web: {profile_name}")

    # ========================================
    # Task processing logging
    # ========================================

    def log_task_start(self, chat_username: str, profile_name: str):
        """Log task processing start."""
        self.info(f"Processing task: {chat_username} (profile: {profile_name})")

    def log_task_complete(self, chat_username: str, success: bool):
        """Log task completion."""
        status = "SUCCESS" if success else "FAILED"
        self.info(f"Task completed: {chat_username} - {status}")

    # ========================================
    # Screenshot logging
    # ========================================

    def get_screenshot_path(self, screenshot_type: str, description: str) -> str:
        """
        Generate screenshot file path.

        Args:
            screenshot_type: error/warning/debug
            description: Description for filename

        Returns:
            Relative path to screenshot file
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
        safe_description = "".join(c if c.isalnum() or c in ('-', '_') else '_' for c in description)
        filename = f"{timestamp}_{safe_description}.png"
        return f"logs/screenshots/{screenshot_type}s/{filename}"

    # ========================================
    # Progress reporting
    # ========================================

    def log_progress(
        self,
        completed: int,
        total: int,
        success: int,
        failed: int,
        elapsed_seconds: float
    ):
        """Log overall progress."""
        percent = (completed / total * 100) if total > 0 else 0
        rate = completed / elapsed_seconds if elapsed_seconds > 0 else 0
        eta_seconds = (total - completed) / rate if rate > 0 else 0

        self.info(
            f"Progress: {completed}/{total} ({percent:.1f}%) | "
            f"Success: {success} | Failed: {failed} | "
            f"Rate: {rate:.2f}/s | ETA: {int(eta_seconds)}s"
        )


# Global logger instance
_logger_instance: Optional[TelegramAutomationLogger] = None


def get_logger() -> TelegramAutomationLogger:
    """Get global logger instance."""
    global _logger_instance
    if _logger_instance is None:
        raise RuntimeError("Logger not initialized. Call init_logger() first.")
    return _logger_instance


def init_logger(log_dir: str = None, level: str = "INFO", log_format: Optional[str] = None) -> TelegramAutomationLogger:
    """Initialize global logger instance."""
    global _logger_instance
    if log_dir is None:
        log_dir = str(DEFAULT_LOG_DIR)
    _logger_instance = TelegramAutomationLogger(log_dir, level, log_format)
    return _logger_instance
