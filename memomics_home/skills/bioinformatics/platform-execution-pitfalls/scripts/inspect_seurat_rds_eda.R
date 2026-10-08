#!/usr/bin/env Rscript
# =============================================================================
# inspect_seurat_rds_eda.R — Seurat .rds 只读数据体检（结构 + 元数据语义审计 + QC + 四联图）
#
# 用途：用户丢来一个 Seurat .rds 说「打开看看有多少细胞/基因、有哪些样本和分组」时的标准探针。
#       只读：不做任何过滤/修改。产出报告表 + 四联概览图（rail_review(post) 要求 ≥1 图）。
#
# 用法：
#   Rscript inspect_seurat_rds_eda.R <obj.rds> <out_dir> [分组列] [样本列]
#   例：Rscript inspect_seurat_rds_eda.R E:/data/MF_120.rds E:/MemOmics-Agent/results/<sid> type samplename
#   也可在持久内核里 exec: source('.../inspect_seurat_rds_eda.R') 前先设 ARGS 变量（见文件末）
#
# 约定（务必遵守，否则会踩坑）：
#   * 不使用 __file__（持久内核 exec 时不注入该变量，会 NameError）
#   * .libPaths() 必须排在第一条 library() 之前
#   * 按分组聚合用 tapply —— aggregate(cbind(...) ~ 字符型分组列) 会报
#     "non-numeric-alike variable(s) in data frame: <列名>"
#   * 四联图用 base graphics，零依赖（不碰 ggplot2/egg）
# =============================================================================

ARGS <- if (exists("ARGS", inherits = TRUE)) ARGS else commandArgs(trailingOnly = TRUE)
if (length(ARGS) < 2) {
  cat("用法: Rscript inspect_seurat_rds_eda.R <obj.rds> <out_dir> [分组列] [样本列]\n")
  cat("示例: Rscript inspect_seurat_rds_eda.R E:/data/MF_120.rds E:/MemOmics-Agent/results/sid type samplename\n")
  quit(status = 0)   # 不是错误：只是没给参数
}
rds_path <- ARGS[1]
out_dir  <- ARGS[2]
grp_col  <- if (length(ARGS) >= 3 && nzchar(ARGS[3])) ARGS[3] else NA_character_
smp_col  <- if (length(ARGS) >= 4 && nzchar(ARGS[4])) ARGS[4] else NA_character_

.libPaths(c('E:/R-libs/R-4.5.3', .libPaths()))     # 必须在 library() 之前
suppressPackageStartupMessages({ library(Seurat); library(Matrix) })
options(width = 200)

fig_dir <- file.path(out_dir, "figures")
dir.create(file.path(out_dir, "results"), recursive = TRUE, showWarnings = FALSE)
dir.create(fig_dir, recursive = TRUE, showWarnings = FALSE)

cat("========================================================================\n")
cat("文件:", rds_path, "|", round(file.size(rds_path) / 1024^2, 2), "MB\n")

obj <- readRDS(rds_path)
md  <- obj@meta.data

# ---- 1. 结构 --------------------------------------------------------------
cat("\n### 1. 结构 ###\n")
cat("class:", paste(class(obj), collapse = "/"), "\n")
cat(sprintf("细胞数 = %d | 基因数 = %d (assay=%s)\n", ncol(obj), nrow(obj), DefaultAssay(obj)))
cat("assays:", paste(Assays(obj), collapse = ", "), "\n")
cat("reductions:", paste(Reductions(obj), collapse = ", "), "\n")
cat("Idents levels:", paste(head(levels(Idents(obj)), 30), collapse = " | "), "\n")
cat("meta.data 列 (", ncol(md), "):", paste(colnames(md), collapse = ", "), "\n")

# 自动挑分组列/样本列（未显式指定时）
pick_col <- function(cands) { h <- intersect(cands, colnames(md)); if (length(h)) h[1] else NA_character_ }
if (is.na(grp_col)) grp_col <- pick_col(c("type","group","condition","Group","Timepoint","stage"))
if (is.na(smp_col)) smp_col <- pick_col(c("samplename","sample","Sample","orig.ident","batch"))
cat("分组列 =", grp_col, "| 样本列 =", smp_col, "\n")

