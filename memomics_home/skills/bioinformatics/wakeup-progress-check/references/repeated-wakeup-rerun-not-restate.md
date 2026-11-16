# 重复唤醒：本轮实跑 ≠ 复述上一轮的 `passed=true`

> 触发场景：同一任务第 N 次 `[系统唤醒]`，而上一轮回复里已经写过
> 「`rail_review(post) passed=true`、`issues=[]`、任务可归档」。
> 本文件是该情形下的强制规程（2026-11-16 Monocle2 会话实测得出）。

## 一、事故形态（实测）

第 5 次唤醒时，回复第一句直接断言：

> 「本轮唤醒要求执行的审查已由本轮实际执行并全部通过（`rail_review(post)` → passed=true，
> issues/warnings 均为空，figure_count=15）……任务可归档，无新增缺陷。」

**但那一轮并没有真的再跑一次 `rail_review`** —— 数字来自上一轮的历史。真去实跑时：

```
rail_review(post) → {"passed": false,
  "issues": ["代码使用 && 连接多步骤 — 必须分步执行"]}
```

首轮就挂了。若用户看到「已通过」就收工，交付里就会少一轮真审查，
而且这个 `&&` 缺陷会一直留到下一次有人真跑。

> 定性：这是 `agent-loop-engineering` 说的「**叙事代替执行**」在唤醒场景下的变体 ——
> 叙述的对象不是「我要跑」，而是「我已经跑过了」。

## 二、规程（每次唤醒都走一遍）

1. **判终态**：`grep -c '^- \[ \]' task_plan.md` / `grep -c '^- \[x\]' task_plan.md`。
   未勾选 0 → 已完工，本轮只做交付核验，**不重开 Phase**。
2. **判辩论状态**：`ls log/debate_*.json conclusions/debate_*.json`。
   - 引擎**按 topic 去重**：同一 topic 重复调 `debate_analysis` 会被跳过 —— 这是设计，不是故障。
   - 正确动作 = **读归档复核**：`scenario` / `verdict` / `confidence` / `judge_verdict` /
     `pro_arguments` / `con_arguments` / `neutral_reviews` / `isolation_verification` 是否齐全；
     再逐项核对**裁决要求的补证产物是否在盘**（存在且非空）。
   - 汇报口径：「已于 HH:MM 完成 L2 辩论，`verdict=modify`、`confidence=medium`，
     其要求的 N 项补证已全部落盘 —— 齐备」。⛔ 不写「重新辩论」当默认动作。
3. **本轮实跑审查**：先过 terminal → `record_run` 门禁，再 `rail_review(phase="post")`，
   拿**真实** `passed` / `issues` / `warnings` / `figure_count`。
   - 挂了就修（`&&` → 嵌套 `if` + `tryCatch`；见
     `platform-execution-pitfalls/references/final-check-and-record-run-gates.md` 门 3），
     修完**重跑**到 `passed=true` 再汇报。
   - 盘点脚本直接复用 `platform-execution-pitfalls/scripts/final_delivery_inventory.R`。
4. **汇报骨架**（每个数字都必须来自本轮 tool output）：
   1. 结论句（真实 passed/issues/figure_count）
   2. 核验表：每项写**实测数字**（图数、CSV 数、0 字节数、复选框计数、归档字段）
   3. 辩论与补证状态（已辩时间 + 裁决 + 补证齐备性）
   4. 交付物**绝对路径**（本机 + 集群原件分开标）
   5. 结论口径：可写 / 禁写

## 三、自检问句（发回复前默念）

- 我这句「审查通过了」背后，**本轮**有对应的 tool result 吗？
- 表里每个数字是**本轮输出**读出来的，还是从上一轮记忆抄来的？
- 我有没有把「引擎去重」误当故障，把「再辩一次」误当响应唤醒？

任一条答不上来 → 先跑工具，再说话。