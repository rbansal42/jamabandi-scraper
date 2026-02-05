"""
Unit tests for the CookieCapture module.
"""

from unittest.mock import MagicMock, patch

import pytest

from scraper.config import reset_config
from scraper.cookie_capture import (
    WEBVIEW_AVAILABLE,
    CookieCaptureMethod,
    CookieCapture,
    extract_cookie_from_header,
)
from scraper.logger import reset_logging


class TestCookieCaptureMethod:
    """Tests for CookieCaptureMethod enum."""

    def test_manual_method_exists(self):
        """CookieCaptureMethod.MANUAL should exist."""
        assert CookieCaptureMethod.MANUAL is not None

    def test_webview_method_exists(self):
        """CookieCaptureMethod.WEBVIEW should exist."""
        assert CookieCaptureMethod.WEBVIEW is not None

    def test_enum_values_are_distinct(self):
        """MANUAL and WEBVIEW should have distinct values."""
        assert CookieCaptureMethod.MANUAL != CookieCaptureMethod.WEBVIEW


class TestExtractCookieFromHeader:
    """Tests for extract_cookie_from_header function."""

    def test_extract_single_cookie(self):
        """Should extract a single cookie from header."""
        header = "sessionID=abc123"
        result = extract_cookie_from_header(header, "sessionID")
        assert result == "abc123"

    def test_extract_from_multiple_cookies(self):
        """Should extract correct cookie when multiple are present."""
        header = "sessionID=abc123; jamabandiID=xyz789; other=value"
        result = extract_cookie_from_header(header, "jamabandiID")
        assert result == "xyz789"

    def test_cookie_not_found(self):
        """Should return None when cookie is not found."""
        header = "sessionID=abc123; other=value"
        result = extract_cookie_from_header(header, "jamabandiID")
        assert result is None

    def test_cookie_with_attributes(self):
        """Should handle cookie headers with attributes like Path, Expires."""
        header = "jamabandiID=xyz789; Path=/; HttpOnly; Secure"
        result = extract_cookie_from_header(header, "jamabandiID")
        assert result == "xyz789"

    def test_empty_header(self):
        """Should return None for empty header."""
        header = ""
        result = extract_cookie_from_header(header, "jamabandiID")
        assert result is None

    def test_none_header(self):
        """Should return None for None header."""
        result = extract_cookie_from_header(None, "jamabandiID")
        assert result is None


class TestCookieCaptureInitialization:
    """Tests for CookieCapture initialization."""

    def setup_method(self):
        """Reset config and logging before each test."""
        reset_config()
        reset_logging()

    def teardown_method(self):
        """Reset config and logging after each test."""
        reset_config()
        reset_logging()

    def test_default_method_manual_when_webview_unavailable(self):
        """Method should be MANUAL when webview is unavailable."""
        with patch("scraper.cookie_capture.WEBVIEW_AVAILABLE", False):
            capture = CookieCapture(prefer_webview=True)
            assert capture.method == CookieCaptureMethod.MANUAL

    def test_stores_login_url(self):
        """Should store login URL from config."""
        capture = CookieCapture()
        assert "login.aspx" in capture.login_url

    def test_stores_cookie_name(self):
        """Should store cookie name."""
        capture = CookieCapture()
        assert capture.cookie_name == "jamabandiID"

    def test_prefer_webview_false_uses_manual(self):
        """Should use MANUAL when prefer_webview is False even if available."""
        with patch("scraper.cookie_capture.WEBVIEW_AVAILABLE", True):
            capture = CookieCapture(prefer_webview=False)
            assert capture.method == CookieCaptureMethod.MANUAL

    def test_prefer_webview_true_uses_webview_when_available(self):
        """Should use WEBVIEW when prefer_webview is True and available."""
        with patch("scraper.cookie_capture.WEBVIEW_AVAILABLE", True):
            capture = CookieCapture(prefer_webview=True)
            assert capture.method == CookieCaptureMethod.WEBVIEW


