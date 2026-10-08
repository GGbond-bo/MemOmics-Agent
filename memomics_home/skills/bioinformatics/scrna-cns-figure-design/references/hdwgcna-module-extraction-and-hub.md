# hdWGCNA: Corrected Positive Result + Module Extraction Bug + Hub Definition (2026-08-01)

Supersedes the earlier "MF network flat / hdWGCNA not applicable" negative result
(`hdwgcna-mf-validated-negative-result.md` — RETRACTED). The negative result was an
artifact; the positive result below is validated on the same human skeletal muscle MF data
(10 subtypes × 2000 cells = 20000, 6 conditions Y/O/OD × Pre/Post).

## 1. The retraction (why the negative result was wrong)

Early run: 4659-metacell datExpr → soft-threshold R² = 0.719 @ power=1 (below 0.8
cutoff), 3000 HVG all fell into a single turquoise module → concluded "MF terminally
differentiated → co-expression flat, WGCNA not applicable".

**What actually fixed it:**
1. **Use release v0.4.12, NOT the dev branch.** The dev branch has bugs: `MetacellsByGroups`
   does not persist `wgcna_name` into the object, function signatures changed
   (`ident.group` param, `TestSoftPowers` returns the Seurat object not `test$data`,
   `RunUMAPMetacells` uses `dims` not `dimensions`).
2. **Rebuild the metacell object with more metacells.** 4659 → 6482 metacells
   (10 subtypes × 6 conditions × 25 aggregations, some conditions dropped for min_cells).
   With 6482 metacells: **soft-threshold R² = 0.98 @ power=10** — a textbook scale-free fit.

**Lesson: a flat soft-threshold + single-module result is a red flag for PIPELINE STATE
(dev branch, stale datExpr, too few metacells), not a property of terminally-differentiated
biology. Metacell count dramatically affects the fit (4659→R²0.72 fail, 6482→R²0.98 pass).**

## 2. Validated positive result (muscle MF, release v0.4.12, 6482 metacells, 10176 genes)

- **9 meaningful modules** (+ grey 6281 unassigned): black 185, blue 868, brown 398,
  green 247, magenta 55, pink 130, red 210, turquoise 1520, yellow 282.
- **Marker→module validation of the user's annotation was perfect**:
  red = fast-twitch (8/9 MYH2/ATP2A1 markers), brown = slow-twitch (10/10 MYH7 markers),
  blue = RP_high (8/8 ribosomal/mito), green = OTUD1+ family, turquoise = RSS (5/6, BMPR1B).
- **Module-trait correlation** (module eigengene × 5 effect axes) answered the user's real
  question directly:
  - **black** (angiogenesis/energy metabolism): Aging −0.51, ExYoung +0.27, ExOld −0.23
    → aging-reversible-in-young, exercise-refractory-in-old = "reversible target"
  - **magenta** (ECM/signaling): Aging +0.39, T2D +0.29, ExYoung −0.20, ExT2D +0.11
    → diabetes blunts exercise suppression = "irreversible damage"
  - blue (OxPhos): Aging −0.26; brown (sarcomere): Aging −0.10, ExYoung +0.08.

## 3. ⛔ Module-gene extraction bug (hit in validation — verify gene names!)

`module_genes.csv` / `hub_genes.csv` from one extraction pass contained **metacell IDs in
the "gene" column** (e.g. `RP_high(I)#OD_Pre_17`) instead of real gene symbols. That breaks
every downstream gene-level step silently.

- **Correct extraction source**: `obj@misc$MF_wgcna$wgcna_modules` (a data.frame with
  `gene_name`, `module`, `color` columns). Save as `modules_extracted.csv`.
- **Always verify**: `any(grepl("#", head(mods$gene_name, 500)))` must be FALSE, and spot-check
  the first 3 entries are real symbols (e.g. AL669831.3, MTATP6P1, PERM1).
- The wrong table came from confusing datExpr **rows** (metacell barcodes) with the module
  color vector aligned to **genes** (columns). When extracting, align by gene.

## 4. Hub gene definition: use kME, NOT network degree (WGCNA standard)

`GetHubGenes` ranks by **kME** (correlation of each gene with the module eigengene),
not by degree in the sparse network. The two disagree:

- black module, degree-top10: NUDT3, ERBB4, FILIP1L, RIF1, GLUL, NDUFA10, RPL3L
- black module, kME-top10: **FKBP5, TNS1, CMSS1, SESN1, GLUL, ITGB6, FILIP1L, ZBTB16, PER1, MIR29B2CHG**

The kME hubs (FKBP5/SESN1/ZBTB16/PER1 = stress/aging genes) were far more
biologically meaningful for the aging story. Compute kME from the module eigengene:
```r
pc1 <- prcomp(expr_m, center = TRUE)$x[, 1]          # module eigengene approx
kME <- apply(expr_m, 2, function(g) cor(g, pc1, use = "p"))
hub_top <- names(sort(abs(kME), decreasing = TRUE))[1:10]
```

## 5. ⛔ Metacell-level p-value inflation (statistical trap for F2e)

Module-trait correlation at **metacell level (n=6482)** produces near-universal significance
(almost every module×effect p<0.001) because of massive pseudoreplication power. **Do not
report metacell-level p-values as evidence.** For final submission:
- Aggregate module eigengenes / scores to **individual level** (n = Y10/O7/OD7 = 24)
  before testing, exactly like the five-effects-axes protocol.
- Report direction consistency + effect size alongside raw p; reserve FDR for headline claims.

## 6. Technical notes hit during validation

- `allowWGCNAThreads()` requires ≥ 2 threads (passing 1 errors).
- ModuleEigengenes checks the MAIN object's `@commands` for a "ScaleData" record — you must
  run `ScaleData` on the main Seurat object (even if computation is on metacells), or it
  errors "Need to run ScaleData".
- `trait_mat` rownames must align to the object the eigengenes were computed on (the main
  object, 20000 cells) — aligning to metacells gives all-NA correlations.
- ComplexHeatmap: `row_annotation` is not a Heatmap() arg — use `right_annotation = rowAnnotation(...)`.
  Significance stars inside cells: `cell_fun` + `grid.text` with a `star(p)` helper
  (`ifelse(p<0.001,"***",ifelse(p<0.01,"**",ifelse(p<0.05,"*","")))`); p-matrix must be
  row/column-aligned with the heatmap matrix in the SAME order. Diverging scale centered
  at 0: `colorRamp2(seq(-lim, lim, length.out=11), colorRampPalette(blue-white-red)(11))`,
  `lim <- max(abs(mat))`. Export SVG/PDF/TIFF via svglite/cairo_pdf/ragg like save_pub_r,
  plus a PNG preview for quick QA; write source_data cor+p CSVs alongside.
- Hub-gene network figure (igraph): module genes → WGCNA::cor → power-10 adjacency →
  keep top 15% quantile edges → `graph_from_adjacency_matrix(weighted=TRUE)` → delete
  isolated vertices → layout_with_fr. Color hubs (top kME) dark vs rest light, label only
  hubs, edge width ∝ weight². Validated: black 179 nodes/2567 edges, magenta 47/227.
- TOM / blockwiseModules with 10176 genes exceeds execute_r's 900s timeout — run via
  background Rscript (terminal background) writing progress to a log.
- GO enrichment may return zero significant terms for genuinely novel modules (RSS/P3-type)
  — that is a feature (uncharacterized state), not a failure; report it as such.
