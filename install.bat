@echo off
setlocal enabledelayedexpansion

title Local AI Assistant - Installer

set "SCRIPT_DIR=%~dp0"
set "SCRIPT_DIR=%SCRIPT_DIR:~0,-1%"
cd /d "%SCRIPT_DIR%"

set "LOG_FILE=%SCRIPT_DIR%\install.log"
echo [%date% %time%] Installer started > "%LOG_FILE%"

:MENU
cls
echo.
echo =============================================
echo    Local AI Assistant - Installer
echo =============================================
echo.
echo  [1] Check environment
echo  [2] Install Python dependencies
echo  [3] Download Whisper Large V3 Turbo
echo  [4] Download OmniVoice
echo  [5] Build Tauri app (exe)
echo  [6] Setup .env from template
echo  [7] Install FFmpeg
echo  [8] Full installation (all steps)
echo  [9] Launch application
echo  [0] Exit
echo.
set /p "choice=Select option: "
echo.

if "%choice%"=="1" goto CHECK_ENV
if "%choice%"=="2" goto INSTALL_PYTHON_DEPS
if "%choice%"=="3" goto DOWNLOAD_WHISPER
if "%choice%"=="4" goto DOWNLOAD_OMNIVOICE
if "%choice%"=="5" goto BUILD_TAURI
if "%choice%"=="6" goto SETUP_ENV
if "%choice%"=="7" goto INSTALL_FFMPEG
if "%choice%"=="8" goto FULL_INSTALL
if "%choice%"=="9" goto RUN_APP
if "%choice%"=="0" goto EOF

echo  [!] Invalid input, try again.
timeout /t 2 >nul
goto MENU

:CHECK_ENV
cls
echo =============================================
echo   Check Environment
echo =============================================
echo.

set "all_ok=1"

echo  [Python]...
where python >nul 2>&1
if %errorlevel% equ 0 (
    python --version 2>&1 | findstr /r "^Python" >nul
    if !errorlevel! equ 0 (
        echo    [+] Python found
        echo    [%date% %time%] Python found >> "%LOG_FILE%"
    )
) else (
    echo    [-] Python not found! Install Python 3.11+
    echo    [%date% %time%] Python NOT found >> "%LOG_FILE%"
    set "all_ok=0"
)

echo  [Node.js]...
where node >nul 2>&1
if %errorlevel% equ 0 (
    echo    [+] Node.js found
    echo    [%date% %time%] Node.js found >> "%LOG_FILE%"
) else (
    echo    [-] Node.js not found! Install Node.js 18+
    echo    [%date% %time%] Node.js NOT found >> "%LOG_FILE%"
    set "all_ok=0"
)

echo  [npm]...
where npm >nul 2>&1
if %errorlevel% equ 0 (
    echo    [+] npm found
    echo    [%date% %time%] npm found >> "%LOG_FILE%"
) else (
    echo    [-] npm not found!
    echo    [%date% %time%] npm NOT found >> "%LOG_FILE%"
    set "all_ok=0"
)

echo  [Rust/Cargo]...
where rustc >nul 2>&1
if %errorlevel% equ 0 (
    echo    [+] Rust found
    echo    [%date% %time%] Rust found >> "%LOG_FILE%"
) else (
    echo    [-] Rust not found! Install from https://rustup.rs
    echo    [%date% %time%] Rust NOT found >> "%LOG_FILE%"
    set "all_ok=0"
)

echo  [Git]...
where git >nul 2>&1
if %errorlevel% equ 0 (
    echo    [+] Git found (optional)
    echo    [%date% %time%] Git found >> "%LOG_FILE%"
) else (
    echo    [-] Git not found (optional)
    echo    [%date% %time%] Git NOT found >> "%LOG_FILE%"
)

echo  [FFmpeg]...
where ffmpeg >nul 2>&1
if %errorlevel% equ 0 (
    echo    [+] FFmpeg found
    echo    [%date% %time%] FFmpeg found >> "%LOG_FILE%"
) else (
    echo    [-] FFmpeg not found. Use option [7] to install
    echo    [%date% %time%] FFmpeg NOT found >> "%LOG_FILE%"
)

