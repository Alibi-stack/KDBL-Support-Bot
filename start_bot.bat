@echo off
cd /d "%~dp0"

if not exist ".\venv\Scripts\python.exe" (
    echo Virtual environment not found. Creating venv...
    python -m venv venv
    if errorlevel 1 (
        echo Failed to create venv. Check that Python is installed.
        pause
        exit /b 1
    )
)

echo Installing/updating dependencies...
".\venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 (
    echo Failed to install dependencies. Check internet connection and try again.
    pause
    exit /b 1
)

echo Starting KDBL Support bot...
".\venv\Scripts\python.exe" main.py
pause
