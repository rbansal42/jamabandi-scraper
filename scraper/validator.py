"""Validation utilities for downloaded files."""

import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Optional

from .logger import get_logger

logger = get_logger("validator")

# Optional pypdf for deep PDF validation
try:
    from pypdf import PdfReader
    from pypdf.errors import PdfReadError

    PYPDF_AVAILABLE = True
except ImportError:
    PYPDF_AVAILABLE = False
    PdfReader = None
    PdfReadError = Exception


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
    PDF_EOF_MARKER = b"%%EOF"
    MIN_SIZE_BYTES = 10 * 1024  # 10KB minimum

    HTML_ERROR_PATTERNS = [
        r"no\s+record\s+found",
        r"error\s+occurred",
        r"session\s+expired",
        r"please\s+login",
        r"access\s+denied",
    ]

    def __init__(self, deep_validation: bool = True):
        """
        Initialize PDF validator.

        Args:
            deep_validation: If True and pypdf is available, perform deep
                validation (page count, structure). If False, only basic checks.
        """
        self.deep_validation = deep_validation and PYPDF_AVAILABLE

    def validate_pdf(self, pdf_path: Path) -> ValidationResult:
        """Validate a PDF file with basic checks."""
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

    def validate_pdf_deep(self, pdf_path: Path) -> ValidationResult:
        """
        Perform deep PDF validation including structure and page count.

        Falls back to basic validation if pypdf is not available.
        """
        # First do basic validation
        basic_result = self.validate_pdf(pdf_path)
        if basic_result.status == ValidationStatus.INVALID:
            return basic_result

        size = pdf_path.stat().st_size

        # Check for EOF marker (basic structural check)
        try:
            with open(pdf_path, "rb") as f:
                f.seek(-128, 2)  # Read last 128 bytes
                tail = f.read()
            if self.PDF_EOF_MARKER not in tail:
                return ValidationResult(
                    ValidationStatus.WARNING,
                    "PDF missing EOF marker (may be truncated)",
                    {"size": size},
                )
        except Exception:
            pass  # File too small, skip this check

        # Deep validation with pypdf if available
        if self.deep_validation and PYPDF_AVAILABLE:
            try:
                reader = PdfReader(pdf_path)
                page_count = len(reader.pages)

                if page_count == 0:
                    return ValidationResult(
                        ValidationStatus.INVALID,
                        "PDF has no pages",
                        {"size": size, "pages": 0},
                    )

                # Try to access first page to ensure it's readable
                _ = reader.pages[0]

                logger.debug(f"PDF validated: {pdf_path.name} ({page_count} pages)")
                return ValidationResult(
                    ValidationStatus.VALID,
                    f"PDF is valid ({page_count} pages)",
                    {"size": size, "pages": page_count},
                )

            except PdfReadError as e:
                return ValidationResult(
                    ValidationStatus.INVALID,
                    f"PDF structure error: {e}",
                    {"size": size},
                )
            except Exception as e:
                logger.warning(f"Deep validation failed for {pdf_path}: {e}")
                # Fall through to return basic result

        return ValidationResult(
            ValidationStatus.VALID,
            "PDF is valid (basic check)",
            {"size": size},
        )

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


def validate_converted_pdf(pdf_path: Path, deep: bool = True) -> ValidationResult:
    """
    Validate a PDF after conversion.

    Args:
        pdf_path: Path to the converted PDF file.
        deep: If True, perform deep validation (page count, structure).

    Returns:
        ValidationResult with status and details.
    """
    validator = PDFValidator(deep_validation=deep)

    if deep:
        return validator.validate_pdf_deep(pdf_path)
    return validator.validate_pdf(pdf_path)
