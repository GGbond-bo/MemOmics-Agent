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

# Build co-expression network and detect modules

library(WGCNA)

#' Build co-expression network and detect modules
#'
#' @param datExpr Expression matrix (samples x genes)
#' @param power Soft-thresholding power
#' @param min_module_size Minimum genes per module
#' @param merge_cut_height Height for merging similar modules
#' @return List containing network object, module colors, and module labels
build_network <- function(datExpr, power, min_module_size = 30, merge_cut_height = 0.25) {

  cat("Building network with power =", power, "\n")

  # One-step network construction and module detection
  net <- blockwiseModules(
    datExpr,
    power = power,
    TOMType = "signed",
    networkType = "signed",
    minModuleSize = min_module_size,
    reassignThreshold = 0,
    mergeCutHeight = merge_cut_height,
    numericLabels = TRUE,
    pamRespectsDendro = FALSE,
    saveTOMs = FALSE,
    verbose = 3
  )

  # Convert numeric labels to colors
  module_colors <- labels2colors(net$colors)

  cat("\nModule detection complete:\n")
  cat("Number of modules:", length(unique(module_colors)) - 1, "(excluding grey/unassigned)\n")
  print(table(module_colors))

  return(list(
    net = net,
    module_colors = module_colors,
    module_labels = net$colors
  ))
}
