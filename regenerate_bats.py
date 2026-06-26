"""Generate all .bat files for the MC Server Monitor project.

   Every file is written with a UTF-8 BOM (EF BB BF) so that the Windows
   CMD running ``chcp 65001`` can parse non-ASCII text properly and file
   content is interpreted as UTF-8.

   Usage: python regenerate_bats.py
"""
import os

HERE = os.path.dirname(os.path.abspath(__file__))
BOM = b"\xef\xbb\xbf"


# ----------------------------------------------------------------------------
# build.bat - one-file packaging via PyInstaller
# ----------------------------------------------------------------------------
BUILD = r"""
@echo off
@echo off
chcp 65001 >nul
setlocal

REM ============================================================
REM   MC Server Monitor - Windows packaging script
REM   Produces a single-file executable: dist\mcmonitor.exe
REM
REM   The resulting .exe is fully self-contained:
REM     - bundles Python interpreter
REM     - bundles Flask, requests, APScheduler
REM     - bundles templates\ and static\
REM     - creates mcmonitor.db next to the .exe at first run
REM ============================================================

cd /d "%~dp0"
echo ============================================================
echo   MC Server Monitor - packaging
echo   Target: dist\mcmonitor.exe (single-file)
echo ============================================================
echo.

where python >nul 2>nul
if errorlevel 1 (
    echo [ERROR] Python not found. Please install Python 3.10+
    echo         from https://www.python.org/downloads/
    echo         and check "Add Python to PATH" during install.
    pause
    exit /b 1
)

for /f "tokens=2 delims= " %%i in ('python -V 2^>^&1') do set PY_VER=%%i
echo [INFO] Python version detected: %PY_VER%
echo.

echo [1/5] Install / update dependencies (Flask + requests + APScheduler + PyInstaller) ...
python -m pip install --upgrade pip -i https://pypi.tuna.tsinghua.edu.cn/simple --disable-pip-version-check >nul 2>nul
python -m pip install --disable-pip-version-check ^
    -i https://pypi.tuna.tsinghua.edu.cn/simple flask requests APScheduler pyinstaller
if errorlevel 1 (
    echo [ERROR] Dependency install failed. Check your network.
    pause
    exit /b 1
)
echo   Dependencies installed.
echo.

echo [2/5] Clean previous build artifacts ...
if exist build rmdir /s /q build
if exist dist  rmdir /s /q dist
echo   Cleaned.
echo.

echo [3/5] Build single-file executable with PyInstaller ...
pyinstaller --onefile --clean --noconfirm ^
    --name mcmonitor ^
    --add-data "templates;templates" ^
    --add-data "static;static" ^
    --collect-all apscheduler ^
    --collect-all flask ^
    --collect-all werkzeug ^
    --collect-all jinja2 ^
    --collect-all itsdangerous ^
    --collect-all click ^
    --collect-all markupsafe ^
    --hidden-import=apscheduler.schedulers.background ^
    --hidden-import=apscheduler.triggers.interval ^
    --hidden-import=apscheduler.triggers.cron ^
    main.py
if errorlevel 1 (
    echo [ERROR] PyInstaller build failed.
    pause
    exit /b 1
)
echo   Build complete.
echo.

echo [4/5] Output file ...
if exist "dist\mcmonitor.exe" (
    echo   Built: %~dp0dist\mcmonitor.exe
    echo   Size:
    for %%A in ("dist\mcmonitor.exe") do echo         %%~zA bytes
    echo.
    echo ============================================================
    echo   Done! You can move mcmonitor.exe to ANY Windows folder
    echo   (or even a USB drive) and double-click to run.
    echo   The database (mcmonitor.db) will be created next to the .exe.
    echo   No Python, no Flask, no other dependency is required.
    echo ============================================================
) else (
    echo [ERROR] dist\mcmonitor.exe was NOT generated.
    pause
    exit /b 1
)

echo.
choice /c YN /m "Run mcmonitor.exe now? [Y=Yes / N=No]"
if not errorlevel 2 (
    cd /d "%~dp0dist"
    start "" "mcmonitor.exe"
)
endlocal
"""


# ----------------------------------------------------------------------------
# launch.bat - the unified launcher:
#   1) locate a python.exe (prefer runtime\ portable; fall back to system)
#   2) if the chosen python has no pip, fall back to downloading the portable
#      python instead (system Python without pip is essentially broken).
#   3) rewrite python312._pth so the portable interpreter finds Lib\site-packages
#   4) check pip; bootstrap with get-pip.py (written to %TEMP%) if missing
#   5) check flask; pip install if missing
#   6) run the app (main.py)
# ----------------------------------------------------------------------------
LAUNCH = r"""
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
"%PY_EXE%" "%PROJECT_DIR%main.py"

echo.
echo   Server stopped. Double-click this file again to restart.
echo.
pause
endlocal
"""


# ----------------------------------------------------------------------------
# README.bat - display instructions on Windows
# ----------------------------------------------------------------------------
README = r"""
@echo off
@echo off
chcp 65001 >nul
setlocal

echo ============================================================
echo   MC Server Monitor  -  usage guide
echo ============================================================
echo.
echo  Quick start (most users):
echo    - Double-click launch.bat in this folder.
echo    - It downloads Python the first time (about 10 MB),
echo      installs Flask, and opens the web UI automatically.
echo.
echo  Want a single .exe that needs NO Python installed?
echo    - On the build machine, double-click build.bat
echo    - It will create dist\mcmonitor.exe
echo    - Copy that .exe to any Windows 10/11 PC
echo    - Double-click - no Python, no pip, no install needed
echo.
echo  What each file does:
echo    - launch.bat          : unified launcher - the only file you need
echo    - build.bat           : (advanced) produce a single-file mcmonitor.exe
echo    - app.py              : the Flask web application
echo    - main.py             : entry point that calls app.py
echo    - templates\          : HTML pages for the UI
echo    - static\             : CSS / images
echo    - mcmonitor.db        : (auto-created) user + server data
echo.
echo  After running:
echo    1) Your browser opens http://127.0.0.1:5000
echo    2) Click "Register" and create a user name / password
echo    3) Log in, then add your Minecraft server (host + port)
echo    4) The dashboard shows online / players / latency / MOTD
echo.
echo  Notes:
echo    - This tool uses the vanilla Minecraft "Server List Ping"
echo      protocol over TCP. No third-party API key is required.
echo    - You do NOT need to install Python yourself - launch.bat
echo      downloads a portable, embeddable Python into runtime\.
echo    - The database (mcmonitor.db) stays in this folder;
echo      back it up if you move the project.
echo.
pause
endlocal
"""


# ----------------------------------------------------------------------------
# write helper
# ----------------------------------------------------------------------------
def _write_bat(filename, body):
    path = os.path.join(HERE, filename)
    # normalize line endings to CRLF then prefix the BOM
    body_clean = body.replace("\r\n", "\n").replace("\n", "\r\n")
    payload = BOM + body_clean.encode("utf-8")
    with open(path, "wb") as fh:
        fh.write(payload)
    size_kb = len(payload) / 1024.0
    print(f"  {filename:<22s}  {size_kb:5.1f} KB   BOM-header = {BOM.hex()}")


def main():
    print("Regenerating .bat files in:", HERE)
    _write_bat("build.bat", BUILD)
    _write_bat("launch.bat", LAUNCH)
    _write_bat("README.bat", README)
    print()
    print("Done. Copy the whole project folder to a Windows machine and")
    print("double-click launch.bat to start the monitor.")


if __name__ == "__main__":
    main()
