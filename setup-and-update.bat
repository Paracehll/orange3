@echo off
REM ============================================
REM Orange Data Mining - Setup & Update
REM Installation and Update Script
REM ============================================

setlocal enabledelayedexpansion
chcp 65001 >nul 2>&1
cd /d "%~dp0"
cls

REM ========================================
REM BANNER
REM ========================================
echo.
echo Orange Data Mining - Setup ^& Update
echo ─────────────────────────────────────────
echo.

REM ========================================
REM STEP 1: Check Python Installation
REM ========================================
echo.
echo [1/5] Checking Python Installation...
python --version >nul 2>&1
if errorlevel 1 (
    echo [X] Python is not installed or not in PATH
    echo     Please install Python 3.11+ from https://www.python.org/
    echo     Make sure to check "Add Python to PATH" during installation
    pause
    exit /b 1
)
for /f "tokens=2" %%i in ('python --version 2^>^&1') do set PYTHON_VERSION=%%i
echo     [OK] Python %PYTHON_VERSION% detected

REM ========================================
REM STEP 2: Virtual Environment Setup
REM ========================================
echo.
echo [2/5] Virtual Environment Setup...
if not exist "venv\Scripts\activate.bat" (
    echo     [..] First-time setup - creating virtual environment...
    python -m venv venv
    if errorlevel 1 (
        echo     [X] Failed to create virtual environment
        pause
        exit /b 1
    )
    echo     [OK] Virtual environment created
    set FIRST_INSTALL=1
) else (
    echo     [OK] Virtual environment exists
    set FIRST_INSTALL=0
)

REM ========================================
REM STEP 3: Activate Virtual Environment
REM ========================================
echo.
echo [3/5] Activating Environment...
call venv\Scripts\activate.bat
if errorlevel 1 (
    echo     [X] Failed to activate virtual environment
    pause
    exit /b 1
)
echo     [OK] Virtual environment activated

REM ========================================
REM STEP 4: Check for Updates
REM ========================================
echo.
echo [4/5] Checking for Updates...

set NEEDS_UPDATE=0

if exist ".git" (
    call git --version >nul 2>&1
    if not errorlevel 1 (
        echo     [..] Checking for code updates from Git...
        call git fetch >nul 2>&1

        set "LOCAL_COMMIT="
        set "REMOTE_COMMIT="
        for /f "tokens=*" %%i in ('call git rev-parse HEAD 2^>nul') do set "LOCAL_COMMIT=%%i"
        for /f "tokens=*" %%i in ('call git rev-parse @{u} 2^>nul') do set "REMOTE_COMMIT=%%i"

        if not "!LOCAL_COMMIT!"=="" if not "!REMOTE_COMMIT!"=="" (
            if not "!LOCAL_COMMIT!"=="!REMOTE_COMMIT!" (
                echo     [..] Updates available! Pulling latest changes...
                call git pull
                if errorlevel 1 (
                    echo     [!!] Warning: git pull failed or encountered conflicts.
                ) else (
                    set NEEDS_UPDATE=1
                )
            ) else (
                echo     [OK] Code is up to date
            )
        ) else (
            echo     [--] Unable to determine remote branch, skipping code update
        )
    ) else (
        echo     [--] Git not available, skipping code update check
    )
) else (
    echo     [--] Not a git repository, skipping code update check
)

if !FIRST_INSTALL!==1 (
    set NEEDS_UPDATE=1
    echo     [..] First installation - will install all dependencies
) else (
    if exist "venv\.requirements_hash" (
        for /f "delims=" %%i in ('certutil -hashfile requirements-pyqt.txt MD5 ^| find /v "hash"') do set NEW_HASH=%%i
        set /p OLD_HASH=<venv\.requirements_hash
        if not "!NEW_HASH!"=="!OLD_HASH!" (
            echo     [..] Dependencies changed - updating packages...
            set NEEDS_UPDATE=1
        )
    ) else (
        echo     [..] No hash found - will update dependencies
        set NEEDS_UPDATE=1
    )
)

REM ========================================
REM STEP 5: Install/Update Dependencies
REM ========================================
echo.
echo [5/5] Managing Dependencies...

if "!NEEDS_UPDATE!"=="1" (
    echo     [..] Upgrading pip...
    python -m pip install --upgrade pip --quiet

    echo     [..] Installing PyQt requirements...
    if exist "requirements-pyqt.txt" (
        pip install -r requirements-pyqt.txt
    )

    echo     [..] Installing Orange3 in editable mode...
    echo.
    pip install -e .
    echo.
    if errorlevel 1 (
        echo     [X] Failed to install dependencies
        echo     [X] Please check your internet connection and try again
        pause
        exit /b 1
    )

    if exist "requirements-pyqt.txt" (
        for /f "delims=" %%i in ('certutil -hashfile requirements-pyqt.txt MD5 ^| find /v "hash"') do echo %%i>venv\.requirements_hash
    )
    echo     [OK] Dependencies updated successfully
) else (
    echo     [OK] Dependencies are up to date
)

REM ========================================
REM SETUP COMPLETE
REM ========================================
echo.
echo ─────────────────────────────────────────
echo [OK] Setup complete!
echo.
echo To start Orange Data Mining, run: start.bat
echo ─────────────────────────────────────────
echo.
pause
