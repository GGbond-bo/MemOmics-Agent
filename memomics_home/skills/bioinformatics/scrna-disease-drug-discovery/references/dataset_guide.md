# GSE195452 Dataset Guide

## Dataset Overview

- **GEO Accession:** GSE195452
- **Platform:** 10X Chromium 3' scRNA-seq
- **Organism:** Homo sapiens
- **Tissue:** Skin biopsies (forearm)
- **Conditions:** Diffuse SSc (dcSSc), Limited SSc (lcSSc), Healthy controls

## Expected Cell Types

Based on skin biopsy scRNA-seq from SSc studies:
- Fibroblasts (multiple subtypes: SFRP2+, CTHRC1+, APOE+, myofibroblast)
- Keratinocytes (basal, suprabasal, differentiated)
- Endothelial cells
- Macrophages/Monocytes
- T cells (CD4+, CD8+, Treg)
- Dendritic cells (cDC, pDC)
- B cells / Plasma cells
- Smooth muscle cells / Pericytes
- Melanocytes

## Expected Results for Validation

### Differential Expression
- **Fibroblasts:** COL1A1, COL3A1, COL5A1, FN1, CTGF (CCN2), ACTA2, POSTN upregulated in SSc
- **Macrophages:** SPP1, TGFB1, CCL18, CD163, MRC1 upregulated (M2 polarization)
- **T cells:** Th2 signature (IL4, IL13, GATA3) and/or Th17 signature (IL17A, RORC)
- **Endothelial:** Signs of EndoMT (decreased PECAM1/CD31, increased ACTA2)

### Pathway Enrichment
- TGF-beta signaling (enriched in fibroblasts)
- ECM-receptor interaction (enriched in fibroblasts)
- Wnt signaling (enriched in fibroblasts, macrophages)
- Inflammatory response (enriched in macrophages, T cells)
- Interferon signaling (enriched in DCs, some fibroblasts)
- IL-4/IL-13 signaling (enriched in macrophages)

### Ligand-Receptor Interactions
- TGFB1 (macrophage) - TGFBR1/2 (fibroblast): primary fibrotic axis
- PDGFB (endothelial/macrophage) - PDGFRA (fibroblast): proliferation
- CCL2 (fibroblast) - CCR2 (monocyte): immune recruitment
- IL13 (T cell) - IL13RA1 (fibroblast/macrophage): Th2-driven fibrosis

### High-Priority Targets (Expected)
These known SSc-relevant genes should score high in multi-omics scoring:
- **TGFBR1/TGFBR2:** Central to TGF-beta-driven fibrosis
- **PDGFRA:** Nintedanib target, fibroblast proliferation
- **IL6R:** Tocilizumab target, inflammatory signaling
- **JAK1/JAK2:** Tofacitinib target, JAK-STAT signaling
- **IL13RA1/IL4R:** Th2 cytokine receptors
- **EDNRA:** Endothelin receptor, bosentan target
