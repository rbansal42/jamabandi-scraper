"""
Unit tests for the logging module.
"""

import logging
import os
import tempfile
from pathlib import Path

import pytest

from scraper.config import reset_config
from scraper.logger import (
    LOG_FORMAT,
    LogContext,
    get_logger,
    log_download,
    log_http_request,
    log_session_event,
    reset_logging,
    setup_logging,
)


@pytest.fixture(autouse=True)
def reset_singletons():
    """Reset config and logger singletons before each test."""
    reset_logging()
    reset_config()
    yield
    reset_logging()
    reset_config()


@pytest.fixture
def temp_log_dir():
    """Create a temporary directory for log files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


class TestSetupLogging:
    """Tests for setup_logging function."""

    def test_creates_log_file_in_specified_directory(self, temp_log_dir):
        """Log file should be created in the specified directory."""
        logger = setup_logging(name="test_logger", log_dir=temp_log_dir, console=False)

        # Write a log message to ensure file is created
        logger.info("Test message")

        # Check that log file exists
        log_file = temp_log_dir / "test_logger.log"
        assert log_file.exists(), f"Log file should exist at {log_file}"

    def test_log_entries_have_timestamps(self, temp_log_dir):
        """Log entries should contain timestamps."""
        logger = setup_logging(name="test_logger", log_dir=temp_log_dir, console=False)

        logger.info("Test message with timestamp")

        log_file = temp_log_dir / "test_logger.log"
        content = log_file.read_text()

        # Check for timestamp format (YYYY-MM-DD HH:MM:SS)
        import re

        timestamp_pattern = r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}"
        assert re.search(timestamp_pattern, content), "Log should contain timestamp"

    def test_log_entries_have_level(self, temp_log_dir):
        """Log entries should contain the log level."""
        logger = setup_logging(name="test_logger", log_dir=temp_log_dir, console=False)

        logger.info("Info message")
        logger.warning("Warning message")
        logger.error("Error message")

        log_file = temp_log_dir / "test_logger.log"
        content = log_file.read_text()

        assert "INFO" in content, "Log should contain INFO level"
        assert "WARNING" in content, "Log should contain WARNING level"
        assert "ERROR" in content, "Log should contain ERROR level"

    def test_respects_log_level(self, temp_log_dir):
        """Logger should respect the configured log level."""
        logger = setup_logging(
            name="test_logger", log_dir=temp_log_dir, level="WARNING", console=False
        )

        logger.debug("Debug message")
        logger.info("Info message")
        logger.warning("Warning message")

        log_file = temp_log_dir / "test_logger.log"
        content = log_file.read_text()

        assert "Debug message" not in content, "DEBUG should not be logged"
        assert "Info message" not in content, "INFO should not be logged"
        assert "Warning message" in content, "WARNING should be logged"

    def test_creates_log_directory_if_missing(self, temp_log_dir):
        """Should create log directory if it doesn't exist."""
        nested_dir = temp_log_dir / "nested" / "logs"

        logger = setup_logging(name="test_logger", log_dir=nested_dir, console=False)
        logger.info("Test")

        assert nested_dir.exists(), "Nested directory should be created"


class TestGetLogger:
    """Tests for get_logger function."""

    def test_returns_root_logger_when_no_name(self, temp_log_dir):
        """get_logger() should return the root logger when no name is provided."""
        setup_logging(name="jamabandi", log_dir=temp_log_dir, console=False)

        logger = get_logger()
        assert logger.name == "jamabandi"

    def test_returns_child_logger_with_name(self, temp_log_dir):
        """get_logger(name) should return a child logger."""
        setup_logging(name="jamabandi", log_dir=temp_log_dir, console=False)

        child = get_logger("worker")
        assert child.name == "jamabandi.worker"

    def test_child_logger_inherits_config(self, temp_log_dir):
        """Child loggers should inherit configuration from parent."""
        setup_logging(name="jamabandi", log_dir=temp_log_dir, console=False)

        child = get_logger("worker")
        child.info("Child logger message")

        # Message should appear in parent's log file
        log_file = temp_log_dir / "jamabandi.log"
        content = log_file.read_text()
        assert "Child logger message" in content
        assert "jamabandi.worker" in content

    def test_auto_initializes_if_not_setup(self):
        """get_logger() should auto-initialize if setup_logging wasn't called."""
        # Don't call setup_logging first
        logger = get_logger()
        assert logger is not None
        assert logger.name == "jamabandi"


