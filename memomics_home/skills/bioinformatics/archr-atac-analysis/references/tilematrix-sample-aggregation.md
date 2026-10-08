# TileMatrix 按样本聚合（避免 2^31-1 cbind 溢出）

## 触发场景

大项目（40 个 Arrow、几十万细胞）直接 `getMatrixFromProject(proj, useMatrix="TileMatrix")`
做 `addIterativeLSI` 或提取 tile 计数时，稀疏矩阵 cell 维太大触发
`Cannot allocate vector ... 2^31-1`（`Matrix` cbind 溢出）。目标是把 cell 维压缩成
sample 维（samples × tiles 小矩阵），再做下游（样本级 DA tiles / 年龄相关）。

## 🔴🔴 矩阵方向 + colMeans/rowMeans（2026-09-14 核心教训，浪费用户一整天）

**`assay(se)` 的方向是 tile × cell（行=tile，列=cell），不是 cell × tile。** 名字最能定方向：

- 列名 = 细胞条码（`GSM8549615_hc77#ACGCACGGTATTCGCT-1`）→ 说明**列是 cell**
- 行名 = `chr:start-end`（tile 坐标）→ 说明**行是 tile**

### 两个运算符产出完全不同的东西

| 运算 | 对什么求均值 | 结果长度 | 结果名字 | 对不对 |
|------|-------------|---------|---------|--------|
| `colMeans(assay(se))` | 对**列=cell** 求均值 | = n_cells（~1 万） | **细胞条码** | ❌ 错的（产生 40×10910 假矩阵，列名全是 barcode） |
| `rowMeans(assay(se))` | 对**行=tile** 求均值 | = n_tiles（~608 万） | `chr:start-end` tile 坐标 | ✅ 对（每个 tile 的覆盖比例） |

**用户原代码 `colMeans` 把每个 tile 覆盖比例算成了"每个细胞的均值"**——这就是 Downloads 里那个 2.75MB / 40×10910 / 列名全是 barcode 的假文件成因。要样本级 tile 覆盖，**只改一个字：`colMeans` → `rowMeans`**（`Matrix::rowMeans`，值域 0-1 覆盖比例，长度=608 万）。

### 覆盖比例 vs 覆盖计数（跨物种比对必须同口径）

`rowMeans(binarize=TRUE 的矩阵)` 产出的是**覆盖比例 0-1**（每个 tile 被该样本多少比例的细胞覆盖，min≈1/n_cells）。`rowsum`/`colSums` 产出的是**覆盖计数**（整数）。人猴 L2 可及性比对时，两侧必须同一口径——猴侧基准矩阵（`E:/专利/file/monkey_tile_matrix_samples_x_tiles.rds` 20×6,085,841）实测值是 0-1 比例（max 0.9988，min≈1/16161），所以**人侧必须也用 `rowMeans`**，别混 `rowsum` 计数进来，否则跨物种对比直接错位。

### 产出真伪自检（拿到 .rds 先验三样，别信文件名）

| 检查 | 真货 | 假货（当日实拍的错件） |
|------|------|----------------------|
| 维度 | `40 × 6,085,841`（样本 × tile） | `40 × 10910`（样本 × cell） |
| 列名 | `chr1:1-500` 类 tile 坐标 | `GSM8549615...#GTTACAGGT...-1` 细胞条码 |
| 体积 | ~400 MB（40 样本稀疏） | ~2.75 MB（只有零头） |

列名前缀 `GSM..._hc####` 即 cell barcode、不是 tile。三样对不上就扔，别拿去和猴侧比对。

### subsetArchRProject 中间产物可直接复用（别重跑最贵那步）

若用户已经跑过 `subsetArchRProject` 生成了 `Human_file/sub_<sample>/` 子项目目录（含 `Save-ArchR-Project.rds`），直接 `loadArchRProject(dir)`（或 `readRDS(file.path(dir, "Save-ArchR-Project.rds"))`）读现成子项目再取矩阵，**跳过最耗时的建项目 + 复制 arrow 那步**：

