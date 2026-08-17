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
# UMAP DIMENSIONALITY REDUCTION
# ============================================================================
#
# Run UMAP for visualization of cell populations.
#
# Functions:
#   - run_umap_reduction(): Generate UMAP embedding
#   - run_tsne_reduction(): Generate tSNE embedding (alternative)
#
# Usage:
#   source("scripts/run_umap.R")
#   seurat_obj <- run_umap_reduction(seurat_obj, dims = 1:30)

#' Run UMAP dimensionality reduction
#'
#' @param seurat_obj Seurat object (after PCA)
#' @param dims PCs to use for UMAP (default: 1:30)
#' @param n_neighbors UMAP n.neighbors parameter (default: 30)
#' @param min_dist UMAP min.dist parameter (default: 0.3)
#' @param metric Distance metric (default: "cosine")
#' @param seed Random seed for reproducibility (default: 42)
#' @param verbose Print progress (default: TRUE)
#' @return Seurat object with UMAP reduction
#' @export
run_umap_reduction <- function(seurat_obj,
                               dims = 1:30,
                               n_neighbors = 30,
                               min_dist = 0.3,
                               metric = "cosine",
                               seed = 42,
                               verbose = TRUE) {

  message("Running UMAP")
  message("  Dimensions: ", paste(range(dims), collapse = "-"))
  message("  n.neighbors: ", n_neighbors)
  message("  min.dist: ", min_dist)
  message("  metric: ", metric)

  # Set seed for reproducibility
  set.seed(seed)

  # Run UMAP
  seurat_obj <- RunUMAP(
    seurat_obj,
    dims = dims,
    n.neighbors = n_neighbors,
    min.dist = min_dist,
    metric = metric,
    seed.use = seed,
    verbose = verbose
  )

  message("UMAP complete")

  return(seurat_obj)
}

#' Run tSNE dimensionality reduction
#'
#' Alternative to UMAP. tSNE is good for visualization but can be slower.
#'
#' @param seurat_obj Seurat object (after PCA)
#' @param dims PCs to use for tSNE (default: 1:30)
#' @param perplexity tSNE perplexity parameter (default: 30)
#' @param seed Random seed for reproducibility (default: 42)
#' @param verbose Print progress (default: TRUE)
#' @return Seurat object with tSNE reduction
#' @export
run_tsne_reduction <- function(seurat_obj,
                               dims = 1:30,
                               perplexity = 30,
                               seed = 42,
                               verbose = TRUE) {

  message("Running tSNE")
  message("  Dimensions: ", paste(range(dims), collapse = "-"))
  message("  Perplexity: ", perplexity)

  # Set seed for reproducibility
  set.seed(seed)

  # Run tSNE
  seurat_obj <- RunTSNE(
    seurat_obj,
    dims = dims,
    perplexity = perplexity,
    seed.use = seed,
    verbose = verbose
  )

  message("tSNE complete")

  return(seurat_obj)
}

#' Run both UMAP and tSNE
#'
#' For comparison purposes.
#'
#' @param seurat_obj Seurat object (after PCA)
#' @param dims PCs to use (default: 1:30)
#' @return Seurat object with both reductions
#' @export
run_both_reductions <- function(seurat_obj, dims = 1:30) {

  message("Running both UMAP and tSNE for comparison")

  seurat_obj <- run_umap_reduction(seurat_obj, dims = dims, verbose = FALSE)
  seurat_obj <- run_tsne_reduction(seurat_obj, dims = dims, verbose = FALSE)

  message("Both reductions complete")
  message("  Available reductions: ", paste(names(seurat_obj@reductions), collapse = ", "))

  return(seurat_obj)
}
