# Case Study: Environment Path Persistence — `environment.json`

## Date
2026-07-29

## Trigger
User asked: "你是怎么管理运行环境的呢？我希望的是，你不是已经获得了一些环境的位置了吗？不应该保存一下吗？下次就先去确定这个环境还在不在，不在，继续找..."

## Root Cause

Every session, MemOmics re-discovered tool paths from scratch:
1. `shutil.which("cellbender")` — every time
2. `sysconfig.get_path("scripts")` — every time
3. `pip show cellbender` fallback — every time

This is wasteful and error-prone. If a tool path changes (e.g., Python upgrade), the Agent should:
1. **Read cached path** from disk
2. **Validate** it still exists
3. **Auto-fix** if broken (re-probe + update cache)
4. **Alert user** only if unfixable

## Fix: Iron Law 25 — Environment Persistence

### Three-Level Check (every analysis startup)

```
Level 1: read_file("environment.json") → load cached paths
    ↓
Level 2: validate each path (shutil.which + os.path.exists)
    ↓
Level 3: auto-fix broken paths (re-probe) → update environment.json
    ↓
Unfixable → prompt user to install/create environment
```

### `environment.json` Schema

```json
{
  "paths": {
    "python": "C:/Users/USERNAME/AppData/Local/Programs/Python/Python312/python.exe",
    "cellbender": "C:/Users/USERNAME/AppData/Local/Programs/Python/Python312/Scripts/cellbender.exe",
    "ptrepack": "C:/Users/USERNAME/AppData/Local/Programs/Python/Python312/Scripts/ptrepack.exe",
    "Rscript": "C:/Program Files/R/R-4.5.3/bin/x64/Rscript.exe"
  },
  "last_validated": "2026-07-29T17:03:00",
  "validated_by": "agent"
}
```

### Companion Script: `scripts/validate_env.py`

One-click validation → OK / MISSING / FIXED per tool.

## Why This Matters

- Without persistence: 30+ seconds of probing every session, potential for stale/wrong paths
- With persistence: ~1 second validation, self-healing on path changes
- Architecture principle: **disk is the source of truth, LLM context is cache**

## Related
- Iron Law 25 (SOUL.md) — environment persistence
- `cellbender-batch-pipeline/scripts/validate_env.py` — companion script
- `cellbender-batch-pipeline/environment.json` — persistent cache (committed to disk)
