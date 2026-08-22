@echo off
chcp 65001 > nul
cd /d "%~dp0"
title Бизнес Видеонаблюдение

echo.
echo   Запуск программы...
echo   Папка: %CD%
echo.

if not exist "run_business.py" (
    echo [ОШИБКА] Нет файла run_business.py в этой папке.
    pause
    exit /b 1
)
if not exist "app_suite.py" (
    echo [ОШИБКА] Нет файла app_suite.py в этой папке.
    pause
    exit /b 1
)

py -3 run_business.py
if %errorlevel%==0 goto done

python run_business.py
if %errorlevel%==0 goto done

python3 run_business.py
if %errorlevel%==0 goto done

echo.
echo [ОШИБКА] Python не найден.
echo Установите Python с https://www.python.org/downloads/
echo Галочка Add python.exe to PATH обязательна.
echo Затем перезагрузите компьютер.
echo.
pause
exit /b 1

:done
echo.
pause
