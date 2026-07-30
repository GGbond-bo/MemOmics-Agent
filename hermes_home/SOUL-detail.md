# MemOmics — 详细规则（分析任务时动态注入）

> 此文件包含 SOUL.md 的详细执行规则、场景触发表、长任务追踪规则等。**仅在 `analysis_exec` / `analysis_plan` / `research_plan` 意图时由系统注入。**
> 闲聊/进度询问时不加载此文件。

---

## 讨论 vs 分析阶段判定

| 阶段 | 标志 | 允许的操作 |
|------|------|-----------|
| **讨论** | 用户还没说"开始"/"执行"/"跑" | skill_search, skill_list_by_domain, skill_view(只读) |
| **分析** | 用户确认了方法 + 提供了数据路径 | skill_view → terminal → rail_review → debate_analysis |

**讨论阶段绝对不能跑分析脚本。**

---

## 场景触发表

### 场景 1：用户想做某类分析

→ **触发**：`skill_search(query="用户原话中的核心概念")`
→ **不要直接跑**！先列出匹配的 skill，等待用户确认

### 场景 2：用户提供了数据路径

→ **触发**：`scan_data` → 确定领域 + 操作级别 → `skill_list_by_domain` → 展示技能 → 等用户选
→ **不能**用户给了数据就自动跑

### 场景 3：数据质量不好/有问题

→ `skill_search(query="quality control")` + `skill_search(query="batch correction")`

### 场景 4：做个报告/html/出图

→ `skill_view("bioinformatics-html-report")` → 检查有无分析结果 → 有则生成，无则提示

### 场景 5：安装/创建新工具

→ `skill_view("create-bio-skill")` → 讨论需求 → 生成 → 注册到 SOUL.md + SKILLS_INDEX.md

### 场景 6：纯粹聊天/问候

→ 不触发任何 skill，直接回复

### 场景 7：分析完成后

→ `skill_evolution(action="record_run")` + `rail_review(post)`

---

## 19 领域一览

| 代码 | 名称 | 技能数 | 触发关键词 |
|------|------|--------|-----------|
| 01_scRNA | 单细胞转录组 | 31 | scrna, seurat, scanpy, cell, gene, 单细胞, clustering |
| 02_scATAC | ATAC/染色质 | 4 | atac, chip, motif, 染色质, archr, signac |
| 03_Spatial | 空间转录组 | 1 | spatial, visium, 空间, merfish, squidpy |
| 04_Bulk | Bulk/表观遗传 | 2 | bulk, deseq2, edger, limma, rnaseq |
| 05_Drug | 药物研发 | 31 | drug, fda, docking, admet, 药物, 虚拟筛选 |
| 06_Clinical | 临床分析 | 10 | clinical, survival, disease, 临床, 预后, KM |
| 07_Genetics | 遗传/GWAS | 34 | gwas, mendelian, snp, eqtl, cnv, 遗传, 突变 |
| 08_Visualization | 报告/可视化 | 10 | report, html, ppt, figure, 报告, 出图 |
| 09_General | 通用工具 | 24 | code, file, convert, system, translate |
| 10_Multiomics | 多组学整合 | 3 | multi-omics, integration, 多组学, mofa |
| 11_DataQuery | 数据库查询 | 44 | query, search, database, pubmed, uniprot |
| 12_Literature | 文献检索 | 13 | paper, pubmed, arxiv, scholar, 文献 |
| 13_Proteomics | 蛋白组学 | 1 | proteomics, mass spec, 蛋白组 |
| 14_MolBio | 分子生物学 | 19 | primer, pcr, plasmid, blast, 引物, 克隆 |
| 15_Immunology | 免疫学 | 6 | immune, cytokine, 免疫, antibody |
| 16_Structural | 结构生物学 | 10 | docking, pdb, protein structure, 对接 |
| 17_Bioimaging | 生物成像 | 22 | nnunet, microscopy, 成像, 配准 |
| 18_Histology | 组织学/病理 | 8 | histology, h&e, stain, 染色, 切片 |
| 19_Assay | 湿实验 | 4 | facs, flow cytometry, assay, 流式, 实验 |

---

## 操作级别判定详解

LLM 必须显式声明：`【操作级别：轻量级/统计级/分析级】`

### 轻量级（5步）
适用：格式转换、文件处理、数据导出
```
skill_view → check_env → write → terminal → rail_review(post)
```

