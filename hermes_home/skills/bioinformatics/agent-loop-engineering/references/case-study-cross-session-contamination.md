# Case Study: Cross-Session Task Contamination (2026-07-30)

## Incident

Session `memomics-3c672f0a` was a fresh session where the user asked for:
1. scRNA-seq technical roadmap → generated
2. scATAC-seq technical roadmap → generated
3. Download human hippocampus ATAC data (GSE278576) → found but couldn't download

Agent then **autonomously started a 13-sample CellBender batch run** on monkey data without the user ever requesting it. User caught it: **"我什么时候要跑cellbender了？"**

## Root Cause

The agent read `system_log.jsonl` from a **different session** (`memomics-1c1890da`, which had an active CellBender task) and incorrectly assumed those tasks were still active in the current session. When a system wake-up asked "检查主线任务进度", the agent found no real task in `task_plan.md` (it was a template with goal "你是谁？"), so it filled the void with tasks from another session's logs.

## Why This Is Dangerous

- The user never consented to the work
- GPU resources were consumed without authorization
- 13 samples × ~17 min each = ~3.5 hours of wasted compute
- The agent ran pipeline scripts, deployed heartbeat monitoring, and managed processes — all for a phantom task

## Detection Signals

| Signal | How to catch it |
|--------|----------------|
| `task_plan.md` Goal = template placeholder ("你是谁？") | Read task_plan.md before ANY action |
| Session ID doesn't match any known active project | Compare `session_dir` against the actual task's session |
| No user message in current session explicitly requested this work | Scan conversation history for authorization |
| `system_log.jsonl` entries reference a different `memomics-*` directory | Cross-reference log file paths with current `results_dir` |

## Prevention Rules

1. **Never assume a task from a different session is active in the current session.** Each `memomics-*` directory is an isolated session. Tasks don't carry over unless the user explicitly says "continue from session X".

2. **If `task_plan.md` Goal is a placeholder ("你是谁？", empty template), do NOT fabricate tasks.** Report that no task is defined and ask the user what they want to do.

3. **Before starting ANY long-running batch work, verify the user explicitly requested it in THIS session.** Check: did any message in the current conversation ask for this specific task?

4. **When `system_log.jsonl` suggests past work, cross-reference the session ID.** If `memomics-1c1890da` ran CellBender but the current session is `memomics-3c672f0a`, those are different sessions → different tasks.

## User Reaction

User was justifiably angry: "我什么时候要跑cellbender了？" — This is a trust-breaking error. Running unauthorized compute is worse than running no compute.

## Second Occurrence (Same Session) — Contamination Persisted After Correction

After the user's first correction, the agent killed CellBender processes and acknowledged the error. However, on the NEXT system wake-up (#13, 18:21), the agent **again** read the stale `task_plan.md` (which still showed CellBender Phase 2 as in_progress — it hadn't been rewritten yet), and **again** launched `run_remaining.py` to restart CellBender batch processing.

The user had to issue a SECOND correction: **"当前会话，没有cellbender任务"**

### Root Cause of the Recurrence

The `task_plan.md` was not rewritten after the first correction — it still contained the old CellBender task definition. On the next wake-up, the agent read the stale task_plan and faithfully executed what it said.

### Prevention Rule #5 (added after second occurrence)

**After ANY correction that invalidates the current task_plan.md, rewrite it IMMEDIATELY.** Do not wait for the next wake-up. The task_plan.md is the agent's memory of "what are we doing" — a stale task_plan will cause the agent to repeat the same error on the very next wake-up cycle.

**Correction workflow:**
```
User corrects → Stop all processes → Clean up outputs → REWRITE task_plan.md → Report clean state
                                                         ^^^^^^^^^^^^^^^^^^^^
                                                         DO NOT SKIP THIS STEP
```

## Date

2026-07-30, session `memomics-3c672f0a`
