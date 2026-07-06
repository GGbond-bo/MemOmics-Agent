---
name: scrna-clustering
description: "从原始数据到细胞注释的完整Seurat v5工作流。含SoupX/DoubletFinder/SCTransform/Harmony/CCA/Pseudobulk DE"
version: 1.0.0
author: MemOmics
license: MIT
platforms: [windows, linux, macos]
metadata:
  hermes:
    tags: [clustering, SCTransform, UMAP, leiden, annotation, 02_基础分析]
    difficulty: basic
    language: R+Python
    category: transcriptomics
prerequisites:
  r_packages: ["SingleR", "celldex", "Seurat"]
  python_packages: ["scanpy", "celltypist"]
---

# scRNA-seq聚类分析

从原始数据到细胞注释的完整Seurat v5工作流。含SoupX/DoubletFinder/SCTransform/Harmony/CCA/Pseudobulk DE

适用场景: 所有scRNA-seq

分析步骤:
  - Normalize (SCTransform): SCTransform recommended
  - HVG selection: FindVariableFeatures
  - PCA + PC selection: ElbowPlot/JackStraw
  - Batch correction (Harmony): Multi-sample integration
  - Cluster (Leiden): FindNeighbors+FindClusters
  - UMAP visualization: RunUMAP 2D projection
  - Cell annotation: SingleR/CellTypist/markers

## 依赖包: Seurat, scanpy, celltypist, celldex, SingleR

难度: basic

触发提示: "对我的单细胞数据进行聚类分析"

别名: scRNA-seq 完整分析 (Seurat v5), scRNA-seq 完整分析 (Scanpy)

## When to Use

适用于: 所有scRNA-seq

## Pipeline

0. **Pre-analysis: Data scan & metadata inspection**（参见 references/large-h5ad-metadata-inspection.md）\n   - 对 >5GB 的 h5ad 文件，先用 h5py 低内存方式读取 obs 元数据\n   - 识别：age分组（数值→Young/Old归类）、sample_id/donor_id分布、QC统计\n   - 确认双层抽样策略：celltype比例 + 样本平衡\n   - 知识库校对：匹配组织+物种+方向的参考阈值\n   - Tool: `execute_python` (用 h5py 而非 anndata)\n\n0a. **h5ad → Seurat loading**（参见 references/rhdf5-load-h5ad-to-seurat.md）\n   - Seurat v5.5.0 lacks `ReadH5AD` — use `rhdf5` (Bioconductor) for reliable loading\n   - For files > 3GB: subset in Python first, then load subset in R\n   - CSR matrix: build as `new("dgCMatrix")`, NOT `sparseMatrix()`\n   - Categorical obs: h5ad uses `categories` + `codes` groups (single underscore, not `__categories`)\n   - Pass metadata as `meta.data=` in `CreateSeuratObject()`, not via `$<-` after creation

1. **Normalize (SCTransform)**
   - SCTransform recommended
   - Tool: `terminal`
2. **HVG selection**
   - FindVariableFeatures
   - Tool: `terminal`
3. **PCA + PC selection**
   - ElbowPlot/JackStraw
   - Tool: `terminal`
4. **Batch correction (Harmony)**
   - Multi-sample integration
   - Tool: `terminal`
5. **Cluster (Leiden)**
   - FindNeighbors+FindClusters
   - Tool: `terminal`
6. **UMAP visualization**
   - RunUMAP 2D projection
   - Tool: `terminal`
7. **Cell annotation**
   - SingleR/CellTypist/markers
   - Tool: `terminal`

## Parameters

| Parameter | Default | Notes |
|-----------|---------|-------|
| `r_packages` | SingleR, celldex, Seurat | |
| `python_packages` | scanpy, celltypist | |
| `steps` | Normalize (SCTransform) -> HVG selection -> PCA + PC selection -> Batch correction (Harmony) -> Cluster (Leiden) -> UMAP visualization -> Cell annotation | |

> **Parameter Adaptation**: Adjust parameters based on tissue quality, species, and condition. Literature values take priority, then official defaults, then tissue-specific adjustments.

## Proven Scripts

> Scripts that have been successfully executed and passed analysis review.
> These are automatically saved after successful runs.

| Species | Tissue | Condition | Date | Score |
|---------|--------|-----------|------|-------|
| *(none yet)* | | | | |

## Common Issues

| Error | Cause | Solution |
|-------|-------|----------|
| R fails to read h5ad | Seurat v5 lacks ReadH5AD; hdf5r crashes in Rscript | Use `rhdf5` (Bioconductor) — see `references/rhdf5-load-h5ad-to-seurat.md` |
| SCTransform OOM on 30k cells | scale.data is full dense matrix — huge save | Remove scale.data before saveRDS: `obj[["SCT"]]@scale.data <- new("matrix")` |
| MT% = 0 after QC | Seurat's `_`→`-` renaming mismatches `^MT-` pattern | Verify with `grep("^MT-", rownames(obj))`; pattern is correct after rename |
| Stratified sampling needed | Raw data has class imbalance for rare cell types | Use Python: proportional allocation by celltype + 50/50 Young/Old within each type |
| `No cell overlap between new meta data` | Adding metadata after CreateSeuratObject fails when cell barcodes mismatch | Pass metadata as `meta.data` argument in `CreateSeuratObject()` call |

## References

- Source: MemOmics built-in
- Category: transcriptomics
- Language: R+Python


## Reference Script (from External Skill)

> Auto-imported from external skill `29_scrnaseq-seurat-core-analysis`.
> This script is a verified reference implementation, NOT a run.py template.
> The agent can use it as a starting point or fetch official docs for the latest version.

- **Source**: `skills/external/29_scrnaseq-seurat-core-analysis/scripts/`
- **Imported scripts**: cluster_cells.R
