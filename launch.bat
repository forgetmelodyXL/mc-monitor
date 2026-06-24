
@echo off
@echo off
chcp 65001 >nul
setlocal

REM ============================================================
REM   MC Server Monitor - unified launcher (Windows)
REM
REM   This single script does everything:
REM     - finds (or auto-downloads) a Python runtime
REM     - ensures pip and Flask are installed for that runtime
REM     - starts the web UI
REM
REM   On a clean Windows machine just double-click this file and wait.
REM ============================================================

cd /d "%~dp0"

set "PROJECT_DIR=%~dp0"
set "PORTABLE_DIR=%PROJECT_DIR%runtime"
set "PORTABLE_PY=%PORTABLE_DIR%\python.exe"
set "PTH_FILE=%PORTABLE_DIR%\python312._pth"
set "GETPIP_FILE=%TEMP%\mcmonitor_get-pip.py"
set "USING_PORTABLE=0"

echo ============================================================
echo   MC Server Monitor - launcher
echo   Project : %PROJECT_DIR%
echo ============================================================
echo.

REM ------------------------------------------------------------------
REM Phase 1 : locate a Python interpreter that can run pip
REM ------------------------------------------------------------------

echo [1/5] Locate Python ...

if exist "%PORTABLE_PY%" (
    echo   Found portable Python: %PORTABLE_PY%
    set "PY_EXE=%PORTABLE_PY%"
    set "USING_PORTABLE=1"
    goto phase2
)

where python >nul 2>nul
if not errorlevel 1 (
    echo   Found system Python on PATH
    python -m pip --version >nul 2>nul
    if not errorlevel 1 (
        set "PY_EXE=python"
        echo   pip is available - using system Python
        goto phase2
    )
    echo   System Python exists but has no pip - will download portable Python instead
)

echo   Downloading portable Python runtime (about 10 MB) ...
if not exist "%PORTABLE_DIR%" mkdir "%PORTABLE_DIR%"
set "PY_EMBED_URL=https://www.python.org/ftp/python/3.12.8/python-3.12.8-embed-amd64.zip"
set "PY_ZIP=%PORTABLE_DIR%\python_embed.zip"

powershell -Command ^
    "$ErrorActionPreference='Stop'; [Net.ServicePointManager]::SecurityProtocol='Tls12'; " ^
    "Write-Host '  Downloading...'; " ^
    "Invoke-WebRequest -Uri '%PY_EMBED_URL%' -OutFile '%PY_ZIP%' -UseBasicParsing; " ^
    "Write-Host '  Download complete.'"
if errorlevel 1 (
    echo   [ERROR] Download failed. Check your internet connection.
    echo           As a fallback, place a python.exe manually in: %PORTABLE_DIR%
    pause
    exit /b 1
)

echo   Extracting to runtime\ ...
powershell -Command ^
    "$ErrorActionPreference='Stop'; " ^
    "Expand-Archive -LiteralPath '%PY_ZIP%' -DestinationPath '%PORTABLE_DIR%' -Force; " ^
    "Write-Host '  Extraction complete.'"
if errorlevel 1 (
    echo   [ERROR] Archive extraction failed.
    pause
    exit /b 1
)
del /q "%PY_ZIP%"

if not exist "%PORTABLE_PY%" (
    echo   [ERROR] %PORTABLE_PY% still missing after extraction.
    pause
    exit /b 1
)
set "PY_EXE=%PORTABLE_PY%"
set "USING_PORTABLE=1"
echo   Portable Python is ready.

REM ------------------------------------------------------------------
REM Phase 2 : rewrite python312._pth (only matters for the portable runtime)
REM ------------------------------------------------------------------

:phase2
echo.
echo [2/5] Configure module search path ...

if "%USING_PORTABLE%"=="1" (
    if exist "%PTH_FILE%" (
        powershell -Command ^
            "$content = 'python312.zip' + [char]13 + [char]10 + " ^
            "'.' + [char]13 + [char]10 + " ^
            "'Lib\site-packages' + [char]13 + [char]10 + " ^
            "'import site' + [char]13 + [char]10; " ^
            "[System.IO.File]::WriteAllText('%PTH_FILE%', $content, [System.Text.Encoding]::ASCII); " ^
            "Write-Host '  python312._pth configured.'"
        if errorlevel 1 (
            echo   [WARNING] Could not write python312._pth - pip / flask may fail.
        )
    )
) else (
    echo   (system Python used - no _pth file rewrite needed)
)

REM ------------------------------------------------------------------
REM Phase 3 : ensure pip is available in the chosen interpreter
REM ------------------------------------------------------------------

echo.
echo [3/5] Check pip ...

"%PY_EXE%" -m pip --version >nul 2>nul
if not errorlevel 1 (
    echo   pip is ready.
    goto phase4
)

echo   pip not found - bootstrapping ...
echo   Downloading get-pip.py ...
powershell -Command ^
    "$ErrorActionPreference='Stop'; [Net.ServicePointManager]::SecurityProtocol='Tls12'; " ^
    "Invoke-WebRequest -Uri 'https://bootstrap.pypa.io/get-pip.py' -OutFile '%GETPIP_FILE%' -UseBasicParsing; " ^
    "Write-Host '  get-pip.py downloaded to %GETPIP_FILE%'"
if errorlevel 1 (
    echo   [ERROR] Cannot download get-pip.py. Check your network.
    pause
    exit /b 1
)

echo   Running get-pip.py ...
"%PY_EXE%" "%GETPIP_FILE%" --no-warn-script-location
if errorlevel 1 (
    echo   [ERROR] get-pip.py failed to install pip.
    pause
    exit /b 1
)

REM verify pip works in a fresh process
"%PY_EXE%" -m pip --version >nul 2>nul
if errorlevel 1 (
    echo   [ERROR] pip still not usable after bootstrap.
    echo           Try deleting the "runtime" folder and double-clicking this file again.
    pause
    exit /b 1
)
echo   pip is ready.

REM ------------------------------------------------------------------
REM Phase 4 : ensure Flask is installed for the chosen interpreter
REM ------------------------------------------------------------------

:phase4
echo.
echo [4/5] Check Flask ...

"%PY_EXE%" -c "import flask" >nul 2>nul
if not errorlevel 1 (
    echo   Flask is ready.
    goto phase5
)

echo   Flask not found, installing ...
"%PY_EXE%" -m pip install --disable-pip-version-check flask
if errorlevel 1 (
    echo   [ERROR] Flask install failed. Check your network.
    pause
    exit /b 1
)

"%PY_EXE%" -c "import flask" >nul 2>nul
if errorlevel 1 (
    echo   [ERROR] Flask still not importable after install.
    echo           Try: %PY_EXE% -m pip install flask
    pause
    exit /b 1
)
echo   Flask is ready.

REM ------------------------------------------------------------------
REM Phase 5 : start the web UI
REM ------------------------------------------------------------------

:phase5
echo.
echo [5/5] Launching MC Server Monitor ...
echo   Python : %PY_EXE%
echo   URL    : http://127.0.0.1:5000
echo ============================================================
echo.

set "PYTHONPATH=%PROJECT_DIR%;%PYTHONPATH%"
set MCMONITOR_DEBUG=1
"%PY_EXE%" "%PROJECT_DIR%main.py"

echo.
echo   Server stopped. Double-click this file again to restart.
echo.
pause
endlocal
