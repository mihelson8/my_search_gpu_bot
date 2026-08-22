@echo off
setlocal
cd /d "%~dp0"
title ANPR desktop shortcut

if exist "anpr_gui.py" goto :ready
echo Looking on Desktop / Downloads / D: ...
for %%R in ("%USERPROFILE%\Desktop" "%USERPROFILE%\Downloads" "D:" "C:") do (
    for /d %%D in ("%%~R\my_search_gpu_bot*") do (
        if exist "%%D\anpr_gui.py" (
            cd /d "%%D"
            goto :ready
        )
        if exist "%%D\my_search_gpu_bot-cursor-anpr-seetong-plates-6b83\anpr_gui.py" (
            cd /d "%%D\my_search_gpu_bot-cursor-anpr-seetong-plates-6b83"
            goto :ready
        )
    )
)

echo START_ANPR.bat not found because this ran from ZIP/WinRAR.
echo Close WinRAR. Open the yellow folder.
echo Double-click START_ANPR.bat  (not this file from the archive).
pause
exit /b 1

:ready
if not exist "%CD%\START_ANPR.bat" (
    echo START_ANPR.bat missing in %CD%
    pause
    exit /b 1
)

powershell -NoProfile -ExecutionPolicy Bypass -File "%CD%\MAKE_DESKTOP_SHORTCUT.ps1"
if errorlevel 1 (
    echo Could not create desktop shortcut.
    pause
    exit /b 1
)

echo Starting program...
call "%CD%\START_ANPR.bat"
