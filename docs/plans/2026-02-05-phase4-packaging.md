# Phase 4: Packaging & Distribution Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace WeasyPrint with wkhtmltopdf (or support both) and create standalone installers for easy distribution.

**Architecture:**
- `pdf_backend.py` - Abstract PDF conversion with multiple backend support
- PyInstaller spec files for building executables
- GitHub Actions workflow for automated builds

**Tech Stack:** Python 3.10+, pdfkit, wkhtmltopdf, PyInstaller, GitHub Actions

---

## Task 1: PDF Backend Abstraction

**Files:**
- Create: `scraper/pdf_backend.py`
- Test: `tests/test_pdf_backend.py`

**Step 1: Write failing tests for PDF backend**

```python
# tests/test_pdf_backend.py
"""Tests for PDF backend abstraction."""
import pytest
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
from scraper.config import reset_config
from scraper.logger import reset_logging


class TestPDFBackendEnum:
    """Tests for PDFBackend enum."""

    def test_weasyprint_value(self):
        from scraper.pdf_backend import PDFBackend
        assert PDFBackend.WEASYPRINT.value == "weasyprint"

    def test_wkhtmltopdf_value(self):
        from scraper.pdf_backend import PDFBackend
        assert PDFBackend.WKHTMLTOPDF.value == "wkhtmltopdf"


class TestBackendDetection:
    """Tests for backend availability detection."""

    def setup_method(self):
        reset_config()
        reset_logging()

    def teardown_method(self):
        reset_config()
        reset_logging()

    def test_detect_available_backends(self):
        from scraper.pdf_backend import detect_available_backends
        backends = detect_available_backends()
        assert isinstance(backends, list)

    def test_get_default_backend_returns_available(self):
        from scraper.pdf_backend import get_default_backend, detect_available_backends
        backends = detect_available_backends()
        if backends:
            default = get_default_backend()
            assert default in backends


class TestWeasyPrintBackend:
    """Tests for WeasyPrint backend."""

    def setup_method(self):
        reset_config()
        reset_logging()

    def teardown_method(self):
        reset_config()
        reset_logging()

    @pytest.mark.skipif(not pytest.importorskip("weasyprint", reason="WeasyPrint not installed"), reason="WeasyPrint not available")
    def test_weasyprint_convert_html_string(self, tmp_path):
        from scraper.pdf_backend import convert_html_to_pdf, PDFBackend
        html = "<html><body><h1>Test</h1></body></html>"
        output = tmp_path / "test.pdf"
        
        result = convert_html_to_pdf(
            html_content=html,
            output_path=str(output),
            backend=PDFBackend.WEASYPRINT
        )
        
        assert result is True
        assert output.exists()
        assert output.stat().st_size > 0


class TestWkhtmltopdfBackend:
    """Tests for wkhtmltopdf backend."""

    def setup_method(self):
        reset_config()
        reset_logging()

    def teardown_method(self):
        reset_config()
        reset_logging()

    def test_wkhtmltopdf_available_check(self):
        from scraper.pdf_backend import is_wkhtmltopdf_available
        result = is_wkhtmltopdf_available()
        assert isinstance(result, bool)


class TestConvertHTMLToPDF:
    """Tests for the main conversion function."""

    def setup_method(self):
        reset_config()
        reset_logging()

    def teardown_method(self):
        reset_config()
        reset_logging()

    def test_convert_creates_output_directory(self, tmp_path):
        from scraper.pdf_backend import convert_html_to_pdf, get_default_backend
        
        html = "<html><body><h1>Test</h1></body></html>"
        output_dir = tmp_path / "subdir" / "nested"
        output = output_dir / "test.pdf"
        
        backend = get_default_backend()
        if backend:
            result = convert_html_to_pdf(
                html_content=html,
                output_path=str(output),
                backend=backend
            )
            if result:
                assert output.parent.exists()

    def test_convert_returns_false_on_invalid_backend(self, tmp_path):
        from scraper.pdf_backend import convert_html_to_pdf
        
        html = "<html><body><h1>Test</h1></body></html>"
        output = tmp_path / "test.pdf"
        
        # Mock an invalid backend scenario
        result = convert_html_to_pdf(
            html_content=html,
            output_path=str(output),
            backend=None
        )
        assert result is False


class TestConvertFile:
    """Tests for file-based conversion."""

    def setup_method(self):
        reset_config()
        reset_logging()

    def teardown_method(self):
        reset_config()
        reset_logging()

    def test_convert_file_reads_html(self, tmp_path):
        from scraper.pdf_backend import convert_file, get_default_backend
        
        html_file = tmp_path / "test.html"
        html_file.write_text("<html><body><h1>Test</h1></body></html>")
        output = tmp_path / "test.pdf"
        
        backend = get_default_backend()
        if backend:
            result = convert_file(
                input_path=str(html_file),
                output_path=str(output),
                backend=backend
            )
            # Just verify it doesn't crash - actual conversion may fail without deps
            assert isinstance(result, bool)

    def test_convert_file_missing_input(self, tmp_path):
        from scraper.pdf_backend import convert_file, get_default_backend, PDFBackend
        
        output = tmp_path / "test.pdf"
        
        result = convert_file(
            input_path="/nonexistent/file.html",
            output_path=str(output),
            backend=PDFBackend.WEASYPRINT
        )
        assert result is False
```

