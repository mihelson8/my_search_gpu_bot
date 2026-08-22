@echo off
chcp 65001 >nul
cd /d "%~dp0"
if not exist "venv\Scripts\activate.bat" (
  echo Создайте venv и установите зависимости: python -m venv venv ^& venv\Scripts\pip install -r requirements.txt
  pause
  exit /b 1
)
call venv\Scripts\activate.bat
if "%MAX_BOT_TOKEN%"=="" (
  echo Задайте переменную MAX_BOT_TOKEN перед запуском.
  echo Документация: https://dev.max.ru/docs/chatbots/bots-coding/prepare
  pause
  exit /b 1
)
set MAX_MODE=polling
python max_bot.py
pause
