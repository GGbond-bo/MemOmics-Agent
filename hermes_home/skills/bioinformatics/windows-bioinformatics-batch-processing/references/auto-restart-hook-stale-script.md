# 自动重启钩子指向旧脚本 — 级联崩溃事故复盘与恢复清单（2026-08-07 memomics-1135ed52）

## 事故时间线（GSE278576 人海马 ATAC 40 样本 ArchR QC）

| 时间 | 事件 |
|------|------|
| 17:20 | 修复版 run_serial_v2.sh 启动（bash 直调 Rscript.exe，绕开 cmd.exe//c MSYS 转义 bug） |
| 17:20-17:35 | v2 处理 hc12 成功（1.28GB arrow + filtered_cells.csv）→ 32/40 |
| 17:35:29 | v2 开始 hc11 |
| 17:45:56 | hc11 FAILED exit=1（并发 tmp 竞争） |
| 17:45:25 | **monitor 自动重启 = 旧 run_serial.sh（bat 版）** ← 根因 |
| 17:45-17:55 | 旧脚本 + v2 并发跑同一批样本 → hc73/hc19/hc26/hc40 连环失败；旧脚本的孤儿 hc40/hc19 Rscript 链无人管理 |
| 17:54 | 又出现 run_serial_v3.sh（`timeout 2100` → git-bash 无 timeout → exit=127），三个版本并存、三个锁名碎片化 |
| 17:56-18:00 | Agent 介入：杀光冲突进程 → 清锁 → 修 monitor 钩子指向 v2 → 重启单实例 v2 + 单实例 monitor → hc11 仍因 tmp 缺失 34s 内失败（后续单实例验证中） |

## 根因链（三层）

1. **直接原因**：monitor_serial.sh 自动重启分支硬编码 `run_serial.sh`（旧 bat 版），v2 才是有 bug 修复的 sanctioned 版本。调度器一死，自动重启把"已修复的串行流程"替换成"会踩 MSYS 转义 bug 的旧流程"，且与仍在跑的 v2 并发。
2. **放大因素**：批量脚本版本增殖（run_serial.sh / run_serial_v2.sh / run_serial_v3.sh）没有退休旧版 → 三个锁名（.run_serial.lock/、.run_serial_v2.pid、.run_serial_v3.pid）互不排斥 → "单实例锁"全部失效 → 并发实例同时存在。
3. **底层**：ArchR 1.0.3 Windows 所有实例共享 `outputDirectory/tmp/`（cleanTmp=TRUE 默认跑完即删）→ 并发实例互相删对方的 tmp arrow → `.tabixToTmp` 报 `Cannot open file tmp-*.arrow does not exist`。

## 恢复清单（杀光 → 清锁 → 修钩子 → 单实例重启 → 验证）

```bash
# ① 杀光全部冲突进程（bash 里 taskkill //F 无效，用 PowerShell Stop-Process）
powershell -NoProfile -Command "Get-CimInstance Win32_Process | Where-Object { \$_.CommandLine -match 'run_serial|monitor_serial|create_arrow' } | ForEach-Object { Stop-Process -Id \$_.ProcessId -Force -ErrorAction SilentlyContinue }"
powershell -NoProfile -Command "Stop-Process -Name Rscript -Force -ErrorAction SilentlyContinue"
sleep 2
# ② 确认归零
powershell -NoProfile -Command "(Get-Process Rscript -ErrorAction SilentlyContinue | Measure-Object).Count"   # 必须 0
# ③ 清空全部锁（每个版本一个锁名，全删）
rm -f batch/.run_serial_v2.pid batch/.run_serial_v3.pid batch/.monitor.pid
rm -rf batch/.run_serial.lock
# ④ 修 monitor 自动重启钩子 → 指向当前 sanctioned 版本（逐字核对脚本名 + pgrep 防重模式）
patch monitor_serial.sh  # run_serial.sh → run_serial_v2.sh（两处：pgrep 检查 + nohup 重启）
# ⑤ 启动单实例 v2（Hermes background + notify_on_complete）+ 单实例 monitor（守护）
# ⑥ 验证：45-60s 后 poll v2 输出出现新样本 START + Rscript worker 存活 + 样本日志写 START
```

## 关键判定教训

- **monitor 自动重启的"防重"检查必须匹配当前版本名**：`pgrep -f "bash.*run_serial.sh"` 匹配不到 `run_serial_v2.sh`（子串不含 run_serial.sh），修复后也要同步。
- **queue-rebuild 脚本重启前先杀 in-flight 孤儿**：v2 启动时重建 remaining = fragments − done(filtered_cells.csv)，正在跑的样本未 done → 会被新实例重选 → 与孤儿 worker 并发。先杀干净再重启。
- **不要读旧的 .out 文件判断新运行**：Hermes background 启动的脚本 stdout 进 Hermes 进程日志（process poll），不是磁盘 .out 文件；.out 文件是之前脱离式启动留下的快照。
- **ArchRProject 的 `file.exists(object@sampleColData$ArrowFiles): 'file'参数无效` 是下游症状**：createArrowFiles 失败返回空 → 脚本继续到 ArchRProject() 报误导性校验错。追根因要看 P1 的 tabixToTmp 错误（tmp arrow 打不开），别在 ArchRProject 处浪费轮次。
