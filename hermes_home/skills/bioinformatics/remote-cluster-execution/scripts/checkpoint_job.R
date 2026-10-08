#!/usr/bin/env Rscript
# ============================================================================
# 方案 A 模板：长任务 = 一个作业跑完整链 + 检查点（2026-10-08 用户拍板）
#
# 为什么要有这个模板（用户原话）：
#   「我要跑长程任务的时候，我总不能每次都读取一次吧？而且我这个才 600M，
#     我的 MF 可是有 10G，难道你也要每次读一下？」
# 解法不是「持久进程」，而是：
#   ① 一个作业跑完整条链（不拆成 n 个小作业 → 大输入只 read 一次）
#   ② 大输入读完立刻落「精简缓存」（reductions+meta），后续步骤/重跑读缓存
#   ③ 每个阶段落检查点（含参数指纹），指纹一致就跳过 → 崩了从断点续
#
# 用法：Rscript checkpoint_job.R <INPUT.rds> <WORKDIR> [参数...]
#   WORKDIR 下会生成：
#     cache/light.rds      ← 精简缓存（≈原文件 5%）
#     ckpt/<stage>.done    ← 阶段检查点 + 参数指纹
#     out/                 ← 产物
#     日志走 stdout（含 #TASK: 打点，兼容 memomics task_run.py）
# ============================================================================

suppressPackageStartupMessages({ library(Seurat) })

args    <- commandArgs(trailingOnly = TRUE)
if (length(args) < 2) stop("用法: Rscript checkpoint_job.R <INPUT.rds> <WORKDIR>")
INPUT   <- normalizePath(args[1], mustWork = TRUE)
WORKDIR <- args[2]
PARAMS  <- if (length(args) > 2) args[3:length(args)] else character(0)

CACHE_DIR <- file.path(WORKDIR, "cache");  dir.create(CACHE_DIR, recursive = TRUE, showWarnings = FALSE)
CKPT_DIR  <- file.path(WORKDIR, "ckpt");   dir.create(CKPT_DIR,  recursive = TRUE, showWarnings = FALSE)
OUT_DIR   <- file.path(WORKDIR, "out");    dir.create(OUT_DIR,   recursive = TRUE, showWarnings = FALSE)
LIGHT     <- file.path(CACHE_DIR, "light.rds")

say  <- function(...) cat(sprintf(...), "\n", sep = "")
stage <- function(s) cat(sprintf("#TASK:STAGE %s\n", s))
prog  <- function(p, msg) cat(sprintf("#TASK:PROGRESS %.2f %s\n", p, msg))
param <- function(k, v) cat(sprintf("#TASK:PARAM %s=%s\n", k, v))
outp  <- function(p) cat(sprintf("#TASK:OUTPUT %s\n", p))
mb <- function(p) round(file.info(p)$size / 1024^2, 1)

# ---- 检查点：参数指纹一致 = 这一步已完成，直接跳过（断点续跑的核心） --------
# 只用 base R（md5sum 打在参数文本上），不假设装了什么包
param_fp <- function(...) {
  f <- tempfile(); writeLines(as.character(list(...)), f)
  h <- unname(tools::md5sum(f)); unlink(f); h
}
done_file <- function(name) file.path(CKPT_DIR, paste0(name, ".done"))
is_done <- function(name, fp) {
  f <- done_file(name)
  file.exists(f) && identical(readLines(f, warn = FALSE)[1], fp)
}
mark_done <- function(name, fp) writeLines(fp, done_file(name))
run_stage <- function(name, fp, expr) {          # expr 是表达式（惰性，跳过时不求值）
  if (is_done(name, fp)) { say("[skip] %s：检查点命中（参数未变）", name); return(invisible(FALSE)) }
  say("[run ] %s", name); force(expr); mark_done(name, fp); invisible(TRUE)
}

say("=== 作业开始 %s ===", format(Sys.time()))
say("输入: %s (%s MB)", INPUT, mb(INPUT))
say("工作目录: %s", WORKDIR)
if (length(PARAMS)) say("参数: %s", paste(PARAMS, collapse = " "))
param("input", INPUT); param("workdir", WORKDIR)
param("input_mb", mb(INPUT))

# ============================ Stage 0：读一次 → 精简缓存 ====================
# 这一步是「不再重复读 10GB」的关键：第一次读原文件，之后全部读 light.rds
stage("0_load_cache")
prog(0.02, "load-or-build light cache")
t0 <- Sys.time()
if (file.exists(LIGHT)) {
  say("命中精简缓存 %s (%s MB) → 不再读原文件", LIGHT, mb(LIGHT))
  light <- readRDS(LIGHT)
} else {
  say("首次运行：readRDS 原文件（本次读一次，之后走缓存）")
  obj <- readRDS(INPUT)
  say("原始对象: %s 细胞 x %s 基因", ncol(obj), nrow(obj))
  light <- list(
    type      = class(obj)[1],
    meta      = obj@meta.data,
    reductions = if (inherits(obj, "Seurat")) obj@reductions else NULL,  # 坐标/嵌入，画图够用
    idents    = if (inherits(obj, "Seurat")) Seurat::Idents(obj) else NULL,
    n_cells   = ncol(obj), n_genes = nrow(obj),
    src       = INPUT, built_at = format(Sys.time())
  )
  saveRDS(light, LIGHT)
  say("精简缓存已落盘: %s (%s MB，原文件 %s MB)", LIGHT, mb(LIGHT), mb(INPUT))
  rm(obj); gc()
}
outp(LIGHT)
param("light_mb", mb(LIGHT))
prog(0.15, "cache ready")

# ============================ Stage 1：主计算（重活放这里） =================
# 用参数指纹当检查点 → 改参数会重跑，不改就跳过
stage("1_compute")
fp1 <- param_fp("compute", PARAMS)
run_stage("1_compute", fp1, {
  meta <- light$meta
  say("meta 列: %s", paste(head(colnames(meta), 12), collapse = ", "))
  res_path <- file.path(OUT_DIR, "compute_result.rds")
  res <- list(n_cells = nrow(meta), summary = utils::head(meta, 3))
  saveRDS(res, res_path); outp(res_path)
})
prog(0.6, "compute done")

# ============================ Stage 2：出图（可反复重跑，读缓存秒级） ======
stage("2_figures")
fp2 <- param_fp("figures", PARAMS)
run_stage("2_figures", fp2, {
  if (!is.null(light$reductions) && "umap" %in% names(light$reductions)) {
    um <- as.data.frame(light$reductions$umap@cell.embeddings)
    grp <- as.factor(light$idents)
    png(file.path(OUT_DIR, "umap.png"), width = 2250, height = 1950, res = 300)
    plot(um[[1]], um[[2]], col = as.integer(grp), pch = 19, cex = 0.35,
         xlab = "UMAP_1", ylab = "UMAP_2", main = basename(INPUT))
    legend("topright", legend = levels(grp), col = seq_along(levels(grp)),
           pch = 19, cex = 0.7, bty = "n")
    dev.off()
    outp(file.path(OUT_DIR, "umap.png"))
    say("图已落盘: %s", file.path(OUT_DIR, "umap.png"))
  } else say("无 umap reduction → 跳过出图")
})
prog(1.0, "done")

elapsed <- round(as.numeric(difftime(Sys.time(), t0, units = "mins")), 3)
say("=== 作业结束，耗时 %s min ===", elapsed)
say("缓存: %s | 检查点: %s | 产物: %s", CACHE_DIR, CKPT_DIR, OUT_DIR)
say("下次重跑：同参数会跳过已完成阶段；改参数只重跑变更阶段；大输入不再重读。")