"""
Unit tests for the RetryManager module.

Tests cover:
- Error classification (transient vs permanent)
- Recording failures
- Getting retryable items
- Retry with mock download function
- Max retries respected
"""

import pytest

from scraper.config import reset_config
from scraper.logger import reset_logging
from scraper.retry_manager import FailedItem, FailureType, RetryManager


class TestErrorClassification:
    """Tests for classifying errors as transient or permanent."""

    def setup_method(self):
        reset_config()
        reset_logging()
        self.manager = RetryManager(max_retries=3)

    def teardown_method(self):
        reset_config()
        reset_logging()

    def test_timeout_is_transient(self):
        """Timeout errors should be classified as transient."""
        failure_type = self.manager._classify_error("Request timeout after 30s")
        assert failure_type == FailureType.TRANSIENT

    def test_rate_limit_is_transient(self):
        """Rate limit errors should be classified as transient."""
        failure_type = self.manager._classify_error("Rate limit exceeded")
        assert failure_type == FailureType.TRANSIENT

    def test_http_429_is_transient(self):
        """HTTP 429 errors should be classified as transient."""
        failure_type = self.manager._classify_error("HTTP 429: Too Many Requests")
        assert failure_type == FailureType.TRANSIENT

    def test_http_500_is_transient(self):
        """HTTP 500 errors should be classified as transient."""
        failure_type = self.manager._classify_error("HTTP 500: Internal Server Error")
        assert failure_type == FailureType.TRANSIENT

    def test_http_502_is_transient(self):
        """HTTP 502 errors should be classified as transient."""
        failure_type = self.manager._classify_error("HTTP 502: Bad Gateway")
        assert failure_type == FailureType.TRANSIENT

    def test_http_503_is_transient(self):
        """HTTP 503 errors should be classified as transient."""
        failure_type = self.manager._classify_error("HTTP 503: Service Unavailable")
        assert failure_type == FailureType.TRANSIENT

    def test_http_504_is_transient(self):
        """HTTP 504 errors should be classified as transient."""
        failure_type = self.manager._classify_error("HTTP 504: Gateway Timeout")
        assert failure_type == FailureType.TRANSIENT

    def test_connection_error_is_transient(self):
        """Connection errors should be classified as transient."""
        failure_type = self.manager._classify_error("Connection refused")
        assert failure_type == FailureType.TRANSIENT

    def test_network_error_is_transient(self):
        """Network errors should be classified as transient."""
        failure_type = self.manager._classify_error("Network unreachable")
        assert failure_type == FailureType.TRANSIENT

    def test_session_expired_is_transient(self):
        """Session expired errors should be classified as transient."""
        failure_type = self.manager._classify_error("Session expired, please re-login")
        assert failure_type == FailureType.TRANSIENT

    def test_no_record_is_permanent(self):
        """'No record' errors should be classified as permanent."""
        failure_type = self.manager._classify_error("No record found for this khewat")
        assert failure_type == FailureType.PERMANENT

    def test_not_found_is_permanent(self):
        """'Not found' errors should be classified as permanent."""
        failure_type = self.manager._classify_error("Record not found")
        assert failure_type == FailureType.PERMANENT

    def test_invalid_is_permanent(self):
        """'Invalid' errors should be classified as permanent."""
        failure_type = self.manager._classify_error("Invalid khewat number")
        assert failure_type == FailureType.PERMANENT

    def test_does_not_exist_is_permanent(self):
        """'Does not exist' errors should be classified as permanent."""
        failure_type = self.manager._classify_error("Khewat does not exist")
        assert failure_type == FailureType.PERMANENT

    def test_unknown_error_is_transient(self):
        """Unknown errors should default to transient (worth retrying)."""
        failure_type = self.manager._classify_error("Some unknown error occurred")
        assert failure_type == FailureType.TRANSIENT

    def test_case_insensitive_classification(self):
        """Error classification should be case-insensitive."""
        failure_type1 = self.manager._classify_error("TIMEOUT occurred")
        failure_type2 = self.manager._classify_error("NO RECORD found")
        assert failure_type1 == FailureType.TRANSIENT
        assert failure_type2 == FailureType.PERMANENT


class TestRecordingFailures:
    """Tests for recording failures."""

    def setup_method(self):
        reset_config()
        reset_logging()
        self.manager = RetryManager(max_retries=3)

    def teardown_method(self):
        reset_config()
        reset_logging()

    def test_record_failure_adds_to_list(self):
        """Recording a failure should add it to the failures list."""
        self.manager.record_failure(123, "Timeout error")

        assert len(self.manager._failures) == 1
        assert self.manager._failures[0].khewat == 123
        assert self.manager._failures[0].error == "Timeout error"

    def test_record_failure_sets_failure_type(self):
        """Recording a failure should classify the error type."""
        self.manager.record_failure(123, "Timeout error")
        self.manager.record_failure(456, "No record found")

        assert self.manager._failures[0].failure_type == FailureType.TRANSIENT
        assert self.manager._failures[1].failure_type == FailureType.PERMANENT

    def test_record_failure_initializes_retry_count(self):
        """New failures should have retry_count of 0."""
        self.manager.record_failure(123, "Timeout error")

        assert self.manager._failures[0].retry_count == 0

    def test_record_failure_increments_existing(self):
        """Recording the same khewat again should increment retry_count."""
        self.manager.record_failure(123, "Timeout error")
        self.manager.record_failure(123, "Another timeout")

        assert len(self.manager._failures) == 1
        assert self.manager._failures[0].retry_count == 1
        assert self.manager._failures[0].error == "Another timeout"

    def test_record_multiple_different_failures(self):
        """Can record failures for multiple different khewats."""
        self.manager.record_failure(100, "Error 1")
        self.manager.record_failure(200, "Error 2")
        self.manager.record_failure(300, "Error 3")

        assert len(self.manager._failures) == 3
        khewats = [f.khewat for f in self.manager._failures]
        assert khewats == [100, 200, 300]


