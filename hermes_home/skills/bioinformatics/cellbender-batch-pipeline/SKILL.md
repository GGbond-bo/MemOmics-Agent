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

> ⚠️ 不要信任 `_pipeline_progress.json` 的 `done_count`。直接统计 `cellbender_output/*/cellbender_output_filtered.h5` 文件数。详见 `references/windows-ckpt-oom-fixes.md`。

---

## 🔴 重启前强制清理清单

**当 pipeline 崩溃需要重启时，必须先执行此清单（不可跳过）：**

```
□ 1. tasklist + powershell 查所有 cellbender 进程
     powershell "Get-WmiObject Win32_Process | Where-Object { $_.CommandLine -like '*cellbender*' }"
□ 2. taskkill /F 杀全部残留 CellBender（它们可能是孤儿进程，父进程已死）
□ 3. 确认 GPU 空闲: nvidia-smi → utilization < 10%
□ 4. 检查 cellbender_output/ 下所有子目录 → 删掉无 filtered.h5 的孤儿目录
□ 5. 确认 RAM 充足: free -m / tasklist 汇总
□ 6. 确认 ptrepack 在 PATH（不然 Stage 3 静默跳过）:
     python -c "import shutil; print(shutil.which('ptrepack'))"
□ 7. 用 Python subprocess.Popen + CREATE_NO_WINDOW 脱离式启动，不用 start /B
```

详见 `references/zombie-cascade-recipe.md`。

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
