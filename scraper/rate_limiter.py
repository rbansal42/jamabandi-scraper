"""Adaptive rate limiting based on server response times."""

import threading
import time
from collections import deque
from typing import Optional

from .config import get_config
from .logger import get_logger

logger = get_logger("rate_limiter")


class RateLimiter:
    """
    Adaptive rate limiter that adjusts delays based on server behavior.

    - Tracks recent response times in a sliding window
    - Increases delay on errors/slow responses
    - Decreases delay when server is responsive
    - Handles 429 with exponential backoff
    """

    def __init__(
        self,
        min_delay: Optional[float] = None,
        max_delay: Optional[float] = None,
        window_size: int = 10,
    ):
        config = get_config()
        self.min_delay = min_delay or config.delays.get("min_delay", 1.0)
        self.max_delay = max_delay or config.delays.get("max_delay", 5.0)
        self.current_delay = self.min_delay
        self.window_size = window_size

        self._response_times: deque = deque(maxlen=window_size)
        self._error_count = 0
        self._last_request_time = 0.0
        self._lock = threading.Lock()
        self._backoff_until = 0.0

    def wait(self) -> None:
        """Wait appropriate time before next request.

        Thread-safe: calculates wait time inside lock, sleeps outside lock
        to avoid blocking other threads.
        """
        wait_time = 0.0

        with self._lock:
            now = time.time()

            # Check backoff period
            if now < self._backoff_until:
                wait_time = self._backoff_until - now
                logger.debug(f"Backoff wait: {wait_time:.1f}s")
            else:
                # Normal rate limiting
                elapsed = now - self._last_request_time
                if elapsed < self.current_delay:
                    wait_time = self.current_delay - elapsed

            # Update last request time before releasing lock
            # (anticipating we will make the request after sleeping)
            self._last_request_time = now + wait_time

        # Sleep OUTSIDE the lock so other threads aren't blocked
        if wait_time > 0:
            time.sleep(wait_time)

    def record_response(self, status_code: int, response_time_ms: float) -> None:
        """Record response and adjust rate limiting."""
        with self._lock:
            if status_code == 429:
                self._handle_rate_limit()
            elif status_code >= 500:
                self._handle_error()
            elif status_code < 400:
                self._handle_success(response_time_ms)

    def _handle_rate_limit(self) -> None:
        """Handle 429 - exponential backoff."""
        self._error_count += 1
        backoff_time = min(60, 2**self._error_count)
        self._backoff_until = time.time() + backoff_time
        self.current_delay = min(self.max_delay, self.current_delay * 2)
        logger.warning(f"Rate limited! Backoff {backoff_time}s")

    def _handle_error(self) -> None:
        """Handle server errors."""
        self._error_count += 1
        self.current_delay = min(self.max_delay, self.current_delay * 1.5)

    def _handle_success(self, response_time_ms: float) -> None:
        """Handle success - potentially decrease delay."""
        self._response_times.append(response_time_ms)
        self._error_count = max(0, self._error_count - 1)

        if len(self._response_times) >= self.window_size:
            avg_time = sum(self._response_times) / len(self._response_times)
            if avg_time < 1000 and self._error_count == 0:
                self.current_delay = max(self.min_delay, self.current_delay * 0.9)

    @property
    def stats(self) -> dict:
        with self._lock:
            return {
                "current_delay": self.current_delay,
                "error_count": self._error_count,
                "avg_response_time": sum(self._response_times)
                / len(self._response_times)
                if self._response_times
                else 0,
            }
