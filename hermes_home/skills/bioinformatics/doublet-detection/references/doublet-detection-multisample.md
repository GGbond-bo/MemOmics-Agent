# 多样本 / 低细胞数双细胞检测 — 可跑配方

> 实测来源：2026-09-24，`MF_2000.rds`（Seurat，2132 cells × 51227 genes，48 样本，6 组 Y/O/OD × Pre/Post，≈44 细胞/样本）。

## 1. 事实核查（一次 execute_r 打印全部）

```r
.libPaths(c("E:/R-libs/R-4.5.3", .libPaths())); library(Seurat)
obj <- readRDS("<路径>.rds")
cat("cells:", ncol(obj), "genes:", nrow(obj), "\n")
print(table(obj$samplename))                     # 每样本细胞数 → 决定策略
md <- obj@meta.data
for (v in c("nCount_RNA", "nFeature_RNA")) if (v %in% colnames(md)) print(tapply(md[[v]], md$type, median))
cnt <- tryCatch(LayerData(obj, assay = "RNA", layer = "counts"),
                error = function(e) GetAssayData(obj, assay = "RNA", slot = "counts"))
cat("integer counts:", all(cnt@x == round(cnt@x)), "| sums:", range(Matrix::colSums(cnt)), "\n")
```

⚠️ R 侧按分组聚合**一律用 `tapply`**（`aggregate` 遇字符型分组列报 `non-numeric-alike`，且 execute_r 出错时 stdout 全丢）。

## 2. 导出中间件（R-4.5.3 → 磁盘，供 Python 或 R-4.4.2 复用）

```r
out <- "E:/MemOmics-Agent/results/<sid>/data"; dir.create(out, recursive = TRUE, showWarnings = FALSE)
writeMM(cnt, file.path(out, "counts.mtx"))
writeLines(rownames(cnt), file.path(out, "features.tsv"))
writeLines(colnames(cnt), file.path(out, "barcodes.tsv"))
write.csv(md, file.path(out, "metadata.csv"))
```

## 3. 路线 A（推荐）：Python scrublet（免跨版本桥接）

`check_env(language="Python", packages=["scanpy","scrublet"])` 实测 installed。

```python
import scanpy as sc, pandas as pd, numpy as np
out = "E:/MemOmics-Agent/results/<sid>/data"
ad = sc.read_mtx(f"{out}/counts.mtx").T                     # 转成 cells × genes
ad.var_names = [l.strip() for l in open(f"{out}/features.tsv")]
ad.obs_names = [l.strip() for l in open(f"{out}/barcodes.tsv")]
ad.obs = pd.read_csv(f"{out}/metadata.csv", index_col=0).loc[ad.obs_names]
sc.pp.scrublet(ad)                                          # 整体检测
# 仅当每样本细胞数 ≥ 200 才用 batch_key（否则估计不稳）
# sc.pp.scrublet(ad, batch_key="samplename")
ad.obs[["doublet_score", "predicted_doublet"]].to_csv(f"{out}/doublet_scores.csv")
print(ad.obs["predicted_doublet"].mean())                   # 总体双细胞率
print(ad.obs.groupby("type", observed=True)["predicted_doublet"].mean())       # 按组
print(ad.obs.groupby("samplename", observed=True)["predicted_doublet"].mean().sort_values(ascending=False).head(10))
```

## 4. 路线 B：R-4.4.2 直调 scDblFinder（不碰 Seurat）

```bash
# bash 里直调绝对路径（⛔ 不要套 cmd //c：MSYS 会吃掉参数，只起 cmd banner、脚本一行不跑）
"C:/Users/23136/AppData/Local/R/R-4.4.2/bin/x64/Rscript.exe" "E:/.../scripts/doublet.R" > log/doublet.log 2>&1; echo "exit=$?"
```

```r
# doublet.R：只读 mtx + meta，零 Seurat 依赖
.libPaths(c("C:/Users/23136/AppData/Local/R/R-4.4.2/library", .libPaths()))
suppressMessages({library(Matrix); library(SingleCellExperiment); library(scDblFinder)})
out <- "E:/MemOmics-Agent/results/<sid>/data"
cnt <- readMM(file.path(out, "counts.mtx"))
rownames(cnt) <- readLines(file.path(out, "features.tsv"))
colnames(cnt) <- readLines(file.path(out, "barcodes.tsv"))
md  <- read.csv(file.path(out, "metadata.csv"), row.names = 1)
sce <- SingleCellExperiment(list(counts = cnt), colData = md)
# 每样本细胞数 <100 ⇒ 不加 samples=；≥200 时加 samples = sce$samplename
sce <- scDblFinder(sce)
res <- as.data.frame(colData(sce))
write.csv(res, file.path(out, "doublet_scDblFinder.csv"))
print(table(res$scDblFinder.class))
```

## 5. 判读：三个分布必须一起看

```python
# ① 按样本：双细胞是否集中在少数样本（= 该样本技术问题）
# ② 按组：组间差异大 ⇒ 剔除会引入组间细胞数不平衡，必须在报告里说明
# ③ 按簇/亚群：双细胞富集于某簇 ⇒ 该簇注释需单独复核
```
| 双细胞率 | 判读 | 动作 |
|---------|------|------|
| < 5% | 低 | 可保留，记入报告 |
| 5–10% | 正常（10x 常规） | 建议剔除 |
| 10–15% | 偏高 | 建议剔除 + 查是否集中 |
| > 15–20% | 很高 | 先查根因再剔 |

剔除准则：率 ≥5% 或富集于特定样本/簇 ⇒ 剔除（保留 `predicted_doublet == FALSE`）；否则保留但**写进 metadata**。
⛔ **先写标记列再 subset**（可回溯、可做敏感性对比）；剔除后**按组分别**列细胞数变化。

## 6. 交付与过审

- 率表（Markdown 管道表，铁律 29）+ 4 张图（分数直方图含阈值线 / 降维叠加标记 / 分数 vs nFeature 散点 / 按组·样本柱状）+ `doublet_scores.csv` + 明确建议
- `rail_review(post)` 的 `output_dir` 传**会话根目录** `results/<sid>/`（子目录只数一层 → figure_count=0 硬判 failed）
- 出图脚本 `ggsave` 后若被判「图片损坏」，是调色板 PNG 误报 → `Image.open(p).convert("RGB").save(p)` 重编码后重审，**不重跑脚本**