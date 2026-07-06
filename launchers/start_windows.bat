@echo off
REM ============================================================
REM   MemOmics-Agent Windows 启动器
REM   自动检测 Python -> 无则用内置 miniconda 创建环境
REM   用法: start.bat [port]
REM ============================================================
setlocal enabledelayedexpansion

set "SCRIPT_DIR=%~dp0"
cd /d "%SCRIPT_DIR%"
set "PORT=%~1"
if "%PORT%"=="" set "PORT=%MEMOMICS_PORT%"
if "%PORT%"=="" set "PORT=8899"
set "VENV_DIR=.venv"
set "CONDA_DIR=miniconda_env"

echo ╔══════════════════════════════════════════════╗
echo ║       MemOmics-Agent v1.0 Starting...        ║
echo ╚══════════════════════════════════════════════╝
echo.

REM === Step 1: Find Python 3.11-3.13 ===
set "PYTHON="
for %%c in (python3 python python3.13 python3.12 python3.11) do (
    if not defined PYTHON (
        where %%c >nul 2>&1
        if !errorlevel! equ 0 (
            %%c -c "import sys; sys.exit(0 if sys.version_info >= (3,11) and sys.version_info < (3,14) else 1)" >nul 2>&1
            if !errorlevel! equ 0 (
                set "PYTHON=%%c"
                echo ✅ 找到系统 Python: %%c
            )
        )
    )
)

REM === Step 2: No Python? Use bundled miniconda ===
if not defined PYTHON (
    echo ⚠️ 未找到 Python 3.11-3.13，使用内置 Miniconda...
    set "CONDA_PYTHON=%SCRIPT_DIR%miniconda_env\python.exe"
    if not exist "!CONDA_PYTHON!" (
        set "INSTALLER=%SCRIPT_DIR%miniconda\Miniconda3-latest-Windows-x86_64.exe"
        if not exist "!INSTALLER!" (
            echo ❌ 内置 miniconda 安装包未找到!
            echo    请从 https://docs.conda.io 下载 Miniconda3-latest-Windows-x86_64.exe
            echo    放到 %SCRIPT_DIR%miniconda\ 目录下
            pause
            exit /b 1
        )
        echo 📦 解压 Miniconda 到 !CONDA_DIR! ...
        start /wait "" "!INSTALLER!" /S /InstallationType=JustMe /RegisterPython=0 /D=%SCRIPT_DIR%miniconda_env
        if not exist "!CONDA_PYTHON!" (
            echo ❌ Miniconda 安装失败!
            pause
            exit /b 1
        )
    )
    set "PYTHON=!CONDA_PYTHON!"
    echo ✅ 使用 Miniconda Python: !PYTHON!
)

REM === Step 3: Create venv if not exists ===
set "VENV_PYTHON=%SCRIPT_DIR%.venv\Scripts\python.exe"
if not exist "%VENV_PYTHON%" (
    echo 🔧 创建虚拟环境...
    "%PYTHON%" -m venv "%VENV_DIR%"
    if !errorlevel! neq 0 (
        echo ⚠️ venv 创建失败，直接使用当前 Python
        set "VENV_PYTHON=%PYTHON%"
    ) else (
        echo ✅ 虚拟环境已创建
    )
)

REM === Step 4: Install dependencies ===
set "PIP="%VENV_PYTHON%" -m pip"
"%VENV_PYTHON%" -c "import fastapi" >nul 2>&1
if !errorlevel! neq 0 (
    echo 📥 安装依赖包...
    %PIP% install --upgrade pip -q
    %PIP% install -r requirements.txt -q
    if !errorlevel! neq 0 (
        echo ⚠️ 部分依赖安装失败，尝试继续...
    ) else (
        echo ✅ 依赖安装完成
    )
) else (
    echo ✅ 依赖已就绪
)

REM === Step 5: Start server ===
echo.
echo 🚀 启动 MemOmics-Agent (端口 %PORT%)...
echo    浏览器访问: http://localhost:%PORT%
echo.
"%VENV_PYTHON%" webui/server.py

endlocal
