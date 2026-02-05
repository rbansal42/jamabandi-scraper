"""Validation utilities for downloaded files."""

import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Optional

from .logger import get_logger

logger = get_logger("validator")


class ValidationStatus(Enum):
    VALID = "valid"
    INVALID = "invalid"
    WARNING = "warning"


@dataclass
class ValidationResult:
    status: ValidationStatus
    message: str
    details: Optional[dict] = None


class PDFValidator:
    """Validates PDF files."""

    PDF_HEADER = b"%PDF-"
    MIN_SIZE_BYTES = 10 * 1024  # 10KB minimum

    HTML_ERROR_PATTERNS = [
        r"no\s+record\s+found",
        r"error\s+occurred",
        r"session\s+expired",
        r"please\s+login",
        r"access\s+denied",
    ]

    def validate_pdf(self, pdf_path: Path) -> ValidationResult:
        """Validate a PDF file."""
        if not pdf_path.exists():
            return ValidationResult(ValidationStatus.INVALID, "File does not exist")

        size = pdf_path.stat().st_size
        if size < self.MIN_SIZE_BYTES:
            return ValidationResult(
                ValidationStatus.WARNING,
                f"File too small ({size} bytes)",
                {"size": size},
            )

        try:
            with open(pdf_path, "rb") as f:
                header = f.read(8)
            if not header.startswith(self.PDF_HEADER):
                return ValidationResult(ValidationStatus.INVALID, "Invalid PDF header")
        except Exception as e:
            return ValidationResult(ValidationStatus.INVALID, f"Read error: {e}")

        return ValidationResult(ValidationStatus.VALID, "PDF is valid", {"size": size})

    def validate_html_content(self, html: str) -> ValidationResult:
        """Validate HTML content for error patterns."""
        html_lower = html.lower()

        for pattern in self.HTML_ERROR_PATTERNS:
            if re.search(pattern, html_lower):
                return ValidationResult(
                    ValidationStatus.INVALID,
                    f"Error pattern found: {pattern}",
                    {"pattern": pattern},
                )

        if len(html) < 1000:
            return ValidationResult(
                ValidationStatus.WARNING,
                f"Content too short ({len(html)} chars)",
            )

        return ValidationResult(ValidationStatus.VALID, "HTML is valid")


def validate_download(html: str, pdf_path: Optional[Path] = None) -> ValidationResult:
    """Convenience function to validate a download."""
    validator = PDFValidator()

    html_result = validator.validate_html_content(html)
    if html_result.status == ValidationStatus.INVALID:
        return html_result

    if pdf_path:
        pdf_result = validator.validate_pdf(pdf_path)
        if pdf_result.status != ValidationStatus.VALID:
            return pdf_result

    return ValidationResult(ValidationStatus.VALID, "Download validated")
