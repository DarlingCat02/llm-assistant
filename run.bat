@echo off
chcp 65001 >nul 2>&1
REM Nuzhno dlya !VENV_HOME! vostoit do kontca stroki v odnom bloke
setlocal enabledelayedexpansion
REM ============================================================================
REM Local AI Assistant - One-Click Launcher (Windows)
REM ============================================================================

echo.
echo ================================================
echo        Local AI Assistant - Zapusk
echo ================================================
echo.

REM Poluchaem direktoriyu skripta
set "SCRIPT_DIR=%~dp0"
cd /d "%SCRIPT_DIR%"

REM ----------------------------------------------------------------------------
REM 1. Proverka nalichiya virtualnogo okruzheniya
REM ----------------------------------------------------------------------------
echo [1/3] Proverka venv...

REM Venv, skopirovannuyu s drugoy mashiny, ne rabotaet: venv\pyvenv.cfg
REM vse eshchyo ukazyvaet na Python, kotorogo zdes net. Proveriaem, chto
REM zapomnennyi interpretator sushchestvuet. Zapusk samogo
REM venv\Scripts\python.exe ne delaem - on otkryvaet sistemnoe okno
REM ob oshibke i zavisaet.
set "VENV_OK="
set "VENV_HOME="
for /f "tokens=1,* delims==" %%A in ('findstr /i /b /c:"home" "venv\pyvenv.cfg" 2^>nul') do for /f "tokens=* delims= " %%B in ("%%B") do set "VENV_HOME=%%B"
REM for /f leaves a trailing space, which would break the path test
:STRIP_VENV_HOME
if defined VENV_HOME if "!VENV_HOME:~-1!"==" " (
    set "VENV_HOME=!VENV_HOME:~0,-1!"
    goto STRIP_VENV_HOME
)
REM home has no trailing backslash, hence the one below
if exist "venv\Scripts\python.exe" if exist "venv\pyvenv.cfg" if defined VENV_HOME if exist "!VENV_HOME!\python.exe" set "VENV_OK=1"
set "VENV_HOME="

if defined VENV_OK (
    echo       OK - venv naydeno
) else (
    if exist "venv\Scripts\python.exe" echo       ERROR - venv s drugoy mashiny!
    if not exist "venv\Scripts\python.exe" echo       ERROR - venv ne naydeno!
    if exist "venv" echo       Udalite papku venv pered sozdaniem novoy.
    echo.
    echo       Neobhodimo sozdat virtualnoe okruzhenie:
    echo       1. Otkroyte komandnuyu stroku v etoy papke
    echo       2. Vypolnite: python -m venv venv
    echo       3. Vypolnite: venv\Scripts\activate
    echo       4. Vypolnite: pip install -r requirements.txt
    echo.
    pause
    exit /b 1
)

REM ----------------------------------------------------------------------------
REM 2. Aktivatsiya virtualnogo okruzheniya
REM ----------------------------------------------------------------------------
echo [2/3] Aktivatsiya venv...
call "venv\Scripts\activate.bat"

if errorlevel 1 (
    echo       ERROR - Aktivatsiya ne udalas!
    echo.
    pause
    exit /b 1
) else (
    echo       OK - venv aktivirovano
)

REM ----------------------------------------------------------------------------
REM 3. Proverka nalichiya Ollama
REM ----------------------------------------------------------------------------
echo.
echo [3/3] Proverka Ollama...

where ollama >nul 2>nul
if errorlevel 1 (
    echo       WARNING - Ollama ne naydena v PATH!
    echo.
    echo       Ubedites chto Ollama ustanovlena i zapushhena:
    echo       - Skachayte s https://ollama.ai
    echo       - Zapustite: ollama serve
    echo.
    echo       Prilozhenie budet pytatysya podklyuchitsya...
) else (
    echo       OK - Ollama naydena
)

REM ----------------------------------------------------------------------------
REM 4. Zapusk prilozheniya
REM ----------------------------------------------------------------------------
echo.
echo ================================================
echo Zapusk prilozheniya...
echo ================================================
echo.

REM Zapuskayem prilozhenie
python -m src.main

REM ----------------------------------------------------------------------------
REM 5. Obrabotka zaversheniya
REM ----------------------------------------------------------------------------
echo.
echo ================================================
echo Prilozhenie zaversheno
echo ================================================
echo.

REM Ne zakryvaem okno srazu - dayom vremya prochitat logi
echo Nazhmite lyubuyu klavishu dlya vyhoda...
pause >nul