class TestLogHttpRequest:
    """Tests for log_http_request helper function."""

    def test_formats_request_correctly(self, temp_log_dir):
        """HTTP request log should be properly formatted."""
        setup_logging(name="jamabandi", log_dir=temp_log_dir, console=False)

        log_http_request("GET", "https://example.com/api", 200, 150)

        log_file = temp_log_dir / "jamabandi.log"
        content = log_file.read_text()

        assert "HTTP GET https://example.com/api -> 200 (150ms)" in content

    def test_logs_error_for_5xx_status(self, temp_log_dir):
        """5xx status codes should be logged as errors."""
        setup_logging(name="jamabandi", log_dir=temp_log_dir, console=False)

        log_http_request("POST", "https://example.com/api", 500, 100)

        log_file = temp_log_dir / "jamabandi.log"
        content = log_file.read_text()

        assert "ERROR" in content

    def test_logs_warning_for_4xx_status(self, temp_log_dir):
        """4xx status codes should be logged as warnings."""
        setup_logging(name="jamabandi", log_dir=temp_log_dir, console=False)

        log_http_request("GET", "https://example.com/api", 404, 50)

        log_file = temp_log_dir / "jamabandi.log"
        content = log_file.read_text()

        assert "WARNING" in content


class TestLogDownload:
    """Tests for log_download helper function."""

    def test_formats_success_correctly(self, temp_log_dir):
        """Successful download should be logged with SUCCESS status."""
        setup_logging(name="jamabandi", log_dir=temp_log_dir, console=False)

        log_download(khewat=123, success=True)

        log_file = temp_log_dir / "jamabandi.log"
        content = log_file.read_text()

        assert "DOWNLOAD khewat=123 status=SUCCESS" in content
        assert "INFO" in content

    def test_formats_failure_correctly(self, temp_log_dir):
        """Failed download should be logged with FAILED status."""
        setup_logging(name="jamabandi", log_dir=temp_log_dir, console=False)

        log_download(khewat=456, success=False, message="Connection timeout")

        log_file = temp_log_dir / "jamabandi.log"
        content = log_file.read_text()

        assert "DOWNLOAD khewat=456 status=FAILED" in content
        assert "Connection timeout" in content
        assert "ERROR" in content


class TestLogSessionEvent:
    """Tests for log_session_event helper function."""

    def test_formats_event_correctly(self, temp_log_dir):
        """Session events should be properly formatted."""
        setup_logging(name="jamabandi", log_dir=temp_log_dir, console=False)

        log_session_event("START", "Beginning scrape session")

        log_file = temp_log_dir / "jamabandi.log"
        content = log_file.read_text()

        assert "SESSION START | Beginning scrape session" in content

    def test_event_without_details(self, temp_log_dir):
        """Session event without details should work."""
        setup_logging(name="jamabandi", log_dir=temp_log_dir, console=False)

        log_session_event("END")

        log_file = temp_log_dir / "jamabandi.log"
        content = log_file.read_text()

        assert "SESSION END" in content


class TestLogContext:
    """Tests for LogContext class."""

    def test_prefixes_info_messages(self, temp_log_dir):
        """LogContext should prefix info messages."""
        logger = setup_logging(name="jamabandi", log_dir=temp_log_dir, console=False)

        ctx = LogContext(logger, "[Worker-1]")
        ctx.info("Processing item")

        log_file = temp_log_dir / "jamabandi.log"
        content = log_file.read_text()

        assert "[Worker-1] Processing item" in content

    def test_prefixes_error_messages(self, temp_log_dir):
        """LogContext should prefix error messages."""
        logger = setup_logging(name="jamabandi", log_dir=temp_log_dir, console=False)

        ctx = LogContext(logger, "[Worker-2]")
        ctx.error("Failed to process")

        log_file = temp_log_dir / "jamabandi.log"
        content = log_file.read_text()

        assert "[Worker-2] Failed to process" in content
        assert "ERROR" in content

    def test_all_log_levels(self, temp_log_dir):
        """LogContext should support all log levels."""
        logger = setup_logging(
            name="jamabandi", log_dir=temp_log_dir, level="DEBUG", console=False
        )

        ctx = LogContext(logger, "[Test]")
        ctx.debug("Debug msg")
        ctx.info("Info msg")
        ctx.warning("Warning msg")
        ctx.error("Error msg")
        ctx.critical("Critical msg")

        log_file = temp_log_dir / "jamabandi.log"
        content = log_file.read_text()

        assert "[Test] Debug msg" in content
        assert "[Test] Info msg" in content
        assert "[Test] Warning msg" in content
        assert "[Test] Error msg" in content
        assert "[Test] Critical msg" in content


class TestLogFormat:
    """Tests for log format."""

    def test_format_includes_all_components(self, temp_log_dir):
        """Log format should include timestamp, level, name, and message."""
        logger = setup_logging(name="jamabandi", log_dir=temp_log_dir, console=False)

        logger.info("Test message")

        log_file = temp_log_dir / "jamabandi.log"
        content = log_file.read_text()

        # Check format: timestamp | level | name | message
        parts = content.split(" | ")
        assert len(parts) >= 4, (
            f"Log should have 4 parts separated by ' | ', got: {content}"
        )
