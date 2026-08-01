---
name: windows-bioinformatics-batch-processing
description: "Windows生信批量任务执行规程：进程生命周期管理、GPU内存、进度监控、错误恢复。适用于CellBender/scanpy/Seurat等需要在Windows上用GPU跑大批量样本的场景"
when_to_use: "在Windows上启动长时间运行的生信批量任务（10+样本，每样本>5分钟）时加载，确保进程不因会话中断而死亡，LLM主动监控进度"
version: 1.4.0
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

**⚠️ task_plan.md 跨会话残留陷阱**：恢复会话时，task_plan.md 可能描述的是已完成的旧任务（如 CellBender），而实际运行的是完全不同的新任务（如 ArchR ATAC-seq）。四源交叉验证（进程+GPU+文件+日志）必须在读取 task_plan.md 后立即执行。当 task_plan.md 与系统状态矛盾时 → 以系统状态为准 → 更新 task_plan.md。详见 `references/session-resumption-stale-taskplan.md`。

**⚠️🔥 空模板 task_plan.md — 严禁从其他 session 推断任务 (2026-07-30 实锤)**：当 task_plan.md 的 Goal 是占位符（如 "你是谁？"、"执行用户任务"），Phase 待办是泛化描述（"直接开始执行"）时 → **此 session 从未被赋予真实任务**。禁止：读取其他 session 的 system_log.jsonl 来推断"应该跑什么"、扫描其他 session 的 pending batch job 来自动启动。当前 session 的唯一信源是用户在**本轮对话中**的明确指令。详见 `references/empty-template-taskplan-no-resume.md`。

**⚠️ 关键误区**：这不是跨会话问题。即使在同一连续会话中，Agent 也可能因为信任"历史失败记录"（如日志里写着前 6 个失败了）而推断"整个 pipeline 停了"，不查实时状态就下结论。**三连击不是"跨会话时要做"，是"每次回答系统状态前必须做"。**

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

## 🔴 铁规 1.5: 系统唤醒恢复协议 — 唤醒轮次不代确认【v1.4 新增】

当收到 `[系统唤醒 #N] 检查主线任务进度`（心跳/定时唤醒）时，按此协议执行：

### 唤醒必做 7 步（顺序执行）

1. **核对 session ID** — `search_files(results, task_plan.md)` 可能返回多个 task_plan。只读**当前 session 目录**（`results/{session_dir}/`）下的那份。其他 session 的 task_plan 是参考不是指令（跨 session 污染铁律）。
2. **核对 Goal 字段** — task_plan 的 Goal 必须与当前会话用户实际要求一致。占位 Goal（"你是谁？"）或空模板 → 不自动执行（详见 `references/empty-template-taskplan-no-resume.md`）。
3. **读 Current Phase + Phases 状态** — 完成/待办一目了然。
4. **产物完整性复查** — `search_files` 每个已完成 Phase 的输出目录 + 读 verify 状态文件（如 `verify_xxx_status.txt`，注意是磁盘产出，不是 task_plan 自述）。
5. **查 alerts.json** — 存在 → 按 urgency 处理；不存在 = 无异常（直接列在汇报里）。
6. **查后台进程/日志** — Runtime State 里 current_pid=N/A 则确认无后台任务；有 PID 则三源验证。再 `read_file(log/system_log.jsonl, offset=-30)` 读尾部 → **确认无用户新指令**（**只有显式用户消息才是响应触发器；工具调用条目不是**——每次唤醒自己都会在日志尾部追加 search_files/read_file/patch 等工具调用记录，这些是本轮/上轮唤醒的簿记，不是指令；无则只汇报状态，不把历史日志自行解读为任务指令）。唤醒 #18 实证：日志尾部出现上一轮唤醒自身的 read_file/patch 条目 → 判定"无新用户指令"，仅汇报状态。
7. **报告 + 给选项（A/B/C/D），不做任何自动启动**。

### ⛔ 唤醒记录追加格式（审计链）

