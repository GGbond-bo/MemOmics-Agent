# MemOmics 更新覆盖脚本（Windows，2026-10-09）
# 用法：双击同目录的 update_windows.bat；或 右键本文件 →「使用 PowerShell 运行」
#       加 -Yes 可跳过人工确认（自动化用）；自动找不到安装目录时可用 -InstallDir 显式指定：
#         powershell -File update_windows.ps1 -InstallDir "D:\apps\MemOmics-Agent"
# 特点：自动定位安装目录（不依赖文件夹名字）→ 只覆盖代码 → 跳过用户数据 → 不删除任何文件。
[CmdletBinding()]
param([switch]$Yes, [string]$InstallDir = '')

$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

$pkg = $PSScriptRoot
if (-not (Test-Path (Join-Path $pkg 'webui\server.py'))) {
    Write-Host "[X] 本脚本必须放在更新包（MemOmics 文件夹）内运行 —— 当前目录里没有 webui\server.py" -ForegroundColor Red
    Write-Host "    当前目录: $pkg"
    exit 1
}

function Test-InstallDir([string]$d) {
    if (-not $d -or -not (Test-Path $d)) { return $false }
    if (-not (Test-Path (Join-Path $d 'webui\server.py'))) { return $false }
    return (Test-Path (Join-Path $d 'memomics_home')) -or (Test-Path (Join-Path $d 'VERSION'))
}

Write-Host "=== MemOmics 更新覆盖（自动匹配安装目录） ===" -ForegroundColor Cyan
Write-Host "  更新包目录: $pkg"

# 1) 找候选安装目录：安装记录(.install_path) > 用户目录常见位置（浅层扫描）
$cands = New-Object System.Collections.ArrayList
function Add-Cand([string]$d) {
    if (Test-InstallDir $d) {
        $full = (Resolve-Path -LiteralPath $d).Path
        if (-not $cands.Contains($full)) { [void]$cands.Add($full) }
    }
}
Add-Cand $pkg
Add-Cand (Join-Path $pkg '..')
$home_ = $env:USERPROFILE
foreach ($sub in @('Desktop', 'Downloads', 'Documents', 'OneDrive\Desktop', 'OneDrive\Documents', '桌面', '')) {
    if (-not $home_) { break }
    $base = if ($sub) { Join-Path $home_ $sub } else { $home_ }
    if (-not (Test-Path $base)) { continue }
    Add-Cand $base
    Get-ChildItem -LiteralPath $base -Directory -ErrorAction SilentlyContinue | ForEach-Object { Add-Cand $_.FullName }
    Get-ChildItem -LiteralPath $base -Directory -ErrorAction SilentlyContinue | ForEach-Object {
        Get-ChildItem -LiteralPath $_.FullName -Directory -ErrorAction SilentlyContinue | ForEach-Object { Add-Cand $_.FullName }
    }
}

# 安装记录里的路径优先
$preferred = $null
foreach ($c in $cands) {
    $ap = Join-Path $c 'memomics_home\.install_path'
    if (Test-Path $ap) {
        $recorded = (Get-Content $ap -Raw -ErrorAction SilentlyContinue).Trim()
        if ($recorded -and (Test-InstallDir $recorded)) { $preferred = (Resolve-Path -LiteralPath $recorded).Path; break }
    }
}
if ($InstallDir) {
    if (-not (Test-InstallDir $InstallDir)) { Write-Host "[X] -InstallDir 指向的目录不像 MemOmics 安装目录: $InstallDir" -ForegroundColor Red; exit 1 }
    Write-Host "  按 -InstallDir 指定的安装目录: $((Resolve-Path -LiteralPath $InstallDir).Path)" -ForegroundColor Green
    $install = (Resolve-Path -LiteralPath $InstallDir).Path
} elseif ($preferred) {
    Write-Host "  按 memomics_home\.install_path 记录的安装目录: $preferred" -ForegroundColor Green
    $install = $preferred
} elseif ($cands.Count -eq 1) {
    $install = $cands[0]
    Write-Host "  找到 1 个候选安装目录: $install" -ForegroundColor Green
} elseif ($cands.Count -gt 1) {
    Write-Host "  找到多个候选安装目录（请选择要更新的那个）:" -ForegroundColor Yellow
    for ($i = 0; $i -lt $cands.Count; $i++) { Write-Host ("   [{0}] {1}" -f ($i + 1), $cands[$i]) }
    $sel = Read-Host "  输入编号（回车=取消）"
    if (-not $sel) { Write-Host "已取消"; exit 0 }
    $idx = [int]$sel - 1
    if ($idx -lt 0 -or $idx -ge $cands.Count) { Write-Host "[X] 编号无效"; exit 1 }
    $install = $cands[$idx]
} else {
    Write-Host "  没有自动找到安装目录。" -ForegroundColor Yellow
    Write-Host "  提示：安装目录 = 双击「启动.bat」所在的文件夹（里面能看到 webui、memomics_home）"
    $manual = Read-Host "  请直接粘贴安装目录路径（回车=取消）"
    if (-not $manual) { Write-Host "已取消"; exit 0 }
    if (-not (Test-InstallDir $manual)) { Write-Host "[X] 该目录不像 MemOmics 安装目录: $manual" -ForegroundColor Red; exit 1 }
    $install = (Resolve-Path -LiteralPath $manual).Path
}

