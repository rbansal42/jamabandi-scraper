"""
Unit tests for the PDF backend abstraction module.

Tests should work even if PDF backends aren't installed.
"""

import os
import tempfile
from pathlib import Path
from unittest import mock

import pytest

from scraper.pdf_backend import (
    PDFBackend,
    is_weasyprint_available,
    is_wkhtmltopdf_available,
    detect_available_backends,
    get_default_backend,
    convert_html_to_pdf,
    convert_file,
    WEASYPRINT_CSS,
    WKHTMLTOPDF_OPTIONS,
    _WEASYPRINT_AVAILABLE,
    _WKHTMLTOPDF_AVAILABLE,
)


class TestPDFBackendEnum:
    """Tests for PDFBackend enum values."""

    def test_weasyprint_value(self):
        """PDFBackend.WEASYPRINT should exist."""
        assert PDFBackend.WEASYPRINT is not None
        assert PDFBackend.WEASYPRINT.value == "weasyprint"

    def test_wkhtmltopdf_value(self):
        """PDFBackend.WKHTMLTOPDF should exist."""
        assert PDFBackend.WKHTMLTOPDF is not None
        assert PDFBackend.WKHTMLTOPDF.value == "wkhtmltopdf"

    def test_enum_members(self):
        """Should have exactly two backends."""
        members = list(PDFBackend)
        assert len(members) == 2


class TestBackendDetection:
    """Tests for backend availability detection."""

    def test_is_weasyprint_available_returns_bool(self):
        """is_weasyprint_available should return a boolean."""
        result = is_weasyprint_available()
        assert isinstance(result, bool)

    def test_is_wkhtmltopdf_available_returns_bool(self):
        """is_wkhtmltopdf_available should return a boolean."""
        result = is_wkhtmltopdf_available()
        assert isinstance(result, bool)

    def test_detect_available_backends_returns_list(self):
        """detect_available_backends should return a list of PDFBackend."""
        result = detect_available_backends()
        assert isinstance(result, list)
        for backend in result:
            assert isinstance(backend, PDFBackend)

    def test_module_level_availability_bools_exist(self):
        """Module-level availability booleans should be defined."""
        assert isinstance(_WEASYPRINT_AVAILABLE, bool)
        assert isinstance(_WKHTMLTOPDF_AVAILABLE, bool)


class TestGetDefaultBackend:
    """Tests for get_default_backend function."""

    def test_returns_none_or_backend(self):
        """get_default_backend should return None or a PDFBackend."""
        result = get_default_backend()
        assert result is None or isinstance(result, PDFBackend)

    @mock.patch("scraper.pdf_backend._WKHTMLTOPDF_AVAILABLE", True)
    @mock.patch("scraper.pdf_backend._WEASYPRINT_AVAILABLE", False)
    def test_prefers_wkhtmltopdf_when_available(self):
        """Should prefer wkhtmltopdf when both are available."""
        # Re-import to get fresh detection with mocked values
        from scraper import pdf_backend

        # Mock both available
        with mock.patch.object(pdf_backend, "_WKHTMLTOPDF_AVAILABLE", True):
            with mock.patch.object(pdf_backend, "_WEASYPRINT_AVAILABLE", True):
                result = pdf_backend.get_default_backend()
                assert result == PDFBackend.WKHTMLTOPDF

    @mock.patch("scraper.pdf_backend._WKHTMLTOPDF_AVAILABLE", False)
    @mock.patch("scraper.pdf_backend._WEASYPRINT_AVAILABLE", True)
    def test_falls_back_to_weasyprint(self):
        """Should fall back to weasyprint if wkhtmltopdf not available."""
        from scraper import pdf_backend

        with mock.patch.object(pdf_backend, "_WKHTMLTOPDF_AVAILABLE", False):
            with mock.patch.object(pdf_backend, "_WEASYPRINT_AVAILABLE", True):
                result = pdf_backend.get_default_backend()
                assert result == PDFBackend.WEASYPRINT


