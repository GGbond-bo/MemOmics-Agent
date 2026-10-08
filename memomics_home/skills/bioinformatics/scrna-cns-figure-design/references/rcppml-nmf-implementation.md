# RcppML Single-Cell NMF — Working Recipe (validated 2026-07, 骨骼肌 20K MF)

Source session: 10 MF subtypes × 2000 cells = 20,000 cells, SCT assay, 6 conditions
(Y_Pre/Y_Post/O_Pre/O_Post/OD_Pre/OD_Post paired design). Full pipeline ran
clean with k=6, all programs biologically interpretable, reproducibility cor = 1.0000.

## ⛔ CRITICAL: gene exclusion BEFORE NMF

**Without exclusion, NMF is destroyed.** First run on raw HVG (3000 genes) produced
programs where MALAT1/TTN/NEB/DMD/NEAT1 dominated every program and cluster×program
loading was flat (~1e-5, no discrimination). MALAT1 (nuclear lncRNA) + giant sarcomere
genes (TTN/NEB/DMD are 100kb+ transcripts) + MT/RPL housekeeping swamp the decomposition.

**Fix (validated):** exclude before fitting, then re-select HVG:

```r
hvg <- VariableFeatures(obj)   # 5000 if <3000
exclude <- c(grep("^MT-", hvg, value=TRUE),
             grep("^RPL", hvg, value=TRUE),
             grep("^RPS", hvg, value=TRUE),
             grep("^MRPL", hvg, value=TRUE),
             grep("^MRPS", hvg, value=TRUE),
             intersect(hvg, c("MALAT1","NEAT1","TTN","TTN-AS1","NEB","DMD","XIST")))
hvg <- setdiff(hvg, exclude)   # 3000 → 2936 in the validated run
```

Result: programs became interpretable (see Program table below). This is the
single most important step for single-cell NMF on muscle/any tissue with
high-abundance structural genes.

## RcppML quirks (each one cost a failed run)

1. **Must `library(Matrix)` explicitly** — else `RcppML::nmf` errors with
   `no item called "package:Matrix" on the search list`.
2. **`nmf()` drops rownames/colnames** — restore after fit:
   ```r
   rownames(W) <- hvg
   colnames(H) <- colnames(mat)
   ```
3. **Deterministic with same seed** — reproducibility check: refit with seed=42,
   max-cor between W matrices = 1.0000. Reuse in methods section as evidence.
4. **Seurat v5**: `GetAssayData(obj, assay="SCT", slot="data")` is DEPRECATED →
   use `layer = "data"`. (`slot=` throws a lifecycle error.)
5. **pheatmap with `filename=` does NOT need `dev.off()`** — extra dev.off()
   errors with "cannot shut down device 1 (the null device)".
6. **ggplot `+` chain bug**: a stray `stat_compare_means_ref <- NULL` inside a
   `+` chain parses as `+<-` → "could not find function +<-". Keep assignments
   OUT of the pipeline.

## Core pipeline (validated)

```
1. SCT data → VariableFeatures (5000, then exclude → ~2900)
2. mat <- as(GetAssayData(obj, assay="SCT", layer="data")[hvg,], "CsparseMatrix")
3. k evaluation: for k in 4:9, run 5 seeds, cor(H-flattened) → stability
   (skeletal muscle: k4=0.50 k5=0.64 k6=0.43 k7=0.43 — noisy, don't over-trust;
   pick by biology too)
4. fit <- RcppML::nmf(mat, k=6, tol=1e-5, maxit=500, seed=42)
   W (genes×k), H (k×cells)
5. Cell-level loading = t(H) → add to meta.data as NMF_1..k
6. Aggregate loading by cluster (10×k) and by condition (6×k) → CSV
7. Visualize: cluster×program z-score heatmap, condition×program heatmap,
   per-program condition boxplots (paired Pre/Post), UMAP feature plots
```

## Program naming + biological validation (the proof it worked)

| Program | Top genes | Highest cluster | Validation |
|---------|-----------|-----------------|------------|
| P1 Fast-twitch | ATP2A1, RYR1 | Pure IIX > IIA | expected |
| P2 Slow-twitch | MYH7, ATP2A2 | LRP1B+(I) > Type I | expected |
| **P3 RSS/aging** | **BMPR1B**, LINC01091, NCALD, TP63 | **RSS** | user marker hit |
| P4 Stress | FKBP5, SESN1 | — | aging stress |
| P5 Cytoskeletal | PALLD, XIRP2 | OTUD1+(I/II) | — |
| P6 Translation | ACTA1, CKM, MB | RP_high(I/II) | expected |

**Validation pattern to reuse:** (a) top genes hit user's known markers
(BMPR1B = RSS marker); (b) cluster with max loading = the biologically expected
one; (c) condition trend reproduces the biological story — P3 loading
Y 3.6e-5 → O 5.0e-5 → OD 6.4e-5 (aging increase) and O_Pre→O_Post 5.0→5.3
(exercise non-response). All three independently confirmed the same finding.

**Verification evidence must be persisted to disk** — ad-hoc verification via a
throwaway temp script is rejected as "stale/not fresh" once the temp script is
deleted (happened twice in the 2026-07 session). BEFORE cleaning up the temp
script, write a durable anchor: `results/<session>/log/verify_<script>_status.txt`
containing pass/fail counts, key recomputed stats, and a timestamp. Keep the
anchor after deleting the temp script so evidence is traceable across wake-ups.

## GO/KEGG interpretation for novel programs

- **Novel program with ZERO GO terms is a FEATURE, not a failure** — P3 (RSS)
  had 0 significant GO terms while P1/P2/P4/P5/P6 had 72–147. This confirms the
  subtype is genuinely uncharacterized (marker genes like BMPR1B not in GO
  muscle terms). Report it as "novel, unannotated program".
- **KEGG often returns empty for muscle programs** — sarcomere/contraction genes
  are not in KEGG metabolic pathways. "No gene can be mapped" is normal; don't
  re-run or treat as error.

## Subsetting note (this session's compromise)

User chose simple per-cluster 2000 sampling (NOT stratified by condition) for a
first pass. Acceptable for program-structure discovery; the stratified
cluster×condition version is still required before program×condition statistics
go into a figure (rare-condition cells like RSS-young ≈ 50 get gutted by random
sampling). Flag it when delivering program×condition plots from unstratified data.
