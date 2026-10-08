# ATAC Cell Type Literature Validation (2026-08-27)

## Search Strategy
- Queries: "human hippocampus scATAC-seq [cell type]", "brain snATAC [cell type] annotation"
- Databases: PubMed, EuropePMC, Semantic Scholar
- Date range: 2022-2026 (recent ATAC methods)

## VS (Vascular) — CONFIRMED

**Literature**:
- Heffel et al. 2024 Nature (PMID:39385032) — human brain multi-omics, reports FOXC1+ vascular endothelial and pericyte populations
- Sziraki et al. 2023 Nat Genet (PMID:38036784) — human brain aging snRNA, reports FOXC1/FOXC2+ vascular cells

**Markers in our data**: CLDN5, FOXC1, FOXC2, FOXF1, FOXF2, ICAM2, VWF, FLT1, PECAM1

**Conclusion**: VS is a well-established brain cell type in ATAC datasets. Annotate with confidence.

## Choroid Plexus (ChP) — LIKELY ABSENT

**Literature**:
- Liu et al. 2025 Cell (PMID:40752494) — human brain multi-region snATAC, reports ChP (TTR/FOLR1/OTX1)
- Bilgic et al. 2025 Aging Cell (PMID:41015942) — mouse hippocampus aging ATAC, reports ChP-related chromatin accessibility

**Markers in our data**: No TTR, FOLR1, or AQP1 found in markerList

**Conclusion**: ChP is present in multi-region brain ATAC but rare in hippocampus-specific datasets. Our 40-sample hippocampus data likely has too few ChP cells to form a distinct cluster. Do not force annotation.

## C13 (HOX+/MNX1+) — UNKNOWN (no literature support)

**Literature search**: 8 papers reviewed, NONE report HOX+/MNX1+ clusters in human hippocampus ATAC

**Markers**: HOXD11 (Log2FC 4.4), MNX1 (4.2), HOXB5 (4.1), HOXA2 (3.9), KRTAP1-3 (3.8)

**Interpretation**:
- MNX1 is a motor neuron marker (PMID:27572435), not expressed in hippocampus
- HOX genes are silenced in adult hippocampus (PMID:26541512)
- KRTAP genes are skin/hair-related, not CNS
- Pattern = peripheral tissue contamination (likely from nearby nerve tissue during dissection)

**Conclusion**: Annotate as Unknown. Not a real hippocampus cell type.

## C26 (OPC-like) — CONFIRMED by L2 debate

**Literature**: No direct match, but OPC/oligodendrocyte precursors are well-documented in brain ATAC

**Markers**: GeneScoreMatrix shows S100B + oligo lineage; getMarkerFeatures shows OR/TAS2R (differential artifacts)

**L2 debate verdict**: OPC-like (early differentiation), not mature ODC, not noise

**Conclusion**: Annotate as OPC-like. The OR/TAS2R peaks are technical artifacts of differential analysis, not cell identity markers.
