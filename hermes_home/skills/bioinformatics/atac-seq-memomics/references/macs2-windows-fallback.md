# MACS2 on Windows: Installation Failure & TileMatrix Fallback

## Problem

MACS2 is listed as a prerequisite for ArchR's `addReproduciblePeakSet()`, but on modern Windows setups it often cannot be installed via any method:

### Failure Mode 1: pip install MACS2
```
pip install MACS2
→ Cython compilation error: 'numpy/uint32_t.pxd' not found
→ 'int32_t' is not a type identifier
→ Compiler crash in AnalyseExpressionsTransform
```
Root cause: MACS2 2.2.9.1 has Cython .pyx files using legacy `cimport numpy` patterns. Modern Cython 3+ numpy headers removed these .pxd files.

### Failure Mode 2: pip install macs3
```
pip install macs3
→ error: Microsoft Visual C++ 14.0 or greater is required
→ Failed to build cykhash
```
Root cause: macs3 depends on cykhash which requires VC++ build tools not present on typical Windows dev setups.

### Failure Mode 3: conda install
```
conda install -c bioconda macs2
→ ModuleNotFoundError: No module named 'zstandard.backend_c'
```
Root cause: conda environment may be corrupted or zstandard package broken.

## Diagnosis

```r
.libPaths(c("USER_R_LIBS/R-4.5.3", .libPaths()))
library(ArchR)
addArchRGenome("hg38")
result <- tryCatch(ArchR::findMacs2(), error = function(e) paste("ERROR:", e$message))
cat("findMacs2 result:", result, "\n")
```

Expected when MACS2 missing: `"ERROR: Could Not Find Macs2! Please install w/ pip..."`

## Solution: TileMatrix Fallback

Skip `addReproduciblePeakSet()` entirely. Use `addTileMatrix(tileSize=500)` — no MACS2 needed.

```r
# Replace this (needs MACS2):
proj <- addReproduciblePeakSet(proj, groupBy = "Clusters", pathToMacs2 = findMacs2())
proj <- addPeakMatrix(proj)
markers <- getMarkerFeatures(proj, useMatrix = "PeakMatrix", groupBy = "AgeGroup")

# With this (no MACS2):
proj <- addTileMatrix(proj, tileSize = 500, force = TRUE)
markers <- getMarkerFeatures(proj, useMatrix = "TileMatrix", groupBy = "AgeGroup",
  bias = c("TSSEnrichment", "nFrags"), testMethod = "wilcoxon")
da_tiles <- getMarkers(markers, cutOff = "FDR <= 0.05 & abs(Log2FC) >= 0.5")
```

### Trade-offs
| Aspect | PeakMatrix (MACS2) | TileMatrix |
|--------|:---:|:---:|
| Resolution | Peak-level (variable) | 500bp fixed bins |
| Requires MACS2 | Yes | No |
| Motif analysis | addMotifAnnotations | Convert tiles→peaks first |
| Differential analysis | getMarkerFeatures | getMarkerFeatures |
| Publication standard | Gold | Accepted alternative |

## Verified
- Windows 11, Python 3.12.10, R 4.5.3, ArchR 1.0.3
- 35,879 cells monkey hippocampus scATAC-seq, 21 clusters
- Session: memomics-1c1890da, 2026-07-29
