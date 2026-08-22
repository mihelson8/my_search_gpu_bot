@echo off
chcp 65001 >nul
setlocal
title Проверка установки Автономера
echo.
echo === Проверка: какая сборка реально стоит ===
echo.

set "STABLE=D:\AvtonomeraSeetong"
if not exist "%STABLE%\anpr_gui.py" set "STABLE=%USERPROFILE%\AvtonomeraSeetong"

echo Папка программы: %STABLE%
echo.

if not exist "%STABLE%\anpr\version.py" (
  echo [ОШИБКА] Файл версии не найден.
  echo Значит UPDATE_NOW.bat ещё не ставил программу в эту папку.
  echo.
  pause
  exit /b 1
)

echo --- Содержимое anpr\version.py ---
findstr /C:"APP_VERSION" "%STABLE%\anpr\version.py"
echo.

findstr /C:"2026.08.22-r13" "%STABLE%\anpr\version.py" >nul
if errorlevel 1 (
  echo [СТАРАЯ СБОРКА] Нужна 2026.08.22-r13
  echo 1^) Закройте программу
  echo 2^) Скачайте новый ZIP и распакуйте
  echo 3^) Запустите UPDATE_NOW.bat из НОВОЙ жёлтой папки
  echo 4^) Снова запустите этот VERIFY_INSTALL.bat
) else (
  echo [OK] В папке стоит сборка r13.
  echo Откройте программу через START_ANPR.bat из:
  echo   %STABLE%
  echo В окне должен быть ЖЁЛТЫЙ значок: СБОРКА 2026.08.22-r13
)

echo.
echo Ярлык на рабочем столе должен вести сюда же.
echo Если ярлык открывает другую папку — удалите ярлык и снова UPDATE_NOW.bat
echo.
pause
exit /b 0
