
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
#      ★ 强制审查项（任一不通过则重新执行）:
#        a. 图片是否生成？无图 → 重新执行
#        b. 图片是否空白（全白/全黑/全单一色）？空白 → 强制重新出图
#        c. 图片是否有 NA/缺失值（>10%像素是NA）？有NA → 强制重新出图
#        d. 图片大小是否过小（<5KB）？过小 → 强制重新出图
#        e. 图片数量是否足够？（每步至少1张图，关键步骤至少2-3张）
#        f. 代码行数是否合理？是否分段执行（禁止&&连接）？
#        g. 数值范围是否合理？跟知识库对应吗？
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
# ★ 参数和结论辩论铁律:
#   - 有参数选择 → 必须调 debate_analysis 辩论
#   - 有结论输出 → 必须调 debate_analysis 辩论
#   - 辩论格式：正方(支持) vs 反方(质疑+替代) → 裁判决断
#   - 最多3轮，3轮后选最优结果
#
# 日志存储: skill 目录下 .run_logs/ 目录，按 物种_组织_方向_日期 命名
# ============================================================

# ============================================================
# 🔒 MemOmics 审查铁律 — 执行本脚本前后的强制步骤
# ============================================================
# 执行前必须: rail_review(action="pre")  — 环境检查 + 参数校验 + 代码审查
# 执行后必须: rail_review(action="post") — 结果质量评估 + 图表检查 + 数值检查
#   ★ 强制: 图片空白/NA/过小 → 重新出图 | 图片不够 → 补图 | 代码未分段 → 重写
#   ★ 强制: 有参数有结论 → debate_analysis 辩论
# 参数有争议: debate_analysis(topic=..., context=...) — 多角色辩论
# 执行失败:   skill_evolution(action="record_error") — 记录错误
# 修复成功:   skill_evolution(action="update_script") — 替换脚本
# ============================================================


# ============================================================================
# CELL CLUSTERING
# ============================================================================
#
# Perform graph-based clustering to identify cell populations.
#
# Functions:
#   - cluster_seurat(): Cluster at single resolution
#   - cluster_multiple_resolutions(): Test multiple resolutions
#   - optimize_clustering_resolution(): Find optimal resolution
#
# Usage:
#   source("scripts/cluster_cells.R")
#   seurat_obj <- cluster_seurat(seurat_obj, dims = 1:30, resolution = 0.8)

#' Cluster cells at single resolution
#'
#' @param seurat_obj Seurat object (after PCA)
#' @param dims PCs to use for clustering (default: 1:30)
#' @param resolution Clustering resolution (default: 0.8)
#' @param algorithm Clustering algorithm (default: 1 = Louvain)
#' @param k_param K parameter for KNN (default: 20)
#' @param verbose Print progress (default: TRUE)
#' @return Seurat object with clusters
#' @export
cluster_seurat <- function(seurat_obj,
                          dims = 1:30,
                          resolution = 0.8,
                          algorithm = 1,
                          k_param = 20,
                          verbose = TRUE) {

  message("Clustering cells")
  message("  Dimensions: ", paste(range(dims), collapse = "-"))
  message("  Resolution: ", resolution)
  message("  K parameter: ", k_param)

  # Warn if too few PCs
  if (max(dims) < 15) {
    message("  WARNING: max(dims)=", max(dims), " is very low. Standard is 20-30 PCs.")
    message("     Using <15 PCs risks collapsing distinct cell populations.")
  }

  # Build KNN graph
  seurat_obj <- FindNeighbors(
    seurat_obj,
    dims = dims,
    k.param = k_param,
    verbose = verbose
  )

  # Find clusters
  seurat_obj <- FindClusters(
    seurat_obj,
    resolution = resolution,
    algorithm = algorithm,
    verbose = verbose
  )

  # Get cluster info
  n_clusters <- length(unique(Idents(seurat_obj)))
  cluster_sizes <- table(Idents(seurat_obj))

  message("Clustering complete")
  message("  Number of clusters: ", n_clusters)
  message("  Cluster sizes:")
  print(cluster_sizes)

  # Warning for very small clusters
  if (any(cluster_sizes < 10)) {
    small_clusters <- names(cluster_sizes)[cluster_sizes < 10]
    warning("Small clusters detected (<10 cells): ", paste(small_clusters, collapse = ", "))
    message("  Consider lowering resolution or investigating these clusters")
  }

  return(seurat_obj)
}