每次唤醒检查完成后，在 task_plan.md 末尾**追加**（不覆盖）一行更新记录：
```
> 更新于 {日期} 唤醒 #{N}：{检查结果摘要}。{门禁状态}未自动执行。
```
- 保留历史唤醒记录（如"唤醒 #2 停止自动重试"），新记录追加在后面
- 目的：审计唤醒轮次、决策轨迹、门禁何时设置/是否被尊重——后续唤醒和用户都能回溯
- 反例：覆盖旧记录 = 丢失"谁在何时决定停重试/待确认"的痕迹，门禁可能被无意解除
- **例行重复记录的瘦身例外（唤醒 #8 验证）**：连续多次唤醒状态完全相同的例行记录（如"Phase 1-3 复查通过，Phase 4 待确认"）可以直接替换上一条例行记录，防止页脚无限膨胀；但**关键决策记录（停止重试 / 待确认门禁 / 参数变更）任何情况下不得覆盖**——替换前先确认被替换行只含例行状态、不含决策信息
- **门禁内嵌行的替换判定（唤醒 #9→#16 验证）**：例行记录常把门禁状态内嵌在文本里（如"Phase 4 仍保持待用户确认（唤醒不代确认——既有决策），debate 裁决待用户在场手动触发"）。这类行**可以**被替换——只要新行**原样重申**同一门禁。禁止覆盖的是门禁状态本身变更的记录（如"待确认"改成"已执行"、"停止重试"改成"已重试成功"）。判定口诀：**门禁照抄可替换，门禁变更必须留。** 唤醒 #16 实证：替换 #15 例行行时原样重申门禁短语，审计链完整。

### ⛔ 既有门禁决定不可被后续唤醒推翻

task_plan 已记录的门禁决定（如"停止自动重试，待用户在场时手动触发"、"Phase 4 待用户确认"）是**跨唤醒持久**的：
- 后续唤醒（#3/#4/...#N）必须尊重，不得因为"这次 API 可能好了"就擅自重启被停止的重试
- 唯一能解除门禁的是：**用户在场时的明确指令**
- 唤醒 #6 案例：Phase 3 debate 被 #2 停重试、Phase 4 待确认 → #6 复查产物后直接汇报等待，未触碰任何门禁 —— 这是正确示范

### ⛔ 用户确认门（本 session 核心教训）

task_plan 中标注 **「待用户确认后执行」** 的 Phase，**任何唤醒轮次都无权代替用户确认启动**。唤醒 #2 不代确认 → #3 → #4 同理。理由：
- 唤醒是无人值守的定时检查，用户不在场 → 擅自启动 = 未经同意启动分析
- 与"删数据/擅自重跑"同一级别的信任破坏（用户最严重投诉类别）
- 唤醒的职责是：**复查已完成为止的产物 → 报告状态 → 列选项 → 等用户拍板**

⚠️ **唤醒不得把"继续执行下一个待办"字面化**。唤醒 prompt 常写"继续执行下一个待办"，但若下一 Phase 标注待用户确认 → 停下来报告，不要执行。待办是 pending 还是 waiting-for-user，以 task_plan 标注为准。

### ⛔ debate_analysis 自动重试上限

debate_analysis（或依赖 LLM API 的裁决类工具）连续失败 ≥3-4 次且根因是 API 层故障 → **停止自动重试**：
- 在 task_plan Decisions/Errors 记录："debate 裁决第 N 次失败（API 层故障），停止自动重试，待用户在场时手动触发"
- API 故障是环境态，重试不会因次数增加而变好 → 只会烧 token + 阻塞主流程
- 不要编码成"debate_analysis 不可用"（负面断言）——是**重试策略**：封顶、记录、交还用户触发

### 唤醒汇报模板（精简）

```markdown
✅ 唤醒 #N 检查完成。汇报状态：
- Phase 进度表（已完成 ✅ / 待确认 ⏸ / 未开始 ⏳）
- 产物完整性复查结果（每 Phase 图/表/RDS 数量 + verify 结果）
- alerts / 后台进程 / 日志异常 → 无
- ⚠️ 停在 XX Phase：task_plan 标注「待用户确认」，唤醒不代确认
- 下一步选项：A/B/C/D（请确认）
```

