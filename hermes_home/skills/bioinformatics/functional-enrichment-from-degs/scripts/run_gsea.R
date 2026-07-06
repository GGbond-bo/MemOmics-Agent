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

#' Run Gene Set Enrichment Analysis (GSEA)
#'
#' Performs GSEA on a ranked gene list to identify enriched pathways.
#' Tests whether genes in pathways are coordinately up- or down-regulated.
#'
#' @param ranked_genes Named numeric vector (gene names = names, rank metric = values)
#' @param term2gene Data frame in TERM2GENE format (columns: term, gene)
#' @param min_size Minimum gene set size (default: 15)
#' @param max_size Maximum gene set size (default: 500)
#' @param pvalue_cutoff P-value cutoff for reporting (default: 0.05)
#' @param n_perm Number of permutations (default: 10000)
#' @return enrichResult object from clusterProfiler
#' @export
#'
#' @examples
#' gsea_result <- run_gsea(ranked_genes, term2gene, n_perm = 10000)
#' head(as.data.frame(gsea_result))

library(clusterProfiler)

run_gsea <- function(ranked_genes, term2gene, min_size = 15, max_size = 500,
                     pvalue_cutoff = 0.05, n_perm = 10000) {

  message("\n=== Running GSEA ===")

  gsea_result <- GSEA(
    geneList = ranked_genes,
    TERM2GENE = term2gene,
    minGSSize = min_size,
    maxGSSize = max_size,
    pvalueCutoff = pvalue_cutoff,
    pAdjustMethod = "BH",
    nPermSimple = n_perm,
    seed = TRUE,
    verbose = TRUE
  )

  n_sig <- sum(gsea_result@result$p.adjust < 0.05)
  message(sprintf("GSEA complete: %d significant gene sets (FDR < 0.05)", n_sig))

  cat("\n✓ Analysis completed successfully!\n\n")

  return(gsea_result)
}