echo.
if "%all_ok%"=="0" (
    echo  [!] Some components are missing.
    echo  [!] Install them before building the application.
) else (
    echo  [+] All required components are installed.
)
echo.
echo  Press any key to return to menu...
pause >nul
goto MENU

:INSTALL_PYTHON_DEPS
cls
echo =============================================
echo   Install Python Dependencies
echo =============================================
echo.
echo  [1/3] Creating virtual environment...

if not exist "venv\Scripts\activate.bat" (
    python -m venv venv
    if !errorlevel! neq 0 (
        echo  [!] Failed to create venv!
        pause
        goto MENU
    )
    echo    [+] Virtual environment created
) else (
    echo    [+] Virtual environment already exists
)

echo  [2/3] Activating venv...
call "venv\Scripts\activate.bat"
if !errorlevel! neq 0 (
    echo  [!] Failed to activate venv!
    pause
    goto MENU
)
echo    [+] venv activated

echo  [3/3] Installing dependencies...
python -m pip install --upgrade pip >nul 2>&1
pip install -r requirements.txt
if !errorlevel! neq 0 (
    echo  [!] Failed to install dependencies!
    echo  [!] Check requirements.txt
    pause
    goto MENU
)
echo    [+] Dependencies installed
echo    [%date% %time%] Python deps installed >> "%LOG_FILE%"

echo.
echo  Press any key to return to menu...
pause >nul
goto MENU

:DOWNLOAD_WHISPER
cls
echo =============================================
echo   Download Whisper Large V3 Turbo
echo =============================================
echo.
echo  Model will be downloaded to:
echo    %SCRIPT_DIR%\llm-assistant-tauri\src-tauri\target\release\openai_whisper-large-v3-turbo
echo.

if not exist "venv\Scripts\activate.bat" (
    echo  [!] First run option [2] - Install Python dependencies
    pause
    goto MENU
)
call "venv\Scripts\activate.bat"

echo  [1/2] Installing huggingface_hub...
pip install huggingface_hub >nul 2>&1
echo    [+] huggingface_hub installed

echo  [2/2] Downloading model...
echo    This may take 5-15 minutes (size ~3 GB)
echo.

set "WHISPER_DIR=%SCRIPT_DIR%\llm-assistant-tauri\src-tauri\target\release\openai_whisper-large-v3-turbo"
if not exist "%WHISPER_DIR%" mkdir "%WHISPER_DIR%"

python -c ^
"import sys;^
from huggingface_hub import snapshot_download;^
print('  Downloading openai/whisper-large-v3-turbo...');^
snapshot_download('openai/whisper-large-v3-turbo', local_dir=r'%WHISPER_DIR:\=\\%');^
print('  [+] Whisper model downloaded successfully')"

if !errorlevel! neq 0 (
    echo  [!] Download failed!
    echo  [!] Try again later or download manually
    pause
    goto MENU
)

echo    [%date% %time%] Whisper downloaded >> "%LOG_FILE%"
echo.
echo  [+] Whisper Large V3 Turbo downloaded!
echo.
pause
goto MENU

:DOWNLOAD_OMNIVOICE
cls
echo =============================================
echo   Download OmniVoice
echo =============================================
echo.
echo  Model will be downloaded to:
echo    %SCRIPT_DIR%\llm-assistant-tauri\src-tauri\target\release\OmniVoice
echo.

if not exist "venv\Scripts\activate.bat" (
    echo  [!] First run option [2] - Install Python dependencies
    pause
    goto MENU
)
call "venv\Scripts\activate.bat"

echo  [1/2] Installing huggingface_hub...
pip install huggingface_hub >nul 2>&1
echo    [+] huggingface_hub installed

echo  [2/2] Downloading model...
echo    This may take 5-10 minutes (size ~2 GB)
echo.

set "OMNI_DIR=%SCRIPT_DIR%\llm-assistant-tauri\src-tauri\target\release\OmniVoice"
if not exist "%OMNI_DIR%" mkdir "%OMNI_DIR%"

