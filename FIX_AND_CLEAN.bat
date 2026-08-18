@echo off
setlocal
cd /d "%~dp0"
title Fix ANPR and remove extra copies
if not exist "%~dp0FIX_AND_CLEAN.ps1" (
    echo FIX_AND_CLEAN.ps1 not found. Close WinRAR and open the yellow folder.
    pause
    exit /b 1
)
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0FIX_AND_CLEAN.ps1"
exit /b %errorlevel%
