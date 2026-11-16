## ============================================================
## 层级注释对账探针：亚群对象 vs 父对象大群
##   —— 六级对账（计数/barcode 交集/反向覆盖/闭合/中间层交叉/两级加和）
##
## 用法（集群作业，别交互式逐个读）：
##   Rscript --vanilla check_annotation_hierarchy.R <父对象.rds> <outdir> <名>=<路径> [<名>=<路径>...]
## 例：
##   Rscript --vanilla check_annotation_hierarchy.R \
##     /path/Muscle_exercise_clean_annotation_umap.rds /path/out \
##     MF=/path/MF_clean_annotation_umap.rds MuSC=/path/MuSC_....rds
##
## 设计要点（都是实测踩出来的，改脚本别改掉）：
##   * 每读完一个对象立刻 write.csv 落盘 → 进程中断也不丢已完成结果（实测被 kill 过）
##   * 每个对象后 rm+gc → 23.5 GB 的 MF 不释放会把后面的对象一起撑爆
##   * 结尾打 ALL DONE → grep 得到=跑完，grep 不到=中途挂了（区分「跑完」与「被杀」）
##   * L1_COL 与 L2_COL 是「预期名」，实际列名靠实际探测；不一致要报差异而不是猜
## ============================================================
suppressPackageStartupMessages({
  library(Seurat)
  library(SeuratObject)
})
cat("== R:", R.version.string, " Seurat:", as.character(packageVersion("Seurat")), "\n")

args <- commandArgs(trailingOnly = TRUE)
if (length(args) < 3) stop("用法: check_annotation_hierarchy.R <父对象> <outdir> <名>=<路径> ...")

parent_f <- args[1]
outdir   <- args[2]
dir.create(outdir, showWarnings = FALSE, recursive = TRUE)

files <- list()
for (a in args[-(1:2)]) {
  kv <- strsplit(a, "=", fixed = TRUE)[[1]]
  files[[kv[1]]] <- paste(kv[-1], collapse = "=")
}

## ---- 配置：父对象的大群列名，以及「亚群名 -> 父对象大群类目」映射 ----
L1_COL <- "Celltype"            # 父对象的大群列（注意可能同时存在只差大小写的 celltype！）
## 期望映射；留空则由脚本按「细胞数最接近的大群」提示，但**必须人工确认**
EXPECT <- c()                  # 例: c(MF="Muscle fibers", MuSC="Muscle stem cells")

## ---- 读父对象，建基准（父对象自己的频数表才是基准，不是记忆）----
cat("\n===== 父对象 =====\n", parent_f, "\n")
parent <- readRDS(parent_f)
cat("dim:", dim(parent)[1], "x", dim(parent)[2], "\n")

pd <- parent@meta.data
cat("meta cols:", paste(colnames(pd), collapse = ", "), "\n")

## 🔴 并排打印所有「看着像分类」的列及其类目数 —— 防止用错层级（Celltype vs celltype）
for (cn in grep("annotation|Annotation|level|Level|celltype|Celltype|^type$",
                colnames(pd), value = TRUE)) {
  cat(sprintf("  [父对象] %-24s %d levels\n", cn, length(unique(as.character(pd[[cn]])))))
}
if (!L1_COL %in% colnames(pd)) stop("父对象没有列 ", L1_COL, "；请先看上面的真实列名再改 L1_COL")

pb <- rownames(pd)
l1 <- setNames(as.character(pd[[L1_COL]]), pb)     # barcode -> 大群
cat("\n---- table(parent$", L1_COL, ") ----\n", sep = "")
tb <- sort(table(l1), decreasing = TRUE)
for (i in seq_along(tb)) cat(sprintf("      %-45s %8d\n", names(tb)[i], as.integer(tb[i])))
cat("total:", length(l1), "\n")
## 用户口径（例：排除 Adipocyte）—— 请在此显式写出，基数用「总数 − 被排除」
EXCLUDE <- character(0)        # 例: c("Adipocyte cells")
BASELINE <- length(l1) - sum(l1 %in% EXCLUDE)
cat("对账基数（总数 − 被排除）:", BASELINE, "\n")
## 顺带落父对象 meta，供回填轮直接用（barcode 必须落）
pd$barcode <- pb
write.csv(pd, file.path(outdir, "meta_PARENT.csv"), row.names = FALSE)

