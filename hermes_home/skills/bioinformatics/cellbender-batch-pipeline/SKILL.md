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
| output filtered.h5 大小 | > 100 MB | < 10 MB = 保存失败，检查 torch.save error |
| epoch 数 | 150/150 | 未完成 = 超时被杀 |
| 最终 JSON 状态 | DONE | 缺少 = 进程崩溃，检查最后更新时间 |
| GPU 利用率 | > 80% | < 10% = 可能卡在 CPU / 进程僵死 |

---

## Pitfalls

1. **ckpt.tar.gz 残留** — 每次新样本前必须删，否则 hash mismatch
2. **PYTHONPATH 污染** — `env.pop('PYTHONPATH', None)` 必须做
3. **subprocess timeout** — 每样本设 2400s (40 min)，不要用 600s
4. **不要用 `execute_python`** — max timeout 600s，样本 1 就需要 ~1800s
5. **sitecustomize.py 不靠谱** — 直接改 checkpoint.py 是唯一可靠路径
