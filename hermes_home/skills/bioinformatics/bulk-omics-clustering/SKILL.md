---
id: "skill_51a601b71a454a00aa0d378fe8e3205c"
name: "bulk-omics-clustering"
when_to_use: "[bulk-omics-clustering] Bulk组学样本聚类：bulk RNA表达矩阵→PCA/t-SNE/UMAP→样本分群→WGCNA共表达网络→模块-性状关联"
display-name: "Bulk Omics Clustering Analysis"
category: Bulk RNA
short-description: Cluster samples or features from bulk transcriptomics, proteomics, or metabolomics data.
detailed-description: Perform systematic clustering analysis on biological data matrices (samples or features) using multiple algorithms with rigorous validation and interpretation. Use when you need to identify natural groupings in expression data, discover biological subtypes, group genes by expression patterns, or compare clustering methods. Supports hierarchical, k-means, HDBSCAN, and Gaussian mixture models. Includes optimal cluster number determination, quality validation, stability testing, and comprehensive visualization. Best for bulk transcriptomics, proteomics, metabolomics, or any quantitative data matrix with 10+ samples/features.
starting-prompt: Cluster my samples by gene expression to identify biological subtypes . .
---
---

## ⛔ MemOmics 强制规则（不可违反，优先级最高）

> 本 skill 已集成到 MemOmics-Agent 自进化生信分析平台。以下规则覆盖所有 Biomni 默认行为。

### 规则1: 拿到数据 → 必须调 search_knowledge
- **每个分析步骤写代码前**，必须先调 `search_knowledge(species=..., tissue=..., direction=..., query="<步骤名> 参数")`
- 知识库有匹配 → 用知识库的参数和模板
- 知识库无匹配 → 用 web 搜索文献，提取方法和参数，存入知识库
- **绝对不能跳过直接写代码**

### 规则2: 7步循环（每步必须走完整循环）
```
1. search_knowledge 查本步骤的方法和参数
2. check_env 检查环境
3. rail_review(pre) 前置审查
4. source/import 预写脚本（禁止 inline 代码）
5. terminal 执行（分步执行，禁止 && 连接多步骤）
6. debate_analysis 多方辩论（正方/反方切断上下文独立生成 + LLM裁决）
7. rail_review(post) 后置审查
```

### 规则3: 代码分段执行 — 写一步跑一步
- ❌ **禁止**一次性写完全部代码用 && 连接执行
- ✅ **必须**分步：写一步 → 执行 → 检查结果 → 辩论 → 下一步

### 规则4: 关键参数多参数尝试 + 辩论
- 涉及数值参数时（如 resolution, n_pcs, min_features, FDR threshold等），**至少尝试 2-3 个值**
- 每次参数变更后调 `debate_analysis` 辩论"这个参数合理吗？结果有没有变好？"
- 辩论格式：正方（支持当前参数）vs 反方（质疑+替代方案）→ 裁判决断
- **不确定的参数就辩论**，不要自己拍脑袋

### 规则5: 执行后审查

### 规则N: 运行记录只是参考，不能跳过审查
- skill_evolution(action="query_logs") 返回的历史运行日志仅供参数参考
- 即使有 quality_score=9.0 的历史日志，仍必须执行 rail_review(pre)、debate_analysis、rail_review(post)
- 禁止因"之前跑过"而跳过任何审查步骤
- 禁止直接用历史日志里的脚本运行而不经本次审查
- 运行日志是"参考"不是"免审凭证"

  - **图片检查**：
    - 图有没有生成？没生成 → **强制重新执行**
    - 图片是否空白（全白/全黑/全单一色）？空白 → **强制重新出图**
    - 图片是否有 NA/缺失值（>10% 像素是 NA）？有 NA → **强制重新出图**
    - 图片大小是否过小（<5KB）？过小 → **强制重新出图**
    - 图片数量是否足够？（每步至少 1 张图，关键步骤至少 2-3 张）
  - **代码质量检查**：
    - 代码行数是否合理？（过短可能偷懒，过长可能未分段）
    - 代码是否有注释？
    - 代码是否分段执行（禁止 && 连接多步骤）？
  - **结果合理性**：
    - 数值范围是否合理？
    - 跟知识库对应吗？
  - **参数和结论辩论**：
    - 有参数的选择 → **必须调 debate_analysis 辩论**
    - 有结论输出 → **必须调 debate_analysis 辩论**
    - 不通过 → 修复重跑
    - 通过 → **必须调 skill_evolution(action="record_run")** 记录成功经验（skill_name/script_name/species/tissue/direction/params_used/result_summary/quality_score/notes） → 创建目录存储(figures/results/scripts/data) → 下一步
    - **不通过 → 修复后重跑 → 成功后调 skill_evolution(action="record_run")**；如果是脚本报错 → **调 skill_evolution(action="record_error")** 记录根因+修复方案

