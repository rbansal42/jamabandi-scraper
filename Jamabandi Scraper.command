#!/bin/bash
cd "$(dirname "$0")"

# Use venv if it exists, otherwise fall back to system python
if [ -f "venv/bin/python3" ]; then
    venv/bin/python3 gui.py
else
    echo "Virtual environment not found. Run setup.command first."
    echo ""
    read -p "Press Enter to exit..."
fi
