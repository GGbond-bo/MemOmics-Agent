# Target Scoring Methodology

## Overview

The multi-omics composite score integrates transcriptomic evidence from scRNA-seq with human genetic evidence to prioritize drug targets. Unlike the `genetic-target-hypothesis` skill (GeneBass-first), this scoring starts from scRNA-seq-derived disease biology and integrates genetic evidence for orthogonal validation.

## Composite Score Formula

```
composite_score = (
    0.20 * de_score +
    0.15 * pathway_score +
    0.15 * lr_score +
    0.10 * specificity_score +
    0.25 * genetic_score +
    0.15 * druggability_score
) * convergence_multiplier
```

Where `convergence_multiplier` = 1.2 if BOTH genetic AND transcriptomic evidence exist, else 1.0.

## Component Scoring

### Differential Expression Score (weight: 0.20)

**Source:** Pseudobulk DE results per cell type (pydeseq2)

**Formula:**
```
sig_score = min(-log10(padj) / 10, 1.0)
fc_weight = min(|log2FC| / 3.0, 1.0)
gene_score = sig_score * 0.6 + fc_weight * 0.4
```

**Modifiers:**
- Disease-relevant cell type bonus: 1.2x (e.g., fibroblasts in SSc)
- Multi-cell-type DE bonus: +10% per additional cell type (up to cap)

### Pathway Centrality Score (weight: 0.15)

**Source:** GSEA results from gseapy, pathway activity from decoupler

**Logic:**
- Count pathways where gene appears in GSEA leading edge (FDR < 0.25)
- Base score: n_pathways / 10 (up to 0.6)
- Disease-relevant pathway boost: n_disease_pathways / 5 (up to 0.4)

### L-R Involvement Score (weight: 0.15)

**Source:** liana-py multi-method consensus ranking

**Logic:**
- Count significant interactions involving the gene as ligand or receptor
- Base score: n_interactions / 20 (up to 0.5)
- Disease-relevant L-R pair boost: +0.2 per known disease pair (up to 0.5)

### Cell-Type Specificity Score (weight: 0.10)

**Source:** Cross-cell-type DE comparison

**Logic:**
- Tau-like specificity index across cell types with significant DE
- Weighted by disease-relevant cell type involvement
- Genes DE specifically in myofibroblasts score higher than ubiquitous genes

### Genetic Evidence Score (weight: 0.25)

**Source:** GeneBass, TWAS Atlas, eQTL Catalogue, Open Targets L2G

**Sub-scoring:**
```
genetic_score = (
    0.50 * genebass_score +      # min(-log10(p) / 10, 1.0)
    0.20 * twas_score +           # Binary: significant in any tissue
    0.15 * eqtl_score +           # Binary: eQTL in disease-relevant tissue
    0.15 * l2g_score +            # Continuous 0-1 from Open Targets
    direction_concordance_bonus   # +0.1 if GeneBass agrees with scRNAseq direction
)
```

**Graceful degradation:** If GeneBass unavailable, remaining components are reweighted. If no genetic data at all, genetic_score weight is redistributed to transcriptomic components.

### Druggability Score (weight: 0.15)

**Source:** Open Targets Platform

**Components:**
- Tractability: small molecule (+0.3), antibody (+0.2)
- Known drugs: approved (+0.4), Phase 3 (+0.3), Phase 2 (+0.2), Phase 1 (+0.1)
- Genetic constraint: LoF-tolerant (+0.1 safer), LoF-constrained (-0.1 safety concern)

## Convergence Bonus

Targets with BOTH:
- Transcriptomic evidence: DE score > 0.3 in any cell type
- Genetic evidence: GeneBass p < 1e-4 or TWAS significant

Receive a 1.2x multiplier on their composite score. This rewards multi-omics convergence as the strongest evidence for target validity.

## Priority Tiers

| Tier | Score | Interpretation |
|------|-------|----------------|
| **HIGH** | >= 0.55 | Strong multi-evidence support, prioritize for validation |
| **MEDIUM** | 0.35 - 0.55 | Moderate evidence, consider with additional data |
| **LOW** | < 0.35 | Limited evidence, exploratory only |

## Disease Context Configuration

The scoring includes a configurable `disease_context` dictionary that adjusts relevance weights. For SSc:

- **Relevant cell types:** myofibroblast, fibroblast, macrophage, endothelial, Th2
- **Relevant pathways:** TGF-beta, Wnt, PDGF, IL-4/IL-13, ECM, fibrosis
- **Relevant L-R pairs:** TGFB1-TGFBR1, PDGFB-PDGFRA, IL13-IL13RA1, etc.

For a different disease, replace the context dictionary with disease-specific cell types, pathways, and L-R pairs.
