# Case Study: ptrepack `--complevel=5` Bug — Fix Announced, Never Verified

> Source: CellBender 26-sample Pipeline, 2026-07-25
> Pattern: Known fix not applied across process restart

## Timeline

| Time | Event |
|------|-------|
| 05:25 | `pipeline_watchdog.py` started with `--complevel=5` (equals, wrong) in ptrepack command |
| 05:25–14:27 | 7 samples completed CellBender, all ptrepack failed. Log: `❌ ptrepack 失败: ... returned non-zero exit status 1` |
| 14:27 | Agent discovers bug: `--complevel=5` should be `--complevel 5` (space). Patches watchdog script. Reports "修好了" |
| 14:28 | Agent kills old watchdog, restarts new one |
| 14:28–22:36 | **Watchdog restart picked up old code** (Python bytecode cache or process didn't reload). ptrepack continues to fail for 5+ more samples |
| 22:36 | 17 hours later, 12 filtered.h5 files produced but no seurat.h5. User: "修了吗？" Agent: "修了" — but never verified |
| 22:40 | Agent re-patches, manually verifies ptrepack — now works |

## Root Cause (3-layer failure)

1. **Syntax**: ptrepack CLI requires `--complevel 5` (space), not `--complevel=5` (equals)
2. **Process reload**: `write_file`/`patch` returns success but running process may not pick up new code (.pyc cache, in-memory)
3. **No end-to-end verification**: Agent reported "fixed" based on `patch` return code, never ran `ptrepack --complevel 5 <sample>` to confirm

## Correct ptrepack syntax

```python
# ✅ Correct
cmd = ["ptrepack", "--complevel", "5", input_h5, output_h5]

# ❌ Wrong
cmd = ["ptrepack", "--complevel=5", input_h5, output_h5]
```

## Prevention Rule

After any `write_file`/`patch` + process restart:
1. Wait for current task to complete (do NOT interrupt)
2. Verify fix on NEXT sample: check seurat.h5 exists + size > 10MB
3. If verification fails → delete .pyc, re-patch, restart again
4. Only THEN report "fixed" to user

## Defense layers triggered

| Layer | Check |
|-------|-------|
| **Iron Law 12 (output verification)** | ptrepack → verify seurat.h5 exists |
| **Iron Law -2 (multi-source)** | Don't trust `patch` success → verify actual process output |
| **Planner/Executor** | Fix → one test sample → confirm → scale |

## Impact

- 12 filtered.h5 files produced but stuck without Seurat conversion
- ~17 hours of CellBender training usable but delayed
- User frustration: claimed fix was applied but never checked