$same = ($install.TrimEnd('\') -ieq $pkg.TrimEnd('\'))
Write-Host ""
Write-Host "  更新包: $pkg"
Write-Host "  安装目录: $install"
if ($same) { Write-Host "  （两者相同：将就地把包内代码覆盖到当前目录）" -ForegroundColor DarkGray }
if (-not $same) {
    Write-Host "  说明：只覆盖代码与产品文件；memomics_home 里的配置/记忆/会话、results、.venv 等用户数据不动。" -ForegroundColor DarkGray
}
if (-not $Yes) {
    $ok = Read-Host "  确认开始覆盖？(y/N)"
    if ($ok -notmatch '^[yY]') { Write-Host "已取消"; exit 0 }
}

# 2) 覆盖：跳过用户数据目录与用户文件
$skipDirs = @('memomics_home', 'results', 'uploads', 'log', '.venv', 'python', 'miniconda', 'miniconda_env',
              'runtime', 'node_modules', '.git', '.backups', '__pycache__', 'sessions', 'memories')
$skipFiles = @('.env', '.install_path')
$args = @($pkg, $install, '/E', '/NFL', '/NDL', '/NJH', '/NJS', '/NP', '/R:1', '/W:1')
foreach ($d in $skipDirs) { $args += @('/XD', (Join-Path $pkg $d)) }
foreach ($f in $skipFiles) { $args += @('/XF', $f) }
& robocopy @args | Out-Null
$rc = $LASTEXITCODE
if ($rc -ge 8) { Write-Host "[X] 覆盖失败（robocopy 退出码 $rc）" -ForegroundColor Red; exit 1 }

# 3) 技能库是发布内容，单独同步（其余 memomics_home 用户数据一律不动）
$srcSkills = Join-Path $pkg 'memomics_home\skills'
if (Test-Path $srcSkills) {
    $dstSkills = Join-Path $install 'memomics_home\skills'
    New-Item -ItemType Directory -Path $dstSkills -Force | Out-Null
    & robocopy $srcSkills $dstSkills /E /NFL /NDL /NJH /NJS /NP /R:1 /W:1 | Out-Null
}
if (Test-Path (Join-Path $pkg 'memomics_home\SKILLS_INDEX.md')) {
    Copy-Item (Join-Path $pkg 'memomics_home\SKILLS_INDEX.md') (Join-Path $install 'memomics_home\SKILLS_INDEX.md') -Force
}

$ver = ''
$vp = Join-Path $install 'VERSION'
if (Test-Path $vp) { $ver = (Get-Content $vp -Raw).Trim() }
Write-Host ""
Write-Host "[OK] 覆盖完成，安装目录版本号: $ver" -ForegroundColor Green
Write-Host ""
Write-Host "  ============================================================" -ForegroundColor Yellow
Write-Host "  [重要] 必须重启才生效 —— 更新只换了磁盘上的代码。" -ForegroundColor Yellow
Write-Host "         请【完全关闭】MemOmics 窗口（旧的启动.bat 控制台）后，" -ForegroundColor Yellow
Write-Host "         再重新双击「启动.bat」。若界面顶部出现""运行的是旧版本""提示，" -ForegroundColor Yellow
Write-Host "         说明进程还没重启（设置里的供应商列表、结果栏看文件都依赖新进程）。" -ForegroundColor Yellow
Write-Host "  ============================================================" -ForegroundColor Yellow
Write-Host "     重新启动时还会自动补装新版依赖（首次可能几分钟）。" -ForegroundColor Green
Write-Host "     首次启动会自动把旧的 hermes_home 数据目录迁移为 memomics_home（只搬不删）。" -ForegroundColor DarkGray