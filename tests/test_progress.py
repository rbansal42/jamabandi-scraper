"""
Unit tests for the ProgressTracker class with enhanced persistence features.
"""

import json
import os
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from scraper.http_scraper import ProgressTracker


class TestAtomicSave:
    """Tests for atomic save functionality."""

    def test_atomic_save_creates_file(self):
        """Atomic save should create the progress file correctly."""
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = Path(tmpdir) / "progress.json"
            tracker = ProgressTracker(str(filepath))

            tracker.mark_complete(1)
            tracker.flush()  # Force save

            assert filepath.exists()
            with open(filepath) as f:
                data = json.load(f)
            assert 1 in data["completed"]
            assert data["last_updated"] is not None

    def test_atomic_save_no_temp_file_leftover(self):
        """Atomic save should not leave temp files behind."""
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = Path(tmpdir) / "progress.json"
            tracker = ProgressTracker(str(filepath))

            tracker.mark_complete(1)
            tracker.flush()

            # Check no .tmp files exist
            tmp_files = list(Path(tmpdir).glob("*.tmp"))
            assert len(tmp_files) == 0

    def test_atomic_save_preserves_data_on_load(self):
        """Data saved atomically should be correctly loaded."""
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = Path(tmpdir) / "progress.json"

            # Create and save
            tracker1 = ProgressTracker(str(filepath))
            tracker1.mark_complete(1)
            tracker1.mark_complete(2)
            tracker1.mark_failed(3, "Test error")
            tracker1.flush()

            # Load in new instance
            tracker2 = ProgressTracker(str(filepath))
            assert 1 in tracker2.data["completed"]
            assert 2 in tracker2.data["completed"]
            assert "3" in tracker2.data["failed"]

    def test_atomic_save_creates_parent_dirs(self):
        """Atomic save should create parent directories if needed."""
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = Path(tmpdir) / "subdir" / "nested" / "progress.json"
            tracker = ProgressTracker(str(filepath))

            tracker.mark_complete(1)
            tracker.flush()

            assert filepath.exists()


class TestSaveInterval:
    """Tests for configurable save interval."""

    def test_default_save_interval(self):
        """Default save interval should be 5."""
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = Path(tmpdir) / "progress.json"
            tracker = ProgressTracker(str(filepath))
            assert tracker.save_interval == 5

    def test_custom_save_interval(self):
        """Custom save interval should be respected."""
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = Path(tmpdir) / "progress.json"
            tracker = ProgressTracker(str(filepath), save_interval=10)
            assert tracker.save_interval == 10

    def test_save_triggers_at_interval(self):
        """Save should trigger after save_interval completions."""
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = Path(tmpdir) / "progress.json"
            tracker = ProgressTracker(str(filepath), save_interval=3)

            # Mark 2 complete - should not save yet
            tracker.mark_complete(1)
            tracker.mark_complete(2)

            # File might exist from init, check unsaved count
            assert tracker._unsaved_count == 2

            # Mark 3rd - should trigger save
            tracker.mark_complete(3)
            assert tracker._unsaved_count == 0  # Reset after save

    def test_save_triggers_for_failures_too(self):
        """Failed items should also count toward save interval."""
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = Path(tmpdir) / "progress.json"
            tracker = ProgressTracker(str(filepath), save_interval=2)

            tracker.mark_failed(1, "Error 1")
            assert tracker._unsaved_count == 1

            tracker.mark_failed(2, "Error 2")
            assert tracker._unsaved_count == 0  # Saved after 2

    def test_flush_saves_pending(self):
        """Flush should save even if interval not reached."""
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = Path(tmpdir) / "progress.json"
            tracker = ProgressTracker(str(filepath), save_interval=10)

            tracker.mark_complete(1)
            assert tracker._unsaved_count == 1

            tracker.flush()
            assert tracker._unsaved_count == 0

            # Verify file has the data
            with open(filepath) as f:
                data = json.load(f)
            assert 1 in data["completed"]

    def test_flush_noop_when_nothing_pending(self):
        """Flush should be a no-op when nothing pending."""
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = Path(tmpdir) / "progress.json"
            tracker = ProgressTracker(str(filepath), save_interval=3)

            # Mark exactly 3 to trigger save
            tracker.mark_complete(1)
            tracker.mark_complete(2)
            tracker.mark_complete(3)
            assert tracker._unsaved_count == 0

            # Get modification time
            mtime_before = filepath.stat().st_mtime
            time.sleep(0.01)  # Ensure time difference

            tracker.flush()  # Should be no-op

            mtime_after = filepath.stat().st_mtime
            assert mtime_before == mtime_after


