# Error Log

> Errors and fixes accumulated from actual analysis runs.
> Each entry helps future runs avoid the same issues.

| Date | Error | Type | Cause | Fix | Species | Tissue | Severity |
|------|-------|------|-------|-----|---------|--------|----------|
| 2026-08-30 21:59 | rtracklayer readBigWig fails on Windows: UCSC library operation failed | missing_package | rtracklayer 在 Windows 上依赖 UCSC kent library 的本地编译组件，Windows/ | 放弃 rtracklayer 读 bigWig，改用 conda-forge 安装 pybigwig（有 Windows |  |  | high |
