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
# ============================================================================
# FIND HIGHLY VARIABLE GENES
# ============================================================================
#
# Identify genes with high cell-to-cell variation (biological signal).
# Note: Skip this if using SCTransform (it finds variable features automatically).
#
# Functions:
#   - find_hvgs(): Find highly variable genes
#   - plot_variable_features(): Visualize variable features
#
# Usage:
#   source("scripts/find_variable_features.R")
#   seurat_obj <- find_hvgs(seurat_obj, n_features = 2000)

library(ggplot2)
library(ggprism)

#' Find highly variable genes
#'
#' Only needed for LogNormalize workflow. SCTransform does this automatically.
#'
#' @param seurat_obj Seurat object (after normalization)
#' @param selection_method Method for variable feature selection (default: "vst")
#' @param n_features Number of features to return (default: 2000)
#' @param verbose Print progress (default: TRUE)
#' @return Seurat object with variable features identified
#' @export
find_hvgs <- function(seurat_obj,
                     selection_method = "vst",
                     n_features = 2000,
                     verbose = TRUE) {

  message("Finding highly variable genes")
  message("  Method: ", selection_method)
  message("  Number of features: ", n_features)

  # Find variable features
  seurat_obj <- FindVariableFeatures(
    seurat_obj,
    selection.method = selection_method,
    nfeatures = n_features,
    verbose = verbose
  )

  # Get variable features
  hvgs <- VariableFeatures(seurat_obj)

  message("  Variable features identified: ", length(hvgs))
  message("  Top 10 HVGs: ", paste(head(hvgs, 10), collapse = ", "))

  return(seurat_obj)
}

#' Plot variable features
#'
#' @param seurat_obj Seurat object with variable features
#' @param n_label Number of genes to label (default: 10)
#' @param output_dir Output directory for plots
#' @param width Plot width (default: 8)
#' @param height Plot height (default: 6)
#' @return ggplot object
#' @export
plot_variable_features <- function(seurat_obj,
                                   n_label = 10,
                                   output_dir = NULL,
                                   width = 8,
                                   height = 6) {

  message("Plotting variable features")

  # Create variable feature plot
  p <- VariableFeaturePlot(seurat_obj)

  # Add labels for top genes
  top_hvgs <- head(VariableFeatures(seurat_obj), n_label)

  p <- LabelPoints(
    plot = p,
    points = top_hvgs,
    repel = TRUE,
    xnudge = 0,
    ynudge = 0
  ) +
    theme_prism() +
    labs(
      title = "Highly Variable Genes",
      x = "Average Expression",
      y = "Standardized Variance"
    )

  # Save plot if output directory specified
  if (!is.null(output_dir)) {
    dir.create(output_dir, recursive = TRUE, showWarnings = FALSE)

    svg_file <- file.path(output_dir, "variable_features.svg")
    ggsave(svg_file, plot = p, width = width, height = height, dpi = 300)
    message("  Saved: ", svg_file)

    png_file <- file.path(output_dir, "variable_features.png")
    ggsave(png_file, plot = p, width = width, height = height, dpi = 300)
    message("  Saved: ", png_file)
  }

  return(p)
}
