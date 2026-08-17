# Heartbeat Process Death During Zombie Cascade

**Date**: 2026-07-25
**Session**: CellBender 26-sample batch, Stage 2
**Relevant pitfall**: cellbender-batch-pipeline pitfall #17

## Incident

User asked "确定一下心跳真的在工作吗？" (Is the heartbeat really working?). Agent performed three-source verification:

| Source | Result |
|--------|--------|
| `tasklist /FI "PID eq 35912"` | NOT FOUND — heartbeat dead |
| `tasklist /FI "PID eq 45680"` | NOT FOUND — pipeline parent dead |
| `nvidia-smi` | GPU 39%, 5GB VRAM — CellBender orphan alive |
| `stat monitor.log` | Last modified 04:00:22, >2 min stale |
| `tasklist python.exe` | PID 45848, 5.7GB RAM — CellBender orphan |
| `cellbender_output.log` | epoch 046/150, training normally |

## Root Cause

Hermes session recycling killed the `run_pipeline.py` parent process (PID 45680). The `heartbeat.py` script (PID 35912), launched as a child of the same session, was also killed. The CellBender subprocess (PID 45848) became an orphan and continued training independently.

## Key Lessons

1. **Heartbeat can die silently** — just because you started it doesn't mean it's still running
2. **Three-source verification is mandatory**: process alive + file timestamp + content freshness
3. **The CellBender orphan detection pattern**: match RAM usage (~5-6GB) from `tasklist` to VRAM usage from `nvidia-smi`
4. **Restart heartbeat immediately** when detected dead — don't wait for next monitoring cycle
5. **`start /B python heartbeat.py &`** launches heartbeat fully detached from the pipeline process tree

## Detection Script

```bash
# Quick heartbeat health check
HEARTBEAT_PID=<pid>
if ! tasklist /FI "PID eq $HEARTBEAT_PID" 2>/dev/null | grep -q "$HEARTBEAT_PID"; then
    echo "HEARTBEAT DEAD — redeploying..."
    start /B python scripts/heartbeat.py --task "CellBender" --dir PROJECT_DATA_DIR --interval 120 &
fi
```
