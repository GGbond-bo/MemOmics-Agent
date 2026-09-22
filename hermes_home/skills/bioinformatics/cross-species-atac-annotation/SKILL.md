---
name: cross-species-atac-annotation
description: >
  Cross-species ATAC-seq cell type annotation strategy: align fine-grained subclusters where possible,
  keep species-specific names for non-overlapping populations. For human-macaque hippocampus ATAC comparison.
trigger_words:
  - "跨物种注释"
  - "cross-species annotation"
  - "人猴注释"
  - "对齐亚群"
  - "subcluster alignment"
  - "predictedAnno"
  - "cellType8"
category: user-skill
source: user-requested
---

# Cross-Species ATAC-seq Cell Type Annotation

## Core Principle (User-Corrected, 2026-08-27)

**DO NOT** force all cells into 8 broad classes. Instead:
1. **Align fine-grained subclusters** where markers match across species → use SAME name
2. **Keep species-specific names** for populations that don't overlap → use ORIGINAL paper's name
3. This preserves biological resolution while enabling cross-species comparison

## Workflow

### Step 1: Check Original Paper's Annotations First

**ALWAYS** check if the original paper provides cell type annotations in supplementary materials before doing custom annotation.

For GEO datasets:
```python
# Search GEO for supplementary files
get_geo_details(accession="GSE278576")
# Look for *_cell_metadata.txt.gz or similar
# Download and check cell_type column
```

**Why**: Zemke 2024 (GSE278576) already had 18 cell types in `human_hippocampus_cell_metadata.txt.gz`. Custom annotation was unnecessary.

### Step 2: Extract Marker Lists from Both Species

**🔴 First: read reference species' REAL annotation from its rds — never compute/wait for it.**

```r
monkey <- readRDS("E:/专利/patent/monkey_Hf_ATAC_final.rds")
meta <- getCellColData(monkey)
sort(table(meta$predictedAnno), decreasing=TRUE)
```

**Why this matters (2026-08-27 lesson)**: The macaque getMarkerFeatures job had been stuck for DAYS. That computation is **unnecessary for annotation** — the target species (human) marker list + the reference species' existing `predictedAnno` column is all you need. Cross-species annotation never requires recomputing reference markers; only target-species markers drive the mapping.

**Authoritative macaque annotation (from rds predictedAnno, 2026-08-27)** — note this DIFFERS from the manuscript's stated subtypes; trust the rds:
ODC (44,021) / DG Ex (28,854) / Astrocyte (23,548) / CA1_SUB s.f. Ex (16,457) / Microglia (9,388) / CA2_4 EX (7,833) / EC L3_5 EX (6,878) / OPC (6,574) / EC L6 EX (3,669) / EC L2 EX (3,226) / CGE CNR1 Inh (2,190) / CAE_SUB deep Ex (2,130) / MGE SST Inh (1,884) / CGE LAMP5 Inh (1,408) / MGE PVALB Inh (1,232) / Ependymal (879) / Choroid Plexus (702) / VS (624)
(manuscript list said "Ast1/2/3, ODC1/2, OPC1/2, Mic1/2/3, Macrophage" — the rds uses simple names Astrocyte/ODC/OPC/Microglia, and includes Ependymal/Choroid Plexus/VS. Always read the actual column.)

**Human (Zemke 2024)**:
- From `human_40_markerList.csv` (getMarkerFeatures output)
- Filter non-coding genes (LOC/MIR/LINC/-AS1/SNORD/KRTAP) before matching

### Step 3: Match Markers and Annotate

**Proven technique (2026-08-27): marker-dictionary weighted scoring over top-60 coding genes.**

```python
# 1. Build per-celltype marker dictionary from consensus brain markers
marker_dict = {
    'ODC': ['OPALIN','MAG','MBP','MOG','PLP1','KLK6','MCAM', ...],
    'OPC': ['CSPG4','PDGFRA','OLIG1','OLIG2','MYT1','SOX6','ASCL1','DLL3','SOX1', ...],
    'Astrocyte': ['GFAP','AQP4','SLC1A2','ALDH1L1','GJA1','S100B','EDNRB','EMX2','LHX2','ZIC5','OTX1', ...],
    'Microglia': ['CX3CR1','P2RY12','P2RY13','TMEM119','C1QA','C1QB','TYROBP','ABI3','IRF8','LILRB4', ...],
    'Microglia_activated': ['CXCL10','CLEC5A','S100A8','CD163','CASP1','FPR2','CCL11', ...],
    'VS': ['CLDN5','FOXC2','FOXF1','FOXF2','ICAM2','VWF','FLT1','PECAM1', ...],
    'MGE_Inh': ['DLX1','DLX6','LHX6','SLC32A1','GAD1','GAD2','SST','PVALB','TAC1','NPY','NKX2-1','SNCB','SRRM4'],
    'CGE_Inh': ['ADARB2','CNR1','LAMP5','VIP','CCK','RELN','SP8','GJD2','INA'],
    'ExN_common': ['SLC17A7','SLC17A6','NRGN','NEUROD2','NEUROD6','STMN2','GAP43','EGR4', ...],
    'EC_L6': ['FEZF2','BCL11B','TLE4','SOX5'], 'EC_L23': ['CUX1','CUX2','SATB2','RORB'],
    'CA1_SUB': ['SSTR2','WFS1','HRH2','NR3C2'], 'DG': ['PROX1','PDYN','DCN','CALB1','TCF21'],
}
# 2. Weighted hit score per cluster: rank<10 → ×2, rank<30 → ×1.5, else ×1
# 3. Best celltype = max score; second score tells ambiguity; write matrix to CSV for audit
```

Filtering rules before scoring: drop `MIR*`, `LOC*`, `LINC*`, `OR*`, `ENSG*`, `*AS1`, `*-AS*`, `*-DT`, `SNORD*`, `KRTAP*`.

Scoring output `marker_scoring_matrix.csv` gives every cluster's best/second annotation + hit genes — the **evidence audit trail** the user demands ("一定要有依据").

