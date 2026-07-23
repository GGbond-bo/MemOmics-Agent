# Error Log

> Errors and fixes accumulated from actual analysis runs.
> Each entry helps future runs avoid the same issues.

| Date | Error | Type | Cause | Fix | Species | Tissue | Severity |
|------|-------|------|-------|-----|---------|--------|----------|
| 2026-07-12 21:23 | there is no package called 'MAST' | PackageNotFoundError | MAST not installed in R environment | install.packages('BiocManager'); BiocManager::install('MAST' | Homo sapiens | heart | medium |
| 2026-07-12 21:26 | there is no package called 'MAST'... | PackageNotFoundError | *(recurrence)* | install.packages('BiocManager'); BiocMan | Homo sapiens | heart | medium |
| 2026-07-12 21:27 | there is no package called 'MAST'... | PackageNotFoundError | *(recurrence)* | install.packages('BiocManager'); BiocMan | Homo sapiens | heart | medium |
