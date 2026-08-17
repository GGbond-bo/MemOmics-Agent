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

# Create hub gene network visualization

library(WGCNA)
library(ggplot2)
library(ggprism)

# Try to load svglite for high-quality SVG (optional)
.has_svglite <- requireNamespace("svglite", quietly = TRUE)
if (.has_svglite) {
  library(svglite)
}

#' Save plot in both PNG and SVG formats with graceful fallback
#'
#' @param plot ggplot object
#' @param base_path Base file path (without extension)
#' @param width Width in inches
#' @param height Height in inches
#' @param dpi Resolution for PNG
.save_plot <- function(plot, base_path, width = 12, height = 8, dpi = 300) {
  # Always save PNG
  png_path <- sub("\\.(svg|png)$", ".png", base_path)
  ggsave(png_path, plot = plot, width = width, height = height, dpi = dpi, device = "png")
  cat("   Saved:", png_path, "\n")

  # Always try SVG - try ggsave first, fall back to svg() device
  svg_path <- sub("\\.(svg|png)$", ".svg", base_path)
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

#' Create hub gene network visualization
#'
#' @param hub_genes List of hub genes per module
#' @param output_file Output file path (without extension, or will be stripped)
plot_hub_genes <- function(hub_genes, output_file = "hub_genes_barplot") {

  # Combine hub genes from all modules
  hub_df <- do.call(rbind, lapply(names(hub_genes), function(mod) {
    df <- hub_genes[[mod]][1:min(5, nrow(hub_genes[[mod]])), ]
    df$module <- mod
    df
  }))

  # Create plot with ggprism theme
  p <- ggplot(hub_df, aes(x = reorder(gene, kWithin), y = kWithin, fill = module)) +
    geom_bar(stat = "identity") +
    coord_flip() +
    facet_wrap(~module, scales = "free_y") +
    labs(x = "Gene", y = "Intramodular Connectivity",
         title = "Top Hub Genes per Module") +
    theme_prism(base_size = 12) +
    theme(legend.position = "none")

  # Save to both PNG and SVG
  plot_height <- max(8, nrow(hub_df) * 0.3)
  .save_plot(p, output_file, width = 12, height = plot_height, dpi = 300)
}
