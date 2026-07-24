@echo off
chcp 65001 >nul
title MemOmics Watchdog

:: ============================================================
:: MemOmics 看门狗 — 独立进程监控，挂了自动重启
:: 用法: 双击运行，或放到 Windows 启动目录
:: ============================================================

set MEMOMICS_DIR=E:\MemOmics-Agent
set RESTART_DELAY=5
set MAX_RESTARTS=10
set HEALTH_URL=http://127.0.0.1:8765/api/sessions

set restart_count=0

:loop
echo ============================================================
echo  MemOmics Watchdog — %date% %time%
echo  工作目录: %MEMOMICS_DIR%
echo  本次已重启: %restart_count% 次
echo ============================================================

:: 找到已有的 MemOmics 进程（python server.py）
tasklist /FI "IMAGENAME eq python.exe" /FO CSV | findstr /i "server.py" >nul
if %errorlevel% equ 0 (
    echo [OK] MemOmics server 已在运行
    timeout /t 60 /nobreak >nul
    set restart_count=0
    goto loop
)

:: 健康检查 — 进程可能在但端口没响应
curl -s --max-time 5 "%HEALTH_URL%" >nul 2>&1
if %errorlevel% equ 0 (
    echo [OK] MemOmics API 响应正常
    timeout /t 60 /nobreak >nul
    set restart_count=0
    goto loop
)

:: 挂了 — 检查是否超过最大重启次数
if %restart_count% geq %MAX_RESTARTS% (
    echo [FATAL] 已重启 %restart_count% 次，超过上限 %MAX_RESTARTS%。停止监控。
    echo         请检查 %MEMOMICS_DIR%\hermes_home\logs\ 中的错误日志。
    pause
    exit /b 1
)

:: 重启
set /a restart_count+=1
echo [WARN] MemOmics 无响应！第 %restart_count% 次重启...
echo [INFO] 启动命令: cd /d %MEMOMICS_DIR% && start.bat

cd /d "%MEMOMICS_DIR%"
start "MemOmics" /D "%MEMOMICS_DIR%" cmd /c "start.bat"

echo [INFO] 等待 %RESTART_DELAY% 秒让服务启动...
timeout /t %RESTART_DELAY% /nobreak >nul

:: 验证启动
curl -s --max-time 10 "%HEALTH_URL%" >nul 2>&1
if %errorlevel% equ 0 (
    echo [OK] 重启成功，MemOmics 已恢复
) else (
    echo [WARN] 健康检查未通过，继续监控...
)

timeout /t 15 /nobreak >nul
goto loop
