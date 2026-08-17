@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"

set "PORT=%~1"
if "%PORT%"=="" set "PORT=8899"

echo ============================================================
echo         MemOmics-Agent v2.0  —  解压即用一键启动
echo ============================================================
echo.

REM --- 端口占用检测（已有实例运行则不重复启动/不重复开浏览器）---
netstat -ano | findstr /r /c:":%PORT% .*LISTENING" >nul 2>&1
if not errorlevel 1 (
    echo [INFO] MemOmics 已在运行 http://127.0.0.1:%PORT%
    echo        请使用已打开的页面，不重复启动。
    echo.
    pause
    exit /b 0
)

set "HERMES_HOME=%~dp0hermes_home"
set "PYTHONPATH=%~dp0;%~dp0hermes-agent;%PYTHONPATH%"
set "MEMOMICS_PORT=%PORT%"

REM --- 首次安装：config.yaml 不存在时从模板生成（升级保留用户配置）---
if not exist "%HERMES_HOME%\config.yaml" (
    if exist "%HERMES_HOME%\config.yaml.example" (
        copy /y "%HERMES_HOME%\config.yaml.example" "%HERMES_HOME%\config.yaml" >nul
        echo [INFO] 已生成默认 config.yaml。API Key 请在 WebUI 设置页填写。
    )
)
set "MEMOMICS_RUN_GATE=1"

REM ============================================================
REM  1. 定位 Python（.venv 优先；没有就找系统 Python 自动创建）
REM ============================================================
set "PYTHON="

if exist ".venv\Scripts\python.exe" (
    set "PYTHON=%~dp0.venv\Scripts\python.exe"
    goto :check_deps
)

set "BASE_PYTHON="
for %%c in (python3.12 python3.11 python3.13 python3 python) do (
    where %%c >nul 2>&1
    if not errorlevel 1 (
        for /f "delims=" %%p in ('where %%c 2^>nul') do (
            if not defined BASE_PYTHON set "BASE_PYTHON=%%p"
        )
    )
)
if not defined BASE_PYTHON (
    for %%d in (
        "%LOCALAPPDATA%\Programs\Python\Python312"
        "%LOCALAPPDATA%\Programs\Python\Python311"
        "%LOCALAPPDATA%\Programs\Python\Python313"
        "C:\Program Files\Python312"
        "C:\Python312"
    ) do (
        if not defined BASE_PYTHON if exist "%%~d\python.exe" set "BASE_PYTHON=%%~d\python.exe"
    )
)
if not defined BASE_PYTHON (
    echo [WARN] 未找到系统 Python —— 使用随包内置 Miniconda（发布包自带 miniconda\ 目录时）。
    set "CONDA_PY=%~dp0miniconda_env\python.exe"
    if not exist "!CONDA_PY!" (
        set "CONDA_INSTALLER=%~dp0miniconda\Miniconda3-latest-Windows-x86_64.exe"
        if not exist "!CONDA_INSTALLER!" (
            echo [ERROR] 未找到 Python 3.11-3.13，且包内无 Miniconda 安装器。
            echo         方案1: 运行 install.bat（自动装 Miniconda）
            echo         方案2: 手动安装 https://www.python.org/downloads/
            pause
            exit /b 1
        )
        echo [INSTALL] 静默安装内置 Miniconda（2-5 分钟）...
        start /wait "" "!CONDA_INSTALLER!" /S /InstallationType=JustMe /RegisterPython=0 /AddToPath=0 /D=%~dp0miniconda_env
        if not exist "!CONDA_PY!" (
            echo [ERROR] Miniconda 安装失败！
            pause
            exit /b 1
        )
    )
    set "BASE_PYTHON=!CONDA_PY!"
    echo [OK] 使用内置 Miniconda Python
)