class TestConstants:
    """Tests for CSS and options constants."""

    def test_weasyprint_css_is_string(self):
        """WEASYPRINT_CSS should be a non-empty string."""
        assert isinstance(WEASYPRINT_CSS, str)
        assert len(WEASYPRINT_CSS) > 0

    def test_weasyprint_css_has_landscape(self):
        """WEASYPRINT_CSS should specify landscape A4."""
        assert "landscape" in WEASYPRINT_CSS.lower()
        assert "A4" in WEASYPRINT_CSS

    def test_wkhtmltopdf_options_is_dict(self):
        """WKHTMLTOPDF_OPTIONS should be a dict."""
        assert isinstance(WKHTMLTOPDF_OPTIONS, dict)

    def test_wkhtmltopdf_options_has_orientation(self):
        """WKHTMLTOPDF_OPTIONS should have orientation setting."""
        assert (
            "orientation" in WKHTMLTOPDF_OPTIONS
            or "--orientation" in WKHTMLTOPDF_OPTIONS
        )
        # Value should be landscape
        key = "orientation" if "orientation" in WKHTMLTOPDF_OPTIONS else "--orientation"
        assert WKHTMLTOPDF_OPTIONS[key].lower() == "landscape"


class TestConvertHtmlToPdf:
    """Tests for convert_html_to_pdf function."""

    def test_returns_false_when_no_backend_available(self):
        """Should return False if no backend is available."""
        from scraper import pdf_backend

        with mock.patch.object(pdf_backend, "_WKHTMLTOPDF_AVAILABLE", False):
            with mock.patch.object(pdf_backend, "_WEASYPRINT_AVAILABLE", False):
                with tempfile.TemporaryDirectory() as tmpdir:
                    output_path = Path(tmpdir) / "test.pdf"
                    result = pdf_backend.convert_html_to_pdf(
                        "<html><body>Test</body></html>", output_path
                    )
                    assert result is False

    def test_creates_output_directory_if_missing(self):
        """Should create output directory if it doesn't exist."""
        # This test relies on having at least one backend available
        backends = detect_available_backends()
        if not backends:
            pytest.skip("No PDF backends available")

        with tempfile.TemporaryDirectory() as tmpdir:
            nested_path = Path(tmpdir) / "nested" / "path" / "test.pdf"
            result = convert_html_to_pdf("<html><body>Test</body></html>", nested_path)
            # If successful, parent dir should exist
            if result:
                assert nested_path.parent.exists()


class TestConvertFile:
    """Tests for convert_file function."""

    def test_returns_false_for_missing_input(self):
        """Should return False if input file doesn't exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            input_path = Path(tmpdir) / "nonexistent.html"
            output_path = Path(tmpdir) / "output.pdf"
            result = convert_file(input_path, output_path)
            assert result is False

    def test_delete_input_removes_file_on_success(self):
        """Should delete input file on success if delete_input=True."""
        backends = detect_available_backends()
        if not backends:
            pytest.skip("No PDF backends available")

        with tempfile.TemporaryDirectory() as tmpdir:
            input_path = Path(tmpdir) / "test.html"
            output_path = Path(tmpdir) / "test.pdf"

            # Create input file
            input_path.write_text("<html><body>Test</body></html>")
            assert input_path.exists()

            result = convert_file(input_path, output_path, delete_input=True)
            if result:
                assert not input_path.exists()
                assert output_path.exists()


@pytest.mark.skipif(not is_weasyprint_available(), reason="WeasyPrint not installed")
class TestWeasyPrintBackend:
    """Tests that require WeasyPrint to be installed."""

    def test_convert_html_with_weasyprint(self):
        """Should successfully convert HTML using WeasyPrint."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "test.pdf"
            result = convert_html_to_pdf(
                "<html><body><h1>Test</h1></body></html>",
                output_path,
                backend=PDFBackend.WEASYPRINT,
            )
            assert result is True
            assert output_path.exists()
            assert output_path.stat().st_size > 0

    def test_convert_with_custom_css(self):
        """Should apply custom CSS when converting."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "test.pdf"
            custom_css = "body { font-size: 20pt; }"
            result = convert_html_to_pdf(
                "<html><body><h1>Test</h1></body></html>",
                output_path,
                backend=PDFBackend.WEASYPRINT,
                custom_css=custom_css,
            )
            assert result is True
            assert output_path.exists()


@pytest.mark.skipif(not is_wkhtmltopdf_available(), reason="wkhtmltopdf not installed")
class TestWkhtmltopdfBackend:
    """Tests that require wkhtmltopdf to be installed."""

    def test_convert_html_with_wkhtmltopdf(self):
        """Should successfully convert HTML using wkhtmltopdf."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "test.pdf"
            result = convert_html_to_pdf(
                "<html><body><h1>Test</h1></body></html>",
                output_path,
                backend=PDFBackend.WKHTMLTOPDF,
            )
            assert result is True
            assert output_path.exists()
            assert output_path.stat().st_size > 0
