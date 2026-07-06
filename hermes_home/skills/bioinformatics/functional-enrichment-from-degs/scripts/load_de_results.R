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

#' Load and Standardize Differential Expression Results
#'
#' Reads DE results from various tools (DESeq2, limma, edgeR) and standardizes
#' column names for downstream enrichment analysis.
#'
#' @param file_path Path to DE results file (CSV or TSV)
#' @return Data frame with standardized columns: gene, log2FC, padj, stat (if available)
#' @export
#'
#' @examples
#' de_results <- load_de_results("path/to/deseq2_results.csv")
#' head(de_results)

load_de_results <- function(file_path) {
  # Read file
  if (grepl("\\.csv$", file_path)) {
    df <- read.csv(file_path, stringsAsFactors = FALSE)
  } else {
    df <- read.delim(file_path, stringsAsFactors = FALSE)
  }

  # Standardize column names
  col_mapping <- c(
    "gene_symbol" = "gene", "Gene" = "gene", "SYMBOL" = "gene",
    "log2FoldChange" = "log2FC", "logFC" = "log2FC",
    "padj" = "padj", "adj.P.Val" = "padj", "FDR" = "padj",
    "stat" = "stat", "t" = "stat", "statistic" = "stat",
    "pvalue" = "pvalue", "P.Value" = "pvalue", "PValue" = "pvalue"
  )

  for (old_name in names(col_mapping)) {
    if (old_name %in% colnames(df)) {
      colnames(df)[colnames(df) == old_name] <- col_mapping[old_name]
    }
  }

  # Handle unnamed first column (row names)
  if (colnames(df)[1] %in% c("", "X", "Unnamed..0")) {
    colnames(df)[1] <- "gene"
  }

  # Validate required columns
  required <- c("gene", "log2FC", "padj")
  missing <- setdiff(required, colnames(df))
  if (length(missing) > 0) {
    stop(paste("Missing required columns:", paste(missing, collapse = ", ")))
  }

  # Remove NA and duplicates
  initial_n <- nrow(df)
  df <- df[!is.na(df$gene) & !is.na(df$log2FC) & !is.na(df$padj), ]
  df <- df[!duplicated(df$gene), ]

  message(sprintf("Loaded %d genes (removed %d rows with NA/duplicates)",
                  nrow(df), initial_n - nrow(df)))

  cat("\n✓ Data loaded successfully\n\n")

  return(df)
}
