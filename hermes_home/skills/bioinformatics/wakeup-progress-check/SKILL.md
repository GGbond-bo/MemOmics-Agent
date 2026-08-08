---
name: wakeup-progress-check
description: 系统唤醒/进度询问时的任务状态核查规程。定位活跃 task_plan → 终态验证 → 三源交叉验证 → 汇报。触发："[系统唤醒]"、"还在跑吗"、"进度"、cron 唤醒、跨会话恢复。
---

# Wakeup Progress Check — 唤醒/进度核查规程

## 何时触发

- 消息包含 `[系统唤醒]` / `⏰` / cron 唤醒
- 消息头含 `📊 LoopX 状态：goal: ... | attention: ... | todos: ...`（LoopX 心跳唤醒变体，2026-08-09 实测；其后的 `[系统唤醒 #N]` 编号是 LoopX 计数器，**不作 task_plan 记录编号**——按已有记录最大号+1 或按终态不追加规则处理）
- 用户问"还在跑吗" / "进度怎么样" / "跑到哪了"
- 新会话启动但 memory 显示有历史任务

## 核心原则

**查完再答，不查就答 = 撒谎（铁律 -2）。** 三个独立数据源交叉验证一致后才能汇报状态。

## Step 1: 定位活跃 task_plan（最新 mtime 优先）

```bash
ls -lt results/*/task_plan.md | head -5
```

- 多个 task_plan 并存时**取最新 mtime** 作为当前主线。
- ⛔ 不要假设唤醒消息/记忆里的目录就是活跃任务——以 mtime 为准。
- ⛔ 不要抄旧编号从 0 重计：终态任务（completed/等用户指示）不重启。
- **唤醒记录编号以 task_plan 实际已有为准，消息头 #N 不作数（2026-08-09 实测）**：消息标"[系统唤醒 #1]"但
  task_plan 已含"唤醒 #1 完成 P3-P6"+"唤醒 #2 终态确认" → 本次实际是 #3。追加记录前 `grep -c '唤醒 #' task_plan.md`
  取最大号+1；⛔ 直接抄消息头编号会撞号/从 0 重计。
- **终态记录已存在 + 磁盘无新产出 → 不追加重复记录（2026-08-09 实测）**：判断"是否要写新唤醒记录/是否要继续"，
  先把产出文件最新 mtime 与 task_plan 上次唤醒记录时间戳对比（`ls -lt <工作目录>/*.{csv,bed,md,rds,png} | head` 取最新一行）。
  若上次终态记录已写、且**没有任何文件 mtime 晚于该记录** → 本次=纯汇报，不追加重复终态记录，保持现状等用户。
  - ⚠️ **系统内部文件不算"新产出"（2026-08-09 实测）**：`ls -lt <会话目录>` 全目录比较时，`token_usage.jsonl` /
    `system_log.jsonl` / monitor 日志会持续写入，mtime 可能晚于终态记录（实测 token_usage.jsonl 02:29 vs plan 02:20），
    但它们是系统 token 计数/日志，**不是分析产出**。判"无新产出"一律用扩展名过滤的
    `ls -lt <目录>/*.{csv,bed,md,rds,png}` 或显式排除 jsonl/log，别被 token_usage.jsonl 误导追加记录/误报活跃。
  - 💡 **`find -newermt` 一行判"无新产出"（唤醒 #6 实测 2026-08-09）**：`ls -lt` 过滤法的省事替代——
    `find <会话目录> -newermt "<上次终态记录时间戳>" -type f | grep -vE '\.loopx|token_usage|system_log|heartbeat|monitor|\.log'`
    直接列出"晚于终态记录的非系统文件"，空 = 纯汇报不追加。⚠️ **`.loopx/` 也算系统内部文件**（goal/runs
    心跳 JSON+MD 持续写入，唤醒 #6 实测：晚于 02:30 的只有 .loopx runs + task_plan 自身 + jsonl → 正确判
    终态且未追加重复记录）；判"无新产出"时排除项必须含 `.loopx`，否则误报活跃。
  - 🔴 **基线 = task_plan.md 自身 mtime，不是上次记录时间戳（唤醒 #7 实测 2026-08-09）**：上一唤醒写终态记录时
    "磁盘无新产出"可能已过期——**记录之后又生成了新文件**（实测 `patent/CLUSTER_STEP_BY_STEP_GUIDE.md` 02:53 vs
    task_plan 02:43，晚 10 min，唤醒 #6 漏记）。判"有无未记账产出"一律用
    `find <会话目录> -newermt "$(ls -l <dir>/task_plan.md | awk '{print $6,$7,$8}')" -type f | grep -vE '\.loopx|token_usage|system_log|\.log'`
    （或直接手填 task_plan mtime），列出的候选**逐个确认是否已记账**——这比只看上次记录时间戳多抓"记录后新生成"的一批。
  - 💡 **发现晚于 task_plan 的新文件 = 补账，不是重启（唤醒 #7 实测 2026-08-09）**：若文件属于已标记 completed
    Phase 的产出（如集群正式版执行手册）→ 先验证结构完整（如 `grep -n '^# M'` 见 M1-M9 全在）→ **追加一条新唤醒
    记录补账**（文件路径/时间/大小/内容摘要 + 上一唤醒为何漏：记录先于文件生成）→ 不重跑、不标 in_progress、不误报活跃。