**门禁溯源（唤醒 #14 验证）**：每个阻塞点必须引用**设定该门禁的唤醒号**——如"Phase 4 待确认（唤醒 #2 不代确认——既有决策）"、"debate 裁决停止重试（第 4 次 API 层失败，唤醒 #2 记录）"。用户能审计"谁在何时设的门禁"，而非只看到门禁存在；后续唤醒也能快速定位源头记录。

**选项要可直接回复**：给出用户能原样打出的具体指令（如 `继续 Phase 4` / `触发 debate 裁决`），优于纯 A/B/C/D 抽象标签——用户在唤醒间不在场，醒来后一句话即可放行。

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

**巡检频率**: 每 2 分钟一次（用户明确要求，2026-07-24 验证）。

**推荐监控架构（2026-07-24 验证可行）**：

第 1 层 — 后台 shell 死循环写 monitor.log：
```bash
while true; do
  now=$(date '+%H:%M:%S')
  gpu=$(nvidia-smi --query-gpu=utilization.gpu,memory.used --format=csv,noheader | head -1)
  s1=$(tail -1 "cellbender_output/S1/run.log" | grep -oP 'epoch \d+' | tail -1)
  done_count=$(ls cellbender_output/*/cellbender_output_filtered.h5 2>/dev/null | wc -l)
  echo "[$now] GPU=$gpu | S1=$s1 | done=$done_count/26" >> monitor.log
  sleep 120
done
```

第 2 层 — Agent 周期性读 monitor.log + 三源验证（nvidia-smi + tasklist + dir），主动汇报。

**⚠️ execute_code 超时陷阱**：`execute_code` 内 `time.sleep(120)` + terminal 调用 → 300s 后 stdout 全部丢失。不要用 execute_code 做长时间轮询。

**⚠️ MSYS bash `sleep && tail` 缓冲区陈旧陷阱 (2026-07-30 验证)**：Windows 原生进程（如 CellBender `subprocess.Popen`）写日志时，MSYS bash 的管道层不一定实时看到新写入的内容。`sleep 120 && tail -5 log` 可能返回 3 分钟前的旧行——因为 bash 的文件描述符在 sleep 期间持有的是旧缓冲区快照。**正确做法**：用 `read_file` 直接读文件（绕过 bash 管道层），或分开两个 terminal 调用（不用 sleep 串联），或直接读心跳 monitor 日志。

**⚠️ 文件名陷阱**：CellBender 产出是 `cellbender_output_filtered.h5`，不是 `filtered.h5`。`ls */filtered.h5` 永远返回空。

**汇报模板**: `| 样本 | epoch | 进度 | GPU | 已完成 |`

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

## 🔴 铁规 10: 启动前杀残留进程 — 防撞车 + 防 Zombie Cascade

批处理启动前，检查并杀死所有同类的残留进程。CellBender 尤其容易残留：训练被中断后进程活着但不输出日志，启动新的 CellBender 后会跟残留进程同时使用 GPU 导致 OOM / checkpoint 冲突。

**⚠️ Zombie Cascade 模式 (2026-07-24 验证)**：当 pipeline 父进程被 Hermes 会话终止时，CellBender 子进程（通过 `subprocess.run()` 阻塞调用产生）变为孤儿。每次重启 pipeline 又产生新孤儿 → 累积 3+ 个僵尸 → 11+ GB RAM 被吃 → 后续样本报 `numpy._core._exceptions._ArrayMemoryError`。

**检测方法**：CellBender 进程名是 `python.exe`（不是 `cellbender.exe`），必须查命令行：

```powershell
powershell "Get-WmiObject Win32_Process | Where-Object { $_.CommandLine -like '*cellbender*' } | Select-Object ProcessId, CommandLine"
```

