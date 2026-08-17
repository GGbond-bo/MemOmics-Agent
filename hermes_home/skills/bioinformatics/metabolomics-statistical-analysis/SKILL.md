---
name: metabolomics-statistical-analysis
description: "代谢组学统计分析全流程：输入 peak intensity matrix → 归一化 → 缺失值填充 → PCA → PLS-DA/OPLS-DA → VIP筛选 → 火山图 → Random Forest → ROC → 生物标志物Panel。基于 MetaboAnalystR 4.0 + ropls + mixOmics + caret。"
version: 1.0.0
author: MemOmics
license: MIT
platforms: [windows, linux, macos]
metadata:
  hermes:
    tags: [metabolomics, LC-MS, GC-MS, NMR, PLS-DA, OPLS-DA, PCA, volcano, biomarker, 代谢组学, 差异分析, 统计分析]
    difficulty: intermediate
    language: R
    category: Metabolomics
prerequisites:
  r_packages: [MetaboAnalystR, ropls, mixOmics, caret, pROC, randomForest, ggplot2, ggprism, ggrepel, ComplexHeatmap, impute, pcaMethods, tidyverse, plotly]
  python_packages: []
related_skills: [metabolomics-functional-enrichment, lasso-biomarker-panel, survival-analysis-clinical, proteomics-diff-exp]
when_to_use: "[metabolomics-statistical-analysis] 代谢组学统计分析 / 代谢物差异分析 / LC-MS差异 / GC-MS差异 / PLS-DA / OPLS-DA / VIP / 代谢标志物 / 代谢组火山图 / metabolomics / metabolic biomarker / peak intensity matrix 差异对比"
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
2. skill_view 加载本 SKILL.md（获取脚本模板+审查规则+参数范围）
3. check_env 检查环境（缺包自动安装）
4. rail_review(pre) 前置审查（参数合理吗？包齐了吗？数据准备好了吗？）
5. 写这一步的代码（基于 skill 模板，只写这一步，不写后续步骤）
6. terminal 执行（分步执行，禁止 && 连接多步骤）
7. debate_analysis 多方辩论（正方/反方切断上下文独立生成 + LLM裁决）
8. rail_review(post) 后置审查（图有没有？结果合理吗？跟知识库对应吗？）
```

### 规则3: 代码分段执行 — 写一步跑一步
- ❌ **禁止**一次性写完全部代码用 && 连接执行
- ✅ **必须**分步：写一步 → 执行 → 检查结果 → 辩论 → 下一步

### 规则4: 关键参数多参数尝试 + 辩论
- 涉及数值参数时（如 VIP 阈值、FDR threshold、ncomp 等），**至少尝试 2-3 个值**
- 每次参数变更后调 `debate_analysis` 辩论"这个参数合理吗？结果有没有变好？"
- 辩论格式（多角色对抗 v3）：正方 3 位 + 反方 4 位 + 裁判编辑
- **不确定的参数就辩论**，不要自己拍脑袋

### 规则5: 执行后审查（强化版）
- 每步执行完调 `rail_review(post)` 审查
- **图片检查**：生成了吗？空白吗？有 NA 吗？<5KB 吗？数量够吗？
- **代码质量检查**：行数合理？有注释？分段执行？
- **结果合理性**：数值范围合理？跟知识库对应吗？
- 通过 → `skill_evolution(action="record_run")`

### 规则N: 运行记录只是参考，不能跳过审查
- 历史运行日志仅供参数参考，不能跳过审查

### 规则6: 结果存储结构
```
results/<模块>/<方法>/
  ├── scripts/     # 分析脚本
  ├── figures/     # PNG + SVG 图表
  ├── data/        # RDS 中间数据
  └── results/     # CSV/TSV 结果表