Confidence rules (validated):
- **Score ≫ second score** → high confidence, use reference name
- **ExN_common dominant but NO subregion-specific marker** (no PROX1=DG, no SSTR2/WFS1=CA1) → keep original cluster name + annotate as `Cxx (ExN)`; do NOT hard-assign DG/CA1/CA2_4/EC
- **One subregion marker hits (e.g. SSTR3 for CA1)** → **candidate-level name with like-suffix + \*** (`CA1-like Ex*`): SSTR3(2.34) is CA1-classic but ATAC accessibility Log2FC ≠ expression and SSTR3 alone is not CA1-exclusive → ALWAYS verify CA1 confirmatory markers WFS1/SORL1 and CA3 marker GRIK1/NR4A2 first; absent → candidate only (2026-08-28: C19/C18 SSTR3 hit, WFS1/SORL1未命中 → named `CA1-like Ex*` / `CA1/SUB-like Ex*`; C17 FEZF2+BCL11B double-hit → `CTX-deep Ex`, evidence stronger, still subregion-named)
- **Score ≈ second score** (e.g. Microglia 24 vs activated 15.5) → activated subtype exists as human-specific population; name by marker signature
- **No score (≤3 markers total)** → keep original name, mark low-confidence/noise

### Step 4: Deliver in the User's Native Toolchain (ArchR write-back, 2026-08-28)

**⚠️ When the user says "我是用ArchR跑的" / "给我代码，我直接注释人脑" → they run ArchR on their own cluster and want a copy-paste R script, NOT a Python scoring script or just a CSV.**

Delivery shape:
1. Give them a minimal ArchR R script: `loadArchRProject` → `getCellColData` → map cluster→name → `addCellColData(..., force=TRUE)` → `saveArchRProject`. Template: `templates/archR_annotate_writeback.R`
2. The annotation map is the SAME mapping you validated in the local analysis (alignment names for matching clusters, marker-derived names for species-specific ones with `*`/`like` convention, original names for low-confidence clusters) — just expressed as a named character vector keyed by their cluster column (default `Clusters`).
3. Include `stopifnot` coverage check so missing clusters fail loudly; warn on extra keys.
4. Remind them the markerList CSV **is already the getMarkerFeatures output** (columns `group_name`/`name`/`Log2FC`/`FDR`) — annotation does NOT require re-running getMarkerFeatures. If a feature job is stuck for days, it can be killed; it's only needed for intra-species DE, not for annotation.

**User preference at this point**: minimal code, paste-in-chat style ("只要怎么读取怎么出图的代码就可以"), no wrapper functions, no defensive checks beyond the essential `stopifnot`.

### Step 5: Annotation Decision Table

| Confidence | Action | Example |
|-----------|--------|---------|
| High (≥3 markers) | Use reference name | C10/C11 → Astrocyte |
| Medium (2 markers) | Use reference name + note | C8 → Astrocyte (partial) |
| Low (1 marker) | Use reference name cautiously | C20 → Microglia (low) |
| No match + no literature support | Annotate **Unknown** | C13 → Unknown (HOX genes, no ATAC lit) |

## Key Findings from Human-Macaque Hippocampus ATAC (final, 2026-08-27)

### Aligned to monkey name (user-confirmed 2026-08-27, FINAL)
| Human cluster | Annotation | Marker evidence |
|---|---|---|
| C1-C6 | **OPC** | CSPG4, MYT1, SOX6, SOX1, ASCL1, DLL3 |
| C7-C12 | **Astrocyte** | GFAP, AQP4, SLC1A2, ALDH1L1, EMX2, LHX2, ZIC5 |
| C14, C15, C16 | **InN** | DLX1, DLX6, LHX6, SLC32A1, GAD1, SNCB |
| C17, C18, C19 | **ExN** | NEUROD2/6, NRGN, SSTR3, FEZF2, EGR4 |
| C20, C21, C22, C23 | **Micro** | CX3CR1, P2RY12, P2RY13, TYROBP, ABI3, IRF8 |
| C24, C25, C26, C27, C28, C29, C30 | **ODC** | OPALIN, MAG, KLK6, PLP1, MOG (C26 UMAP overlaps ODC group despite noisy DE peaks; see P15) |

### Human-specific notes
- **C13** → **Unknown** (HOX+/MNX1+, no literature support; see P19)
- **C26** → **ODC** (debate said OPC-like, but UMAP topology overrides — overlaps C24-C30; see P15)
- **C24/C27** → no FDR-significant markers (P7), but real clusters (QC normal, spread across samples)

### Step 5.5: FINAL User-Confirmed Annotations (2026-08-28) — Use These, Stop Re-Annotating

**User gave the definitive cluster→cellType8 maps for BOTH species (do NOT override with marker analysis — user said "全部注释成功"):**
- **Human** (30 clusters, keyed on `Clusters` C1..C30): OPC=C1-6, Astro=C7-12, Unknown=C13, InN=C14-16, ExN=C17-19, Micro=C20-23, ODC=C24-30
- **Monkey** (keyed on **`predictedAnno` manuscript codes**, NOT `Clusters`): ExN=2,3,4,8,9,10,11; InN=5,6,13,14; Astro=1,12; Micro=15; OPC=17; ODC=16; VS=18; ChP=7

Copy-paste-ready R for both species: `references/final_annotations_user_confirmed_20260828.md` (exact vectors + factor-indexing-safe code, monkey map expressed with predictedAnno NAMES as keys to sidestep numbering ambiguity).

**User workflow preference at this point**: they run ArchR on their OWN cluster and just want copy-paste R scripts. "给我一个参考代码就行" / "分别给我两个干净代码" — deliver complete, runnable R with no wrapper functions; include `stopifnot(!any(is.na(...)))` as the only guard. When they say "我这边已经确定好注释了", map exactly what they give; do not propose marker-based "corrections" afterwards.

### Step 6: Verify Age Metadata Before species×age Analysis (2026-08-27)

When the patent's next phase needs a species×age (CRE conservation) model, FIRST verify where each species' donor-age info lives — do NOT assume the rds has it:

```r
# 1. Check rds for age columns
colnames(getCellColData(proj))   # look for Age / Age_group / Individual
# Monkey (张潇): ✅ has Age + Age_group (21 indiv, 63 libs, ages 5-31, 4 groups)
# Human (Zemke): ❌ no Age column — only Sample (GSM..._hcXX), tissue, donor id

# 2. If missing, check GEO series matrix characteristics
#    Human GSE278576 series matrix only has "tissue: hippocampus" + "donor id: hcXX" — NO age field
```

**Key facts**: Monkey age is in-rds and ready to model (`Age_group`: Young/Middle/Old/Exceptionally old). Human donor→age is NOT in the rds or GEO series matrix — it lives in the article's supplementary metadata (PMID 39463924). If the user can't supply the donor-age table: (a) model species main effect only (no interaction), or (b) ask user for the supplementary table. Never fabricate donor ages ("一定要有依据").

Full detail in `references/gse278576_metadata.md` (second half).

