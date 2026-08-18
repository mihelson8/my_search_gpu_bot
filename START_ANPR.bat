@echo off
setlocal
cd /d "%~dp0"
title ANPR Seetong

if exist "anpr_gui.py" goto :ready

call :find_copy "%USERPROFILE%\Desktop"
if exist "anpr_gui.py" goto :ready
call :find_copy "%USERPROFILE%\Downloads"
if exist "anpr_gui.py" goto :ready
call :find_copy "D:"
if exist "anpr_gui.py" goto :ready
call :find_copy "C:"
if exist "anpr_gui.py" goto :ready

echo anpr_gui.py not found.
echo Close WinRAR. Open the yellow folder, then double-click START_ANPR.bat
echo next to anpr_gui.py
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
    if errorlevel 1 (
        %LAUNCH% -m pip install opencv-python Pillow mss numpy
    )
    %LAUNCH% -m pip install rapidocr-onnxruntime 2>nul
)

echo Updating desktop shortcut...
powershell -NoProfile -ExecutionPolicy Bypass -File "%CD%\MAKE_DESKTOP_SHORTCUT.ps1" >nul 2>&1

echo Starting ANPR window...
where pythonw >nul 2>&1
if not errorlevel 1 (
    start "" /D "%CD%" pythonw.exe "%CD%\anpr_gui.py"
    exit /b 0
)
%LAUNCH% anpr_gui.py
if errorlevel 1 (
    echo Failed to start anpr_gui.py
    pause
)
exit /b 0

:find_copy
for /d %%D in ("%~1\my_search_gpu_bot*") do (
    if exist "%%D\anpr_gui.py" (
        cd /d "%%D"
        goto :eof
    )
    for /d %%N in ("%%D\my_search_gpu_bot*") do (
        if exist "%%N\anpr_gui.py" (
            cd /d "%%N"
            goto :eof
        )
    )
)
goto :eof
