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
| `--total-droplets-included` | 25000 | 官方默认 |
| `--expected-cells` | 5000 | 显式设定 |
| `--cuda` | yes | GPU 必需 |

---

## Quality Check

| 检查项 | 正常范围 | 异常处理 |
|--------|---------|---------|
| output filtered.h5 大小 | > 80 MB | < 10 MB = 保存失败，检查 torch.save / ckpt unpack error |
| epoch 数 | 150/150 | 未完成 = 超时或 ckpt 异常 |
| 最终 JSON 状态 | DONE | 缺少 = 进程崩溃，检查最后更新时间 |
| GPU 利用率 | > 80% | < 10% = 可能卡在 CPU / 进程僵死 |
| **🆕 ckpt unpack** | 无 `Failed to unpack` 错误 | 存在 → 清理 %TEMP% + 删 ckpt，重跑样本 |
| **🆕 RAM 可用** | > 10 GB free | < 5 GB → 有僵尸进程，杀 `cellbender.exe` 残留 |
| **🆕 产出文件统计** | `dir *_filtered.h5` 与实际一致 | `done=N/26` 不可信，直接统计磁盘文件数 |
| **🆕🔥 心跳存活验证** | `stat monitor.log` 最后修改 < 2×interval + `tasklist` 进程存活 | 超过 2×interval 无更新 → 心跳已死 → 立即重新部署 + 执行验证协议。详见 `references/heartbeat-3x-death-timeline.md` |

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
□ 6. 确认 ptrepack 在 PATH（不然 Stage 3 静默跳过）:
     python -c "import shutil; print(shutil.which('ptrepack'))"
