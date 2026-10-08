# CRISPick Dataset File Format

CRISPick (Broad Institute Genetic Perturbation Platform) publishes genome-wide precomputed
sgRNA designs. The bundled `resource/CRISPick_download_links.txt` lists 238 URLs covering
13 organisms and 4 Cas enzymes. These are NOT bundled (50–700 MB each); download on demand.

## File naming convention

```
sgRNA_design_{TAXID}_{GENOME}_{CAS}_{APPLICATION}_{ALGORITHM}_{SOURCE}_{DATE}.txt.gz
```

| Component   | Examples | Notes |
|-------------|----------|-------|
| TAXID       | `9606` (human), `10090` (mouse), `10116` (rat), `9615` (dog), `9913` (cow), `9544` (monkey), `7227` (fly) | NCBI taxonomy ID |
| GENOME      | `GRCh38`, `GRCh37`, `GRCm38` | reference build |
| CAS         | `SpyoCas9`, `SaurCas9`, `AsCas12a`, `enAsCas12a` | enzyme (see PAM table) |
| APPLICATION | `CRISPRko`, `CRISPRa`, `CRISPRi` | knockout / activation / inhibition |
| ALGORITHM   | `RS3seq-Chen2013+RS3target`, `Azimuth_2.0`, `Seq-DeepCpf1`, `enPAM+GB` | scoring model |
| SOURCE      | `NCBI`, `Ensembl` | gene model source |

Each dataset has a companion `.summary.txt` (1–3 MB). `find_crispick_dataset.py` returns the
full `.txt.gz` by default.

## Enzyme / PAM reference

| Cas enzyme  | File token   | PAM      | PAM location | sgRNA length |
|-------------|--------------|----------|--------------|--------------|
| SpCas9      | `SpyoCas9`   | NGG      | 3' of target | 20 bp |
| SaCas9      | `SaurCas9`   | NNGRRT   | 3' of target | 20–21 bp |
| AsCas12a    | `AsCas12a`   | TTTV     | 5' of target | 23–25 bp |
| enAsCas12a  | `enAsCas12a` | TTTV     | 5' of target | 23–25 bp |

**CRITICAL:** AsCas12a (wild-type) and enAsCas12a (enhanced) are DIFFERENT enzymes. Guides
designed for one may not work with the other. `find_crispick_dataset.py` matches the exact
enzyme token so the two never cross-contaminate, and emits a warning when either is requested.

## Column reference

The `.txt` is tab-delimited. **Column names differ between real CRISPick exports and the
abbreviated names shown in some examples.** `select_crispick_sgrnas.py` resolves each logical
field against the alias lists below, so it works on either layout. If a download uses a name
not listed here, the selector raises an error listing the available columns (add the alias to
`COLUMN_ALIASES` in `select_crispick_sgrnas.py`).

### Fields present in all datasets
| Logical field | Real CRISPick name | Alternate names seen | Meaning |
|---------------|--------------------|----------------------|---------|
| gene          | `Target Gene Symbol` | `Gene_Symbol`, `Gene Symbol` | gene the guide targets |
| sequence      | `sgRNA Sequence`     | `sgRNA_sequence` | 20 bp guide (5'→3') |
| combined rank | `Combined Rank`      | `Combined_Rank`, `Pick Order` | overall rank, **lower = better** (default) |
| on-target rank| `On-Target Rank`     | `On_Target_Rank` | efficiency-only rank, lower = better |
| off-target rank| `Off-Target Rank`   | `Off_Target_Rank` | specificity-only rank, lower = better |
| PAM           | `PAM Sequence`       | `PAM` | the PAM (e.g. AGG, TGG) |

When rank columns are absent, the selector falls back to score columns (higher = better):
`On-Target Efficacy Score` / `sgRNA_score`, `Off-Target Stringency` / `Off_target_stringency`.

### Knockout-specific
| Logical field | Real name | Meaning |
|---------------|-----------|---------|
| exon          | `Exon Number` (`Exon_ID`) | which exon is targeted |
| cut position  | `sgRNA Cut Position (1-based)` | genomic coordinate of cut |
| target cut %  | `Target Cut %` | % of protein N-terminal to the cut (lower = earlier = usually better KO) |

### Activation / inhibition-specific
| Logical field | Real name | Meaning |
|---------------|-----------|---------|
| TSS offset    | `sgRNA 'Cut' Site TSS Offset` | distance from transcription start site (bp) |
| DHS score     | `DHS Score` | DNase-hypersensitivity score (CRISPRa relevance) |

## Selection guidance (matches the source guide)
- **Default:** rank by **Combined Rank** (balances efficiency + specificity).
- Prioritize **On-Target Rank** for maximum cutting efficiency; **Off-Target Rank** for maximum specificity.
- **Knockout:** prefer early exons / low `Target Cut %` (first ~50% of the protein).
- Pick **3–4 guides**, ideally spread across distinct exons for redundancy.
