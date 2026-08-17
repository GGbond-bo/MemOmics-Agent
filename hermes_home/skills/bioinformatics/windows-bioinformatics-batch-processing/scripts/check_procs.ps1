# check_procs.ps1 — Windows 批处理进程诊断（MemOmics，2026-08-07 唤醒 #4 实测定型）
#
# 用途: 进程状态三源验证失败时的最终裁决器。
#   git-bash 下 tasklist //FI 可能静默空、Get-Process 会把 bash/cmd 包装算进计数、
#   process(action='list') 对脱离式任务恒空 —— 本脚本用 CIM 精确 Name 过滤 + CommandLine 一锤定音。
#
# 用法（从 git-bash 调用，零转义问题）:
#   powershell.exe -NoProfile -ExecutionPolicy Bypass -File check_procs.ps1            # 查 Rscript.exe
#   powershell.exe -NoProfile -ExecutionPolicy Bypass -File check_procs.ps1 python     # 查 python.exe
#   powershell.exe -NoProfile -ExecutionPolicy Bypass -File check_procs.ps1 cellbender
#
# 输出: 每进程 PID + 启动年龄(min) + 命令行（截断 200 字符）
#   判定: CommandLine 含分析脚本名 + 大内存 = 真在跑（worker 层）；
#         Age 持续增长 + CommandLine 指向当前样本 = 批处理正常推进。
param(
    [string]$ProcName = "Rscript.exe"
)

$procs = Get-CimInstance Win32_Process -Filter "Name='$ProcName'" | Select-Object ProcessId, CreationDate, CommandLine
$now = Get-Date
Write-Output "=== $ProcName processes: $($procs.Count) ==="
foreach ($p in $procs) {
    $ageMin = [math]::Round(($now - $p.CreationDate).TotalMinutes, 1)
    $cmd = $p.CommandLine
    if ($cmd.Length -gt 200) { $cmd = $cmd.Substring(0, 200) + "..." }
    Write-Output "PID=$($p.ProcessId) Age=${ageMin}min CMD=$cmd"
}

Write-Output "=== bash/cmd wrappers ==="
$wrappers = Get-CimInstance Win32_Process -Filter "Name='bash.exe' OR Name='cmd.exe'" | Select-Object ProcessId, Name, CommandLine
foreach ($w in $wrappers) {
    $cmd = $w.CommandLine
    if ($cmd.Length -gt 200) { $cmd = $cmd.Substring(0, 200) + "..." }
    Write-Output "PID=$($w.ProcessId) NAME=$($w.Name) CMD=$cmd"
}
