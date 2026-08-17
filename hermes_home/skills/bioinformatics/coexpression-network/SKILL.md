---
id: "skill_4aec92a664ad4b63baaf2b4981daa277"
name: "coexpression-network"
when_to_use: "[coexpression-network] 需使用coexpression network功能，适用于相关生信分析场景"
display-name: "Weighted Gene Co-expression Network Analysis (WGCNA)"
category: Multi-omics
short-description: Build gene co-expression networks to identify modules and hub genes from RNA-seq data.
detailed-description: |
  Performs weighted gene co-expression network analysis (WGCNA) to identify modules of coordinately
  expressed genes and hub genes within those modules. Takes normalized RNA-seq count matrices,
  constructs scale-free co-expression networks, detects modules using hierarchical clustering,
  correlates modules with sample traits, and identifies hub genes. Best for: finding gene regulatory
  networks, identifying key genes driving biological processes, relating gene groups to phenotypes.
  Requires ≥15 samples (20+ recommended) and 5,000-15,000 most variable genes.
starting-prompt: Build a co-expression network to identify gene modules and hub genes from my RNA-seq data . .
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



# Weighted Gene Co-expression Network Analysis (WGCNA)

## Overview

Build weighted gene co-expression networks to identify modules of coordinately expressed genes and discover hub genes that may be key regulators. This workflow uses WGCNA (Weighted Gene Co-expression Network Analysis) to group genes into modules based on their expression patterns across samples, then correlates these modules with experimental conditions or traits.

**Key Concept:** Unlike single-gene analysis, WGCNA identifies groups of genes that behave similarly across samples, revealing biological pathways and potential regulatory relationships.

**Use Cases:**
- Identify gene modules associated with experimental conditions
- Discover hub genes (highly connected genes within modules)
- Find genes with similar expression patterns to known genes of interest
- Reduce dimensionality of gene expression data for downstream analysis
- Generate hypotheses about gene function based on co-expression

**Default Prompt:** "Build a co-expression network to identify gene modules and hub genes from my RNA-seq data"

## When to Use This Skill

Use WGCNA when you want to:

- **Identify gene modules** associated with experimental conditions or phenotypes
- **Discover hub genes** that are highly connected within modules and may be key regulators
- **Find co-expressed genes** with similar expression patterns to known genes of interest
- **Reduce dimensionality** of large gene expression datasets for downstream analysis
- **Generate hypotheses** about gene function based on co-expression patterns

**Requirements:**
- ≥15 samples (20+ recommended for robust results)
- Normalized expression data (VST, rlog, TPM, or FPKM - NOT raw counts)
- 5,000-15,000 most variable genes
- Batch effects removed or corrected

**Not suitable for:**
- Small sample sizes (<15 samples) - consider alternative approaches
- Raw count data - normalize first using DESeq2 or similar
- Data with uncorrected batch effects - correct before WGCNA

---

## Installation

**Core WGCNA packages:**
```r
if (!requireNamespace("BiocManager", quietly = TRUE))
    install.packages("BiocManager")

BiocManager::install("WGCNA")
```

**Visualization packages:**
```r
install.packages(c("ggplot2", "ggprism"))
BiocManager::install("ComplexHeatmap")
```

**Enrichment analysis (optional):**
```r
BiocManager::install(c("clusterProfiler", "org.Hs.eg.db"))  # Human
# BiocManager::install("org.Mm.eg.db")  # Mouse
# BiocManager::install("org.Rn.eg.db")  # Rat
```

| Software | Version | License | Commercial Use | Installation |
|----------|---------|---------|----------------|--------------|
| WGCNA | ≥1.70 | GPL-2+ | ✅ Permitted | `BiocManager::install('WGCNA')` |
| ggplot2 | ≥3.3.0 | MIT | ✅ Permitted | `install.packages('ggplot2')` |
| ComplexHeatmap | ≥2.10.0 | MIT | ✅ Permitted | `BiocManager::install('ComplexHeatmap')` |
| clusterProfiler | ≥4.0.0 | Artistic-2.0 | ✅ Permitted | `BiocManager::install('clusterProfiler')` |

---

## Inputs

