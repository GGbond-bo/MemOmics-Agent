# Windows 批处理并发与监控陷阱（2026-08 GSE278576 40 样本实测）

40 样本 ArchR QC 批量 + watchdog 自动续跑过程中踩过的坑。

## 1. 多实例并发 = ArchR tmp 目录竞争崩溃（最严重）

**症状**：多个 run_serial.sh + 多个 monitor_serial.sh 同时存活 → Rscript 报 `.tabixToTmp: Cannot open tmp-arrow file` / createArrowFiles 返回空。
**根因**：`create_arrow_qc.R` 开头 `unlink(tmp_dir)` 无差别清空 ArchR tmp → 实例 A 清 tmp 把实例 B 正在写的 arrow 删了。
**修复**：
- **单实例锁**：run_serial 启动时写 PID 锁文件，启动前 `pgrep` 检查 + 锁文件双重确认
- **watchdog 冷却**：检测到"无进程"后必须 ≥300s 冷却再重启，防止 watchdog 自杀性循环重启
- 彻底清理：`taskkill /F /IM Rscript.exe /T` + `taskkill /F /IM bash.exe /T`（/T 杀进程树）

## 2. bash 调用 R 4.5.3 会 segfault

R 4.5.3 + MSYS bash 下 `Rscript --vanilla` 频繁 segfault（0xC0000005），cmd.exe 下正常。
**绕过**：`cmd.exe /c "C:\Program Files\R\R-4.5.3\bin\x64\Rscript.exe" script.R`（不要用 bash 直接 exec Rscript）。

## 3. cmd.exe //c 的 MSYS 路径转义坑

`run_serial.sh` 里 `cmd.exe //c "E:\\...\\batch\\run_X.bat"` 在 MSYS bash 下 `\r` 被解释为回车 → bat 文件名 `run_` 变成 `un_` → 报 `'un_GSM...bat' 不是内部或外部命令`。
**修复**：绕开 cmd.exe//c，bash 直接调用 `"/c/Program Files/R/R-4.5.3/bin/x64/Rscript.exe"`（之前验证过的方式）。

## 4. PowerShell 内联命令被 bash 转义

`powershell -Command "Get-Process Rscript | Select Id,$_..."` 中 `$_` 被 bash 展开 → 空/错。
**修复**：用 write_file 写 .ps1 文件再执行；或 PowerShell 字符串用单引号包裹。

## 5. tasklist grep 误报

`tasklist | grep -i "R\.exe"` 匹配到 `NVDisplay.Container.exe`、`crashpad_handler.exe` 等无关进程（大小写不敏感 `r.exe` 子串）。
**修复**：用 `Get-Process Rscript -ErrorAction SilentlyContinue`（精确进程名）或 PowerShell `Name -match '^Rscript$'`。

## 6. 心跳必须检测"真实日志增长"而非进程名

watchdog 的 alive 判定若只看 `Get-Process Rscript`，会因瞬时失败误判 `procs=0` 并重启新实例（触发 #1 的并发崩溃）。
**修复**：心跳 = 日志文件 mtime/行数增长检测 + 进程存活双条件，避免误重启。

## 7. 孤儿进程接管链

watchdog 死了但 Rscript 还活着 → 新 watchdog 会重启 run_serial → 两个 run_serial 抢同一批样本。
**修复**：run_serial 锁检测已有实例就 SKIP；Rscript 的父进程是旧 watchdog 时，不能杀 watchdog（连带杀 Rscript），要用独立 bridge 脚本等它完成。

## 8. 批量样本的失败重试（bridge/fallback 模式）

大样本（5.42GB）因页文件压力崩溃后，用**独立 bridge 脚本**检测"输出目录出现后自动补跑"，比修改主循环更安全（不动正在跑的实例）。
