#!/usr/bin/env Rscript
# =============================================================================
# r_session_daemon.R — MemOmics 集群常驻 R 会话（kernel 式持久化）  2026-10-09
#
# 目标：在集群节点上跑一个「读一次、一直用」的 R 进程。MuSC 这种大 rds 读进来后，
#       UMAP / FindMarkers / CellChat / 参数扫描都在同一个进程里接着做，**不重读文件**。
#
# 设计约束（实测过的集群现状）：
#   • R4.41 里没有 Rserve、没有 qs；只有 base R + jsonlite（本脚本连 jsonlite 都不用）。
#   • 登录节点不能跑重活、SGE qmaster 不通 → 用 setsid 常驻（和作业同一条既有路径）。
#   • 共享机器不开公网端口；同节点内部走**文件队列**，零三方依赖、无 socket 生命周
#     期坑，daemon 崩了也能从磁盘上看出跑到哪了。
#
# 协议（全部是纯文本，base R 读写）：
#   请求：<dir>/queue/<id>.req.R   —— 一个 R 脚本文件，第一行是 #MM-REQ 头注释。
#          daemon 用 file.rename() 原子认领（queue → run），同一请求不会被跑两次。
#   结果：<dir>/done/<id>.res.txt  —— 头部 key:value + 五个 ---XXX--- 分段（OUTPUT /
#          WARNINGS / ERROR / READS / PLOTS）。请求原文归档为 done/<id>.req.R。
#   状态：<dir>/state.txt          —— 心跳 key:value（2 秒一次）：pid/status/current/
#          jobs_done/readrds_calls/rss_kb/objects/plots_total…，本机侧轮询它就知道会话活没活。
#   日志：<dir>/session.log        —— 追加式事件流水（也给 htop/MobaXterm 看）。
#   图表：<dir>/plots/             —— 抓到的每张图一个 PNG（<请求号>_NN.png），面板按 cell
#          贴回去。机制：把默认绘图设备改写成往这个目录写文件（见 §3.5），cell 结束时
#          dev.off() 收尾 —— 所以非交互进程里画的图不再丢进 Rplots.pdf。
#   自检：<dir>/ckpt/*.rds、<dir>/out/ 是它的产物目录。
#
# 会话内可用的辅助函数（投代码时直接调）：
#   mm_info()                        自检：R 版本/pid/内存/对象清单/readRDS 审计
#   mm_reads()                       readRDS 审计（本会话读过几次、读了哪个文件）
#   mm_save(name, objects)           落检查点（默认全部会话对象）→ ckpt/<name>.rds
#   mm_restore(path)                 从检查点恢复（省略 path = 最新一个）
#   mm_plots(n)                      看最近抓到的图（文件路径 + 大小）
#   mm_quit()                         优雅退出（推荐；直接 quit() 也会被接住）
#
# 启动（由 MemOmics remote_cluster 的 session_start 动作拉起，也可手敲）：
#   cd <dir> && setsid -f Rscript r_session_daemon.R --dir <dir> >> session.log 2>&1 < /dev/null
#
# 已知边界：
#   • 单进程单线程：一个请求在跑时，后面的排队等（这正是「一个 kernel」的语义）。
#   • 命名空间：代码默认在 globalenv() 里求值；不要覆盖 .mm_* 开头的内部函数。
#   • 抓图粒度 = 顶层表达式：一行画一张图 → 一个 PNG；同一个表达式里画多张（比如 for
#     循环里连续 plot）只留最后一张。cell 结束时还开着的设备会被自动关掉并记一条警告。
#   • readRDS 审计只统计**会话层**（globalenv）里未加限定的 readRDS 调用；包内部自己
#     读文件不走这个包装器。所以验收还要配合「同一 pid / 内存驻留 / 耗时」一起看。
# =============================================================================

## ---- 0. 启动参数与目录 -------------------------------------------------------
args <- commandArgs(trailingOnly = TRUE)
.opt <- function(key, default = "") {
  i <- match(key, args)
  if (is.na(i) || i >= length(args)) return(default)
  args[[i + 1L]]
}

