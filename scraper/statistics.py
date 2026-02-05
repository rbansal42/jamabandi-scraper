"""
Real-time statistics tracker for download metrics.

Provides thread-safe tracking of download progress, speed calculations,
and formatted status output.
"""

import threading
import time
from collections import deque
from typing import Optional

from .config import get_config
from .logger import get_logger

logger = get_logger("statistics")


class StatisticsTracker:
    """
    Thread-safe statistics tracker for download operations.

    Tracks:
    - Completed/failed/pending counts
    - Bytes downloaded
    - Download speed (using sliding window)
    - ETA calculation
    - Success rate

    Example:
        tracker = StatisticsTracker(total_items=100)
        tracker.record_success(bytes_downloaded=1024)
        tracker.record_failure()
        print(tracker.format_stats())
    """

    def __init__(self, total_items: int, window_seconds: float = 60.0):
        """
        Initialize the statistics tracker.

        Args:
            total_items: Total number of items to process
            window_seconds: Size of sliding window for speed calculation (default: 60s)
        """
        self._total = total_items
        self._window_seconds = window_seconds

        self._completed = 0
        self._failed = 0
        self._bytes_downloaded = 0

        # Sliding window for speed calculation: list of (timestamp, count) tuples
        self._recent_downloads: deque = deque()

        self._start_time = time.time()
        self._lock = threading.Lock()

    def record_success(self, bytes_downloaded: int = 0) -> None:
        """
        Record a successful download.

        Args:
            bytes_downloaded: Number of bytes downloaded (default: 0)
        """
        with self._lock:
            self._completed += 1
            self._bytes_downloaded += bytes_downloaded
            self._recent_downloads.append((time.time(), 1))
            self._prune_old_entries()

    def record_failure(self) -> None:
        """Record a failed download."""
        with self._lock:
            self._failed += 1

    def _prune_old_entries(self) -> None:
        """Remove entries outside the sliding window. Must be called with lock held."""
        cutoff = time.time() - self._window_seconds
        while self._recent_downloads and self._recent_downloads[0][0] < cutoff:
            self._recent_downloads.popleft()

    def get_stats(self) -> dict:
        """
        Get current statistics as a dictionary.

        Returns:
            Dictionary containing:
            - completed: Number of successful downloads
            - failed: Number of failed downloads
            - pending: Number of items remaining
            - total: Total number of items
            - bytes_downloaded: Total bytes downloaded
            - downloads_per_minute: Current download speed
            - eta_seconds: Estimated time remaining (None if no speed)
            - success_rate: Percentage of successful downloads (0-100)
            - elapsed_seconds: Time since tracker started
        """
        with self._lock:
            self._prune_old_entries()

            completed = self._completed
            failed = self._failed
            total = self._total
            pending = total - completed - failed
            bytes_downloaded = self._bytes_downloaded
            elapsed = time.time() - self._start_time

            # Calculate downloads per minute from sliding window
            if self._recent_downloads:
                window_count = len(self._recent_downloads)
                if window_count > 0:
                    # Calculate actual window span
                    oldest_time = self._recent_downloads[0][0]
                    newest_time = self._recent_downloads[-1][0]
                    window_span = newest_time - oldest_time

                    if window_span > 0:
                        # Rate based on actual time between first and last download
                        downloads_per_minute = (window_count / window_span) * 60.0
                    elif window_count == 1:
                        # Single download, estimate based on time since start
                        time_since_start = newest_time - self._start_time
                        if time_since_start > 0:
                            downloads_per_minute = 60.0 / time_since_start
                        else:
                            downloads_per_minute = 0.0
                    else:
                        downloads_per_minute = 0.0
                else:
                    downloads_per_minute = 0.0
            else:
                downloads_per_minute = 0.0

            # Calculate ETA
            if downloads_per_minute > 0 and pending > 0:
                eta_seconds = (pending / downloads_per_minute) * 60.0
            else:
                eta_seconds = None

            # Calculate success rate
            processed = completed + failed
            if processed > 0:
                success_rate = (completed / processed) * 100.0
            else:
                success_rate = 0.0

            return {
                "completed": completed,
                "failed": failed,
                "pending": pending,
                "total": total,
                "bytes_downloaded": bytes_downloaded,
                "downloads_per_minute": downloads_per_minute,
                "eta_seconds": eta_seconds,
                "success_rate": success_rate,
                "elapsed_seconds": elapsed,
            }

    def format_stats(self) -> str:
        """
        Get a human-readable formatted string of current statistics.

        Returns:
            Formatted string like:
            "Progress: 50/100 (50.0%) | Failed: 5 | Speed: 10.5/min | ETA: 4m 45s | 1.5 MB"
        """
        stats = self.get_stats()

        completed = stats["completed"]
        total = stats["total"]
        failed = stats["failed"]
        pending = stats["pending"]
        speed = stats["downloads_per_minute"]
        eta = stats["eta_seconds"]
        bytes_dl = stats["bytes_downloaded"]
        success_rate = stats["success_rate"]

        # Format progress percentage
        if total > 0:
            progress_pct = ((completed + failed) / total) * 100.0
        else:
            progress_pct = 0.0

        # Format bytes
        bytes_str = self._format_bytes(bytes_dl)

        # Format ETA
        if eta is not None:
            eta_str = self._format_eta(eta)
        else:
            eta_str = "--"

        # Format speed
        speed_str = f"{speed:.1f}/min"

        return (
            f"Progress: {completed + failed}/{total} ({progress_pct:.1f}%) | "
            f"OK: {completed} | Failed: {failed} | "
            f"Speed: {speed_str} | ETA: {eta_str} | {bytes_str}"
        )

    def _format_bytes(self, bytes_value: int) -> str:
        """Format bytes as human-readable string (B/KB/MB)."""
        if bytes_value < 1024:
            return f"{bytes_value} B"
        elif bytes_value < 1024 * 1024:
            return f"{bytes_value / 1024:.1f} KB"
        else:
            return f"{bytes_value / (1024 * 1024):.1f} MB"

    def _format_eta(self, seconds: float) -> str:
        """Format ETA as 'Xm Ys'."""
        if seconds < 0:
            return "--"
        minutes = int(seconds // 60)
        secs = int(seconds % 60)
        if minutes > 0:
            return f"{minutes}m {secs}s"
        else:
            return f"{secs}s"

    def reset(self, total_items: Optional[int] = None) -> None:
        """
        Reset all statistics.

        Args:
            total_items: Optional new total (keeps existing if not provided)
        """
        with self._lock:
            if total_items is not None:
                self._total = total_items
            self._completed = 0
            self._failed = 0
            self._bytes_downloaded = 0
            self._recent_downloads.clear()
            self._start_time = time.time()
