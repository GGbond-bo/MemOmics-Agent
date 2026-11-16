# 「重复唤醒」：待审阅列表里的任务其实早已完成（2026-11-16 实测）

## 场景

系统唤醒 / LoopX tick 里带一段「⏰ 有待审阅任务！以下步骤已完成，等待辩论/审查」，
列出 4 项（官方上游 / 轨迹图 / 官方基因分析 / 产物回收），并要求
「① 检查产出 ② debate_analysis ③ rail_review(post) ④ 通过→标 completed」。

实际情况：这些**同一个会话早前就全做完了** —— 辩论在 2.5 小时前已归档、`rail_review(post)` 已
`passed=true`、`task_plan.md` 里对应 Phase 全是 `complete`。
唤醒的列表是**注入的历史快照**，不是新增待办。

## 三种做法，只有一种对

| 做法 | 后果 |
|---|---|
| ❌ 直接复述上轮结论「都已完成」 | 没有本轮证据，读者无法判断是不是照抄；一旦中间有文件被删就撒谎了 |
| ❌ 老实按唤醒要求重跑辩论 + 重跑全套产物 | 几小时代价；辩论引擎按 topic 去重，重发只会拿回同一份裁决；重跑还可能覆盖已核对过的产物 |
| ✅ **只读磁盘重核验 + 明说这是重复唤醒 + 表格列实测值 + 引用归档裁决** | 分钟级，有本轮硬证据，结论可复核 |

## 标准动作（逐条都可直接照抄）

1. **先读 `task_plan.md` 的 Phase 状态**，把唤醒列的 N 项**逐项映射**到已完成的 Phase 上
   （唤醒说"官方上游"→ Phase 2；"轨迹与伪时间图"→ Phase 3 …）。
   只写「都做完了」等于没回应；映射表才证明覆盖完整。
2. **一条只读命令做磁盘实测**，取这几类硬指标：
   - 图成对性：`ls figures/*.png | wc -l` 与 `ls figures/*.pdf | wc -l` 必须相等
   - 表数量：`ls results/*.csv | wc -l`
   - 脚本数量：`ls scripts/*.R | wc -l`
   - 空产物：`find figures results -type f -size 0 | wc -l` 必须是 0
   - 辩论归档：`ls -1 log/debate_*.json`
   - 临时件残留：`ls .heartbeat_stop PROGRESS.md alerts.json 2>/dev/null | wc -l` 应为 0
3. **裁决从归档文件里读，不要凭记忆复述**：
   ```python
   d = json.load(open('log/debate_<ts>_<hash>.json', encoding='utf-8'))
   for k in ['topic','scenario','verdict','confidence','level']: ...
   ```
   实测可拿到 `verdict=modify` / `confidence=medium` / `scenario.stats_design`（含裁判身份与 7 条 rubric）。
   引用文件里的字段，比记得的结论更抗质疑。
4. **顺带核对「裁决要求补的分析是否都已落盘」**（本会话是 5 项敏感性 + 一份结论分级表），
   逐项给文件名或数值 —— 这是"辩论不是走过场"的唯一证据。
5. **汇报里把口径再钉一遍**：什么可以写成事实、什么禁止写成生物学结论。
   跨唤醒容易遗忘，每次复述一遍最省事（本会话：早/晚端是算法方向不是分化起点，root5 ρ=−0.969 反转，
   主轴与核糖体 ρ=0.826）。
6. 收尾按门禁顺序：`skill_evolution(record_run)` → `rail_review(post)`。
   注意 `record_run` 参数名是 `skill_name`（不是 `skill`），见
   `platform-execution-pitfalls/references/skill-evolution-param-names.md`；
   只读清点脚本的 post 审查会报 `figure_count: 0`，但 `passed` 仍为 `true`，别据此重跑出图。

## 判据小结

**"重复唤醒"成立的三个同时条件**：① `task_plan.md` 相应 Phase 全 `complete`；
② 辩论归档文件存在且 topic 与本议题一致；③ `rail_review(post)` 有 `passed=true` 记录。
三者齐 → 只核验不重跑。任一缺失 → 才按正常流程补做。