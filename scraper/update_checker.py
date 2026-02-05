"""
Update checker for Jamabandi Scraper.

Checks GitHub releases for new versions on startup.
No auto-update - just notifies user with download link.
"""

import re
import threading
from dataclasses import dataclass
from typing import Callable, Optional
from packaging import version

import requests

from .logger import get_logger

logger = get_logger("update_checker")

# Current application version
__version__ = "1.1.0"

# GitHub repository info
GITHUB_OWNER = "rbansal42"
GITHUB_REPO = "jamabandi-scraper"
RELEASES_API_URL = (
    f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/releases/latest"
)
RELEASES_PAGE_URL = f"https://github.com/{GITHUB_OWNER}/{GITHUB_REPO}/releases/latest"


@dataclass
class UpdateInfo:
    """Information about an available update."""

    current_version: str
    latest_version: str
    release_url: str
    release_notes: str
    is_update_available: bool


class UpdateChecker:
    """
    Checks for application updates from GitHub releases.

    Usage:
        checker = UpdateChecker()
        checker.check_async(callback=on_update_result)

        # Or synchronous:
        info = checker.check()
        if info.is_update_available:
            print(f"Update available: {info.latest_version}")
    """

    def __init__(
        self,
        current_version: str = __version__,
        timeout: float = 10.0,
    ):
        """
        Initialize update checker.

        Args:
            current_version: Current application version (semver).
            timeout: HTTP request timeout in seconds.
        """
        self.current_version = current_version
        self.timeout = timeout
        self._check_thread: Optional[threading.Thread] = None

    def check(self) -> UpdateInfo:
        """
        Check for updates synchronously.

        Returns:
            UpdateInfo with version comparison results.
        """
        try:
            logger.info("Checking for updates...")

            response = requests.get(
                RELEASES_API_URL,
                timeout=self.timeout,
                headers={"Accept": "application/vnd.github.v3+json"},
            )
            response.raise_for_status()

            data = response.json()
            latest_tag = data.get("tag_name", "")
            release_notes = data.get("body", "")
            release_url = data.get("html_url", RELEASES_PAGE_URL)

            # Parse version (remove 'v' prefix if present)
            latest_version = self._normalize_version(latest_tag)
            current_normalized = self._normalize_version(self.current_version)

            is_update_available = self._is_newer(latest_version, current_normalized)

            if is_update_available:
                logger.info(
                    f"Update available: {latest_version} (current: {current_normalized})"
                )
            else:
                logger.info(f"Already on latest version: {current_normalized}")

            return UpdateInfo(
                current_version=current_normalized,
                latest_version=latest_version,
                release_url=release_url,
                release_notes=release_notes or "",
                is_update_available=is_update_available,
            )

        except requests.RequestException as e:
            logger.warning(f"Failed to check for updates: {e}")
            return UpdateInfo(
                current_version=self.current_version,
                latest_version=self.current_version,
                release_url=RELEASES_PAGE_URL,
                release_notes="",
                is_update_available=False,
            )
        except Exception as e:
            logger.error(f"Unexpected error checking for updates: {e}")
            return UpdateInfo(
                current_version=self.current_version,
                latest_version=self.current_version,
                release_url=RELEASES_PAGE_URL,
                release_notes="",
                is_update_available=False,
            )

    def check_async(
        self,
        callback: Callable[[UpdateInfo], None],
        error_callback: Optional[Callable[[Exception], None]] = None,
    ) -> None:
        """
        Check for updates asynchronously.

        Args:
            callback: Called with UpdateInfo when check completes.
            error_callback: Called if an error occurs (optional).
        """

        def _check_worker():
            try:
                info = self.check()
                callback(info)
            except Exception as e:
                logger.error(f"Async update check failed: {e}")
                if error_callback:
                    error_callback(e)

        self._check_thread = threading.Thread(target=_check_worker, daemon=True)
        self._check_thread.start()

    def _normalize_version(self, ver: str) -> str:
        """Normalize version string (remove 'v' prefix)."""
        ver = ver.strip()
        if ver.startswith("v"):
            ver = ver[1:]
        return ver

    def _is_newer(self, latest: str, current: str) -> bool:
        """Check if latest version is newer than current."""
        try:
            return version.parse(latest) > version.parse(current)
        except Exception:
            # Fallback to string comparison if version parsing fails
            return latest != current and latest > current


def get_current_version() -> str:
    """Get the current application version."""
    return __version__


def check_for_updates(callback: Callable[[UpdateInfo], None]) -> None:
    """
    Convenience function to check for updates asynchronously.

    Args:
        callback: Called with UpdateInfo when check completes.
    """
    checker = UpdateChecker()
    checker.check_async(callback)
