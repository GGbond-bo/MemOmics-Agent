# Dual-Origin Evidence Chain — Mixed/Ambiguous Myofiber Subtypes

> Source: 2026-07-31 session, human skeletal muscle snRNA-seq (10 MF subtypes × 2000 cells, SCT),
> Specialized MF = uncommitted mixed subtype. User's F2 narrative: "SpecializedMF = 慢肌去神经 + 快肌发育 双路线".
> User explicitly rejected single-line Monocle3 pseudotime (hides dual origin) — prefers continuum landscape + evidence chain.

## When to use

A cluster is annotated as "mixed"/"specialized"/"uncommitted" and you must prove (not just assert)
that it has **two biological routes** — and, critically, how the two routes relate (independent
origins vs one cascade). Classic case: Specialized MF suspected to combine slow-twitch
denervation + fast-twitch developmental/regenerative programs.

## The 7-step recipe

1. **Literature-validate two route-specific modules** (search_papers first — denervation:
   PMID 42267670 Clin Sci 2026, PMID 40044687 Nat Commun 2025; development: PMID 42255477).
   Canonical gene lists (human skeletal muscle):
   - Denervation module: `CHRNG, CHRNA1, CHRND, NCAM1, GDNF, ERBB3, NTF3, NGF, NTRK2`
     (NCAM1/CD56 = denervation gold standard; CHRNG/CHRNA1/CHRND = fetal AChR re-expression)
   - Developmental/regenerative module: `MYH3, MYH8, MYOG, MYOD1, DLK1, ACTC1`
     (MYH3 = embryonic, MYH8 = neonatal myosin; MYOG/MYOD1 = myogenic regulators)

2. **Verify module genes are expressed in THIS dataset before scoring.** In snRNA-seq,
   GAP43, MYL4, PEG3, NPM2 had 0% expression → drop them. `intersect(genes, rownames(obj))`
   and report expr% per gene per group. A module built on silent genes is a null score.

3. **Dual-axis AddModuleScore** (Seurat, assay="SCT"): one score per module. Compare target
   cluster mean vs reference clusters (Pure Type I, Pure Type IIA, RSS).
   Strong signal pattern: target cluster is the ONLY group with mean > 0 on BOTH axes
   (Specialized MF denerv=+0.076 vs PureI −0.016 / IIA −0.027; devel=+0.033 vs −0.033/−0.019).
   Report gene-level expr% deltas too (CHRNG SP=29.8% vs IIA 5.9%; NCAM1 13.6% vs 5%;
   MYH3 16.7%; MYH8 2.5% vs 0.7%; MYOG 21%) — these survive reviewer scrutiny better than scores alone.

4. **Hartigan dip test** (`diptest` package; auto-install if missing) on each axis within the
   target cluster. Interpretation:
   - p < 0.05 → evidence of >1 mode → two separable subpopulations (strong dual-origin claim)
   - p > 0.05 → NOT evidence of one origin! Frame as "no discrete subclusters; the two routes
     are coupled in a continuous transcriptional cascade" (aligns with continuum-landscape narrative).

5. **Quadrant analysis** (median-split within target cluster): both_high / denerv_high /
   devel_high / both_low. Single-arm fraction is the key number — Specialized MF: 45.5% of cells
   in single arms (denerv_high 457 + devel_high 452), 27% both_high. Two single-high arms that
   can exist independently = routes are partially independent, not one forced cascade.

6. **Orthogonal-program correlation** (tie to NMF or pseudobulk programs): correlate each axis
   with cell-level loadings of known programs (P1=fast, P2=slow). Specialized MF: denerv vs P2
   (slow) r=+0.358, devel vs P1 r=−0.381, P1 vs P2 r=−0.497. This shows *which fiber background*
   each route operates on: denervation associates with slow-twitch program, developmental is
   independent of (anti-correlated with) fast-twitch maturity program.

7. **Address the confounder head-on**: fetal myosin re-expression (MYH3/MYH8) is a *known
   consequence of denervation itself*, so "developmental module enrichment" alone does NOT prove
   an independent developmental origin. The rebuttal must be structural: single-arm cells exist
   (quadrant step 5) + devel anti-correlates with the fast program while denerv correlates with
   the slow program (step 6) → two partially decoupled axes, not one forced cascade. If your data
   can't support that, say so — the honest statement is "denervation-driven fetal program
   re-activation (single cascade)", which is still a publishable, mechanistically rich claim.

## Interpretation language (user-approved, continuum-landscape compliant)

- ❌ "two discrete subpopulations" if dip test is single-mode
- ✅ "dual-route structure coupled in a continuous cascade: slow-twitch denervation arm +
  fast-twitch developmental/regenerative arm, with a both_high transition state"
- ✅ Quote Dos Santos 2023 Nature (12 myofiber subtypes, no hierarchy) as the non-hierarchical benchmark.

## Outputs & verification pattern

- Figures: dual-axis scatter (target vs references, quadrant lines), per-axis density histograms,
  UMAP colored by each axis, orthogonal-program scatter.
- Tables: group means CSV, dip test CSV, quadrant table, axis×program correlation CSV.
- After the run, reproduce the key statistics independently in an ad-hoc verify script
  (recompute scores from raw data, don't read the script's outputs) and **persist a verification
  anchor** to `results/<session>/log/verify_<step>_status.txt` — the anchor is what makes the
  verification evidence trackable (temp verify scripts get cleaned up; the anchor survives).
  Known pitfall in verify scripts: use `grep("^NMF_", colnames(x), value=TRUE)` — omitting
  `value=TRUE` returns column *indices* of the source df, which mis-index the target df.

## Known pitfall: debate service outage

`debate_analysis` returned "[pro_* 辩论生成失败]" for all roles 3× in a row (LLM API layer,
not a parameter issue — topic/context/KBs were all provided). Workflow lesson: after 3
generation failures, record "debate pending — retry with user present" in task_plan, do NOT
block the analysis (the rail_review + verify chain already guards quality), and disclose the
failure transparently rather than pretending the debate ran.
