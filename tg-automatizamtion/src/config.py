"""
Configuration module for Telegram Automation System

Loads and validates configuration from config.yaml file.
Supports campaign groups with per-group settings.
"""

import json
import yaml
from pathlib import Path
from typing import Dict, Any, Optional, List, Union
from dataclasses import dataclass, field

# Determine project root directory (parent of src/)
PROJECT_ROOT = Path(__file__).parent.parent
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "config.yaml"
DEFAULT_GROUPS_PATH = PROJECT_ROOT / "data" / "groups.json"


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
    headless: Union[bool, str] = False  # bool или "virtual" для автоматического Xvfb
    geoip: bool = True  # Автоопределение геолокации по IP прокси
    humanize: Union[bool, float] = True  # Человекоподобные движения мыши (True или float секунд)


@dataclass
class RetryConfig:
    """Retry policy configuration."""
    enabled: bool = False
    max_attempts: int = 3
    delay_between_retries: int = 60
    max_attempts_before_block: int = 3  # Block task after N failed attempts


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
class VideoConfig:
    """Video recording configuration."""
    enabled: bool = False                    # Выключено по умолчанию
    output_dir: str = "logs/videos"          # Базовая папка для видео
    width: int = 854                         # 480p ширина (16:9)
    height: int = 480                        # 480p высота


@dataclass
class LoggingConfig:
    """Logging configuration."""
    level: str = "INFO"
    format: str = "%(asctime)s | %(name)s | %(levelname)s | %(message)s"


@dataclass
class PostgreSQLConfig:
    """PostgreSQL configuration."""
    host: str = "localhost"
    port: int = 5432
    database: str = "telegram_automation"
    user: str = "postgres"
    password: str = ""

    @property
    def connection_string(self) -> str:
        """Get PostgreSQL connection string."""
        return f"postgresql://{self.user}:{self.password}@{self.host}:{self.port}/{self.database}"


@dataclass
class SQLiteConfig:
    """SQLite configuration."""
    path: str = "db/telegram_automation.db"
    wal_mode: bool = True

    @property
    def absolute_path(self) -> str:
        """Get absolute path to database file, resolved from PROJECT_ROOT."""
        db_path = Path(self.path)
        if db_path.is_absolute():
            return str(db_path)
        return str(PROJECT_ROOT / db_path)


@dataclass
class DatabaseConfig:
    """Database configuration with PostgreSQL and SQLite support."""
    type: str = "postgresql"  # "postgresql" или "sqlite"
    postgresql: PostgreSQLConfig = field(default_factory=PostgreSQLConfig)
    sqlite: SQLiteConfig = field(default_factory=SQLiteConfig)

    @property
    def is_postgresql(self) -> bool:
        """Check if using PostgreSQL."""
        return self.type.lower() == "postgresql"

    @property
    def is_sqlite(self) -> bool:
        """Check if using SQLite."""
        return self.type.lower() == "sqlite"

    # Для обратной совместимости
    @property
    def absolute_path(self) -> str:
        """Get absolute path to SQLite database file."""
        return self.sqlite.absolute_path


@dataclass
class ProxyConfig:
    """Proxy management configuration."""
    enabled: bool = True                              # Глобальный переключатель прокси
    disabled_profiles: List[str] = field(default_factory=list)  # UUID профилей без прокси
    pool_file: str = "data/proxies.txt"
    min_attempts_for_check: int = 10          # Мин. попыток перед анализом
    chat_not_found_threshold: int = 40        # % для ротации
    unblock_tasks_on_rotate: bool = True      # Разблокировать задачи при ротации
    health_reset_hours: int = 1               # Через сколько часов дать "второй шанс"

    def __post_init__(self):
        """Validate and normalize disabled_profiles."""
        # Защита от null в YAML
        if self.disabled_profiles is None:
            self.disabled_profiles = []
        # Защита от string вместо list
        if isinstance(self.disabled_profiles, str):
            self.disabled_profiles = [self.disabled_profiles]

    @property
    def absolute_pool_path(self) -> str:
        """Get absolute path to proxy pool file."""
        pool_path = Path(self.pool_file)
        if pool_path.is_absolute():
            return str(pool_path)
        return str(PROJECT_ROOT / pool_path)


