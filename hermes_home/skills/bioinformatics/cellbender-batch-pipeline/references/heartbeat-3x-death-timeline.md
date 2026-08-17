# Heartbeat 3x Death Timeline — CellBender 26 Sample Session

**Session**: 2026-07-25, CellBender Stage 2 on PROJECT_DATA_DIR (26 h5ad → filtered.h5)
**Pattern**: Same-session heartbeat death ×3, pipeline zombie cascade, 0 filtered.h5 despite 10+ completed CellBender training runs.

## Timeline

| Time | Event | Heartbeat PID | run_pipeline PID | CellBender Orphan | GPU |
|------|-------|---------------|------------------|-------------------|-----|
| ~02:30 | Pipeline started | — | 45680 | — | — |
| ~02:45 | Heartbeat deployed #1 | 35912 | 45680 (alive) | — | 48% |
| ~03:54 | Pipeline wakes from idle, restarts 4CL_D4_1 | 35912 (alive) | 45680 (alive) | — | 48% |
| 04:00:22 | **Last heartbeat write #1** | ~~35912~~ | ~~45680~~ | — | 2% |
| 04:01 | GPU drops to 2%, pipeline.log stops updating | dead | dead | 45848 spawned | 2% |
| 04:04 | CellBender orphan epoch 50 detected | dead | dead | 45848 (epoch 050) | 54% |
| ~04:06 | Heartbeat deployed #2 | 40040 | — | 45848 (epoch 065-077) | 26-47% |
| ~20:16 | **Session resumed** — heartbeat #2 alive, but pipeline still dead | 40040 (alive) | dead | 45848 (epoch 029) + new orphan | 81% |
| 20:40 | 4CL_D4_1 reaches epoch 142, GPU drops to 1% | 40040 (alive) | dead | 45848 | 1% |
| 20:42-21:14 | New samples start but epoch tracking lost | 40040 (alive) | dead | 45848 + new samples | 43-86% |

## Root Cause

1. Hermes session recycling kills `run_pipeline.py` parent process
2. Heartbeat (`terminal(background=true)`) hangs under same process tree → dies too
3. CellBender subprocess survives as orphan → runs current sample to completion → stops (no parent loop to advance)
4. Restarting heartbeat doesn't fix the dead pipeline → same cycle repeats

## Key Metrics After 20+ Hours

- CellBender training completed: **10 samples** (have output.h5 or posterior.h5)
- filter.h5 produced: **0** (ptrepack never ran)
- Heartbeat redeployments: 3
- Heartbeat deaths: 3
- User "进度呢？" / "心跳还在吗？" / "这不是死掉了吗？" queries: 4

## Actionable Takeaway

**`run_pipeline.py` approach is fundamentally unreliable for sessions spanning > 2 hours.**
Replace with **bash loop** that uses file-existence skip logic — survives any parent process death.
