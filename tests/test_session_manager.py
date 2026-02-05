"""
Unit tests for the SessionManager module.

Tests cover:
- SessionState enum values
- Initialization (initial state ACTIVE, stores cookie)
- Expiry detection (login redirect, enter mobile text, session timeout text, valid response not expired)
- State transitions (mark_expired, mark_refreshing, update_cookie restores active)
- Callbacks (expiry callback called, refresh callback called with cookie)
- Waiting (returns immediately when active, blocks when expired, raises on timeout)
- Thread safety (concurrent state changes)
"""

import threading
import time

import pytest

from scraper.config import reset_config
from scraper.logger import reset_logging
from scraper.session_manager import (
    EXPIRY_CONTENT_PATTERNS,
    EXPIRY_URL_PATTERNS,
    SessionExpiredError,
    SessionManager,
    SessionState,
)


class TestSessionStateEnum:
    """Tests for the SessionState enum."""

    def test_active_value(self):
        """ACTIVE should have value 'active'."""
        assert SessionState.ACTIVE.value == "active"

    def test_expired_value(self):
        """EXPIRED should have value 'expired'."""
        assert SessionState.EXPIRED.value == "expired"

    def test_refreshing_value(self):
        """REFRESHING should have value 'refreshing'."""
        assert SessionState.REFRESHING.value == "refreshing"


class TestSessionExpiredError:
    """Tests for the SessionExpiredError exception."""

    def test_can_raise_session_expired_error(self):
        """SessionExpiredError should be raisable with a message."""
        with pytest.raises(SessionExpiredError) as exc_info:
            raise SessionExpiredError("Session timed out")
        assert "Session timed out" in str(exc_info.value)

    def test_inherits_from_exception(self):
        """SessionExpiredError should inherit from Exception."""
        assert issubclass(SessionExpiredError, Exception)


class TestInitialization:
    """Tests for SessionManager initialization."""

    def setup_method(self):
        reset_config()
        reset_logging()

    def teardown_method(self):
        reset_config()
        reset_logging()

    def test_initial_state_is_active(self):
        """New SessionManager should have ACTIVE state."""
        manager = SessionManager(cookie="test_cookie")
        assert manager.state == SessionState.ACTIVE

    def test_stores_initial_cookie(self):
        """SessionManager should store the initial cookie."""
        manager = SessionManager(cookie="my_session_cookie")
        assert manager.cookie == "my_session_cookie"

    def test_cookie_property_returns_current_cookie(self):
        """cookie property should return the current cookie value."""
        manager = SessionManager(cookie="initial_cookie")
        assert manager.cookie == "initial_cookie"


class TestExpiryDetection:
    """Tests for session expiry detection."""

    def setup_method(self):
        reset_config()
        reset_logging()
        self.manager = SessionManager(cookie="test_cookie")

    def teardown_method(self):
        reset_config()
        reset_logging()

    def test_login_aspx_url_detected(self):
        """URL containing login.aspx should be detected as expired."""
        result = self.manager.is_session_expired_response(
            url="https://example.com/login.aspx",
            content="<html>Login Page</html>",
        )
        assert result is True

    def test_login_asp_url_detected(self):
        """URL containing login.asp should be detected as expired."""
        result = self.manager.is_session_expired_response(
            url="https://example.com/login.asp",
            content="<html>Login Page</html>",
        )
        assert result is True

    def test_login_path_url_detected(self):
        """URL containing /login should be detected as expired."""
        result = self.manager.is_session_expired_response(
            url="https://example.com/login",
            content="<html>Login Page</html>",
        )
        assert result is True

    def test_enter_mobile_content_detected(self):
        """Content with 'enter mobile' should be detected as expired."""
        result = self.manager.is_session_expired_response(
            url="https://example.com/page",
            content="<html>Please Enter Mobile number to continue</html>",
        )
        assert result is True

    def test_session_timed_out_content_detected(self):
        """Content with 'session has timed out' should be detected as expired."""
        result = self.manager.is_session_expired_response(
            url="https://example.com/page",
            content="<html>Your session has timed out. Please login again.</html>",
        )
        assert result is True

    def test_session_expired_content_detected(self):
        """Content with 'session expired' should be detected as expired."""
        result = self.manager.is_session_expired_response(
            url="https://example.com/page",
            content="<html>Session expired, please authenticate.</html>",
        )
        assert result is True

    def test_please_login_content_detected(self):
        """Content with 'please login' should be detected as expired."""
        result = self.manager.is_session_expired_response(
            url="https://example.com/page",
            content="<html>Please login to continue</html>",
        )
        assert result is True

    def test_please_log_in_content_detected(self):
        """Content with 'please log in' should be detected as expired."""
        result = self.manager.is_session_expired_response(
            url="https://example.com/page",
            content="<html>Please log in to access this page</html>",
        )
        assert result is True

    def test_authentication_required_content_detected(self):
        """Content with 'authentication required' should be detected as expired."""
        result = self.manager.is_session_expired_response(
            url="https://example.com/page",
            content="<html>Authentication required</html>",
        )
        assert result is True

    def test_valid_response_not_expired(self):
        """Valid response without expiry patterns should not be detected as expired."""
        result = self.manager.is_session_expired_response(
            url="https://example.com/data",
            content="<html>Here is your data: successful response</html>",
        )
        assert result is False

    def test_case_insensitive_url_detection(self):
        """URL pattern matching should be case-insensitive."""
        result = self.manager.is_session_expired_response(
            url="https://example.com/LOGIN.ASPX",
            content="<html>Page</html>",
        )
        assert result is True

    def test_case_insensitive_content_detection(self):
        """Content pattern matching should be case-insensitive."""
        result = self.manager.is_session_expired_response(
            url="https://example.com/page",
            content="<html>SESSION EXPIRED</html>",
        )
        assert result is True


