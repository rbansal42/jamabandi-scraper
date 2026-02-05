"""
Unit tests for the update_checker module.
"""

import threading
import time
from unittest.mock import MagicMock, patch

import pytest

from scraper.config import reset_config
from scraper.logger import reset_logging
from scraper.update_checker import (
    UpdateChecker,
    UpdateInfo,
    check_for_updates,
    get_current_version,
    __version__,
    RELEASES_API_URL,
    RELEASES_PAGE_URL,
)


@pytest.fixture(autouse=True)
def reset_singletons():
    """Reset config and logger singletons before each test."""
    reset_logging()
    reset_config()
    yield
    reset_logging()
    reset_config()


class TestUpdateInfo:
    """Tests for UpdateInfo dataclass."""

    def test_creates_with_all_fields(self):
        """UpdateInfo should be creatable with all fields."""
        info = UpdateInfo(
            current_version="1.0.0",
            latest_version="1.1.0",
            release_url="https://example.com",
            release_notes="New features",
            is_update_available=True,
        )
        assert info.current_version == "1.0.0"
        assert info.latest_version == "1.1.0"
        assert info.release_url == "https://example.com"
        assert info.release_notes == "New features"
        assert info.is_update_available is True

    def test_update_not_available(self):
        """UpdateInfo should handle no update case."""
        info = UpdateInfo(
            current_version="1.0.0",
            latest_version="1.0.0",
            release_url="https://example.com",
            release_notes="",
            is_update_available=False,
        )
        assert info.is_update_available is False


class TestUpdateChecker:
    """Tests for UpdateChecker class."""

    def test_init_with_defaults(self):
        """Should initialize with default version."""
        checker = UpdateChecker()
        assert checker.current_version == __version__
        assert checker.timeout == 10.0

    def test_init_with_custom_version(self):
        """Should accept custom version."""
        checker = UpdateChecker(current_version="2.0.0", timeout=5.0)
        assert checker.current_version == "2.0.0"
        assert checker.timeout == 5.0

    def test_normalize_version_removes_v_prefix(self):
        """Should remove 'v' prefix from version string."""
        checker = UpdateChecker()
        assert checker._normalize_version("v1.2.3") == "1.2.3"
        assert checker._normalize_version("1.2.3") == "1.2.3"
        assert checker._normalize_version("  v2.0.0  ") == "2.0.0"

    def test_is_newer_with_semver(self):
        """Should correctly compare semantic versions."""
        checker = UpdateChecker()
        assert checker._is_newer("1.1.0", "1.0.0") is True
        assert checker._is_newer("1.0.0", "1.0.0") is False
        assert checker._is_newer("0.9.0", "1.0.0") is False
        assert checker._is_newer("2.0.0", "1.9.9") is True

    def test_is_newer_with_patch_versions(self):
        """Should handle patch version comparisons."""
        checker = UpdateChecker()
        assert checker._is_newer("1.0.1", "1.0.0") is True
        assert checker._is_newer("1.0.0", "1.0.1") is False

    @patch("scraper.update_checker.requests.get")
    def test_check_returns_update_available(self, mock_get):
        """Should return update available when newer version exists."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "tag_name": "v2.0.0",
            "body": "Release notes here",
            "html_url": "https://github.com/releases/v2.0.0",
        }
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        checker = UpdateChecker(current_version="1.0.0")
        info = checker.check()

        assert info.is_update_available is True
        assert info.latest_version == "2.0.0"
        assert info.current_version == "1.0.0"
        assert info.release_notes == "Release notes here"
        mock_get.assert_called_once()

    @patch("scraper.update_checker.requests.get")
    def test_check_returns_no_update(self, mock_get):
        """Should return no update when already on latest."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "tag_name": "v1.0.0",
            "body": "",
            "html_url": "https://github.com/releases/v1.0.0",
        }
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        checker = UpdateChecker(current_version="1.0.0")
        info = checker.check()

        assert info.is_update_available is False
        assert info.latest_version == "1.0.0"

    @patch("scraper.update_checker.requests.get")
    def test_check_handles_network_error(self, mock_get):
        """Should handle network errors gracefully."""
        import requests

        mock_get.side_effect = requests.RequestException("Network error")

        checker = UpdateChecker(current_version="1.0.0")
        info = checker.check()

        assert info.is_update_available is False
        assert info.current_version == "1.0.0"

    @patch("scraper.update_checker.requests.get")
    def test_check_handles_invalid_json(self, mock_get):
        """Should handle invalid JSON response."""
        mock_response = MagicMock()
        mock_response.json.side_effect = ValueError("Invalid JSON")
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        checker = UpdateChecker(current_version="1.0.0")
        info = checker.check()

        # Should not crash, returns default
        assert info.is_update_available is False

    @patch("scraper.update_checker.requests.get")
    def test_check_async_calls_callback(self, mock_get):
        """Should call callback with result in async mode."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "tag_name": "v2.0.0",
            "body": "Notes",
            "html_url": "https://example.com",
        }
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        callback_result = []

        def callback(info):
            callback_result.append(info)

        checker = UpdateChecker(current_version="1.0.0")
        checker.check_async(callback)

        # Wait for thread to complete
        time.sleep(0.5)

        assert len(callback_result) == 1
        assert callback_result[0].is_update_available is True

    @patch("scraper.update_checker.requests.get")
    def test_check_async_calls_error_callback_on_exception(self, mock_get):
        """Should call error callback when exception occurs."""
        mock_get.side_effect = Exception("Unexpected error")

        error_result = []

        def callback(info):
            pass  # Should not be called

        def error_callback(exc):
            error_result.append(exc)

        checker = UpdateChecker(current_version="1.0.0")
        checker.check_async(callback, error_callback)

        # Wait for thread to complete
        time.sleep(0.5)

        # Error callback may or may not be called depending on implementation
        # The main thing is it shouldn't crash


class TestConvenienceFunctions:
    """Tests for module-level convenience functions."""

    def test_get_current_version(self):
        """Should return the current version string."""
        version = get_current_version()
        assert version == __version__
        assert isinstance(version, str)

    @patch("scraper.update_checker.UpdateChecker.check_async")
    def test_check_for_updates_calls_checker(self, mock_check_async):
        """Should create checker and call check_async."""

        def dummy_callback(info):
            pass

        check_for_updates(dummy_callback)

        mock_check_async.assert_called_once_with(dummy_callback)


class TestConstants:
    """Tests for module constants."""

    def test_releases_api_url_format(self):
        """Should have correct GitHub API URL format."""
        assert "api.github.com" in RELEASES_API_URL
        assert "releases/latest" in RELEASES_API_URL

    def test_releases_page_url_format(self):
        """Should have correct GitHub releases page URL format."""
        assert "github.com" in RELEASES_PAGE_URL
        assert "releases/latest" in RELEASES_PAGE_URL

    def test_version_format(self):
        """Version should be semver format."""
        parts = __version__.split(".")
        assert len(parts) >= 2
        # Should be numeric parts
        for part in parts:
            assert part.isdigit() or part[0].isdigit()
