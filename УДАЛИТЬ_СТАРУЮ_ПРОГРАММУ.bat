@echo off
setlocal
cd /d "%~dp0"
call "%~dp0UNINSTALL_COMPLETE.bat"
exit /b %errorlevel%
