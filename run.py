#!/usr/bin/env python3
"""Launch the Jamabandi Scraper GUI."""

import multiprocessing

from scraper.gui import main

if __name__ == "__main__":
    # Required for multiprocessing to work correctly in frozen PyInstaller apps
    multiprocessing.freeze_support()
    main()
