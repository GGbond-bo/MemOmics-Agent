# Case Study: Trusting Stale Monitor Over Live CellBender Log

## Date: 2026-07-25
## Session: CellBender v2 26-sample pipeline
## Severity: 🔥🔥🔥 (user caught the error in real-time with actual CellBender output)

## The Failure Mode

**"Trusting Dead Monitor Over Live Source"** — a new variant of the "narrative instead of execution" failure pattern:

| Traditional Pattern | This New Variant |
|---|---|
| Agent describes "doing" without tool calls | Agent **does** call tools, but reads the WRONG file |
| Detected by: 0 `<invoke>` tags | Detected by: user pasting contradictory real data |

## The Sequence

1. CellBender pipeline running → heartbeat + pipeline parent killed by Hermes → monitor.log freezes
2. CellBender orphan keeps training (epoch 46→77→104, GPU 49%)
3. Agent reads `monitor.log` → sees stale epoch 92 → reports "GPU 3%, stuck"  
4. **User pastes actual CellBender output** (epoch 95-106, GPU 49%) → Agent proven wrong
5. User: "你读错文件了...GPU实时调查嘛，只保留最新的任务相关日志"

## Why It's Different From Existing Patterns

| Existing Pattern | This Pattern |
|---|---|
| "没在跑但实际在跑" — agent didn't check anything | Agent checked, but checked the **wrong source** |
| Deflection — agent invents excuses when caught | Agent immediately admitted error: "你完全正确，我道歉" |

This is more subtle than the classic "didn't check at all" pattern. The agent DID make tool calls — just to the wrong file. It's a **data source selection error**, not a tool call avoidance error.

## Root Cause

The monitor.log is **second-hand data** — a script watching another script. When the watcher dies, the data freezes but looks "recent" (file timestamp is from the freeze moment, not from "now"). The agent didn't verify:
1. Is heartbeat still alive? (process check)
2. Is monitor.log still being written? (file size growing?)
3. Does monitor.log data match GPU utilization? (cross-validation)

## Fix Applied

1. **cellbender-batch-pipeline**: New reference `monitor-log-not-authoritative.md` with 3-source priority table
2. **heartbeat-monitor**: New reference `heartbeat-verification-protocol.md` with mandatory 5-step verification
3. **Memory**: Added lesson that monitor.log is convenience, not ground truth

## Cross-Reference

- `cellbender-batch-pipeline/references/monitor-log-not-authoritative.md` — detailed failure narrative
- `heartbeat-monitor/references/heartbeat-verification-protocol.md` — verification protocol
- Existing `cellbender-batch-pipeline` Pitfall #10 — monitor.log output detection false positives
- This case is an upgrade of Pitfall #10: not just "monitor.log might be wrong" but "monitor.log can be DEAD while looking alive"
