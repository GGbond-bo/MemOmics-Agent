# error_scanner.py — Known Defect & Fix Plan

> Status: **Pitfall #29 documented, fix NOT YET applied to error_scanner.py**
> Session: 2026-07-25 ~ 2026-07-26

## Defect

`error_scanner.py` v1.0 only scans `watchdog.log`:

```python
# BUG: only watches watchdog-managed samples
def scan_logs():
    return [WATCHDOG_LOG]  # hardcoded single file
```

If CellBender is launched manually (direct `cellbender.exe` call, bash loop, or `terminal` foreground), its log lives at `cellbender_output/{sample}/cellbender_output.log` — invisible to error_scanner.

**Real-world hit**: `4CL_SD_D4_2_scRNA` crashed at MCKP chunk 5/9 (2026-07-26 16:20) with `_ArrayMemoryError`. `error_scanner.py` did NOT detect it because the sample was manual-launched, not watchdog-managed.

## Fix (NOT YET APPLIED)

```python
import glob
import os

def scan_logs():
    """Scan ALL CellBender logs, regardless of launcher."""
    logs = []
    
    # 1. Watchdog log (if exists)
    if os.path.exists(WATCHDOG_LOG):
        logs.append(WATCHDOG_LOG)
    
    # 2. ALL per-sample CellBender logs — most recent N modified
    sample_logs = sorted(
        glob.glob("cellbender_output/*/cellbender_output.log"),
        key=os.path.getmtime,
        reverse=True
    )
    logs.extend(sample_logs[:5])  # most recently modified 5
    
    return logs
```

## Why Not Yet Fixed

The fix was designed and documented during the session, but the session was interrupted by the `4CL_SD_D4_2_scRNA` MCKP OOM emergency before the fix could be applied to `error_scanner.py` on disk.

## When to Apply

At the start of the next long-running task, before launching the pipeline:
1. Apply the fix to `error_scanner.py`
2. Restart the error_scanner daemon
3. Verify by reading `alerts.json` after the first scan cycle

## Related

- `cellbender-batch-pipeline` SKILL.md pitfall #29 — full diagnosis
- `references/monitoring-lessons-2026-07-25.md` — monitoring architecture analysis
