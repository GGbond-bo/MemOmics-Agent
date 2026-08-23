# MemOmics WebUI opener: waits for the server port, then opens the URL in a real browser.
# Uses explicit browser executables because the system default URL association may be
# broken (ShellExecute fails with "Application not found").
# Usage: powershell -NoProfile -ExecutionPolicy Bypass -File open_webui.ps1 [port]
# Shared by: launch_from_desktop.ps1 (busy branch) and start.bat (auto-open).

param([int]$Port = 8899)

$ErrorActionPreference = 'SilentlyContinue'

$url = "http://127.0.0.1:$Port"

# Wait up to ~12s for the server to start listening
# (start.bat calls this before uvicorn is up; busy branch returns immediately)
for ($i = 0; $i -lt 12; $i++) {
    $busy = netstat -ano | Select-String -Pattern (":$Port\s+\S+\s+LISTENING")
    if ($busy) { break }
    Start-Sleep -Seconds 1
}

# Explicit browser detection: first existing executable wins.
# (avoid the broken system URL association -> ShellExecute "Application not found")
$browsers = @(
    "${env:ProgramFiles(x86)}\Microsoft\Edge\Application\msedge.exe",
    "$env:ProgramFiles\Microsoft\Edge\Application\msedge.exe",
    "$env:LOCALAPPDATA\Google\Chrome\Application\chrome.exe",
    "$env:ProgramFiles\Google\Chrome\Application\chrome.exe",
    "${env:ProgramFiles(x86)}\Google\Chrome\Application\chrome.exe",
    "$env:ProgramFiles\Mozilla Firefox\firefox.exe",
    "${env:ProgramFiles(x86)}\Mozilla Firefox\firefox.exe",
    "$env:ProgramFiles\Internet Explorer\iexplore.exe"
)
foreach ($b in $browsers) {
    if (Test-Path $b) {
        Start-Process -FilePath $b -ArgumentList $url
        return
    }
}

# Last resort: system association (may fail if association is broken)
Start-Process $url
return
