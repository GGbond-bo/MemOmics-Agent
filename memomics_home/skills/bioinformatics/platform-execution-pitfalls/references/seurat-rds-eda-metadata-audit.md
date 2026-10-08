# Seurat `.rds` 数据体检与元数据语义审计

> 触发场景：用户丢来一个 `.rds`（Seurat 对象）说「**先打开看看里面有多少细胞、多少基因、有哪些样本和分组，做个最基本的统计告诉我**」。
> 这是**只读 EDA**，不是分析：不过滤、不修改、不建 task_plan，但**必须落盘报告 + 出图**（rail_review(post) 会判 failed）。
> 首次实测 2026-09-24（人骨骼肌肌纤维 MF_120，120 细胞 × 51,227 基因）。

---

## 0. 三条硬约束（先记住，否则白跑）

1. **不转 h5ad**：数据是 `.rds` 就走 R（`readRDS` + Seurat）。Windows 上 h5ad↔rds 转换（SeuratDisk）频繁失败。
2. **必须出图**：rail_review(post) 对「未生成任何图片」**硬判 failed**。base graphics 四联图即可（见 §5），一次出 PNG+PDF+TIFF。
3. **复用 kernel 里的 `obj`**：同一会话后续步骤不要再 `readRDS`（post-review 会告警，大对象重读极慢）。只有报 `object not found`（内核超时/重启）才重新加载。

---

## 1. Step 1 — 结构探测（一次调用拿全）

```r
.libPaths(c('E:/R-libs/R-4.5.3', .libPaths()))   # 必须在第一条 library() 之前
suppressPackageStartupMessages(library(Seurat))
options(width = 200)

obj <- readRDS(p)
print(class(obj)); print(dim(obj))               # dim = genes x cells（R 顺序，别报反）
print(Assays(obj)); print(DefaultAssay(obj)); print(Reductions(obj))
print(head(levels(Idents(obj)), 30))             # 当前分组标签
print(colnames(obj@meta.data))                   # 元数据列清单
print(head(obj@meta.data, 5))                    # 前 5 行看语义（样本/分组/QC 列长什么样）
```

**要点**：`dim(obj)` 是 **基因 × 细胞**，汇报时要转成「细胞 N × 基因 M」。
`colnames(meta.data)` 是后续所有判断的基础 —— 先看清有哪些列（本例 50 列，含 `samplename`/`age`/`type`/`sex`/`celltype`/`annotation_L2`/`annotation_L3` + 18 个 `*_AUC` 打分列）。

---

## 2. Step 2 — 元数据语义审计（本类任务的核心价值）

用户问「有哪些样本和分组」，**光列表格不够** —— 要顺带回答三个会被审稿人/辩论追问的问题：

### 2.1 分组列 × 命名后缀 是否完全绑定

```r
map <- unique(md[, c("samplename","type","age","sex","library")])
map$C_suffix <- grepl("C", sub("^Old_", "", map$samplename)) & grepl("^Old", map$samplename)
print(table(map$type, map$C_suffix))
```

**为什么做**：样本名里的后缀（`Old_10C_Pre` 的 `C`）如果与分组 **100% 绑定、零例外**，说明它是**分组标识**而非随机批次；但**生物学含义数据本身推不出来** → 必须列进「需用户确认」清单，不要猜。
（本例：O 组 18/18 全带 C，OD 组 19/19 全不带，Y 组全不带 → 完全绑定。）

### 2.2 批次列是否嵌套于样本（判断有无跨组批次混杂）

```r
library(Matrix)  # 若用到
cat("library 数:", length(unique(md$library)), "| samplename 数:", length(unique(md$samplename)), "\n")
tab <- table(md$samplename, md$library)
cat("样本-文库一对一的样本数:", sum(rowSums(tab > 0) == 1), "/", nrow(tab), "\n")
```

**判据**：若**每个 library 只归属一个 samplename**（嵌套成立）→ 不存在「一个文库混多组」的跨组批次混杂；library 只是**样本内的技术分库**。
⚠️ **永远检查 `orig.ident`**：Seurat 合并后常全为 `SeuratProject`（零信息）→ 整合时 `group.by.vars` 要用 `samplename` / `library`，**不能用 `orig.ident`**。