class TestThreadSafety:
    """Tests for thread-safe operations."""

    def test_concurrent_mark_complete(self):
        """Concurrent mark_complete calls should be thread-safe."""
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = Path(tmpdir) / "progress.json"
            tracker = ProgressTracker(
                str(filepath), save_interval=100
            )  # High interval to avoid saves

            def mark_items(start, count):
                for i in range(start, start + count):
                    tracker.mark_complete(i)

            threads = []
            for t in range(5):  # 5 threads
                thread = threading.Thread(target=mark_items, args=(t * 20, 20))
                threads.append(thread)

            for t in threads:
                t.start()
            for t in threads:
                t.join()

            # All 100 items should be completed
            assert len(tracker.data["completed"]) == 100
            assert sorted(tracker.data["completed"]) == list(range(100))

    def test_concurrent_mark_and_flush(self):
        """Concurrent marking and flushing should be thread-safe."""
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = Path(tmpdir) / "progress.json"
            tracker = ProgressTracker(str(filepath), save_interval=5)

            errors = []

            def mark_items():
                try:
                    for i in range(50):
                        tracker.mark_complete(i)
                        time.sleep(0.001)
                except Exception as e:
                    errors.append(e)

            def periodic_flush():
                try:
                    for _ in range(10):
                        tracker.flush()
                        time.sleep(0.005)
                except Exception as e:
                    errors.append(e)

            t1 = threading.Thread(target=mark_items)
            t2 = threading.Thread(target=periodic_flush)

            t1.start()
            t2.start()
            t1.join()
            t2.join()

            assert len(errors) == 0
            assert len(tracker.data["completed"]) == 50

    def test_concurrent_mixed_operations(self):
        """Mixed concurrent operations should be thread-safe."""
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = Path(tmpdir) / "progress.json"
            tracker = ProgressTracker(str(filepath), save_interval=10)

            def complete_items():
                for i in range(0, 50, 2):
                    tracker.mark_complete(i)

            def fail_items():
                for i in range(1, 50, 2):
                    tracker.mark_failed(i, f"Error {i}")

            with ThreadPoolExecutor(max_workers=4) as executor:
                futures = [
                    executor.submit(complete_items),
                    executor.submit(fail_items),
                    executor.submit(complete_items),  # Duplicate, should be handled
                    executor.submit(fail_items),
                ]
                for f in futures:
                    f.result()  # Wait and check for exceptions

            tracker.flush()

            # 25 completed (0, 2, 4, ..., 48)
            assert len(tracker.data["completed"]) == 25
            # 25 failed (1, 3, 5, ..., 49)
            assert len(tracker.data["failed"]) == 25


