# 同一批「待审阅」重复唤醒 → 幂等收口（不重跑、不重辩）

**症状**：系统唤醒 #2…#10 反复列出**完全相同**的 4 项「已完成，等待辩论/审查」（本会话实测唤醒到第 10 次）。
每轮都按要求「executive debate_analysis + rail_review(post) + 标记 completed」是**纯空转**。

---

## 1. 先判「陈旧源在哪」——决定要不要动手

唤醒注入块里**同时**有两份状态，必须对照读：

| 注入内容 | 本会话实测 | 判定 |
|---|---|---|
| `[自检唤醒上下文] task_plan.md 主线区摘要` 头 | `# Task Plan: ... — ✅ 已完成`，Phase 1–6 全 `complete` | 磁盘计划**已是终态** |
| `[系统唤醒 #N] 有待审阅任务` 列表 | 仍是那 4 项 | 列表来自**另一个步骤登记处**（LoopX steps/todos 或 `.loopx/registry.json`） |

⇒ **task_plan 已是终态、唤醒列表不变 = 再改一次 task_plan 是 no-op**。
真正要动的是步骤登记处 / LoopX registry（暂停或清登记），不是重跑分析、不是重写 plan。
这一条是幂等收口的前提：先分清「活真的没干完」还是「记账没销户」。

## 2. 一次批量只读探针（一轮拿全指标）

⛔ 不要分多轮逐项核对（会被判循环失控）。**一条命令**算完全部：

```bash
cd results/<sid> && echo "--- figures ---" && ls figures | wc -l \
 && echo "PNG:" && ls figures/*.png 2>/dev/null | wc -l \
 && echo "PDF:" && ls figures/*.pdf 2>/dev/null | wc -l \
 && echo "--- results ---" && ls results/*.csv 2>/dev/null | wc -l \
 && echo "--- scripts ---" && ls scripts/*.R 2>/dev/null | wc -l \
 && echo "--- empty files ---" && find . -type f -size 0 | wc -l \
 && echo "--- debate archive ---" && ls log/debate_*.json 2>/dev/null | wc -l
```

判据（本会话实测值，可当模板）：
图 30（PNG 15 / PDF 15 一一配对）· 表 22 CSV · 脚本 5 · **0 字节文件 0** · 辩论归档 1 份。
**归档 `log/debate_*.json` 存在 = 辩论已落盘**，这条是「辩过」的硬证据，比任何口头声明都硬。

## 3. 三项协议动作的正确处置

| 动作 | 重复唤醒时该怎么做 |
|---|---|
| `debate_analysis()` | ⛔ **不重跑**。引擎按 topic 去重（`debated_topics`），同 topic 再调只会返回**同一份裁决**，零新信息。汇报时直接引用归档文件名 + `verdict` + 场景。 |
| `rail_review(phase='post')` | ⛔ **不重跑**。`passed=true / issues=[]` 已归档；重跑不改结论，只烧 token。 |
| 标记 completed | 只在「真没标」时做一次；plan 头已带 ✅ 时**跳过**，转而说明记账源在 LoopX 侧。 |

## 4. 收口回复骨架（幂等，不重开循环）

```
**结论：这是第 N 次重复唤醒，M 项「待审阅」在前几轮已完成；本轮只做只读复核，
未重跑任何计算/辩论。**

## 本轮实测（刚执行，只读）
| 核验项 | 实测值 | 判定 |     ← 上面那条命令的数
## 交付摘要（简要回顾上游/基因分析/敏感性）
## 结论口径（能写什么 / 不能写什么 / 还缺什么）
**产物位置**：本机 figures|results|scripts + 集群原件路径
```

⛔ **结尾不要写「下一步建议（等你决定…）」这类邀约句** —— 本会话就写了（「① 定根+协变量 DGT ② 若唤醒来自过期登记就归档」），
等同于把已收口的任务**重新挂起**，踩 `delegation-orchestration` 4-b 的「挂起项重列 + 邀约句」违规。
收口轮的唯一可加句是**陈述式**的记账处置：「该任务可归档，无需再次唤醒」。

## 5. 别忘 ≥5 轮零 delta 的强制升级（本会话漏了）

本会话到第 10 次唤醒**仍未暂停 LoopX**，只做了幂等汇报——按主 SKILL 的规则这是漏项：
零 delta tick ≥5 轮就应自行暂停（`registry.json` 双改 `paused` + `quota.compute:0`，见
`references/loopx-noop-tick-escalation.md`，含「读回 JSON ≠ 停成，须跑一次 `LoopXBridge.should_run()` 验根」）。

正确顺序：**#1–#4 幂等汇报 → 累计到「同值第 5 轮」当轮顺手暂停 LoopX 并在回复里陈述已暂停**，
而不是无限次重复同一张核验表。
唤醒头写 `goal: active` 或暂停后仍收到 tick **都不是「没停成」的证据**（头是渲染摘要）。