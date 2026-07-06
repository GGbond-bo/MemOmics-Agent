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

#' Run Over-Representation Analysis (ORA)
#'
#' Performs ORA to test if a gene list overlaps with pathways more than expected by chance.
#' Uses Fisher's exact test / hypergeometric test.
#'
#' @param gene_list Character vector of gene symbols
#' @param term2gene Data frame in TERM2GENE format (columns: term, gene)
#' @param background Character vector of all tested genes (important for correct statistics)
#' @param direction Description of gene list direction (e.g., "upregulated", "downregulated", "all")
#' @param pvalue_cutoff P-value cutoff for reporting (default: 0.05)
#' @param min_size Minimum gene set size (default: 10)
#' @param max_size Maximum gene set size (default: 500)
#' @return enrichResult object from clusterProfiler, or NULL if no genes
#' @export
#'
#' @examples
#' # Upregulated genes
#' ora_up <- run_ora(sig_genes$up, term2gene, sig_genes$background, direction = "upregulated")
#'
#' # Downregulated genes
#' ora_down <- run_ora(sig_genes$down, term2gene, sig_genes$background, direction = "downregulated")

library(clusterProfiler)

run_ora <- function(gene_list, term2gene, background, direction = "all",
                    pvalue_cutoff = 0.05, min_size = 10, max_size = 500) {

  if (length(gene_list) == 0) {
    message(sprintf("No %s genes for ORA", direction))
    return(NULL)
  }

  message(sprintf("\n=== Running ORA (%s, n=%d genes) ===", direction, length(gene_list)))

  ora_result <- enricher(
    gene = gene_list,
    TERM2GENE = term2gene,
    universe = background,  # CRITICAL: specify background
    pvalueCutoff = pvalue_cutoff,
    pAdjustMethod = "BH",
    minGSSize = min_size,
    maxGSSize = max_size
  )

  if (!is.null(ora_result) && nrow(ora_result@result) > 0) {
    n_sig <- sum(ora_result@result$p.adjust < 0.05)
    message(sprintf("ORA complete: %d significant gene sets (FDR < 0.05)", n_sig))
  } else {
    message("No significant enrichments found")
  }

  return(ora_result)
}
