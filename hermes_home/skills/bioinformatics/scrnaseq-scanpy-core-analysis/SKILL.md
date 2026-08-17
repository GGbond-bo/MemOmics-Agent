---
id: "skill_e4c50152a70f4d6fa8a4802573755f54"
name: "scrnaseq-scanpy-core-analysis"
when_to_use: "[scrnaseq-scanpy-core-analysis] Scanpy单细胞核心分析：10X数据→QC→归一化→HVG→PCA→邻居图→UMAP→Leiden聚类→marker→注释"
display-name: "Single-Cell RNA-seq Core Analysis (Scanpy)"
category: scRNA
short-description: "Complete single-cell RNA-seq analysis using Scanpy from raw data to cell type annotation with clustering and visualization."
detailed-description: "Complete single-cell RNA-seq analysis using Scanpy from raw data to cell type annotation. Use when you have 10X Chromium, Drop-seq, or other scRNA-seq data requiring QC, normalization, clustering, and visualization. Implements current best practices including ambient RNA correction (CellBender), batch-aware adaptive QC (MAD), doublet detection (Scrublet), standard or Pearson residuals normalization, batch integration (scVI/Harmony), multi-resolution Leiden clustering, and pseudobulk differential expression for condition comparisons. Best for human or mouse data with 500+ cells per sample. Produces publication-ready plots and annotated AnnData objects."
starting-prompt: "Analyze single-cell RNA-seq data with Scanpy from QC through cell type annotation. Generate a PDF report with an intro, methods, results, conclusions and figures from all of the analyses you perform."
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



# Single-Cell RNA-seq Core Analysis (Scanpy)

Complete workflow for single-cell RNA-seq analysis using Scanpy and the scverse ecosystem. Process raw data through quality control, normalization, clustering, and cell type annotation with publication-ready visualizations.

## When to Use This Skill

- **Analyze 10X Chromium data** (CellRanger output, H5 files, raw/filtered matrices)
- **Process Drop-seq, Smart-seq2, or inDrop** single-cell RNA-seq data
- **Integrate multi-batch data** using scVI, scANVI, or Harmony
- **Annotate cell types** manually or with automated reference-based methods
- **Compare conditions** using pseudobulk differential expression (multi-sample data)

**Don't use for:** Bulk RNA-seq (use bulk-rnaseq-counts-to-de-deseq2), R-based scRNA-seq (use scrnaseq-seurat-core-analysis), Spatial transcriptomics (coming soon)

## Installation

| Package | Version | License | Commercial Use | Installation |
|---------|---------|---------|----------------|--------------|
| scanpy | ≥1.9 | BSD-3-Clause | Permitted | `pip install scanpy` |
| anndata | ≥0.8 | BSD-3-Clause | Permitted | `pip install anndata` |
| numpy | ≥1.20 | BSD-3-Clause | Permitted | `pip install numpy` |
| pandas | ≥1.3 | BSD-3-Clause | Permitted | `pip install pandas` |
| matplotlib | ≥3.4 | PSF | Permitted | `pip install matplotlib` |
| seaborn | ≥0.12 | BSD-3-Clause | Permitted | `pip install seaborn` |
| adjustText | ≥0.8 | MIT | Permitted | `pip install adjustText` |
| scrublet | ≥0.2.3 | MIT | Permitted | `pip install scrublet` |
| scvi-tools | ≥1.0 | BSD-3-Clause | Permitted | `pip install scvi-tools` |
| harmonypy | ≥0.0.9 | GPL-3 | Permitted | `pip install harmonypy` |
| celltypist | ≥1.0 | MIT | Permitted | `pip install celltypist` |
| pydeseq2 | ≥0.4 | MIT | Permitted | `pip install pydeseq2` |

**Install all:** `pip install scanpy anndata numpy pandas matplotlib seaborn adjustText scrublet`

**Minimum versions:** Python ≥3.8, scanpy ≥1.9, anndata ≥0.8

## Inputs

**Required:**
- **Raw or filtered count matrix:** CellRanger output (`filtered_feature_bc_matrix/`), H5 files (`.h5`), AnnData (`.h5ad`), or count matrices (CSV/TSV)

**Optional:** Sample metadata (CSV/TSV) with sample IDs, conditions, batches, donor IDs

