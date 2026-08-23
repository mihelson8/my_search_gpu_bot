@echo off
cd /d "%~dp0"
title Business Suite Desktop

echo Starting desktop GUI...
echo Folder: %CD%
echo.

if not exist "desktop_gui.py" (
    echo [ERROR] desktop_gui.py not found.
    pause
    exit /b 1
)

where py >nul 2>&1
if %errorlevel%==0 (
    py -3 desktop_gui.py
    if %errorlevel%==0 goto done
)

where python >nul 2>&1
if %errorlevel%==0 (
    python desktop_gui.py
    if %errorlevel%==0 goto done
)

where python3 >nul 2>&1
if %errorlevel%==0 (
    python3 desktop_gui.py
    if %errorlevel%==0 goto done
)

echo Desktop GUI failed. Trying web version...
if exist "START_APP_WINDOWS.bat" call "%~dp0START_APP_WINDOWS.bat"
goto end

:done
echo.
pause

:end