### 规则6: 结果存储结构
```
results/<模块>/<方法>/
  ├── scripts/     # 分析脚本
  ├── figures/     # PNG + SVG 图表
  ├── data/        # RDS/H5AD 中间数据
  └── results/     # CSV/TSV 结果表
```


### 规则7: 脚本出错/成功 → 必须调 skill_evolution（自进化）

| 时机 | action | 调 | 不调 |
|------|--------|----|------|
| 脚本报错+你分析根因+修复后 | record_error | ✅ R/Python 脚本报错，你找到根因并修复 | ❌ trivial 错误（打字错误、路径不存在） |
| 脚本成功+结果通过 rail_review | record_success | ✅ 分析步骤完成，图生成，审查通过 | ❌ 闲聊/方法咨询/非分析任务 |
| 修复后脚本验证稳定有效 | update_script | ✅ 同一错误修复了，重跑成功 | ❌ 只改参数没改脚本；未验证就更新 |

---



# Bulk Omics Clustering Analysis

Systematic workflow for clustering biological samples, features, or any quantitative data matrix. Implements multiple clustering algorithms with rigorous validation, comparison, and interpretation to identify meaningful data groupings.

## When to Use This Skill

Use clustering analysis when you need to:
- ✅ **Group biological samples** by gene expression profiles (bulk RNA-seq, proteomics)
- ✅ **Identify feature patterns** (genes/proteins with similar expression across conditions)
- ✅ **Discover subtypes** in disease or treatment response groups
- ✅ **Analyze trajectories** in time-series or developmental data
- ✅ **Quality control** by detecting batch effects or outliers
- ✅ **Compare methods** by systematically evaluating multiple clustering approaches

**Don't use this skill for:**
- ❌ Single-cell RNA-seq clustering → Use scrnaseq-scanpy-core-analysis or scrnaseq-seurat-core-analysis
- ❌ Gene co-expression network analysis → Use coexpression-network

**Key Concept:** Clustering reveals natural groupings in data without prior labels. Different algorithms make different assumptions—this workflow helps you choose and validate the right approach for your data.

**Language Support:** This skill supports both **Python** and **R** implementations. Choose based on your preference and existing analysis pipeline. Python offers scikit-learn ecosystem integration; R offers ComplexHeatmap and rich Bioconductor tools.

## Quick Start (5-Minute Example)

Test the workflow with the ALL (Acute Lymphoblastic Leukemia) dataset - 128 pediatric ALL patients with B-cell and T-cell subtypes:

**R (Recommended for ALL dataset):**
```r
# 1. Load example data (ALL dataset from Chiaretti et al. 2004)
source("scripts/load_example_data.R")
data_list <- load_example_clustering_data()
data <- data_list$data
sample_names <- data_list$sample_names
feature_names <- data_list$feature_names
metadata <- data_list$metadata

# 2. Run clustering
source("scripts/hierarchical_clustering.R")
result <- hierarchical_clustering(data, n_clusters = 2)
cluster_labels <- result$cluster_labels
hclust_obj <- result$clustering_object

# 3. Visualize
source("scripts/plot_cluster_heatmap.R")
plot_cluster_heatmap(
  data,
  cluster_labels,
  output_dir = "quick_test_results"
)

# 4. Export results
# Results automatically saved by plotting functions
cat("\n✓ Quick start complete!\n")
cat(sprintf("Cell types: B-cell ALL (n=%d), T-cell ALL (n=%d)\n",
            sum(metadata$cell_type == "B"),
            sum(metadata$cell_type == "T")))
```

**Python users:** The Python implementation can use the same ALL dataset via rpy2, or use your own data. For ALL dataset examples in Python, you'll need `pip install rpy2` and R installed. See full workflow below.

**Expected output:** Dendrogram distinguishing B-cell vs T-cell ALL, PCA plots, silhouette plots, heatmaps in `quick_test_results/`

