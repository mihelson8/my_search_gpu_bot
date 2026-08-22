@echo off
cd /d "%~dp0"
title Create Desktop Shortcut

where py >nul 2>&1
if %errorlevel%==0 (
  py -3 create_desktop_shortcut.py
  exit /b %errorlevel%
)

where python >nul 2>&1
if %errorlevel%==0 (
  python create_desktop_shortcut.py
  exit /b %errorlevel%
)

echo [ERROR] Python not found
pause
exit /b 1
