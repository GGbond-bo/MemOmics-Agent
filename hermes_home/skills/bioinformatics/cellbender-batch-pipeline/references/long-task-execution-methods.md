# Long Task Execution Methods — 48hr CellBender Field Test

> 2026-07-25 ~ 2026-07-26, 26 样本 CellBender batch pipeline 实战验证
> 结论：只有一种方式可靠存活超过 1 小时。

## Method Comparison

### Method 1: `terminal(background=True)` — Hermes 管理的后台

```python
terminal(command="python run_pipeline.py", background=True, notify_on_complete=True, timeout=60000)
process(action="poll", session_id="xxx")
```

| 优点 | 致命伤 |
|------|--------|
| session_id 可管理 | **绑定 Hermes 会话生命周期** |
| notify_on_complete 自动通知 | 会话回收 → 进程树级联 kill |

**死亡机制**：
```
Hermes Agent 会话 (PID 1000)
  └─ terminal(background=True) bash shell (PID 2000)   ← 被杀
       └─ python run_pipeline.py (PID 3000)              ← 被杀
            └─ python cellbender.exe --cuda (PID 4000)   ← 变孤儿存活
       └─ python heartbeat.py & (PID 5000)               ← 被杀
```

**Field evidence**：
- 03:54 启动 → 04:00 会话回收 → bash + pipeline + heartbeat 全死
- 07:15 再次启动 → 08:43 再次回收 → 全死
- CellBender 子进程变孤儿存活（有独立 CUDA 上下文）
- **Verdict: ❌ 不适合 > 30 分钟的任务**

### Method 2: `subprocess.Popen + CREATE_NO_WINDOW` — 操作系统级脱离

```python
proc = subprocess.Popen(
    ["python", "pipeline_watchdog.py"],
    creationflags=subprocess.CREATE_NO_WINDOW,  # Windows
    stdout=open(log_file, 'w'),
    stderr=subprocess.STDOUT
)
```

| 优点 | 缺点 |
|------|------|
| **完全脱离 Hermes** — 会话回收不影响 | 无 session_id，需手动 PID 管理 |
| pipeline_watchdog.py 存活 18+ 小时 | 报错了 Agent 不自动介入（见 error_scanner 方案） |

**Field evidence**：
- `pipeline_watchdog.py` PID 19976: 13:26 → 次日 07:37（18h+ 未死）
- **Verdict: ✅ 唯一可靠的长任务方案**

### Method 3: Bash `&` 后台 — shell 级

```bash
terminal(command="python heartbeat.py &", background=True)
```

| 死亡原因 |
|----------|
| 双重绑定 — bash 父进程 + Hermes 会话 |
| 任一死亡 → 子进程一起死 |
| heartbeat v1 死了 3 次 |

**Verdict: ❌ 比 Method 1 更脆**

### Method 4: `terminal(foreground, timeout=600)` — 阻塞式

```bash
terminal(command="cellbender run ...", timeout=600)
```

| 限制 |
|------|
| **600s 是 Hermes foreground 硬上限**（框架限制，非用户设定） |
| CellBender 单样本需要 ~3600s |
| 超时 → 进程被 kill（已验证：epoch 43/150 被杀） |

**Verdict: ❌ 长任务不可用**

### Method 5: Windows 计划任务

```powershell
schtasks /create /tn "CellBender" /tr "python run.py" /sc once /st 02:00
```

| 优点 | 缺点 |
|------|------|
| 系统重启仍存活 | 配置复杂，不灵活 |

**Verdict: 🟡 辅助用途（定时检查进度），不适合主动 pipeline**

## Final Verdict

| Method | Survives Session Recycle | Manageable | Overall |
|--------|:---:|:---:|:---:|
| terminal(background=True) | ❌ | ✅ | ❌ |
| Bash & | ❌ | ❌ | ❌ |
| terminal(foreground, 600s) | N/A | N/A | ❌ |
| **subprocess.Popen + CREATE_NO_WINDOW** | **✅** | **⚠️ manual** | **✅** |
| Windows 计划任务 | ✅ | ❌ | 🟡 |

**经 48 小时 CellBender 实战验证：唯一可靠的是 subprocess.Popen + CREATE_NO_WINDOW。**
代价：需要自写 PID 文件 + 信号文件管理（pipeline_status.json）。

## Companion Components Required

For Method 2 to be production-grade:

| Component | Role |
|-----------|------|
| `pipeline_watchdog.py` | Self-healing: bash dies → watchdog takes over |
| `heartbeat_v2.py` | Auto-discovering log reader (reads real logs, not monitor.log) |
| `error_scanner.py` | Detects known error patterns across ALL log sources |
| `pipeline_status.json` | Disk-persistent state (survives Agent restarts) |
| `alerts.json` | Structured error reports for Agent to poll |