- 读 task_plan 全文，注意 `Current Phase` / `## 未完成待办` / 用户红线（如"等待用户确认"）。

## Step 2: 终态验证 — 三个高频陷阱

**陷阱 A：陈旧 Status 标记**
task_plan 头部写"✅ 任务已完成"、所有 checkbox 已勾选，但某个 Phase 的 `**Status:**` 行残留 `in_progress`。
→ 先用磁盘产出验证完成声明（硬证据），确认后**顺手 patch 掉陈旧标记**，保持 plan 自洽。
→ ⛔ 不因标记不一致就重跑 Phase。

**陷阱 B：空模块目录 ≠ 产出缺失**
会话目录下某模块子目录（如 `04_xxx/`）为空，但产出实际写在**另一个** `results/{session_dir}/`（跨会话接力常见）。
→ 报缺失前先查 memory、log/system_log.jsonl、相邻 session 目录确认产出真实位置。
→ ⛔ 看到空目录就报警 = 误报。

**陷阱 C：完成声明 ≠ 完成事实**
task_plan 说"已完成"但可能是上次 Agent 的乐观记录。
→ 每个模块至少抽查 1-2 个关键产出文件真实存在且非空（rds/csv/png 的大小）。
→ HTML 报告、最终图等交付物单独确认存在。

**陷阱 D：批量产物（40/40 式）完整性两条命令验证，别逐样本读日志**
批处理（多样本 QC / 去污染 / 下载）宣称完成时，用「汇总行 + 目录数」双重确认：
→ `ls -d <输出目录>/<样本前缀>* | wc -l` 数目录/文件数，与计划数比对（如 40）。
→ 若批处理写过汇总 CSV（如 `QC_summary_all40.csv`），`tail -2` 看 TOTAL 行：
   `TOTAL,265909,,40/40` 自带完成标记；TOTAL 行不存在或不是 N/N → 批处理未完成。
→ 2026-08-08 唤醒 #4 实测（GSE278576 40 样本 QC）：两条命令即可确认完成态，无需读 40 个样本日志。
→ ⛔ **数目录 ≠ 数条目（唤醒 #17 实测）**：`ls <dir> | wc -l` 会把 summary CSV 等非目录条目计入
   （40 样本目录 + QC_summary_all40.csv + 1 杂项 = 42 条目）。判"N/N"用 `ls -d */ | wc -l` 数**目录**，
   非目录条目逐个点名，禁止把"42 条目"直接报成"40 样本"。

