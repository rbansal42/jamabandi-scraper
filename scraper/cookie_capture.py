"""
Cookie capture module for Jamabandi Scraper.

Provides manual and optional webview-based cookie capture
for authenticated session handling.
"""

from __future__ import annotations

from enum import Enum
from typing import Callable, Optional

from .config import Config
from .logger import get_logger

# Try to import webview, set availability constant
try:
    import webview

    WEBVIEW_AVAILABLE = True
except ImportError:
    WEBVIEW_AVAILABLE = False


class CookieCaptureMethod(Enum):
    """Enumeration of cookie capture methods."""

    MANUAL = "manual"
    WEBVIEW = "webview"


def extract_cookie_from_header(
    header: Optional[str], cookie_name: str
) -> Optional[str]:
    """
    Extract a specific cookie value from a cookie header string.

    Args:
        header: Cookie header string (e.g., "name=value; other=foo")
        cookie_name: Name of the cookie to extract

    Returns:
        Cookie value if found, None otherwise
    """
    if not header:
        return None

    # Split by semicolon to get individual cookies/attributes
    parts = header.split(";")

    for part in parts:
        part = part.strip()
        if "=" in part:
            name, _, value = part.partition("=")
            if name.strip() == cookie_name:
                return value.strip()

    return None


class CookieCapture:
    """
    Cookie capture handler supporting manual and webview methods.

    Usage:
        capture = CookieCapture()

        # Manual capture
        print(capture.get_manual_instructions())
        capture.capture_manual(user_provided_cookie)

        # Or webview capture (if available)
        if capture.is_webview_available():
            capture.capture_webview()
    """

    def __init__(self, prefer_webview: bool = True) -> None:
        """
        Initialize cookie capture handler.

        Args:
            prefer_webview: Whether to prefer webview method if available
        """
        self._config = Config()
        self._logger = get_logger("cookie_capture")
        self._prefer_webview = prefer_webview
        self._captured_cookie: Optional[str] = None

        # Get login URL from config
        base_url = self._config.get("urls.base_url", "https://jamabandi.nic.in")
        login_path = self._config.get("urls.login_path", "/PublicNakal/login.aspx")
        self._login_url = f"{base_url}{login_path}"

        self._cookie_name = "jamabandiID"

        # Callback for when cookie is captured
        self.on_cookie_captured: Optional[Callable[[str], None]] = None

    @property
    def login_url(self) -> str:
        """Get the login URL."""
        return self._login_url

    @property
    def cookie_name(self) -> str:
        """Get the cookie name to capture."""
        return self._cookie_name

    @property
    def method(self) -> CookieCaptureMethod:
        """Get the current capture method based on availability and preference."""
        if self._prefer_webview and WEBVIEW_AVAILABLE:
            return CookieCaptureMethod.WEBVIEW
        return CookieCaptureMethod.MANUAL

    def is_webview_available(self) -> bool:
        """
        Check if webview capture is available.

        Returns:
            True if pywebview is installed and available
        """
        return WEBVIEW_AVAILABLE

    def get_manual_instructions(self) -> str:
        """
        Get step-by-step instructions for manual cookie capture.

        Returns:
            Detailed instructions string for manual capture
        """
        return f"""
Manual Cookie Capture Instructions
==================================

To capture the '{self._cookie_name}' cookie, follow these steps:

1. Open your web browser (Chrome, Firefox, or Edge recommended)

2. Navigate to: {self._login_url}

3. Complete the login process:
   - Enter your credentials
   - Solve any CAPTCHA if presented
   - Click the login/submit button

4. Open Developer Tools (DevTools):
   - Chrome/Edge: Press F12 or Ctrl+Shift+I (Cmd+Option+I on Mac)
   - Firefox: Press F12 or Ctrl+Shift+I (Cmd+Option+I on Mac)

5. Navigate to the Application/Storage tab:
   - Chrome/Edge: Click "Application" tab, then "Cookies" in sidebar
   - Firefox: Click "Storage" tab, then "Cookies" in sidebar

6. Find the cookie named '{self._cookie_name}':
   - Look for the domain: jamabandi.nic.in
   - Find the row with Name: {self._cookie_name}
   - Copy the Value column content

7. Paste the cookie value when prompted

Note: The cookie value should be a long alphanumeric string (at least 10 characters).
"""

    # Minimum cookie length for validation
    MIN_COOKIE_LENGTH = 10

    # Characters that could enable HTTP header injection attacks
    DANGEROUS_CHARS = "\r\n\x00"

    def validate_cookie(self, cookie: str) -> bool:
        """
        Validate a cookie value.

        Args:
            cookie: Cookie value to validate

        Returns:
            True if cookie is valid, False otherwise
        """
        if not cookie:
            return False

        # Strip whitespace
        cookie = cookie.strip()

        if not cookie:
            return False

        # Must be at least MIN_COOKIE_LENGTH characters
        if len(cookie) < self.MIN_COOKIE_LENGTH:
            return False

        # Check for dangerous characters (HTTP header injection prevention)
        if any(c in cookie for c in self.DANGEROUS_CHARS):
            self._logger.warning("Cookie contains dangerous characters")
            return False

        return True

    def capture_manual(self, cookie: str) -> bool:
        """
        Capture cookie from manually provided value.

        Args:
            cookie: Cookie value provided by user

        Returns:
            True if cookie was valid and stored, False otherwise
        """
        if not self.validate_cookie(cookie):
            self._logger.warning("Invalid cookie provided for manual capture")
            return False

        self._captured_cookie = cookie.strip()
        self._logger.info("Cookie captured successfully via manual method")
        self._notify_cookie_captured(self._captured_cookie)
        return True

    def capture_webview(self, timeout: float = 300.0) -> Optional[str]:
        """
        Capture cookie using webview window.

        Opens a webview window with the login page and captures the
        session cookie after successful login.

        Args:
            timeout: Maximum time to wait for login in seconds

        Returns:
            Captured cookie value, or None if capture failed
        """
        if not WEBVIEW_AVAILABLE:
            self._logger.warning("Webview not available, cannot capture via webview")
            return None

        self._logger.info(f"Opening webview for cookie capture (timeout: {timeout}s)")

        captured_cookie: Optional[str] = None

        def on_loaded():
            """Callback when page loads - check for cookie."""
            nonlocal captured_cookie
            try:
                # Get cookies from the webview
                cookies = window.get_cookies()
                for cookie in cookies:
                    if cookie.get("name") == self._cookie_name:
                        captured_cookie = cookie.get("value")
                        if self.validate_cookie(captured_cookie):
                            self._captured_cookie = captured_cookie
                            self._notify_cookie_captured(captured_cookie)
                            window.destroy()
                            return
            except Exception as e:
                self._logger.error(f"Error checking cookies: {e}")

        # Create webview window
        window = webview.create_window(
            title="Jamabandi Login - Cookie Capture",
            url=self._login_url,
            width=1000,
            height=700,
        )

        # Set up page loaded callback
        window.events.loaded += on_loaded

        # Start webview (blocks until window is closed)
        webview.start()

        return captured_cookie

    def get_captured_cookie(self) -> Optional[str]:
        """
        Get the captured cookie value.

        Returns:
            Captured cookie value, or None if not captured
        """
        return self._captured_cookie

    def _notify_cookie_captured(self, cookie: str) -> None:
        """
        Notify callback that cookie was captured.

        Args:
            cookie: The captured cookie value
        """
        if self.on_cookie_captured is not None:
            try:
                self.on_cookie_captured(cookie)
            except Exception as e:
                self._logger.error(f"Error in cookie capture callback: {e}")