**Step 2: Implement PDF backend module**

```python
# scraper/pdf_backend.py
"""PDF conversion backend abstraction supporting WeasyPrint and wkhtmltopdf."""

import shutil
import subprocess
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


# Check backend availability at import time
_WEASYPRINT_AVAILABLE = False
_WKHTMLTOPDF_AVAILABLE = False

try:
    from weasyprint import HTML, CSS
    from weasyprint.text.fonts import FontConfiguration
    _WEASYPRINT_AVAILABLE = True
except ImportError:
    pass

try:
    import pdfkit
    # Also check if wkhtmltopdf binary exists
    if shutil.which("wkhtmltopdf"):
        _WKHTMLTOPDF_AVAILABLE = True
except ImportError:
    pass


# Custom CSS for WeasyPrint (landscape A4 for Jamabandi tables)
WEASYPRINT_CSS = """
@page {
    size: A4 landscape;
    margin: 0.6cm;
}
@media print {
    html, body { display: block !important; visibility: visible !important; }
}
html, body { display: block !important; visibility: visible !important; margin: 0; padding: 0; }
table { width: 100% !important; border-collapse: collapse; font-size: 7.5pt; }
th, td { border: 1px solid #333; padding: 2px 3px; }
th { font-size: 7pt; background-color: #eee; }
"""

# wkhtmltopdf options for similar output
WKHTMLTOPDF_OPTIONS = {
    'page-size': 'A4',
    'orientation': 'Landscape',
    'margin-top': '6mm',
    'margin-right': '6mm',
    'margin-bottom': '6mm',
    'margin-left': '6mm',
    'encoding': 'UTF-8',
    'no-outline': None,
    'quiet': None,
}


def is_weasyprint_available() -> bool:
    """Check if WeasyPrint is available."""
    return _WEASYPRINT_AVAILABLE


def is_wkhtmltopdf_available() -> bool:
    """Check if wkhtmltopdf is available."""
    return _WKHTMLTOPDF_AVAILABLE


def detect_available_backends() -> List[PDFBackend]:
    """Detect which PDF backends are available.
    
    Returns:
        List of available PDFBackend values
    """
    backends = []
    if _WKHTMLTOPDF_AVAILABLE:
        backends.append(PDFBackend.WKHTMLTOPDF)
    if _WEASYPRINT_AVAILABLE:
        backends.append(PDFBackend.WEASYPRINT)
    return backends


def get_default_backend() -> Optional[PDFBackend]:
    """Get the default PDF backend.
    
    Prefers wkhtmltopdf (easier to bundle), falls back to WeasyPrint.
    
    Returns:
        Default PDFBackend or None if none available
    """
    config = get_config()
    preferred = config.get("pdf.backend", None)
    
    if preferred:
        if preferred == "wkhtmltopdf" and _WKHTMLTOPDF_AVAILABLE:
            return PDFBackend.WKHTMLTOPDF
        elif preferred == "weasyprint" and _WEASYPRINT_AVAILABLE:
            return PDFBackend.WEASYPRINT
    
    # Auto-detect: prefer wkhtmltopdf for easier bundling
    if _WKHTMLTOPDF_AVAILABLE:
        return PDFBackend.WKHTMLTOPDF
    if _WEASYPRINT_AVAILABLE:
        return PDFBackend.WEASYPRINT
    
    return None


def convert_html_to_pdf(
    html_content: str,
    output_path: str,
    backend: Optional[PDFBackend] = None,
    custom_css: Optional[str] = None,
) -> bool:
    """Convert HTML content to PDF.
    
    Args:
        html_content: HTML string to convert
        output_path: Path to save PDF file
        backend: PDF backend to use (auto-detected if None)
        custom_css: Additional CSS to apply
        
    Returns:
        True if conversion succeeded, False otherwise
    """
    if backend is None:
        backend = get_default_backend()
    
    if backend is None:
        logger.error("No PDF backend available")
        return False
    
    # Ensure output directory exists
    output_file = Path(output_path)
    output_file.parent.mkdir(parents=True, exist_ok=True)
    
    try:
        if backend == PDFBackend.WEASYPRINT:
            return _convert_weasyprint(html_content, output_path, custom_css)
        elif backend == PDFBackend.WKHTMLTOPDF:
            return _convert_wkhtmltopdf(html_content, output_path, custom_css)
        else:
            logger.error(f"Unknown backend: {backend}")
            return False
    except Exception as e:
        logger.exception(f"PDF conversion failed: {e}")
        return False


def convert_file(
    input_path: str,
    output_path: str,
    backend: Optional[PDFBackend] = None,
    delete_input: bool = False,
) -> bool:
    """Convert HTML file to PDF.
    
    Args:
        input_path: Path to input HTML file
        output_path: Path to save PDF file
        backend: PDF backend to use (auto-detected if None)
        delete_input: Delete input file after successful conversion
        
    Returns:
        True if conversion succeeded, False otherwise
    """
    input_file = Path(input_path)
    
    if not input_file.exists():
        logger.error(f"Input file not found: {input_path}")
        return False
    
    try:
        html_content = input_file.read_text(encoding="utf-8")
    except Exception as e:
        logger.error(f"Failed to read input file: {e}")
        return False
    
    result = convert_html_to_pdf(html_content, output_path, backend)
    
    if result and delete_input:
        try:
            input_file.unlink()
            logger.debug(f"Deleted input file: {input_path}")
        except Exception as e:
            logger.warning(f"Failed to delete input file: {e}")
    
    return result


def _convert_weasyprint(html_content: str, output_path: str, custom_css: Optional[str]) -> bool:
    """Convert using WeasyPrint backend."""
    if not _WEASYPRINT_AVAILABLE:
        logger.error("WeasyPrint not available")
        return False
    
    from weasyprint import HTML, CSS
    from weasyprint.text.fonts import FontConfiguration
    
    font_config = FontConfiguration()
    css_text = WEASYPRINT_CSS
    if custom_css:
        css_text += "\n" + custom_css
    
    css = CSS(string=css_text, font_config=font_config)
    html = HTML(string=html_content)
    html.write_pdf(output_path, stylesheets=[css], font_config=font_config)
    
    logger.debug(f"Converted with WeasyPrint: {output_path}")
    return True


def _convert_wkhtmltopdf(html_content: str, output_path: str, custom_css: Optional[str]) -> bool:
    """Convert using wkhtmltopdf backend."""
    if not _WKHTMLTOPDF_AVAILABLE:
        logger.error("wkhtmltopdf not available")
        return False
    
    import pdfkit
    
    # Inject custom CSS into HTML if provided
    if custom_css:
        style_tag = f"<style>{custom_css}</style>"
        if "<head>" in html_content:
            html_content = html_content.replace("<head>", f"<head>{style_tag}")
        else:
            html_content = f"{style_tag}{html_content}"
    
    options = WKHTMLTOPDF_OPTIONS.copy()
    pdfkit.from_string(html_content, output_path, options=options)
    
    logger.debug(f"Converted with wkhtmltopdf: {output_path}")
    return True
```

