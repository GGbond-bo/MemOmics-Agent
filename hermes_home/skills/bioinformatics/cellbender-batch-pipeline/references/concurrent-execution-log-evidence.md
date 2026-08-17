# Concurrent Execution Bug — Log Evidence

**Date**: 2026-07-25  
**Session**: CellBender 26-sample batch pipeline  
**Skill**: cellbender-batch-pipeline  

## The Bug

At `00:01:47`, the pipeline launched TWO CellBender processes simultaneously:

```
[2026-07-25 00:01:47] [Stage2] [7CL_D4_1_scRNA] [13/26] 开始
[2026-07-25 00:01:47] [Stage2] [7CL_D2_2_scRNA] [6/26] 开始
```

At this point, `7CL_D3_2` and `7CL_D2_1` had both just failed (chunks completed but no filtered.h5). The monitor then started `7CL_D4_1` and `7CL_D2_2` in the same second — two CellBender GPU processes running in parallel.

## Root Cause Analysis

`run_pipeline.py` has this flow:

```python
for sample in samples:
    result = subprocess.run(cellbender_cmd, timeout=2400)
    if not verify_output(output_path):
        logger.error(f"FAIL")
        continue  # ← immediately goes to next sample
```

When `subprocess.run()` returns (timeout or process exit), the CellBender child process may still be:
- Holding GPU memory (CUDA context not fully freed)
- Holding `%TEMP%` file handles (ckpt.tar.gz extraction temp files)
- Writing posterior.h5 to disk

The `continue` immediately starts the next sample's `subprocess.run()`, which launches a second CellBender BEFORE the first one has fully exited.

## Consequences

1. **ArrayMemoryError**: 2x CellBender → 14+ GB RAM → numpy OOM in `compute_denoised_counts`
2. **FileNotFoundError**: Temp file locks from process #1 prevent process #2 from unpacking ckpt
3. **Ghost processes**: Both may appear to complete but produce no filtered.h5
4. **Checkpoint corruption**: Two processes writing to different output dirs but sharing GPU memory

## Fix Applied

```python
import time, subprocess

for sample in samples:
    # Guard 1: Kill any residuals before starting
    subprocess.run(["taskkill", "/F", "/IM", "cellbender.exe"], 
                   capture_output=True)
    
    # Guard 2: Wait for GPU to fully release
    while True:
        gpu = subprocess.run(
            ["nvidia-smi", "--query-gpu=utilization.gpu", 
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True
        )
        if int(gpu.stdout.strip()) < 20:
            break
        time.sleep(5)
    
    result = subprocess.run(cellbender_cmd, timeout=2400)
    
    # Guard 3: Post-run cooldown BEFORE starting next sample
    time.sleep(10)  # Wait for temp file handles to release
    
    if not verify_output(output_path):
        logger.error(f"FAIL")
        continue
```

## Verification

After fixing, the log should show sequential timestamps with gaps between samples:

```
[2026-07-25 14:05:30] [Stage2] [X_scRNA] OK — filtered.h5: 85 MB (12.3 min)
[2026-07-25 14:05:40] [Stage2] [Y_scRNA] [N/26] 开始  ← 10s gap after cooldown
```

NOT this (bug):
```
[2026-07-25 00:01:47] [Stage2] [7CL_D4_1_scRNA] [13/26] 开始
[2026-07-25 00:01:47] [Stage2] [7CL_D2_2_scRNA] [6/26] 开始  ← SAME SECOND!
```
