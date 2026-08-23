# MemOmics 执行链路修复与记忆治理规划

> 2026-08-14 · 依据三路代码调查（说而不做断链 / 长任务执行器全景 / 记忆系统现状）
> 状态：**规划稿，待用户确认后分批实施**

---

## 一、问题 1：说而不做检测到，为什么没有激活 agent 重新执行？

### 诊断结论（代码证据链）

检测器（server.py:8400-8423）**只做两件事：写标记 + 给前端发一条 info 提示**。真正的重执行依赖一条脆弱链：

```
finally(8466) → _schedule_self_check → pop(_urgent_wakeup) → _wakeup(3s) → _trigger_agent_turn → agent.run_conversation
```

断链点（按致命度排序）：

| # | 断点 | 位置 | 后果 |
|---|---|---|---|
| 1 | `_force_tool_check` 是**死标记** | 只写不读（仅 8423 一处写入） | "强制调用工具"纯属 UI 文案，从未实现 |
| 2 | `_urgent_wakeup` 在 pop 前有 **6 个静默 early-return** | 813/823/860/869/889/903 | 命中任一闸门 → 标记被吞，不唤醒 |
| 3 | `_wakeup` 的 921 行早退无重排 | `if running_agent: return` | 3 秒窗口内用户发新消息 → 唤醒永久消失 |
| 4 | `_trigger_agent_turn` 的 `if not agent: return` | 1050-1051 | session["agent"] 为 None 时静默失败 |
| 5 | 全程 `except: pass` | 976/1076 等多处 | 任何异常无日志、无重试、无告警 |

**最短答案**：不存在强制的重执行路径——一切希望寄托在 finally 的间接调度上，而该路径有 6+ 个静默断点，`_force_tool_check` 从未被消费。

### 修复路线（P0，半天）

1. **直连重执行**：说而不做命中时，不写 `_urgent_wakeup` 走间接链，而是**直接 `asyncio.create_task(_trigger_agent_turn(session, 强制指令消息))`**（绕过自检六闸门）
2. **唤醒重排**：`_wakeup` 早退时，在 finally 重新 `_schedule_self_check(urgent=True)`
3. **实现或删除 `_force_tool_check`**：实现方式——强制指令消息注入 `"⛔ 强制工具调用：本轮必须先调用工具产出，禁止纯文本回复"` 并验证本轮确有 tool_call，无则再次重执行（上限 2 次，复用 `_saying_wakeup_n`）
4. **紧急标记保护**：六闸门的 early-return 前先检查 `_urgent_wakeup`，urgent 时跳过闸门
5. **静默失败改造**：关键链上的 `except: pass` 全部加 `logger.warning` + 状态上报前端

---

## 二、问题 2：长任务后台用什么执行器？为什么出这么多问题？

### 诊断结论：没有统一执行器，是三层自治结构

```
真正执行   = OS 脱离进程（agent 写的 bash 脚本 + Rscript）
            platform_runtime.spawn_detached / nohup + CREATE_NEW_PROCESS_GROUP
裁决层     = LoopX（loopx_bridge.should_run：只判"该不该继续唤醒"）
闹钟层     = server 自检 _schedule_self_check + 心跳 _heartbeat_loop（唤醒 agent 来检查）
保镖层     = guardian.sh(v5) / monitor_serial.sh / watchdog_v3 / task_guardian.py（保脚本活着）
```

### 出问题的根因（架构缺陷，不是补丁能救）

1. **三层用文件当 API 互相猜状态**：task_plan.md（文本状态机）、monitor.log、alerts.json、.heartbeat_stop——无事务边界、无单一所有权，每层各自误判
2. **状态载体错误**：task_plan.md 文本当状态机 → "无 in_progress Phase"字样锁死完成判定（已有 3 次补丁记录）
3. **会话内存态重启即丢** → 重启后任务状态全失，靠"播种自检"猜补，又误判已完成任务
4. **补丁叠加**：batch/ 目录存 run_serial.sh v1/v2/v3 + watchdog v2/v3 + guardian v5 共 10+ 脚本；单实例锁修了三遍（PID 文件→mkdir 锁→再加 PID 锁）
5. **terminal(background=True) 路径已被实战证伪**：进程树绑定 Hermes 会话生命周期，会话回收→级联 kill（skill 文档有实测记录）

