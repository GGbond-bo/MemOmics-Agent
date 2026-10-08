# ============================================================
# verify_figure_pixels.R —— 图件像素级验证探针（防"空白/黑底/配色静默失效"）
#
# 用途：出图后**必须**跑的硬门禁。判断三件事：
#   ① 是否空白/黑底（dark% / colored% / near-white%）
#   ② 每个面板行是否真有内容（三分带 colored%）
#   ③ **预期配色是否真的画上去了**（逐 hex 计数；任一为 0 = 该分组填充失效）
#
# 为什么需要 ③：命名向量配色键错配（如 c(Young=…,Old=…) 而实际取值是 Y_Pre/O_Pre/OD_Pre）
#   会让 fill 变 NA —— ggplot **不报错**，只是画出空白箱体，文件大小/非白% 全部正常。
#   实测：修复前 6 个组别色全部 n=0、band3 colored=0.00%，而 dark 仍有 3.70%（框线/坐标轴还在）。
#
# 依赖：png（R 自带推荐包）。用法：
#   source("scripts/verify_figure_pixels.R")
#   chk_px("figures/Fig_x_v2.png",
#          expected = c("#8CD3C0","#009E73","#8CC0DC","#0072B2","#ECB78C","#D55E00"))  # 预期配色
#   chk_px("figures/Supplementary_Fig_S1.png", expected = c(...))
# ============================================================

suppressPackageStartupMessages(library(png))

#' 像素级图件体检
#' @param path       PNG 路径（用 600 dpi 主图 PNG，不要用 PDF/TIFF）
#' @param expected   预期出现的 hex 颜色向量（分组配色/关键色阶两端）；任一命中数为 0 会 FAIL
#' @param step       子采样步长（大图默认 4 = 每 4 像素取 1，够准且快）
#' @param tol        颜色匹配容差（抗锯齿），默认 6
#' @param dark_max   暗像素判据（RGB 全 < 此值算 dark），默认 100
#' @param sat_min    彩色像素判据（max-min > 此值算 colored），默认 30
chk_px <- function(path, expected = character(0), step = 4, tol = 6,
                   dark_max = 100, sat_min = 30) {
  if (!file.exists(path)) stop("找不到图件: ", path)
  im <- png::readPNG(path)
  h <- dim(im)[1]; w <- dim(im)[2]
  sub <- im[seq(1, h, step), seq(1, w, step), 1:3] * 255
  r <- sub[, , 1]; g <- sub[, , 2]; b <- sub[, , 3]
  mx <- pmax(r, g, b); mn <- pmin(r, g, b)

  cat(sprintf("\n=== %s ===\n", basename(path)))
  cat(sprintf("size %dx%d (pixel)  |  step=%d  |  采样子样本 %.0fk px\n",
              w, h, step, length(r) / 1000))

  dark    <- mean(mx < dark_max) * 100
  colored <- mean(mx - mn > sat_min) * 100
  nearw   <- mean(mn > 240) * 100
  cat(sprintf("dark(max<%d)      = %6.2f %%   [判据 <10   空白/黑底则异常高]\n", dark_max, dark))
  cat(sprintf("colored(max-min>%d)= %6.2f %%   [判据 >1    正常图必须有彩色]\n", sat_min, colored))
  cat(sprintf("near-white(min>240)= %6.2f %%   [白底应 >75]\n", nearw))

  mask <- mx >= 0  # 全画布；如需只统计"非白"内容框，改 mn <= 240
  m2 <- mn <= 240
  if (any(m2)) {
    rows <- range(which(rowSums(m2) > 0)); cols <- range(which(colSums(m2) > 0))
    cat(sprintf("content bbox: rows %d-%d / cols %d-%d  (画布 %d x %d)\n",
                rows[1], rows[2], cols[1], cols[2], h, w))
  }

  # 三分带：验证每个面板行都有内容（多 panel 组合图必查）
  for (i in 1:3) {
    y0 <- (i - 1) * h %/% 3 + 1; y1 <- i * h %/% 3
    s <- im[y0:y1, seq(1, w, step), 1:3] * 255
    m <- pmax(s[, , 1], s[, , 2], s[, , 3]); n <- pmin(s[, , 1], s[, , 2], s[, , 3])
    cat(sprintf("  band%d (y %5d-%5d): colored=%6.2f%%  dark=%6.2f%%\n",
                i, y0, y1, mean(m - n > sat_min) * 100, mean(m < dark_max) * 100))
  }

  # 预期配色逐 hex 计数（核心：静默失效只有这样才抓得到）
  fail <- character(0)
  if (length(expected)) {
    cat("-- expected colour hex counts --\n")
    for (t in expected) {
      tt <- grDevices::col2rgb(t)[, 1]
      hit <- sum(abs(r - tt[1]) < tol & abs(g - tt[2]) < tol & abs(b - tt[3]) < tol)
      flag <- if (hit == 0) { fail <- c(fail, t); "  <== 缺失 (fill/colour 静默失效!)" } else ""
      cat(sprintf("   %s  n=%-8d%s\n", t, hit, flag))
    }
  }

  verdict <- if (dark > 10 || colored < 1 || length(fail) > 0) "FAIL" else "PASS"
  cat(sprintf(">>> %s%s\n", verdict,
              if (length(fail)) paste0("  (缺失色: ", paste(fail, collapse = ", "), ")") else ""))
  invisible(list(dark = dark, colored = colored, nearwhite = nearw, missing = fail, verdict = verdict))
}

#' 便捷包装：主图 + 补充图一次体检（expected 用命名列表）
chk_all <- function(files, step = 4) {
  res <- lapply(names(files), function(nm) chk_px(nm, expected = files[[nm]], step = step))
  names(res) <- names(files)
  bad <- names(res)[vapply(res, function(x) x$verdict == "FAIL", logical(1))]
  cat("\n=========================================\n")
  if (length(bad)) cat("❌ 未通过:", paste(bad, collapse = ", "), "\n") else cat("✅ 全部 PASS\n")
  cat("=========================================\n")
  invisible(res)
}

# ------------------------------------------------------------------
# 参考基线（2026-09-24 MF_2000 投稿组合图 v2，183×196 mm @600 dpi → 4322×4629 px）
#   dark 2.40% | colored 8.49% | near-white 87.74% | bbox rows 181-4611 / cols 35-4317
#   band1/2/3 colored = 1.92 / 23.55 / 3.35 %
#   6 个组别色 hex 计数 = 2043 / 3124 / 15660 / 2811 / 3377 / 2930
# 失败对照（修复前，同脚本同尺寸）：band3 colored = 0.00%，6 个组别色全部 n = 0
# ------------------------------------------------------------------