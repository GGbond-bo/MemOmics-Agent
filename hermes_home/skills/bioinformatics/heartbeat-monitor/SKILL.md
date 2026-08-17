# Heartbeat Monitor — 长任务心跳监控

## 何时触发

Agent 启动任何预计 **> 60 分钟** 的分析任务时，**必须**同步部署心跳监控。

触发条件（满足任一）：
- `estimated_minutes > 60`
- 命令包含 CellBender / 大规模聚类 / 训练 / 批量处理（通常 >1h）
- task_plan Phase 的 Mode 声明为 `background+heartbeat`

> ⛔ ≤ 60 分钟的任务**不需要** cron 心跳。foreground + MemOmics `_schedule_self_check` 足够。

## 心跳间隔选择

| 任务预计时长 | 心跳间隔 | 原因 |
|-------------|---------|------|
| < 1 h | **不部署 cron** | foreground + MemOmics 自检足够 |
| 1 h - 6 h | `schedule="15m"` | 每小时 4 次检查 |
| 6 h - 24 h | `schedule="30m"` | 每天 48 次检查 |
| > 24 h（过夜/多天） | `schedule="1h"` | 每天 24 次检查，省 token |

## 部署步骤

### Step 0: 确认路径

MemOmics 有两个关键目录：
- **会话路径** (`results_dir`): `results/{session_dir}/` — task_plan.md、PROGRESS.md、alerts.json 都在这里
- **分析目录** (`analysis_dir`): 用户指定的数据路径（如 `PROJECT_DATA_DIR`）— 实际数据产出在这里

> ⛔ **路径铁律**：PROGRESS.md、alerts.json **必须在会话路径下**，除非用户明确指定了分析目录。
> 这样所有会话文件在一个地方，便于归档和清理。

### Step 1: 确定预期产出文件

（不变）从 skill_view() 输出中提取预期产出文件列表。

### Step 2: 创建 cron job

```python
cronjob(
    action="create",
    name="监控-{任务名}",
    schedule="{interval}",     # 根据上表选择：15m / 30m / 1h
    prompt=HEARTBEAT_PROMPT,  # 从本 SKILL.md 的 Prompt 模板中复制
    skills=["heartbeat-monitor"],
    workdir="{results_dir}",  # ⚠️ 会话路径！不是 analysis_dir
    deliver="local",          # 只保存输出，不推送到聊天
    # 不设 repeat — 生信任务可能跑数天/一周，由心跳自检+Agent 主动关闭
)
```

> ⛔ workdir 必须设为 `{results_dir}`（会话路径），因为 task_plan.md 在这里。
> cron agent 需要通过 analysis_dir 变量知道去哪里扫描数据产出。

### Step 3: 更新 task_plan.md

```
| **Cron Job ID** | {job_id} |
| **Heartbeat Interval** | 15m |
| **Cron workdir** | {results_dir} |
| **Scan target** | {analysis_dir} |
```

---

## Cron Ticker 生命周期

### 何时启动？
**自动启动**。`start.bat` 启动 MemOmics 时，`@app.on_event("startup")` 自动启动 Hermes cron ticker（60s daemon thread）。
启动日志：`[MemOmics] Cron ticker started`

### 何时创建心跳 job？
**按需创建**。Agent 判断长任务（>30 min 或 estimated_minutes > 30）时，调用 `cronjob(action="create")`。
短任务不创建 cron job — 用 MemOmics 自带的 `_schedule_self_check` 足够。

### 何时停止单个 job？

**四层保险机制**（不设时间硬限，适应长达一周的生信任务）：

| 层 | 触发条件 | 执行者 | 说明 |
|----|---------|--------|------|
| 1️⃣ Agent 主动 | 任务完成，Agent 被唤醒 | `cronjob(action="remove")` | 正常路径 |
| 2️⃣ 心跳自检 | cron agent 读 task_plan.md → 所有 Phase `complete` | 写 `.heartbeat_stop` → MemOmics 唤醒 Agent | 最可靠 |
| 3️⃣ MemOmics 清理 | `_heartbeat_loop` 检测 `.heartbeat_stop` 或 completion alert | 唤醒 Agent remove | 30s 内 |
| 4️⃣ 无产出超时 | 连续 N 次心跳无新产出 + 进程已死 | 写 alerts.json (urgency=HIGH) → Agent 确认 | 防僵死 |