python -c ^
"import sys;^
from huggingface_hub import snapshot_download;^
print('  Downloading k2-fsa/OmniVoice...');^
snapshot_download('k2-fsa/OmniVoice', local_dir=r'%OMNI_DIR:\=\\%');^
print('  [+] OmniVoice model downloaded successfully')"

if !errorlevel! neq 0 (
    echo  [!] Download failed!
    echo  [!] Try again later or download manually
    pause
    goto MENU
)

echo  [+] OmniVoice downloaded. Install the package:
echo      pip install omnivoice
echo    [%date% %time%] OmniVoice downloaded >> "%LOG_FILE%"
echo.
echo  Press any key to return to menu...
pause >nul
goto MENU

:BUILD_TAURI
cls
echo =============================================
echo   Build Tauri Application (exe)
echo =============================================
echo.
echo  Note: first build may take 10-30 minutes
echo  (downloading Cargo dependencies and compiling Rust)
echo.

echo  [1/4] Checking Node.js...
where node >nul 2>&1
if !errorlevel! neq 0 (
    echo  [!] Node.js not found! Install Node.js 18+
    pause
    goto MENU
)
echo    [+] Node.js found

echo  [2/4] Checking Rust...
where rustc >nul 2>&1
if !errorlevel! neq 0 (
    echo  [!] Rust not found! Install from https://rustup.rs
    pause
    goto MENU
)
echo    [+] Rust found

echo  [3/4] Installing npm dependencies...
echo.
cd /d "%SCRIPT_DIR%\llm-assistant-tauri"
call npm install
if !errorlevel! neq 0 (
    echo  [!] npm install failed!
    cd /d "%SCRIPT_DIR%"
    pause
    goto MENU
)
echo    [+] npm dependencies installed

echo  [4/4] Building Tauri application...
echo    This may take 10-30 minutes...
echo.
call npm run tauri build
if !errorlevel! neq 0 (
    echo  [!] Tauri build failed!
    echo  [!] Check the build logs above
    cd /d "%SCRIPT_DIR%"
    pause
    goto MENU
)
echo.
echo    [+] Tauri application built!
echo    [+] exe file: llm-assistant-tauri\src-tauri\target\release\llm-assistant-tauri.exe
echo    [%date% %time%] Tauri build complete >> "%LOG_FILE%"

cd /d "%SCRIPT_DIR%"
echo.
pause
goto MENU

:SETUP_ENV
cls
echo =============================================
echo   Setup .env from Template
echo =============================================
echo.

if not exist ".env" (
    if exist ".env.example" (
        copy ".env.example" ".env" >nul
        echo  [+] .env created from .env.example
        echo  [!] Edit .env to match your LLM provider
        echo.
        echo  Example:
        echo    LLM_PROVIDER=ollama
        echo    LLM_MODEL=llama3.2:3b
        echo    LLM_HOST=http://localhost:11434
        echo.
        echo  Or for LM Studio:
        echo    LLM_PROVIDER=lm_studio
        echo    LLM_MODEL=qwen3.5-4b:latest
        echo    LLM_HOST=http://localhost:1234
    ) else (
        echo  [!] .env.example not found!
    )
) else (
    echo  [+] .env already exists
)
echo.
echo  Press any key to return to menu...
pause >nul
goto MENU

:INSTALL_FFMPEG
cls
echo =============================================
echo   Install FFmpeg
echo =============================================
echo.

where ffmpeg >nul 2>&1
if !errorlevel! equ 0 (
    echo  [+] FFmpeg is already installed and available in PATH
    echo.
    pause
    goto MENU
)

echo  FFmpeg not found. Would you like to download and install it?
echo.
echo  Note: this will modify the user PATH (no admin rights
echo  required, but you may need to restart the console)
echo.
set /p "ff_choice=Download FFmpeg? (y/n): "
if /i not "!ff_choice!"=="y" goto MENU

echo.
echo  [1/3] Downloading FFmpeg...
echo.

set "FFMPEG_DIR=%SCRIPT_DIR%\ffmpeg"
if not exist "%FFMPEG_DIR%" mkdir "%FFMPEG_DIR%"