□ 7. 用 Python subprocess.Popen + CREATE_NO_WINDOW 脱离式启动，不用 start /B
```

详见 `references/zombie-cascade-recipe.md`。

---

## 🔴 长任务监控铁律 (Monitoring Iron Law)

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

1. **ckpt.tar.gz 残留** — 每次新样本前必须删，否则 hash mismatch
2. **PYTHONPATH 污染** — `env.pop('PYTHONPATH', None)` 必须做
3. **subprocess timeout** — 每样本设 2400s (40 min)，不要用 600s
4. **不要用 `execute_python`** — max timeout 600s，样本 1 就需要 ~1800s
5. **sitecustomize.py 不靠谱** — 直接改 checkpoint.py 是唯一可靠路径
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
    - **症状**: 脚本 `glob("F:/CellBender_v2/*.h5ad")` 返回空 → 输出 "Total to run: 0, DONE" → Agent 报告"跑起来了！"
    - **根因**: h5ad 文件实际在 `F:/CellBender_v2/h5ad/` 子目录，Agent 写脚本时假设它们在工作目录根目录，没有先 `ls` 确认。
    - **检测**: "Total to run: 0" 但 `dir *_filtered.h5` 只有 2 个 → 不是"全部完成"，是路径错了。必须检查 `expected_todo - completed` 是否等于 0 — 如果 `expected=26, completed=2, todo=0` → 逻辑矛盾，任务未执行。
    - **修复**: (a) 写批量脚本前必须 `ls`/`search_files` 确认 h5ad 文件位置 (b) 脚本启动后立刻读日志确认 `Total to run` 参数合理 (c) 如果 todo=0 而 completed < expected → 自动报错，不宣称"跑起来了"
14. **🆕🔥 心跳监控口头承诺未实施 (2026-07-25, 26样本证实)**：
    - **症状**: Agent 说"2分钟报一次"但实际没有 cron/后台脚本/定时器。用户问"你怎么搭的心跳监控？"→ Agent 承认"根本没有心跳监控"。
    - **根因**: LLM 把"承诺未来会做"当成"已经做了"。这与铁律-1 是同一个模式但更难检测——承诺的是未来行为而非当前动作。
    - **修复**: 必须部署实体的后台监控脚本写入 `monitor.log`，不能只靠口头发誓。见 `references/heartbeat-monitor.sh`。
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

19. **🔥🔥 心跳+管道 3 连死 — `run_pipeline.py` 系统性不可靠 (2026-07-25, 同一会话内 3 次复现)**：
    - **症状**: 同一会话内，心跳被部署了 3 次，死了 3 次。monitor.log 停写时间点与 run_pipeline.py 死亡时间吻合（04:00—04:06 区间），但 CellBender 孤儿一直在跑（epoch 46 → 77 → 142 → 新样本）。用户追问 3 轮"心跳还在吗？""这不是死掉了吗？"。
    - **根因**: `run_pipeline.py` 的 subprocess 树挂在 Hermes 会话进程树下。Hermes 会话回收/压缩 → 父进程被杀 → 心跳（同一进程树的子进程）一起死 → CellBender 子进程变孤儿继续跑但 pipeline 失去自动推进能力。每次重启心跳只部署了新监控进程，但 pipeline 父进程已死 → CellBender 跑完当前样本后停在那里。
    - **为什么 3 次都没修好**: 每次只修复了心跳（重新部署），但没解决 pipeline 父进程已死的根本问题——CellBender 孤儿跑完当前样本不会自动切下一个（`run_pipeline.py` 的 for 循环已不存在）。
    - **检测**: 心跳写了但 epoch 数据消失（pipeline.log 为空或停更）+ `done=N/26` 计数不再增长 + filtered.h5 文件数不变超过 30 分钟 + 同时有 orphan CellBender 在跑（`tasklist` 有 5GB+ python.exe 但 `run_pipeline.py` 的 PID 不在）。
    - **修复方案 A（推荐，根本解决）**: **放弃 `run_pipeline.py`，直接用最简 bash 循环调 `cellbender.exe`**：
      ```bash
      for h5 in F:/CellBender_v2/h5ad/*.h5ad; do
        sample=$(basename "$h5" .h5ad)
        out="F:/CellBender_v2/cellbender_output/$sample/cellbender_output.h5"
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

22. **🔥🔥 MCKP estimator CPU 独占期 — GPU 掉到 2% 不代表卡死 (2026-07-25, 26样本证实)**：
    - **症状**: CellBender 训练 150/150 epochs 完成，写了 posterior.h5 + PDF + cell_barcodes.csv，日志最后一行 `Computing target noise counts per gene for MCKP estimator`，但 `output.h5` 和 `output_filtered.h5` 还没出现。GPU 从 60% 掉到 2%，VRAM 还在 5GB。看起来像"卡死了"。
    - **根因**: MCKP estimator 是纯 CPU 计算（每基因算噪声计数），GPU 空转但进程活着（16GB 内存，CPU 时间持续累加）。这一步完成后才会写 `output.h5` → 应用 FPR → 生成 `output_filtered.h5`。大样本（5 万基因）MCKP 可在 3-5 分钟内完成。
    - **检测**: (a) `tasklist` 确认进程存活 (b) `stat ckpt.tar.gz` 检查修改时间 (c) 等待 5 分钟后 `ls output.h5` 重检。**不要因为 GPU=2% 就 kill 重跑——已经在最后一步，kill 就真白跑了。**
    - **区别僵死**: 真的僵死 = 进程 0% CPU + 日志不再增长 > 10 分钟。MCKP 正常 = CPU 持续 + 日志可能在 MCKP 段无输出（单行无换行）。

23. **🔥 ptrepack 输出目录 + nbconvert HTML 非关键 (2026-07-25, 用户纠正)**：
    - **ptrepack 输出**: `F:/CellBender_v2/seurat_h5/`（不是 `ptrepack_output/`）。文件名格式: `{sample}_filtered_seurat.h5`。
    - **nbconvert HTML 错误**: CellBender v0.3.2 在 Windows 上路径格式不兼容的已知 bug。PDF 报告正常生成，不影响下游。
    - **心跳自动发现 v2.1**: `scripts/heartbeat_v2.py` 已升级为自动发现活跃样本。

24. **🔥🔥 `cellbender_output_filtered.h5` 命名陷阱 — `--output` 决定所有产出前缀 (2026-07-25, watchdog bug)**：
    - **症状**: 验证代码用 `output_filtered.h5` 检查产出 → 文件不存在 → 已完成样本被判 pending。
    - **根因**: `--output cellbender_output.h5` → filtered 文件为 `cellbender_output_filtered.h5`（不是 `output_filtered.h5`）。
    - **文件名映射**: `--output X.h5` → `X_filtered.h5`, `X_posterior.h5`, `X_metrics.csv`, `X_cell_barcodes.csv`。
    - **修复**: 用 `*_filtered.h5` glob 而非硬编码前缀。

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

27. **🔥🔥 `torch.load` `weights_only=True` — PyTorch 2.11 默认值与旧 ckpt 不兼容 (2026-07-25, 26样本证实)**：
    - **症状**: `4CL_SD_D4_2_scRNA` 两次重试后日志显示 `_pickle.UnpicklingError: Weights only load failed...`。但日志里有 `Successfully unpacked tarball` — ckpt 解压成功了，是 `torch.load` 拒绝 `cellbender.remove_background.model.RemoveBackgroundPyroModel` 类。
    - **区分于 pitfall 8**: 不是 ckpt 解压失败，是 torch.load 失败。日志有关键线索：`Successfully unpacked tarball` → `UnpicklingError`。
    - **修复**: 删除 ckpt.tar.gz + 旧产出 → 从头跑（不用 ckpt 恢复）。不能调 `weights_only=False`（CellBender 内部调用 torch.load）。已验证成功。
    - **预防**: PyTorch 升级后旧 ckpt 全部失效，首次启动前清理全部 ckpt.tar.gz。

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