> ⛔ **不设 repeat 硬限制**。生信任务（CellBender、大规模聚类、scVI）可能跑数天甚至一周。
> 硬限会中途杀死心跳，导致长任务失去监控。

### 无产出超时计算（第 4 层）

```
连续无产出心跳数阈值 = max(6, 任务预计小时数)
示例：
  - 6h 任务 → 连续 6 次心跳无新文件 + 进程死 → 警告
  - 72h 任务 → 连续 72 次心跳无新文件 + 进程死 → 警告
  - 7天任务 → 连续 168 次无新文件 + 进程死 → 警告
```

> ⛔ 只有"无新产出 **且** 进程已死"才触发。单独无新产出不警告（CellBender 一个样本可能跑 2 小时）。
> ⛔ 触发后写 alerts.json (urgency=HIGH)，**不自动停止** — 等 Agent 确认后再决定。

---

## 心跳 Prompt 模板（HEARTBEAT_PROMPT）

每次心跳触发时，cron agent 收到以下 prompt。**必须包含具体的磁盘扫描命令**。

```
你是一个分析任务监控 Agent。你的唯一职责是检查分析进度并汇报。

## 路径约定
- **工作目录（当前）**: {workdir}  ← cron job 的 workdir，即会话路径
- **task_plan 路径**: {workdir}/task_plan.md
- **PROGRESS.md**: {workdir}/PROGRESS.md  ← 进度摘要写在这里
- **alerts.json**: {workdir}/alerts.json    ← 警报写在这里
- **数据产出目录**: {analysis_dir}          ← 扫描产出文件的地方

> ⛔ PROGRESS.md 和 alerts.json 必须写在 workdir（会话路径）下，不要写到别处。

## 任务信息
- **任务名称**: {task_name}
- **预期产出**: {expected_outputs}
- **预期文件数**: {expected_count}
- **最小文件大小**: {min_file_size}

## 每次心跳必做

### 1. 扫描磁盘产出（直接证据）
terminal("dir {analysis_dir}\{output_subdir} /s /b 2>nul")
或
search_files(pattern="*_filtered.h5", directory="{analysis_dir}")

→ 数文件数量 + 检查每个文件大小
→ 对比预期数量和最小大小
→ 记录新文件（对比上次 PROGRESS.md）

### 2. 检查进程存活
terminal("tasklist /FI \"IMAGENAME eq python.exe\" 2>nul | find /c \"cellbender\"")
或
terminal("tasklist /FI \"IMAGENAME eq Rscript.exe\" 2>nul")

→ 如果计数为 0 但产出未完成 → 进程可能崩溃

### 3. 扫描日志尾部
read_file("{analysis_dir}/pipeline.log", offset=-30)
或
terminal("findstr /i \"error traceback fail\" {analysis_dir}\\*.log 2>nul")

→ 检查 traceback / Error / FAIL / Killed

### 4. 三源交叉验证
磁盘产出数 + 进程状态 + 日志内容 → 三者一致 → 正常
任何不一致 → 写 alerts.json (urgency=HIGH)

### 5. 更新 PROGRESS.md
写入格式：
```
## {timestamp}
- 产出: {count}/{expected} 文件
- 最新文件: {newest_file} ({size})
- 进程: {alive/dead}
- 日志: {clean/error}
- 状态: {normal/error/complete}
```

### 6. 判定完成/异常 — 硬指标

**只有三个客观指标全部满足，才判定完成：**

```
✅ 指标1: 磁盘产出数 == 预期文件数
   terminal("dir {analysis_dir}\{output_subdir} /s /b 2>nul | find /c /v \"\"")
   → 返回的数字必须 >= {expected_count}

✅ 指标2: 每个文件大小 > 0
   terminal("for %f in ({analysis_dir}\{output_subdir}\*) do @echo %~zf")
   → 所有文件 size > 0，不能有空文件

✅ 指标3: 计算进程已正常退出
   terminal("tasklist /FI \"IMAGENAME eq python.exe\" | find /c \"cellbender\"")
   → 返回 0（进程已退出）
   → 同时检查退出码：read_file("{analysis_dir}/exit_code.txt") 或日志中 "completed successfully"
