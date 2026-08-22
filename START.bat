@echo off
cd /d "%~dp0"
title Business Suite

echo Starting Business Suite...
echo.

where py >nul 2>&1
if %errorlevel%==0 (
  py -3 -c "import os,runpy; os.chdir(r'%~dp0'); runpy.run_path('app_suite.py', run_name='__main__')"
  goto end
)

where python >nul 2>&1
if %errorlevel%==0 (
  python -c "import os,runpy; os.chdir(r'%~dp0'); runpy.run_path('app_suite.py', run_name='__main__')"
  goto end
)

echo [ERROR] Python not found. Install from python.org with Add to PATH.
pause

:end
pause
