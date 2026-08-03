# 任务完成后的唤醒门控协议（Post-Completion Wakeup Gate）

> 适用场景：Phase 1-N 全部 complete 后，系统唤醒（`⏰ [系统唤醒 #N]`）或用户主动问进度。
> 2026-08-02 session memomics-1c1890da（猴海马 scATAC ArchR 全流程）验证。
> 这是"跑完 ≠ 收尾"教训的延伸：**跑完 ≠ 下一步可以自动启动**。

## 核心原则

唤醒检查**不是**执行入口。默认姿态 = 汇报 + 等指示，除非用户本次明确说"继续"。

## Step 0: 定位当前 session 的 task_plan（多个 task_plan 并存时）

`search_files(pattern="task_plan.md", path="E:/MemOmics-Agent/results")` 会命中**多个历史 session 的 task_plan**（实测 6 个）。读错 session 的 plan → 基于旧任务状态做判断 → 触发跨 session 污染。

定位方法（按优先级）：
1. 当前会话上下文 / 记忆中的 session ID（如 memomics-1c1890da）
2. 磁盘上有最新活跃产出（log/脚本/心跳文件更新时间最近）的目录
3. 与最近一次记录在案的任务匹配的目录

> ⛔ 拿到 task_plan 后先核对 Current Phase 里的 session 标识与任务内容是否与本次唤醒上下文一致，不一致即停，不要"继续执行下一个待办"。

## Step 1: 三源验证（铁律 -2）

| 源 | 做什么 | 证据 |
|----|--------|------|
| ① task_plan.md | 读 Current Phase + ⛔ 标记 + Output 路径 | 每个 Phase 的 Status 行 |
| ② 磁盘产出 | search_files / terminal ls -lt 实查文件数 + 大小 + 时间戳 | 不能只读 task_plan 声称的路径 |
| ③ 进程 | tasklist 查 Rscript/python 残留 | 无进程 + 产出落盘 = 任务确已结束 |
| ④ GPU 空闲 | nvidia-smi --query-gpu=utilization.gpu,memory.used --format=csv,noheader | 唤醒 #18 实测 GPU 3%/3970MiB = 无 CUDA 分析在跑；高占用 + tasklist 无进程 = 需进一步查（可能是未捕获的 GPU 任务） |

> ⛔ 产出路径按 task_plan 的 Output / Environment 段查，不凭记忆。

## Step 2: 检查"停止/等待"标记（最关键）

task_plan.md 或记忆中有任一信号 → **绝不自动启动下一步**：

- `用户下达"停止"命令` / `等待用户指示后再启动` 等 ⛔ 标记
- 记忆中的 BLOCKED_KEYWORDS（CellBender / Monkey / 未指令任务）
- 用户明确说过"先不要跑" / "不要动" / "等我"

即使 Phase 全部 complete、即使 task_plan 写了"后续计划"，只要用户下过停止命令 → 只汇报 + 给选项。

## Step 3: 检查外部依赖门控

下一步依赖的外部资源未就位 → 也不启动，明确报告缺口：

- 用户手动下载的数据集（如 GSE278576 人海马 ATAC 40 样本仅 2 个就位）
- 跨机器 / 需用户操作的环境
- 需要用户确认的新分析方向（如跨物种对比 = 新任务，不是自动延续）

汇报里写清楚"有几个 / 缺几个"，避免反复问"要不要启动"。

### 手动下载样本的"就位"判定（2026-08-02 唤醒 #12 细化）

数文件数不够，必须做**逐样本就位检查**：

1. **按样本对检查**：fragment 数据集就位 = `.tsv.gz` **和** `.tbi.gz` 两个文件都在。
   单个 `.tsv.gz` 没有索引（如 hc78 缺 `GSM..._atac_fragments.tsv.gz.tbi.gz`）→ 该样本**不可用**，
   ArchR `createArrowFiles()` 需要 Tabix 索引。报告为"hc77 就位、hc78 缺索引"而不是"2/40"。
