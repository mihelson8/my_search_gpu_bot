@echo off
setlocal
cd /d "%~dp0"
title ANPR desktop shortcut

if not exist "%~dp0START_ANPR.bat" (
    echo START_ANPR.bat not found.
    echo Run this file from the extracted project folder.
    pause
    exit /b 1
)

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
  "$s.Save();" ^
  "Write-Host ('OK: ' + $p)"

if errorlevel 1 (
    echo Could not create desktop shortcut.
    pause
    exit /b 1
)

echo.
echo Shortcut created on Desktop: Avtonomera Seetong
echo Double-click it to start the program.
echo.
pause
