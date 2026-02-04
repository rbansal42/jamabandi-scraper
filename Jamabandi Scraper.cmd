@echo off
cd /d "%~dp0"

REM Use venv if it exists, otherwise prompt to run setup
if exist "venv\Scripts\python.exe" (
    venv\Scripts\python.exe gui.py
) else (
    echo Virtual environment not found. Run setup.cmd first.
    echo.
)
pause