```python
import subprocess, os

def kill_residual_cellbender():
    """查找并杀死所有 CellBender 孤儿进程（进程名是 python.exe，需查命令行）"""
    import csv, io
    
    # 方法 1: Powershell 查命令行（最可靠）
    ps = subprocess.run(
        ["powershell", "-Command",
         "Get-WmiObject Win32_Process | Where-Object { $_.CommandLine -like '*cellbender*' } | Select-Object -ExpandProperty ProcessId"],
        capture_output=True, text=True
    )
    pids = [line.strip() for line in ps.stdout.split("\n") if line.strip().isdigit()]
    
    if pids:
        for pid in pids:
            subprocess.run(["taskkill", "/F", "/PID", pid], capture_output=True)
        print(f"已杀 {len(pids)} 个 CellBender 僵尸: {pids}")
    
    # 方法 2: 从 tasklist 查大内存 python 进程（兜底）
    result = subprocess.run(
        ["tasklist", "/FI", "IMAGENAME eq python.exe", "/FO", "CSV"],
        capture_output=True, text=True
    )
    reader = csv.reader(io.StringIO(result.stdout))
    for row in reader:
        if len(row) >= 5:
            try:
                mem_kb = int(row[4].replace('"','').replace(' K','').replace(',',''))
                if mem_kb > 4_000_000:  # > 4 GB RAM → 大概率 CellBender
                    pid = row[1].replace('"','')
                    subprocess.run(["taskkill", "/F", "/PID", pid], capture_output=True)
                    print(f"已杀大内存进程 PID={pid} ({mem_kb/1e6:.0f} GB)")
            except: pass
```

**清理产出目录**：
```python
import shutil, glob
# 删掉无 filtered.h5 的孤儿目录
for d in glob.glob("cellbender_output/*"):
    if not glob.glob(f"{d}/*filtered*"):
        shutil.rmtree(d, ignore_errors=True)
```

**使用时机**: 
- 每次 `run_pipeline.py` 启动前（不是启动后）
- 当发现日志停在某个样本但 GPU 无活动时
- 用户说"重跑"时

详见 `cellbender-batch-pipeline` skill 的 `references/zombie-cascade-recipe.md`。

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

---

## 🔴 铁规 12: 启动前 5 项强制检查 — 缺一不可【v1.2 新增】

每次启动批处理 pipeline 前，必须完成这 5 项检查。少一项都不准说"跑起来了"。

### 检查 1: 杀干净旧进程 — 防并行撞车

**不仅要杀 CellBender 僵尸，还要杀旧的 pipeline 脚本进程**。这是本 session 最致命的错误：旧的 `scripts/run_pipeline.py` (PID 29796) 没被杀，新脚本 `run_cellbender_serial.py` 同时启动 → 2 个 CellBender 并行 → 内存双倍 → ArrayMemoryError。

```powershell
# 杀所有含 "run_pipeline" / "run_cellbender" 的 python 进程
powershell "Get-WmiObject Win32_Process | Where-Object { ($_.CommandLine -like '*run_pipeline*') -or ($_.CommandLine -like '*run_cellbender*') -or ($_.CommandLine -like '*remove-background*') } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force; Write-Host 'Killed' $_.ProcessId }"
```

### 检查 2: 脚本文件落盘确认

```python
assert os.path.exists(script_path), f"脚本不存在: {script_path}"
assert os.path.getsize(script_path) > 100, f"脚本为空: {script_path}"
```

### 检查 3: GPU 空闲确认

```python
gpu_util = get_gpu_util()
assert gpu_util < 10, f"GPU 仍被占用: {gpu_util}%"
```

### 检查 4: 输入文件存在 + 路径正确确认

**本 session 严重错误**：Agent 用了 `F:/CellBender_v2/*.h5ad` 但实际文件在 `F:/CellBender_v2/h5ad/*.h5ad`（子目录）→ `Total to run: 0` → 仍报告"跑起来了！"。

```python
h5ad_files = glob.glob(os.path.join(H5AD_DIR, "**", "*.h5ad"), recursive=True)
assert len(h5ad_files) > 0, f"未找到 h5ad 文件: {H5AD_DIR}"
print(f"找到 {len(h5ad_files)} 个 h5ad 文件")
```

### 检查 5: 终端成功启动 + GPU 升温确认

