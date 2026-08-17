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
# SETUP AND DATA IMPORT FOR SEURAT ANALYSIS
# ============================================================================
#
# This script handles initial setup and data loading for Seurat scRNA-seq analysis.
#
# Functions:
#   - setup_seurat_libraries(): Load required R packages
#   - import_10x_data(): Load 10X Genomics CellRanger output
#   - import_h5_data(): Load H5 format data
#   - import_count_matrix(): Load from CSV/TSV count matrix
#   - add_metadata(): Add sample metadata to Seurat object
#
# Usage:
#   source("scripts/setup_and_import.R")
#   setup_seurat_libraries()
#   seurat_obj <- import_10x_data("path/to/filtered_feature_bc_matrix/")

#' Load required libraries for Seurat analysis
#'
#' @return NULL (loads packages into environment)
#' @export
setup_seurat_libraries <- function() {
  suppressPackageStartupMessages({
    library(Seurat)
    library(ggplot2)
    library(ggprism)   # For publication-quality plots
    library(dplyr)
    library(patchwork) # For combining plots
  })
  message("Required libraries loaded successfully")
  message(paste0("Seurat version: ", packageVersion("Seurat")))
}

#' Import 10X Genomics data
#'
#' @param data_dir Path to directory containing barcodes, features, and matrix files
#' @param project_name Project name for Seurat object (default: "scRNAseq")
#' @param min_cells Minimum number of cells for a gene to be included (default: 3)
#' @param min_features Minimum number of features for a cell to be included (default: 200)
#' @return Seurat object with raw counts
#' @export
import_10x_data <- function(data_dir,
                            project_name = "scRNAseq",
                            min_cells = 3,
                            min_features = 200) {

  if (!dir.exists(data_dir)) {
    stop("Data directory does not exist: ", data_dir)
  }

  message("Loading 10X data from: ", data_dir)

  # Read 10X data
  data <- Read10X(data.dir = data_dir)

  # Create Seurat object
  seurat_obj <- CreateSeuratObject(
    counts = data,
    project = project_name,
    min.cells = min_cells,
    min.features = min_features
  )

  message(sprintf("Created Seurat object: %d genes x %d cells",
                  nrow(seurat_obj), ncol(seurat_obj)))

  return(seurat_obj)
}

#' Import H5 format data
#'
#' @param h5_file Path to H5 file
#' @param project_name Project name for Seurat object (default: "scRNAseq")
#' @param min_cells Minimum number of cells for a gene to be included (default: 3)
#' @param min_features Minimum number of features for a cell to be included (default: 200)
#' @return Seurat object with raw counts
#' @export
import_h5_data <- function(h5_file,
                          project_name = "scRNAseq",
                          min_cells = 3,
                          min_features = 200) {

  if (!file.exists(h5_file)) {
    stop("H5 file does not exist: ", h5_file)
  }

  message("Loading H5 data from: ", h5_file)

  # Read H5 data
  data <- Read10X_h5(filename = h5_file)

  # Create Seurat object
  seurat_obj <- CreateSeuratObject(
    counts = data,
    project = project_name,
    min.cells = min_cells,
    min.features = min_features
  )

  message(sprintf("Created Seurat object: %d genes x %d cells",
                  nrow(seurat_obj), ncol(seurat_obj)))

  return(seurat_obj)
}

#' Import count matrix from CSV/TSV
#'
#' @param file_path Path to count matrix file (genes as rows, cells as columns)
#' @param sep Separator character (default: auto-detect)
#' @param project_name Project name for Seurat object (default: "scRNAseq")
#' @param min_cells Minimum number of cells for a gene to be included (default: 3)
#' @param min_features Minimum number of features for a cell to be included (default: 200)
#' @return Seurat object with raw counts
#' @export
import_count_matrix <- function(file_path,
                                sep = NULL,
                                project_name = "scRNAseq",
                                min_cells = 3,
                                min_features = 200) {

  if (!file.exists(file_path)) {
    stop("Count matrix file does not exist: ", file_path)
  }

  # Auto-detect separator
  if (is.null(sep)) {
    if (grepl("\\.tsv$", file_path)) {
      sep <- "\t"
    } else {
      sep <- ","
    }
  }

  message("Loading count matrix from: ", file_path)

  # Read count matrix
  if (sep == "\t") {
    counts <- read.csv(file_path, sep = "\t", row.names = 1, check.names = FALSE)
  } else {
    counts <- read.csv(file_path, row.names = 1, check.names = FALSE)
  }

  # Convert to sparse matrix for efficiency
  counts <- as(as.matrix(counts), "dgCMatrix")

  # Create Seurat object
  seurat_obj <- CreateSeuratObject(
    counts = counts,
    project = project_name,
    min.cells = min_cells,
    min.features = min_features
  )

  message(sprintf("Created Seurat object: %d genes x %d cells",
                  nrow(seurat_obj), ncol(seurat_obj)))

  return(seurat_obj)
}

#' Add sample metadata to Seurat object
#'
#' @param seurat_obj Seurat object
#' @param metadata_file Path to metadata CSV file (with cell barcodes as row names)
#' @return Seurat object with added metadata
#' @export
add_metadata <- function(seurat_obj, metadata_file) {

  if (!file.exists(metadata_file)) {
    stop("Metadata file does not exist: ", metadata_file)
  }

  message("Loading metadata from: ", metadata_file)

  # Read metadata
  metadata <- read.csv(metadata_file, row.names = 1)

  # Check that cell barcodes match
  cells_in_obj <- colnames(seurat_obj)
  cells_in_meta <- rownames(metadata)

  if (length(intersect(cells_in_obj, cells_in_meta)) == 0) {
    stop("No matching cell barcodes between Seurat object and metadata file")
  }

  # Add metadata to Seurat object
  seurat_obj <- AddMetaData(seurat_obj, metadata = metadata)

  message(sprintf("Added %d metadata columns to %d cells",
                  ncol(metadata), nrow(metadata)))

  return(seurat_obj)
}
