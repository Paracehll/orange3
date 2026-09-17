@echo off
REM ============================================
REM Orange Data Mining - Start Application
REM Quick Launch Script
REM ============================================

setlocal enabledelayedexpansion
chcp 65001 >nul 2>&1
cls

REM ========================================
REM BANNER
REM ========================================
echo.
echo Orange Data Mining
echo --------------------------
echo.

REM ========================================
REM Check if setup was run
REM ========================================
if not exist "venv" (
    echo [X] Virtual environment not found!
    echo     Please run setup-and-update.bat first to install.
    echo.
    pause
    exit /b 1
)

REM ========================================
REM Activate Virtual Environment
REM ========================================
echo Initializing environment...
call venv\Scripts\activate.bat
if errorlevel 1 (
    echo [X] Failed to activate virtual environment
    echo     Try running setup-and-update.bat to fix the installation
    pause
    exit /b 1
)
echo [OK] Environment ready

REM ========================================
REM Optional: pull latest code on startup
REM ========================================
git --version >nul 2>&1
if not errorlevel 1 (
    echo Checking for code updates from Git...
    git fetch >nul 2>&1
    for /f %%i in ('git rev-parse HEAD 2^>nul') do set LOCAL_COMMIT=%%i
    for /f %%i in ('git rev-parse @{u} 2^>nul') do set REMOTE_COMMIT=%%i
    if not "!LOCAL_COMMIT!"=="!REMOTE_COMMIT!" (
        if not "!REMOTE_COMMIT!"="" (
            echo Updates available, pulling latest changes...
            git pull --ff-only
        )
    ) else (
        echo [OK] Code is up to date
    )
) else (
    echo [INFO] Git not available, skipping code update check
)
echo.

REM ========================================
REM LAUNCH APPLICATION
REM ========================================
echo Launching Orange...
echo.

python -m Orange.canvas %*
set EXITCODE=!ERRORLEVEL!

REM If server/app stops normally
echo.
echo --------------------------
echo Orange stopped (exit code !EXITCODE!).
echo.
pause
