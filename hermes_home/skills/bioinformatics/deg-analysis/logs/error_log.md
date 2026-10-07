# Error Log

> Errors and fixes accumulated from actual analysis runs.
> Each entry helps future runs avoid the same issues.

| Date | Error | Type | Cause | Fix | Species | Tissue | Severity |
|------|-------|------|-------|-----|---------|--------|----------|
| 2026-07-12 21:23 | there is no package called 'MAST' | PackageNotFoundError | MAST not installed in R environment | install.packages('BiocManager'); BiocManager::install('MAST' | Homo sapiens | heart | medium |
| 2026-07-12 21:26 | there is no package called 'MAST'... | PackageNotFoundError | *(recurrence)* | install.packages('BiocManager'); BiocMan | Homo sapiens | heart | medium |
| 2026-07-12 21:27 | there is no package called 'MAST'... | PackageNotFoundError | *(recurrence)* | install.packages('BiocManager'); BiocMan | Homo sapiens | heart | medium |
| 2026-09-24 16:27 | unused argument (compression = "none") — ggsave 在 for 循环里对 png 设备传了 compression= | runtime_error | ggsave 的 compression 参数按设备分发，png 设备不接受该参数（仅 tiff/其他支持） | 拆开三次 ggsave 调用：png/pdf 不传 compression，tiff 传 compression="lz |  |  | low |
| 2026-09-24 18:04 | variables in design formula cannot contain NA: type (DESeq2 DESeqDataSetFromMatr | logic_error | pseudobulk 聚合列名（colnames(pb)）与 sub$samplename 的匹配未命中原样本名 → m | 待修:pseudobulk meta$type 由 sub$type[match(colnames(pb), sub$s |  |  | medium |
| 2026-09-26 02:21 | error in evaluating the argument 'X' in selecting a method for function 'lapply' | logic_error | split() 的分组变量为 NULL —— 想当然假设 meta 里有 individual 列 | MF_subset_2000.rds 的 meta.data 不含 individual 列（只有 samplename | human | skeletal_muscle | medium |