@dataclass
class Config:
    """Main configuration class."""
    limits: LimitsConfig = field(default_factory=LimitsConfig)
    timeouts: TimeoutsConfig = field(default_factory=TimeoutsConfig)
    telegram: TelegramConfig = field(default_factory=TelegramConfig)
    retry: RetryConfig = field(default_factory=RetryConfig)
    screenshots: ScreenshotsConfig = field(default_factory=ScreenshotsConfig)
    video: VideoConfig = field(default_factory=VideoConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)
    database: DatabaseConfig = field(default_factory=DatabaseConfig)
    proxy: ProxyConfig = field(default_factory=ProxyConfig)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Config':
        """Create Config from dictionary."""
        # Parse database config with nested structures
        db_data = data.get('database', {})
        db_config = DatabaseConfig(
            type=db_data.get('type', 'postgresql'),
            postgresql=PostgreSQLConfig(**db_data.get('postgresql', {})),
            sqlite=SQLiteConfig(**db_data.get('sqlite', {}))
        )

        return cls(
            limits=LimitsConfig(**data.get('limits', {})),
            timeouts=TimeoutsConfig(**data.get('timeouts', {})),
            telegram=TelegramConfig(**data.get('telegram', {})),
            retry=RetryConfig(**data.get('retry', {})),
            screenshots=ScreenshotsConfig(**data.get('screenshots', {})),
            video=VideoConfig(**data.get('video', {})),
            logging=LoggingConfig(**data.get('logging', {})),
            database=db_config,
            proxy=ProxyConfig(**data.get('proxy', {}))
        )

    @classmethod
    def load_from_file(cls, config_path: str = None) -> 'Config':
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
        if config_path is None:
            config_path = str(DEFAULT_CONFIG_PATH)
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

        # Validate retry config
        if self.retry.max_attempts_before_block < 1:
            raise ValueError("max_attempts_before_block must be >= 1")

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
            'limits': self.limits.__dict__.copy(),
            'timeouts': self.timeouts.__dict__.copy(),
            'telegram': self.telegram.__dict__.copy(),
            'retry': self.retry.__dict__.copy(),
            'screenshots': self.screenshots.__dict__.copy(),
            'video': self.video.__dict__.copy(),
            'logging': self.logging.__dict__.copy(),
            'database': {
                'type': self.database.type,
                'postgresql': self.database.postgresql.__dict__.copy(),
                'sqlite': self.database.sqlite.__dict__.copy()
            },
            'proxy': self.proxy.__dict__.copy()
        }

    def save_to_file(self, config_path: str = None):
        """
        Save configuration to YAML file.

        Args:
            config_path: Path to config.yaml file
        """
        if config_path is None:
            config_path = str(DEFAULT_CONFIG_PATH)
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


def load_config(config_path: str = None) -> Config:
    """Load and validate global configuration."""
    global _config_instance
    if config_path is None:
        config_path = str(DEFAULT_CONFIG_PATH)
    _config_instance = Config.load_from_file(config_path)
    _config_instance.validate()
    return _config_instance


def create_default_config(config_path: str = None):
    """Create default configuration file."""
    if config_path is None:
        config_path = str(DEFAULT_CONFIG_PATH)
    config = Config()
    config.save_to_file(config_path)
    return config


# =====================================================
# Campaign Groups Support
# =====================================================

