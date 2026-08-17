# snRNA-seq QC Pitfalls — MAD Filtering and Parameter Selection

Session-derived reference for single-nucleus RNA-seq quality control, focusing on
pitfalls that differ from standard scRNA-seq workflows.

---

## 1. The percent.mt MAD Trap

### Problem

When applying batch-aware MAD (Median Absolute Deviation) outlier detection to
snRNA-seq data, including `percent.mt` in the metrics list causes massive
over-filtering of healthy cells.

**Mechanism:**
- snRNA-seq nuclei have very little mitochondrial RNA (no cytoplasm)
- Typical values: median MT% = 0.3-0.5%, max = 3-5%
- MAD scale = median(|x - median(x)|) → becomes tiny (0.1-0.3%)
- nmads=3 upper threshold = median + 3×MAD = 0.38% + 3×0.15% ≈ 0.83%
- Cells with MT% of 1-2% (perfectly healthy) get flagged as outliers

**Observed impact (2026-07-02 session, human skeletal muscle snRNA-seq):**

| Configuration | Cells removed | % removed | Problem |
|--------------|--------------|-----------|---------|
| Fixed only (MT%<15%, nCount≥500) | 5 | 0.02% | MT% threshold useless (max was 3.06%) |
| Fixed + MAD(nmads=5, all 3 metrics) | 1,432 | 4.77% | Moderate but MT% MAD questionable |
| Fixed (MT%<5%, nCount≥1000) + MAD(nmads=3, all 3 metrics) | 4,342 | 14.48% | **Too aggressive** — MT% MAD removed 3,000+ healthy cells |
| Fixed (MT%<5%, nCount≥1000) + MAD(nmads=3, **nFeature+nCount only**) | 1,232 | 4.11% | ✅ Optimal — MT% by fixed threshold only |

### Solution

**Exclude `percent.mt` from MAD metrics for snRNA-seq.** Use fixed threshold for MT%,
MAD only for nFeature_RNA and nCount_RNA.

```r
# ❌ WRONG — includes percent.mt, creates sub-1% thresholds
seurat_obj <- batch_mad_outlier_detection(
  seurat_obj,
  batch_col = "sample_id",
  metrics = c("nFeature_RNA", "nCount_RNA", "percent.mt"),
  nmads = 3
)

# ✅ CORRECT — MT% by fixed threshold only, MAD on nFeature+nCount
seurat_obj <- batch_mad_outlier_detection(
  seurat_obj,
  batch_col = "sample_id",
  metrics = c("nFeature_RNA", "nCount_RNA"),
  nmads = 3
)
# Then apply fixed MT% filter separately:
seurat_filtered <- filter_cells_by_qc(
  seurat_obj,
  min_features = 200, max_features = 6000,
  max_mt_percent = 5,  # snRNA-seq: 5%, not 15-20%
  min_counts = 1000, max_counts = 50000
)
```

### When to apply this

- **snRNA-seq** (single-nucleus): median MT% < 1%, max < 5% → **exclude MT% from MAD**
- **scRNA-seq** (single-cell): median MT% > 5% → MAD on MT% is fine
- **Uncertain**: check `median(percent.mt)` — if < 1%, treat as snRNA-seq

---

## 2. snRNA-seq vs scRNA-seq Thresholds

| Parameter | scRNA-seq | snRNA-seq | Rationale |
|-----------|-----------|-----------|-----------|
| max_pct_mt | 15-20% | 5% | Nuclei have minimal mitochondria |
| min_counts | 500 | 1000 | snRNA-seq has lower capture; but 500 too low (noise) |
| max_counts | 50000 | 50000 | Same — doublet prevention |
| MAD metrics | nFeature + nCount + MT% | nFeature + nCount only | MT% MAD unstable at low values |
| MAD nmads | 3-5 | 3 | 5 too loose for pre-filtered data; 3 standard |

---

## 3. h5ad → Seurat Conversion (R anndata package)

Seurat does not have `ReadH5AD()`. Use the R `anndata` package:

```r
library(anndata)
library(Seurat)
library(Matrix)

# Read h5ad
adata <- read_h5ad("path/to/data.h5ad")

# Convert counts: adata$X is cells × genes, Seurat needs genes × cells
# CRITICAL: keep sparse to avoid 12+ GB dense allocation
counts_mat <- as(adata$X, "CsparseMatrix")  # NOT as.matrix()!
counts_mat <- t(counts_mat)
rownames(counts_mat) <- adata$var_names
colnames(counts_mat) <- adata$obs_names

# Extract metadata
meta_data <- as.data.frame(adata$obs)

# Create Seurat object
seurat_obj <- CreateSeuratObject(
  counts = counts_mat,
  meta.data = meta_data
)
```

### Common errors during conversion

| Error | Cause | Fix |
|-------|-------|-----|
| `ReadH5AD not found` | Seurat doesn't have this function | Use `anndata::read_h5ad()` |
| `sparse->dense coercion: allocating vector of size 12.3 GiB` | `as.matrix(adata$X)` densifies the full matrix | Use `as(adata$X, "CsparseMatrix")` |
| `sprintf("%d", nCount_RNA) — format invalid` | `nCount_RNA` is numeric (double), not integer | Use `%.0f` instead of `%d` |
| `Feature names cannot have underscores` | Seurat replaces `_` with `-` in feature names | Warning only, but note for downstream matching |

---

## 4. Debate-Driven Parameter Evolution

This session's QC parameters evolved through 2 rounds of `debate_analysis`:

