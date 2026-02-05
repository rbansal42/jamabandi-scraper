"""Session manager for detecting expiry and coordinating re-authentication."""

import threading
from enum import Enum
from typing import Callable, Optional

from .logger import get_logger

logger = get_logger("session")


class SessionState(Enum):
    """Enum representing the current session state."""

    ACTIVE = "active"
    EXPIRED = "expired"
    REFRESHING = "refreshing"


class SessionExpiredError(Exception):
    """Raised when session expires and cannot be refreshed in time."""

    pass


# Patterns indicating session expiry in URL
EXPIRY_URL_PATTERNS = ["login.aspx", "login.asp", "/login"]

# Patterns indicating session expiry in content (case-insensitive)
EXPIRY_CONTENT_PATTERNS = [
    "enter mobile",
    "session has timed out",
    "session expired",
    "please login",
    "please log in",
    "authentication required",
]


class SessionManager:
    """
    Manages session state, detects expiry, and coordinates re-authentication.

    Thread-safe implementation using locks and events for coordination.
    """

    def __init__(self, cookie: str):
        """
        Initialize the session manager.

        Args:
            cookie: The initial session cookie value
        """
        self._cookie = cookie
        self._state = SessionState.ACTIVE
        self._lock = threading.Lock()
        self._active_event = threading.Event()
        self._active_event.set()  # Initially active

        # Callbacks
        self._on_session_expired: Optional[Callable[[], None]] = None
        self._on_session_refreshed: Optional[Callable[[str], None]] = None

    @property
    def cookie(self) -> str:
        """Get the current session cookie (thread-safe)."""
        with self._lock:
            return self._cookie

    @property
    def state(self) -> SessionState:
        """Get the current session state (thread-safe)."""
        with self._lock:
            return self._state

    @property
    def on_session_expired(self) -> Optional[Callable[[], None]]:
        """Get the session expired callback."""
        return self._on_session_expired

    @on_session_expired.setter
    def on_session_expired(self, callback: Optional[Callable[[], None]]) -> None:
        """Set the session expired callback."""
        self._on_session_expired = callback

    @property
    def on_session_refreshed(self) -> Optional[Callable[[str], None]]:
        """Get the session refreshed callback."""
        return self._on_session_refreshed

    @on_session_refreshed.setter
    def on_session_refreshed(self, callback: Optional[Callable[[str], None]]) -> None:
        """Set the session refreshed callback."""
        self._on_session_refreshed = callback

    def is_session_expired_response(self, url: str, content: str) -> bool:
        """
        Check if a response indicates session expiry.

        Args:
            url: The response URL (may have been redirected)
            content: The response body content

        Returns:
            True if the response indicates session expiry
        """
        # Check URL patterns
        url_lower = url.lower()
        for pattern in EXPIRY_URL_PATTERNS:
            if pattern.lower() in url_lower:
                return True

        # Check content patterns (case-insensitive)
        content_lower = content.lower()
        for pattern in EXPIRY_CONTENT_PATTERNS:
            if pattern.lower() in content_lower:
                return True

        return False

    def mark_expired(self) -> None:
        """
        Mark the session as expired.

        Clears the active event and calls the expired callback.
        """
        callback = None
        with self._lock:
            if self._state != SessionState.EXPIRED:
                self._state = SessionState.EXPIRED
                self._active_event.clear()
                callback = self._on_session_expired
                logger.warning("Session marked as expired")

        # Call callback outside lock to prevent deadlocks
        if callback is not None:
            try:
                callback()
            except Exception as e:
                logger.exception(f"Error in session expired callback: {e}")

    def mark_refreshing(self) -> None:
        """Mark the session as being refreshed."""
        with self._lock:
            if self._state == SessionState.EXPIRED:
                self._state = SessionState.REFRESHING
                logger.info("Session refresh in progress")

    def update_cookie(self, new_cookie: str) -> None:
        """
        Update the session cookie and mark session as active.

        Args:
            new_cookie: The new session cookie value
        """
        callback = None
        with self._lock:
            self._cookie = new_cookie
            self._state = SessionState.ACTIVE
            self._active_event.set()
            callback = self._on_session_refreshed
            logger.info("Session cookie updated, session is now active")

        # Call callback outside lock to prevent deadlocks
        if callback is not None:
            try:
                callback(new_cookie)
            except Exception as e:
                logger.exception(f"Error in session refreshed callback: {e}")

    def wait_for_valid_session(self, timeout: float = 300.0) -> None:
        """
        Wait for the session to become active.

        Blocks until the session is active or timeout is reached.

        Args:
            timeout: Maximum time to wait in seconds (default: 300)

        Raises:
            SessionExpiredError: If timeout is reached before session becomes active
        """
        if not self._active_event.wait(timeout=timeout):
            raise SessionExpiredError(
                f"Session did not become active within {timeout} seconds"
            )

    def check_and_handle_response(self, url: str, content: str) -> bool:
        """
        Check a response for session expiry and handle if expired.

        Args:
            url: The response URL
            content: The response body content

        Returns:
            True if session was detected as expired, False otherwise
        """
        if self.is_session_expired_response(url, content):
            self.mark_expired()
            return True
        return False
