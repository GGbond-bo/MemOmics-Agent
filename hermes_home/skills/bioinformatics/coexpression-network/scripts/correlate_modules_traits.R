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

# Correlate module eigengenes with sample traits

library(WGCNA)
library(ComplexHeatmap)
library(circlize)

#' Correlate module eigengenes with sample traits
#'
#' @param datExpr Expression matrix
#' @param module_colors Module color assignments
#' @param traits Data frame of sample traits (numeric)
#' @param output_file Path to save heatmap
#' @return List with module eigengenes, correlations, and p-values
correlate_modules_traits <- function(datExpr, module_colors, traits,
                                      output_file = "module_trait_correlation.svg") {

  # Calculate module eigengenes
  MEs <- moduleEigengenes(datExpr, colors = module_colors)$eigengenes
  MEs <- orderMEs(MEs)

  # Convert traits to numeric if needed
  traits_numeric <- data.frame(lapply(traits, function(x) {
    if (is.factor(x) || is.character(x)) {
      as.numeric(as.factor(x))
    } else {
      as.numeric(x)
    }
  }))
  rownames(traits_numeric) <- rownames(traits)

  # Calculate correlations
  module_trait_cor <- cor(MEs, traits_numeric, use = "pairwise.complete.obs")
  module_trait_pval <- corPvalueStudent(module_trait_cor, nrow(datExpr))

  # Create text matrix for heatmap (correlation and p-value)
  text_matrix <- matrix(
    paste0(signif(module_trait_cor, 2), "\n(", signif(module_trait_pval, 1), ")"),
    nrow = nrow(module_trait_cor),
    ncol = ncol(module_trait_cor)
  )

  # Create color function
  col_fun <- colorRamp2(c(-1, 0, 1), c("blue", "white", "red"))

  # Create heatmap with ComplexHeatmap
  ht <- Heatmap(
    module_trait_cor,
    name = "Correlation",
    col = col_fun,
    cluster_rows = FALSE,
    cluster_columns = FALSE,
    show_row_names = TRUE,
    show_column_names = TRUE,
    row_names_side = "left",
    column_names_side = "bottom",
    column_title = "Module-Trait Relationships",
    cell_fun = function(j, i, x, y, width, height, fill) {
      grid.text(text_matrix[i, j], x, y, gp = gpar(fontsize = 8))
    },
    heatmap_legend_param = list(
      title = "Correlation",
      at = c(-1, -0.5, 0, 0.5, 1)
    ),
    width = unit(max(8, ncol(traits) * 1.5), "cm"),
    height = unit(max(8, nrow(module_trait_cor) * 0.5), "cm")
  )

  # Save to file
  svg(output_file, width = max(8, ncol(traits) * 1.5), height = max(8, nrow(module_trait_cor) * 0.4))
  draw(ht)
  dev.off()

  cat("Saved:", output_file, "\n")

  # Return results
  results <- data.frame(
    module = rownames(module_trait_cor),
    stringsAsFactors = FALSE
  )

  for (trait in colnames(module_trait_cor)) {
    results[[paste0(trait, "_cor")]] <- module_trait_cor[, trait]
    results[[paste0(trait, "_pval")]] <- module_trait_pval[, trait]
  }

  return(list(
    MEs = MEs,
    correlations = module_trait_cor,
    pvalues = module_trait_pval,
    results = results
  ))
}
