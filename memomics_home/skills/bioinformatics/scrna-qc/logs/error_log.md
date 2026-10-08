# Error Log

> Errors and fixes accumulated from actual analysis runs.
> Each entry helps future runs avoid the same issues.

| Date | Error | Type | Cause | Fix | Species | Tissue | Severity |
|------|-------|------|-------|-----|---------|--------|----------|
| 2026-07-04 02:44 | sc.pp.filter_genes() → anndata copy() → numpy._ArrayMemoryError: Unable to alloc | memory | sc.pp.filter_genes internally calls .copy() which creates a  | Replace sc.pp.filter_genes() with inplace: gene_counts = (ad | human | skeletal_muscle | medium |
