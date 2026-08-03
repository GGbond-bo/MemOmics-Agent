@echo off
setlocal
cd /d "%~dp0"

set "PORT=%~1"
if "%PORT%"=="" set "PORT=8899"

echo ============================================================
echo         MemOmics-Agent v2.0
echo ============================================================
echo.

set "HERMES_HOME=%~dp0hermes_home"
set "PYTHONPATH=%~dp0;%~dp0hermes-agent;%PYTHONPATH%"
set "MEMOMICS_PORT=%PORT%"
REM 默认仅监听本机（127.0.0.1）。如需局域网访问：set "MEMOMICS_HOST=0.0.0.0"

REM --- Find Python ---
set "PYTHON="

REM Check .venv first
if exist ".venv\Scripts\python.exe" (
    set "PYTHON=%~dp0.venv\Scripts\python.exe"
    goto :check_deps
)

REM Check system python3 / python
python3 --version >nul 2>&1
if %errorlevel% equ 0 (
    for /f "delims=" %%p in ('python3 -c "import sys; print(sys.executable)"') do set "PYTHON=%%p"
    goto :check_deps
)

python --version >nul 2>&1
if %errorlevel% equ 0 (
    for /f "delims=" %%p in ('python -c "import sys; print(sys.executable)"') do set "PYTHON=%%p"
    goto :check_deps
)

REM Check explicit paths
for %%d in (
    "%LOCALAPPDATA%\Programs\Python\Python312"
    "%LOCALAPPDATA%\Programs\Python\Python311"
    "C:\Program Files\Python312"
    "C:\Python312"
) do (
    if exist "%%~d\python.exe" (
        set "PYTHON=%%~d\python.exe"
        goto :check_deps
    )
)

echo [ERROR] Python 3.11-3.13 not found.
pause
exit /b 1

:check_deps
echo [CHECK] Python: "%PYTHON%"
"%PYTHON%" -c "import fastapi" >nul 2>&1
if %errorlevel% equ 0 (
    echo [OK] Dependencies ready
    goto :start_server
)

echo [INSTALL] Installing dependencies (first time, 3-8 min)...
"%PYTHON%" -m pip install --upgrade pip --quiet 2>nul
"%PYTHON%" -m pip install -r requirements.txt
if %errorlevel% neq 0 (
    echo [WARN] Some packages failed to install. App may start with limited features.
)

:start_server
echo.
echo [START] http://localhost:%PORT%
echo.

REM Launch CellBender monitor daemon (if present)
if exist "F:\CellBender_v2\heartbeat_v2.py" (
    echo [MONITOR] Starting CellBender heartbeat monitor...
    start "CellBender-Heartbeat" /MIN python "F:\CellBender_v2\heartbeat_v2.py" --task "CellBender_26samples" --output-dir "F:\CellBender_v2\cellbender_output" --seurat-dir "F:\CellBender_v2\seurat_h5" --interval 120 --output "F:\CellBender_v2\monitor_v2.log"
)
if exist "F:\CellBender_v2\error_scanner.py" (
    echo [MONITOR] Starting CellBender error scanner...
    start "CellBender-ErrorScanner" /MIN python "F:\CellBender_v2\error_scanner.py"
)

"%PYTHON%" webui\server.py
echo.
echo Exit code: %errorlevel%
pause
exit /b 0