**Note:** For your own data, follow the full workflow below with the Clarification Questions.

## Installation

### Language Choice

This workflow supports both Python and R. Choose one based on:
- **Python**: Better for large-scale data (>10k samples), integration with machine learning pipelines, modern plotting (plotnine)
- **R**: Better for heatmap visualization (ComplexHeatmap), Bioconductor integration, traditional bioinformatics workflows

You can also mix: use R for visualization (heatmaps) and Python for clustering algorithms.

### Python Installation

### Required Software

| Software | Version | License | Commercial Use | Installation |
|----------|---------|---------|----------------|--------------|
| numpy | ≥1.20 | BSD-3-Clause | ✅ Permitted | `pip install numpy` |
| pandas | ≥1.3 | BSD-3-Clause | ✅ Permitted | `pip install pandas` |
| scikit-learn | ≥1.0 | BSD-3-Clause | ✅ Permitted | `pip install scikit-learn` |
| scipy | ≥1.7 | BSD-3-Clause | ✅ Permitted | `pip install scipy` |
| hdbscan | ≥0.8.28 | BSD-3-Clause | ✅ Permitted | `pip install hdbscan` |
| umap-learn | ≥0.5 | BSD-3-Clause | ✅ Permitted | `pip install umap-learn` |
| plotnine | ≥0.10 | MIT | ✅ Permitted | `pip install plotnine` |
| plotnine-prism | Latest | MIT | ✅ Permitted | `pip install plotnine-prism` |
| seaborn | ≥0.11 | BSD-3-Clause | ✅ Permitted | `pip install seaborn` |
| matplotlib | ≥3.4 | PSF-based | ✅ Permitted | `pip install matplotlib` |
| adjustText | ≥0.8 | MIT | ✅ Permitted | `pip install adjustText` |
| statsmodels | ≥0.13 | BSD-3-Clause | ✅ Permitted | `pip install statsmodels` |

**Optional:** gap-stat (Apache 2.0), yellowbrick (Apache 2.0) - both permitted for commercial use

**Minimum Python version:** Python ≥3.8

**License Compliance:** All software packages use BSD-3-Clause, MIT, or similar permissive licenses that allow commercial use in AI agent applications.

### R Installation

**Minimum R version:** R ≥4.0

**Required packages:** cluster, factoextra, NbClust, ComplexHeatmap, pheatmap, dendextend, dbscan, mclust, ggplot2, ggprism (all GPL/MIT licensed, commercial use permitted)

**Quick install:**
```r
install.packages(c('cluster', 'factoextra', 'NbClust', 'pheatmap',
                   'dendextend', 'dbscan', 'mclust', 'ggplot2', 'ggprism'))
if (!require('BiocManager')) install.packages('BiocManager')
BiocManager::install('ComplexHeatmap')
```

