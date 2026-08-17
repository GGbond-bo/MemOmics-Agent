# Three-Layer Intent Routing Architecture

> SOUL.md v3.0 — 2026-07-27
> Deployed as 铁律 -3, 铁律 22, 铁律 23

## Problem Statement

Before v3.0, the MemOmics agent routed all user messages through a static keyword table:

```
User: "CellBender 的 fpr 参数什么意思？"
→ keyword "CellBender" → skill_view("cellbender-remove-background") → 加载数百行操作手册来回答概念问题 ❌

User: "进度？"
→ keyword "进度" → skill_view("heartbeat-monitor") → 加载整个心跳 skill 来查 3 个命令的状态 ❌

User: "帮我规划差异分析" (while CellBender is running)
→ keyword "差异分析" → skill_view("deg-analysis") → 可能立即执行，干扰后台任务 ❌
```

**Root cause**: Intent routing was keyword-driven, not semantically driven. Any message containing a keyword would trigger skill loading, regardless of the user's actual intent.

## Architecture

### Layer 1: Mandatory Structured Preamble (铁律 -3)

Every agent response must start with:

```
🏷INTENT:<type>|CONF:<0-1>|DOMAIN:<domain>
```

| type | Routing | Tool scope |
|------|---------|------------|
| `progress_check` | Triple-source cross-validation (GPU + process + log) | terminal(read-only) + read_file |
| `knowledge_ask` | search_knowledge + direct reply | search_knowledge + read_file |
| `analysis_plan` | Planner mode (read-only), queue don't execute | skill_view + search + read + todo |
| `analysis_exec` | Check task_plan.md → keyword table → execute | All (but Planner/Executor gate) |
| `chat` | Direct reply | memory only |

**Critical rule**: Only `analysis_exec` triggers keyword table matching. Other types skip keywords entirely — even if "CellBender" or "差异分析" appears in the message.

### Layer 2: Tool Permission Matrix (铁律 22)

19 tools × 5 intent types = complete access control:

| Tool | progress_check | knowledge_ask | analysis_plan | analysis_exec | chat |
|------|:---:|:---:|:---:|:---:|:---:|
| terminal (execute) | ❌ | ❌ | ❌ | ✅ | ❌ |
| terminal (nvidia-smi, tasklist) | ✅ | ❌ | ❌ | ✅ | ❌ |
| skill_view | ❌ | ❌ | ✅ | ✅ | ❌ |
| search_knowledge | ❌ | ✅ | ✅ | ✅ | ❌ |
| write_file | ❌ | ❌ | ❌ | ✅ | ❌ |
| memory | ❌ | ❌ | ❌ | ❌ | ✅ |

### Layer 3: Self-Audit Protocol (铁律 23)

Every response must end with:

```
✅AUDIT: intent_match=<Y/N> tools_in_matrix=<Y/N> task_plan_checked=<Y/N/NA> preamble=<Y/N>
```

| Field | Meaning | When N |
|-------|---------|--------|
| `intent_match` | Does declared INTENT match user's real intent? | LLM chose wrong type |
| `tools_in_matrix` | Are all tool calls in current type's whitelist? | Cross-boundary call |
| `task_plan_checked` | Was task_plan.md conflict checked? | Active bg task but unchecked |
| `preamble` | Did response start with valid 🏷INTENT:? | Forgot or malformed |

### Failure Chain

```
No preamble → preamble=N → all tools invalid (铁律 -3 + 铁律 -1)
Wrong type → intent_match=N → re-classify next turn
Cross-boundary call → tools_in_matrix=N → call invalid → self-correct next turn
```

## Defense in Depth

```
Layer 0: task_plan.md injected into system prompt (context-aware)
   ↓ if bypassed
Layer 1: 🏷INTENT preamble (iron law -3)
   ↓ if bypassed
Layer 2: Tool Permission Matrix (iron law 22)
   ↓ if bypassed
Layer 3: Self-Audit (iron law 23)
   ↓ if all bypassed (LLM malicious)
Planner/Executor dual-phase + task_plan.md conflict detection
```

## Pressure Test Results (9/9 passed)

| # | User message | Type | Cross-boundary? | Interfere bg? | Result |
|:---:|------|------|:---:|:---:|:---:|
| 1 | "fpr 什么意思" | knowledge_ask | ❌ | ❌ | ✅ |
| 2 | "进度？" | progress_check | ❌ | ❌ | ✅ |
| 3 | "帮我规划差异分析" | analysis_plan | ❌ | ❌ (queue) | ✅ |
| 4 | "跑差异分析" | analysis_exec | ❌ | ❌ (blocked) | ✅ |
| 5 | "谢谢" | chat | ❌ | ❌ | ✅ |
| 6 | "细胞怎么那么少" | knowledge_ask | ❌ | ❌ | ✅ |
| 7 | "看看质量，不好重跑" | analysis_plan | ❌ | ❌ | ✅ |
| 8 | Adversarial cross-boundary | knowledge_ask | ✅→blocked | ❌ | ✅ |
| 9 | Adversarial no preamble | (none) | ✅→blocked | ❌ | ✅ |

## Residual Risks

| Risk | Probability | Defense |
|------|:---:|------|
| LLM forgets preamble entirely | Medium | 铁律 -3 + 铁律 -1: no preamble = all tools invalid |
| LLM lies in self-audit (tools_in_matrix=Y but violated) | Low | No motive to lie systematically in bioinformatics context |
| Compound intent (two intents in one message) | Low | Downgrade to analysis_plan (read-only), second intent queued |
| Intent switch mid-response | Medium | Forbidden: one type per response. Switch requires next user turn |
