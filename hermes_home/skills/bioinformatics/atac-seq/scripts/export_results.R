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
# EXPORT RESULTS
# ============================================================================
# Functions:
#   - export_atac_results(): Export all results (CSV, RDS, plots)
#   - save_archr_project(): Save ArchRProject
# Usage:
#   source("scripts/export_results.R")

export_atac_results <- function(proj, output_dir) {
  message("=== Exporting ATAC Results ===")
  dir.create(output_dir, recursive=TRUE, showWarnings=FALSE)
  dirs <- c("figures", "data", "results", "scripts")
  for (d in dirs) dir.create(file.path(output_dir, d), recursive=TRUE, showWarnings=FALSE)

  # 1. Save cell metadata
  cell_meta <- as.data.frame(proj@cellColData)
  write.csv(cell_meta, file.path(output_dir, "results", "cell_metadata.csv"), row.names=FALSE)
  message("Cell metadata: ", nrow(cell_meta), " cells")

  # 2. Save peak set
  peaks <- getPeakSet(proj)
  if (nrow(peaks) > 0) {
    peak_df <- as.data.frame(peaks)
    write.csv(peak_df, file.path(output_dir, "results", "peaks.csv"), row.names=FALSE)
    message("Peaks: ", nrow(peak_df))
  }

  # 3. Save marker features
  tryCatch({
    markers <- ArchR::getMarkerFeatures(ArchRProj=proj, useMatrix="PeakMatrix", groupBy="Clusters")
    marker_df <- ArchR::markersList(markers)
    if (length(marker_df) > 0) {
      all_markers <- do.call(rbind, lapply(names(marker_df), function(n) {
        df <- as.data.frame(marker_df[[n]])
        df$cluster <- n
        df
      }))
      write.csv(all_markers, file.path(output_dir, "results", "diff_peaks.csv"), row.names=FALSE)
      message("Differential peaks exported")
    }
  }, error=function(e) message("Could not export markers: ", e$message))

  # 4. Plot UMAP
  tryCatch({
    p <- ArchR::plotEmbedding(ArchRProj=proj, colorBy="cellColData", name="Clusters", embedding="UMAP")
    ArchR::plotPDF(p, name="UMAP_Clusters", ArchRProj=proj, addDOC=FALSE, outDir=file.path(output_dir, "figures"))
    message("UMAP plot saved")
  }, error=function(e) message("Could not plot UMAP: ", e$message))

  message("=== Export complete ===")
  message("Output: ", output_dir)
  invisible(TRUE)
}

save_archr_project <- function(proj, output_dir) {
  message("=== Saving ArchRProject ===")
  saveRDS(proj, file.path(output_dir, "data", "archr_project.rds"))
  message("Saved: ", file.path(output_dir, "data", "archr_project.rds"))
  invisible(TRUE)
}
