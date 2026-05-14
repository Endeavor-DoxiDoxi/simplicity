@echo off
REM ───────────────────────────────────────────────
REM  Simplicity Installer — Windows
REM ───────────────────────────────────────────────
setlocal enabledelayedexpansion

set "SIMPLICITY_DIR=%~dp0"
set "SIMPLICITY_DIR=%SIMPLICITY_DIR:~0,-1%"
set "VENV_DIR=%SIMPLICITY_DIR%\.venv"
set "WRAPPER_BAT=%SIMPLICITY_DIR%\simp.bat"
set "CONFIG_DIR=%USERPROFILE%\.simplicity"
set "TOOLS_DIR=%CONFIG_DIR%\tools"
set "WORKSPACE_DIR=%SIMPLICITY_DIR%\workspace"

echo.
echo   🌸  S I M P L I C I T Y   I N S T A L L E R
echo   ─────────────────────────────────────────
echo.

REM ── Python check ──────────────────────────────
set "PYTHON="
for %%p in (python python3) do (
    where %%p >nul 2>&1
    if !errorlevel! == 0 (
        for /f "tokens=2 delims=." %%v in ('%%p --version 2^>^&1') do (
            set "MAJOR=%%v"
        )
        if !MAJOR! GEQ 3 (
            set "PYTHON=%%p"
            goto :found_python
        )
    )
)
:found_python

if "%PYTHON%"=="" (
    echo ❌ Python 3.11+ is required. Install it from https://python.org
    echo    Make sure to check "Add Python to PATH" during installation.
    pause
    exit /b 1
)
echo ✅ Found Python

REM ── Virtual environment ───────────────────────
if not exist "%VENV_DIR%" (
    echo 📦 Creating virtual environment...
    "%PYTHON%" -m venv "%VENV_DIR%"
)
echo ✅ Virtual environment ready

REM ── Install package ───────────────────────────
echo 📦 Installing Simplicity...
"%VENV_DIR%\Scripts\pip" install -e "%SIMPLICITY_DIR%" --quiet
echo ✅ Simplicity installed

REM ── Create wrapper batch ──────────────────────
(
    echo @echo off
    echo REM Simplicity wrapper — auto-activates venv
    echo set "SIMPLICITY_DIR=%%~dp0"
    echo set "SIMPLICITY_DIR=%%SIMPLICITY_DIR:~0,-1%%"
    echo "%%SIMPLICITY_DIR%%\.venv\Scripts\simplicity" %%*
) > "%WRAPPER_BAT%"
echo ✅ Wrapper script: %WRAPPER_BAT%

REM ── Create config directories ─────────────────
mkdir "%CONFIG_DIR%" 2>nul
mkdir "%TOOLS_DIR%" 2>nul
mkdir "%WORKSPACE_DIR%" 2>nul
echo ✅ Config:    %CONFIG_DIR%
echo ✅ Workspace: %WORKSPACE_DIR%

REM ── Copy example tools ────────────────────────
if exist "%SIMPLICITY_DIR%\examples\get_datetime.py" (
    copy "%SIMPLICITY_DIR%\examples\get_datetime.py" "%TOOLS_DIR%\" >nul 2>&1
    echo ✅ Example tool installed
)

echo.
echo   ┌─────────────────────────────────────────┐
echo   │  🌸 Simplicity installed successfully!  │
echo   └─────────────────────────────────────────┘
echo.
echo   To use it from anywhere, add to your PATH:
echo     setx PATH "%%PATH%%;%SIMPLICITY_DIR%"
echo.
echo   Or run with:
echo     simp chat
echo.
echo   First-time setup:
echo     simp auth
echo.
pause
