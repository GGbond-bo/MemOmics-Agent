# Genetic Evidence Guide

## Overview

The genetic evidence module provides orthogonal human genetic support for scRNAseq-derived drug targets. Genes with both transcriptomic disease signatures AND human genetic evidence are the highest-confidence targets.

## Evidence Hierarchy

1. **GeneBass** (rare variant burden) — best when disease is in UK Biobank. Raw p-values and effect sizes.
2. **Open Targets Disease Genetics** (GWAS + ClinVar + gene burden) — primary fallback. Uses the actual disease's GWAS and clinical variant evidence. For SSc: IRF5, STAT4, CD247, TYK2, BLK, etc.
3. **TWAS Atlas** — disease-specific TWAS results only. No proxy diseases.
4. **eQTL Catalogue** — tissue-specific regulatory evidence (skin, blood, immune). Filtered at p < 0.05.
5. **Open Targets L2G** — ML-based gene prioritization at GWAS loci.

The key improvement over proxy-disease approaches: we use SSc-specific GWAS evidence from Open Targets rather than borrowing RA or lupus genetics from GeneBass.

## Data Sources

### GeneBass (UK Biobank Exome Sequencing)
- **What:** Rare variant burden test results from 500K UK Biobank exomes across 4,131 phenotypes
- **How:** Tests whether rare protein-truncating (pLoF) or missense variants in a gene are enriched in individuals with a phenotype
- **Why useful:** Directly links gene function to disease -- if LoF variants protect against disease, inhibiting that gene is therapeutic
- **Direction:** BETA_Burden < 0 for pLoF = loss-of-function is protective = inhibit. BETA_Burden > 0 = LoF increases risk = activate.
- **Limitation:** SSc is too rare in UK Biobank for powered burden tests (typically 0 hits)

### Open Targets Disease Genetics (GWAS + ClinVar + gene burden)
- **What:** Aggregated genetic association evidence from GWAS catalog, ClinVar, and gene burden studies
- **How:** Open Targets computes a `genetic_association` score (0-1) per gene-disease pair integrating common variant GWAS, clinical variants (ClinVar), and rare variant burden from multiple biobanks
- **Why useful:** Disease-specific genetic evidence without needing proxy diseases. For SSc: 110 genes with genetic evidence including known GWAS hits (IRF5, STAT4, CD247, TYK2, TNFSF4)
- **EFO IDs for SSc:** EFO_0000717 (systemic scleroderma), MONDO_0016358 (limited cutaneous), EFO_0000404 (diffuse scleroderma)

### TWAS Atlas (CNCB-NGDC)
- **What:** Published TWAS results from multiple methods (FUSION, S-PrediXcan, SMR)
- **How:** Tests whether genetically predicted gene expression is associated with disease risk
- **Searches:** Disease-specific terms only (no proxy diseases). For SSc: systemic sclerosis, scleroderma, pulmonary fibrosis, ILD, Raynaud's

### eQTL Catalogue (EBI)
- **What:** Tissue-specific eQTL associations from multiple studies
- **Filter:** p < 0.05 significance threshold applied
- **Tissues for SSc:** Skin, whole blood, immune cells, fibroblasts, lung

### Open Targets L2G (Locus-to-Gene)
- **What:** ML scores (0-1) prioritizing the most likely causal gene at each GWAS locus
- **How:** Integrates colocalization, chromatin interaction, distance, and functional annotations

## Scoring

```
genetic_score = (
    # Primary: GeneBass OR OT Disease Genetics (0.40-0.50)
    GeneBass: min(-log10(p)/10, 1.0) * 0.40 + OT: score * 0.10
    OR (if no GeneBass):
    OT Disease Genetics: score * 0.50

    # Secondary:
    + TWAS significant: 0.15
    + eQTL support: 0.10
    + L2G: score * 0.10
    + Direction concordance: +0.10 bonus
)
```

## Graceful Degradation

1. **GeneBass + OT available:** Full scoring with rare variant + common variant evidence
2. **GeneBass empty, OT available:** OT Disease Genetics is primary (SSc has 110 genes)
3. **No genetic APIs available:** Transcriptomic-only scoring (genetic weight redistributed)
