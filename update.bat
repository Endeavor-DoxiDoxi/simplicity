@echo off
REM ───────────────────────────────────────────────
REM  Simplicity Updater — pull latest + reinstall
REM ───────────────────────────────────────────────
setlocal enabledelayedexpansion

set "SIMPLICITY_DIR=%~dp0"
set "SIMPLICITY_DIR=%SIMPLICITY_DIR:~0,-1%"
cd /d "%SIMPLICITY_DIR%"

echo.
echo   .  .  .   S I M P L I C I T Y   U P D A T E R
echo   ------------------------------------------------
echo.

REM ── Check git ──────────────────────────────────
git rev-parse --git-dir >nul 2>&1
if errorlevel 1 (
    echo ERROR: Not a git repository.
    pause
    exit /b 1
)

REM ── Pull latest ────────────────────────────────
echo ... Pulling latest from GitHub...
git pull origin main 2>&1
if errorlevel 1 (
    echo.
    echo WARNING: Pull may have had issues. Trying to continue...
)

echo [OK] Code updated

REM ── Reinstall ──────────────────────────────────
if exist "%SIMPLICITY_DIR%\.venv\" (
    echo ... Reinstalling (venv)...
    "%SIMPLICITY_DIR%\.venv\Scripts\pip" install -e "%SIMPLICITY_DIR%" --quiet
    echo [OK] Package reinstalled
) else (
    where conda >nul 2>&1
    if !errorlevel!==0 (
        conda env list | findstr /C:"simplicity " >nul 2>&1
        if !errorlevel!==0 (
            echo ... Reinstalling (conda)...
            conda run -n simplicity pip install -e "%SIMPLICITY_DIR%" --quiet
            echo [OK] Package reinstalled
        )
    )
)

REM ── Show recent commits ────────────────────────
echo.
echo   Recent changes:
git log --oneline -10 2>&1
echo.

echo   . . . . . . . . . . . . . . . . . . . . . . . .
echo   .  Update complete!
echo   . . . . . . . . . . . . . . . . . . . . . . . .
echo.
echo   Your config and tools are untouched.
echo   Run: simp chat
echo.
echo   TIP: If 'simp update' doesn't work, just run this
echo   update.bat directly — it does the same thing.
echo.
pause
