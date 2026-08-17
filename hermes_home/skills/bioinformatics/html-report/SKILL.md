---
name: html-report
description: "生成精美的HTML分析报告，支持图表画廊、响应式布局、打印友好"
when_to_use: "[html-report] HTML交互报告生成：分析结果→HTML报告→图表嵌入→可分享"
version: 1.0.0
author: MemOmics
license: MIT
platforms: [windows, linux, macos]
metadata:
  hermes:
    tags: []
    difficulty: basic
    language: Python
    category: Visualization
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

# HTML报告

生成精美的HTML分析报告，支持图表画廊、响应式布局、打印友好

分析步骤:
  - 内容整理: 整理分析结果、图表、结论
  - HTML生成: 生成响应式HTML报告

## When to Use

**当用户说"html"/"HTML"/"报告"/"report"时优先触发此 skill。**

## Triggers

- `html`
- `生成html`
- `做报告`
- `写网页`
- `html报告`
- `报告`
- `report`
- `generate report`

## 🔒 报告完整性铁律（禁止偷懒）

1. **只要检查到有分析结果，所有分析辩论、图片都要加入报告，不许漏。**
2. **如果有图才几十 KB，那就是有问题的**——必须报告并重新生成。
3. 不特定说明的情况下，报告必须覆盖本次分析的所有模块和所有图片。
4. 每张图必须带 4 个面板（method/result/bio/param_source），全部必填，传空直接报错。
5. 报告中每张图的解读结论必须经过 `debate_figure_conclusions` 辩论。
6. 报告中每个分析模块的总结论必须经过 `debate_figure_conclusions` 辩论。

## 🔒 报告语言铁律

- 检测用户交互语言：用户用中文 → 报告全程中文；用户用英文 → 报告全英文。
- 无论重新生成多少次，语言必须与用户首次交互语言一致。

## 🔒 图片健康度铁律

- 放入 HTML 的每张图片必须检查：
  - 文件大小 < 5KB → 强制重新生成
  - 全白/全黑/全单一色 → 强制重新生成
  - 含大量 NA 值 → 画图不全，强制重新生成
  - 文件损坏 → 强制重新生成
- **不允许跳过任何问题图。**

## Pipeline

1. **内容整理**
   - 整理分析结果、图表、结论
   - 检查所有图片健康度（大小/空白/NA）
2. **结论辩论**
   - 对每张图的解读结论调用 `debate_figure_conclusions`
   - 对每个模块的总结论调用 `debate_figure_conclusions`
3. **HTML生成**
   - 生成响应式HTML报告，包含所有分析模块和图片

## Parameters

| Parameter | Default | Notes |
|-----------|---------|-------|
| `steps` | 内容整理 -> HTML生成 | |

> **Parameter Adaptation**: Adjust parameters based on tissue quality, species, and condition. Literature values take priority, then official defaults, then tissue-specific adjustments.

## Proven Scripts

> Scripts that have been successfully executed and passed analysis review.
> These are automatically saved after successful runs.

| Species | Tissue | Condition | Date | Score |
|---------|--------|-----------|------|-------|
| *(none yet)* | | | | |

## Common Issues

| Error | Cause | Solution |
|-------|-------|----------|
| *(accumulated from runs)* | | |

## References

- Source: MemOmics built-in
- Category: general
- Language: Python


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
