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
# =============================================================================
# Load Example Data for MOFA+ Multi-Omics Integration
# =============================================================================
# Loads the CLL (Chronic Lymphocytic Leukemia) multi-omics dataset
# from the MOFAdata package. 200 patients, 4 omics layers:
#   - Drugs: drug response (310 features)
#   - Methylation: DNA methylation (4248 features)
#   - mRNA: gene expression (5000 features)
#   - Mutations: somatic mutations (69 features, binary)
#
# Also downloads sample metadata from EBI for clinical annotations.
# =============================================================================

options(repos = c(CRAN = "https://cloud.r-project.org"))

.install_if_missing <- function(pkg, bioc = FALSE) {
    if (!requireNamespace(pkg, quietly = TRUE)) {
        cat("Installing", pkg, "...\n")
        if (bioc) {
            if (!requireNamespace("BiocManager", quietly = TRUE))
                install.packages("BiocManager")
            BiocManager::install(pkg, ask = FALSE, update = FALSE)
        } else {
            install.packages(pkg)
        }
    }
}

#' Load CLL multi-omics example data
#'
#' @return list with components:
#'   - data: named list of 4 matrices (Drugs, Methylation, mRNA, Mutations)
#'   - metadata: data.frame of sample annotations (or NULL if download fails)
load_cll_data <- function() {
    cat("\n=== Loading CLL Multi-Omics Example Data ===\n\n")

    # --- Install/load MOFAdata ---
    .install_if_missing("MOFAdata", bioc = TRUE)
    library(MOFAdata)

    # --- Load CLL dataset ---
    cat("Loading CLL multi-omics data (200 patients, 4 omics layers)...\n")
    utils::data("CLL_data", package = "MOFAdata", envir = environment())

    # Validate structure
    stopifnot(is.list(CLL_data))
    stopifnot(length(CLL_data) >= 4)

    # --- Print per-view summary ---
    cat("\nDataset overview:\n")
    all_samples <- unique(unlist(lapply(CLL_data, colnames)))
    cat(sprintf("  Total unique samples: %d\n", length(all_samples)))
    cat("\n  View summaries:\n")
    for (view_name in names(CLL_data)) {
        mat <- CLL_data[[view_name]]
        n_feat <- nrow(mat)
        n_samp <- ncol(mat)
        pct_missing <- round((1 - n_samp / length(all_samples)) * 100, 1)
        cat(sprintf("    %-15s %5d features x %3d samples (%4.1f%% samples missing)\n",
                    view_name, n_feat, n_samp, pct_missing))
    }

    # --- Sample overlap ---
    sample_lists <- lapply(CLL_data, colnames)
    shared <- Reduce(intersect, sample_lists)
    cat(sprintf("\n  Samples with ALL 4 views: %d / %d (%.0f%%)\n",
                length(shared), length(all_samples),
                100 * length(shared) / length(all_samples)))

    # --- Download sample metadata ---
    metadata <- .download_cll_metadata()

    cat("\n✓ Data loaded successfully!\n\n")
    return(list(data = CLL_data, metadata = metadata))
}

#' Download CLL sample metadata from EBI
#' @return data.frame or NULL if download fails
.download_cll_metadata <- function() {
    cat("\nDownloading sample metadata...\n")
    urls <- c(
        "https://ftp.ebi.ac.uk/pub/databases/mofa/cll_vignette/sample_metadata.txt",
        "https://raw.githubusercontent.com/bioFAM/MOFA2_tutorials/master/R_tutorials/CLL/sample_metadata.txt"
    )

    for (url in urls) {
        tryCatch({
            tmp <- tempfile(fileext = ".txt")
            options(timeout = 60)
            utils::download.file(url, tmp, quiet = TRUE, method = "auto")
            meta <- utils::read.delim(tmp, stringsAsFactors = FALSE)
            unlink(tmp)

            if (nrow(meta) > 0 && "sample" %in% colnames(meta)) {
                rownames(meta) <- meta$sample
                cat(sprintf("  Metadata loaded: %d samples, %d variables\n",
                            nrow(meta), ncol(meta)))
                cat(sprintf("  Variables: %s\n", paste(colnames(meta), collapse = ", ")))
                return(meta)
            }
        }, error = function(e) {
            cat(sprintf("  (Download failed from %s)\n", substr(url, 1, 50)))
        })
    }

    cat("  Metadata download failed — proceeding without clinical annotations.\n")
    cat("  (Factor-trait association plots will be skipped.)\n")
    return(NULL)
}

#' Load user-provided multi-omics data
#'
#' @param file_paths Named list of file paths to CSV/TSV matrices
#'   e.g., list(RNA = "rna.csv", Protein = "protein.csv")
#' @param metadata_path Optional path to sample metadata CSV
#' @return list with components: data (named list of matrices), metadata (or NULL)
load_user_data <- function(file_paths, metadata_path = NULL) {
    cat("\n=== Loading User Multi-Omics Data ===\n\n")

    stopifnot(is.list(file_paths) && !is.null(names(file_paths)))
    stopifnot(length(file_paths) >= 2)

    data_list <- list()
    for (view_name in names(file_paths)) {
        path <- file_paths[[view_name]]
        cat(sprintf("Loading %s from %s...\n", view_name, basename(path)))

        # Read CSV or TSV
        if (grepl("\\.tsv$|\\.txt$", path, ignore.case = TRUE)) {
            mat <- as.matrix(utils::read.delim(path, row.names = 1, check.names = FALSE))
        } else {
            mat <- as.matrix(utils::read.csv(path, row.names = 1, check.names = FALSE))
        }
        cat(sprintf("  %s: %d features x %d samples\n", view_name, nrow(mat), ncol(mat)))
        data_list[[view_name]] <- mat
    }

    # Load metadata if provided
    metadata <- NULL
    if (!is.null(metadata_path)) {
        cat(sprintf("\nLoading metadata from %s...\n", basename(metadata_path)))
        if (grepl("\\.tsv$|\\.txt$", metadata_path, ignore.case = TRUE)) {
            metadata <- utils::read.delim(metadata_path, row.names = 1,
                                          stringsAsFactors = FALSE)
        } else {
            metadata <- utils::read.csv(metadata_path, row.names = 1,
                                        stringsAsFactors = FALSE)
        }
        cat(sprintf("  Metadata: %d samples, %d variables\n",
                    nrow(metadata), ncol(metadata)))
    }

    # Print summary
    all_samples <- unique(unlist(lapply(data_list, colnames)))
    cat(sprintf("\n  Total views: %d\n", length(data_list)))
    cat(sprintf("  Total unique samples: %d\n", length(all_samples)))

    cat("\n✓ Data loaded successfully!\n\n")
    return(list(data = data_list, metadata = metadata))
}
