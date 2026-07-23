#!/usr/bin/env python3
"""Convert h5ad to 10X MTX format - use simple paths, then move."""
import anndata as ad
import scipy.io
import numpy as np
import pandas as pd
import os, shutil

h5ad_file = "D:/我的下载/muscle_aging_60k_subset.h5ad"
tmp_dir = r"E:\tmp_mtx"
final_dir = r"E:\MemOmics-Agent\hermes-agent\results\基础分析\Seurat_QC\data\mtx"

print(f"Reading h5ad: {h5ad_file}")
adata = ad.read_h5ad(h5ad_file)
print(f"  Shape: {adata.shape}")

# Use raw counts if available
if adata.raw is not None:
    print("  Using raw counts from .raw")
    counts = adata.raw.X
    var_names = adata.raw.var_names.tolist()
else:
    print("  Using .X")
    counts = adata.X
    var_names = adata.var_names.tolist()

from scipy.sparse import isspmatrix_csc, csc_matrix, csr_matrix
if hasattr(counts, 'toarray'):
    if not isspmatrix_csc(counts) and not isinstance(counts, csr_matrix):
        counts = csc_matrix(counts)
elif isinstance(counts, np.ndarray):
    counts = csc_matrix(counts)

print(f"  Counts matrix type: {type(counts)}, shape: {counts.shape}")

# Write to simple path first
os.makedirs(tmp_dir, exist_ok=True)
mtx_path = os.path.join(tmp_dir, "matrix.mtx")
barcodes_path = os.path.join(tmp_dir, "barcodes.tsv")
features_path = os.path.join(tmp_dir, "features.tsv")

print(f"Writing matrix.mtx to {mtx_path}...")
scipy.io.mmwrite(mtx_path, counts)
print(f"  matrix.mtx written, size: {os.path.getsize(mtx_path) / 1e6:.1f} MB")

print(f"Writing barcodes.tsv...")
barcodes = pd.DataFrame(adata.obs_names, columns=["barcodes"])
barcodes.to_csv(barcodes_path, sep="\t", header=False, index=False)
print(f"  {len(barcodes)} barcodes written")

print(f"Writing features.tsv...")
if "gene_symbols" in adata.var.columns:
    gene_ids = adata.var_names.tolist()
    gene_symbols = adata.var["gene_symbols"].tolist()
    features = pd.DataFrame({"id": gene_ids, "name": gene_symbols, "feature_type": "Gene Expression"})
elif "gene_ids" in adata.var.columns:
    gene_ids = adata.var["gene_ids"].tolist()
    features = pd.DataFrame({"id": gene_ids, "name": var_names, "feature_type": "Gene Expression"})
else:
    features = pd.DataFrame({"id": var_names, "name": var_names, "feature_type": "Gene Expression"})
features.to_csv(features_path, sep="\t", header=False, index=False)
print(f"  {len(features)} features written")

# Save metadata
meta_path = os.path.join(tmp_dir, "metadata.csv")
adata.obs.to_csv(meta_path)
print(f"  metadata.csv saved")

# Move to final directory
os.makedirs(final_dir, exist_ok=True)
for f in os.listdir(tmp_dir):
    shutil.move(os.path.join(tmp_dir, f), os.path.join(final_dir, f))
    print(f"  Moved {f} -> final dir")

os.rmdir(tmp_dir)
print(f"\nDone! All files in {final_dir}")
for f in os.listdir(final_dir):
    print(f"  {f}: {os.path.getsize(os.path.join(final_dir, f))/1e6:.1f} MB")