2. **文件大小 sanity check**：ATAC fragment 文件正常应数百 MB 级。若整个目录只有几 MB
   （2026-08-02 实测 2 样本共 3.0MB）→ 要么下载不完整、要么只有测试文件，不能视为可用数据。
3. **剔除杂散文件**：目录里可能残留测试文件（如 `test_speed.bin`，带宽测试遗留），计数时排除。

## Step 4: 汇报格式（结论先行）

1. **完成状态表**：Phase / 内容 / 状态 / 关键产出（产出要实查过的路径 + 大小）
2. **挂起原因**：停止命令 / 外部依赖缺口（一句话）
3. **可选下一步**：明确哪些等用户、哪些可做 pilot（如"先跑 hc77/hc78 两个样本验证流程可行性"）

## Step 4b: 已知遗留产出（0-byte / 失败修复）处理 — 2026-08-02 唤醒 #14 验证

task_plan 的 Issues 段记录过、且修复尝试已失败的产出（如 `Volcano_Young_vs_Old.pdf`/`Volcano_plot.png`/`MA_plot_Young.pdf` 三个 0-byte 文件，`18_fix_plots.R` 失败）：

- **汇报为"已知遗留（不阻塞）"**，列出具体文件名 + 大小，说明修复已试过失败
- **修复作为"可选下一步"给出**（如"补 Volcano 0 字节文件"），**不自动重跑**——0-byte 对低信号对比方向是确定性的，重跑无效（见 da-plotting-fallback.md）
- 关键：与挂起原因分开列——遗留文件不阻塞主线完成，但要在汇报里透明呈现，不能藏

## Step 4c: 停止命令后清理残留守护进程 — 2026-08-02 唤醒 #13 验证

**用户质疑："怎么还在跑呢？心跳机制不应该结束了吗？"** → 三源验证发现真正在跑的不是当前分析进程，而是**历史 session 遗留的守护脚本**（cellbender_guardian.py ×2，7-30 启动后未清）。

**根因**：每次部署 heartbeat/guardian 用 `subprocess.Popen` + `CREATE_NO_WINDOW`（脱离 Agent 生命周期）后，**停止命令只 kill 了主分析进程，没清理这些守护脚本**。它们会一直挂到系统重启。

**修复协议**（用户说"停止/清理后台"时，除了 task_plan 标记 + cronjob 暂停 + 主进程 kill，还必须）：
1. `process(action='list')` 查 Hermes 后台进程
2. `tasklist | grep -i python` 查 python 守护（guardian/heartbeat 通常是 python）
3. 区分：`webui/server.py` = Hermes 框架自身（**不能杀**）；`*_guardian.py` / `*_heartbeat*.py` = 任务守护（**杀**）
4. `taskkill /F /PID <pid>` 逐个清理，**按文件名核对后再杀**（避免误杀框架服务）

**用户问"为什么你不监督"的诚实回答模板**（不是借口，是架构说明）：
- Agent 是 turn-based 请求-响应模型：你发消息→我响应→回合结束，两次消息之间不"活着"
- `notify_on_complete` 通知在用户新消息触发的全新 turn 里可能被吞掉
- 正确姿态：**每个 turn 开头先 `process(action='list')` + 查进程**，不等通知；主动轮询是唯一可靠方式
- 用户要的不是道歉，是根因 + 修复 + 下次不再犯

## 本次验证案例（2026-08-02）

- task_plan: Phase 1-6 complete ✅（环境→QC→LSI/UMAP/聚类→TileMatrix+DA→可视化报告→Motif）
- 产出实查: ArchR_ATAC_Analysis_Report.html 2.65MB、Motif_Top_Old/Young.png、motif_rank CSVs
- 进程: tasklist 无 Rscript → 三源一致
- ⛔ 标记: task_plan 记录用户 2026-08-02 下达"停止"命令，跨物种对比等指示
- 外部依赖: GSE278576 40 样本仅 hc77/hc78 2 个就位（且 hc78 缺 tbi 索引）→ 无法启动猴-人 CRE 对比
- 正确动作: 汇报状态 + 挂起原因 + 给 3 个选项（等下载齐 / hc77+hc78 pilot / 其他），不自动启动
