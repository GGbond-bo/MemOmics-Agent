# Final User-Confirmed Annotations — Both Species (2026-08-28)

User's authoritative cluster→cellType8 maps. **Source of truth; do NOT re-annotate, do NOT override with marker analysis.**

## Human (30 clusters, `human_Hf_ATAC_40_clustered.rds` → `proj$Clusters` values C1..C30)

| CellType | Clusters |
|---|---|
| ExN | 18, 17, 19 |
| InN | 14, 15, 16 |
| Astro | 7, 8, 9, 10, 11, 12 |
| Micro | 20, 21, 22, 23 |
| OPC | 1, 2, 3, 4, 5, 6 |
| ODC | 24, 25, 26, 27, 28, 29, 30 |
| Unknown | 13 |

Copy-paste R (cluster keys are the `Clusters` column; strip the "C" prefix):

```r
ct <- c("1"="OPC","2"="OPC","3"="OPC","4"="OPC","5"="OPC","6"="OPC",
        "7"="Astro","8"="Astro","9"="Astro","10"="Astro","11"="Astro","12"="Astro",
        "13"="Unknown",
        "14"="InN","15"="InN","16"="InN",
        "17"="ExN","18"="ExN","19"="ExN",
        "20"="Micro","21"="Micro","22"="Micro","23"="Micro",
        "24"="ODC","25"="ODC","26"="ODC","27"="ODC","28"="ODC","29"="ODC","30"="ODC")
cl <- sub("C", "", as.character(proj$Clusters))
proj$cellType8 <- unname(ct[cl])
stopifnot(!any(is.na(proj$cellType8)))
```

## Monkey (18 predictedAnno subtypes, `monkey_Hf_ATAC_final.rds` → **`proj$predictedAnno`**, NOT `proj$Clusters`)

⚠️ Integer keys are **张潇's predictedAnno manuscript codes** — resolve against the `predictedAnno` column values, never cluster IDs (P21).

| CellType | predictedAnno codes |
|---|---|
| ExN | 2, 3, 4, 8, 9, 10, 11 |
| InN | 5, 6, 13, 14 |
| Astro | 1, 12 |
| Micro | 15 |
| OPC | 17 |
| ODC | 16 |
| VS | 18 |
| ChP | 7 |

Copy-paste R — **safest form uses predictedAnno NAMES as keys** (sidesteps numbering ambiguity; see P1 factor-indexing and P21):

```r
ct_map <- c(
  "Astrocyte"="Astro",
  "CA1_SUB s_f_Ex"="ExN", "CA2_4 EX"="ExN", "DG Ex"="ExN",
  "EC L2 EX"="ExN", "EC L3_5 EX"="ExN", "EC L6 EX"="ExN", "CAE_SUB deep Ex"="ExN",
  "CGE CNR1 lnh"="InN", "CGE LAMP5 lnh"="InN",
  "MGE SST lnh"="InN", "MGE PVALB lnh"="InN",
  "Microglia"="Micro", "OPC"="OPC", "ODC"="ODC",
  "Ependymal"="VS", "VS"="VS", "Choroid Plexus"="ChP"
)
proj$cellType8 <- unname(ct_map[as.character(proj$predictedAnno)])
table(proj$cellType8, useNA="always")
```

Note: Ependymal + VS → VS; Choroid Plexus → ChP (user's grouping — Ependymal 879 + VS 624 → VS, Choroid Plexus 702 → ChP).

## Verification
- Human: 265,909 cells, all 30 clusters mapped, no NA (Unknown only for C13).
- Monkey: 161,497 cells, all 18 predictedAnno subtypes mapped, no NA.
- Both written back as `cellType8` column via `addCellColData(..., force=TRUE)` or direct `proj$cellType8 <-`.