**Data requirements:** Min 500 cells/sample (1000+ recommended), Human or Mouse, UMI-based or read counts. See [references/qc_guidelines.md](references/qc_guidelines.md) for tissue-specific thresholds.

## Outputs

**Analysis objects:**
- `adata_processed.h5ad` - Complete annotated AnnData object
  - **Load with:** `import scanpy as sc; adata = sc.read_h5ad('adata_processed.h5ad')`
  - Contains: raw counts, normalized data, QC metrics, clusters, cell types, UMAP/PCA
  - **Note:** `adata.X` contains log-normalized (not scaled) data. Scaled data is used internally for PCA but not stored in .X. This is correct for downstream analysis (DE, visualization).
  - **Required for:** trajectory inference, cell-cell communication, downstream analyses

**Reports:**
- `scrna_analysis_report.pdf` - Agent-generated comprehensive PDF with Methods, Results, Figures, Conclusions
- `analysis_summary.txt` - Text summary of dataset, QC, clustering, integration (generated by `export_anndata_results()`)

**⚠️ PDF style rules:**
- **US Letter page size (8.5 × 11 in)** — always set page dimensions explicitly; do not rely on library defaults
- **No Unicode superscripts** — use `3.36e-06` or `3.36 × 10^(-6)`, not Unicode superscript chars (they render as ■ in PDF fonts)
- **No half-empty pages** — group headings with their content; only page-break before major sections (Results, Conclusions)
- **Figures ≥80% page width** — multi-panel figures must be large enough to read; never embed below 50% width

**Tables:** `cell_metadata.csv`, `expression_matrix_counts.csv`, `expression_matrix_normalized.csv`, `pca_coordinates.csv`, `umap_coordinates.csv`, `cluster_markers_all.csv`, `{celltype}_deseq2_results.csv`

**Visualizations (PNG + SVG at 300 DPI):** QC violins, UMAP plots, marker heatmaps, dot plots, volcano/MA plots

## Clarification Questions

**Default settings (use unless user specifies otherwise):**
- Format: Filtered 10X CellRanger output | Species: Human | Tissue: PBMC
- Normalization: Standard (target sum + log1p) | Clustering: Test 0.4, 0.6, 0.8, 1.0

### 1. **Input Files** (ASK THIS FIRST):
   - Do you have specific single-cell data file(s) to analyze?
   - Expected: CellRanger output, H5, H5AD, or count matrix
   - **Or use example/demo data?** (PBMC 3k dataset available)

### 2. **Data format and species:**
   - *(If using your own data)* What format? Filtered 10X (default), Raw 10X, H5, H5AD? Human or Mouse? Tissue type?
   - *(If using example data)* Defaults apply: filtered 10X, human, PBMC — skip to Q3

### 3. **Batch structure:**
   - a) Single sample (no integration needed)
   - b) Multiple batches (scVI recommended, Harmony for speed)

### 4. **Analysis scope:**
   - a) Standard: QC + normalize + cluster + annotate (recommended)
   - b) Standard + pseudobulk DE (requires ≥2 samples per condition)
   - c) Custom: specify which steps

### 5. **Clustering granularity:**
   - a) Coarse (0.3-0.5) — major cell types only
   - b) Standard (0.6-0.8) — recommended
   - c) Fine (1.0-1.5) — subtypes
   - d) Test multiple: 0.4, 0.6, 0.8, 1.0 (recommended)

## Standard Workflow

🚨 **MANDATORY: USE SCRIPTS EXACTLY AS SHOWN - DO NOT WRITE INLINE CODE** 🚨

**Detailed step-by-step code:** [references/workflow-details.md](references/workflow-details.md)

**CRITICAL - DO NOT:**
- Write inline analysis code → **STOP: Use the script functions**
- Write custom export code → **STOP: Use `export_anndata_results()`**
- Skip verification messages → **STOP: Check for "✓" messages after each step**

**IF SCRIPTS FAIL - Script Failure Hierarchy:**
1. **Fix and Retry (90%)** - Install missing package, re-run script
2. **Modify Script (5%)** - Edit the script file itself, document changes
3. **Use as Reference (4%)** - Read script, adapt approach, cite source
4. **Write from Scratch (1%)** - Only if genuinely impossible, explain why

