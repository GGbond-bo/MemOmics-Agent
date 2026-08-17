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
# MOTIF ANALYSIS (chromVAR + JASPAR)
# ============================================================================
# Functions:
#   - add_motif_annotations(): Add motif annotations
#   - run_chromvar(): Run chromVAR deviation analysis
#   - plot_motif_heatmap(): Plot motif deviation heatmap
# Usage:
#   source("scripts/motif_analysis.R")

add_motif_annotations <- function(proj, motif_db="JASPAR2022", species="vertebrates") {
  message("=== Adding Motif Annotations (", motif_db, ") ===")
  proj <- ArchR::addMotifAnnotations(ArchRProj=proj, motifSet=motif_db, name="Motif")
  message("Motif annotations added")
  invisible(proj)
}

run_chromvar <- function(proj, reduced_dims="Harmony") {
  message("=== chromVAR Deviation Analysis ===")
  proj <- ArchR::addBgdPeaks(ArchRProj=proj)
  proj <- ArchR::addDeviationsMatrix(ArchRProj=proj, peakAnnotation="Motif", force=TRUE)
  message("chromVAR complete")
  invisible(proj)
}

plot_motif_heatmap <- function(proj, output_dir, group_by="Clusters", top_n=20) {
  message("=== Plotting Motif Heatmap (top ", top_n, ") ===")
  dir.create(output_dir, recursive=TRUE, showWarnings=FALSE)
  # Get variable motifs
  motif_dev <- ArchR::getVarDeviations(proj, name="MotifMatrix", plot=FALSE)
  top_motifs <- head(motif_dev$name, top_n)
  p <- ArchR::plotGroups(ArchRProj=proj, groupBy=group_by, colorBy="MotifMatrix",
    name=top_motifs, imputeWeights=ArchR::getImputeWeights(proj))
  ArchR::plotPDF(p, name="Motif_Heatmap", ArchRProj=proj, addDOC=FALSE, outDir=output_dir)
  message("Motif heatmap saved")
  invisible(TRUE)
}
