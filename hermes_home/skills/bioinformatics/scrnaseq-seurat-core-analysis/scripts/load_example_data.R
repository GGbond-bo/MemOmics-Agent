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
# LOAD EXAMPLE DATA
# ============================================================================
#
# Load example single-cell RNA-seq datasets for testing and demonstrations.
# This script provides user-facing functions to load data from the SeuratData
# package for learning and testing the workflow.
#
# Functions:
#   - load_seurat_data(): Load example datasets (pbmc3k, ifnb, etc.)
#
# Usage:
#   source("scripts/load_example_data.R")
#   seurat_obj <- load_seurat_data("pbmc3k")

#' Load example data from SeuratData package
#'
#' Loads publicly available single-cell RNA-seq datasets from the SeuratData
#' package. Use this for testing the workflow with real data.
#'
#' Available datasets:
#'   - "pbmc3k": 3k PBMCs from a healthy donor (10X Genomics)
#'   - "ifnb": Immune cells stimulated with interferon-beta
#'   - Other datasets from SeuratData package
#'
#' @param dataset_name Name of dataset (e.g., "pbmc3k", "ifnb")
#' @param type Type of data to load (default: auto-detect for dataset)
#' @return Seurat object with raw counts
#' @export
#'
#' @examples
#' # Load PBMC 3k dataset for testing
#' seurat_obj <- load_seurat_data("pbmc3k")
#'
#' # Load interferon-beta dataset
#' seurat_obj <- load_seurat_data("ifnb")
load_seurat_data <- function(dataset_name, type = NULL) {

  # Set CRAN mirror
  options(repos = c(CRAN = "https://cloud.r-project.org"))

  # Check if SeuratData is installed
  if (!requireNamespace("SeuratData", quietly = TRUE)) {
    message("Installing SeuratData package (first time only)...")
    if (!requireNamespace("remotes", quietly = TRUE)) {
      install.packages("remotes")
    }
    remotes::install_github('satijalab/seurat-data')
  }

  library(SeuratData)

  message("Loading ", dataset_name, " dataset from SeuratData")

  # Install dataset if not available
  if (!dataset_name %in% InstalledData()$Dataset) {
    message("Installing ", dataset_name, " dataset (this may take a few minutes)...")
    InstallData(dataset_name)
  }

  # Auto-detect type for specific datasets
  if (is.null(type)) {
    if (dataset_name == "pbmc3k") {
      type <- "default"  # pbmc3k uses "default" not "filtered"
    } else {
      type <- "filtered"
    }
  }

  # Load dataset
  LoadData(dataset_name, type = type)

  # Get the object
  seurat_obj <- get(dataset_name)

  # Update object for Seurat v5 compatibility
  if (packageVersion("Seurat") >= "5.0.0") {
    message("Updating object for Seurat v5 compatibility...")
    # SeuratObject v5 compatibility fix
    if (!".cache" %in% slotNames(seurat_obj)) {
      seurat_obj <- UpdateSeuratObject(seurat_obj)
    }
  }

  message(sprintf("✓ Data loaded successfully: %d genes x %d cells",
                  nrow(seurat_obj), ncol(seurat_obj)))

  return(seurat_obj)
}
