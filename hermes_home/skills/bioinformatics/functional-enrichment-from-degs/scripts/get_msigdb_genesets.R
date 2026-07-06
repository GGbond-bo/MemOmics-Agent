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

#' Get MSigDB Gene Sets
#'
#' Retrieves gene sets from MSigDB for use in enrichment analysis.
#' Supports multiple databases and species.
#'
#' @param species Species name: "human" or "mouse" (default: "human")
#' @param categories Vector of category names to include (default: c("H"))
#'   Options: "H" (Hallmark), "KEGG", "REACTOME", "GO:BP", "GO:MF", "GO:CC"
#' @return Data frame in TERM2GENE format (columns: term, gene)
#' @export
#'
#' @examples
#' # Hallmark gene sets only (default)
#' term2gene <- get_msigdb_genesets(species = "human", categories = c("H"))
#'
#' # Hallmark + KEGG
#' term2gene <- get_msigdb_genesets(species = "human", categories = c("H", "KEGG"))
#'
#' # GO Biological Process
#' term2gene <- get_msigdb_genesets(species = "human", categories = c("GO:BP"))

library(msigdbr)

get_msigdb_genesets <- function(species = "human", categories = c("H")) {
  # Map species
  species_name <- ifelse(species == "human", "Homo sapiens", "Mus musculus")

  # Category mapping (updated for msigdbr >= 10.0.0)
  cat_map <- list(
    "H" = list(collection = "H", subcollection = NULL),           # Hallmark
    "KEGG" = list(collection = "C2", subcollection = "CP:KEGG"),  # KEGG
    "REACTOME" = list(collection = "C2", subcollection = "CP:REACTOME"),
    "GO:BP" = list(collection = "C5", subcollection = "GO:BP"),
    "GO:MF" = list(collection = "C5", subcollection = "GO:MF"),
    "GO:CC" = list(collection = "C5", subcollection = "GO:CC"),
    # Support for old-style subcategory format (e.g., "C2:CP:KEGG")
    "C2:CP:KEGG" = list(collection = "C2", subcollection = "CP:KEGG"),
    "C2:CP:REACTOME" = list(collection = "C2", subcollection = "CP:REACTOME"),
    "C5:GO:BP" = list(collection = "C5", subcollection = "GO:BP"),
    "C5:GO:MF" = list(collection = "C5", subcollection = "GO:MF"),
    "C5:GO:CC" = list(collection = "C5", subcollection = "GO:CC")
  )

  all_genesets <- list()

  for (cat in categories) {
    if (!cat %in% names(cat_map)) {
      warning(sprintf("Unknown category: %s", cat))
      next
    }

    params <- cat_map[[cat]]

    # Use new msigdbr API (collection/subcollection instead of category/subcategory)
    if (is.null(params$subcollection)) {
      msig <- msigdbr(species = species_name, collection = params$collection)
    } else {
      msig <- msigdbr(species = species_name, collection = params$collection,
                      subcollection = params$subcollection)
    }

    # Convert to list format for clusterProfiler
    gs <- split(msig$gene_symbol, msig$gs_name)
    all_genesets <- c(all_genesets, gs)

    message(sprintf("Loaded %d gene sets from %s", length(unique(msig$gs_name)), cat))
  }

  # Convert to TERM2GENE format
  term2gene <- do.call(rbind, lapply(names(all_genesets), function(term) {
    data.frame(term = term, gene = all_genesets[[term]], stringsAsFactors = FALSE)
  }))

  return(term2gene)
}
