---
name: cross-species-cre-conservation
category: GWAS/Genetics
description: >
  Cross-species cis-regulatory element (CRE) conservation assessment framework.
  Five-layer pipeline (sequence → epigenetic → 3D structure → functional →
  CRECS composite score) for quantitatively evaluating whether regulatory
  elements from one species (e.g., monkey) can substitute for another
  (e.g., human) in brain research. Patent-ready methodology with A/B/C/D
  four-tier classification. Data sources: ENCODE ATAC-seq/ChIP-seq/Hi-C, 
  UCSC phastCons/GERP, GTEx RNA-seq, public monkey brain epigenomic datasets.
trigger:
  when:
    # RED — mandatory skill_view triggers
    - user mentions "CRE" / "调控元件" / "cis-regulatory" / "顺式调控"
    - user mentions "enhancer conservation" / "增强子保守性"
    - user mentions "CRECS" / "跨物种CRE" / "cross-species CRE"
    - user mentions "cross-species ATAC" / "跨物种ATAC" / "跨物种染色质"
    - user mentions "chromatin accessibility conservation" / "染色质可及性保守"
    - user mentions "enhancer replaceability" / "enhancer substitutability"
    - user asks "猴脑能替代人脑做调控元件研究吗"
    - user mentions "LiftOver cross-species regulatory"
    - user mentions "phastCons" / "GERP" in cross-species context
  rules:
    - Framework assumes no prior CRE knowledge from user — explain concepts with analogies
    - Always start with Part 0 (beginner primer) for users who self-identify as beginners
    - Default comparison pair: human vs rhesus/cynomolgus macaque
    - Patent angle: this is a method invention, not a scientific discovery — frame accordingly
    - Data is public (ENCODE/GEO/UCSC) — no wet-lab experiment needed
---

# 🧬 Cross-Species CRE Conservation Assessment

## Overview

A five-layer quantitative framework for evaluating whether cis-regulatory elements (CREs) — enhancers, promoters, silencers, insulators — from one species can substitute for another in brain research. Designed for patent-oriented professional master's students who need an applied, data-driven method with clear industrial value.

**Core insight**: While cell-type composition differs between species (e.g., human vs monkey brain), CRE-level conservation is more fundamental, less confounded, and directly relevant to drug-target validation and model selection.

## Default Assumptions

| Parameter | Default | Notes |
|-----------|---------|-------|
| Species pair | Human (hg38) vs Rhesus macaque (rheMac10) | ~25 Mya divergence |
| Tissue | Brain (hippocampus, prefrontal cortex, etc.) | Expandable to other tissues |
| Data sources | ENCODE, PsychENCODE, GEO, GTEx, UCSC | All public, no wet-lab needed |
| Genome chain | UCSC hg38 ↔ rheMac10 LiftOver | Reciprocal best-hit required |

## Five-Layer Pipeline

```
L0: Data Collection → L0.5: Preprocessing → L1: Sequence → L2: Epigenetic
→ L3: 3D Structure → L4: Functional → L5: CRECS Score → Validation
```

### L0 — Data Collection (all public)
Data needed per species:
1. **ATAC-seq / DNase-seq peaks** (BED) — open chromatin regions = candidate CREs
2. **H3K27ac ChIP-seq** (bigWig) — active enhancer marks
3. **H3K4me3 ChIP-seq** (bigWig) — active promoter marks
4. **CTCF ChIP-seq** (BED) — insulator binding
5. **Hi-C / HiChIP** (optional) — 3D chromatin contacts
6. **RNA-seq** (for L4 validation)

Key human sources: ENCODE, PsychENCODE, GTEx
Key monkey sources: Meng 2026 Nat Commun (cortex ATAC), Luo 2020 Cell (hippocampus Hi-C), monkey brain epigenome project

### L0.5 — Preprocessing
1. Uniform genome versions: human hg38, monkey rheMac10
2. Download UCSC chain files for LiftOver
3. One-to-one ortholog gene pairing (biomaRt / Ensembl)
4. Reciprocal LiftOver of CRE coordinates

### L1 — Sequence Conservation
Metrics:
- **Sequence similarity** (Needleman-Wunsch global alignment)
- **phastCons score** (UCSC 100-way — pre-computed, just query)
- **GERP score** (genomic evolutionary rate — pre-computed)
- **TF binding site conservation** (JASPAR FIMO motif scan)

Orthologous CRE threshold: LiftOver reciprocal overlap ≥ 50% AND sequence similarity ≥ 70%

### L2 — Epigenetic Conservation
Metrics:
- ATAC signal correlation between orthologous CRE pairs
- H3K27ac signal difference (normalized)
- Cell-type specificity conservation (Jaccard of open cell types)

