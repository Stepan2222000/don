"""
Configuration module for Telegram Automation System

Loads and validates configuration from config.yaml file.
"""

import yaml
from pathlib import Path
from typing import Dict, Any, Optional
from dataclasses import dataclass, field


@dataclass
class LimitsConfig:
    """Limits and restrictions configuration."""
    max_messages_per_hour: int = 30
    max_cycles: int = 1
    delay_randomness: float = 0.2
    cycle_delay_minutes: int = 20


@dataclass
class TimeoutsConfig:
    """Timeouts configuration."""
    search_timeout: int = 10
    send_timeout: int = 5
    page_load_timeout: int = 30


@dataclass
class TelegramConfig:
    """Telegram-specific configuration."""
    url: str = "https://web.telegram.org/k"
    headless: bool = False


@dataclass
class RetryConfig:
    """Retry policy configuration."""
    enabled: bool = False
    max_attempts: int = 3
    delay_between_retries: int = 60


@dataclass
class ScreenshotsConfig:
    """Screenshots configuration."""
    enabled: bool = True
    on_error: bool = True
    on_warning: bool = False
    on_debug: bool = False
    full_page: bool = True
    quality: int = 80
    format: str = "png"
    max_age_days: int = 30


@dataclass
class LoggingConfig:
    """Logging configuration."""
    level: str = "INFO"
    format: str = "%(asctime)s | %(name)s | %(levelname)s | %(message)s"


@dataclass
class DatabaseConfig:
    """Database configuration."""
    path: str = "db/telegram_automation.db"
    wal_mode: bool = True


@dataclass
class Config:
    """Main configuration class."""
    limits: LimitsConfig = field(default_factory=LimitsConfig)
    timeouts: TimeoutsConfig = field(default_factory=TimeoutsConfig)
    telegram: TelegramConfig = field(default_factory=TelegramConfig)
    retry: RetryConfig = field(default_factory=RetryConfig)
    screenshots: ScreenshotsConfig = field(default_factory=ScreenshotsConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)
    database: DatabaseConfig = field(default_factory=DatabaseConfig)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Config':
        """Create Config from dictionary."""
        return cls(
            limits=LimitsConfig(**data.get('limits', {})),
            timeouts=TimeoutsConfig(**data.get('timeouts', {})),
            telegram=TelegramConfig(**data.get('telegram', {})),
            retry=RetryConfig(**data.get('retry', {})),
            screenshots=ScreenshotsConfig(**data.get('screenshots', {})),
            logging=LoggingConfig(**data.get('logging', {})),
            database=DatabaseConfig(**data.get('database', {}))
        )

    @classmethod
    def load_from_file(cls, config_path: str = "config.yaml") -> 'Config':
        """
        Load configuration from YAML file.

        Args:
            config_path: Path to config.yaml file

        Returns:
            Config instance

        Raises:
            FileNotFoundError: If config file doesn't exist
            yaml.YAMLError: If config file is invalid
        """
        config_file = Path(config_path)

        if not config_file.exists():
            raise FileNotFoundError(
                f"Configuration file not found: {config_path}\n"
                f"Please create config.yaml or run: python -m src.main init"
            )

        with open(config_file, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)

        if data is None:
            data = {}

        return cls.from_dict(data)

    def validate(self):
        """
        Validate configuration values.

        Raises:
            ValueError: If configuration is invalid
        """
        # Validate limits
        if self.limits.max_messages_per_hour <= 0:
            raise ValueError("max_messages_per_hour must be > 0")

        if self.limits.max_cycles < 1:
            raise ValueError("max_cycles must be >= 1")

        if not (0.0 <= self.limits.delay_randomness <= 1.0):
            raise ValueError("delay_randomness must be between 0.0 and 1.0")

        # Validate timeouts
        if self.timeouts.search_timeout <= 0:
            raise ValueError("search_timeout must be > 0")

        if self.timeouts.send_timeout <= 0:
            raise ValueError("send_timeout must be > 0")

        if self.timeouts.page_load_timeout <= 0:
            raise ValueError("page_load_timeout must be > 0")

        # Validate screenshot quality
        if not (0 <= self.screenshots.quality <= 100):
            raise ValueError("screenshot quality must be between 0 and 100")

        if self.screenshots.format not in ['png', 'jpeg', 'jpg']:
            raise ValueError("screenshot format must be 'png' or 'jpeg'")

        # Validate logging level
        valid_levels = ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']
        if self.logging.level.upper() not in valid_levels:
            raise ValueError(f"logging level must be one of: {valid_levels}")

    def to_dict(self) -> Dict[str, Any]:
        """Convert configuration to dictionary."""
        return {
            'limits': self.limits.__dict__,
            'timeouts': self.timeouts.__dict__,
            'telegram': self.telegram.__dict__,
            'retry': self.retry.__dict__,
            'screenshots': self.screenshots.__dict__,
            'logging': self.logging.__dict__,
            'database': self.database.__dict__
        }

    def save_to_file(self, config_path: str = "config.yaml"):
        """
        Save configuration to YAML file.

        Args:
            config_path: Path to config.yaml file
        """
        with open(config_path, 'w', encoding='utf-8') as f:
            yaml.dump(self.to_dict(), f, default_flow_style=False, sort_keys=False)


# Global configuration instance
_config_instance: Optional[Config] = None


def get_config() -> Config:
    """Get global configuration instance."""
    global _config_instance
    if _config_instance is None:
        raise RuntimeError("Configuration not loaded. Call load_config() first.")
    return _config_instance


def load_config(config_path: str = "config.yaml") -> Config:
    """Load and validate global configuration."""
    global _config_instance
    _config_instance = Config.load_from_file(config_path)
    _config_instance.validate()
    return _config_instance


def create_default_config(config_path: str = "config.yaml"):
    """Create default configuration file."""
    config = Config()
    config.save_to_file(config_path)
    return config
