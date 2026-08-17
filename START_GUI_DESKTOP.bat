@echo off
chcp 65001 > nul
cd /d "%~dp0"
title CCTV and China Cargo Business Suite Desktop

echo ============================================================
echo   CCTV and China Cargo Business Suite (Desktop)
echo ============================================================
echo.

python desktop_gui.py

if %errorlevel% neq 0 (
    echo [Fallback] Starting web version...
    python app_suite.py
)


