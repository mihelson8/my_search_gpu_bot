@echo off
cd /d "%~dp0"
title Business Suite

echo ============================================================
echo   CCTV Business Suite
echo   http://localhost:8765
echo ============================================================
echo.
echo Folder: %CD%
echo.

if not exist "app_suite.py" (
    echo [ERROR] app_suite.py not found in this folder.
    pause
    exit /b 1
)

REM Prefer run_business.py wrapper when present
set "SCRIPT=app_suite.py"
if exist "run_business.py" set "SCRIPT=run_business.py"

where py >nul 2>&1
if %errorlevel%==0 (
    echo Using: py -3
    py -3 "%SCRIPT%"
    if %errorlevel%==0 goto ok
)

where python >nul 2>&1
if %errorlevel%==0 (
    echo Using: python
    python "%SCRIPT%"
    if %errorlevel%==0 goto ok
)

where python3 >nul 2>&1
if %errorlevel%==0 (
    echo Using: python3
    python3 "%SCRIPT%"
    if %errorlevel%==0 goto ok
)

echo.
echo [ERROR] Python not found.
echo Install Python 3 from https://www.python.org/downloads/
echo Enable checkbox: Add python.exe to PATH
echo Then reboot and run this file again.
echo.
pause
exit /b 1

:ok
echo.
pause
exit /b 0
