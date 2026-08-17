@echo off
setlocal
cd /d "%~dp0"
title ANPR desktop shortcut

if not exist "%~dp0START_ANPR.bat" (
    echo START_ANPR.bat not found.
    echo Run this file from the extracted project folder.
    pause
    exit /b 1
)

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0MAKE_DESKTOP_SHORTCUT.ps1"
if errorlevel 1 (
    echo Could not create desktop shortcut.
    pause
    exit /b 1
)

echo.
echo Shortcut created. Icon is the plate, not Python.
echo If the old Python icon is still there, delete it and press F5 on the Desktop.
echo.
pause
