# CoVarNet — Cell-Type Coordination Modules (Nature 2025, Zhang Zemin lab)

## Reference
- Shi Q, Chen Y, Li Y, ... Zhang Z. **Cross-tissue multicellular coordination and its rewiring in cancer.** *Nature* 643:529-539, 2025. DOI 10.1038/s41586-025-09053-4, PMID 40437094. Open access PMC12240829. Online resource: http://cm.cancer-pku.cn

## Core algorithm (CoVarNet)
1. **Input**: cell-subtype abundance frequency matrix (sample × subset)
2. **Pearson correlation matrix R** + specificity index: `Cutoff(n,N) = 1 − (n−1)×2/((N−1)×2−1)`
3. **NMF decomposition** (k=12; cophenetic correlation for rank selection; 30-run consensus)
4. **CM network**: top subtypes as nodes, specific correlated pairs as edges; 10,000-node permutation test for significance

Key property: captures BOTH local (spatial adjacency) and distal (systemic) multicellular coordination — pure data-driven, no ligand-receptor prior.

## Findings
- **12 CMs across 35 tissues** (33 datasets / 26 cohorts); CM02/03 = gut mucosa immunity, CM05 = Peyer's patch, CM08 = skin fibroblast+vessel, CM12 = breast (fibroblast S06/S09/S10 + immune + venous endothelium)
- **Validation chain**: CellCharter spatial niches → Xenium high-res → CellPhoneDB CCI enrichment inside CMs → GTEx bulk RNA-seq (12,240 samples × 23 tissues) independent verification
- **Aging**: spleen CM05 (naive B/T) activity ↓ with age (KW P=0.00028); CM06 (memory/effector) ↑ (P=6e-4); convergent regulons NR4A1/NR4A2 core drivers
- **Menopause**: breast CM12 activity ↓ after menopause (P=0.022); fibroblast subsets decline sequentially (S10 → S06); inflammation genes ↓
- **Cancer rewiring (two simultaneous rewires)**:
  1. Tissue-specific healthy CMs collapse in tumor (e.g. CRC CM03, P<2.2e-16)
  2. Convergent cancer ecosystem **cCM02** in 8 cancer types (CRC/KIRC/HCC/LUAD/HNSC/OV/cSCC/CESC): TAM(Mph_C1QC/SPP1) + Tex(CD8T07/CD4T09_CXCL13) + ISG15+ stress cells + myCAF/iCAF/apCAF + LAMP3+ cDC. cCM02 ↑ in tumor vs adjacent (P=1.1e-11~7.2e-13); higher activity = worse prognosis.

## Reuse for muscle fiber F5 upgrade
- Matrix = MF subtype (or MF+immune+MuSC) abundance × sample → NMF → coordination modules
- Question: do denervation-slow myofiber + Schwann cells + specific immune cells form a CM that rises with aging? → "denervation ecosystem" story
- CoVarNet logic is the F5 upgrade path (Zhang Zemin's answer to CellChat's ligand-receptor limitation). Do NOT put in F2 — F2 gene programs use NMF/cNMF (see main SKILL.md).

## Method params reusable elsewhere
- NMF rank selection: cophenetic correlation, 30 runs consensus
- Specificity cutoff formula above
- Module significance: 10,000 node permutations
- Regulon analysis: SCENIC convergent regulons
