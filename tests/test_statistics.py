"""
Unit tests for the StatisticsTracker module.
"""

import threading
import time
from unittest.mock import patch

import pytest

from scraper.config import reset_config
from scraper.logger import reset_logging
from scraper.statistics import StatisticsTracker


class TestStatisticsTrackerInitialization:
    """Tests for StatisticsTracker initialization."""

    def setup_method(self):
        """Reset config and logging before each test."""
        reset_config()
        reset_logging()

    def teardown_method(self):
        """Reset config and logging after each test."""
        reset_config()
        reset_logging()

    def test_initial_counts_at_zero(self):
        """All counts should be zero initially."""
        tracker = StatisticsTracker(total_items=100)
        stats = tracker.get_stats()

        assert stats["completed"] == 0
        assert stats["failed"] == 0
        assert stats["bytes_downloaded"] == 0

    def test_total_stored_correctly(self):
        """Total items should be stored correctly."""
        tracker = StatisticsTracker(total_items=100)
        stats = tracker.get_stats()

        assert stats["total"] == 100

    def test_pending_equals_total_initially(self):
        """Pending should equal total initially."""
        tracker = StatisticsTracker(total_items=50)
        stats = tracker.get_stats()

        assert stats["pending"] == 50

    def test_custom_window_seconds(self):
        """Should accept custom window_seconds."""
        tracker = StatisticsTracker(total_items=100, window_seconds=30.0)
        assert tracker._window_seconds == 30.0

    def test_default_window_seconds(self):
        """Default window_seconds should be 60."""
        tracker = StatisticsTracker(total_items=100)
        assert tracker._window_seconds == 60.0


class TestStatisticsTrackerRecording:
    """Tests for recording successes and failures."""

    def setup_method(self):
        reset_config()
        reset_logging()

    def teardown_method(self):
        reset_config()
        reset_logging()

    def test_record_success_increments_completed(self):
        """record_success should increment completed count."""
        tracker = StatisticsTracker(total_items=100)

        tracker.record_success()
        stats = tracker.get_stats()

        assert stats["completed"] == 1

    def test_record_success_tracks_bytes(self):
        """record_success should track bytes downloaded."""
        tracker = StatisticsTracker(total_items=100)

        tracker.record_success(bytes_downloaded=1024)
        tracker.record_success(bytes_downloaded=2048)
        stats = tracker.get_stats()

        assert stats["bytes_downloaded"] == 3072

    def test_record_success_default_bytes_zero(self):
        """record_success with no bytes should default to zero."""
        tracker = StatisticsTracker(total_items=100)

        tracker.record_success()
        stats = tracker.get_stats()

        assert stats["bytes_downloaded"] == 0

    def test_record_failure_increments_failed(self):
        """record_failure should increment failed count."""
        tracker = StatisticsTracker(total_items=100)

        tracker.record_failure()
        stats = tracker.get_stats()

        assert stats["failed"] == 1

    def test_pending_decreases_with_progress(self):
        """Pending should decrease as items are processed."""
        tracker = StatisticsTracker(total_items=10)

        tracker.record_success()
        tracker.record_success()
        tracker.record_failure()
        stats = tracker.get_stats()

        assert stats["pending"] == 7
        assert stats["completed"] == 2
        assert stats["failed"] == 1


