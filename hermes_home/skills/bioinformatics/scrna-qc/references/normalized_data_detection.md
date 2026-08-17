# Detecting Pre-Normalized scRNA-seq Data

## Problem

Many h5ad files from public datasets (GEO, cellxgene, published atlases) arrive
with `adata.X` already normalized — raw counts are not stored. Running standard
QC filters (especially `min_counts`/`max_counts`) on normalized data produces
meaningless results. Doublet detection (Scrublet) and ambient RNA removal
(SoupX) also require raw counts and will fail or produce garbage.

## Detection Checklist

Run these checks immediately after loading the h5ad:

```python
import numpy as np
import scipy.sparse as sp

# 1. Check dtype
print(adata.X.dtype)  # float32/float64 → likely normalized; int → likely raw

# 2. Sample values
if sp.issparse(adata.X):
    sample = adata.X[:5, :10].toarray()
else:
    sample = adata.X[:5, :10]
print(sample)  # non-integer floats → normalized

# 3. Check if all values are integers
if sp.issparse(adata.X):
    is_integer = np.allclose(adata.X.data, np.round(adata.X.data))
else:
    is_integer = np.allclose(adata.X, np.round(adata.X))
print(is_integer)  # False → normalized

# 4. Check for raw counts stored elsewhere
print(adata.raw is not None)       # raw might be here
print('counts' in adata.layers)    # might be in layers

# 5. Sanity check total_counts
row_sums = np.array(adata.X.sum(axis=1)).flatten()
print(f"total_counts: min={row_sums.min():.2f}, median={np.median(row_sums):.2f}, max={row_sums.max():.2f}")
# Raw scRNA-seq: median typically 2,000-50,000+ UMIs
# If median < 5,000 AND values are floats → likely normalized (e.g., log1p normalized)
```

## Decision Matrix

| Condition | Data State | n_genes filter | n_counts filter | pct_mt filter | Doublet | SoupX |
|-----------|-----------|----------------|-----------------|---------------|---------|-------|
| int values, median > 5000 | Raw counts | ✅ | ✅ | ✅ | ✅ | ✅ |
| float values, non-integer, no raw | Normalized | ✅ | ❌ skip | ✅ (relative ref) | ❌ skip | ❌ skip |
| float values, but adata.raw exists | Normalized + raw available | ✅ | ✅ (use raw) | ✅ | ✅ (use raw) | ✅ (use raw) |
| float values, 'counts' in layers | Normalized + counts layer | ✅ | ✅ (use layer) | ✅ | ✅ (use layer) | ✅ (use layer) |

## Key Insight: n_genes_by_counts is Normalization-Invariant

`n_genes_by_counts` counts the number of genes with non-zero expression per cell.
This is a binary detection metric (gene expressed or not) — it does NOT depend
on whether values are raw counts or normalized. Therefore, `min_genes` and
`max_genes` filters remain valid regardless of data state.

## Key Insight: pct_mt on Normalized Data

`pct_counts_mt` computed from normalized data is NOT the same as mt% from raw
UMIs. It's a relative measure of mt gene expression proportion. However, it
still serves as a useful relative reference for identifying stressed/dying
cells — the distribution pattern is preserved even if absolute values differ.

## Common Scenario: Pre-filtered Data

If the h5ad came from an annotated dataset (has `celltype` column), it was
likely already QC'd upstream. Expect:
- Very low filter rate (<1% cells removed)
- Low max pct_mt (e.g., <5% even for muscle)
- No cells below min_genes threshold

This is EXPECTED — document it in the QC report and proceed.