**陷阱 E：未勾 `[ ]` 待办 ≠ 未完成 — 磁盘产出优先于 plan 标记（唤醒 #0 实测 2026-08-09）**
task_plan 里某 Phase 标 `in_progress`、某 todo 还勾 `[ ]`，但**实际工作已由上一会话完成**——plan 只是忘了同步。
→ 先按 mtime 找产出：`ls -lt <工作目录>/` + `find <工作目录> -name '<产出模式>'`，把"plan 声称未完成"与"磁盘时间戳"对照。
→ 实测案例：P3 剩"猴侧 JASPAR motif"未勾，但 `p3_l1_motif.R` + 4 个输出 CSV（01:30-01:32 mtime）都在 → 实际已完成；
   P6 专利文档标 pending，但 patent/ 下三份文档已生成（01:31-01:32）→ 实际已完成。
→ 判定规则：**文件 mtime 晚于 plan 最后更新或接近 → 以磁盘为准**，patch 同步 plan（勾掉、标 completed），不要重跑。

**陷阱 E2：patch task_plan 时可能被并行 sibling subagent 修改（2026-08-09 实测）**
唤醒同步 plan 时，另一个 subagent 可能同时在写同一个 task_plan.md（本会话 patch P6 段失败，系统提示文件 01:32:36 被 sibling `4e5e409c` 修改过）。
→ patch 失败信息若含 "modified by sibling subagent" → **先 re-read 再决定**：目标段可能已被对方同步（本次 P6 已被对方标 completed，直接跳过即可），不要硬 patch 覆盖对方更新。
→ 多个 patch 分批发时，把容易冲突的段落（如 Status 行）放在最后，先做低冲突追加。

**陷阱 F：脚本无 log 时，从输出 CSV 重算关键统计，不照抄 plan 叙述（2026-08-09 实测）**
脚本跑完但 stdout 未落盘（无 .log 文件）→ task_plan 里只有叙述性结果（如"Jaccard 0.020"），无法核对。
→ 重算路径：读输出 CSV（如 motif rank 文件）→ 按脚本逻辑重算关键统计（top30 重叠、Jaccard、共享清单）→ 写回 plan 时带重算结果。
→ 这同时验证了产出物可读 + 结果可复现，比信任 plan 叙述更可靠（plan 数字可能来自中间版本）。
→ ⚠️ 重算时注意脚本用 `utf-8-sig` 读 CSV（BOM），Windows 路径用 `E:/` 而非 `/e/`（execute_code 沙箱不识别 MSYS 路径）。

## Step 3: 三源交叉验证

| 源 | 命令 | 验证什么 |
|----|------|---------|
| 进程 | `tasklist \| grep -iE 'Rscript\|python\|cellbender'` | 是否有分析进程在跑 |
| 磁盘 | `find {dir} -type f` / `ls -la` | 产出文件数量、大小、时间戳 |
| 日志 | `tail` 最新日志 / `log/system_log.jsonl` 尾部 | 最后动作、有无 error |
| GPU（辅助源） | `nvidia-smi --query-gpu=utilization.gpu,memory.used --format=csv,noheader` | GPU 任务（CellBender/scTour/深度任务）是否在跑；`3%, ~3.4GiB` 空载=仅系统桌面占用（唤醒 #4/#1 实测） |

三者一致 → 才能下结论。

⚠️ **日志陈旧判定（唤醒 #8 实测 2026-08-08）**：`tail log/system_log.jsonl` 先看末条 ts——若远早于 task_plan.md 的 mtime（实测末条 07-26 vs plan 08-08，差 13 天），说明近期会话未写该日志，日志源陈旧降权，结论以进程+磁盘两源为准。⛔ 不要把陈旧日志末条当作当前任务的"最后动作"汇报（如误报"最后动作=CellBender checkpoint 检查"——那是 13 天前另一个 session 的残留）。