**Required:**
1. **Normalized expression matrix** (CSV/TSV):
   - Rows: Genes, Columns: Samples
   - Values: VST, rlog, TPM, or FPKM (NOT raw counts)
   - 5,000-15,000 most variable genes recommended

2. **Sample metadata** (CSV/TSV):
   - Sample IDs matching expression matrix columns
   - Traits/conditions for module-trait correlation

**Optional:**
- Differential expression results (to highlight DEGs)
- Gene annotations for enrichment analysis

**Data Requirements:**
- ≥15 samples (20+ recommended)
- Batch effects removed or corrected
- No missing values in expression matrix

---

## Outputs

**CSV Files:**
1. **`wgcna_gene_modules.csv`** - Gene-module assignments with connectivity metrics
2. **`wgcna_hub_genes.csv`** - Top hub genes per module
3. **`wgcna_module_trait_cor.csv`** - Module-trait correlations with p-values
4. **`wgcna_eigengenes.csv`** - Module eigengene values per sample
5. **`wgcna_report.md`** - Summary report with interpretation

**Plots (PNG + SVG):**
6. **`soft_power_selection.png/.svg`** - Power selection diagnostic plot
7. **`module_dendrogram.png/.svg`** - Gene dendrogram with module colors
8. **`module_trait_correlation.png/.svg`** - Module-trait heatmap
9. **`eigengene_heatmap.png/.svg`** - Module eigengene expression patterns
10. **`hub_genes_barplot.png/.svg`** - Hub genes by connectivity

**Analysis Objects (RDS):**
11. **`wgcna_network.rds`** - Complete network object from blockwiseModules
    - Load with: `net <- readRDS('wgcna_network.rds')`
    - Required for: module preservation analysis, advanced network visualization
12. **`wgcna_module_colors.rds`** - Module color assignments per gene
    - Load with: `colors <- readRDS('wgcna_module_colors.rds')`
    - Required for: downstream module-specific analyses
13. **`wgcna_expression_matrix.rds`** - Filtered expression matrix used for analysis
    - Load with: `expr <- readRDS('wgcna_expression_matrix.rds')`
    - Required for: reanalysis, module preservation testing
14. **`wgcna_full_results.rds`** - Complete results object with all components
    - Load with: `results <- readRDS('wgcna_full_results.rds')`
    - Required for: replotting, additional analyses

**Key Metrics:**
- `module`: Module color assignment (grey = unassigned)
- `kWithin`: Intramodular connectivity (higher = more connected)
- `MM`: Module membership (correlation with eigengene)
- `hub_score`: Combined connectivity metric (MM × kWithin)

---

## Clarification Questions

1. **Input Files** (ASK THIS FIRST):
   - Do you have specific normalized expression data and sample metadata files to analyze?
   - If uploaded: Are these the expression matrix and metadata you'd like to analyze?
   - Expected formats: CSV or TSV with genes as rows, samples as columns
   - **Or use example data?** Female mouse liver dataset (135 samples, liver tissue, multiple traits)

2. **What is your normalized expression data format?**
   - VST (variance stabilizing transformation) from DESeq2
   - rlog (regularized log) from DESeq2
   - TPM (transcripts per million)
   - FPKM/RPKM
   - If unsure or raw counts: normalize first using DESeq2

3. **How many samples do you have?**
   - 15-30 samples (minimum for WGCNA, results may be less robust)
   - 30-50 samples (good power for network detection)
   - 50+ samples (excellent power, most reliable results)

4. **What traits/conditions do you want to correlate with modules?**
   - Treatment vs control (binary)
   - Disease status or phenotype
   - Continuous variables (age, dose, time, weight)
   - Multiple traits (all will be tested)

5. **Gene filtering strategy?**
   - Top 5,000 most variable genes (default, recommended)
   - Top 10,000-15,000 genes (for larger datasets)
   - All genes passing expression threshold
   - Pre-filtered gene list (e.g., from DE analysis)

---

## Standard Workflow

🚨 **MANDATORY: USE SCRIPTS EXACTLY AS SHOWN - DO NOT WRITE INLINE CODE** 🚨

