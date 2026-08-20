@echo off
chcp 65001 > nul
setlocal
cd /d "%~dp0"
title Vet Bot - veterinarnyy triazh koshek

echo ============================================================
echo   Veterinarnyy bot: triazh koshek po foto i video
echo ============================================================
echo.

if not exist "vet_bot.py" (
    echo [Error] vet_bot.py not found in this folder.
    echo Put START_VET_BOT.bat next to vet_bot.py
    pause
    exit /b 1
)

set "LAUNCH="
py -3 --version >nul 2>&1 && set "LAUNCH=py -3"
if not defined LAUNCH python --version >nul 2>&1 && set "LAUNCH=python"
if not defined LAUNCH (
    echo [Error] Python 3 not found.
    echo Install Python 3 from https://www.python.org/downloads/
    echo Enable checkbox: Add python.exe to PATH
    pause
    exit /b 1
)

echo Folder: %CD%
echo Python: %LAUNCH%
echo.

%LAUNCH% -c "import telegram, PIL, dotenv" 2>nul
if errorlevel 1 (
    echo Installing packages, please wait...
    %LAUNCH% -m pip install -r requirements.txt
    if errorlevel 1 (
        echo [Error] pip install failed
        pause
        exit /b 1
    )
)

where ffmpeg >nul 2>&1
if errorlevel 1 (
    echo [Warning] ffmpeg not found: video analysis will be disabled, photos will work.
    echo Install ffmpeg from https://www.gyan.dev/ffmpeg/builds/ and add bin folder to PATH.
    echo.
)

if not defined VET_BOT_TOKEN (
    if not exist ".env" (
        echo Token from @BotFather is required on first run.
        set /p VET_BOT_TOKEN=Paste bot token and press Enter: 
        if not defined VET_BOT_TOKEN (
            echo [Error] Token is empty.
            pause
            exit /b 1
        )
        > ".env" echo VET_BOT_TOKEN=%VET_BOT_TOKEN%
        echo Token saved to .env, next runs will start without questions.
        echo.
    )
)

echo Starting bot. Keep this window open, close it to stop the bot.
echo Auto-restart is on: if the bot crashes, it will start again in 10 seconds.
echo.

:run
%LAUNCH% vet_bot.py
set "CODE=%errorlevel%"

if "%CODE%"=="0" goto :done
if "%CODE%"=="1" goto :tokenerror

echo.
echo [Warning] Bot stopped unexpectedly (code %CODE%). Restarting in 10 seconds...
echo Press Ctrl+C now to cancel restart.
timeout /t 10 /nobreak >nul
goto :run

:tokenerror
echo.
echo [Error] Token rejected. Get a new one from @BotFather and fix .env
pause
exit /b 1

:done
echo.
echo Bot stopped.
pause
