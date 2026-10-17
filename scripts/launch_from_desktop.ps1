# MemOmics desktop-icon launcher (Windows)   v3 / 2026-10-17
# Double-clicking the MemOmics desktop icon runs this script:
#   server already running -> open the WebUI in the browser
#   not running            -> start the package launcher .bat IN THIS WINDOW
#                             (visible progress; closing the window stops MemOmics)
# Idempotent and safe to run repeatedly.
#
# 历史修复记录：
#   2026-09-10（"关掉后点图标没反应"）：本文件原为"无 BOM 的 UTF-8 + 中文字面量 '启动.bat'"，
#     Windows PowerShell 5.1 按系统代码页(GBK)解析源码 → 字面量乱码 → Test-Path 失败 →
#     静默回退到"只开浏览器"。现已带 UTF-8 BOM（打包脚本也会强制补 BOM）；
#     启动脚本定位改为三层：start.bat → 中文名 → 内容特征，任何一层命中即可，编码无关。
#   2026-10-13（"换节点后图标点不开"）：不再只看端口占用，必须 /api/health 真返回 MemOmics；
#     支持发现真实端口（memomics_home/runtime/port.txt + 8899..8909 扫描）；失败弹窗 + 留痕。
#   2026-10-17（"点图标半天没反应、以为没启动"）：
#     ① 旧版对每个候选端口都发一次 HTTP 健康检查，而本机对"没有监听的端口"建连要空等
#        ~2 秒（安全软件静默丢包），11 个端口 ≈ 23 秒纯静默。现在先用**一次 netstat 快照**
#        筛出真正 LISTENING 的端口，只对这些端口做健康校验 → 毫秒级。
#     ② 快捷方式不再带 -WindowStyle Hidden：启动窗口可见，开场就打印进度，用户能看到
#        "关闭本窗口 = 停止 MemOmics"；旧版全隐藏 → 没有任何反馈，用户会反复点击。
#     ③ 启动锁 memomics_home/runtime/launch.lock（独占创建）：连点图标不会拉起第二个实例，
#        第二次点击只会"等就绪并打开浏览器"。

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

function Say([string]$msg) {
    try { Write-Host $msg } catch { }
    Write-Log $msg
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
        $r = Invoke-WebRequest -Uri ("http://127.0.0.1:" + $p + "/api/health") -UseBasicParsing -TimeoutSec 2
        return ($r.StatusCode -eq 200 -and ($r.Content -match 'MemOmics'))
    } catch { return $false }
}

# 一次 netstat 快照 → 处于 LISTENING 的本机端口集合（哈希表）。
# 绝不直接向"没有监听的端口"发起连接：本机上那种建连要空等约 2 秒。
function Get-ListenPorts() {
    $map = @{}
    try {
        foreach ($line in (& netstat -ano)) {
            if ($line -match '^\s*TCP\s+\S+:(\d+)\s+\S+\s+LISTENING') {
                $map[[int]$Matches[1]] = $true
            }
        }
    } catch { }
    return $map
}

# 候选端口：服务自己写的 port.txt → 环境变量 → 默认区间（start.bat 会自动换端口，最多 +12）
function Get-CandidatePorts() {
    $cands = @()
    $portFile = Join-Path $root 'memomics_home\runtime\port.txt'
    if (Test-Path $portFile) {
        $raw = Get-Content $portFile -Raw -Encoding UTF8 -ErrorAction SilentlyContinue
        if ($raw -match '(\d{4,5})') { $cands += [int]$Matches[1] }
    }
    if ($env:MEMOMICS_PORT) { try { $cands += [int]$env:MEMOMICS_PORT } catch { } }
    $cands += 8899..8920
    return ($cands | Where-Object { $_ -ge 1024 } | Select-Object -Unique)
}

function Find-RunningPort([int[]]$cands) {
    $listen = Get-ListenPorts
    foreach ($c in $cands) {
        if ($listen.ContainsKey($c)) {
            if (Test-MemOmics $c) { return $c }
        }
    }
    return 0
}

function Wait-RunningPort([int[]]$cands, [int]$TimeoutSec) {
    $deadline = (Get-Date).AddSeconds($TimeoutSec)
    $tick = 0
    while ((Get-Date) -lt $deadline) {
        $p = Find-RunningPort $cands
        if ($p) { return $p }
        Start-Sleep -Milliseconds 700
        $tick = $tick + 1
        if (($tick % 7) -eq 0) { try { Write-Host -NoNewline "." } catch { } }
    }
    return 0
}

try { $Host.UI.RawUI.WindowTitle = 'MemOmics' } catch { }

Write-Log ("启动器开始：root=$root")
$cands = Get-CandidatePorts

# ---- 1) 已在运行？→ 直接开浏览器（只对 LISTENING 端口做健康校验，毫秒级） ----
$port = Find-RunningPort $cands
if ($port) {
    Write-Log ("服务已在运行（port=$port）→ 打开浏览器")
    try { Write-Host ("[MemOmics] 已在运行，正在打开浏览器 http://127.0.0.1:{0}" -f $port) } catch { }
    Open-WebUI $port
    exit 0
}
Write-Log '未发现运行中的 MemOmics（/api/health 校验均失败）→ 准备拉起启动器'