#' Cluster at multiple resolutions
#'
#' Test different clustering granularities to find optimal resolution.
#'
#' @param seurat_obj Seurat object (after PCA)
#' @param dims PCs to use for clustering (default: 1:30)
#' @param resolutions Vector of resolutions to test (default: c(0.4, 0.6, 0.8, 1.0))
#' @param verbose Print progress (default: TRUE)
#' @return Seurat object with multiple cluster columns in metadata
#' @export
cluster_multiple_resolutions <- function(seurat_obj,
                                        dims = 1:30,
                                        resolutions = c(0.4, 0.6, 0.8, 1.0),
                                        verbose = TRUE) {

  message("Testing multiple clustering resolutions")
  message("  Dimensions: ", paste(range(dims), collapse = "-"))
  message("  Resolutions: ", paste(resolutions, collapse = ", "))

  # Warn if too few PCs
  if (max(dims) < 15) {
    message("  WARNING: max(dims)=", max(dims), " is very low. Standard is 20-30 PCs.")
    message("     Using <15 PCs risks collapsing distinct cell populations.")
  }

  # Build KNN graph once
  seurat_obj <- FindNeighbors(
    seurat_obj,
    dims = dims,
    verbose = verbose
  )

  # Cluster at each resolution
  seurat_obj <- FindClusters(
    seurat_obj,
    resolution = resolutions,
    verbose = verbose
  )

  # Print summary for each resolution
  message("\nClustering summary:")
  for (res in resolutions) {
    col_name <- paste0("RNA_snn_res.", res)
    if (col_name %in% colnames(seurat_obj@meta.data)) {
      n_clusters <- length(unique(seurat_obj@meta.data[[col_name]]))
      message(sprintf("  Resolution %.1f: %d clusters", res, n_clusters))
    }
  }

  message("\nTo set active clustering resolution, use:")
  message("  Idents(seurat_obj) <- 'RNA_snn_res.0.8'")

  return(seurat_obj)
}

#' Calculate clustering metrics
#'
#' Assess clustering quality using silhouette scores.
#'
#' @param seurat_obj Seurat object with clusters
#' @param dims PCs used for clustering
#' @param resolution Resolution to evaluate (column name or NULL for active idents)
#' @return List with silhouette scores and mean score
#' @export
evaluate_clustering <- function(seurat_obj, dims = 1:30, resolution = NULL) {

  message("Evaluating clustering quality")

  # Check if cluster package is available
  if (!requireNamespace("cluster", quietly = TRUE)) {
    stop("cluster package required. Install with: install.packages('cluster')")
  }

  library(cluster)

  # Get embeddings
  embeddings <- Embeddings(seurat_obj, reduction = "pca")[, dims]

  # Get cluster assignments
  if (is.null(resolution)) {
    clusters <- as.numeric(as.character(Idents(seurat_obj)))
  } else {
    clusters <- as.numeric(as.character(seurat_obj@meta.data[[resolution]]))
  }

  # Calculate silhouette scores
  dist_matrix <- dist(embeddings)
  sil <- silhouette(clusters, dist_matrix)

  mean_sil <- mean(sil[, 3])

  message(sprintf("  Mean silhouette score: %.3f", mean_sil))
  message("  Interpretation:")
  message("    > 0.5: Strong structure")
  message("    0.25-0.5: Reasonable structure")
  message("    < 0.25: Weak structure")

  return(list(
    silhouette = sil,
    mean_score = mean_sil
  ))
}

#' Find optimal clustering resolution
#'
#' Use silhouette analysis to suggest best resolution.
#'
#' @param seurat_obj Seurat object (after PCA with FindNeighbors already run)
#' @param dims PCs used for clustering
#' @param resolutions Resolutions to test
#' @return Data frame with scores for each resolution
#' @export
optimize_clustering_resolution <- function(seurat_obj,
                                          dims = 1:30,
                                          resolutions = seq(0.2, 1.5, 0.2)) {

  message("Optimizing clustering resolution")
  message("  Testing resolutions: ", paste(resolutions, collapse = ", "))

  results <- data.frame(
    resolution = numeric(),
    n_clusters = numeric(),
    silhouette_score = numeric()
  )

  for (res in resolutions) {
    # Cluster at this resolution
    seurat_obj <- FindClusters(
      seurat_obj,
      resolution = res,
      verbose = FALSE
    )

    # Evaluate
    eval <- evaluate_clustering(seurat_obj, dims = dims)

    # Store results
    n_clusters <- length(unique(Idents(seurat_obj)))
    results <- rbind(results, data.frame(
      resolution = res,
      n_clusters = n_clusters,
      silhouette_score = eval$mean_score
    ))
  }

  # Find best resolution
  best_idx <- which.max(results$silhouette_score)
  best_res <- results$resolution[best_idx]

  message("\nResults:")
  print(results)
  message(sprintf("\nSuggested resolution: %.1f (silhouette = %.3f, %d clusters)",
                  best_res,
                  results$silhouette_score[best_idx],
                  results$n_clusters[best_idx]))

  return(results)
}
