# ArchR TileMatrix 提取 → 跨物种「样本 × tile」矩阵（2026-09-14/15 实测）

人侧 GSE278576 要与猴侧 T2T-MFA8 做 L2 衰老可及性比对，第一步是把人侧每个样本的
TileMatrix 抽出来，聚合成「样本 × 统一 tile 网格」的覆盖比例矩阵。这一步栽了一整天的坑，
全部根因与正确姿势如下。

## 目标矩阵的正确形态（先钉死，别搞反维度）

```
行 = 样本（40 个）
列 = 基因组 tile（几十万~几百万，500bp 一格）
值 = 该 tile 的覆盖比例（0~1，= 覆盖该 tile 的细胞数 / 该样本总细胞数）
```

判据：
- 列名应该是 **tile 坐标**（`chr1:0-499` / `NC_088375.1:0-499`），**不是** 细胞 barcode（`GSMxxx#ACG...`）
- 体积应与猴侧同量级（人侧 40 样本 ≈ 500MB，猴侧 20 样本 ≈ 200MB 稀疏 rds）

**产物列名若是 `样本名#细胞barcode`、或只有 2.8MB 那么小 —— 维度搞反了，落到了细胞而非 tile。** 这是本 session 浪费一天的根因。

## 根因 1：`rowMeans` 写成 `colMeans`（最致命）

ArchR `getMatrixFromProject(..., useMatrix="TileMatrix")` 返回的 SummarizedExperiment：
- **行 = tile**，**列 = 细胞**

要「每个 tile 的覆盖比例」→ 对**行**求均值 → `Matrix::rowMeans(assay(se))`。
`colMeans` 对列（细胞）求均值 → 得到「每个细胞一个数」→ 列名变 barcode，维度 40×细胞数。
**就 `col` → `row` 这一个字，是全部错误的本源。**

## 根因 2：`Matrix::rowMeans()` 丢弃行名 → 合并时塌成 0 列

症状：单样本每个向量长度、值域都正确，但合并后 `dim = 40 × 0`。

原因：`Matrix::rowMeans()` 返回的向量**不带行名**（`names(v) == NULL`）。合并脚本若写成
`Reduce(intersect, lapply(agg_list, names))` 按 tile 名取交集对齐，交集是 NULL → 空。

修复：显式补名
```r
v <- Matrix::rowMeans(assay(se)); names(v) <- rownames(assay(se))
```
若 rownames 本身是 NULL（见根因 3），用 `rowData(se)` 生成 tile 名再赋。

## 根因 3：ArchR 1.0.3 的 tile 坐标在 `rowData`，不在 `rownames`

`assay(se)` 的 `rownames` 在 ArchR 1.0.3 里**是 NULL**。chr/start/end 放在 `rowData(se)`
前三列（`seqnames` / `start` / `end`，tileSize=500）。

正确拿 tile 名：
```r
rd <- rowData(se)
tile_names <- paste0(rd$seqnames, ":", rd$start, "-", rd$end)   # 长度 = tile 数
```

## 根因 4：人/猴 tile 数不同是「参考基因组不同」，不是 bug

- 猴侧 T2T-MFA8 = **6,085,841** tile
- 人侧 hg38 = **6,062,095** tile

两个数**天生不等**。别拿「对齐到 6085841」当验收标准 —— 跨物种坐标对齐是后面单独的
liftOver / 统一同源网格步骤，与「提取」这一步无关。提取阶段唯一验收 = **同物种内 N 个
样本之间 tile 数彼此一致**。

## 最快路径：箭头文件里已预存 `rowSums`，不用重构稀疏矩阵

ArchR 的 `.arrow` (HDF5) 里 `TileMatrix/` 键下预存：
- `TileMatrix/Info/FeatureDF` = 全部 tile 坐标（seqnames + start，tileSize=500）
- `TileMatrix/Info/CellNames` = 细胞名
- 每条染色体下 `rowSums`（1 × n_tile）= 覆盖该 tile 的细胞计数

「每个 tile 覆盖比例」= `rowSums / n_cells`，**直接读现成 rowSums，不重构稀疏矩阵**。
实测用 Python `h5py` 读箭头、预分配 float32 稠密矩阵（40×6062095 ≈ 970MB）一次填入，
成功产出 `human_tile_mean_samples_x_tiles.npz`（40×6062095，非零率 91.65%）。

配套产出（供下游对齐）：
- `human_token_chr.npy` / `human_token_start.npy`（每 tile 染色体 + 起始坐标）
- `human_token_chr_order.npy`（chr1…chrX 顺序）
- `human_sample_names.npy`（N 样本名）

## 人侧 meta 表格式（L1/L2 关联输入）

`human_meta_40donors.csv`，5 列：
```
sample,gsm,donor_id,age,sex
GSM8549615_hc77,GSM8549615,hc77,20,male
...
GSM8549654_hc9,GSM8549654,hc9,95,female
```
- **`sample` 列 = 矩阵行名原文**（`GSM8549615_hc77` 连体），后续 `match(sample, rownames(matrix))` 零拼接
- **`age` = 连续值**（20→95，跨成人寿命），不是分组 —— 衰老关联（Spearman/Pearson）用连续年龄
- `sex` 作可选协变量

年龄来源 = GSE278576 BioSample `age`/`sex` attribute（hc77 已单独验证 = 20/male）。
GEO series matrix 里**没有** age，必须去 BioSample 拿。

## 工作流铁律（用户明确要求）

**先测一个单元，再循环。** 用户原话："能不能先测试一个箭头文件是否能够找到矩阵，再循环呢？
你现在浪费我很多时间了。"

- 循环前先对**单个**箭头文件/子项目跑「读到矩阵 + 列名对不对 + 值域对不对」的 20 秒探针
- 确认 4 个验收点（`dim`=tile×细胞、`rownames` 是否 NULL、`rowMeans` 长度、值域 0~1）全对，才写循环
- 循环里每个样本算完立即 `saveRDS` 到临时目录 + `if(file.exists()) next` 断点续跑，避免 100 分钟白跑
- 目录名叫 `Human file`（空格）还是 `Human_file`（下划线）**不要靠猜，先 `list.dirs()` 打印出来对**。本 session 一次把空格猜成下划线导致「找到子项目 0 个」空转

## 数据布局歧义（本 session 绕圈的另一半原因）

人侧数据其实有两种并存形态，别混：
1. **ArchR project**（`sub_GSMxxx/Save-ArchR-Project.rds` + ArrowFiles/ 等）——集群上的
2. **裸箭头文件**（`ArchR_Arrow_QC/GSMxxx.arrow` 平铺，无 rds 无 sub 目录）——本机的

test 阶段先 `list.dirs()` / `list.files` 确认到底是哪一种，再选 `readRDS(Save-ArchR-Project.rds)`
还是 `h5py` 直读 `.arrow`。别一开始就假设有 project rds。