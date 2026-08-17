# Case Study: MCKP Estimator GPU Deception (2026-07-25)

## Scenario
CellBender epoch 150/150 done, writing posterior + PDF + barcodes. Log last line:
`Computing target noise counts per gene for MCKP estimator`

GPU drops from 60% → 2%. No `output.h5` or `output_filtered.h5` yet.

## What Agent Did (WRONG)
1. Saw GPU=2% → "must be stuck, kill and restart"
2. Didn't read CellBender's real log
3. Announced "全部白跑了"

## What User Pointed Out
"这不是一直在跑吗？你看过这个日志了吗？"
CellBender was in MCKP estimator — pure CPU phase, 5 minutes remaining.

## Root Cause Triad
| Layer | Failure |
|-------|---------|
| **Data source** | Agent read monitor.log (stale, epoch 092) instead of cellbender_output.log (epoch 106) |
| **Inference** | GPU=2% → "stuck" — single-source conclusion without cross-validation |
| **Process knowledge** | Didn't know MCKP estimator is CPU-only phase lasting 3-5 minutes |

## Correct Protocol
1. Read `cellbender_output.log` last 50 lines — not monitor.log
2. Check `tasklist` — process alive with CPU time increasing
3. GPU=2% + process alive + log growing → MCKP in progress, DO NOT KILL
4. Wait 5 minutes, check if `output.h5` appeared

## Detection Rule
```
GPU < 5% AND process alive (MEM > 4GB) AND last log line contains "MCKP" → NORMAL
GPU < 5% AND process dead AND log no growth > 10 min → STUCK
```

## Lesson
**MCKP estimator looks like a crash but it's the final step.** Killing it wastes 25 minutes of training for nothing.