### 修复路线

**P1（统一记录簿，2 天）**：LoopX 从"裁判"升级为**唯一 job 记录簿**——所有长任务必须先 `LoopXBridge.register_job()`（goal 幂等注册已有），job 状态（running/done/failed/progress/eta）只写 LoopX 的 job store；server 自检/心跳**只读 LoopX 状态**，不再猜文件；bash 脚本层保留但启动/停止都登记。

**P2（机器可读状态，1 天）**：task_plan.md 头部加 YAML frontmatter 状态区（`status: running|done|paused` + `job_id` + `progress_pct`），文本区只给人看；`_task_plan_active` 改读 frontmatter，杜绝文本词法猜测。

**P3（脚本收敛，1 天）**：把 run_serial/watchdog/monitor/guardian 的 v1/v2/v3 收敛为单一 `batch/run_batch.sh`（内含单实例锁、停滞重启、心跳写 LoopX job store），旧脚本归档。

---

## 三、问题 3：记忆治理（USER.md / MEMORY.md 分层 + 打分 + 外置 + 索引）

### 现状（实测数据）

| 项目 | 现状 |
|---|---|
| MEMORY.md | 15.2 KB（~75 行 / ~70 条），agent 笔记（环境坑/工具 bug/项目事实） |
| USER.md | 19.4 KB（~117 行 / ~110 条），用户偏好与铁律 |
| 硬限制 | `memory_char_limit: 10000`（config.yaml:24-25），超限拒写并逼当轮手动 consolidate |
| 注入 | **每轮全量注入全文**（memory_tool.py:674-690 无截断、无 RAG、无分层） |
| 治理 | 无自动压缩、无归档、无重要性分层、无索引 |
| 已有基础设施 | memory_store.db facts（trust_score / retrieval_count / helpful_count / FTS5 / HRR 向量）；session assets 表；knowledge_base；error_memory |

### 设计：三层记忆金字塔

```
┌─────────────────────────────────────────────────┐
│ L1 核心层（注入 system prompt，≤ 8K+6K 字符）      │
│   高重要性 + 高使用 + 用户 pin 的条目               │
│   MEMORY.md（agent 笔记）/ USER.md（用户铁律）      │
├─────────────────────────────────────────────────┤
│ L2 外置层（memory_store.db facts 表，已有）        │
│   中低分条目下沉到这里，保留全文                    │
│   按查询检索注入（prefetch ≤5 条，已有机制）        │
│   索引：facts_fts(FTS5) + hrr_vector + 新 importance │
├─────────────────────────────────────────────────┤
│ L3 归档层（hermes_home/memories/archive/）         │
│   180 天未用或 score<0.3，移出全部注入链            │
│   永不删除（用户要求"一直保留"）                    │
│   索引文件 memories/index.json                    │
└─────────────────────────────────────────────────┘
```

### 打分模型（用户要求：使用程度 + 重要性）

```
score = 0.5 × importance + 0.35 × usage + 0.15 × pinned

importance（写入时评定，LLM 自评 + 来源加成）:
  用户明确强调/纠正沉淀        = 0.9
  环境坑/工具 bug（可复用）    = 0.7
  项目事实/默认参数            = 0.5
  一次性/临时信息              = 0.3

usage（使用程度，0-1）:
  recall_n：条目被检索命中+注入的次数（facts.retrieval_count 已有）
  usage = min(1, recall_n / 5)   ← 5 次命中即满
  时间衰减：90 天未用 ×0.8，180 天未用 ×0.5

pinned（用户强调位）:
  pinned=1 时 score 最低保底 0.85 → 永不降级
  （"用户强调的一直保留"的机制化保证）
```

