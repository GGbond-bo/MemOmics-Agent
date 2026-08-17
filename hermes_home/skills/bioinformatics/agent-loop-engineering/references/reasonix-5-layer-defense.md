# Reasonix 5 层防御机制 — 源码级分析

> 源码阅读：`DeepSeek-Reasonix` v1.9+
> 文件：SPEC.md, COLLABORATION_MODES.md, GOAL_ENFORCEMENT.md, TOOL_CONTRACT.md, TASK_CONTRACT.md, RECOVERY.md
> 日期：2026-07-25

---

## 第 1 层：Goal 拦截 + Todo 证据审计门禁

**源码位置**：`GOAL_ENFORCEMENT.zh-CN.md`, `internal/control/controller.go`

```
Agent 声称 [goal:complete]
      ↓
系统检查：
  ① Canonical todos — 是否有未完成的 todo？
  ② Project checks — AGENTS.md 中的 verify 指令是否通过？
      ↓
任一未通过 → 拦截，提醒 agent 继续。
strict 模式：持续拦截直到 todos 全部完成。
```

**MemOmics 移植状态**：
- ✅ MemOmics 有 `todo` 工具
- ❌ 但没有**强制审计门禁** — Agent 可以同时声称"完成了"但 todos 未勾掉
- 🔧 改造方案：在 `rail_review(post)` 中增加强制检查——分析的 todos 未全部 `completed` → `passed=false`

---

## 第 2 层：Delivery Profile 的"无证据=未完成"门禁

**源码位置**：`COLLABORATION_MODES.zh-CN.md` L103-108, `TOOL_CONTRACT.zh-CN.md` L41-50

> "变更后必须复查结果、运行成功的验证命令，并用引用该命令的 `complete_step` 正式签收；不满足时拦截最终回答并自动要求继续。对明确要求实现、修复或修改的任务，**如果没有观察到真实变更，宿主会拒绝'已经完成'的纯文本声明**。"

**核心逻辑**：
```
Agent 说 "我修好了"
      ↓
Host 检查：tool_call 日志中是否有 write_file/patch/terminal 的实际执行记录？
      ↓
没有 → 拦截，拒绝 "done" 声明
有   → 检查输出文件是否存在？验证命令是否成功？
      ↓
不满足 → 拦截
满足   → 放行
```

**这是直接解决 MemOmics "撒谎"问题的框架级机制。** 如果 Agent 输出"修好了"但 Host 检查到过去 3 轮中没有任何 `patch`/`write_file`/`terminal` 调用，直接拦截回复。

**MemOmics 移植状态**：
- ⚠️ `rail_review(post)` 部分覆盖（检查文件产出）
- ❌ 但没有 tool_call 日志追踪
- 🔧 改造方案：在 `rail_review(post)` 增加 tool_call 计数检查

---

## 第 3 层：Idle 检测 + 连续无工具调用警告

**源码位置**：`GOAL_ENFORCEMENT.zh-CN.md` L8

> "连续 2 轮无工具调用时，提醒 agent 推进或说明卡点"

**MemOmics 移植状态**：
- ⚠️ Hermes 可以检测空回复（`(empty)` 系统模板）
- ❌ 但没有检测"有文字但无工具调用"的模式
- 🔧 改造方案：在 Hermes agent loop 中增加 `idle_detection`：
```
如果最近 2 轮 assistant 回复中：
  ① 包含 "let me", "I will", "正在", "让我" 等动作动词
  ② 但 0 个 <invoke> 标签
→ 不发给用户，自动追加 "⚠️ 未检测到工具调用。请直接调用工具或说明原因。"
→ 给 LLM 一次自动修正机会
```

---

## 第 4 层：双模型协作（Planner + Executor 隔离）

**源码位置**：`SPEC.zh-CN.md` §3.5

```
Planner session（低频，只读研究工具）
    → 产出简洁计划
    → 不执行任何写操作

Executor session（独立 session，完整工具面）
    → 接收计划 → 执行 → 验证
    → 两条会话互不混合
```

**为什么能防止"撒谎"**：
- Planner 的"规划思考"和 Executor 的"执行动作"在**两个独立的 provider 调用**中
- Planner 不会在"思考怎么修"的时候自行脑补"已经修好了"
- 交接点为严格的 handoff 结构，不是自由叙事

**MemOmics 现状**：
- `debate_analysis` 已经拆分了多角色（7 个独立编辑器调用）
- 但主 agent 仍是单体
- 长期：需要 Hermes 支持 subagent profile（类似 Reasonix 的 `runAs: subagent`）

---

## 第 5 层：Guardian 恢复机制（`reasonix-guard`）

**源码位置**：`RECOVERY.zh-CN.md`

核心设计：
- Config 快照 + SHA-256 校验（"修复前"状态可回滚）
- `RepairPlan` JSON 白名单机制 — AI 建议的修复只能包含白名单动作（隔离配置、恢复快照、重建派生状态），**不允许运行 shell、修改凭据、指定任意文件路径**
- 自动安全模式：5 分钟内连续 3 次启动失败 → 进入无扩展的安全模式

**对 MemOmics 的启示**：
- `rail_review(post)` 已经是一个轻量版 Guardian
- 但缺少"回滚"能力 — 如果 Agent 修脚本修坏了，无自动恢复到上一版的机制

---

## TeLLAgent 论文的补充框架（PMC13213623, 2026）

双 Agent 工具执行框架：

```
Orchestrator Agent（编排者）
    ↓ 生成 Tool Plan
Validator Agent（验证者）
    ↓ 检查 plan 是否合理 → 拦截/放行
    ↓ 验证执行结果是否与 plan 一致
```

| 机制 | 解决的问题 | MemOmics 是否有？ |
|------|-----------|------------------|
| **Tool Plan 验证** | Agent 生成了"看起来合理"但实际不能执行的 plan | ❌ 无 |
| **执行结果校验** | Agent 声称"做完了"但实际没产出 | ⚠️ `rail_review(post)` 部分覆盖 |
| **双 Agent 互为监督** | 单 Agent 的"自我合理化"偏差 | ⚠️ `debate_analysis` 部分覆盖，但不是持续监督 |
| **工具调用轨迹审计** | 无法追溯"Agent 说做了 vs 实际做了" | ❌ 无 |

---

## MemOmics 当前防御状态总览

| 层 | Reasonix 名称 | MemOmics 状态 | 差距 |
|----|-------------|-------------|------|
| 1 | Goal + Todo 审计 | `todo` 工具存在，无强制门禁 | 改 `rail_review(post)` |
| 2 | Delivery Profile | ⚠️ `rail_review(post)` 部分覆盖 | 加 tool_call 计数 |
| 3 | Idle 检测 | ❌ 无 | 改 Hermes agent loop |
| 4 | Planner/Executor | ❌ 无（单体 agent） | 需 subagent 支持 |
| 5 | Guardian 恢复 | ⚠️ 无回滚能力 | 需较大改动 |
