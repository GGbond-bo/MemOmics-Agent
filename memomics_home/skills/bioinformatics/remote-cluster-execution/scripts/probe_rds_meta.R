#!/usr/bin/env Rscript
# probe_rds_meta.R —— 打一个「已加载对象」的身份指纹：维度 / assay / reducers / 每列元数据基数与取值。
#
# 为什么要有它：远端多 GB rds 的「身份核对」（判断哪个文件对上用户口述的细胞数/注释数）时，
# 关键信息全在 meta.data 的列基数里 —— 低基数的列就是注释列，n= 就是类目数。
#
# 用法 A（推荐，集群常驻会话，对象已在内存，不回读文件）：
#   remote_cluster(action="session_exec", session_id="s-...",
#                  code=paste(readLines("<此脚本路径>"), collapse="\n"))
#   ⛔ 先把下面 OBJ 改成会话里的真实对象名。
#
# 用法 B（Rscript 独立跑，需自己先 readRDS）：
#   Rscript probe_rds_meta.R /path/to/x.rds
#
# ⛔ 绝不要在这个脚本里写 quit()/q() —— 用法 A 会被 daemon 直接执行，
#    退出码会杀掉常驻会话、丢掉 37 GB 内存对象。只用 cat() 输出。

OBJ <- "muscle_all"   # <-- 改成会话里的对象名（用法 B 时忽略）

args <- commandArgs(trailingOnly = TRUE)
if (length(args) >= 1 && !is.null(args[1]) && nzchar(args[1])) {
  cat("readRDS:", args[1], "\n")
  obj <- readRDS(args[1])
  OBJ <- "obj"
} else {
  obj <- get(OBJ, envir = globalenv())
}

cat("object:", OBJ, "| class:", paste(class(obj), collapse = "/"), "\n")

md <- NULL
if (inherits(obj, "Seurat")) {
  cat("dim:", nrow(obj), "genes x", ncol(obj), "cells\n")   # <-- 细胞数在这
  cat("assays:", paste(names(obj@assays), collapse = ", "), "\n")
  cat("reductions:", paste(names(obj@reductions), collapse = ", "), "\n")
  md <- obj@meta.data
} else if (is.matrix(obj)) {
  cat("dim:", paste(dim(obj), collapse = " x "), "\n")
} else if (is.data.frame(obj)) {
  cat("dim:", paste(dim(obj), collapse = " x "), "\n")
  md <- obj
} else {
  cat("dim:", paste(dim(obj), collapse = " x "), "\n")
  md <- tryCatch(as.data.frame(obj), error = function(e) NULL)
}

if (is.null(md) || ncol(md) == 0) {
  cat("没有可打的列（非 Seurat / 非 data.frame 视图）—— 到此为止。\n")
} else {
  cat("meta cols:", ncol(md), "\n----\n")
  for (cn in colnames(md)) {
    v  <- md[[cn]]
    nu <- length(unique(v))
    if (nu <= 60) {
      # 低基数 = 注释/分组列，直接把取值全列出来
      cat(sprintf("%-26s [%-9s] n=%d :: %s\n", cn, class(v)[1], nu,
                  paste(as.character(unique(v)), collapse = " | ")))
    } else {
      cat(sprintf("%-26s [%-9s] n=%d (high-card)\n", cn, class(v)[1], nu))
    }
  }
}

if (inherits(obj, "Seurat")) {
  cat("---- Idents levels:", length(levels(obj)), "\n")
  cat(paste(levels(obj), collapse = " | "), "\n")
}
cat("=== PROBE DONE ===\n")