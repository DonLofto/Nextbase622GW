@echo off
setlocal
title Nextbase 622GW temporary Bluetooth recovery
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0prepare-windows.ps1" -Action Prepare
set "recovery_result=%errorlevel%"
echo.
if not "%recovery_result%"=="0" echo Preparation stopped. Read the message above before doing anything with the card.
pause
exit /b %recovery_result%