# ---- 2) 未运行：先处理启动锁（防连点重复拉起） ----
$runtimeDir = Join-Path $root 'memomics_home\runtime'
try { if (-not (Test-Path $runtimeDir)) { New-Item -ItemType Directory -Path $runtimeDir -Force | Out-Null } } catch { }
$lockPath = Join-Path $runtimeDir 'launch.lock'

$otherPid = 0
if (Test-Path $lockPath) {
    $rawPid = Get-Content $lockPath -Raw -ErrorAction SilentlyContinue
    if ($rawPid -match '(\d+)') { $otherPid = [int]$Matches[1] }
    # 锁"活着"的条件：PID 还在 + 文件时间戳够新（防 PID 被别的进程复用导致白等）
    $lockAgeMin = 999
    try { $lockAgeMin = ((Get-Date) - (Get-Item $lockPath).LastWriteTime).TotalMinutes } catch { }
    if ($otherPid -gt 0 -and $lockAgeMin -lt 15 -and (Get-Process -Id $otherPid -ErrorAction SilentlyContinue)) {
        Write-Log ("已有启动在进行（PID $otherPid）→ 等待就绪（最长 240 秒）")
        try { Write-Host "[MemOmics] 另一次启动正在进行中，正在等待服务就绪（最长 4 分钟）" } catch { }
        $port = Wait-RunningPort $cands 240
        try { Write-Host "" } catch { }
        if ($port) {
            Write-Log ("等待就绪成功（port=$port）→ 打开浏览器")
            try { Write-Host ("[MemOmics] 已就绪，正在打开浏览器 http://127.0.0.1:{0}" -f $port) } catch { }
            Open-WebUI $port
        } else {
            Write-Log ("等待超时：PID $otherPid 仍未就绪")
            try { Write-Host "[MemOmics] 等待超时：请看另一个启动窗口的提示（首次安装依赖可能较慢）。" } catch { }
        }
        exit 0
    }
    Write-Log ("清理过期启动锁（PID $otherPid 已不存在）")
    Remove-Item $lockPath -Force -ErrorAction SilentlyContinue
}

$haveLock = $false
try {
    $fs = [System.IO.File]::Open($lockPath, [System.IO.FileMode]::CreateNew, [System.IO.FileAccess]::Write, [System.IO.FileShare]::Read)
    $bytes = [System.Text.Encoding]::ASCII.GetBytes([string]$PID)
    $fs.Write($bytes, 0, $bytes.Length)
    $fs.Close()
    $haveLock = $true
} catch { $haveLock = $false }

# ---- 3) 定位启动脚本（三层，全部与编码无关） ----
$startBat = ''

# 3a) ASCII 名字优先（开发目录 / 改名过的安装包）
$asciiBat = Join-Path $root 'start.bat'
if (Test-Path $asciiBat) { $startBat = $asciiBat }

# 3b) 中文名（安装包里的启动器文件名）——本文件已带 BOM，字面量安全
if (-not $startBat) {
    $cnBat = Join-Path $root ([string]([char]0x542F) + [string]([char]0x52A8) + '.bat')
    if (Test-Path $cnBat) { $startBat = $cnBat }
}

# 3c) 内容特征兜底：启动器 .bat 里同时出现 MemOmics-Agent 与 MEMOMICS_PORT
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
    Write-Log ("拉起启动器：$startBat（窗口保持可见）")
    try {
        Write-Host ""
        Write-Host "=============================================================="
        Write-Host "  MemOmics 正在启动 ..."
        Write-Host "  - 启动日志就在本窗口，服务就绪后会自动打开浏览器"
        Write-Host "  - 首次启动/首次安装依赖可能需要几分钟，请勿关闭本窗口"
        Write-Host "  - ★ 关闭本窗口 = 停止 MemOmics"
        Write-Host "=============================================================="
        Write-Host ""
        $Host.UI.RawUI.WindowTitle = 'MemOmics — 运行中（关闭本窗口即停止）'
    } catch { }
    # 在同一个控制台里前台运行启动器：用户能看到进度，窗口就是 MemOmics 的控制台
    $proc = Start-Process -FilePath $env:ComSpec -ArgumentList '/c', ("`"$startBat`"") -WorkingDirectory $root -NoNewWindow -PassThru
    if ($proc) { $proc.WaitForExit() }
    try { Write-Host "" } catch { }
    Write-Log ("启动器已退出：$startBat")
    if ($haveLock) { Remove-Item $lockPath -Force -ErrorAction SilentlyContinue }
    exit 0
}

# ---- 4) 什么都没找到：明确告诉用户（日志 + 弹窗），不再静默 ----
$msg = "[MemOmics] 未找到启动脚本（start.bat / 启动.bat）。`n安装目录：$root`n日志：$logPath"
Write-Log "失败：未找到启动脚本（root=$root）"
if ($haveLock) { Remove-Item $lockPath -Force -ErrorAction SilentlyContinue }
Show-Popup $msg
exit 1