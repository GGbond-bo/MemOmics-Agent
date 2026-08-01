# Five-Effect-Axes Matrix — Validated Recipe (paired multi-condition design)

Session: 2026-07-31, human skeletal muscle MF snRNA-seq, 10 clusters × 2000 cells,
6 groups (Y/O/OD × Pre/Post), 14 AUCell functional scores.
User direction: "不要只集中RSS，要集中IIX这些，展示五种效应的影响" — focus the
systematic panel on the canonical fast-fiber family, show all five effect axes.

## Why this pattern

Many exercise/aging/T2D intervention datasets are 6 groups = 2 factors (condition ×
Pre/Post). Presenting ad-hoc pairings (e.g. only "Old vs Young" and "Old vs Old+Ex")
leaves reviewers asking "where's the T2D effect? the young-exercise effect? the
T2D-exercise effect?" Enumerate ALL 5 axes once, run one statistics table, and let
the matrix answer "which axis moves which score in which fiber family".

## Design → axis mapping

| Axis | Contrast | Test | Rationale |
|------|----------|------|-----------|
| Aging | O_Pre vs Y_Pre | unpaired Wilcoxon | same baseline state, age differs |
| T2D | OD_Pre vs O_Pre | unpaired Wilcoxon | same age, diabetes differs |
| Ex-Young | Y_Post vs Y_Pre | paired Wilcoxon | same individuals |
| Ex-Old | O_Post vs O_Pre | paired Wilcoxon | same individuals |
| Ex-T2D | OD_Post vs OD_Pre | paired Wilcoxon | same individuals |

## Statistical protocol (validated)

1. **Individual-level pseudobulk** — NEVER test at cell level (pseudoreplication).
   ```r
   md$pair_id <- sub("_(Pre|Post)$", "", md$samplename)   # Young_1_Pre -> Young_1
   agg <- md %>% group_by(pair_id, type, annotation_L3) %>%
     summarise(across(all_of(score_cols), mean), .groups = "drop")
   ```
2. Paired test (exercise axes): intersect pair_ids, `wilcox.test(post, pre, paired=TRUE)`.
   Unpaired test (aging/T2D axes): `wilcox.test(group1, group2)`.
3. FDR via `p.adjust(p, "fdr")`; stars: *** <0.001, ** <0.01, * <0.05.
4. **Small-n caveat**: with Y=10 / O=7 / OD=7 individuals, only 2/350 cells survive
   FDR (OxPhos-aging, SenMayo-aging in fast family). This is a POWER problem, not a
   no-signal problem. Report three metrics together:
   - effect size (mean delta at individual level)
   - raw p
   - **direction consistency** (same-sign fraction across clusters for a score×axis)
   Muscle result: 8 score×axis combos were 4/4 or 5/5 same-direction — a stable
   directional story despite weak per-test p.
5. Always state individual n per group in the figure/table (n=7 is a reviewer target).

## Focus-cluster mapping

```r
fast_cl <- c("Pure Type IIX","Pure Type IIA","OTUD1+(II)","RP_high(II)")
focus_clusters <- c(fast_cl, "RSS")          # novel state as context, NOT protagonist
focus_label <- c("Pure Type IIX"="Fast-IIX", "Pure Type IIA"="Fast-IIA",
                 "OTUD1+(II)"="Fast-OTUD1+", "RP_high(II)"="Fast-RP_high",
                 "RSS"="RSS(near-fast)")
```

## Figures produced (validated)

1. **Fast-family five-effect heatmap** (`Fig_five_effects_fastfibers_heatmap.png`):
   rows = cluster|score blocks (5 clusters × 14 scores), cols = 5 axes,
   fill = mean delta (blue-white-red), row annotations = Cluster + Score Category,
   `display_numbers = matrix(star, ...)` from p.adj. pheatmap; write PNG at 300 dpi,
   no manual dev.off() when using filename=.
2. **Canonical cluster dotplot** (`Fig_five_effects_IIX_dotplot.png`): x = axis,
   y = score (facet by score category, free_y), size = |eff|, fill = eff,
   `geom_text(label=star)`. ggplot2 → ggsave.
3. **Fast vs Slow family summary** (`Fig_fast_vs_slow_family.png`): collapse each
   family to individual-level means, same 5 axes, facet by family — shows whether
   fast and slow fibers respond to the same axes.

## Validated findings (muscle MF — use as expected-value anchors)

| Axis | Fast-family effect | Interpretation |
|------|--------------------|----------------|
| Aging | scoreI −0.180, IIa −0.062, OxPhos −0.063 (5/5 same sign) | identity blur, oxidative capacity drop |
| T2D | ~null on fast family; RSS: IIx +0.055 (p=0.017) | diabetes mostly spares fast fibers but drives the near-fast novel state |
| Ex-Young | near zero | healthy young baseline has nothing to restore |
| Ex-Old | IIa +0.101 (reversal!), RegMyon +0.035 | exercise restores fast-fiber identity + regeneration |
| Ex-T2D | IIa only ~1/4 of Ex-Old magnitude | T2D blunts exercise reversibility |

**Narrative**: "Exercise is the mirror of aging on the metabolic/identity axis
(IIa/Sarcomeric/OxPhos reversible) but not on the senescence/stress axis
(SenMayo/Stress/TNFA irreversible); T2D blunts the mirror (Ex-T2D recovery ≈ 1/4 of
Ex-Old)." RSS shows the aging-specific + exercise-refractory profile at the score level.

## Seurat/score gotchas

- Score columns matched with `grep("score.*AUC", colnames(md), value=TRUE)` → 14 columns
  (AUCell scores). Filter carefully — metadata may carry other "score" columns.
- Some clusters have very few cells in a condition (RSS Y_Pre=93) — individual-level
  aggregation still works but that individual's estimate is noisy; direction
  consistency across clusters is the stabilizer.
- Pair_id from samplename requires the naming to be `X_Pre`/`X_Post`; probe with
  `unique(md$samplename)` first; if names don't carry the suffix, map manually.

## Verification pattern (ad-hoc, disk-anchored)

Write `hermes-verify-five-effects.R` into temp dir that RE-COMPUTES from raw meta RDS:
- n individuals per group (10/10/7/7/7/7), pseudobulk uniqueness
- key effects: Aging_I=−0.180, Aging_IIa=−0.062, ExOld_IIa=+0.101, RSS_T2D_IIx=+0.055,
  Aging IIa 5/5 same-sign
- product existence (3 PNG >300KB, 2 CSV, stats table 350 rows)
Write anchor to `results/<session>/log/verify_five_effects_status.txt` before deleting
the temp script. 15 pass / 0 fail in the validated run.
