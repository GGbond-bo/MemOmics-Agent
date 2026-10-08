# GSE278576 Human Hippocampus ATAC Metadata

## Discovery (2026-08-27)

Zemke 2024 (Science) provides cell type annotations in GEO supplementary materials.

## Key Files

| File | Description |
|------|-------------|
| `GSE278576_human_hippocampus_cell_metadata.txt.gz` | Cell metadata with `cell_type` column (18 types) |
| `GSE278576_human_hippocampus_gene_activity_matrix.mtx.gz` | Gene activity matrix |
| `GSE278576_human_hippocampus_peak_matrix.mtx.gz` | Peak matrix |

## Cell Types (18)

From the metadata file:
- Oligodendrocyte (95,447 cells, 35.9%)
- ExN (52,319, 19.7%)
- Astrocyte (27,738, 10.4%)
- InN (24,xxx)
- Microglia
- OPC
- Endothelial
- Pericyte
- etc.

## Lesson

**ALWAYS check GEO supplementary materials for existing annotations before doing custom annotation.**
The original paper may already have detailed cell type annotations that are more reliable than marker-based re-annotation.

## Download Command

```bash
# Download metadata
curl -L "https://ftp.ncbi.nlm.nih.gov/geo/series/GSE278nnn/GSE278576/suppl/GSE278576_human_hippocampus_cell_metadata.txt.gz" -o metadata.txt.gz
gunzip metadata.txt.gz
```

---

# AGE COLUMN AVAILABILITY (2026-08-27) — CRITICAL for species×age patent analysis

## Species age-info status at a glance

| Species | rds | Age column in rds? | Where donor→age lives | Ready for species×age model? |
|---------|-----|---------------------|------------------------|------------------------------|
| **Monkey (张潇)** | `E:/专利/patent/monkey_Hf_ATAC_final.rds` | ✅ YES (`Age` + `Age_group`) | In the rds directly | ✅ Read from rds, no external lookup |
| **Human (Zemke GSE278576)** | `E:/专利/patent/human_Hf_ATAC_40_clustered.rds` | ❌ NO Age column | NOT in GEO series matrix; donor→age mapping is in the article's supplementary metadata | ❌ Needs external donor-age table |

## Monkey age details (from rds cellColData, verified 2026-08-27)

- **Sample column format**: `M1_Hip_1..4` / `O1_Hip_1..4` (M=Middle, O=Old, plus Young/Exceptionally old) — 63 libraries
- **21 individuals**, 63 samples
- **Age values present**: 5, 10, 11, 12, 22, 23, 28, 29, 31
- **Age_group present**: Young / Middle / Old / Exceptionally old
  - Youth (39,699) / Middle (38,875) / Old (45,884) / Young (38,039)
- Use `Age_group` for species×age categorical model — already 4 balanced groups, ready to run.

## Human age details (verified 2026-08-27)

- **Sample column**: 40 values `GSM8549615_hc77` … `GSM8549654_hc9` (GSM + donor id hcXX). 40 samples.
- **rds cellColData columns**: Sample, TSSEnrichment, ReadsInTSS, ReadsInPromoter, ReadsInBlacklist, PromoterRatio, PassQC, NucleosomeRatio, nMultiFrags, nMonoFrags, nFrags, nDiFrags, DoubletScore, DoubletEnrichment, BlacklistRatio, Clusters — **NO Age / Age_group / Individual column**.
- **GEO series matrix** (`GSE278576_series_matrix.txt.gz`) characteristics only contain: `tissue: hippocampus` + `donor id: hcXX`. **No age field.**
- **GEO suppl cell-metadata file 404'd** in this environment (`GSE278576_human_hippocampus_cell_metadata.txt.gz` → HTTP 404); article pages (bioRxiv/PubMed) returned 403/429 (bot blocks).
- The dataset is **"40 neurotypical human donors spanning the adult lifespan"** (per GSE abstract) — age is continuous across adulthood, but the **donor→age lookup table is NOT in GEO series matrix**; it lives in the Zemke 2024 article supplementary metadata (PMID 39463924).

## Practical implication (patent species×age analysis)

- **Monkey side**: species×age model fully constructible from rds alone (`Age_group`).
- **Human side**: BLOCKED on donor→age mapping unless the user supplies the Zemke supplementary donor-age table. If they can't, options:
  1. Ask user for the article's donor-age supplementary table.
  2. Drop the interaction term and model **species main effect only** (does not need human age).
  3. Infer human age bins from the paper's described adult-lifespan sampling — but do NOT fabricate exact ages ("一定要有依据").
