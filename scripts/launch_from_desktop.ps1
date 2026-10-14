# MemOmics desktop-icon launcher (Windows)
# Double-clicking the MemOmics desktop icon runs this script:
#   server already running -> open WebUI in browser
#   not running            -> start the package launcher .bat (which opens the browser)
# Idempotent and safe to run repeatedly.
#
# 2026-09-10 修复（"关掉 MemOmics 后点桌面图标没反应"）：
#   原因一：本文件原为"无 BOM 的 UTF-8 + 中文字面量 '启动.bat'"，Windows PowerShell 5.1
#           按系统代码页(GBK)解析源码 → 字面量变乱码 → Test-Path 失败 → 静默回退到
#           "只开浏览器"分支。现已带 UTF-8 BOM（打包脚本也会强制补 BOM）。
#   原因二：仅靠中文字面量太脆。现按 start.bat → 中文名启动器 → 内容特征 三层定位，
#           任何一层命中即可，且完全编码无关。
#
# 2026-10-13 硬化（"换了节点后桌面图标点不开、启动.bat 正常"）：
#   ① 不再只看 netstat 端口占用：必须 /api/health 真的返回 MemOmics 才算"已在运行"
#      （换节点后 8899 常被别的进程占用 → 旧逻辑会误判"已运行"并只打开别人的页面）；
#   ② 自动发现真实端口：优先读服务写下的 memomics_home/runtime/port.txt，
#      其次扫 8899..8909（服务被占端口时会自动换端口，图标脚本必须跟着走）；
#   ③ 全程写 log/desktop_launch.log；找不到启动脚本时**弹提示框**（不再静默什么都不发生）。

$ErrorActionPreference = 'SilentlyContinue'

$root = Split-Path -Parent $PSScriptRoot
if (-not $root -or -not (Test-Path $root)) { $root = $PSScriptRoot }

$logDir = Join-Path $root 'log'
try { if (-not (Test-Path $logDir)) { New-Item -ItemType Directory -Path $logDir -Force | Out-Null } } catch { }
$logPath = Join-Path $logDir 'desktop_launch.log'

function Write-Log([string]$msg) {
    try {
        Add-Content -Path $logPath -Value ("[{0}] {1}" -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $msg) -Encoding UTF8
    } catch { }
}

function Show-Popup([string]$msg, [int]$icon = 48) {
    try { (New-Object -ComObject WScript.Shell).Popup($msg, 25, 'MemOmics', $icon) | Out-Null } catch {
        try { Write-Host $msg } catch { }
    }
}

function Open-WebUI([int]$p) {
    $ow = Join-Path $root 'scripts\open_webui.ps1'
    if (Test-Path $ow) {
        & $ow $p
    } else {
        try { Start-Process ("http://127.0.0.1:" + $p) } catch { }
    }
}

function Test-MemOmics([int]$p) {
    # 只认"真的是 MemOmics"的监听：/api/health 返回 200 且内容含 MemOmics
    try {
        $r = Invoke-WebRequest -Uri ("http://127.0.0.1:" + $p + "/api/health") -UseBasicParsing -TimeoutSec 3
        return ($r.StatusCode -eq 200 -and ($r.Content -match 'MemOmics'))
    } catch { return $false }
}

Write-Log ("启动器开始：root=$root")

# ---- 端口发现（服务可能不在默认端口） ----
$port = 0
$portFile = Join-Path $root 'memomics_home\runtime\port.txt'
if (Test-Path $portFile) {
    $raw = Get-Content $portFile -Raw -Encoding UTF8 -ErrorAction SilentlyContinue
    if ($raw -match '(\d{4,5})') {
        $cand = [int]$Matches[1]
        if (Test-MemOmics $cand) { $port = $cand; Write-Log ("端口来自 runtime/port.txt：$cand") }
        else { Write-Log ("runtime/port.txt 记录 $cand，但 /api/health 不是 MemOmics（忽略）") }
    }
}
if (-not $port) {
    $cands = @()
    if ($env:MEMOMICS_PORT) { try { $cands += [int]$env:MEMOMICS_PORT } catch { } }
    $cands += 8899..8909
    foreach ($cand in ($cands | Where-Object { $_ -ge 1024 } | Select-Object -Unique)) {
        if (Test-MemOmics $cand) { $port = $cand; Write-Log ("扫描发现 MemOmics 在端口 $cand"); break }
    }
}

# 1) Server already running -> just bring up the WebUI.
if ($port) {
    Write-Log ("服务已在运行（port=$port）→ 打开浏览器")
    Open-WebUI $port
    exit 0
}
Write-Log '未发现运行中的 MemOmics（/api/health 校验均失败）→ 准备拉起启动器'

# 2) Locate the launcher .bat (three layers, all encoding-independent).
$startBat = ''

# 2a) ASCII name first (dev checkout / renamed packages)
$asciiBat = Join-Path $root 'start.bat'
if (Test-Path $asciiBat) { $startBat = $asciiBat }

# 2b) Chinese name (the packaged launcher filename) — safe now that this file has a BOM
if (-not $startBat) {
    $cnBat = Join-Path $root ([string]([char]0x542F) + [string]([char]0x52A8) + '.bat')
    if (Test-Path $cnBat) { $startBat = $cnBat }
}

# 2c) Content signature fallback: the launcher .bat declares both banners below.
if (-not $startBat) {
    $cand = Get-ChildItem $root -Filter '*.bat' -File -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -notmatch '(?i)^(run_debug|install|watchdog)' } |
        Where-Object {
            $c = Get-Content $_.FullName -Raw -Encoding Default -ErrorAction SilentlyContinue
            $c -and ($c -match 'MemOmics-Agent') -and ($c -match 'MEMOMICS_PORT')
        } | Select-Object -First 1
    if ($cand) { $startBat = $cand.FullName }
}

if ($startBat -and (Test-Path $startBat)) {
    Write-Log ("拉起启动器：$startBat")
    # 没找到运行中的实例时端口一律交给启动器自己决定（它会自动换端口并写到 runtime/port.txt）
    Start-Process -FilePath $env:ComSpec -ArgumentList '/c', ("`"$startBat`"") -WorkingDirectory $root
    exit 0
}

# 3) Nothing found: 明确告诉用户（日志 + 弹窗），不再静默
$msg = "[MemOmics] 未找到启动脚本（start.bat / 启动.bat）。`n安装目录：$root`n日志：$logPath"
Write-Log "失败：未找到启动脚本（root=$root）"
Show-Popup $msg
Open-WebUI 8899
exit 0