powershell -Command ^
"$url = 'https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip';^
$zipPath = [System.IO.Path]::GetTempFileName() + '.zip';^
Write-Host '  Downloading FFmpeg (~50 MB)...';^
try {^
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12;^
    Invoke-WebRequest -Uri $url -OutFile $zipPath -UseBasicParsing;^
    Write-Host '  [+] Downloaded. Extracting...';^
    Expand-Archive -Path $zipPath -DestinationPath '$env:TEMP\ffmpeg_extract' -Force;^
    Remove-Item -Path $zipPath -Force;^
    $source = Join-Path '$env:TEMP\ffmpeg_extract' (Get-ChildItem '$env:TEMP\ffmpeg_extract' -Directory | Select-Object -First 1).Name;^
    Copy-Item -Path (Join-Path $source 'bin\ffmpeg.exe') -Destination '%FFMPEG_DIR%\ffmpeg.exe' -Force;^
    Remove-Item -Path '$env:TEMP\ffmpeg_extract' -Recurse -Force;^
    Write-Host '  [+] FFmpeg extracted';^
} catch {^
    Write-Host '  [-] Download error: ' $_.Exception.Message;^
    exit 1;^
}"

if !errorlevel! neq 0 (
    echo  [!] Failed to download FFmpeg automatically
    echo  [!] Download manually: https://ffmpeg.org/download.html
    echo  [!] And place ffmpeg.exe in the ffmpeg\ folder
    pause
    goto MENU
)

echo  [2/3] Adding to user PATH...
setx PATH "%FFMPEG_DIR%;%PATH%" >nul
if !errorlevel! equ 0 (
    echo    [+] FFmpeg added to user PATH
    echo    [%date% %time%] FFmpeg installed to %FFMPEG_DIR% >> "%LOG_FILE%"
) else (
    echo    [!] Failed to add to PATH (setx unavailable)
    echo    [!] Add manually: %FFMPEG_DIR% to your PATH
)

echo  [3/3] Verification...
where ffmpeg >nul 2>&1
if !errorlevel! equ 0 (
    echo    [+] FFmpeg is working!
) else (
    echo    [!] Restart the console to apply PATH changes
)

echo.
echo  [+] FFmpeg installed to: %FFMPEG_DIR%
echo.
pause
goto MENU

:FULL_INSTALL
cls
echo =============================================
echo   Full Installation
echo =============================================
echo.
echo  Will execute:
echo    1. Check environment
echo    2. Install Python dependencies
echo    3. Setup .env from template
echo    4. Download Whisper Large V3 Turbo
echo    5. Download OmniVoice
echo    6. Build Tauri application
echo.
echo  Full installation may take 30-60 minutes.
echo.
set /p "full_choice=Start full installation? (y/n): "
if /i not "!full_choice!"=="y" goto MENU

call :CHECK_ENV_SILENT

echo.
echo  === [2/6] Install Python Dependencies ===
echo.
if not exist "venv\Scripts\activate.bat" (
    python -m venv venv
    if !errorlevel! neq 0 (
        echo  [!] Failed to create venv! Aborting.
        pause
        goto MENU
    )
    echo    [+] venv created
) else (
    echo    [+] venv already exists
)
call "venv\Scripts\activate.bat"
pip install -r requirements.txt
if !errorlevel! neq 0 (
    echo  [!] Failed to install dependencies! Aborting.
    pause
    goto MENU
)
echo    [+] Dependencies installed

echo.
echo  === [3/6] Setup .env ===
echo.
if not exist ".env" (
    if exist ".env.example" (
        copy ".env.example" ".env" >nul
        echo    [+] .env created from .env.example
        echo    [!] Remember to edit .env after installation
    ) else (
        echo    [!] .env.example not found
    )
) else (
    echo    [+] .env already exists
)

