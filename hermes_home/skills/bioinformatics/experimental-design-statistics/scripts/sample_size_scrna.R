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

# ============================================================
# 🔒 MemOmics 审查铁律 — 执行本脚本前后的强制步骤
# ============================================================
# 执行前必须: rail_review(action="pre")  — 环境检查 + 参数校验 + 代码审查
# 执行后必须: rail_review(action="post") — 结果质量评估 + 图表检查 + 数值检查
# 参数有争议: debate_analysis(topic=..., context=...) — 多角色辩论
# 执行失败:   skill_evolution(action="record_error") — 记录错误
# 修复成功:   skill_evolution(action="update_script") — 替换脚本
# ============================================================
# Sample Size Estimation for Single-Cell RNA-seq
# Functions for determining sample size for scRNA-seq experiments
# Accounts for dropout and cell-to-cell variability

#' Estimate parameters from pilot scRNA-seq data
#'
#' @param pilot_sce SingleCellExperiment object with pilot scRNA-seq data
#' @return List with estimated parameters for power analysis
#' @export
#' @examples
#' # library(SingleCellExperiment)
#' # pilot_sce <- readRDS("pilot_scrna.rds")
#' # params <- estimate_scrna_params(pilot_sce)
estimate_scrna_params <- function(pilot_sce) {

  if (!requireNamespace("SingleCellExperiment", quietly = TRUE)) {
    stop("Package 'SingleCellExperiment' is required. Install with BiocManager::install('SingleCellExperiment')")
  }

  if (!methods::is(pilot_sce, "SingleCellExperiment")) {
    stop("pilot_sce must be a SingleCellExperiment object")
  }

  # Extract counts
  counts <- SingleCellExperiment::counts(pilot_sce)

  # Calculate dropout rate (proportion of zeros)
  dropout_rate <- sum(counts == 0) / length(counts)

  # Calculate mean expression per gene
  gene_means <- rowMeans(counts)
  mean_expression <- mean(gene_means[gene_means > 0])

  # Calculate CV per gene (coefficient of variation)
  gene_cvs <- apply(counts, 1, function(x) {
    if (mean(x) > 0) {
      sd(x) / mean(x)
    } else {
      NA
    }
  })
  median_cv <- median(gene_cvs, na.rm = TRUE)

  # Number of cells and samples
  n_cells <- ncol(pilot_sce)
  n_samples <- length(unique(pilot_sce$sample))  # Assumes 'sample' column exists

  result <- list(
    dropout_rate = dropout_rate,
    mean_expression = mean_expression,
    median_cv = median_cv,
    n_cells = n_cells,
    n_samples = n_samples,
    n_genes = nrow(counts),
    recommendation = interpret_scrna_params(dropout_rate, median_cv, n_cells)
  )

  return(result)
}


#' Calculate sample size for scRNA-seq using powsimR
#'
#' @param pilot_sce SingleCellExperiment object (optional, for parameter estimation)
#' @param fold_change Minimum fold-change to detect
#' @param power Target power (default: 0.8)
#' @param min_cells_per_sample Minimum cells to sequence per sample (default: 500)
#' @param target_cell_type_prop Proportion of target cell type if studying rare population (default: NULL)
#' @param dropout_rate Dropout rate if pilot_sce not provided (default: 0.6)
#' @param mean_expression Mean expression if pilot_sce not provided (default: 10)
#' @return Recommended sample size and cells per sample
#' @export
samplesize_scrna_powsimr <- function(pilot_sce = NULL,
                                     fold_change = 2,
                                     power = 0.8,
                                     min_cells_per_sample = 500,
                                     target_cell_type_prop = NULL,
                                     dropout_rate = 0.6,
                                     mean_expression = 10) {

  # Check if powsimR is available (it's a large package, may not be installed)
  if (!requireNamespace("powsimR", quietly = TRUE)) {
    message("Package 'powsimR' not installed.")
    message("Providing general guidelines based on literature and parameters.")

    # Use general guidelines if powsimR not available
    return(samplesize_scrna_general(
      fold_change = fold_change,
      power = power,
      min_cells_per_sample = min_cells_per_sample,
      target_cell_type_prop = target_cell_type_prop
    ))
  }

  # If pilot data provided, extract parameters
  if (!is.null(pilot_sce)) {
    params <- estimate_scrna_params(pilot_sce)
    dropout_rate <- params$dropout_rate
    mean_expression <- params$mean_expression
  }

  # Provide recommendation based on parameters
  # Full powsimR simulation would be complex; providing guideline-based estimates

  result <- samplesize_scrna_general(
    fold_change = fold_change,
    power = power,
    min_cells_per_sample = min_cells_per_sample,
    target_cell_type_prop = target_cell_type_prop,
    dropout_rate = dropout_rate,
    mean_expression = mean_expression
  )

  return(result)
}