summ <- data.frame()
flush_summ <- function() if (nrow(summ)) {
  write.csv(summ, file.path(outdir, "annotation_columns_summary.csv"), row.names = FALSE)
}

## ---- 逐对象对账 ----
for (nm in names(files)) {
  f <- files[[nm]]
  cat("\n\n########################################################\n")
  cat("### ", nm, " :: ", f, "\n")
  cat("########################################################\n")
  if (!file.exists(f)) { cat("!!! FILE NOT FOUND\n"); next }

  obj <- tryCatch(readRDS(f), error = function(e) {
    cat("!!! READ ERROR:", conditionMessage(e), "\n"); NULL
  })
  if (is.null(obj)) next

  md <- obj@meta.data
  bc <- rownames(md)
  cat("dim (gene x cell):", dim(obj)[1], "x", dim(obj)[2], "\n")
  if (inherits(obj, "Seurat")) cat("assays:", paste(Assays(obj), collapse = ", "), "\n")
  cat("meta cols:", paste(colnames(md), collapse = ", "), "\n")

  ## ① 计数 + ②③ barcode 交集/反向覆盖
  exp_g <- if (length(EXPECT) && nm %in% names(EXPECT)) EXPECT[[nm]] else NA
  cat("== barcode 对账")
  if (!is.na(exp_g)) cat(" [", exp_g, "]", sep = "")
  cat("\n   本对象细胞数            :", length(bc), "\n")
  cat("   在主对象中命中(barcode) :", sum(bc %in% pb), "\n")
  if (!is.na(exp_g)) {
    gset <- pb[l1 == exp_g]
    cat("   与主对象该大群交集      :", sum(bc %in% gset), "\n")
    cat("   主对象该大群被覆盖      :", sum(gset %in% bc), "/", length(gset),
        sprintf(" (%.1f%%)\n", 100 * sum(gset %in% bc) / max(1, length(gset))))
    cat("   主对象该大群细胞数      :", length(gset), "\n")
    if (length(bc) != length(gset) || sum(bc %in% gset) != length(bc))
      cat("   ⚠️ 与预期大群不一致 —— 先用 barcode 交集定位差异，不要直接合并\n")
  } else {
    ## 未声明映射：提示「细胞数最接近」的大群，供人工确认
    cand <- sort(sapply(split(pb, l1), function(x) abs(length(x) - length(bc))))[1:3]
    cat("   (未声明映射) 细胞数最接近的大群:",
        paste(sprintf("%s(差%d)", names(cand), as.integer(cand)), collapse = ", "), "\n")
  }

  ## 落 meta（中断也不丢）
  md$barcode <- bc
  write.csv(md, file.path(outdir, paste0("meta_", nm, ".csv")), row.names = FALSE)

  ## ③ 低基数列频数（注释列必然命中；>80 唯一值的列明细略）
  for (cn in colnames(md)) {
    if (cn == "barcode") next
    u <- unique(as.character(md[[cn]]))
    if (length(u) <= 80 && length(u) > 1) {
      cat("\n--- [", cn, "] ", length(u), " levels\n", sep = "")
      tb2 <- sort(table(md[[cn]], useNA = "ifany"), decreasing = TRUE)
      for (i in seq_along(tb2)) cat(sprintf("      %-45s %8d\n", names(tb2)[i], as.integer(tb2[i])))
    }
  }

  ## 注释类列汇总（哪个对象用哪个列名 —— 回填映射表就从这里来）
  for (cn in grep("annotation|Annotation|level|Level|celltype|Celltype",
                  colnames(md), value = TRUE)) {
    summ <- rbind(summ, data.frame(
      file = nm, n_cells = ncol(obj), column = cn,
      n_levels = length(unique(as.character(md[[cn]]))),
      levels = paste(sort(unique(as.character(md[[cn]]))), collapse = "|"),
      stringsAsFactors = FALSE))
  }
  flush_summ()
  cat(">>> 落盘完成:", nm, "\n")
  rm(obj, md); gc()          # 🔴 必须释放，否则大对象累积撑爆作业
}

flush_summ()
cat("\n===== SUMMARY TABLE =====\n"); print(summ)
cat("\n===== ALL DONE =====\n")