# Functional-Score Reversal Matrix (打分"衰老-运动逆转矩阵")

Validated on human skeletal muscle MF (14 AUCell module scores, 10 subtypes × 6
conditions Y/O/OD × Pre/Post, Seurat RDS). When a paper already has module
scores (AUCell/AddModuleScore) across a multi-condition design, this analysis
frequently delivers the MAIN biological story faster and clearer than NMF —
and it's what CNS reviewers want to see ("what exactly does exercise reverse?").

## When to use

- User has existing score columns (`score*_AUC`, `AddModuleScore`, AUCell, etc.)
- Multi-condition design, ideally paired Pre/Post
- User asks "看看打分能做成什么样子" / feels NMF output lacks a story
- Want a quantitative "exercise reversibility" statement per functional axis

## Core logic (3 steps)

**Step 1 — condition × subtype × score means.** From per-cell metadata
(annotation col, condition col, score cols), aggregate mean per
subtype × condition.

```r
gc_mean <- meta %>% group_by(annotation_L3, type) %>%
  summarise(across(all_of(score_cols), mean), .groups="drop")
```

**Step 2 — effect deltas.** For any pair of conditions compute per-subtype
score delta matrices:

```r
mk_delta <- function(a,b) {
  d <- gc_mean %>% filter(type %in% c(a,b)) %>% group_by(annotation_L3) %>%
    summarise(across(all_of(score_cols), ~ .[type==b][1] - .[type==a][1]))
  m <- as.matrix(d[,-1]); rownames(m) <- d$annotation_L3; colnames(m) <- score_short; m
}
aging <- mk_delta("Y_Pre","O_Pre")   # aging effect
exer  <- mk_delta("O_Pre","O_Post")  # exercise effect (elderly)
```

**Step 3 — reversal classification + reversal rate.** For each subtype×score:
- reversed: `aging*exercise < 0` AND `abs(exercise) >= threshold` (0.005 worked)
- no-response: `abs(exercise) < threshold`
- aggravated: same sign as aging

Reversal rate per score = % of subtypes where exercise reversed the aging
direction. This single number separates the axes into two groups:

```
REVERSIBLE (exercise reverses aging):   IIa 100%, Sarcomeric 90%,
                                        RegMyon 70%, OxPhos 60%
IRREVERSIBLE (exercise cannot touch):   SenMayo 0%, Stress 0%,
                                        TNFA 0%, Inflammatory 0%, Atrophy 10%
```

## The biological narrative (validated on muscle MF)

> "Exercise is the mirror of aging — but only half the mirror. It restores the
> metabolic-structural-identity axis (IIa/Sarcomeric/OxPhos/RegMyon) in nearly
> all fiber subtypes, yet is completely inert on the senescence-inflammation
> axis (SenMayo/Stress/TNFA/Inflammatory)."

**RSS specificity**: RSS showed blunted-but-not-absent exercise response —
IIa +0.060 vs other-9-subtype mean +0.090 (weakest responders), RegMyon +0.020
(weakest of all), while SenMayo/Atrophy fully inert. Narrative: "exercise
touches RSS's metabolic shell but not its senescence core" — RSS is
exercise-refractory at the program level, not just the proportion level.

## Deliverables that landed well

1. **Dual matrix heatmap** — left panel aging delta, right panel exercise
   delta, SAME row order (subtypes along slow→fast axis), shared symmetric
   color scale, same score column order. Visualizes mirror-reversal instantly.
   (pheatmap ×2 + grid.arrange, or two PNGs; pheatmap cannot be nested inside
   base layout() — use `silent=TRUE` + grid.arrange on `ph[[4]]`.)
2. **Reversal-rate bar chart** — scores sorted by reversal rate, dashed line
   at 50%, fill = reversible vs irreversible axis. THE one-panel summary.
3. **RSS fingerprint** — dodge bars of aging vs exercise delta per score for
   the target cluster.
4. **Mirror test scatter** — per subtype, x=aging delta, y=exercise delta;
   dashed `y=-x` line = perfect reversal; highlight target subtype (RSS) in
   red vs grey others. Facet per score.

## Pitfalls

- Score columns are named `scoreI_AUC`... — extract with
  `grep("^score.*_AUC$", colnames(meta), value=TRUE)`; many other obs columns
  exist (metadata, leiden, SCT_snn_res.*) — don't assume all numeric cols are scores.
- Subtype order matters for the dual heatmap: order rows along the biological
  axis (slow→fast: Pure I, LRP1B+(I), OTUD1+(I), RP_high(I), IIA, IIX,
  OTUD1+(II), RP_high(II), Specialized MF, RSS) — do NOT use clustering.
- Score order: identity (I/II/IIa/IIx) → metabolic (OxPhos/Insulin) →
  structure (Sarcomeric) → degeneration (Atrophy/SenMayo) → regeneration
  (RegMyon) → stress (Stress/ROS/TNFA/Inflammatory).
- Use a shared symmetric scale across both matrices
  (`maxabs <- max(abs(aging), abs(exer))`) so colors are comparable.
- Reversal threshold is per-analysis; check raw delta magnitudes first
  (this dataset: identity/metabolic deltas ~0.05-0.33, senescence/inflammation
  ~0.001-0.01 — threshold 0.005 cleanly separated real from noise).
- SenMayo scores are LOW dynamic range (0-0.09) — do not interpret tiny deltas
  as signal; the 0% reversal conclusion rests on exercise deltas < threshold.

## Deliverable style (user preference, 2026-07-31)

User explicitly rejected NMF output that was an artifact inventory ("我没看
出来"). When presenting ANY analysis (NMF, scores, hdWGCNA), lead with the
plain-language biological conclusion ("so what"), then support with evidence
figures/files. For scores specifically: "运动是衰老的镜像，但只镜像了一半"
style framing landed far better than program tables.