echo.
echo  === [4/6] Download Whisper Large V3 Turbo ===
echo.
pip install huggingface_hub >nul 2>&1
set "WHISPER_DIR=%SCRIPT_DIR%\llm-assistant-tauri\src-tauri\target\release\openai_whisper-large-v3-turbo"
if not exist "%WHISPER_DIR%" mkdir "%WHISPER_DIR%"
python -c "from huggingface_hub import snapshot_download; snapshot_download('openai/whisper-large-v3-turbo', local_dir=r'%WHISPER_DIR:\=\\%'); print('Done')"
if !errorlevel! equ 0 (
    echo    [+] Whisper downloaded
) else (
    echo    [!] Failed to download Whisper
)
echo    [%date% %time%] Full: Whisper done >> "%LOG_FILE%"

echo.
echo  === [5/6] Download OmniVoice ===
echo.
set "OMNI_DIR=%SCRIPT_DIR%\llm-assistant-tauri\src-tauri\target\release\OmniVoice"
if not exist "%OMNI_DIR%" mkdir "%OMNI_DIR%"
python -c "from huggingface_hub import snapshot_download; snapshot_download('k2-fsa/OmniVoice', local_dir=r'%OMNI_DIR:\=\\%'); print('Done')"
if !errorlevel! equ 0 (
    echo    [+] OmniVoice downloaded
) else (
    echo    [!] Failed to download OmniVoice
)
echo    [%date% %time%] Full: OmniVoice done >> "%LOG_FILE%"

echo.
echo  === [6/6] Build Tauri Application ===
echo.
cd /d "%SCRIPT_DIR%\llm-assistant-tauri"
call npm install
if !errorlevel! neq 0 (
    echo  [!] npm install failed
    cd /d "%SCRIPT_DIR%"
    pause
    goto MENU
)
call npm run tauri build
if !errorlevel! neq 0 (
    echo  [!] Tauri build failed
    cd /d "%SCRIPT_DIR%"
    pause
    goto MENU
)
cd /d "%SCRIPT_DIR%"
echo    [+] Tauri application built!
echo    [%date% %time%] Full: Tauri build complete >> "%LOG_FILE%"

echo.
echo =============================================
echo   Full installation complete!
echo =============================================
echo.
echo  exe file: llm-assistant-tauri\src-tauri\target\release\llm-assistant-tauri.exe
echo  Don't forget:
echo    - Edit .env (LLM provider, model)
echo    - Start Ollama or LM Studio
echo    - Install: pip install omnivoice (for TTS)
echo.
pause
goto MENU

:RUN_APP
cls
echo =============================================
echo   Launch Application
echo =============================================
echo.

set "TAURI_EXE=%SCRIPT_DIR%\llm-assistant-tauri\src-tauri\target\release\llm-assistant-tauri.exe"

if exist "%TAURI_EXE%" (
    echo  [1] Launch Tauri application (exe)
)
echo  [2] Launch console mode (CLI)
echo  [3] Return to menu
echo.
set /p "run_choice=Select option: "

if "%run_choice%"=="1" (
    if exist "%TAURI_EXE%" (
        echo  Launching Tauri application...
        start "" "%TAURI_EXE%"
        echo  [+] Application launched!
    ) else (
        echo  [!] exe not found. First run option [5]
    )
    goto RUN_APP_END
)

if "%run_choice%"=="2" (
    if not exist "venv\Scripts\activate.bat" (
        echo  [!] First run option [2]
    ) else (
        echo  Launching console mode...
        echo  To return, close the window or press Ctrl+C
        echo.
        start "Local AI Assistant - CLI" cmd /c "call venv\Scripts\activate.bat && python -m src.main"
        echo  [+] CLI launched in a separate window
    )
    goto RUN_APP_END
)

if "%run_choice%"=="3" goto MENU

:RUN_APP_END
echo.
pause
goto MENU

:CHECK_ENV_SILENT
echo.
echo  Checking environment...
where python >nul 2>&1
if !errorlevel! equ 0 (echo    [+] Python OK) else (echo    [-] Python not found!)
where node >nul 2>&1
if !errorlevel! equ 0 (echo    [+] Node.js OK) else (echo    [-] Node.js not found!)
where rustc >nul 2>&1
if !errorlevel! equ 0 (echo    [+] Rust OK) else (echo    [-] Rust not found!)
echo.
exit /b 0

:EOF
echo.
echo  Thank you for using Local AI Assistant!
echo.
timeout /t 2 >nul
exit /b 0
