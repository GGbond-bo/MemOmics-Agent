# Error Scanner Design — Lessons from 48-Hour CellBender Session

## Background

During the 2026-07-25 ~ 2026-07-26 26-sample CellBender session, `error_scanner.py` was created as a separate daemon to continuously scan for known error patterns. However, it failed to detect a critical crash (`_ArrayMemoryError` at MCKP chunk 5/9 for `4CL_SD_D4_2_scRNA`) because of a fundamental design flaw.

## Design Flaw #1: Single Log Source

`error_scanner.py` v1 only scanned `watchdog.log`:

```python
# v1 — BROKEN
def scan_logs():
    with open("watchdog.log", "r") as f:
        content = f.read()
    # ... pattern matching ...
```

**Why this fails**: CellBender may be launched through multiple paths:
- `pipeline_watchdog.py` → writes to `watchdog.log`
- Direct `terminal(cellbender ...)` invocation → writes to `cellbender_output/<sample>/cellbender_output.log`
- Bash `run_one_by_one.sh` → output piped to per-sample log
- Manual `subprocess.Popen` by Agent → unknown log path

The error scanner must monitor **all** possible log sources, not just the one it knows about.

## Design Flaw #2: No Time-To-Live (TTL) on Log Reads

When Agent reads a log file at 16:44 that was last modified at 16:20, the content is 24 minutes stale. The scanner didn't distinguish between "this crash just happened" and "this crash happened half an hour ago and the process has been dead since."

## Corrected Design (v2)

```python
KNOWN_ERRORS = {
    "mckp_array_memory": {
        "pattern": r"numpy\._core\._exceptions\._ArrayMemoryError.*Unable to allocate",
        "severity": "critical",
        "auto_fix": True,
        "fix_desc": "increase --low-count-threshold or --total-droplets-included",
        "fix_action": "restart_with_higher_threshold",
    },
    "ptrepack_complevel_equals": {
        "pattern": r"ptrepack.*--complevel=\\d.*non-zero exit",
        "severity": "high",
        "auto_fix": True,
        "fix_desc": "replace '--complevel=N' with '--complevel N'",
        "fix_action": "patch_watchdog_ptrepack",
    },
    "ckpt_torch_load_weights_only": {
        "pattern": r"UnpicklingError.*Weights only load failed",
        "severity": "high",
        "auto_fix": True,
        "fix_desc": "delete ckpt.tar.gz + rerun without checkpoint",
        "fix_action": "delete_ckpt_rerun",
    },
    "cellbender_crash_no_output": {
        "pattern": r"exit_code=[^0].*filtered.h5 missing",
        "severity": "critical",
        "auto_fix": False,  # needs manual investigation
        "fix_desc": "check posterior.h5 → ptrepack if available, else rerun",
    },
}

def scan_all_logs(base_dir):
    """Scan ALL cellbender logs, not just watchdog.log."""
    all_logs = []
    
    # Source 1: Per-sample cellbender logs (most important!)
    for log_path in glob(f"{base_dir}/cellbender_output/*/cellbender_output.log"):
        all_logs.append(("cellbender", log_path))
    
    # Source 2: Watchdog log (if exists)
    watchdog_log = f"{base_dir}/watchdog.log"
    if os.path.exists(watchdog_log):
        all_logs.append(("watchdog", watchdog_log))
    
    # Source 3: Pipeline status
    status_file = f"{base_dir}/pipeline_status.json"
    if os.path.exists(status_file):
        all_logs.append(("pipeline_status", status_file))
    
    alerts = []
    for source_type, log_path in all_logs:
        mtime = os.path.getmtime(log_path)
        age_seconds = time.time() - mtime
        
        # TTL check: skip logs older than 30 minutes
        if age_seconds > 1800:
            continue
        
        with open(log_path, 'r') as f:
            content = f.read()
        
        for error_name, error_def in KNOWN_ERRORS.items():
            if re.search(error_def["pattern"], content):
                alerts.append({
                    "error": error_name,
                    "source": log_path,
                    "source_type": source_type,
                    "detected_at": time.time(),
                    "log_mtime": mtime,
                    "log_age_seconds": age_seconds,
                    "auto_fix": error_def["auto_fix"],
                    "fix_desc": error_def["fix_desc"],
                })
    
    return alerts
```

## Key Rules for Error Scanner

1. **Multi-source**: Scan ALL `cellbender_output/*/cellbender_output.log`, not just watchdog.log
2. **TTL enforcement**: Skip logs older than 30 minutes — they're stale
3. **Timestamp annotation**: Every alert must include `log_mtime` and `log_age_seconds`
4. **Auto-fix gating**: Only `auto_fix=True` errors get automated fixes. `auto_fix=False` errors require Agent intervention
5. **Independent process**: Scanner runs as a separate `subprocess.Popen + CREATE_NO_WINDOW` daemon, writing to `alerts.json`
6. **Agent pull model**: Agent reads `alerts.json` at the START of every response turn (Iron Law 18)

## Integration with Agent Loop

```
Every Agent Response Turn:
  1. Check task_plan.md → current Phase
  2. Check alerts.json → any unacknowledged errors?
  3. If alerts.json has entries:
     a. auto_fix=True → apply fix + acknowledge alert
     b. auto_fix=False → report to user + ask for decision
  4. If no alerts and pipeline running → report progress normally
  5. If no alerts and pipeline dead → investigate why
```

## Session-Specific Evidence

- `4CL_SD_D4_2_scRNA` crashed at 16:20 with `_ArrayMemoryError` (MCKP chunk 5/9)
- error_scanner v1 missed this because it only scanned `watchdog.log`
- `cellbender_output/4CL_SD_D4_2_scRNA/cellbender_output.log` contained the crash but was never scanned
- By the time Agent asked at 16:44, the crash was 24 minutes old and the process was already dead
