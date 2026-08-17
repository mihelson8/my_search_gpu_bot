@echo off
chcp 65001 > nul
title CCTV ^& China Cargo Business Suite (Native Desktop)

echo ============================================================
echo   🚀 Запуск автономного приложения для Windows (GUI)
echo ============================================================
echo.

python desktop_gui.py

if %errorlevel% neq 0 (
    echo При возникновении ошибки запускается веб-версия в браузере:
    python app_suite.py
)
