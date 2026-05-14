@echo off
REM ───────────────────────────────────────────────
REM  Simplicity Updater — Windows
REM ───────────────────────────────────────────────
setlocal enabledelayedexpansion

set "SIMPLICITY_DIR=%~dp0"
set "SIMPLICITY_DIR=%SIMPLICITY_DIR:~0,-1%"
cd /d "%SIMPLICITY_DIR%"

echo.
echo   .  .  .   S I M P L I C I T Y   U P D A T E R
echo   ------------------------------------------------
echo.

REM ── Check if git repo ─────────────────────────
git rev-parse --git-dir >nul 2>&1
if errorlevel 1 (
    echo   You downloaded Simplicity as a ZIP — not a git clone.
    echo   The updater needs git to pull the latest changes.
    echo.
    echo   Easiest fix: re-download from:
    echo   https://github.com/Endeavor-DoxiDoxi/simplicity
    echo.
    echo   Or clone with git for future updates:
    echo   git clone https://github.com/Endeavor-DoxiDoxi/simplicity.git
    echo   cd simplicity
    echo   install.bat
    echo.
    echo   Your config and tools are in: %USERPROFILE%\.simplicity
    echo   Copy them to the new install to keep your settings.
    echo.
    pause
    exit /b 1
)

REM ── Pull latest ────────────────────────────────
echo ... Pulling latest from GitHub...
git pull origin main 2>&1
if errorlevel 1 (
    echo.
    echo WARNING: Pull had issues. Trying to continue...
)

echo [OK] Code updated

REM ── Reinstall ──────────────────────────────────
if exist "%SIMPLICITY_DIR%\.venv\" (
    echo ... Reinstalling...
    "%SIMPLICITY_DIR%\.venv\Scripts\pip" install -e "%SIMPLICITY_DIR%" --quiet
    echo [OK] Package reinstalled
) else (
    echo ... No venv found. Run install.bat first.
)

REM ── Show recent changes ────────────────────────
echo.
echo   Recent changes:
git log --oneline -10 2>&1
echo.

echo   . . . . . . . . . . . . . . . . . . . . . . . .
echo   .  Update complete!
echo   . . . . . . . . . . . . . . . . . . . . . . . .
echo.
echo   Run: simp chat
echo.
echo   TIP: 'simp update' runs this script automatically.
echo   Or just run update.bat directly.
echo.
pause
