---
name: pdf-translate
description: "使用PDFMathTranslate(pdf2zh)进行学术论文保留排版翻译，公式/图/表格完整保留，支持Google/OpenAI/DeepSeek等24种引擎"
version: 1.0.0
author: MemOmics
license: MIT
platforms: [windows, linux, macos]
metadata:
  hermes:
    tags: [translate, pdf, 翻译, 中英文, 公式保留, 排版保留, pdf2zh, PDFMathTranslate, 文献翻译]
    difficulty: basic
    language: Python
    category: literature
prerequisites:
  r_packages: []
  python_packages: ["pdf2zh>=1.7.0"]
---

# PDF保留排版翻译

使用PDFMathTranslate(pdf2zh)进行学术论文保留排版翻译，公式/图/表格完整保留，支持Google/OpenAI/DeepSeek等24种引擎

适用场景: 学术论文翻译, 保留排版PDF翻译, 公式和图表保留翻译, 中英对照PDF生成

依赖包: pdf2zh>=1.7.0

难度: basic

触发提示: "帮我翻译这篇PDF文献"

别名: PDF翻译, 文献翻译, 中英对照, translate pdf, bilingual pdf

## When to Use

适用于: 学术论文翻译, 保留排版PDF翻译, 公式和图表保留翻译, 中英对照PDF生成

## Parameters

| Parameter | Default | Notes |
|-----------|---------|-------|
| `service` | {'type': 'string', 'default': 'google', 'description': '翻译引擎：google/bing/openai/deepseek/zhipu/deepl/azure/ollama/argos', 'required': False} | |
| `lang_in` | {'type': 'string', 'default': 'en', 'description': '源语言代码', 'required': False} | |
| `lang_out` | {'type': 'string', 'default': 'zh', 'description': '目标语言代码', 'required': False} | |
| `pages` | {'type': 'list', 'default': None, 'description': '指定翻译的页码列表(0-based)，null=全部', 'required': False} | |

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
- Category: literature
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
