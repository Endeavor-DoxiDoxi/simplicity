@echo off
REM ───────────────────────────────────────────────
REM  Simplicity Installer — Windows
REM ───────────────────────────────────────────────
setlocal enabledelayedexpansion

set "SIMPLICITY_DIR=%~dp0"
set "SIMPLICITY_DIR=%SIMPLICITY_DIR:~0,-1%"
set "CONFIG_DIR=%USERPROFILE%\.simplicity"
set "TOOLS_DIR=%CONFIG_DIR%\tools"
set "WORKSPACE_DIR=%SIMPLICITY_DIR%\workspace"

echo.
echo   .  .  .   S I M P L I C I T Y   I N S T A L L E R
echo   ------------------------------------------------
echo.

REM ── Pick environment type ────────────────────
echo Choose environment type:
echo   [1] Virtual env (venv)    - lightweight, self-contained
echo   [2] Conda                  - if you use Anaconda/Miniconda

where conda >nul 2>&1
if %errorlevel%==0 (
    echo   Conda detected!
    set DEFAULT_ENV=2
) else (
    echo   Conda not found - defaulting to venv
    set DEFAULT_ENV=1
)

set /p ENV_CHOICE="Choice [%DEFAULT_ENV%]: "
if "%ENV_CHOICE%"=="" set ENV_CHOICE=%DEFAULT_ENV%

REM ── Pick wrapper name ─────────────────────────
echo.
echo Pick a command name:
echo   [1] simp          - short & quick
echo   [2] simplicity    - full name (recommended)

set /p NAME_CHOICE="Choice [2]: "
if "%NAME_CHOICE%"=="" set NAME_CHOICE=2

if "%NAME_CHOICE%"=="1" (
    set "WRAPPER_NAME=simp"
) else (
    set "WRAPPER_NAME=simplicity"
)

REM Handle conflict: if simplicity/ dir exists, use simplicity-cli
if "%WRAPPER_NAME%"=="simplicity" if exist "%SIMPLICITY_DIR%\simplicity\" (
    set "WRAPPER_NAME=simplicity-cli"
    echo   Note: 'simplicity' is the package dir, using 'simplicity-cli' instead
)
set "WRAPPER_BAT=%SIMPLICITY_DIR%\%WRAPPER_NAME%.bat"

REM ── Python check ──────────────────────────────
if "%ENV_CHOICE%"=="1" (
    set "PYTHON="
    for %%p in (python python3) do (
        where %%p >nul 2>&1
        if !errorlevel! == 0 (
            for /f "tokens=2 delims=." %%v in ('%%p --version 2^>^&1') do set MAJOR=%%v
            if !MAJOR! GEQ 3 (
                set "PYTHON=%%p"
                goto :found_python
            )
        )
    )
    :found_python
    if "%PYTHON%"=="" (
        echo ERROR: Python 3.11+ required. Install from https://python.org
        pause
        exit /b 1
    )
    echo [OK] Found Python
)

REM ── Setup environment ─────────────────────────
if "%ENV_CHOICE%"=="2" (
    call :setup_conda
) else (
    call :setup_venv
)

REM ── Create wrapper batch ──────────────────────
if "%ENV_CHOICE%"=="2" (
    (
        echo @echo off
        echo REM Simplicity wrapper (conda)
        echo conda run -n simplicity simplicity %%*
    ) > "%WRAPPER_BAT%"
) else (
    (
        echo @echo off
        echo REM Simplicity wrapper (venv)
        echo set "SIM=%%~dp0"
        echo set "SIM=%%SIM:~0,-1%%"
        echo "%%SIM%%\.venv\Scripts\simplicity" %%*
    ) > "%WRAPPER_BAT%"
)
echo [OK] Wrapper: %WRAPPER_NAME%.bat

REM ── Create config directories ─────────────────
mkdir "%CONFIG_DIR%" 2>nul
mkdir "%TOOLS_DIR%" 2>nul
mkdir "%WORKSPACE_DIR%" 2>nul
echo [OK] Config:    %CONFIG_DIR%
echo [OK] Workspace: %WORKSPACE_DIR%

REM ── Copy example tools ────────────────────────
if exist "%SIMPLICITY_DIR%\examples\get_datetime.py" (
    copy "%SIMPLICITY_DIR%\examples\get_datetime.py" "%TOOLS_DIR%\" >nul 2>&1
    echo [OK] Example tool installed
)

echo.
echo   . . . . . . . . . . . . . . . . . . . . . . . .
echo   .  Simplicity installed successfully!
echo   . . . . . . . . . . . . . . . . . . . . . . . .
echo.
echo   Run right now:
echo     %WRAPPER_NAME% chat
echo.
echo   For global access (just '%WRAPPER_NAME%'):
echo     setx PATH "%%PATH%%;%SIMPLICITY_DIR%"
echo     (restart your terminal after)
echo.
echo   First-time setup:
echo     %WRAPPER_NAME% auth
echo.
pause
goto :eof

:setup_venv
echo ... Creating virtual environment...
if not exist "%SIMPLICITY_DIR%\.venv" (
    "%PYTHON%" -m venv "%SIMPLICITY_DIR%\.venv"
)
echo [OK] Virtual environment ready

echo ... Installing Simplicity...
"%SIMPLICITY_DIR%\.venv\Scripts\pip" install -e "%SIMPLICITY_DIR%" --quiet
if errorlevel 1 (
    echo ERROR: pip install failed. Try running as administrator.
    pause
    exit /b 1
)
echo [OK] Simplicity installed
goto :eof

:setup_conda
where conda >nul 2>&1
if errorlevel 1 (
    echo ERROR: Conda not found. Install from https://docs.conda.io
    pause
    exit /b 1
)

REM Check if env already exists
conda env list | findstr /C:"simplicity " >nul 2>&1
if errorlevel 1 (
    echo ... Creating conda env 'simplicity'...
    conda create -y -n simplicity python=3.13 pip
    if errorlevel 1 (
        echo ERROR: Conda env creation failed
        pause
        exit /b 1
    )
) else (
    echo [OK] Conda env 'simplicity' already exists
)

echo ... Installing Simplicity...
conda run -n simplicity pip install -e "%SIMPLICITY_DIR%" --quiet
echo [OK] Simplicity installed
goto :eof
