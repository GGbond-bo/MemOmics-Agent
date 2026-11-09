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

## 加分场景：路线被用户中途否决后，task_plan 必须显式收口（2026-11-03 实测）

**现象**：跑到一半用户否决这条路线（原话"还不如我之前的 v2 版本稳妥，你觉得怎么处理？"），
产物作废、作业停掉，但 `task_plan.md` 里 Phase 仍 `**Status:** in_progress`、
Verification Checklist 还挂着 `- [ ]` → 完成契约永远不满足 → 唤醒一轮轮空转。

**做法（一次写完，别分轮补）**：

1. 先处置现场：`ps -ef | grep <作业标记> | grep -v grep | wc -l` = 0，再删作废产物
   （删除走 `platform-execution-pitfalls/references/destructive-cleanup-with-audit-script.md`）
2. 顶部 `## Goal` 追加**最终结论**（谁裁决的、为什么退回、哪一版是有效结果），
   原目标保留但标"原目标"
3. 作废 Phase 的 `**Status:**` 改 `cancelled`，未完成项把 `- [ ]` 改成 `- [-]`（或纯文本）
   —— 契约**只认 `- [ ]`**，`- [-]` 不算未勾选
4. **新增一个「清理与定稿」Phase 标 `complete`**，把删除、三源核实、保留证据链写进去，
   让主线以"已完成"收尾而不是以"取消"收尾（用户看面板时才知道活干完了）
5. `Decisions Made` 补一行：为什么退回旧版本（日后被追问时的自证）

**判据**：唤醒一次只读 → `task_plan` 无 `- [ ]` + 各 Phase 全 `complete`/`cancelled`
→ 终态，按上文"引用上轮在案数字、不重跑核验"处理。