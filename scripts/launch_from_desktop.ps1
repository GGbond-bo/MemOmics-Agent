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

$ErrorActionPreference = 'SilentlyContinue'

$root = Split-Path -Parent $PSScriptRoot
if (-not $root -or -not (Test-Path $root)) { $root = $PSScriptRoot }
$port = $env:MEMOMICS_PORT
if (-not $port) { $port = '8899' }

function Open-WebUI {
    $ow = Join-Path $root 'scripts\open_webui.ps1'
    if (Test-Path $ow) {
        & $ow $port
    } else {
        try { Start-Process ("http://127.0.0.1:" + $port) } catch { }
    }
}

# 1) Server already listening -> just bring up the WebUI.
$busy = netstat -ano | Select-String -Pattern (":$port\s+\S+\s+LISTENING")
if ($busy) { Open-WebUI; exit 0 }

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
    Start-Process -FilePath $env:ComSpec -ArgumentList '/c', ("`"$startBat`" $port") -WorkingDirectory $root
    exit 0
}

# 3) Nothing found: tell the user instead of silently doing nothing.
Write-Host "[MemOmics] 未找到启动脚本（start.bat / 启动.bat），请检查安装目录: $root"
Open-WebUI
exit 0
