"""
Profile Manager for Telegram Automation System

Manages Donut Browser profiles for automation.
Reads profile metadata and provides access to profile information.
"""

import json
import os
from pathlib import Path
from typing import List, Dict, Any, Optional
from dataclasses import dataclass


def get_default_profiles_dir() -> str:
    """
    Get default Donut Browser profiles directory based on OS.

    Returns:
        Path to profiles directory:
        - If DONUTBROWSER_DATA_DIR is set: $DONUTBROWSER_DATA_DIR/profiles/
        - Default: PROJECT_ROOT/../donutbrowser/data/profiles/
    """
    # Check for data directory override first
    if override_dir := os.environ.get("DONUTBROWSER_DATA_DIR"):
        return os.path.join(override_dir, "profiles")

    # Default: relative to project root
    from .config import PROJECT_ROOT
    return str(PROJECT_ROOT.parent / "donutbrowser" / "data" / "profiles")


def get_default_proxies_dir() -> str:
    """
    Get default Donut Browser proxies directory.

    Returns:
        Path to proxies directory:
        - If DONUTBROWSER_DATA_DIR is set: $DONUTBROWSER_DATA_DIR/proxies/
        - Default: PROJECT_ROOT/../donutbrowser/data/proxies/
    """
    if override_dir := os.environ.get("DONUTBROWSER_DATA_DIR"):
        return os.path.join(override_dir, "proxies")

    # Default: relative to project root
    from .config import PROJECT_ROOT
    return str(PROJECT_ROOT.parent / "donutbrowser" / "data" / "proxies")


@dataclass
class DonutProfile:
    """Donut Browser profile information."""
    profile_id: str  # UUID
    profile_name: str
    browser: str  # "camoufox"
    version: str  # Browser version
    profile_path: Path  # Full path to profile directory
    metadata_path: Path  # Path to metadata.json
    browser_data_path: Path  # Path to profile/  directory

    # Camoufox configuration
    executable_path: Optional[str] = None
    fingerprint: Optional[str] = None  # JSON string
    proxy: Optional[str] = None
    proxy_id: Optional[str] = None

    # Additional metadata
    process_id: Optional[int] = None
    last_launch: Optional[int] = None
    release_type: str = "stable"
    group_id: Optional[str] = None
    tags: List[str] = None

    def __post_init__(self):
        if self.tags is None:
            self.tags = []


