---
name: windows-bioinformatics-batch-processing
description: "Windows生信批量任务执行规程：进程生命周期管理、GPU内存、进度监控、错误恢复。适用于CellBender/scanpy/Seurat等需要在Windows上用GPU跑大批量样本的场景"
when_to_use: "在Windows上启动长时间运行的生信批量任务（10+样本，每样本>5分钟）时加载，确保进程不因会话中断而死亡，LLM主动监控进度"
version: 1.0.0
author: MemOmics
license: MIT
platforms: [windows]
metadata:
  hermes:
    tags: [windows, batch, process-management, cellbender, gpu]
    difficulty: advanced
    language: Python
    category: bioinformatics
---

## 🔴 铁规 0: 先调查再回答 — 禁止凭推理断言系统状态

**这是用户最愤怒的错误模式。** 当用户问"现在还在跑吗？"时，凭"之前做了规划所以不可能在跑"推理断言"没有在跑"——但进程表里有 2 个 CellBender 各占 7.2 GB RAM，GPU 73%。

### 三连击检查法（回答系统状态问题前必须全做）

```python
import subprocess

def check_system_state() -> dict:
    """先查再回答——不可省略。"""
    state = {}
    
    # 1. tasklist: 相关的 python/cellbender 进程
    tasklist = subprocess.run(
        ["tasklist", "/FI", "IMAGENAME eq python.exe", "/FO", "CSV"],
        capture_output=True, text=True
    )
    state["python_processes"] = [l.strip() for l in tasklist.stdout.split("\n") if l.strip()]
    
    # 2. nvidia-smi: GPU 占用
    gpu = subprocess.run(
        ["nvidia-smi", "--query-gpu=index,name,memory.used,memory.total,utilization.gpu",
         "--format=csv,noheader,nounits"],
        capture_output=True, text=True
    )
    state["gpu"] = gpu.stdout.strip()
    
    # 3. dir: 检查输出目录
    ls = subprocess.run(["dir", work_dir, "/B"], shell=True, capture_output=True, text=True)
    state["dir_contents"] = [l for l in ls.stdout.split("\n") if l.strip()]
    
    return state
```

**执行顺序**: 用户问系统状态问题 → 执行三连击 → 根据数据回答 → 绝不说"我不知道"或"应该没有"。

### 汇报模板

```markdown
## ✅ 实际状态（查了，不是猜的）

### Python 进程（{n} 个活着）
```
PID   RAM        推测
16312  7.2 GB  🔴 CellBender #1
28208  7.2 GB  🔴 CellBender #2
```

### GPU
```
{util}% 占用, {used_mb} MB / {total_mb} MB
```

### 目录
```
{work_dir}/ 存在 → 内容: [dir listing]
```
```

---

## 🔴 铁规 2: Windows 进程生命周期 — 必须脱离式启动

Hermes 的 `terminal(background=true, notify_on_complete=true)` 创建的进程绑定在 Hermes 会话生命周期上。
当 Hermes 会话回收、上下文压缩、或 LLM 更换时 → **后台进程静默死亡（无日志、无提示）**。

### ✅ 正确做法：subprocess.Popen 脱离式启动

```python
import subprocess, os, sys

def launch_detached(cmd: str, log_path: str, cwd: str = None) -> int:
    """启动脱离 Hermes 生命周期的 Windows 系统级后台进程"""
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    with open(log_path, 'w') as log_f:
        proc = subprocess.Popen(
            cmd,
            shell=True,
            cwd=cwd,
            stdout=log_f,
            stderr=subprocess.STDOUT,
            creationflags=subprocess.CREATE_NO_WINDOW  # 系统级脱离
        )
    return proc.pid
```

### ✅ 或使用 start /B

```bat
rem launcher.bat — 关掉终端也不影响
start /B python F:\path\to\run_pipeline.py > stdout.log 2>&1
```

## 🔴 铁规 3: LLM 主动巡检 — 不等人问

脱离式启动后，LLM 不能再依赖 process.poll() — 改为每轮对话前读磁盘日志文件：

```python
def check_progress(log_path: str) -> dict:
    """读日志文件提取进度"""
    import re
    if not os.path.exists(log_path):
        return {"status": "not_started", "last_line": ""}
    with open(log_path, 'r') as f:
        lines = f.readlines()
    last_line = lines[-1].strip() if lines else ""
    # 提取样本号: "Processing sample 5/26"
    match = re.search(r'(\d+)/(\d+)', last_line)
    return {"status": "running", "last_line": last_line,
            "progress": f"{match.group(1)}/{match.group(2)}" if match else "unknown"}
```

**巡检频率**: 每 5 分钟一次（即每轮对话输出来自于读日志）。
**汇报模板**: `当前样本 {i}/{n}, GPU {util}%, VRAM {used}/{total}GB, 已产出 {k} 个文件, 预估剩余 {est}`

## 🔴 铁规 4: 串行执行 — 一次一个样本

| 资源 | 单样本 | 两个并行后果 |
|------|--------|-------------|
| RAM | ~7 GB | 14+ GB → OOM |
| VRAM | ~10 GB | 分配冲突 → crash |
| Checkpoint | 稳定 | 互相覆盖 → hash mismatch |
| 输出 h5 | 正常写盘 | 无产出 |

