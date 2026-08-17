# SCTransform Timeout Fallback Strategy

Session-derived reference (2026-07-02, human skeletal muscle aging, 40K cells).

## Problem

SCTransform (both v1 and v2) times out (>600s) on 40K cells with 55K genes in R,
even with aggressive memory settings.

### All combinations tried and failed:
| Attempt | Config | Result |
|---------|--------|--------|
| 1 | v2 + sequential + conserve.memory=TRUE + ncells=2000 | Timeout |
| 2 | v2 + multisession workers=1 + 70GB future.globals.maxSize | Timeout |
| 3 | v2 + glmGamPoi | Timeout |
| 4 | v1 + conserve.memory=TRUE | Timeout |
| 5 | v2 + glmGamPoi + return.only.var.genes=TRUE | Timeout |

### Root cause:
The corrected UMI residual calculation step is O(n_cells × n_genes) dense matrix
computation. 40K × 55K = 2.2 billion floating-point operations per iteration,
which exceeds what R can handle in a reasonable time even with sequential
processing.

## Solution: NormalizeData + ScaleData Fallback

```r
library(Seurat)
library(future)
plan("multisession", workers = 1)
options(future.globals.maxSize = 70 * 1024^3)

seurat_obj <- NormalizeData(seurat_obj,
    normalization.method = "LogNormalize",
    scale.factor = 10000)

seurat_obj <- FindVariableFeatures(seurat_obj,
    selection.method = "vst",
    nfeatures = 3000)

seurat_obj <- ScaleData(seurat_obj,
    vars.to.regress = "percent.mt")
```

### When to use this fallback:
- Cell count > 30K: try SCT once, if timeout → fallback
- Cell count > 50K: skip SCT entirely, use NormalizeData directly
- Do NOT retry SCT more than 2 times — it will not suddenly succeed

### Impact assessment:
- LogNormalize + ScaleData is the classic Seurat pipeline, proven on thousands of datasets
- Main difference: SCT better handles sequencing depth variation via regularized negative binomial
- For 40K cells with balanced sampling, LogNormalize results are reliable
- Document the fallback in the analysis report for transparency

## Harmony2 Compatibility with Seurat v5.5.0

### Problem
Harmony2 (v2.0.3) changed its API — `getMethod("RunHarmony", "Seurat")` fails with:
```
Error in getMethod("RunHarmony", "Seurat"):
  no suitable method for 'RunHarmony'
```

### Solution
Call `RunHarmony()` directly on the PCA embedding matrix:

```r
library(harmony)

# Extract PCA embeddings
pca_embeddings <- Embeddings(seurat_obj, "pca")

# Run Harmony directly on the matrix
harmony_result <- RunHarmony(
    data_mat = pca_embeddings,
    meta_data = seurat_obj@meta.data,
    vars_use = "sample_id",
    do_pca = FALSE  # PCA already done
)

# Add back to Seurat object
seurat_obj[["harmony"]] <- CreateDimReducObject(
    embeddings = harmony_result,
    key = "harmony_",
    assay = "RNA"
)
```

### Alternative: downgrade to Harmony v1
```r
# If Harmony2 continues to cause issues:
remotes::install_version("harmony", version = "0.1.1")
```