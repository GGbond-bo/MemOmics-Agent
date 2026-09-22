---
name: deg-mixed-design
description: "混合设计差异表达分析（组间独立比较 + 组内配对/重复测量）。使用场景：多组（如 Young/Old/T2D）× 运动前后取样的 scRNA/bulk 数据，需同时算组间主效应、配对时间效应与组×时间交互。推荐 pseudobulk + dream/muscat 混合模型，MAST 作敏感性验证"
when_to_use: "[deg-mixed-design] 多组独立比较 + 组内前后/多点配对取样的 DEG。用户提到'配对'、'运动前后'、'前后比较'、'重复测量'、'独立+配对'、'随机效应'、'组×时间交互'时优先本 skill；纯两组简单比较走 deg-analysis"
version: 1.0.0
author: MemOmics
license: MIT
platforms: [windows, linux, macos]
metadata:
  hermes:
    tags: [deg, mixed-design, paired, repeated-measures, pseudobulk, dream, muscat, 03_高级分析]
    difficulty: advanced
    language: R
    category: scRNA
prerequisites:
  r_packages: ["muscat", "variancePartition", "limma", "lme4", "MAST", "DESeq2", "edgeR"]
  python_packages: []
---

# 混合设计 DEG：组间独立 + 组内配对（split-plot / repeated measures）

## 何时用本 skill

实验结构 = **多个独立组 + 组内重复测量**（前后配对/多时间点），需要同时回答：
1. 组间主效应（独立比较，如 aging: Old_pre vs Young_pre；diabetes: T2D_pre vs Old_pre）
2. 时间/处理主效应（配对比较，如每组 post vs pre）
3. 组×时间交互（各组对处理/运动的响应是否不同 —— 往往是研究亮点）

典型：3 组（健康/老年/老年糖尿病）× 运动前后 = 24 个体 × 2 = 48 样本。

## 核心原则（不可违反）

1. **生物学重复 = 个体，不是细胞**。n≥5/组时 pseudobulk（每个体×条件聚合 counts）是默认选择；逐细胞模型（MAST/Wilcoxon on cells）= 伪重复（pseudoreplication），是审稿人第一攻击点。
   - 金标准：Squair et al. 2022 *Nat Commun* "Confronting false discoveries in single-cell differential expression"。
2. **配对必须建模**。同一人 pre/post 高度相关，忽略配对 → 功效损失 + SE 估计错误。用 `(1|subject)` 随机效应或 block 吸收。
3. **优先统一模型，不拆碎片化 t 检验**。能直接检验组×时间交互，且避免多重比较碎片化。
4. **编辑口径交付**：先结论（交互/主效应是否显著）后证据；来源必须带 PMID/DOI；给方法与源码出处。

## 主流程（推荐 方案A，备 方案B，MAST 作验证）

### 方案 A（首选）：pseudobulk + 线性混合模型（muscat / dream）
```r
library(muscat); library(variancePartition)
sce <- prepSCE(obj, group_id="group", sample_id="subject")
pb <- aggregateData(sce, assay="counts", fun="sum")        # 每个体×条件 → 1 个 pseudobulk
form <- ~ group * time + (1|subject)                        # 统一模型
res <- pbDS(pb, design=form, coef="groupOld:timepost")      # 交互/主效应对比
```
- dream（variancePartition 家族，lme4 内核）专为单细胞多样本设计，支持小样本 + 随机效应
- 出处：Crowell et al. 2020 *Mol Syst Biol*（muscat）；Hoffman & Schadt（variancePartition/dream）

### 方案 B（经典替代）：limma-voom + duplicateCorrelation
```r
dupcor <- duplicateCorrelation(pb_counts, design, block=subject)
fit <- lmFit(pb_counts, design, block=subject, correlation=dupcor$consensus)
fit <- eBayes(fit)  # 两两对比走对比矩阵
```
- block=subject 吸收组内相关；适合已聚合 count 矩阵