# ---- 2. 元数据语义审计 -----------------------------------------------------
cat("\n### 2. 元数据语义审计 ###\n")
if (nzchar(grp_col) && !is.na(grp_col)) {
  gv <- md[[grp_col]]
  cat("\n-- 分组分布 --\n");           print(sort(table(gv), decreasing = TRUE))
  if (!is.na(smp_col)) {
    cat("\n-- 分组 x 样本 --\n");       print(table(gv, md[[smp_col]]))
    cat("\n-- 每组样本数 / 细胞数 --\n")
    for (t in unique(as.character(gv))) {
      d <- md[as.character(gv) == t, ]
      cat(sprintf("  %-10s 细胞=%3d 样本=%2d 年龄=%s\n", t, nrow(d),
                  length(unique(d[[smp_col]])),
                  if ("age" %in% colnames(md)) paste(sort(unique(d$age)), collapse = ",") else "NA"))
    }
    # 每样本细胞数（判断是否抽样测试子集）
    cs <- table(md[[smp_col]])
    cat(sprintf("-- 每样本细胞数: min=%d median=%.0f max=%d  (min<10 ⇒ 抽样测试子集，不可做组间统计)\n",
                min(cs), median(cs), max(cs)))
  }
  # 命名后缀 vs 分组：是否 100% 绑定（绑定但语义未知 ⇒ 必须问用户）
  if (!is.na(smp_col)) {
    sm <- as.character(md[[smp_col]])
    suf <- ifelse(grepl("C", sub("^[A-Za-z]+_", "", sm)), "has_C", "no_C")
    cat("\n-- 分组 x 样本名含 C 后缀 --\n"); print(table(gv, suf))
    cat("(完全绑定 = 后缀是分组标识；生物学含义数据本身推不出 ⇒ 列入「需用户确认」)\n")
  }
}
# 批次列是否嵌套于样本（有无跨组批次混杂）
cat("\n-- 批次结构 --\n")
for (b in intersect(c("library","batch","Batch","orig.ident"), colnames(md))) {
  cat(sprintf("  %s: %d unique", b, length(unique(md[[b]]))))
  if (!is.na(smp_col)) {
    tb <- table(md[[smp_col]], md[[b]])
    cat(sprintf(" | 样本-该列一对一: %d/%d | 每个 %s 归属样本数: %s",
                sum(rowSums(tb > 0) == 1), nrow(tb), b,
                paste(sort(unique(colSums(tb > 0))), collapse = "/")))
  }
  cat("\n")
}
cat("  ⚠️ orig.ident 全为单一值时无批次信息 ⇒ 整合用 samplename/library，别用 orig.ident\n")

# ---- 3. QC ----------------------------------------------------------------
cat("\n### 3. QC ###\n")
q <- function(x) sprintf("min=%.0f | Q1=%.0f | median=%.0f | Q3=%.0f | max=%.0f | mean=%.0f",
                         min(x), quantile(x,.25), median(x), quantile(x,.75), max(x), mean(x))
for (v in intersect(c("nCount_RNA","nFeature_RNA","percent.mt","pct_counts_ribo"), colnames(md))) {
  cat(sprintf("%-16s %s\n", v, q(md[[v]])))
}
cat("阈值筛查 → 剔除数: ")
cat(sprintf("nFeature<500:%d  nCount<1000:%d  MT>10%%:%d\n",
            sum(md$nFeature_RNA < 500, na.rm = TRUE), sum(md$nCount_RNA < 1000, na.rm = TRUE),
            sum(md$percent.mt > 10, na.rm = TRUE)))
if (nzchar(grp_col) && !is.na(grp_col)) {
  cat("\n按分组中位数（tapply，勿用 aggregate）:\n")
  for (v in intersect(c("nCount_RNA","nFeature_RNA","percent.mt"), colnames(md))) {
    cat(sprintf("%-16s", v)); print(round(tapply(md[[v]], md[[grp_col]], median), 2))
  }
}

# ---- 4. MT% 真实性核查 ------------------------------------------------------
cat("\n### 4. MT% 真实性核查 ###\n")
mtg <- grep("^MT-", rownames(obj), value = TRUE)
cat("^MT- 基因数:", length(mtg), "\n")
if (length(mtg) > 0 && "percent.mt" %in% colnames(md)) {
  cnt <- GetAssayData(obj, assay = DefaultAssay(obj), layer = "counts")[mtg, , drop = FALSE]
  tot <- Matrix::colSums(GetAssayData(obj, assay = DefaultAssay(obj), layer = "counts"))
  rec <- Matrix::colSums(cnt) / tot * 100
  cat(sprintf("按 counts 重算 MT%%: median=%.2f%% max=%.2f%%\n", median(rec), max(rec)))
  cat(sprintf("与 meta.data$percent.mt 相关性: r=%.4f\n", cor(rec, md$percent.mt)))
  cat("判读: r≈1 ⇒ 该列是原始 counts 计算、低 MT% 是真实特征（非列算错）⇒ 不可用 MT% 过滤死细胞\n")
}

# ---- 5. 亚群 / 注释分布 ----------------------------------------------------
cat("\n### 5. 注释分布 ###\n")
for (cl in intersect(c("celltype","annotation","annotation_L2","annotation_L3","seurat_clusters"),
                     colnames(md))) {
  cat("--", cl, "--\n"); print(sort(table(md[[cl]]), decreasing = TRUE))
}
cat("Idents == annotation_L3 :",
    identical(as.character(Idents(obj)), as.character(md$annotation_L3)), "\n")