**NEVER skip directly to writing inline code without trying the script first.**

---

**Step 1 — Load and QC** | [scripts/setup_and_import.py](scripts/setup_and_import.py), [scripts/qc_metrics.py](scripts/qc_metrics.py), [scripts/filter_cells.py](scripts/filter_cells.py)

```python
# Load data (Option A: example, Option B: your data)
from load_example_data import load_example_data
adata = load_example_data("pbmc3k")

# QC metrics + adaptive filtering + doublet detection
from qc_metrics import calculate_qc_metrics, batch_mad_outlier_detection
from filter_cells import run_scrublet_detection, filter_by_mad_outliers
adata = calculate_qc_metrics(adata, species="human")
adata = batch_mad_outlier_detection(adata, batch_key="batch")  # creates 'outlier' column
adata = run_scrublet_detection(adata, batch_key="batch")
adata = filter_by_mad_outliers(adata, remove_doublets=True)
```

**DO NOT write inline QC code.** Doublet rate auto-scales per batch (~0.8% per 1,000 cells). Aim for >70% cell retention. For raw data, prepend ambient RNA correction: [references/ambient_rna_correction.md](references/ambient_rna_correction.md)

**✅ VERIFICATION:** `"✓ Data loaded successfully!"` → QC metrics added → filtering summary with retention %.

**Step 2 — Normalize, reduce, integrate** | [scripts/normalize_data.py](scripts/normalize_data.py), [scripts/scale_and_pca.py](scripts/scale_and_pca.py), [scripts/integrate_scvi.py](scripts/integrate_scvi.py)

```python
from normalize_data import run_standard_normalization
from find_variable_genes import find_highly_variable_genes
from scale_and_pca import scale_data, run_pca_analysis
adata = run_standard_normalization(adata, target_sum=1e4)
adata = find_highly_variable_genes(adata, n_top_genes=2000)
adata = scale_data(adata, vars_to_regress=["total_counts", "pct_counts_mt"])
adata = run_pca_analysis(adata, n_pcs=50)

# Multi-batch: integration + 4 项铁轨评估（必输出）
from integrate_scvi import run_scvi_integration
from integration_diagnostics import compute_lisi_scores, compute_batch_asw, compute_kbet
adata = run_scvi_integration(adata, batch_key="batch", condition_key="condition")
lisi = compute_lisi_scores(adata, batch_key="batch", use_rep="X_scVI")
asw = compute_batch_asw(adata, batch_key="batch", cluster_key="leiden_0.8")
kbet = compute_kbet(adata, batch_key="batch", cluster_key="leiden_0.8")
# PC 方差贡献
sc.pl.pca_variance_ratio(adata, n_pcs=50, save="_scree.png")
```

**DO NOT write inline normalization or integration code.** The integration script auto-detects batch-condition confounding. [Details →](references/integration_methods.md)

**✅ VERIFICATION:**
- Normalization: `"✓ Normalization complete"`
- PCA: `"PCA loadings verified: N HVG rows have non-zero loadings"` — if you see a WARNING about zero loadings, re-run PCA with `use_highly_variable=True`
- After PCA, call `suggest_n_pcs(adata)` to get recommended PC count for Step 3
- Integration (multi-batch): 4 项集成质量评估 (LISI+ASW+kBET+PC方差) printed

**Step 3 — Cluster, annotate, visualize** | [scripts/cluster_cells.py](scripts/cluster_cells.py), [scripts/find_markers.py](scripts/find_markers.py), [scripts/annotate_celltypes.py](scripts/annotate_celltypes.py)

```python
from cluster_cells import build_neighbor_graph, cluster_leiden_multiple_resolutions
from run_umap import run_umap_reduction
from find_markers import find_all_cluster_markers
from plot_dimreduction import plot_umap_clusters
use_rep = "X_scVI" if "X_scVI" in adata.obsm else "X_pca"
# Default n_pcs=30 is standard. NEVER use <15 PCs.
adata = build_neighbor_graph(adata, use_rep=use_rep, n_neighbors=10, n_pcs=30)
adata = cluster_leiden_multiple_resolutions(adata, resolutions=[0.4, 0.6, 0.8, 1.0])
adata = run_umap_reduction(adata)
markers = find_all_cluster_markers(adata, cluster_key="leiden_0.8")
plot_umap_clusters(adata, cluster_key="leiden_0.8", output_dir="results/umap")

# Annotate (manual or CellTypist)
from annotate_celltypes import annotate_clusters_manual
annotations = {"0": "CD4 T cells", "1": "CD14+ Monocytes", ...}
adata = annotate_clusters_manual(adata, annotations, cluster_key="leiden_0.8")
```