```r
sub_dirs <- list.dirs("Human_file", recursive = FALSE)
sub_dirs <- sub_dirs[grepl("^sub_", basename(sub_dirs))]
for (d in sub_dirs) {
  proj_sub <- ArchR::loadArchRProject(d)          # 读现成子项目
  se <- getMatrixFromProject(proj_sub, useMatrix="TileMatrix", binarize=TRUE)
  agg_list[[sub("^sub_","",basename(d))]] <- Matrix::rowMeans(assay(se))  # ← rowMeans
  rm(se, proj_sub); gc()
}
```

## 🔴 关键 API 事实（2026-09-14 源码实测，ArchR 1.0.3）

- **`getMatrixFromProject` 没有 `cellNames` 参数**。formals 只有 8 个：
  `ArchRProj, useMatrix, useSeqnames, excludeChr, verbose, binarize, threads, logFile`。
  传 `cellNames=...` → `unused argument (cellNames=...)`，第一轮就崩。
- **它读的是 project 挂载的全部 Arrow，然后 cbind** —— 根本没有"按 cell 子集只读某个
  arrow"的能力。所以"去掉 cellNames + 每轮过滤"依然是全量读 → 照样溢出。所谓"逐 arrow 读取"
  若写在同一个 proj 上就是假象。
- `.availableCells` 是内部函数（`.` 前缀），要写 `ArchR:::.availableCells(...)` 才调得到。

## 正解：每个 arrow 单独建 project

不是"一个 proj 反复读 + cellNames 过滤"，而是"每个 arrow 单独建只挂 1 个 arrow 的 project"。
单 arrow ≈ 几千细胞，nnz 安全。

```r
library(Matrix)
library(ArchR)

arrowFiles <- getArrowFiles(proj)
agg_list <- vector("list", length(arrowFiles))

for (i in seq_along(arrowFiles)) {
  cat(sprintf("[%d/%d] %s\n", i, length(arrowFiles), basename(arrowFiles[i])))
  # 每次只挂 1 个 arrow → 单 arrow project
  proj_i <- ArchRProject(ArrowFiles = arrowFiles[i],
                         outputDirectory = paste0("tmp/proj_", i),
                         copyArrows = FALSE)
  se_i <- getMatrixFromProject(proj_i, useMatrix = "TileMatrix",
                               binarize = TRUE, threads = 1)
  mat_i <- assay(se_i)                    # 单 arrow: tiles × cells（行=tile，列=cell）
  sample_i <- proj_i$Sample               # 单 arrow 的样本标签
  agg_i <- t(Matrix::rowsum(t(mat_i), group = sample_i))   # → samples × tiles
  agg_list[[i]] <- agg_i
  rm(proj_i, se_i, mat_i); gc()
}

# 合并（按样本行名对齐相加；不同 arrow 的 tile 行完全一致则直接 +）
agg <- Reduce(function(a, b) {
  common <- intersect(rownames(a), rownames(b))
  a_only <- setdiff(rownames(a), rownames(b))
  b_only <- setdiff(rownames(b), rownames(a))
  rbind(a[a_only, , drop=FALSE], b[b_only, , drop=FALSE],
        a[common, , drop=FALSE] + b[common, , drop=FALSE])
}, agg_list)

saveRDS(agg, file = "human_tile_matrix_samples_x_tiles.rds")
```

## 要点

- 每个 arrow 单独建 project 时，`proj_i$Sample` 直接是该 arrow 内细胞的样本标签，
  不需要 `match(colnames(mat_i), sampleMap$barcode)` 跨文件对齐。
- 合并阶段 `Reduce` 里 `common` 行相加（同一样本跨多个 arrow 的 cell 会被合并到同一个
  sample 行——若 sample 与 arrow 是一对一，则直接 rbind 即可，不会有 common）。
- 用 `outputDirectory = paste0("tmp/proj_", i)` 临时目录；`copyArrows=FALSE` 避免重复拷贝。
- 大项目另注意：`addIterativeLSI` / `addPeakMatrix` 的 OOM 见 SKILL.md Phase 5「getMarkerFeatures OOM 陷阱」。