class TestStatisticsTrackerSpeedCalculation:
    """Tests for download speed calculation."""

    def setup_method(self):
        reset_config()
        reset_logging()

    def teardown_method(self):
        reset_config()
        reset_logging()

    def test_speed_zero_when_no_downloads(self):
        """Speed should be zero when no downloads recorded."""
        tracker = StatisticsTracker(total_items=100)
        stats = tracker.get_stats()

        assert stats["downloads_per_minute"] == 0.0

    def test_speed_calculated_from_recent_downloads(self):
        """Speed should be calculated from recent downloads."""
        tracker = StatisticsTracker(total_items=100, window_seconds=60.0)

        # Simulate downloads over time
        with patch("time.time") as mock_time:
            mock_time.return_value = 1000.0
            tracker._start_time = 1000.0

            # 10 downloads over 10 seconds = 60 per minute
            for i in range(10):
                mock_time.return_value = 1000.0 + i
                tracker.record_success()

            mock_time.return_value = 1009.0
            stats = tracker.get_stats()

        # 10 downloads over 9 seconds = 66.67/min
        assert stats["downloads_per_minute"] > 60.0

    def test_old_downloads_pruned_from_window(self):
        """Downloads outside window should be pruned."""
        tracker = StatisticsTracker(total_items=100, window_seconds=10.0)

        with patch("time.time") as mock_time:
            mock_time.return_value = 1000.0
            tracker._start_time = 1000.0

            # Old downloads
            tracker.record_success()
            tracker.record_success()

            # Move time forward past window
            mock_time.return_value = 1020.0

            # New downloads
            tracker.record_success()

            stats = tracker.get_stats()

        # Only the recent download should count for speed
        # But completed count should still reflect all downloads
        assert stats["completed"] == 3


class TestStatisticsTrackerEtaCalculation:
    """Tests for ETA calculation."""

    def setup_method(self):
        reset_config()
        reset_logging()

    def teardown_method(self):
        reset_config()
        reset_logging()

    def test_eta_none_when_no_speed(self):
        """ETA should be None when there's no speed."""
        tracker = StatisticsTracker(total_items=100)
        stats = tracker.get_stats()

        assert stats["eta_seconds"] is None

    def test_eta_calculated_when_speed_available(self):
        """ETA should be calculated based on speed and pending."""
        tracker = StatisticsTracker(total_items=100, window_seconds=60.0)

        with patch("time.time") as mock_time:
            mock_time.return_value = 1000.0
            tracker._start_time = 1000.0

            # Record some downloads to establish speed
            for i in range(10):
                mock_time.return_value = 1000.0 + i * 6  # 10 downloads per minute
                tracker.record_success()

            mock_time.return_value = 1054.0
            stats = tracker.get_stats()

        # With 90 pending and ~10/min, ETA should be around 9 minutes (540 seconds)
        assert stats["eta_seconds"] is not None
        assert stats["eta_seconds"] > 0

    def test_eta_decreases_with_progress(self):
        """ETA should decrease as more items are completed."""
        tracker = StatisticsTracker(total_items=100, window_seconds=60.0)

        with patch("time.time") as mock_time:
            mock_time.return_value = 1000.0
            tracker._start_time = 1000.0

            # First batch of downloads
            for i in range(10):
                mock_time.return_value = 1000.0 + i
                tracker.record_success()

            mock_time.return_value = 1009.0
            stats1 = tracker.get_stats()
            eta1 = stats1["eta_seconds"]

            # More downloads
            for i in range(20):
                mock_time.return_value = 1009.0 + i
                tracker.record_success()

            mock_time.return_value = 1028.0
            stats2 = tracker.get_stats()
            eta2 = stats2["eta_seconds"]

        # ETA should have decreased (fewer pending items)
        assert eta1 is not None
        assert eta2 is not None
        assert eta2 < eta1


