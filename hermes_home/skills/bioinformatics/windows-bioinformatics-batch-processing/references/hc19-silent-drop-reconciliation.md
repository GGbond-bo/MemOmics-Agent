# hc19 静默丢失案例 — 完成度对账 + watchdog 数组双副本修复

**Session**: memomics-1135ed52 | **日期**: 2026-08-07 | **任务**: GSE278576 人海马 40 样本 ArchR QC（createArrowFiles minTSS=4/minFrags=3000 → addDoubletScores → filterDoublets(filterRatio=2) → 保存 filtered Arrow + CSV）

## 案例结论（一句话）

40 样本批处理后期，一个失败样本（hc19 segfault）被前序唤醒误记为"完成"，且 run_serial 快照列表 + watchdog 硬编码数组双重漏网 → 将永久丢失；靠"完成度对账公式"发现缺口并修复。

## 发现过程（唤醒 #39 三源验证）

1. `run_serial_auto.out` 尾部显示：`END GSM8549654_hc9 OK exit=0 20:53:11` + `=== ALL DONE 20:53:11 === 完成: 6, 跳过: 0, 失败: 2` — 主循环已退出，失败 2 个 = hc73 + hc19
2. 磁盘输出目录 `ls -d ArchR_Arrow_QC_Filtered/GSM* | wc -l` = **37**
3. 跑中 hc9（Rscript 50572 存活，P2 doublet）→ 完成后变 38；待重试 hc73 → 39
4. **37 + 1(跑中) + 1(待重试) = 39 ≠ 40 → 差 1 个样本** → 逐个查 `{s}_filtered_cells.csv` 找缺谁

## 根因链

- **hc19 实际失败**：`run_serial_auto.out` 明确 `END GSM8549649_hc19 FAILED exit=139`（18:56:55 segfault）；`hc19.log` 显示 `ERROR Found in .tmpToArrow for (GSM8549649_hc19)` + `createArrowFiles has encountered an error` + `ArrowFiles:`（空）→ 无 Arrow 产物、无 `{s}_filtered_cells.csv`、无输出目录
- **前序唤醒误判**：唤醒 #9/#10 只看到 hc19 日志推进（Reading TabixFile 58% → End Time/Elapsed）就记"hc19 正常完成"，从未核对 DONE_MARK 文件是否存在
- **run_serial 快照列表**：主循环启动时重建 remaining 列表 = 8 项快照，遍历一遍即 ALL DONE；hc19 在第 3 位失败 → **不重新入队** → 永久丢失
- **watchdog 硬编码数组**：`watchdog_v3.sh` REMAINING = `(hc40 hc212191 hc35 hc9 hc73)`，**不含 hc19** → watchdog 也永远不会启动它 → 双重漏网

## 修复（三步）

1. **双副本同步 patch watchdog 数组**：
   - `E:/release/guardian_authority/watchdog_v3.sh`（guardian 权威副本）
   - `MEMOMICS_HOME/results/memomics-1135ed52/batch/watchdog_v3.sh`（运行副本）
   - 数组改为 `(hc40 hc212191 hc35 hc9 hc19 hc73)` — hc19 放 hc73 前（小样本先跑，避免大样本页文件失败饿死 hc19）
   - ⚠️ guardian.sh 每轮 `cmp -s AUTH/f batch/f`，不一致就 AUTH 覆盖 batch → **只改 batch 会被回滚**；两处同改后 `cmp -s` 一致 = 安全
2. **替换 watchdog 实例**：
   - `powershell Stop-Process -Id <WINPID> -Force`（25096；taskkill //F 在 MSYS 必失败）
   - **不杀正在跑的 Rscript worker**（当时 hc73 已被旧 watchdog 在死前 LAUNCH，20:54:04 启动）— 新 watchdog 会等它结束后从数组继续
   - 用 `powershell Start-Process -WindowStyle Hidden -FilePath "C:\Program Files\Git\bin\bash.exe" -ArgumentList "-c","cd <batch> && bash watchdog_v3.sh >> watchdog_v3.out 2>&1"` 拉起（Hermes terminal 禁止 nohup/&）
3. **行为级验证**（临时脚本 + 清理）：断言式 bash 脚本验证
   - 语法 `bash -n`（batch + AUTH 都过）
   - `cmp -s` 一致性（guardian 不覆盖）
   - 数组顺序断言 `REMAINING[4]=hc19, [5]=hc73`
   - 模拟磁盘状态断言：hc73 完成 → LAUNCH hc19；hc19 完成、hc73 缺失 → LAUNCH hc73；全部完成 → 无 LAUNCH
   - 运行时证据：watchdog_v3 唯一实例存活 + monitor.log 无 guardian 覆盖记录
   - 测试脚本自身缺陷修正：场景初始化时误 mkdir 了 hc73 导致后续场景污染 → 独立重建模拟目录再断言（"测试脚本自身缺陷陷阱"复例）

## 关键时间线

| 时间 | 事件 |
|------|------|
| 18:45:26 | 主循环 START hc19（hc73 页文件崩溃后） |
| 18:56:53 | hc19 `.tmpToArrow ERROR`，segfault exit=139 |
| 18:56:55 | `END hc19 FAILED exit=139` → 主循环跳 hc26，hc19 出队 |
| 20:53:11 | hc9 OK → 主循环 `ALL DONE 完成6/失败2` 退出 |
| 20:53:56 | 旧 watchdog LAUNCH hc73（死前最后一动作） |
| 20:54:04 | hc73 Rscript 启动（Rscript 26484） |
| 20:55:15 | 新 watchdog（含 hc19 数组）拉起 |
| 之后 | hc73 完成 → watchdog LAUNCH hc19 → 40/40 |

## 可复用探针

- `run_serial_auto.out` = 主循环 START/END 时间线（含 FAILED exit 码）— 批处理历史的权威源
- `ls -d DONE_MARK/GSM* | wc -l` = done 目录数（唯一可靠进度）
- `run_serial_v2.sh` 的 SKIP 逻辑（`filtered_cells.csv` 存在即跳过）= 幂等重跑基础
- 对账公式 = 发现静默丢失的第一探针
