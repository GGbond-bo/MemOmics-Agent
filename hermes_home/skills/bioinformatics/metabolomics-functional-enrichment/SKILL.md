---
name: metabolomics-functional-enrichment
description: "代谢组学功能富集分析：输入差异代谢物列表 → MSEA代谢物集富集 → MetPA代谢通路分析 → mummichog通路推断 → ORA过表达分析。基于 MetaboAnalystR 4.0 + KEGG + HMDB + SMPDB。"
version: 1.0.0
author: MemOmics
license: MIT
category: Metabolomics
platforms: [windows, linux, macos]
metadata:
  hermes:
    tags: [metabolomics, enrichment, MSEA, MetPA, mummichog, pathway, KEGG, HMDB, 代谢通路, 功能富集, 代谢物集富集]
    difficulty: intermediate
    language: R
    category: Metabolomics
prerequisites:
  r_packages: [MetaboAnalystR, igraph, RSQLite, KEGGgraph, fgsea, ggplot2, ggprism, plotly]
  python_packages: []
related_skills: [metabolomics-statistical-analysis, functional-enrichment, pathway-enrichment]
when_to_use: "[metabolomics-functional-enrichment] 代谢组功能富集 / 代谢通路 / MetPA / MSEA / mummichog / 代谢物通路富集 / metabolite set enrichment / metabolic pathway analysis / KEGG代谢通路 / HMDB富集"
---

## ⛔ MemOmics 强制规则（不可违反，优先级最高）

> 本 skill 已集成到 MemOmics-Agent 自进化生信分析平台。使用本 skill 前，必须先通过 skill_view 加载本文件。以下规则覆盖所有默认行为。

### 规则1: 写代码前 → 必须先 search_knowledge + skill_view
- **每个分析步骤写代码前**，必须先调 `search_knowledge(species=..., tissue=..., direction=..., query="<步骤名> 参数")`
- 知识库有匹配 → 用知识库的参数和模板
- 知识库无匹配 → 用 web 搜索文献，提取方法和参数，存入知识库
- **绝对不能跳过直接写代码**

### 规则2: 8步循环（每步必须走完整循环）
```
1. search_knowledge 查本步骤的方法和参数
2. skill_view 加载本 SKILL.md
3. check_env 检查环境（缺包自动安装）
4. rail_review(pre) 前置审查
5. 写这一步的代码
6. terminal 执行（分步执行，禁止 && 连接多步骤）
7. debate_analysis 多方辩论
8. rail_review(post) 后置审查
```

### 规则3: 代码分段执行 — 写一步跑一步
- ❌ **禁止**一次性写完全部代码用 && 连接执行
- ✅ **必须**分步

### 规则4: 关键参数多参数尝试 + 辩论
- 涉及数值参数时，**至少尝试 2-3 个值**
- 辩论格式：正方 3 位 + 反方 4 位 + 裁判编辑
- **不确定的参数就辩论**

### 规则5: 执行后审查（强化版）
- 图片检查、代码质量检查、结果合理性检查
- 通过 → `skill_evolution(action="record_run")`

### 规则N: 运行记录只是参考，不能跳过审查

### 规则6: 结果存储结构
```
results/<模块>/<方法>/
  ├── scripts/     # 分析脚本
  ├── figures/     # PNG + SVG 图表
  ├── data/        # RDS 中间数据
  └── results/     # CSV/TSV 结果表
```

### 规则7: 脚本出错/成功 → 必须调 skill_evolution（自进化）

---

# 代谢组学功能富集分析

对差异代谢物或完整 peak intensity matrix 进行功能富集分析，揭示代谢通路层面的生物学意义。

## When to Use

### ✅ 应该使用
- 有差异代谢物列表（名称或 HMDB/KEGG ID），需要看哪些通路被显著扰动
- 有完整的 peak intensity matrix（定量数据），做 MSEA 或 mummichog
- 需要代谢通路可视化（KEGG 通路图着色）
- 与 metabolomics-statistical-analysis 串联使用

### ❌ 不应该使用
- 基因/蛋白列表 → 用 functional-enrichment 或 pathway-enrichment skill
- 代谢物鉴定不确定（只有 m/z 没有名称）→ 用 mummichog（无需 Level 1 鉴定）
- 没有统计学显著代谢物 → 用 MSEA（基于全部排序列表，不硬阈值）

## Pipeline

### Method 1: ORA (过表达分析) — 最常用
- 输入：显著差异代谢物名称列表
- 数据库：KEGG、HMDB、SMPDB（MetaboAnalystR 内置 ~500,000 代谢物集）
- 超几何检验 → p-value → FDR 校正
- 输出：富集通路表 + 气泡图

