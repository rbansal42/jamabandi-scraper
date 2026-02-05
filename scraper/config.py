"""
Configuration module with YAML support and defaults.

Provides a singleton Config class for managing application settings
with support for nested access via dot notation.
"""

from __future__ import annotations

import copy
import threading
from pathlib import Path
from typing import Any, Optional

import yaml

# Thread lock for singleton initialization
_config_lock = threading.Lock()


DEFAULTS = {
    "urls": {
        "base_url": "https://jamabandi.nic.in",
        "form_path": "/PublicNakal/CreateNewRequest",
        "login_path": "/PublicNakal/login.aspx",
    },
    "http": {
        "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:147.0) Gecko/20100101 Firefox/147.0",
        "timeout": 30,
        "verify_ssl": False,
    },
    "delays": {
        "min_delay": 1.0,
        "max_delay": 2.5,
        "form_postback_sleep": 0.25,
    },
    "retry": {
        "max_retries": 3,
        "retry_delay": 5.0,
    },
    "concurrency": {
        "max_workers": 8,
        "default_workers": 3,
    },
    "paths": {
        "downloads_dir": "downloads",
        "logs_dir": "logs",
        "progress_file": "progress.json",
    },
    "logging": {
        "level": "INFO",
        "max_file_size_mb": 10,
        "backup_count": 5,
    },
}


def _deep_merge(base: dict, override: dict) -> dict:
    """
    Deep merge override dict into base dict.

    Values in override take precedence. Nested dicts are merged recursively.
    Returns a new dict without modifying the inputs.
    """
    result = copy.deepcopy(base)
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = (
                copy.deepcopy(value) if isinstance(value, (dict, list)) else value
            )
    return result


class _SectionProxy:
    """
    Proxy class that provides both dict-like and attribute access to config sections.
    This enables compatibility with code that uses config.paths.logs_dir style access.
    """

    def __init__(self, data: dict):
        self._data = data

    def __getitem__(self, key: str) -> Any:
        return self._data[key]

    def __getattr__(self, name: str) -> Any:
        if name.startswith("_"):
            return object.__getattribute__(self, name)
        try:
            value = self._data[name]
            # Convert path strings to Path objects for paths section
            if isinstance(value, str) and (
                "dir" in name or "file" in name or "path" in name.lower()
            ):
                return Path(value)
            return value
        except KeyError:
            raise AttributeError(f"Config section has no attribute '{name}'")

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    def __contains__(self, key: str) -> bool:
        return key in self._data

    def keys(self):
        return self._data.keys()

    def values(self):
        return self._data.values()

    def items(self):
        return self._data.items()


class Config:
    """
    Singleton configuration class with YAML support.

    Usage:
        config = Config()
        base_url = config.get("urls.base_url")
        timeout = config.http["timeout"]
    """

    _instance: Optional[Config] = None
    _initialized: bool = False

    def __new__(cls, config_path: Optional[str] = None) -> Config:
        if cls._instance is None:
            with _config_lock:
                # Double-checked locking for thread safety
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, config_path: Optional[str] = None) -> None:
        # Skip re-initialization if already done (singleton)
        if Config._initialized:
            return

        self._data: dict = {}
        self._config_path = config_path or self._find_config_file()
        self._load()
        Config._initialized = True

    def _find_config_file(self) -> Optional[str]:
        """Find config.yaml in current directory or project root."""
        # Check current directory
        if Path("config.yaml").exists():
            return "config.yaml"

        # Check relative to this file's directory (project root)
        project_root = Path(__file__).parent.parent
        config_file = project_root / "config.yaml"
        if config_file.exists():
            return str(config_file)

        return None

    def _load(self) -> None:
        """Load configuration from YAML file, merged over defaults."""
        # Use deep copy to avoid modifying DEFAULTS
        self._data = copy.deepcopy(DEFAULTS)

        if self._config_path and Path(self._config_path).exists():
            with open(self._config_path, "r", encoding="utf-8") as f:
                user_config = yaml.safe_load(f) or {}
            self._data = _deep_merge(DEFAULTS, user_config)

    def get(self, key: str, default: Any = None) -> Any:
        """
        Get a config value using dot notation.

        Args:
            key: Dot-separated key path (e.g., "urls.base_url")
            default: Value to return if key not found

        Returns:
            The config value or default if not found
        """
        keys = key.split(".")
        value = self._data

        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return default

        return value

    @property
    def urls(self) -> _SectionProxy:
        """Access urls configuration section."""
        return _SectionProxy(self._data.get("urls", {}))

    @property
    def http(self) -> _SectionProxy:
        """Access http configuration section."""
        return _SectionProxy(self._data.get("http", {}))

    @property
    def delays(self) -> _SectionProxy:
        """Access delays configuration section."""
        return _SectionProxy(self._data.get("delays", {}))

    @property
    def retry(self) -> _SectionProxy:
        """Access retry configuration section."""
        return _SectionProxy(self._data.get("retry", {}))

    @property
    def concurrency(self) -> _SectionProxy:
        """Access concurrency configuration section."""
        return _SectionProxy(self._data.get("concurrency", {}))

    @property
    def paths(self) -> _SectionProxy:
        """Access paths configuration section."""
        return _SectionProxy(self._data.get("paths", {}))

    @property
    def logging(self) -> _SectionProxy:
        """Access logging configuration section."""
        return _SectionProxy(self._data.get("logging", {}))

    @classmethod
    def reset(cls) -> None:
        """
        Reset the singleton instance.

        Useful for testing to get a fresh config instance.
        """
        cls._instance = None
        cls._initialized = False

    def reload(self, config_path: Optional[str] = None) -> None:
        """
        Reload configuration from file.

        Args:
            config_path: Optional new path to config file
        """
        if config_path:
            self._config_path = config_path
        self._load()


# Backward compatibility functions for logger.py
def get_config() -> Config:
    """Get the global configuration instance."""
    return Config()


def reset_config() -> None:
    """Reset the configuration singleton (useful for testing)."""
    Config.reset()
