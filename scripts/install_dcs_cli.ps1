# 安装官方 DCS Cloud CLI（dcs.exe / dcs）—— MemOmics「☁️ DCS 云」连接器依赖它。
#
# 用法（PowerShell）：
#   powershell -ExecutionPolicy Bypass -File scripts\install_dcs_cli.ps1
#   powershell -ExecutionPolicy Bypass -File scripts\install_dcs_cli.ps1 -Version v1.2.0 -Force
#
# 行为：
#   1. 从官方 CDN（cdn-refs.dcs.cloud）取版本号，下载对应平台二进制 + SHA256SUMS；
#   2. **先校验 SHA256，校验不过就删文件、绝不执行**；
#   3. 落到 %LOCALAPPDATA%\MemOmics\tools\dcs\（连接器自动探测这个位置），
#      并打印下一步（绑定 PAT 的入口）。
#
# 说明：官方下载源只认 CDN；GitHub Releases 不提供二进制（官方 README 明说）。

[CmdletBinding()]
param(
    [string]$Version = "",
    [string]$Dest = "",
    [switch]$Force
)

$ErrorActionPreference = "Stop"
$CdnBase = "https://cdn-refs.dcs.cloud/app/dcs_cli"

function Get-PlatformFile {
    if ($IsWindows -or ($env:OS -eq "Windows_NT")) { return "dcs.exe" }
    $os = [System.Runtime.InteropServices.RuntimeInformation]::OSDescription
    $arch = [System.Runtime.InteropServices.RuntimeInformation]::OSArchitecture
    if ($os -match "Darwin") {
        if ("$arch" -match "Arm64") { return "dcs-darwin-arm64" }
        return "dcs-darwin-amd64"
    }
    if ("$arch" -match "Arm64") { return "dcs-linux-arm64" }
    return "dcs-linux-amd64"
}

if (-not $Dest -or $Dest.Trim() -eq "") {
    if ($IsWindows -or ($env:OS -eq "Windows_NT")) {
        $Dest = Join-Path $env:LOCALAPPDATA "MemOmics\tools\dcs"
    } else {
        $Dest = Join-Path $HOME ".memomics/tools/dcs"
    }
}
New-Item -ItemType Directory -Force -Path $Dest | Out-Null

if (-not $Version -or $Version.Trim() -eq "") {
    Write-Host "[DCS] 查询最新版本 ..." -NoNewline
    $Version = (Invoke-WebRequest -Uri "$CdnBase/version.txt" -UseBasicParsing).Content.Trim().Split("`n")[0].Trim()
}
Write-Host "[DCS] 版本 = $Version"

$file = Get-PlatformFile
$target = Join-Path $Dest $file
$url = "$CdnBase/$Version/$file"
$sumsUrl = "$CdnBase/$Version/SHA256SUMS"

Write-Host "[DCS] 下载 $url"
$tmp = "$target.download"
Invoke-WebRequest -Uri $url -OutFile $tmp -UseBasicParsing
Invoke-WebRequest -Uri $sumsUrl -OutFile "$Dest\SHA256SUMS" -UseBasicParsing

# --- 校验（校验不过绝不落盘、绝不执行）---
$expected = $null
foreach ($line in Get-Content "$Dest\SHA256SUMS") {
    $parts = $line.Trim() -split "\s+"
    if ($parts.Count -ge 2 -and ($parts[-1].TrimStart("*") -eq $file -or $parts[-1] -eq $file)) {
        $expected = $parts[0].ToLower()
        break
    }
}
if (-not $expected) {
    Remove-Item $tmp -Force -ErrorAction SilentlyContinue
    throw "SHA256SUMS 里没有 $file 的校验值 —— 已删除下载文件，请联系维护者。"
}
$actual = (Get-FileHash -Algorithm SHA256 $tmp).Hash.ToLower()
if ($actual -ne $expected) {
    Remove-Item $tmp -Force -ErrorAction SilentlyContinue
    throw "SHA256 校验失败！期望 $expected，实际 $actual —— 已删除下载文件，未执行。"
}
Write-Host "[DCS] SHA256 校验通过：$actual"

if ((Test-Path $target) -and -not $Force) {
    $old = (Get-FileHash -Algorithm SHA256 $target).Hash.ToLower()
    if ($old -eq $expected) {
        Remove-Item $tmp -Force
        Write-Host "[DCS] 已装同版本且校验一致，跳过：$target"
    } else {
        Move-Item -Force $tmp $target
        Write-Host "[DCS] 已更新：$target"
    }
} else {
    Move-Item -Force $tmp $target
    Write-Host "[DCS] 已安装：$target"
}
if (-not ($IsWindows -or ($env:OS -eq "Windows_NT"))) {
    chmod +x $target 2>$null
}

Write-Host ""
Write-Host "[DCS] 下一步（MemOmics 里）："
Write-Host "  1. 打开 WebUI 左侧「☁️ DCS 云」面板；"
Write-Host "  2. 到 https://www.dcs.cloud 个人中心 → 访问令牌 → 创建（有效期最长 1 年）→ 复制；"
Write-Host "  3. 把令牌粘贴进面板「绑定」，然后就能查项目 / 传数据 / 开容器了。"
Write-Host ""
Write-Host "[DCS] 命令行自检：& '$target' --version"