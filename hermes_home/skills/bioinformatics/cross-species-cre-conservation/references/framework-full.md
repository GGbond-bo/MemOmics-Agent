# Full CRE Conservation Framework (Session: 2026-07-21)

> Complete framework generated for user's patent pivot from "cell-type replaceability" to "CRE conservation assessment."
> User profile: 专硕 (professional master's), beginner in CRE/genomics, needs analogies and concrete steps.

## Session Context

- **Original direction**: Cross-species cell-type replaceability (monkey→human hippocampus aging)
- **Critique from senior colleague**: Human and monkey brains have high cell-type composition heterogeneity; chromosomes differ. Cell-type-level comparison is confounded.
- **New direction**: Cross-species cis-regulatory element (CRE) conservation assessment — molecular level, not confounded by cell composition.
- **Deep research result**: No existing patent or systematic method exists for this — true white space.

## Framework Structure (8 Parts)

### Part 0: Beginner Primer
- CRE = "sticky notes on architectural blueprints"
- ATAC-seq = "scanning open pages"
- phastCons = "pre-calculated lookup, no math needed"
- LiftOver = "converting page numbers between editions"

### Part 1: Five-Layer Pipeline
- L1: Sequence conservation (phastCons, GERP, sequence alignment, TF binding sites)
- L2: Epigenetic conservation (ATAC signal correlation, H3K27ac, cell-type specificity)
- L3: 3D structure conservation (E-P loops, TAD boundaries, compartments)
- L4: Functional conservation (target gene expression, eQTL, GWAS colocalization)
- L5: CRECS composite score → A/B/C/D classification

### Part 2: Technical Roadmap (Mermaid)
See parent SKILL.md for the Mermaid flowchart.

### Part 3: Step-by-Step Execution Plan
Phase 1: Data download (~1 week) — ENCODE + GEO
Phase 2: Orthologous CRE pairing (~3 days) — reciprocal LiftOver
Phase 3: Epigenetic conservation (~3 days) — signal extraction + correlation
Phase 4: Composite scoring (~2 days) — CRECS formula
Phase 5: Validation (~3 days) — evolutionary anchors + negative controls + GWAS

### Part 4: Module Table
Each phase with purpose, tools, input, output — see parent SKILL.md.

### Part 5: Patent Innovation Points
- CRECS composite scoring (no existing multi-dimension weighted method)
- Reciprocal LiftOver CRE pairing (bidirectional validation)
- A/B/C/D four-tier with cell-type resolution
- GWAS cross-validation layer
- Adaptive weight adjustment via debate_analysis

### Part 6: Why This Direction Is Better
Comparison table: new CRE direction vs old cell-type direction on 8 dimensions.

### Part 7: Next Steps Checklist
6 actionable items for the user.

### Part 8: 5 Key Concepts (one-liners)
ATAC-seq peak, LiftOver, phastCons, BigWig, BED file.

## Key Quantitative Formulas

```
Orthologous CRE: overlap ≥ 50% AND sequence similarity ≥ 70%

E_conservation = 0.6 × cor(ATAC) × (1 − |ΔH3K27ac|/max) + 0.4 × cell_type_Jaccard

CRECS = 0.20·S_seq + 0.35·S_epi + 0.20·S_3D + 0.25·S_func

A: ≥0.75 | B: 0.50-0.75 | C: 0.25-0.50 | D: <0.25
```

## Key Literature (from deep research)

| Paper | Focus | Relevance |
|-------|-------|-----------|
| Meng 2026 Nat Commun | Monkey cortex cis-regulatory atlas | Primary monkey data source |
| Sarropoulos 2026 Science | Mammalian cerebellum regulatory evolution | Competitive landscape |
| Keough 2023 Science (108 citations) | HARs 3D genome remodeling | Most-cited regulatory evolution work |
| Johansen 2025 Cell Genomics | Enhancer prediction method evaluation | Related but evaluates "methods" not "conservation" |
| Moore 2026 Nature | ENCODE cCRE expanded registry | Human CRE reference catalog |
| Kabbe 2026 Nat Neurosci | Adult CNS single-nucleus epigenome atlas | Human brain CRE data |
