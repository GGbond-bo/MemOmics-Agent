# Process Launch Decision Tree — Long-Running Bioinformatics Tasks

> **Validated**: 48 hours / 26 samples CellBender session (2026-07-25/26)
> **Applies to**: Any bioinformatics task with expected runtime > 5 minutes

## Decision Tree

```
Task expected duration?
  │
  ├─ < 5 min (pip install, simple file conversion, dir listing)
  │     → terminal(foreground, timeout=300)
  │     → Blocks Agent briefly, but safe — short enough
  │
  ├─ 5–600 min (SCTransform, clustering, DEG, cell type annotation)
  │     → terminal(background=True, notify_on_complete=True)
  │     → Record PID + log path in task_plan.md
  │     → ⚠️ WILL DIE if Hermes session recycles (context compression, new turn init)
  │     → Mitigation: keep user engaged so session doesn't recycle
  │
  └─ > 600 min OR multi-step serial pipeline > 3 hours
        → subprocess.Popen + CREATE_NO_WINDOW (Windows)
        → Completely detached from Hermes process tree
        → Write:
           ├─ pipeline_status.json (PID, current_sample, log_path)
           ├─ task_plan.md (Phase + checklist + errors)
           └─ alerts.json (error_scanner output)
        → Start error_scanner.py as parallel detached process
        → Survives Hermes session death, system sleep, context compression
```

## Why `terminal(background=True)` Dies

```
Hermes Agent session (PID 1000)
  └─ terminal(background=True) bash shell (PID 2000)     ← Hermes kill during recycle
       └─ python run_pipeline.py (PID 3000)               ← dies with parent
            └─ python cellbender.exe --cuda (PID 4000)    ← becomes ORPHAN, survives
       └─ python heartbeat.py & (PID 5000)                ← dies with parent
```

Process tree: all children of the Hermes session are killed when the session recycles.
Only CellBender's CUDA child survives (OS won't kill a process with an active CUDA context).

## The Only Surviving Pattern: Popen + CREATE_NO_WINDOW

```python
import subprocess, os

# Launch completely detached from Hermes
proc = subprocess.Popen(
    ["python", "pipeline_watchdog.py"],
    creationflags=subprocess.CREATE_NO_WINDOW,  # Windows: no console window
    stdout=open(log_file, 'w'),
    stderr=subprocess.STDOUT,
    env={**os.environ, "PYTHONPATH": ""}  # clear PYTHONPATH
)

# Write PID for later management
with open("pipeline_status.json", "w") as f:
    json.dump({"pid": proc.pid, "started": datetime.now().isoformat()}, f)

# proc lives on even if this Python process (Hermes) dies
```

## Management Protocol (since no session_id)

| Action | How |
|--------|-----|
| Check if alive | `tasklist /FI "PID eq <pid>"` |
| Read progress | `read_file(<real log>, offset=-50)` + `stat` for mtime |
| Kill safely | `taskkill /F /PID <pid>` — NEVER `/IM python.exe` |
| Recover after context loss | `read_file(task_plan.md)` → find PID → check alive → read log |

## When NOT to Use Popen

- Single < 5 min commands — overhead not worth it
- Interactive commands needing pty (use `terminal(pty=true)` instead)
- Anything that needs `process(action="poll")` / `process(action="wait")` management (these only work with terminal background)

## Related

- `cellbender-batch-pipeline/scripts/pipeline_watchdog.py` — reference implementation
- `cellbender-batch-pipeline/scripts/heartbeat_v2.py` — heartbeat using same pattern
- `cellbender-batch-pipeline/references/monitoring-lessons-2026-07-25.md` — full timeline
- `agent-loop-engineering/references/case-study-cellbender-failures.md` — failure patterns
