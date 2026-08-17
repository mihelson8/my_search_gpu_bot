@echo off
setlocal
cd /d "%~dp0"
title ANPR Seetong

if not exist "anpr_gui.py" (
    echo anpr_gui.py not found in:
    echo %CD%
    echo.
    echo Open the extracted folder
    echo my_search_gpu_bot-cursor-anpr-seetong-plates-6b83
    echo and double-click START_ANPR.bat there.
    pause
    exit /b 1
)

rem Put a shortcut on the Desktop so you do not open this folder every time.
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$d=[Environment]::GetFolderPath('Desktop');" ^
  "$n=[string]([char]0x0410)+[char]0x0432+[char]0x0442+[char]0x043E+[char]0x043D+[char]0x043E+[char]0x043C+[char]0x0435+[char]0x0440+[char]0x0430;" ^
  "$p=Join-Path $d ($n + ' Seetong.lnk');" ^
  "$w=New-Object -ComObject WScript.Shell;" ^
  "$s=$w.CreateShortcut($p);" ^
  "$s.TargetPath='%~dp0START_ANPR.bat';" ^
  "$s.WorkingDirectory='%~dp0';" ^
  "$s.WindowStyle=1;" ^
  "$s.Description='ANPR Seetong';" ^
  "if (Test-Path '%~dp0anpr_icon.ico') { $s.IconLocation='%~dp0anpr_icon.ico,0' };" ^
  "$s.Save()" >nul 2>&1

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

echo Using: %LAUNCH%
%LAUNCH% -c "import cv2,numpy,PIL,mss" 2>nul
if errorlevel 1 (
    echo Installing packages, please wait...
    %LAUNCH% -m pip install -r requirements-anpr.txt
    if errorlevel 1 (
        echo pip install failed
        pause
        exit /b 1
    )
)

echo Keep Seetong open. Click Start in the app window.
echo Desktop shortcut: Avtonomera Seetong
%LAUNCH% anpr_gui.py
if errorlevel 1 (
    echo Failed to start anpr_gui.py
    pause
)
