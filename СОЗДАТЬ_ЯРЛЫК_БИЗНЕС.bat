@echo off
chcp 65001 > nul
cd /d "%~dp0"
title Ярлык: Бизнес Видеонаблюдение

set "BAT=%~dp0START_APP_WINDOWS.bat"
if not exist "%BAT%" (
    echo Не найден START_APP_WINDOWS.bat
    pause
    exit /b 1
)

set "ICO=%~dp0app_icon.ico"
set "DESKTOP=%USERPROFILE%\Desktop"
if not exist "%DESKTOP%" set "DESKTOP=%USERPROFILE%\Рабочий стол"

set "LNK=%DESKTOP%\Бизнес Видеонаблюдение.lnk"

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$w = New-Object -ComObject WScript.Shell; $s = $w.CreateShortcut('%LNK%'); $s.TargetPath = '%BAT%'; $s.WorkingDirectory = '%~dp0'; $s.WindowStyle = 1; $s.Description = 'CCTV Business Suite'; if (Test-Path '%ICO%') { $s.IconLocation = '%ICO%,0' }; $s.Save(); Write-Host 'OK:' $s.FullName"

if %errorlevel% neq 0 (
    echo Не удалось создать ярлык.
    pause
    exit /b 1
)

echo.
echo Ярлык создан на рабочем столе: Бизнес Видеонаблюдение
echo.
pause
