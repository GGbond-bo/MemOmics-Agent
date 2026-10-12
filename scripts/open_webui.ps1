# MemOmics WebUI opener: waits until the WebUI is REALLY ready, then opens the URL in a real browser.
# Uses explicit browser executables because the system default URL association may be
# broken (ShellExecute fails with "Application not found").
# Usage: powershell -NoProfile -ExecutionPolicy Bypass -File open_webui.ps1 [port]
# Shared by: launch_from_desktop.ps1 (busy branch) and start.bat (auto-open).
#
# 2026-10-12 修复（用户反馈）：旧版只等 TCP 端口 LISTENING —— uvicorn 绑定端口后还要跑
# startup（迁移/技能索引/缓存预热），此时浏览器提前打开会看到报错页，用户以为安装失败。
# 现在改为轮询 /api/health（要求返回 MemOmics 标记）才算“加载完成”，再打开浏览器。

param([int]$Port = 8899, [int]$TimeoutSec = 180)

$ErrorActionPreference = 'SilentlyContinue'

$url = "http://127.0.0.1:$Port"

$ready = $false
$deadline = (Get-Date).AddSeconds($TimeoutSec)
while ((Get-Date) -lt $deadline) {
    try {
        $r = Invoke-WebRequest -UseBasicParsing -TimeoutSec 3 "$url/api/health"
        if ($r.StatusCode -eq 200 -and ($r.Content -match 'MemOmics')) {
            # 更新场景：旧进程还在跑（health 带 restart_required=true）时不能算就绪，
            # 否则打开的是"正在被替换的旧界面"。等它切到新代码再开。
            if ($r.Content -match '"restart_required"\s*:\s*true') {
                Start-Sleep -Milliseconds 700
                continue
            }
            $ready = $true
            break
        }
    } catch { }
    Start-Sleep -Milliseconds 700
}

if ($ready) {
    # 就绪后再给前端一点时间完成首屏资源加载，避免"打开即白屏"的观感
    Start-Sleep -Milliseconds 500
} else {
    Write-Host "[WARN] $url/api/health 在 $TimeoutSec 秒内未就绪（可能依赖安装较慢），仍打开浏览器；请看启动窗口的日志。"
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