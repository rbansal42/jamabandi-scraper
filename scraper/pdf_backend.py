"""
PDF backend abstraction module.

Supports both WeasyPrint and wkhtmltopdf backends for HTML to PDF conversion.
Provides automatic backend detection and fallback.
"""

from __future__ import annotations

import shutil
from enum import Enum
from pathlib import Path
from typing import List, Optional

from .config import get_config
from .logger import get_logger

logger = get_logger("pdf_backend")


class PDFBackend(Enum):
    """Available PDF conversion backends."""

    WEASYPRINT = "weasyprint"
    WKHTMLTOPDF = "wkhtmltopdf"


# Detect WeasyPrint availability at import time
try:
    from weasyprint import HTML, CSS
    from weasyprint.text.fonts import FontConfiguration

    _WEASYPRINT_AVAILABLE = True
except ImportError:
    _WEASYPRINT_AVAILABLE = False
    HTML = None
    CSS = None
    FontConfiguration = None

# Detect pdfkit/wkhtmltopdf availability at import time
try:
    import pdfkit

    # Also verify the wkhtmltopdf binary exists
    _WKHTMLTOPDF_BINARY = shutil.which("wkhtmltopdf")
    _WKHTMLTOPDF_AVAILABLE = _WKHTMLTOPDF_BINARY is not None
except ImportError:
    pdfkit = None
    _WKHTMLTOPDF_AVAILABLE = False


# Custom CSS for WeasyPrint - landscape A4 for Jamabandi tables
WEASYPRINT_CSS = """
@page {
    size: A4 landscape;
    margin: 0.6cm;
}

/* Override the print-blocking CSS */
@media print {
    html, body {
        display: block !important;
        visibility: visible !important;
    }
}

/* Force everything to be visible */
html, body {
    display: block !important;
    visibility: visible !important;
    margin: 0;
    padding: 0;
}

/* Table rendering */
table {
    width: 100% !important;
    border-collapse: collapse;
    font-size: 7.5pt;
    table-layout: fixed;
    word-wrap: break-word;
    overflow-wrap: break-word;
}

th, td {
    border: 1px solid #333;
    padding: 2px 3px;
    overflow: hidden;
    word-wrap: break-word;
    overflow-wrap: break-word;
}

th {
    font-size: 7pt;
    background-color: #eee;
}

/* Strip any leftover inline widths */
span[style] {
    width: auto !important;
    max-width: 100% !important;
    position: static !important;
}

/* Hide unnecessary elements */
.btn_login, .header_43, form > div:first-child {
    display: none !important;
}

script {
    display: none !important;
}

#btnLogout, #btnGetVirifiableNakal, #dvlang {
    display: none !important;
}
"""

# Equivalent options for wkhtmltopdf
WKHTMLTOPDF_OPTIONS = {
    "orientation": "Landscape",
    "page-size": "A4",
    "margin-top": "6mm",
    "margin-right": "6mm",
    "margin-bottom": "6mm",
    "margin-left": "6mm",
    "encoding": "UTF-8",
    "no-stop-slow-scripts": None,
    "enable-local-file-access": None,
    "quiet": None,
}


def is_weasyprint_available() -> bool:
    """Check if WeasyPrint is available for use."""
    return _WEASYPRINT_AVAILABLE


def is_wkhtmltopdf_available() -> bool:
    """Check if wkhtmltopdf is available for use."""
    return _WKHTMLTOPDF_AVAILABLE


def detect_available_backends() -> List[PDFBackend]:
    """
    Detect which PDF backends are available on this system.

    Returns:
        List of available PDFBackend enum values.
    """
    available = []
    if _WKHTMLTOPDF_AVAILABLE:
        available.append(PDFBackend.WKHTMLTOPDF)
    if _WEASYPRINT_AVAILABLE:
        available.append(PDFBackend.WEASYPRINT)
    return available


def get_default_backend() -> Optional[PDFBackend]:
    """
    Get the default PDF backend to use.

    Prefers wkhtmltopdf over WeasyPrint for better performance.
    Can be overridden via config if a pdf.backend setting exists.

    Returns:
        The default PDFBackend, or None if no backends are available.
    """
    config = get_config()

    # Check if config specifies a preferred backend
    preferred = config.get("pdf.backend")
    if preferred:
        preferred_lower = preferred.lower()
        if preferred_lower == "wkhtmltopdf" and _WKHTMLTOPDF_AVAILABLE:
            return PDFBackend.WKHTMLTOPDF
        elif preferred_lower == "weasyprint" and _WEASYPRINT_AVAILABLE:
            return PDFBackend.WEASYPRINT

    # Default preference: wkhtmltopdf > weasyprint
    if _WKHTMLTOPDF_AVAILABLE:
        return PDFBackend.WKHTMLTOPDF
    if _WEASYPRINT_AVAILABLE:
        return PDFBackend.WEASYPRINT

    return None


