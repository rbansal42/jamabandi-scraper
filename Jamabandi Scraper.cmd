@echo off
cd /d "%~dp0"

REM Use venv if it exists, otherwise prompt setup
if exist "venv\Scripts\python.exe" (
    venv\Scripts\python.exe run.py
) else (
    echo Virtual environment not found.
    echo Please double-click "Install Dependencies.cmd" first.
    echo.
)
pause
