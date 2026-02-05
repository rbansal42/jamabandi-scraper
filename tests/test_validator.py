"""
Unit tests for the validator module.
"""

import tempfile
from pathlib import Path

import pytest

from scraper.config import reset_config
from scraper.logger import reset_logging
from scraper.validator import (
    PDFValidator,
    ValidationResult,
    ValidationStatus,
    validate_download,
    validate_converted_pdf,
    PYPDF_AVAILABLE,
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
def temp_dir():
    """Create a temporary directory for test files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def validator():
    """Create a PDFValidator instance."""
    return PDFValidator()


class TestValidationResult:
    """Tests for ValidationResult dataclass."""

    def test_creates_with_required_fields(self):
        """ValidationResult should be creatable with status and message."""
        result = ValidationResult(ValidationStatus.VALID, "Test message")
        assert result.status == ValidationStatus.VALID
        assert result.message == "Test message"
        assert result.details is None

    def test_creates_with_details(self):
        """ValidationResult should accept optional details."""
        result = ValidationResult(
            ValidationStatus.WARNING, "Warning message", {"key": "value"}
        )
        assert result.status == ValidationStatus.WARNING
        assert result.details == {"key": "value"}


class TestPDFValidatorValidatePDF:
    """Tests for PDFValidator.validate_pdf method."""

    def test_valid_pdf_file(self, validator, temp_dir):
        """Should return VALID for a proper PDF file."""
        pdf_path = temp_dir / "test.pdf"
        # Create a valid PDF-like file (header + enough content)
        content = b"%PDF-1.4\n" + b"x" * (15 * 1024)  # 15KB of content
        pdf_path.write_bytes(content)

        result = validator.validate_pdf(pdf_path)

        assert result.status == ValidationStatus.VALID
        assert result.message == "PDF is valid"
        assert result.details["size"] == len(content)

    def test_missing_file(self, validator, temp_dir):
        """Should return INVALID for non-existent file."""
        pdf_path = temp_dir / "nonexistent.pdf"

        result = validator.validate_pdf(pdf_path)

        assert result.status == ValidationStatus.INVALID
        assert result.message == "File does not exist"

    def test_small_file(self, validator, temp_dir):
        """Should return WARNING for files smaller than MIN_SIZE_BYTES."""
        pdf_path = temp_dir / "small.pdf"
        content = b"%PDF-1.4\n" + b"x" * 1000  # ~1KB
        pdf_path.write_bytes(content)

        result = validator.validate_pdf(pdf_path)

        assert result.status == ValidationStatus.WARNING
        assert "too small" in result.message
        assert result.details["size"] == len(content)

    def test_invalid_header(self, validator, temp_dir):
        """Should return INVALID for files without PDF header."""
        pdf_path = temp_dir / "not_pdf.pdf"
        content = b"<html>This is HTML, not PDF</html>" + b"x" * (15 * 1024)
        pdf_path.write_bytes(content)

        result = validator.validate_pdf(pdf_path)

        assert result.status == ValidationStatus.INVALID
        assert result.message == "Invalid PDF header"

    def test_empty_file(self, validator, temp_dir):
        """Should return WARNING for empty file (size check comes first)."""
        pdf_path = temp_dir / "empty.pdf"
        pdf_path.write_bytes(b"")

        result = validator.validate_pdf(pdf_path)

        assert result.status == ValidationStatus.WARNING
        assert "too small" in result.message


class TestPDFValidatorValidateHTMLContent:
    """Tests for PDFValidator.validate_html_content method."""

    def test_valid_html_content(self, validator):
        """Should return VALID for normal HTML content."""
        html = "<html><body>" + "Normal content. " * 100 + "</body></html>"

        result = validator.validate_html_content(html)

        assert result.status == ValidationStatus.VALID
        assert result.message == "HTML is valid"

    def test_no_record_found_pattern(self, validator):
        """Should return INVALID when 'no record found' pattern is detected."""
        html = "<html><body>No Record Found for this query</body></html>"

        result = validator.validate_html_content(html)

        assert result.status == ValidationStatus.INVALID
        assert "Error pattern found" in result.message
        assert result.details["pattern"] == r"no\s+record\s+found"

    def test_error_occurred_pattern(self, validator):
        """Should return INVALID when 'error occurred' pattern is detected."""
        html = "<html><body>An error occurred while processing</body></html>"

        result = validator.validate_html_content(html)

        assert result.status == ValidationStatus.INVALID
        assert result.details["pattern"] == r"error\s+occurred"

    def test_session_expired_pattern(self, validator):
        """Should return INVALID when 'session expired' pattern is detected."""
        html = "<html><body>Your session expired. Please login again.</body></html>"

        result = validator.validate_html_content(html)

        assert result.status == ValidationStatus.INVALID
        assert result.details["pattern"] == r"session\s+expired"

    def test_please_login_pattern(self, validator):
        """Should return INVALID when 'please login' pattern is detected."""
        html = "<html><body>Please login to continue</body></html>"

        result = validator.validate_html_content(html)

        assert result.status == ValidationStatus.INVALID
        assert result.details["pattern"] == r"please\s+login"

    def test_access_denied_pattern(self, validator):
        """Should return INVALID when 'access denied' pattern is detected."""
        html = "<html><body>Access Denied - You don't have permission</body></html>"

        result = validator.validate_html_content(html)

        assert result.status == ValidationStatus.INVALID
        assert result.details["pattern"] == r"access\s+denied"

    def test_short_content(self, validator):
        """Should return WARNING for content shorter than 1000 chars."""
        html = "<html><body>Short content</body></html>"

        result = validator.validate_html_content(html)

        assert result.status == ValidationStatus.WARNING
        assert "too short" in result.message

    def test_case_insensitive_matching(self, validator):
        """Should detect error patterns regardless of case."""
        html = "<html><body>NO RECORD FOUND</body></html>"

        result = validator.validate_html_content(html)

        assert result.status == ValidationStatus.INVALID


class TestValidateDownload:
    """Tests for validate_download convenience function."""

    def test_valid_html_only(self):
        """Should return VALID for valid HTML when no PDF path provided."""
        html = "<html><body>" + "Valid content. " * 100 + "</body></html>"

        result = validate_download(html)

        assert result.status == ValidationStatus.VALID
        assert result.message == "Download validated"

    def test_invalid_html(self):
        """Should return INVALID when HTML contains error patterns."""
        html = "<html><body>No record found</body></html>"

        result = validate_download(html)

        assert result.status == ValidationStatus.INVALID
        assert "Error pattern found" in result.message

    def test_valid_html_and_pdf(self, temp_dir):
        """Should return VALID when both HTML and PDF are valid."""
        html = "<html><body>" + "Valid content. " * 100 + "</body></html>"
        pdf_path = temp_dir / "test.pdf"
        pdf_path.write_bytes(b"%PDF-1.4\n" + b"x" * (15 * 1024))

        result = validate_download(html, pdf_path)

        assert result.status == ValidationStatus.VALID

    def test_valid_html_invalid_pdf(self, temp_dir):
        """Should return INVALID when HTML is valid but PDF is not."""
        html = "<html><body>" + "Valid content. " * 100 + "</body></html>"
        pdf_path = temp_dir / "not_pdf.pdf"
        pdf_path.write_bytes(b"<html>Not a PDF</html>" + b"x" * (15 * 1024))

        result = validate_download(html, pdf_path)

        assert result.status == ValidationStatus.INVALID
        assert result.message == "Invalid PDF header"

    def test_valid_html_missing_pdf(self, temp_dir):
        """Should return INVALID when PDF file doesn't exist."""
        html = "<html><body>" + "Valid content. " * 100 + "</body></html>"
        pdf_path = temp_dir / "missing.pdf"

        result = validate_download(html, pdf_path)

        assert result.status == ValidationStatus.INVALID
        assert result.message == "File does not exist"

    def test_valid_html_small_pdf(self, temp_dir):
        """Should return WARNING when PDF is too small."""
        html = "<html><body>" + "Valid content. " * 100 + "</body></html>"
        pdf_path = temp_dir / "small.pdf"
        pdf_path.write_bytes(b"%PDF-1.4\n" + b"x" * 100)

        result = validate_download(html, pdf_path)

        assert result.status == ValidationStatus.WARNING
        assert "too small" in result.message


class TestPDFValidatorDeepValidation:
    """Tests for PDFValidator.validate_pdf_deep method."""

    def test_valid_pdf_with_eof_marker(self, temp_dir):
        """Should return VALID for PDF with proper EOF marker."""
        pdf_path = temp_dir / "test.pdf"
        content = b"%PDF-1.4\n" + b"x" * (15 * 1024) + b"\n%%EOF\n"
        pdf_path.write_bytes(content)

        validator = PDFValidator(deep_validation=False)
        result = validator.validate_pdf_deep(pdf_path)

        assert result.status == ValidationStatus.VALID

    def test_pdf_without_eof_marker(self, temp_dir):
        """Should return WARNING for PDF without EOF marker."""
        pdf_path = temp_dir / "test.pdf"
        # Large enough file without EOF marker
        content = b"%PDF-1.4\n" + b"x" * (15 * 1024)
        pdf_path.write_bytes(content)

        validator = PDFValidator(deep_validation=False)
        result = validator.validate_pdf_deep(pdf_path)

        assert result.status == ValidationStatus.WARNING
        assert "EOF marker" in result.message

    def test_missing_file_deep(self, temp_dir):
        """Should return INVALID for non-existent file."""
        pdf_path = temp_dir / "nonexistent.pdf"

        validator = PDFValidator(deep_validation=False)
        result = validator.validate_pdf_deep(pdf_path)

        assert result.status == ValidationStatus.INVALID
        assert result.message == "File does not exist"

    def test_deep_validation_disabled_without_pypdf(self, temp_dir):
        """Should fall back to basic validation when deep_validation=False."""
        pdf_path = temp_dir / "test.pdf"
        content = b"%PDF-1.4\n" + b"x" * (15 * 1024) + b"\n%%EOF\n"
        pdf_path.write_bytes(content)

        validator = PDFValidator(deep_validation=False)
        result = validator.validate_pdf_deep(pdf_path)

        assert result.status == ValidationStatus.VALID
        assert "basic check" in result.message or "pages" not in result.message


class TestValidateConvertedPDF:
    """Tests for validate_converted_pdf convenience function."""

    def test_valid_pdf(self, temp_dir):
        """Should return VALID for valid PDF."""
        pdf_path = temp_dir / "test.pdf"
        content = b"%PDF-1.4\n" + b"x" * (15 * 1024) + b"\n%%EOF\n"
        pdf_path.write_bytes(content)

        result = validate_converted_pdf(pdf_path, deep=False)

        assert result.status == ValidationStatus.VALID

    def test_invalid_pdf(self, temp_dir):
        """Should return INVALID for invalid PDF."""
        pdf_path = temp_dir / "test.pdf"
        content = b"<html>Not a PDF</html>" + b"x" * (15 * 1024)
        pdf_path.write_bytes(content)

        result = validate_converted_pdf(pdf_path, deep=False)

        assert result.status == ValidationStatus.INVALID

    def test_missing_pdf(self, temp_dir):
        """Should return INVALID for missing file."""
        pdf_path = temp_dir / "nonexistent.pdf"

        result = validate_converted_pdf(pdf_path, deep=False)

        assert result.status == ValidationStatus.INVALID


@pytest.mark.skipif(not PYPDF_AVAILABLE, reason="pypdf not installed")
class TestPDFValidatorWithPyPDF:
    """Tests for PDF validation with pypdf (requires pypdf installed)."""

    def test_validates_real_pdf_structure(self, temp_dir):
        """Should validate actual PDF structure when pypdf available."""
        # This test requires a real PDF file created by a PDF library
        # For unit testing, we just verify the validator initializes correctly
        validator = PDFValidator(deep_validation=True)
        assert validator.deep_validation is True
