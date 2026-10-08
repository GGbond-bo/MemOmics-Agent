# Skeletal Muscle Myofiber F2 Design — Session Case Study

> Human skeletal muscle snRNA-seq, 324K cells, 5 conditions (Young / Old / Old+Ex / T2D / T2D+Ex).
> 10 myofiber subtypes identified: Pure Type I/IIA/IIX, OTUD1+(I/II), RP_high(I/II),
> LRP1B+(I), Specialized MF, RSS.

## Key Biology Discovered by the User

1. **Specialized MF is a dual-origin population**: denervation-slow (CHRNA1+MYH7+,
   denervation score high) AND developmental-fast (RUNX1+MYH2+, regeneration score high)
   converge into the same transcriptional state. Aging increases the denervation component;
   exercise increases the developmental component in normal elderly but the denervation
   component in T2D+exercise.

2. **RSS is an aging-specific, exercise-resistant state**: near-zero in Young,
   increases dramatically in Old, does NOT respond to exercise. Located near fast-twitch
   (Pure IIX) in UMAP space. Top markers: BMPR1B, EFNA5, COL14A1, NSG2, SORBS2, RYR2.

## F2 Design Evolution Through User Corrections

### Initial (rejected) proposal: 3-layer hierarchy
```
L1: fast/slow axis → L2: functional substates → L3: special populations
```
**User correction**: "我没见到哪个文章这么做过。他们之间就是存在转换关系的，也不确定谁转换谁。
展示层级，我感觉不是很好。"

→ Replaced with "continuum" language. No artificial containers.

### Second (rejected) proposal: forced Monocle3 trajectory
```
Trajectory A: Pure IIA → Pure IIX → OTUD1+(II) → Specialized MF
Trajectory B: Pure Type I → LRP1B+(I) → RSS
```
**User correction**: Pure IIX is purer fast-twitch than IIA; Specialized MF has two
subcomponents with opposite trajectories; RSS is near fast-twitch, not slow-twitch.

→ Replaced with: (a) Specialized MF sub-clustering proof, (b) PCA perturbation vector
field instead of pseudotime.

### Final F2 architecture accepted by user

```
2a. Condition-resolved UMAP (5-panel split + density contours)
2b. Fiber type continuum split-violin (fast_score - slow_score per cluster per condition)
2c. Specialized MF dual-origin evidence
    2c-i.   Sub-clustering (denervated-slow vs developmental-fast)
    2c-ii.  Differential markers
    2c-iii. Condition-specific responses
    2c-iv.  RNA velocity / diffusion map convergence
2d. RSS aging-specificity evidence chain
    2d-i.   UMAP highlight
    2d-ii.  Top marker violin
    2d-iii. Condition proportion (with exercise non-response quantification)
    2d-iv.  Function score validation vs other 9 clusters
2e. Multi-condition perturbation vector field (PCA vectors + reversibility index)
2f. NMF gene program discovery (program × cluster + program × condition)
```

## Implementation Notes

- Data used: `muscle_aging_60k_subset.h5ad` (60K cells, 45,607 MF cells)
- Conditions available: Young (YM samples), Old (OM samples), T2D (P samples)
- No exercise condition in this dataset — need separate exercise cohort data
- 10 MF subtype annotations (RSS, Specialized MF, etc.) are in a separate user file
  (not in the public h5ad), path not yet provided
