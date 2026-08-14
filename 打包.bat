@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"

set "RT=runtime\python"
set "PY_VER=3.12.10"
set "EMBED_URL=https://www.python.org/ftp/python/%PY_VER%/python-%PY_VER%-embed-amd64.zip"
set "PIP_URL=https://bootstrap.pypa.io/get-pip.py"
set "ML=0"
set "NOREBUILD=0"
if "%~1"=="--ml" set "ML=1"
if "%~2"=="--ml" set "ML=1"
if "%~1"=="--norebuild" set "NOREBUILD=1"
if "%~2"=="--norebuild" set "NOREBUILD=1"

echo ============================================================
echo   MemOmics 便携打包 — 目标机解压即用，无需装 Python
echo ============================================================
echo.

REM ============================================================
REM  1. 构建便携运行时（官方嵌入版 Python + 预装全部依赖）
REM ============================================================
if "%NOREBUILD%"=="1" goto :skip_runtime

if not exist "%RT%\python.exe" (
    echo [1/3] 下载官方嵌入版 Python %PY_VER% (~11MB)...
    if not exist "runtime" mkdir runtime
    powershell -Command "Invoke-WebRequest -Uri '%EMBED_URL%' -OutFile 'runtime\embed.zip'" 2>nul
    if not exist "runtime\embed.zip" (
        echo [ERROR] 嵌入版 Python 下载失败，请检查网络
        pause
        exit /b 1
    )
    powershell -Command "Expand-Archive -Path 'runtime\embed.zip' -DestinationPath '%RT%' -Force" 2>nul
    del "runtime\embed.zip" /q >nul 2>&1
    if not exist "%RT%\python.exe" (
        echo [ERROR] 解压失败
        pause
        exit /b 1
    )
    REM 补丁 ._pth：启用 site-packages（嵌入版默认关闭，这是关键一步）
    (echo python312.zip& echo .& echo Lib\site-packages& echo import site) > "%RT%\python312._pth"
    echo [OK] 嵌入版 Python 就绪
)

if not exist "%RT%\Scripts\pip.exe" (
    echo [2/3] 引导 pip...
    powershell -Command "Invoke-WebRequest -Uri '%PIP_URL%' -OutFile 'runtime\get-pip.py'" 2>nul
    "%RT%\python.exe" "runtime\get-pip.py" --no-warn-script-location --quiet 2>nul
    del "runtime\get-pip.py" /q >nul 2>&1
)

echo [3/3] 安装依赖到便携运行时（几分钟，装过自动跳过）...
if not exist "runtime\.deps_ok" (
    "%RT%\python.exe" -m pip install --upgrade pip --quiet 2>nul
    "%RT%\python.exe" -m pip install -r requirements.txt -r requirements-vision.txt
    if errorlevel 1 (
        echo [WARN] 部分包安装失败
    ) else (
        echo installed > "runtime\.deps_ok"
    )
) else (
    echo [OK] 依赖已就绪
)
if "%ML%"=="1" (
    if not exist "runtime\.ml_ok" (
        echo [ML] 安装 torch-cpu（约 1GB，仅 --ml 模式）...
        "%RT%\python.exe" -m pip install torch --index-url https://download.pytorch.org/whl/cpu 2>nul
        echo installed > "runtime\.ml_ok"
    )
)

:skip_runtime
if not exist "%RT%\python.exe" (
    echo [ERROR] 便携运行时不存在。去掉 --norebuild 重新运行。
    pause
    exit /b 1
)

REM ============================================================
REM  2. 组装打包目录（排除用户数据/密钥/.venv/开发文件）
REM ============================================================
set "STAGE=%TEMP%\memomics_portable"
if exist "%STAGE%" rmdir /s /q "%STAGE%"
mkdir "%STAGE%"

echo.
echo [打包] 复制文件（排除用户数据与密钥）...
robocopy "%~dp0" "%STAGE%" /E /NFL /NDL /NJH /NJS /NP /XF *.pyc /XD ^
    .venv .git .backups node_modules miniconda_env miniconda __pycache__ ^
    results hermes_home\sessions hermes_home\memories hermes_home\session_anchors ^
    hermes_home\logs hermes_home\cache hermes_home\cron hermes_home\envs ^
    hermes_home\checkpoints hermes_home\hooks hermes_home\sandboxes ^
    hermes_home\runtime hermes_home\scripts hermes_home\image_cache ^
    hermes_home\audio_cache hermes_home\lsp hermes_home\pairing ^
    hermes_home\storages hermes_home\weixin >nul
REM 密钥文件绝不进包（首启时由 start.bat 从模板生成）
del "%STAGE%\hermes_home\config.yaml" /q >nul 2>&1
del "%STAGE%\hermes_home\provider_keys.json" /q >nul 2>&1
del "%STAGE%\hermes_home\model_config.json" /q >nul 2>&1
del "%STAGE%\hermes_home\.credentials.yaml" /q >nul 2>&1
del "%STAGE%\venv_deps_ok.txt" /q >nul 2>&1
del "%STAGE%\venv_vision_ok.txt" /q >nul 2>&1
del "%STAGE%\.install_path" /q >nul 2>&1

REM ============================================================
REM  3. 压缩
REM ============================================================
for /f "tokens=2 delims==" %%i in ('wmic os get localdatetime /value ^| find "="') do set "DT=%%i"
set "DT=!DT:~0,8!"
set "ZIP=%~dp0MemOmics-portable-!DT!.zip"
if exist "%ZIP%" del "%ZIP%" /q

echo [压缩] 生成 %ZIP% （大文件压缩需几分钟）...
powershell -Command "Compress-Archive -Path '%STAGE%\*' -DestinationPath '%ZIP%' -CompressionLevel Optimal" 2>nul
if not exist "%ZIP%" (
    echo [回退] Compress-Archive 失败，改用 tar...
    tar -a -cf "%ZIP%" -C "%STAGE%" . 2>nul
)
rmdir /s /q "%STAGE%" >nul 2>&1

if exist "%ZIP%" (
    for %%f in ("%ZIP%") do (
        set /a "MB=%%~zf/1024/1024"
        echo.
        echo ============================================================
        echo  打包完成: %%~nxf  (!MB! MB)
        echo  目标机: 解压 → 双击 start.bat → 3 秒后浏览器自动打开
        echo ============================================================
    )
) else (
    echo [ERROR] 压缩失败
)
pause
exit /b 0
