@echo off
setlocal
cd /d "%~dp0"
call "%~dp0FIX_AND_CLEAN.bat"
exit /b %errorlevel%