```

### 规则7: 脚本出错/成功 → 必须调 skill_evolution（自进化）

| 时机 | action |
|------|--------|
| 脚本报错+分析根因+修复后 | record_error |
| 脚本成功+结果通过 rail_review | record_success |
| 修复后脚本验证稳定有效 | update_script |

---

# 代谢组学统计分析 (Metabolomics Statistical Analysis)

针对 LC-MS/GC-MS/NMR 代谢组学数据的完整统计分析流程。输入 peak intensity matrix，输出差异代谢物、多变量模型、生物标志物 Panel。

## When to Use

### ✅ 应该使用
- 有 LC-MS / GC-MS / NMR 代谢组学 peak intensity matrix（行=代谢物，列=样本）
- 需要比较两组或多组条件（如疾病 vs 对照、处理 vs 未处理）
- 需要 PLS-DA / OPLS-DA 多变量建模
- 需要筛选差异代谢物 (VIP + p-value + FC)
- 需要构建生物标志物 Panel (ROC/Random Forest/LASSO)
- 数据已从原始谱图处理完成（通过 XCMS/MZmine/MS-DIAL/MetaboAnalystR 预处理模块）

### ❌ 不应该使用
- 还是原始 .mzML/.raw 谱图 → 先用 MetaboAnalystR 预处理模块或 metabolomics-pipeline-metaboanalyst
- 靶向代谢组学绝对定量数据（有标准曲线） → 用不同统计方法（不需要归一化/缺失值填充）
- 只有 1 个样本/组 → 无法统计检验
- 需要代谢通路富集 → 配合 metabolomics-functional-enrichment

## Pipeline

### Step 1: 数据加载与验证
```
Tool: terminal (Rscript)
输入: peak intensity matrix (CSV/TSV, 行=代谢物名, 列=样本名) + metadata (CSV, 含 condition 列)
输出: 验证报告
```

### Step 2: 归一化 + 缺失值填充 + 数据变换
```
方法选择（自动检测或用户指定）:
- 归一化: PQN (Probabilistic Quotient Normalization, 默认) / Quantile / VSN / Median / MSTUS / SUM
- 缺失值: kNN (默认) / MinProb / Half-min / Mean
- 数据变换: Log2 (默认) / Log10 / Cube-root / None
- Scaling: Pareto (默认) / Auto / Range / Mean-center / None
```

### Step 3: 单变量分析
```
- t-test / Wilcoxon / ANOVA (多组)
- 火山图 (log2FC + -log10 p-value)
- 多重检验校正 (FDR/Bonferroni)
```

### Step 4: 多变量分析 — PCA
```
- 无监督降维
- Score plot (PC1 vs PC2, QC样本聚类检查)
- Scree plot (解释方差)
- Loading plot
```

### Step 5: 多变量分析 — PLS-DA
```
- 有监督分组模型
- Score plot (组间分离)
- VIP scores (≥1.0 为显著贡献, 默认阈值)
- ⚠️ 必须做置换检验 (n≥1000), 输出 R2/Q2/p 值
- 过拟合检查: permutation plot
```

### Step 6: 多变量分析 — OPLS-DA (可选, 2组比较)
```
- 正交信号校正, 更好解释组间差异
- S-plot (协方差 vs 相关性)
- 差异代谢物筛选
```

### Step 7: 机器学习 — Random Forest
```
- 变量重要性排序 (Mean Decrease Accuracy / Gini)
- Out-of-bag error rate
- Top N 代谢物热图
```

### Step 8: ROC 曲线 + 生物标志物评估
```
- 单个标志物 ROC (AUC + 95% CI)
- 多标志物 Logistic 回归 Panel
- 也可串联 lasso-biomarker-panel skill
```

## Parameters

| 参数 | 默认值 | 说明 | 来源 |
|------|--------|------|------|
| `normalization` | `"PQN"` | 归一化方法 | Dieterle et al. 2006 Anal Chem |
| `imputation` | `"kNN"` | 缺失值填充方法 | k=10 neighbors |
| `transform` | `"log2"` | 数据变换 | 使数据更接近正态分布 |
| `scaling` | `"Pareto"` | 特征 scaling (mean-center + /√SD) | van den Berg et al. 2006 BMC Genomics |
| `p_threshold` | `0.05` | 单变量显著阈值 | 常规 FDR 校正 |
| `fc_threshold` | `1.5` | Fold change 阈值 | 常规倍数 |
| `vip_threshold` | `1.0` | PLS-DA VIP 阈值 | 常规, 可调 1.0-2.0 |
| `n_permutations` | `1000` | PLS-DA 置换检验次数 | **不低于 1000** |
| `rf_ntree` | `500` | Random Forest 树数 | 常规 |
| `pca_ncomp` | `5` | PCA 主成分数 | 可调 |
| `plsda_ncomp` | `3` | PLS-DA 成分数 | 通过 CV 确定 |

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
| **PLS-DA 完美分离但有置换检验 p>0.05** | 过拟合 | 减少 ncomp、检查样本量是否足够（n≥10/组）、确认置换检验 n≥1000 |
| **缺失值过多导致 kNN 失败** | 某代谢物在某组全部缺失 | 先过滤 >50% 缺失的代谢物，或用 MinProb 替代 |
| **PQN 归一化失败** | 参考样本选择问题 | 自动选 QC 样本为参考，无 QC 则用所有样本中位数 |
| **MetaboAnalystR 安装失败** | 依赖包冲突 | 先 `metanr_packages()` 装依赖，再用 `pak::pak("xia-lab/MetaboAnalystR")` |
| **火山图点太密** | 代谢物特征数 >1000 | 用 ggrepel 标注 top 20 即可 |
| **OPLS-DA 不收敛** | 仅有 2 组但 ncomp 过高 | OPLS-DA 只需 1 predictive + 1 orthogonal component |
| **⛔ 两组比较实际是技术重复 (r>0.9)** | 列名误导 | **STOP**: 两个数值列是技术重复 → 禁做差异分析，取均值排名即可 |

## References

- Pang Z, Chong J, Li S, Xia J. "MetaboAnalystR 4.0: a unified LC-MS workflow for global metabolomics." *Nature Communications*. 2024. DOI:10.1038/s41467-024-48009-6
- Chong J, Xia J. "MetaboAnalystR: an R package for flexible and reproducible analysis of metabolomics data." *Bioinformatics*. 2018;34(24):4313-4314. DOI:10.1093/bioinformatics/bty528
- Dieterle F, Ross A, Schlotterbeck G, Senn H. "Probabilistic quotient normalization as robust method to account for dilution of complex biological mixtures." *Analytical Chemistry*. 2006;78(13):4281-4290. DOI:10.1021/ac051632c
- van den Berg RA, et al. "Centering, scaling, and transformations: improving the biological information content of metabolomics data." *BMC Genomics*. 2006;7:142. DOI:10.1186/1471-2164-7-142
- Thévenot EA, et al. "Analysis of the Human Adult Urinary Metabolome Variations with Age, Body Mass Index, and Gender by Implementing a Comprehensive Workflow for Univariate and OPLS Statistical Analyses." *J Proteome Res*. 2015;14(8):3322-3335. DOI:10.1021/acs.jproteome.5b00354 — **ropls 包及 OPLS-DA 方法学**
- Sumner LW, et al. "Proposed minimum reporting standards for chemical analysis." *Metabolomics*. 2007;3(3):211-221. DOI:10.1007/s11306-007-0070-6 — **MSI 鉴定标准**
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
