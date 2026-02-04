@echo off
REM ============================================================
REM Jamabandi Scraper - Windows Setup
REM ============================================================
cd /d "%~dp0"

echo ============================================
echo   Jamabandi Scraper - Installing Dependencies
echo ============================================
echo.

REM Check Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    python3 --version >nul 2>&1
    if %errorlevel% neq 0 (
        echo ERROR: Python 3 is not installed.
        echo Download it from https://www.python.org/downloads/
        echo Make sure to check "Add Python to PATH" during install.
        echo.
        pause
        exit /b 1
    )
    set PYTHON=python3
) else (
    set PYTHON=python
)

for /f "tokens=*" %%i in ('%PYTHON% --version') do echo Found: %%i

REM Create virtual environment
echo.
if not exist "venv" (
    echo Creating virtual environment...
    %PYTHON% -m venv venv
) else (
    echo Virtual environment already exists.
)

REM Activate and install
echo.
echo Installing Python packages...
call venv\Scripts\activate.bat
pip install --upgrade pip -q
pip install -r requirements.txt

echo.
echo ============================================
echo   Setup complete!
echo ============================================
echo.
echo To launch the app, double-click:
echo   Jamabandi Scraper.cmd
echo.
pause