class TestGetRetryable:
    """Tests for getting retryable items."""

    def setup_method(self):
        reset_config()
        reset_logging()
        self.manager = RetryManager(max_retries=3)

    def teardown_method(self):
        reset_config()
        reset_logging()

    def test_get_retryable_returns_transient_failures(self):
        """get_retryable should return only transient failures."""
        self.manager.record_failure(100, "Timeout error")
        self.manager.record_failure(200, "No record found")  # permanent
        self.manager.record_failure(300, "Connection error")

        retryable = self.manager.get_retryable()

        assert 100 in retryable
        assert 300 in retryable
        assert 200 not in retryable

    def test_get_retryable_respects_max_retries(self):
        """get_retryable should exclude items that exceeded max retries."""
        self.manager.record_failure(100, "Timeout")
        # Simulate 3 retries (0, 1, 2)
        self.manager._failures[0].retry_count = 3

        retryable = self.manager.get_retryable()

        assert 100 not in retryable

    def test_get_retryable_includes_under_max_retries(self):
        """get_retryable should include items under max retries."""
        self.manager.record_failure(100, "Timeout")
        self.manager._failures[0].retry_count = 2  # still under max_retries=3

        retryable = self.manager.get_retryable()

        assert 100 in retryable

    def test_get_retryable_empty_when_no_failures(self):
        """get_retryable should return empty list when no failures."""
        retryable = self.manager.get_retryable()

        assert retryable == []


class TestGetPermanentFailures:
    """Tests for getting permanent failures."""

    def setup_method(self):
        reset_config()
        reset_logging()
        self.manager = RetryManager(max_retries=3)

    def teardown_method(self):
        reset_config()
        reset_logging()

    def test_get_permanent_failures_returns_permanent_only(self):
        """get_permanent_failures should return only permanent failures."""
        self.manager.record_failure(100, "Timeout error")  # transient
        self.manager.record_failure(200, "No record found")  # permanent
        self.manager.record_failure(300, "Invalid khewat")  # permanent

        permanent = self.manager.get_permanent_failures()

        assert len(permanent) == 2
        khewats = [f.khewat for f in permanent]
        assert 200 in khewats
        assert 300 in khewats
        assert 100 not in khewats

    def test_get_permanent_failures_empty_when_none(self):
        """get_permanent_failures should return empty list when no permanent failures."""
        self.manager.record_failure(100, "Timeout error")

        permanent = self.manager.get_permanent_failures()

        assert permanent == []


