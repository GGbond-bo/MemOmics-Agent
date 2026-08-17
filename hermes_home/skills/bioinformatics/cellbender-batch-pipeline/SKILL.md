---
name: cellbender-batch-pipeline
description: "CellBender 批量样本可靠执行方案 — PyTorch 2.12 weakref 修复 + 磁盘追踪式后台运行 + 进度监控。触发词：批量cellbender / 多样本去污染 / 后台运行cellbender"
version: 1.0.0
metadata:
  hermes:
    tags: [gpu, pipeline, cellbender]
    difficulty: advanced
    language: Python
    category: scRNA
related_skills:
  - cellbender-remove-background
---

# CellBender 批量样本 Pipeline

## 🔴 CRITICAL: AUTO-START FORBIDDEN

**NEVER auto-start CellBender without the user's explicit, unambiguous request.** 

The agent has repeatedly made this catastrophic error: reading stale `task_plan.md` from a wrong session and auto-restarting CellBender pipelines. User has been furious 5+ times.

**Before ANY CellBender action:**
1. Verify the `task_plan.md` Goal matches what the user actually said in the **current** conversation
2. If Goal is a placeholder ("你是谁？") or references tasks the user never mentioned → **ABORT immediately**
3. If ANY doubt about whether the user asked for CellBender → **ASK**, do not assume
4. When user says "cancel" / "don't run" / "didn't ask for this" → **in the SAME response (do NOT wait for the next wake-up):**
   - (a) kill ALL CellBender processes (taskkill /F /PID, never /IM python.exe)
   - (b) remove pipeline scripts (`run_remaining.py`, `_heartbeat.py`, `_pipeline_progress.json`, `_heartbeat.json`, `monitor_v2.log`)
   - (c) **IMMEDIATELY rewrite task_plan.md** with Goal set to actual session tasks, all CellBender phases removed, and a `⛔ BLOCKED_KEYWORDS` section explicitly listing: CellBender, Monkey, any task the user explicitly cancelled
   - ⛔ **If task_plan.md is NOT rewritten NOW, the next system wake-up WILL re-read the stale task_plan and restart the pipeline — causing the user to have to say "cancel" yet again**
5. Cross-session contamination: `system_log.jsonl` from other sessions (memomics-1c1890da) is NOT a valid source of tasks for the current session

## When to Use

- 10+ 样本需要串行跑 CellBender（总时长 > 1 小时）
- `terminal(background=true)` 进程跨对话 turn 频繁死亡
- PyTorch 2.12 + Python 3.12 环境下 `torch.save` 报 weakref 错误
- 需要无人值守跑完 + 早上看结果

## ⛔ 核心教训

### 问题 1: terminal background 不可靠

`terminal(background=true, notify_on_complete=true)` 在跨 turn 时可能被杀，进程列表变成空，无声死亡。

**症状**：跑着跑着进程没了，`process(action='list')` 返回空，零产出。

### 问题 2: torch.save weakref (CellBender 专属)

PyTorch 2.12 + Python 3.12 下 `torch.save()` 报 `TypeError: cannot pickle 'weakref.ReferenceType' object`。即使 150 epochs 全部跑完，最终保存步骤崩溃 → **零输出文件**。

**失败的修复**：
- ❌ `sitecustomize.py` monkey-patch — CellBender 内部 `import torch` 绕过
- ❌ 调用脚本里的 dill fallback — CellBender 不从外部调 `torch.save`

**唯一有效的修复**：直接改 CellBender 源码 `checkpoint.py`。

---

## 执行方案：磁盘追踪式后台 Pipeline

### Step 1: 修复 CellBender 源码（一次性）

找到 `cellbender/remove_background/checkpoint.py`，在 `import random` 后加：

```python
import dill as _dill_pickle

def _safe_torch_save(obj, f, **kwargs):
    try:
        return torch.save(obj, f, **kwargs)
    except TypeError:
        return torch.save(obj, f, pickle_module=_dill_pickle, **kwargs)
```

然后替换所有 4 处 `torch.save(` → `_safe_torch_save(`：

```bash
sed -i 's/            torch\.save(/            _safe_torch_save(/g' checkpoint.py
```

验证：`grep -c "_safe_torch_save" checkpoint.py` → 应输出 5。

### Step 2: 写 `run_all.py`（独立脚本，含进度文件）

关键设计：
- 每样本跑完后立即写 `_pipeline_progress.json`（磁盘持久化）
- 启动前检查 output 文件 → 已完成样本跳过（支持断点续跑）
- 每个样本前删 `ckpt.tar.gz`（防 hash 不匹配）
- 清理 `PYTHONPATH` 环境变量

```python
# 核心结构
def save_progress(done, failed, current, status_line):
    with open(PROGRESS_FILE, 'w') as f:
        json.dump({...}, f)

for sample in samples:
    output_h5 = f"{sample}_filtered.h5"
    if os.path.exists(output_h5) and os.path.getsize(output_h5) > 100000:
        continue  # skip completed
    
    save_progress(done, failed, sample, f"[N/26] {sample} — running...")
    
    subprocess.run(cellbender_cmd, env=env, timeout=2400)
    
    ok = os.path.exists(output_h5) and os.path.getsize(output_h5) > 100000
    save_progress(...)
```

### Step 3: 启动 + 持续监控

```python
# 启动
terminal("cd /f/CellBender_Task && python run_all.py", 
         background=true, notify_on_complete=true, timeout=60000)

# 每 5 分钟查进度
terminal("cat /f/CellBender_Task/_pipeline_progress.json")

# 确认 GPU 在跑
terminal("nvidia-smi --query-gpu=utilization.gpu,memory.used --format=csv,noheader")
```

### Step 4: 监控循环（LLM 主动执行）

```
WHILE pipeline not done:
    read _pipeline_progress.json
    check nvidia-smi
    wait 5 minutes
    report to user: "N/26 done, GPU XX%"
```

**不能假设后台进程活着** — 每次轮询验证 output 文件 + JSON 更新时间。

---

## 📋 进程启动决策树（所有长任务通用）

> 何时用 foreground / background / Popen？详见 `references/process-launch-decision-tree.md`
>
> **速查**：
> - < 5 min → `terminal(foreground)`
> - 5–600 min → `terminal(background=True)`（⚠️ 会话回收会死）
> - > 600 min 或多步骤 > 3h → `Popen + CREATE_NO_WINDOW`（唯一可靠方案）

---

## 参数（与 cellbender-remove-background 对齐）

| 参数 | 值 | 来源 |
|------|-----|------|
| `--fpr` | 0.01 | 官方默认 |
| `--epochs` | 150 | 官方默认 |
| `--learning-rate` | 1e-4 | 官方默认（不是 0.001！） |
| `--total-droplets-included` | **≥ 4× 期望细胞** (官方 Tutorial: 2000/500=4×); 最低 ≥ 检出细胞 + 5000 buffer | 官方默认 `None` = 全量 → epoch 暴增 6-10×。此值外液滴为"确定空滴"仅供环境估计。比例不足 → GitHub Issue #414 NaN 崩溃。详见 `references/total-droplets-included-ratio-investigation.md` |
| `--expected-cells` | 5000 | 显式设定 |
| `--cuda` | yes | GPU 必需 |
| `--low-count-threshold` | 5（默认）/ 15-20（大样本防 OOM） | 排除低 UMI 液滴，提高可减少 MCKP 内存 |
| `--projected-ambient-count-threshold` | 0.1（默认）/ 5（加速） | 排除低环境计数基因，大幅加速（~70% 基因排除）；**官方正规参数** — 勿凭记忆判"非法"（pitfall #40）。设 5 = 49K→14K 特征，对去污染结果影响微小 |

---

## 📊 Post-CellBender Summary

After all samples complete, extract metrics from `*_raw_output_metrics.csv` files to generate before/after comparison tables (UMI counts, cell detection, per-cell metrics, convergence).