dir <- .opt("--dir")
if (!nzchar(dir)) stop("用法: r_session_daemon.R --dir <会话目录> [--rscript <Rscript 路径>]")
dir <- normalizePath(dir, winslash = "/", mustWork = TRUE)
rscript_self <- .opt("--rscript", file.path(R.home("bin"), "Rscript"))

.SESSION_VERSION <- "2"

queue_dir <- file.path(dir, "queue"); run_dir <- file.path(dir, "run")
done_dir  <- file.path(dir, "done");  ckpt_dir <- file.path(dir, "ckpt")
out_dir   <- file.path(dir, "out");   lock_dir <- file.path(dir, "daemon.lock")
plots_dir <- file.path(dir, "plots")
# staging/：投递方先写这里再原子 mv 进 queue/，避免 daemon 认领到写了一半的请求
stage_dir <- file.path(dir, "staging")
for (d in c(queue_dir, run_dir, done_dir, ckpt_dir, out_dir, stage_dir, plots_dir)) {
  dir.create(d, showWarnings = FALSE, recursive = TRUE)
}
log_path   <- file.path(dir, "session.log")
state_path <- file.path(dir, "state.txt")

.started <- Sys.time()

## ---- 1. 小工具 --------------------------------------------------------------
.fmt_now <- function(t = Sys.time()) format(t, "%Y-%m-%d %H:%M:%S")

.log <- function(...) {
  msg <- paste0("[", .fmt_now(), "] ", paste0(..., collapse = ""), "\n")
  try(cat(msg, file = log_path, append = TRUE, sep = ""), silent = TRUE)
  invisible(NULL)
}

.mm_fmt_bytes <- function(b) {
  if (is.null(b) || length(b) == 0L || is.na(b)) return("?")
  u <- c("B", "KB", "MB", "GB", "TB"); i <- 1L
  while (b >= 1024 && i < length(u)) { b <- b / 1024; i <- i + 1L }
  if (i == 1L) sprintf("%.0f%s", b, u[i]) else sprintf("%.1f%s", b, u[i])
}

.mm_rss_kb <- function() {
  st <- tryCatch(readLines("/proc/self/status", warn = FALSE), error = function(e) character(0))
  v <- grep("^VmRSS:", st, value = TRUE)
  if (!length(v)) return(NA_real_)
  suppressWarnings(as.numeric(sub("\\s*kB\\s*$", "", sub("^VmRSS:\\s*", "", v[1]))))
}

.mm_truncate <- function(txt, limit = 400000L) {
  if (is.na(txt) || nchar(txt) <= limit) return(txt)
  head_n <- as.integer(limit * 0.60); tail_n <- as.integer(limit * 0.35)
  paste0(substr(txt, 1L, head_n),
         sprintf("\n…[输出过长已截断：共 %d 字符，只保留头尾]\n", nchar(txt)),
         substr(txt, nchar(txt) - tail_n + 1L, nchar(txt)))
}

## ---- 2. 会话状态与 readRDS 审计 ---------------------------------------------
state <- new.env(parent = emptyenv())
state$status <- "idle"; state$current <- ""; state$busy_since <- ""
state$done <- 0L; state$last_id <- ""; state$last_status <- ""; state$last_ms <- 0L
state$quit <- FALSE

audit <- new.env(parent = emptyenv())
audit$n <- 0L; audit$paths <- character(0); audit$sizes <- numeric(0); audit$times <- character(0)

.mm_reads_note <- function(file) {
  b <- tryCatch(file.info(file)$size, error = function(e) NA_real_)
  audit$n <- audit$n + 1L
  audit$paths <- c(audit$paths, as.character(file))
  audit$sizes <- c(audit$sizes, b)
  audit$times <- c(audit$times, .fmt_now())
  .log("readRDS: ", file, " (", .mm_fmt_bytes(b), ")")
  invisible(NULL)
}

