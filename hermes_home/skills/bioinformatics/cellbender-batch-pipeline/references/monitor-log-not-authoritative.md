# Monitor.log vs CellBender Log: Trusting Dead Monitor Over Live Source

## Date: 2026-07-25
## Session: CellBender v2 26-sample pipeline (ongoing)

## The Failure

1. `run_pipeline.py` + `heartbeat.py` were killed by Hermes session recycling → `monitor.log` stopped updating at 04:14
2. CellBender orphan process (PID 45848) continued running, actively training `4CL_SD_D4_1_scRNA` through epoch 104+
3. GPU was at 49%, actively computing
4. User asked "进度呢？" (progress?)
5. Agent read stale `monitor.log` → saw epoch 92 from an earlier sample run → wrongly concluded "GPU 3%, stuck"
6. User pasted actual CellBender output (epoch 95-106, GPU 49%) → agent was proven wrong in real-time

## Root Cause

- `monitor.log` is **second-hand data** written by a heartbeat script that lives in the same process tree as `run_pipeline.py`
- When Hermes kills the pipeline parent process, the heartbeat dies too → monitor.log freezes
- CellBender child process becomes orphan → keeps running but monitor.log is forever frozen
- Agent trusted dead monitor over live CellBender log

## User's Explicit Correction

> "你读错文件了，现在是25号的凌晨4点多，怎么老去读那些几个小时前的日志呢？GPU实时调查嘛，只保留最新的任务相关日志和pipeline文件"

Translation: "You're reading the wrong file. It's 4 AM on the 25th — why do you keep reading logs from hours ago? Check GPU in real time. Only keep the latest task-related logs and pipeline files."

## The Fix: Three-Source Priority

| Priority | Data Source | Trust When | Don't Trust When |
|----------|------------|-----------|-----------------|
| 🥇 Highest | `cellbender_output.log` (CellBender's own stdout) | File size actively growing | No update for 10+ min |
| 🥈 Medium | `nvidia-smi` real-time query | Any moment | Can't tell "what" is running alone |
| 🥉 Reference | `monitor.log` | Only when heartbeat process confirmed alive | Heartbeat dead → data frozen |

## Detection Protocol

When user asks for progress:

1. `ls -la cellbender_output/*/cellbender_output.log` — check last modified time + file size
2. `tail -20 cellbender_output/<current>/cellbender_output.log` — get latest epoch
3. `nvidia-smi` — cross-validate GPU utilization
4. Only if sources 1-3 agree → report to user

## Lesson

**Never trust `monitor.log` as the primary data source for training progress.** It's a convenience view written by an unreliable process. CellBender's own log (`cellbender_output.log`) is ground truth. When the two disagree, trust CellBender's log.