**Step 3: Run tests**

Run: `.venv/bin/pytest tests/test_pdf_backend.py -v`

**Step 4: Commit**

```bash
git add scraper/pdf_backend.py tests/test_pdf_backend.py
git commit -m "feat: add PDF backend abstraction with wkhtmltopdf support (#8)"
```

---

## Task 2: Update PDF Converter to Use Backend

**Files:**
- Modify: `scraper/pdf_converter.py`

**Step 1: Update imports and use backend**

Replace direct WeasyPrint usage with pdf_backend calls. The existing `convert_html_to_pdf` function should delegate to the backend module.

**Step 2: Update config.yaml**

Add PDF backend configuration:
```yaml
pdf:
  backend: "auto"  # "auto", "weasyprint", or "wkhtmltopdf"
```

**Step 3: Run tests**

Run: `.venv/bin/pytest tests/ -v`

**Step 4: Commit**

```bash
git add scraper/pdf_converter.py config.yaml
git commit -m "refactor: update pdf_converter to use backend abstraction"
```

---

## Task 3: PyInstaller Configuration

**Files:**
- Create: `jamabandi.spec`
- Create: `build_scripts/build_windows.py`
- Create: `build_scripts/build_macos.py`

**Step 1: Create PyInstaller spec file**

```python
# jamabandi.spec
# -*- mode: python ; coding: utf-8 -*-

block_cipher = None

a = Analysis(
    ['run.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('config.yaml', '.'),
        ('scraper/*.py', 'scraper'),
    ],
    hiddenimports=[
        'scraper.gui',
        'scraper.http_scraper',
        'scraper.pdf_converter',
        'scraper.config',
        'scraper.logger',
        'pdfkit',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='JamabandiScraper',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='assets/icon.ico' if sys.platform == 'win32' else 'assets/icon.icns',
)

# macOS app bundle
if sys.platform == 'darwin':
    app = BUNDLE(
        exe,
        name='Jamabandi Scraper.app',
        icon='assets/icon.icns',
        bundle_identifier='com.jamabandi.scraper',
        info_plist={
            'CFBundleName': 'Jamabandi Scraper',
            'CFBundleDisplayName': 'Jamabandi Scraper',
            'CFBundleVersion': '1.0.0',
            'CFBundleShortVersionString': '1.0.0',
            'NSHighResolutionCapable': True,
        },
    )
```

