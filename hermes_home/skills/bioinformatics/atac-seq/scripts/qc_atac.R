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
# ATAC-SEQ QUALITY CONTROL
# ============================================================================
# Functions:
#   - plot_atac_qc(): Generate QC plots
#   - filter_atac_cells(): Filter cells by QC metrics
#   - remove_doublets_atac(): Remove doublets
# Usage:
#   source("scripts/qc_atac.R")

plot_atac_qc <- function(proj, output_dir) {
  message("=== Plotting ATAC QC ===")
  dir.create(output_dir, recursive=TRUE, showWarnings=FALSE)
  p1 <- ArchR::plotGroups(ArchRProj=proj, groupBy="Sample", colorBy="CellColData", name="TSSEnrichment", plotAs="ridges")
  p2 <- ArchR::plotGroups(ArchRProj=proj, groupBy="Sample", colorBy="CellColData", name="log10(nFrags)", plotAs="ridges")
  p3 <- ArchR::plotFragmentSizes(ArchRProj=proj)
  p4 <- ArchR::plotTSSProfile(ArchRProj=proj)
  ArchR::plotPDF(p1, p2, p3, p4, name="QC_ATAC_Overview", ArchRProj=proj, addDOC=FALSE, outDir=output_dir)
  message("QC plots saved to: ", output_dir)
  invisible(TRUE)
}

filter_atac_cells <- function(proj, min_tss=8, min_frip=0.15, max_blacklist=0.05, min_frags=1000, max_frags=100000) {
  message("=== Filtering ATAC Cells ===")
  n_before <- nCells(proj)
  keep <- proj$TSSEnrichment >= min_tss & proj$nFrags >= min_frags & proj$nFrags <= max_frags
  if ("FRIP" %in% colnames(cellColData(proj))) keep <- keep & proj$FRIP >= min_frip
  if ("BlacklistRatio" %in% colnames(cellColData(proj))) keep <- keep & proj$BlacklistRatio <= max_blacklist
  proj <- proj[keep, ]
  n_after <- nCells(proj)
  message("Cells: ", n_before, " -> ", n_after, " (removed ", n_before-n_after, ")")
  message("Params: min_tss=", min_tss, " min_frip=", min_frip, " max_blacklist=", max_blacklist)
  invisible(proj)
}

remove_doublets_atac <- function(proj, doublet_rate=0.08) {
  message("=== Removing Doublets (rate=", doublet_rate, ") ===")
  proj <- ArchR::addDoubletScores(input=proj, k=10, knnMethod="UMAP", LSIMethod=1)
  proj <- ArchR::filterDoublets(proj)
  message("Cells after doublet removal: ", nCells(proj))
  invisible(proj)
}