## 会话层的 readRDS 包装：谁在读大文件，账本上看得见（FindMarkers 这类步骤不该产生新读）
readRDS <- function(file, ...) {
  .mm_reads_note(file)
  base::readRDS(file, ...)
}

## 防止代码里顺手 quit() 把 daemon 带走：统一转成优雅退出
quit <- function(save = "no", status = 0, runLast = TRUE) {
  .mm_quit()
  invisible(NULL)
}
q <- quit

## ---- 3. 会话对象清单与辅助函数 ----------------------------------------------
.mm_session_objects <- function() {
  setdiff(ls(globalenv(), all.names = TRUE), .core_names)
}

.mm_reads_count <- function() audit$n

mm_reads <- function() {
  cat("readRDS 审计：本会话累计 ", audit$n, " 次\n", sep = "")
  if (audit$n) {
    for (i in seq_len(audit$n)) {
      cat(sprintf("  %2d. %s  %10s  %s\n", i, audit$times[i],
                  .mm_fmt_bytes(audit$sizes[i]), audit$paths[i]))
    }
  } else {
    cat("  （还没有任何会话层 readRDS 调用）\n")
  }
  invisible(audit$n)
}

mm_info <- function() {
  objs <- .mm_session_objects()
  cat("=== MemOmics 常驻会话自检 ===\n")
  cat("R        : ", R.version.string, "\n", sep = "")
  cat(sprintf("进程     : pid %d @ %s，起于 %s（已运行 %.2f 小时）\n",
              Sys.getpid(), Sys.info()[["nodename"]], .fmt_now(.started),
              as.numeric(difftime(Sys.time(), .started, units = "hours"))))
  cat("目录     : ", dir, "\n", sep = "")
  cat("内存     : VmRSS ", .mm_fmt_bytes(.mm_rss_kb() * 1024), "\n", sep = "")
  cat(sprintf("图表     : 本次 cell 抓到 %d 张；plots/ 累计 %d 张\n",
              plots$n, length(list.files(plots_dir, pattern = "\\.png$"))))
  cat("会话对象 : ", length(objs), " 个\n", sep = "")
  if (length(objs)) {
    sel <- objs[seq_len(min(length(objs), 100L))]
    sizes <- vapply(sel, function(o) {
      tryCatch(as.numeric(object.size(get(o, envir = globalenv()))), error = function(e) NA_real_)
    }, numeric(1))
    ord <- order(sizes, decreasing = TRUE, na.last = TRUE)
    for (i in head(ord, 12L)) {
      d <- tryCatch(paste(dim(get(sel[i], envir = globalenv())), collapse = " x "),
                    error = function(e) "")
      cat(sprintf("  %-30s %-10s %s\n", sel[i], .mm_fmt_bytes(sizes[i]),
                  if (nzchar(d)) paste0("[", d, "]") else ""))
    }
    if (length(objs) > 100L) cat(sprintf("  …（共 %d 个对象，只列前 100 个里最大的 12 个）\n", length(objs)))
  }
  mm_reads()
  invisible(NULL)
}

mm_save <- function(name = NULL, objects = NULL) {
  if (is.null(name) || !nzchar(name)) name <- paste0("ckpt-", format(Sys.time(), "%Y%m%d-%H%M%S"))
  name <- gsub("[/\\\\]", "_", name)
  path <- file.path(ckpt_dir, paste0(name, ".rds"))
  objs <- if (is.null(objects) || !length(objects)) .mm_session_objects() else as.character(objects)
  missing_objs <- setdiff(objs, ls(globalenv(), all.names = TRUE))
  if (length(missing_objs)) stop("对象不存在: ", paste(missing_objs, collapse = ", "))
  if (!length(objs)) stop("会话里没有可保存的对象")
  t0 <- Sys.time()
  lst <- lapply(objs, function(o) get(o, envir = globalenv()))
  names(lst) <- objs
  saveRDS(lst, file = path, compress = TRUE)
  b <- tryCatch(file.info(path)$size, error = function(e) NA_real_)
  cat(sprintf("MM_CKPT: %s %.0f\n", path, ifelse(is.na(b), 0, b)))
  cat(sprintf("已保存 %d 个对象 → %s（%s，用时 %.1f 秒）\n", length(objs), path,
              .mm_fmt_bytes(b), as.numeric(difftime(Sys.time(), t0, units = "secs"))))
  .log("ckpt saved: ", path, " (", .mm_fmt_bytes(b), ", ", length(objs), " objs)")
  invisible(path)
}

