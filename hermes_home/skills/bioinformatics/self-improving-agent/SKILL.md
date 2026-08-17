---
name: self-improving-agent
description: "自进化能力：分析成功后自动沉淀经验为新技能；分析失败后自动学习错误模式避免重复犯错；根据使用频率自动优化参数。包括技能沉淀、错误学习、参数进化三大子系统。"
when_to_use: "[self-improving-agent] 自进化能力：分析成功后自动沉淀经验为新技能；分析失败后自动学习错误模式避免重复犯错；根据使用频率自动优化参数。包括技能沉淀、错误学习、参数进化三大子系统。"
version: 1.0.0
author: MemOmics
license: MIT
platforms: [windows, linux, macos]
metadata:
  hermes:
    tags: [meta, evolution, self-improving, learn, 自进化, 自我改进, 经验沉淀, 技能生成, 元技能]
    difficulty: advanced
    language: Python
    category: General Utility
prerequisites:
  r_packages: []
  python_packages: []
### 规则N: 运行记录只是参考，不能跳过审查
- skill_evolution(action="query_logs") 返回的历史运行日志仅供参数参考
- 即使有 quality_score=9.0 的历史日志，仍必须执行 rail_review(pre)、debate_analysis、rail_review(post)
- 禁止因"之前跑过"而跳过任何审查步骤
- 禁止直接用历史日志里的脚本运行而不经本次审查
- 运行日志是"参考"不是"免审凭证"

---

# 自进化代理 (self-improving-agent)

MemOmics 的自进化能力：分析成功后自动沉淀经验为新技能；分析失败后自动学习错误模式避免重复犯错；根据使用频率自动优化参数。

## 三大子系统

### 1. 技能沉淀 (Skill Sedimentation)

**触发条件**：分析审查通过 (overall_score ≥ 0.7)

**工作流程**：
1. 分析完成后，review.post 评估质量
2. 如果通过，调用 `save_proven_code()` 将成功脚本保存到 `skill/scripts/proven/`
3. 参数记录到 `skill/scripts/proven/params.json`
4. 下次相同分析可直接复用 proven script

**存储位置**：`memory_omics/skills/built_in/<skill_id>/scripts/`

### 2. 错误学习 (Error Learning)

**触发条件**：工具报错 或 审查失败

**工作流程**：
1. 捕获错误信息（错误类型、工具名、上下文）
2. `ErrorMemory.record()` 记录到 `errors.jsonl`
3. 分析根因（如"包未安装"、"参数超出范围"、"数据格式不对"）
4. 下次执行前检查 `ErrorMemory`，如果有匹配的错误记录，自动应用修复方案

**存储位置**：`knowledge_base/error_memory/errors.jsonl`

**当前数据**：30 条错误记录

### 3. 参数进化 (Parameter Evolution)

**触发条件**：审查通过

**工作流程**：
1. 每次分析成功后，关键参数（如 `resolution`、`mt_percent_threshold`、`npcs`）被记录
2. `EvolutionEngine` 用 EWMA (指数加权移动平均) 更新参数推荐值
3. 参数质量评分随时间衰减（避免老经验过度影响）
4. 下次相同分析类型，推荐使用进化后的参数

**存储位置**：`data/evolution_log/state.json`

**当前数据**：7 条进化历史

## 使用示例

### 查看自进化状态
```
用户: 自进化状态
→ 展示: 已沉淀技能数、错误记忆条数、参数进化次数
→ 展示: 最近5条进化记录
```

### 手动触发技能沉淀
```
用户: 把刚才的分析沉淀成技能
→ 从最后一次成功的分析中提取脚本+参数
→ 调用 create_skill 保存为新技能
→ 下次可直接复用
```

### 从错误中学习
```
用户: 为什么老是重复犯同样的错误？
→ 查询 ErrorMemory 中的历史错误
→ 展示: 最近10条错误+根因+修复方案
→ 说明: 这些错误模式已记录，下次执行前会自动检查
```

### 参数优化
```
用户: 优化一下聚类参数
→ 查询 EvolutionEngine 中 clustering 参数组的历史
→ 展示: resolution 从0.3→0.5的演化轨迹
→ 推荐最优值并说明理由
```

## 自动触发场景

### 分析成功后
```
分析完成 → review.post 通过 →
  ├─ save_proven_code() → 保存成功脚本
  ├─ EvolutionEngine.propose_edit() → 更新参数
  └─ 通知用户: "✅ 本次分析已沉淀为技能，参数已优化"
```

### 分析失败后
```
工具报错 → ErrorMemory.record() →
  ├─ 记录错误类型+根因+修复方案
  ├─ 下次执行前自动检查相同错误模式
  └─ 通知用户: "⚠️ 错误已记录，下次会自动避免"
```

### 运行任务时需要未安装的技能
```
agent 需要某技能 → find-skill 搜索 →
  ├─ 找到 → install_skill 自动安装 → 继续任务
  └─ 没找到 → 通知用户 + 尝试用 LLM 生成新技能
```

## 与其他技能的链路

- **chains_to**: `find-skill`（搜索需要的技能）、`install_skill`（安装技能）
- 依赖: `EvolutionEngine`、`ErrorMemory`、`SkillManager`、`PackageInstaller`

## Proven Scripts

| Species | Tissue | Condition | Date | Score |
|---------|--------|-----------|------|-------|
| *(none yet)* | | | | |


---

## 🗣️ 辩论机制（debate_analysis）

本 skill 在执行后，如果涉及**参数选择、方法决策、结果判断**等不确定环节，**必须**调用  工具进行多角色辩论。

### 辩论规则
- **正方 3 位专业编辑**（各自独立，互相看不到）：生物学编辑 / 统计学编辑 / 生信编辑
- **反方 4 位专业编辑**（各自独立，互相看不到，也看不到正方）：生物学编辑 / 统计学编辑 / 生信编辑 / 历史经验编辑
- **裁判**：看到所有 7 方论点后给出裁决 + 置信度（高/中/低）
- **上下文隔离**：每个编辑是独立的 LLM API 调用，messages 只包含自己的 prompt
- **分科知识库**：生物学编辑用 biology_kb / 统计学编辑用 statistics_kb / 生信编辑用 bioinfo_kb / 历史经验编辑用 history_errors
- **辩论结果自动归档**到 results/.../log/debate_*.json

### 触发场景
- 参数选择有多个合理选项时（如分辨率 0.4 vs 0.6 vs 0.8）
- 结果可能受方法选择影响时（如不同注释方法给出不同结果）
- 生物结论需要验证可靠性时
- QC 阈值不确定时（如 MT% 阈值 10% vs 15% vs 20%）

### 不触发场景
- 参数有明确知识库推荐且无争议时
- 纯计算步骤（如保存文件、读取数据）
