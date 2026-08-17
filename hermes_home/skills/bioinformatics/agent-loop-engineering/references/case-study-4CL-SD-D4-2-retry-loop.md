# Case Study: 4CL_SD_D4_2 — 4 Attempts, Same Crash (2026-07-25/26)

## TL;DR

`4CL_SD_D4_2_scRNA` took 4 attempts to complete. The first 3 failed identically — MCKP `_ArrayMemoryError` at chunk 5/9. Each retry used **unchanged parameters** (`--low-count-threshold 5`), guaranteeing the same crash. Only after switching to `--low-count-threshold 20` did it succeed.

**Root lesson**: Same params + same crash = guaranteed same result. Don't retry without changing something.

## Timeline

| Attempt | Start | End | Mode | Outcome |
|---------|-------|-----|------|---------|
| #1 | ~22:00 D3 | ~23:00 D3 | Bash loop (watchdog) | MCKP chunk 5/9 → `_ArrayMemoryError: 323 MiB` |
| #2 | ~15:22 D4 | ~16:20 D4 | Agent deleted dir + fresh run | Same crash, same chunk, same error |
| #3 | ~16:40 D4 | ~17:50 D4 | Popen detached, fresh run | Same crash (posterior.h5 saved, no output.h5) |
| #4 | ~18:00 D4 | ~18:10 D4 | Popen, `--low-count-threshold 20` | ✅ SUCCESS |

## Error Details

```
File "cellbender/remove_background/estimation.py", line 631, in _chunk_estimate_noise
    df['map'] = df['m'].apply(lambda x: lookup_map_from_m[x])
numpy._core._exceptions._ArrayMemoryError: Unable to allocate 323. MiB
    for an array with shape (42335779,) and data type int64
```

- **26,610 features** passed `--low-count-threshold 5` filter (vs ~19,000 in other samples)
- MCKP estimator created a **42,335,779-row DataFrame**
- numpy could not allocate 323 MiB of **contiguous** memory — 56 GB total but fragmented

## Why 3 Attempts Failed

| Failure Mode | Attempt(s) | Root Cause |
|-------------|-----------|------------|
| **Agent deleted directory without permission** | #2 | "清理后台" misinterpreted as "delete and restart". User: "谁要你删了？？？" |
| **Same params retried** | #2, #3 | Crash was deterministic but Agent didn't change `--low-count-threshold` |
| **Stale log read as "current"** | #3 aftermath | 16:20 crash log read at 16:44, reported as "current state". User: "现在以及下午4点44了，你还在看之前的日志" |
| **ckpt torch.load incompatibility** | Attempt to resume #3 | PyTorch 2.11 `weights_only=True` blocked loading old ckpt |

## The Fix That Worked (Attempt #4)

Changed `--low-count-threshold 5` → `--low-count-threshold 20`, reducing features from 26,610 to ~18,000. MCKP DataFrame shrank below the contiguous memory threshold.

Also killed all zombie processes first to defragment RAM.

## Architecture Lessons

### Lesson 1: Retry Protocol
```
After crash N:
  1. Identify exact error (read log, not infer)
  2. Check: same error as previous attempt?
     YES → MUST change parameters. Same params = same crash.
     NO → new error, diagnose separately
  3. Apply exactly ONE change per retry (measure what worked)
  4. Record in task_plan.md Decisions Made table
```

### Lesson 2: Delete Requires Permission
```
"清理后台" = kill zombies + free RAM + continue
"清理后台" ≠ rm -rf output_dir
Any delete operation → ask user first.
```

### Lesson 3: Log Timestamp Validation
```
read_file(log) → no mtime → text might be stale
Always stat the log after reading.
mtime > 5 min → "data may be stale, last recorded HH:MM"
mtime > 30 min → "log is dead, cannot report as current"
```

### Lesson 4: ckpt Resume Limitations
```
ckpt.tar.gz resume works for: training continuation
ckpt.tar.gz resume fails for: torch.load(weights_only=True) old ckpt
→ Before resuming, delete ckpt if PyTorch was recently upgraded
→ OR need to patch CellBender source to call torch.load(weights_only=False)
```

## Related Skills

- `cellbender-batch-pipeline` pitfall 30 (MCKP OOM), pitfall 27 (torch.load), pitfall 31 (cleanup misinterpretation), pitfall 32 (stale log)
- `agent-loop-engineering` — "Same Error Retried Without Change" anti-pattern
- `cellbender-batch-pipeline/references/process-launch-decision-tree.md` — when to use Popen