## Pitfalls

### P1: Factor Indexing in R (CRITICAL)
```r
# WRONG — factor indexing uses integers, not names
proj$cellType8 <- map8[proj$predictedAnno]  # BUG!

# CORRECT — convert to character first
proj$cellType8 <- map8[as.character(proj$predictedAnno)]
```
**Root cause**: ArchR stores categorical columns as factors. `map8[factor]` indexes by integer position, not by name.

### P2: Non-coding Gene Pollution
ATAC marker lists contain大量 LOC/MIR/LINC/-AS1 genes that obscure real markers.
**Fix**: Always filter to coding genes before cross-species matching.

### P3: getMarkerFeatures Performance
- GeneScoreMatrix + 160K cells + 30 clusters: ~2 minutes
- PeakMatrix + 160K cells + 30 clusters: 30-60 minutes
- Use `testMethod="U"` (Wilcoxon) or `"G"` (Gaussian, faster)
- **⚠️ On a busy/stuck session it can hang for DAYS — never let annotation block on it.** Reference-species marker features are NOT needed for cross-species annotation (the `predictedAnno` column already exists in the rds). Only the TARGET species' marker list is required. If the user says "feature 跑了好几天" — proceed with target markers + reference predictedAnno immediately and tell them the feature computation is only needed for intra-species DE, not annotation.

### P4: QC Thresholds (Zhang Xiao 2026 Official)
- TSS ≥ 4
- nFrags ≥ 3000
- These are NOT sufficient to identify low-quality clusters — need additional QC (DoubletScore, FRiP)

### P5: rds is source of truth, not the manuscript
The manuscript's stated subtype list (e.g. "Ast1/2/3, ODC1/2, Mic1/2/3, Macrophage") did NOT match the actual `predictedAnno` column in the monkey rds (which used Astrocyte/ODC/OPC/Microglia + Ependymal/Choroid Plexus/VS). Always `sort(table(getCellColData(rds)$predictedAnno))` and use those exact strings for comparison — otherwise alignment names will silently diverge.

### P6: VS vs Macrophage mislabel (2026-08-28, real error caught)
C21 was first labeled **VS** because its marker list contained `CLDN5, FOXC2, FOXF1, FOXF2, ICAM2` — but those were the *only top-25 markers shown*, and CLDN5/ICAM2 are shared by endothelial AND perivascular macrophage populations. Looking at the FULL top-25, the dominant signal was **CCL18, CCL3, CCL23, CCL5, CCL11** (chemokine family) → vascular-associated **Macrophage**, matching monkey `Macrophage` subtype (LYVE1/F13A1/CCL18).
**Fix**: when a cluster shows BOTH vascular markers (FOXC2/FOXF2/CLDN5) AND CCL-family chemokines, the CCL family wins → Macrophage, not VS. Never decide VS/fibroblast vs Macrophage from the FOX genes alone — check the full top-25 for CCL/CXCL chemokines first.

### P7 (CORRECTED 2026-08-28): markerList cluster count ≠ RDS cluster count — NEVER infer "missing" clusters from the marker list
**Wrong earlier claim (self-corrected after user challenge: "人脑不是有30个亚群吗？" / "length(unique(proj@cellColData$Clusters))这里不是30吗？"):** the human markerList CSV has only 28 rows → I concluded "C24/C27 do not exist". **That inference was WRONG.**

**Verified truth:** `length(unique(proj@cellColData$Clusters))` = **30** — the RDS `human_Hf_ATAC_40_clustered.rds` contains C1–C30 continuously (265,909 cells). The markerList only emits rows for clusters that had ≥1 marker passing `FDR<0.01 & Log2FC>1`; C24 (n=3,089) and C27 (n=4,821) have **no significant markers**, so getMarkerFeatures silently dropped their rows — the clusters still exist in the data.

**Rules:**
1. **Cluster inventory source of truth = RDS cellColData** (`sort(unique(proj$Clusters))` or `length(unique(proj@cellColData$Clusters))`), NEVER the markerList `group_name` column.
2. Absence in marker list = "no significant DE markers under cutoff", NOT "cluster doesn't exist".
3. Marker-less clusters can still be real populations: check QC from cellColData (TSS/nFrags/DoubletScore/sample distribution). C24/C27: TSS 10.1/8.2 (≥4 OK), nFrags 9.9K/12.3K, DoubletScore 0, spread across 30–40 samples → real, gradually-differentiated clusters (ArchR Wilcoxon frequently yields no FDR-significant peaks for such groups — known behavior).
4. To name them: run a **minimal pairwise comparison** (only those clusters vs `Rest` → 2 groups) with relaxed `cutOff="FDR<=0.1"` — far faster than the full 30-cluster comparison and won't hang for days.
5. Keep `assert set(present) == expected_set` in scripts, but base `expected_set` on the RDS cluster vector, not on pre-conceived counts.