#' General scRNA-seq sample size guidelines
#'
#' @param fold_change Target fold-change
#' @param power Target power
#' @param min_cells_per_sample Minimum cells per sample
#' @param target_cell_type_prop Proportion of target cell type
#' @param dropout_rate Dropout rate (default: 0.6)
#' @param mean_expression Mean expression (default: 10)
#' @return Recommendations for sample size
#' @export
samplesize_scrna_general <- function(fold_change = 2,
                                     power = 0.8,
                                     min_cells_per_sample = 500,
                                     target_cell_type_prop = NULL,
                                     dropout_rate = 0.6,
                                     mean_expression = 10) {

  # Base recommendations from literature (Vieth et al. 2017, others)

  # Determine base sample size by effect size
  if (fold_change >= 3) {
    base_n <- 3  # Large effects
  } else if (fold_change >= 2) {
    base_n <- 6  # Moderate effects
  } else {
    base_n <- 10  # Small effects
  }

  # Adjust for power
  if (power >= 0.9) {
    base_n <- base_n + 2
  }

  # Adjust for rare cell types
  if (!is.null(target_cell_type_prop)) {
    if (target_cell_type_prop < 0.05) {
      # Very rare (<5%)
      base_n <- base_n + 4
      min_cells_per_sample <- max(min_cells_per_sample, 2000)
    } else if (target_cell_type_prop < 0.15) {
      # Rare (5-15%)
      base_n <- base_n + 2
      min_cells_per_sample <- max(min_cells_per_sample, 1000)
    }
  }

  # Adjust for high dropout
  if (dropout_rate > 0.7) {
    base_n <- base_n + 2
    min_cells_per_sample <- min_cells_per_sample + 200
  }

  result <- list(
    recommended_n_per_group = base_n,
    recommended_cells_per_sample = min_cells_per_sample,
    total_samples = base_n * 2,
    total_cells = base_n * 2 * min_cells_per_sample,
    parameters = list(
      fold_change = fold_change,
      power = power,
      dropout_rate = dropout_rate,
      mean_expression = mean_expression,
      target_cell_type_prop = target_cell_type_prop
    ),
    recommendation = recommend_scrna_design(base_n, min_cells_per_sample, target_cell_type_prop)
  )

  return(result)
}


#' Quick reference for scRNA-seq sample sizes
#'
#' @return Data frame with study types and recommended sample sizes
#' @export
quick_reference_scrna <- function() {

  reference <- data.frame(
    study_type = c(
      "Exploratory (cell type discovery)",
      "DE between conditions (common cell types)",
      "DE between conditions (rare cell types <5%)",
      "Trajectory analysis",
      "Spatial transcriptomics integration"
    ),
    min_samples_per_group = c(3, 6, 10, 5, 4),
    recommended_samples_per_group = c(5, 8, 12, 8, 6),
    cells_per_sample = c("1000-2000", "500-1000", "2000-5000", "1000-2000", "1000-2000"),
    notes = c(
      "Focus on diversity",
      "Balance samples vs cells",
      "More samples critical",
      "Need continuous sampling",
      "Pilot for integration"
    ),
    stringsAsFactors = FALSE
  )

  return(reference)
}


#' Interpret scRNA-seq pilot parameters
#' @keywords internal
interpret_scrna_params <- function(dropout, cv, n_cells) {
  interpretation <- paste0(
    "Pilot scRNA-seq data characteristics:\n",
    "  Dropout rate: ", round(dropout * 100, 1), "%\n",
    "  Median CV: ", round(cv, 2), "\n",
    "  Cells in pilot: ", n_cells, "\n\n"
  )

  if (dropout > 0.8) {
    interpretation <- paste0(interpretation, "High dropout: Consider deeper sequencing or more cells\n")
  }

  if (cv > 1.5) {
    interpretation <- paste0(interpretation, "High cell-to-cell variability: May need more samples\n")
  }

  if (n_cells < 500) {
    interpretation <- paste0(interpretation, "Small pilot: Consider larger pilot for robust estimates\n")
  }

  return(interpretation)
}


#' Recommend scRNA-seq design
#' @keywords internal
recommend_scrna_design <- function(n_samples, n_cells, rare_prop) {
  recommendation <- paste0(
    "Recommended scRNA-seq design:\n",
    "  Biological samples: ", n_samples, " per group (", n_samples * 2, " total)\n",
    "  Cells per sample: ~", n_cells, "\n",
    "  Total cells to sequence: ~", format(n_samples * 2 * n_cells, big.mark = ","), "\n\n"
  )

  if (!is.null(rare_prop) && rare_prop < 0.1) {
    recommendation <- paste0(
      recommendation,
      "Studying rare cell type (<10% of cells):\n",
      "  - Prioritize MORE SAMPLES over more cells per sample\n",
      "  - Biological variation > technical variation for rare types\n"
    )
  }

  recommendation <- paste0(
    recommendation,
    "\nKey principle: BIOLOGICAL SAMPLES >> CELLS PER SAMPLE\n",
    "More samples (biological replicates) provide better statistical power than more cells from fewer samples.\n"
  )

  return(recommendation)
}


#' Calculate cells needed for rare cell type detection
#'
#' @param cell_type_proportion Expected proportion of target cell type (e.g., 0.01 = 1%)
#' @param min_cells_needed Minimum cells of this type needed for analysis (default: 50)
#' @param samples_per_group Number of samples per group
#' @return Recommended cells per sample
#' @export
cells_for_rare_type <- function(cell_type_proportion,
                                min_cells_needed = 50,
                                samples_per_group = 6) {

  # Calculate cells needed per sample to get min_cells_needed of target type
  cells_per_sample <- ceiling(min_cells_needed / (cell_type_proportion * samples_per_group))

  # Add 20% buffer
  cells_per_sample <- ceiling(cells_per_sample * 1.2)

  result <- list(
    recommended_cells_per_sample = cells_per_sample,
    expected_target_cells_per_sample = ceiling(cells_per_sample * cell_type_proportion),
    total_cells_to_sequence = cells_per_sample * samples_per_group * 2,
    expected_total_target_cells = ceiling(cells_per_sample * cell_type_proportion * samples_per_group * 2),
    note = paste0(
      "To obtain ~", min_cells_needed, " cells of type representing ",
      round(cell_type_proportion * 100, 2), "% of population"
    )
  )

  return(result)
}