**Step 1 - Load data:**
```r
library(WGCNA)
allowWGCNAThreads()

source("scripts/load_example_data.R")
wgcna_data <- load_example_wgcna_data()
datExpr <- wgcna_data$datExpr
meta <- wgcna_data$meta

# For your own data:
# source("scripts/prepare_wgcna_data.R")
# data <- prepare_wgcna_data("expression.csv", "metadata.csv", top_n_genes = 5000)
# datExpr <- data$datExpr
# meta <- data$meta
```

**Step 2 - Run WGCNA analysis:**
```r
source("scripts/wgcna_workflow.R")
results <- run_wgcna_analysis(
  datExpr,
  meta,
  traits = c("weight_g", "Glucose_mg_dl"),  # Adjust to your traits
  organism = "mouse"  # or "human", "rat", or NULL to skip enrichment
)
```
**DO NOT write inline WGCNA code. Just source the script.**

**Step 3 - Generate visualizations:**
```r
source("scripts/plot_all_wgcna.R")
plot_all_wgcna(results, output_dir = "wgcna_results")
```
🚨 **DO NOT write inline plotting code (png, svg, plotDendroAndColors, etc.). Just use the script.** 🚨

**The script handles PNG + SVG export with graceful fallback for SVG dependencies.**

**Step 4 - Export results:**
```r
source("scripts/export_wgcna_results.R")
export_all(results, output_dir = "wgcna_results")
```
**DO NOT write custom export code. Use export_all().**

**✅ VERIFICATION - You should see:**
- After Step 1: `"✓ Successfully loaded female mouse liver dataset"`
- After Step 2: `"✓ WGCNA analysis completed successfully!"`
- After Step 3: `"✓ All WGCNA plots generated successfully!"`
- After Step 4: `"=== Export Complete ==="`

⚠️ **CRITICAL - DO NOT:**
- ❌ **Write inline WGCNA code** → **STOP: Use `source("scripts/wgcna_workflow.R")`**
- ❌ **Write inline plotting code (png, svg, plotDendroAndColors, etc.)** → **STOP: Use `plot_all_wgcna()`**
- ❌ **Write custom export code** → **STOP: Use `export_all()`**
- ❌ **Try to install svglite** → script handles SVG fallback automatically
- ❌ Use absolute paths like `/mnt/knowhow/` → use relative paths `scripts/`
- ❌ Skip soft power selection → required for scale-free topology
- ❌ Use raw counts → normalize first with DESeq2 VST or rlog

**⚠️ IF SCRIPTS FAIL - Script Failure Hierarchy:**
1. **Fix and Retry (90%)** - Install missing package, re-run script
2. **Modify Script (5%)** - Edit the script file itself, document changes
3. **Use as Reference (4%)** - Read script, adapt approach, cite source
4. **Write from Scratch (1%)** - Only if genuinely impossible, explain why

**NEVER skip directly to writing inline code without trying the script first.**

**What the scripts provide:**
- [scripts/load_example_data.R](scripts/load_example_data.R) - Auto-fetch tutorial data (~135 samples)
- [scripts/prepare_wgcna_data.R](scripts/prepare_wgcna_data.R) - Load and filter your data
- [scripts/wgcna_workflow.R](scripts/wgcna_workflow.R) - Complete WGCNA analysis (power selection, network building, module-trait correlation, hub genes, enrichment)
- [scripts/plot_all_wgcna.R](scripts/plot_all_wgcna.R) - All publication-quality plots (PNG + SVG)
- [scripts/plotting_helpers.R](scripts/plotting_helpers.R) - Plot saving functions **with automatic SVG fallback handling**
- [scripts/export_wgcna_results.R](scripts/export_wgcna_results.R) - Export results and analysis objects

---

## Parameter Customization

**When customization is needed:**

