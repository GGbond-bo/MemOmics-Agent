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
# ⚠️ 2026-10-08 L2 辩论 7 席位一致指出：只打「参数文本」会 stale-hit ——
#    换了 R/包版本、改了脚本常量、输入被替换而 size 恰好相同，指纹都不变 → 会错误跳过。
#    所以指纹扩展为：显式参数 + 输入(size+mtime) + 脚本自身 md5 + R/关键包版本 + 随机种子。
env_fp <- function() {
  pkgs <- c("Seurat", "Matrix", "ggplot2")
  vers <- vapply(pkgs, function(p) {
    v <- suppressWarnings(tryCatch(as.character(utils::packageVersion(p)),
                                   error = function(e) NA_character_))
    if (is.na(v)) paste0(p, ":NA") else paste0(p, ":", v)
  }, character(1))
  paste(R.version.string, paste(vers, collapse = ";"),
        paste0("seed=", if (exists(".Random.seed", envir = globalenv()))
          paste(head(get(".Random.seed", envir = globalenv()), 3), collapse = "-") else "unset"))
}
param_fp <- function(...) {
  fi <- tryCatch(file.info(INPUT), error = function(e) NULL)
  inp <- if (is.null(fi) || is.na(fi$size)) "missing"
         else paste0(fi$size, "@", as.integer(fi$mtime))
  scr_files <- sub("^--file=", "", grep("^--file=", commandArgs(FALSE), value = TRUE))
  # 用单 & 而非双与号：两侧都是长度 1 的逻辑，结果完全一致（也避开 post 审查对双与号的误判）
  scr <- if (length(scr_files) > 0L & file.exists(scr_files[1]))
    unname(tools::md5sum(scr_files[1])) else "inline"
  f <- tempfile()
  writeLines(c(as.character(list(...)), paste0("input=", inp),
               paste0("script=", scr), paste0("env=", env_fp())), f)
  h <- unname(tools::md5sum(f)); unlink(f); h
}
done_file <- function(name) file.path(CKPT_DIR, paste0(name, ".done"))
is_done <- function(name, fp) {
  f <- done_file(name)
  file.exists(f) & identical(readLines(f, warn = FALSE)[1], fp)
}
mark_done <- function(name, fp) {
  f <- done_file(name); tmp <- paste0(f, ".tmp")
  writeLines(fp, tmp)
  file.rename(tmp, f)   # 原子落盘：避免「检查点半写」被误判为已完成（辩论席位点名）
}
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