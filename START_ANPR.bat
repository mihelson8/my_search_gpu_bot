@echo off
setlocal
cd /d "%~dp0"
title ANPR Seetong

if exist "anpr_gui.py" goto :ready
echo Looking on Desktop...
for /d %%D in ("%USERPROFILE%\Desktop\my_search_gpu_bot-cursor-anpr-seetong-plates-6b83*") do (
    if exist "%%D\anpr_gui.py" (
        cd /d "%%D"
        goto :ready
    )
    if exist "%%D\my_search_gpu_bot-cursor-anpr-seetong-plates-6b83\anpr_gui.py" (
        cd /d "%%D\my_search_gpu_bot-cursor-anpr-seetong-plates-6b83"
        goto :ready
    )
)
for /d %%D in ("%USERPROFILE%\Downloads\my_search_gpu_bot-cursor-anpr-seetong-plates-6b83*") do (
    if exist "%%D\anpr_gui.py" (
        cd /d "%%D"
        goto :ready
    )
    if exist "%%D\my_search_gpu_bot-cursor-anpr-seetong-plates-6b83\anpr_gui.py" (
        cd /d "%%D\my_search_gpu_bot-cursor-anpr-seetong-plates-6b83"
        goto :ready
    )
)

echo anpr_gui.py not found.
echo Close WinRAR. Open the yellow folder on Desktop.
echo Then double-click START_ANPR.bat next to anpr_gui.py
pause
exit /b 1

:ready
set "LAUNCH="
py -3 --version >nul 2>&1 && set "LAUNCH=py -3"
if not defined LAUNCH python --version >nul 2>&1 && set "LAUNCH=python"
if not defined LAUNCH (
    echo Python not found.
    echo Install Python 3 from https://www.python.org/downloads/
    echo Enable: Add python.exe to PATH
    pause
    exit /b 1
)

echo Folder: %CD%
echo Using: %LAUNCH%
%LAUNCH% -c "import cv2,numpy,PIL,mss" 2>nul
if errorlevel 1 (
    echo Installing packages, please wait...
    %LAUNCH% -m pip install -r requirements-anpr.txt
    %LAUNCH% -m pip install rapidocr-onnxruntime 2>nul
    if errorlevel 1 (
        %LAUNCH% -m pip install opencv-python Pillow mss numpy
    )
)

echo Starting ANPR window...
%LAUNCH% anpr_gui.py
if errorlevel 1 (
    echo Failed to start anpr_gui.py
    pause
)
