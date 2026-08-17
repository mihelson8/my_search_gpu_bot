@echo off
chcp 65001 > nul
cd /d "%~dp0"

echo ============================================================
echo   Создание ярлыка программы на вашем Рабочем столе...
echo ============================================================
echo.

set "VBS_SCRIPT=%TEMP%\CreateBusinessShortcut_%RANDOM%.vbs"

echo Set oWS = WScript.CreateObject("WScript.Shell") > "%VBS_SCRIPT%"
echo sLinkFile = oWS.SpecialFolders("Desktop") ^& "\Бизнес Видеонаблюдение и Китай.lnk" >> "%VBS_SCRIPT%"
echo Set oLink = oWS.CreateShortcut(sLinkFile) >> "%VBS_SCRIPT%"
echo oLink.TargetPath = "%~dp0START_APP_WINDOWS.bat" >> "%VBS_SCRIPT%"
echo oLink.WorkingDirectory = "%~dp0" >> "%VBS_SCRIPT%"
echo oLink.Description = "CCTV & China Cargo Business Suite" >> "%VBS_SCRIPT%"
if exist "%~dp0app_icon.ico" echo oLink.IconLocation = "%~dp0app_icon.ico,0" >> "%VBS_SCRIPT%"
echo oLink.Save >> "%VBS_SCRIPT%"

cscript //nologo "%VBS_SCRIPT%"
if exist "%VBS_SCRIPT%" del "%VBS_SCRIPT%"

echo.
echo ============================================================
echo   [УСПЕХ] Ярлык "Бизнес Видеонаблюдение и Китай"
echo   успешно создан на вашем Рабочем столе!
echo.
echo   Теперь вы можете запускать программу прямо с Рабочего стола.
echo ============================================================
echo.
pause
