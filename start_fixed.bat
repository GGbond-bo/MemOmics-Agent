@echo off
chcp 65001 >nul 2>&1
cd /d "%~dp0"

set "PORT=%~1"
if "%PORT%"=="" set "PORT=8899"

echo ============================================================
echo         MemOmics-Agent v2.0 Starting...
echo ============================================================
echo.

set "HERMES_HOME=%~dp0hermes_home"
set "PYTHONPATH=%~dp0;%~dp0hermes-agent;%PYTHONPATH%"
set "MEMOMICS_PORT=%PORT%"
REM 默认仅监听本机（127.0.0.1）。如需局域网访问：set "MEMOMICS_HOST=0.0.0.0"

REM === Step 1: Check .venv ===
if exist ".venv\Scripts\python.exe" goto :have_venv

REM === Step 2: Find system Python ===
set "PYTHON="
for %%c in (python3 python python3.13 python3.12 python3.11) do (
    where %%c >nul 2>&1
    if !errorlevel! equ 0 (
        %%c -c "import sys; sys.exit(0 if sys.version_info >= (3,11) and sys.version_info < (3,14) else 1)" >nul 2>&1
        if !errorlevel! equ 0 (
            set "PYTHON=%%c"
            echo [OK] Found system Python: %%c
        )
    )
)

REM === Step 3: No Python? Use miniconda ===
if not "%PYTHON%"=="" goto :create_venv
echo [WARN] Python 3.11-3.13 not found, using bundled Miniconda...
if not exist "miniconda_env\python.exe" (
    if not exist "miniconda\Miniconda3-latest-Windows-x86_64.exe" (
        echo [ERROR] Bundled miniconda installer not found!
        pause
        exit /b 1
    )
    echo [INSTALL] Extracting Miniconda...
    start /wait "" "miniconda\Miniconda3-latest-Windows-x86_64.exe" /S /InstallationType=JustMe /RegisterPython=0 /D=%~dp0miniconda_env
)
set "PYTHON=miniconda_env\python.exe"
echo [OK] Using Miniconda Python

:create_venv
echo [SETUP] Creating virtual environment...
"%PYTHON%" -m venv .venv
if not exist ".venv\Scripts\python.exe" goto :no_venv
echo [OK] Virtual environment created

:have_venv
echo [OK] Using .venv
.venv\Scripts\python.exe -c "import fastapi" >nul 2>&1
if !errorlevel! neq 0 (
    echo [INSTALL] Installing dependencies (2-3 minutes)...
    .venv\Scripts\python.exe -m pip install --upgrade pip -q
    .venv\Scripts\python.exe -m pip install -r requirements.txt -q
    echo [OK] Dependencies installed
) else (
    echo [OK] Dependencies ready
)
echo.
echo [START] MemOmics on port %PORT%...
echo    URL: http://localhost:%PORT%
echo.
.venv\Scripts\python.exe webui\server.py
echo.
echo MemOmics stopped.
pause
exit /b 0

:no_venv
echo [WARN] venv creation failed, using system Python directly
"%PYTHON%" -c "import fastapi" >nul 2>&1
if !errorlevel! neq 0 (
    echo [INSTALL] Installing dependencies (2-3 minutes)...
    "%PYTHON%" -m pip install --upgrade pip -q
    "%PYTHON%" -m pip install -r requirements.txt -q
    echo [OK] Dependencies installed
) else (
    echo [OK] Dependencies ready
)
echo.
echo [START] MemOmics on port %PORT%...
echo    URL: http://localhost:%PORT%
echo.
"%PYTHON%" webui\server.py
echo.
echo MemOmics stopped.
pause
