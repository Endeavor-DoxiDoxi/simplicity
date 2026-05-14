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
echo   Install directory: %SIMPLICITY_DIR%
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

REM ── Discord support ───────────────────────────
echo.
set /p DISCORD_CHOICE="Install Discord bot support? (discord.py) [y/N]: "
if /i "%DISCORD_CHOICE%"=="y" set INSTALL_DISCORD=1

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
        echo         Make sure to check "Add Python to PATH" during install.
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

REM ── Create wrappers ───────────────────────────
(
    echo @echo off
    echo REM Simplicity wrapper
    echo set "SIMP_DIR=%%~dp0"
    echo set "SIMP_DIR=%%SIMP_DIR:~0,-1%%"
    if "%ENV_CHOICE%"=="2" (
        echo conda run -n simplicity simplicity %%*
    ) else (
        echo "%%SIMP_DIR%%\.venv\Scripts\simplicity" %%*
    )
) > "%SIMPLICITY_DIR%\simp.bat"
echo [OK] Wrapper: simp.bat

REM Also simplicity.bat if name isn't taken
if not exist "%SIMPLICITY_DIR%\simplicity\" (
    copy "%SIMPLICITY_DIR%\simp.bat" "%SIMPLICITY_DIR%\simplicity.bat" >nul 2>&1
)

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

REM ── Done ──────────────────────────────────────
echo.
echo   . . . . . . . . . . . . . . . . . . . . . . . .
echo   .  Simplicity installed successfully!
echo   . . . . . . . . . . . . . . . . . . . . . . . .
echo.
echo   ^>^> YOU ARE IN: %SIMPLICITY_DIR%
echo.
echo   Run from THIS folder:
echo     simp chat
echo.
echo   (or: .venv\Scripts\simplicity chat)
echo.
echo   First-time setup:
echo     simp auth
echo.
echo   Tip: add this folder to PATH for global access:
echo     setx PATH "%%PATH%%;%SIMPLICITY_DIR%"
echo     (then restart your terminal)
echo.
pause
goto :eof

:setup_venv
echo ... Creating virtual environment...
if not exist "%SIMPLICITY_DIR%\.venv" (
    "%PYTHON%" -m venv "%SIMPLICITY_DIR%\.venv"
    if errorlevel 1 (
        echo ERROR: venv creation failed
        pause
        exit /b 1
    )
)
echo [OK] Virtual environment ready

echo ... Installing Simplicity...
"%SIMPLICITY_DIR%\.venv\Scripts\pip" install -e "%SIMPLICITY_DIR%" --quiet
if errorlevel 1 (
    echo.
    echo ERROR: pip install failed.
    echo Try running this terminal AS ADMINISTRATOR.
    pause
    exit /b 1
)
echo [OK] Simplicity installed

if "%INSTALL_DISCORD%"=="1" (
    echo ... Installing discord.py...
    "%SIMPLICITY_DIR%\.venv\Scripts\pip" install discord.py --quiet
    echo [OK] Discord support installed
)
goto :eof

:setup_conda
where conda >nul 2>&1
if errorlevel 1 (
    echo ERROR: Conda not found. Install from https://docs.conda.io
    pause
    exit /b 1
)

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
if errorlevel 1 (
    echo ERROR: pip install failed
    pause
    exit /b 1
)
echo [OK] Simplicity installed

if "%INSTALL_DISCORD%"=="1" (
    echo ... Installing discord.py...
    conda run -n simplicity pip install discord.py --quiet
    echo [OK] Discord support installed
)
goto :eof
