@echo off
setlocal
cd /d "%~dp0"
set OPEN_BROWSER=-OpenBrowser
echo %* | findstr /I /C:"-OpenBrowser" >nul && set OPEN_BROWSER=
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\demo.ps1" %OPEN_BROWSER% %*
set EXIT_CODE=%ERRORLEVEL%
if not "%EXIT_CODE%"=="0" (
  echo.
  echo 演示失败，退出码 %EXIT_CODE%。
  pause
)
exit /b %EXIT_CODE%
