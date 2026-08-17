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

# Identify hub genes within each module

library(WGCNA)

#' Identify hub genes within each module
#'
#' @param datExpr Expression matrix
#' @param module_colors Module assignments
#' @param power Soft-thresholding power
#' @param n_hub Number of hub genes per module
#' @return List with gene info and hub genes per module
identify_hub_genes <- function(datExpr, module_colors, power, n_hub = 10) {

  # Calculate module membership (correlation with module eigengene)
  MEs <- moduleEigengenes(datExpr, colors = module_colors)$eigengenes

  # Calculate gene-module membership
  gene_module_membership <- as.data.frame(cor(datExpr, MEs, use = "p"))
  colnames(gene_module_membership) <- gsub("ME", "MM_", colnames(gene_module_membership))

  # Calculate intramodular connectivity
  adj <- adjacency(datExpr, power = power, type = "signed")

  # Get connectivity for each gene
  connectivity <- intramodularConnectivity(adj, module_colors)

  # Combine results
  gene_info <- data.frame(
    gene = colnames(datExpr),
    module = module_colors,
    kWithin = connectivity$kWithin,
    kOut = connectivity$kOut,
    kTotal = connectivity$kTotal,
    stringsAsFactors = FALSE
  )

  # Add module membership
  gene_info <- cbind(gene_info, gene_module_membership)

  # Identify hub genes per module
  hub_genes <- list()
  modules <- unique(module_colors)
  modules <- modules[modules != "grey"]  # Exclude unassigned

  for (mod in modules) {
    mod_genes <- gene_info[gene_info$module == mod, ]
    mm_col <- paste0("MM_", mod)

    if (mm_col %in% colnames(mod_genes)) {
      # Rank by module membership and connectivity
      mod_genes$hub_score <- abs(mod_genes[[mm_col]]) * mod_genes$kWithin
      mod_genes <- mod_genes[order(-mod_genes$hub_score), ]
      hub_genes[[mod]] <- head(mod_genes, n_hub)
    }
  }

  cat("Identified hub genes for", length(hub_genes), "modules\n")

  return(list(
    gene_info = gene_info,
    hub_genes = hub_genes
  ))
}
