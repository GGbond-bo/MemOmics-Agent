# Batch Task Plan Hygiene — Wake-Up Check Bloat Management

## Problem

During long-running batch tasks (40 samples × 15-20 min each = 10-20h), automated
wake-up checks write a full status block to `task_plan.md` every ~2-5 minutes.
After 30+ checks, the file grows from ~50 lines of actionable task info to 
400+ lines of mostly redundant status dumps. The Environment table, Phase status,
Decisions, and Errors sections get buried.

## When to Trim

| Signal | Action |
|--------|--------|
| task_plan.md > 15 wake-up entries | Trim to latest 5 + one summary line |
| task_plan.md > 300 lines | Trim to latest 3 + summary |
| task_plan.md > 20 KB | Trim to latest 3 + summary |

## How to Collapse

Replace old wake-up entries with a single collapsed line:

```markdown
## ✅ 唤醒 #1–#25 摘要（已折叠）
- #1–#5: 20:00–21:00, hc26→hc40→hc212191, 34→36/40, 正常推进
- #6–#15: 21:00–23:00, hc35→hc9→hc73, 36→39/40, hc73 页文件压力重试2次后成功
- #16–#25: 23:00–01:00, 最后1个样本 hc78, 39→40/40, 全部完成
```

Keep only the latest 3-5 full-format wake-up entries for forensic value.

## What to Keep in Every Entry (Minimal Format)

Each wake-up entry must include, at minimum:

```markdown
## ✅ 唤醒 #N（HH:MM）
- PID: {pid}, 样本: {sample_id}, 阶段: P1/P2/P3, 进度: XX%
- 磁盘: {done}/40
- 剩余: {list}
- cron: {status}
- 结论: {干预/不干预}
```

Drop: ArchRLogs verbatim template output, internal log line transcripts,
duplicate environment info, and re-stated decisions already in the Decisions table.

## Anti-Pattern: Re-stating Core Rules

The task_plan.md is for task-specific state (Environment probes, Phase progress,
Decisions, Errors). Core rules (three-source verification, rail_review, debate)
belong in SOUL.md iron laws and skill SKILL.md — never copy them into task_plan.md.