**DO NOT write inline clustering or annotation code.** CellTypist validates labels post-hoc (flags suspect ILC/HSC, contamination, low-complexity). [Markers →](references/marker_gene_database.md)

**⚠️ n_pcs for neighbor graph:** Default is 30 PCs (standard). Using <15 PCs risks collapsing distinct populations. If you used `suggest_n_pcs()` in Step 2, pass that value here.

For **pseudobulk DE** (multi-sample, ≥2 replicates/condition): [scripts/pseudobulk_de.py](scripts/pseudobulk_de.py). Script blocks with N=1. [Details →](references/pseudobulk_de_guide.md)

**✅ VERIFICATION:**
- Cluster counts → UMAP plots saved → marker genes identified → cell type annotations added
- After `find_all_cluster_markers()`: verify the returned DataFrame columns and print `markers.head()` to confirm values are sensible before saving to CSV.

**Step 4 — Export results** | [scripts/export_results.py](scripts/export_results.py)

```python
from export_results import export_anndata_results

export_anndata_results(adata, output_dir="results", cluster_key="cell_type")
```

**DO NOT write custom export code. Use export_anndata_results().**

Exports: H5AD, expression matrices (raw + normalized CSV), cell metadata, UMAP/PCA coordinates, text summary.

**✅ VERIFICATION:** You MUST see:
```
=== Export Complete ===
```
**If you don't see "Export Complete":** The export did not complete. Re-run the export function.

**⚠️ Large datasets (>20k cells):** H5AD export may take 10-60 seconds depending on dataset size. The script prints progress updates (size estimate, compression method, elapsed time). If export appears stuck for >2 minutes, interrupt and retry with `save_h5ad(adata, path, compression=None)` to skip compression.

## Decision Guide

| Decision | Quick Guide | Reference |
|----------|-------------|-----------|
| **Ambient RNA** | Skip for filtered/PBMC. CellBender for raw/high-soup (brain, lung, tumor) | [ambient_rna_correction.md](references/ambient_rna_correction.md) |
| **QC Strategy** | MAD (multi-batch). Fixed (single batch, tissue-specific) | [qc_guidelines.md](references/qc_guidelines.md) |
| **Normalization** | Standard (most data). Pearson (heteroscedastic) | [scanpy_best_practices.md](references/scanpy_best_practices.md) |
| **Integration** | scVI (complex batches). Harmony (fast, simple) | [integration_methods.md](references/integration_methods.md) |
| **Resolution** | Test 0.4, 0.6, 0.8, 1.0. Choose by biology and stability | [scanpy_best_practices.md](references/scanpy_best_practices.md) |
| **Annotation** | Manual (accurate). CellTypist (fast). Both (validate) | [marker_gene_database.md](references/marker_gene_database.md) |

**Complete working examples:** [references/common-patterns.md](references/common-patterns.md)

## Common Issues

| Issue | Cause | Solution |
|-------|-------|----------|
| `ImportError: No module named 'scanpy'` | Not installed | `pip install scanpy anndata numpy pandas matplotlib seaborn` |
| Low cell retention (<70%) | Strict QC thresholds | Use MAD (nmads=5→7) or tissue-specific thresholds |
| Out of memory | Large dataset (>50k cells) | Use backed mode or subsample |
| Clusters driven by batch | Insufficient integration | Use scVI, increase n_latent, check confounding |
| Poor UMAP separation | Wrong parameters | Check PCA elbow, use 20-40 PCs, adjust n_neighbors |
| High MT% in all cells | Degradation or tissue-specific | Check distribution — bimodal: stricter filter; uniform: may be biological |
| `FileNotFoundError: barcodes.tsv.gz` | Wrong directory | Verify 10X output files present. Use `import_h5_data()` for .h5 |
| H5AD export hangs or is very slow | Large file write with compression | Normal for >50 MB files. Script uses fast `lzf` compression. If still slow, pass `compression=None` to `save_h5ad()`. |
| `NameError` after export interruption | Kernel restart lost variables | Re-run from Step 1 to restore `adata`. Export is idempotent — safe to re-run. |
| **batch_key 唯一值过多**（如 >100） | 误用了 barcode/obs_names 作为 batch 列 | **写代码前检查**：`adata.obs['<batch_key>'].nunique()`。正确值应为 sample/donor ID（通常 2-20）。已有 `sample_id (16,003 unique)` 先例 → 在 `adata.obs.columns` 中找正确列 |

