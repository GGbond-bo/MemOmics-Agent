# 14-Score Difference Analysis + z-score Heatmap (validated 2026-08-12)

User asked "我打分已经给你了，你能帮我找找差异吗？别人期刊是怎么出图的，怎么展示差异的？
希望你能找到大文章的思路和出图代码，并分析这些打分" for a 50万-cell metadata CSV carrying
14 AUCell score columns. Validated on muscle MF (48 samples: Y=10/O=7/OD=7, 6 groups
Y/O/OD × Pre/Post paired).

## Workflow (reuse the L3 proportion machinery — do NOT re-invent statistics)

1. **Per-sample aggregation first**: `meta[, lapply(.SD, mean, na.rm=TRUE), by=samplename,
   .SDcols=score_cols]` — never test at cell level (pseudoreplication, same rule as
   proportions). 48 samples × 14 scores.
2. **Same 6-comparison framework** as the proportion analysis: 3 paired Pre→Post
   (Y/O/OD, matched by base_id = samplename minus `_Pre/_Post`) + 3 unpaired cross-group
   (YvsO, OvsOD, YvsOD). Same `safe_paired()` / `cliffs_delta()` and dual FDR
   (per-score BH across its 6 comparisons + global BH across all 84 rows).
3. Save `data/score_diff_all_14scores.csv` (14×6 = 84 rows) + `data/score_group_means.csv`
   (6 groups × 14 scores) for downstream plotting.

## Deliverable figure: z-score row-normalized ComplexHeatmap with significance stars

This is the display style used in big muscle atlas papers (Kim 2023 Nat Commun /
Dos Santos 2023 Nature): rows = scores (readable labels), cols = 6 groups in logical
order (Y_Pre/Y_Post/O_Pre/O_Post/OD_Pre/OD_Post, cluster_columns=FALSE), fill =
row-scaled z-score (`t(scale(t(mat)))`), diverging ramp
`colorRamp2(c(-2,0,2), c("#1F4E79","white","#B22222"))`.

- **Star overlay** via `cell_fun`: build a score×group star matrix from the FDR table —
  star = FDR<0.001→"***", <0.01→"**", <0.05→"*"; for each significant row write the star
  into BOTH compared groups' cells (`fdr_mat[sc, g1]` and `fdr_mat[sc, g2]`). Deduplicate
  repeated stars per cell.
- **Export**: open device → `draw(ht)` → `dev.off()` — never ggsave (ComplexHeatmap is a
  grid object). PNG (110×130mm@300dpi) + PDF both fine.
- **Verify direction against group means**: same trap as proportion deltas — print mean
  per group for each significant score and write the direction in words before
  interpreting (e.g. "scoreIIa Y 0.260 → O 0.177 = aging ↓").

## Validated muscle findings (expected-value anchors)

| Score | Signal | Numbers |
|---|---|---|
| scoreIIa | aging ↓ (strongest) | FDR=0.0006, Y 0.260 → O 0.177 |
| scoreOxPhos | aging ↓ (strongest) | FDR=0.0006, Y 0.240 → O 0.189 |
| scoreInsulin | aging ↓ + Y exercise ↑ | Y→O FDR=0.019; Y Pre→Post FDR=0.039 |
| scoreI | diabetes ↓ | Y→OD FDR=0.004, 0.697 → 0.524 |
| scoreSarcomeric | aging ↓ | Y→O / Y→OD FDR=0.006 |
| scoreSenMayo | aging ↓ (counterintuitive) | Y→O FDR=0.007 — at FIBER level SenMayo goes DOWN with age; interpret carefully (fiber-level senescence signature is not the aging driver; do not narrate as "senescence decreases") |

Interpretation rule of thumb: 15 FDR<0.05 of 84 rows survived; scores separate into
aging-driven (IIa/OxPhos/Sarcomeric/Insulin), diabetes-driven (I), and exercise-responsive
(Insulin Y-ex). **Score analysis answers "比例没变≠功能没变"** — composition and state
are independent dimensions; after the proportion story, run the same score analysis to
show what changed INSIDE the cells whose proportions did not move.

## MSigDB download answer (user asked "这里面下载哪一个?")

For HALLMARK_GLYCOLYSIS (or any MSigDB hallmark page): download **gmt** (or **grp**).
- gmt = one gene set per line, universal format, read by `msigdbr`/`fgsea`/`AUCell`/`clusterProfiler`
- grp = pure gene list (one column), simplest if you just need the gene names
Either works for AUCell/AddModuleScore; recommend gmt as the general choice.

## Gene-set gap analysis (what to add to a 14-score panel)

Reviewed user's pathway_score.xlsx (all entries had PMID/DB sources) + their draft
16-gene denervation set. Gaps by priority:
- **P0**: Glycolysis (pairs with existing OxPhos → metabolic flexibility index
  OxPhos/Glycolysis), Denervation (fix: add NCAM1, PMID 3892537 foundational; remove
  SCN4A — adult Na channel DOWN-regulated on denervation, cancels SCN5A signal),
  AMPK-PGC1α exercise axis, Autophagy, Adipogenesis, Fibrosis.
- **P1**: Angiogenesis, mTOR/protein-synthesis, FAO, Mitophagy.
- **Denervation set evaluation pattern**: per-gene verdict (gold-standard / classic /
  reasonable / weak / overlapping-with-existing-score) — user's set had 7/16 genes
  overlapping Atrophy/RegMyon/Sarcomeric scores (FBXO32/TRIM63/CTSL/GABARAPL1/BAG3 →
  Atrophy; DCLK1/MYOG → RegMyon; DES → Sarcomeric), causing inflated cross-score
  correlation. Core keepers: CHRNA1/CHRNG/CHRND/MYOG/RUNX1/SCN4A/SCN5A/KCNMB1 + NCAM1
  (+ GAP43 optional).
- 9 PMC open-access download links (NCAM foundation, denervation-review, NMJ-mTORC1,
  HDAC4-MYOG feedback, etc.) — see `skeletal-muscle-gene-score-sources.md` for the full
  literature table with PMIDs.

## Scripts (validated)

- `03_score_diff.R`: read metadata → per-sample aggregation → 6 comparisons → dual FDR →
  write CSVs. Exit 0, ~1 min on 508k cells.
- `04_score_heatmap.R`: group means → z-score matrix → ComplexHeatmap with cell_fun stars →
  PNG+PDF export. Produces figures/score_heatmap_14x6.png (49KB).