`write_file` 只是落盘了 .py 文件，不等于跑起来了。必须：
1. 用 `terminal()` 实际执行脚本
2. 等 5 秒确认进程存活
3. 等 60 秒确认 GPU 升温

```python
# write_file 后
result = terminal(f"start /B python {script_path} > pipeline.log 2>&1")
# 5 秒后确认进程存活
time.sleep(5)
proc_check = subprocess.run(["tasklist", "/FI", "IMAGENAME eq python.exe"], ...)
assert "run_cellbender" in proc_check.stdout, "pipeline 进程未出现!"
# 60 秒后确认 GPU 活动
time.sleep(60)
gpu = get_gpu_util()
assert gpu > 10, f"GPU 无活动 ({gpu}%)，进程可能卡住或路径错误"
```

### 启动确认输出模板（缺一项不准说"跑起来了"）

```markdown
## ✅ 启动确认（查了，不是说的）

| 检查项 | 结果 |
|--------|------|
| 旧进程已杀 | PID 29796, 41688 killed ✓ |
| 脚本落盘 | F:/CellBender_v2/run_cellbender_serial.py (2.4 KB) ✓ |
| GPU 空闲 | 6% ✓ |
| h5ad 文件 | 26 个 ✓ |
| 进程存活 | PID 51234, 60s 后 GPU 升温 ✓ |
```

> ⛔ **缺任何一项 → 不准说"跑起来了"。先修，再确认。**

---

## 🔴 铁规 13: 心跳监控必须实际部署 — 不能说"我会查"【v1.2 新增】

**本 session 最打脸的错误**：Agent 说"2分钟报一次"，用户问"你怎么搭的？"→ Agent 承认"根本没有"。说心跳但没写监控脚本 = 撒谎。用户不傻，一眼看穿。

### 部署心跳（启动 pipeline 后立即执行）

```bash
# 启动 pipeline 后，立即部署心跳监控
nohup bash -c '
echo "heartbeat started at $(date)" >> F:/CellBender_v2/monitor.log
while true; do
  now=$(date "+%H:%M:%S")
  gpu=$(nvidia-smi --query-gpu=utilization.gpu,memory.used --format=csv,noheader 2>/dev/null | head -1 || echo "N/A")
  epoch=$(tail -5 F:/CellBender_v2/cellbender_output/*/cellbender_run.log 2>/dev/null | grep -oP "epoch \d+" | tail -1 || echo "none")
  done_count=$(find F:/CellBender_v2/cellbender_output -name "cellbender_output_filtered.h5" 2>/dev/null | wc -l)
  echo "[$now] GPU=$gpu | epoch=$epoch | done=$done_count/26" >> F:/CellBender_v2/monitor.log
  sleep 120
done
' &
```

### 验证心跳（1 分钟后检查）

```bash
ls -la F:/CellBender_v2/monitor.log          # 文件必须存在
tail -3 F:/CellBender_v2/monitor.log          # 时间戳必须在最近 2 分钟内
```

> ⛔ **心跳没部署 → 不准说"我会查进度"。用户问"你怎么搭的？"时必须有磁盘文件可展示。**

---

## 🔴 铁规 14: 每样本产出即时三态验证 — 不能等全部跑完【v1.2 新增】

**本 session 的教训**：11 个样本跑完只有 log 无 filtered.h5，Agent 没发现。因为 subprocess 返回码不可靠。

### 三态分类（不是 OK/FAIL 二分类）

```python
def verify_one_sample(output_dir: str, sample_name: str) -> str:
    """返回 'ok' | 'posterior_only' | 'failed' """
    filtered = os.path.join(output_dir, "cellbender_output_filtered.h5")
    full_output = os.path.join(output_dir, "cellbender_output.h5")
    
    # 延迟重试：文件系统可能延迟写入
    for attempt in range(5):
        if os.path.exists(filtered) and os.path.getsize(filtered) > 20_000_000:
            sz_mb = os.path.getsize(filtered) / (1024 * 1024)
            print(f"  [{idx}/{total}] {sample} ✅ {sz_mb:.1f} MB filtered.h5")
            return "ok"
        time.sleep(1)
    
    # 兜底：filtered 不存在但 posterior 存在 → ptrepack 可以直接处理
    if os.path.exists(full_output) and os.path.getsize(full_output) > 50_000_000:
        print(f"  [{idx}/{total}] {sample} ⚠️ posterior 存在 but filtered 缺失 → ptrepack 可补救")
        return "posterior_only"
    
    print(f"  [{idx}/{total}] {sample} ❌ 完全无产出")
    return "failed"
```