mm_restore <- function(path = NULL) {
  if (is.null(path) || !nzchar(path)) {
    files <- list.files(ckpt_dir, pattern = "\\.rds$", full.names = TRUE)
    if (!length(files)) stop("ckpt/ 下没有检查点可恢复")
    path <- files[which.max(file.mtime(files))]
  } else if (!grepl("/", path, fixed = TRUE)) {
    ## 裸名字：补 ckpt/ 前缀，再补 .rds 后缀（2026-10-09 实测：漏了后缀 → 「检查点不存在」）
    cand <- file.path(ckpt_dir, path)
    if (!file.exists(cand) && file.exists(paste0(cand, ".rds"))) cand <- paste0(cand, ".rds")
    path <- cand
  }
  if (!file.exists(path)) stop("检查点不存在: ", path)
  t0 <- Sys.time()
  lst <- base::readRDS(path)
  if (!is.list(lst)) lst <- list(obj = lst)
  list2env(lst, envir = globalenv())
  cat(sprintf("已从 %s 恢复 %d 个对象（%.1f 秒）：%s\n", path, length(lst),
              as.numeric(difftime(Sys.time(), t0, units = "secs")),
              paste(names(lst), collapse = ", ")))
  .log("ckpt restored: ", path, " (", length(lst), " objs)")
  invisible(path)
}

mm_quit <- function() {
  state$quit <- TRUE
  cat("已请求退出：当前请求跑完就收工（检查点请先用 mm_save() 落盘）\n")
  .log("quit requested")
  invisible(TRUE)
}

mm_help <- function() {
  cat("MemOmics 常驻 R 会话 —— 会话内可用：\n")
  cat("  mm_info()               自检（R/pid/内存/对象/readRDS 审计/图表）\n")
  cat("  mm_reads()              readRDS 审计明细\n")
  cat("  mm_save(name, objects)  落检查点 → ckpt/<name>.rds（省略参数 = 存全部会话对象）\n")
  cat("  mm_restore(path)        从检查点恢复（省略 path = 最新一个）\n")
  cat("  mm_plots(n)             看最近抓到的图（默认 8 张）\n")
  cat("  mm_quit()               优雅退出\n")
  cat("  目录：", dir, "（queue/ 求情，done/ 结果，ckpt/ 检查点，out/ 产物，plots/ 图）\n", sep = "")
  invisible(NULL)
}

## ---- 3.5 抓图：把默认绘图设备写到 plots/（Notebook 总端用） --------------------
## 背景：Rscript 这种非交互进程里，plot() 会落到 Rplots.pdf 或干脆不落盘 ——「像 Jupyter
## 一样看到图」就差这一层。做法：改写 options(device=...)，让 R 每次要开绘图设备时
## 直接开一个写进 plots/ 的 PNG；cell 结束时统一 dev.off() 收尾（见 .mm_capture），
## 再把文件清单写进结果的 ---PLOTS--- 分段。
plots <- new.env(parent = emptyenv())
plots$files <- character(0); plots$n <- 0L; plots$skipped <- 0L; plots$req <- ""
.MM_MAX_PLOTS <- 120L            # 一个 cell 最多抓 120 张；超了不再落盘（防某循环画爆磁盘）

.mm_plot_reset <- function(req_id) {
  plots$files <- character(0); plots$n <- 0L; plots$skipped <- 0L
  plots$req <- if (nzchar(req_id)) req_id else "cell"
  invisible(NULL)
}