Formula: `E_conservation = 0.6 × cor(ATAC) × (1 - normalized_H3K27ac_diff) + 0.4 × cell_type_Jaccard`

### L3 — 3D Structure Conservation (when Hi-C available)
Metrics:
- Enhancer-promoter loop sharing
- TAD boundary position conservation
- A/B compartment concordance

Fallback (no Hi-C): Use "nearest gene" approximation + ABC model predictions.

### L4 — Functional Conservation
Metrics:
- Target gene expression correlation (snRNA-seq)
- eQTL effect conservation
- GWAS colocalization (coloc)

### L5 — CRECS Composite Score

```
CRECS = 0.20 × S_sequence + 0.35 × S_epigenetic + 0.20 × S_3D + 0.25 × S_functional
```

Four-tier classification:
| Grade | CRECS | Meaning | Application |
|-------|-------|---------|-------------|
| **A** | ≥ 0.75 | High conservation, monkey can fully substitute | 🟢 Drug screening priority |
| **B** | 0.50–0.75 | Moderate, usable with extra validation | 🟡 Use with caution |
| **C** | 0.25–0.50 | Low conservation, limited substitutability | 🟠 Specific conditions only |
| **D** | < 0.25 | Species-specific, not substitutable | 🔴 Find alternative model |

### Validation Layer
1. **Evolutionary anchors**: known ultra-conserved CREs → expected Grade A
2. **Negative controls**: randomly shuffled regions → expected Grade D
3. **GWAS cross-check**: brain disease GWAS loci → expected high conservation in relevant cell types

## Patent Angles

| Innovation Point | Prior Art Gap | Our Advantage |
|-----------------|---------------|---------------|
| CRECS composite scoring | Only single-dimension comparisons exist | 4-dimension weighted, brain-specific |
| Reciprocal LiftOver CRE pairing | Unidirectional mapping, high false positives | Bidirectional + sequence filter |
| A/B/C/D four-tier with cell-type resolution | No systematic output of "which can substitute" | Directly guides model selection |
| GWAS cross-validation | Assessment methods lack independent validation | Human disease genetics validates biological meaning |
| Adaptive weights via debate_analysis | Weights are subjective | Biologically validated post-hoc adjustment |

## Key Tools

| Layer | Tools |
|-------|-------|
| L0.5 | UCSC LiftOver, BEDTools, biomaRt, pybedtools |
| L1 | phastCons (UCSC query), GERP, JASPAR FIMO, Biostrings |
| L2 | deepTools, GenomicRanges (R), rtracklayer, pyBigWig |
| L3 | HiC-Pro, FAN-C, ABC model (python) |
| L4 | DESeq2, coloc (R), statsmodels |
| L5 | Custom Python/R scoring script |

## Pitfalls

1. **Genome version mismatch**: Always verify both species use the SAME UCSC genome version convention (e.g., both hg38 or both GRCh38)
2. **LiftOver chain direction**: hg38→rheMac10 vs rheMac10→hg38 — use the correct chain for each direction
3. **Ortholog mapping gaps**: Not all human genes have a 1:1 monkey ortholog — handle many-to-many separately
4. **Cell-type mixing in bulk data**: If using bulk ATAC-seq, CRE signals are averaged across cell types — use snATAC-seq when possible
5. **phastCons is pre-computed for specific alignments**: Verify the track includes both human and rhesus in the multiple alignment
6. **Don't mix peak callers**: Use the same peak caller (MACS2) and same parameters for both species to avoid caller bias
7. **Hi-C resolution limits**: Most public Hi-C is 5-10kb resolution — fine for TADs but may miss individual E-P loops

## Beginner Teaching Pattern

When the user self-identifies as a beginner ("小白"), start with Part 0 analogies:
- CRE = "sticky notes on architectural blueprints" telling which page to read
- ATAC-seq = "scanning which pages are open"
- LiftOver = "converting page numbers between two different editions of the same book"
- phastCons = "a pre-calculated score you look up in a database — no math needed"

Then use the `references/beginner-quickstart.md` for concrete first steps.

## Integration with Other Skills

- **research-plan**: Generates Mermaid roadmap + module table for this framework
- **bioinformatics-patent-strategy**: Maps CRECS innovation points to patent claims
- **deep-research**: Multi-round literature search to verify patent gaps before execution
- **atac-seq-memomics**: Single-species ATAC-seq QC and peak calling (L0 prerequisite)

## References

| File | Content |
|------|---------|
| `references/framework-full.md` | Complete 8-part technical framework from 2026-07-21 session |
| `references/beginner-quickstart.md` | Step-by-step first analysis for CRE beginners |
| `references/patent-angles.md` | Detailed patent claim mapping and A25 defense strategy |
| `references/data-sources.md` | Curated list of ENCODE/GEO accessions for human and monkey brain CRE data |
