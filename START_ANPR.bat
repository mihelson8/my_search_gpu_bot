@echo off
setlocal
cd /d "%~dp0"
title ANPR Seetong

if exist "%~dp0FIX_AND_CLEAN.ps1" (
    powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0FIX_AND_CLEAN.ps1"
    if errorlevel 1 pause
    exit /b %errorlevel%
)

if exist "anpr_gui.py" goto :ready
echo anpr_gui.py not found. Close WinRAR. Open the yellow folder.
pause
exit /b 1

:ready
set "LAUNCH="
py -3 --version >nul 2>&1 && set "LAUNCH=py -3"
if not defined LAUNCH python --version >nul 2>&1 && set "LAUNCH=python"
if not defined LAUNCH (
    echo Python not found. Install Python 3 and enable Add python.exe to PATH.
    pause
    exit /b 1
)
%LAUNCH% -c "import cv2,numpy,PIL,mss" 2>nul
if errorlevel 1 (
    echo Installing packages, please wait...
    %LAUNCH% -m pip install -r requirements-anpr.txt
    if errorlevel 1 %LAUNCH% -m pip install opencv-python Pillow mss numpy
)
if exist "%CD%\MAKE_DESKTOP_SHORTCUT.ps1" (
    powershell -NoProfile -ExecutionPolicy Bypass -File "%CD%\MAKE_DESKTOP_SHORTCUT.ps1" >nul 2>&1
)
where pythonw >nul 2>&1
if not errorlevel 1 (
    start "" /D "%CD%" pythonw.exe "%CD%\anpr_gui.py"
    exit /b 0
)
%LAUNCH% anpr_gui.py
if errorlevel 1 pause
exit /b 0
