@echo off
chcp 936 >nul
setlocal
set "HERE=%~dp0"
echo === MemOmics ¸üÐÂ¸²¸Ç£¨Windows£© ===
powershell -NoProfile -ExecutionPolicy Bypass -File "%HERE%update_windows.ps1" %*
echo.
pause