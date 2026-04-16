@echo off
REM ============================================================================
REM Local AI Assistant - Web Launcher (Windows)
REM ============================================================================

echo.
echo ================================================
echo   Local AI Assistant - Web Server
echo ================================================
echo.

set "SCRIPT_DIR=%~dp0"
cd /d "%SCRIPT_DIR%"

REM Check venv
if exist "venv\Scripts\activate.bat" (
    echo [OK] venv found
) else (
    echo [ERROR] venv not found!
    echo Run: python -m venv venv
    pause
    exit /b 1
)

REM Activate venv
call "venv\Scripts\activate.bat"

REM Check packages
echo [INFO] Checking dependencies...
pip show fastapi >nul 2>nul
if errorlevel 1 (
    echo [INFO] Installing dependencies...
    pip install -r backend\requirements.txt
)

REM Disable HuggingFace online requests
set HF_HUB_OFFLINE=1
set TRANSFORMERS_OFFLINE=1
set HF_HUB_DISABLE_TELEMETRY=1

REM Start server
echo.
echo ================================================
echo Starting FastAPI server...
echo ================================================
echo.
echo Open in browser: http://localhost:8000
echo.
echo Press Ctrl+C to stop
echo ================================================
echo.

python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload

if errorlevel 1 (
    echo.
    echo [ERROR] Server failed to start!
    pause
) else (
    echo.
    echo Server stopped
    pause
)
