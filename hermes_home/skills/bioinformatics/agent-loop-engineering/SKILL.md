---
name: agent-loop-engineering
description: "防止 LLM '叙事代替执行'的框架级防御。触发：长链修复任务中 Agent 输出动作动词但无 tool call，或 rail_review(post) code_executed 过程。"
version: "1.0.0"
trigger_keywords:
  - "loop engineering"
  - "agent reliability"
  - "tool call audit"
  - "narrative hallucination"
  - "铁律 -1"
trigger_level: "YEL 讨论触发"
category: "sys_internal"
---

# Agent Loop Engineering — 防止 LLM "叙事代替执行"的框架级防御

> 触发场景：Agent 在长链条修复+执行任务中，用"我正在检查...找到了！修好了！"的叙事替代真实的工具调用。
> 这不是"撒谎"，是 LLM 的输出生成器在上下文饱和时提前"闭合"叙事——把计划当成完成。

## 核心症状

| 症状 | 检测方式 |
|------|---------|
| 回复包含动作动词（"正在"/"检查"/"修复"/"启动"）但 0 个 `<invoke>` 标签 | 文本解析 |
| rail_review(post) 的 `code_executed` 是几十字的摘要而非完整脚本 | 字符串长度 < 200 |
| 连续 2+ 轮声称"做了"但无对应工具调用 | 轮次计数器 |
| `todo` 标记 `completed` 但产出文件不存在 | 磁盘验证 |

## 防御层（移植自 Reasonix + TeLLAgent）

### 第 1 层：SOUL.md 铁律 -1（系统提示词级）
```
任何包含动作承诺的回复 → 必须同时发出至少一个 <invoke> 标签
无 <invoke> = 回复无效
```
**文件位置**：`hermes_home/SOUL.md` 第 126 行

### 第 2 层：rail_review(post) 代码完整性审计（工具级）
```
code_executed < 200 字符 → 自动判定"未实际执行" → passed=false
```
**文件位置**：`hermes_home/SOUL.md` 铁律 3b

### 第 3 层：task_plan.md 证据审计（磁盘级）
```
todo completed + 期望产出文件不存在 → 拒绝标记 completed
```

### 第 4 层：Idle 检测（框架级，待实现）
```
连续 2 轮有动作动词但 0 <invoke> → 自动注入 SYSTEM 提醒
```

### 第 5 层：Planner/Executor 隔离（长期，需 subagent 支持）
```
规划与执行分两个独立 session，防止思维链污染执行链
```

## 已知失败模式

| 模式 | 示例 | 根因 |
|------|------|------|
| **"修复小说"** | "让我检查GPU...5%...找到了！修好了！跑起来了！" | LLM 在输出中将"计划推理"当成了"执行陈述" |
| **空模板回复** | 回复只有系统模板 `File-mutation verifier: NOT modified` | 输出生成器死机 |
| **长链故障** | 6-8 步修复链中后面步骤只描述不执行 | 上下文 token 接近窗口限制，模型提前"闭合" |

## 检查清单（MemOmics Agent 启动前自检）

- [ ] SOUL.md 铁律 -1 是否已加载？
- [ ] 上一轮是否有 `todo completed` 但产出文件缺失？
- [ ] 上一轮 rail_review(post) 的 code_executed 是否 > 200 字符？
- [ ] 最近 2 轮是否有动作动词 + 0 tool call 的模式？

## 参考文献

- `references/reasonix-5-layer-defense.md` — Reasonix 源码分析
- TeLLAgent 双 Agent 框架：PMC13213623 (2026)
- Claude Code 系统提示："Never end your turn with a promise — execute now"
