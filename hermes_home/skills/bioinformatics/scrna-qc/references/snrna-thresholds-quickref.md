# snRNA-seq vs scRNA-seq QC Threshold Quick Reference

## Key Distinction

| Feature | scRNA-seq | snRNA-seq |
|---------|-----------|-----------|
| MT% median | 5-15% | 0.2-1.0% |
| MT% max (healthy) | 15-25% | 3-5% |
| **max_pct_mt threshold** | **15-20%** | **5%** |
| nCount median | 2,000-10,000 | 1,000-5,000 |
| min_counts | 500 | 1,000 |

## Detection: Is this snRNA-seq?

Check `median(percent.mt)`:
- If < 1% → **snRNA-seq** (single-nucleus)
- If > 5% → scRNA-seq (single-cell)
- If 1-5% → ambiguous, check data source metadata

## Why This Matters

Using scRNA-seq thresholds (MT%<15%) on snRNA-seq data is useless —
the maximum MT% in snRNA-seq is typically 3-5%, so the 15% threshold
filters nothing. Conversely, using MAD on MT% for snRNA-seq creates
sub-1% thresholds that flag healthy cells as outliers.

## Session Reference (2026-07-02)

Human skeletal muscle snRNA-seq, 40K cells:
- MT% median: 0.28%, max: 4.99%
- Used MT%<5% fixed threshold
- Excluded MT% from MAD metrics
- Result: 0.02% cells removed by fixed thresholds (normal for pre-filtered data)

See also: `references/snrna_qc_pitfalls.md` for detailed MAD filtering analysis.