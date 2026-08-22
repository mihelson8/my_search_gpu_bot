@echo off
chcp 65001 > nul
cd /d "%~dp0"
title CCTV and China Cargo Business Suite
setlocal EnableDelayedExpansion

echo ============================================================
echo   CCTV and China Cargo Business Suite
echo   Пульт управления бизнесом / видеонаблюдение
echo ============================================================
echo.
echo Папка: %CD%
echo.

REM --- Find Python (Windows: py launcher, python, python3) ---
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
    echo [ОШИБКА] Python не найден на этом компьютере.
    echo.
    echo Что сделать:
    echo   1. Скачайте Python: https://www.python.org/downloads/
    echo   2. При установке ОБЯЗАТЕЛЬНО поставьте галочку
    echo      "Add python.exe to PATH"
    echo   3. Закройте это окно и снова запустите START_APP_WINDOWS.bat
    echo.
    echo Если Python уже установлен — перезагрузите ПК после установки.
    echo.
    pause
    exit /b 1
)

echo Найден Python: %PY%
%PY% -c "import sys; print('Версия:', sys.version)"
echo.

if not exist "app_suite.py" (
    echo [ОШИБКА] Файл app_suite.py не найден в этой папке.
    echo Распакуйте весь ZIP целиком, не только ярлык.
    echo.
    pause
    exit /b 1
)

if not exist "business_suite_db.py" (
    echo [ОШИБКА] Файл business_suite_db.py не найден.
    echo Скачайте проект заново с GitHub (весь ZIP).
    echo.
    pause
    exit /b 1
)

echo Запуск пульта...
echo После старта откройте браузер: http://localhost:8765
echo Чтобы остановить программу — закройте это окно.
echo.
echo ============================================================
echo.

%PY% app_suite.py
set "ERR=%errorlevel%"

echo.
if not "%ERR%"=="0" (
    echo [ОШИБКА] Программа завершилась с кодом %ERR%.
    echo Частые причины:
    echo   - порт 8765 занят другим приложением
    echo   - антивирус блокирует Python
    echo   - повреждённые файлы после копирования
    echo.
)
pause
exit /b %ERR%
