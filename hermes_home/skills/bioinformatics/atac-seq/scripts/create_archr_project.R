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
# CREATE ArchR PROJECT FROM FRAGMENT FILES
# ============================================================================
# Functions:
#   - create_arrow_files(): Create Arrow files from fragment files
#   - create_archr_project(): Create ArchRProject from Arrow files
# Usage:
#   source("scripts/create_archr_project.R")

create_arrow_files <- function(frag_files, sample_names, output_dir, min_frags=1000, min_tss=4) {
  message("=== Creating Arrow Files ===")
  if (length(frag_files) != length(sample_names)) stop("frag_files and sample_names must have same length")
  dir.create(output_dir, recursive=TRUE, showWarnings=FALSE)
  ArrowFiles <- ArchR::createArrowFiles(inputFiles=frag_files, sampleNames=sample_names, minTSS=min_tss, minFrags=min_frags, addTileMat=TRUE, addGeneScoreMat=TRUE)
  message("Created ", length(ArrowFiles), " Arrow files")
  invisible(ArrowFiles)
}

create_archr_project <- function(ArrowFiles, output_dir, sample_names=NULL) {
  message("=== Creating ArchRProject ===")
  proj <- ArchR::ArchRProject(ArrowFiles=ArrowFiles, outputDirectory=output_dir, copyArrows=TRUE)
  proj$Sample <- factor(proj$Sample)
  message("ArchRProject: ", nCells(proj), " cells, ", length(ArrowFiles), " samples")
  message("  Median fragments: ", median(proj$nFrags))
  message("  Median TSS: ", median(proj$TSSEnrichment))
  invisible(proj)
}