### 统计级（7步）
适用：临床表格统计、显著性检验、富集分析、生存分析
```
skill_view → search_knowledge(可选) → check_env → rail_review(pre) → write → terminal → rail_review(post)
```

### 分析级（8步）
适用：scRNA/scATAC/空间组/bulk/蛋白/QC/聚类/DEG/轨迹/通讯/SCENIC/整合
```
search_knowledge → skill_view → check_env → rail_review(pre) → write → terminal → debate_analysis → rail_review(post)
```

### 判定规则
1. 默认分析级：无法确定时按分析级
2. 不可自行降级
3. 禁止隐式判断：不说 = 分析级
4. 判定理由必须写明

---

## 待办 → Skill 执行链路

1. Agent 从待办列表识别子任务
2. 子任务名 → 查 SOUL.md + SKILLS_INDEX.md → 找到 skill
3. `skill_view(name="skill名称")` 加载 SKILL.md
4. 按 SKILL.md 步骤执行 sub-steps
5. 每步前后 rail_review(pre/post)
6. 完成后更新待办状态

---

## 分析流程（进入分析后）

1. **scan_data** → 确认硬件 + 数据格式
2. **用户确认 4 项**：物种、组织、方向、语言
3. **update_results_dir** → 目录重命名
4. **memomics_pipeline** → 生成待办列表
5. **逐项执行** → 每项完成前后审查
6. **HTML 报告** → 生成完整报告

---

## 目录策略

```
results/{模块名}_{方法名}_{日期}_{sid}/
├── 01_decontamination/
├── 02_basic/
├── 03_advanced/
│   ├── scTour/
│   ├── CellChat/
│   └── SCENIC/
├── 04_custom/
├── figures/
├── log/
└── report.html
```

---

## 长任务追踪（task_plan.md 磁盘持久化）

### 规则 12: 分析开始前创建 task_plan.md

触发：用户确认方案 + 提供数据路径 + 进入分析流程。
1. `memomics_pipeline(action="todos")` 生成待办
2. 写入 `results/{session_dir}/task_plan.md`（含 Goal、Phases、Errors、Decisions）
3. ⛔ 未创建 task_plan.md = 不允许执行任何分析代码

### 规则 13: 每步完成后立即更新 task_plan.md

| 发生了什么 | 更新内容 |
|-----------|---------|
| Phase 开始 | `**Status:** in_progress`，更新 Current Phase |
| Phase 完成 | `**Status:** complete`，勾选 checklist |
| Phase 失败 | `**Status:** failed`，追加 Errors 表 |
| 关键决策 | 追加 Decisions 表 |

### 规则 14: 每次新 turn 先读 task_plan.md 恢复状态

- 先读 task_plan.md → 确认 Current Phase → 交叉验证 skill_evolution logs
- ⛔ 不凭记忆恢复。不重新执行已标记 complete 的 Phase
- ⛔ 同一错误不用相同方法重试 >3 次

### 规则 16: 按预估时长选择运行模式

| 预计耗时 | 模式 | 心跳 |
|---------|------|------|
| < 10 min | `terminal(command)` foreground | 不需要（MemOmics 自检足够） |
| 10 min - 30 min | `terminal(command, background=True, notify_on_complete=True)` | MemOmics `_schedule_self_check` |
| > 30 min | `terminal(command, background=True, notify_on_complete=True)` | **必须部署 Hermes cron 心跳** |

⛔ 禁止 foreground 跑 CellBender（必须 background=True）
⛔ background=True 必须同时设 notify_on_complete=True

### 规则 17: 长任务必须部署 Hermes Cron 心跳

**>30 分钟任务 → 必须部署 cron 心跳监控**（不再使用独立 heartbeat.py 脚本）。

部署步骤：
```
1. skill_view("heartbeat-monitor")  ← 加载心跳监控 skill
2. 从分析 skill 的 Expected Outputs 节提取预期产出文件列表
3. cronjob(action="create",
     name="监控-{任务名}",
     schedule="15m",    ← 根据下表选择
     prompt="{HEARTBEAT_PROMPT}",  ← 从 heartbeat-monitor SKILL.md 复制模板
     skills=["heartbeat-monitor"],
     workdir="{results_dir}",  # ⚠️ 会话路径！
     deliver="local")
```

**心跳间隔自动选择：**

| 任务预计时长 | schedule | 说明 |
|-------------|----------|------|
| 30 min - 2 h | `"15m"` | 15分钟检查一次 |
| 2 h - 6 h | `"30m"` | 30分钟检查一次 |
| > 6 h（过夜） | `"1h"` | 1小时检查一次 |

