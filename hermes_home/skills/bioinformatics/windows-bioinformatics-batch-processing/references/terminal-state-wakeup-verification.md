# 终态唤醒验证（Terminal-State Wakeup Verification）

长任务（ArchR QC / CellBender / 批量分析）完成后，LoopX/系统唤醒会持续触发。此时任务已终态，正确的动作是**验证 + 记录 + 等待用户指令**，绝不自动启动红线阶段（如 P4 merge/LSI 这类"待用户确认"的后续步骤）。

## 验证组合（三源一致才判终态）

| 数据源 | 命令 | 期望 |
|--------|------|------|
| ① 进程 | PowerShell `Get-Process -Name Rscript,R`（MSYS 下 bash tasklist 可能失败，必须用 PowerShell） | 0 个分析进程 |
| ② 磁盘产出 | `ls -d <out>/GSM* \| wc -l` + `<out>/GSM*/*_filtered_cells.csv \| wc -l` | 目录数 == N，CSV 数 == N |
| ③ cron | `ls -la hermes_home/cron/` | 仅系统 ticker 文件（ticker_heartbeat / ticker_last_success / executions.db / .tick.lock），**无任务 cron** |
| ④ 后台进程 | process(action="list") | 空（无 watchdog/fallback/bridge/guardian 残留） |

## ⚠️ 陷阱：tasklist grep 子串误报（2026-08-08 实测）

`tasklist | grep -iE "Rscript|R\.exe|bash"` **几乎总能返回一堆进程**，因为 `R\.exe` 会匹配任何含 `er.exe` 子串的名字：`NVDisplay.Container.exe` / `explorer.exe` / `crashpad_handler.exe` / `qmlauncher.exe` / `RuntimeBroker.exe` / `UserOOBEBroker.exe` 等全部命中 → 极易误判"还有 R 进程在跑"。

**正确判定**（bash/MSYS 下 tasklist 本身可用，不必退到 PowerShell）：
- 进程名精确匹配：`tasklist | grep -iE "Rscript(\.exe)?($| )"` 或 `tasklist | grep -ic 'Rscript.exe'`（Rscript 是全名，安全）
- 若用 `R\.exe` 必须锚定首部：`grep -E '^R\.exe'`（R GUI），不要裸 `R\.exe`
- 判定前逐行核对：命中项是否真的是 Rscript/R.exe（NVIDIA/浏览器相关进程全是误报）
- PowerShell 备选：`Get-Process Rscript,R -ErrorAction SilentlyContinue`

## ⚠️ 陷阱：多 session 环境选活跃 task_plan（2026-08-08 实测）

results/ 下有多个 session 的 task_plan.md（实测 6 个）时，唤醒消息不指定 session。**不能按名字/直觉选** — 用 mtime 判定：`ls -lt --time-style=full-iso MEMOMICS_HOME/results/*/task_plan.md`，最新修改者即活跃任务（本例 memomics-1135ed52 00:39，其余最早到 07-14）。读尾部（大文件 >250 行先读 tail，如 `wc -l` 后 offset=total-150）看最近唤醒记录与红线段，再决定是否三源验证。

## ⛔ 权威完成信号陷阱：.arrow 计数 ≠ 样本数（2026-08-08 实测）

- `find ... -name "*.arrow" | wc -l` 返回 **46**，样本数是 **40** — 临时 arrow / 子目录副本会虚增计数
- **.arrow glob 计数不是权威完成信号**。权威信号 = **每样本完成文件**（ArchR 用 `*_filtered_cells.csv`，CellBender 用 `*_filtered.h5`）：目录数 + 完成文件数都必须 == N
- 汇报时写清楚"N/N 目录 + N/N CSV"，并注明 arrow 计数超过样本数是正常现象，避免未来 session 误判

## 唤醒记录写入

终态确认后，往 task_plan.md **顶部**追加一条唤醒检查记录（不要覆盖旧记录，保持可追溯）：

```
## ✅ 唤醒 #N 检查（<时间戳>）
- 三源验证：进程 0 + 磁盘 N/N + cron 无残留
- 状态: <P1+P2+P3> 全量完成，终态保持。总 Keep <细胞数> cells
- <红线阶段名> (如 P4) 等待用户确认后另行执行（红线：不自动执行）
- 结论: 任务已终态，无需干预
```

## ⚠️ 陷阱：顶层 glob 误判（2026-08-08 实测）

`ls <out> | grep -c "*_filtered_cells.csv"` 在**顶层目录**返回 **0** — 因为每样本完成文件在 `GSM*` 子目录**内部**，不在顶层。顶层 glob 返回 0 是正常现象，不代表产出缺失。误判路径：把 0 当"没产出"→ 误报错误 → 浪费一轮三源验证。

**正确验证组合**：`ls -d <out>/GSM* | wc -l`（顶层子目录计数）+ `<out>/GSM*/*_filtered_cells.csv | wc -l`（子目录内完成文件计数）+ 顶层汇总文件（如 `QC_summary_all40.csv`）。三者 == N 才判完整。

## ⚠️ 陷阱：task_plan.md 唤醒记录无限膨胀（2026-08-08 实测）

每次终态唤醒都往 task_plan.md 顶部追加"唤醒 #N 检查"记录 → 文件膨胀到 **68KB / 821 行**，其中 ~10+ 条内容几乎相同（"终态保持 / P4 等待确认"）。这与"不要覆盖旧记录，保持可追溯"的建议冲突。

**修正规则**：终态确认**连续 2-3 次结论相同**后，停止追加新记录 — 改为只更新最新一条的时间戳+结论，或把旧的连续相同记录压缩成一行（如"唤醒 #0-#19 均终态保持，详见历史"）。task_plan.md 的核心价值是"快速恢复状态"，重复记录是噪音。可追溯性用 log/system_log.jsonl 保留，不需要 task_plan 全文堆叠。

## ⚠️ 陷阱：并发唤醒竞争写 task_plan.md（2026-08-08 实测）

LoopX 多周期并发唤醒时，两个 Agent 同时 append 唤醒记录 → patch 报警告 "task_plan.md was modified by sibling subagent ... after this agent's last read"。**丢失更新风险**。

**规则**：patch 前重读文件；若系统提示已修改，重新 read_file 后再 patch；以追加语义处理（保留双方记录）而不是覆盖。若必须覆盖，先 read_file 合并双方最新内容。

## 汇报格式

三源结果表格 + 状态判定（终态保持）+ 红线声明 + "下一步由用户决定"。P4 类红线阶段**绝不自动执行**——只验证、只记录、等用户说"开始"。

## 相关

- `references/session-resumption-stale-taskplan.md`：恢复会话时 task_plan 可能描述旧任务，四源交叉验证必须在读 task_plan 后立即执行
- 内存规则："终态唤醒汇报必须含 cron 检查字段"；cron 检查与读 task_plan 放同一并行批次
