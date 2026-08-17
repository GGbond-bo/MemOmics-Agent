---
name: find-skill
description: "智能搜索可用技能：当用户需要某个分析功能但不确定有没有现成技能时，自动搜索239个内置技能+外部蓝图，找到最匹配的并推荐安装。也支持用户说'有没有XXX的技能'时触发。"
when_to_use: "[find-skill] 智能搜索可用技能：当用户需要某个分析功能但不确定有没有现成技能时，自动搜索239个内置技能+外部蓝图，找到最匹配的并推荐安装。也支持用户说'有没有XXX的技能'时触发。"
version: 1.0.0
author: MemOmics
license: MIT
platforms: [windows, linux, macos]
metadata:
  hermes:
    tags: [meta, skill, search, find, 技能, 搜索技能, 有没有, 元技能]
    difficulty: beginner
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

# 技能搜索 (find-skill)

智能搜索可用技能：当用户需要某个分析功能但不确定有没有现成技能时，自动搜索239个内置技能+外部蓝图，找到最匹配的并推荐安装。

## 适用场景

- 用户说"有没有XXX的技能/方法/分析"时，**自动触发**
- 用户在做分析时需要某个特定方法，但不确定技能库里有没有
- 用户想浏览某个研究方向有哪些可用技能
- agent 在执行任务时发现需要某个未安装的技能

## 触发条件

当用户消息包含以下模式时自动触发：
- "有没有XXX的技能"
- "找XXX技能"
- "需要XXX技能"
- "有没有XXX分析"
- "什么技能可以用"
- "find skill" / "skill search"

## 工作流程

1. **搜索**：调用 `search_skills` 工具，输入用户关键词，搜索内置239个技能 + 外部蓝图
2. **展示**：将搜索结果按相关度排序，展示给用户
3. **推荐**：如果找到高度匹配的技能，用 `ask_choice` 让用户选择是否安装
4. **安装**：用户确认后调用 `install_skill` 自动安装

## 使用示例

### 用户主动触发
```
用户: 有没有做细胞通讯的技能？
→ find-skill 搜索 "细胞通讯"
→ 找到: cellchat, nichenet, liana 等3个技能
→ 推荐最匹配的 cellchat，询问是否安装
→ 用户确认 → 自动安装
```

### Agent 内部触发
```
用户: 帮我做轨迹分析
→ agent 执行分析时需要 monocle3
→ find-skill 搜索 "monocle3"
→ 找到: monocle3 技能
→ 自动安装并继续分析
```

## 与其他技能的链路

- **chains_to**: `install_skill`, `search_skills`, `skill_hub`
- 安装完成后，技能自动注册到 agent 的可用技能列表

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
