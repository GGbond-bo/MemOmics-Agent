# Final 8-Class Annotations — User-Confirmed (2026-08-27)

Both annotations confirmed by user. Source of truth — do NOT override with marker analysis.

## Human Hippocampus (40 samples, 265,909 cells, 30 clusters)

| cellType8 | Clusters | Count |
|-----------|----------|-------|
| OPC | C1, C2, C3, C4, C5, C6 | 6 |
| Astro | C7, C8, C9, C10, C11, C12 | 6 |
| Unknown | C13 | 1 |
| InN | C14, C15, C16 | 3 |
| ExN | C17, C18, C19 | 3 |
| Micro | C20, C21, C22, C23 | 4 |
| ODC | C24, C25, C26, C27, C28, C29, C30 | 7 |

**Notes**:
- C13 = Unknown (HOX+/MNX1+, peripheral tissue contamination, no literature support)
- C24/C27 = no FDR-significant markers but real clusters (QC normal)
- C26 = ODC despite debate saying OPC-like (UMAP topology overrides; see P15/P20)

## Macaque Hippocampus (63 samples, 161,497 cells, 18 clusters)

| cellType8 | Clusters | Count |
|-----------|----------|-------|
| ExN | C2, C3, C4, C8, C9, C10, C11 | 7 |
| InN | C5, C6, C13, C14 | 4 |
| Astro | C1, C12 | 2 |
| Micro | C15 | 1 |
| OPC | C17 | 1 |
| ODC | C16 | 1 |
| VS | C18 | 1 |
| ChP | C7 | 1 |

**Notes**:
- Monkey has VS (C18) and ChP (C7) — human does not have distinct VS/ChP clusters
- Monkey ExN has fine subclusters (DG/CA1/CA2/EC from predictedAnno), but 8-class maps to broad ExN

## ArchR Write-back Code Templates

### Human
```r
# See templates/archR_annotate_writeback.R for full template
# Mapping vector:
map_human <- c(
  "1"="OPC","2"="OPC","3"="OPC","4"="OPC","5"="OPC","6"="OPC",
  "7"="Astro","8"="Astro","9"="Astro","10"="Astro","11"="Astro","12"="Astro",
  "13"="Unknown",
  "14"="InN","15"="InN","16"="InN",
  "17"="ExN","18"="ExN","19"="ExN",
  "20"="Micro","21"="Micro","22"="Micro","23"="Micro",
  "24"="ODC","25"="ODC","26"="ODC","27"="ODC","28"="ODC","29"="ODC","30"="ODC"
)
```

### Monkey
```r
# NOTE: monkey keys are predictedAnno NAMES (张潇 18-subtype IDs), NOT Clusters — see SKILL P21.
# Apply to as.character(proj$predictedAnno) AFTER reading levels; safer to key by name:
map_monkey <- c(
  "Astrocyte"="Astro",
  "CA1_SUB s_f_Ex"="ExN","CA2_4 EX"="ExN","DG Ex"="ExN","EC L2 EX"="ExN",
  "EC L3_5 EX"="ExN","EC L6 EX"="ExN","CAE_SUB deep Ex"="ExN",
  "MGE SST lnh"="InN","MGE PVALB lnh"="InN","CGE CNR1 lnh"="InN","CGE LAMP5 lnh"="InN",
  "Microglia"="Micro",
  "OPC"="OPC","ODC"="ODC",
  "Ependymal"="VS","VS"="VS",
  "Choroid Plexus"="ChP"
)
# proj$cellType8 <- map_monkey[as.character(proj$predictedAnno)]
```
