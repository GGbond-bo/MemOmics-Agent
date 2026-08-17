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

# Load and prepare expression data for WGCNA

library(WGCNA)

#' Load and prepare expression data for WGCNA
#'
#' @param expr_file Path to expression matrix (genes x samples)
#' @param meta_file Path to sample metadata
#' @param top_n_genes Number of most variable genes to keep
#' @param min_samples Minimum samples required
#' @return List containing datExpr, metadata, and gene info
prepare_wgcna_data <- function(expr_file, meta_file, top_n_genes = 5000, min_samples = 15) {

  # Load expression data
  if (grepl("\\.csv$", expr_file)) {
    expr_data <- read.csv(expr_file, row.names = 1, check.names = FALSE)
  } else {
    expr_data <- read.delim(expr_file, row.names = 1, check.names = FALSE)
  }

  # Load metadata
  if (grepl("\\.csv$", meta_file)) {
    meta_data <- read.csv(meta_file, row.names = 1)
  } else {
    meta_data <- read.delim(meta_file, row.names = 1)
  }

  cat("Expression matrix:", nrow(expr_data), "genes x", ncol(expr_data), "samples\n")
  cat("Metadata:", nrow(meta_data), "samples\n")

  # Check sample count
  if (ncol(expr_data) < min_samples) {
    warning(paste("Only", ncol(expr_data), "samples. WGCNA works best with 15+ samples."))
  }

  # Match samples between expression and metadata
  common_samples <- intersect(colnames(expr_data), rownames(meta_data))
  if (length(common_samples) < ncol(expr_data)) {
    cat("Using", length(common_samples), "samples present in both expression and metadata\n")
  }

  expr_data <- expr_data[, common_samples]
  meta_data <- meta_data[common_samples, , drop = FALSE]

  # Remove genes with too many missing values or zero variance
  good_genes <- apply(expr_data, 1, function(x) {
    sum(is.na(x)) < 0.1 * length(x) && var(x, na.rm = TRUE) > 0
  })
  expr_data <- expr_data[good_genes, ]
  cat("Genes after filtering:", nrow(expr_data), "\n")

  # Select top variable genes
  gene_var <- apply(expr_data, 1, var, na.rm = TRUE)
  top_genes <- names(sort(gene_var, decreasing = TRUE))[1:min(top_n_genes, nrow(expr_data))]
  expr_data <- expr_data[top_genes, ]
  cat("Selected top", nrow(expr_data), "variable genes\n")

  # Transpose for WGCNA (samples as rows, genes as columns)
  datExpr <- t(expr_data)

  # Check for outlier samples
  gsg <- goodSamplesGenes(datExpr, verbose = 3)
  if (!gsg$allOK) {
    datExpr <- datExpr[gsg$goodSamples, gsg$goodGenes]
    cat("Removed outlier samples/genes\n")
  }

  return(list(
    datExpr = datExpr,
    meta = meta_data,
    gene_info = data.frame(gene = colnames(datExpr), variance = gene_var[colnames(datExpr)])
  ))
}