.mm_device <- function(...) {
  ## R 要开默认设备时调这里（调用方给的 filename/width/... 一律忽略：我们按自己的规矩命名）
  if (plots$n >= .MM_MAX_PLOTS) {
    plots$skipped <- plots$skipped + 1L
    ## 超限的图进一个临时 pdf（不占 plots/），保证代码不报错
    grDevices::pdf(file = tempfile("mm_spill", tmpdir = dir))
    return(invisible(NULL))
  }
  plots$n <- plots$n + 1L
  rid <- gsub("[^A-Za-z0-9._-]", "_", if (nzchar(plots$req)) plots$req else "cell")
  f <- file.path(plots_dir, sprintf("%s_%02d.png", rid, plots$n))
  grDevices::png(filename = f, width = 1440, height = 1080, res = 144, bg = "white")
  plots$dev <- grDevices::dev.cur()      # 记住是我们开的哪一个：表达式收尾时只关它
  plots$files <- c(plots$files, f)
  .log("plot captured: ", f)
  invisible(NULL)
}
options(device = .mm_device)

.mm_close_own_device <- function() {
  ## 只关「我们开的那个」设备：关了它，下一个 plot 才会触发 .mm_device 再开一个新文件。
  ## （R 的默认设备是复用同一个 —— 不逐个表达式收尾的话，一个 cell 里的第二张图会
  ##   直接覆盖第一张，最后只剩最后一张。）
  d <- plots$dev
  plots$dev <- NULL
  if (is.null(d) || length(d) == 0L || d <= 1L) return(invisible(FALSE))
  if (d %in% grDevices::dev.list()) try(grDevices::dev.off(d), silent = TRUE)
  invisible(TRUE)
}

.mm_eval_code <- function(path) {
  ## 复刻 source(echo=FALSE, print.eval=TRUE, local=FALSE) 的语义，但**逐表达式**执行：
  ## 每个顶层表达式跑完就把我们开的绘图设备收尾 → 一张图一个 PNG 文件。
  ## 边界（写进文档）：同一个表达式里画多张图（如 for 循环里连续 plot）仍然只留最后一张。
  exprs <- parse(path, keep.source = FALSE)
  for (i in seq_along(exprs)) {
    v <- withVisible(eval(exprs[[i]], envir = globalenv()))
    if (isTRUE(v$visible)) print(v$value)
    .mm_close_own_device()
  }
  invisible(NULL)
}

.mm_flush_plots <- function() {
  ## cell 结束时把还开着的设备全关掉：不关的话最后一张图不会落盘。
  ## 返回被关掉的设备名（除 png 外说明用户自己开过 pdf()/其它设备 —— 上层会在警告里提示）。
  open <- grDevices::dev.list()
  if (!length(open)) return(character(0))
  while (grDevices::dev.cur() > 1L) try(grDevices::dev.off(), silent = TRUE)
  names(open)
}

mm_plots <- function(n = 8L) {
  files <- list.files(plots_dir, pattern = "\\.png$", full.names = TRUE)
  if (!length(files)) { cat("plots/ 还没有图（本会话累计抓到 0 张）\n"); return(invisible(character(0))) }
  files <- files[order(file.mtime(files), decreasing = TRUE)]
  sel <- utils::head(files, max(1L, as.integer(n)))
  cat(sprintf("最近 %d 张图（plots/ 共 %d 张）：\n", length(sel), length(files)))
  for (f in sel) {
    cat(sprintf("  %s  %10s  %s\n", .fmt_now(file.mtime(f)), .mm_fmt_bytes(file.info(f)$size), f))
  }
  invisible(sel)
}

