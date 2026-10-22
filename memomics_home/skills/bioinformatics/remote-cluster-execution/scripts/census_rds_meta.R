## census_rds_meta.R — 集群 rds 对象普查：逐文件细胞数 + 每个 meta 列的类目数
## 用途：几十个候选 rds 里找「满足某个条件」的那一个（细胞数 N / 注释 K 类）——见 remote-cluster-execution 铁规 12.1
## 用法：Rscript --vanilla census_rds_meta.R <目录> [子目录 …] > census.log 2>&1
## 例    Rscript --vanilla census_rds_meta.R /hwfssz3/PS_JLU/liuyuxuan3/Muscle 0326 Merge
##
## 投递：remote_cluster push → remote_cluster submit "Rscript --vanilla census_rds_meta.R <目录> … > census.log 2>&1"
## 收尾：remote_cluster pull census.log → 本机 execute_code 正则切块解析（不要整份读进上下文）
##   快速先捞：tail -c 1500 census.log   # 确认有 ==== ALL DONE ====
##              grep -n 'n=2[0-9]' census.log   # 先定位类目数落在目标区间的列
##
## ⚠️ 两条写死的纪律（都踩过，别改）：
##   1) 文件清单**自发现**（list.files），不要手写路径数组 —— 手写清单会静默漏掉最大的那个候选
##   2) 开头**必须** library(Seurat)：v4 对象的 Seurat 类定义在 Seurat 包，不加载就报
##      "unable to find required package 'Seurat'"，与 v5 对象混放会造成「一半文件读不了」的假象
options(warn = 1)

args <- commandArgs(trailingOnly = TRUE)
if (length(args) < 1) stop("用法: Rscript --vanilla census_rds_meta.R <目录> [子目录 …]")
base <- args[1]
subdirs <- if (length(args) > 1) args[-1] else character(0)

# ---- 纪律 2：Seurat 先加载（v4/v5 混放的差异式失败靠这一行消除）----
if (requireNamespace("Seurat", quietly = TRUE)) {
  suppressPackageStartupMessages(library(Seurat))
  cat("Seurat version:", as.character(packageVersion("Seurat")), "\n")
} else {
  cat("WARN: Seurat 不可用，Seurat v4 对象会读失败（报 unable to find required package 'Seurat'）\n")
}

# ---- 纪律 1：文件清单自发现 + 开头打印全量清单（漏没漏一眼可见）----
scan_dir <- function(d) {
  if (!dir.exists(d)) return(character(0))
  list.files(d, pattern = "\\.rds$", full.names = TRUE)
}
dirs <- c(base, file.path(base, subdirs))
all_files <- unique(unlist(lapply(dirs, scan_dir)))

cat("\n==== 目录下全部 rds（含体积）====\n")
cat("扫描目录:", paste(dirs, collapse = " | "), "\n")
if (length(all_files) == 0) { cat("  (无 rds)\n"); quit(status = 1) }
for (f in all_files) cat(sprintf("  %8.2f GB  %s\n", file.size(f) / 2^30, f))

cat("\nSTART", format(Sys.time()), "| 文件数:", length(all_files), "\n")

for (f in all_files) {
  gb <- round(file.size(f) / 2^30, 2)
  cat("\n########", sub(paste0(base, "/"), "", f), "|", gb, "GB\n")
  res <- tryCatch({
    x <- readRDS(f)
    if (inherits(x, "Seurat")) {
      cat("SEURAT | genes:", nrow(x), "| cells:", ncol(x), "\n")
      md <- x@meta.data
      cat("COLS:", paste(colnames(md), collapse = " | "), "\n")
      for (cn in colnames(md)) {
        u <- unique(as.character(md[[cn]]))
        cat(sprintf("  [%s] n=%d", cn, length(u)))
        if (length(u) <= 60) cat(" ::", paste(u, collapse = ","))   # 小基数才列取值
        cat("\n")
      }
    } else {
      # 非 Seurat：把类/槽/名字打出来，别默默跳过
      cat("CLASS:", paste(class(x), collapse = ","), "\n")
      if (isS4(x)) cat("SLOTS:", paste(head(slotNames(x), 40), collapse = ","), "\n")
      if (is.list(x)) cat("NAMES:", paste(head(names(x), 40), collapse = ","), "\n")
    }
    rm(x); invisible(gc())
    "ok"
  }, error = function(e) paste("ERROR:", conditionMessage(e)))
  cat("STATUS:", res, "\n")
  cat("MEM_FREE_GB:", round(as.numeric(system("free -g | awk 'NR==2{print $4}'", intern = TRUE)), 1), "\n")
}

cat("\n==== ALL DONE", format(Sys.time()), "====\n")