**进程源细化（唤醒 #2 实测 2026-08-08）**：`tasklist | grep python` 命中多个 python.exe **不代表有分析进程在跑**——
webui/server.py、cellbender_guardian.py 等系统守护常驻且进程名相同，误报会触发"任务恢复"错判。必须查命令行区分：
→ `powershell -Command 'Get-CimInstance Win32_Process | Where-Object {$_.Name -like "python*"} | Select-Object ProcessId,CommandLine | Format-Table -AutoSize'`
⛔ bash(MSYS) 会展开 `$_`（变成上条命令末参数，如 /e/MemOmics-Agent）→ PowerShell 命令必须整体用**单引号**包裹，否则语法报错。
⛔ wmic 已弃用返回空，用 Get-CimInstance 替代。
识别结果：`webui\\server.py` / `cellbender_guardian.py` = 系统守护（不算活跃分析）；`Rscript` / `cellbender remove-background` / 分析脚本路径 = 真实分析进程。

**R/ArchR 进程判定（唤醒 #5 实测 2026-08-08）**：`tasklist | grep -iE "Rscript|R\.exe|archr"` 在 MSYS 下可能
混入不匹配的系统进程（NVDisplay.Container/nvcontainer/qmlauncher/AndrowsSvr 等 NVIDIA/Windows 驱动守护）。
判"无分析进程"看的是**进程名列表里没有 Rscript/R.exe/分析脚本路径**，不是 grep 输出为空——输出非空但有进程名清单
仍可安全判定"无活跃分析"。R 分析进程特征：`Rscript.exe` + 命令行含分析脚本（如 `archr_script.R`）；驱动守护进程不算。
⛔ **`Rscript.exe ... _kernel_worker.R` = 系统组件，不是分析进程（唤醒 #2 实测 2026-08-09）**：这是 execute_r 的持久内核 worker，
CPU 时间持续增长、心跳监控会把它误判为活跃分析并报 STALL（假警报）。判定活跃分析**必须先看命令行**——只有命令行含分析脚本
路径（如 `archr_script.R`）的 Rscript 才算活跃；`_kernel_worker.R` 出现 = 正常系统组件，心跳 STALL 是假警报，不要干预。

**进程源快速判空首选 `//FI` 过滤器，替代 grep 全列表（唤醒 #3 实测 2026-08-09）**：
`tasklist //FI "IMAGENAME eq Rscript.exe"`（MSYS bash 下**双斜杠**防路径转换）+ 同样查 `python.exe` 两条命令，过滤在源头做，
无匹配时输出仅表头+`---` 一行——**完全避开 grep 全列表的驱动守护混入/正则误匹配问题**，判空无歧义。
→ 判定：仅表头 = 无该类进程；命中 → 用 Get-CimInstance 查命令行区分分析进程 vs `_kernel_worker.R`/webui 守护。
→ 与 `search_files` 产出清单 + task_plan 状态拼成三源验证的进程源，干净且零假警报。
→ ⚠️ **`//FI` 双斜杠并非所有 bash 环境都生效（唤醒 #9 实测 2026-08-09，memomics-1c1890da）**：同一台机器上
   `tasklist //FI "IMAGENAME eq Rscript.exe"` 直接报 `无效参数/选项 - '//FI'`（MSYS 下乱码中文 `����: ��Ч����/ѡ�� - '//FI'`）——
   双斜杠未被 MSYS 路径转换展开，tasklist 收到字面 `//FI`。判空只能靠 `|| echo` 兜底（exit 0 但无进程清单）→
   兜底 echo **不是有效进程源**，不能以它充当三源验证。处置：`//FI` 报错 → **立即转 Get-CimInstance**（见上方/下方
   完整命令），不再重试 `//FI`/`/FI` 变体；`|| echo NO_*` 兜底仅用于防 exit 1 记失败，结论必须由 CIM 输出支撑。
