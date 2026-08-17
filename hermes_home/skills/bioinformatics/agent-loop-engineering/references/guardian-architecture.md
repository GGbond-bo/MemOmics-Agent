# Guardian Architecture — Git Snapshot + Auto-Rollback

> Deployed 2026-07-26 | `memomics/bio_tools/guardian.py` (155 lines)

## Architecture

```
┌──────────────────────────────────────────────────┐
│                  SOUL.md Iron Law 14               │
│  "修改项目文件前必须先 guardian(action='snapshot')"  │
└──────────────────────┬───────────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────────┐
│              guardian(action, label)               │
│                                                    │
│  action='snapshot'  → git add -A && git commit    │
│  action='check'     → failure_count++ → if >=3:   │
│                       git reset --hard <commit>    │
│  action='reset'     → failure_count = 0           │
└──────────────────────┬───────────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────────┐
│           memomics/config/guardian_state.json      │
│  {                                                 │
│    consecutive_failures: 0,                        │
│    last_snapshot: { label, commit_hash, ts },      │
│    snapshot_history: [...],                        │
│    last_rollback: { commit, ts, reason }           │
│  }                                                 │
└──────────────────────────────────────────────────┘
```

## Integration Points

| Trigger | Guardian Action |
|---------|----------------|
| `write_file`/`patch` on project file | `guardian_snapshot(label)` |
| `rail_review(post)` returns `passed=false` | `guardian_check()` — increment counter |
| After 3rd consecutive failure | `guardian_check()` → `git reset --hard` |
| `rail_review(post)` returns `passed=true` | `guardian_reset_counters()` |

## State Machine

```
               ┌─────────┐
          ┌───▶│  CLEAN   │◀─── guardan_reset()
          │    │ (count=0)│     (after success)
          │    └────┬─────┘
          │         │ rail_review(post) failed
          │         ▼
          │    ┌─────────┐
          │    │  WARN1   │ (count=1)
          │    └────┬─────┘
          │         │ rail_review(post) failed again
          │         ▼
          │    ┌─────────┐
          │    │  WARN2   │ (count=2)
          │    └────┬─────┘
          │         │ rail_review(post) failed again
          │         ▼
          │    ┌─────────┐
          │    │ ROLLBACK │ (count=3 → git reset --hard → count=0)
          │    └─────────┘
          │
          └── (back to CLEAN)
```

## Code Reference

```python
# Minimal usage
from memomics.bio_tools.guardian import guardian

# Before modifying a file
guardian("snapshot", label="before-qc-fix")

# After 3rd rail_review(post) failure
result = guardian("check", failure_count=3)
# → {"action": "rollback", "commit_hash": "1f7d482c", ...}

# After successful review
guardian("reset")
```

## Verification

`hermes-verify-guardian.py` — 8/8 PASSED (2026-07-26):
1. Schema valid (snapshot/check/reset enums)
2. State reset to clean
3. Git snapshot created
4. 3 consecutive failures → auto-rollback
5. Counter zeroed after rollback
6. Manual reset works
7. State file persisted on disk
8. guardian.py survives rollback (same-commit expected)