class TestMetadataTracking:
    """Tests for metadata and statistics tracking."""

    def test_stats_initialized(self):
        """Stats should be initialized with correct structure."""
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = Path(tmpdir) / "progress.json"
            tracker = ProgressTracker(str(filepath))

            stats = tracker.get_stats()
            assert "start_time" in stats
            assert "total_time" in stats
            assert "download_count" in stats
            assert "bytes_downloaded" in stats

    def test_download_count_incremented(self):
        """Download count should increment on mark_complete."""
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = Path(tmpdir) / "progress.json"
            tracker = ProgressTracker(str(filepath))

            tracker.mark_complete(1)
            tracker.mark_complete(2)
            tracker.mark_complete(3)

            assert tracker.data["stats"]["download_count"] == 3

    def test_bytes_downloaded_tracked(self):
        """Bytes downloaded should be accumulated."""
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = Path(tmpdir) / "progress.json"
            tracker = ProgressTracker(str(filepath))

            tracker.mark_complete(1, bytes_downloaded=1000)
            tracker.mark_complete(2, bytes_downloaded=2000)
            tracker.mark_complete(3, bytes_downloaded=500)

            assert tracker.data["stats"]["bytes_downloaded"] == 3500

    def test_duplicate_complete_not_double_counted(self):
        """Marking same khewat twice should not double-count."""
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = Path(tmpdir) / "progress.json"
            tracker = ProgressTracker(str(filepath))

            tracker.mark_complete(1, bytes_downloaded=1000)
            tracker.mark_complete(1, bytes_downloaded=1000)  # Duplicate

            assert tracker.data["stats"]["download_count"] == 1
            assert tracker.data["stats"]["bytes_downloaded"] == 1000

    def test_start_time_set_on_set_config(self):
        """Start time should be set when config is set."""
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = Path(tmpdir) / "progress.json"
            tracker = ProgressTracker(str(filepath))

            assert tracker.data["stats"]["start_time"] is None

            tracker.set_config(
                {
                    "district_code": "17",
                    "tehsil_code": "102",
                    "village_code": "02532",
                    "period": "2023-2024",
                }
            )

            assert tracker.data["stats"]["start_time"] is not None

    def test_start_time_preserved_on_reload(self):
        """Start time should be preserved when loading existing progress."""
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = Path(tmpdir) / "progress.json"

            tracker1 = ProgressTracker(str(filepath))
            tracker1.set_config(
                {
                    "district_code": "17",
                    "tehsil_code": "102",
                    "village_code": "02532",
                    "period": "2023-2024",
                }
            )
            original_start_time = tracker1.data["stats"]["start_time"]

            # Load in new instance
            tracker2 = ProgressTracker(str(filepath))
            tracker2.set_config(
                {
                    "district_code": "17",
                    "tehsil_code": "102",
                    "village_code": "02532",
                    "period": "2023-2024",
                }
            )

            # Start time should be preserved (not reset)
            assert tracker2.data["stats"]["start_time"] == original_start_time

    def test_stats_loaded_from_existing_file(self):
        """Stats should be correctly loaded from existing progress file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = Path(tmpdir) / "progress.json"

            # Create tracker and add some data
            tracker1 = ProgressTracker(str(filepath))
            tracker1.mark_complete(1, bytes_downloaded=500)
            tracker1.mark_complete(2, bytes_downloaded=600)
            tracker1.flush()

            # Load in new instance
            tracker2 = ProgressTracker(str(filepath))

            assert tracker2.data["stats"]["download_count"] == 2
            assert tracker2.data["stats"]["bytes_downloaded"] == 1100


class TestBackwardCompatibility:
    """Tests for backward compatibility with older progress files."""

    def test_loads_legacy_format_without_stats(self):
        """Should handle legacy progress files without stats section."""
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = Path(tmpdir) / "progress.json"

            # Write legacy format file
            legacy_data = {
                "config": {"district": "17"},
                "completed": [1, 2, 3],
                "failed": {"4": "Some error"},
                "last_updated": "2024-01-01T00:00:00",
            }
            with open(filepath, "w") as f:
                json.dump(legacy_data, f)

            # Load should work
            tracker = ProgressTracker(str(filepath))

            assert tracker.data["completed"] == [1, 2, 3]
            assert "4" in tracker.data["failed"]
            # Stats should be initialized
            assert "stats" in tracker.data
            assert tracker.data["stats"]["download_count"] == 0

    def test_loads_partial_stats(self):
        """Should handle progress files with partial stats section."""
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = Path(tmpdir) / "progress.json"

            # Write file with partial stats
            partial_data = {
                "config": {},
                "completed": [1],
                "failed": {},
                "last_updated": None,
                "stats": {"download_count": 5},  # Missing other fields
            }
            with open(filepath, "w") as f:
                json.dump(partial_data, f)

            tracker = ProgressTracker(str(filepath))

            # Existing stat preserved
            assert tracker.data["stats"]["download_count"] == 5
            # Missing stats filled in
            assert tracker.data["stats"]["bytes_downloaded"] == 0
            assert tracker.data["stats"]["start_time"] is None


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_mark_complete_removes_from_failed(self):
        """Marking complete should remove from failed list."""
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = Path(tmpdir) / "progress.json"
            tracker = ProgressTracker(str(filepath))

            tracker.mark_failed(1, "Initial failure")
            assert "1" in tracker.data["failed"]

            tracker.mark_complete(1)
            assert "1" not in tracker.data["failed"]
            assert 1 in tracker.data["completed"]

    def test_completed_list_stays_sorted(self):
        """Completed list should remain sorted."""
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = Path(tmpdir) / "progress.json"
            tracker = ProgressTracker(str(filepath))

            tracker.mark_complete(5)
            tracker.mark_complete(1)
            tracker.mark_complete(3)
            tracker.mark_complete(2)
            tracker.mark_complete(4)

            assert tracker.data["completed"] == [1, 2, 3, 4, 5]

    def test_get_pending_respects_completed(self):
        """get_pending should exclude completed items."""
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = Path(tmpdir) / "progress.json"
            tracker = ProgressTracker(str(filepath))

            tracker.mark_complete(2)
            tracker.mark_complete(4)

            pending = tracker.get_pending(1, 5)
            assert pending == [1, 3, 5]

    def test_corrupted_json_handled(self):
        """Should handle corrupted JSON gracefully."""
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = Path(tmpdir) / "progress.json"

            # Write corrupted JSON
            with open(filepath, "w") as f:
                f.write("{corrupted json content")

            # Should not raise, use defaults
            tracker = ProgressTracker(str(filepath))

            assert tracker.data["completed"] == []
            assert tracker.data["failed"] == {}
