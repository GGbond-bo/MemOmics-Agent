# Case Study: `taskkill /F /IM python.exe` — Agent Kills Itself

## Incident (2026-07-25, CellBender pipeline)

User: "你杀 watchdog，你怎么把 MemOmics 的程序也杀了？你能不能带点脑子？"

Agent had used `taskkill /F /IM python.exe` to clean up zombie CellBender processes. This killed:
- The watchdog (intended)
- The heartbeat monitor
- **MemOmics Hermes Agent itself** (unintended)

## Root Cause

Agent was in "batch cleanup" mindset and chose the broadest filter (`/IM python.exe` = "kill all python") instead of precise PID targeting.

## Correct Protocol

```
# 1. List all python processes
tasklist /FI "IMAGENAME eq python.exe"

# 2. Identify target PIDs (watchdog, zombie CellBender, old heartbeat)
# 3. Kill ONLY those PIDs
taskkill /F /PID 19976

# NEVER:
taskkill /F /IM python.exe  ← KILLS MEMOMICS
```

## Prevention Rule

⛔ **`taskkill /F /IM python.exe` is permanently banned.** Any process cleanup must use `/PID <pid>` with individually verified PIDs. This rule is encoded in:
- `cellbender-batch-pipeline` skill, cleanup checklist step 2
- `cellbender-batch-pipeline` pitfall 28
