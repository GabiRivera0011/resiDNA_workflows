@echo off
REM Double-click launcher for the resiDNA Sample Analysis Tool.
REM Creates the Python environment on first run, and automatically
REM reinstalls dependencies whenever app\requirements.txt changes (e.g.
REM after copying in an update) - not just on first run - by comparing its
REM hash against the one recorded at the last install. A normal run with no
REM dependency changes starts instantly.

setlocal enabledelayedexpansion
cd /d "%~dp0"

set "HASH_FILE=.venv\.requirements_hash"
set "NEW_HASH="
for /f "skip=1 tokens=1" %%H in ('certutil -hashfile app\requirements.txt SHA256 2^>nul') do (
    if not defined NEW_HASH set "NEW_HASH=%%H"
)

set "OLD_HASH="
if exist "%HASH_FILE%" set /p OLD_HASH=<"%HASH_FILE%"

if not exist ".venv\Scripts\python.exe" (
    echo Setting up a Python environment - this only happens once. Please wait...
    echo.
    python -m venv .venv
    if errorlevel 1 (
        echo.
        echo ERROR: Could not create a Python environment.
        echo Make sure Python 3.10 or newer is installed and on your PATH.
        pause
        exit /b 1
    )
)

if not "%NEW_HASH%"=="%OLD_HASH%" (
    echo Installing/updating dependencies - this happens on first run, and again
    echo whenever an update changes app\requirements.txt. Please wait...
    echo.
    ".venv\Scripts\pip.exe" install -r app\requirements.txt
    if errorlevel 1 (
        echo.
        echo ERROR: Could not install dependencies. Check your internet connection and try again.
        pause
        exit /b 1
    )
    >"%HASH_FILE%" echo %NEW_HASH%
    echo.
    echo Setup complete.
    echo.
)

echo Starting resiDNA Sample Analysis Tool...
echo Your browser will open automatically once it's ready.
echo Close this window to stop the app.
echo.
".venv\Scripts\streamlit.exe" run app\app.py

echo.
echo The app has stopped. Press any key to close this window.
pause >nul