class TestManualCapture:
    """Tests for manual cookie capture."""

    def setup_method(self):
        """Reset config and logging before each test."""
        reset_config()
        reset_logging()

    def teardown_method(self):
        """Reset config and logging after each test."""
        reset_config()
        reset_logging()

    def test_get_manual_instructions_returns_string(self):
        """get_manual_instructions should return a non-empty string."""
        capture = CookieCapture()
        instructions = capture.get_manual_instructions()
        assert isinstance(instructions, str)
        assert len(instructions) > 0

    def test_get_manual_instructions_contains_devtools(self):
        """Manual instructions should mention DevTools."""
        capture = CookieCapture()
        instructions = capture.get_manual_instructions()
        assert "DevTools" in instructions or "devtools" in instructions.lower()

    def test_validate_cookie_valid(self):
        """Should return True for valid cookie."""
        capture = CookieCapture()
        assert capture.validate_cookie("abc123xyz789") is True

    def test_validate_cookie_empty(self):
        """Should return False for empty cookie."""
        capture = CookieCapture()
        assert capture.validate_cookie("") is False

    def test_validate_cookie_whitespace_only(self):
        """Should return False for whitespace-only cookie."""
        capture = CookieCapture()
        assert capture.validate_cookie("   ") is False

    def test_validate_cookie_too_short(self):
        """Should return False for cookie shorter than 10 characters."""
        capture = CookieCapture()
        assert capture.validate_cookie("abc") is False

    def test_validate_cookie_min_length(self):
        """Should return True for cookie exactly 10 characters."""
        capture = CookieCapture()
        assert capture.validate_cookie("1234567890") is True

    def test_capture_manual_stores_valid_cookie(self):
        """capture_manual should store valid cookie and return True."""
        capture = CookieCapture()
        result = capture.capture_manual("validcookie123")
        assert result is True
        assert capture.get_captured_cookie() == "validcookie123"

    def test_capture_manual_rejects_invalid_cookie(self):
        """capture_manual should reject invalid cookie and return False."""
        capture = CookieCapture()
        result = capture.capture_manual("")
        assert result is False
        assert capture.get_captured_cookie() is None


class TestWebviewAvailability:
    """Tests for webview availability check."""

    def setup_method(self):
        """Reset config and logging before each test."""
        reset_config()
        reset_logging()

    def teardown_method(self):
        """Reset config and logging after each test."""
        reset_config()
        reset_logging()

    def test_is_webview_available_returns_boolean(self):
        """is_webview_available should return a boolean."""
        capture = CookieCapture()
        result = capture.is_webview_available()
        assert isinstance(result, bool)

    def test_is_webview_available_matches_constant(self):
        """is_webview_available should match WEBVIEW_AVAILABLE constant."""
        with patch("scraper.cookie_capture.WEBVIEW_AVAILABLE", True):
            capture = CookieCapture()
            # Need to reload/reimport or access the instance method
            # The method checks the module constant
        capture = CookieCapture()
        assert capture.is_webview_available() == WEBVIEW_AVAILABLE


class TestCookieCallback:
    """Tests for cookie capture callback."""

    def setup_method(self):
        """Reset config and logging before each test."""
        reset_config()
        reset_logging()

    def teardown_method(self):
        """Reset config and logging after each test."""
        reset_config()
        reset_logging()

    def test_on_cookie_captured_called(self):
        """on_cookie_captured callback should be called when cookie is captured."""
        capture = CookieCapture()
        callback = MagicMock()
        capture.on_cookie_captured = callback

        capture.capture_manual("validcookie123")

        callback.assert_called_once_with("validcookie123")

    def test_callback_not_called_on_invalid_cookie(self):
        """Callback should not be called when cookie is invalid."""
        capture = CookieCapture()
        callback = MagicMock()
        capture.on_cookie_captured = callback

        capture.capture_manual("")

        callback.assert_not_called()

    def test_callback_is_none_by_default(self):
        """on_cookie_captured should be None by default."""
        capture = CookieCapture()
        assert capture.on_cookie_captured is None


class TestWebviewCapture:
    """Tests for webview-based cookie capture."""

    def setup_method(self):
        """Reset config and logging before each test."""
        reset_config()
        reset_logging()

    def teardown_method(self):
        """Reset config and logging after each test."""
        reset_config()
        reset_logging()

    def test_capture_webview_returns_none_when_unavailable(self):
        """capture_webview should return None when webview is unavailable."""
        with patch("scraper.cookie_capture.WEBVIEW_AVAILABLE", False):
            capture = CookieCapture()
            result = capture.capture_webview()
            assert result is None
