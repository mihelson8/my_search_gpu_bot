@echo off
chcp 65001 > nul
cd /d "%~dp0"
title Автономера Seetong — Свой / Чужой

echo ============================================================
echo   Распознавание автономеров с окна Seetong
echo   База Свой / Чужой
echo ============================================================
echo.

python -c "import cv2, numpy, PIL, mss" 2>nul
if %errorlevel% neq 0 (
    echo [Установка] Нужны пакеты для скриншотов и распознавания...
    python -m pip install -r requirements-anpr.txt
    echo.
)

echo Откройте программу Seetong с картинкой камеры, затем в этом окне нажмите Старт.
echo.

python anpr_gui.py

if %errorlevel% neq 0 (
    echo.
    echo [Ошибка] Не удалось запустить anpr_gui.py
    pause
)