### Round 1: Initial parameters → Modified
- **Initial**: MT%<15%, nCount≥500, nmads=5 (all 3 metrics)
- **Debate verdict**: "modify" (con 8:6 pro)
- **Issues raised**:
  - MT%<15% is useless for snRNA-seq (max was 3.06%)
  - nCount≥500 too low (median is 2190)
  - nmads=5 too loose
- **Adjusted to**: MT%<5%, nCount≥1000, nmads=3

### Round 2: nmads=3 with all metrics → Modified again
- **Second run**: MT%<5%, nCount≥1000, nmads=3 (all 3 metrics)
- **Debate verdict**: "modify" (con 9:6 pro)
- **Issues raised**:
  - 14.48% removal rate too high for pre-filtered data
  - MT% MAD creates thresholds <1%, mislabels healthy cells
  - Fixed threshold only removed 6 cells — almost all removal from MAD on MT%
- **Adjusted to**: Exclude percent.mt from MAD metrics entirely

### Lesson
When QC removes an unexpectedly high percentage of cells and the removal is
dominated by one metric's MAD, investigate whether that metric's distribution
makes MAD inappropriate. Low-variance metrics (like MT% in snRNA-seq) produce
tiny MAD scales that flag physiologically normal cells.

---

## 5. Verification Pattern for R/Seurat QC

After running QC, verify with a Python script that checks:

1. R script syntax: `Rscript -e "parse(file='script.R'); cat('OK')"` (use forward slashes in path)
2. Parameter values in script text (grep for `MAX_MT_PCT`, `nmads`, `metrics = c(...)`)
3. Output files exist and exceed minimum sizes
4. QC summary CSV has expected cell counts (before/after)
5. RDS loads in R and has correct class + dimensions
6. `filtering_summary.csv` is saved by `compare_before_after_filtering()` to `figures/`, NOT `results/`

### Windows RDS loading caveat
On Windows, loading large RDS files (98+ MB) in a subprocess can fail with
exit code 3221225477 (ACCESS_VIOLATION) due to memory pressure. If this happens,
retry with a longer timeout or check the file's magic bytes as a fallback.

---

## 6. Pre-filtered Data Characteristics

When data has been pre-filtered upstream (common for public datasets):

- Fixed threshold filtering removes very few cells (0-0.1%)
- Most QC value comes from MAD outlier detection
- Max MT% is already very low (<5%)
- nFeature range is already within standard bounds
- This is **expected behavior** — document in QC report, do not force more aggressive filtering

The goal of QC on pre-filtered data is to catch batch-specific outliers and
edge cases, not to reproduce a full de novo QC.

---

## 7. Global MAD vs Per-Sample MAD (Batch-Aware Filtering)

### Problem

Computing MAD globally across all cells (ignoring sample/batch identity) can
mask batch-level QC differences. When samples have different quality profiles
(different median nFeature, different variance), a global median and MAD
represent none of them well — the thresholds become too permissive for
high-quality samples and too strict for low-quality ones.

**Observed impact (2026-07-02 session, 29,993 cells / 24 samples):**

| MAD mode | nmads | Cells removed | % removed | Per-sample range |
|----------|-------|---------------|-----------|-----------------|
| Global (all cells pooled) | 3.0 | 6 | 0.02% | 0–0.1% |
| **Per-sample (batch-aware)** | **2.5** | **403** | **1.34%** | **0–3.6%** |

The global MAD removed almost nothing because the 24 samples' distributions
"averaged out" — the global median and MAD were broad enough that no cell
in any sample was an outlier. Per-sample MAD correctly identified
sample-specific outliers: e.g., OM9_GM lost 3.6% of cells, OM9_VL lost 2%,
while several clean samples lost 0%.

### Solution

Always compute MAD **within each sample/batch**, not globally:

```r
# ❌ WRONG — global MAD, masks batch differences
mad_feature <- calculate_mad_thresholds(seu$nFeature_RNA, nmads = 3)
mad_count   <- calculate_mad_thresholds(seu$nCount_RNA, nmads = 3)
# → removes 0.02% of cells, misses batch-specific outliers

# ✅ CORRECT — per-sample MAD
for (smp in unique(seu$sample_id)) {
  idx <- seu$sample_id == smp
  if (sum(idx) >= 30) {  # MAD unstable on tiny n
    mad_f <- calculate_mad_thresholds(seu$nFeature_RNA[idx], nmads = 2.5)
    mad_c <- calculate_mad_thresholds(seu$nCount_RNA[idx],   nmads = 2.5)
  } else {
    # Small samples: use fixed global thresholds
    mad_f <- c(min_features, max_features)
    mad_c <- c(min_counts, max_counts)
  }
  # Assign per-cell thresholds based on sample membership
  seu$eff_min_feat[idx] <- max(min_features, mad_f[1])
  seu$eff_max_feat[idx] <- min(max_features, mad_f[2])
  # ... same for nCount
}
```

### nmads choice

- **nmads=3** is standard for scRNA-seq but was too lenient globally
- **nmads=2.5** with per-sample computation gave the best result (1.34% removal)
- For pre-filtered data, nmads=2.5 per-sample is a good starting point
- Always verify removal rate is in a reasonable range (0.5–5% for pre-filtered data)

### Debate-driven discovery

This issue was found via `debate_analysis`: the opponent scored 9 vs proponent 6,
correctly identifying that "0.02% removal is abnormally low" and "global MAD
masks batch effects." The judge recommended per-sample MAD with nmads=2.5.

### Lesson

When QC removes an unexpectedly **low** percentage of cells (<0.5%) on
multi-sample data, check whether MAD was computed globally. Switching to
per-sample MAD typically increases sensitivity to batch-specific outliers
without being aggressive on any single sample.
