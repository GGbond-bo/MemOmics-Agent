# Guardian No-Op Technique — Neutralize Zombie Cron-Launched Scripts

> **Session**: memomics-1135ed52 (2026-08-07)
> **Problem**: guardian.sh was being re-launched every 60 seconds by the Hermes server.py (PID 55412) cron ticker. schtasks queries returned nothing, no cron job entries found, no way to stop the source. Killing guardian processes worked for one cycle but they kept respawning at :02 each minute.

## Root Cause

The Hermes webui/server.py (PID 55412 — the platform's own process that cannot be killed) had a built-in cron ticker that was executing `batch/guardian.sh` every minute. This is the **platform's own scheduler**, not a user-created cron job, so there's no `cronjob remove` or `schtasks delete` that can stop it.

## The Technique

**When you can't stop the scheduler, replace the target script with a harmless no-op stub.**

Instead of fighting the scheduler:
1. Kill all running instances of the target script
2. Overwrite the script file with a no-op stub that just logs "DISABLED" and exits 0
3. The scheduler keeps calling it every minute — but it does nothing except append a harmless log line

### Before (harmful guardian.sh):
```bash
#!/bin/bash
# guardian.sh — checks if watchdog_v2 is alive, respawns if dead
if watchdog_v2_dead; then
  echo "guardian: watchdog_v2 已死，重新拉起" >> monitor.log
  nohup bash batch/watchdog_v2.sh &
fi
```

### After (no-op stub):
```bash
#!/bin/bash
# guardian.sh — DISABLED by watchdog_v3 migration 2026-08-07 19:24
# watchdog_v3 now handles all monitoring. This stub is left to prevent
# the Hermes server from crashing when it tries to run the old guardian.
echo "[$(date '+%F %T')] guardian: DISABLED (watchdog_v3 active)" >> batch/monitor.log
exit 0
```

## Why This Works

- The scheduler (Hermes cron ticker) is a **platform-level process** — killing it kills the entire web UI session
- The scheduler fires every ~60 seconds and runs the script path it was told to run
- If the file at that path is a no-op, the scheduler "succeeds" every cycle without side effects
- The log line provides audit trail that the scheduler is still alive but deliberately inert

## When to Use

| Scenario | Use no-op? |
|----------|:---:|
| Cron/schtasks you **can** find and delete | ❌ — just delete the task |
| Scheduler is a platform process you can't kill | ✅ — no-op the target |
| Scheduler source unknown but script keeps running | ✅ — no-op the target, then investigate |
| Multiple scripts in a chain (guardian → watchdog → run_serial) | ✅ — no-op the topmost one you can't disable |

## Pitfalls

1. **Don't delete the script file** — if the scheduler can't find the file, it may log errors, crash, or try alternative paths. A no-op stub that exits 0 is safer than a missing file.
2. **Leave a comment explaining why** — future sessions (or other agents) may see the stub and try to "fix" it back to the original. The comment header prevents that.
3. **Verify with monitor.log** — after deploying the no-op, check that the scheduler logs show "DISABLED" instead of the old behavior.
