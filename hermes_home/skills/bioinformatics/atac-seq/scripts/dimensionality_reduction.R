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
# DIMENSIONALITY REDUCTION (IterativeLSI)
# ============================================================================
# Functions:
#   - run_iterative_lsi(): Run IterativeLSI
#   - add_harmony(): Add Harmony batch correction
#   - add_umap_atac(): Add UMAP embedding
# Usage:
#   source("scripts/dimensionality_reduction.R")

run_iterative_lsi <- function(proj, features=25000, n_components=30) {
  message("=== IterativeLSI (features=", features, " n_comp=", n_components, ") ===")
  proj <- ArchR::addIterativeLSI(ArchRProj=proj, useMatrix="TileMatrix", name="IterativeLSI",
    iterations=2, clusterParams=list(resolution=c(0.2), sampleCells=10000, n.start=10),
    reductionParams=list(dimensions=n_components), varFeatures=features, dimsUse=2:n_components)
  message("IterativeLSI complete: ", n_components, " components")
  invisible(proj)
}

add_harmony <- function(proj, batch_key="Sample") {
  message("=== Harmony (batch=", batch_key, ") ===")
  proj <- ArchR::addHarmony(ArchRProj=proj, groupBy=batch_key, name="Harmony", reducedDims="IterativeLSI")
  message("Harmony correction complete")
  invisible(proj)
}

add_umap_atac <- function(proj, reduced_dims="Harmony", n_neighbors=30, min_dist=0.5, metric="cosine") {
  message("=== UMAP (dims=", reduced_dims, " n_neighbors=", n_neighbors, ") ===")
  proj <- ArchR::addUMAP(ArchRProj=proj, reducedDims=reduced_dims, name="UMAP",
    nNeighbors=n_neighbors, minDist=min_dist, metric=metric)
  message("UMAP complete")
  invisible(proj)
}
