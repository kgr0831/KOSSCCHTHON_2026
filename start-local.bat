@echo off
setlocal
cd /d "%~dp0"
title Dudri - local services
"%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\bootstrap-local.ps1" %*
set "DUDRI_EXIT_CODE=%ERRORLEVEL%"
if "%DUDRI_EXIT_CODE%"=="0" goto done
echo.
echo [local] Startup stopped with error %DUDRI_EXIT_CODE%.
echo [local] This window stays open so you can read the message above.
echo [local] Check your internet connection and this folder's .env settings, then retry.
pause
:done
endlocal & exit /b %DUDRI_EXIT_CODE%
