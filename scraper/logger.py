"""
Logging module for Jamabandi Scraper.
Provides file rotation, console output, and helper functions for structured logging.
"""

import logging
import sys
import threading
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Optional

from .config import get_config

# Global logger instance and lock for thread-safe initialization
_root_logger: Optional[logging.Logger] = None
_logger_lock = threading.Lock()

# Log format
LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"


def setup_logging(
    name: str = "jamabandi",
    log_dir: Optional[Path] = None,
    level: Optional[str] = None,
    console: bool = True,
) -> logging.Logger:
    """
    Set up logging with file rotation and optional console output.

    Args:
        name: Logger name (default: "jamabandi")
        log_dir: Directory for log files (default: from config)
        level: Log level (default: from config)
        console: Whether to output to console (default: True)

    Returns:
        Configured logger instance
    """
    global _root_logger

    config = get_config()

    # Use config values if not provided
    if log_dir is None:
        log_dir = config.paths.logs_dir
    if level is None:
        level = config.logging.level

    # Ensure log_dir is a Path
    log_dir = Path(log_dir)

    # Create log directory if it doesn't exist
    log_dir.mkdir(parents=True, exist_ok=True)

    # Get or create logger
    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))

    # Clear existing handlers to avoid duplicates
    logger.handlers.clear()

    # Create formatter
    formatter = logging.Formatter(LOG_FORMAT)

    # Calculate max bytes from MB
    max_bytes = config.logging.max_file_size_mb * 1024 * 1024
    backup_count = config.logging.backup_count

    # Add rotating file handler
    log_file = log_dir / f"{name}.log"
    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    file_handler.setLevel(getattr(logging, level.upper(), logging.INFO))
    logger.addHandler(file_handler)

    # Add console handler if requested
    if console:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(formatter)
        console_handler.setLevel(getattr(logging, level.upper(), logging.INFO))
        logger.addHandler(console_handler)

    # Don't propagate to root logger to avoid duplicate messages
    logger.propagate = False

    # Store as global instance
    _root_logger = logger

    return logger


def get_logger(name: Optional[str] = None) -> logging.Logger:
    """
    Get a logger instance.

    Args:
        name: Logger name. If None, returns the root jamabandi logger.
              If provided, returns a child logger (e.g., "jamabandi.worker")

    Returns:
        Logger instance
    """
    global _root_logger

    # Thread-safe initialization with double-checked locking
    if _root_logger is None:
        with _logger_lock:
            if _root_logger is None:
                _root_logger = setup_logging()

    if name is None:
        return _root_logger

    # Return child logger
    root_name = _root_logger.name
    if name.startswith(root_name + "."):
        return logging.getLogger(name)
    else:
        return logging.getLogger(f"{root_name}.{name}")


def log_http_request(method: str, url: str, status: int, elapsed_ms: float) -> None:
    """
    Log an HTTP request with structured format.

    Args:
        method: HTTP method (GET, POST, etc.)
        url: Request URL
        status: HTTP status code
        elapsed_ms: Request duration in milliseconds
    """
    logger = get_logger()
    msg = f"HTTP {method} {url} -> {status} ({elapsed_ms:.0f}ms)"

    if status >= 500:
        logger.error(msg)
    elif status >= 400:
        logger.warning(msg)
    else:
        logger.info(msg)


def log_download(khewat: int, success: bool, message: str = "") -> None:
    """
    Log a download event with structured format.

    Args:
        khewat: Khewat number being downloaded
        success: Whether the download succeeded
        message: Optional additional message
    """
    logger = get_logger()
    status = "SUCCESS" if success else "FAILED"
    msg = f"DOWNLOAD khewat={khewat} status={status}"
    if message:
        msg += f" | {message}"

    if success:
        logger.info(msg)
    else:
        logger.error(msg)


def log_session_event(event: str, details: str = "") -> None:
    """
    Log a session event with structured format.

    Args:
        event: Event name (e.g., "START", "END", "CAPTCHA_SOLVED")
        details: Optional additional details
    """
    logger = get_logger()
    msg = f"SESSION {event}"
    if details:
        msg += f" | {details}"
    logger.info(msg)


class LogContext:
    """
    A logging context that prefixes all messages with a given prefix.
    Useful for worker IDs or request contexts.

    Example:
        ctx = LogContext(logger, "[Worker-1]")
        ctx.info("Processing item")  # Logs: "[Worker-1] Processing item"
    """

    def __init__(self, logger: logging.Logger, prefix: str):
        """
        Initialize a log context.

        Args:
            logger: The underlying logger to use
            prefix: Prefix to add to all messages
        """
        self._logger = logger
        self._prefix = prefix

    def _format(self, msg: str) -> str:
        """Add prefix to message."""
        return f"{self._prefix} {msg}"

    def debug(self, msg: str) -> None:
        """Log a debug message with prefix."""
        self._logger.debug(self._format(msg))

    def info(self, msg: str) -> None:
        """Log an info message with prefix."""
        self._logger.info(self._format(msg))

    def warning(self, msg: str) -> None:
        """Log a warning message with prefix."""
        self._logger.warning(self._format(msg))

    def error(self, msg: str) -> None:
        """Log an error message with prefix."""
        self._logger.error(self._format(msg))

    def critical(self, msg: str) -> None:
        """Log a critical message with prefix."""
        self._logger.critical(self._format(msg))

    def exception(self, msg: str) -> None:
        """Log an exception message with prefix."""
        self._logger.exception(self._format(msg))


def reset_logging() -> None:
    """
    Reset the global logger instance.
    Useful for testing.
    """
    global _root_logger
    if _root_logger is not None:
        # Close all handlers
        for handler in _root_logger.handlers[:]:
            handler.close()
            _root_logger.removeHandler(handler)
    _root_logger = None
