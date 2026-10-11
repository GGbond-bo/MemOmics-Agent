# Workflow Details

Extended code examples and guidance for each phase of the drug discovery pipeline.

## Phase 1: Data Loading

### Loading pre-annotated h5ad (from scrnaseq-scanpy-core-analysis)

```python
from load_data import load_annotated_h5ad
adata = load_annotated_h5ad("adata_processed.h5ad",
                             celltype_key="cell_type",
                             condition_key="condition",
                             sample_key="sample_id")
```

The function auto-resolves common column name variants (celltype, CellType, annotation, etc.). If your h5ad uses different names, specify them explicitly.

### Sample selection: Use ALL samples

**Critical rule: Use ALL available biological samples.** Statistical power for pseudobulk DE depends on the number of biological replicates, not the total cell count. Dropping samples to reduce dataset size directly reduces power.

**Subsample CELLS within samples, not samples themselves:**

```python
# Good: keeps all samples, caps cells per cell_type x condition
target_per_group = 3000  # cells per cell_type x condition
groups = adata.obs.groupby(["cell_type", "condition"])
keep = groups.apply(lambda x: x.sample(min(len(x), target_per_group), random_state=42))
adata = adata[keep.index.get_level_values(-1)].copy()
```

```python
# BAD: drops entire samples (loses biological replicates)
samples = adata.obs["sample_id"].unique()[:50]  # DON'T DO THIS
adata = adata[adata.obs["sample_id"].isin(samples)]  # Loses power
```

**For GSE195452 specifically:** The dataset has 727 amplification batches but only ~165 patients. Use `patient_id` for pseudobulk grouping, not `Amp_batch_ID`. Each patient has ~4 batches, so patient-level aggregation gives ~165 pseudobulk replicates vs 727 sparse batches.

**Why not a flat cell cap?** With 16 cell types x 2 conditions = 32 groups, a 30K cap gives ~940 cells per group. For plate-based data with 500+ samples, that's 1-2 cells per sample — too sparse for pseudobulk DE.

### Smart-seq2 vs 10X considerations

| Feature | 10X Chromium | Smart-seq2 / Plate-based |
|---------|-------------|--------------------------|
| Cells per sample | 1000-10000 | 100-384 |
| Samples | 5-20 | 50-700 |
| min_cells for pseudobulk | 10 (default) | 3-5 (lower) |
| Subsampling needed? | Usually no (<50K) | Often yes (>100K total) |
| Gene detection | Shallow (3' bias) | Deep (full-length) |

## Phase 2a: Differential Expression

### DESeq2 input validation

**Critical:** DESeq2 requires raw integer counts, NOT log-normalized data.

The script auto-detects `adata.layers["counts"]` if present. If not, it checks whether `.X` looks like counts (integers) or log-normalized (decimals). Always pass `layer="counts"` explicitly when available:

```python
de_results = run_pseudobulk_de(adata, reference="Healthy", layer="counts")
```

### Handling failed cell types

When DESeq2 produces degenerate results (all padj = 1.0, usually from too few pseudobulk replicates), the script:
1. Detects the failure (padj range < 0.01, 0 genes with padj < 0.1)
2. Automatically falls back to cell-level Wilcoxon DE for that cell type
3. Marks results with `de_method = "wilcoxon_fallback"`

No manual intervention needed.

## Phase 2b: Pathway Enrichment

### GSEA ranking metric

Default: `sign(log2FC) x -log10(padj)` — combines effect size and significance.

Why this matters: Using log2FC alone (legacy default) ranks genes by fold-change magnitude regardless of statistical confidence. Genes with padj=1.0 and high noise-driven fold-changes dominate the ranking, producing spurious GSEA results.

### GSEA quality gate

The script automatically skips cell types where:
- DE returned 0 significant genes at padj < 0.05
- padj range is < 0.01 (all padj values are essentially identical = degenerate)

This prevents the artifact where GSEA shows FDR=0 pathways for cell types with no real DE signal.

## Phase 2c: Ligand-Receptor Analysis

LIANA runs multiple methods (CellPhoneDB, NATMI, Connectome, log2FC) and produces a consensus ranking.

**Runtime:** 10-30 minutes for >10K cells with 10+ cell types. Partial results are saved after each step (consensus ranking, condition comparison, disease-relevant pairs) so progress is not lost on interruption.

## Phase 2e: Genetic Evidence

### Evidence hierarchy

1. **Open Targets GWAS/ClinVar/gene burden** — primary. Disease-specific (e.g., SSc EFO_0000717). For SSc: 110 genes with genetic evidence including IRF5, STAT4, CD247, TYK2.
2. **GeneBass** — best when disease has UK Biobank burden test results. SSc is too rare (0 hits).
3. **TWAS Atlas** — disease-specific terms only (no proxy diseases).
4. **eQTL Catalogue** — skin/immune tissue eQTLs, filtered at p < 0.05.
5. **Open Targets L2G** — ML gene prioritization at GWAS loci.

### When GeneBass has no hits

The skill automatically uses Open Targets Disease Genetics as the primary source. No proxy diseases (e.g., RA, lupus) are used. This gives disease-specific genetic evidence even for rare diseases.

## Phase 2b: GSEA Thresholds

Two FDR thresholds are used intentionally:

- **GSEA output tables:** FDR < 0.25 — standard GSEA reporting threshold. Includes all pathways for exploration and heatmap visualization.
- **Target scoring (pathway_score):** FDR < 0.05 — stricter threshold. Only robustly enriched pathways contribute to composite target scores.

This dual-threshold approach lets users explore broad pathway trends in the report while ensuring target scoring is conservative.

## Phase 3: Target Scoring

### Adaptive reweighting

If L-R interactions or genetic evidence is unavailable, those component weights are redistributed to the remaining components (weights always sum to 1.0). The skill never penalizes targets for missing data dimensions.

### Cross-compartment analysis

GWAS hits are often immune genes (IRF5, STAT4) while DE hits are fibroblast genes. These don't overlap directly, but may be connected through L-R interactions:

- If a GWAS gene (e.g., IRF5 in macrophages) is a ligand source in L-R interactions targeting fibroblasts → its fibroblast receptor partner gets a 10% cross-compartment bonus
- If a DE gene (e.g., TGFBR1 in fibroblasts) has L-R partners with genetic evidence → it gets the same bonus

This bridges the immune-fibroblast disconnect in SSc.

### Druggability auto-query

When `score_targets()` is called without `ot_annotations`, it automatically queries Open Targets for the top 50 candidate genes. This ensures druggability is always included in the composite score, even if the agent doesn't explicitly call `query_target_annotations()`.

### Convergence bonus

Targets with BOTH genetic evidence (OT score > 0 or GeneBass p < 1e-4) AND transcriptomic evidence (DE score > 0.3) receive a 1.2x multiplier on their composite score.
