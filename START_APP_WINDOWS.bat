@echo off
chcp 65001 > nul
title CCTV ^& China Cargo Business Suite

echo ============================================================
echo   🚀 CCTV ^& China Cargo Business Suite
echo   Пульт управления базой клиентов, офферами и планом 7 дней
echo ============================================================
echo.

REM Проверка наличия Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ОШИБКА] Python не найден на вашем компьютере.
    echo Пожалуйста, установите Python с официального сайта: https://www.python.org/
    echo Обязательно поставьте галочку "Add Python to PATH" при установке!
    pause
    exit /b
)

echo Запуск локального сервера программы...
echo Открываем браузер на странице программы...
echo.

python app_suite.py

pause
