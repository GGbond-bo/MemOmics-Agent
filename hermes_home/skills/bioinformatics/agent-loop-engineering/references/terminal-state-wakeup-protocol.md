# 终态唤醒协议（Terminal-State Wakeup Protocol）

> 来源：memomics-1c1890da 系统唤醒 #11/#16/#18 连续 4 次漏查 cronjob(list) 后固化的铁律（2026-08）。
> 本协议是 agent-loop-engineering 的执行模式防御的一部分，与 heartbeat-monitor（受保护技能）互补：
> heartbeat-monitor 管"部署心跳 + 心跳该做什么"；本协议管"Agent 被唤醒后该查什么"。

## 触发场景

系统注入唤醒消息，典型形态：

```
📊 LoopX 状态：goal: active | attention: ok | todos: none
⏰ [系统唤醒 #N] 检查主线任务进度
1. 读 task_plan.md 看当前 Phase
2. search_files 看最新产出
3. 继续执行下一个待办
```

⚠️ **唤醒 prompt 从不提查 cron**。按 prompt 顺序执行 = 必然漏查残留心跳 job。

## 唤醒三连（同一并行批次发出，不可分步）

```
同一轮 tool call 批次：
  1. read_file("{workdir}/task_plan.md")   ← 看当前 Phase + 核对 session ID
  2. search_files 看最新产出               ← 磁盘实测，禁止引用 task_plan 旧文本
  3. cronjob(action="list")                ← 与读 task_plan 同一轮并行！
```

> ⛔ cronjob(action="list") 必须与"读 task_plan"放同一并行工具调用批次（同轮一起发出，非"下一步"）。
> 顺序指令（先读 task_plan，然后"下一步"查 cron）依赖 Agent 自觉——连续 4 次证明会漏。

## 终态判定（task_plan 全部 complete + 停止标记）

- 先核对 **session ID**，防止跨 session 污染
- **Placeholder Goal 勿执行**；旧 session 任务不自动延续
- 汇报必须含 **"cron 检查"字段**：
  - 有残留 job → `cronjob(action="remove")`
  - 无残留 → 写 "无残留"
- **进度/下载数字必须磁盘实测**（dir 计数/文件大小），禁止引用 task_plan 旧文本（如 "2/40"）
- **前置数据逐样本完整性检查**：fragments 样本缺 .tbi.gz 索引 = 样本不完整（hc78 案例）——不能只数文件数量

## 跨 session 污染铁律（唤醒时最高优先级）

- BLOCKED_KEYWORDS: CellBender / Monkey / 未指令任务
- **NEVER auto-start CellBender** 无显式请求（用户愤怒 5+ 次）
- 取消 → 立即删条目 + 脚本不留炸弹
- 纠正后必须立即重写 task_plan.md（不等下次唤醒），否则下次唤醒重蹈覆辙