- **Soft power selection:** Read [references/parameter-tuning-guide.md](references/parameter-tuning-guide.md) to understand how to choose appropriate power values for your data
- **Module detection parameters:** See [references/parameter-tuning-guide.md#module-detection](references/parameter-tuning-guide.md) for guidance on min_module_size and merge_cut_height
- **Complete custom workflow:** Read [references/wgcna-reference.md](references/wgcna-reference.md) for detailed code examples with explanations (only if you need full control)

---

## Common Issues

| Issue | Cause | Solution |
|-------|-------|----------|
| Too few samples error | <15 samples | WGCNA requires ≥15 samples; combine replicates or use alternative methods |
| Scale-free R² never exceeds 0.75 | Batch effects or poor data quality | Check for batch effects; try different normalization; inspect PCA |
| All genes assigned to grey module | minModuleSize too large or poor gene filtering | Lower minModuleSize to 20-30; increase top_n_genes to 10,000-15,000 |
| No significant module-trait correlations | Weak biological signal or incorrect traits | Check trait coding (numeric for continuous, 0/1 for binary); try more samples |
| Soft power recommended is very high (>20) | Data not suitable for scale-free network | Check normalization; consider signed vs unsigned network |
| Hub gene identification fails | Module colors not provided correctly | Ensure module_colors matches gene order in datExpr |
| Enrichment analysis returns no results | Wrong organism or gene ID format | Verify organism parameter matches data; convert gene IDs if needed |
| Memory errors during network construction | Too many genes | Reduce to 5,000-10,000 most variable genes; increase RAM |

---

## Interpretation Guidelines

**Module colors:**
- Each color = distinct co-expression module
- **Grey** = genes not assigned to any module
- Larger modules may represent broader biological processes

**Hub genes:**
- High `kWithin` = highly connected within module
- High `MM` = strong correlation with module eigengene
- Hub genes are candidates for experimental validation

**Module-trait correlations:**
- **|r| > 0.5 and p < 0.05** = significant association
- Positive correlation = module genes increase with trait
- Negative correlation = module genes decrease with trait
- Focus on modules with strongest associations

---

## Suggested Next Steps

After identifying modules and hub genes:

1. **Functional validation** - Validate hub genes experimentally (qPCR, knockdown, overexpression)
2. **Enrichment analysis** - Test modules for GO/KEGG enrichment to understand biological processes
3. **Compare with DE results** - Overlay DE genes on network to see which modules are enriched
4. **Network visualization** - Export to Cytoscape for detailed network visualization
5. **Cross-dataset validation** - Test module preservation in independent datasets

---

## Related Skills

- **[bulk-rnaseq-counts-to-de-deseq2](../bulk-rnaseq-counts-to-de-deseq2/)** - Normalize counts and perform differential expression analysis (run before WGCNA)
- **[de-results-to-gene-lists](../de-results-to-gene-lists/)** - Extract gene lists from DE results to overlay on network
- **[functional-enrichment-from-degs](../functional-enrichment-from-degs/)** - Perform GO/KEGG enrichment on modules

---

## References

**Documentation:**
- [WGCNA Best Practices Guide](references/wgcna-best-practices.md) - Comprehensive guide on data preparation, QC, and troubleshooting
- [Parameter Tuning Guide](references/parameter-tuning-guide.md) - Detailed parameter selection guidance
- [WGCNA Reference](references/wgcna-reference.md) - Complete code examples with explanations
- [Troubleshooting Guide](references/troubleshooting.md) - Common errors and solutions

**Example Data:**
- [Example Datasets](assets/eval/datasets/example_datasets.md) - Public datasets for WGCNA analysis

**Key Papers:**
- [Key WGCNA Papers](assets/eval/papers/key_papers.md) - Essential publications
- Langfelder & Horvath (2008). WGCNA: an R package for weighted correlation network analysis. *BMC Bioinformatics*. doi:10.1186/1471-2105-9-559
- Zhang & Horvath (2005). A general framework for weighted gene co-expression network analysis. *Statistical Applications in Genetics and Molecular Biology*. doi:10.2202/1544-6115.1128


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
     topic="{当前分析} 参数与结果 —— {样本}",
     context="参数: {实际参数} | 结果: {输出摘要}",
     knowledge_base_info=<KB内容>,
   )
3. save_conclusions(module="{模块}", topic="{分析名}", ...)
4. skill_evolution(action="record_run")
5. 更新 task_plan.md
```

⛔ 未完成以上 5 步 = 禁止启动下一个分析步骤。
⛔ debate confidence=low → 调整参数重跑。
