---
name: deep-research
description: "13-agent深度研究团队，系统性文献检索+综述+PRISMA"
when_to_use: "[deep-research] 13-agent深度研究团队，系统性文献检索+综述+PRISMA"
version: 1.1.0
author: MemOmics
license: MIT
platforms: [windows, linux, macos]
metadata:
  hermes:
    tags: [deep-research, literature-review, systematic-review, patent-search, 文献综述, 研究设计, 专利调研]
    difficulty: advanced
    language: Python
    category: Literature
prerequisites:
  r_packages: []
  python_packages: []
---

# 深度研究

13-agent深度研究团队，系统性文献检索+综述+PRISMA。支持方法专利 prior-art 调研。

适用场景: 深度文献研究, 系统性综述, 方法专利调研, 专利空白分析

难度: advanced

触发提示: "深度调研" / "系统调研" / "专利调研" / "prior art" / "方法专利" / "可专利性"

别名: 深度研究, 文献综述, 系统性回顾, 专利调研

## When to Use

适用于:
- 深度文献研究, 系统性综述
- 方法专利/软著 prior-art 调研 (跨物种比较、组学方法、可代替性评估)
- 专利空白分析 (从文献格局推断专利机会)
- 毕业/课题相关的系统性 method landscape 调研

## 方法专利调研流程

详见 references/patent-method-research.md。

核心策略:
1. **Round 1 (6-8 并行)**: search_knowledge + search_papers_by_context + 多角度 search_papers — 同时发出
2. **Round 2**: download_pdf(top-5) + search_papers(refined)
3. **Round 3**: 结构化报告 (优先级分层 + 空白分析 + 可视化总结)

专利 API 不可达时的回退: 走"文献→专利空白推断"路线 — 从论文格局识别未覆盖的方法专利机会。

## Support Files
- `references/patent-method-research.md` — 生信方法专利 prior-art 调研完整方法论
- `scripts/run.py` — 执行脚本

## Proven Scripts

| Species | Tissue | Condition | Date | Score |
|---------|--------|-----------|------|-------|
| *(none yet)* | | | | |

## Common Issues

| Error | Cause | Solution |
|-------|-------|----------|
| 专利数据库 API 全部不可达 | Google Patents/Espacenet/WIPO 限制服务器访问 | 走文献→专利空白推断路线；给用户手动检索策略 |
| Nature 系列 PDF 下载失败 | Cloudflare 反爬虫 | bioRxiv PDF 通常可下载；告知用户手动获取 |
| *(accumulated from runs)* | | |

## References

- Source: MemOmics built-in
- Category: literature
- Language: Python


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
- 参数选择有多个合理选项时
- 结果可能受方法选择影响时
- 生物结论需要验证可靠性时
- QC 阈值不确定时

### 不触发场景
- 参数有明确知识库推荐且无争议时
- 纯计算步骤（如保存文件、读取数据）
