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

# Generate all WGCNA visualizations
# This script consolidates all plotting steps into a single function

library(WGCNA)

#' Generate all WGCNA plots
#'
#' @param results Results object from run_wgcna_analysis()
#' @param output_dir Directory to save plots (default: current directory)
#' @param output_prefix Prefix for output files (default: "wgcna")
plot_all_wgcna <- function(results, output_dir = ".", output_prefix = "wgcna") {

  cat("\n=== Generating WGCNA Visualizations ===\n\n")

  # Create output directory if needed
  if (!dir.exists(output_dir)) {
    dir.create(output_dir, recursive = TRUE)
  }

  # Plot 1: Module dendrogram
  cat("Generating module dendrogram...\n")
  source("scripts/plot_module_dendrogram.R")
  plot_module_dendrogram(
    results$network$net,
    results$module_colors,
    output_file = file.path(output_dir, paste0(output_prefix, "_module_dendrogram"))
  )

  # Plot 2: Eigengene heatmap
  cat("Generating eigengene heatmap...\n")
  source("scripts/plot_eigengene_heatmap.R")
  plot_eigengene_heatmap(
    results$trait_results$MEs,
    results$meta,
    output_file = file.path(output_dir, paste0(output_prefix, "_eigengene_heatmap"))
  )

  # Plot 3: Module-trait correlation heatmap (if available)
  if (!is.null(results$trait_results)) {
    cat("Generating module-trait correlation heatmap...\n")
    tryCatch({
      # Use built-in WGCNA function for trait correlation plot
      trait_data <- results$meta[, sapply(results$meta, is.numeric), drop = FALSE]
      if (ncol(trait_data) > 0) {
        MEs <- results$trait_results$MEs
        moduleTraitCor <- cor(MEs, trait_data, use = "p")
        moduleTraitPvalue <- corPvalueStudent(moduleTraitCor, nrow(trait_data))

        # Save PNG
        png(file.path(output_dir, paste0(output_prefix, "_module_trait_correlation.png")),
            width = 10, height = 8, units = "in", res = 300)
        textMatrix <- paste(signif(moduleTraitCor, 2), "\n(",
                           signif(moduleTraitPvalue, 1), ")", sep = "")
        dim(textMatrix) <- dim(moduleTraitCor)
        labeledHeatmap(Matrix = moduleTraitCor,
                      xLabels = colnames(trait_data),
                      yLabels = names(MEs),
                      ySymbols = names(MEs),
                      colorLabels = FALSE,
                      colors = blueWhiteRed(50),
                      textMatrix = textMatrix,
                      setStdMargins = FALSE,
                      cex.text = 0.5,
                      zlim = c(-1, 1),
                      main = "Module-Trait Relationships")
        dev.off()
        cat("   Saved:", file.path(output_dir, paste0(output_prefix, "_module_trait_correlation.png")), "\n")

        # Try SVG
        tryCatch({
          svg(file.path(output_dir, paste0(output_prefix, "_module_trait_correlation.svg")),
              width = 10, height = 8)
          labeledHeatmap(Matrix = moduleTraitCor,
                        xLabels = colnames(trait_data),
                        yLabels = names(MEs),
                        ySymbols = names(MEs),
                        colorLabels = FALSE,
                        colors = blueWhiteRed(50),
                        textMatrix = textMatrix,
                        setStdMargins = FALSE,
                        cex.text = 0.5,
                        zlim = c(-1, 1),
                        main = "Module-Trait Relationships")
          dev.off()
          cat("   Saved:", file.path(output_dir, paste0(output_prefix, "_module_trait_correlation.svg")), "\n")
        }, error = function(e) {
          cat("   (SVG export failed)\n")
        })
      }
    }, error = function(e) {
      cat("   (Module-trait correlation plot skipped:", e$message, ")\n")
    })
  }

  # Plot 4: Hub genes barplot
  cat("Generating hub genes barplot...\n")
  source("scripts/plot_hub_genes.R")
  plot_hub_genes(
    results$hub_results$hub_genes,
    output_file = file.path(output_dir, paste0(output_prefix, "_hub_genes_barplot"))
  )

  cat("\n✓ All WGCNA plots generated successfully!\n\n")
}