### 2.3 组 × 亚群 / 组 × 样本 交叉表

```r
print(table(md$type, md$annotation_L3))   # 每组各亚群细胞数
print(table(md$type, md$samplename))      # 每组各样本细胞数（看配对完整性）
```

用途：① 发现**不完整配对**（本例 Y 组 9 Pre / 10 Post，多出 1 例无配对 Pre）；② 一眼看出**每样本细胞数是否太少**（本例 1–9 个/样本 → 判定为抽样测试子集，不能做组间统计）。

---

## 3. Step 3 — QC 分布 + 阈值筛查

```r
q <- function(x) sprintf("min=%.0f | Q1=%.0f | median=%.0f | Q3=%.0f | max=%.0f | mean=%.0f",
                         min(x), quantile(x,.25), median(x), quantile(x,.75), max(x), mean(x))
cat("nCount_RNA:", q(md$nCount_RNA), "\nnFeature_RNA:", q(md$nFeature_RNA), "\n")
cat("percent.mt:", q(md$percent.mt), "\npct_counts_ribo:", q(md$pct_counts_ribo), "\n")
cat(sum(md$nFeature_RNA < 500), sum(md$nCount_RNA < 1000), sum(md$percent.mt > 10), "\n")

# 按分组的中位数 —— 用 tapply，别用 aggregate（见下）
for (v in c("nCount_RNA","nFeature_RNA","percent.mt","pct_counts_ribo")) {
  cat(sprintf("%-16s", v)); print(round(tapply(md[[v]], md$type, median), 2))
}
```

🔴 **`aggregate(cbind(...) ~ type, data = md)` 会报 `non-numeric-alike variable(s) in data frame: type`** —— 该函数不适配字符型分组列。**一律改用 `tapply`**（`aggregate(samplename ~ type, ...)` 这类字符取值列同样会崩）。

---

## 4. Step 4 — MT% 真实性核查（推翻「列算错了」的猜测）

**动机**：当 `percent.mt` 中位数≈0 或明显偏离该组织常识（人骨骼肌通常 5–25%）时，第一反应容易是「这列是不是基于 SCT/已回归的矩阵算的」。**别猜，实测**：

```r
mtg <- grep("^MT-", rownames(obj), value = TRUE)          # MT 基因是否真在矩阵里
cat("^MT- 基因数:", length(mtg), "\n")
if (length(mtg) > 0) {
  cnt <- GetAssayData(obj, assay = "RNA", layer = "counts")[mtg, , drop = FALSE]
  tot <- Matrix::colSums(GetAssayData(obj, assay = "RNA", layer = "counts"))
  rec <- Matrix::colSums(cnt) / tot * 100
  cat(sprintf("按 counts 层重算 MT%%: median=%.2f%%  max=%.2f%%\n", median(rec), max(rec)))
  cat(sprintf("与 meta.data percent.mt 的相关性: r=%.4f\n", cor(rec, md$percent.mt)))
}
```

**判读**：
- `r ≈ 1.0000` → 该列**确为原始 counts 计算**，低 MT% 是**数据的真实特征**（提示上游做过去污染/去背景，或比对时过滤了 MT reads），**不是列算错**。
- 结论要写进报告：**这种数据不能用 MT% 过滤死细胞**（全组都极低，区分度为零）。
- 本例实测：37 个 `^MT-` 基因、重算 median 0.36% / max 3.21%、`r = 1.0000` → 推翻了「基于 SCT 计算」的初判。

⚠️ 这是**汇报前必须自查的一类错误**：对可疑数值先做一次可复算的核对，再写进结论。

---

## 5. Step 5 — 四联概览图（过 rail_review 的必需项）

base graphics，零依赖（不碰 ggplot2/egg，避开库路径问题）；一个 `draw()` 函数 + 三种格式各调一次：

