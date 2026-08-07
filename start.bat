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

REM --- 首次安装检测：config.yaml 不存在时从模板生成（升级保留用户已有配置）---
if not exist "%HERMES_HOME%\config.yaml" (
    if exist "%HERMES_HOME%\config.yaml.example" (
        copy /y "%HERMES_HOME%\config.yaml.example" "%HERMES_HOME%\config.yaml" >nul
        echo [INFO] 已生成默认 config.yaml（首次安装）。API Key 请在 WebUI 设置页填写。
    )
)
REM P1-A: 任务完成闸门（防老任务被自动重启）——默认开启，出问题可删此行回退
set "MEMOMICS_RUN_GATE=1"
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

REM --- 环境校准: validate_env 校验/修复路径 + R 默认版本对齐 ---
"%PYTHON%" "%~dp0scripts\validate_env.py" >nul 2>&1
"%PYTHON%" "%~dp0scripts\validate_env.py" --r-bin > "%TEMP%\memomics_rbin.txt" 2>nul
for /f "usebackq delims=" %%r in ("%TEMP%\memomics_rbin.txt") do set "R_BIN=%%r"
del "%TEMP%\memomics_rbin.txt" >nul 2>&1
if exist "%R_BIN%\Rscript.exe" (
    set "PATH=%R_BIN%;%PATH%"
    echo [CHECK] R: %R_BIN%\Rscript.exe
)
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
echo [START] http://127.0.0.1:%PORT%
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

REM 前台运行 server（2026-08-08 恢复单窗口模式）。
REM server 就绪后由 server.py 自己自动打开浏览器（webbrowser 调用默认浏览器，
REM 不会像 explorer.exe 那样弹"找不到"错误框），本窗口显示运行日志。
"%PYTHON%" webui\server.py
echo.
echo Exit code: %errorlevel%
pause
exit /b 0
