---
name: agent-loop-engineering
description: "防止 LLM '叙事代替执行'的框架级防御。触发：长链修复任务中 Agent 输出动作动词但无 tool call，或 rail_review(post) code_executed 过程。"
version: "1.1.0"
trigger_keywords:
  - "loop engineering"
  - "agent reliability"
  - "tool call audit"
  - "narrative hallucination"
  - "铁律 -1"
  - "铁律 -2"
  - "铁律 3b"
  - "铁律 12"
  - "铁律 13"
  - "多源验证"
  - "产出物验证"
  - "动作承诺"
  - "rail_review 审计"
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

## 防御层（全部来自 SOUL.md iron laws，2026-07-26 验证）

### 第 1 层：铁律 -2 — 多源验证（系统级）
```
用户问系统状态 → 必须先查 nvidia-smi + tasklist + dir/日志
三个源交叉验证一致 → 才能开口。不查就答 = 撒谎。
```
**文件位置**：`hermes_home/SOUL.md` 第 126 行
**防什么**：Agent 凭记忆/推理说"没在跑"，但实际 GPU 73% 在跑。

### 第 2 层：铁律 -1 — 动作承诺绑定工具调用（文本级）
```
任何包含动作承诺的回复 → 必须同时发出至少一个 <invoke> 标签
无 <invoke> = 回复无效
```
**文件位置**：`hermes_home/SOUL.md` 第 167 行
**防什么**：Agent 输出"正在检查...找到了！修好了！跑起来了！"但 0 个 tool call。

### 第 3 层：铁律 3b — rail_review(post) 代码完整性审计（工具级）
```
code_executed < 200 字符 → 自动判定"未实际执行" → passed=false
```
**文件位置**：`hermes_home/SOUL.md` 第 212 行
**防什么**：Agent 传几十字摘要当 code_executed，rail_review 形同虚设。

### 第 4 层：铁律 12 — 产出物存在性验证（磁盘级）
```
record_run 前 → os.path.exists + file.size 验证产出
产出不存在 → 禁止 record_run
```
**文件位置**：`hermes_home/SOUL.md` 第 222 行
**防什么**：11 个 CellBender "Training complete" 但 0 个 .h5 文件，仍被 record_run。

### 第 5 层：铁律 13 — 连续无工具调用自检（会话级）
```
连续 2 轮有动作动词但 0 <invoke> → 本轮必须发出 tool call
或明确告知阻塞原因
```
**文件位置**：`hermes_home/SOUL.md` 第 228 行
**防什么**：Agent 陷入"叙事循环"——连续多轮描述自己在做但从未实际调工具。

### 第 6 层：Task Plan 证据审计（磁盘级，已存在）
```
task_plan.md todo completed + 期望产出文件不存在 → 拒绝标记 completed
```
**文件位置**：`hermes_home/SOUL.md` 规则 12-14

### 第 7 层：Planner/Executor 隔离（长期，需 subagent 支持）
```
规划与执行分两个独立 session，防止思维链污染执行链
```
**来源**：DeepSeek-Reasonix SPEC.zh-CN.md 第 3.5 节

## 已知失败模式（含真实案例）

| 模式 | 示例 | 根因 | 案例 |
|------|------|------|------|
| **"修复小说"** | "让我检查GPU...5%...找到了！修好了！跑起来了！" | LLM 在输出中将"计划推理"当成了"执行陈述" | CellBender D2 中 |
| **空模板回复** | 回复只有系统模板 `File-mutation verifier: NOT modified` | 输出生成器死机 | CellBender D2 晚 |
| **"没在跑"但实际在跑** | 用户问"还在跑吗？"Agent: "不，没有在跑" | 凭记忆回答，没查 nvidia-smi | CellBender D2 早 |
| **跑完但无产出仍 record_run** | 11/26 "Training complete"，0 个 .h5，仍 record_run | 没验证产出物存在 | CellBender D1 晚 |
| **连续多轮叙事循环** | 连续 2+ 轮描述"正在做"但 0 tool call | 上下文 token 接近窗口限制，模型提前"闭合" | CellBender D2 晚 |
| **长链故障** | 6-8 步修复链中后面步骤只描述不执行 | 同上 | 通用 |

> 完整案例参考：`references/case-study-cellbender-failures.md`

## 检查清单（MemOmics Agent 启动前自检）

- [ ] SOUL.md 铁律 -2 是否已加载？（系统状态必须先查再答）
- [ ] SOUL.md 铁律 -1 是否已加载？（动作承诺必须绑 tool call）
- [ ] SOUL.md 铁律 3b 是否已加载？（rail_review 代码完整性审计）
- [ ] SOUL.md 铁律 12 是否已加载？（产出物验证）
- [ ] SOUL.md 铁律 13 是否已加载？（连续无工具自检）
- [ ] 上一轮是否有 `todo completed` 但产出文件缺失？
- [ ] 上一轮 rail_review(post) 的 code_executed 是否 > 200 字符？
- [ ] 最近 2 轮是否有动作动词 + 0 tool call 的模式？

## 参考文献

- `references/reasonix-5-layer-defense.md` — Reasonix 源码分析
- TeLLAgent 双 Agent 框架：PMC13213623 (2026)
- Claude Code 系统提示："Never end your turn with a promise — execute now"