@dataclass
class CampaignGroup:
    """Campaign group configuration."""
    id: str
    profiles: List[str] = field(default_factory=list)
    messages: List[str] = field(default_factory=list)
    settings: Dict[str, Any] = field(default_factory=dict)

    def get_merged_config(self, base_config: Config) -> Config:
        """
        Merge group settings with base config.
        Group settings override base config values.

        Args:
            base_config: Base configuration from config.yaml

        Returns:
            Config instance with merged settings
        """
        # Start with base config as dict
        merged = base_config.to_dict()

        # Merge group settings
        for key, value in self.settings.items():
            if key in merged and isinstance(merged[key], dict) and isinstance(value, dict):
                # Merge nested dicts (e.g., limits, timeouts)
                merged[key].update(value)
            else:
                # Direct override
                merged[key] = value

        # Create new Config from merged dict
        return Config.from_dict(merged)


@dataclass
class GroupsData:
    """Container for all campaign groups."""
    groups: List[CampaignGroup] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'GroupsData':
        """Create GroupsData from dictionary."""
        groups = [
            CampaignGroup(
                id=g['id'],
                profiles=g.get('profiles', []),
                messages=g.get('messages', []),
                settings=g.get('settings', {})
            )
            for g in data.get('groups', [])
        ]
        return cls(groups=groups)

    @classmethod
    def load_from_file(cls, groups_path: str = None) -> 'GroupsData':
        """
        Load groups from JSON file.

        Args:
            groups_path: Path to groups.json file

        Returns:
            GroupsData instance

        Raises:
            FileNotFoundError: If groups file doesn't exist
            json.JSONDecodeError: If groups file is invalid
        """
        if groups_path is None:
            groups_path = str(DEFAULT_GROUPS_PATH)
        groups_file = Path(groups_path)

        if not groups_file.exists():
            raise FileNotFoundError(
                f"Groups file not found: {groups_path}\n"
                f"Please create data/groups.json"
            )

        with open(groups_file, 'r', encoding='utf-8') as f:
            data = json.load(f)

        return cls.from_dict(data)

    def get_group(self, group_id: str) -> Optional[CampaignGroup]:
        """Get group by ID."""
        for group in self.groups:
            if group.id == group_id:
                return group
        return None

    def add_group(self, group: CampaignGroup):
        """Add or update group."""
        # Remove existing group with same ID
        self.groups = [g for g in self.groups if g.id != group.id]
        # Add new group
        self.groups.append(group)

    def remove_group(self, group_id: str) -> bool:
        """Remove group by ID. Returns True if group was removed."""
        original_length = len(self.groups)
        self.groups = [g for g in self.groups if g.id != group_id]
        return len(self.groups) < original_length

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            'groups': [
                {
                    'id': g.id,
                    'profiles': g.profiles,
                    'messages': g.messages,
                    'settings': g.settings
                }
                for g in self.groups
            ]
        }

    def save_to_file(self, groups_path: str = None):
        """Save groups to JSON file."""
        if groups_path is None:
            groups_path = str(DEFAULT_GROUPS_PATH)
        with open(groups_path, 'w', encoding='utf-8') as f:
            json.dump(self.to_dict(), f, indent=2, ensure_ascii=False)


def load_groups(groups_path: str = None) -> GroupsData:
    """Load groups from JSON file."""
    if groups_path is None:
        groups_path = str(DEFAULT_GROUPS_PATH)
    return GroupsData.load_from_file(groups_path)


def get_group_config(group_id: str, base_config: Optional[Config] = None, groups_path: str = None) -> Config:
    """
    Get merged configuration for a specific group.

    Args:
        group_id: Group ID
        base_config: Base configuration (if None, loads from config.yaml)
        groups_path: Path to groups.json file

    Returns:
        Config instance with group settings merged

    Raises:
        ValueError: If group not found
    """
    if base_config is None:
        base_config = get_config()

    if groups_path is None:
        groups_path = str(DEFAULT_GROUPS_PATH)

    groups_data = load_groups(groups_path)
    group = groups_data.get_group(group_id)

    if group is None:
        raise ValueError(f"Group not found: {group_id}")

    return group.get_merged_config(base_config)
