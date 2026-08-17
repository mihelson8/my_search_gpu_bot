@echo off
setlocal
cd /d "%~dp0"
title ANPR desktop shortcut

if not exist "%~dp0START_ANPR.bat" (
    echo.
    echo This was started from the ZIP / WinRAR. That does not work.
    echo.
    echo 1. Close this window and close WinRAR.
    echo 2. In Downloads right-click the ZIP.
    echo 3. Click: Izvlech v tekuschuyu papku
    echo 4. Open the yellow FOLDER, go inside until you see anpr_gui.py
    echo 5. Double-click DESKTOP_SHORTCUT_ANPR.bat there.
    echo.
    pause
    exit /b 1
)

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0MAKE_DESKTOP_SHORTCUT.ps1"
if errorlevel 1 (
    echo Could not create desktop shortcut.
    pause
    exit /b 1
)

echo.
echo Shortcut created. Icon is the plate, not Python.
echo If the old Python icon is still there, delete it and press F5 on the Desktop.
echo.
pause
