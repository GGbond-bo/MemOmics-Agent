# Error Log

> Errors and fixes accumulated from actual analysis runs.
> Each entry helps future runs avoid the same issues.

| Date | Error | Type | Cause | Fix | Species | Tissue | Severity |
|------|-------|------|-------|-----|---------|--------|----------|
| 2026-07-12 21:23 | Cannot allocate vector of size 8.0 Gb | MemoryError | SCTransform on full dataset exceeded memory limit | Use SCTransform with conserve.memory=TRUE and downsample to  | Homo sapiens | heart | high |
| 2026-07-12 21:23 | SCTransform model failed to converge for 342 genes | ConvergenceError | Too many cells with zero counts in genes | Use glmGamPoi backend: SCTransform(..., method='glmGamPoi') | Homo sapiens | heart | medium |
| 2026-07-12 21:23 | SCTransform on 150K cells crashed with glmGamPoi | MemoryError | glmGamPoi version 1.8 incompatible with Matrix 1.6 | Downgrade glmGamPoi to 1.6.0 + conserve.memory=TRUE (from qu | Homo sapiens | heart | low |
| 2026-07-12 21:26 | Cannot allocate vector of size 8.0 Gb... | MemoryError | *(recurrence)* | Use SCTransform with conserve.memory=TRU | Homo sapiens | heart | high |
| 2026-07-12 21:26 | SCTransform model failed to converge for 342 genes... | ConvergenceError | *(recurrence)* | Use glmGamPoi backend: SCTransform(...,  | Homo sapiens | heart | medium |
| 2026-07-12 21:26 | SCTransform on 150K cells crashed with glmGamPoi... | MemoryError | *(recurrence)* | Downgrade glmGamPoi to 1.6.0 + conserve. | Homo sapiens | heart | low |
| 2026-07-12 21:27 | Cannot allocate vector of size 8.0 Gb... | MemoryError | *(recurrence)* | Use SCTransform with conserve.memory=TRU | Homo sapiens | heart | high |
| 2026-07-12 21:27 | SCTransform model failed to converge for 342 genes... | ConvergenceError | *(recurrence)* | Use glmGamPoi backend: SCTransform(...,  | Homo sapiens | heart | medium |
| 2026-07-12 21:27 | SCTransform on 150K cells crashed with glmGamPoi... | MemoryError | *(recurrence)* | Downgrade glmGamPoi to 1.6.0 + conserve. | Homo sapiens | heart | low |
