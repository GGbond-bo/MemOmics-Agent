# ArchR TileMatrix → 样本级矩阵提取（L2 可及性输入制备）

> 场景：多供体 / 跨物种 scATAC，需把 ArchR 项目里的 TileMatrix 提取成
> 「样本 × tile」矩阵，作为 L2 可及性保守比对（人 vs 猴）的输入。
> 实测锚点：猴侧 20 样本 × 6,085,841 tile = 206 MB（dgCMatrix 稀疏）；
> 人侧 40 样本预期 ≈ 400 MB。

## 三个必踩的坑 / 决策点

### 1. 2^31-1 溢出（全量 cbind 必爆）
- 症状：`p[length(p)] cannot exceed 2^31-1`
- 根因：`getMatrixFromProject(proj)` 把所有 arrow/细胞一次性 cbind 成一个稀疏矩阵，
  非零元素数(nnz) > 2^31−1 ≈ 21.4 亿。40 供体 = 26.6 万细胞 × 600万 tile ≈ 26.6 亿 nnz，必超。
- 绕过：逐个 arrow 建独立 project（`ArchRProject(ArrowFiles=arrowFiles[i])`）逐个提取，
  或按样本 `subsetArchRProject` 后逐个提取；每个提取完立即 `rm(...); gc()`。
- 产物是「样本级」小矩阵时，最终不会有这个溢出——溢出只在「几十万细胞级巨矩阵」阶段发生。

### 2. 存 cell 级 vs 样本级（口径错位 → 文件爆炸）
- ❌ `saveRDS(assay(se_sample))`：存的是该样本「所有细胞 × tile」的原始矩阵
  → 单样本就 ~200MB，40 样本 8GB，最后还得 cbind 成 26.6 万细胞巨矩阵。
- ✅ 正确口径 = 每个样本压成 **1 行 × tiles** 的「覆盖比例」(0~1)：
  ```r
  agg_list[[i]] <- Matrix::colMeans(assay(se))
  # 40 个 1 行向量 → do.call(rbind, ...) → 40 样本 × tiles，≈ 400MB
  ```

### 3. 口径必须两侧一致（覆盖比例 ≠ 覆盖计数）
- 覆盖比例(colMeans, 0~1) 与 覆盖计数(colSums/rowsum, 整数) 是两种口径，不可混用。
- 比对新数据前，先读一侧矩阵值域确认口径：
  - `min ≈ 1/细胞数`、`max ≈ 0.99` → colMeans 覆盖比例
  - 全是整数 → 覆盖计数
  - 两侧不一致 → L2 比对全错。
- 猴侧实测口径 = colMeans 覆盖比例（M1 最小非零 0.0001 = 1/10013，max 0.9988）。

## 合并片段（agg_list 已在内存，length=40）

```r
if (is.null(names(agg_list))) names(agg_list) <- all_samples
lens <- sapply(agg_list, length)
cat("tile列数全一致?", length(unique(lens)) == 1,
    "| 首末列名一致?", identical(names(agg_list[[1]]), names(agg_list[[40]])), "\n")
cn  <- names(agg_list[[1]])          # 按首个样本 tile 名统一顺序（兜底重排，防错位）
agg <- do.call(rbind, lapply(agg_list, `[`, cn))
rownames(agg) <- names(agg_list)
agg <- Matrix::Matrix(agg, sparse = TRUE)   # 转 dgCMatrix，与猴侧同口径
saveRDS(agg, "Human_file/human_tile_matrix_samples_x_tiles.rds")
cat("✅", dim(agg), "| 大小", round(file.size(...)/1024^2, 2), "MB\n")
```
> 跑完验证 `dim(agg)` 第二维 ≈ 另一侧的 tile 列数（本例 ~6,085,841），对不上 = 列集合有出入，
> 需取并集列对齐（缺失列补 0 再 rbind）。

## 假文件 / 错口径文件检测（不读数据别下结论「能用」）

读 `dim()` + `colnames()` 前缀，三个指纹一次判死：
- **正确** 样本×tile 矩阵：列名 = `chr:start-end`（tile 坐标），列数 ≈ 数百万（hg38 500bp 平铺 ≈ 608万）。
- **错误** 中间产物：列名 = 细胞条码（`GSMxxx_sample#GTTACAG...-1`），列数 = 细胞数（几千~几万）。
- **体积**：真矩阵几百 MB；假矩阵只有几 MB 零头。

实测实例：一个 40 × 10,910 的 dense `matrix`，列名全是 `GSM8549634_hc6021#...` 细胞条码
——是某次跑岔、只处理了单个样本、把细胞条码铺成列的半成品，不是样本×tile 矩阵。

## 跨物种坐标对齐（人 hg38 vs 猴 T2T-MFA8）

**无需对 tile 做跨物种坐标对齐。** 候选元件坐标表（如 `v9_A_class_CRE_coords.csv`）
每行自带两侧坐标（human_chr/start/end + monkey_chr/start/end），402 个元件人猴已配对。
做法：两侧各自用**自己坐标系**的坐标查**自己那侧** TileMatrix → 元件层面直接比对。

⚠️ 别把「基因同源表」(`monkey_human_orthologs_full.csv`, macaque_gene_id→human_gene_id)
当坐标对齐表——那是 gene ID 映射，跟 tile/元件坐标对齐是两回事。

## 传递交付的口径纪律

- 给估计值（文件大小/细胞数/维度）前先实测锚定，不要拍脑袋给「几十 MB」这类会被当场拆穿的数：
  用同物种同口径的已落盘产物做锚（猴侧 206MB → 人侧 40 样本 ≈ 2 倍 ≈ 400MB），并说明「这是估算不是实测」。
- 用户贴控制台截图（`exists()`/`length()`）求证时，按 OCR 读出的值作答，先确认变量还在、元素数对不对，
  再给下一步（本例 `exists=TRUE` + `length=40` 说明 40 个 colMeans 向量都在，直接进入 rbind 合并）。