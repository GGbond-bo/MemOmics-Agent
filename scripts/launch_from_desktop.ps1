# MemOmics desktop-icon launcher (Windows)
# Double-clicking the MemOmics desktop icon runs this script:
#   server already running -> open WebUI in default browser
#   not running            -> start start.bat (which also opens the browser)
# Idempotent and safe to run repeatedly.

$ErrorActionPreference = 'SilentlyContinue'

$root = Split-Path -Parent $PSScriptRoot
$port = $env:MEMOMICS_PORT
if (-not $port) { $port = '8899' }

# Port check (same logic as start.bat: netstat LISTENING)
$busy = netstat -ano | Select-String -Pattern (":$port\s+\S+\s+LISTENING")
if ($busy) {
    Start-Process "http://127.0.0.1:$port"
    exit 0
}

$startBat = Join-Path $root 'start.bat'
if (-not (Test-Path $startBat)) { $startBat = Join-Path $root '启动.bat' }
if (Test-Path $startBat) {
    Start-Process -FilePath $env:ComSpec -ArgumentList '/c', ("`"$startBat`" $port") -WorkingDirectory $root
} else {
    Start-Process "http://127.0.0.1:$port"
}
exit 0
