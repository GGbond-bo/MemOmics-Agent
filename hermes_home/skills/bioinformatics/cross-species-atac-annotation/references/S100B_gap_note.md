# S100B Gap in ATAC Marker Lists — 2026-08-27 User Correction (Expanded)

## Problem
User flagged: "25, 27, 28, 29, 30，人脑这几个亚群高表达S100B啊，你真的对吗？"

S100B is a **classic Astrocyte marker** (GFAP/S100B/AQP4 trio), but it does NOT appear in the 89-gene reference list or the full 20,326-row marker CSV. This means:

1. S100B locus is **accessible** in these clusters (it's a real gene)
2. But its peaks don't show **differential** accessibility in the 30-cluster Wilcoxon test
3. getMarkerFeatures silently drops it → annotation misses the Astrocyte signal

## Why This Happens
- **ATAC accessibility ≠ RNA expression**: S100B may be highly expressed (RNA/GAS) but its chromatin peaks are similarly open across multiple cell types → no differential signal
- **Multiple testing burden**: 30-cluster comparison is harsh; pairwise comparison often recovers missing markers
- **Peak-level vs gene-level**: getMarkerFeatures tests individual peaks, not aggregated gene accessibility

## Which Clusters Are Affected
| Cluster | Cells | Markers in CSV | S100B status | Previous annotation | Correct annotation |
|---------|-------|----------------|-------------|--------------------|--------------------|
| C25 | 2 | 5 (OR2T4 etc) | High GeneScoreMatrix | ExN (weak/none) | Astro (pending GFAP/AQP4 check) |
| C27 | ~4821 | 0 | High GeneScoreMatrix | not in CSV | Astro (pending GFAP/AQP4 check) |
| C28 | 2 | 3 (LINC00482 etc) | High GeneScoreMatrix | ExN (weak/none) | Astro (pending GFAP/AQP4 check) |
| C29 | ~unknown | 1 (LOC284412) | High GeneScoreMatrix | not in CSV | Astro (pending GFAP/AQP4 check) |
| C30 | 8 | 15 (OPALIN/MAG etc) | High GeneScoreMatrix | ODC | ODC (OPALIN/MAG confirmed, but S100B also high → possible doublet) |

## Verification Method (User-Proven, 2026-08-27)

The user ran `plotEmbedding` with GeneScoreMatrix and **directly observed** S100B was high:

```r
markerGenes <- c(
  "SLC17A7","CAMK2A","SATB2","NRGN",          # ExN
  "GAD1","GAD2","SST","PVALB","VIP","LAMP5",  # InN
  "GFAP","ALDH1L1","S100B","AQP4",            # Astro
  "P2RY12","CX3CR1","AIF1","TREM2","TMEM119", # Micro
  "PDGFRA","CSPG4","SOX6",                    # OPC
  "MBP","PLP1","MOBP",                        # ODC
  "CLDN5","VWF","PECAM1","ABCC9",             # VS
  "TTR","CLIC6","FOXJ1"                       # ChP
)

p <- plotEmbedding(
    ArchRProj = proj, 
    colorBy = "GeneScoreMatrix", 
    name = markerGenes, 
    embedding = "UMAPHarmony",
    imputeWeights = getImputeWeights(proj)
)
```

**This is the most reliable verification** — GeneScoreMatrix aggregates peak accessibility near gene bodies via imputation, catching signal that individual peak-level tests miss.

## Fix Strategy (Priority Order)

### 1. 🔴 plotEmbedding visual check (FASTEST, MOST RELIABLE)
Run the above code. If S100B lights up in C25/C27/C28/C29 → they're Astro. Also check GFAP, ALDH1L1, AQP4 in the same plot.

### 2. GeneScoreMatrix numerical extraction
```r
gas <- getGeneScoreMatrix(proj)
s100b_idx <- grep("S100B", rownames(gas))
if (length(s100b_idx) > 0) {
  s100b_scores <- gas[s100b_idx[1], ]
  tapply(s100b_scores, proj$Clusters, median)
}
```

### 3. Pairwise comparison (P9 method)
```r
cd <- getCellColData(proj)
grp <- ifelse(cd$Clusters %in% c("C25","C27","C28","C29"), cd$Clusters, "Rest")
proj <- addCellColData(proj, data=grp, name="s100b_check", force=TRUE)
mk <- getMarkerFeatures(proj, useMatrix="PeakMatrix", groupBy="s100b_check",
                        testMethod="wilcoxon", bias=c("TSSEnrichment","log10(nFrags)"),
                        cutOff="FDR<=0.1")
```

### 4. Cross-reference with RNA
If scRNA-seq data exists for same tissue, check S100B expression.

## Key Lesson

**Always cross-check annotation with `plotEmbedding(colorBy="GeneScoreMatrix")` for canonical markers.** The DEG-based annotation pipeline has a blind spot: genes that are accessible across many cell types (like S100B in all Astrocytes) won't show up as differentially expressed, but GeneScoreMatrix will show them. This is especially critical for clusters with ≤5 DEGs (evidence=weak/none) — these are most likely to be mis-annotated.

**Small cluster noise filter**: Clusters with ≤8 cells (C25=2, C28=2, C30=8) should be flagged as potential doublets/artifacts regardless of marker profile. Check DoubletScore and sample distribution before assigning cell type.
