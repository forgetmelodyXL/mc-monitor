
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
python -m pip install --disable-pip-version-check -i https://pypi.tuna.tsinghua.edu.cn/simple flask requests APScheduler pyinstaller
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