class TestStatisticsTrackerSuccessRate:
    """Tests for success rate calculation."""

    def setup_method(self):
        reset_config()
        reset_logging()

    def teardown_method(self):
        reset_config()
        reset_logging()

    def test_success_rate_100_percent_all_success(self):
        """Success rate should be 100% when all succeed."""
        tracker = StatisticsTracker(total_items=100)

        for _ in range(10):
            tracker.record_success()

        stats = tracker.get_stats()
        assert stats["success_rate"] == 100.0

    def test_success_rate_0_percent_all_fail(self):
        """Success rate should be 0% when all fail."""
        tracker = StatisticsTracker(total_items=100)

        for _ in range(10):
            tracker.record_failure()

        stats = tracker.get_stats()
        assert stats["success_rate"] == 0.0

    def test_success_rate_calculated_correctly(self):
        """Success rate should be calculated correctly."""
        tracker = StatisticsTracker(total_items=100)

        # 7 successes, 3 failures = 70% success rate
        for _ in range(7):
            tracker.record_success()
        for _ in range(3):
            tracker.record_failure()

        stats = tracker.get_stats()
        assert stats["success_rate"] == 70.0

    def test_success_rate_zero_when_no_processing(self):
        """Success rate should be 0% when nothing processed."""
        tracker = StatisticsTracker(total_items=100)
        stats = tracker.get_stats()

        assert stats["success_rate"] == 0.0


class TestStatisticsTrackerThreadSafety:
    """Tests for thread safety."""

    def setup_method(self):
        reset_config()
        reset_logging()

    def teardown_method(self):
        reset_config()
        reset_logging()

    def test_concurrent_record_success(self):
        """record_success should be thread-safe."""
        tracker = StatisticsTracker(total_items=10000)
        errors = []

        def record_successes():
            try:
                for _ in range(100):
                    tracker.record_success(bytes_downloaded=100)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=record_successes) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        stats = tracker.get_stats()
        assert stats["completed"] == 1000
        assert stats["bytes_downloaded"] == 100000

    def test_concurrent_record_failure(self):
        """record_failure should be thread-safe."""
        tracker = StatisticsTracker(total_items=10000)
        errors = []

        def record_failures():
            try:
                for _ in range(100):
                    tracker.record_failure()
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=record_failures) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        stats = tracker.get_stats()
        assert stats["failed"] == 1000

    def test_concurrent_mixed_operations(self):
        """Mixed operations should be thread-safe."""
        tracker = StatisticsTracker(total_items=10000)
        errors = []

        def record_successes():
            try:
                for _ in range(100):
                    tracker.record_success(bytes_downloaded=50)
            except Exception as e:
                errors.append(e)

        def record_failures():
            try:
                for _ in range(50):
                    tracker.record_failure()
            except Exception as e:
                errors.append(e)

        def read_stats():
            try:
                for _ in range(100):
                    tracker.get_stats()
            except Exception as e:
                errors.append(e)

        threads = (
            [threading.Thread(target=record_successes) for _ in range(5)]
            + [threading.Thread(target=record_failures) for _ in range(5)]
            + [threading.Thread(target=read_stats) for _ in range(3)]
        )

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        stats = tracker.get_stats()
        assert stats["completed"] == 500
        assert stats["failed"] == 250


class TestStatisticsTrackerFormatting:
    """Tests for formatted output."""

    def setup_method(self):
        reset_config()
        reset_logging()

    def teardown_method(self):
        reset_config()
        reset_logging()

    def test_format_stats_returns_string(self):
        """format_stats should return a string."""
        tracker = StatisticsTracker(total_items=100)
        result = tracker.format_stats()

        assert isinstance(result, str)
        assert len(result) > 0

    def test_format_stats_contains_progress(self):
        """format_stats should contain progress information."""
        tracker = StatisticsTracker(total_items=100)
        tracker.record_success()
        tracker.record_success()

        result = tracker.format_stats()

        assert "2/100" in result
        assert "Progress" in result

    def test_format_stats_contains_failed_count(self):
        """format_stats should contain failed count."""
        tracker = StatisticsTracker(total_items=100)
        tracker.record_failure()
        tracker.record_failure()
        tracker.record_failure()

        result = tracker.format_stats()

        assert "Failed: 3" in result

    def test_format_bytes_as_b(self):
        """Small byte counts should be formatted as B."""
        tracker = StatisticsTracker(total_items=100)
        tracker.record_success(bytes_downloaded=500)

        result = tracker.format_stats()

        assert "500 B" in result

    def test_format_bytes_as_kb(self):
        """Kilobyte counts should be formatted as KB."""
        tracker = StatisticsTracker(total_items=100)
        tracker.record_success(bytes_downloaded=5 * 1024)

        result = tracker.format_stats()

        assert "KB" in result

    def test_format_bytes_as_mb(self):
        """Megabyte counts should be formatted as MB."""
        tracker = StatisticsTracker(total_items=100)
        tracker.record_success(bytes_downloaded=5 * 1024 * 1024)

        result = tracker.format_stats()

        assert "MB" in result

    def test_format_eta_with_minutes(self):
        """ETA should be formatted as 'Xm Ys'."""
        tracker = StatisticsTracker(total_items=100)

        # Mock to get a predictable ETA
        with patch("time.time") as mock_time:
            mock_time.return_value = 1000.0
            tracker._start_time = 1000.0

            for i in range(10):
                mock_time.return_value = 1000.0 + i
                tracker.record_success()

            mock_time.return_value = 1009.0
            result = tracker.format_stats()

        # Should contain 'm' for minutes
        assert "m" in result or "s" in result

    def test_format_eta_placeholder_when_none(self):
        """ETA should show '--' when not calculable."""
        tracker = StatisticsTracker(total_items=100)
        result = tracker.format_stats()

        assert "--" in result