echo [SETUP] 首次运行：用 %BASE_PYTHON% 创建 .venv ...
"%BASE_PYTHON%" -m venv ".venv"
if errorlevel 1 (
    echo [ERROR] 创建 .venv 失败
    pause
    exit /b 1
)
set "PYTHON=%~dp0.venv\Scripts\python.exe"
echo [OK] .venv 创建完成

:check_deps
echo [CHECK] Python: "%PYTHON%"

REM --- 环境校准 + R 检测 ---
"%PYTHON%" "%~dp0scripts\validate_env.py" >nul 2>&1
REM 旧安装自愈：文件级修复迁移（幂等，失败不影响启动）
"%PYTHON%" "%~dp0scripts\apply_fix_bundle.py" >nul 2>&1
"%PYTHON%" "%~dp0scripts\validate_env.py" --r-bin > "%TEMP%\memomics_rbin.txt" 2>nul
for /f "usebackq delims=" %%r in ("%TEMP%\memomics_rbin.txt") do set "R_BIN=%%r"
del "%TEMP%\memomics_rbin.txt" >nul 2>&1
if exist "%R_BIN%\Rscript.exe" (
    set "PATH=%R_BIN%;%PATH%"
    echo [CHECK] R: %R_BIN%\Rscript.exe
) else (
    echo [INFO] R 未检测到（可选；R 分析如 Seurat 需要）
)

REM ============================================================
REM  2. 依赖安装（两类独立标记，装成功一次就不再装）
REM ============================================================
set "DEPS_MARK=%~dp0.venv_deps_ok.txt"
set "VISION_MARK=%~dp0.venv_vision_ok.txt"

if exist "!DEPS_MARK!" goto :vision_install
echo [INSTALL] 首次安装核心依赖（3-8 分钟，仅此一次）...
"%PYTHON%" -m pip install --upgrade pip --quiet 2>nul
"%PYTHON%" -m pip install -r "%~dp0requirements.txt"
if errorlevel 1 (
    echo [WARN] 部分核心包安装失败（下次启动会自动重试）
) else (
    echo installed > "!DEPS_MARK!"
    echo [OK] 核心依赖安装完成
)

:vision_install
if exist "!VISION_MARK!" goto :deps_done
echo [INSTALL] 安装读图组件（OCR 看图，约 200MB，仅此一次）...
"%PYTHON%" -m pip install -r "%~dp0requirements-vision.txt"
if errorlevel 1 (
    echo [INFO] 读图组件未安装成功（可选，不影响其他功能；下次自动重试）
) else (
    echo installed > "!VISION_MARK!"
    echo [OK] 读图组件安装完成
)

:deps_done
echo [OK] 依赖就绪

REM ============================================================
REM  3. 启动（前台运行，关窗即停）
REM ============================================================
if "%MEMOMICS_SKIP_RUN%"=="1" (
    echo [TEST] MEMOMICS_SKIP_RUN=1 — 环境就绪，跳过启动。
    pause
    exit /b 0
)

echo.
echo [START] http://127.0.0.1:%PORT%
echo         3 秒后自动打开浏览器（如未打开请手动访问）
echo         关闭本窗口 = 停止 MemOmics
echo.

REM 延迟自动开浏览器（不阻塞启动）
start "" cmd /c "timeout /t 3 /nobreak >nul & start http://127.0.0.1:%PORT%"

REM CellBender 心跳监控（仅当本机存在时启用，其他机器自动跳过）
if exist "PROJECT_DATA_DIR\heartbeat_v2.py" (
    echo [MONITOR] CellBender heartbeat...
    start "CellBender-Heartbeat" /MIN "%PYTHON%" "PROJECT_DATA_DIR\heartbeat_v2.py" --task "CellBender_26samples" --output-dir "PROJECT_DATA_DIR\cellbender_output" --seurat-dir "PROJECT_DATA_DIR\seurat_h5" --interval 120 --output "PROJECT_DATA_DIR\monitor_v2.log"
)

"%PYTHON%" webui\server.py
echo.
echo Exit code: %errorlevel%
pause
exit /b 0
