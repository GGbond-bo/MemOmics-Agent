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
#!/usr/bin/env Rscript
#' Clustering heatmap visualization using ComplexHeatmap
#'
#' This script creates publication-quality heatmaps with dendrograms
#' using ComplexHeatmap (superior to Python's seaborn for bioinformatics)
#'
#' @param data_matrix Data matrix (samples x genes)
#' @param cluster_labels Cluster assignments for samples
#' @param output_path Base output path (will save PNG + SVG)

library(ComplexHeatmap)
library(circlize)  # For color mapping
library(grid)      # For graphics

#' Plot clustered heatmap with ComplexHeatmap
#'
#' @param data Matrix with samples in rows, features in columns
#' @param cluster_labels Vector of cluster assignments
#' @param feature_names Character vector of feature names
#' @param sample_names Character vector of sample names
#' @param top_n_features Number of top variable features to show
#' @param output_path Base path for output files (no extension)
#' @return ComplexHeatmap object
plot_cluster_heatmap <- function(data,
                                  cluster_labels,
                                  feature_names = NULL,
                                  sample_names = NULL,
                                  top_n_features = 50,
                                  output_path = "cluster_heatmap") {

  # Set default names if not provided
  if (is.null(sample_names)) {
    sample_names <- paste0("Sample_", seq_len(nrow(data)))
  }
  if (is.null(feature_names)) {
    feature_names <- paste0("Feature_", seq_len(ncol(data)))
  }

  rownames(data) <- sample_names
  colnames(data) <- feature_names

  # Select top variable features
  feature_vars <- apply(data, 2, var)
  top_indices <- order(feature_vars, decreasing = TRUE)[1:min(top_n_features, ncol(data))]
  data_subset <- data[, top_indices]

  # Sort by cluster
  cluster_order <- order(cluster_labels)
  data_sorted <- data_subset[cluster_order, ]
  cluster_sorted <- cluster_labels[cluster_order]

  # Create color annotation for clusters
  cluster_colors <- structure(
    rainbow(length(unique(cluster_labels))),
    names = as.character(sort(unique(cluster_labels)))
  )

  # Row annotation (samples colored by cluster)
  row_ha <- rowAnnotation(
    Cluster = as.character(cluster_sorted),
    col = list(Cluster = cluster_colors),
    show_annotation_name = TRUE,
    annotation_name_side = "top"
  )

  # Z-score scaling
  data_scaled <- t(scale(t(data_sorted)))

  # Create color mapping for heatmap
  col_fun <- colorRamp2(
    c(-2, 0, 2),
    c("blue", "white", "red")
  )

  # Create heatmap
  ht <- Heatmap(
    data_scaled,
    name = "Z-score",
    col = col_fun,
    # Clustering
    cluster_rows = FALSE,  # Already sorted by cluster
    cluster_columns = TRUE,
    clustering_distance_columns = "euclidean",
    clustering_method_columns = "complete",
    show_row_dend = FALSE,
    show_column_dend = TRUE,
    # Display
    show_row_names = FALSE,  # Too many samples
    show_column_names = TRUE,
    column_names_gp = gpar(fontsize = 8),
    # Annotations
    left_annotation = row_ha,
    # Size
    width = unit(12, "cm"),
    height = unit(10, "cm"),
    # Title
    column_title = "Clustered Heatmap",
    column_title_gp = gpar(fontsize = 14, fontface = "bold")
  )

  # Save PNG
  png_path <- paste0(output_path, ".png")
  png(png_path, width = 10, height = 8, units = "in", res = 300)
  draw(ht)
  dev.off()
  message("Heatmap saved to ", png_path)

  # Save SVG
  svg_path <- paste0(output_path, ".svg")
  svg(svg_path, width = 10, height = 8)
  draw(ht)
  dev.off()
  message("Heatmap saved to ", svg_path)

  return(ht)
}

#' Example usage
#'
#' @examples
#' # Load data
#' data <- read.csv("expression_matrix.csv", row.names = 1)
#' metadata <- read.csv("sample_metadata.csv", row.names = 1)
#' cluster_labels <- metadata$cluster
#'
#' # Create heatmap
#' plot_cluster_heatmap(
#'   data = as.matrix(data),
#'   cluster_labels = cluster_labels,
#'   feature_names = colnames(data),
#'   sample_names = rownames(data),
#'   top_n_features = 50,
#'   output_path = "results/cluster_heatmap"
#' )

# If run as script
if (sys.nframe() == 0) {
  message("ComplexHeatmap clustering visualization script")
  message("Usage: Rscript plot_cluster_heatmap.R")
  message("Or source this file and use plot_cluster_heatmap() function")
}