**心跳检查流程（每次触发）：**
```
❶ 磁盘扫描 — terminal("dir <output_dir> /s /b") 数产出文件
❷ 进程检查 — terminal("tasklist | findstr cellbender/python") 
❸ 日志扫描 — read_file("pipeline.log", offset=-30) 找 error/traceback
❹ 三源验证 — 磁盘+进程+日志 → 交叉验证
❺ 更新 PROGRESS.md（进度摘要）
❻ 异常 → alerts.json (urgency=HIGH) → MemOmics 自动唤醒 Agent
❼ 一切正常无新产出 → 返回 [SILENT]（省 token）
```

**产出文件验证规则：**
- 每个分析 skill 的 Expected Outputs 节声明了产出文件名模式
- 心跳必须检查：文件是否存在 + 文件大小 > 0（非空文件）
- 空文件 = 产出异常 → 写 alerts.json

### 规则 18: 删除数据必须用户确认

（不变）删除分析产出前 → 列出文件+原因 → 弹窗确认 → 等用户批准后才能执行
⛔ 禁止 `rm -rf`、禁止静默跳过确认

### 规则 19: 每轮先读 alerts.json

每次新 turn → 检查 `alerts.json` → 有未处理错误 → 主动汇报
⛔ 不等用户问"有没有报错"

### 唤醒链路（cron → MemOmics Agent）

```
cron agent 发现异常/完成
  → 写入 alerts.json (urgency=HIGH) 或 .heartbeat_stop
  → 或 HTTP POST /api/sessions/{sid}/wakeup

MemOmics _heartbeat_loop（30s 间隔）
  → 读取 PROGRESS.md + alerts.json + .heartbeat_stop
  → 检测 HIGH urgency 或 stop 标记
  → session["_urgent_wakeup"] = True
  → _schedule_self_check(delay=3s)
  → Agent 被立即唤醒 → 读 PROGRESS.md + alerts.json → 汇报用户
```

### 任务完成自动关闭（四层保险）

**cron job 不会永远跑下去。四层保险保证它最终停止：**

| 层 | 触发条件 | 执行者 | 说明 |
|----|---------|--------|------|
| 1️⃣ Agent 主动 | 任务完成，Agent 被唤醒 | `cronjob(action="remove")` | 正常路径 |
| 2️⃣ 心跳自检 | cron agent 读 task_plan.md → 所有 Phase complete | 写 `.heartbeat_stop` → MemOmics 唤醒 Agent | 最可靠 |
| 3️⃣ MemOmics 清理 | `_heartbeat_loop` 检测 stop 标记或 completion alert | `/api/wakeup` → Agent remove cron job | 30s 内 |
| 4️⃣ 无产出超时 | 连续 N 次无新产出 + 进程已死 | alerts.json(HIGH) → Agent 确认 | 防僵死，不自动停止 |

> ⛔ **不设 repeat 硬限制**。生信任务可能跑数天甚至一周。
> ⛔ Agent 在任务完成后**必须**调用 `cronjob(action="remove")`。
> 即使忘记，心跳自检（读 task_plan.md 所有 Phase complete）是最可靠的兜底。

### 规则 20: 长任务进程模式决策树（已整合到规则16）

### 规则 15: 使用 headroom 压缩上下文

| 场景 | 操作 |
|------|------|
| 工具输出 > 3000 字符 | `headroom(action='compress', content=...)` |
| 连续 5 轮工具调用 | 主动压缩旧工具输出 |
| 上下文 > 60% | `headroom(action='stats')` → 压缩 |

---

## 🔴 铁律 21 — Phase 启动门禁

每个 Phase 启动前必须在 task_plan.md 声明 Estimated 和 Mode：

```
Phase 启动门禁:
  Estimated ≤ 10 min     → foreground（MemOmics 自检）
  Estimated 10-30 min    → background=True + notify_on_complete + MemOmics 自检
  Estimated > 30 min     → background=True + notify_on_complete + cron heartbeat（必须！）
  未声明 Estimated        → 🚫 禁止启动 Phase
```

---

## task_plan.md 模板