```

**三个都满足 → 任务完成 → 写 alerts.json (type=completion, urgency=HIGH)**
**进程退出但产出不足 → 进程崩溃 → 写 alerts.json (type=process_died, urgency=HIGH)**
**一小时后仍无变化 → 写 alerts.json (type=stalled, urgency=HIGH)**

> ⛔ 判定完成**不是**读 task_plan.md 的 Phase 状态（那是 Agent 写的，可能不准确）。
> ⛔ 判定完成**是**扫描磁盘 + 检查进程 + 检查文件大小。**硬证据，不靠标记。**

### 7. 判定完成后做什么

```
cron agent 判定完成 →
  1. write_file("{workdir}/.heartbeat_stop", "completed: {count}/{expected} files\n")
  2. write alerts.json (type=completion, urgency=HIGH)
  3. write PROGRESS.md 最后一条："任务完成。{count}/{expected} 文件产出，进程已退出。"
  4. 返回 "任务完成。心跳监控自动终止。"
```

MemOmics `_heartbeat_loop` 30s 内检测到 `.heartbeat_stop` →
  1. `session["_urgent_wakeup"] = True`
  2. 3 秒后 Agent 被唤醒
  3. Agent 读 PROGRESS.md + alerts.json → **现在 Agent 知道任务完成了**
  4. Agent 调用 `cronjob(action="remove")` → 心跳正式停止
  5. Agent 更新 task_plan.md → 生成报告 → 通知用户

## alerts.json 格式
写入 {analysis_dir}/alerts.json：
```json
[{
  "ts": "{ISO时间}",
  "type": "completion|error|process_died|progress",
  "urgency": "HIGH|LOW",
  "msg": "具体描述",
  "detail": {"completed": 5, "expected": 26, "latest_file": "sample_5_filtered.h5"},
  "handled": false
}]
```

## 关键约束
- ⛔ 不要尝试修复错误 — 你的职责是检测+汇报，不是修复
- ⛔ 不要启动新的分析任务 — 只监控当前任务
- ⛔ 每次最多 5 个 tool call — 保持轻量
- ⛔ 如果一切正常且无新产出 → 返回 "[SILENT]"（节省 token）
- ✅ 发现 HIGH urgency → 必须写 alerts.json → MemOmics 会自动唤醒主 Agent
```

---

## 产出文件检测映射表

| 分析类型 | Skill | 关键产出文件 | 检测命令 |
|---------|-------|-------------|---------|
| CellBender | cellbender-remove-background | `*_filtered.h5` (每个样本1个) | `dir /s /b *_filtered.h5` |
| QC | scrna-qc | `*_qc_report.html`, `*_filtered.h5ad` | `dir /s /b *_qc*` |
| 聚类 | scrna-clustering | `*_clustered.h5ad`, `*_umap.png` | `dir /s /b *_clustered* *_umap*` |
| DEG | deg-analysis | `*_deg.csv`, `*_volcano.png` | `dir /s /b *_deg* *_volcano*` |
| 轨迹 | trajectory-analysis | `*_trajectory.h5ad`, `*_pseudotime.png` | `dir /s /b *_trajectory*` |
| 通讯 | cellchat-v2 | `*_cellchat.rds`, `*_interaction_heatmap.png` | `dir /s /b *_cellchat*` |
| SCENIC | — | `*_regulons.csv`, `*_auc_mtx.csv` | `dir /s /b *_regulon* *_auc*` |
| 富集 | functional-enrichment | `*_enrichment.csv`, `*_gsea.png` | `dir /s /b *_enrich* *_gsea*` |

> **规则**：部署心跳前，Agent 必须从 skill 的 Expected Outputs 节中提取精确的文件名模式，
> 填入 HEARTBEAT_PROMPT 的 `{expected_outputs}` 占位符。不能凭记忆写。

---

## 参考

- Hermes cron 调度器：`cron/scheduler.py` — 60s tick，inactivity-based timeout (600s)
- MemOmics 唤醒链路：alerts.json HIGH → `_heartbeat_loop` 30s 检测 → `_urgent_wakeup` → 3s 唤醒
- SOUL-detail.md：长任务追踪规则 12-21
