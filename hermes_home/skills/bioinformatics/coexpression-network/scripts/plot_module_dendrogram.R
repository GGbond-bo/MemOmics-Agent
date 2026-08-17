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

# Create module dendrogram with colors

library(WGCNA)

#' Create module dendrogram with colors (PNG + SVG)
#'
#' @param net Network object from blockwiseModules
#' @param module_colors Module color assignments
#' @param output_file Output file path (without extension, or will be stripped)
plot_module_dendrogram <- function(net, module_colors, output_file = "module_dendrogram") {

  # Remove extension if provided
  output_file <- sub("\\.(svg|png)$", "", output_file)

  # Save PNG (always)
  png_path <- paste0(output_file, ".png")
  png(png_path, width = 12, height = 8, units = "in", res = 300)
  plotDendroAndColors(
    net$dendrograms[[1]],
    module_colors[net$blockGenes[[1]]],
    "Module colors",
    dendroLabels = FALSE,
    hang = 0.03,
    addGuide = TRUE,
    guideHang = 0.05,
    main = "Gene Dendrogram and Module Colors"
  )
  dev.off()
  cat("   Saved:", png_path, "\n")

  # Try SVG with fallback
  svg_path <- paste0(output_file, ".svg")
  tryCatch({
    svg(svg_path, width = 12, height = 8)
    plotDendroAndColors(
      net$dendrograms[[1]],
      module_colors[net$blockGenes[[1]]],
      "Module colors",
      dendroLabels = FALSE,
      hang = 0.03,
      addGuide = TRUE,
      guideHang = 0.05,
      main = "Gene Dendrogram and Module Colors"
    )
    dev.off()
    cat("   Saved:", svg_path, "\n")
  }, error = function(e) {
    cat("   (SVG export failed)\n")
  })
}