def _convert_weasyprint(
    html_content: str, output_path: Path, custom_css: Optional[str] = None
) -> bool:
    """
    Convert HTML to PDF using WeasyPrint.

    Args:
        html_content: HTML string to convert.
        output_path: Path to write the PDF file.
        custom_css: Optional additional CSS to apply.

    Returns:
        True if conversion succeeded, False otherwise.
    """
    if not _WEASYPRINT_AVAILABLE:
        logger.error("WeasyPrint is not available")
        return False

    try:
        font_config = FontConfiguration()

        # Build stylesheets
        stylesheets = [CSS(string=WEASYPRINT_CSS, font_config=font_config)]
        if custom_css:
            stylesheets.append(CSS(string=custom_css, font_config=font_config))

        # Create HTML object and convert
        html_doc = HTML(string=html_content)
        html_doc.write_pdf(
            output_path, stylesheets=stylesheets, font_config=font_config
        )

        logger.info(f"Converted to PDF using WeasyPrint: {output_path}")
        return True

    except Exception as e:
        logger.error(f"WeasyPrint conversion failed: {e}")
        return False


def _convert_wkhtmltopdf(
    html_content: str, output_path: Path, custom_css: Optional[str] = None
) -> bool:
    """
    Convert HTML to PDF using wkhtmltopdf via pdfkit.

    Args:
        html_content: HTML string to convert.
        output_path: Path to write the PDF file.
        custom_css: Optional additional CSS to inject into the HTML.

    Returns:
        True if conversion succeeded, False otherwise.
    """
    if not _WKHTMLTOPDF_AVAILABLE:
        logger.error("wkhtmltopdf is not available")
        return False

    try:
        # Inject custom CSS into HTML if provided
        if custom_css:
            import re

            style_tag = f"<style>{custom_css}</style>"
            # Case-insensitive matching for HTML tags
            html_lower = html_content.lower()
            if "<head>" in html_lower:
                # Find the actual tag position (case-insensitive) and insert after it
                match = re.search(r"<head[^>]*>", html_content, re.IGNORECASE)
                if match:
                    insert_pos = match.end()
                    html_content = (
                        html_content[:insert_pos]
                        + style_tag
                        + html_content[insert_pos:]
                    )
            elif "<html>" in html_lower:
                match = re.search(r"<html[^>]*>", html_content, re.IGNORECASE)
                if match:
                    insert_pos = match.end()
                    html_content = (
                        html_content[:insert_pos]
                        + f"<head>{style_tag}</head>"
                        + html_content[insert_pos:]
                    )
            else:
                html_content = f"<html><head>{style_tag}</head>{html_content}</html>"

        # Convert using pdfkit
        pdfkit.from_string(html_content, str(output_path), options=WKHTMLTOPDF_OPTIONS)

        logger.info(f"Converted to PDF using wkhtmltopdf: {output_path}")
        return True

    except Exception as e:
        logger.error(f"wkhtmltopdf conversion failed: {e}")
        return False


def convert_html_to_pdf(
    html_content: str,
    output_path: Path,
    backend: Optional[PDFBackend] = None,
    custom_css: Optional[str] = None,
) -> bool:
    """
    Convert HTML content to PDF using the specified or default backend.

    Args:
        html_content: HTML string to convert.
        output_path: Path to write the PDF file.
        backend: Specific backend to use, or None for auto-detection.
        custom_css: Optional additional CSS to apply.

    Returns:
        True if conversion succeeded, False otherwise.
    """
    # Ensure output_path is a Path object
    output_path = Path(output_path)

    # Create output directory if needed
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Determine backend to use
    if backend is None:
        backend = get_default_backend()

    if backend is None:
        logger.error("No PDF backend available. Install weasyprint or wkhtmltopdf.")
        return False

    # Dispatch to appropriate converter
    if backend == PDFBackend.WEASYPRINT:
        return _convert_weasyprint(html_content, output_path, custom_css)
    elif backend == PDFBackend.WKHTMLTOPDF:
        return _convert_wkhtmltopdf(html_content, output_path, custom_css)
    else:
        logger.error(f"Unknown backend: {backend}")
        return False


def convert_file(
    input_path: Path,
    output_path: Path,
    backend: Optional[PDFBackend] = None,
    delete_input: bool = False,
) -> bool:
    """
    Convert an HTML file to PDF.

    Args:
        input_path: Path to the input HTML file.
        output_path: Path to write the PDF file.
        backend: Specific backend to use, or None for auto-detection.
        delete_input: If True, delete the input file after successful conversion.

    Returns:
        True if conversion succeeded, False otherwise.
    """
    input_path = Path(input_path)
    output_path = Path(output_path)

    # Check input file exists
    if not input_path.exists():
        logger.error(f"Input file not found: {input_path}")
        return False

    try:
        # Read the HTML file
        html_content = input_path.read_text(encoding="utf-8")

        # Convert to PDF
        success = convert_html_to_pdf(html_content, output_path, backend)

        # Delete input file on success if requested
        if success and delete_input:
            try:
                input_path.unlink()
                logger.info(f"Deleted input file: {input_path}")
            except OSError as e:
                logger.warning(f"Could not delete input file {input_path}: {e}")

        return success

    except Exception as e:
        logger.error(f"Failed to convert file {input_path}: {e}")
        return False
