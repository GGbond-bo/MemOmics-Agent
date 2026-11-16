# 唤醒源排查：会话待办清单里的陈旧条目（waiting_review / pending）

## 症状

系统唤醒反复列出**同一批**「以下步骤已完成，等待辩论/审查」的条目，每轮内容几乎逐字相同；
而 task_plan 早已全 `complete`、产出早已拉回本机核验过。

典型唤醒头：

```
⏰ [系统唤醒 #12] 有待审阅任务！
以下步骤已完成，等待辩论/审查：
  - 官方上游：estimateSizeFactors/...
  - 轨迹与伪时间图：...
请立即：1. 检查产出 2. debate_analysis() 3. rail_review(phase='post') 4. 标记 completed
```

## 根因

登记源是**本会话 todo 列表里残留的 `waiting_review` / `pending` 条目**，不是 LoopX registry，
也不是 task_plan。`todo()` 无参调用即可看到真实分布：

```json
{"summary": {"total": 12, "pending": 6, "in_progress": 0, "waiting_review": 4, "completed": 2}}
```

只要 `waiting_review + pending > 0`，调度器就会持续把这批条目当成待审阅任务唤醒，
**与计算是否真的跑完无关**。只做只读复核（数图数表、重看日志）永远治不了它。

## 判据（三条同时成立即确认）

1. task_plan 的 Phase 表全为 `**Status:** complete`，主线复选框全勾；
2. 产出已核验：文件字节数 > 0、图号 PNG+PDF 成对、无 0 字节文件；
3. `todo()` 仍有 `waiting_review` 或 `pending` 条目，且其 content 描述的工作在上述产出里有对应物。

## 处置三步

1. **先核验，再标记**（顺序不可颠倒，否则等于谎报完成）

   ```bash
   cd results/<sid>/results
   for f in a.csv b.csv c.md; do
     [ -s "$f" ] && printf 'OK   %-48s %8s B\n' "$f" "$(stat -c%s "$f")" || printf 'MISS %s\n' "$f"
   done
   cd ../figures
   for n in 08 09 10 11 12; do printf '%s: %s\n' "$n" "$(ls ${n}_* 2>/dev/null | tr '\n' ' ')"; done
   ```

2. **一次性 `todo(merge=true)` 全部标 completed**，content 里写清对应产出作为凭据
   （便于日后审计「凭什么说它做完了」）：

   ```json
   {"id": "debate_todo_1_0", "status": "completed",
    "content": "供体级伪时间汇总 + LMM ...：condition p=2.2e-3 / ICC=0.361 → donor_level_*.csv、lmm_*.csv、图 09/10"}
   ```

3. **复查 summary** 必须变成 `waiting_review: 0, pending: 0` 才算断根。

## 禁止

- ⛔ **不要第 N 次重跑 `rail_review` / `debate_analysis`**：同 topic 会被引擎去重，
  直接返回同一裁决，纯烧 token；高影响条目还会吃掉会话辩论 budget。
- ⛔ **不要未核验就标 completed**：谎言式断根比循环唤醒更糟，后续无法追溯。
- ⛔ 不要把这批条目 `cancelled` 了事——它们是**真做完**的，不是放弃的。

## 实测

Monocle2 交付后连续 **12 次**同一批唤醒：

| 轮次 | 处置 | 结果 |
|---|---|---|
| 1–11 | 每轮只做只读复核（数 figures/results、查空文件、重述结论） | 结论都对，**下一轮照旧唤醒** |
| 12 | `todo()` 读登记源 → 核验 12 个文件非空 + 图 08–12 成对 → `todo(merge=true)` 标 10 条 completed | summary 归零，**断根** |

教训：**第 3 次出现「同一批唤醒 + 结论未变」时就该去查 todo 登记源**，
而不是继续只读复核并把同一段结论再写一遍。