**Expected warnings (not errors):**

| Warning | Meaning | Action |
|---------|---------|--------|
| SVG export failed | Optional SVG dependency unavailable | Normal — PNG always generated. Both created in most environments. |
| Detected doublet rate differs from expected | Scrublet threshold or pre-filtering | Inspect `adata.obs['doublet_score'].hist()`. Adjust threshold if needed. |
| Pseudobulk DE blocked: N=1 | Insufficient replicates | Need ≥2 per condition. Use cell-level Wilcoxon for exploratory only. |
| Batch-condition confounding | Condition has 1 sample | Clustering valid. Composition comparisons need caveats. |
| CellTypist labels suspect (ILC, HSC) | Automated misclassification | Cross-check markers. Relabel ILC→NK or HSC→Unassigned. |
| Multimodal data detected | RNA-only workflow on CITE-seq | Note in reports: "RNA modality only; ADT not analyzed." |

**Detailed troubleshooting:** [references/troubleshooting_guide.md](references/troubleshooting_guide.md)

## Suggested Next Steps

1. **Functional Enrichment** — functional-enrichment-from-degs for pathway analysis of DE results
2. **Trajectory Analysis** — PAGA, Palantir, or scVelo for developmental datasets
3. **Cell-Cell Communication** — CellPhoneDB, LIANA, or NicheNet for ligand-receptor interactions

## Related Skills

**Alternative:** scrnaseq-seurat-core-analysis (R-based) | **Downstream:** functional-enrichment-from-degs, de-results-to-plots, de-results-to-gene-lists | **Complementary:** bulk-omics-clustering, experimental-design-statistics

## References

1. **Scanpy:** Wolf FA, et al. (2018) *Genome Biol*. 19:15.
2. **Best Practices:** Luecken MD, Theis FJ. (2019) *Mol Syst Biol*. 15:e8746.
3. **Pseudobulk DE:** Squair JW, et al. (2021) *Nat Commun*. 12:5692.
4. **scVI:** Lopez R, et al. (2018) *Nat Methods*. 15:1053-1058.

**Detailed guides:** [workflow-details.md](references/workflow-details.md) | [common-patterns.md](references/common-patterns.md) | [scanpy_best_practices.md](references/scanpy_best_practices.md) | [qc_guidelines.md](references/qc_guidelines.md) | [integration_methods.md](references/integration_methods.md) | [pseudobulk_de_guide.md](references/pseudobulk_de_guide.md) | [marker_gene_database.md](references/marker_gene_database.md) | [troubleshooting_guide.md](references/troubleshooting_guide.md)

**Scripts:** [scripts/](scripts/) | **Evaluation:** [assets/eval/complete_example_analysis.py](assets/eval/complete_example_analysis.py)


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

**Scanpy 核心分析各子步骤 terminal 返回后，必须立即：**

```
1. rail_review(phase='post')
2. debate_analysis(
     topic="{步骤} 参数与结果 —— {样本}",
     context="数据: {细胞数}cells | 参数: {实际参数} | 结果: {输出摘要}",
     knowledge_base_info=<KB内容>,
   )
3. save_conclusions(module="02_basic", topic="{步骤}", ...)
4. skill_evolution(action="record_run", skill="scrnaseq-scanpy-core-analysis", ...)
5. 更新 task_plan.md
```

⛔ Scanpy 步骤必须逐个执行：不准在一次 terminal 中跑完所有步骤。
⛔ 每个子步骤都要辩论参数。
