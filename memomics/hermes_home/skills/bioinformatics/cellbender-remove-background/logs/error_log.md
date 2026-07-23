# Error Log

> Errors and fixes accumulated from actual analysis runs.
> Each entry helps future runs avoid the same issues.

| Date | Error | Type | Cause | Fix | Species | Tissue | Severity |
|------|-------|------|-------|-----|---------|--------|----------|
| 2026-07-04 22:01 | CRR278962 启动后卡在 epoch 1/150，loss 不动，没有进度 | environment | PYTHONPATH 环境变量污染，导致 cellbender 加载了错误的 Python 模块路径 | unset PYTHONPATH 后重新启动，正常运行 | 猕猴 | 大脑 | medium |
