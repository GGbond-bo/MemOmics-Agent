# Error Log

> Errors and fixes accumulated from actual analysis runs.
> Each entry helps future runs avoid the same issues.

| Date | Error | Type | Cause | Fix | Species | Tissue | Severity |
|------|-------|------|-------|-----|---------|--------|----------|
| 2026-08-01 02:08 | hdWGCNA/WGCNA 在 MF 亚群数据上拆不出模块：soft threshold R2 最高 0.72（power=1，未达 0.8 标准），3000  | logic_error | MF（终末分化肌纤维）的转录程序高度协调——慢肌/快肌/代谢基因共享一个主轴，共表达网络不满足 scale-free 假 | 改用 NMF（RcppML/nmf 包）做基因程序分解——已在同数据上成功拆出 6 个程序（快肌 P1/慢肌 P2/RS | human | skeletal_muscle | medium |
