# Oligodendrocyte (OPC/ODC) Gap Analysis — Human 40-Sample Hippocampus ATAC

**Date**: 2026-08-27
**Data**: `E:/专利/human_40_markerList.csv` (getMarkerFeatures output)
**RDS**: `E:/专利/patent/human_Hf_ATAC_40_clustered.rds` (265,909 cells, 30 clusters)

## Oligo Gene Distribution in MarkerList

| Gene | Type | Found in clusters | In markerList? |
|------|------|-------------------|----------------|
| CSPG4 | OPC | C1, C2, C3, C4, C5, C6 | ✅ |
| PDGFRA | OPC | C2, C3 | ✅ |
| OPALIN | ODC (mature) | C30 | ✅ |
| MAG | ODC (mature) | C30 | ✅ |
| SOX10 | OPC/ODC | — | ❌ |
| MBP | ODC (mature) | — | ❌ |
| PLP1 | ODC (mature) | — | ❌ |
| MOG | ODC (mature) | — | ❌ |
| MOBP | ODC (mature) | — | ❌ |
| OLIG1 | OPC | — | ❌ |
| OLIG2 | OPC | — | ❌ |
| MYRF | ODC | — | ❌ |

## Key Observations

1. **CSPG4 appears in C1-C6 (ExN clusters)**: These clusters have BCL11B/CACNG4/SEZ6L as top markers (ExN), but CSPG4 is also significant. This suggests either:
   - Mixed OPC+ExN populations (resolution too low)
   - CSPG4 has non-OPC roles in hippocampal neurons

2. **ODC only 8 cells**: C30 is the only ODC cluster with OPALIN/MAG. MBP/PLP1/MOG/MOBP are completely absent from the markerList — either:
   - These genes have no differential accessibility (all peaks similarly open)
   - ODC cells were filtered out during QC
   - The ODC population is immature (expressing OPALIN/MAG but not yet MBP/PLP1)

3. **Macaque comparison**: Monkey has 44,021 ODC (27%) and 6,574 OPC (4%) — healthy proportions. Human having <0.01% ODC is clearly a technical issue.

## Diagnostic Commands

```r
# Check oligo markers in GeneScoreMatrix
proj <- loadArchRProject("E:/专利/patent/human_Hf_ATAC_40_clustered.rds")
gsm <- getMatrixFromProject(proj, useMatrix = "GeneScoreMatrix")
rownames(gsm) <- proj@geneAnnot$Symbol

oligo_markers <- c("OPALIN","MAG","MBP","PLP1","MOBP","PDGFRA","CSPG4","SOX10")
for(g in oligo_markers){
  idx <- which(rownames(gsm) == g)
  if(length(idx) == 0){ cat(g, "not in GSM\n"); next }
  vals <- assay(gsm[idx,])
  means <- tapply(colMeans(vals), proj$Clusters, mean)
  cat(g, "\n"); print(sort(means, decreasing=TRUE)[1:10])
}
```

## Hypotheses to Test

1. **Resolution hypothesis**: Re-cluster at higher resolution (1.0-1.2) → check if OPC/ODC separate from ExN
2. **QC hypothesis**: Check nFrags distribution for C30 cells → if low, lower nFrags threshold
3. **CSPG4 dual-role hypothesis**: Check if CSPG4+ cells in C1-C6 co-express ExN markers (SLC17A7/NRGN) or OPC markers (PDGFRA/SOX6)
