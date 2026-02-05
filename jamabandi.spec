# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec file for JamabandiScraper.

Build with: pyinstaller jamabandi.spec --clean
Or use: python build.py
"""

import sys
from pathlib import Path

# Determine platform
is_windows = sys.platform == 'win32'
is_macos = sys.platform == 'darwin'

# Project paths
project_root = Path(SPECPATH)
scraper_dir = project_root / 'scraper'

# Collect all scraper module files as data
scraper_datas = []
for py_file in scraper_dir.glob('*.py'):
    scraper_datas.append((str(py_file), 'scraper'))

# Data files to include
datas = [
    ('config.yaml', '.'),
    *scraper_datas,
]

# Hidden imports that PyInstaller might miss
hiddenimports = [
    # Scraper modules
    'scraper',
    'scraper.config',
    'scraper.gui',
    'scraper.logger',
    'scraper.validator',
    'scraper.session_manager',
    'scraper.http_scraper',
    'scraper.selenium_scraper',
    'scraper.pdf_converter',
    'scraper.cookie_capture',
    'scraper.rate_limiter',
    'scraper.retry_manager',
    'scraper.statistics',
    'scraper.pdf_backend',
    'scraper.update_checker',
    # Third-party dependencies
    'pdfkit',
    'bs4',
    'weasyprint',
    'pypdf',
    'packaging',
    'webdriver_manager',
    'requests',
    'yaml',
    'selenium',
    'selenium.webdriver',
    'selenium.webdriver.chrome',
    'selenium.webdriver.chrome.service',
    'selenium.webdriver.chrome.options',
    'selenium.webdriver.common.by',
    'selenium.webdriver.support.ui',
    'selenium.webdriver.support.expected_conditions',
    # Tkinter (GUI)
    'tkinter',
    'tkinter.ttk',
    'tkinter.filedialog',
    'tkinter.messagebox',
    'tkinter.scrolledtext',
    # Standard library that may be missed
    'queue',
    'threading',
    'logging',
    'json',
    'csv',
    'pathlib',
    'datetime',
    'time',
    'os',
    'sys',
]

# Platform-specific icon
if is_windows:
    icon_file = 'assets/icon.ico'
elif is_macos:
    icon_file = 'assets/icon.icns'
else:
    icon_file = None

# Check if icon exists, use None if not
if icon_file and not (project_root / icon_file).exists():
    icon_file = None

# Analysis configuration
a = Analysis(
    ['run.py'],
    pathex=[str(project_root)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Exclude unnecessary modules to reduce size
        'matplotlib',
        'numpy',
        'pandas',
        'scipy',
        'PIL',
        'cv2',
        'test',
        'tests',
        'unittest',
        'pytest',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=None,
    noarchive=False,
)

# Create the PYZ archive
pyz = PYZ(
    a.pure,
    a.zipped_data,
    cipher=None,
)

# Create the executable
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='JamabandiScraper',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,  # GUI application, no console window
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=icon_file,
)

# Collect all files
coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='JamabandiScraper',
)

# macOS: Create .app bundle
if is_macos:
    app = BUNDLE(
        coll,
        name='JamabandiScraper.app',
        icon=icon_file,
        bundle_identifier='com.jamabandi.scraper',
        info_plist={
            'CFBundleName': 'JamabandiScraper',
            'CFBundleDisplayName': 'Jamabandi Scraper',
            'CFBundleVersion': '1.0.0',
            'CFBundleShortVersionString': '1.0.0',
            'NSHighResolutionCapable': True,
            'NSRequiresAquaSystemAppearance': False,  # Support dark mode
        },
    )
