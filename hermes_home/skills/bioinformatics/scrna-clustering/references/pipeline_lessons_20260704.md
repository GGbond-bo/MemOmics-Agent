# MemOmics Pipeline Lessons — Human Skeletal Muscle Aging (2026-07-04)

## 1. Gene Filter OOM (scrna-qc)
- `sc.pp.filter_genes(adata, min_cells=3)` calls `.copy()` internally → OOM on 40k×55k matrix
- Fix: `gene_counts = (adata.X > 0).sum(0).A1; gene_mask = gene_counts >= 3; adata._inplace_subset_var(gene_mask)`

## 2. MT Gene Name Mismatch (scrna-clustering)
- `make.names()` converts `-` to `.` → `MT-CO1` becomes `MT.CO1`
- Fix: `grep("^MT\\.", rownames(obj))` and `PercentageFeatureSet(obj, pattern="^MT\\.")`

## 3. SCTransform scale.data vs PCA Conflict
- Clearing scale.data breaks RunPCA ("Data has not been scaled")
- Fix: Keep scale.data until after PCA+UMAP, clear only before saveRDS

## 4. Harmony2 API Changes
- `max.iter.harmony` → `max_iter`; `assay.use` → removed
- Correct: `RunHarmony(obj, group.by.vars="donor_id", reduction="pca", reduction.save="harmony", theta=2, max_iter=20)`

## 5. Batch Variable: donor_id NOT sample_id
- sample_id (16,003 unique, avg 2.5 cells) → 1-iteration pseudo-convergence
- donor_id (19 donors, avg 2,100 cells) → 6-iteration proper convergence

## 6. Pseudobulk Group Names
- `AggregateExpression` + Seurat replaces `_` with `-` in group names
- Fix: Build metadata lookup from original obj@meta.data, merge by `gsub("_", "-", group)`

## 7. h5ad Layers for Raw Counts
- Use `h5py` (not anndata) to inspect large h5ad files
- Check `layers/counts` for raw counts when X is float32 normalized
- Extract via h5py for SCTransform input