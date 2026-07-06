@echo off
chcp 65001 >nul 2>&1
cd /d "%~dp0"

echo === MemOmics Debug Start ===

set "HERMES_HOME=%~dp0hermes_home"
set "PYTHONPATH=%~dp0;%~dp0hermes-agent;%PYTHONPATH%"
set "MEMOMICS_PORT=8899"
set "MEMOMICS_HOST=0.0.0.0"

echo HERMES_HOME=%HERMES_HOME%
echo.

if exist ".venv\Scripts\python.exe" (
    echo Using .venv python
    .venv\Scripts\python.exe webui\server.py
) else (
    echo Using system python
    python webui\server.py
)

echo.
echo === Exit code: %errorlevel% ===
echo === MemOmics stopped. Press any key to close. ===
pause
