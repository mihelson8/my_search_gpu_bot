@echo off
setlocal
cd /d "%~dp0"
title Update Avtonomera NOW
echo Closing old program and installing the newest files...
call "%~dp0FIX_AND_CLEAN.bat"
exit /b %errorlevel%
