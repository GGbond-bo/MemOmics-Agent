# Loading Large h5ad Files into R/Seurat (rhdf5 Method)

## Why Not ReadH5AD?
Seurat v5.5.0 does NOT include `ReadH5AD`. The function is not exported.
Alternatives:
- `rhdf5` (Bioconductor) — THE reliable path for Windows
- `hdf5r` — R6 API may fail silently in Rscript mode (尤其是 Windows)
- SeuratDisk `Convert()` + `LoadH5Seurat` — requires additional install

## Proven Workflow: Python Subset → R (rhdf5) → Seurat

### Step 1: Python Subset (if file > 3GB)
For files > 3GB, R cannot load them directly. Subset in Python first:

```python
import h5py, numpy as np, scipy.sparse as sp, pandas as pd, anndata as ad

f = h5py.File('big.h5ad', 'r')
obs = f['obs']

# Extract categorical metadata
def get_cat_val(key):
    codes = obs[key]['codes'][:]
    cats = obs[key]['categories'][:]
    cats = [x.decode() if isinstance(x, bytes) else str(x) for x in cats]
    return np.array([cats[c] for c in codes])

# Stratified sampling (celltype + young/old balance)
# ... (sampling logic)
selected = sorted(selected_indices[:30000])

# Read CSR row-by-row to avoid loading entire matrix
X_grp = f['X']
indptr = X_grp['indptr'][:]
row_data, row_idx, row_ptr = [], [], [0]
for src_row in selected:
    s, e = int(indptr[src_row]), int(indptr[src_row+1])
    row_data.extend(X_grp['data'][s:e])
    row_idx.extend(X_grp['indices'][s:e])
    row_ptr.append(row_ptr[-1] + (e - s))

subset = sp.csr_matrix((row_data, row_idx, row_ptr, None),
                       shape=(len(selected), n_genes))

# Build AnnData and save
obs_df = pd.DataFrame({'celltype': celltype[selected], ...})
adata = ad.AnnData(X=subset, obs=obs_df, var=var_df)
adata.write('subset_30k.h5ad')
```

### Step 2: R Loading with rhdf5

```r
library(Seurat)
library(rhdf5)
library(Matrix)

input_file <- "subset_30k.h5ad"

# Read CSR matrix
data <- h5read(input_file, "X/data")
indices <- h5read(input_file, "X/indices")
indptr <- h5read(input_file, "X/indptr")
n_cells <- length(indptr) - 1
n_genes <- h5readAttributes(input_file, "X")$shape[2]

# Build dgCMatrix (genes x cells for Seurat)
X <- new("dgCMatrix")
X@i <- as.integer(indices)
X@p <- as.integer(indptr)
X@x <- as.numeric(data)
X@Dim <- as.integer(c(n_genes, n_cells))

# Read gene names
gene_names <- h5read(input_file, "var/_index")
gene_names <- sapply(gene_names, function(x)
    if(is.raw(x)) rawToChar(x) else as.character(x))

# Read categorical metadata
read_cat <- function(path) {
    codes <- h5read(input_file, paste0(path, "/codes"))
    cats <- h5read(input_file, paste0(path, "/categories"))
    cats <- sapply(cats, function(x)
        if(is.raw(x)) rawToChar(x) else as.character(x))
    cats[codes + 1]
}

celltype <- read_cat("obs/celltype")
age <- h5read(input_file, "obs/age")
sample_id <- read_cat("obs/sample_id")

# Fix gene names: Seurat replaces _ with -
rownames(X) <- make.names(gene_names, unique=TRUE)
rownames(X) <- gsub("_", "-", rownames(X))
colnames(X) <- paste0("cell_", 1:n_cells)

# Create Seurat object with metadata
meta_df <- data.frame(
    row.names = colnames(X),
    celltype = celltype,
    age = age,
    sample_id = sample_id,
    stringsAsFactors = FALSE
)
seurat_obj <- CreateSeuratObject(
    counts = X, meta.data = meta_df,
    project = "Project", min.cells = 0, min.features = 0
)
```

## Key Pitfalls

| Pitfall | Symptom | Fix |
|---------|---------|-----|
| hdf5r fails in Rscript | `Error: 不适用于非函数` | Use `rhdf5` (Bioconductor) instead |
| Wrong categories path | `Object '__categories' does not exist` | h5ad saved by anndata uses `categories` (single underscore); raw CellRanger uses `__categories` (double). Check with `h5ls(file, recursive=TRUE)` |
| CSR dimension mismatch | `'dims' must contain all (i,j) pairs` | Build with `new("dgCMatrix")` not `sparseMatrix()` |
| No cell overlap in metadata | `No cell overlap between new meta data and Seurat object` | Pass metadata as `meta.data` in `CreateSeuratObject()` call, not via `$<-` after creation |
| Gene names with underscores | Warning about `_` → `-` replacement | Pre-apply `make.names()` + `gsub("_", "-")` |
| Out of memory saving SCTransform obj | Script exits after `Place corrected count matrix` | Remove scale.data: `seurat_obj[["SCT"]]@scale.data <- new("matrix")` before saveRDS |
| MT% = 0 for all cells | `All cells have the same value of percent.mt` | Check if Seurat's `_`→`-` replacement changed MT gene names; verify with `grep("^MT-", rownames(obj))` |

## Verification Steps
1. After loading: `stopifnot(ncol(seurat_obj) == n_cells)`
2. After SCTransform: `stopifnot("SCT" %in% names(seurat_obj@assays))`
3. Validate celltype distribution matches Python metadata
