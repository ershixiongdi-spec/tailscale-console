@echo off
REM ===========================================================================
REM  Tailscale Console - Windows one-click build script
REM  Produces: dist\TailscaleConsole.exe (standalone, no Python needed at runtime)
REM
REM  Prerequisites:
REM    - Windows 10/11
REM    - Python 3.9+ (from python.org, OR Microsoft Store, OR `winget install Python.Python.3.12`)
REM      Must be on PATH. If not, see section [PYTHON CHECK] below.
REM    - Internet access (to download pyinstaller/pywebview/pillow from PyPI, ~100MB first time)
REM
REM  Usage:
REM    Double-click this file, OR open cmd/PowerShell and run:
REM      build_windows.bat
REM
REM  After build:
REM    dist\TailscaleConsole.exe  <- double-click to run
REM ===========================================================================

setlocal enabledelayedexpansion
cd /d "%~dp0"

echo.
echo ============================================================
echo   Tailscale Console - Windows Build
echo ============================================================
echo.

REM ---- [PYTHON CHECK] ----
echo [1/5] Checking Python...
where py >nul 2>nul
if %errorlevel%==0 (
    set "PYCMD=py -3"
    goto :py_ok
)
where python >nul 2>nul
if %errorlevel%==0 (
    set "PYCMD=python"
    goto :py_ok
)
where python3 >nul 2>nul
if %errorlevel%==0 (
    set "PYCMD=python3"
    goto :py_ok
)
echo.
echo [ERROR] Python not found on PATH.
echo.
echo Install Python 3.9+ from one of:
echo   1. https://www.python.org/downloads/windows/  (check "Add Python to PATH")
echo   2. Microsoft Store: search "Python 3.12"
echo   3. winget install Python.Python.3.12
echo.
echo Then re-run this script.
pause
exit /b 1

:py_ok
%PYCMD% --version
if %errorlevel% neq 0 (
    echo [ERROR] Python command failed. Check your installation.
    pause
    exit /b 1
)

REM ---- [TAILSCALE CLI CHECK] (warn only, not fatal) ----
echo.
echo [2/5] Checking Tailscale CLI (optional, for runtime)...
if exist "C:\Program Files\Tailscale\tailscale.exe" (
    echo   Found: C:\Program Files\Tailscale\tailscale.exe
) else (
    echo   Not found in default location.
    echo   The .exe will still build, but device list/ping will be empty at runtime.
    echo   Install Tailscale client from https://tailscale.com/download if needed.
)

REM ---- [VENV] ----
echo.
echo [3/5] Creating virtual environment...
if exist ".venv\Scripts\python.exe" (
    echo   .venv already exists, reusing.
) else (
    %PYCMD% -m venv .venv
    if %errorlevel% neq 0 (
        echo [ERROR] venv creation failed.
        pause
        exit /b 1
    )
)
set "VENV_PY=.venv\Scripts\python.exe"

REM ---- [INSTALL DEPS] ----
echo.
echo [4/5] Installing dependencies (pyinstaller, pywebview, pillow)...
echo   This may take 1-3 minutes on first run (downloads ~100MB).
"%VENV_PY%" -m pip install --upgrade pip >nul 2>&1
"%VENV_PY%" -m pip install pyinstaller pywebview pillow
if %errorlevel% neq 0 (
    echo [ERROR] pip install failed. Check your internet connection.
    echo   If behind a proxy, set HTTP_PROXY/HTTPS_PROXY env vars first.
    pause
    exit /b 1
)

REM ---- [BUILD] ----
echo.
echo [5/5] Building TailscaleConsole.exe with PyInstaller...
echo   This takes 1-2 minutes.
"%VENV_PY%" _build.py
if %errorlevel% neq 0 (
    echo.
    echo [ERROR] Build failed. See PyInstaller output above.
    pause
    exit /b 1
)

REM ---- [DONE] ----
echo.
echo ============================================================
echo   Build complete!
echo ============================================================
echo.
echo   Product: dist\TailscaleConsole.exe
echo.
if exist "dist\TailscaleConsole.exe" (
    for %%A in ("dist\TailscaleConsole.exe") do (
        set "FSIZE=%%~zA"
        set /a "FMB=!FSIZE!/1048576"
        echo   Size: !FMB! MB
    )
    echo.
    echo   To run: double-click dist\TailscaleConsole.exe
    echo   To distribute: copy that .exe to any Windows machine.
    echo.
    echo   First run may trigger Windows SmartScreen - click "More info" then "Run anyway".
) else (
    echo   [WARNING] dist\TailscaleConsole.exe not found. Check build log above.
)
echo.
pause
