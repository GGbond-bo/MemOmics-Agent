# Proven Script: Human Skeletal Muscle Aging (40K cells)

**Date**: 2026-07-02
**Score**: PASS
**Species**: Human (Homo sapiens)
**Tissue**: Skeletal muscle
**Condition**: Aging (Young 15-34y vs Old 77-99y)

## Pipeline Summary

| Step | Method | Key Parameters | Result |
|------|--------|---------------|--------|
| Subset | Python: stratified sampling | 40K cells, balanced Young/Old, proportional by celltype | 39,995 cells |
| QC | Seurat v5.5.0 | nFeature 200-6000, MT%<5%, nCount<40000 | 39,988 cells (7 removed) |
| Normalize | NormalizeData + ScaleData | LogNormalize, 3000 HVGs, regress MT% | SCTransform timeout → fallback |
| PCA | RunPCA | 50 PCs, 42 used (90.1% var) | Elbow plot confirmed |
| Batch | Harmony2 v2.0.3 | 24 samples, dims=1:42 | API compatibility fix applied |
| Cluster | FindClusters (Leiden) | res=0.5 selected (tested 0.3/0.5/0.8/1.0) | 14 clusters |
| UMAP | RunUMAP | dims=1:42, n.neighbors=30 | Clean separation |
| Annotate | FindAllMarkers → manual | min.pct=0.25, logfc.threshold=0.25 | 14 cell types, 5,892 markers |

## Cell Types Identified

| Cluster | Cell Type | Key Markers | ~Cells |
|---------|-----------|-------------|--------|
| 0 | Type I (slow) | ATP2A2, MYH7B, TNNT1, TNNI1 | 6,856 |
| 1 | Type II (fast) | MYH2, MYH1, ACTN3 | 4,073 |
| 2 | Type II sub | MYH1, MYH2 | 4,062 |
| 3 | FAP | PDGFRA, DCN, COL1A1 | 3,693 |
| 4 | Endothelial | PECAM1, VWF, CDH5 | 3,486 |
| 5 | Denervated MF | CHRNA1, MUSK, NCAM1 | 2,922 |
| 6 | MuSC | PAX7, MYF5, CHRDL2 | 2,763 |
| 7 | SMC/Pericyte | ACTA2, RGS5, PDGFRB | 2,493 |
| 8 | Myeloid | CD14, CD68, ITGAM | 2,419 |
| 9 | Lymphocyte | CD3D, CD3E, CD2 | 2,293 |
| 10 | Adipocyte | ADIPOQ, PLIN1, LEP | 2,038 |
| 11 | Schwann Cell | MPZ, PMP22, SOX10 | 1,940 |
| 12 | Mast Cell | KIT, TPSAB1, CPA3 | 1,923 |
| 13 | NMJ | CHRNE, COLQ, DOK7 | 1,882 |

## Key Pitfalls Encountered

1. **SCTransform timeout**: 40K cells too large for SCT corrected UMI → fell back to NormalizeData+ScaleData
2. **Harmony2 API**: v2.0.3 removed S4 method registration → used direct `RunHarmony()` call
3. **snRNA-seq MT%**: median 0.28%, used MT%<5% fixed threshold (not 15%)

## Output Files

- `results/02_basic/qc/data/seurat_qc.rds`
- `results/02_basic/normalize/data/seurat_norm.rds`
- `results/02_basic/harmony/data/seurat_harmony.rds`
- `results/02_basic/annotation/data/seurat_annotated.rds`
- `results/02_basic/annotation/results/all_markers_res0.5.csv`