→ **python 快速分流：`//FI python.exe` 输出再按分析脚本关键词 grep（唤醒 #1 实测 2026-08-09）**：
   `tasklist //FI "IMAGENAME eq python.exe" | grep -iE 'phylop|l1_|download|ortholog|heartbeat|cellbender'`
   grep 无命中 = 无分析相关 python 进程，直接判空，**免去 Get-CimInstance 全列表排查**；命中才需 CIM 区分
   系统守护 vs 真实分析。关键词按本次项目实际脚本名定（如跨物种专利项目=phylop/l1_/download/ortholog），
   比 grep 全列表（混 webui/server.py 守护）更精准，比直接对 python.exe 全量 CIM 更省。
   ⚠️ **`| grep` 无命中 = exit 1 = 终端工具记失败（唤醒 #9 实测 2026-08-09）**：`tasklist //FI ... | grep -iE '...'`
   在无分析进程时 grep 返回 1，harness 把整条命令记作失败并累积"连续失败"计数（实测同一命令模式被记 19 次
   失败、触发上限告警"连续失败 19 次（上限 3）"）——判空结论本身是对的，但别用裸 grep 结尾的复合命令重复跑。
   修复二选一：
   ① 追加兜底：`tasklist //FI "IMAGENAME eq python.exe" | grep -iE '...' || echo NO_ANALYSIS_PROC`
      （grep 无命中时 echo 兜底 → exit 0，不再被记失败）
   ② 直接 Get-CimInstance（本会话实测可靠）：
      `powershell -Command 'Get-CimInstance Win32_Process | Where-Object {$_.Name -match "Rscript|python|cellbender"} | Select-Object ProcessId,Name,CommandLine | Format-Table -AutoSize -Wrap'`
      单引号整体包住防 MSYS 展开 `$_`；输出直接可判：webui/server.py + cellbender_guardian.py +
      _kernel_worker.R = 仅系统组件，无分析进程。

**终态清理：遗留"空跑"进程（唤醒 #2 实测 2026-08-09）**：主线全部 completed 时，进程源常残留非分析进程，占资源+持续写日志：
→ 心跳监控（`heartbeat_*.py`）分析完成后仍在跑，监控已死任务，持续写 heartbeat log 并误报 STALL → 杀掉
→ 弃用下载循环（`download_*.sh` + curl 断点续传）：某资源已弃用但下载没停（本会话 gene_orthologs.gz 因 Ensembl Compara 不可用
   已改走 NCBI gene XML，下载却仍在续传至 51MB）→ 对照 memory/task_plan 确认弃用后杀掉
→ 判定：`powershell Get-CimInstance` 查命令行含 `heartbeat|download|ortholog` → 逐个确认目的 → `taskkill /F /PID <pid>` 批量清理
   （本会话一次清 8 个：4 心跳 + 4 下载）；⛔ 只杀确认弃用/空跑的，`_kernel_worker.R`/`webui/server.py`/`cellbender_guardian.py` 不能杀
→ 清理后更新 task_plan 唤醒记录（写清杀了哪些、为什么），保持 plan 自洽

## Step 4: 汇报

- **有活跃任务** → 汇报进度 + 继续推进当前 Phase。
- **全部终态** → 如实汇报"无活跃任务"，逐条列出：每条主线的状态、验证证据、待用户确认的阻塞项。
- ⛔ **红线：终态任务不自动重启，阻塞项（如"等待用户明确指示后启动"）绝不自动执行**——只列出选项让用户选。
- 汇报格式：状态表 + 主线摘要 + 下一步选项（编号列表，简洁）。
- **选项菜单三查（2026-08-08 #7/#11/#14 三次漏用后强制，唤醒 #17 首次完整通过）**：凡是有 pending 被阻塞的下一步，菜单必须逐项勾选——
  ① 越线动作（需用户放行，如启动新 Phase）
  ② **不越线 prep 中间档**（只读/下载/准备类，如"先做数据检查/EDA 再定"、ortholog 映射、chain 文件准备）——最易漏，漏了用户只能全盘确认
  ③ 保持现状 / 其他任务
  三项缺一 = 不合格菜单。**中间档不必限定一种形态**：任何"先放行的准备性工作"都满足三查。
