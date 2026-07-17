---
name: paper-summary
description: "深度AI文献解读：全文提取→结构化总结(15字段)→图表提取→报告生成"
when_to_use: "[paper-summary] 已有PDF或论文链接，需生成结构化的论文摘要（背景/方法/结果/结论），快速了解论文内容"
version: 1.1.0
author: MemOmics
license: MIT
platforms: [windows, linux, macos]
metadata:
  hermes:
    tags: []
    difficulty: basic
    language: Python
    category: General Utility
prerequisites:
  r_packages: []
  python_packages: []
---

### 规则N: 运行记录只是参考，不能跳过审查
- skill_evolution(action="query_logs") 返回的历史运行日志仅供参数参考
- 即使有 quality_score=9.0 的历史日志，仍必须执行 rail_review(pre)、debate_analysis、rail_review(post)
- 禁止因"之前跑过"而跳过任何审查步骤
- 禁止直接用历史日志里的脚本运行而不经本次审查
- 运行日志是"参考"不是"免审凭证"

---

# AI文献总结

深度AI文献解读：全文提取→结构化总结(15字段)→图表提取→报告生成

分析步骤:
  - 全文提取: markitdown提取全文→fitz兜底→Docling兜底
  - AI总结: LLM 结构化总结 15 字段（见 `references/15_fields_template.md`）
  - 图表提取: fitz提取Figure+Caption
  - 报告生成: 生成暗色主题 HTML 报告（≥12KB，含 TOC 导航 + 数据面板）

## When to Use

当你需要 AI文献总结 时触发

## Triggers

- `总结论文`
- `解读文献`
- `论文总结`
- `ai总结`
- `文献解读`
- `解读`
- `解读论文`
- `论文解读`
- `全文解读`
- `精读`
- `讲一下这篇`
- `帮我看看这篇`
- `summarize paper`
- `interpret paper`
- `interpret`

## Pipeline

1. **全文提取**
   - markitdown提取全文→fitz兜底→Docling兜底
2. **AI总结**
   - LLM 结构化总结 15 字段（见 `references/15_fields_template.md`）
3. **图表提取**
   - fitz 提取 Figure+Caption（注意：主图常为矢量嵌入，提取多为辅助图；不影响交付）
4. **报告生成**
   - 生成暗色主题 HTML 报告（≥12KB，含 TOC 导航 + 数据面板）

## 15 字段清单

| # | 字段 | 内容要点 |
|---|------|----------|
| 1 | 标题 | 完整标题 + 中文译名 |
| 2 | 作者 | 全部作者 + 通讯标注 |
| 3 | 期刊/年份 | 期刊名、年份、PMID |
| 4 | DOI/数据 | DOI + GEO 等数据库 accession |
| 5 | 关键词 | 8-10 个关键词 |
| 6 | 研究背景 | 科学问题 + 填补空白 |
| 7 | 研究假设 | 2-4 条核心假设 |
| 8 | 实验设计 | 受试者/方案/采样/技术 (表格) |
| 9 | 方法管线 | 步骤→工具→参数 (表格) |
| 10 | 核心发现 | 5-8 条核心发现 |
| 11 | 图表解读 | Figure→内容→结论 (表格) |
| 12 | 讨论 | 关键讨论点 |
| 13 | 局限性 | 局限→影响 (表格) |
| 14 | 意义 | 科学/转化意义 |
| 15 | 与你的关联 | 与用户研究的对比 + 下一步建议 |

> 完整模板和格式约定见 `references/15_fields_template.md`

## Parameters

| Parameter | Default | Notes |
|-----------|---------|-------|
| `steps` | 全文提取 -> AI总结 -> 图表提取 -> 报告生成 | |

> **Parameter Adaptation**: Adjust parameters based on tissue quality, species, and condition. Literature values take priority, then official defaults, then tissue-specific adjustments.

## Proven Scripts

> Scripts that have been successfully executed and passed analysis review.
> These are automatically saved after successful runs.

| Species | Tissue | Condition | Date | Score |
|---------|--------|-----------|------|-------|
| human | skeletal_muscle | exercise | 2026-07-18 | 9/10 |

## Common Issues

| Error | Cause | Solution |
|-------|-------|----------|
| rail_review(post) 误报 "代码过短" | 本 skill 是知识工作管线（LLM 编排多工具），非纯脚本执行；rail_review 按代码长度检测会误报 | 忽略此误报——检查实际交付物（HTML ≥12KB + 15 字段齐全）即可通过 |
| 主图提取为空白/小图 | PDF 主图常为矢量嵌入，fitz 提取的是位图渲染残片或辅助图标 | 正常现象，不影响交付；图表解读部分由 LLM 从全文 Figure Legends 直接提取 |

## References

- `references/15_fields_template.md` — 15 字段完整模板 + 格式约定 + 已验证案例
- Source: MemOmics built-in
- Category: general
- Language: Python

---

## 🗣️ 辩论机制（debate_analysis）

本 skill 在执行后，如果涉及**参数选择、方法决策、结果判断**等不确定环节，**必须**调用 debate_analysis 工具进行多角色辩论。

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
- **本 skill 属于知识工作管线，通常不涉及参数选择争议——可跳过 debate**