```r
grp  <- c("Y_Pre","Y_Post","O_Pre","O_Post","OD_Pre","OD_Post")   # 与数据实际水平一致
cols <- c("#4C72B0","#8CB4E0","#DD8452","#F0B27A","#55A868","#95D5A0")
gfac <- factor(md$type, levels = grp)

draw <- function() {
  par(mfrow = c(2,2), mar = c(6,5,3.2,1.5), las = 1)
  n  <- sapply(grp, function(t) sum(md$type == t)); bp <- barplot(n, col = cols, main = "A  各组细胞数", ylab = "细胞数", names.arg = grp, ylim = c(0, max(n)*1.18)); text(bp, n, n, pos = 3, cex = .85, xpd = NA)
  ns <- sapply(grp, function(t) length(unique(md$samplename[md$type == t]))); bp2 <- barplot(ns, col = cols, main = "B  各组样本数", ylab = "样本数", names.arg = grp, ylim = c(0, max(ns)*1.18)); text(bp2, ns, ns, pos = 3, cex = .85, xpd = NA)
  boxplot(md$nFeature_RNA ~ gfac, col = cols, main = "C  每细胞基因数 (nFeature_RNA)", ylab = "基因数/细胞")
  boxplot(md$percent.mt ~ gfac, col = cols, main = "D  线粒体基因比例 (%)", ylab = "MT%"); abline(h = 10, lty = 2, col = "red")
}
png(f, width = 2600, height = 2000, res = 300); draw(); dev.off()
pdf(f2, width = 9, height = 7);                 draw(); dev.off()
tiff(f3, width = 2600, height = 2000, res = 300, compression = "lzw"); draw(); dev.off()
print(file.info(list.files(fig_dir, pattern = "overview", full.names = TRUE)))   # 非空验证
```

出图后**直接重审 `rail_review(post)` 即通过**，不要再回头重跑统计（静态判定，重跑不改结论）。

---

## 6. Step 6 — 交付物布局

```
results/<sid>/
├── results/eda_report.md                      # 完整报告（规模/分组/亚群/QC/风险点/下一步）
├── results/<name>_group_summary.csv           # 各组：细胞数/样本数/年龄/QC 中位数
├── results/<name>_celltype_by_group.csv       # 亚群 × 组 细胞数矩阵
├── results/<name>_cell_metadata.csv           # 每细胞 QC + 标签明细
├── results/<name>_sample_group_map.csv        # 样本 → 组/年龄/批次 映射（供复核）
├── figures/<name>_EDA_overview.{png,pdf,tiff}
└── scripts/inspect_<name>_eda.R  +  fig_<name>_EDA_overview.R
```

报告里**必须单列一节「需用户确认」**（分组后缀语义 / OD 组定义 / 是否改用更大子集），不要把推断当结论写进正文。

---

## 7. 辩论门控的收尾规则

EDA 后门控通常触发 **L1 轻量辩论**，裁决常以 `need_more_info` 收尾并列出缺失证据。**裁决里 `owner=ai` 的待办要当轮就做**（本例：分组映射核查 §2.1 + MT 真实性核查 §4 补做后，报告质量直接上一个台阶），只把清单转述给用户 = 没完成。`owner=user` 的（分组语义确认）才写进「需用户确认」。

---

## 8. 实测样例（MF_120，2026-09-24）

| 项 | 值 |
|---|---|
| 规模 | 120 细胞 × 51,227 基因；assays RNA+SCT；reductions pca/harmony/umap |
| 元数据 | 50 列；`Idents == annotation_L3`（已验证一致） |
| 分组 | Y/O/OD × Pre/Post = 6 组；43 样本；全 Female |
| 各样本细胞数 | **1–9 个** → 判定为抽样测试子集，**不能做组间统计** |
| QC | nCount 中位 5,582；nFeature 中位 2,584；MT% 中位 0.36%；按 nFeature<500 / nCount<1000 / MT>10% 筛查 **剔除 0 个细胞** |
| 关键发现 | ① `C` 后缀与 O/OD 分组 100% 绑定但语义待确认；② MT% 经 counts 重算 r=1.0000 是真实值；③ `orig.ident` 全为 `SeuratProject`、library 嵌套于 samplename |