# Error Log

> Errors and fixes accumulated from actual analysis runs.
> Each entry helps future runs avoid the same issues.

| Date | Error | Type | Cause | Fix | Species | Tissue | Severity |
|------|-------|------|-------|-----|---------|--------|----------|
| 2026-07-04 04:09 | RunHarmony with sample_id (16,003 unique) → 1 iteration convergence (pseudo-conv | logic_error | sample_id had 16,003 unique values (individual cell barcodes | Switch batch variable from sample_id to donor_id (19 donors) | human | skeletal_muscle | high |
