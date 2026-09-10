# MemOmics 桌面图标创建脚本（Windows）
# 用法: powershell -ExecutionPolicy Bypass -File create_desktop_icon.ps1
# 首次启动时在桌面创建 MemOmics 快捷方式（企鹅图标）。
# 双击行为：服务已运行 -> 打开浏览器；未运行 -> 启动服务（见 launch_from_desktop.ps1）。
# 幂等：已存在同名快捷方式则跳过（不覆盖用户手动改过的）。

$ErrorActionPreference = 'SilentlyContinue'

# 安装根目录（脚本所在目录的上一级 = MemOmics 根）
$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)

# 启动脚本：优先 start.bat，兼容 启动.bat
$startBat = Join-Path $root 'start.bat'
if (-not (Test-Path $startBat)) { $startBat = Join-Path $root '启动.bat' }
if (-not (Test-Path $startBat)) { exit 0 }

# 桌面路径（兼容 OneDrive 重定向）
$desktop = [Environment]::GetFolderPath('Desktop')
if (-not $desktop -or -not (Test-Path $desktop)) { $desktop = Join-Path $env:USERPROFILE 'Desktop' }
if (-not (Test-Path $desktop)) { exit 0 }

$lnkPath = Join-Path $desktop 'MemOmics.lnk'
$launcher = Join-Path $root 'scripts\launch_from_desktop.ps1'
if (Test-Path $lnkPath) {
    # 2026-09-10 修复：原来"已存在就跳过"，导致旧安装遗留的快捷方式（指向已删除/
    # 另一个安装目录）永远无法自愈——用户双击图标毫无反应。现在校验指向：
    #   指向本安装目录 → 尊重现状直接退出；指向别处/失效 → 继续往下重建。
    $okLnk = $false
    try {
        $ws0 = New-Object -ComObject WScript.Shell
        $sc0 = $ws0.CreateShortcut($lnkPath)
        if ($sc0.Arguments -like "*launch_from_desktop.ps1*") {
            $okLnk = ($sc0.Arguments -like "*$root*")
        }
    } catch { $okLnk = $false }
    if ($okLnk) { exit 0 }
}

# 图标：webui/assets/penguin.png -> 256x256 PNG-in-ICO（持久化到 %LOCALAPPDATA%\MemOmics，
# 不占用安装目录；temp 会被清理导致图标丢失，这里不用 temp）
$icoPath = ''
$iconPng = Join-Path $root 'webui\assets\penguin.png'
$icoDir = Join-Path $env:LOCALAPPDATA 'MemOmics'
if (Test-Path $iconPng) {
    try {
        if (-not (Test-Path $icoDir)) { New-Item -ItemType Directory -Path $icoDir -Force | Out-Null }
        $icoPath = Join-Path $icoDir 'memomics_penguin.ico'
        Add-Type -AssemblyName System.Drawing
        $src = [System.Drawing.Image]::FromFile($iconPng)
        $canvas = New-Object System.Drawing.Bitmap 256, 256, ([System.Drawing.Imaging.PixelFormat]::Format32bppArgb)
        $g = [System.Drawing.Graphics]::FromImage($canvas)
        $g.Clear([System.Drawing.Color]::Transparent)
        $g.InterpolationMode = [System.Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic
        $g.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::HighQuality
        $scale = [Math]::Min(256.0 / $src.Width, 256.0 / $src.Height)
        $nw = [int]($src.Width * $scale)
        $nh = [int]($src.Height * $scale)
        $g.DrawImage($src, [int]((256 - $nw) / 2), [int]((256 - $nh) / 2), $nw, $nh)
        $g.Dispose()
        $ms = New-Object System.IO.MemoryStream
        $canvas.Save($ms, [System.Drawing.Imaging.ImageFormat]::Png)
        $pngBytes = $ms.ToArray()
        $ms.Dispose()
        $canvas.Dispose()
        $src.Dispose()
        # PNG-in-ICO：ICONDIR(6) + ICONDIRENTRY(16) + PNG 数据（尺寸字节 0 = 256）
        $ms2 = New-Object System.IO.MemoryStream
        $bw = New-Object System.IO.BinaryWriter($ms2)
        $bw.Write([uint16]0)          # reserved
        $bw.Write([uint16]1)          # type: icon
        $bw.Write([uint16]1)          # count
        $bw.Write([byte]0)            # width 0 = 256
        $bw.Write([byte]0)            # height 0 = 256
        $bw.Write([byte]0)            # colors
        $bw.Write([byte]0)            # reserved
        $bw.Write([uint16]1)          # planes
        $bw.Write([uint16]32)         # bpp
        $bw.Write([uint32]$pngBytes.Length)  # size
        $bw.Write([uint32]22)         # offset (6+16)
        $bw.Write($pngBytes)
        $bw.Flush()
        [System.IO.File]::WriteAllBytes($icoPath, $ms2.ToArray())
        $bw.Close()
        $ms2.Dispose()
    } catch {
        $icoPath = ''
    }
}

$shell = New-Object -ComObject WScript.Shell
$sc = $shell.CreateShortcut($lnkPath)
$launcher = Join-Path $root 'scripts\launch_from_desktop.ps1'
if (Test-Path $launcher) {
    $sc.TargetPath = "$env:WINDIR\System32\WindowsPowerShell\v1.0\powershell.exe"
    $sc.Arguments = "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$launcher`""
} else {
    $sc.TargetPath = "$env:ComSpec"
    $sc.Arguments = "/c `"$startBat`""
}
$sc.WorkingDirectory = $root
$sc.Description = 'MemOmics — 智能多组学生信分析助手（双击启动并打开 WebUI）'
if ($icoPath -and (Test-Path $icoPath)) {
    $sc.IconLocation = "$icoPath,0"
} else {
    $sc.IconLocation = "$env:WINDIR\System32\shell32.dll,13"
}
$sc.Save()

Write-Host "[桌面图标] 已创建：双击桌面 MemOmics 即可启动"
exit 0
