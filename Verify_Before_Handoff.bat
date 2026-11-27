@echo off
REM Run this before copying files to a handoff USB drive. Confirms the
REM current state of this folder passes its full test suite.
REM
REM This is the one safety check standing between "I changed some files"
REM and "IT received a working app" -- there is no CI here, and company
REM policy doesn't allow this folder to update itself over the network, so
REM this script has to be run by hand, every time, before packaging.

setlocal enabledelayedexpansion
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo Setting up a Python environment - this only happens once. Please wait...
    python -m venv .venv
    if errorlevel 1 (
        echo.
        echo ERROR: Could not create a Python environment.
        echo Make sure Python 3.10 or newer is installed and on your PATH.
        pause
        exit /b 1
    )
)

echo Installing/checking dependencies...
".venv\Scripts\pip.exe" install -q -r app\requirements.txt -r tests\requirements.txt
if errorlevel 1 (
    echo.
    echo ERROR: Could not install dependencies. Check your internet connection and try again.
    pause
    exit /b 1
)

echo.
echo Running the full test suite...
echo ================================================================
".venv\Scripts\python.exe" -m pytest tests -v > "%TEMP%\resiDNA_test_output.txt" 2>&1
set TEST_EXIT=%ERRORLEVEL%
type "%TEMP%\resiDNA_test_output.txt"
echo ================================================================
echo.

findstr /C:"skipped" "%TEMP%\resiDNA_test_output.txt" >nul
if %errorlevel%==0 (
    echo NOTE: Some tests were SKIPPED above, not run. This is expected here --
    echo the real company data files ^(Data\*.xls / .xlsx^) are never included
    echo in a handoff folder, so the tests that need them cannot execute.
    echo A skip does NOT mean that check passed. It means it did not run at
    echo all in this environment. This is normal and not a reason to stop.
    echo.
)

if %TEST_EXIT%==0 (
    echo RESULT: ALL TESTS PASSED. Safe to proceed with the handoff.
) else (
    echo RESULT: TESTS FAILED. DO NOT hand off this folder yet.
    echo Fix the failure^(s^) shown above and run this script again before packaging.
)

del "%TEMP%\resiDNA_test_output.txt" >nul 2>&1
echo.
echo Press any key to close this window.
pause >nul
