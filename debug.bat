@echo off
rem ---------------------------------------------------------------
rem  Tailscale Console - debug launcher
rem  Runs the source version in a console so errors stay visible.
rem  NOTE: keep this file ASCII-only - non-ASCII inside .bat files
rem        gets mangled by the console code page.
rem ---------------------------------------------------------------
setlocal
cd /d "%~dp0"

set "VENV=C:\Users\Administrator\.workbuddy\binaries\python\envs\default\Scripts"
set "PY=%VENV%\python.exe"
if not exist "%PY%" set "PY=python"

echo ============================================
echo  Tailscale Console - debug mode
echo  Errors will be shown in this window.
echo ============================================
echo.

"%PY%" "%~dp0app.py"
echo.
echo ---- program exited with code %errorlevel% ----
echo.
pause
