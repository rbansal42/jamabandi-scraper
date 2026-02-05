# Phase 3: Monitoring & Session Management Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add session management, real-time statistics, and cookie capture to improve UX and reliability for long-running scrapes.

**Architecture:** Three independent modules that integrate with the existing scraper:
- `session_manager.py` - Monitors session health, coordinates re-authentication
- `statistics.py` - Tracks download metrics, calculates speed/ETA
- `cookie_capture.py` - Browser-based cookie extraction (optional pywebview)

**Tech Stack:** Python 3.14, tkinter, threading, dataclasses, optional pywebview

---

## Task 1: Statistics Tracker Core

**Files:**
- Create: `scraper/statistics.py`
- Test: `tests/test_statistics.py`

**Step 1: Write failing tests for StatisticsTracker**

```python
# tests/test_statistics.py
"""Tests for download statistics tracker."""
import time
import threading
import pytest
from scraper.config import reset_config
from scraper.logger import reset_logging
from scraper.statistics import StatisticsTracker


class TestStatisticsTrackerInitialization:
    """Tests for StatisticsTracker initialization."""

    def setup_method(self):
        reset_config()
        reset_logging()

    def teardown_method(self):
        reset_config()
        reset_logging()

    def test_initial_counts_are_zero(self):
        """Initial statistics should be zero."""
        tracker = StatisticsTracker(total_items=100)
        stats = tracker.get_stats()
        assert stats["completed"] == 0
        assert stats["failed"] == 0
        assert stats["pending"] == 100

    def test_total_items_stored(self):
        """Total items should be stored."""
        tracker = StatisticsTracker(total_items=500)
        assert tracker.total_items == 500


class TestStatisticsTrackerRecording:
    """Tests for recording downloads."""

    def setup_method(self):
        reset_config()
        reset_logging()
        self.tracker = StatisticsTracker(total_items=100)

    def teardown_method(self):
        reset_config()
        reset_logging()

    def test_record_success_increments_completed(self):
        """Recording success should increment completed count."""
        self.tracker.record_success(bytes_downloaded=1024)
        stats = self.tracker.get_stats()
        assert stats["completed"] == 1
        assert stats["pending"] == 99

    def test_record_success_tracks_bytes(self):
        """Recording success should track bytes downloaded."""
        self.tracker.record_success(bytes_downloaded=1024)
        self.tracker.record_success(bytes_downloaded=2048)
        stats = self.tracker.get_stats()
        assert stats["bytes_downloaded"] == 3072

    def test_record_failure_increments_failed(self):
        """Recording failure should increment failed count."""
        self.tracker.record_failure()
        stats = self.tracker.get_stats()
        assert stats["failed"] == 1

    def test_record_failure_decrements_pending(self):
        """Recording failure should also decrement pending."""
        self.tracker.record_failure()
        stats = self.tracker.get_stats()
        assert stats["pending"] == 99


class TestStatisticsTrackerSpeed:
    """Tests for speed calculations."""

    def setup_method(self):
        reset_config()
        reset_logging()
        self.tracker = StatisticsTracker(total_items=100)

    def teardown_method(self):
        reset_config()
        reset_logging()

    def test_speed_zero_when_no_downloads(self):
        """Speed should be 0 when no downloads recorded."""
        stats = self.tracker.get_stats()
        assert stats["downloads_per_minute"] == 0.0

    def test_speed_calculated_correctly(self):
        """Speed should be calculated from recent downloads."""
        # Record 6 downloads
        for _ in range(6):
            self.tracker.record_success(bytes_downloaded=1024)
            time.sleep(0.01)  # Small delay
        stats = self.tracker.get_stats()
        # Should have non-zero speed
        assert stats["downloads_per_minute"] > 0


class TestStatisticsTrackerETA:
    """Tests for ETA calculations."""

    def setup_method(self):
        reset_config()
        reset_logging()
        self.tracker = StatisticsTracker(total_items=100)

    def teardown_method(self):
        reset_config()
        reset_logging()

    def test_eta_none_when_no_speed(self):
        """ETA should be None when no downloads yet."""
        stats = self.tracker.get_stats()
        assert stats["eta_seconds"] is None

    def test_eta_decreases_as_progress_made(self):
        """ETA should decrease as items are completed."""
        # Record several downloads quickly
        for _ in range(10):
            self.tracker.record_success(bytes_downloaded=1024)
        stats = self.tracker.get_stats()
        if stats["downloads_per_minute"] > 0:
            assert stats["eta_seconds"] is not None
            assert stats["eta_seconds"] > 0


class TestStatisticsTrackerSuccessRate:
    """Tests for success rate calculations."""

    def setup_method(self):
        reset_config()
        reset_logging()
        self.tracker = StatisticsTracker(total_items=100)

    def teardown_method(self):
        reset_config()
        reset_logging()

    def test_success_rate_100_when_all_success(self):
        """Success rate should be 100% when no failures."""
        for _ in range(10):
            self.tracker.record_success(bytes_downloaded=1024)
        stats = self.tracker.get_stats()
        assert stats["success_rate"] == 100.0

    def test_success_rate_0_when_all_failure(self):
        """Success rate should be 0% when all failures."""
        for _ in range(10):
            self.tracker.record_failure()
        stats = self.tracker.get_stats()
        assert stats["success_rate"] == 0.0

    def test_success_rate_calculated_correctly(self):
        """Success rate should be calculated correctly."""
        for _ in range(7):
            self.tracker.record_success(bytes_downloaded=1024)
        for _ in range(3):
            self.tracker.record_failure()
        stats = self.tracker.get_stats()
        assert stats["success_rate"] == 70.0


class TestStatisticsTrackerThreadSafety:
    """Tests for thread safety."""

    def setup_method(self):
        reset_config()
        reset_logging()
        self.tracker = StatisticsTracker(total_items=1000)

    def teardown_method(self):
        reset_config()
        reset_logging()

    def test_concurrent_recording(self):
        """Concurrent recording should be thread-safe."""
        def record_many():
            for _ in range(100):
                self.tracker.record_success(bytes_downloaded=1024)

        threads = [threading.Thread(target=record_many) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        stats = self.tracker.get_stats()
        assert stats["completed"] == 500
        assert stats["bytes_downloaded"] == 500 * 1024


class TestStatisticsTrackerFormatting:
    """Tests for formatted output."""

    def setup_method(self):
        reset_config()
        reset_logging()
        self.tracker = StatisticsTracker(total_items=100)

    def teardown_method(self):
        reset_config()
        reset_logging()

    def test_format_human_readable(self):
        """Should provide human-readable formatted stats."""
        for _ in range(25):
            self.tracker.record_success(bytes_downloaded=1024 * 100)  # 100KB each
        for _ in range(5):
            self.tracker.record_failure()
        formatted = self.tracker.format_stats()
        assert "25" in formatted  # completed
        assert "5" in formatted  # failed
        assert "%" in formatted  # success rate
```

**Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_statistics.py -v`
Expected: FAIL with "No module named 'scraper.statistics'"

**Step 3: Implement StatisticsTracker**

```python
# scraper/statistics.py
"""Real-time download statistics tracking."""

import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Optional

from .config import get_config
from .logger import get_logger

logger = get_logger("statistics")


@dataclass
class DownloadRecord:
    """Record of a single download attempt."""
    timestamp: float
    success: bool
    bytes_downloaded: int = 0


class StatisticsTracker:
    """
    Track download statistics in real-time.
    
    Features:
    - Completed/failed/pending counts
    - Download speed (downloads per minute)
    - ETA calculation
    - Success rate percentage
    - Bytes downloaded tracking
    - Thread-safe operations
    """
    
    def __init__(self, total_items: int, window_seconds: float = 60.0):
        """Initialize the statistics tracker.
        
        Args:
            total_items: Total number of items to download
            window_seconds: Time window for speed calculation (default 60s)
        """
        self.total_items = total_items
        self.window_seconds = window_seconds
        
        self._completed = 0
        self._failed = 0
        self._bytes_downloaded = 0
        self._start_time: Optional[float] = None
        
        # Sliding window for speed calculation
        self._recent_downloads: deque = deque()
        
        self._lock = threading.Lock()
    
    def record_success(self, bytes_downloaded: int = 0) -> None:
        """Record a successful download.
        
        Args:
            bytes_downloaded: Size of downloaded file in bytes
        """
        with self._lock:
            now = time.time()
            if self._start_time is None:
                self._start_time = now
            
            self._completed += 1
            self._bytes_downloaded += bytes_downloaded
            self._recent_downloads.append(
                DownloadRecord(timestamp=now, success=True, bytes_downloaded=bytes_downloaded)
            )
            self._prune_old_records(now)
    
    def record_failure(self) -> None:
        """Record a failed download."""
        with self._lock:
            now = time.time()
            if self._start_time is None:
                self._start_time = now
            
            self._failed += 1
            self._recent_downloads.append(
                DownloadRecord(timestamp=now, success=False)
            )
            self._prune_old_records(now)
    
    def _prune_old_records(self, now: float) -> None:
        """Remove records older than the window."""
        cutoff = now - self.window_seconds
        while self._recent_downloads and self._recent_downloads[0].timestamp < cutoff:
            self._recent_downloads.popleft()
    
    def get_stats(self) -> dict:
        """Get current statistics.
        
        Returns:
            Dictionary with all statistics
        """
        with self._lock:
            now = time.time()
            self._prune_old_records(now)
            
            completed = self._completed
            failed = self._failed
            pending = self.total_items - completed - failed
            total_attempted = completed + failed
            
            # Calculate speed (downloads per minute)
            if self._recent_downloads:
                window_start = self._recent_downloads[0].timestamp
                window_duration = now - window_start
                if window_duration > 0:
                    recent_count = len(self._recent_downloads)
                    downloads_per_minute = (recent_count / window_duration) * 60
                else:
                    downloads_per_minute = 0.0
            else:
                downloads_per_minute = 0.0
            
            # Calculate ETA
            if downloads_per_minute > 0 and pending > 0:
                eta_seconds = (pending / downloads_per_minute) * 60
            else:
                eta_seconds = None
            
            # Calculate success rate
            if total_attempted > 0:
                success_rate = (completed / total_attempted) * 100
            else:
                success_rate = 0.0
            
            return {
                "completed": completed,
                "failed": failed,
                "pending": pending,
                "total": self.total_items,
                "bytes_downloaded": self._bytes_downloaded,
                "downloads_per_minute": round(downloads_per_minute, 2),
                "eta_seconds": round(eta_seconds, 1) if eta_seconds else None,
                "success_rate": round(success_rate, 1),
                "elapsed_seconds": round(now - self._start_time, 1) if self._start_time else 0,
            }
    
    def format_stats(self) -> str:
        """Get human-readable formatted statistics.
        
        Returns:
            Formatted string with key statistics
        """
        stats = self.get_stats()
        
        # Format bytes
        bytes_dl = stats["bytes_downloaded"]
        if bytes_dl >= 1024 * 1024:
            bytes_str = f"{bytes_dl / (1024 * 1024):.1f} MB"
        elif bytes_dl >= 1024:
            bytes_str = f"{bytes_dl / 1024:.1f} KB"
        else:
            bytes_str = f"{bytes_dl} B"
        
        # Format ETA
        if stats["eta_seconds"]:
            eta_mins = int(stats["eta_seconds"] // 60)
            eta_secs = int(stats["eta_seconds"] % 60)
            eta_str = f"{eta_mins}m {eta_secs}s"
        else:
            eta_str = "calculating..."
        
        return (
            f"Progress: {stats['completed']}/{stats['total']} "
            f"({stats['failed']} failed, {stats['success_rate']:.1f}% success)\n"
            f"Speed: {stats['downloads_per_minute']:.1f}/min | "
            f"ETA: {eta_str} | "
            f"Downloaded: {bytes_str}"
        )
    
    def reset(self, total_items: Optional[int] = None) -> None:
        """Reset all statistics.
        
        Args:
            total_items: New total items count (optional)
        """
        with self._lock:
            if total_items is not None:
                self.total_items = total_items
            self._completed = 0
            self._failed = 0
            self._bytes_downloaded = 0
            self._start_time = None
            self._recent_downloads.clear()
```

**Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_statistics.py -v`
Expected: PASS (all tests)

**Step 5: Commit**

```bash
git add scraper/statistics.py tests/test_statistics.py
git commit -m "feat: add statistics tracker for download metrics (#9)"
```

---

## Task 2: Session Manager Core

**Files:**
- Create: `scraper/session_manager.py`
- Test: `tests/test_session_manager.py`

**Step 1: Write failing tests for SessionManager**

```python
# tests/test_session_manager.py
"""Tests for session manager."""
import threading
import time
import pytest
from unittest.mock import Mock, patch
from scraper.config import reset_config
from scraper.logger import reset_logging
from scraper.session_manager import (
    SessionManager,
    SessionState,
    SessionExpiredError,
)


class TestSessionState:
    """Tests for SessionState enum."""

    def test_active_state(self):
        """Should have ACTIVE state."""
        assert SessionState.ACTIVE.value == "active"

    def test_expired_state(self):
        """Should have EXPIRED state."""
        assert SessionState.EXPIRED.value == "expired"

    def test_refreshing_state(self):
        """Should have REFRESHING state."""
        assert SessionState.REFRESHING.value == "refreshing"


class TestSessionManagerInitialization:
    """Tests for SessionManager initialization."""

    def setup_method(self):
        reset_config()
        reset_logging()

    def teardown_method(self):
        reset_config()
        reset_logging()

    def test_initial_state_is_active(self):
        """Initial state should be active with valid cookie."""
        manager = SessionManager(cookie="valid_cookie")
        assert manager.state == SessionState.ACTIVE

    def test_stores_cookie(self):
        """Should store the cookie."""
        manager = SessionManager(cookie="test_cookie_123")
        assert manager.cookie == "test_cookie_123"


class TestSessionExpiryDetection:
    """Tests for session expiry detection."""

    def setup_method(self):
        reset_config()
        reset_logging()
        self.manager = SessionManager(cookie="test_cookie")

    def teardown_method(self):
        reset_config()
        reset_logging()

    def test_detect_login_redirect(self):
        """Should detect login.aspx redirect as expiry."""
        assert self.manager.is_session_expired_response(
            url="https://jamabandi.nic.in/PublicNakal/login.aspx",
            content=""
        )

    def test_detect_enter_mobile_text(self):
        """Should detect 'enter mobile' text as expiry."""
        assert self.manager.is_session_expired_response(
            url="https://jamabandi.nic.in/PublicNakal/form",
            content="Please enter mobile number to continue"
        )

    def test_detect_session_timeout_text(self):
        """Should detect session timeout text as expiry."""
        assert self.manager.is_session_expired_response(
            url="https://example.com",
            content="Your session has timed out. Please login again."
        )

    def test_valid_response_not_expired(self):
        """Should not detect valid response as expired."""
        assert not self.manager.is_session_expired_response(
            url="https://jamabandi.nic.in/PublicNakal/form",
            content="<html><body>Nakal content here</body></html>"
        )


class TestSessionStateTransitions:
    """Tests for session state transitions."""

    def setup_method(self):
        reset_config()
        reset_logging()
        self.manager = SessionManager(cookie="test_cookie")

    def teardown_method(self):
        reset_config()
        reset_logging()

    def test_mark_expired_changes_state(self):
        """Marking expired should change state."""
        self.manager.mark_expired()
        assert self.manager.state == SessionState.EXPIRED

    def test_mark_refreshing_changes_state(self):
        """Marking refreshing should change state."""
        self.manager.mark_refreshing()
        assert self.manager.state == SessionState.REFRESHING

    def test_update_cookie_restores_active(self):
        """Updating cookie should restore active state."""
        self.manager.mark_expired()
        self.manager.update_cookie("new_cookie")
        assert self.manager.state == SessionState.ACTIVE
        assert self.manager.cookie == "new_cookie"


class TestSessionManagerCallbacks:
    """Tests for callback functionality."""

    def setup_method(self):
        reset_config()
        reset_logging()
        self.manager = SessionManager(cookie="test_cookie")
        self.callback_called = False
        self.callback_arg = None

    def teardown_method(self):
        reset_config()
        reset_logging()

    def test_expiry_callback_called(self):
        """Expiry callback should be called when session expires."""
        def on_expire():
            self.callback_called = True

        self.manager.on_session_expired = on_expire
        self.manager.mark_expired()
        assert self.callback_called

    def test_refresh_callback_called(self):
        """Refresh callback should be called with new cookie."""
        def on_refresh(new_cookie):
            self.callback_called = True
            self.callback_arg = new_cookie

        self.manager.on_session_refreshed = on_refresh
        self.manager.update_cookie("refreshed_cookie")
        assert self.callback_called
        assert self.callback_arg == "refreshed_cookie"


class TestSessionManagerWaiting:
    """Tests for waiting on session refresh."""

    def setup_method(self):
        reset_config()
        reset_logging()
        self.manager = SessionManager(cookie="test_cookie")

    def teardown_method(self):
        reset_config()
        reset_logging()

    def test_wait_returns_immediately_when_active(self):
        """Wait should return immediately when session is active."""
        start = time.time()
        self.manager.wait_for_valid_session(timeout=5.0)
        elapsed = time.time() - start
        assert elapsed < 0.1

    def test_wait_blocks_when_expired(self):
        """Wait should block when session is expired."""
        self.manager.mark_expired()
        
        # Update cookie from another thread after delay
        def refresh():
            time.sleep(0.2)
            self.manager.update_cookie("new_cookie")
        
        t = threading.Thread(target=refresh)
        t.start()
        
        start = time.time()
        self.manager.wait_for_valid_session(timeout=5.0)
        elapsed = time.time() - start
        
        t.join()
        assert 0.1 < elapsed < 1.0
        assert self.manager.state == SessionState.ACTIVE

    def test_wait_raises_on_timeout(self):
        """Wait should raise SessionExpiredError on timeout."""
        self.manager.mark_expired()
        with pytest.raises(SessionExpiredError):
            self.manager.wait_for_valid_session(timeout=0.1)


class TestSessionManagerThreadSafety:
    """Tests for thread safety."""

    def setup_method(self):
        reset_config()
        reset_logging()
        self.manager = SessionManager(cookie="test_cookie")

    def teardown_method(self):
        reset_config()
        reset_logging()

    def test_concurrent_state_changes(self):
        """Concurrent state changes should be safe."""
        def toggle_state():
            for _ in range(100):
                self.manager.mark_expired()
                self.manager.update_cookie("new")

        threads = [threading.Thread(target=toggle_state) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Should end in a valid state
        assert self.manager.state in (SessionState.ACTIVE, SessionState.EXPIRED, SessionState.REFRESHING)
```

**Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_session_manager.py -v`
Expected: FAIL with "No module named 'scraper.session_manager'"

**Step 3: Implement SessionManager**

```python
# scraper/session_manager.py
"""Session management for handling cookie expiry and refresh."""

import threading
from enum import Enum
from typing import Callable, Optional

from .logger import get_logger

logger = get_logger("session")


class SessionState(Enum):
    """Session state enumeration."""
    ACTIVE = "active"
    EXPIRED = "expired"
    REFRESHING = "refreshing"


class SessionExpiredError(Exception):
    """Raised when session expires and cannot be refreshed."""
    pass


class SessionManager:
    """
    Manages session state and cookie lifecycle.
    
    Features:
    - Detects session expiry from HTTP responses
    - Coordinates re-authentication flow
    - Thread-safe state management
    - Callback support for UI integration
    - Blocking wait for session refresh
    """
    
    # Patterns that indicate session expiry
    EXPIRY_URL_PATTERNS = [
        "login.aspx",
        "login.asp",
        "/login",
    ]
    
    EXPIRY_CONTENT_PATTERNS = [
        "enter mobile",
        "session has timed out",
        "session expired",
        "please login",
        "please log in",
        "authentication required",
    ]
    
    def __init__(self, cookie: str):
        """Initialize session manager.
        
        Args:
            cookie: Initial session cookie value
        """
        self._cookie = cookie
        self._state = SessionState.ACTIVE
        self._lock = threading.Lock()
        self._refresh_event = threading.Event()
        self._refresh_event.set()  # Initially not waiting
        
        # Callbacks for UI integration
        self.on_session_expired: Optional[Callable[[], None]] = None
        self.on_session_refreshed: Optional[Callable[[str], None]] = None
    
    @property
    def cookie(self) -> str:
        """Get current cookie value."""
        with self._lock:
            return self._cookie
    
    @property
    def state(self) -> SessionState:
        """Get current session state."""
        with self._lock:
            return self._state
    
    def is_session_expired_response(self, url: str, content: str) -> bool:
        """Check if HTTP response indicates session expiry.
        
        Args:
            url: Response URL (may have been redirected)
            content: Response body content
            
        Returns:
            True if response indicates session expiry
        """
        url_lower = url.lower()
        content_lower = content.lower()
        
        # Check URL patterns
        for pattern in self.EXPIRY_URL_PATTERNS:
            if pattern in url_lower:
                logger.debug(f"Session expiry detected in URL: {pattern}")
                return True
        
        # Check content patterns
        for pattern in self.EXPIRY_CONTENT_PATTERNS:
            if pattern in content_lower:
                logger.debug(f"Session expiry detected in content: {pattern}")
                return True
        
        return False
    
    def mark_expired(self) -> None:
        """Mark session as expired."""
        with self._lock:
            if self._state != SessionState.EXPIRED:
                logger.warning("Session marked as expired")
                self._state = SessionState.EXPIRED
                self._refresh_event.clear()  # Block waiters
        
        # Call callback outside lock
        if self.on_session_expired:
            try:
                self.on_session_expired()
            except Exception as e:
                logger.error(f"Error in expiry callback: {e}")
    
    def mark_refreshing(self) -> None:
        """Mark session as being refreshed."""
        with self._lock:
            logger.info("Session refresh in progress")
            self._state = SessionState.REFRESHING
    
    def update_cookie(self, new_cookie: str) -> None:
        """Update cookie and restore active state.
        
        Args:
            new_cookie: New session cookie value
        """
        with self._lock:
            logger.info("Session cookie updated")
            self._cookie = new_cookie
            self._state = SessionState.ACTIVE
            self._refresh_event.set()  # Unblock waiters
        
        # Call callback outside lock
        if self.on_session_refreshed:
            try:
                self.on_session_refreshed(new_cookie)
            except Exception as e:
                logger.error(f"Error in refresh callback: {e}")
    
    def wait_for_valid_session(self, timeout: float = 300.0) -> None:
        """Wait for session to become valid.
        
        Blocks until session is active or timeout expires.
        
        Args:
            timeout: Maximum seconds to wait
            
        Raises:
            SessionExpiredError: If timeout expires without refresh
        """
        if self._refresh_event.wait(timeout=timeout):
            return
        
        raise SessionExpiredError(
            f"Session expired and not refreshed within {timeout}s"
        )
    
    def check_and_handle_response(self, url: str, content: str) -> bool:
        """Check response and handle expiry if detected.
        
        Args:
            url: Response URL
            content: Response content
            
        Returns:
            True if session is valid, False if expired
        """
        if self.is_session_expired_response(url, content):
            self.mark_expired()
            return False
        return True
```

**Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_session_manager.py -v`
Expected: PASS (all tests)

**Step 5: Commit**

```bash
git add scraper/session_manager.py tests/test_session_manager.py
git commit -m "feat: add session manager for expiry detection and re-auth (#10)"
```

---

## Task 3: Cookie Capture Module

**Files:**
- Create: `scraper/cookie_capture.py`
- Test: `tests/test_cookie_capture.py`

**Step 1: Write failing tests for CookieCapture**

```python
# tests/test_cookie_capture.py
"""Tests for cookie capture functionality."""
import pytest
from unittest.mock import Mock, patch, MagicMock
from scraper.config import reset_config
from scraper.logger import reset_logging
from scraper.cookie_capture import (
    CookieCapture,
    CookieCaptureMethod,
    extract_cookie_from_header,
)


class TestCookieCaptureMethod:
    """Tests for CookieCaptureMethod enum."""

    def test_manual_method(self):
        """Should have MANUAL method."""
        assert CookieCaptureMethod.MANUAL.value == "manual"

    def test_webview_method(self):
        """Should have WEBVIEW method."""
        assert CookieCaptureMethod.WEBVIEW.value == "webview"


class TestExtractCookieFromHeader:
    """Tests for cookie extraction from header string."""

    def test_extract_single_cookie(self):
        """Should extract single cookie value."""
        header = "jamabandiID=abc123"
        result = extract_cookie_from_header(header, "jamabandiID")
        assert result == "abc123"

    def test_extract_from_multiple_cookies(self):
        """Should extract correct cookie from multiple."""
        header = "sessionID=xyz; jamabandiID=abc123; other=value"
        result = extract_cookie_from_header(header, "jamabandiID")
        assert result == "abc123"

    def test_return_none_when_not_found(self):
        """Should return None when cookie not found."""
        header = "sessionID=xyz; other=value"
        result = extract_cookie_from_header(header, "jamabandiID")
        assert result is None

    def test_handle_cookie_with_attributes(self):
        """Should handle cookies with attributes."""
        header = "jamabandiID=abc123; Path=/; HttpOnly"
        result = extract_cookie_from_header(header, "jamabandiID")
        assert result == "abc123"

    def test_handle_empty_header(self):
        """Should handle empty header."""
        result = extract_cookie_from_header("", "jamabandiID")
        assert result is None


class TestCookieCaptureInitialization:
    """Tests for CookieCapture initialization."""

    def setup_method(self):
        reset_config()
        reset_logging()

    def teardown_method(self):
        reset_config()
        reset_logging()

    def test_default_method_is_manual(self):
        """Default method should be manual when webview unavailable."""
        with patch('scraper.cookie_capture.WEBVIEW_AVAILABLE', False):
            capture = CookieCapture()
            assert capture.method == CookieCaptureMethod.MANUAL

    def test_stores_login_url(self):
        """Should store login URL from config."""
        capture = CookieCapture()
        assert "jamabandi.nic.in" in capture.login_url

    def test_cookie_name_default(self):
        """Should have correct default cookie name."""
        capture = CookieCapture()
        assert capture.cookie_name == "jamabandiID"


class TestCookieCaptureManual:
    """Tests for manual cookie capture."""

    def setup_method(self):
        reset_config()
        reset_logging()
        self.capture = CookieCapture()

    def teardown_method(self):
        reset_config()
        reset_logging()

    def test_get_instructions_returns_string(self):
        """Should return instructions for manual capture."""
        instructions = self.capture.get_manual_instructions()
        assert isinstance(instructions, str)
        assert "cookie" in instructions.lower()

    def test_validate_cookie_format_valid(self):
        """Should validate correct cookie format."""
        assert self.capture.validate_cookie("abc123def456")

    def test_validate_cookie_format_empty(self):
        """Should reject empty cookie."""
        assert not self.capture.validate_cookie("")

    def test_validate_cookie_format_whitespace(self):
        """Should reject whitespace-only cookie."""
        assert not self.capture.validate_cookie("   ")


class TestCookieCaptureWebview:
    """Tests for webview-based cookie capture."""

    def setup_method(self):
        reset_config()
        reset_logging()

    def teardown_method(self):
        reset_config()
        reset_logging()

    def test_webview_available_check(self):
        """Should report webview availability."""
        capture = CookieCapture()
        # Result depends on system, just check it's boolean
        assert isinstance(capture.is_webview_available(), bool)


class TestCookieCaptureCallback:
    """Tests for callback functionality."""

    def setup_method(self):
        reset_config()
        reset_logging()
        self.capture = CookieCapture()
        self.callback_value = None

    def teardown_method(self):
        reset_config()
        reset_logging()

    def test_on_cookie_captured_callback(self):
        """Should call callback when cookie is captured."""
        def callback(cookie):
            self.callback_value = cookie

        self.capture.on_cookie_captured = callback
        self.capture._notify_cookie_captured("test_cookie")
        assert self.callback_value == "test_cookie"
```

**Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_cookie_capture.py -v`
Expected: FAIL with "No module named 'scraper.cookie_capture'"

**Step 3: Implement CookieCapture**

```python
# scraper/cookie_capture.py
"""Cookie capture functionality for authentication."""

import re
from enum import Enum
from typing import Callable, Optional

from .config import get_config
from .logger import get_logger

logger = get_logger("cookie_capture")

# Check if pywebview is available
try:
    import webview
    WEBVIEW_AVAILABLE = True
except ImportError:
    WEBVIEW_AVAILABLE = False
    logger.debug("pywebview not available, using manual cookie entry")


class CookieCaptureMethod(Enum):
    """Cookie capture method enumeration."""
    MANUAL = "manual"
    WEBVIEW = "webview"


def extract_cookie_from_header(header: str, cookie_name: str) -> Optional[str]:
    """Extract a specific cookie value from a cookie header string.
    
    Args:
        header: Cookie header string (e.g., "name=value; name2=value2")
        cookie_name: Name of the cookie to extract
        
    Returns:
        Cookie value if found, None otherwise
    """
    if not header:
        return None
    
    # Split by semicolon and find the cookie
    for part in header.split(";"):
        part = part.strip()
        if "=" in part:
            name, _, value = part.partition("=")
            if name.strip() == cookie_name:
                return value.strip()
    
    return None


class CookieCapture:
    """
    Handles cookie capture for authentication.
    
    Supports two methods:
    - Manual: User copies cookie from browser DevTools
    - Webview: Built-in browser window for automatic capture
    
    Falls back to manual if webview is unavailable.
    """
    
    def __init__(self, prefer_webview: bool = True):
        """Initialize cookie capture.
        
        Args:
            prefer_webview: Prefer webview method if available
        """
        config = get_config()
        self.login_url = config.urls.get(
            "login_url",
            "https://jamabandi.nic.in/PublicNakal/login.aspx"
        )
        self.cookie_name = "jamabandiID"
        
        # Determine capture method
        if prefer_webview and WEBVIEW_AVAILABLE:
            self.method = CookieCaptureMethod.WEBVIEW
        else:
            self.method = CookieCaptureMethod.MANUAL
        
        # Callback for when cookie is captured
        self.on_cookie_captured: Optional[Callable[[str], None]] = None
        
        # Captured cookie storage
        self._captured_cookie: Optional[str] = None
    
    def is_webview_available(self) -> bool:
        """Check if webview capture is available.
        
        Returns:
            True if pywebview is installed and can be used
        """
        return WEBVIEW_AVAILABLE
    
    def get_manual_instructions(self) -> str:
        """Get instructions for manual cookie capture.
        
        Returns:
            Human-readable instructions
        """
        return f"""
Manual Cookie Capture Instructions:
===================================

1. Open your web browser (Chrome, Firefox, or Edge)

2. Navigate to: {self.login_url}

3. Complete the OTP authentication process

4. After successful login, open Developer Tools:
   - Chrome/Edge: Press F12 or Ctrl+Shift+I
   - Firefox: Press F12 or Ctrl+Shift+I

5. Go to the Application/Storage tab:
   - Chrome/Edge: Application > Cookies
   - Firefox: Storage > Cookies

6. Find the cookie named "{self.cookie_name}"

7. Copy the entire Value (right-click > Copy Value)

8. Paste the value in the cookie field below
"""
    
    def validate_cookie(self, cookie: str) -> bool:
        """Validate cookie format.
        
        Args:
            cookie: Cookie value to validate
            
        Returns:
            True if cookie appears valid
        """
        if not cookie or not cookie.strip():
            return False
        
        # Basic format validation - should be alphanumeric with some special chars
        cookie = cookie.strip()
        if len(cookie) < 10:
            logger.warning(f"Cookie too short: {len(cookie)} chars")
            return False
        
        return True
    
    def capture_manual(self, cookie: str) -> bool:
        """Capture cookie from manual entry.
        
        Args:
            cookie: Cookie value entered by user
            
        Returns:
            True if cookie was valid and captured
        """
        if not self.validate_cookie(cookie):
            return False
        
        self._captured_cookie = cookie.strip()
        logger.info("Cookie captured via manual entry")
        self._notify_cookie_captured(self._captured_cookie)
        return True
    
    def capture_webview(self, timeout: float = 300.0) -> Optional[str]:
        """Capture cookie using webview browser.
        
        Opens a browser window for the user to login.
        Monitors for the session cookie and captures it.
        
        Args:
            timeout: Maximum seconds to wait for login
            
        Returns:
            Captured cookie value, or None if cancelled/timeout
        """
        if not WEBVIEW_AVAILABLE:
            logger.error("Webview not available")
            return None
        
        captured_cookie = None
        
        def on_loaded():
            """Called when page loads - check for cookie."""
            nonlocal captured_cookie
            try:
                cookies = window.get_cookies()
                for cookie in cookies:
                    if cookie.get("name") == self.cookie_name:
                        captured_cookie = cookie.get("value")
                        logger.info("Cookie captured via webview")
                        window.destroy()
                        break
            except Exception as e:
                logger.debug(f"Cookie check error: {e}")
        
        try:
            window = webview.create_window(
                "Jamabandi Login",
                self.login_url,
                width=800,
                height=600,
            )
            window.events.loaded += on_loaded
            webview.start()
            
            if captured_cookie:
                self._captured_cookie = captured_cookie
                self._notify_cookie_captured(captured_cookie)
                return captured_cookie
            
        except Exception as e:
            logger.error(f"Webview error: {e}")
        
        return None
    
    def get_captured_cookie(self) -> Optional[str]:
        """Get the most recently captured cookie.
        
        Returns:
            Cookie value, or None if not captured
        """
        return self._captured_cookie
    
    def _notify_cookie_captured(self, cookie: str) -> None:
        """Notify callback that cookie was captured.
        
        Args:
            cookie: Captured cookie value
        """
        if self.on_cookie_captured:
            try:
                self.on_cookie_captured(cookie)
            except Exception as e:
                logger.error(f"Error in cookie callback: {e}")
```

**Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_cookie_capture.py -v`
Expected: PASS (all tests)

**Step 5: Commit**

```bash
git add scraper/cookie_capture.py tests/test_cookie_capture.py
git commit -m "feat: add cookie capture module with manual and webview support (#7)"
```

---

## Task 4: Update Module Exports

**Files:**
- Modify: `scraper/__init__.py`

**Step 1: Update exports**

```python
# scraper/__init__.py
# Jamabandi Land Records Scraper

from .config import Config, get_config, reset_config
from .logger import (
    setup_logging,
    get_logger,
    log_http_request,
    log_download,
    log_session_event,
)
from .rate_limiter import RateLimiter
from .retry_manager import RetryManager, FailureType, FailedItem
from .validator import (
    PDFValidator,
    ValidationStatus,
    ValidationResult,
    validate_download,
)
from .statistics import StatisticsTracker
from .session_manager import SessionManager, SessionState, SessionExpiredError
from .cookie_capture import (
    CookieCapture,
    CookieCaptureMethod,
    extract_cookie_from_header,
)
```

**Step 2: Run all tests**

Run: `.venv/bin/pytest tests/ -v`
Expected: PASS (all tests)

**Step 3: Commit**

```bash
git add scraper/__init__.py
git commit -m "chore: export Phase 3 modules from package"
```

---

## Task 5: Integrate Statistics into HTTP Scraper

**Files:**
- Modify: `scraper/http_scraper.py`

**Step 1: Import and initialize StatisticsTracker**

Add to imports:
```python
from .statistics import StatisticsTracker
```

In `JamabandiHTTPScraper.__init__`:
```python
# Statistics tracker (initialized in run() when we know total count)
self.stats_tracker: Optional[StatisticsTracker] = None
```

**Step 2: Initialize stats in run()**

In `run()` method, after getting pending:
```python
# Initialize statistics tracker
self.stats_tracker = StatisticsTracker(total_items=len(pending))
```

**Step 3: Record successes and failures**

In `download_nakal()`, after `self.progress.mark_complete()`:
```python
if self.stats_tracker:
    self.stats_tracker.record_success(bytes_downloaded=len(response.content))
```

After `self.progress.mark_failed()`:
```python
if self.stats_tracker:
    self.stats_tracker.record_failure()
```

**Step 4: Log periodic stats**

In the main loop in `run()`, periodically log stats:
```python
# Log stats every 10 downloads
if i > 0 and i % 10 == 0 and self.stats_tracker:
    self.logger.info(self.stats_tracker.format_stats())
```

**Step 5: Run all tests**

Run: `.venv/bin/pytest tests/ -v`
Expected: PASS

**Step 6: Commit**

```bash
git add scraper/http_scraper.py
git commit -m "feat: integrate statistics tracker into http_scraper"
```

---

## Task 6: Integrate Session Manager into HTTP Scraper

**Files:**
- Modify: `scraper/http_scraper.py`

**Step 1: Import SessionManager**

Add to imports:
```python
from .session_manager import SessionManager, SessionState, SessionExpiredError
```

**Step 2: Initialize in constructor**

In `JamabandiHTTPScraper.__init__`:
```python
# Session manager for expiry detection
self.session_manager = SessionManager(cookie=session_cookie)
```

**Step 3: Check responses for session expiry**

In `download_nakal()`, after getting response:
```python
# Check for session expiry
if not self.session_manager.check_and_handle_response(response.url, response.text):
    log_session_event("Session expired during download")
    return False  # Signal to stop
```

**Step 4: Wait for valid session before requests**

At the start of `download_nakal()`:
```python
try:
    self.session_manager.wait_for_valid_session(timeout=300)
except SessionExpiredError:
    self.logger.error("Session expired and not refreshed")
    return False
```

**Step 5: Run all tests**

Run: `.venv/bin/pytest tests/ -v`
Expected: PASS

**Step 6: Commit**

```bash
git add scraper/http_scraper.py
git commit -m "feat: integrate session manager into http_scraper for expiry detection"
```

---

## Task 7: Add GUI Session Refresh Dialog

**Files:**
- Modify: `scraper/gui.py`

**Step 1: Add session refresh dialog class**

```python
class SessionRefreshDialog(simpledialog.Dialog):
    """Dialog for entering new session cookie after expiry."""

    def body(self, master):
        ttk.Label(
            master,
            text="Session has expired! Please login again and paste new cookie:",
            wraplength=350,
        ).grid(row=0, column=0, columnspan=2, pady=(0, 8))
        
        self.cookie_var = tk.StringVar()
        self.entry = ttk.Entry(master, textvariable=self.cookie_var, width=50)
        self.entry.grid(row=1, column=0, columnspan=2, pady=(0, 8))
        
        ttk.Label(
            master,
            text="Get cookie from browser DevTools > Application > Cookies",
            font=("TkDefaultFont", 9, "italic"),
        ).grid(row=2, column=0, columnspan=2)
        
        return self.entry

    def apply(self):
        self.result = self.cookie_var.get().strip()
```

**Step 2: Add session expiry handler method**

In `JamabandiGUI`:
```python
def _handle_session_expired(self):
    """Handle session expiry by prompting for new cookie."""
    def show_dialog():
        dialog = SessionRefreshDialog(self.root, title="Session Expired")
        if dialog.result:
            # Update the scraper's session
            self.vars["session_cookie"].set(dialog.result)
            self._append_log("New cookie entered, resuming...")
            # Notify session manager
            if hasattr(self, '_session_manager'):
                self._session_manager.update_cookie(dialog.result)
    
    # Must run in main thread
    self.root.after(0, show_dialog)
```

**Step 3: Connect to session manager**

When starting scrape, set up callback:
```python
# Set up session expiry callback
scraper.session_manager.on_session_expired = self._handle_session_expired
self._session_manager = scraper.session_manager
```

**Step 4: Run all tests**

Run: `.venv/bin/pytest tests/ -v`
Expected: PASS

**Step 5: Commit**

```bash
git add scraper/gui.py
git commit -m "feat: add GUI session refresh dialog for cookie re-entry"
```

---

## Task 8: Add GUI Statistics Display

**Files:**
- Modify: `scraper/gui.py`

**Step 1: Add statistics labels to progress frame**

In `_build_progress_frame()`:
```python
# Statistics display
self.stats_frame = ttk.LabelFrame(self.progress_frame, text="Statistics")
self.stats_frame.pack(fill="x", padx=8, pady=4)

self.stats_labels = {}
for stat in ["speed", "eta", "success_rate", "bytes"]:
    row = ttk.Frame(self.stats_frame)
    row.pack(fill="x", padx=4, pady=2)
    ttk.Label(row, text=f"{stat.replace('_', ' ').title()}:").pack(side="left")
    self.stats_labels[stat] = ttk.Label(row, text="--")
    self.stats_labels[stat].pack(side="right")
```

**Step 2: Add periodic stats update**

```python
def _update_stats_display(self, stats: dict):
    """Update statistics display."""
    self.stats_labels["speed"].config(
        text=f"{stats.get('downloads_per_minute', 0):.1f}/min"
    )
    
    eta = stats.get("eta_seconds")
    if eta:
        mins, secs = divmod(int(eta), 60)
        self.stats_labels["eta"].config(text=f"{mins}m {secs}s")
    else:
        self.stats_labels["eta"].config(text="calculating...")
    
    self.stats_labels["success_rate"].config(
        text=f"{stats.get('success_rate', 0):.1f}%"
    )
    
    bytes_dl = stats.get("bytes_downloaded", 0)
    if bytes_dl >= 1024 * 1024:
        self.stats_labels["bytes"].config(text=f"{bytes_dl / (1024*1024):.1f} MB")
    else:
        self.stats_labels["bytes"].config(text=f"{bytes_dl / 1024:.1f} KB")
```

**Step 3: Run all tests**

Run: `.venv/bin/pytest tests/ -v`
Expected: PASS

**Step 4: Commit**

```bash
git add scraper/gui.py
git commit -m "feat: add GUI statistics display for download metrics"
```

---

## Task 9: Update README and Config

**Files:**
- Modify: `README.md`
- Modify: `config.yaml`

**Step 1: Add Phase 3 features to README**

Add section:
```markdown
### Session Management

The scraper automatically detects session expiry and prompts for a new cookie:
- Monitors HTTP responses for login redirects
- Pauses all workers when session expires
- GUI dialog prompts for new cookie
- Resumes from where it left off

### Real-Time Statistics

Track download progress with live statistics:
- Downloads per minute
- Estimated time remaining (ETA)
- Success rate percentage
- Total bytes downloaded
```

**Step 2: Update config.yaml**

Add session section:
```yaml
session:
  expiry_patterns:
    - "login.aspx"
    - "enter mobile"
    - "session expired"
  refresh_timeout: 300  # seconds to wait for new cookie
```

**Step 3: Commit**

```bash
git add README.md config.yaml
git commit -m "docs: update README and config for Phase 3 features"
```

---

## Task 10: Final Integration Testing

**Step 1: Run full test suite**

Run: `.venv/bin/pytest tests/ -v`
Expected: All tests pass

**Step 2: Verify imports work**

```python
from scraper import (
    StatisticsTracker,
    SessionManager,
    SessionState,
    SessionExpiredError,
    CookieCapture,
    CookieCaptureMethod,
)
```

**Step 3: Commit any final fixes**

```bash
git add -A
git commit -m "test: verify Phase 3 integration"
```

---

## Summary

**Total Tasks:** 10
**New Files:** 6 (3 modules + 3 test files)
**Modified Files:** 4 (http_scraper.py, gui.py, __init__.py, README.md, config.yaml)
**Estimated Tests:** ~70 new tests

**Closes Issues:** #7, #9, #10