class TestExpiryPatterns:
    """Tests for expiry pattern constants."""

    def test_expiry_url_patterns_exist(self):
        """EXPIRY_URL_PATTERNS should be defined."""
        assert EXPIRY_URL_PATTERNS is not None
        assert len(EXPIRY_URL_PATTERNS) >= 3

    def test_expiry_content_patterns_exist(self):
        """EXPIRY_CONTENT_PATTERNS should be defined."""
        assert EXPIRY_CONTENT_PATTERNS is not None
        assert len(EXPIRY_CONTENT_PATTERNS) >= 6


class TestStateTransitions:
    """Tests for session state transitions."""

    def setup_method(self):
        reset_config()
        reset_logging()
        self.manager = SessionManager(cookie="test_cookie")

    def teardown_method(self):
        reset_config()
        reset_logging()

    def test_mark_expired_changes_state(self):
        """mark_expired should change state to EXPIRED."""
        self.manager.mark_expired()
        assert self.manager.state == SessionState.EXPIRED

    def test_mark_expired_twice_no_error(self):
        """Calling mark_expired twice should not raise error."""
        self.manager.mark_expired()
        self.manager.mark_expired()
        assert self.manager.state == SessionState.EXPIRED

    def test_mark_refreshing_changes_state(self):
        """mark_refreshing should change state to REFRESHING when expired."""
        self.manager.mark_expired()
        self.manager.mark_refreshing()
        assert self.manager.state == SessionState.REFRESHING

    def test_mark_refreshing_only_from_expired(self):
        """mark_refreshing should only work from EXPIRED state."""
        self.manager.mark_refreshing()
        # Should still be ACTIVE since we didn't expire first
        assert self.manager.state == SessionState.ACTIVE

    def test_update_cookie_restores_active(self):
        """update_cookie should restore state to ACTIVE."""
        self.manager.mark_expired()
        self.manager.update_cookie("new_cookie")
        assert self.manager.state == SessionState.ACTIVE

    def test_update_cookie_changes_cookie_value(self):
        """update_cookie should update the cookie value."""
        self.manager.update_cookie("new_cookie_value")
        assert self.manager.cookie == "new_cookie_value"

    def test_update_cookie_from_refreshing(self):
        """update_cookie should work from REFRESHING state."""
        self.manager.mark_expired()
        self.manager.mark_refreshing()
        self.manager.update_cookie("refreshed_cookie")
        assert self.manager.state == SessionState.ACTIVE
        assert self.manager.cookie == "refreshed_cookie"


class TestCallbacks:
    """Tests for session callbacks."""

    def setup_method(self):
        reset_config()
        reset_logging()
        self.manager = SessionManager(cookie="test_cookie")

    def teardown_method(self):
        reset_config()
        reset_logging()

    def test_expired_callback_called(self):
        """on_session_expired callback should be called when session expires."""
        callback_called = []

        def on_expired():
            callback_called.append(True)

        self.manager.on_session_expired = on_expired
        self.manager.mark_expired()

        assert len(callback_called) == 1

    def test_expired_callback_only_called_once(self):
        """on_session_expired callback should only be called once per expiry."""
        callback_count = []

        def on_expired():
            callback_count.append(1)

        self.manager.on_session_expired = on_expired
        self.manager.mark_expired()
        self.manager.mark_expired()

        assert len(callback_count) == 1

    def test_refreshed_callback_called_with_cookie(self):
        """on_session_refreshed callback should be called with new cookie."""
        received_cookies = []

        def on_refreshed(cookie):
            received_cookies.append(cookie)

        self.manager.on_session_refreshed = on_refreshed
        self.manager.update_cookie("new_cookie")

        assert len(received_cookies) == 1
        assert received_cookies[0] == "new_cookie"

    def test_callbacks_can_be_none(self):
        """Callbacks should be None by default and not cause errors."""
        assert self.manager.on_session_expired is None
        assert self.manager.on_session_refreshed is None

        # These should not raise
        self.manager.mark_expired()
        self.manager.update_cookie("new_cookie")


