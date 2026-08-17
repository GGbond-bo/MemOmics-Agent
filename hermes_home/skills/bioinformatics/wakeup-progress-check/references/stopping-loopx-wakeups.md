# LoopX 唤醒停止方法（用户要求停掉唤醒时）

**触发**：用户说"为什么你一直在唤醒呢？任务都结束了，还在唤醒"、"把唤醒停掉"、"不要唤醒我了"（2026-08-12 用户确认选项 A 实测）。

## 根因（唤醒从哪来）

- 唤醒**不是用户消息，是 LoopX 调度器自动发的**：
  - `memomics/loopx_bridge.py`（MemOmics 自研调度层）+ `hermes_home/runtime/jobs.json`（任务状态，2604 行历史）
  - `hermes_home/cron/ticker_heartbeat`（框架 ticker，每分钟 tick 一次）
- 机制：`LoopX 每分钟 tick → 读 registry.json / goal 状态 → 发现 goal: active（未标记完成）→ 自动插入 [系统唤醒 #N] 消息 → Agent 收到后按唤醒规程检查 → 汇报"没新任务" → 循环`
- **问题根源**：任务 P0-P6 全完成了，但 goal 状态从未被标记为 inactive/complete → LoopX 认为任务还在进行 → 持续唤醒。

## 修复步骤（2026-08-12 实测成功）

### 1. 找到状态文件

```bash
# registry.json 是 LoopX goal 状态的真实来源（不是 .loopx/ACTIVE_GOAL_STATE.md，后者不存在）
ls results/<session_id>/.loopx/registry.json
# 备份
cp results/<session_id>/.loopx/registry.json results/<session_id>/.loopx/registry.json.bak_$(date +%H%M%S)
```

### 2. 修改状态（Python 安全改 JSON）

```python
import json
p = 'results/<session_id>/.loopx/registry.json'
with open(p, encoding='utf-8') as f:
    reg = json.load(f)
for g in reg['goals']:
    if g['id'] == '<session_id>':
        g['quota']['compute'] = 0                      # ← 关键！触发官方 paused 机制
        g['quota']['spent_slots'] = g['quota'].get('allowed_slots', 500)
        g['status'] = 'paused'
        g['adapter']['status'] = 'paused'
with open(p, 'w', encoding='utf-8') as f:
    json.dump(reg, f, ensure_ascii=False, indent=1)
```

> ⚠️ **只改 status=cleared 不够**（2026-08-12 实测）：`should_run()` 里 `waiting` 状态被 bridge 的 Codex 兼容逻辑"忽略并放行"（`state in ("waiting","skip","no_run","connected_without_run") → should=True`），cleared 被解析成无活跃 goal → 仍会被放行。
> ✅ **正确组合 = `status=paused` + `quota.compute=0`**（quota.py: `compute quota is 0; automatic agent turns are paused` 是官方硬停机制）。

### 3. 验证已停

```python
import sys
sys.path.insert(0, '.')
from memomics.loopx_bridge import _load_loopx, LoopXBridge
b = LoopXBridge('<session_id>', 'MEMOMICS_HOME/results/<session_id>', user_online=True)
d = b.should_run()
print(d)
# 期望: {'should_run': False, 'state': 'paused', 'decision': 'skip',
#        'reason': 'compute quota is 0; automatic agent turns are paused', ...}
```

`should_run=False` = 唤醒已停 ✅

### 4. 记录 + 记忆

- task_plan.md 追加"唤醒停止记录"（根因 + 修复 + 备份路径）
- memory 保存"LoopX 唤醒停止方法"（恢复方法 = compute 改回 >0 + status 改回 active）

## 恢复方法（以后要重新跑任务时）

把 `registry.json` 里 `quota.compute` 改回 `>0`、`status` 改回 `active` 即可（备份文件在 `registry.json.bak_*`）。

## 用户偏好教训（2026-08-12 用户直接批评）

1. **用户没问进度时，不要长篇汇报进度** — 用户原话："我有问你这些进度吗？你一直回我这些干什么呢？我不是问你代码吗？"唤醒来了就机械汇报 = 噪音。
2. **终态唤醒应极简** — 一行"无新任务"即可，不要每次铺开 P0-P6 列表。
3. **用户问代码/具体问题时，直接回答问题** — 不要被唤醒流程带偏。
