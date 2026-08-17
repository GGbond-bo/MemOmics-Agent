# Public Data Sources: Human & Monkey Brain CRE

## Human Brain Regulatory Data

### ATAC-seq / DNase-seq
| Accession | Description | Brain Region | Source |
|-----------|-------------|--------------|--------|
| ENCODE (various) | Bulk ATAC-seq, multiple brain regions | Cortex, hippocampus, cerebellum | encodeproject.org |
| PsychENCODE | snATAC-seq, prefrontal cortex | PFC | psychencode.org |
| GSE278576 | snRNA-seq + snATAC-seq, 40 donors, lifespan | Hippocampus | GEO (PMID: 39463924) |
| Roadmap Epigenomics | DNase-seq, multiple brain regions | Whole brain, hippocampus | roadmapepigenomics.org |

### ChIP-seq (Histone Marks)
| Accession | Mark | Brain Region | Source |
|-----------|------|--------------|--------|
| ENCODE | H3K27ac | Multiple brain regions | encodeproject.org |
| ENCODE | H3K4me3 | Multiple brain regions | encodeproject.org |
| ENCODE | CTCF | Multiple brain regions | encodeproject.org |
| PsychENCODE | H3K27ac | Prefrontal cortex | psychencode.org |

### Hi-C / 3D Genome
| Accession | Resolution | Brain Region | Source |
|-----------|------------|--------------|--------|
| PsychENCODE | 5-10kb | Hippocampus, PFC, temporal cortex | psychencode.org |
| ENCODE | 5kb | Multiple tissues | encodeproject.org |

### RNA-seq
| Accession | Description | Source |
|-----------|-------------|--------|
| GTEx v8/v9 | Bulk RNA-seq, 13+ brain regions, hundreds of donors | gtexportal.org |
| PsychENCODE | snRNA-seq | psychencode.org |

## Monkey Brain Regulatory Data

### ATAC-seq
| Accession | Description | Brain Region | Source |
|-----------|-------------|--------------|--------|
| Meng 2026 (Nat Commun) | snATAC-seq, rhesus macaque cortex | Cortex | GEO (search: "macaque cortex ATAC-seq Meng") |
| Monkey Brain Epigenome Project | ATAC-seq, multiple regions | Multiple | TBD |

### ChIP-seq
| Accession | Mark | Brain Region | Source |
|-----------|------|--------------|--------|
| Monkey Brain Epigenome Project | H3K27ac, H3K4me3, CTCF | Multiple | TBD (check ENCODE for macaque entries) |

### Hi-C
| Accession | Description | Source |
|-----------|-------------|--------|
| Luo 2020 (Cell) | Rhesus hippocampus 3D genome | GEO |

### RNA-seq
| Accession | Description | Source |
|-----------|-------------|--------|
| Macaque brain transcriptome atlas | Multiple brain regions | GEO / SRA |

## Cross-Species Resources

| Resource | URL | What It Provides |
|----------|-----|-----------------|
| UCSC LiftOver chains | hgdownload.soe.ucsc.edu | hg38↔rheMac10 coordinate conversion |
| UCSC phastCons 100-way | genome.ucsc.edu | Pre-computed conservation scores |
| UCSC GERP | genome.ucsc.edu | Pre-computed constraint scores |
| Ensembl Compara | ensembl.org | Ortholog gene mappings (human↔macaque) |
| JASPAR | jaspar.genereg.net | TF binding motif matrices for FIMO scanning |

## Priority Download Order

```
Priority 1 (MUST — L1):
  [ ] Human brain ATAC-seq peaks (ENCODE)
  [ ] Macaque brain ATAC-seq peaks (Meng 2026)
  [ ] hg38↔rheMac10 LiftOver chain files (UCSC)

Priority 2 (RECOMMENDED — L2):
  [ ] Human brain H3K27ac bigWig (ENCODE)
  [ ] Macaque brain H3K27ac bigWig
  [ ] phastCons100way bigWig (UCSC)

Priority 3 (NICE-TO-HAVE — L3/L4):
  [ ] Human brain Hi-C (PsychENCODE)
  [ ] Macaque brain Hi-C (Luo 2020)
  [ ] Human brain RNA-seq (GTEx)
  [ ] Macaque brain RNA-seq
```