class TestWaiting:
    """Tests for wait_for_valid_session functionality."""

    def setup_method(self):
        reset_config()
        reset_logging()
        self.manager = SessionManager(cookie="test_cookie")

    def teardown_method(self):
        reset_config()
        reset_logging()

    def test_returns_immediately_when_active(self):
        """wait_for_valid_session should return immediately when active."""
        start = time.time()
        self.manager.wait_for_valid_session(timeout=5.0)
        elapsed = time.time() - start
        assert elapsed < 0.1

    def test_blocks_when_expired(self):
        """wait_for_valid_session should block when session is expired."""
        self.manager.mark_expired()

        # Start a thread that will update cookie after a short delay
        def update_after_delay():
            time.sleep(0.1)
            self.manager.update_cookie("refreshed_cookie")

        thread = threading.Thread(target=update_after_delay)
        thread.start()

        start = time.time()
        self.manager.wait_for_valid_session(timeout=5.0)
        elapsed = time.time() - start

        thread.join()

        assert elapsed >= 0.1
        assert elapsed < 1.0  # Should not wait too long

    def test_raises_on_timeout(self):
        """wait_for_valid_session should raise SessionExpiredError on timeout."""
        self.manager.mark_expired()

        with pytest.raises(SessionExpiredError) as exc_info:
            self.manager.wait_for_valid_session(timeout=0.1)

        assert "0.1 seconds" in str(exc_info.value)


class TestCheckAndHandleResponse:
    """Tests for check_and_handle_response."""

    def setup_method(self):
        reset_config()
        reset_logging()
        self.manager = SessionManager(cookie="test_cookie")

    def teardown_method(self):
        reset_config()
        reset_logging()

    def test_returns_true_and_marks_expired(self):
        """check_and_handle_response should return True and mark expired for expired response."""
        result = self.manager.check_and_handle_response(
            url="https://example.com/login.aspx",
            content="<html>Login</html>",
        )

        assert result is True
        assert self.manager.state == SessionState.EXPIRED

    def test_returns_false_for_valid_response(self):
        """check_and_handle_response should return False for valid response."""
        result = self.manager.check_and_handle_response(
            url="https://example.com/data",
            content="<html>Your data</html>",
        )

        assert result is False
        assert self.manager.state == SessionState.ACTIVE


class TestThreadSafety:
    """Tests for thread safety of SessionManager."""

    def setup_method(self):
        reset_config()
        reset_logging()
        self.manager = SessionManager(cookie="test_cookie")

    def teardown_method(self):
        reset_config()
        reset_logging()

    def test_concurrent_state_changes(self):
        """Multiple threads changing state should not cause errors."""
        errors = []

        def expire_and_refresh():
            try:
                for _ in range(10):
                    self.manager.mark_expired()
                    time.sleep(0.001)
                    self.manager.update_cookie("new_cookie")
            except Exception as e:
                errors.append(e)

        def read_state():
            try:
                for _ in range(50):
                    _ = self.manager.state
                    _ = self.manager.cookie
                    time.sleep(0.001)
            except Exception as e:
                errors.append(e)

        threads = []
        for _ in range(3):
            threads.append(threading.Thread(target=expire_and_refresh))
            threads.append(threading.Thread(target=read_state))

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0

    def test_concurrent_cookie_reads(self):
        """Multiple threads reading cookie should not cause errors."""
        cookies_read = []
        errors = []

        def read_cookie():
            try:
                for _ in range(100):
                    cookies_read.append(self.manager.cookie)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=read_cookie) for _ in range(5)]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        assert len(cookies_read) == 500

    def test_callback_called_outside_lock(self):
        """Callbacks should be called outside the lock to prevent deadlocks."""
        # This test verifies that we can access the manager from within a callback
        accessed_from_callback = []

        def on_expired():
            # Try to access the manager from within the callback
            # If the lock is held, this would deadlock
            state = self.manager.state
            accessed_from_callback.append(state)

        self.manager.on_session_expired = on_expired
        self.manager.mark_expired()

        assert len(accessed_from_callback) == 1
        assert accessed_from_callback[0] == SessionState.EXPIRED