**Detailed R installation guide:** [references/r-quick-start.md#r-installation](references/r-quick-start.md#r-installation)

## Inputs

### Required Input

**1. Data Matrix** (CSV, TSV, Excel, or HDF5):
- **Sample clustering**: Rows = samples, Columns = features (genes/proteins)
- **Feature clustering**: Rows = features, Columns = samples
- Values should be normalized and comparable (TPM, FPKM, VST, Z-scores)
- Missing values: handle by imputation or removal before clustering

**2. Sample/Feature Metadata** (CSV or TSV, optional but recommended):
- IDs matching data matrix rows/columns
- Annotations for validation (tissue type, condition, known groups)
- Used to interpret and validate clustering results

### Data Requirements

- **Minimum samples/features**: 10+ (20+ recommended for robust clustering)
- **Normalization**: Required—use appropriate method for data type
- **Batch effects**: Remove or regress out before clustering
- **Outliers**: Identify and consider removing extreme outliers
- **Dimensionality**: High-dimensional data (>1000 features) benefits from PCA first

### Supported Data Types

- **Transcriptomics**: Bulk RNA-seq (normalized counts, TPM, FPKM)
- **Proteomics**: Protein abundance data
- **Metabolomics**: Metabolite concentrations
- **Multi-omics**: Integrated features from multiple assays
- **Clinical**: Patient feature matrices
- **Any quantitative matrix**: General-purpose application

## Outputs

**Cluster assignments:**
- `clustering_assignments.csv` - Sample/feature IDs with cluster labels
- `clustering_statistics.csv` - Size, centroids, and characteristics per cluster

**Validation metrics:**
- `clustering_validation_metrics.json` - Silhouette, Davies-Bouldin, Calinski-Harabasz scores
- `stability_results.csv` - Bootstrap resampling stability scores (if run)

**Characterization:**
- `clustering_cluster*_features.csv` - Top distinguishing features for each cluster (ANOVA/Kruskal-Wallis)
- `clustering_all_cluster_features.csv` - Combined features for all clusters

**Analysis objects (pickle/RDS):**
- `clustering_analysis_object.pkl` - Complete clustering object for downstream use
  - Load with: `import pickle; obj = pickle.load(open('clustering_analysis_object.pkl', 'rb'))`
  - Contains: linkage matrix (hierarchical), fitted model (k-means, GMM, HDBSCAN)
  - Required for: Advanced analysis, re-cutting dendrograms, model inspection
- `clustering_data_matrix.csv` - Normalized/transformed data matrix used for clustering

**Visualizations (PNG + SVG at 300 DPI):**
- Dendrogram (hierarchical clustering)
- PCA/UMAP scatter plots with cluster colors
- Silhouette plots
- Cluster heatmaps
- Cluster size barplots
- Optimal k determination plots (if run)

**Supporting data:**
- `clustering_parameters.json` - All parameters used in analysis

## Clarification Questions

Before starting analysis, gather the following information:

### 1. **Input Files** (ASK THIS FIRST):
   - Do you have specific gene expression or omics data file(s) to cluster?
   - If you've uploaded a file, is it the data matrix (samples × features or features × samples) you'd like to analyze?
   - Expected file types: CSV, TSV, Excel (.xlsx), HDF5 (.h5), or RDS (R data objects)
   - **Or use ALL (Acute Lymphoblastic Leukemia) example data?** (Real patient data: 128 pediatric ALL samples with B-cell and T-cell subtypes, 1000 most variable genes. Dynamically loads from Bioconductor in ~30 seconds via [scripts/load_example_data.R](scripts/load_example_data.R). Citation: Chiaretti et al. 2004. **R recommended** for this dataset.)

### 2. **Which programming language do you prefer?**
   - **Python**: Modern ecosystem with scikit-learn, better for large datasets (>10k samples), machine learning integration
   - **R**: Rich Bioconductor tools, excellent heatmap visualization (ComplexHeatmap), traditional bioinformatics workflows
   - **Both**: Use Python for clustering algorithms, R for heatmap visualization (recommended for best of both worlds)
   - **No preference**: Will use Python (default, more comprehensive scripts available)

### 3. **What are you clustering?**
   - **Samples** (rows = samples, columns = features like genes)
     - Example: Group patients by gene expression profiles
   - **Features** (rows = features, columns = samples)
     - Example: Group genes by expression patterns across conditions
   - **Both** (explore both clustering directions)

### 4. **What is your data format and normalization status?**
   - **Bulk RNA-seq**: TPM, FPKM, VST, rlog
   - **Proteomics**: TMT/iTRAQ normalized intensities, LFQ
   - **Metabolomics**: Normalized peak areas
   - **Already normalized**: Z-scores, scaled values
   - **Raw data**: Needs normalization (specify data type)

### 5. **What clustering approach do you prefer?**
   - **Hierarchical (recommended for exploration)**: Creates a tree-like dendrogram showing relationships at all scales. You can cut the tree at any height to get different numbers of clusters after seeing the structure. Best for visualization and when you don't know k. Deterministic (same results every run). Works well for small-medium datasets (<5k samples).
   - **K-means**: Fast partitioning method that requires specifying k upfront. Best for large datasets (>5k samples) with spherical/compact clusters. Results may vary between runs, so use high n_init.
   - **Density-based (HDBSCAN)**: Automatically finds k by identifying dense regions. Can detect arbitrary cluster shapes and marks outliers. No need to specify k. Best when clusters have varying densities or you want outlier detection.
   - **Model-based (GMM)**: Probabilistic soft clustering where samples have membership probabilities for each cluster. Useful when clusters overlap or you need uncertainty estimates. Requires specifying k.
   - **Compare all methods**: Systematic comparison (recommended for exploratory analysis)

### 6. **Do you know the expected number of clusters (k)?**
   - **Yes, k = [number]**: Will validate this choice with quality metrics
   - **No, exploratory**: Will test multiple k values (2-15) and help determine optimal k
   - **Approximate range**: k between [min] and [max]
   - **Not needed**: Hierarchical clustering lets you choose k later; HDBSCAN finds k automatically

### 7. **What distance metric is most appropriate?**
   - **Euclidean**: Default for most continuous data
   - **Correlation**: For gene expression (focuses on pattern similarity)
   - **Manhattan**: Robust to outliers
   - **Cosine**: For high-dimensional sparse data
   - **Unsure**: Will use Euclidean (default)

### 8. **Should we apply dimensionality reduction first?**
   - **Yes, use PCA**: Recommended for >1000 features
   - **Yes, use UMAP**: For visualization and manifold learning
   - **No**: Keep original feature space (<100 features)
   - **Both**: PCA for clustering, UMAP for visualization

### 9. **How should cluster quality be validated?**
   - **Internal metrics only**: Silhouette, Davies-Bouldin, Calinski-Harabasz
   - **Known labels available**: Compare to known groups (adjusted Rand index)
   - **Stability analysis**: Bootstrap resampling to test robustness
   - **Biological validation**: Check for differential features between clusters

## Standard Workflow

🚨 **MANDATORY: USE SCRIPTS EXACTLY AS SHOWN - DO NOT WRITE INLINE CODE** 🚨

**Note:** This skill requires decisions (algorithm, distance metric, k value) - adapt parameters to your data using guidance in [references/decision-guide.md](references/decision-guide.md).

**Step 1 - Load data:**

**For ALL example data (R recommended):**
```r
source("scripts/load_example_data.R")
data_list <- load_example_clustering_data()
data <- data_list$data
sample_names <- data_list$sample_names
feature_names <- data_list$feature_names
metadata <- data_list$metadata
```

**For your own data (Python or R):**
```python
# Python
from scripts.prepare_data import load_and_prepare_data
data, sample_names, feature_names = load_and_prepare_data(
    "your_data.csv",
    normalize_method="zscore"
)
```

```r
# R
source("scripts/prepare_data.R")
data_list <- load_and_prepare_data("your_data.csv", normalize_method = "zscore")
data <- data_list$data
```

**DO NOT write custom data loading code. Use the provided functions.**

**Step 2 - Run clustering analysis:**

```python
# Choose ONE clustering method and run it:

# Option A: Hierarchical clustering (recommended for exploration)
from scripts.hierarchical_clustering import hierarchical_clustering
linkage_matrix, cluster_labels = hierarchical_clustering(
    data,
    n_clusters=2,  # For ALL dataset: B-cell vs T-cell; adjust for your data
    linkage_method="ward",
    distance_metric="euclidean"
)
clustering_object = linkage_matrix

# Option B: K-means clustering (fast, for large datasets)
from scripts.kmeans_clustering import kmeans_clustering
cluster_labels, kmeans_model = kmeans_clustering(
    data,
    n_clusters=2,  # For ALL dataset: B-cell vs T-cell; adjust for your data
    n_init=50
)
clustering_object = kmeans_model

# Option C: HDBSCAN (automatic k detection)
from scripts.density_clustering import hdbscan_clustering
cluster_labels, hdbscan_model = hdbscan_clustering(
    data,
    min_cluster_size=10
)
clustering_object = hdbscan_model

# Validate clustering quality
from scripts.cluster_validation import validate_clustering
validation_results = validate_clustering(data, cluster_labels, metrics="all")
print(f"Silhouette score: {validation_results['silhouette']:.3f}")
```
**DO NOT write custom clustering code. Use one of the provided methods.**

**Step 3 - Generate visualizations:**

```python
# Generate comprehensive plots
from scripts.plot_clustering_results import plot_all_results
from scripts.dimensionality_reduction import apply_pca, apply_umap

# Optional: compute PCA/UMAP for visualization
pca_data = apply_pca(data, n_components=2)
umap_data = apply_umap(data, n_components=2)

# Create all plots
plot_all_results(
    data=data,
    cluster_labels=cluster_labels,
    sample_names=sample_names,
    feature_names=feature_names,
    pca_data=pca_data,
    umap_embedding=umap_data,
    linkage_matrix=clustering_object if 'linkage_matrix' in locals() else None,
    output_dir="clustering_results"
)
```
🚨 **DO NOT write inline plotting code (matplotlib.pyplot.savefig, seaborn.clustermap, etc.). Use plot_all_results().** 🚨

**The script handles PNG + SVG export with graceful fallback for optional dependencies.**

**Step 4 - Export results:**

```python
# Export all results including analysis objects for downstream use
from scripts.export_results import export_all

export_all(
    data=data,
    cluster_labels=cluster_labels,
    sample_names=sample_names,
    feature_names=feature_names,
    validation_results=validation_results,
    clustering_object=clustering_object,
    output_dir="clustering_results"
)
```
**DO NOT write custom export code. Use export_all().**

**✅ VERIFICATION - You should see:**
- After Step 1: `"✓ Data loaded successfully!"`
- After Step 2: `"✓ Clustering completed successfully!"`
- After Step 3: `"✓ Plots saved to clustering_results"`
- After Step 4: `"=== Export Complete ==="`

**❌ IF YOU DON'T SEE THESE:** You wrote inline code. Stop and use the scripts as shown.

⚠️ **CRITICAL - DO NOT:**
- ❌ **Write inline clustering algorithms** → **STOP: Use provided clustering functions**
- ❌ **Write inline plotting code (matplotlib.pyplot.savefig, seaborn.clustermap, etc.)** → **STOP: Use `plot_all_results()`**
- ❌ **Write custom export code** → **STOP: Use `export_all()`**
- ❌ **Try to install plotting dependencies manually** → scripts handle fallback automatically

**⚠️ IF SCRIPTS FAIL - Script Failure Hierarchy:**
1. **Fix and Retry (90%)** - Install missing package, re-run script
2. **Modify Script (5%)** - Edit the script file itself, document changes
3. **Use as Reference (4%)** - Read script, adapt approach, cite source
4. **Write from Scratch (1%)** - Only if genuinely impossible, explain why

**NEVER skip directly to writing inline code without trying the script first.**

**For detailed parameter guidance and decision-making**, see:
- Algorithm selection: [references/decision-guide.md#algorithm](references/decision-guide.md#algorithm)
- Distance metrics: [references/decision-guide.md#distance](references/decision-guide.md#distance)
- Optimal k: [references/decision-guide.md#optimal-k](references/decision-guide.md#optimal-k)

## Common Issues

| Error | Cause | Solution |
|-------|-------|----------|
| `ValueError: n_clusters exceeds n_samples` | Too many clusters requested for dataset size | Reduce k or ensure data has ≥10 samples |
| `Ward linkage requires euclidean distance` | Incompatible linkage method and distance metric | Use euclidean distance with ward, or switch to average/complete linkage |
| `ModuleNotFoundError: No module named 'plotnine_prism'` | Missing optional visualization dependency | Install: `pip install plotnine-prism` |
| Silhouette score < 0.25 | Poor cluster separation, k may be wrong | Try different k values, check data quality, use optimal k methods |
| HDBSCAN returns only noise (-1 labels) | min_cluster_size too large for dataset | Reduce min_cluster_size (try 5-10 for small datasets) or increase min_samples |
| `ValueError: Input contains NaN` | Missing values in data matrix | Impute or remove NaN values before clustering |
| Clusters of very unequal sizes | Algorithm bias or true biological structure | Validate with biology; try HDBSCAN for density-based approach |
| Different runs give different clusters (k-means) | Random initialization varies | Increase n_init (50-100) for stable results, or use hierarchical clustering |

**Debugging checklist:**
1. Check data shape and missing values: `data.shape`, `np.isnan(data).sum()`
2. Verify normalization: Data should be comparable across features (z-scores, scaled)
3. Check cluster labels: Should range from 0 to k-1 (or include -1 for noise in HDBSCAN)
4. Validate with metrics: Silhouette >0.3 is decent, >0.5 is good
5. Inspect visually: PCA/UMAP plots should show clear groupings

## Decision Guide

Make three critical decisions before clustering:

| Decision | Quick Guide | Detailed Reference |
|----------|-------------|-------------------|
| **Algorithm** | Hierarchical (<5k samples, exploration), K-means (>5k, speed), HDBSCAN (unknown k, outliers), GMM (soft clustering) | [decision-guide.md#algorithm](references/decision-guide.md#algorithm) |
| **Distance** | Correlation (gene expression), Euclidean (normalized data), Manhattan (outliers), Cosine (sparse) | [decision-guide.md#distance](references/decision-guide.md#distance) |
| **Cluster # (k)** | Use multiple metrics (elbow, silhouette, gap), prioritize silhouette, consider biology | [decision-guide.md#optimal-k](references/decision-guide.md#optimal-k) |

**Comprehensive decision guidance:** [references/decision-guide.md](references/decision-guide.md)

## Common Patterns

**Pattern 1:** Sample Subtype Discovery - [references/common-patterns.md#pattern-1](references/common-patterns.md#pattern-1)
**Pattern 2:** Gene Co-clustering - [references/common-patterns.md#pattern-2](references/common-patterns.md#pattern-2)
**Pattern 3:** Method Comparison - [references/common-patterns.md#pattern-3](references/common-patterns.md#pattern-3)
**Additional:** QC/outlier detection, stability testing, batch validation - [references/common-patterns.md](references/common-patterns.md)

## Suggested Next Steps

After completing clustering:

1. **Differential Analysis** - Use bulk-rnaseq-counts-to-de-deseq2 to identify cluster-specific signatures
2. **Functional Enrichment** - Use functional-enrichment-from-degs to interpret cluster biology
3. **Refinement** - If unclear: try different metrics, adjust k, remove outliers, use variable features subset

## Related Skills

**Prerequisite:** bulk-rnaseq-counts-to-de-deseq2 (normalize RNA-seq data)
**Alternatives:** scrnaseq-scanpy-core-analysis, scrnaseq-seurat-core-analysis (single-cell), coexpression-network
**Downstream:** de-results-to-gene-lists, functional-enrichment-from-degs, de-results-to-plots

## References

**Reference documentation:**
- [references/decision-guide.md](references/decision-guide.md) - Comprehensive decision guidance (algorithm, distance, k)
- [references/common-patterns.md](references/common-patterns.md) - Additional use case patterns
- [references/clustering_methods_comparison.md](references/clustering_methods_comparison.md) - Algorithm selection guide
- [references/validation_metrics_guide.md](references/validation_metrics_guide.md) - Metric interpretation
- [references/distance_metrics_guide.md](references/distance_metrics_guide.md) - Distance metric selection
- [references/parameter_guide.md](references/parameter_guide.md) - Parameter tuning details
- [references/best_practices.md](references/best_practices.md) - Workflow best practices

**Python scripts:**
- [scripts/prepare_data.py](scripts/prepare_data.py) - Data loading and preprocessing
- [scripts/distance_metrics.py](scripts/distance_metrics.py) - Distance calculations
- [scripts/dimensionality_reduction.py](scripts/dimensionality_reduction.py) - PCA, UMAP
- [scripts/hierarchical_clustering.py](scripts/hierarchical_clustering.py) - Hierarchical methods
- [scripts/kmeans_clustering.py](scripts/kmeans_clustering.py) - K-means variants
- [scripts/density_clustering.py](scripts/density_clustering.py) - DBSCAN, HDBSCAN
- [scripts/model_based_clustering.py](scripts/model_based_clustering.py) - GMM
- [scripts/optimal_clusters.py](scripts/optimal_clusters.py) - Optimal k determination
- [scripts/cluster_validation.py](scripts/cluster_validation.py) - Quality metrics
- [scripts/stability_analysis.py](scripts/stability_analysis.py) - Bootstrap validation
- [scripts/characterize_clusters.py](scripts/characterize_clusters.py) - Feature importance
- [scripts/plot_clustering_results.py](scripts/plot_clustering_results.py) - Visualizations
- [scripts/export_results.py](scripts/export_results.py) - Export functions

**R scripts:**
- [scripts/hierarchical_clustering.R](scripts/hierarchical_clustering.R) - Hierarchical clustering with dendextend
- [scripts/plot_cluster_heatmap.R](scripts/plot_cluster_heatmap.R) - ComplexHeatmap visualization (recommended for publication figures)
- Additional R implementations available upon request

**Evaluation:**
- [eval/complete_example_analysis.py](eval/complete_example_analysis.py) - Full workflow example

**Online resources:**

*Python:*
- [scikit-learn clustering](https://scikit-learn.org/stable/modules/clustering.html)
- [HDBSCAN documentation](https://hdbscan.readthedocs.io/)

*R:*
- [factoextra clustering](https://rpkgs.datanovia.com/factoextra/)
- [ComplexHeatmap vignettes](https://jokergoo.github.io/ComplexHeatmap-reference/book/)
- [dendextend tutorial](https://cran.r-project.org/web/packages/dendextend/vignettes/dendextend.html)

**Key papers:**
- Rousseeuw (1987) - Silhouettes for cluster validation
- Tibshirani et al. (2001) - Gap statistic
- McInnes et al. (2017) - HDBSCAN algorithm
- D'haeseleer (2005) - Clustering in genomics


## 🔒 审查机制（rail_review）

本 skill 执行代码前**必须**调用  进行前置审查，执行后**必须**调用  进行后置审查。

### 审查内容
- **pre 审查**：环境检查（包是否安装）→ 参数校验（参数是否合理）→ 代码审查（语法/逻辑）→ 硬件检查（内存/GPU是否够）
- **post 审查**：结果质量评估（输出是否合理）→ 图表检查（图是否生成）→ 数值检查（细胞数/基因数是否异常）→ 错误检查（有无 warning/error）

### 审查不通过
- pre 不通过 → **阻断执行**，修正后重新审查
- post 不通过 → **阻断下一步**，修正后重跑，直到通过
- 失败时调用  记录错误
- 修复成功后调用  +  替换脚本


---

## 🔒 审查与辩论机制（分析 skill 必须执行）

### 执行前审查 (rail_review pre)
使用此 skill 的分析步骤前，**必须**调用 ：
- 检查环境：R/Python 版本、必需包是否安装
- 检查参数：参数来源（知识库/文献/辩论/经验），不能凭空设值
- 检查数据：输入数据格式、细胞数、维度是否合理
- 不通过则阻断，修正后重试

### 执行后审查 (rail_review post)
分析步骤完成后，**必须**调用 ：
- 检查输出：文件是否生成、大小是否合理
- 检查质量：QC 指标、聚类质量、注释置信度
- 检查图表：是否生成了预期图表、图表是否合理
- 不通过则阻断，修正后重试
- **失败时**：调用  记录错误
- **修复成功后**：调用  +  替换脚本

### 多角色辩论 (debate_analysis)
当遇到**不确定的参数选择或结果判断**时，**必须**调用 ：
- 正方 3 位专业编辑（各自独立，互相不知道）：生物学编辑 / 统计学编辑 / 生信编辑
- 反方 4 位专业编辑（各自独立，互相不知道，也看不到正方）：生物学编辑 / 统计学编辑 / 生信编辑 / 历史经验编辑
- 裁判编辑：看到所有 7 方论点，给出裁决 + 置信度（高/中/低）
- 上下文隔离：每个编辑独立 HTTP API 调用，messages 只有自己的 prompt
- 分科知识库：生物学编辑用 biology_kb / 统计学编辑用 statistics_kb / 生信编辑用 bioinfo_kb / 历史经验编辑用 history_errors
- 辩论结果自动归档到 results/.../log/debate_*.json

### 辩论触发场景
- 聚类分辨率选择（0.3 vs 0.5 vs 0.8 vs 1.2）
- QC 阈值设定（MT% 10% vs 15% vs 20%）
- 细胞类型注释争议（marker 不明显时）
- 归一化方法选择（SCT vs LogNormalize）
- 降维参数选择（PC 数量 10 vs 20 vs 30）
- 差异表达阈值（p<0.05 vs p<0.01, logFC 阈值）
- 任何需要多方审视的分析决策
---

## ⛔ Terminal 完成后强制协议（铁律 26）

```
1. rail_review(phase='post')
2. debate_analysis(
     topic="Bulk RNA-seq {DE/富集} 参数与结果 —— {对比组}",
     context="方法: {DESeq2/edgeR/limma} | 参数: FDR<{x} logFC>{y} | 结果: {n} DEGs",
     knowledge_base_info=<KB内容>,
   )
   辩论: 方法选对了吗？FDR/logFC阈值合理？DEG量在正常范围？p值校正方法对吗？
3. save_conclusions(module="02_basic"或"03_advanced", topic="Bulk DEG", ...)
4. skill_evolution(action="record_run")
5. 更新 task_plan.md
```

⛔ 不准一次跑完所有对比组。每对对比单独跑，单独辩论。
⛔ debate confidence=low → 调整参数重跑。
