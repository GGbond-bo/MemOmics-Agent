# ATAC-seq QC Guidelines

## Cell-Level QC Thresholds (per knowledge base)

| Metric | Pass | Borderline | Fail |
|--------|------|------------|------|
| TSS enrichment | >8 | 4-8 | <4 |
| Fragments per cell | 1000-100000 | 500-1000 | <500 |
| FRiP (reads in peaks) | >0.15 | 0.05-0.15 | <0.05 |
| Blacklist ratio | <0.05 | 0.05-0.10 | >0.10 |
| Nucleosome signal | <2 | 2-4 | >4 |

## Doublet Detection
- Method: ArchR doublet enrichment
- Rate: 0.08 (8%) for snATAC muscle
- Always filter doublets before clustering

## Sample-Level QC
- Check per-sample TSS distribution (ridges plot)
- Remove samples with median TSS < 4
- Check fragment size periodicity (~200bp nucleosome)

## Tissue-Specific Notes (Skeletal Muscle)
- snATAC-seq preferred (muscle is hard to dissociate)
- Myonuclei are large; expect higher fragment counts
- Aging samples may have lower quality — adjust thresholds
