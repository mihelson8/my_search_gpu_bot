@echo off
chcp 65001 > nul
title CCTV and China Cargo Business Suite

echo ============================================================
echo   CCTV and China Cargo Business Suite
echo   Start Business Control Panel
echo ============================================================
echo.

python app_suite.py

if %errorlevel% neq 0 (
    echo.
    echo [Error] Failed to run python app_suite.py
    pause
)

