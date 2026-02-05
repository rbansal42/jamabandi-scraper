#!/usr/bin/env python3
"""Build script for creating standalone executables."""

import subprocess
import sys


def main():
    """Run PyInstaller with the spec file."""
    cmd = [sys.executable, "-m", "PyInstaller", "jamabandi.spec", "--clean"]
    subprocess.run(cmd, check=True)


if __name__ == "__main__":
    main()
