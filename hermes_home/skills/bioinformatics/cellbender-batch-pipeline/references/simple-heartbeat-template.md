# Simple Heartbeat Monitor Template (v3)

> **When to use**: You need a lightweight, self-contained heartbeat that writes JSON snapshots every 60s.
> **vs heartbeat_v2.py**: v2 auto-discovers active samples + handles edge cases. This is the "quick deploy" version — fewer features, zero dependencies beyond stdlib, and trivially auditable in one read_file call.

## Design

```
while true:
    read GPU (nvidia-smi)
    read _pipeline_progress.json (current sample, done/failed counts)
    read CellBender output log (epoch, ELBO)
    write _heartbeat.json
    sleep 60
```

## Key principle: read from the REAL log, not a monitor summary

The heartbeat reads epoch/ELBO directly from `cellbender_output.log` (CellBender's own output), not from any derived file. This avoids the "monitor.log is stale" problem (pitfall 20).

## Deployment

```bash
# Start as completely independent background process:
python _heartbeat.py &
# PID recorded separately, heartbeat survives pipeline death
```

## Template Code

```python
#!/usr/bin/env python3
"""Heartbeat monitor for CellBender batch — runs independently, writes _heartbeat.json"""
import os, json, subprocess, time, glob, re
from datetime import datetime

OUT_DIR = r"E:\monkey\cellbender"           # ← CHANGE THIS
HEARTBEAT_FILE = os.path.join(OUT_DIR, "_heartbeat.json")
PROGRESS_FILE = os.path.join(OUT_DIR, "_pipeline_progress.json")

def get_gpu():
    try:
        r = subprocess.run(
            ["nvidia-smi", "--query-gpu=utilization.gpu,memory.used,memory.total,temperature.gpu",
             "--format=csv,noheader"],
            capture_output=True, text=True, timeout=5
        )
        return r.stdout.strip()
    except:
        return "N/A"

def get_active_sample():
    """Find the currently running sample by checking latest log mod time"""
    latest = None
    latest_time = 0
    for d in glob.glob(os.path.join(OUT_DIR, "CRR*")):     # ← CHANGE pattern
        log = os.path.join(d, "cellbender_output.log")
        if os.path.exists(log):
            mt = os.path.getmtime(log)
            if mt > latest_time and "_TRASH" not in d and "_DEL" not in d:
                latest_time = mt
                latest = os.path.basename(d)
    return latest, latest_time

def get_epoch(log_file):
    if not os.path.exists(log_file):
        return None
    try:
        with open(log_file, 'r') as f:
            content = f.read()
        epochs = re.findall(r'Epoch (\d+)', content)
        return int(epochs[-1]) if epochs else None
    except:
        return None

def get_elbo(log_file):
    if not os.path.exists(log_file):
        return None
    try:
        with open(log_file, 'r') as f:
            content = f.read()
        elbos = re.findall(r'elbo: ([-\d.]+)', content)
        return float(elbos[-1]) if elbos else None
    except:
        return None

while True:
    try:
        progress = {}
        if os.path.exists(PROGRESS_FILE):
            with open(PROGRESS_FILE, 'r') as f:
                progress = json.load(f)

        active, active_mtime = get_active_sample()
        log_file = os.path.join(OUT_DIR, active, "cellbender_output.log") if active else None
        epoch = get_epoch(log_file) if log_file else None
        elbo = get_elbo(log_file) if log_file else None

        heartbeat = {
            "ts": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "gpu": get_gpu(),
            "active": active,
            "epoch": epoch,
            "elbo": elbo,
            "progress": progress.get("status", "N/A"),
            "done_count": len(progress.get("done", [])),
            "failed_count": len(progress.get("failed", [])),
        }

        with open(HEARTBEAT_FILE, 'w') as f:
            json.dump(heartbeat, f)

        time.sleep(60)
    except Exception as e:
        print(f"Heartbeat error: {e}", flush=True)
        time.sleep(60)
```

## Customization points

| Field | Line | What to change |
|-------|------|---------------|
| `OUT_DIR` | ~line 8 | Path to your CellBender output directory |
| `CRR*` in glob | ~line 28 | Sample directory pattern (e.g. `*_scRNA` for 4CL/7CL samples) |
| `cellbender_output.log` | ~line 29 | Log filename if different |

## How Agent queries it

```python
# One read_file call gives full status:
read_file("E:/monkey/cellbender/_heartbeat.json")
# Returns: {"ts": "2026-07-30 18:20:00", "gpu": "29 %, 4823 MiB, 16303 MiB",
#           "active": "CRR278963", "epoch": 12, "elbo": -15234.5,
#           "progress": "[3/15] CRR278963 — running", "done_count": 2, "failed_count": 0}
```

## Verification

Heartbeat is alive if:
- `_heartbeat.json` mtime < 120 seconds ago
- `tasklist | grep python` shows the heartbeat PID

Heartbeat is dead if:
- mtime > 2×interval (120s for 60s interval)
- → Re-deploy with `python _heartbeat.py &`