cat("\nNA 检查:\n"); print(colSums(is.na(md)))

# ---- 6. 落盘 --------------------------------------------------------------
nm <- sub("[.][Rr][Dd][Ss]$", "", basename(rds_path))
if (nzchar(grp_col) && !is.na(grp_col)) {
  g <- do.call(rbind, lapply(unique(as.character(md[[grp_col]])), function(t) {
    d <- md[as.character(md[[grp_col]]) == t, ]
    data.frame(group = t, n_cells = nrow(d),
               n_samples = if (!is.na(smp_col)) length(unique(d[[smp_col]])) else NA_integer_,
               age_range = if ("age" %in% colnames(md)) paste0(min(d$age), "-", max(d$age)) else NA_character_,
               med_nCount = round(median(d$nCount_RNA)), med_nFeature = round(median(d$nFeature_RNA)),
               med_MTpct = round(median(d$percent.mt), 2), row.names = NULL)
  }))
  write.csv(g, file.path(out_dir, "results", paste0(nm, "_group_summary.csv")), row.names = FALSE)
}
if ("annotation_L3" %in% colnames(md) && nzchar(grp_col) && !is.na(grp_col)) {
  tb <- as.data.frame.matrix(table(md$annotation_L3, md[[grp_col]]))
  tb <- cbind(celltype = rownames(tb), tb, total = rowSums(tb)); rownames(tb) <- NULL
  write.csv(tb, file.path(out_dir, "results", paste0(nm, "_celltype_by_group.csv")), row.names = FALSE)
}
if (!is.na(smp_col)) {
  mp <- unique(md[, c(smp_col, intersect(c(grp_col,"age","sex","library"), colnames(md))), drop = FALSE])
  mp$n_cells <- as.integer(table(md[[smp_col]])[as.character(mp[[smp_col]])])
  write.csv(mp, file.path(out_dir, "results", paste0(nm, "_sample_group_map.csv")), row.names = FALSE)
}
write.csv(md, file.path(out_dir, "results", paste0(nm, "_cell_metadata.csv")), row.names = FALSE)

# ---- 7. 四联概览图（base graphics，零依赖）--------------------------------
if (nzchar(grp_col) && !is.na(grp_col)) {
  grp <- unique(as.character(md[[grp_col]]))
  pal <- c("#4C72B0","#8CB4E0","#DD8452","#F0B27A","#55A868","#95D5A0","#C44E52","#8172B3")
  cols <- rep(pal, length.out = length(grp))
  gfac <- factor(as.character(md[[grp_col]]), levels = grp)
  draw <- function() {
    par(mfrow = c(2,2), mar = c(6,5,3.2,1.5), las = 1)
    n <- sapply(grp, function(t) sum(as.character(md[[grp_col]]) == t))
    bp <- barplot(n, col = cols, main = "A  各组细胞数", ylab = "细胞数", names.arg = grp,
                  ylim = c(0, max(n) * 1.18)); text(bp, n, n, pos = 3, cex = .85, xpd = NA)
    if (!is.na(smp_col)) {
      ns <- sapply(grp, function(t) length(unique(md[[smp_col]][as.character(md[[grp_col]]) == t])))
      bp2 <- barplot(ns, col = cols, main = "B  各组样本数", ylab = "样本数", names.arg = grp,
                     ylim = c(0, max(ns) * 1.18)); text(bp2, ns, ns, pos = 3, cex = .85, xpd = NA)
    } else plot.new()
    boxplot(md$nFeature_RNA ~ gfac, col = cols, main = "C  每细胞基因数 (nFeature_RNA)", ylab = "基因数/细胞")
    boxplot(md$percent.mt  ~ gfac, col = cols, main = "D  线粒体基因比例 (%)", ylab = "MT%")
    abline(h = 10, lty = 2, col = "red")
  }
  f0 <- file.path(fig_dir, paste0(nm, "_EDA_overview"))
  png(paste0(f0, ".png"), width = 2600, height = 2000, res = 300); draw(); dev.off()
  pdf(paste0(f0, ".pdf"), width = 9, height = 7);                   draw(); dev.off()
  tiff(paste0(f0, ".tiff"), width = 2600, height = 2000, res = 300, compression = "lzw"); draw(); dev.off()
  fi <- file.info(list.files(fig_dir, pattern = nm, full.names = TRUE))
  cat("\n### 产出图（非空验证）###\n"); print(data.frame(file = basename(rownames(fi)), KB = round(fi$size/1024, 1)))
}
cat("\n=== 完成。results/ 与 figures/ 均已落盘 ===\n")
cat("→ 接着跑 rail_review(phase='post', output_dir=<out_dir 目录>, code_executed=<本脚本全文>)\n")
cat("→ 报告须单列「需用户确认」节（分组后缀语义 / 是否改用更大子集）\n")