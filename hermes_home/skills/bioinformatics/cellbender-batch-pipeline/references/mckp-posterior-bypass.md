# MCKP Estimator OOM — Posterior Bypass Workaround

## Problem

CellBender's MCKP estimator (`compute_denoised_counts()`) produces a pandas DataFrame with 42M+ rows for high-feature-count samples (26,610 features). This triggers:

```
numpy._core._exceptions._ArrayMemoryError: Unable to allocate 323. MiB
for an array with shape (42335779,) and data type int64
```

CellBender has **NO flag to skip MCKP**. The `compute_denoised_counts()` method always goes through `estimator.estimate_noise()` which creates the problematic DataFrame.

## Symptom Pattern

- CellBender training completes (150/150 epochs), posterior written to disk
- Log shows: `Computing target noise counts per gene for MCKP estimator`
- `output.h5` and `output_filtered.h5` NEVER appear
- Crash at `estimation.py:631` — `_chunk_estimate_noise()` line
- Typically on chunk 5/9 of MCKP

## Why only one sample?

`4CL_SD_D4_2_scRNA` has 26,610 features after filtering (other samples: ~19,000). Every 1,000 extra features = ~1.6M extra rows in the MCKP DataFrame. 7,000 extra features = ~11M extra rows → crosses the numpy allocation threshold.

## Workaround: Extract denoised counts from posterior.h5

If posterior.h5 exists and is complete (verified via `h5py`), extract `p_x_means` directly:

```python
import h5py, numpy as np, scipy.sparse as sp

f = h5py.File('posterior.h5', 'r')
p_x_means = f['p_x_means'][:]  # shape: (n_cells, n_genes) — denoised counts
cell_prob = f['cell_probability'][:]  # shape: (n_cells,)
f.close()

# Filter by cell probability > 0.5
keep = cell_prob > 0.5
filtered = p_x_means[keep, :]

# Convert to sparse matrix and save as h5ad
# ... standard anndata creation ...
```

**Trade-off**: MCKP separates noise from signal per gene. Bypassing means slightly less precise noise separation, but posterior means are already the denoised counts from 150 epochs of training. Sufficient for downstream analysis.

## When to use

1. MCKP OOM on 3+ retries with different parameters
2. posterior.h5 exists and is complete (h5py verification passes)
3. Other 25/26 samples processed normally — not worth debugging one edge case for hours