→ **唤醒 #5 反面例（2026-08-08 猴-人 ATAC 跨物种项目）**：pending = Phase 4（人海马 merge+LSI+聚类）与 Phase 7（猴-人 CRE 对比），
   菜单只列了两条越线启动项 + 隐含"保持现状"，**未列 prep 中间档** → 不合格（用户只能全盘确认）。
   本项目合法中间档：① 校验/下载 T2T-MFA8v1.1→hg38 liftover chain 文件；② 构建猴-人 1:1 ortholog 基因映射表；
   ③ 逐样本复核 fragments .tbi 索引完整性。均为只读/下载/准备类，不越线，可直接放行。

## Mid-Task 唤醒变体：进程已死但可修复（2026-08-08 memomics-1c1890da 验证）

mid-run 唤醒发现**进程已死**（heartbeat `rscript=` 为空 / tasklist 无 Rscript）+ 日志尾部有明确报错（如 `错误: 'ArchRProj'的值没有`）时，正确动作**不是**"只汇报不干预"——需要区分三种情形：

| 情形 | 信号 | 动作 |
|------|------|------|
| 进程活着 | Rscript 在跑、日志在推进 | 不干预，确认推进正常即可 |
| **进程死了 + 可修复错误** | 无 Rscript + 日志尾部是参数/逻辑错误（ArchR 参数错、脚本 bug） | **修复续跑**：skill patch 根因 → 改脚本 → 写续跑脚本从已有 checkpoint 恢复（如 umap.rds 已保存则跳过 LSI/UMAP 只跑 addClusters）→ background 重跑 → 更新 task_plan Errors Encountered + skill |
| 进程死了 + 外部依赖缺失 | 无 Rscript + 缺文件/数据/权限 | 汇报缺口，等用户放行 |

**执行要点**：
1. 报错日志常在前一步产出已落盘之后（如 UMAP 保存后 addClusters 崩）——先查已有 checkpoint rds，能续跑就不从头
2. 运行类修复（>10min）必须 background + notify_on_complete，避免 foreground 超时二次被杀
3. 修完必须把根因写入 task_plan Errors Encountered + 对应 skill（防下次同坑）
4. ⛔ 修复续跑时**禁止在 shell 命令里 rm 旧产物**（删除保护拦截 + 用户铁律）；ArchR 脚本内部 `force=TRUE` 同名覆盖即可

## Mid-Run 变体 B：进程活着但进入长静默阶段（2026-08-08 memomics-1c1890da 验证）

**场景**：Rscript 活着、heartbeat 也在跑，但脚本 stdout 日志已冻结 N 分钟（ArchR getMatrixFromProject/TileMatrix 提取等阶段切换间不写日志，10-30 min 静默是**正常**的）。此时不要反复 `tail` 日志干等，也不要在 1-2 次无进展后就判定卡死。

**正确动作 = 部署输出-watcher + ad-hoc 运行时验证**：

1. **输出-watcher 脚本**（monitor_02c.sh 模式，bash 循环）：
   - 每 20s 检查**期望产出文件是否存在**（如 annotation CSV + RDS 都出现 → 打印 DONE + ls 产出 → exit 0）
   - 同时检查**进程是否死亡但产出缺失**（`tasklist /FI "IMAGENAME eq Rscript.exe"` 无 Rscript + 无产出 → tail 日志尾部 + exit 1）
   - 设超时上限（如 120 轮 × 20s = 40min）→ 超时 tail 日志 + exit 2
   - `terminal(background=true, notify_on_complete=true)` 启动 → 完成/失败/超时都会自动通知，Agent 不用轮询
