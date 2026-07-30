# Import GEO Public ATAC Fragment Files into ArchR

## When to use this guide

When a GEO dataset provides pre-processed ATAC fragment files (`.tsv.gz` + `.tbi.gz` Tabix-indexed) instead of raw fastq. This is common for high-profile publications — saves alignment step entirely.

## Key GEO ATAC data pattern

Many recent ATAC-seq datasets on GEO provide fragment files in supplementary data:
- `*_fragments.tsv.gz` — gzipped TSV: columns are typically `chr`, `start`, `end`, `barcode`, `count`
- `*_fragments.tsv.gz.tbi.gz` — gzipped Tabix index

These can be **directly imported into ArchR** via `createArrowFiles()` — no alignment needed.

## Known human hippocampus ATAC datasets

| Dataset | Samples | Tissue | Direction | Publication | Format |
|---------|:-------:|--------|-----------|-------------|--------|
| **GSE278576** | 40 ATAC | Hippocampus | Aging | Science 2026, PMID 42490474 | fragments.tsv.gz |
| GSE147672 | 26 (hipp) | Multi-region brain | AD/PD reference | — | bulk/scATAC |
| GSE226529 | 6 | Hippocampus | AD vs Control | — | bulk ATAC |

## ENCODE limitation

ENCODE has **no human hippocampus ATAC-seq** as of 2026-07. All 4 `snATAC-seq` experiments under "hippocampus" are *Mus musculus*. For brain ATAC data, GEO is the primary source.

## Import workflow

```r
library(ArchR)

# Step 1: Download fragment files from GEO FTP
# ftp://ftp.ncbi.nlm.nih.gov/geo/samples/GSM8549nnn/GSM8549XXX/suppl/

# Step 2: Create Arrow files directly from fragments
addArchRGenome("hg38")

ArrowFiles <- createArrowFiles(
  inputFiles = c(
    "sample1_fragments.tsv.gz",
    "sample2_fragments.tsv.gz"
  ),
  sampleNames = c("sample1", "sample2"),
  minTSS = 4,
  minFrags = 1000,
  addTileMat = TRUE,
  addGeneScoreMat = TRUE
)

proj <- ArchRProject(
  ArrowFiles = ArrowFiles,
  outputDirectory = "ArchR_Output",
  copyArrows = TRUE
)
```

## Metadata retrieval

GEO Series Matrix files (`GSE278576_series_matrix.txt.gz`) contain sample characteristics (age, sex, tissue). Download from:
`https://ftp.ncbi.nlm.nih.gov/geo/series/GSE278nnn/GSE278576/matrix/`

Extract with Python:
```python
import GEOparse
gse = GEOparse.get_GEO(geo="GSE278576", destdir="./")
# Access sample characteristics via gse.phenotype_data
```

## File size estimation

Typical human ATAC fragment file: 1-3 GB per sample (tsv.gz). 40 samples ≈ 80-120 GB total.
Consider downloading a subset first to validate the import pipeline.