class ProfileManager:
    """Manager for Donut Browser profiles."""

    def __init__(self, profiles_dir: Optional[str] = None, proxies_dir: Optional[str] = None):
        """
        Initialize profile manager.

        Args:
            profiles_dir: Path to Donut Browser profiles directory.
                         Defaults to OS-specific path (see get_default_profiles_dir()).
            proxies_dir: Path to Donut Browser proxies directory.
                        Defaults to OS-specific path (see get_default_proxies_dir()).
        """
        if profiles_dir is None:
            profiles_dir = get_default_profiles_dir()

        if proxies_dir is None:
            proxies_dir = get_default_proxies_dir()

        self.profiles_dir = Path(profiles_dir)
        self.proxies_dir = Path(proxies_dir)

        if not self.profiles_dir.exists():
            raise FileNotFoundError(
                f"Donut Browser profiles directory not found: {self.profiles_dir}\n"
                f"Please ensure Donut Browser is installed and profiles are created."
            )

    def get_all_profiles(self) -> List[DonutProfile]:
        """
        Get all Donut Browser profiles.

        Returns:
            List of DonutProfile objects
        """
        profiles = []

        # Scan profiles directory
        for item in self.profiles_dir.iterdir():
            if not item.is_dir():
                continue

            metadata_file = item / "metadata.json"
            if not metadata_file.exists():
                continue

            try:
                profile = self._load_profile(item, metadata_file)
                profiles.append(profile)
            except Exception as e:
                print(f"Warning: Failed to load profile {item.name}: {e}")
                continue

        return sorted(profiles, key=lambda p: p.profile_name)

    def _load_proxy(self, proxy_id: str) -> Optional[str]:
        """
        Load proxy configuration by ID and return proxy URL string.

        Args:
            proxy_id: UUID of the proxy

        Returns:
            Proxy URL string (e.g., "http://user:pass@host:port") or None if not found
        """
        if not proxy_id:
            return None

        proxy_file = self.proxies_dir / f"{proxy_id}.json"
        if not proxy_file.exists():
            print(f"Warning: Proxy file not found: {proxy_file}")
            return None

        try:
            with open(proxy_file, 'r', encoding='utf-8') as f:
                proxy_data = json.load(f)

            settings = proxy_data.get('proxy_settings', {})
            proxy_type = settings.get('proxy_type', 'http')
            host = settings.get('host')
            port = settings.get('port')
            username = settings.get('username')
            password = settings.get('password')

            if not host or not port:
                print(f"Warning: Proxy missing host or port: {proxy_id}")
                return None

            # Build proxy URL
            if username and password:
                return f"{proxy_type}://{username}:{password}@{host}:{port}"
            else:
                return f"{proxy_type}://{host}:{port}"

        except Exception as e:
            print(f"Warning: Failed to load proxy {proxy_id}: {e}")
            return None

    def _load_profile(self, profile_dir: Path, metadata_file: Path) -> DonutProfile:
        """Load profile from metadata.json."""
        with open(metadata_file, 'r', encoding='utf-8') as f:
            metadata = json.load(f)

        # Extract camoufox config
        camoufox_config = metadata.get('camoufox_config', {})

        # Get proxy - first try camoufox_config.proxy, then resolve from proxy_id
        proxy = camoufox_config.get('proxy')
        proxy_id = metadata.get('proxy_id')

        if not proxy and proxy_id:
            # Resolve proxy from separate proxy file
            proxy = self._load_proxy(proxy_id)

        return DonutProfile(
            profile_id=metadata.get('id'),
            profile_name=metadata.get('name'),
            browser=metadata.get('browser', 'camoufox'),
            version=metadata.get('version', ''),
            profile_path=profile_dir,
            metadata_path=metadata_file,
            browser_data_path=profile_dir / "profile",
            executable_path=camoufox_config.get('executable_path'),
            fingerprint=camoufox_config.get('fingerprint'),
            proxy=proxy,
            proxy_id=proxy_id,
            process_id=metadata.get('process_id'),
            last_launch=metadata.get('last_launch'),
            release_type=metadata.get('release_type', 'stable'),
            group_id=metadata.get('group_id'),
            tags=metadata.get('tags', [])
        )

    def get_profile_by_id(self, profile_id: str) -> Optional[DonutProfile]:
        """
        Get profile by UUID.

        Args:
            profile_id: Profile UUID

        Returns:
            DonutProfile or None if not found
        """
        profile_dir = self.profiles_dir / profile_id
        metadata_file = profile_dir / "metadata.json"

        if not metadata_file.exists():
            return None

        try:
            return self._load_profile(profile_dir, metadata_file)
        except Exception:
            return None

    def get_profile_by_name(self, profile_name: str) -> Optional[DonutProfile]:
        """
        Get profile by name.

        Args:
            profile_name: Profile display name

        Returns:
            DonutProfile or None if not found
        """
        for profile in self.get_all_profiles():
            if profile.profile_name == profile_name:
                return profile
        return None

    def find_profiles_by_names(self, profile_names: List[str]) -> List[DonutProfile]:
        """
        Find profiles by names.

        Args:
            profile_names: List of profile display names

        Returns:
            List of found DonutProfile objects
        """
        all_profiles = self.get_all_profiles()
        found_profiles = []
        not_found = []

        for name in profile_names:
            profile = next((p for p in all_profiles if p.profile_name == name), None)
            if profile:
                found_profiles.append(profile)
            else:
                not_found.append(name)

        if not_found:
            available = ", ".join([p.profile_name for p in all_profiles])
            raise ValueError(
                f"Profiles not found: {', '.join(not_found)}\n"
                f"Available profiles: {available}"
            )

        return found_profiles

    def list_profile_names(self) -> List[str]:
        """Get list of all profile names."""
        return [p.profile_name for p in self.get_all_profiles()]

    def validate_profile(self, profile: DonutProfile) -> bool:
        """
        Validate that profile is ready for automation.

        Args:
            profile: DonutProfile to validate

        Returns:
            True if profile is valid

        Raises:
            ValueError: If profile is invalid
        """
        # Check browser type
        if profile.browser != "camoufox":
            raise ValueError(f"Only Camoufox profiles are supported, got: {profile.browser}")

        # Check profile directory exists
        if not profile.browser_data_path.exists():
            raise ValueError(f"Profile data directory not found: {profile.browser_data_path}")

        # Check executable path
        if not profile.executable_path:
            raise ValueError(f"Executable path not set for profile: {profile.profile_name}")

        if not Path(profile.executable_path).exists():
            raise ValueError(
                f"Camoufox executable not found: {profile.executable_path}\n"
                f"Please check profile configuration or download Camoufox browser."
            )

        # Check fingerprint
        if not profile.fingerprint:
            raise ValueError(f"Fingerprint not configured for profile: {profile.profile_name}")

        # Try to parse fingerprint JSON
        try:
            json.loads(profile.fingerprint)
        except json.JSONDecodeError:
            raise ValueError(f"Invalid fingerprint JSON for profile: {profile.profile_name}")

        return True

    def print_profiles_table(self):
        """Print table of available profiles."""
        profiles = self.get_all_profiles()

        if not profiles:
            print("No profiles found.")
            return

        # Print header
        print(f"\n{'Name':<20} {'ID':<36} {'Browser':<12} {'Proxy':<15}")
        print("-" * 85)

        # Print profiles
        for profile in profiles:
            proxy_display = "Not Set" if not profile.proxy else profile.proxy[:15]
            print(
                f"{profile.profile_name:<20} "
                f"{profile.profile_id:<36} "
                f"{profile.browser:<12} "
                f"{proxy_display:<15}"
            )

        print(f"\nTotal profiles: {len(profiles)}\n")


# Global profile manager instance
_profile_manager_instance: Optional[ProfileManager] = None


def get_profile_manager() -> ProfileManager:
    """Get global profile manager instance."""
    global _profile_manager_instance
    if _profile_manager_instance is None:
        _profile_manager_instance = ProfileManager()
    return _profile_manager_instance


def init_profile_manager(profiles_dir: Optional[str] = None) -> ProfileManager:
    """Initialize global profile manager instance."""
    global _profile_manager_instance
    _profile_manager_instance = ProfileManager(profiles_dir)
    return _profile_manager_instance


# =====================================================
# Convenience functions for scripts
# =====================================================

def get_all_profiles() -> List[DonutProfile]:
    """Get all Donut Browser profiles (convenience wrapper)."""
    return get_profile_manager().get_all_profiles()


def get_profile_by_name(profile_name: str) -> Optional[DonutProfile]:
    """Get profile by name (convenience wrapper)."""
    return get_profile_manager().get_profile_by_name(profile_name)


def get_profile_by_id(profile_id: str) -> Optional[DonutProfile]:
    """Get profile by ID (convenience wrapper)."""
    return get_profile_manager().get_profile_by_id(profile_id)


def print_profiles_table():
    """Print profiles table (convenience wrapper)."""
    return get_profile_manager().print_profiles_table()