### 方案 C：MAST（用户常默认使用）
- MAST 是**逐细胞模型**（Hurdle: 表达量 + 检出率），zlm 以固定效应为主，随机效应支持弱
- 逐细胞 = 伪重复风险；必须用时把 subject 当固定效应（n 个体 = n-1 参数）或至少加入 cngeneson + subject 协变量
- **定位为敏感性验证**，主分析走方案 A/B；两方法 DEG 交集/差异要说明
- 出处：Finak et al. 2015 *Genome Biol*

## 执行步骤

1. search_knowledge(species=, tissue=, direction=, query="混合设计 DEG / 配对") 查已有参数
2. 确认设计骨架：组数 × 每组个体数 × 时间点数 → 判断是否 ≥5 个体/组（不足 → 混合模型仍优于逐细胞，但需强调功效限制）
3. check_env 检查 muscat/variancePartition/limma/MAST
4. rail_review(pre) → 写聚合+模型代码 → 分步执行
5. 出 6 个对比（必要时）：aging 主效应、diabetes 主效应、每组 time 效应、group×time 交互
6. 关键结论走 debate_analysis（L2 或 L1），rail_review(post)，record_run
7. 交付：主分析 + MAST 敏感性 + 交集图（UpSet/韦恩）；结论标注来源 PMID/DOI

## 陷阱

- 聚合时禁止按 condition 聚合（每组只剩 1 个 pseudobulk → DESeq2 报 "design matrix has same number of samples and coefficients"）；必须 sample_id(个体)×group
- 组间失衡（如 10 vs 7 vs 7）→ 混合模型天然处理，但汇报时注明并给每对比 n
- 时间点只有 2 个时交互即"差值之差"，可辅以每组 pre→post 的 delta 分析验证
- 别把"运动前后配对"误当成独立样本；配对检验相关文献：limma block / paired Wilcoxon 均可作交叉验证
- **⛔ 审计「别人/上一轮算好的」效应表时，先确认配对到底有没有真被建模（2026-09-15 实测）**：混合设计下的现成效应表（如 AUCell 打分 `effect5_d_v2.csv`）**可能写着"运动前后"却是独立检验算的**——实测该表 5 个效应全部用 **个体级 pooled-SD Cohen's d + Welch 独立 t**（全表 1100/1100 格复现确认），同批人 Pre/Post 的相关性完全没进模型。审计方法：拿一格的 d/p 真值，枚举 {聚合层级} × {d 公式} × {检验族} 变体跑一遍看谁同时命中（**不要凭"设计看起来是配对"就假定用了配对检验**；注意 n1=n2 时 pooled d 与配对 dav 数值恒等，**d 相同不能推断口径**，只有 p 会说话）。判定口诀：**d 命中 p 不中 → 检验族错；d 与 p 都不中 → 聚合层级错**。
  - 影响量化（同批数据只换检验）：ExOld p **0.4521 → 0.2874**（配对 t）、ExYoung 0.4272 → 0.4008、ExT2D 0.8341 → 0.8501 —— 方向不变但功效被浪费，**小样本（n=7/组）时这个差距足以改变"是否有信号"的判断**，所以审计到就报，交用户决定是否切配对重算。
  - 本文档 §核心原则 2「配对必须建模」是对**新分析**的要求；对既有结果表则先审计再决定要不要返工。

## 同结构文章 + 源码线索

文献目录与 GitHub 源码检索配方：见 `references/source-code-papers.md`（含 2026-08-28 实查核实：MoTrPAC 人类公共数据"meta 分析"是官方代码仓库 `MoTrPAC/motrpac_public_data_analysis` 而非单篇文章，核心模型 `g_fc ~ b0 + b1*x_tr + 1|dataset`）

## 相关

- 常规两组 DEG 流程（DESeq2/Wilcoxon/MAST 全流程、P1-P5 陷阱）：加载 `deg-analysis` skill
- 细胞比例显著性（独立+配对混合比例检验）：`celltype-proportion-comparison`