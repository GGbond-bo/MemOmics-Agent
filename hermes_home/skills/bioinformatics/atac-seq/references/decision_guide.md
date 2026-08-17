# ATAC-seq Analysis Decision Guide

## scATAC vs Bulk ATAC
| Scenario | Use |
|----------|-----|
| Single-cell resolution needed | scATAC (ArchR/Signac) |
| Population-level peaks | Bulk ATAC (MACS2) |

## ArchR vs Signac
| Feature | ArchR | Signac |
|---------|-------|--------|
| Scale | >100K cells | <100K cells |
| Peak calling | Built-in MACS2 | External |
| Memory | Arrow files (disk) | In-memory |
| Multiome | Via Seurat | Native WNN |
| Recommendation | Large-scale scATAC | Small-scale or Multiome |

## Key Parameter Decisions

### TSS Enrichment Cutoff
- **Conservative**: >8 (ArchR default)
- **Standard**: >4 (include more cells)
- **Decision**: Use 8 for muscle (high quality required)

### Resolution
- **0.4-0.6**: Broad cell types (e.g. myonuclei vs FAP vs EC)
- **0.8-1.2**: Subtypes (e.g. TypeI vs TypeII myonuclei) — KB recommended for muscle
- **>1.2**: Very fine subclusters (risky, may be noise)

### IterativeLSI Components
- **20-30**: Standard (30 recommended for muscle)
- **>40**: Risk over-fitting technical noise

## Literature Sources
- ArchR: Granja et al., 2021, Nature Genetics
- Signac: Stuart et al., 2021, Nature Methods
- MACS2: Zhang et al., 2008, Genome Biology
- chromVAR: Schep et al., 2017, Nature Methods
- Muscle snATAC: Dos Santos et al., 2025, Cell Rep (PMID: 40632651)
