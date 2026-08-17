# ArchR 1.0.3 Windows 实测陷阱（2026-08 P0/P1 批量 + P3 注释）

在 Windows + R 4.5.3 上跑 ArchR 批量样本（GSE278576 40 样本 QC + 人侧 4 样本 merge/聚类/注释）实测踩坑汇总。

## 1. addClusters 必须用 `input=` 参数（不能用 ArchRProj=）

ArchR 1.0.3 `addClusters` 签名是 `function(input = NULL, ..., ArchRProj = NULL)`。
若调用 `addClusters(ArchRProj = proj, ...)`，函数内部第 13-16 行触发兼容路径：
```r
if (is(ArchRProj, "ArchRProject")) {
    message("When running addClusters 'input' param should be used for 'ArchRProj'...")
    input <- ArchRProj
    rm(ArchRProj)   # ← 删除后，后续代码再引用 ArchRProj 变量 → object not found
}
```
→ 报错 `错误: 'ArchRProj'的值没有`。**修复：`addClusters(input = proj, reducedDims = "IterativeLSI", ...)`。**

## 2. addGeneScoreMatrix 在 Windows 上连续崩溃

`addGeneScoreMatrix(input=proj)` 在 Windows 写 Arrow 阶段（"Creating GeneScoreMatrix"）静默崩溃 2 次（内存充足 33GB 空闲，非 OOM）。
**替代方案（等效简化版 gene score）**：用 TileMatrix 500bp bins + marker 基因 TSS±2kb 覆盖度评分：
- `getFeatures(proj, useMatrix="TileMatrix")` 拿 GRanges（6,062,095 条，chr:start-end 格式）
- marker GRanges → `findOverlaps(win, tile_gr)` → 提取命中 tile 行的矩阵
- 按 celltype 聚合 tile 覆盖数 / 该类总 marker tile 数 → 分数
- threads=1 防并发崩溃

## 3. getMatrixFromProject 全矩阵 OOM

`getMatrixFromProject(proj, useMatrix="TileMatrix")` 加载全矩阵（6M tiles × 35K cells）在 "Organizing Assays" 阶段报 `cannot allocate vector of size 7.5 Gb`。
**绕开方案**：
- Python 端从 Arrow 按需读取（TileMatrix 是 CSC 稀疏格式，indptr 长度 = nCells+1，只取 marker 区域行）
- 或 `getMatrixFromArrow()`（但该函数**没有 `features` 参数**，只有 useSeqnames/cellNames）
- 注意 `rowRanges(tile)` 在部分版本返回 NULL → 坐标在 `rowData(tile)` 的 seqnames/start 列

## 4. Arrow TileMatrix 是 CSC 不是 CSR

从 Arrow 直接读 TileMatrix 时：`indptr` 长度 = nCells+1，`indices` 是每个 cell 的非零 tile 行号。
按行（feature）读索引会全错 → **必须按列（cell）读**：`indices[indptr[j]:indptr[j+1]]`。

## 5. Arrow cellNames 与 R 导出名的前缀不一致

Arrow 里 cellNames 是短 barcode（`TACCAGGTCATCCACC-1`），而 R `getCellColData` 导出的是带样本前缀全名（`GSM8549616_hc78#TACCAGGTCATCCACC-1`）。
Python 侧匹配 cell 时**必须 strip 前缀**（split `#` 取后半），否则全部匹配失败 → 分数全 0 → 注释全成一个类别。

## 6. filtered Arrow 未真正剔除 doublet（重要）

`_Filtered/` 目录 Arrow 与 QC 目录 Arrow 是**同一文件**（字节数完全一致）——doublet 过滤只记录在 `_filtered_cells.csv`（含 cellNames 列），**Arrow 内仍含全部细胞**。
merge/下游分析前**必须用 CSV 的 cellNames 名单子集**，否则 doublet 污染聚类（实测 QC 表 29,357 vs Arrow 内 35,787，+18%）。

## 7. getGeneAnnotation 的 mcols 列名

`getGeneAnnotation(proj)$genes` 的 mcols 列名是 `gene_id, symbol`，**不是 `name`**。
`mcols(geneAnno)$name` 返回 NULL → marker 全匹配 0 → 报 "GeneAnnotation genes: 0"。

## 8. getFeatures 返回 GRanges 直接可用

注释 tile 定位用 `getFeatures(proj, useMatrix="TileMatrix")` 直接返回 GRanges（chr1:0-499 等），**不要**依赖 `rowRanges(assay)`（可能 NULL）。
