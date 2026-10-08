# Error Log

> Errors and fixes accumulated from actual analysis runs.
> Each entry helps future runs avoid the same issues.

| Date | Error | Type | Cause | Fix | Species | Tissue | Severity |
|------|-------|------|-------|-----|---------|--------|----------|
| 2026-07-04 04:09 | RunHarmony with sample_id (16,003 unique) → 1 iteration convergence (pseudo-conv | logic_error | sample_id had 16,003 unique values (individual cell barcodes | Switch batch variable from sample_id to donor_id (19 donors) | human | skeletal_muscle | high |
| 2026-09-24 17:24 | execute_r 内用 exec(open(...).read()) 报 <text>:1:116: unexpected symbol | syntax_error | 把 execute_python 的脚本加载写法套用到 execute_r：R 没有 exec()/open() 内建， | R 内核里运行脚本文件必须用 source(path, encoding="UTF-8")；exec(open().re |  |  | low |
| 2026-09-24 17:25 | NA/NaN/Inf in foreign function call (arg 1) — 脚本 harmony_samplename_integration. | runtime_error | 距离矩阵就地修改（diag<-Inf）污染了后续 silhouette 调用；silhouette 的 dmatrix  | kNN 检索把 diag(D)<-Inf 后，同一矩阵又被传给了 cluster::silhouette(dmatrix |  |  | medium |
| 2026-09-24 17:26 | 'dmatrix' is not a dissimilarity matrix compatible to 'x' (cluster::silhouette) | runtime_error | 混用 silhouette 的两种距离入参形式：dmatrix 要 matrix、dist 要 dist 对象；传 di | cluster::silhouette(dmatrix=) 必须传 n×n 对称距离矩阵（对角 0），不能传 as.di |  |  | low |
| 2026-09-24 17:27 | RunHarmony: Argument assay.use is unhandled. Please refer to the documentation f | runtime_error | harmony 1.2.x 起 RunHarmony 参数白名单变化（assay.use 被移除/改由 DefaultA | 本机 harmony 版本不接受 assay.use 参数 → 移除该参数；RunHarmony 自动使用 Defaul |  |  | medium |
| 2026-09-24 17:30 | there is no package called 'mclust'（mclust::adjustedRandIndex） | missing_package | 本机 R-4.5.3 库无 mclust（Seurat 5.5.1 不再把它列为依赖），ARI 需要另找来源 | 不安装包（铁律29 缺包先问用户）；ARI 改为自实现列联表公式：ARI=(idx-exp)/(max-exp)，idx |  |  | low |