## ---- 4. 状态心跳 -------------------------------------------------------------
.write_state <- function(status = NULL) {
  if (is.null(status)) status <- if (nzchar(state$current)) "busy" else "idle"
  lines <- c(
    paste0("version=", .SESSION_VERSION),
    paste0("pid=", Sys.getpid()),
    paste0("host=", Sys.info()[["nodename"]]),
    paste0("dir=", dir),
    paste0("rscript=", rscript_self),
    paste0("r_version=", R.version.string),
    paste0("started=", .fmt_now(.started)),
    paste0("updated=", .fmt_now()),
    paste0("status=", status),
    paste0("current=", if (nzchar(state$current)) state$current else "-"),
    paste0("busy_since=", if (nzchar(state$busy_since)) state$busy_since else "-"),
    paste0("jobs_done=", state$done),
    paste0("last_id=", if (nzchar(state$last_id)) state$last_id else "-"),
    paste0("last_status=", if (nzchar(state$last_status)) state$last_status else "-"),
    paste0("last_ms=", state$last_ms),
    paste0("readrds_calls=", audit$n),
    paste0("plots_total=", length(list.files(plots_dir, pattern = "\\.png$"))),
    paste0("plots_last=", plots$n),
    paste0("rss_kb=", ifelse(is.na(.mm_rss_kb()), -1, .mm_rss_kb())),
    paste0("objects=", length(.mm_session_objects()))
  )
  tmp <- paste0(state_path, ".tmp")
  try(writeLines(lines, tmp), silent = TRUE)
  try(file.rename(tmp, state_path), silent = TRUE)
  invisible(NULL)
}

## ---- 5. 执行一个请求 ----------------------------------------------------------
.mm_capture <- function(id, path) {
  .mm_plot_reset(id)
  tf <- tempfile("mmout", tmpdir = dir)
  con <- file(tf, open = "wt")
  warns <- character(0)
  err <- NULL
  sink(con); sink(con, type = "message")
  res <- tryCatch({
    withCallingHandlers(
      .mm_eval_code(path),
      warning = function(w) { warns <<- c(warns, conditionMessage(w)); invokeRestart("muffleWarning") }
    )
    NULL
  }, error = function(e) e)
  sink(type = "message"); sink()
  close(con)
  ## 抓图收尾：cell 里还开着的绘图设备要关掉，最后一张图才会落盘（关完再读输出）
  closed <- .mm_flush_plots()
  other_dev <- setdiff(unique(closed), "png")
  if (length(other_dev)) {
    warns <- c(warns, sprintf("cell 结束时自动关闭了还开着的绘图设备：%s（跨 cell 保持设备未支持）",
                              paste(other_dev, collapse = ", ")))
  }
  txt <- tryCatch(readLines(tf, warn = FALSE, encoding = "UTF-8"),
                  error = function(e) character(0))
  unlink(tf)
  if (inherits(res, "error")) err <- conditionMessage(res)
  list(status = if (is.null(err)) "ok" else "error",
       output = .mm_truncate(paste(txt, collapse = "\n")),
       warnings = paste(warns, collapse = "\n"),
       error = if (is.null(err)) "" else err,
       plots = plots$files,
       plots_skipped = plots$skipped)
}

.write_res <- function(id, r, t0, ms) {
  res_path <- file.path(done_dir, paste0(id, ".res.txt"))
  reads <- if (audit$n) {
    paste(sprintf("%s\t%.0f\t%s", audit$times, ifelse(is.na(audit$sizes), 0, audit$sizes),
                  audit$paths), collapse = "\n")
  } else ""
  plot_lines <- ""
  if (length(plots$files)) {
    sizes <- vapply(plots$files, function(f) {
      tryCatch(as.numeric(file.info(f)$size), error = function(e) NA_real_)
    }, numeric(1))
    plot_lines <- paste(sprintf("%s\t%.0f", plots$files, ifelse(is.na(sizes), 0, sizes)),
                        collapse = "\n")
  }
  lines <- c(
    "#MM-RESULT v2",
    paste0("id: ", id),
    paste0("status: ", r$status),
    paste0("ms: ", round(ms)),
    paste0("started: ", .fmt_now(t0)),
    paste0("finished: ", .fmt_now()),
    paste0("readrds_calls: ", audit$n),
    paste0("job_index: ", state$done + 1L),
    paste0("rss_kb: ", ifelse(is.na(.mm_rss_kb()), -1, .mm_rss_kb())),
    paste0("objects: ", length(.mm_session_objects())),
    paste0("plots: ", length(plots$files)),
    paste0("plots_skipped: ", plots$skipped),
    "---OUTPUT---",
    r$output,
    "---WARNINGS---",
    r$warnings,
    "---ERROR---",
    r$error,
    "---READS---",
    reads,
    "---PLOTS---",
    plot_lines
  )
  tmp <- paste0(res_path, ".tmp")
  writeLines(lines, tmp, useBytes = TRUE)
  file.rename(tmp, res_path)
  invisible(res_path)
}

