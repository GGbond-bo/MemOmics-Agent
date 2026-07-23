# MemOmics: subset h5ad to 60K cells, save as RDS
import anndata as ad
import numpy as np
import sys

print("Loading h5ad...")
adata = ad.read_h5ad("D:/我的下载/Migule_lai_24 _new.h5ad")
print(f"Loaded: {adata.n_obs} cells, {adata.n_vars} genes")

# Subset to 60,000 cells
np.random.seed(42)
if adata.n_obs > 60000:
    idx = np.random.choice(adata.n_obs, 60000, replace=False)
    adata = adata[idx, :].copy()
    print(f"Subset to {adata.n_obs} cells")

# Save as h5ad for R
out_path = "results/基础分析/Seurat/data/subset_60k.h5ad"
import os
os.makedirs(os.path.dirname(out_path), exist_ok=True)
adata.write_h5ad(out_path)
print(f"Saved to {out_path}")
print("Done!")