2. **ad-hoc 运行时验证**（临时脚本 + PASS/FAIL 计数，验证完即删）：① watcher bash -n 语法 ② Rscript 进程存活 + 内存 ③ 日志存在 + mtime ④ watcher 进程存活。PASS=4 FAIL=0 即通过。
3. **watcher 逻辑 mock 验证（升级版，2026-08-08 唤醒 #1 实测）**：运行时验证只证明\"进程活着\"，**不证明 watcher 逻辑正确**。当 watcher 是本会话新部署的，或系统要求\"新鲜验证证据\"时，在临时目录 mock 三分支逻辑：
   - **分支 DONE**：`mkdir` mock 目录 + `touch` 期望产出文件 → `sed "s|OUT=<真实目录>|OUT=<mock目录>|"` 生成 mock watcher → 跑 → 期望输出含 `DONE:` 且 exit 0
   - **分支 PROC_DIED**：mock 空目录 + `sed 's|sleep 20|sleep 1|'` 加速 → 跑 → 期望输出含 `PROC_DIED` 且 exit 1
   - **分支 TIMEOUT**：grep watcher 里超时分支存在（如 `TIMEOUT 50min`）即可
   - PASS/FAIL 计数，FAIL=0 通过；mock 脚本 `trap 'rm -rf "$TMP"' EXIT` 自清理，验证完删临时脚本（不污染真实目录）
   - 💡 可复用脚本：`scripts/verify_watcher.sh <watcher路径>` 一条命令完成 A/B/C/D 四检查（本会话实证，见 2026-08-08 唤醒 #1）
   - ⚠️ **分支 C 假失败（2026-08-08 唤醒 #2 实测，PASS=3 FAIL=1）**：分支 C mock 的 PROC_DIED 判定用真实 `tasklist /FI "IMAGENAME eq Rscript.exe"`——若验证瞬间**机器上真有 Rscript 在跑**（如 02e 注释进程还活着），mock watcher 看到进程存在 → 不触发 PROC_DIED → 循环到 TIMEOUT 或意外 exit 0 → 报 ❌。**这不是 watcher 逻辑错，是验证环境被真实进程污染。** 处置：① verify_watcher 前先 `tasklist | grep Rscript` 确认无同名进程；② 或对分支 C 的 sed 额外把 `Rscript.exe` 替换成不可能存在的名字（如 `NO_SUCH_PROC.exe`），mock 才能独立于真实环境触发死进程分支；③ 判定：A/B/D 全 PASS + C 假失败（真实 Rscript 在跑）= watcher 实际可用，先杀/等进程结束再复验 C。
4. **长脚本的\"验证\"= 运行时验证**：进程存活 + 日志推进 + 最终产出物生成，三者就是证据。中间阶段产出未写盘 = 预期行为（脚本设计为阶段完成才写），不是失败。
5. ⚠️ **task_plan 引用的脚本名可能已陈旧（唤醒 #1 实测）**：task_plan 记录\"后台运行中 02b_annotate_human_bg.R\"，但真实运行已升级为 02c_annotate_human_tile.R（02b 崩溃后迭代）。**报\"在跑哪个脚本\"前必须 `ls -lt <工作目录>/*.{R,log}` 看最新 mtime**，以目录里最新脚本/日志为准，不要直接照抄 task_plan 的脚本名——否则汇报错脚本、错误判定进度。
6. 汇报状态：进程活着 → 不干预，等 notify。产出出现则验证产物并推进下一 Phase；进程死亡则按上方变体 A 修复续跑。

## 相关

- 长任务心跳监控（Agent 不在场时的自动检测）：`heartbeat-monitor` skill
- ATAC 专项的唤醒门禁细节：`atac-seq-memomics` references/post-completion-wakeup-gate.md
