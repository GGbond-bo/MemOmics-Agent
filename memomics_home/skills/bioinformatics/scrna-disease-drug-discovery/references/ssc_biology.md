# Systemic Sclerosis (SSc) Disease Context

## Disease Overview

Systemic sclerosis (SSc, also known as scleroderma) is a chronic autoimmune connective tissue disease characterized by a triad of:
1. **Vascular damage** -- endothelial cell injury and dysfunction
2. **Immune dysregulation** -- autoimmune activation with fibrotic cytokine production
3. **Fibrosis** -- excessive collagen deposition in skin and internal organs

## Clinical Subtypes

- **Diffuse cutaneous SSc (dcSSc)** -- rapid onset, widespread skin fibrosis, higher risk of organ involvement (lung, heart, kidney)
- **Limited cutaneous SSc (lcSSc)** -- slower progression, skin fibrosis limited to extremities, associated with pulmonary arterial hypertension

## Key Cell Types in SSc Pathogenesis

| Cell Type | Role in SSc | Expected DE Signature |
|-----------|-------------|----------------------|
| **Myofibroblasts** | Primary effector of fibrosis. Secrete excessive collagen and ECM. Activated by TGF-beta, PDGF, endothelin. | COL1A1, COL3A1, ACTA2, FN1, CTGF upregulated |
| **Fibroblasts** | Precursors to myofibroblasts. Heterogeneous subtypes with varying pro-fibrotic potential. | Subtype-specific: SFRP2+, CTHRC1+, APOE+ subtypes |
| **Macrophages** | Pro-fibrotic (M2) macrophages secrete TGF-beta, IL-13, PDGF. Drive fibroblast activation. | SPP1, TGFB1, CCL18, CD163 upregulated |
| **T cells (Th2/Th17)** | Th2 cells produce IL-4, IL-13 (pro-fibrotic). Th17 produces IL-17 (inflammatory). | IL4, IL13, IL17A, GATA3 |
| **Endothelial cells** | Early vascular damage. Endothelial-to-mesenchymal transition (EndoMT) contributes to fibrosis. | VWF, PECAM1, loss of CD31, gain of ACTA2 |
| **Dendritic cells** | Antigen presentation, type I interferon production. | IFN signature, plasmacytoid DC markers |
| **B/Plasma cells** | Autoantibody production (anti-topo I, anti-centromere). | Immunoglobulin genes |
| **Keratinocytes** | Skin barrier dysfunction, paracrine signaling to fibroblasts. | KRT genes, barrier genes |

## Key Signaling Pathways

| Pathway | Role | Key Genes |
|---------|------|-----------|
| **TGF-beta/SMAD** | Master regulator of fibrosis. TGF-beta1 from macrophages/platelets activates fibroblasts via SMAD2/3. | TGFB1, TGFBR1, TGFBR2, SMAD2, SMAD3, SMAD7 |
| **Wnt/beta-catenin** | Pro-fibrotic, synergizes with TGF-beta. WNT5A particularly relevant. | WNT5A, WNT3A, FZD1, FZD2, CTNNB1, AXIN2 |
| **PDGF signaling** | Fibroblast proliferation and migration. PDGF-BB from platelets/macrophages. | PDGFB, PDGFA, PDGFRA, PDGFRB |
| **IL-4/IL-13** | Th2 cytokines drive M2 macrophage polarization and fibroblast activation. | IL4, IL13, IL4R, IL13RA1, STAT6 |
| **IL-6/JAK-STAT** | Pro-inflammatory and pro-fibrotic. Elevated in SSc serum. Tocilizumab target. | IL6, IL6R, IL6ST, JAK1, JAK2, STAT3 |
| **Endothelin** | Vasoconstriction and pro-fibrotic. Bosentan target. | EDN1, EDNRA, EDNRB |
| **Notch** | Fibroblast differentiation, EndoMT. | NOTCH1, NOTCH3, JAG1, HES1 |
| **Interferon** | Type I IFN signature common in early SSc. | IFNA, IFNB, MX1, ISG15, IFI44L |

## Key Ligand-Receptor Interactions

| L-R Pair | Source Cell | Target Cell | Significance |
|----------|------------|-------------|--------------|
| TGFB1 - TGFBR1/2 | Macrophage | Fibroblast | Primary fibrotic axis |
| PDGFB - PDGFRA | Macrophage/Endothelial | Fibroblast | Fibroblast proliferation |
| IL13 - IL13RA1 | Th2 cell | Fibroblast/Macrophage | Th2-driven fibrosis |
| CCL2 - CCR2 | Fibroblast | Monocyte | Monocyte recruitment |
| CXCL12 - CXCR4 | Endothelial | T cell/Monocyte | Immune cell homing |
| EDN1 - EDNRA | Endothelial | Smooth muscle/Fibroblast | Vasoconstriction + fibrosis |
| WNT5A - FZD2 | Macrophage | Fibroblast | Non-canonical Wnt fibrosis |

## Approved and Investigational Therapies

| Drug | Target | Modality | Indication | Status |
|------|--------|----------|------------|--------|
| Nintedanib | PDGFR/FGFR/VEGFR | Small molecule TKI | SSc-ILD | Approved |
| Tocilizumab | IL-6R | Monoclonal antibody | SSc (skin) | Approved |
| Rituximab | CD20 | Monoclonal antibody | SSc (off-label) | Phase 3 |
| Bosentan | EDNRA/B | Small molecule | PAH in SSc | Approved |
| Pirfenidone | TGF-beta (indirect) | Small molecule | SSc-ILD (investigational) | Phase 2 |
| Tofacitinib | JAK1/3 | Small molecule | SSc (investigational) | Phase 2 |
| Romilkimab | IL-4/IL-13 | Bispecific antibody | SSc (investigational) | Phase 2 |

## GSE195452 Dataset

- **Platform:** 10X Chromium scRNA-seq
- **Tissue:** Skin biopsies (forearm)
- **Conditions:** Diffuse SSc, Limited SSc, Healthy controls
- **Expected cell types:** Fibroblasts (multiple subtypes), keratinocytes, endothelial cells, macrophages, T cells, DCs, B cells, smooth muscle cells, pericytes
- **Key findings to validate:** Pro-fibrotic fibroblast subtypes, macrophage-fibroblast TGF-beta signaling, Th2/Th17 immune activation
