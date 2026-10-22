#!/usr/bin/env Rscript
# ============================================================
# measure_text_in_inches.R —— 精确量「文字占用多少英寸」
#   专治四类请求：① 分组名/轴名太长压到邻组 ② 标签挤在一起要不要加宽画布
#                 ③ 「XXX 这个名字太长了，有没有简短贴切的」→ 候选词逐个量，凭数据选
#                 ④ 改名前先验，避免改完还是溢出
#
# 用法:
#   Rscript measure_text_in_inches.R \
#     --labels "Metabolism,Nutrient,Contractile,Inflamm-aging,Decompensation" \
#     --bands  3,4,3,3,2  --row-in 0.379 \
#     --pt 9 --cex 0.8333 --font 2 --dev-w 16.5 --dev-h 8.4
#
#   --labels  逗号分隔的待测文字
#   --bands   每个 label「被分配到多少行」的高度（横向标签=块宽用不到；竖排组名=该组行数）
#             不给 bands 则只量宽度、不做溢出判定
#   --row-in  1 行 = 多少英寸。算法（base graphics 热图常用）:
#               axes_h_in <- dev_h - mai[1] - mai[3]
#               row_in    <- axes_h_in / (NROWS + 1.5)     # ylim 高度 = NROWS+1.5 单位, CELL=1
#   --pt/--cex/--font  必须与目标脚本 par(ps=)/text(cex=,font=) 完全一致，否则量的是别的字
#              （脚本里写 cex = 7.5/9 时，这里传 --cex 0.8333）
#   --gap-in  相邻分组间隙（英寸），用于算「安全溢出 = gap/2」；默认 0
#
# 输出: 每个 label 的 实宽(in) / 所属 band 可用高度(in) / 溢出(in) / 结论
# ============================================================

args <- commandArgs(trailingOnly = TRUE)
getarg <- function(k, default = NULL) {
  i <- match(k, args); if (is.na(i) || i == length(args)) return(default); args[i + 1] }
hasarg <- function(k) k %in% args

LABELS <- strsplit(getarg("--labels", ""), ",")[[1]]
if (length(LABELS) == 1 && LABELS == "") stop("必须给 --labels")
BANDS  <- if (hasarg("--bands")) as.numeric(strsplit(getarg("--bands"), ",")[[1]]) else NULL
ROW_IN <- if (hasarg("--row-in")) as.numeric(getarg("--row-in")) else NULL
PT     <- as.numeric(getarg("--pt",   "9"))
CEX    <- as.numeric(getarg("--cex",  "1"))
FONT   <- as.numeric(getarg("--font", "1"))
DEV_W  <- as.numeric(getarg("--dev-w", "16.5"))
DEV_H  <- as.numeric(getarg("--dev-h", "8.4"))
GAP_IN <- as.numeric(getarg("--gap-in", "0"))

if (!is.null(BANDS) && length(BANDS) != length(LABELS))
  stop(sprintf("--bands 个数(%d) 与 --labels 个数(%d) 不一致", length(BANDS), length(LABELS)))

# ---- 关键：先把坐标系设成「1 用户单位 = 1 英寸」 ---------------------------------
# ⛔ 三个实测坑（不看注释必踩）:
#   1) 不 plot.new() 就 strwidth → Error: plot.new has not been called yet
#      （strwidth 依赖活动绘图区，空设备 pdf(NULL) 之后必须 plot.new()+plot.window()）
#   2) plot.window(xlim=c(0,1)) 时 strwidth 返回的是**用户坐标**不是英寸
#      症状：14 字符的字符串量出 0.063 —— 数值小得离谱就是单位错了
#   3) 修法二选一：本脚本用 A（坐标系即英寸，最稳）；B = strwidth(s, units="inches")
#      ⚠️ B 必须在有活动设备时调用，且 par(ps=) 要与目标脚本一致
pdf(NULL, width = DEV_W, height = DEV_H)
par(mai = rep(0, 4), ps = PT, family = "sans", xpd = NA)
plot.new(); plot.window(xlim = c(0, DEV_W), ylim = c(0, DEV_H))   # A: 1 unit = 1 inch

W <- vapply(LABELS, function(s) strwidth(s, cex = CEX, font = FONT), numeric(1))

cat(sprintf("\n设备 %.2f x %.2f in | ps=%g cex=%g font=%g\n", DEV_W, DEV_H, PT, CEX, FONT))
cat(sprintf("安全溢出上限 = gap/2 = %.3f in/侧\n\n", GAP_IN / 2))

if (is.null(BANDS) || is.null(ROW_IN)) {
  cat(sprintf("%-20s %8s   %s\n", "label", "width_in", "chars"))
  for (i in seq_along(LABELS))
    cat(sprintf("%-20s %8.3f   %d\n", LABELS[i], W[i], nchar(LABELS[i])))
  cat("\n(未给 --bands/--row-in，只报宽度；要溢出判定请补这两个参数)\n")
} else {
  avail <- BANDS * ROW_IN
  cat(sprintf("%-20s %6s %9s %10s %10s   %s\n",
              "label", "chars", "width_in", "avail_in", "overflow", "verdict"))
  for (i in seq_along(LABELS)) {
    ov <- W[i] - avail[i]
    v <- if (ov <= 0) "OK (fits)"
         else if (ov <= GAP_IN / 2) "tight (spills into gap only)"
         else "OVERFLOWS into neighbour axis"
    cat(sprintf("%-20s %6d %9.3f %10.3f %+10.3f   %s\n",
                LABELS[i], nchar(LABELS[i]), W[i], avail[i], ov, v))
  }
}
cat("\n")
invisible(dev.off())