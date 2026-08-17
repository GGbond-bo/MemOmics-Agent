# ============================================================
# 🔒 MemOmics 审查与辩论机制 + 自进化日志
# ============================================================
# 此脚本由 MemOmics Agent 执行。原脚本永远不被修改。
#
# 执行前必须:
#   1. rail_review(action="pre")  — 检查环境/参数/数据
#   2. skill_evolution(action="query_logs", script_name="本脚本名",
#      species="物种", tissue="组织", direction="方向")
#      → 查同类运行日志，有则参考已有参数和经验，无则按原脚本执行
#   3. debate_analysis(topic, context) — 参数不确定时多角色辩论
#
# 执行后必须:
#   1. rail_review(action="post") — 检查输出/质量/图表
#   2. 如果通过 → skill_evolution(action="record_run",
#      script_name="本脚本名", species="物种", tissue="组织",
#      direction="方向", params_used="参数JSON", result_summary="结果",
#      quality_score=8, notes="经验总结")
#      → 记录成功运行日志，供后续同类型分析参考
#   3. 如果失败 → skill_evolution(action="record_error",
#      script_name="本脚本名", species="物种", tissue="组织",
#      direction="方向", error_message="报错", root_cause="根因",
#      fix_applied="修复方案")
#      → 记录错误日志，修正后重跑
#
# 日志存储: skill 目录下 .run_logs/ 目录，按 物种_组织_方向_日期 命名
# ============================================================

# Plotting Helper Functions for WGCNA
# Provides robust plot saving with PNG + SVG export and graceful fallback

# Try to load svglite for high-quality SVG (optional)
.has_svglite <- requireNamespace("svglite", quietly = TRUE)
if (.has_svglite) {
    library(svglite)
}

#' Save base R plot to both PNG and SVG formats
#'
#' Helper function for WGCNA plots that use base R graphics.
#' Takes a plotting expression and saves it to both PNG and SVG.
#'
#' @param plot_expr Expression that creates the plot (use substitute() or quote())
#' @param base_path Path without extension (e.g., "output/dendrogram")
#' @param width Plot width in inches (default: 12)
#' @param height Plot height in inches (default: 8)
#' @param dpi Resolution for PNG (default: 300)
#'
#' @examples
#' .save_base_plot(
#'   quote(plotDendroAndColors(net$dendrograms[[1]], colors, "Modules")),
#'   "module_dendrogram",
#'   width = 12,
#'   height = 8
#' )
.save_base_plot <- function(plot_expr, base_path, width = 12, height = 8, dpi = 300) {

    # Remove extension if provided
    base_path <- sub("\\.(svg|png)$", "", base_path)

    # Always save PNG first
    png_path <- paste0(base_path, ".png")
    png(png_path, width = width, height = height, units = "in", res = dpi)
    eval(plot_expr)
    dev.off()
    cat("   Saved:", png_path, "\n")

    # Always try SVG - base R svg() device
    svg_path <- paste0(base_path, ".svg")
    tryCatch({
        svg(svg_path, width = width, height = height)
        eval(plot_expr)
        dev.off()
        cat("   Saved:", svg_path, "\n")
    }, error = function(e) {
        cat("   (SVG export failed)\n")
    })
}

#' Save ggplot object to both PNG and SVG formats
#'
#' Helper function for ggplot-based plots (if any are added to this skill).
#'
#' @param plot ggplot object to save
#' @param base_path Path without extension
#' @param width Plot width in inches
#' @param height Plot height in inches
#' @param dpi Resolution for PNG
.save_ggplot <- function(plot, base_path, width = 8, height = 6, dpi = 300) {

    # Remove extension if provided
    base_path <- sub("\\.(svg|png)$", "", base_path)

    # Always save PNG
    png_path <- paste0(base_path, ".png")
    ggsave(png_path, plot = plot, width = width, height = height, dpi = dpi, device = "png")
    cat("   Saved:", png_path, "\n")

    # Always try SVG - try ggsave first, fall back to svg() device
    svg_path <- paste0(base_path, ".svg")
    tryCatch({
        ggsave(svg_path, plot = plot, width = width, height = height, device = "svg")
        cat("   Saved:", svg_path, "\n")
    }, error = function(e) {
        # If ggsave fails, try base R svg() device directly
        tryCatch({
            svg(svg_path, width = width, height = height)
            print(plot)
            dev.off()
            cat("   Saved:", svg_path, "\n")
        }, error = function(e2) {
            cat("   (SVG export failed)\n")
        })
    })
}
