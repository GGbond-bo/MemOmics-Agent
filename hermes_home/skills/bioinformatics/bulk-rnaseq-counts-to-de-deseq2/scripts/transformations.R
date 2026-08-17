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
# Data transformations for DESeq2
# Variance stabilization for visualization and clustering

library(DESeq2)

#' Get normalized counts from DESeqDataSet
#'
#' @param dds DESeqDataSet object (after DESeq())
#'
#' @return Matrix of size-factor normalized counts
#' @export
get_normalized_counts <- function(dds) {
    cat("Extracting normalized counts...\n")
    norm_counts <- counts(dds, normalized = TRUE)

    # Show size factors
    cat("Size factors:\n")
    print(sizeFactors(dds))
    cat("\n")

    return(norm_counts)
}

#' Apply variance stabilizing transformation
#'
#' @param dds DESeqDataSet object (after DESeq())
#' @param blind Whether to estimate dispersions ignoring design (default: FALSE)
#'
#' @return DESeqTransform object with VST values
#' @export
apply_vst <- function(dds, blind = FALSE) {
    cat("Applying variance stabilizing transformation (VST)...\n")

    if (blind) {
        cat("  blind = TRUE: Estimating dispersions without design\n")
    } else {
        cat("  blind = FALSE: Using design for transformation\n")
    }

    vsd <- vst(dds, blind = blind)

    cat("  Recommended for: >30 samples\n")
    cat("  VST transformation complete\n\n")

    return(vsd)
}

#' Apply regularized log transformation
#'
#' @param dds DESeqDataSet object (after DESeq())
#' @param blind Whether to estimate dispersions ignoring design (default: FALSE)
#'
#' @return DESeqTransform object with rlog values
#' @export
apply_rlog <- function(dds, blind = FALSE) {
    cat("Applying regularized log transformation (rlog)...\n")

    if (blind) {
        cat("  blind = TRUE: Estimating dispersions without design\n")
    } else {
        cat("  blind = FALSE: Using design for transformation\n")
    }

    if (ncol(dds) > 100) {
        warning("rlog is slow for large datasets (>100 samples). Consider using VST instead.")
    }

    rld <- rlog(dds, blind = blind)

    cat("  Recommended for: <30 samples\n")
    cat("  rlog transformation complete\n\n")

    return(rld)
}

#' Choose and apply appropriate transformation
#'
#' @param dds DESeqDataSet object (after DESeq())
#' @param method Transformation method: 'auto', 'vst', or 'rlog' (default: 'auto')
#' @param blind Whether to estimate dispersions ignoring design (default: FALSE)
#'
#' @return DESeqTransform object
#' @export
transform_counts <- function(dds, method = "auto", blind = FALSE) {
    n_samples <- ncol(dds)

    cat("=== Transforming Counts ===\n")
    cat("Samples:", n_samples, "\n\n")

    if (method == "auto") {
        if (n_samples > 30) {
            cat("Auto-selecting VST (>30 samples)\n\n")
            return(apply_vst(dds, blind = blind))
        } else {
            cat("Auto-selecting rlog (<30 samples)\n\n")
            return(apply_rlog(dds, blind = blind))
        }
    } else if (method == "vst") {
        return(apply_vst(dds, blind = blind))
    } else if (method == "rlog") {
        return(apply_rlog(dds, blind = blind))
    } else {
        stop("method must be 'auto', 'vst', or 'rlog'")
    }
}

#' Extract transformed values as matrix
#'
#' @param transformed DESeqTransform object (from vst or rlog)
#'
#' @return Matrix of transformed values
#' @export
get_transformed_matrix <- function(transformed) {
    return(assay(transformed))
}

#' Compare VST and rlog transformations
#'
#' @param dds DESeqDataSet object (after DESeq())
#'
#' @export
compare_transformations <- function(dds) {
    cat("=== Comparing Transformations ===\n\n")

    # Get both transformations
    cat("Computing VST...\n")
    vsd <- vst(dds, blind = FALSE)

    cat("Computing rlog...\n")
    if (ncol(dds) > 100) {
        cat("⚠ Warning: rlog may be slow for large datasets\n")
    }
    rld <- rlog(dds, blind = FALSE)

    # Extract matrices
    vsd_mat <- assay(vsd)
    rld_mat <- assay(rld)

    # Compare
    cat("\n=== Comparison ===\n")
    cat("Correlation between VST and rlog:", cor(vsd_mat[,1], rld_mat[,1]), "\n")

    # Plot comparison
    par(mfrow = c(1, 2))

    # VST
    plot(vsd_mat[,1], vsd_mat[,2],
         main = "VST",
         xlab = colnames(vsd_mat)[1],
         ylab = colnames(vsd_mat)[2],
         pch = 16, cex = 0.5)

    # rlog
    plot(rld_mat[,1], rld_mat[,2],
         main = "rlog",
         xlab = colnames(rld_mat)[1],
         ylab = colnames(rld_mat)[2],
         pch = 16, cex = 0.5)

    par(mfrow = c(1, 1))

    cat("\nRecommendation:\n")
    if (ncol(dds) > 30) {
        cat("  Use VST for your dataset (n =", ncol(dds), "samples)\n")
    } else {
        cat("  Use rlog for your dataset (n =", ncol(dds), "samples)\n")
    }
}

# Transformation decision guide
#' Print transformation decision guide
#'
#' @export
print_transformation_guide <- function() {
    cat("=== Transformation Decision Guide ===\n\n")
    cat("WHEN TO USE TRANSFORMATIONS:\n")
    cat("  ✓ For visualization (PCA, heatmaps)\n")
    cat("  ✓ For clustering analysis\n")
    cat("  ✓ When methods assume homoscedasticity\n")
    cat("  ✗ NOT for differential expression (use raw counts)\n\n")

    cat("VST (Variance Stabilizing Transformation):\n")
    cat("  • Use when: n > 30 samples\n")
    cat("  • Pros: Fast, suitable for large datasets\n")
    cat("  • Cons: Less accurate for very small samples\n")
    cat("  • Function: vst(dds, blind = FALSE)\n\n")

    cat("RLOG (Regularized Log Transformation):\n")
    cat("  • Use when: n < 30 samples\n")
    cat("  • Pros: Better stabilization for small samples\n")
    cat("  • Cons: Slow for large datasets (>100 samples)\n")
    cat("  • Function: rlog(dds, blind = FALSE)\n\n")

    cat("BLIND PARAMETER:\n")
    cat("  • blind = FALSE: Use design formula (recommended)\n")
    cat("  • blind = TRUE: Ignore design (exploratory only)\n\n")
}

# Example usage:
# library(DESeq2)
# source("scripts/transformations.R")
#
# # After DESeq2 analysis
# dds <- DESeq(dds)
#
# # Show decision guide
# print_transformation_guide()
#
# # Auto-select transformation
# transformed <- transform_counts(dds, method = "auto")
# transformed_matrix <- get_transformed_matrix(transformed)
#
# # Or manually choose
# vsd <- apply_vst(dds, blind = FALSE)
# rld <- apply_rlog(dds, blind = FALSE)
#
# # Compare both methods
# compare_transformations(dds)
