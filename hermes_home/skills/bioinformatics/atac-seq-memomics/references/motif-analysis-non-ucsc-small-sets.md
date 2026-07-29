# Motif Enrichment for Non-UCSC Genomes with Small DA Tile Sets

## Problem

When running motif enrichment on DA tiles from T2T/non-UCSC genomes:
1. **JASPAR2024 broken API** — `getMatrixSet(JASPAR2024)` fails. Use **JASPAR2020**.
2. **NCBI→UCSC chr mapping** — T2T assemblies use NC_088xxx.1, BSgenome uses chr1
3. **T2T coords exceed BSgenome bounds** — older BSgenome (rheMac10) shorter than T2T → `getSeq` fails "beyond boundaries"
4. **48-60 tiles too few for Fisher test** — 633 motifs × Bonferroni → all FDR=1

## Verified Workflow (2026-07-29, macaque hippocampus T2T)

### 1. NCBI→UCSC mapping + bounds check
```r
nc2chr <- c("NC_088375.1"="chr1", ..., "NC_088395.1"="chrX")
make_gr <- function(df, genome) {
  df$chr <- nc2chr[df$seqnames]
  df <- df[!is.na(df$chr), ]
  df$end <- df$start + 499
  clen <- seqlengths(genome)
  df <- df[df$end <= clen[df$chr], ]  # bounds check
  GRanges(seqnames=df$chr, ranges=IRanges(start=df$start, end=df$end))
}
```

### 2. JASPAR2020 + score-based ranking
```r
library(JASPAR2020)  # NOT JASPAR2024
motifs <- getMatrixSet(JASPAR2020, list(species=9606, collection="CORE"))
scores <- matchMotifs(motifs, seqs, genome=genome, out="scores")
# Rank by mean score fold-change (not p-value — 48 tiles too few)
results <- data.frame(
  motif = colnames(scores),
  fc = colMeans(assay(fg_scores)) / pmax(colMeans(assay(bg_scores)), 0.001)
)[order(-fc), ]
```

### 3. Annotate IDs → TF names
```r
sapply(head(results$motif, 10), function(id) name(motifs[[id]]))
```

## Key Results (Macaque Hippocampus Aging)
| Group | Top TF | FC | Relevance |
|-------|--------|:--:|-----------|
| OLD | CEBPB | 5.28 | Inflammation/senescence pioneer TF |
| OLD | ZFP57 | 6.14 | Imprinting maintenance |
| YOUNG | HOXB8 | 8.38 | Adult neurogenesis |
| YOUNG | FOSL1::JUND | 3.40 | AP-1, synaptic plasticity |

## Common Pitfalls
- `names(gr)` returns empty — use `as.character(seqnames(gr))`
- `assay(fg_scores)` is a matrix, NOT `assay(fg_scores)[[1]]`
- Always filter tiles beyond BSgenome boundaries before `getSeq`