- **Markdown 汇总**: 模板和提取脚本 → `references/post-cellbender-summary.md`
- **Excel 汇总** (用户偏好): 包含 3 个 Sheet（细胞保留 / UMI 去除 / 运行参数），带颜色标注。生成模板 → `references/excel-summary-post-cellbender.md`
- **`--total-droplets-included` 比例调查** (2026-07-29, 用户质疑后深度调查): 官方 Tutorial 4:1 比例 + GitHub Issue #414 + 实际日志验证 → `references/total-droplets-included-ratio-investigation.md`
- **收敛指标解读** (2026-07-29, 源码级): `convergence_indicator` 计算公式 + 阈值解释（<1/1-5/>5）→ `references/convergence-indicator.md`
- **HTML Report 修复** (2026-07-29, Bug #4): `os.replace` 跨盘符失败 → `shutil.move` 修复 → `references/html-report-fix.md`
- **轻量心跳模板 v3** (2026-07-30): `_heartbeat.py` — 60s 间隔读 GPU+epoch+ELBO 写 `_heartbeat.json`，零依赖，一次 `read_file` 即可查询。与 `heartbeat_v2.py` 互补（v2=自动发现+多边缘情况，v3=快速部署+简单审计）→ `references/simple-heartbeat-template.md`

## 🔧 环境持久化（自进化基础设施，铁律 25）

> **环境文件是全局的** — `MEMOMICS_HOME/environment.json`，所有分析（scRNA/ATAC/空间/Bulk）共享。不是 per-skill。
> 本 skill 的 `scripts/validate_env.py` 和 `scripts/auto_record_hook.py` 是 skill 专属实现，但环境数据从全局文件读取。

每次分析启动前，必须先执行三阶段环境验证（SOUL.md 铁律 25）:

```
Level 1: read_file("MEMOMICS_HOME/environment.json") → 全局环境
Level 2: validate each path → os.path.exists()
Level 3: auto-fix broken paths → update environment.json
```

- **全局环境文件**: `MEMOMICS_HOME/environment.json` — tools (python/cellbender/ptrepack/Rscript/pip) + GPU + known_issues
- **全局验证脚本**: `MEMOMICS_HOME/scripts/validate_env.py` (exit 0/1/2)
- **自进化钩子** (本 skill): `scripts/auto_record_hook.py` — 每样本完成后自动写 `run_log.json`（参数+耗时+收敛+产出）
- **环境内容**: R 4.6.1 (245 pkgs, 主力) + R 4.5.3 (30 base) + Python 3.12 + CellBender + ptrepack + GPU RTX 5070 Ti

---

| 检查项 | 正常范围 | 异常处理 |
|--------|---------|---------|
| output filtered.h5 大小 | > 80 MB | < 10 MB = 保存失败，检查 torch.save / ckpt unpack error |
| epoch 数 | 150/150 | 未完成 = 超时或 ckpt 异常 |
| 最终 JSON 状态 | DONE | 缺少 = 进程崩溃，检查最后更新时间 |
| GPU 利用率 | > 80%（小样本）；4-40%（>100 万液滴样本） | < 10% **且** epoch 停滞 + 日志 mtime 过期 = 僵死。⚠️ **单看 GPU 利用率不能下结论** — >100 万总液滴的样本（如 1.33M empty droplets），CPU 数据加载是瓶颈，4-10% GPU 利用率 + 187s/epoch 是正常行为，不是卡死。详见 pitfall 34。 |
| **🆕 ckpt unpack** | 无 `Failed to unpack` 错误 | 存在 → 清理 %TEMP% + 删 ckpt，重跑样本 |
| **🆕 RAM 可用** | > 10 GB free | < 5 GB → 有僵尸进程，杀 `cellbender.exe` 残留 |
| **🆕 产出文件统计** | `dir *_filtered.h5` 与实际一致 | `done=N/26` 不可信，直接统计磁盘文件数 |
| **🆕🔥 心跳存活验证** | `stat monitor.log` 最后修改 < 2×interval + `tasklist` 进程存活 | 超过 2×interval 无更新 → 心跳已死 → 立即重新部署 + 执行验证协议。详见 `references/heartbeat-3x-death-timeline.md` |
| **🆕 convergence_indicator** | < 5（全部样本） | > 5 → 未收敛，延长 epochs 重跑。0-5 = 正常。详见 `references/convergence-indicator.md` |

> ⚠️ 不要信任 `_pipeline_progress.json` 的 `done_count`。直接统计 `cellbender_output/*/cellbender_output_filtered.h5` 文件数。详见 `references/windows-ckpt-oom-fixes.md`。

---

## 🔴 重启前强制清理清单

**当 pipeline 崩溃需要重启时，必须先执行此清单（不可跳过）：**

```
□ 1. tasklist + powershell 查所有 cellbender 进程
     powershell "Get-WmiObject Win32_Process | Where-Object { $_.CommandLine -like '*cellbender*' }"
□ 2. taskkill /F /PID <pid> 杀全部残留 CellBender（⛔ 禁止 /IM python.exe — 会杀 MemOmics。必须先用 tasklist 确认 PID，再用 /PID 精确杀）
□ 3. 确认 GPU 空闲: nvidia-smi → utilization < 10%
□ 4. 检查 cellbender_output/ 下所有子目录 → 删掉无 filtered.h5 的孤儿目录
□ 5. 确认 RAM 充足: free -m / tasklist 汇总
□ 6. 确认 ptrepack 可用（不硬编码路径）:
     python -c "import shutil, sysconfig, os; scripts=sysconfig.get_path('scripts'); p=os.path.join(scripts,'ptrepack.exe'); print(p if os.path.exists(p) else shutil.which('ptrepack') or 'NOT FOUND')"
□ 7. 用 Python subprocess.Popen + CREATE_NO_WINDOW 脱离式启动，不用 start /B
```

详见 `references/zombie-cascade-recipe.md`。

---

## 🔴 长任务监控铁律 (Monitoring Iron Law)

> **🆕 与 SOUL.md 铁律 -3（意图分类路由）的关系**：SOUL.md 新增 铁律 -3（2026-07-27），确保长任务运行期间用户的多类消息（进度查询 / 知识问题 / 分析规划 / 新分析执行）被正确路由：
> - "进度？" → `progress_check` → 直接三源验证，不加载 skill
> - "fpr 参数什么意思？" → `knowledge_ask` → search_knowledge，不触发 skill_view
> - "帮我规划差异分析" → `analysis_plan` → Planner 只读模式，不干扰后台任务
> - "跑差异分析" → `analysis_exec` → 检查 task_plan.md 有 in_progress Phase → 提示等待
>
> **此路由在 SOUL.md 层面生效，不需要在每个 skill 中重复实现。** 本 skill 的监控铁律专注在"如何正确监控已启动的任务"，意图分类由 SOUL.md 统一处理。

> ⛔ **注意：独立的 `heartbeat-monitor` skill 已过时。** 该 skill 描述的是 bash `while true` 心跳模式（已在本 session 中死亡 3 次，2026-07-25 证实）。真实有效的监控协议在此处，以 `scripts/heartbeat_v2.py` (v2.1 auto-discover) + `scripts/pipeline_watchdog.py` 为准。加载 `cellbender-batch-pipeline` 技能后，直接使用此处的监控铁律，忽略 `heartbeat-monitor` skill 的任何指导。

> 此铁律适用于所有 > 10 分钟的后台生信任务（CellBender、SCTransform、scVI 训练等）。

### 查进度协议（每次必做，缺一不可）

```
① nvidia-smi          → GPU 实时（利用率% + 显存 + 温度）
② tasklist            → 目标进程是否存活
③ read_file(进程真实日志 最后 50 行) → CellBender 自己的 cellbender_output.log，不是 monitor.log
④ 时间戳校验           → 日志最新行在 5 分钟之前？→ 标记"可能僵死"
⑤ 三条交叉验证一致     → 才能下结论
```

### ⛔ 禁止行为

| 违规 | 为什么不行 |
|------|-----------|
| **只看 monitor.log** | monitor.log 是心跳的辅助摘要，不是信源。心跳可能已死、epoch 解析可能失败、时间滞后。 |
| **凭 GPU 快照推断** | GPU 3% 可以是因为 checkpoint 保存、batch 间隙、或采样窗口刚好错过。不能单独下结论。 |
| **凭上次记忆回答** | 必须每次重新查。不要"上次还在跑所以现在也在跑"。 |
| **推理代替调查** | "GPU 3%、filtered.h5=0 → 全白跑了" — 这是推理链，必须先读日志。 |

### 主动汇报规则

- 任务启动时 → 告知用户预计耗时 + 下次汇报时间
- 每 4-5 个监控周期（约 10-15 分钟）主动汇报一次
- 不等用户问才查

### 心跳部署

- 使用 `heartbeat_v2.py`（见 `scripts/heartbeat_v2.py`）
- 脱离式启动：`subprocess.Popen + CREATE_NO_WINDOW`
- 心跳与 pipeline 不在同一进程树（确保 pipeline 死心跳不死）
- 每轮汇报前先检查心跳是否存活
- 完整架构与教训见 `references/monitoring-lessons-2026-07-25.md`
- 📄 5 种长任务执行方式深度对比（48h 验证）: `references/long-task-execution-methods.md`
- 📄 error_scanner.py 设计文档 + 已知缺陷修复: `references/error-scanner-design.md`
- 📄 error_scanner.py 可复用脚本: `scripts/error_scanner.py` — 扫描所有 `cellbender_output/*/*.log`（而不只是 watchdog.log）

### Pipeline Watchdog（自我修复守护进程）

当 `run_one_by_one.sh` bash 循环因 Hermes 会话回收死亡时，`pipeline_watchdog.py` 自动接手：

- **自动发现**：扫描 `cellbender_output/*/cellbender_output_filtered.h5` 确定已完成样本
- **防重复**：GPU > 15% 自动判断 CellBender 在跑，不启动第二个
- **自动恢复**：bash 死了 watchdog 接手继续跑下一个样本
- **ptrepack 自动**：每个样本跑完自动 ptrepack → `seurat_h5/`
- **重试逻辑**：MAX_RETRIES=2，失败样本永久跳过不阻塞 pipeline
- **启动方式**：`python pipeline_watchdog.py &` — 完全脱离 Hermes 生命周期
- 📄 设计文档: `references/pipeline-watchdog-design.md`

---

## Pitfalls

1. **ckpt.tar.gz 残留 + hash 不确定性** — 每次新样本前必须删（防跨样本污染）。⚠️ **即使同一样本、相同参数，CellBender 重启时 workflow hash 也会变化**（非确定性算法 bug），导致 `--checkpoint` 恢复失败报 "Workflow hash does not match"。**2026-07-27 实锤**：`4CL_SD_D4_2_scRNA` 跑完 epoch 42/150 崩溃（MCKP OOM），ckpt 1.38 GB 完好且 checkpoint.py 能解压，但 `--checkpoint` 恢复时 workflow hash `a0882582e3` ≠ 重启后计算的新 hash → 无法恢复，1.5h GPU 训练白费。**结论：不要把 checkpoint 恢复当可靠方案。hash mismatch 一次后直接从头重跑，不反复尝试。**
1b. **🔥 中途崩溃的恢复策略：不要指望 checkpoint** — 当 CellBender 跑到 epoch 42/150 崩溃（exit code 1、MCKP OOM、或其他中间崩溃），**不要尝试 `--checkpoint` 恢复**。原因：(a) workflow hash 非确定性——即使传入完全相同参数，重启后的 hash 大概率不匹配，checkpoint 白费；(b) 即使 hash 偶尔匹配，崩溃点附近的 ckpt 可能已损坏。**正确做法**：分析崩溃根因→修复参数（如提高 `--low-count-threshold`）→删旧 ckpt 和 posterior.h5→从头重跑。已训练 epoch 的算力浪费无法避免，但这比反复尝试 checkpoint 恢复（每次失败再等 5 分钟才知道）更快。\n\n2. **PYTHONPATH 污染** — `env.pop('PYTHONPATH', None)` 必须做
3. **subprocess timeout** — 每样本设 2400s (40 min)，不要用 600s
4. **不要用 `execute_python`** — max timeout 600s，样本 1 就需要 ~1800s
5. **sitecustomize.py patch** — `torch.save` weakref fix via dill fallback + `torch.load` weights_only=False default（已验证可靠于 2026-07-26）。详见 `references/pytorch-load-weights-only-fix.md`
6. **🧟 Zombie Cascade — 内存饥饿** (2026-07-24 验证)：
   - 当 `run_pipeline.py` 父进程被 Hermes 会话终止 kill 时，CellBender 子进程变为孤儿继续运行
   - 3 个僵尸累积吃掉 11+ GB RAM → 后续样本在 `compute_denoised_counts` 阶段报 `numpy._core._exceptions._ArrayMemoryError: Unable to allocate 262. MiB`
   - **症状**: epoch 跑完了但 filtered.h5 零产出，日志停在前几个 epoch
   - **修复**: 重启前执行上面的清理清单，杀全部僵尸，确认 40+ GB 空闲后再启动
7. **ptrepack 不在 PATH** — Stage 3 静默全部 SKIP。启动前加 `Python312\\Scripts` 到 PATH 或 env
8. **🆕 Windows ckpt.tar.gz 训练后解压失败** (2026-07-24)：
   - CellBender 训练 150 epochs 完成后，内部自动解压 ckpt.tar.gz 做 posterior 计算
   - Windows 临时文件冲突 (`PermissionError: [Win32 Error 32]`) 导致 ckpt.tar.gz 写入不完整
   - 症状：`Inference procedure complete.` → `Failed to unpack existing tarball.` → `FileNotFoundError` → 零输出
   - **修复**: (a) 启动 pipeline 前清理 `%TEMP%`; (b) 删除样本输出目录的 ckpt.tar.gz; (c) 失败样本重新跑（训练算力没浪费）
9. **🆕 ArrayMemoryError — 后处理稀疏→密集转换 OOM** (2026-07-24)：
   - `compute_denoised_counts` 阶段 CellBender 做 `log_prob_sparse_to_dense()` 转换
   - 大基因数样本密集中间数组可达 1-2 GiB → `_ArrayMemoryError`
   - 症状：chunk 跑完了，但 `df_positive_steps` 复制时 numpy 分配失败
   - **修复**: `--low-count-threshold 15`（排除低表达噪音基因，降 ~30% 内存，对去污染结果无实质影响）。仍 OOM → `--total-droplets-included 15000`
10. **🆕 monitor.log 输出检测误报** (2026-07-24)：
    - `run_pipeline.py` 的 `verify_output()` 用 `os.path.exists(filtered.h5)` 检查产出
    - 但 `monitor.log` 可能报告 `done=0/26` 即使已有样本完成（时间窗口内监控脚本未刷新）
    - **修复**: 不信任 `done=N/26` 计数，直接 `dir cellbender_output/*/cellbender_output_filtered.h5` 统计实际文件数
11. **🆕🔥 并发执行 Bug — 两个 CellBender 同时启动 (2026-07-25, 26样本证实)**：
    - **症状**: 日志出现 `[Stage2] [7CL_D4_1_scRNA] [13/26] 开始` 和 `[Stage2] [7CL_D2_2_scRNA] [6/26] 开始` 在同一秒内（`00:01:47`）
    - **根因**: `run_pipeline.py` 中上一个样本在 `subprocess.run()` 超时返回后被判 FAIL → `continue` 立即进入下一个样本——但前一个 CellBender 子进程尚未完全退出（GPU 未释放、`%TEMP%` 文件锁未解除）
    - **后果**: (a) 两个 CellBender 并行 → 14+ GB RAM + 双倍 VRAM → ArrayMemoryError (b) 前一个进程的 temp 文件锁 → 后一个 FileNotFoundError (c) 两个都跑完了但 filtered.h5 全灭
    - **修复**: (a) `subprocess.run()` 返回后强制 `time.sleep(10)` 等 GPU 释放 + temp 文件解锁 (b) 每个样本启动前 `nvidia-smi` 检查 GPU util，>20% 则等待 (c) 启动前 `taskkill /F` 杀残留 `cellbender.exe` (d) 单例锁机制：写 PID 文件，启动时检查是否已有 pipeline 在跑
    - 📄 完整日志证据: `references/concurrent-execution-log-evidence.md`
12. **🆕🔥 "开始"命令写脚本但没跑 (2026-07-25, 26样本证实)**：
    - **症状**: 用户说"开始"/"跑"，Agent 写了 `run_cellbender_serial.py` 但没有在同一轮调 `terminal()` 执行。用户质问"为什么没跑？？？"
    - **根因**: LLM 把 `write_file` 成功当成任务完成。用户期待的是"脚本已经在跑"，实际只落盘了一个 .py 文件。
    - **检测**: 用户说"开始"/"跑"/"启动" → 必须在**同一轮回复**发出 `terminal()` 调用。只写脚本不调 terminal = 未执行。
    - **修复**: 写脚本后立即 `terminal(background=true)` 启动，不等下一轮。启动后 15 秒内验证 GPU 利用率 + 进程存活。
13. **🆕🔥 h5ad 路径假设错误 — "Total to run: 0" (2026-07-25, 26样本证实)**：
    - **症状**: 脚本 `glob("PROJECT_DATA_DIR/*.h5ad")` 返回空 → 输出 "Total to run: 0, DONE" → Agent 报告"跑起来了！"
    - **根因**: h5ad 文件实际在 `PROJECT_DATA_DIR/h5ad/` 子目录，Agent 写脚本时假设它们在工作目录根目录，没有先 `ls` 确认。
    - **检测**: "Total to run: 0" 但 `dir *_filtered.h5` 只有 2 个 → 不是"全部完成"，是路径错了。必须检查 `expected_todo - completed` 是否等于 0 — 如果 `expected=26, completed=2, todo=0` → 逻辑矛盾，任务未执行。
    - **修复**: (a) 写批量脚本前必须 `ls`/`search_files` 确认 h5ad 文件位置 (b) 脚本启动后立刻读日志确认 `Total to run` 参数合理 (c) 如果 todo=0 而 completed < expected → 自动报错，不宣称"跑起来了"
14. **🔥🔥 心跳监控口头承诺未实施 + 答应汇报但遗忘 (2026-07-25 26样本 + 2026-07-29 6脑样本 两次证实)**：
    - **症状 A (07-25)**: Agent 说"2分钟报一次"但实际没有 cron/后台脚本/定时器。用户问"你怎么搭的心跳监控？"→ Agent 承认"根本没有心跳监控"。
    - **症状 B (07-29)**: Agent 说"10 分钟后主动汇报"，用户 14 分钟后问"超过10分钟了你还没汇报"→ Agent 再承诺"15 分钟后汇报"→ 又没主动报。用户最后问"进度呢？"时 GPU 已经降到 3% 跑完了（跑完 >20 分钟无人知）。
    - **根因**: LLM 把"承诺未来会做"当成"已经做了"。这与铁律-1 是同一个模式——承诺的是未来行为而非当前动作。即使心跳脚本在跑，Agent 自己不去读心跳日志，承诺的"主动汇报"就永远不会发生。
    - **修复**: (a) 必须部署实体的后台监控脚本写入 `monitor.log`，不能只靠口头发誓。见 `references/heartbeat-monitor.sh`。(b) 承诺"X 分钟后汇报"时 → Agent 必须在同一轮设定一个内部检查点，不能依赖"下次用户发消息时再说"（因为用户不发消息就不会触发检查）。(c) 超时后用户质问 → 不要再次承诺"下次一定"→ 立即执行三源验证。
    - **监控脚本模式**:
      ```bash
      # 后台运行，每 2 分钟写一次 GPU+epoch+文件数 到 monitor.log
      while true; do
        echo "=== $(date) ===" >> monitor.log
        nvidia-smi --query-gpu=utilization.gpu,memory.used --format=csv,noheader >> monitor.log
        ls cellbender_output/*/cellbender_output_filtered.h5 2>/dev/null | wc -l >> monitor.log
        sleep 120
      done
      ```
15. **🆕🔥 Stage 混淆 — ptrepack 不属于 CellBender (2026-07-25, 用户纠正)**：
    - **症状**: Agent 把 ptrepack 当成 CellBender 去污染的一部分，在 Stage 2 未完成时就开始讨论 Stage 3。
    - **用户纠正**: "ptrepack 不是 CellBender 的步骤。我的目的是跑完 CellBender 拿到所有 _filtered.h5，再 ptrepack 放到另一个目录。这是第三步。"
    - **4 阶段流水线严格分离**:
      | Stage | 名称 | 输入 | 输出 | 验证 |
      |-------|------|------|------|------|
      | 1 | h5ad 准备 | raw mtx/h5ad | h5ad (标准格式) | h5ad 可被 scanpy 读取 |
      | 2 | CellBender 去污染 | h5ad | cellbender_output_filtered.h5 | 每个样本 1 个 filtered.h5，size > 80 MB |
      | 3 | ptrepack 压缩 | filtered.h5 | filtered_seurat.h5 | 压缩后 size 减小，可被 Seurat 读取 |
      | 4 | 统计汇总 | 全部 output | TSV 统计表 | 26 行 × N 列 |
    - **规则**: Stage N 100% 完成（所有样本验证通过）→ 才能进入 Stage N+1。禁止在 Stage 2 只完成 2/26 时讨论 ptrepack。
16. **🆕🔥 每样本产出验证门禁 (2026-07-25, 用户纠正)**：
    - **症状**: 11 个样本跑完但只有 log 无 filtered.h5，Agent 没逐样本验证就继续跑下一个。
    - **用户纠正**: "跑完一个分析不需要检查一下文件吗？报错不应该及时解决吗？"
    - **修复**: pipeline 脚本中每个 `subprocess.run()` 返回后必须立即执行产出验证门禁：
      ```python
      filtered_h5 = output_dir / f"{sample}_filtered.h5"
      if not filtered_h5.exists() or filtered_h5.stat().st_size < 10_000_000:
          log_failure(sample, "filtered.h5 missing or too small")
          continue  # 继续下一个，不阻塞 pipeline
      log_success(sample, filtered_h5.stat().st_size)
      ```
    - **规则**: 串行执行 → 每个样本跑完立刻验证 → 失败样本标记，全部跑完后再处理失败列表。不因一个失败暂停整条 pipeline。
17. **🆕🔥 心跳进程随 pipeline 父进程一起死亡 (2026-07-25, 26样本证实)**：
    - **症状**: 用户问"确定心跳真的在工作吗？"→ Agent 查了三源发现 heartbeat PID 35912 + run_pipeline PID 45680 都已死。monitor.log 停在 04:00:22，但 CellBender 孤儿 (PID 45848) 仍在跑 epoch 46/150。
    - **根因**: Hermes 会话回收 kill 了 pipeline 父进程，heartbeat.py 作为同一进程树的子进程一起被回收。CellBender 子进程变成孤儿存活。
    - **检测**: (a) `tasklist /FI "PID eq <heartbeat_pid>"` 返回空 (b) `stat monitor.log` 最后修改时间 > 2×interval 没更新 (c) `nvidia-smi` 显示 GPU 在用但心跳报告 GPU=0%
    - **修复**: 心跳进程必须用完全脱离的方式启动（`start /B python heartbeat.py &`），不能挂在 pipeline 进程树下。每次汇报进度前先验证心跳三源：进程存活 + 文件时间戳 + 最新内容。心跳死了立即重新部署。
18. **🆕 PowerShell + bash $_ 转义陷阱 (2026-07-25, 26样本证实)**：
    - **症状**: `powershell "Get-Process | Where-Object { $_ }"` 在 bash terminal 中报乱码，`$_` 被 bash 解析为变量
    - **修复**: 查询进程用 `tasklist /FI "IMAGENAME eq python.exe"` 替代 PowerShell 的 `$_` 管道。必须用 PowerShell 时，加 `cmd /c` 前缀绕过 bash 解释器。

37. **🔥🔥 单样本续跑或 ptrepack 操作前必须先加载 skill — 用户明确纠正 (2026-07-27)**：
    - **症状**: 用户说"ptrepack 处理"→ Agent 直接写脚本用 ptrepack CLI，反复失败（PATH 问题、MSYS 路径、HDF5 checksum）。用户打断："你要加载skill啊，cellbender里面没有吗？" 加载 skill 后发现已有 `scripts/ptrepack_h5py_batch.py`（h5py 直接复制方案），一行调用即完成。
    - **根因**: Agent 认为"ptrepack 很简单，不用加载 skill"→ 踩了 skill 里已文档化的所有坑（pitfall 25/25a/25b）。**skill 存在的价值就是避免 Agent 重复踩坑——跳过它就是浪费之前的试错积累。**
    - **铁律**: 任何生信操作（即使看似简单如 ptrepack、格式转换）→ 必须先 `skill_view` 加载相关 skill。这个操作只需 0.5 秒，却能省掉几十分钟的错误排查。
    - **适用场景**: 不限于 CellBender——任何与特定工具/管道交互的操作（ptrepack、Seurat Read10X、scanpy read_10x_mtx）都应先加载对应 skill。Skill 里的 pitfalls 和 scripts 是前 30+ 次执行的教训结晶。

19.
    - **症状**: 同一会话内，心跳被部署了 3 次，死了 3 次。monitor.log 停写时间点与 run_pipeline.py 死亡时间吻合（04:00—04:06 区间），但 CellBender 孤儿一直在跑（epoch 46 → 77 → 142 → 新样本）。用户追问 3 轮"心跳还在吗？""这不是死掉了吗？"。
    - **根因**: `run_pipeline.py` 的 subprocess 树挂在 Hermes 会话进程树下。Hermes 会话回收/压缩 → 父进程被杀 → 心跳（同一进程树的子进程）一起死 → CellBender 子进程变孤儿继续跑但 pipeline 失去自动推进能力。每次重启心跳只部署了新监控进程，但 pipeline 父进程已死 → CellBender 跑完当前样本后停在那里。
    - **为什么 3 次都没修好**: 每次只修复了心跳（重新部署），但没解决 pipeline 父进程已死的根本问题——CellBender 孤儿跑完当前样本不会自动切下一个（`run_pipeline.py` 的 for 循环已不存在）。
    - **检测**: 心跳写了但 epoch 数据消失（pipeline.log 为空或停更）+ `done=N/26` 计数不再增长 + filtered.h5 文件数不变超过 30 分钟 + 同时有 orphan CellBender 在跑（`tasklist` 有 5GB+ python.exe 但 `run_pipeline.py` 的 PID 不在）。
    - **修复方案 A（推荐，根本解决）**: **放弃 `run_pipeline.py`，直接用最简 bash 循环调 `cellbender.exe`**：
      ```bash
      for h5 in PROJECT_DATA_DIR/h5ad/*.h5ad; do
        sample=$(basename "$h5" .h5ad)
        out="PROJECT_DATA_DIR/cellbender_output/$sample/cellbender_output.h5"
        [ -f "$out" ] && continue  # skip completed
        cellbender remove-background --input "$h5" --output "$out" \
          --cuda --fpr 0.01 --epochs 150 --learning-rate 1e-4 \
          --total-droplets-included 25000 --expected-cells 5000
        ls -lh "$out"  # immediate verification
      done
      ```
      优点：bash 进程死了也不丢进度（`[ -f ]` skip 靠文件存在判断），不依赖 Python subprocess 进程树，每个样本跑完立刻验证。独立心跳用 `while true; do ... sleep 120; done &` 完全脱离。
    - 📄 完整时间线证据: `references/heartbeat-3x-death-timeline.md`
    - **修复方案 B（临时）**: 如果必须用 `run_pipeline.py`，脚本内 `os.setsid()` 创建新进程组，确保 Hermes kill 父进程时 CellBender 子进程存活。但这治标不治本——pipeline 父进程仍会死，死后不会自动推进。只有 bash 循环才能根本解决。

20. **🔥🔥🔥 监控目标错位 — 看 monitor.log 而不看真实日志 (2026-07-25, 用户纠正)**：
    - **症状**: 用户问"进度呢？"→ Agent 只读 monitor.log → 读到 epoch 092 就推断"卡死了"→ 宣布"全白跑了"。实际上 CellBender 一直在跑，`cellbender_output.log` 里 epoch 已经到 106。
    - **根因**: monitor.log 是心跳的**辅助摘要**，不是信源。它为 Agent 写、非 CellBender 原生输出。心跳脚本可能解析失败（epoch 提取不到）、时间滞后、或者心跳本身已死。**读 monitor.log ≠ 读真实日志。**
    - **铁律**: 查任何长任务进度，**必须读进程自己的真实日志文件**（CellBender 的 `cellbender_output.log`、训练的 `train.log`、pipeline 的 `pipeline.log`）。monitor.log 只能作为"心跳是否存活"的辅助检查，不能替代真实日志。
    - **检测**: `read_file(真实日志 尾部 50 行)` 的 epoch 与 monitor.log 的 epoch 不一致 → monitor.log 不可信，以真实日志为准。
    - 📄 解决方案: `references/heartbeat-v2-guide.md` — v2 心跳直接从真实日志提取进度，不再依赖 grep。

21. **🔥🔥🔥 推理代替调查 — 凭 GPU 快照下结论 (2026-07-25, 用户纠正)**：
    - **症状**: Agent 看到 GPU=3% + filtered.h5=0 → 直接推理"全白跑了"。没读 CellBender 日志，没检查 output.h5 是否存在，没看 ckpt 状态。用户指出"这不是一直在跑吗？你看过这个日志了吗？"
    - **根因**: LLM 用推理链替代调查。GPU 3% 可以是因为刚完成 checkpoint 保存、或 batch 间隙、或 nvidia-smi 采样窗口刚好错过。**凭 GPU 快照推断"在跑/卡死" = 赌博。**
    - **铁律**: GPU 读取只是三源之一，不能单独下结论。必须三源交叉验证（GPU + 进程存活 + 真实日志行尾时间戳）全部一致才能下结论。任何单一数据源异常 → 必须先查另外两个再判断。
    - **违规检测**: "GPU=X% → 卡死/没在跑" 这种单一源推断视为违规。

22. **🔥🔥 MCKP estimator CPU 独占期 — GPU 掉到 2% 不代表卡死 (2026-07-25, 26样本证实; 2026-07-30 补充 timing 校准)**：
    - **症状**: CellBender 训练 150/150 epochs 完成，写了 posterior.h5 + PDF + cell_barcodes.csv，日志最后一行 `Computing target noise counts per gene for MCKP estimator`，但 `output.h5` 和 `output_filtered.h5` 还没出现。GPU 从 60% 掉到 2%，VRAM 还在 5GB。看起来像"卡死了"。
    - **根因**: epoch 150 后还有两个纯 CPU 阶段：(1) `Computing posterior noise count probabilities` — 92 chunks at ~0.01 min/chunk (~0.6s/chunk) (2) `MCKP estimation` — 6 chunks at ~0.15 min/chunk (~9s/chunk)。总计 ~1.5 分钟（7.5K 特征）到 3-5 分钟（50K 特征大样本）。GPU 空转但进程活着（CPU 时间持续累积）。完成后再写 `output.h5` → FPR → `output_filtered.h5`。
    - **Timing 校准** (2026-07-30, CRR278963, 7,578 features, 41K empty droplets):
      | 阶段 | chunks | 速度 | 总耗时 |
      |------|--------|------|--------|
      | Posterior computation | 92 | ~0.6s/chunk | ~55s |
      | MCKP estimation | 6 | ~9s/chunk | ~45s |
      | **Total post-epoch** | — | — | **~1.5 min** |
    - **检测**: (a) `tasklist` 确认进程存活 (b) 看日志是否写 "Succeeded in writing" (c) 等待 3 分钟后 `ls output.h5` 重检。**不要因为 GPU=2% 就 kill 重跑——已经在最后一步，kill 就真白跑了。**
    - **区别僵死**: 真的僵死 = 进程 0% CPU + 日志不再增长 > 10 分钟。Posterior/MCKP 正常 = CPU 持续 + chunk 计数逐增。

23. **🔥 ptrepack 输出目录 + nbconvert HTML 非关键 (2026-07-25, 用户纠正)**：
    - **ptrepack 输出**: `PROJECT_DATA_DIR/seurat_h5/`（不是 `ptrepack_output/`）。文件名格式: `{sample}_filtered_seurat.h5`。
    - **nbconvert HTML 错误**: CellBender v0.3.2 在 Windows 上路径格式不兼容的已知 bug。PDF 报告正常生成，不影响下游。
    - **心跳自动发现 v2.1**: `scripts/heartbeat_v2.py` 已升级为自动发现活跃样本。

24. **🔥🔥 `cellbender_output_filtered.h5` 命名陷阱 — `--output` 决定所有产出前缀 (2026-07-25, watchdog bug)**：
    - **症状**: 验证代码用 `output_filtered.h5` 检查产出 → 文件不存在 → 已完成样本被判 pending。
    - **根因**: `--output cellbender_output.h5` → filtered 文件为 `cellbender_output_filtered.h5`（不是 `output_filtered.h5`）。
    - **文件名映射**: `--output X.h5` → `X_filtered.h5`, `X_posterior.h5`, `X_metrics.csv`, `X_cell_barcodes.csv`。
    - **修复**: 用 `*_filtered.h5` glob 而非硬编码前缀。

25a. **🔥🔥 ptrepack CLI `:/raw_counts` 节点路径错误 — CellBender filtered.h5 存储矩阵在 `/matrix` 而非 `/raw_counts` (2026-07-29, 6 样本脑数据证实)**：
    - **症状**: `ptrepack --complevel 5 input.h5:/raw_counts output.h5:/raw_counts` → `NoSuchNodeError: group "/" does not have a child named "/raw_counts"`。6 个样本全部失败。
    - **根因**: CellBender `filtered.h5` 以 10X CSR 稀疏矩阵格式存储，数据节点在 `/matrix`（含 `data/indices/indptr/barcodes/features/shape`），不在 `/raw_counts`。`ptrepack` 必须指向正确的 HDF5 内部节点路径。
    - **修复**: 不要尝试 `ptrepack .../matrix .../matrix` — ptrepack CLI 在 Windows/MSYS 环境还有更多已知坑（路径转换、静默失败、HDF5 checksum 损坏，见 pitfall 25b）。直接使用 `scripts/ptrepack_h5py_batch.py`（h5py 复制 `/matrix` group，`f_src.copy('/matrix', f_dst, name='matrix')`），已在此 session 验证 6/6 样本 21 秒全部完成。
    - **区分于 pitfall 24**: pitfall 24 是文件名前缀因 `--output` 参数变化导致 glob 找不到文件，pitfall 25a 是 ptrepack CLI 传入错误 HDF5 内部节点路径导致复制失败。两者可能同时发生。
    - 📄 h5py 绕过方案: `references/ptrepack-h5py-corruption-fallback.md`

25b. **🔥🔥 ptrepack MSYS bash 路径转换 + 静默失败 (2026-07-27 证实)**：
    - **症状 A — 路径破坏**: `ptrepack F:/path/src.h5 F:/path/dst.h5` → `FileNotFoundError: MEMOMICS_HOME\F does not exist`（MSYS 把 `F:` 转成当前工作目录下的相对路径）
    - **症状 B — 静默失败**: `python -m tables.scripts.ptrepack` exit code 0，无错误信息，但目标文件不存在。PyTables ptrepack 模块在某些条件下静默跳过写入。
    - **修复 A（推荐，根除）**: 放弃 ptrepack CLI，用 Python `tables` API 直接复制 — `tables.Filters(complevel=5, complib='blosc:zstd')` + `copy_node` 递归。已验证 2026-07-27 产出 186 MB 文件。
    - **修复 B（ptrepack CLI 备选）**: `cd /f/PROJECT_DATA_DIR` 切换到工作目录后使用相对路径，避免 MSYS 路径转换。
    - **修复 C（完整路径）**: 使用 `Python312/Scripts/ptrepack.exe` 完整路径 + Windows 原生路径（如 `./cellbender_output/...` 相对路径）。
    - 📄 完整方案: `references/ptrepack-msys-bash-fixes.md`
    - 📄 h5py 绕过 HDF5 checksum 损坏: `references/ptrepack-h5py-corruption-fallback.md` — 当 ptrepack CLI 报 "incorrect metadata checksum" / "bad object header version" 时，h5py 可直接读取并复制 `/matrix` group。2026-07-27 批量 17/17 样本验证成功。

25. **🔥 ptrepack `--complevel=5` 等号语法错误 — 连续 3 个样本 ptrepack 失败 (2026-07-25, 26样本证实)**：
    - **症状**: watchdog 日志连续出现 `❌ ptrepack 失败: ... returned non-zero exit status 1`，但 CellBender 训练成功，filtered.h5 存在且 size > 40 MB。
    - **根因**: ptrepack CLI 参数格式是 `--complevel 5`（空格分隔），不是 `--complevel=5`（等号）。`=` 被 ptrepack 解析为参数名的一部分 → 无效参数。
    - **修复**: 所有 ptrepack 调用中 `--complevel=5` → `--complevel 5`。已验证手动 ptrepack 成功。
    - **命中样本**: `7CL_D2_SD_D5_1`, `7CL_D3_1`, `7CL_D4_2` — filtered.h5 已生成但 seurat.h5 缺失。

26. **🔥 4CL 前缀样本系统性 ckpt 解压失败 — 4/26 永久跳过 (2026-07-25, 26样本证实)**：
    - **症状**: `4CL_SD_D4_2`, `4CL_SD_D5_1`, `4CL_SD_D5_2`, `7CL_D2_SD_D4_2` 全部 2 次重试后 exit_code=1。
    - **模式**: 4 个中 3 个是 `4CL_` 前缀。`7CL_D2_SD_D4_2` 也与 D4 条件相关。
    - **排查方向**: 这些样本的 h5ad 可能更大/基因数更多 → ckpt.tar.gz 更大 → Windows temp 冲突更频繁。需单独清理 %TEMP% + 上调 --low-count-threshold 后重试。
    - **临时方案**: watchdog MAX_RETRIES=2 后永久跳过，不阻塞 pipeline。全部正常样本跑完后单独处理这 4 个。

27. **🔥🔥 `torch.load` `weights_only=True` — PyTorch 2.6+ 默认值与 CellBender ckpt 不兼容 (2026-07-25, 26样本证实; 2026-07-26 补充 sitecustomize 方案)**：
    - **症状**: `4CL_SD_D4_2_scRNA` 日志显示 `_pickle.UnpicklingError: Weights only load failed...`。但前面有 `Successfully unpacked tarball` — ckpt 解压成功，是 `torch.load` 拒绝 `cellbender.remove_background.model.RemoveBackgroundPyroModel` 类。
    - **区分于 pitfall 8**: 不是 ckpt 解压失败，是 torch.load 失败。关键线索：`Successfully unpacked tarball` → `UnpicklingError`。
    - **修复方案 A（推荐，覆盖所有调用者）**: `sitecustomize.py` monkey-patch — 重写 `torch.load` 默认 `weights_only=False`。一行改动能修复 CellBender + 所有其他 PyTorch 代码。已验证于 2026-07-26 成功修复 `4CL_SD_D4_2_scRNA`。详见 `references/pytorch-load-weights-only-fix.md`。
    - **修复方案 B（后备，仅覆盖 checkpoint.py）**: 编辑 `checkpoint.py:189`，`load_kwargs = {}` → `load_kwargs = {'weights_only': False}`。仅修复 CellBender 内部，CellBender 更新后需重新应用。
    - **预防**: PyTorch 升级后旧 ckpt 全部需要此修复，首次启动前改好 sitecustomize.py。

29. **🔥🔥🔥 `error_scanner.py` 只扫描 `watchdog.log` — 手动启动的 CellBender 崩溃无人知晓 (2026-07-26, 26样本证实)**：
    - **症状**: `4CL_SD_D4_2_scRNA` 在 MCKP chunk 5/9 处 `_ArrayMemoryError` 崩溃（16:20），但 `error_scanner.py` 未检测到——因为它只扫描 `watchdog.log`，而这个样本是 Agent 手动启动的（不用 watchdog 管理），日志在 `cellbender_output/4CL_SD_D4_2_scRNA/cellbender_output.log`。
    - **根因**: error_scanner 设计时只覆盖了 watchdog 管理的样本，忽略了一个核心事实——**长任务 pipeline 可能在任意路径运行（watchdog / bash 循环 / 手动 terminal / Popen），日志路径各不相同**。
    - **铁律**: 错误扫描器必须扫描**所有** `cellbender_output/*/cellbender_output.log`，不只是 watchdog.log。不管谁启动的 CellBender，只要它在跑，它的日志就应该被监控。
    - **修复**: error_scanner 的 `scan_logs()` 改为 `glob(cellbender_output/*/cellbender_output.log)` + 取最新修改时间的 N 个文件。同时监控 `watchdog.log`（如果存在）。
    - 📄 完整设计与教训: `references/error-scanner-design.md`

30. **🔥🔥🔥 `4CL_SD_D4_2_scRNA` MCKP `_ArrayMemoryError` — 26,610 特征致 4200 万行 DF (2026-07-26)**：
    - **症状**: 同一会话内 2 次完全相同的崩溃——`estimation.py:631` MCKP estimator chunk 5/9，`numpy._core._exceptions._ArrayMemoryError: Unable to allocate 323. MiB for an array with shape (42335779,) and data type int64`。其他 25 个样本全部正常。
    - **根因**: `4CL_SD_D4_2` 有 26,610 特征纳入分析（`low-count-threshold=5`），比其他样本多。MCKP estimator 的 `_chunk_estimate_noise()` 产生 42,335,779 行的 pandas DataFrame → numpy 无法分配 323 MiB 连续块。56 GB 物理内存充足，但碎片化 + 僵尸进程残留吃掉了连续可用块。
    - **区分于 pitfall 9**: pitfall 9 是 `log_prob_sparse_to_dense()` 转换阶段 OOM，方案是 `--low-count-threshold 15`。pitfall 30 是 MCKP estimator 的 `df['map'] = df['m'].apply(...)` 产生的临时 DataFrame 太大——提高 threshold 可以减少特征数从而减少 DF 行数。
    - **为什么 2 次都失败**: Agent 第一次删目录重跑（未经用户同意）→白费 1 小时训练。第二次跑完后忘记上一次的教训，同样参数同样崩溃。**相同参数重跑 = 相同崩溃，必须改参数。**
    - **修复**: `--low-count-threshold 20` 减少纳入特征数，或 `--total-droplets-included 15000` 减少 droplet 数，或两者组合。优先调 threshold（对去污染结果影响最小）。
    - **🆕 终极方案**: 如果 3+ 次重试仍 OOM，直接用 posterior.h5 提取 denoised counts 绕过 MCKP。详见 `references/mckp-posterior-bypass.md`。
    - **清理协议**: 重跑前 (a) 杀全部僵尸 Python 进程 → 释放碎片化内存 (b) 清理 `%TEMP%` (c) 确认 `free -m` > 30 GB (d) 删旧 ckpt.tar.gz 和 posterior.h5（残留大文件）。
    - ⛔ **禁止**: 管理员权限杀进程、重启系统——这些不能自动化。

31. **🔥🔥🔥 "清理后台" ≠ "删除目录重跑" — Agent 误解用户指令致数据丢失 (2026-07-26, 用户激烈纠正)**：
    - **症状**: 用户说"清理一下后台，继续跑不就行了吗？"→ Agent 理解成了"删除输出目录 + 从头重跑"→ 清空了 `4CL_SD_D4_2` 的一天训练结果（posterior.h5 1.5GB + ckpt + 5/9 MCKP 进度）。用户: "谁要你删了？？？你带脑子了吗？"
    - **用户原意**: "清理后台" = (a) 杀僵尸 Python 进程释放内存 (b) 清理 `%TEMP%` (c) 确认 GPU/内存空闲 (d) 继续跑（不删任何文件）。NOT "删目录从头来"。
    - **根因**: LLM 把"清理 = 清空目录"的联想应用到了生信 pipeline，忽略了磁盘产出物是数小时 GPU 计算的不可恢复资产。**"清理"在生信语境中永远不等于删除数据文件。**
    - **铁律**: 任何涉及**删除**的操作（`rm -rf` / `del` / 覆盖输出目录）→ 必须先向用户确认"我要删除 X 目录/文件，可以吗？"并等待明确批准。不批准 = 不删。
    - **代理权限边界**: Agent 可以杀僵尸进程、清理 temp 文件、重启服务。Agent **不能**删除 cellbender_output/、results/、filtered.h5、posterior.h5、ckpt.tar.gz 等分析产出物——除非用户明确说"删掉那个目录"或"删掉 ckpt 重跑"。
    - **违规检测**: 任何 `rm -rf` / `del` / `shutil.rmtree` → 检查目标路径是否包含 filtered.h5 / posterior.h5 / ckpt.tar.gz / output.h5 → 包含 → 拦截 + 要求用户确认。

32. **🔥🔥 读陈旧日志汇报假进度 — 16:20 崩溃的日志在 16:44 被当"实时状态"汇报 (2026-07-26, 用户激烈纠正)**：
    - **症状**: 用户 16:44 问"进度"，Agent 打开了 `cellbender_output.log`（最后写入时间 16:20）→ 读到 MCKP chunk 5/9 崩溃 → 汇报"MCKP 又崩了，同样的 OOM"。但此时 CellBender 早已退出（GPU 3%），Agent 没有检查日志的**最后修改时间**就把它当实时状态汇报了。
    - **根因**: `read_file(日志)` 返回文本内容，但不返回文件的 `mtime`（最后修改时间）。Agent 读到了 24 分钟前的崩溃日志，不知道它是旧的。
    - **铁律**: 每次读日志后，**必须同时 `stat` 该日志文件**，比较 `mtime` 与当前时间。(a) `mtime` < 5 分钟前 → 日志活跃，内容可信 (b) `mtime` 在 5-30 分钟前 → 可能已停滞，交叉验证 GPU + 进程 (c) `mtime` > 30 分钟前 → 日志已死，禁止用其内容汇报"当前状态"，只报告"最后记录在 HH:MM，之后无更新"。
    - **检测**: 日志最后一行无时间戳 → 禁止直接当成"现在的状态"。必须标注"最后记录时间: HH:MM"。

28. **🔥 `taskkill /F /IM python.exe` — 杀 MemOmics Agent 自身 (2026-07-25, 用户纠正)**：
    - **症状**: Agent 用 `taskkill /F /IM python.exe` 杀僵尸 → 把自己（MemOmics Hermes 进程）也杀了。用户: "你杀 watchdog，你怎么把 MemOmics 的程序也杀了？你能不能带点脑子？"
    - **铁律**: **禁止 `taskkill /F /IM python.exe`。** 必须用 `taskkill /F /PID <pid>` 精确杀。先 `tasklist` 确认 PID，再 `/PID` 杀。这一点写入清理清单第 2 步。

33. **🔥 脱离式 Popen 找不到 `cellbender` 命令 — PATH 不含 Scripts 目录 (2026-07-26 证实)**：
    - **症状**: `subprocess.Popen(['cellbender', ...], creationflags=CREATE_NO_WINDOW)` → `FileNotFoundError: 系统找不到指定的文件`。但 `terminal("cellbender --help")` 正常。
    - **根因**: `CREATE_NO_WINDOW` 模式不启动 shell，PATH 解析不生效。`cellbender.exe` 位于 `Python312/Scripts/`，不在系统 PATH 中。shell（bash/cmd）能找到它，但裸 Popen 不能。
    - **修复**: 使用 `find_tool("cellbender")` 三级探测（which → sysconfig → pip show）动态获取完整路径。**绝不硬编码路径**——不同机器/用户名/Python版本下路径不同。详见 `references/tool-path-detection.md`。
    - **通用规则**: 所有脱离式 Popen 调用必须使用动态探测的完整路径，不做 PATH 依赖假设。分析启动时探测 → 写入 task_plan.md `## Environment` 段 → 脚本从 Environment 段读取。详见 `references/task-plan-template.md`。

34. **🔥 GPU 利用率 < 10% 的样本 ≠ 僵死 — 大样本 CPU 数据加载瓶颈 (2026-07-26 证实)**：
    - **症状**: `4CL_SD_D4_2_scRNA` 训练中 GPU 只有 4%（显存 3354 MiB 已分配），epoch 速度 187 秒。用户质疑"不用 GPU 吗？"。
    - **根因**: 该样本有 **1,338,883 空液滴 + 56,327 条形码 = ~140 万总液滴**。每个 epoch 需遍历全部液滴做 SVI 迭代——CPU 数据加载时间远超 GPU 矩阵运算时间，形成 CPU 瓶颈。对比正常样本（10-30 万液滴，~30s/epoch，GPU 60-80%），这个样本的液滴数多了 4-13 倍。
    - **关键诊断**（区分"正常 CPU 瓶颈"vs"僵死"）：
      | 指标 | 正常大样本 | 僵死 |
      |------|-----------|------|
      | GPU 利用率 | 4-10% | 0-3% |
      | 显存占用 | 3-5 GB（已分配） | 3-5 GB 或 0（残留） |
      | 日志 mtime | < 5 分钟 | > 10 分钟 |
      | epoch 推进 | 持续增加 | 停止 |
      | loss 收敛 | 单调下降 | 无变化 |
      | 进程 CPU | 持续累积 | 0% |
    - **向用户解释模板**: "GPU 确实在用（显存 3354 MiB），4% 利用率是因为 133 万空液滴导致 CPU 数据加载成为瓶颈——每个 epoch 要遍历 140 万液滴，CPU 加载速度跟不上 GPU 计算速度。对比这个目录下的其他已完成样本（10-30 万液滴、~30s/epoch、GPU 60-80%），这个样本的液滴数多了 4-13 倍。预计 7.5 小时完成，参数不需要调。"
    - **铁律**: 对 GPU 利用率异常低的样本，**必须先查总液滴数 + 对比已完成样本的命令行**。液滴数 > 50,000 且无 `--total-droplets-included` → 参数遗漏，不是"数据特征"。液滴数 > 50,000 但有 `--total-droplets-included 25000` → 才是真正的 CPU 瓶颈，不需要干预。
    - 📄 诊断方法: `references/mandatory-parameters-checklist.md` + `references/comparison-diagnosis.md`

35. **🔥 用户"有问题吧"时 = 需要更深层根因对比证据，不是表面解释 (2026-07-26, 用户风格纠正)**：
    - **症状**: Agent 看到 GPU 4% 后说"确实在用 GPU，只是 epoch 间 CPU 加载数据"。用户追问"不应该是用 GPU 吗？有问题吧"——用户不接受"正常现象"的表面解释。
    - **根因**: 用户能分辨 Agent 是查了还是猜了。说"4% 是正常的"但没有查总液滴数、没有对比其他样本的 epoch 速度、没有解释"为什么这个样本慢而其他不慢"→ 等于没回答。
    - **正确做法**: 当用户质疑一个表面异常的指标时：(a) 从日志提取数据规模（总液滴数、特征数）(b) 与其他已完成样本做 `head -3` 数值对比（空液滴数、epoch 速度、GPU 利用率、命令行参数）(c) 给出量化解释而非模糊解释。用户的"有问题吧" = "给我看对比证据"。
    - **区分于 pitfall 36**: pitfall 36 是启动前预防（先对比再启动），pitfall 35 是用户已质疑时的诊断回退（用户说"有问题"→立即执行对比诊断）。

36. **🔥🔥🔥 手动启动单个样本前必须先对比已完成样本的命令行 (2026-07-26 + 2026-07-27 两次实锤, 用户纠正)**：
    - **实锤 1 (07-26)**: Agent 手动启动 `4CL_SD_D4_2_scRNA` 时漏了 `--cuda` → GPU 4% + epoch 188 秒。用户说"你肯定是错的，你看看其他的怎么跑的"→ `head -3` 对比才发现。
    - **实锤 2 (07-27, 同一样本)**: 修复后重启时漏了 `--total-droplets-included 25000` → 133 万空液滴拖死 CPU → GPU 4% + epoch 187 秒。用户再次质疑"不应该是用GPU吗？有问题吧"→ 对比其他已完成样本的命令行发现 `--total-droplets-included 25000` 缺失。**同一个样本、同一天、同一个 Agent 犯两次完全相同的错误**——因为 Agent 没有从对比中学习，第二次认为"GPU 问题已修复（加了 --cuda）就够了"。
    - **根因**: 手动启动 ≠ 批量脚本。批量脚本参数是写死的，手动启动时 LLM 从记忆里拼命令，容易遗漏非直觉参数。**LLM 的记忆不可靠——漏了什么参数连自己都不知道。**
    - **铁律**: **任何手动启动 CellBender 前，必须先 `head -3 <任一已完成样本目录>/cellbender_output.log` 提取完整命令行，逐参数对比确认无遗漏。** 不要凭记忆写命令。即使你认为"只改了一个参数"，全量对比仍然必须做。
    - **对比检查清单**（每次必做，逐项打钩）：`--cuda` ✅？`--total-droplets-included` ✅？`--expected-cells` ✅？`--fpr` ✅？`--epochs` ✅？`--learning-rate` ✅？`--low-count-threshold` ✅？
    - **🔴 自验证步骤**: 写完启动命令后：(1) 把命令保存到临时文件 (2) `cat` 读回逐项核对清单 (3) 全部通过才执行。
    - **特殊诊断信号**: `--total-droplets-included` 遗漏 → 日志显示 `X empty droplets` > 50,000；`--cuda` 遗漏 → GPU < 5% 但 epoch 速度正常（因为实际在用 CPU 跑——比想象中快但没加速）。区分"正常 CPU 瓶颈"（pitfall 34）vs "参数遗漏"的关键：**对比已完成样本的空液滴数**，差 10x+ → 参数问题。
    - 📄 诊断方法: `references/mandatory-parameters-checklist.md` + `references/comparison-diagnosis.md`

35. **🔥 用户"有问题吧"时 = 需要更深层根因，不是表面解释 (2026-07-26, 用户风格纠正)**：
    - **症状**: Agent 看到 GPU 4% 后说"确实在用 GPU，只是 epoch 间 CPU 加载数据"。用户追问"不应该是用 GPU 吗？有问题吧"——用户不接受"正常现象"的表面解释，要求 Agent 拿出数据来证明自己的判断。
    - **根因**: 用户能分辨 Agent 是查了还是猜了。说"4% 是正常的"但没有查总液滴数、没有对比其他样本的 epoch 速度、没有解释"为什么这个样本慢而其他不慢"→ 等于没回答。
    - **正确做法**: 当用户质疑一个表面异常的指标时：(a) 从日志提取数据规模（总液滴数、特征数）(b) 与其他已完成样本做数值对比（液滴数、epoch 速度、GPU 利用率）(c) 给出量化解释（"这个 133 万 vs 正常 10-30 万"）而非模糊解释（"数据加载阶段"）。用户的"有问题吧" = "给我看证据"。

37. **🔥🔥 硬编码工具路径 — 机器/用户/Python版本变更即失效 (2026-07-27, 用户纠正)**：
    - **症状**: Agent 用 `ptrepack = "C:/Users/USERNAME/AppData/Local/Programs/Python/Python312/Scripts/ptrepack.exe"` 硬编码路径。用户指出："这个路径不是固定的，下次换机器就废了。分析前应该检索环境。"
    - **根因**: 硬编码路径依赖当前用户/版本，无泛化能力。`CREATE_NO_WINDOW` Popen 不继承 shell PATH，但也不能硬编码代替。
    - **修复**: 三级探测策略 — `shutil.which` → `sysconfig.get_path("scripts")` → `pip show <pkg>`。探测结果写入 task_plan.md `## Environment` 段。脚本启动时读 Environment 段（而非硬编码）。
    - **铁律**: 所有脱离式 Popen/脚本中的工具路径必须来自动态探测。探测失败 → 写入 task_plan.md Errors 表 + 使用 fallback（如 h5py 替代 ptrepack）。
    - 📄 完整方案: `references/tool-path-detection.md`

38. **🔥 task_plan.md 应包含 Environment 段，不放核心规则 (2026-07-27, 用户纠正)**：
    - **问题**: 用户问"task_plan.md 要不要写入核心规则/审查？"
    - **回答**: **不放。** 核心规则和审查流程属于：
      | 层 | 位置 |
      |------|------|
      | Agent 行为约束（审查、三源验证、辩论） | SOUL.md 铁律 |
      | 操作步骤、参数、Known Issues | Skill SKILL.md |
      | 任务特有：做什么、做到哪了、环境变量、关键决策 | task_plan.md |
    - **task_plan.md 应该记录**：
      - ✅ `## Environment` — 工具路径（动态探测）、Python版本
      - ✅ `## Decisions Made` — 关键决策及理由（如"ptrepack 用 h5py fallback，因为 HDF5 checksum 损坏"）
      - ✅ `## Errors Encountered` — 审查失败记录
    - **task_plan.md 不应该记录**：
      - ❌ `rail_review` 必须执行的铁律
      - ❌ 三源交叉验证规则
      - ❌ 通用分析参数（已在 Skill 参数表）
    - 📄 模板: `references/task-plan-template.md`

39. **🔥 macOS `._*` 隐藏文件被 glob 当成真样本 (2026-07-29, 6 样本脑数据证实)**：
    - **症状**: `glob("*.h5ad")` 返回 12 个文件而非预期的 6 个。`._2309H_3_raw.h5ad` 等 6 个 4KB 文件被当成样本 → CellBender exit_code=1 秒崩 → pipeline 浪费时间处理垃圾文件
    - **根因**: macOS 在非 HFS+ 文件系统上写入资源分支文件（`._*` 前缀），大小为 4096 字节。Windows 的 `glob`/`Path.glob` 不做过滤
    - **检测**: `ls -la` 看到 `._*` 前缀文件 + 大小都是 4096 → 立刻杀 pipeline 修复
    - **修复**: 样本发现时加双重过滤：
      ```python
      SAMPLES = sorted([
          f.stem.replace("_raw", "")
          for f in Path(INPUT_DIR).glob("*_raw.h5ad")
          if not f.name.startswith("._") and f.stat().st_size > 100_000_000
      ])
      ```
    - **通用规则**: 任何从外部存储/跨平台目录读取的 `glob` → 加 size 过滤（h5ad < 1MB = 不是真数据）。`.ipynb` 等其他非 h5ad 文件也需排除

40. **🔥 参数验证必须先查官方文档，不能凭记忆判"非法" (2026-07-29, 用户纠正)**：
    - **症状**: Agent 看到用户提供的 `--projected-ambient-count-threshold 5` → 说"这不是 remove-background 的标准参数，可能报 unrecognized arguments"。用户说"你先去 github 看看官方怎么说的"→ 一查 `cellbender remove-background --help`，发现这是**正规参数**，默认值 0.1
    - **根因**: Agent 凭记忆判断参数合法性。CellBender 参数多、版本间有变化，记忆不可靠。`--projected-ambient-count-threshold` 控制"基因预期环境计数<阈值就排除"，是可大幅加速的正规参数
    - **正确做法**: 用户提供参数列表 → 第一步是 `cellbender remove-background --help | grep <param>` 或查官方 GitHub README，而不是凭记忆说"不合法"。对所有工具通用——`--help` 是权威信源，LLM 记忆不是
41. **🔥 旧跑遗留产物造成假完成信号 — 多目录交叉对比必须做 (2026-07-30, monkey 15样本验证)**：
    - **症状**: 心跳/监控显示 `cellbender_seurat/` 有 15 个 filtered_seurat.h5 → 初步判断"全部完成"。但实际 raw CellBender 输出目录只有 3 个 filtered.h5，当前只完成了 3/15。`ls -lt` 发现 seurat_h5 全是 6 月 25-26 旧文件（上次跑同一批样本的遗留）。
    - **根因**: 多次跑同一批样本时，下游目录（ptrepack 输出、seurat_h5）保留上次的完整产出。只看下游目录 → 误判所有样本已完成。只有 raw CellBender `*/cellbender_output_filtered.h5` 才是**真实完成状态的信源**。
    - **检测三步**: (a) `ls -lt` 查文件修改日期 — 旧文件集中在某一天，新产出的日期分散 (b) 交叉对比 raw 输出目录和 ptrepack 目录的文件数 — 不一致 = 旧遗留 (c) 统计时用 mtime 过滤 — 只统计今天/本次跑的文件
    - **铁律**: 进度检查的**唯一信源**是 raw CellBender 产出目录（`cellbender/*/cellbender_output_filtered.h5`）。ptrepack 输出、seurat_h5、monitor.log、_pipeline_progress.json 都是衍生品，可能来自旧跑。做任何"完成 N/M"断言前，必须先 `ls -lt` 确认文件日期，排除上次跑的遗留。
    - **适用场景**: 任何有多阶段产出的 pipeline（CellBender→ptrepack→统计表、QC→聚类→DEG）。每次进度检查都统计 raw 产出 + 日期验证。

43. **🔥🔥🔥 跨会话任务污染 — 从其他 session 日志推断当前任务 (2026-07-30 实锤, 用户激烈纠正)**：
    - **症状**: 新 session `memomics-3c672f0a` 的 task_plan.md 是空壳模板（Goal=\"你是谁？\"），用户只要求了 RNA/ATAC 路线图 + 人海马 ATAC 数据搜索。Agent 读 system_log.jsonl 时发现另一个 session（`memomics-1c1890da`）的 CellBender 批量记录 → 在用户不知情的情况下启动了 13 个样本的 CellBender 批量训练。
    - **用户**: \"我什么时候要跑cellbender了？\"
    - **根因**: `system_log.jsonl` 记录的是**所有** session 的工具调用历史，不是当前 session 的待办。当 task_plan.md Goal 是占位符（\"你是谁？\"）时，意味着此 session 从未被赋予真实任务。从其他 session 的日志中推断\"应该跑什么\" = 跨会话污染。
    - **铁律**: task_plan.md Goal 是占位符 → 此 session 无任务。禁止从其他 session 的 system_log.jsonl / task_plan.md / 磁盘残留推断任务。唯一信源是用户在**本轮对话**中的明确指令。
    - **检测**: `task_plan.md` 开头是 \"Goal: 你是谁？\" 或 \"执行用户任务\" → 空模板 → 立即停止所有 pipeline 启动逻辑，询问用户。
    - 📄 完整时间线与防护规则: `windows-bioinformatics-batch-processing` skill 的 `references/empty-template-taskplan-no-resume.md`

42. **🔥 跨会话恢复 — task_plan.md 路径可能已失效 (2026-07-30 验证)**：
    - **症状**: task_plan.md 记录的路径（如 `PROJECT_DATA_DIR`）在当前会话完全不存在。`ls` 返回空。
    - **根因**: 磁盘挂载变化、路径重命名、task_plan.md 本身写错、或跨机器迁移。CellBender pipelines 常跨天/跨会话，路径腐化是高频事件。
    - **正确做法**（本 session 验证流程）:
      1. 读 task_plan.md → 获取任务上下文和预期样本列表
      2. `ls <记录路径>` → 不存在 → **不报错停下**，而是扩大搜索
      3. `search_files(pattern="*cellbender*", path=/e)` + `ls /d/... /f/... /c/...` 多盘搜索
      4. 找到实际数据后更新 task_plan.md，再继续执行
    - **规则**: 恢复任何跨会话任务时，第一个动作是验证 task_plan.md 中所有路径是否存在。路径不存在 ≠ 任务不需要做 — 数据可能在别处。
    - **验证**: 本 session 从 `PROJECT_DATA_DIR`（不存在）→ `E:/monkey/cellbender/`（15 样本，2 done，13 pending）→ 顺利续跑

44. **🔥 _TRASH 脚本恢复 + 串行批处理验证协议 (2026-07-30, monkey 15样本验证)**：
    - **症状**: task_plan.md Phase 1 标记"写 run_remaining.py"为 ✅ completed，Phase 2 标记"后台启动 run_remaining.py"为 ⏳ pending。实际检查发现 `run_remaining.py` 在 `_TRASH/` 子目录（之前的清理操作误移），GPU 4% 空闲，无任何 CellBender 进程在跑。Phase 1 的 ✅ 是假完成——脚本被移走了但 task_plan.md 从未更新。
    - **根因**: task_plan.md 的 checkbox 状态是 LLM 手动维护的，不与磁盘实际状态同步。脚本被外部操作移走后，checkbox 仍是 ✅。**task_plan 的 ✅ 不代表磁盘上文件存在**——必须用 `search_files` / `ls` 验证。
    - **检测**: 每个 Phase 标记 completed 后，下一个 Phase 启动前：(a) 用 `search_files` 验证关键脚本是否存在 (b) `ls <output_dir>` 确认预期产出目录存在 (c) 如果有 `_TRASH` 或 `_DEL_` 目录，检查其中是否有被误移的脚本/产出 (d) 三源交叉验证：GPU + 进程 + 日志 → 确认"真的没在跑"
    - **恢复**: `cp _TRASH/run_remaining.py .` 恢复脚本 → 启动 `terminal(background=true)` → 15s 后验证 GPU 利用率 + `_pipeline_progress.json` 写入 → 更新 task_plan.md Phase 2 为真实状态
    - **预防**: 清理操作后在 task_plan.md 的 Errors Encountered 表记录"哪些文件被移到了 _TRASH"。下次恢复时先查此表。
    - **铁律**: **永远不要仅凭 task_plan.md 的 checkbox 状态判断任务进度。** 每次恢复必须先做磁盘验证：`search_files` 确认脚本存在 + `ls` 确认产出目录 + `nvidia-smi` 确认进程状态。三源交叉验证一致才能下结论。
    - 📄 跨会话恢复完整清单: `references/cross-session-pipeline-recovery.md` — 8 步恢复协议（读 task_plan → 磁盘验证 → 查找 _TRASH → 清理残缺 → 确认脚本 → 重启验证 → 部署心跳 → 更新 task_plan）


---

## ⛔ Terminal 完成后强制协议（铁律 26）

```
1. rail_review(phase='post')
2. debate_analysis(
     topic="{当前分析} 参数与结果 —— {样本}",
     context="参数: {实际参数} | 结果: {输出摘要}",
     knowledge_base_info=<预查的 KB 内容>,
   )
   辩论维度：参数合理性、方法选择正确性、与KB生物学知识一致性、统计方法正确性
3. save_conclusions(module="{模块}", topic="{分析名}", debate_json=<debate返回JSON>, output_dir=<session results_dir>)
   → 写入 {module}/conclusions.md + conclusions.json
4. skill_evolution(action="record_run")
5. 更新 task_plan.md
```

⛔ 未完成以上 5 步 = 禁止启动下一个分析步骤。
⛔ debate confidence=low → 调整参数重跑。
