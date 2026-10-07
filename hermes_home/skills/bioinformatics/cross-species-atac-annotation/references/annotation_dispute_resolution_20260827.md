# Annotation Dispute Resolution & Contamination Signatures (2026-08-27)

## L2 Debate for Annotation Disputes

When annotation is uncertain and the user questions a classification, use **L2 full 8-role debate** (not L1 lightweight):

- **Trigger**: User asks "你触发的是8个专家辩论吗？" or similar
- **L1 = insufficient** for annotation disputes — L1 uses context sampling which misses critical evidence
- **L2 = 8 roles**: pro_biology, pro_statistics, pro_bioinformatics, con_biology, con_statistics, con_bioinformatics, con_history, judge
- **Topic format**: "Cxx = [claimed cell type]? — validate with GeneScoreMatrix + getMarkerFeatures evidence"

### C26 Case Study (L2 debate result, 2026-08-27)
- Topic: "C26 = ODC?"
- Verdict: **modify** (high confidence) → C26 = **OPC-like (少突前体)**
- Key evidence: GeneScoreMatrix shows S100B + ODC lineage; getMarkerFeatures OR/TAS2R peaks are differential artifacts not identity markers
- C26 vs C30: C30 = mature ODC (KLK6/MAG/OPALIN), C26 = early differentiation (DLL3/GNG2/ASCL1/OLIG1 high, PLP1/MBP absent)

## C13 Contamination Signature (2026-08-27)

**Pattern**: MNX1 + HOX gene cluster + KRTAP + non-CNS genes in hippocampal ATAC

| Marker | Log2FC | Category |
|--------|--------|----------|
| MNX1-AS1 | 4.93 | Motor neuron marker |
| HOXD11 | 4.41 | Body axis patterning (Hox cluster) |
| HOXB5 | 4.20 | Body axis patterning |
| UTS2R | 4.12 | Urotensin receptor |
| KRTAP1-3/4-2 | 3.7-4.0 | Keratin-associated protein (skin/hair) |
| GRM6 | 4.01 | Glutamate receptor (functional) |

**Diagnosis**: Peripheral tissue contamination (spinal cord / trigeminal ganglion / peripheral nerve)
- MNX1 is a motor neuron专用 marker (PMID: 27572435) — should NOT be expressed in hippocampus
- HOX genes are silenced in adult hippocampal neurons (PMID: 26541512)
- KRTAP genes are skin/hair follicle markers

**Rule**: Clusters with MNX1 + ≥3 HOX genes + KRTAP = **peripheral tissue contamination** → exclude from downstream analysis

## C20-C23 Microglia Subtypes (confirmed 2026-08-27)

| Cluster | State | Markers | DoubletRate |
|---------|-------|---------|-------------|
| C20 | Homeostatic | TAL1, IRF8, C3AR1, ABI3 | 20.5% DS>10 ⚠️ |
| C21 | Inflammatory | CCL18, CCL23, FOXC2 | 8.4% |
| C22 | Phagocytic | SIGLEC7, LILRB4, TYROBP | 1.6% |
| C23 | Macrophage (peripheral) | CD163, S100A8, CLEC5A, CXCL10 | 1.5% |

C20 has highest doublet rate — some "homeostatic microglia" cells may be true doublets.
C23 is blood-derived macrophage (NOT microglia) — CD163/S100A8 are macrophage-specific markers absent from C20-C22.