### P8: Why ATAC annotation is harder/slower than RNA (user-facing explanation, 2026-08-27)
When user asks "为什么ATAC比RNA注释这么麻烦" / "为什么这么慢":
1. **Signal gap**: RNA = direct gene expression (1 gene = 1 value); ATAC = chromatin accessibility (1 gene = 5-10 peaks, you don't know which is the "master switch")
2. **Reference scarcity**: scRNA has Human Cell Atlas / Tabula Sapiens / CellMarker (millions of cells); scATAC hippocampus reference is nearly nonexistent — manual marker-based annotation required
3. **Verification bottleneck**: RNA markers validate across any RNA dataset; ATAC markers require same-species same-tissue ATAC data (public ATAC datasets are 10-100× rarer than RNA)
4. **Scale**: 30 clusters × 160K cells × 300K peaks = ~10M statistical tests per comparison; Wilcoxon on PeakMatrix takes 30-60 min vs ~2 min for GeneScoreMatrix
5. **Cross-species harder**: RNA orthologs mostly 1:1; ATAC peaks are species-specific even when genes are conserved — must annotate each species independently

### P10: S100B and the ATAC Expression-Accessibility Gap (2026-08-27 user correction, expanded 2026-08-27)

**User challenge**: "25, 27, 28, 29, 30，人脑这几个亚群高表达S100B啊，你真的对吗？"

**Root cause**: The8-class marker dictionary correctly includes S100B as an Astrocyte marker, but `getMarkerFeatures` (Wilcoxon on PeakMatrix) did NOT find S100B as a significant peak-level marker for ANY cluster. This means:
- S100B gene locus is accessible (it's a real gene) but its peaks don't show **differential** accessibility between clusters
- Yet the user says S100B is "highly expressed" — confirmed via `plotEmbedding(colorBy="GeneScoreMatrix")` showing high S100B imputed gene accessibility in C25/C27/C28/C29/C30
- **ATAC accessibility ≠ RNA expression**: a gene can be highly expressed (RNA/GAS) but its chromatin peaks may be similarly open across all cell types → no differential signal → getMarkerFeatures drops it

**Impact on annotation**: The8-class dictionary scoring missed S100B contribution entirely because S100B never appeared in the marker list. C25/C27/C28/C29 were annotated as ExN with "weak/none" evidence (0-5 DEGs each), when they should have been Astrocyte based on S100B GeneScoreMatrix.

**Fix strategy** (when user flags expression markers not in ATAC marker list):
1. **🔴 FIRST: `plotEmbedding` visual check (user-proven method, 2026-08-27)**:
```r
markerGenes <- c("GFAP","ALDH1L1","S100B","AQP4",  # Astro
                 "SLC17A7","CAMK2A","NRGN",           # ExN
                 ...)  # all cell type markers
p <- plotEmbedding(ArchRProj = proj, colorBy = "GeneScoreMatrix",
                   name = markerGenes, embedding = "UMAPHarmony",
                   imputeWeights = getImputeWeights(proj))
```
This is the **most reliable verification** — GeneScoreMatrix aggregates peak accessibility near gene bodies via imputation, catching signal that individual peak-level tests miss. If a cell type marker lights up in the right clusters, trust it over the DEG list.
2. **Check GAS (Gene Activity Score)**: `getGeneScoreMatrix(proj)` → extract S100B row → compare across clusters. GAS aggregates peak accessibility near the gene body, which may capture signal that individual peak-level tests miss.
3. **Check peak matrix directly**: `getAvailableMatrices(proj)` → PeakMatrix → extract peaks near S100B locus (chr1:15,350,000-15,450,000 hg38) → compare accessibility across clusters.
4. **Pairwise comparison for low-marker clusters**: Use P9 method (pairwise vs Rest, relaxed FDR≤0.1) — this often recovers markers that the full 30-cluster comparison misses due to multiple testing burden.
5. **Cross-reference with RNA**: If scRNA-seq data exists for same tissue, check S100B expression in RNA to confirm whether these clusters are genuinely Astrocyte.

**General rule**: When user says "cluster X expresses gene Y" but gene Y is not in the ATAC marker list, **never dismiss** — investigate GAS/peak matrix/pairwise comparison. The marker list is a filtered subset, not the full picture.

**🔴 NEW RULE (2026-08-27): Always cross-check annotation with `plotEmbedding(colorBy="GeneScoreMatrix")` for canonical markers.** The DEG-based annotation pipeline has a blind spot: genes that are accessible across many cell types (like S100B in all Astrocytes) won't show up as differentially expressed, but GeneScoreMatrix will show them. This is especially critical for clusters with ≤5 DEGs (evidence=weak/none) — these are most likely to be mis-annotated.

**⚠️ Small cluster noise filter**: Clusters with ≤8 cells (C25=2, C28=2, C30=8) should be flagged as potential doublets/artifacts regardless of marker profile. Check DoubletScore and sample distribution before assigning cell type.

### P11: Standard CNS Marker List for ATAC Annotation (2026-08-27, user-provided)

**User-provided marker list** (34 genes, 9 cell types):
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
```

**Why this is more reliable than peak-level DEG scoring**:
1. **Standard marker list** is curated from published brain atlases (Allen Brain Atlas, Tabula Sapiens, etc.)
2. **GeneScoreMatrix aggregation** captures signal that individual peak-level tests miss
3. **User-verified**: This list correctly identifies S100B as Astro marker (peak-level DEG missed it)

**Workflow correction (2026-08-27)**:
- **OLD approach**: Run `getMarkerFeatures` → use top DEGs for annotation → miss markers like S100B
- **NEW approach**: Use standard marker list + `plotEmbedding(colorBy="GeneScoreMatrix")` → verify visually → then refine with DEGs if needed

**Iterative annotation strategy (user preference, 2026-08-27)**:
1. **Step 1**: Use standard marker list to identify major cell types (ExN/InN/Astro/Micro/OPC/ODC/VS/ChP)
2. **Step 2**: Check if subtypes can be resolved within each major type
3. **Step 3**: For subtypes, use additional markers (e.g., PROX1 for DG, WFS1 for CA1)
4. **Step 4**: Document evidence for each annotation (marker expression, cluster size, sample distribution)

### P12: Oligodendrocyte (OPC/ODC) Annotation Gap — Rare Cell Type Under-Recovery (2026-08-27)

**Symptom**: Human hippocampus 40-sample ATAC data has only 8 ODC cells (C30, marker: OPALIN/MAG) and 0 OPC clusters — expected 5-15% oligo (~1,000-3,000 cells).

**Root cause analysis (3 hypotheses, ordered by likelihood)**:
1. **Clustering resolution too low** (most likely): resolution=0.8 merged OPC+ODC into larger clusters. CSPG4 (OPC marker) appears in C1-C6 (ExN-annotated), suggesting OPC cells are mixed into ExN clusters.
2. **QC over-filtering**: ODC cells have low nFrags (fewer open chromatin regions) → filtered out by nFrags≥3000 threshold.
3. **Biological**: CSPG4 may be expressed in developing neurons (not purely OPC), but this needs validation.

**Diagnostic (30-second GeneScoreMatrix check)**:
```r
proj <- loadArchRProject("path/to/ArchRProject")
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
**Interpretation**: If CSPG4/PDGFRA light up in C1-C6 → those clusters contain OPC cells mixed with ExN. If they don't → CSPG4 in the marker list is a false positive (biological dual-role or technical).

**Key markers for oligo diagnosis**:
- **OPC**: CSPG4, PDGFRA, SOX6, SOX10, OLIG1, OLIG2
- **ODC (mature)**: OPALIN, MAG, MBP, PLP1, MOG, MOBP, KLK6, MCAM
- **Red flag**: If only OPALIN/MAG appear (like C30) but MBP/PLP1/MOG don't → the ODC population is immature or the marker list is incomplete

**Action when oligo count is suspiciously low**:
1. Run GeneScoreMatrix diagnostic above
2. Check if CSPG4+ cells are scattered in ExN clusters (resolution issue)
3. Check QC metrics for ODC-like cells (low nFrags = QC loss)
4. Consider re-clustering at higher resolution for the OPC/ODC fraction

**Cross-species check**: Macaque has ODC (44,021 cells, 27%) and OPC (6,574 cells, 4%) — healthy proportions. If human has <1% oligo, the discrepancy is technical, not biological.

### P13: Reference Paper for Hippocampal ATAC Annotation (2026-08-27)

**Paper**: "Dysregulated adult hippocampal neurogenesis in major depressive disorders"
- **PMID**: 42629468
- **Journal**: Nature Medicine (2026)
- **DOI**: 10.1038/s41591-026-04571-8
- **Relevance**: May contain ATAC-seq annotation for human hippocampus cell types

**Action**: Download and review this paper for:
1. Cell type annotation strategy (what markers they used)
2. Subtype resolution (did they identify DG/CA1/CA3 subtypes?)
3. Comparison with our 30-cluster annotation

**Note**: Full text not yet available (no PMC, PDF download failed). User should check if they have access to this paper.

### P14: Don't re-annotate what the user already knows (2026-08-27)

**Trigger**: User asks "20, 21 又是什么？" about clusters they've already classified. I launched into full marker re-analysis without asking what they already know.

**Root cause**: Assumed the user needed me to identify clusters from scratch, when they already know C24-C30 = ODC and were specifically asking about C20/C21/C22/C23 because those were uncertain.

**Fix**: Before doing marker-based annotation, **always ask**: "这些亚群你已经有初步判断了吗？还是完全不确定需要我从头分析？" — the user may have partial knowledge and just need targeted help on specific uncertain clusters.

**Why it matters**: The marker list CSV has column `group_name` (NOT `cluster`). The marker list may not contain all clusters (C24/C27 have no significant DEGs → absent from CSV). Re-running annotation the user has already done wastes time and can contradict their validated annotations.

### P15: C26 — UMAP Topology > Marker Reclassification (CORRECTED TWICE, final 2026-08-27)

**Iteration history**:
1. C26 initially labeled "noise" (OR/TAS2R top markers)
2. L2 debate corrected to "OPC-like" (SOX17+/ROBO2+/DCC+ + GeneScoreMatrix oligo signal)
3. **User final correction**: C26 = **ODC** (part of C24-C30 ODC group)

**Why the debate got it wrong**: The agent argued SOX17+/ROBO2+/DCC+ markers meant OPC/neural progenitor identity. But C26 **overlaps with C24-C30 (ODC) in UMAP space** — spatial clustering topology is the primary criterion. When a cluster clearly groups with a cell type in UMAP, marker analysis should confirm, not override.

**Red flag rule (FINAL)**: When getMarkerFeatures top markers are OR*/TAS2R*/AMY*, the cluster is **hard to classify by peak-level DE alone** — it does NOT automatically mean noise. **Always verify with GeneScoreMatrix** before declaring noise/artifact. But **UMAP topology is the primary identity criterion** — if a cluster overlaps spatially with a cell type group, it belongs to that group even if some markers seem contradictory.

**C13 vs C26 distinction**: C13 (MNX1 + HOX genes + KRTAP) = **peripheral tissue contamination** (confirmed, MNX1 is motor neuron specific, PMID:27572435). C26 (OR/TAS2R + UMAP overlap with ODC) = **ODC亚群 with noisy DE peaks**. Both show non-CNS markers, but the underlying cause is completely different.

**Verification workflow**:
1. **First**: Check UMAP spatial position — does the cluster overlap with a known cell type group?
2. If UMAP overlap is clear → assign to that group (markers are secondary confirmation)
3. If UMAP position is ambiguous → use GeneScoreMatrix for canonical cell type markers (P11 marker list)
4. If GeneScoreMatrix also shows nothing → then it may be genuine noise/doublet
5. For annotation disputes → use L2 full debate (see P18), but **debate must respect UMAP topology**

### P19: Literature Validation for ATAC Cell Type Annotation (2026-08-27)

**When**: Any cluster with ambiguous/non-standard markers, or user asks "文献里有没有报道过这种细胞类型".

**Workflow**:
1. Identify cluster's top markers (getMarkerFeatures + GeneScoreMatrix)
2. Search PubMed/EuropePMC for cell type in specific tissue+assay context (e.g., "human hippocampus scATAC-seq choroid plexus")
3. If literature confirms → annotate with confidence + cite PMID
4. If literature does NOT confirm → annotate as **Unknown** (user preference: "没有的画，就先注释unknown")
5. Document: markers found, search terms, papers found/not found, conclusion

**Human hippocampus ATAC literature findings**:

| Cell type | Literature support | Markers in data | Verdict |
|-----------|-------------------|-----------------|---------|
| **VS** (vascular) | ✅ Heffel 2024 Nature (PMID:39385032), Sziraki 2023 Nat Genet (PMID:38036784) | FOXC1/FOXC2/ICAM2 | **Annotate as VS** |
| **ChP** (choroid plexus) | ⚠️ Rare in hippocampus ATAC; Liu 2025 Cell (PMID:40752494) in multi-region brain ATAC | No TTR/FOLR1 in markerList | **Likely absent** |
| **C13** (HOX+/MNX1+) | ❌ No literature support | HOXD11/MNX1/HOXB5/KRTAP | **Annotate as Unknown** |
| **C26** (ODC亚群) | ✅ UMAP overlaps C24-C30; GeneScoreMatrix oligo signal | OR/TAS2R noisy DE peaks, but ODC marker activity in GAS | **Annotate as ODC** (debate said OPC-like, UMAP topology overrides) |

**VS markers (validated)**: CLDN5, FOXC1, FOXC2, FOXF1, FOXF2, ICAM2, VWF, FLT1, PECAM1
**ChP markers (to check)**: TTR, FOLR1, OTX1, AQP1, CLIC6, FOXJ1
**Contamination signature**: MNX1 + ≥3 HOX genes + KRTAP → peripheral tissue → Unknown

### P18: When to Use L2 Full Debate for Annotation (2026-08-27)

**Trigger**: Any annotation disagreement where evidence is mixed or user questions a classification.

**L1 is insufficient** for annotation disputes — L1 uses context sampling which misses critical marker evidence. L2 (8 roles) is required when:
- getMarkerFeatures and GeneScoreMatrix give contradictory signals (C26 case)
- User challenges an annotation ("你说的对吗？" / "你触发的是8个专家辩论吗？")
- Cluster has <5 DEGs and annotation is ambiguous
- Two cell types share markers and disambiguation matters

**Response to "你触发的是8个专家辩论吗？"**: Yes, use L2. If only L1 was used, re-trigger with L2 immediately — do not defend L1 as sufficient.

**C13 contamination detection** (2026-08-27, validated by literature search P19): MNX1 + ≥3 HOX genes + KRTAP = peripheral tissue contamination → **Unknown**. MNX1 is motor neuron专用 (PMID:27572435), HOX genes silenced in adult hippocampus (PMID:26541512). 8 papers searched, NONE report HOX+/MNX1+ in human hippocampus ATAC. This pattern is distinct from C26's OR/TAS2R noise — C13 has genuine non-CNS gene expression from contaminating tissue, while C26 has technical peak-level artifacts with real lineage signal underneath.

### P16: Doublet Score Validation for Ambiguous Clusters (2026-08-27)

**When**: Any cluster with <5 DEGs, or markers that seem ambiguous/contradictory, or cluster shows unexpected marker profile.

**Workflow**:
```r
# 1. Extract doublet metrics from cellColData
emb <- getEmbedding(proj, embedding = "UMAPHarmony")  # NOTE: not "UMAP"!
df <- as.data.frame(getCellColData(proj, select = c("DoubletScore","DoubletEnrichment","Clusters")))
df$UMAP1 <- emb[,1]; df$UMAP2 <- emb[,2]

# 2. Per-cluster doublet stats
stats <- aggregate(DoubletScore ~ Clusters, data=df,
                   FUN=function(x) c(median=median(x), mean=mean(x), pct_gt10=mean(x>10)*100))

# 3. Flag clusters with >10% cells having DS>10
# C20: 20.5% DS>10 → highest doublet rate → likely contains true doublets
```

**Threshold**: >10% cells with DoubletScore >10 = investigate further (subset, check co-expression of conflicting markers).

### P17: Microglia Subtypes in ATAC (C20/C21/C22/C23) (2026-08-27)

**Lesson**: Human hippocampus ATAC reveals 3-4 microglia-related clusters, not just one "Microglia" group:

| Cluster | State | Key Markers | DS>10% |
|---------|-------|-------------|--------|
| C20 | Homeostatic | TAL1, IRF8, C3AR1, ABI3, CX3CR1 | **20.5%** ⚠️ |
| C21 | Inflammatory | CCL18, CCL23, FOXC2, CCL3, CCL5, CCL11 | 8.4% |
| C22 | Phagocytic | SIGLEC7, LILRB4, TYROBP, FPR2, FPR3 | 1.6% |
| C23 | Macrophage (peripheral) | CXCL10, CLEC5A, S100A8, CD163, FPR2 | 1.5% |

**C20 has 20.5% doublet rate** — this is the highest of ALL 30 clusters. The "homeostatic microglia" signal may be partially contaminated by doublets. Validate by subsetting C20 cells with DoubletScore < 5 and re-checking markers.

**C23 vs C20-C22**: C23 is blood-derived macrophage (CD163+/S100A8+/CLEC5A+), NOT microglia. Key distinction: C20-C22 share CX3CR1/TAL1/IRF8 (microglia signature), C23 does not.

### P20: UMAP Topology Is Primary Identity Criterion (2026-08-27, user-enforced)

**Lesson from C26**: The agent used marker analysis (SOX17+/ROBO2+/DCC+) to argue C26 was OPC-like, contradicting the user's observation that C26 overlaps with ODC (C24-C30) in UMAP. The user was right.

**Rule**: When a cluster **spatially overlaps with a cell type group in UMAP/UMAPHarmony**, it belongs to that group. Marker analysis is secondary confirmation, not primary identity. This is because:
1. ATAC peaks are noisy (OR/TAS2R/AMY peaks appear as "differentially accessible" but don't reflect cell identity)
2. GeneScoreMatrix aggregation can show signal from neighboring cells in UMAP space
3. The clustering algorithm already grouped these cells together based on overall chromatin similarity

**When marker analysis DOES override UMAP**: Only when the cluster is spatially isolated (no overlap with any group) AND markers are unambiguous (≥3 canonical markers with strong Log2FC). In that case, the cluster is genuinely novel/different.

**Priority order**: UMAP topology > GeneScoreMatrix > getMarkerFeatures DEGs > literature

### P9: Minimal pairwise getMarkerFeatures for unresolved clusters (fast, won't hang)
cd <- getCellColData(proj)
grp <- ifelse(cd$Clusters %in% c("C24","C27"), cd$Clusters, "Rest")
proj <- addCellColData(proj, data=grp, name="unresolved", force=TRUE)
mk <- getMarkerFeatures(proj, useMatrix="PeakMatrix", groupBy="unresolved",
                        testMethod="wilcoxon", bias=c("TSSEnrichment","log10(nFrags)"))
for (cc in c("C24","C27")) { m <- getMarkers(mk, groupBy=cc, cutOff="FDR<=0.1"); print(head(m@elementMetadata[,c("name","Log2FC","FDR")], 20)) }
```
Relaxed FDR (1e-1) is intentional — these clusters are gradually differentiated and the default 1e-2 returns nothing.

### P21: Numbering scheme differs per species — resolve map keys against the CORRECT annotation column (2026-08-27 user correction)

When the user hands you a numbered cluster→cellType map like `ExN:2,3,4,8,9,10,11`, the meaning of the integers depends on **which column carries the annotation** — and it differs per species:

- **Human** (`human_Hf_ATAC_40_clustered.rds`): the annotation key is the **`Clusters`** column (C1–C30). Map keys are the cluster integers → `as.character(proj$Clusters)`.
- **Monkey** (`monkey_Hf_ATAC_final.rds`): the user's numbers are **NOT cluster IDs** — they index **张潇's `predictedAnno` manuscript numbering** (the 18-subtype coded IDs 1–18). Map keys must be resolved against `as.character(proj$predictedAnno)`, NOT `proj$Clusters`.

**User's exact correction**: "猴脑这个错了，这个数字代表的是张潇注释的predictedAnno编号，帮我替换成对应的亚群名" — the numeric keys for monkey are the manuscript's subtype IDs, whose *names* you must look up from the rds `predictedAnno` factor levels (1=Astrocyte, 2=CA1_SUB s_f_Ex, 3=CA2_4 EX, 4=CGE CNR1 lnh, 5=CGE LAMP5 lnh, 6=Choroid Plexus, 7=DG Ex, 8=EC L2 EX, 9=EC L3_5 EX, 10=EC L6 EX, 11=CAE_SUB deep Ex, 12=MGE SST lnh, 13=MGE PVALB lnh, 14=Microglia, 15=ODC, 16=OPC, 17=Ependymal, 18=VS).

**Rule**: before applying a numbered map, determine which column the user is numbering (`Clusters` vs `predictedAnno`) by inspecting `colnames(getCellColData(rds))` and the factor levels. Apply `as.character()` to the correct column so the name-vector indexes by name, not integer position (see P1). Do NOT assume all species use the same numbering source. Safest is to express the monkey map with **predictedAnno NAMES as keys** (e.g. `"Astrocyte"="Astro", "DG Ex"="ExN", ...`) rather than numeric IDs — that sidesteps the numbering-convention ambiguity entirely.

### P22: Human donor-age NOT in GEO — ASK USER FOR THE PAPER'S SUPPLEMENTARY METADATA TABLE (2026-08-27 verified → RESOLVED 2026-08-28)

For the species×age patent model on human (Zemke GSE278576), attempting to download the donor→age table from GEO fails:
- GEO **series matrix** contains only `tissue: hippocampus` + `donor id: hcXX` — NO age field.
- The GEO cell-metadata supplemental file (`GSE278576_hippocampus_RNA_seurat_object_filtered_cells_metadata.tsv`) returns **404** on both FTP and HTTPS download URLs.

**✅ RESOLVED (2026-08-28)**: the donor→age table lives in the paper's *supplementary metadata folder*, which the user supplied at `D:/我的下载/media-2/Supplemental Tables S1-S24/Table_S1.tsv`. Ask the user for this file rather than grinding GEO endpoints.

**Table_S1.tsv verified structure** (11 columns, 48 donors, includes non-ATAC donors):
`Donor ID, Age, Age group, Sex, Source, Brain bank id, Assays, Cause of death, PMI, Braak Stage, Race`

**How to pick the 40 ATAC donors**: filter `Assays` containing `10x multiome` (exactly 40 of the 48 rows; the other 8 are confocal-fluorescence-only or snm3C-only donors like 813/6819/5182/5089/6371/1637/6688). Verify match count against RDS: 40 unique `Sample` values in the human rds.

**Sample name → donor extraction** (RDS Sample column pattern `GSM8549615_hc77`):
```r
donor_num <- as.integer(sub(".*hc([0-9]+).*", "\\1", proj@cellColData$Sample))
```

**R named-vector pitfall (parse error)**: numeric names MUST be quoted:
```r
# ✗ WRONG — parse error: "unexpected '='"
donor_age <- c(78=20, 77=20, ...)
# ✓ CORRECT
donor_age <- c("78"=20, "77"=20, "5579"=25, ...)
```

**Age_group construction** (matches paper bins):
```r
age_group <- cut(ages, breaks=c(19,40,60,80,100),
                 labels=c("20-40","40-60","60-80","80-100"), right=FALSE)
```
Verified result: **4 groups × 10 donors × ~25% cells each (61,798 / 70,124 / 70,335 / 63,652 cells), ALL 265,909 cells matched with 0 NA**.

**Sandbox write-limitation workaround**: the sandbox cannot write to `E:/专利/patent` (outside `MEMOMICS_ALLOWED_WRITE_ROOTS`) — save the age-annotated rds under `results/<sid>/` and hand the user a 5-line local write-back script (`readRDS` → match donor → `addCellColData` → `saveRDS` to their path).

The verified full 40-donor mapping is in `references/human40_donor_age_verified_20260828.md` — reuse it directly; do NOT re-derive or re-download.

### P24: Cross-species age-group alignment = LIFE STAGE, not absolute age; cell-proportion stats use INDIVIDUAL unit + Spearman (2026-08-29)

Session lessons for the species×age proportion analysis (thesis deliverable):
1. **Never align age groups by absolute values** — monkey (5-6/10-12/22-23/28-31 yr, lifespan ~30) vs human (20-40/40-60/60-80/80-100, lifespan ~80) must map by RELATIVE life stage (Young/Middle/Old/Exceptionally old). 张潇原文 defines the 4 monkey groups explicitly. Add a unified `age_stage` column on both sides. Detail + copy-paste code in `references/life_stage_alignment_and_celltype_proportion_stats.md`.
2. **Statistical unit = individual** (human 40, monkey 21), never cell count (pseudoreplication). Aggregate per-sample proportions first, then boxplot per-individual dots + stage.
3. **Age_group is ordinal → Spearman ρ, not Pearson** (Schober 2018 PMID 29481436). Read `ρ=-0.65 ***` as direction (sign) + strength (|ρ|) + significance (p).
4. **"No significant change" in BOTH species is same-direction evidence** — for the substitutability claim, "both flat" (ρ≈0, both ns) supports conservation just like "both change together". Only species-DIVERGENT patterns weaken substitutability. User explicitly asked this about InN.
5. **Palette workflow**: when user says "调整配色，等我同意" — wait for approval, then REUSE the approved hex palette in later project figures. Human has Unknown (C13) and monkey has VS/ChP — use only shared cell types for cross-species stats (6 shared: ExN/InN/Astro/Micro/OPC/ODC).

### P23: NEVER hand-transcribe the donor-age vector — build it programmatically from Table_S1 (2026-08-28 user catch)

**Error**: agent hand-wrote `age_map <- c("hc77"=20, "hc78"=25, "hc5579"=26, ...)` from memory/scan of Table_S1. It was **shifted by one**: user caught it — "78不是20岁吗？" (Table_S1: Donor 78 = Age 20). One wrong row cascades every subsequent value (hc5579=25 not 26, hc76=26 not 28, ...).

**Fix (mandatory)**: build the map from the TSV with pandas, then emit the R vector from the dataframe — never type 40 values by hand:

```python
import pandas as pd
df = pd.read_csv(r"D:/我的下载/media-2/Supplemental Tables S1-S24/Table_S1.tsv", sep="\t")
df = df[df["Assays"].str.contains("10x multiome")]        # exactly the 40 ATAC donors
pairs = [(f'hc{r["Donor ID"]}', r["Age"]) for _, r in df.iterrows()]
print("age_map <- c(" + ", ".join(f'"{h}"={a}' for h, a in pairs) + ")")
```

Then cross-validate against the rds Sample list: `set(sample_hc_ids) == set(map_hc_ids)` (must be 40/40), AND spot-check specific donors the user already knows (e.g. hc78=20 → Zhrank 20-40 group). When the user supplies the authoritative supplementary table, read it fully and map exactly — do not reconstruct partial/estimated values.

## References

- **Age-column availability per species for the species×age patent model (2026-08-27): `references/gse278576_metadata.md` (SECOND HALF)** — Monkey rds HAS `Age`+`Age_group` (21 indiv, ages 5-31, 4 groups, ready to model); Human Zemke rds has NO Age column and GEO series matrix only has `tissue`+`donor id (hcXX)` — donor→age lives in the article supplementary metadata (PMID 39463924), not GEO. Before building species×age interaction, check this file; if human age table is unavailable, fall back to species-main-effect model (don't fabricate ages).**
- **✅ Life-stage alignment + cell-type proportion stats (2026-08-29 thesis deliverable): `references/life_stage_alignment_and_celltype_proportion_stats.md`** — monkey/human age-group mapping by life stage (never absolute age), individual-unit statistics, Spearman for ordinal age groups, "no change in both" = conserved interpretation, palette approval workflow, **concordance per-celltype figure template (mean±SEM trajectory + individual dots + ρ [Bootstrap CI] p in legend; reusable script `scripts/concordance_astro_opc.py` — when user says "画一张跟 XX 一样的图", reuse existing script with celltype loop changed)**, and the **专利结论表 deliverable convention** (accumulative `conclusions/专利结论表.md` with method+source per entry, stats sourced from `results/cross_species_trend_stats.csv`, never from memory).
- **✅ VERIFIED human 40-donor → Age mapping (2026-08-28, from user-supplied Table_S1.tsv): `references/human40_donor_age_verified_20260828.md`** — REUSE this direct mapping (4 groups × 10 donors, all 265,909 cells matched, 0 NA). Includes R code and the quoted-numeric-name pitfall. Do NOT re-derive or re-download; ask user for the supplemental Table_S1.tsv if it went missing. 
- **✅ GSE278576 全量注释+年龄+峰值管线汇总 (2026-08-29/30): `references/gse278576_human40_annotation_age_20260828.md`** — 人脑 30 群/猴脑 63 文库全量状态表、用户定稿 8 大类映射（人 keyed on Clusters / 猴 keyed on predictedAnno 编号 1-18）、跨物种 life-stage 年龄对齐、细胞比例物种×年龄统计规则（个体单位+Spearman）、峰值 calling 生产坑与 L1 bigWig 集群路线速查。gse278576-atac-aging-comparison skill 是 manual 不可写，本文件挂在这里作为该数据的权威参考。 
- **Human hippocampus 8-class marker gene list (89 genes, ranked by n_cluster, validated 2026-08-27): `references/hippocampus_8class_markers_89genes.csv`** — canonical markers from `getMarkerFeatures` on human 40-sample ATAC data, FDR<0.01 & Log2FC>1, ranked by how many clusters each gene appears as a top marker (higher = more reliable). Use this as the authoritative gene list when user asks for "8大类 gene marker" or "注释依据". Note: SOX6 appears in both InN and OPC; CSPG4 appears in both OPC and VS — this is biologically correct, distinguish by co-expression context.
- **S100B gap explanation (ATAC expression-accessibility mismatch): `references/S100B_gap_note.md`** — why classic markers like S100B may be absent from ATAC marker lists, which clusters are affected, and how to verify with GAS/pairwise comparison.
- **Oligodendrocyte (OPC/ODC) gap analysis: `references/oligo_gap_analysis_20260827.md`** — why human hippocampus ATAC has only 8 ODC cells (vs monkey 44K), CSPG4 appearing in ExN clusters, diagnostic commands, and hypotheses.
- **Full 30-cluster audit trail (scores, evidence, debate verdict): `references/human_30cluster_annotation_20260827.md`**
- **Final 28-row annotation table + ExN naming check (2026-08-28 定稿)**: `references/human_28cluster_annotation_final_20260828.md` (⚠️ table has 28 rows ONLY because C24/C27 lack significant markers — the RDS itself has 30 clusters; see P7)
- **Final 8-class annotations (user-confirmed 2026-08-27, both species)**: `references/final_8class_annotations_20260827.md` — the definitive cluster→cellType8 mapping for human (30 clusters) and monkey (18 clusters). Source of truth; do NOT override with marker analysis.
- **✅ SUPERSEDING user-confirmed final maps + copy-paste R (2026-08-28): `references/final_annotations_user_confirmed_20260828.md`** — human keyed on `Clusters` (OPC C1-6 / Astro C7-12 / Unknown C13 / InN C14-16 / ExN C17-19 / Micro C20-23 / ODC C24-30) + monkey keyed on `predictedAnno` codes (ExN 2,3,4,8,9,10,11; InN 5,6,13,14; Astro 1,12; Micro 15; OPC 17; ODC 16; VS 18; ChP 7), with copy-paste R for both species. Use this file when the user asks for annotation write-back code or validates the final table.
- **ArchR write-back template (copy-paste for user's own cluster)**: `templates/archR_annotate_writeback.R`
- **Annotation dispute resolution & contamination signatures (C26 OPC-like, C13 contamination, microglia subtypes)**: `references/annotation_dispute_resolution_20260827.md`
- **Literature validation for ATAC cell types (VS/ChP/C13/C26)**: `references/atac_literature_validation_20260827.md`
- Zhang Xiao 2026 Cell: `D:/学习文献/Revised text-final.docx` (manuscript)
- Peng 2026 Nature Medicine: PMID 42629468 "Dysregulated adult hippocampal neuroogenesis in major depressive disorders" (may contain hippocampal ATAC annotation)
- Zemke 2024 Science: GSE278576 (40 human hippocampus samples)
- Human marker list: `E:/专利/human_40_markerList.csv`
- Macaque RDS: `E:/专利/patent/monkey_Hf_ATAC_final.rds`
- Human RDS: `E:/专利/patent/human_Hf_ATAC_40_clustered.rds`

## Proven Scripts

> Auto-generated from actual analysis runs. Each row records a successful execution.

| 物种 | 组织 | 方向 | 日期 | 脚本 | auto | user | ✔ |
|------|------|------|------|------|------|------|----|
| human | hippocampus | aging | 2026-08-27 | read_monkey_predictedAnno.R | - | - |  |
| human | hippocampus | aging | 2026-08-27 | annotate_human_30clusters.py | - | - |  |
| human | hippocampus | aging | 2026-08-27 | annotate_human_30clusters.py | - | - |  |
| human | hippocampus | - | 2026-08-27 | human_subcluster_annotation_final.csv (annotate_subcluster_alignment) | - | - |  |
| human | hippocampus | aging | 2026-08-27 | annotate_subcluster_alignment.py | - | - |  |