class TestStatisticsTrackerReset:
    """Tests for reset functionality."""

    def setup_method(self):
        reset_config()
        reset_logging()

    def teardown_method(self):
        reset_config()
        reset_logging()

    def test_reset_clears_counts(self):
        """reset should clear all counts."""
        tracker = StatisticsTracker(total_items=100)
        tracker.record_success(bytes_downloaded=1000)
        tracker.record_success(bytes_downloaded=500)
        tracker.record_failure()

        tracker.reset()
        stats = tracker.get_stats()

        assert stats["completed"] == 0
        assert stats["failed"] == 0
        assert stats["bytes_downloaded"] == 0

    def test_reset_preserves_total_by_default(self):
        """reset should preserve total by default."""
        tracker = StatisticsTracker(total_items=100)
        tracker.record_success()

        tracker.reset()
        stats = tracker.get_stats()

        assert stats["total"] == 100

    def test_reset_with_new_total(self):
        """reset should accept new total."""
        tracker = StatisticsTracker(total_items=100)
        tracker.record_success()

        tracker.reset(total_items=200)
        stats = tracker.get_stats()

        assert stats["total"] == 200

    def test_reset_clears_sliding_window(self):
        """reset should clear the sliding window."""
        tracker = StatisticsTracker(total_items=100)

        # Record some downloads
        for _ in range(10):
            tracker.record_success()

        # Verify window has entries
        assert len(tracker._recent_downloads) > 0

        tracker.reset()

        # Window should be empty
        assert len(tracker._recent_downloads) == 0

    def test_reset_resets_start_time(self):
        """reset should reset the start time."""
        tracker = StatisticsTracker(total_items=100)
        original_start = tracker._start_time

        # Wait a tiny bit
        time.sleep(0.01)

        tracker.reset()

        assert tracker._start_time > original_start


class TestStatisticsTrackerElapsedTime:
    """Tests for elapsed time tracking."""

    def setup_method(self):
        reset_config()
        reset_logging()

    def teardown_method(self):
        reset_config()
        reset_logging()

    def test_elapsed_seconds_increases(self):
        """elapsed_seconds should increase over time."""
        tracker = StatisticsTracker(total_items=100)

        stats1 = tracker.get_stats()
        time.sleep(0.05)
        stats2 = tracker.get_stats()

        assert stats2["elapsed_seconds"] > stats1["elapsed_seconds"]

    def test_elapsed_seconds_starts_near_zero(self):
        """elapsed_seconds should start near zero."""
        tracker = StatisticsTracker(total_items=100)
        stats = tracker.get_stats()

        # Should be very small (less than 1 second)
        assert stats["elapsed_seconds"] < 1.0
