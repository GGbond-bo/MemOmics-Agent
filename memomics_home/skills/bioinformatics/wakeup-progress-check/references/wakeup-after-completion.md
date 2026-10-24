# 唤醒可能晚于任务完成（2026-10-21 实测）

> ⚠️ 本 skill 的 SKILL.md 已达 ~100.3K 字符（写入上限 100K），**SKILL.md 补丁会被拒**。
> 新经验先落 `references/`，SKILL.md 瘦身后再加指针。

**现象**：任务已完成、已汇报、产物已落盘并核验过，`[系统唤醒 #0]` 仍会进来一轮，
指示「读 task_plan → 看产出 → 继续下一个待办」。若照字面再跑一轮核验（重读 task_plan、
重 ls 产出、再跑回读脚本），平台判定「工具调用循环」并插队强制干预：
> 【系统循环检测·强制干预】… 若任务产物已生成，直接视为完成，**禁止再做任何验证/检查动作** …

**判据（一轮只读，够用就停）**

| 看什么 | 判据 | 结论 |
|--------|------|------|
| `task_plan.md` 主线 | 全 `[x]` + 各 Phase `**Status:** complete` | 终态（权威） |
| `.task_state.json` | `armed` / `rounds_started` / `reason` | 仅旁证，**不单独判活** |
| 产出目录 | 产物 mtime = 上轮汇报时间 | 无新 delta |

⚠️ 唤醒头的 `goal: active` / `todos: none` 是**注入的渲染摘要**，不是任务未完成的证据；
`.task_state.json` 的 `armed:true` 由「用户消息 → 新任务」置位，同样不代表有活干。

**动作**：终态 → **引用上轮已在案的核验数字**（回复里的实证表 / QA csv），不要为"再确认一次"
重跑；确需新证据只跑一次并落文件。收到强制干预 → 停手，2–3 句给结论（已完成/失败/卡死 + 产物路径），
本轮不再发工具调用。

完整案例（含 `skill_evolution` 必须传 `skill_name`、回读核验假阴性、read-before-write 门禁）→
`platform-execution-pitfalls/references/post-delivery-verification-discipline.md`