@echo off
setlocal enabledelayedexpansion
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
set "MEMOMICS_HOST=0.0.0.0"

REM === Step 1: Check if already installed ===
if exist ".venv\Scripts\python.exe" goto :check_deps

REM === Step 2: Find Python ===
set "PYTHON="

REM 2a: try command-line python3 / python
call :test_cmd python3
if not "!PYTHON!"=="" goto :found
call :test_cmd python
if not "!PYTHON!"=="" goto :found

REM 2b: try explicit paths (most common install locations)
call :test_path "%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
if not "!PYTHON!"=="" goto :found
call :test_path "%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
if not "!PYTHON!"=="" goto :found
call :test_path "%LOCALAPPDATA%\Programs\Python\Python313\python.exe"
if not "!PYTHON!"=="" goto :found
call :test_path "C:\Program Files\Python312\python.exe"
if not "!PYTHON!"=="" goto :found
call :test_path "C:\Program Files\Python311\python.exe"
if not "!PYTHON!"=="" goto :found
call :test_path "C:\Python312\python.exe"
if not "!PYTHON!"=="" goto :found
call :test_path "%USERPROFILE%\miniconda3\python.exe"
if not "!PYTHON!"=="" goto :found
call :test_path "%USERPROFILE%\anaconda3\python.exe"
if not "!PYTHON!"=="" goto :found

REM === Step 3: Nothing found, use bundled miniconda ===
echo [WARN] No Python 3.11-3.13 found on this system
echo [INFO] Will install bundled Miniconda to miniconda_env\

if not exist "miniconda\Miniconda3-latest-Windows-x86_64.exe" (
    echo [ERROR] miniconda\Miniconda3-latest-Windows-x86_64.exe missing!
    echo   The package may be corrupted. Please re-extract.
    pause
    exit /b 1
)

REM Check if already installed from previous attempt
if exist "miniconda_env\python.exe" (
    echo [OK] miniconda_env already installed
    set "PYTHON=%~dp0miniconda_env\python.exe"
    goto :found
)

echo [INSTALL] Installing Miniconda ^(1-2 minutes^)...

REM Build clean destination path (no trailing backslash)
set "CDEST=%~dp0miniconda_env"
if "!CDEST:~-1!"=="\" set "CDEST=!CDEST:~0,-1!"

REM /D= MUST be last argument, no quotes around path
start /wait "" "miniconda\Miniconda3-latest-Windows-x86_64.exe" /S /InstallationType=JustMe /RegisterPython=0 /D=!CDEST!

if not exist "miniconda_env\python.exe" (
    echo [ERROR] Miniconda installation failed!
    echo   Check: enough disk space? Antivirus blocking?
    pause
    exit /b 1
)

set "PYTHON=%~dp0miniconda_env\python.exe"
echo [OK] Miniconda installed ^(Python 3.13^)

REM === Step 4: Create .venv ===
:found
if "!PYTHON!"=="" (
    echo [ERROR] No Python available. Cannot continue.
    pause
    exit /b 1
)

echo [SETUP] Creating .venv with !PYTHON!

REM Remove old broken .venv
if exist ".venv" rmdir /s /q ".venv" 2>nul

"!PYTHON!" -m venv .venv
if exist ".venv\Scripts\python.exe" (
    echo [OK] .venv created
    set "VPY=.venv\Scripts\python.exe"
) else (
    echo [WARN] .venv creation failed, using Python directly
    set "VPY=!PYTHON!"
)
goto :install_deps

REM === Step 5: Dependencies ===
:check_deps
set "VPY=.venv\Scripts\python.exe"

:install_deps
"!VPY!" -c "import fastapi" >nul 2>&1
if !errorlevel! equ 0 (
    echo [OK] Dependencies ready
    goto :start_server
)

echo [INSTALL] Installing dependencies ^(3-8 min, first time only^)...
echo.
"!VPY!" -m pip install --upgrade pip --quiet 2>nul
"!VPY!" -m pip install -r requirements.txt
if !errorlevel! neq 0 (
    echo.
    echo [WARN] Some packages failed to install.
    echo   The app may still start with limited features.
)

REM === Step 5.5: Git availability ===

echo [CHECK] Git for GitHub operations...


REM Check 0: bundled portable git
set "GIT_HOME=%~dp0git"
if exist "%GIT_HOME%\cmd\git.exe" (
    set "PATH=%GIT_HOME%\cmd;%GIT_HOME%\bin;%GIT_HOME%\usr\bin;%GIT_HOME%\mingw64\bin;%PATH%"
    echo [OK] Git found (bundled portable)
    goto :start_server
)

REM Check 1: system git
git --version >nul 2>&1

if !errorlevel! equ 0 (

    echo [OK] Git found on PATH

    goto :start_server

)

if exist "%LOCALAPPDATA%\hermes\git\cmd\git.exe" (

    set "PATH=%LOCALAPPDATA%\hermes\git\cmd;%PATH%"

    echo [OK] Git found (Hermes portable)

    goto :start_server

)

echo [WARN] Git NOT found - GitHub operations will fail!

echo   Install: https://git-scm.com/download/win

echo   Or: powershell -File hermes-agent\scripts\install.ps1

echo   MemOmics will start without git support.

timeout /t 3 >nul



REM === Step 6: Start ===
:start_server
echo.
echo [START] http://localhost:!PORT!
echo.

REM === 启动 CellBender 监控守护（如果存在）===
if exist "F:\CellBender_v2\heartbeat_v2.py" (
    echo [MONITOR] 启动 CellBender 心跳监控...
    start "CellBender-Heartbeat" /MIN python "F:\CellBender_v2\heartbeat_v2.py" --task "CellBender_26samples" --output-dir "F:\CellBender_v2\cellbender_output" --seurat-dir "F:\CellBender_v2\seurat_h5" --interval 120 --output "F:\CellBender_v2\monitor_v2.log"
)
if exist "F:\CellBender_v2\error_scanner.py" (
    echo [MONITOR] 启动 CellBender 错误扫描...
    start "CellBender-ErrorScanner" /MIN python "F:\CellBender_v2\error_scanner.py"
)

"!VPY!" webui\server.py
echo.
echo Exit code: !errorlevel!
pause
exit /b 0

REM ========== helper functions ==========

REM Test a command (python3 / python) - sets PYTHON if valid
:test_cmd
set "cmd=%~1"
!cmd! --version >nul 2>&1
if !errorlevel! neq 0 exit /b
!cmd! -c "import sys; sys.exit(0 if (3,10) <= sys.version_info < (3,14) else 1)" >nul 2>&1
if !errorlevel! neq 0 exit /b
for /f "delims=" %%p in ('!cmd! -c "import sys; print(sys.executable)"') do set "PYTHON=%%p"
echo [OK] Found: !PYTHON!
exit /b

REM Test an explicit path - sets PYTHON if exists and is valid
:test_path
set "tp=%~1"
if not exist "!tp!" exit /b
"!tp!" --version >nul 2>&1
if !errorlevel! neq 0 exit /b
set "PYTHON=!tp!"
echo [OK] Found: !PYTHON!
exit /b