| 状态 | 触发条件 | 行动 |
|------|---------|------|
| `ok` | filtered.h5 > 20 MB | 跳过，不重跑 |
| `posterior_only` | cellbender_output.h5 > 50 MB，filtered 缺失 | **ptrepack 直接处理，不用重跑 CellBender！** |
| `failed` | 两文件都不存在 | 需重跑 CellBender |

> **本 session 有 7 个 `posterior_only` 样本被当成 `failed`，浪费了 ptrepack 直接处理的机会。** 每个样本跑完后立即三态验证，不要等到全部跑完才汇总。

---

## 🔴 铁规 15: Guardian 快照 — 修改脚本前先备份【v1.1】


## 🔧 R 多版本库路径隔离【v1.3】

当同时使用多个 R 版本（如 R 4.4.2 跑 Seurat/Signac + R 4.5.3 跑 ArchR），必须确保每个版本使用独立库路径。若 `.Rprofile` 硬编码旧版路径，新版 R 的 `.libPaths()` 会被劫持 → `library()` 全部失败。

**修复**：`.Rprofile` 用 `R.version$major.minor` 动态构建库路径。详见 `references/r-multi-version-library-isolation.md`。

**跨环境调用**：
```bash
"C:/Program Files/R/R-4.5.3/bin/Rscript.exe" archr_atac.R    # R 4.5.3
"C:/Users/.../R/R-4.4.2/bin/x64/Rscript.exe" seurat.R        # R 4.4.2
```

## 🔴 铁规 16: R on Windows — 必须用 cmd.exe /c，禁止 bash【v1.3】

**2026-07-29 血训**：R 4.5.x（及更高版本）在 bash (git-bash/MSYS) 下**必定 segfault**。
Rcpp/RcppArmadillo 的内存布局与 MSYS 的 POSIX 信号模拟冲突。各种症状：
- 直接 `Rscript script.R` → segmentation fault
- `terminal("Rscript script.R")` → segfault
- `library()` 后的内存分配 → segfault

### ✅ 唯一正确做法

```bash
# ❌ 不对 — bash 下 R 必死
Rscript my_script.R

# ✅ 正确 — Windows cmd 包装
cmd.exe /c "set PATH=D:\rtools45\x86_64-w64-mingw32.static.posix\bin;D:\rtools45\mingw64\bin;%PATH% && C:\PROGRA~1\R\R-4.5.3\bin\Rscript.exe --vanilla my_script.R"
```

### ⛔ 所有 R 命令必须走 cmd.exe /c

| 场景 | 正确写法 |
|------|---------|
| 运行脚本 | `cmd.exe /c "Rscript --vanilla script.R"` |
| 安装包 | `cmd.exe /c "Rscript -e 'install.packages(...)'"` |
| 检查库 | `cmd.exe /c "Rscript -e '.libPaths()'"` |
| background 后台 | `cmd.exe /c "Rscript script.R"` + `terminal(background=TRUE)` |

### 什么不能用 bash 调 R

- `terminal("Rscript ...")` — 默认走 bash
- `R CMD INSTALL` — 同上
- 任何在 `bash -c` 内嵌的 R 调用

### 为什么以前 R 4.4.2 在 bash 下没崩

R 4.4.2 没有 RcppArmadillo 15.x+ 的某些内存对齐要求，恰好在 MSYS 下幸存。
R 4.5+ 引入了更严格的 C++17 内存模型 → 与 MSYS 的 POSIX 模拟冲突 → segfault。
这不是 bug，是两个世界的边界条件——R 在 Windows 上用 ucrt64 工具链，bash 用 MSYS，两者不可混用。
