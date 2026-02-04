#!/bin/bash
cd "$(dirname "$0")"

# Use venv if it exists, otherwise prompt setup
if [ -f "venv/bin/python3" ]; then
    venv/bin/python3 run.py
else
    echo "Virtual environment not found."
    echo "Please double-click 'Install Dependencies.command' first."
    echo ""
    read -p "Press Enter to exit..."
fi
