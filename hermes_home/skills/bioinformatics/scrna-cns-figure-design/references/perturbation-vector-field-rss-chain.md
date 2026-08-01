# Perturbation Vector Field + RSS Aging-Specific Evidence Chain — Validated R Recipe

> Validated 2026-07-31 on human skeletal muscle snRNA-seq: `MF_subset_2000.rds`
> (10 myofiber subtypes × 2000 = 20000 cells, 6 conditions Y/O/OD × Pre/Post),
> NMF k=6 program space (RcppML). Session `memomics-2f229850`, scripts
> `phase4/phase4_rss_perturbation.R` + `phase5/phase5_nature_figures.R`.

## Data wiring (Seurat gotchas — all hit in production)

```r
obj <- readRDS(".../MF_subset_2000.rds")          # 20000 cells
meta_nmf <- readRDS(".../nmf/meta_with_nmf_loadings_k6.rds")

# ⚠️ loading columns are NMF_1..NMF_6, NOT P1..P6 — probe, don't assume
nmf_cols <- grep("^NMF_[0-9]+$", colnames(meta_nmf), value = TRUE)
prog_names <- paste0("P", 1:6)
meta_nmf[, prog_names] <- meta_nmf[, nmf_cols[1:6]]

# ⚠️ Seurat UMAP embeddings are lowercase umap_1/umap_2
umap <- as.data.frame(obj@reductions$umap@cell.embeddings)
colnames(umap) <- c("UMAP_1", "UMAP_2")

# align by barcode rownames; verify count
common <- intersect(rownames(obj@meta.data), rownames(meta_nmf))
stopifnot(length(common) == ncol(obj))
meta <- cbind(obj@meta.data[common, ], meta_nmf[common, prog_names])
```

## Part 1 — RSS aging-specific evidence chain (4-part)

```r
rss <- meta[meta$annotation_L3 == "RSS", ]
p3t <- rss %>% group_by(type) %>% summarise(m = mean(P3), .groups = "drop")
# 1) aging slope: Y_Pre < O_Pre < OD_Pre  (validated 6.2e-5 → 1.03e-4 → 1.11e-4, 1.65x)
# 2) exercise non-response: |O_Pre→O_Post| ~ 0  (validated |Δ| = 6.7e-7)
# 3) fold vs rest widens: RSS mean / others mean at Y vs O  (validated 1.70 → 2.45)
# 4) marker trend across conditions: e.g. BMPR1B  (validated 0.45→0.95→0.93, ex flat)
```

Use the SAME program metric (P3 loading) for both the aging slope and the exercise
non-response — that is the strength of the chain (not proportion bars).

## Part 2 — perturbation vector field + reversibility

```r
programs <- prog_names   # P1..P6
all_cond <- meta %>% group_by(annotation_L3, type) %>%
  summarise(across(all_of(programs), mean), .groups = "drop")

get_v <- function(sub, from, to) {
  f <- sub %>% filter(type == from) %>% select(all_of(programs)) %>% as.numeric()
  t <- sub %>% filter(type == to)   %>% select(all_of(programs)) %>% as.numeric()
  if (length(f) == 6 & length(t) == 6) t - f else rep(NA, 6)
}

vec_df <- do.call(rbind, lapply(unique(all_cond$annotation_L3), function(cl) {
  sub <- all_cond %>% filter(annotation_L3 == cl)
  a <- get_v(sub, "Y_Pre", "O_Pre");  e <- get_v(sub, "O_Pre", "O_Post")
  data.frame(cluster = cl,
             aging   = sqrt(sum(a^2, na.rm = TRUE)),
             ex_old  = sqrt(sum(e^2, na.rm = TRUE)),
             rev     = if (sum(a^2, na.rm = TRUE) > 0) sum(a*e, na.rm = TRUE)/sum(a^2, na.rm = TRUE) else NA)
}))
```

Interpretation (validated): RSS rev=−0.107 (exercise orthogonal, NOT reversed);
Specialized MF rev=+0.025 (exercise does NOT reverse, both routes rise). Other clusters
show negative rev (−0.10…−0.22) = partial reversal.

## Part 3 — nature-figure export (SVG+PDF+TIFF, R backend)

Use `nature-figure` skill's `theme_nature_contract()` + `save_pub_r()`:
- SVG: `svglite::svglite()` — editable text (fonttype none)
- PDF: `grDevices::cairo_pdf(..., family="Arial")` — TrueType text
- TIFF: `ragg::agg_tiff(res=600)`
- ComplexHeatmap: NOT a ggplot — open device, `draw(ht, heatmap_legend_side="right")`,
  `dev.off()` per format (do NOT use save_pub_r on a Heatmap object)
- Export `source_data/*.csv` alongside figures — manuscript-facing traceability
- `umap_1` lowercase quirk applies here too (see data wiring)

## Verification anchor (run once after analysis, keep the anchor)

Recompute the key stats from RAW data (not from output CSVs), write
`results/<session>/log/verify_<step>_status.txt`:
```
VERIFY phase4_rss_perturbation.R + phase5_nature_figures.R | <ts> | 19 pass / 0 fail
RSS P3: Y=6.217e-05 O=1.028e-04 OD=1.111e-04 | fold_Y=1.77 fold_O=2.41 | RSS_rev=-0.107 SP_rev=0.025
```
Then clean the temp verify script. A persistent dated anchor is the "already verified"
evidence later sessions can cite.

## Outputs produced (session 2026-07-31)

- `phase4/figures/`: Phase4_RSS_P3_by_condition.png, Phase4_P3_cluster_condition_heatmap.png,
  Phase4_perturbation_vectors_barplot.png, Phase4_vector_field_PCA.png
- `phase4/data/`: RSS_P3_by_type.csv, RSS_vs_others_P3.csv, exercise_response_P3.csv,
  perturbation_vectors.csv, phase4_objects.rds
- `phase5/figures/`: Fig2A_condition_UMAP, Fig2B_NMF_program_cluster,
  Fig2C_P3_condition, Fig2D_perturbation_vectors — each .svg/.pdf/.tiff
- `phase5/source_data/`: 3 CSV
