---
name: scrna-qc
description: "质控+Doublet去除+Ambient RNA去除, 支持人/鼠, 自动推荐阈值"
version: 1.0.0
author: MemOmics
license: MIT
platforms: [windows, linux, macos]
metadata:
  hermes:
    tags: [qc, doublet, ambient-rna, scRNA-seq, 01_质控]
    difficulty: basic
    language: R+Python
    category: transcriptomics
prerequisites:
  r_packages: ["Seurat", "patchwork", "ggplot2", "dplyr"]
  python_packages: ["scanpy", "matplotlib", "harmonypy"]
---

# scRNA-seq质量控制

质控+Doublet去除+Ambient RNA去除, 支持人/鼠, 自动推荐阈值

适用场景: 所有scRNA-seq

分析步骤:
  - Read10X/ReadH5: Load 10X/Smart-seq2 data
  - QC metrics (mt/ribo): PercentageFeatureSet
  - Doublet removal: DoubletFinder/scDblFinder
  - Ambient RNA (SoupX): Correct ambient RNA
  - Filter cells: By nFeature/percent.mt
  - QC report + Violin: Before/after comparison

依赖包: ggplot2, matplotlib, harmonypy, Seurat, scanpy, patchwork, dplyr

难度: basic

触发提示: "对我的单细胞数据进行质控"

## When to Use

适用于: 所有scRNA-seq

## Step 0: Detect Data State (CRITICAL — do before any QC)

Before writing QC code, determine whether `adata.X` contains **raw counts** or **already-normalized values**. This changes which filters are valid.

**Detection checklist (Python/Scanpy):**
1. Check `adata.X.dtype` — `float32`/`float64` suggests normalized; `int` suggests raw
2. Sample values: `adata.X[:5,:10].toarray()` — if non-integer floats → normalized
3. Check `adata.raw is not None` — raw counts may be stored there
4. Check `adata.layers` for a `'counts'` key
5. Check `np.allclose(X.data, np.round(X.data))` — False → normalized
6. Sanity-check total_counts median: raw scRNA-seq typically 2,000–50,000+ UMIs; if median < 5,000 and values are floats → likely normalized

**If data is already normalized:**
- ✅ `n_genes_by_counts` filter still valid (gene detection unaffected by normalization)
- ✅ `pct_counts_mt` usable as relative reference (computed from normalized expression)
- ❌ Do NOT filter by `total_counts` / `n_counts` (normalized sums are not UMIs)
- ❌ Doublet detection (Scrublet/DoubletFinder) requires raw counts — skip if unavailable
- ❌ SoupX ambient RNA removal requires raw counts — skip if unavailable
- Note in QC report that data was pre-normalized and raw counts unavailable

## Pipeline

1. **Read10X/ReadH5**
   - Load 10X/Smart-seq2 data
   - Tool: `terminal`
2. **Step 0: Detect data state** (see above)
3. **QC metrics (mt/ribo)**
   - R: `PercentageFeatureSet` | Python: `sc.pp.calculate_qc_metrics`
   - Human mt genes: `MT-` prefix | Mouse: `mt-` prefix
   - Tool: `terminal`
4. **Doublet removal** (SKIP if data is normalized — requires raw counts)
   - DoubletFinder/scDblFinder (R) | Scrublet (Python)
   - Tool: `terminal`
5. **Ambient RNA (SoupX)** (SKIP if data is normalized — requires raw counts)
   - Correct ambient RNA
   - Tool: `terminal`
6. **Filter cells**
   - Raw data: filter by n_genes + n_counts + pct_mt
   - Normalized data: filter by n_genes + pct_mt ONLY (skip n_counts)
   - Tool: `terminal`
7. **Gene filter**
   - `min_cells=3` (remove genes in <3 cells)
8. **QC report + Violin**
   - Before/after comparison + by-group (age_group/sample_id) breakdown
   - Tool: `terminal`

## Parameters

### Standard QC thresholds (by species/tissue)

| Species | Tissue | min_genes | max_genes | max_pct_mt | min_counts | max_counts |
|---------|--------|-----------|-----------|------------|------------|------------|
| Human | Skeletal muscle | 200 | 6000 | 15% | 500 | 50000 |
| Human | Default | 200 | 6000 | 20% | 500 | 50000 |
| Mouse | Default | 200 | 6000 | 20% | 500 | 50000 |

> **Note**: Skeletal muscle cells have naturally high mitochondrial content — use 15% (not 10%) to avoid over-filtering. For normalized data, omit `min_counts`/`max_counts` columns entirely.

### Parameter adaptation priority
1. Literature values (search_knowledge + web_search for tissue-specific thresholds)
2. AGENTS.md project defaults
3. Official Scanpy/Seurat defaults
4. Tissue-specific adjustments (e.g., muscle mt% naturally higher)

| Parameter | Default | Notes |
|-----------|---------|-------|
| `r_packages` | Seurat, patchwork, ggplot2, dplyr | |
| `python_packages` | scanpy, matplotlib, seaborn, harmonypy | |
| `steps` | Detect data state → QC metrics → (Doublet) → (SoupX) → Filter → Gene filter → Report | |
| `gene_min_cells` | 3 | Remove genes detected in <3 cells |

## Proven Scripts

> Scripts that have been successfully executed and passed analysis review.
> These are automatically saved after successful runs.

| Species | Tissue | Condition | Date | Score | Script |
|---------|--------|-----------|------|-------|--------|
| Human | Skeletal muscle | Aging (Young vs Old) | 2026-07-02 | PASS (58/58 checks) | `scripts/scanpy_qc_normalized.py` |

> See also: `references/normalized_data_detection.md` for the detection technique.

## Common Issues

| Error | Cause | Solution |
|-------|-------|----------|
| `TypeError: Axes.violinplot() got an unexpected keyword argument 'showextremes'` | matplotlib ≥3.9 removed `showextremes` param entirely (even `=False` crashes) | Remove `showextremes` from all `ax.violinplot()` calls; use `showmedians=True` only |
| `FutureWarning: Use scanpy.set_figure_params instead` | scanpy renamed `sc.settings.set_figure_params` | Use `sc.settings.set_figure_params(...)` (warning only, still works) |
| QC filter removes 0% cells | Data was already pre-filtered/QC'd upstream (common for annotated h5ad from public datasets) | Expected behavior — document in QC report, proceed to next step |
| `pct_counts_mt` very low (<5%) on muscle data | Data is normalized or pre-filtered | Check Step 0 data detection; low mt% confirms upstream QC was done |

## References

- Source: MemOmics built-in
- Category: transcriptomics
- Language: R+Python


## Reference Script (from External Skill)

> Auto-imported from external skill `29_scrnaseq-seurat-core-analysis`.
> This script is a verified reference implementation, NOT a run.py template.
> The agent can use it as a starting point or fetch official docs for the latest version.

- **Source**: `skills/external/29_scrnaseq-seurat-core-analysis/scripts/`
- **Imported scripts**: qc.R, filter_cells.R
