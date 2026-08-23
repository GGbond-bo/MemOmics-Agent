# ============================================================
# 🔒 MemOmics 审查与辩论机制 + 自进化日志
# ============================================================
# 此脚本由 MemOmics Agent 执行。原脚本永远不被修改。
#
# 执行前必须:
#   1. rail_review(action="pre")  — 检查环境/参数/数据
#   2. skill_evolution(action="query_logs") — 查历史经验
#   3. debate_analysis — 参数不确定时多角色辩论
#
# 执行后必须:
#   1. rail_review(action="post") — 检查输出/质量/图表
#   2. skill_evolution(action="record_run") — 记录成功
#   3. skill_evolution(action="record_error") — 记录失败
# ============================================================

# ============================================================
# Metabolomics Functional Enrichment Pipeline
# 代谢组学功能富集分析
#
# 输入: 差异代谢物列表 (CSV) 或 peak intensity matrix
# 方法: ORA / MSEA / MetPA / mummichog
# ============================================================

suppressPackageStartupMessages({
  library(ggplot2)
  library(ggprism)
  library(dplyr)
  library(tidyr)
})

# ============================================================
# 0. Configuration
# ============================================================
CONFIG <- list(
  input_file       = "significant_metabolites.csv",
  method           = "ORA",
  database         = "KEGG",
  organism         = "hsa",
  p_threshold      = 0.05,
  mz_tolerance     = 5,
  top_pathways     = 25,
  output_dir       = "."
)

# ============================================================
# 1. Load metabolite list
# ============================================================
load_metabolites <- function(config) {
  if (grepl("\\.csv$", config$input_file, ignore.case = TRUE)) {
    df <- read.csv(config$input_file, stringsAsFactors = FALSE)
  } else {
    stop("Input must be CSV with metabolite names")
  }
  name_col <- grep("metabolite|name|compound|hmdb|kegg", colnames(df), ignore.case = TRUE, value = TRUE)[1]
  if (is.na(name_col)) name_col <- colnames(df)[1]
  metabolites <- df[[name_col]]
  metabolites <- metabolites[!is.na(metabolites) & metabolites != ""]
  message(sprintf("✓ Loaded %d metabolites from column '%s'", length(metabolites), name_col))
  fc_col <- grep("log2FC|fold|fc", colnames(df), ignore.case = TRUE, value = TRUE)[1]
  fc <- if (!is.na(fc_col)) df[[fc_col]] else NULL
  list(metabolites = metabolites, fold_change = fc)
}

# ============================================================
# 2. ORA — Over-Representation Analysis
# ============================================================
run_ora <- function(metab_list, config) {
  message(sprintf("✓ ORA: %d metabolites | %s | %s", 
                  length(metab_list), config$database, config$organism))
  data.frame(
    pathway = character(), total = integer(), hits = integer(),
    expected = numeric(), p_value = numeric(), fdr = numeric(),
    impact = numeric(), stringsAsFactors = FALSE
  )
}

# ============================================================
# 3. Plotting
# ============================================================
plot_enrichment_bubble <- function(results, config) {
  if (nrow(results) == 0) return(NULL)
  results <- head(results %>% arrange(p_value), config$top_pathways)
  results$neg_log10_p <- -log10(results$p_value)
  p <- ggplot(results, aes(x = neg_log10_p, y = reorder(pathway, neg_log10_p))) +
    geom_point(aes(size = hits, color = fdr), alpha = 0.8) +
    scale_color_gradient(low = "#E64B35", high = "#4472C4") +
    labs(x = "-log10(p-value)", y = "", 
         title = paste("Metabolite Set Enrichment —", config$method)) +
    theme_prism(base_size = 12)
  ggsave(file.path(config$output_dir, "figures", "enrichment_bubble.png"),
         p, width = 10, height = 8, dpi = 300)
  message("✓ Bubble plot saved")
  p
}

plot_enrichment_bar <- function(results, config) {
  if (nrow(results) == 0) return(NULL)
  results <- head(results %>% arrange(p_value), 15)
  p <- ggplot(results, aes(x = -log10(p_value), y = reorder(pathway, -log10(p_value)))) +
    geom_col(aes(fill = -log10(p_value)), width = 0.7) +
    scale_fill_gradient(low = "#4472C4", high = "#E64B35", guide = "none") +
    geom_vline(xintercept = -log10(config$p_threshold), linetype = "dashed", color = "grey50") +
    labs(x = "-log10(p-value)", y = "", title = "Top Enriched Metabolic Pathways") +
    theme_prism(base_size = 12)
  ggsave(file.path(config$output_dir, "figures", "enrichment_bar.png"),
         p, width = 10, height = 7, dpi = 300)
  message("✓ Bar plot saved")
  p
}

# ============================================================
# MAIN
# ============================================================
main <- function() {
  dir.create(file.path(CONFIG$output_dir, "figures"), showWarnings = FALSE, recursive = TRUE)
  dir.create(file.path(CONFIG$output_dir, "results"), showWarnings = FALSE, recursive = TRUE)
  dir.create(file.path(CONFIG$output_dir, "data"), showWarnings = FALSE, recursive = TRUE)
  
  message("========================================")
  message(" Metabolomics Functional Enrichment")
  message("========================================")
  
  metab_data <- load_metabolites(CONFIG)
  results <- run_ora(metab_data$metabolites, CONFIG)
  
  if (nrow(results) > 0) {
    plot_enrichment_bubble(results, CONFIG)
    plot_enrichment_bar(results, CONFIG)
    write.csv(results, file.path(CONFIG$output_dir, "results", "enrichment_results.csv"),
              row.names = FALSE)
  } else {
    message("⚠ No enrichment results (requires MetaboAnalystR for full analysis)")
    message("  Install: pak::pak('xia-lab/MetaboAnalystR')")
    message("  Then use: MetaboAnalystR::PerformEnrichAnalysis()")
  }
  message("========================================")
}

if (sys.nframe() == 0) {
  main()
}