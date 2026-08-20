@echo off
setlocal
cd /d "%~dp0"
title Remove old Avtonomera Seetong
echo.
echo This will DELETE the old Avtonomera program completely.
echo Seetong camera program will NOT be deleted.
echo.
pause
if exist "%~dp0UNINSTALL_COMPLETE.ps1" (
    powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0UNINSTALL_COMPLETE.ps1"
) else (
    echo Running built-in cleanup...
    powershell -NoProfile -ExecutionPolicy Bypass -Command ^
      "Stop-Process -Name python*,pythonw* -Force -ErrorAction SilentlyContinue; ^
       $d=[Environment]::GetFolderPath('Desktop'); ^
       Remove-Item (Join-Path $d 'Avtonomera Seetong.lnk') -Force -EA SilentlyContinue; ^
       Remove-Item (Join-Path $d 'Автономера Seetong.lnk') -Force -EA SilentlyContinue; ^
       foreach($r in @($d,(Join-Path $env:USERPROFILE 'Downloads'),'D:\','C:\')){ ^
         if(Test-Path $r){ Get-ChildItem $r -Directory -EA SilentlyContinue | Where-Object { $_.Name -like 'my_search_gpu_bot*' -or $_.Name -eq 'AvtonomeraSeetong' } | ForEach-Object { Write-Host ('Deleting '+$_.FullName); Remove-Item $_.FullName -Recurse -Force -EA SilentlyContinue }; ^
         Get-ChildItem $r -File -EA SilentlyContinue | Where-Object { $_.Name -like 'my_search_gpu_bot*.zip' } | ForEach-Object { Remove-Item $_.FullName -Force -EA SilentlyContinue } } }; ^
       Remove-Item 'D:\AvtonomeraSeetong' -Recurse -Force -EA SilentlyContinue; ^
       Write-Host 'DONE. Old program removed.'; pause"
)
exit /b %errorlevel%
