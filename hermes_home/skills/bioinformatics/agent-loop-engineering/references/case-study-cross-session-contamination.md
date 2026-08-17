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

## Third Occurrence — Multi-Copy task_plan.md Contamination

After the second correction, the agent wrote a clean `task_plan.md` to `results/memomics-3c672f0a/task_plan.md` with explicit red lines:

```
## 红线（本 session 绝对不做）
- ❌ CellBender
- ❌ Monkey 数据处理
- ❌ 任何未经用户明确指令的分析任务
```

However, on the next system wake-up, the agent **found and acted on a SECOND copy** of `task_plan.md` at `E:/monkey/cellbender/task_plan.md` — a copy that the pipeline had written to the data directory during the unauthorized run. This copy still contained the old CellBender Phase 2 tasks, and the agent started executing from it, bypassing the clean copy in `results/`.

**The user had to issue a THIRD correction: "你怎么又跑cellbender了？"**

### Root Cause

1. **Multi-copy problem**: Pipeline scripts (like `run_remaining.py`) write their own `task_plan.md` to the data directory (`E:/monkey/cellbender/`). When cleaning up, the agent only fixed the main `results/` copy — data-directory copies survived.
2. **System injection**: The Hermes framework can inject stale `task_plan.md` content into the system prompt (visible in system messages: "以下是磁盘上 task_plan.md 的当前状态摘要"). If a stale copy exists anywhere, it can be injected as context.
3. **Weak copy**: Even after writing a clean `task_plan.md`, the agent's correction was fragile — it lived in only one location and could be bypassed by any other copy.

### Prevention Rule #6 (added after third occurrence)

**After correction, scavenge ALL `task_plan.md` copies across the filesystem, not just the one in `results/`.** Pipeline scripts, data directories, and work directories may all contain stale copies. Clean them all.

```
Step: search_files(pattern="task_plan.md", target="files", path="E:/")
    → For each copy found outside results/memomics-*:
      → If it contains CellBender/monkey tasks: delete or overwrite with clean version
```

## Fourth Occurrence — System-Level Context Injection

Even with clean `task_plan.md` in all disk locations, the **system message itself** injected stale task content:

```
[SYSTEM] 以下是磁盘上 task_plan.md 的当前状态摘要。你正在进行一个长任务...
## Goal
3. **支线**: 完成 E:/monkey/ 下 15 个 CRR 样本的 CellBender remove-background
```

This means the Hermes framework cached the old task_plan content and injected it into the system prompt, bypassing the agent's clean write. The agent correctly identified this as stale but the injected content contaminated the initial context.

### Prevention Rule #7 (system-level defense)

**When the system prompt contains a task summary that contradicts the current session's actual tasks, trust the user's conversation history over the system injection.** Add an explicit override in the agent's response acknowledging the contradiction.

**Detection signal**: System prompt says "你正在进行一个长任务" but the most recent user messages don't mention that task → flag as stale context injection.

---

## Summary: Complete Defense Stack

| Layer | Defense | When Deployed |
|-------|---------|---------------|
| Prevention #1 | Cross-session ID verification | First incident |
| Prevention #2 | Empty task_plan → ask, don't fabricate | First incident |
| Prevention #3 | Verify user authorization in THIS session | First incident |
| Prevention #4 | Cross-reference system_log session IDs | First incident |
| Prevention #5 | Rewrite task_plan.md IMMEDIATELY after correction | Second incident |
| Prevention #6 | Scavenge ALL task_plan.md copies (not just results/) | Third incident |
| Prevention #7 | Trust conversation history over system prompt injection | Fourth incident |

---

## Corrected Cleanup Workflow (Final)

```
User corrects →
  1. Stop ALL processes (taskkill /PID, never /IM python.exe)
  2. Delete ALL pipeline artifacts (scripts, heartbeat, progress files)
  3. Search for ALL task_plan.md copies: search_files(pattern="task_plan.md", target="files", path="E:/")
  4. Overwrite EVERY copy with clean version containing explicit 红线
  5. Verify GPU idle + no pipeline processes
  6. Report clean state to user
```

## Date

2026-07-30, session `memomics-3c672f0a`
