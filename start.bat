@echo off
rem ---------------------------------------------------------------
rem  Tailscale Console launcher
rem  Prefer the packaged exe; fall back to the source version.
rem  NOTE: keep this file ASCII-only - non-ASCII inside .bat files
rem        gets mangled by the console code page.
rem ---------------------------------------------------------------
setlocal
cd /d "%~dp0"

if exist "%~dp0dist\TailscaleConsole.exe" (
  start "" "%~dp0dist\TailscaleConsole.exe"
  exit /b 0
)

set "VENV=C:\Users\Administrator\.workbuddy\binaries\python\envs\default\Scripts"
set "PYW=%VENV%\pythonw.exe"
set "PY=%VENV%\python.exe"

if not exist "%PYW%" if exist "%PY%" set "PYW=%PY%"
if not exist "%PYW%" goto nopython
if not exist "%~dp0app.py" goto noapp

start "" "%PYW%" "%~dp0app.py"
exit /b 0

:nopython
echo.
echo  [ERROR] Neither dist\TailscaleConsole.exe nor Python was found.
echo  Expected Python at: %VENV%
echo  Try running debug.bat for details.
echo.
pause
exit /b 1

:noapp
echo.
echo  [ERROR] app.py is missing from this folder.
echo.
pause
exit /b 1