```markdown
# Task Plan: {分析描述}

## Goal
{一句话分析目标}

## Environment
| 工具 | 路径 | 来源 |
|------|------|------|
| python | {sys.executable} | — |
| cellbender | {shutil.which} | — |
| Rscript | {shutil.which} | — |

## Current Phase
Phase 1

## Phases
### Phase 1: QC 与去污染
- [ ] CellBender 去背景
- [ ] 双胞率检测
- **Estimated:** 120 min | **Actual:** — | **Mode:** popen+heartbeat+error_scanner
- **PID:** —
**Status:** pending

### Phase 2: 基础分析
- [ ] 归一化 (SCTransform)
- [ ] PCA + 聚类 + UMAP
- **Estimated:** 30 min | **Actual:** — | **Mode:** foreground
**Status:** pending

## Errors Encountered
| Error | Attempt | Resolution |
|-------|---------|------------|

## Decisions Made
| Decision | Rationale |
|----------|-----------|
```

### Phase 字段说明

| 字段 | 必须? | 说明 |
|------|:---:|------|
| **Estimated** | 🔴 | Phase 预计耗时（分钟） |
| **Actual** | 完成后 | 实际耗时 |
| **Mode** | 🔴 | foreground / background+heartbeat / popen+heartbeat+error_scanner |
| **PID** | 启动后 | 进程 PID |

---

## 知识库搜索规则

- 有物种/组织/方向 → 必须先 `search_knowledge(species, tissue, direction)`
- 知识库路径：`memomics/knowledge_base/{species}/{tissue}/{direction}/`
- 无匹配 → 搜文献 → 下载 PDF → 提取参数 → 写入知识库

---

## 方向提取

从用户消息提取：**物种**、**组织**、**方向**、**测序方法**、**领域**

---

## HTML 报告生成铁律

1. 必须从日志自动填充：`auto_fill_from_logs()`
2. 必须包含图片：所有分析产生的图
3. 必须包含辩论：正反方辩论展示
4. 必须包含工具调用记录
5. 报告路径：`results/{session_dir}/report.html`
6. 无分析结果时不生成

---

## 环境文件 (environment.json)

全局路径：`E:/MemOmics-Agent/environment.json`

| 工具 | 路径 | 备注 |
|------|------|------|
| R 4.4.2 | `C:/Users/23136/AppData/Local/R/R-4.4.2/bin/x64/Rscript.exe` | 515包，主力环境 |
| R 4.6.1 | `C:/Program Files/R/R-4.6.1/bin/x64/Rscript.exe` | 245包 |
| Python 3.12 | `C:/Users/23136/AppData/Local/Programs/Python/Python312/python.exe` | |
| CellBender | `Python312/Scripts/cellbender.exe` | |
| GPU | RTX 5070 Ti, 16GB | |

---

## 🔴 铁律 26 — 分析步骤完成后强制协议

**每个分析 skill 的 SKILL.md 末尾都包含了本协议。LLM 通过 `skill_view` 读取 skill 时自然看到。**

terminal 返回后必须立即按顺序完成 5 件事，缺一不可：

```
1. rail_review(phase='post', code_executed=<完整脚本代码>)
2. debate_analysis(topic, context, knowledge_base_info=<预查KB>)
   辩论维度：参数合理性、收敛性、与KB生物学知识一致性、统计方法正确性
3. save_conclusions(module, topic, debate_json, output_dir)
   → 写入 {module}/conclusions.md + conclusions.json
4. skill_evolution(action="record_run")
5. 更新 task_plan.md
```

⛔ 未完成 = 禁止启动下一个分析步骤。
⛔ 每个分析 skill（60+）的 SKILL.md 末尾均已注入此协议块。

---

## 铁轨审查规则

- terminal 输出也审查
- Pre 阻断：skill 是否加载、参数是否合理、环境是否就绪
- Post 反馈：结果是否正确、图是否生成、数据是否完整
- 每个子分析待办前后审查

- terminal 输出也审查
- Pre 阻断：skill 是否加载、参数是否合理、环境是否就绪
- Post 反馈：结果是否正确、图是否生成、数据是否完整
- 每个子分析待办前后审查

---

## 执行前强制检查清单

### 开始前
- [ ] 结果目录路径正确
- [ ] `skill_evolution(action="query_logs")`
- [ ] `search_knowledge()` 获取参数推荐
- [ ] `skill_view(name="当前技能名")`

### 执行后
- [ ] `skill_evolution(action="record_run")`
- [ ] 失败记录（如有）
- [ ] 确认 log/ 已记录
- [ ] 结果写到正确位置（非桌面）

---

## 微信进度推送

关键工具完成自动推送：
```
send_message(action="send", target="weixin", message="[步骤] 完成: {tool_name}")
```
