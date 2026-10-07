#!/usr/bin/env Rscript
# ============================================================================
# verify_heatmap_export.R —— 矩阵热图出图后的确定性核验（base R，零第三方包）
# 用法：改下面 CONFIG 区 → Rscript verify_heatmap_export.R
# 核验三项：
#   ① 四格式落盘且非空 + 体积量级（空白图会远小于下限）
#   ② PNG 真实尺寸与 DPI（直接解析 IHDR 与 pHYs 块，不依赖任何图像包）
#   ③ svglite SVG 的分组色命中数 = 该色成员数（组名用同色文字时 +1）
# 最后打印逐项判定与总 PASS/FAIL。
# ⚠️ ③ 只对 svglite 生成的 SVG 成立：cairo 的 svg() 把颜色写成 rgb(%) 且文字转 glyph 路径，
#    用 hex 值 grep 会 100% 假阴性 —— 不要据此断言"色块没渲染"，改用栅格层像素计数。
# ⚠️ 逐张单发核验会被循环检测判为重复操作：本脚本一次给出全部图的结论，不要拆成多次调用。
# ============================================================================

## ---------- CONFIG ----------
DIR         <- "E:/MemOmics-Agent/results/<session>/figures/CNS"
FIGS        <- c("FigA3_program_subcluster_CNS", "FigA3_program_subcluster_pre_v3_CNS")
EXTS        <- c("png", "pdf", "svg", "tiff")
CANVAS_MM_W <- 183           # 期望纸宽（Nature 双栏；单栏 89）
DPI_EXPECT  <- 300
MIN_BYTES   <- c(png = 50000, pdf = 10000, svg = 20000, tiff = 100000)
GROUP_COLORS <- list(        # hex 小写 → 期望命中数（成员数，组名同色文字则 +1）
  "#2c7fb8" = 5, "#1b9e77" = 5, "#7ba05b" = 4, "#d64550" = 5, "#8c5fa8" = 3,
  "#3f3f3f" = 4, "#b0b0b0" = 4, "#c98a3c" = 2)
## ---------------------------

png_info <- function(f) {                      # 解析 PNG：IHDR 宽高色深 + pHYs DPI
  con <- file(f, "rb"); on.exit(close(con))
  readBin(con, "raw", 8)                       # 签名
  h <- readBin(con, "raw", 25)                 # 长度4 + "IHDR"4 + 宽4 + 高4 + 深1 + 色型1 + 3 + CRC4
  be <- function(v) sum(as.integer(v) * 256^(rev(seq_along(v)) - 1))
  out <- list(w = be(h[9:12]), h = be(h[13:16]), depth = as.integer(h[17]),
              color_type = as.integer(h[18]), dpi = NA_real_)
  repeat {
    lb <- readBin(con, "raw", 4); if (length(lb) < 4) break
    len <- be(lb); if (len > 5e7) break
    type <- rawToChar(readBin(con, "raw", 4))
    body <- readBin(con, "raw", len)
    if (type == "pHYs") {
      ppux <- be(body[1:4]); unit <- as.integer(body[9])
      if (identical(unit, 1L)) out$dpi <- round(ppux * 0.0254)   # 像素/米 → 像素/英寸
    }
    readBin(con, "raw", 4)                     # CRC
    if (type %in% c("IEND", "IDAT")) { if (type == "IDAT") next else break }
  }
  out
}

svg_hex_counts <- function(f, keys) {
  txt <- tolower(paste(readLines(f, warn = FALSE), collapse = "\n"))
  vapply(keys, function(k) {
    hits <- gregexpr(k, txt, fixed = TRUE)[[1]]
    if (identical(as.integer(hits[1]), -1L)) 0L else length(hits)
  }, integer(1))
}

fail <- character(0)
cat(sprintf("%-44s %-5s %10s %s\n", "figure", "fmt", "bytes", "note"))
for (b in FIGS) for (e in EXTS) {
  f <- file.path(DIR, paste0(b, ".", e)); note <- "-"
  if (!file.exists(f)) { fail <- c(fail, paste0(b, ".", e, " 缺失")); note <- "MISSING" }
  else {
    sz <- file.size(f)
    if (sz < MIN_BYTES[[e]]) { fail <- c(fail, paste0(b, ".", e, " 体积异常小(疑似空白)")); note <- "TOO-SMALL" }
    if (e == "png") {
      info <- png_info(f); mm <- info$w / DPI_EXPECT * 25.4
      note <- sprintf("%dx%d px | %.1f mm 宽 | dpi=%s", info$w, info$h, mm,
                      if (is.na(info$dpi)) "n/a" else format(info$dpi))
      if (!is.na(info$dpi) && info$dpi != DPI_EXPECT)
        fail <- c(fail, sprintf("%s.png dpi=%s（期望 %d）", b, info$dpi, DPI_EXPECT))
      if (abs(mm - CANVAS_MM_W) > 1.5)
        fail <- c(fail, sprintf("%s.png 纸宽 %.1f mm（期望 %.0f mm）", b, mm, CANVAS_MM_W))
    }
    if (e == "svg") {
      cnt <- svg_hex_counts(f, names(GROUP_COLORS)); exp <- unlist(GROUP_COLORS)
      okc <- cnt == exp
      note <- sprintf("分组色命中 %s（期望 %s）", paste(cnt, collapse = "/"), paste(exp, collapse = "/"))
      if (!all(okc))
        fail <- c(fail, sprintf("%s.svg 分组色不符: %s", b,
                                paste(sprintf("%s 得%d 期%d", names(cnt)[!okc], cnt[!okc], exp[!okc]), collapse = "; ")))
    }
    cat(sprintf("%-44s %-5s %10d %s\n", b, e, sz, note))
  }
}
cat("\n")
if (length(fail)) {
  cat("❌ FAIL（", length(fail), "项）:\n  - ", paste(fail, collapse = "\n  - "), "\n", sep = "")
  quit(status = 1)
}
cat("✅ PASS：四格式齐备、体积正常、纸宽与 DPI 符合、分组色命中数 = 成员数\n")