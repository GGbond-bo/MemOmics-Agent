# Case Study: Wrong Data Source — monitor.log vs Real Log

**Date**: 2026-07-25  
**Session**: CellBender D4 (26-sample batch)  
**Severity**: Critical — led to false declarations of pipeline failure

## The Event

1. CellBender was running `4CL_SD_D4_1_scRNA`, training normally at epoch 106/150
2. User asked: "进度呢？" (What's the progress?)
3. Agent read `monitor.log` — heartbeat had died, last entry showed epoch 092
4. Agent declared: "全白跑了" (Everything was wasted)
5. User pointed out: "这个不是一直在跑吗？你看过这个日志了吗？" (Hasn't this been running all along? Did you even look at this log?)
6. User pasted the *real* `cellbender_output.log` showing epoch 095—106, loss 17774→10219

## Root Cause

**Agent trusted `monitor.log` as the authoritative data source**, when it was a stale secondary summary:

| Data Source | What It Is | Reliability |
|-------------|-----------|-------------|
| `cellbender_output.log` | CellBender's own stdout | ✅ Authoritative — this IS the ground truth |
| `monitor.log` | Heartbeat script's periodic snapshot | ❌ Stale if heartbeat died, always 1-2 cycles behind |

## Why monitor.log Failed

1. Heartbeat (PID 35912) died when Hermes recycled the session
2. monitor.log last entry: 04:00:22
3. User asked at ~04:14 — monitor.log was 14 minutes stale
4. Agent didn't check timestamp before trusting the data

## The Three-Source Rule (Post-Mortem)

After this event, SOUL.md Iron Law 16 was created:

**Every progress query MUST verify three independent sources:**

```
① nvidia-smi          → GPU real-time (util% + VRAM + temp)
② tasklist            → Is the target process alive?
③ read_file(REAL log, last 50 lines) → CellBender's own output
```

**monitor.log is NOT a source — it's a heartbeat health indicator only.**

## Key Lessons

1. **monitor.log ≠ real log.** It's a convenience summary for the Agent, not an authoritative data source.
2. **Check timestamps.** If monitor.log hasn't been updated in > 2× check_interval, it's stale — discard.
3. **Read the REAL log first.** Before forming any conclusion, read `cellbender_output.log` tail.
4. **Don't declare failure from secondary evidence.** GPU=3% + monitor shows epoch 92 → could mean checkpoint save, not death.
5. **User knows more than you about their data.** When they push back, re-examine your data sources.

## Detection Pattern

```
IF Agent says "not running" or "stuck at epoch N"
   BUT hasn't called read_file(REAL_LOG)
   → VIOLATION — Iron Law 16 breach
```

## Related

- `references/case-study-trusting-stale-monitor.md` — earlier instance of same pattern
- `cellbender-batch-pipeline` pitfall 20 — "监控目标错位"
- `cellbender-batch-pipeline` pitfall 21 — "推理代替调查"
- SOUL.md Iron Law 16 — Three-source cross-verification
- SOUL.md Iron Law 17 — Heartbeat must survive Agent lifecycle
