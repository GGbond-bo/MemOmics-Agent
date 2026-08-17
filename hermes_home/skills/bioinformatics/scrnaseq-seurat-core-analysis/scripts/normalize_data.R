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

# ============================================================================
# DATA NORMALIZATION
# ============================================================================
#
# This script normalizes expression data using either SCTransform or LogNormalize.
#
# Functions:
#   - run_sctransform(): Normalize with SCTransform (recommended for UMI data)
#   - run_lognormalize(): Normalize with LogNormalize (classic workflow)
#   - scale_data(): Scale data (for LogNormalize workflow)
#
# Usage:
#   source("scripts/normalize_data.R")
#   # For SCTransform (recommended)
#   seurat_obj <- run_sctransform(seurat_obj)
#   # OR for LogNormalize
#   seurat_obj <- run_lognormalize(seurat_obj)

#' Normalize data using SCTransform
#'
#' SCTransform is recommended for UMI-based data (e.g., 10X Chromium).
#' It normalizes, finds variable features, and scales data in one step.
#'
#' @param seurat_obj Seurat object (post-filtering)
#' @param vars_to_regress Variables to regress out (default: c("percent.mt"))
#' @param n_genes Number of variable genes to return (default: 3000)
#' @param verbose Print progress (default: TRUE)
#' @return Seurat object with SCT assay
#' @export
run_sctransform <- function(seurat_obj,
                            vars_to_regress = c("percent.mt"),
                            n_genes = 3000,
                            vst_flavor = "v2",
                            verbose = TRUE) {

  message("Running SCTransform normalization")
  message("  Variables to regress: ", paste(vars_to_regress, collapse = ", "))
  message("  Variable genes to identify: ", n_genes)
  message("  VST flavor: ", vst_flavor)

  # === 必需依赖：glmGamPoi (SCTransform v2 加速) ===
  if (!requireNamespace("glmGamPoi", quietly = TRUE)) {
    stop("glmGamPoi package required for SCTransform v2. Install: BiocManager::install('glmGamPoi')")
  }

  # === 并行与内存配置（环境配置，不是分析参数，不辩论） ===
  library(future)
  library(glmGamPoi)  # SCTransform v2 加速依赖
  # workers 根据 CPU 核心数设置：保守用一半核心，至少 1
  n_cores <- max(1, floor(availableCores() / 2))
  plan(multisession, workers = n_cores)
  # 固定 70GB 内存上限（一般比较大，比较好）
  options(future.globals.maxSize = 70 * 1024^3)
  message("  Parallel: multisession, workers = ", n_cores)
  message("  Memory limit: 70 GB (fixed)")

  # Check if vars_to_regress exist in metadata
  missing_vars <- setdiff(vars_to_regress, colnames(seurat_obj@meta.data))
  if (length(missing_vars) > 0) {
    warning("Variables not found in metadata: ", paste(missing_vars, collapse = ", "))
    vars_to_regress <- intersect(vars_to_regress, colnames(seurat_obj@meta.data))
  }

  # Run SCTransform with vst.flavor = "v2" (requires glmGamPoi)
  seurat_obj <- SCTransform(
    seurat_obj,
    vst.flavor = vst_flavor,
    vars.to.regress = vars_to_regress,
    variable.features.n = n_genes,
    verbose = verbose
  )

  message("SCTransform complete")
  message("  Default assay: ", DefaultAssay(seurat_obj))
  message("  Variable features: ", length(VariableFeatures(seurat_obj)))

  return(seurat_obj)
}

#' Normalize data using LogNormalize
#'
#' Classic Seurat normalization workflow. Use when:
#' - Non-UMI data (e.g., Smart-seq2)
#' - SCTransform causes issues
#' - You need more control over individual steps
#'
#' @param seurat_obj Seurat object (post-filtering)
#' @param normalization_method Normalization method (default: "LogNormalize")
#' @param scale_factor Scale factor for normalization (default: 10000)
#' @param verbose Print progress (default: TRUE)
#' @return Seurat object with normalized data
#' @export
run_lognormalize <- function(seurat_obj,
                             normalization_method = "LogNormalize",
                             scale_factor = 10000,
                             verbose = TRUE) {

  message("Running LogNormalize normalization")
  message("  Method: ", normalization_method)
  message("  Scale factor: ", scale_factor)

  # Normalize data
  seurat_obj <- NormalizeData(
    seurat_obj,
    normalization.method = normalization_method,
    scale.factor = scale_factor,
    verbose = verbose
  )

  message("Normalization complete")

  return(seurat_obj)
}

#' Scale data (for LogNormalize workflow)
#'
#' Scales and centers features. Only needed for LogNormalize workflow
#' (SCTransform does this automatically).
#'
#' @param seurat_obj Seurat object (after LogNormalize and FindVariableFeatures)
#' @param features Features to scale (default: all genes)
#' @param vars_to_regress Variables to regress out (default: NULL)
#' @param verbose Print progress (default: TRUE)
#' @return Seurat object with scaled data
#' @export
scale_data <- function(seurat_obj,
                      features = NULL,
                      vars_to_regress = NULL,
                      verbose = TRUE) {

  message("Scaling data")

  # Use all genes if not specified
  if (is.null(features)) {
    features <- rownames(seurat_obj)
    message("  Scaling all genes: ", length(features))
  } else {
    message("  Scaling specified features: ", length(features))
  }

  # Check if vars_to_regress exist
  if (!is.null(vars_to_regress)) {
    message("  Variables to regress: ", paste(vars_to_regress, collapse = ", "))
    missing_vars <- setdiff(vars_to_regress, colnames(seurat_obj@meta.data))
    if (length(missing_vars) > 0) {
      warning("Variables not found in metadata: ", paste(missing_vars, collapse = ", "))
      vars_to_regress <- intersect(vars_to_regress, colnames(seurat_obj@meta.data))
    }
  }

  # Scale data
  seurat_obj <- ScaleData(
    seurat_obj,
    features = features,
    vars.to.regress = vars_to_regress,
    verbose = verbose
  )

  message("Scaling complete")

  return(seurat_obj)
}

#' Compare SCTransform and LogNormalize results
#'
#' For testing/comparison purposes. Runs both methods and compares results.
#'
#' @param seurat_obj Seurat object (post-filtering)
#' @param output_dir Output directory for comparison plots
#' @return List with both Seurat objects
#' @export
compare_normalization_methods <- function(seurat_obj, output_dir = NULL) {

  message("Comparing SCTransform and LogNormalize methods")

  # Create two copies
  seurat_sct <- seurat_obj
  seurat_log <- seurat_obj

  # Run SCTransform
  seurat_sct <- run_sctransform(seurat_sct, verbose = FALSE)

  # Run LogNormalize workflow
  seurat_log <- run_lognormalize(seurat_log, verbose = FALSE)
  source("scripts/find_variable_features.R")
  seurat_log <- find_hvgs(seurat_log, verbose = FALSE)
  seurat_log <- scale_data(seurat_log, verbose = FALSE)

  # Run PCA for both
  seurat_sct <- RunPCA(seurat_sct, verbose = FALSE)
  seurat_log <- RunPCA(seurat_log, verbose = FALSE)

  message("Both methods completed. Compare PCA and clustering results.")

  if (!is.null(output_dir)) {
    message("Save comparison plots using plot_pca.R functions")
  }

  return(list(
    sct = seurat_sct,
    lognorm = seurat_log
  ))
}
