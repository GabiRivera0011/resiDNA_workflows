@echo off
REM Double-click launcher for the resiDNA Sample Analysis Tool.
REM First run: creates a local Python environment and installs dependencies
REM (one-time, a minute or two). Every run after that starts instantly.

setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\streamlit.exe" (
    echo First-time setup - creating a Python environment and installing dependencies.
    echo This only happens once. Please wait...
    echo.
    python -m venv .venv
    if errorlevel 1 (
        echo.
        echo ERROR: Could not create a Python environment.
        echo Make sure Python 3.10 or newer is installed and on your PATH.
        pause
        exit /b 1
    )
    ".venv\Scripts\pip.exe" install -r app\requirements.txt
    if errorlevel 1 (
        echo.
        echo ERROR: Could not install dependencies. Check your internet connection and try again.
        pause
        exit /b 1
    )
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