### Method 2: MSEA (代谢物集富集分析) — 使用全部定量数据
- 输入：所有代谢物 × 浓度/FC 排序列表（无需硬阈值）
- 类似 GSEA：按浓度排序 → 看某通路代谢物是否集中在顶部
- 输出：富集通路 + enrichment ratio + p-value

### Method 3: MetPA (代谢通路分析) — KEGG 通路可视化
- 输入：代谢物名称（需 KEGG/HMDB ID 映射）
- 输出：通路拓扑分析 + KEGG 通路图着色
- Impact score：结合 centrality + enrichment

### Method 4: mummichog — 无需 Level 1 鉴定的通路推断
- 输入：m/z + retention time + p-value（LC-MS feature table）
- 原理：利用生物通路网络拓扑，绕过代谢物鉴定步骤
- 特别适合：非靶向代谢组学
- 数据库：KEGG 代谢网络

## Parameters

| 参数 | 默认值 | 说明 | 来源 |
|------|--------|------|------|
| `method` | `"ORA"` | 富集方法: ORA / MSEA / MetPA / mummichog | 自动选择 |
| `database` | `"KEGG"` | 通路数据库: KEGG / HMDB / SMPDB | |
| `organism` | `"hsa"` | KEGG 物种代码 (人='hsa', 鼠='mmu') | |
| `p_threshold` | `0.05` | 显著富集阈值 | |
| `mz_tolerance` | `5` | mummichog m/z 容差 (ppm) | Li et al. 2013 |
| `top_pathways` | `25` | 展示 top N 通路 | |

## Proven Scripts

> 经实际运行验证成功的脚本记录。`skill_evolution(action="record_run")` 自动追加至此表。
>
> 🆕 评分规则：`auto` 来自 rail_review 技术审查，`user` 来自用户认可。`query_logs` 按 approved → recency → score 排序推荐。

| 物种 | 组织 | 方向 | 日期 | 脚本 | auto | user | ✔ |
|:----|:----|:----|:----:|:-----|:----:|:----:|:-:|
| <!-- 首次运行后自动填充 --> | | | | | | | |

## Common Issues

| Issue | Cause | Fix |
|-------|-------|-----|
| **代谢物名无法映射到 KEGG** | 名称格式不一致 | 先统一为 HMDB ID 或 KEGG Compound ID，或使用 MetaboAnalystR 内置名称映射 |
| **mummichog 返回空结果** | m/z tolerance 太严或数据库不匹配 | 放宽到 10 ppm，确认使用的是正确的 KEGG 物种库 |
| **ORA 无显著通路** | 差异代谢物太少或分布太广 | 尝试 MSEA（不硬阈值），或放宽 p-value 阈值到 0.1 |
| **通路太多无法解读** | 代谢物数量大 | 用 FDR < 0.05 过滤，按 impact score 排序，取 top 15 |
| **MetPA KEGG 图着色失败** | 化合物 ID 与 KEGG pathway 不匹配 | 用 HMDB 转换或手动检查 compound ID 格式 |

## References

- Pang Z, Chong J, Li S, Xia J. "MetaboAnalystR 4.0: a unified LC-MS workflow for global metabolomics." *Nature Communications*. 2024. DOI:10.1038/s41467-024-48009-6
- Chong J, Xia J. "MetaboAnalystR: an R package for flexible and reproducible analysis of metabolomics data." *Bioinformatics*. 2018. DOI:10.1093/bioinformatics/bty528
- Li S, et al. "Predicting network activity from high throughput metabolomics." *PLoS Computational Biology*. 2013;9(7):e1003123. DOI:10.1371/journal.pcbi.1003123 — **mummichog 方法学**
- Xia J, Wishart DS. "MetPA: a web-based metabolomics tool for pathway analysis and visualization." *Bioinformatics*. 2010;26(18):2342-2344. DOI:10.1093/bioinformatics/btq418 — **MetPA 方法学**
- Chong J, et al. "MetaboAnalyst 5.0: narrowing the gap between raw spectra and functional insights." *Nucleic Acids Research*. 2022;49(W1):W388-W396. DOI:10.1093/nar/gkab382
- MetaboAnalystR GitHub: https://github.com/xia-lab/MetaboAnalystR (v4.3.0)
- MetaboAnalyst 官网: https://www.metaboanalyst.ca/
---

## ⛔ Terminal 完成后强制协议（铁律 26）

```
1. rail_review(phase='post')
2. debate_analysis(
     topic="代谢组学分析 —— {样本}",
     context="方法: {PLS-DA/LIMMA/OPLS-DA} | 参数: VIP>{x} p<{y} | 结果: {n}差异代谢物",
     knowledge_base_info=<KB内容>,
   )
   辩论: 方法对吗？VIP/p值阈值合理？代谢物鉴定可信度？富集通路跟生物学一致？
3. save_conclusions(module="03_advanced", topic="Metabolomics", ...)
4. skill_evolution(action="record_run")
5. 更新 task_plan.md
```
