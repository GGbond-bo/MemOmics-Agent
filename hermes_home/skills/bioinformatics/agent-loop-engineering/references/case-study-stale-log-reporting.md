# Case Study: Reporting Stale Logs As Live Status

> Source: CellBender Session 2026-07-26, 16:20-16:44

## The Event

```
16:20 - 4CL_SD_D4_2_scRNA crashes at MCKP chunk 5/9 (ArrayMemoryError)
        cellbender_output.log last modified: 16:20
        CellBender process exits, GPU drops to 3%
16:44 - User asks "进度"
        Agent: read_file("cellbender_output.log") → sees crash → reports "MCKP 又崩了"
        Agent did NOT check file mtime before reporting it as "current state"
        Log was 24 minutes old — CellBender had been dead for 24 minutes

User: "你他妈的，蠢货...现在以及下午4点44了，你还在看之前的日志。"
```

## Root Cause

`read_file()` returns text content but NOT file mtime. Agent read a 24-minute-old crash log and presented it as live status, without:
1. Checking `stat` on the file before reading
2. Comparing mtime against current time
3. Cross-validating with GPU + process list

## Defense Layer

**Iron Law (cellbender-batch-pipeline pitfall #34):**
```
After every read_file(log), MUST also stat the log file:

① mtime < 5 min    → log is active, content trustworthy
② mtime 5-30 min   → may be stalled, cross-validate GPU + tasklist
③ mtime > 30 min   → log is DEAD — FORBIDDEN to use content as "current state"
                     Only report: "Last recorded at HH:MM, no updates since"
```

## Correct Investigation Protocol (what 16:44 SHOULD have looked like)

```
1. stat cellbender_output.log → mtime = 16:20 (24 min ago)
2. Judgement: log may be stale → cannot report directly
3. nvidia-smi → GPU 3% → no training running
4. tasklist → no CellBender process
5. ls output dir → no output.h5, no filtered.h5
6. Report: "4CL_SD_D4_2 last recorded at 16:20 (MCKP crash), 24 min no updates. GPU idle. Needs intervention."
```

## Why This Is An Agent Loop Problem

This is the intersection of two failures:

1. **No mtime check in the monitoring protocol** — the "三源交叉验证" only specifies GPU + process + log content, missing the temporal dimension
2. **LLM treats text retrieval as truth retrieval** — `read_file` returns valid text, LLM doesn't know it's stale

The fix: **always stat before read**, and integrate mtime into the judgement logic.
