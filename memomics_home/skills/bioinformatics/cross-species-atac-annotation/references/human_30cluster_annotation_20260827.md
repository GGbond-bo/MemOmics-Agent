# Human Hippocampus 30-Subcluster Annotation — Final Audit Trail (2026-08-27)

Session: memomics-cd677556. Data: GSE278576 (Zemke 2024), human hippocampus scATAC, 40 samples,
265,909 cells, ArchR 30 clusters C1-C30. Target species marker list: `E:/专利/human_40_markerList.csv`
(20,326 rows, getMarkerFeatures). Reference species: macaque (`E:/专利/patent/monkey_Hf_ATAC_final.rds`).

## Monkey reference annotation (read from rds predictedAnno — source of truth)

| Subclass | Cells | | Subclass | Cells |
|---|---|---|---|---|
| ODC | 44,021 | | CGE CNR1 Inh | 2,190 |
| DG Ex | 28,854 | | CAE_SUB deep Ex | 2,130 |
| Astrocyte | 23,548 | | MGE SST Inh | 1,884 |
| CA1_SUB s.f. Ex | 16,457 | | CGE LAMP5 Inh | 1,408 |
| Microglia | 9,388 | | MGE PVALB Inh | 1,232 |
| CA2/4 EX | 7,833 | | Ependymal | 879 |
| EC L3/5 EX | 6,878 | | Choroid Plexus | 702 |
| OPC | 6,574 | | VS | 624 |
| EC L6 EX | 3,669 | | | |
| EC L2 EX | 3,226 | | | |

Note: manuscript said Ast1/2/3 / ODC1/2 / OPC1/2 / Mic1/2/3 / Macrophage — rds does NOT have these.

## Human final annotation (human_subcluster_annotation_final.csv)

| Human | Annotation | Best score | Evidence markers (top hits) |
|---|---|---|---|
| C1 | OPC | 9.0 | CSPG4, MYT1, SOX6, DLL3, ASCL1 |
| C2 | OPC | 9.5 | CSPG4, PDGFRA, MYT1, SOX6, DLL3 |
| C3 | OPC | 9.0 | CSPG4, MYT1, SOX1, ASCL1, PDGFRA |
| C4 | OPC | 6.0 | CSPG4, MYT1, ASCL1, DLL3, GSX1 |
| C5 | OPC | 7.5 | CSPG4, MYT1, SOX6, ASCL1, DLL3 |
| C6 | OPC | 9.5 | CSPG4, MYT1, SOX1, ASCL1, SOX6 |
| C7 | Astrocyte | 9.5 | AQP4, SLC1A2, GJA1, EDNRB, FOXG1 |
| C8 | Astrocyte | 14.5 | GFAP, AQP4, SLC1A2, ALDH1L1, EMX2, PAX6 |
| C9 | Astrocyte | 16.0 | GFAP, AQP4, SLC1A2, ALDH1L1, EMX2, LHX2, ZIC5, CXCL14 |
| C10 | Astrocyte | 14.5 | GFAP, AQP4, SLC1A2, ALDH1L1, EMX2, LHX2, CXCL14 |
| C11 | Astrocyte | 11.5 | GFAP, AQP4, SLC1A2, ALDH1L1, EMX2 |
| C12 | Astrocyte | 13.0 | GFAP, AQP4, SLC1A2, ALDH1L1, EMX2, ZIC5, FEZF2 |
| C13 | C13 (kept) | — | HOXD11/MNX1/HOXB5 HOX cluster + GRM6 → suspected doublet/artifact |
| C14 | MGE Inh | 13.5 | DLX1, DLX6, SLC32A1, GAD1, SNCB, SRRM4 |
| C15 | MGE Inh | 13.5 | DLX1, DLX6, LHX6, SLC32A1, GAD1, SNCB, CDK5R2 |
| C16 | MGE Inh | 10.0 | DLX1, DLX6, GAD1, SLC32A1, SNCB, GJD2 |
| C17 | C17 (ExN) | 15.0 | EGR4, NEUROD2, FEZF2, SLC17A7, CDK5R2, LRRC10B, ICAM5 |
| C18 | C18 (ExN) | 16.5 | NEUROD6, SSTR3, EGR4, LRRC10B, GSG1L2, CTXN2 |
| C19 | C19 (ExN) | 17.0 | NRGN, SSTR3, HRH2, CDK5R2, GSG1L2, LRRC10B, ICAM5 |
| C20 | Microglia | 22.0 | CX3CR1, P2RY12, P2RY13, C1QB, ABI3, IRF8, LILRB4 |
| C21 | VS | 10.0 | CLDN5, FOXC2, FOXF1, FOXF2, ICAM2 |
| C22 | Microglia | 28.5 | CX3CR1, P2RY12, P2RY13, TMEM119, TYROBP, ABI3, LILRB4, IRF8, HLA-DRB1 |
| C23 | Microglia_activated | 24.0+15.5 | CXCL10, CLEC5A, S100A8, CD163, CASP1, FPR2, CCL11 + steady-state hits |
| C25 | C25 (kept) | 0 | TCAF2, CPA5 (only 5 markers) → low confidence |
| C26 | C26 (kept) | 1 | TAS2R9, IFNA10, AMY2A, KLRC4 → suspected tech noise |
| C28 | C28 (kept) | 0 | HMX2, CT47A7 (only 3 markers) → low confidence |
| C29 | C29 (kept) | 0 | no markers (1) → low confidence |
| C30 | ODC | 13.5 | OPALIN, MAG, KLK6, MCAM, TMEM31, VWA1 |

C24/C27 absent from marker list (marker list has groups 1-23,25,26,28,29,30 — no 24/27).

## Why ExN clusters keep original names
C17-19 hit ExN_common strongly (score 15-17) but have NO subregion markers (PROX1=DG,
SSTR2/WFS1=CA1_SUB, FEZF2 alone insufficient for EC). Monkey subclasses DG Ex / CA1_SUB s.f. Ex /
CA2_4 EX / EC L2/L3_5/L6 EX cannot be assigned without subregion evidence → keep `Cxx (ExN)`,
align at broad ExN level for cross-species comparison.

## Debate verdict (L1, budget-limited)
Verdict `need_more_info` (low confidence): judges accepted the conservative keep-original-name
strategy but flagged (1) unannotated low-confidence clusters (C13/25/26/28/29) should be further
validated; (2) cross-species granularity mismatch (monkey EC/CA subclasses vs broad human ExN) is
unavoidable at ATAC resolution. Pro side repeatedly recommended AUCell/AddModuleScore validation
(AUC>0.6, marker pct>0.5) for low-confidence groups as follow-up.

## Artifacts
- `task4/human_subcluster_annotation_final.csv` — final table with evidence (27 clusters)
- `task4/marker_scoring_matrix.csv` — per-cluster best/second score + hit genes (audit trail)
- `scripts/annotate_human_30clusters.py` — dictionary-scoring script (reproducible)
- `E:/专利/patent/human_subcluster_annotation_aligned.csv` — earlier 8-class/rough version (superseded)