@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"

echo ============================================
echo  MemOmics-Agent Windows Setup
echo ============================================
echo.

REM === STEP 1: Find or install Python ===
echo [1/4] Checking Python environment...

set "PYTHON_EXE="

call :find_python
if not "!PYTHON_EXE!"=="" goto :create_venv

REM No Python found, install Miniconda to extract directory
echo [!] Python 3.11-3.13 not found
echo [2/4] Installing Miniconda to local directory...

set "CONDA_ROOT=%~dp0miniconda_env"
echo     Location: !CONDA_ROOT!

if exist "!CONDA_ROOT!\python.exe" (
    echo [OK] Miniconda already installed
    set "PYTHON_EXE=!CONDA_ROOT!\python.exe"
    goto :create_venv
)

set "INSTALLER="
if exist "%~dp0miniconda\Miniconda3-latest-Windows-x86_64.exe" (
    set "INSTALLER=%~dp0miniconda\Miniconda3-latest-Windows-x86_64.exe"
    echo [OK] Using bundled Miniconda installer
) else (
    echo [>>] Downloading Miniconda...
    powershell -Command "Invoke-WebRequest -Uri 'https://repo.anaconda.com/miniconda/Miniconda3-latest-Windows-x86_64.exe' -OutFile '%~dp0miniconda_installer.exe'" 2>nul
    if exist "%~dp0miniconda_installer.exe" (
        set "INSTALLER=%~dp0miniconda_installer.exe"
    ) else (
        echo [XX] Download failed - please check internet connection
        echo [XX] Or install Python 3.11-3.13 manually from https://www.python.org/
        goto :error
    )
)

echo [>>] Installing Miniconda (silent, ~1-2 min)...
"!INSTALLER!" /InstallationType=JustMe /AddToPath=0 /RegisterPython=0 /S /D=!CONDA_ROOT! >nul 2>&1
if errorlevel 1 (
    echo [XX] Miniconda installation failed
    goto :error
)

timeout /t 3 /nobreak >nul
if not exist "!CONDA_ROOT!\python.exe" (
    echo [XX] python.exe not found after install
    goto :error
)

set "PYTHON_EXE=!CONDA_ROOT!\python.exe"
echo [OK] Miniconda installed

REM === STEP 3: Create venv and install dependencies ===
:create_venv
echo.
echo [3/4] Setting up virtual environment...

if exist "%~dp0.venv\Scripts\python.exe" (
    echo [i] Rebuilding .venv...
    rmdir /s /q "%~dp0.venv" 2>nul
)

echo [>>] Creating venv...
"!PYTHON_EXE!" -m venv "%~dp0.venv"
if errorlevel 1 (
    echo [XX] Failed to create virtual environment
    goto :error
)

echo [>>] Upgrading pip...
"%~dp0.venv\Scripts\python.exe" -m pip install --upgrade pip -q 2>nul

echo [>>] Installing dependencies (may take 3-8 min)...
"%~dp0.venv\Scripts\pip.exe" install -r "%~dp0requirements.txt"
if errorlevel 1 (
    echo [!] Some packages failed to install, but core may still work
)

echo [>>] Installing vision components (OCR 看图, optional)...
"%~dp0.venv\Scripts\pip.exe" install -r "%~dp0requirements-vision.txt" 2>nul
if errorlevel 1 (
    echo [!] Vision components failed (optional, app still works)
)

echo [OK] Dependencies installed

REM === STEP 4: Summary ===
echo.
echo ============================================
echo   Setup Complete
echo ============================================
echo.
echo   Startup: double-click start.bat
echo   URL:     http://localhost:8899
echo.

REM Check R
where Rscript >nul 2>&1 && echo [OK] R detected || echo [!] R not found (optional)

REM Check GPU
nvidia-smi >nul 2>&1 && echo [OK] GPU detected || echo [i] No GPU (optional)

REM Clean up installer
if exist "%~dp0miniconda_installer.exe" (
    echo.
    set /p "DEL=Delete installer to save space? [Y/N] "
    if /i "!DEL!"=="Y" del "%~dp0miniconda_installer.exe" 2>nul
)

echo.
echo ============================================
pause
exit /b 0

REM === ERROR ===
:error
echo.
echo ============================================
echo   Setup FAILED
echo   - Check disk space (5GB+ recommended)
echo   - Check antivirus settings
echo   - Or install Python 3.11-3.13 manually
echo ============================================
pause
exit /b 1

REM === SUB: find Python 3.11-3.13 ===
:find_python
for %%c in (python3.12 python3.11 python3.13 python3 python) do (
    where %%c >nul 2>&1
    if not errorlevel 1 (
        for /f "delims=" %%p in ('where %%c 2^>nul') do (
            set "TEST_PY=%%p"
            goto :test_py
        )
    )
)
exit /b

:test_py
"!TEST_PY!" --version >nul 2>&1
if errorlevel 1 exit /b
for /f "tokens=2" %%v in ('"!TEST_PY!" --version 2^>^&1') do set "FULL_VER=%%v"
for /f "tokens=1,2 delims=." %%a in ("!FULL_VER!") do (
    set "MAJOR=%%a"
    set "MINOR=%%b"
)
if "!MAJOR!"=="3" if !MINOR! geq 11 if !MINOR! leq 13 (
    set "PYTHON_EXE=!TEST_PY!"
    echo [OK] Found Python !FULL_VER! at !TEST_PY!
    exit /b
)
exit /b
