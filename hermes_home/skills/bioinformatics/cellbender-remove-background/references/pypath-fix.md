# PYTHONPATH Fix for CellBender

> **Root cause**: CellBender is sensitive to PYTHONPATH pollution. A stale PYTHONPATH
> (often from a previous conda env or system Python) causes the process to silently
> hang — it appears to start but produces only conda warnings in the log, never
> reaching CellBender's inference loop.

## Diagnosis

If the CellBender log shows only conda warnings and no `[epoch 001]` line within
30 seconds, it's a PYTHONPATH issue. Example of a stuck log:

```
UserWarning: zstandard could not be imported...
Error while loading conda entry point: conda-libmamba-solver...
```

## ❌ Do NOT use `conda run`

```bash
# WRONG — PYTHONPATH persists, CellBender silently hangs
conda run -n cellbender cellbender remove-background --input ... --output ...
```

## ✅ Correct activation patterns

### Bash (Git Bash / MSYS / WSL / Linux)

```bash
unset PYTHONPATH
source /e/USER_MINICONDA/etc/profile.d/conda.sh
conda activate cellbender
cellbender remove-background --input "..." --output "..." --cuda > run.log 2>&1
```

### PowerShell

```powershell
Remove-Item Env:PYTHONPATH -ErrorAction SilentlyContinue
conda activate cellbender
cellbender remove-background --input "..." --output "..." --cuda > run.log 2>&1
```

### CMD

```cmd
set PYTHONPATH=
conda activate cellbender
cellbender remove-background --input "..." --output "..." --cuda > run.log 2>&1
```

## Pre-run checklist

1. `unset PYTHONPATH` (or platform equivalent)
2. `rm -f ckpt.tar.gz` (avoid hash mismatch from previous runs)
3. Verify GPU: `nvidia-smi` should show available GPU
4. Start CellBender with `--checkpoint-mins 5` (short interval for safety)
5. Wait 30s, then `tail -5 run.log` — should see `[epoch 001]` line