### 层间流转规则

| 事件 | 动作 |
|---|---|
| score ≥ 0.7 且 usage ≥ 0.4 | 晋级/保持 L1（写入 MEMORY.md 或保留） |
| score < 0.5 或 90 天未用 | L1 → L2（下沉 memory_store.db facts，MEMORY.md 留一行索引 `[L2→fact:123]`） |
| score < 0.3 或 180 天未用（且非 pinned） | L2 → L3 归档（archive/YYYY-MM.md + index.json 条目） |
| pinned=1 | 永远留在 L1，无论 score（仅用户可取消） |

### 索引设计

`hermes_home/memories/index.json`（L2/L3 条目统一索引）：

```json
{
  "version": 1,
  "entries": {
    "fact:123": {
      "layer": "L2",
      "source": "MEMORY.md",
      "keywords": ["ggplot2", "字体", "报错"],
      "importance": 0.7, "usage": 0.6, "pinned": false,
      "score": 0.62, "last_used": "2026-08-14", "created": "2026-08-02",
      "locator": "memory_store.db#facts#123"
    }
  },
  "stats": {"L1": 45, "L2": 60, "L3": 120}
}
```

### 治理循环（谁、何时、怎么跑）

| 触发器 | 执行者 | 动作 |
|---|---|---|
| 每次 `memory` 工具 add | 工具层 | 条目写 L1 时自动带 `[imp:0.x][pinned:y/n]` 元数据；超限触发 consolidate |
| 每 10 次 add 或每日启动 | `memory_governor`（server 后台任务，新增） | 全量打分 → 按流转规则执行 L1↔L2↔L3 迁移 → 重写 index.json → 前端记忆面板显示层级 |
| 会话中检索 | holographic prefetch（已有） | L2 按查询注入 ≤5 条；L1 全量注入 |
| 用户说"记住 XXX" | 沉淀为 USER.md 条目 | 强制 pinned=1 |

### 兼容与风险

- **不破坏现有**：MEMORY.md/USER.md 格式保持 `§` 分隔（ENTRY_DELIMITER），条目头部加元数据行，旧条目默认 importance=0.5、usage=0（自然下沉，渐进治理）
- **压缩免疫保留**：L1 仍受 context_compressor 的"记忆不压缩"保护；L2 只注入检索命中
- **注入预算**：L1 全量（≤8K+6K 字符）+ L2 检索 ≤5 条 + L3 零注入 → system prompt 净降 ~40%
- **数据不丢**：三层全保留原文，只是注入层级不同；pinned 永不降级

### 实施顺序（记忆治理，2-3 天）

1. **D1**：memory 工具条目元数据化（imp/pinned 写入格式）+ `memories/index.json` 初始化扫描
2. **D1**：`memory_governor` 后台任务（打分 + 流转 + 索引重写 + 前端面板展示层级）
3. **D2**：holographic facts 表加 `importance/pinned` 字段 + L2 下沉写入路径 + MEMORY.md 索引行渲染
4. **D2**：归档器（L3 迁移 + archive 文件 + 防误删锁）
5. **D3**：铁律更新（SOUL.md：记忆治理规则 + 用户 pin 语法"记住这个，很重要"）+ 回归

---

## 四、总体优先级与工作量

| 批次 | 内容 | 工作量 | 价值 |
|---|---|---|---|
| **A（先做）** | 说而不做断链 5 项修复 | 半天 | 直接消除"检测了不执行" |
| **B** | 记忆治理 D1-D3 | 2-3 天 | 用户明确要求，容量危机临近（55-75%） |
| **C** | 长任务 P1 LoopX 记录簿 | 2 天 | 根治"老是出问题" |
| **D** | 长任务 P2/P3 状态机+脚本收敛 | 2 天 | 复杂度消肿 |

> 建议顺序 A → B → C → D：A 是正确性底线（检测必须真的重执行），B 是用户点名需求，C/D 是长期治理。
