# RegDiffusion Integration with pySCENIC

> ⚡ **100x faster than GRNBoost2** — 32 seconds vs 30-60 minutes for 10k cells on RTX 5070 Ti

## Overview

RegDiffusion ([TuftsBCB/RegDiffusion](https://github.com/TuftsBCB/RegDiffusion), v0.2.2) uses a diffusion model to infer TF-target relationships from single-cell RNA-seq data. Its output format (`TF, target, importance` CSV) is fully compatible with pySCENIC's `modules_from_adjacencies()` → cisTarget → AUCell pipeline.

## Installation

```bash
# Install in the correct Python environment
pip install regdiffusion
# Requires: torch, scanpy, numpy, pandas, scikit-learn, pyvis, h5py
```

## Complete Workflow

### Step 1: Load data and filter HVG
```python
import scanpy as sc
import pandas as pd
import numpy as np

adata = sc.read_h5ad("data.h5ad")
# Normalize and select HVG (5000 recommended)
sc.pp.normalize_total(adata, target_sum=1e4)
sc.pp.log1p(adata)
sc.pp.highly_variable_genes(adata, n_top_genes=5000)
adata_hvg = adata[:, adata.var['highly_variable']].copy()

# Extract expression matrix (cells x genes, float32)
from scipy.sparse import issparse
X = adata_hvg.X
if issparse(X): X_dense = X.toarray().astype(np.float32)
else: X_dense = np.asarray(X).astype(np.float32)
gene_names = adata_hvg.var_names.values
```

### Step 2: Train RegDiffusion
```python
import regdiffusion as rd

trainer = rd.RegDiffusionTrainer(
    exp_array=X_dense,          # cells x genes, log-transformed
    device='cuda',               # GPU required for speed
    n_steps=1000,
    batch_size=128,
    memory_efficient=True        # ⚠️ uses RegDiffusionME class
)
trainer.train(n_steps=1000)
# ✅ Training complete in ~32s for 9568 cells x 5000 genes
```

### Step 3: Extract adjacency matrix
```python
# ⚠️ CRITICAL: memory_efficient=True → use get_adj(), NOT .adj_matrix
adj_matrix = trainer.model.get_adj()  # returns numpy float16 (n_genes, n_genes)
```

### Step 4: Convert to GRNBoost2-compatible format
```python
adj_data = []
for i in range(len(gene_names)):
    for j in range(len(gene_names)):
        if i == j: continue
        w = float(abs(adj_matrix[i, j]))
        if w > 0.01:  # filter near-zero
            adj_data.append({'TF': gene_names[i], 'target': gene_names[j], 'importance': w})
adjacencies = pd.DataFrame(adj_data).sort_values('importance', ascending=False)
```

### Step 5: pySCENIC pipeline (cisTarget + AUCell)
```python
from pyscenic.utils import modules_from_adjacencies
from pyscenic.prune import prune2df, df2regulons
from pyscenic.aucell import aucell
from ctxcore.rnkdb import FeatherRankingDatabase as RankingDatabase

ex_matrix = pd.DataFrame(X_dense, index=adata_hvg.obs_names, columns=gene_names)
modules = list(modules_from_adjacencies(adjacencies, ex_matrix, rho_mask_dropouts=True))

dbs = [RankingDatabase(fname="hg38_10kbp...feather", name="hg38")]
motif_df = prune2df(dbs, modules, "motifs-v10nr...tbl")
regulons = df2regulons(motif_df)

auc_matrix = aucell(ex_matrix, regulons, num_workers=4)
```

## ⚠️ Known Issues & Fixes

### 1. cisTarget corrupts regulon gene names
**Symptom**: `regulon.genes` contains single characters (e.g. `['[', '(', "'", 'A', ...]`) instead of gene names after cisTarget. AUCell scores all zero.

**Root cause**: RegDiffusion adjacency matrices built from 5000 HVG genes. cisTarget motif database maps motifs to RefSeq gene IDs, which don't match the HVG gene names in the expression matrix.

**Fix**: Use Direct TF Activity Scoring instead of cisTarget:
```python
TOP_K = 50
tf_activity = {}
for tf in key_tfs:
    tf_adj = adjacencies[adjacencies['TF'] == tf].head(TOP_K)
    targets = [t for t in tf_adj['target'] if t in gene_to_idx]
    if len(targets) < 5: continue
    target_idxs = [gene_to_idx[t] for t in targets]
    activity = expression_matrix[:, target_idxs].mean(axis=1)
    tf_activity[tf] = activity
```

### 2. RegDiffusionME has no `.adj_matrix`
**Symptom**: `AttributeError: 'RegDiffusionME' object has no attribute 'adj_matrix'`

**Fix**: Use `trainer.model.get_adj()` instead of `trainer.model.adj_matrix.detach().cpu().numpy()`

### 3. NumPy 2.x compatibility
**Symptom**: `AttributeError: module 'numpy' has no attribute 'object'`

**Fix**: Patch `pyscenic/transform.py` — replace 3 occurrences of `np.object` with `object`.

### 4. Dask compatibility
**Symptom**: `TypeError: object of type 'generator' has no len()`

**Fix**:
```bash
pip install 'dask[complete]==2024.8.0'
pip uninstall -y dask-expr
```

## Performance Benchmarks (RTX 5070 Ti, 17GB VRAM)

| Dataset | Method | Time | Speedup |
|---------|--------|------|---------|
| 9568 cells x 5000 genes | **RegDiffusion** | **32 sec** | 100x |
| 9568 cells x 5000 genes | GRNBoost2 (4 workers) | ~45 min | 1x |
| 6974 cells x 5000 genes | RegDiffusion | ~25 sec | — |
| cisTarget (10kb DB) | — | ~65 sec | — |
| AUCell (9568 cells, 20 regulons) | — | ~10 sec | — |

## References

- RegDiffusion: TuftsBCB/RegDiffusion (https://github.com/TuftsBCB/RegDiffusion)
- pySCENIC: Van de Sande et al. 2020, Nature Protocols