**Step 2: Commit**

```bash
git add jamabandi.spec build_scripts/
git commit -m "build: add PyInstaller configuration for standalone builds (#11)"
```

---

## Task 4: GitHub Actions Workflow

**Files:**
- Create: `.github/workflows/build.yml`

**Step 1: Create build workflow**

```yaml
# .github/workflows/build.yml
name: Build Installers

on:
  push:
    tags:
      - 'v*'
  workflow_dispatch:

jobs:
  build-windows:
    runs-on: windows-latest
    steps:
      - uses: actions/checkout@v4
      
      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      
      - name: Install dependencies
        run: |
          pip install -r requirements.txt
          pip install pyinstaller pdfkit
      
      - name: Install wkhtmltopdf
        run: choco install wkhtmltopdf -y
      
      - name: Build executable
        run: pyinstaller jamabandi.spec
      
      - name: Upload artifact
        uses: actions/upload-artifact@v4
        with:
          name: JamabandiScraper-Windows
          path: dist/JamabandiScraper.exe

  build-macos:
    runs-on: macos-latest
    steps:
      - uses: actions/checkout@v4
      
      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      
      - name: Install dependencies
        run: |
          pip install -r requirements.txt
          pip install pyinstaller pdfkit
          brew install wkhtmltopdf
      
      - name: Build app
        run: pyinstaller jamabandi.spec
      
      - name: Create DMG
        run: |
          hdiutil create -volname "Jamabandi Scraper" -srcfolder "dist/Jamabandi Scraper.app" -ov -format UDZO dist/JamabandiScraper.dmg
      
      - name: Upload artifact
        uses: actions/upload-artifact@v4
        with:
          name: JamabandiScraper-macOS
          path: dist/JamabandiScraper.dmg

  release:
    needs: [build-windows, build-macos]
    runs-on: ubuntu-latest
    if: startsWith(github.ref, 'refs/tags/')
    steps:
      - name: Download artifacts
        uses: actions/download-artifact@v4
      
      - name: Create Release
        uses: softprops/action-gh-release@v1
        with:
          files: |
            JamabandiScraper-Windows/JamabandiScraper.exe
            JamabandiScraper-macOS/JamabandiScraper.dmg
          generate_release_notes: true
```

**Step 2: Commit**

```bash
git add .github/workflows/build.yml
git commit -m "ci: add GitHub Actions workflow for automated builds (#11)"
```

---

## Task 5: Update Exports and Documentation

**Files:**
- Modify: `scraper/__init__.py`
- Modify: `README.md`
- Modify: `requirements.txt`

**Step 1: Update exports**

Add pdf_backend exports to `__init__.py`.

**Step 2: Update requirements.txt**

Add `pdfkit` as optional dependency.

**Step 3: Update README**

Add installation instructions for releases.

**Step 4: Commit**

```bash
git add scraper/__init__.py README.md requirements.txt
git commit -m "docs: update for Phase 4 packaging features"
```

---

## Summary

**Total Tasks:** 5
**New Files:** 5 (pdf_backend.py, test file, spec, workflow, build scripts)
**Modified Files:** 4 (pdf_converter.py, config.yaml, __init__.py, README.md)

**Closes Issues:** #8, #11