process_request <- function(id, path) {
  t0 <- Sys.time()
  state$status <- "busy"; state$current <- id; state$busy_since <- .fmt_now(t0)
  .write_state("busy")
  .log("begin ", id)
  r <- .mm_capture(id, path)
  ms <- as.numeric(difftime(Sys.time(), t0, units = "secs")) * 1000
  .write_res(id, r, t0, ms)
  file.rename(path, file.path(done_dir, paste0(id, ".req.R")))
  state$done <- state$done + 1L
  state$last_id <- id; state$last_status <- r$status; state$last_ms <- round(ms)
  state$status <- "idle"; state$current <- ""; state$busy_since <- ""
  .write_state("idle")
  .log("end ", id, " status=", r$status, " ", sprintf("%.1fs", ms / 1000),
       " readrds=", audit$n, " plots=", length(r$plots))
}

## ---- 6. 单实例锁 ---------------------------------------------------------------
if (file.exists(lock_dir)) {
  old_pid <- tryCatch(trimws(readLines(file.path(lock_dir, "pid"), warn = FALSE)[1]),
                      error = function(e) NA_character_)
  alive <- !is.na(old_pid) && nzchar(old_pid) && file.exists(file.path("/proc", old_pid))
  if (alive) stop(sprintf("该目录已有常驻会话在跑（pid=%s）。换目录或先让它退出（mm_quit）。", old_pid))
  unlink(lock_dir, recursive = TRUE, force = TRUE)
  .log("cleaned stale lock (pid=", old_pid, ")")
}
dir.create(lock_dir, showWarnings = FALSE)
writeLines(as.character(Sys.getpid()), file.path(lock_dir, "pid"))

## 上次崩溃剩在 run/ 的请求：退回 queue/ 重跑（幂等失败会在 res 里看到）
leftover <- list.files(run_dir, pattern = "\\.req\\.R$")
for (f in leftover) file.rename(file.path(run_dir, f), file.path(queue_dir, f))
if (length(leftover)) .log("requeued ", length(leftover), " leftover request(s)")

## ---- 7. 启动横幅 ---------------------------------------------------------------
.log("daemon start v", .SESSION_VERSION, " pid=", Sys.getpid(),
     " host=", Sys.info()[["nodename"]], " R=", R.version.string,
     " rscript=", rscript_self, " dir=", dir)
.log("libPaths: ", paste(.libPaths(), collapse = " | "))

## 到这里为止定义的都是「基础设施」，快照一下，供会话对象清单用
.core_names <- unique(c(ls(globalenv(), all.names = TRUE), ".core_names"))

.write_state("idle")

## ---- 8. 主循环 -----------------------------------------------------------------
last_beat <- 0
repeat {
  now_s <- as.numeric(Sys.time())
  if (now_s - last_beat >= 2) {
    .write_state(if (nzchar(state$current)) "busy" else "idle")
    last_beat <- now_s
  }
  if (isTRUE(state$quit)) break
  reqs <- sort(list.files(queue_dir, pattern = "\\.req\\.R$", full.names = FALSE))
  if (!length(reqs)) { Sys.sleep(0.3); next }
  id <- sub("\\.req\\.R$", "", reqs[1])
  src <- file.path(queue_dir, reqs[1]); dst <- file.path(run_dir, reqs[1])
  if (!file.rename(src, dst)) { Sys.sleep(0.2); next }   # 原子认领，抢不到就等下一轮
  process_request(id, dst)
}

.write_state("stopped")
.log("daemon exit")
unlink(lock_dir, recursive = TRUE, force = TRUE)
base::quit(save = "no", status = 0)