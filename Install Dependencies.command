#!/bin/bash
# ============================================================
# Jamabandi Scraper - macOS Setup
# ============================================================
cd "$(dirname "$0")"

echo "============================================"
echo "  Jamabandi Scraper - Installing Dependencies"
echo "============================================"
echo ""

# Check Python
if ! command -v python3 &> /dev/null; then
    echo "ERROR: Python 3 is not installed."
    echo "Install it from https://www.python.org/downloads/ or via Homebrew:"
    echo "  brew install python"
    echo ""
    read -p "Press Enter to exit..."
    exit 1
fi

PYTHON_VER=$(python3 --version)
echo "Found: $PYTHON_VER"

# Check for tkinter
echo ""
echo "Checking tkinter..."
if python3 -c "import tkinter" 2>/dev/null; then
    echo "  tkinter: OK"
else
    echo "  tkinter: NOT FOUND"
    echo "  Attempting to install via Homebrew..."
    if command -v brew &> /dev/null; then
        PY_MINOR=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
        brew install "python-tk@$PY_MINOR"
    else
        echo "  Homebrew not found. Install tkinter manually:"
        echo "    brew install python-tk"
    fi
fi

# Create virtual environment
echo ""
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
else
    echo "Virtual environment already exists."
fi

# Activate and install
echo ""
echo "Installing Python packages..."
source venv/bin/activate
pip install --upgrade pip -q
pip install -r requirements.txt

echo ""
echo "============================================"
echo "  Setup complete!"
echo "============================================"
echo ""
echo "To launch the app, double-click:"
echo "  Jamabandi Scraper.command"
echo ""
read -p "Press Enter to exit..."
