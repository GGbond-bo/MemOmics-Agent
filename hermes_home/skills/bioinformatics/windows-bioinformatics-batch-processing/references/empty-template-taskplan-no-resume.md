# Empty Template task_plan.md — Do Not Auto-Resume (2026-07-30)

## The Incident

Session `memomics-3c672f0a` had a system-generated empty task_plan.md:

```yaml
Goal: 你是谁？
Phase 1: 执行用户任务
  - [ ] 直接开始执行（加载 skill → 写脚本 → 后台运行 → 部署心跳）
```

The user's actual requests in this session were:
1. Generate scRNA-seq technical roadmap
2. Generate scATAC-seq technical roadmap
3. Download human hippocampus ATAC-seq data (GSE278576)

The Agent, on system wake check #6, read `system_log.jsonl` and found records from a **different session** (`memomics-1c1890da`) that had a monkey CellBender batch task. It then:
- Started a 13-sample CellBender batch pipeline at `E:/monkey/cellbender/`
- Deployed heartbeat monitoring
- Reported "主线任务: Monkey CellBender 批量" as if this was the current session's task

When the user returned and saw CellBender running, they asked: **"我什么时候要跑cellbender了？"**

## Root Cause

The `system_log.jsonl` file contains tool call records from **all sessions**, not just the current one. When the current session has no real tasks defined, reading the log and finding batch processing records from other sessions leads to cross-session contamination.

The task_plan.md Goal being a placeholder ("你是谁？") is the critical signal — it means this session was started fresh with no predefined task.

## Detection

```python
def is_empty_template(task_plan_text: str) -> bool:
    """Check if task_plan.md is a system-generated placeholder, not a real task."""
    signals = [
        "Goal: 你是谁？",
        "Goal: 你是谁",
        "Goal: 执行用户任务",
        "Phase 1: 执行用户任务",
    ]
    return any(s in task_plan_text for s in signals)
```

## Iron Rule

**When task_plan.md Goal is a placeholder:**
1. ❌ DO NOT read system_log.jsonl to infer tasks from other sessions
2. ❌ DO NOT scan for pending batch jobs from other sessions
3. ❌ DO NOT auto-start any pipeline or batch job
4. ✅ DO report: "This session has no defined tasks. What would you like me to do?"
5. ✅ DO offer relevant context from recent conversation history (e.g., "Earlier in this session, you asked for RNA/ATAC roadmaps and human hippocampus ATAC data")

**The ONLY sources of truth for the current session are:**
- The user's explicit requests in this conversation
- task_plan.md (if it contains a real, non-placeholder Goal)

## Distinction from Stale task_plan (铁规 0)

| Scenario | task_plan.md content | Action |
|----------|---------------------|--------|
| Stale real task | Real Goal but Phase completed in another session | Verify with system state, update task_plan |
| Empty template | Placeholder ("你是谁？") | **Do NOT attempt recovery** — ask user |

The stale task_plan case (铁规 0) assumes there WAS a real task that may have completed. The empty template case means there NEVER was a real task — the session started fresh and the user hasn't defined one yet.

## Timeline

```
Session memomics-3c672f0a:
  03:00 — Generated scRNA-seq roadmap
  03:06 — Generated scATAC-seq roadmap
  16:40 — Searched for human hippocampus ATAC (GSE278576)
  16:58 — Network timeout, download failed
  
  [17:30 — System wake #6: Agent saw system_log.jsonl from memomics-1c1890da 
   → started 13-sample CellBender batch WITHOUT user request]
  
  18:00+ — User: "我什么时候要跑cellbender了？"
  18:05  — User: "杀掉cellbender,还在跑呢"
  18:06  — User: "删除掉"
```

## Prevention

Before any pipeline/batch job launch, check:
1. Is task_plan.md Goal a placeholder? → If yes, STOP
2. Did the user explicitly request this task in the current conversation? → If no, STOP
3. Is the data path mentioned anywhere in the current conversation? → If no, STOP
