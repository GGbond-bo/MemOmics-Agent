---
name: academic-research
description: "综合学术研究技能：实验方案设计、文献检索、研究规划"
when_to_use: "[academic-research] 综合学术研究技能：实验方案设计、文献检索、研究规划"
version: 1.0.0
author: MemOmics
license: MIT
platforms: [windows, linux, macos]
metadata:
  hermes:
    tags: [research, experiment, design, 实验设计, 方案, 研究设计]
    difficulty: advanced
    language: Python
    category: Literature
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

# 学术研究设计

综合学术研究技能：实验方案设计、文献检索、研究规划

适用场景: 实验方案设计, 研究规划, 文献综述

难度: advanced

触发提示: "帮我设计实验方案"

别名: 实验方案, 研究设计, experiment design, 研究方案

## When to Use

适用于: 实验方案设计, 研究规划, 文献综述

## 执行模板 — 研究方案生成

当用户请求生成研究方案时，必须按以下模板输出：

```
## 研究方案: {species} {tissue} {direction}
### 背景与假说
- 生物学问题:
- 已有数据:
- 科学假说:

### 文献依据
| 文献(作者+年份,DOI) | 方法 | 关键发现 | 来源 |
|---------------------|------|----------|------|
| ... | ... | ... | [KB]/[PMID] |

### 分析方法
1. **[KB]** Seurat v4.0.2 → SCTransform → QC (已在本知识库 Nikopoulou 2023 中验证)
2. **[KB]** Harmony v1.0 → 批次校正
3. **[PubMed]** cell-cell communication → CellChat v2 (PMID:33950716)
... (每个方法标注来源)

### 图表策略
- Figure 1: UMAP + 标记基因表达
- Figure 2: ...

### 可执行待办
调用 memomics_pipeline(action='todos', selected_modules=[...])
```

## ⚠️ 知识库引用规则（Iron Law #7）

1. **必须**调 `search_knowledge(species, tissue, direction)` 加载本地KB论文
2. KB中的论文推荐**优先级最高**：版本号 → KB版本，方法链 → KB已验证流程
3. KB来源标注 **[KB]**，PubMed来源标注 **[PMID:xxx]**
4. 方案中推荐的工具如果与KB冲突 → 优先KB中的版本号
5. 如果KB中某篇论文的方法链与用户研究高度相关 → 在方案中引用并说明"可复现性"

## Loop Gate — 方案质量检查

交付前必须通过以下检查：
- [ ] search_knowledge 是否已调用？KB内容是否注入方案？
- [ ] 方案中的工具/版本号是否标注了来源 ([KB] / [PMID])？
- [ ] 是否有 ≥2 个方法推荐来自KB论文？
- [ ] 方案是否包含可执行待办？

全部 ✅ → 交付。有 ❌ → 补充缺失步骤。

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
