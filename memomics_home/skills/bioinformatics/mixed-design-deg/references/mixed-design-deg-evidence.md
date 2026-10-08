# 混合设计 DEG 同构高分文章源码证据库

> 2026-08-28 会话沉淀。场景：24 donors × 2 时间点（pre/post 运动），3 组（Y=10 / O=7 / OD=7），48 样本。比较：衰老(Y_Pre vs O_Pre，独立)、糖尿病(O_Pre vs OD_Pre，独立)、各组运动前后(Post−Pre，配对)。
> 源码已 clone 到 `E:/tmp/deg_source/`（本机本地路径，可复阅）。

## ① Lovric et al. 2022 — 运动单细胞·配对（反面教材）

- **文章**：Single-cell sequencing deconvolutes cellular responses to exercise in human skeletal muscle. **Commun Biol** (2022), DOI 10.1038/s42003-022-04088-z, GEO GSE214544
- **结构**：3 人 × pre/post 大腿活检 = 6 样本配对（样本极少）
- **源码**：`E:/tmp/deg_source/Lovric_RStudio/04_differential_analysis.R`（L102-112）
  ```r
  de_genes <- FindMarkers(seurat_subset,
    ident.1 = "Post", ident.2 = "Pre",
    test.use = "wilcox", logfc.threshold = 0, min.pct = 0.1)
  ```
- **教训**：纯细胞级 Wilcoxon，完全不建模 donor 配对 → 假重复设计（3 人 pre/post 当独立样本）。能发 Comm Biol 靠样本少+结论保守。审稿人一问"统计单位是什么"就翻车。
- 该论文另有 scanpy 复现仓库 `E:/tmp/deg_source/Lovric_repro/`（QC/聚类部分，DE 分析较弱）。

## ② MoTrPAC 大鼠训练研究 — bulk 独立组间 + 协变量

- **文章**：MoTrPAC Consortium 大鼠训练多组学（Nature 2024 系列）
- **源码**：`E:/tmp/deg_source/MoTrPAC_rat/R/transcript_differential_analysis.R`（run_deseq）
  ```r
  dds <- DESeqDataSetFromMatrix(counts, meta,
         design = ~ group + pct_globin + RIN + pct_umi_dup + median_5_3_bias)
  dds <- DESeq(dds)
  res <- results(dds, contrast = c("group", "1w", "control"))  # 1w/2w/4w/8w vs control
  lfcShrink(dds, contrast = c, type = "ashr")                  # ashr+optmethod='mixSQP'
  ```
- **关键**：bulk 层面 DESeq2；RNA 质量协变量（globin/RIN/UMI dup/5'3' bias）显式纳入；时间点作独立 group 做 contrast（大鼠是独立动物，非配对）。

## ③ MoTrPAC 人类公共数据 meta 分析 — 独立+配对混合的正确示范

- **源码**：`E:/tmp/deg_source/MoTrPAC_public/metaanalysis/metaanalysis_tests.R` + `simplified_moderators_metaanalysis.R`
  ```r
  rma.mv(yi, vi, mods = ~ training + time,
         random = ~ V1 | gse, data = gdata,           # gse(研究)作随机效应
         control = list(maxiter=10000, stepadj=0.5))
  # get_gene_analysis_pvals(): 每基因效应量 yi + 方差 vi（由各原始研究 per-gene t 统计量转换，含配对处理的 t）
  # 选择阈值: I2_thr=50, AIC_diff_thr=5, acute/longterm beta_thr=0.1, P_thr=1e-3
  # get_rma_obj_with_mods(): has_training/has_time 分支, random = ~ V1|gse 始终保留
  ```
- 数据预处理见 `metaanalysis_archive/acute_data_preprocessing.R`：排除无时间/无 subject id 样本，标准化 time（-1=baseline, 小时）。
- **关键**：单数据集内 training(组间)+time(配对) 同时进模型；跨数据集 rma.mv 带 gse 随机效应——"独立、配对、随机效应"三者同时建模的期刊级正统做法。

## ④ Zemke 海马 aging（用户专利相关）

- **源码**：`E:/tmp/deg_source/Zemke_hippocampus/`；`03_age_correlation/` 有 correlation_gene_expression.ipynb（连续年龄相关）、02_feature_calling/ 有 DMR 分析。
- 用连续年龄相关 + 单细胞 multi-omics（非离散组间比较），可参考其基因-年龄相关部分。

## 找同构文章源码的 GitHub 工作流（复现步骤）

1. GitHub API 搜仓库（未认证限流 60/h，遇 403 就等/换 curl 直接 clone 已知仓库）：
   `https://api.github.com/search/repositories?q=<关键词>&sort=stars&per_page=6`
2. 候选仓库直接 `git clone --depth 1 <repo> /e/tmp/deg_source/<名>`（clone 不占 API）
3. 定位 DEG 脚本：search_files `*.R` / `*.ipynb`，或 grep `DESeq|MAST|FindMarkers|dream|limma|pseudobulk|rma.mv`
4. 读核心函数：找 formula（`~ group + time + (1|donor)`）/ contrasts / 聚合代码，而非只看 README
5. 关键词灵感：`MoTrPAC` / `exercise+single+cell+skeletal+muscle` / `<tissue>+aging+single` + 特定作者名（如 Zemke/nrzemke）