@echo off
chcp 65001 > nul
cd /d "%~dp0"
title CCTV and China Cargo Business Suite Desktop
setlocal EnableDelayedExpansion

echo ============================================================
echo   CCTV and China Cargo Business Suite (Desktop)
echo ============================================================
echo.
echo Папка: %CD%
echo.

set "PY="
where py >nul 2>&1
if %errorlevel%==0 (
    py -3 -c "import sys" >nul 2>&1
    if !errorlevel!==0 set "PY=py -3"
)
if not defined PY (
    where python >nul 2>&1
    if !errorlevel!==0 (
        python -c "import sys" >nul 2>&1
        if !errorlevel!==0 set "PY=python"
    )
)
if not defined PY (
    where python3 >nul 2>&1
    if !errorlevel!==0 (
        python3 -c "import sys" >nul 2>&1
        if !errorlevel!==0 set "PY=python3"
    )
)

if not defined PY (
    echo [ОШИБКА] Python не найден.
    echo Скачайте: https://www.python.org/downloads/
    echo Галочка "Add python.exe to PATH" обязательна.
    echo.
    pause
    exit /b 1
)

echo Найден Python: %PY%
echo.

if not exist "desktop_gui.py" (
    echo [ОШИБКА] desktop_gui.py не найден. Распакуйте весь ZIP.
    pause
    exit /b 1
)

echo Запуск окна программы...
%PY% desktop_gui.py
if %errorlevel% neq 0 (
    echo.
    echo [Fallback] Десктоп не открылся, пробуем веб-версию...
    if exist "app_suite.py" (
        %PY% app_suite.py
    ) else (
        echo app_suite.py тоже не найден.
    )
    echo.
    pause
)
