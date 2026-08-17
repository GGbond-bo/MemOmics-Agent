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
# CLUSTERING (Seurat + Leiden)
# ============================================================================
# Functions:
#   - add_clusters_atac(): Add Leiden/Seurat clustering
#   - compare_resolutions_atac(): Try multiple resolutions
# Usage:
#   source("scripts/cluster_atac.R")

add_clusters_atac <- function(proj, resolution=0.8, reduced_dims="Harmony", method="Seurat", name="Clusters") {
  message("=== Clustering (res=", resolution, " method=", method, ") ===")
  if (method == "Seurat") {
    proj <- ArchR::addClusters(input=proj, reducedDims=reduced_dims, method="Seurat", name=name, resolution=resolution)
  } else if (method == "Leiden") {
    proj <- ArchR::addClusters(input=proj, reducedDims=reduced_dims, method="leiden", name=name, resolution=resolution)
  } else stop("method must be Seurat or Leiden")
  n_clusters <- length(unique(proj[[name]][[1]]))
  message("Clusters: ", n_clusters, " (res=", resolution, ")")
  invisible(proj)
}

compare_resolutions_atac <- function(proj, resolutions=c(0.4, 0.6, 0.8, 1.0, 1.2), reduced_dims="Harmony") {
  message("=== Comparing Resolutions ===")
  results <- numeric(length(resolutions))
  names(results) <- as.character(resolutions)
  for (i in seq_along(resolutions)) {
    res <- resolutions[i]
    name_tmp <- paste0("Clusters_res", res)
    proj_tmp <- ArchR::addClusters(input=proj, reducedDims=reduced_dims, method="Seurat", name=name_tmp, resolution=res)
    n <- length(unique(proj_tmp[[name_tmp]][[1]]))
    results[i] <- n
    message("  res=", res, " -> ", n, " clusters")
    proj_tmp@cellColData[[name_tmp]] <- NULL
    gc()
  }
  message("
Resolution comparison:")
  for (i in seq_along(results)) message("  ", names(results)[i], " -> ", results[i], " clusters")
  invisible(results)
}
