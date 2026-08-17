# h5ad → Seurat via MTX fallback

## Problem
`SeuratDisk::Convert(h5ad, dest="h5seurat")` fails with:
- `HDF5-API Errors: decrementing ID ref count`
- `Unable to copy object` / `H5Ocopy` errors
- R session crash (exit code 3221225477)

Root cause: HDF5 version mismatch between Python anndata and R SeuratDisk; non-standard obs column types.

## Solution: Two-step MTX export/import

### Step 1: Python — export to MTX
```python
import scanpy as sc
import scipy.io
import pandas as pd

adata = sc.read_h5ad("input.h5ad")

# Export counts matrix (transpose: genes × cells)
scipy.io.mmwrite("matrix.mtx", adata.X.T.tocsr())

# Export features and barcodes
pd.DataFrame(adata.var.index).to_csv("features.tsv", header=False, index=False)
pd.DataFrame(adata.obs.index).to_csv("barcodes.tsv", header=False, index=False)

# Export metadata
adata.obs.to_csv("metadata.csv")
```

### Step 2: R — build Seurat from MTX
```r
library(Seurat)

counts <- ReadMtx(
  mtx = "matrix.mtx",
  features = "features.tsv",
  cells = "barcodes.tsv"
)

meta <- read.csv("metadata.csv", row.names = 1)

obj <- CreateSeuratObject(
  counts = counts,
  meta.data = meta,
  project = "project_name",
  min.cells = 3,
  min.features = 200
)
```

## Alternative: Pure R with zellkonverter
```r
BiocManager::install("zellkonverter")
library(zellkonverter)
obj <- readH5AD("input.h5ad", assay_name = "RNA")
```
Note: zellkonverter may have its own HDF5 compatibility issues on Windows.

## Verified
2026-07-17, Windows 11, human skeletal muscle aging subset (10k cells, 35k genes).
SeuratDisk 0.0.0.9021, Seurat 5.5.0 → failed. MTX fallback → succeeded.
