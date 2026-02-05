"""Retry manager for failed downloads."""

import time
from dataclasses import dataclass
from enum import Enum
from typing import Callable, List, Optional

from .config import get_config
from .logger import get_logger

logger = get_logger("retry")


class FailureType(Enum):
    TRANSIENT = "transient"  # Worth retrying
    PERMANENT = "permanent"  # Don't retry


@dataclass
class FailedItem:
    khewat: int
    error: str
    failure_type: FailureType
    retry_count: int = 0


class RetryManager:
    """Manages retry logic for failed downloads."""

    TRANSIENT_ERRORS = [
        "timeout",
        "rate limit",
        "429",
        "500",
        "502",
        "503",
        "504",
        "connection",
        "network",
        "session expired",
    ]
    PERMANENT_ERRORS = ["no record", "not found", "invalid", "does not exist"]

    def __init__(self, max_retries: Optional[int] = None):
        config = get_config()
        self.max_retries = max_retries or config.retry.get("max_retries", 3)
        self.retry_delay = config.retry.get("retry_delay", 5.0)
        self._failures: List[FailedItem] = []

    def record_failure(self, khewat: int, error: str) -> None:
        """Record a failed download."""
        failure_type = self._classify_error(error)

        for item in self._failures:
            if item.khewat == khewat:
                item.retry_count += 1
                item.error = error
                return

        self._failures.append(
            FailedItem(khewat=khewat, error=error, failure_type=failure_type)
        )
        logger.debug(f"Recorded {failure_type.value} failure for khewat {khewat}")

    def _classify_error(self, error: str) -> FailureType:
        error_lower = error.lower()
        for pattern in self.PERMANENT_ERRORS:
            if pattern in error_lower:
                return FailureType.PERMANENT
        return FailureType.TRANSIENT

    def get_retryable(self) -> List[int]:
        """Get khewats worth retrying."""
        return [
            item.khewat
            for item in self._failures
            if item.failure_type == FailureType.TRANSIENT
            and item.retry_count < self.max_retries
        ]

    def get_permanent_failures(self) -> List[FailedItem]:
        return [
            item
            for item in self._failures
            if item.failure_type == FailureType.PERMANENT
        ]

    def retry_all(self, download_func: Callable[[int], bool]) -> dict:
        """Retry all retryable failures with exponential backoff."""
        retryable = self.get_retryable()
        if not retryable:
            return {"retried": 0, "succeeded": 0, "failed": 0}

        logger.info(f"Retrying {len(retryable)} failed downloads...")
        succeeded = failed = 0

        for khewat in retryable:
            item = next(f for f in self._failures if f.khewat == khewat)
            delay = self.retry_delay * (2**item.retry_count)

            logger.info(
                f"Retry {item.retry_count + 1}/{self.max_retries} for khewat {khewat}"
            )
            time.sleep(min(delay, 30))  # Cap at 30s

            try:
                if download_func(khewat):
                    succeeded += 1
                    self._failures = [f for f in self._failures if f.khewat != khewat]
                else:
                    failed += 1
                    item.retry_count += 1
            except Exception as e:
                failed += 1
                item.retry_count += 1
                item.error = str(e)

        return {"retried": len(retryable), "succeeded": succeeded, "failed": failed}

    def summary(self) -> dict:
        return {
            "total": len(self._failures),
            "retryable": len(self.get_retryable()),
            "permanent": len(self.get_permanent_failures()),
        }