class TestRetryAll:
    """Tests for retry_all functionality."""

    def setup_method(self):
        reset_config()
        reset_logging()
        self.manager = RetryManager(max_retries=3)

    def teardown_method(self):
        reset_config()
        reset_logging()

    def test_retry_all_calls_download_func(self):
        """retry_all should call download function for retryable items."""
        self.manager.record_failure(100, "Timeout")
        self.manager.record_failure(200, "Timeout")

        called_with = []

        def mock_download(khewat):
            called_with.append(khewat)
            return True

        # Patch time.sleep to avoid delays
        import scraper.retry_manager

        original_sleep = scraper.retry_manager.time.sleep
        scraper.retry_manager.time.sleep = lambda x: None

        try:
            self.manager.retry_all(mock_download)
        finally:
            scraper.retry_manager.time.sleep = original_sleep

        assert 100 in called_with
        assert 200 in called_with

    def test_retry_all_returns_stats(self):
        """retry_all should return retry statistics."""
        self.manager.record_failure(100, "Timeout")
        self.manager.record_failure(200, "Timeout")

        def mock_download(khewat):
            return khewat == 100  # Only 100 succeeds

        import scraper.retry_manager

        original_sleep = scraper.retry_manager.time.sleep
        scraper.retry_manager.time.sleep = lambda x: None

        try:
            result = self.manager.retry_all(mock_download)
        finally:
            scraper.retry_manager.time.sleep = original_sleep

        assert result["retried"] == 2
        assert result["succeeded"] == 1
        assert result["failed"] == 1

    def test_retry_all_removes_successful(self):
        """retry_all should remove successfully retried items from failures."""
        self.manager.record_failure(100, "Timeout")

        def mock_download(khewat):
            return True

        import scraper.retry_manager

        original_sleep = scraper.retry_manager.time.sleep
        scraper.retry_manager.time.sleep = lambda x: None

        try:
            self.manager.retry_all(mock_download)
        finally:
            scraper.retry_manager.time.sleep = original_sleep

        assert len(self.manager._failures) == 0

    def test_retry_all_increments_retry_count_on_failure(self):
        """retry_all should increment retry_count when download fails."""
        self.manager.record_failure(100, "Timeout")

        def mock_download(khewat):
            return False

        import scraper.retry_manager

        original_sleep = scraper.retry_manager.time.sleep
        scraper.retry_manager.time.sleep = lambda x: None

        try:
            self.manager.retry_all(mock_download)
        finally:
            scraper.retry_manager.time.sleep = original_sleep

        assert self.manager._failures[0].retry_count == 1

    def test_retry_all_handles_exception(self):
        """retry_all should handle exceptions from download function."""
        self.manager.record_failure(100, "Timeout")

        def mock_download(khewat):
            raise RuntimeError("Download failed")

        import scraper.retry_manager

        original_sleep = scraper.retry_manager.time.sleep
        scraper.retry_manager.time.sleep = lambda x: None

        try:
            result = self.manager.retry_all(mock_download)
        finally:
            scraper.retry_manager.time.sleep = original_sleep

        assert result["failed"] == 1
        assert self.manager._failures[0].error == "Download failed"
        assert self.manager._failures[0].retry_count == 1

    def test_retry_all_skips_permanent_failures(self):
        """retry_all should not retry permanent failures."""
        self.manager.record_failure(100, "No record found")  # permanent

        called_with = []

        def mock_download(khewat):
            called_with.append(khewat)
            return True

        import scraper.retry_manager

        original_sleep = scraper.retry_manager.time.sleep
        scraper.retry_manager.time.sleep = lambda x: None

        try:
            result = self.manager.retry_all(mock_download)
        finally:
            scraper.retry_manager.time.sleep = original_sleep

        assert 100 not in called_with
        assert result["retried"] == 0

    def test_retry_all_returns_zeros_when_nothing_to_retry(self):
        """retry_all should return zeros when nothing to retry."""
        result = self.manager.retry_all(lambda x: True)

        assert result == {"retried": 0, "succeeded": 0, "failed": 0}


class TestSummary:
    """Tests for summary functionality."""

    def setup_method(self):
        reset_config()
        reset_logging()
        self.manager = RetryManager(max_retries=3)

    def teardown_method(self):
        reset_config()
        reset_logging()

    def test_summary_returns_counts(self):
        """summary should return correct counts."""
        self.manager.record_failure(100, "Timeout")  # transient, retryable
        self.manager.record_failure(200, "No record")  # permanent
        self.manager.record_failure(300, "Connection error")  # transient, retryable
        # Make one exceed max retries
        self.manager._failures[2].retry_count = 3

        summary = self.manager.summary()

        assert summary["total"] == 3
        assert summary["retryable"] == 1  # only 100, since 300 exceeded max
        assert summary["permanent"] == 1

    def test_summary_empty_when_no_failures(self):
        """summary should return zeros when no failures."""
        summary = self.manager.summary()

        assert summary == {"total": 0, "retryable": 0, "permanent": 0}


class TestConfigIntegration:
    """Tests for configuration integration."""

    def setup_method(self):
        reset_config()
        reset_logging()

    def teardown_method(self):
        reset_config()
        reset_logging()

    def test_uses_config_max_retries(self):
        """RetryManager should use max_retries from config when not specified."""
        manager = RetryManager()
        # Default config has max_retries=3
        assert manager.max_retries == 3

    def test_uses_config_retry_delay(self):
        """RetryManager should use retry_delay from config."""
        manager = RetryManager()
        # Default config has retry_delay=5.0
        assert manager.retry_delay == 5.0

    def test_override_max_retries(self):
        """Explicit max_retries should override config."""
        manager = RetryManager(max_retries=5)
        assert manager.max_retries == 5


class TestFailedItemDataclass:
    """Tests for the FailedItem dataclass."""

    def test_failed_item_creation(self):
        """FailedItem should be creatable with required fields."""
        item = FailedItem(
            khewat=123, error="Test error", failure_type=FailureType.TRANSIENT
        )

        assert item.khewat == 123
        assert item.error == "Test error"
        assert item.failure_type == FailureType.TRANSIENT
        assert item.retry_count == 0  # default

    def test_failed_item_with_retry_count(self):
        """FailedItem should accept optional retry_count."""
        item = FailedItem(
            khewat=123,
            error="Test error",
            failure_type=FailureType.PERMANENT,
            retry_count=2,
        )

        assert item.retry_count == 2


class TestFailureTypeEnum:
    """Tests for the FailureType enum."""

    def test_transient_value(self):
        """TRANSIENT should have value 'transient'."""
        assert FailureType.TRANSIENT.value == "transient"

    def test_permanent_value(self):
        """PERMANENT should have value 'permanent'."""
        assert FailureType.PERMANENT.value == "permanent"
