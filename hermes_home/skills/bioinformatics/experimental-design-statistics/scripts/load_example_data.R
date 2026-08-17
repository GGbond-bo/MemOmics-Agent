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
# Load Example Data for Experimental Design
# Provides pilot data for testing power analysis and sample size calculations

#' Load example pilot data for experimental design testing
#'
#' Downloads and prepares example RNA-seq count data with known variability
#' characteristics for testing power analysis and sample size calculations.
#'
#' @return List with components:
#'   - counts: Raw count matrix
#'   - metadata: Sample metadata (condition, batch, etc.)
#'   - dds: DESeqDataSet object (for DESeq2-based calculations)
#'   - dispersions: Gene-level dispersion estimates
#'   - cv: Coefficient of variation summary
#'
#' @export
load_example_data <- function() {

  # Set CRAN mirror
  options(repos = c(CRAN = "https://cloud.r-project.org"))

  message("\n=== Loading Example Pilot Data ===\n")

  # Check and install required packages
  required_packages <- c("pasilla", "DESeq2")

  for (pkg in required_packages) {
    if (!requireNamespace(pkg, quietly = TRUE)) {
      message(paste0("Installing ", pkg, " package..."))
      if (pkg %in% c("pasilla", "DESeq2")) {
        if (!requireNamespace("BiocManager", quietly = TRUE)) {
          install.packages("BiocManager")
        }
        BiocManager::install(pkg, update = FALSE, ask = FALSE)
      } else {
        install.packages(pkg)
      }
    }
  }

  # Load libraries
  suppressPackageStartupMessages({
    library(pasilla)
    library(DESeq2)
  })

  message("Loading pasilla RNA-seq pilot data (Drosophila, Brooks et al. 2011)...")

  # Load real pasilla count data
  fn_counts <- system.file("extdata", "pasilla_gene_counts.tsv", package = "pasilla")
  fn_samples <- system.file("extdata", "pasilla_sample_annotation.csv", package = "pasilla")

  counts_raw <- read.table(fn_counts, header = TRUE, row.names = 1)
  sample_info <- read.csv(fn_samples, row.names = 1)

  # Fix sample name alignment (annotation has "fb" suffix, counts don't)
  sample_info$sample_id <- sub("fb$", "", rownames(sample_info))
  rownames(sample_info) <- sample_info$sample_id
  sample_info <- sample_info[colnames(counts_raw), ]

  # Create clean metadata
  metadata <- data.frame(
    sample_id = sample_info$sample_id,
    condition = sample_info$condition,
    type = sample_info$type,
    stringsAsFactors = FALSE
  )
  rownames(metadata) <- metadata$sample_id

  # Filter low-count genes (require >=10 counts in at least 3 samples)
  keep <- rowSums(counts_raw >= 10) >= 3
  counts_filtered <- counts_raw[keep, ]

  message(paste0("  Samples: ", ncol(counts_filtered)))
  message(paste0("  Genes: ", nrow(counts_filtered)))
  message(paste0("  Conditions: ", paste(unique(metadata$condition), collapse = ", ")))

  # Create DESeqDataSet
  dds <- DESeqDataSetFromMatrix(
    countData = counts_filtered,
    colData = metadata,
    design = ~ condition
  )

  # Run DESeq2 to get dispersion estimates
  message("\nCalculating dispersion estimates for power analysis...")
  dds <- DESeq(dds, quiet = TRUE)

  # Extract dispersion estimates
  dispersions <- dispersions(dds)

  # Calculate coefficient of variation (CV)
  # CV is useful for power calculations
  normalized_counts <- counts(dds, normalized = TRUE)
  gene_means <- rowMeans(normalized_counts)
  gene_sds <- apply(normalized_counts, 1, sd)
  gene_cvs <- gene_sds / gene_means

  # Summary CV (median is more robust than mean)
  median_cv <- median(gene_cvs[is.finite(gene_cvs) & gene_cvs > 0], na.rm = TRUE)
  mean_cv <- mean(gene_cvs[is.finite(gene_cvs) & gene_cvs > 0], na.rm = TRUE)

  message(paste0("\nVariability estimates from pilot data:"))
  message(paste0("  Median CV: ", round(median_cv, 3)))
  message(paste0("  Mean CV: ", round(mean_cv, 3)))
  message(paste0("  Median dispersion: ", round(median(dispersions, na.rm = TRUE), 4)))

  # Create planned experiment metadata for batch design demo
  # Simulates a full experiment with recommended n based on pilot data
  set.seed(42)
  n_per_group <- 10  # ~n needed for FC=1.5 at 90% power with this CV
  planned_metadata <- data.frame(
    sample_id = paste0("S", sprintf("%02d", 1:(2 * n_per_group))),
    condition = rep(c("untreated", "treated"), each = n_per_group),
    # Template: perfectly balanced for demo. Real experiments will have actual sex distribution.
    sex = rep(c("F", "M"), times = n_per_group),
    age_group = sample(rep(c("young", "old"), times = n_per_group)),
    stringsAsFactors = FALSE
  )

  message("\n✓ Example pilot data loaded successfully!\n")
  message("  Pilot data: ", ncol(dds), " samples, ", nrow(dds), " genes")
  message("  Median CV: ", round(median_cv, 3), " (", unique(metadata$condition)[1],
          " vs ", unique(metadata$condition)[2], ")")
  message("  Planned experiment metadata: ", nrow(planned_metadata), " samples for batch design")

  # Return all components
  return(list(
    counts = counts_filtered,
    metadata = metadata,
    dds = dds,
    dispersions = dispersions,
    cv = list(
      median = median_cv,
      mean = mean_cv,
      per_gene = gene_cvs[is.finite(gene_cvs)]
    ),
    planned_metadata = planned_metadata
  ))
}


#' Load tissue-specific CV database
#'
#' Loads literature-derived coefficient of variation values for different
#' tissue types when pilot data is not available.
#'
#' @param tissue_type Optional: filter to specific tissue
#' @return Data frame with tissue-specific CV values
#'
#' @export
load_cv_database <- function(tissue_type = NULL) {

  cv_file <- "references/cv_tissue_database.csv"

  if (!file.exists(cv_file)) {
    stop(paste0("CV database not found: ", cv_file,
                "\nPlease ensure you are in the experimental-design-statistics directory."))
  }

  cv_db <- read.csv(cv_file, stringsAsFactors = FALSE)

  if (!is.null(tissue_type)) {
    cv_db <- cv_db[cv_db$tissue == tissue_type, ]
    if (nrow(cv_db) == 0) {
      stop(paste0("Tissue type '", tissue_type, "' not found in database."))
    }
  }

  message(paste0("✓ Loaded CV estimates for ", nrow(cv_db), " tissue type(s)"))

  return(cv_db)
}


#' Quick test of experimental design workflow
#'
#' Demonstrates complete workflow with example data
#'
#' @export
test_workflow <- function() {

  message("\n=== Testing Experimental Design Workflow ===\n")

  # Load example data
  pilot_data <- load_example_data()

  message("\n--- Step 1: Example data loaded ---")
  message("Use pilot_data$dds for power calculations")
  message("Use pilot_data$cv$median for sample size estimation")
  message("Use pilot_data$planned_metadata for batch design\n")

  message("Next steps:")
  message("  1. Run power analysis: source('scripts/power_rnaseq.R')")
  message("  2. Calculate sample size: source('scripts/sample_size_de.R')")
  message("  3. Design batch layout: source('scripts/batch_assignment.R')")
  message("  4. Export design: source('scripts/export_design.R')")

  invisible(pilot_data)
}
