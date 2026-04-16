@echo off
chcp 65001 >nul 2>&1
REM ============================================================================
REM Local AI Assistant - Voice Service Launcher (Windows)
REM ============================================================================
REM Запускает голосовой сервис (будущая реализация)
REM ============================================================================

echo.
echo ================================================
echo   Local AI Assistant - Voice Service
echo ================================================
echo.
echo VNIAMANIE: Golosovoy servis poka ne realizovan!
echo.
echo Dlya aktivatsii:
echo   1. Ustanovite zavisimosti:
echo      pip install pynput speechrecognition pyaudio
echo.
echo   2. Realizuyte kod v services/voice_service.py
echo.
echo   3. Zapustite snova
echo.
echo ================================================
echo.

set "SCRIPT_DIR=%~dp0"
cd /d "%SCRIPT_DIR%"

if exist "venv\Scripts\activate.bat" (
    call "venv\Scripts\activate.bat"
)

REM Zaglushka
echo [INFO] Zapusk golosovogo servisa (zaglushka)...
echo [INFO] Sm. services/voice_service.py dlya realizatsii
echo.

python services/voice_service.py

pause
