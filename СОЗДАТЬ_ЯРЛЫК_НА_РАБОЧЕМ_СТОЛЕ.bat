@echo off
setlocal
cd /d "%~dp0"
title Desktop shortcut

if exist "%~dp0DESKTOP_SHORTCUT_ANPR.bat" (
    call "%~dp0DESKTOP_SHORTCUT_ANPR.bat"
    exit /b %errorlevel%
)

echo DESKTOP_SHORTCUT_ANPR.bat not found.
echo In this folder run: python anpr_gui.py
pause
