# 样本×tile 矩阵：聚合方向与数据归属陷阱（跨物种 L2 比对）

人/猴 L2 染色质可及性比对，两侧都需要「样本 × tile」的覆盖矩阵（行=样本，列=统一 tile 网格）。
这一步极易在三个地方搞错，2026-09-14 人侧矩阵全踩了一遍，教训如下。

## 1. 聚合方向：rowMeans(tile) vs colMeans(细胞) ← 最易错

- **正确**：目标矩阵 = 行=样本(40)，列=tile(~608万)，值 = 每个 tile 的覆盖比例。
  从 ArchR Matrix 抽 coverage 时，覆盖落在 **tile 轴（genome interval）**，不是细胞轴。
- **错误**：把**细胞**当聚合单元，对「列=细胞」求 `colMeans`，
  结果列名变成 `样本名#细胞barcode`（如 `GSM8549615_hc77#ACGCACGGTATTCGCT-1`）。
- **判别签名**（不用读全量就能判对错）：

  | 信号 | 正确(tile 矩阵) | 错误(细胞矩阵) |
  |---|---|---|
  | 文件大小 | ~206MB（40 样本 × 608万 tile 稀疏） | ~2.8MB（26.6 万细胞 × 40） |
  | 列名 | tile 坐标 / 统一索引 | `样本名#barcode` |
  | 维度 | 40 × 6085841 | 40 × 几百~几千 |
- **对齐基准**：猴侧 `monkey_tile_matrix_samples_x_tiles.rds` = **6085841 tiles**。
  人侧必须对齐到**同一个 6085841 网格**（异参考基因组 hg38 vs 猴侧，需 liftOver 到同源网格后再比对）。

## 2. ArchR `Save-ArchR-Project.rds` 存绝对 arrow 路径

- `saveArchRProject()` 把每个细胞所属 arrow 的路径写成**绝对路径**存进 rds。
  之后 `readRDS` + `loadArchRProject`/`getMatrixFromProject` 会去那个绝对路径找 arrow，
  文件搬家/改名后报：
  `Cannot open file. File 'E:\专利\ArrowFiles\O1_Hip_1.arrow' does not exist.`
- **教训**：别靠 rds 文件名判断数据归属——`project_tilemat.rds` 这种名字不提示人/猴。
  **先看它引用的 arrow 样本名**：`O1_Hip_1` = 猴（Old1 海马），`GSM8549615` = 人（GSE278576 海马）。
  本会话 `E:/专利/ArchR_Output/project_tilemat.rds` 就是**猴侧**旧 project，不是人侧的。

## 3. QC 过滤后的 arrow 只含 fragments + QC metrics，不含 TileMatrix

- 目录名 `ArchR_Arrow_QC_Filtered/`（每样本一个 `.arrow` + `_filtered_cells.csv`，
  内含 `TSSEnrichment/nFrags/DoubletScore/cellNames/DoubletFilter`）说明流水线
  **只跑到 QC + 去双联体，还没跑 `addTileMatrix()`**。
- 因此「从这些 arrow 直接抽 tile 覆盖」**不成立**——里面根本没有 TileMatrix group。
  正确路径：在合并后的 ArchR project 上 `addTileMatrix()` 重建，或先确认 arrow 里确有 TileMatrix group。
- **判定方法**：读 arrow 的 HDF5 顶层 group（ArchR 的 tile matrix 存为 `TileMatrix` group），
  不存在 → 需重建。

## 复算骨架（聚合方向正确版，勿盲跑）

```r
# 目标：40(样本) × 6085841(tile) 稀疏矩阵，与猴侧同网格
# 关键：coverage 落在 tile 轴 → 用 rowMeans(对 tile)，不是 colMeans(对细胞)
se <- getMatrixFromProject(proj, useMatrix = "TileMatrix", binarize = TRUE)
cov_tile <- Matrix::rowMeans(assay(se))   # ★ rowMeans，长度 = 608万 tile
```

## 一句话结论

看到「样本×tile」读出来只有几 MB、列名带 `#barcode`，就是又把**细胞维度**当 tile 了。
改回 `rowMeans`（对 tile 轴），不是重新读数据。