@echo off
setlocal
cd /d "%~dp0"
title Install ANPR packages

set "LAUNCH="
py -3 --version >nul 2>&1 && set "LAUNCH=py -3"
if not defined LAUNCH python --version >nul 2>&1 && set "LAUNCH=python"
if not defined LAUNCH (
    echo Python not found. Install Python 3 and enable Add to PATH.
    pause
    exit /b 1
)

echo Installing: %LAUNCH% -m pip install -r requirements-anpr.txt
%LAUNCH% -m pip install -r requirements-anpr.txt
if errorlevel 1 (
    echo Install failed
    pause
    exit /b 1
)

echo OK. Now run: python anpr_gui.py
pause