```python
# ✅ 正确：for 循环串行
for i, sample in enumerate(samples, 1):
    logger.info(f"[{i}/{n}] 开始 {sample}")
    result = subprocess.run(cmd, ...)  # 阻塞等待
    verify_output(output_path)
    logger.info(f"[{i}/{n}] ✅ 完成 {sample}")

# ❌ 错误：并行启动
for sample in samples:
    subprocess.Popen(cmd, ...)  # 多个同时跑
```

## 🔴 铁规 5: 输出验证 — 不信任 exit code

exit code 0 ≠ 有输出。一些深度学习工具（如 CellBender）训练跑完但保存失败时 exit code 0。

```python
def verify_output(file_path: str, min_size: int = 100_000) -> bool:
    if not os.path.exists(file_path):
        logger.error(f"❌ 文件不存在: {file_path}")
        return False
    actual = os.path.getsize(file_path)
    if actual < min_size:
        logger.error(f"❌ 文件太小: {actual} bytes (< {min_size})")
        return False
    logger.info(f"✅ 验证通过: {file_path} ({actual/1e6:.1f} MB)")
    return True
```

## 🔴 铁规 6: GPU 检测 — 启动前确认

```python
import subprocess, json
result = subprocess.run(
    ["nvidia-smi", "--query-gpu=index,name,memory.total,memory.used,utilization.gpu",
     "--format=csv,noheader,nounits"],
    capture_output=True, text=True
)
print(result.stdout)
# 检查至少一个 GPU 可用
```

## 🔴 铁规 7: 日志结构 — 持久化可读

```
F:/batch_project/
├── logs/
│   └── pipeline.log         # 带时间戳的运行日志
├── output/{sample}/         # 每个样本的输出
├── scripts/
│   └── run_pipeline.py      # 核心 watchdog 脚本
├── summary/
│   └── stats.tsv            # 全部样本汇总表
└── launcher.bat             # 脱离式启动器
```

## 🔴 铁规 8: 目录命名 — 语义化

❌ `cellbender_gzzkq8fy`（随机 session ID，无意义）  
✅ `F:\CellBender_v2\output\4CL_SD_D4_1_scRNA\`

## 🔴 铁规 9: 参数确认 — 启动前输出模板

每次启动批量任务前，LLM 必须输出此确认表：

```markdown
### 参数确认
| 参数 | 值 | 来源 |
|------|-----|------|
| --fpr | 0.01 | 官方默认 |
| --learning-rate | 1e-4 | 官方默认 |
| GPU | CUDA | 显式指定 |
| sitecustomize | v4 deployed | TypeError+AttributeError |
| PYTHONPATH | cleared | env -u |
| 执行模式 | 串行 | 一次一个 |
```
---

## 🔴 铁规 10: 启动前杀残留进程 — 防撞车

批处理启动前，检查并杀死所有同类的残留进程。CellBender 尤其容易残留：训练被中断后进程活着但不输出日志，启动新的 CellBender 后会跟残留进程同时使用 GPU 导致 OOM / checkpoint 冲突。

```python
import subprocess, os, signal

def kill_residual(process_name: str = "cellbender"):
    """杀掉同名的所有残留进程。在 Windows 上 taskkill 比 kill() 可靠。"""
    result = subprocess.run(
        ["tasklist", "/FI", f"IMAGENAME eq {process_name}.exe", "/FO", "CSV"],
        capture_output=True, text=True
    )
    lines = [l.strip() for l in result.stdout.split("\n") if l.strip()]
    # CSV 格式: "python.exe","1234","Console","1","7,456 K"
    import csv, io
    reader = csv.reader(io.StringIO(result.stdout))
    pids = []
    for row in reader:
        if len(row) >= 2 and "cellbender" in row[0].lower():
            pids.append(row[1])
    if pids:
        subprocess.run(["taskkill", "/F"] + [f"/PID {p}" for p in pids],
                       capture_output=True)
        logger.warning(f"已杀残留 {process_name}: {pids}")
```

**使用时机**: 每次 `run_pipeline.py` 启动时，在 for 循环处理第一个样本之前执行。

---

## 🔴 铁规 11: Watchdog 循环 — 失败不崩，继续下一个

批量任务中一个样本失败不应该终止整个批次。使用 watchdog 循环模式：

```python
def run_batch(samples: list, process_fn, log_file: str) -> dict:
    """Watchdog 循环：一个失败→记录→继续下一个"""
    results = {}
    total = len(samples)
    
    for i, sample in enumerate(samples, 1):
        write_log(log_file, f"[{i}/{total}] 开始 {sample}")
        try:
            ok = process_fn(sample)
            results[sample] = {"status": "ok" if ok else "fail"}
            if not ok:
                # 验证产出失败（文件不存在/太小）
                write_log(log_file, f"[{i}/{total}] ❌ 产出验证失败 → 继续下一个")
        except Exception as e:
            # 捕获所有异常，不崩循环
            results[sample] = {"status": "error", "error": str(e)}
            write_log(log_file, f"[{i}/{total}] ❌ 异常: {str(e)[:200]} → 继续下一个")
            traceback.print_exc()
        finally:
            time.sleep(5)  # GPU 释放间隔
    
    n_ok = sum(1 for v in results.values() if v.get("status") == "ok")
    write_log(log_file, f"DONE: {n_ok}/{total} 成功")
    return results
```

**关键原则**:
- 不抛 `SystemExit` / `sys.exit()` — 用返回值传递失败
- 不依赖 Hermes `notify_on_complete` — 日志写磁盘，LLM 通过读日志监控
- 每个样本独立运行、独立清理、独立验证
