---
name: ppt-master
description: "AI驱动的SVG-PPT生成系统，多角色协作：策划→执行→质量检查→导出"
version: 1.0.0
author: MemOmics
license: MIT
platforms: [windows, linux, macos]
metadata:
  hermes:
    tags: [ppt, presentation, svg, slide, powerpoint, 报告]
    difficulty: intermediate
    language: Python
    category: visualization
prerequisites:
  r_packages: []
  python_packages: ["python-pptx", "Pillow", "PyMuPDF"]
---

# PPT Master

AI驱动的SVG-PPT生成系统，多角色协作：策划→执行→质量检查→导出

适用场景: 文献解读后生成PPT, 分析报告制作PPT

依赖包: python-pptx, Pillow, PyMuPDF

难度: intermediate

触发提示: "生成PPT"

别名: 做PPT, 生成PPT, PPT生成, 制作演示文稿

## When to Use

适用于: 文献解读后生成PPT, 分析报告制作PPT

## Parameters

| Parameter | Default | Notes |
|-----------|---------|-------|
| `python_packages` | python-pptx, Pillow, PyMuPDF | |

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
- Category: visualization
- Language: Python


---

## 🗣️ 辩论机制（debate_analysis）

本 skill 在执行后，如果涉及**参数选择、方法决策、结果判断**等不确定环节，**必须**调用  工具进行多角色辩论。

### 辩论规则
- **正方 3 角色**（各自独立，互相看不到）：生物学 agent / 统计学 agent / 生信 agent
- **反方 4 角色**（各自独立，互相看不到，也看不到正方）：生物学 agent / 统计学 agent / 生信 agent / 历史经验 agent
- **裁判**：看到所有 7 方论点后给出裁决 + 置信度（高/中/低）
- **上下文隔离**：每个角色是独立的 LLM API 调用，messages 只包含自己的 prompt

### 触发场景
- 参数选择有多个合理选项时（如分辨率 0.4 vs 0.6 vs 0.8）
- 结果可能受方法选择影响时（如不同注释方法给出不同结果）
- 生物结论需要验证可靠性时
- QC 阈值不确定时（如 MT% 阈值 10% vs 15% vs 20%）

### 不触发场景
- 参数有明确知识库推荐且无争议时
- 纯计算步骤（如保存文件、读取数据）
