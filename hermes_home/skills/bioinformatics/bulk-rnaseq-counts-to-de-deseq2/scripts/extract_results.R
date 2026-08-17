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
# Extract and filter DESeq2 results
# Functions for getting results with various contrasts and thresholds

library(DESeq2)
library(apeglm)

#' Extract results by coefficient name
#'
#' @param dds DESeqDataSet object (after DESeq())
#' @param coef_name Coefficient name (see resultsNames(dds))
#' @param alpha Significance threshold (default: 0.05)
#'
#' @return DESeqResults object
#' @export
extract_by_coefficient <- function(dds, coef_name, alpha = 0.05) {
    cat("Extracting results for:", coef_name, "\n")
    cat("Significance threshold: alpha =", alpha, "\n\n")

    res <- results(dds, name = coef_name, alpha = alpha)

    cat("Results summary:\n")
    print(summary(res))

    return(res)
}

#' Extract results by contrast
#'
#' @param dds DESeqDataSet object (after DESeq())
#' @param factor_name Factor name in colData (e.g., 'condition')
#' @param numerator Level to compare (e.g., 'treated')
#' @param denominator Reference level (e.g., 'control')
#' @param alpha Significance threshold (default: 0.05)
#'
#' @return DESeqResults object
#' @export
extract_by_contrast <- function(dds, factor_name, numerator, denominator,
                                alpha = 0.05) {
    cat("Extracting contrast:", numerator, "vs", denominator, "\n")
    cat("Factor:", factor_name, "\n")
    cat("Significance threshold: alpha =", alpha, "\n\n")

    res <- results(dds,
                  contrast = c(factor_name, numerator, denominator),
                  alpha = alpha)

    cat("Results summary:\n")
    print(summary(res))

    return(res)
}

#' Apply log fold change shrinkage
#'
#' @param dds DESeqDataSet object (after DESeq())
#' @param coef_name Coefficient name (required for apeglm/ashr)
#' @param shrink_type Shrinkage method: 'apeglm', 'ashr', or 'normal' (default: 'apeglm')
#'
#' @return DESeqResults object with shrunken LFC
#' @export
apply_lfc_shrinkage <- function(dds, coef_name, shrink_type = "apeglm") {
    cat("Applying LFC shrinkage...\n")
    cat("  Coefficient:", coef_name, "\n")
    cat("  Method:", shrink_type, "\n")

    if (shrink_type == "apeglm") {
        cat("  ✓ Best shrinkage, preserves large LFC\n\n")
    } else if (shrink_type == "ashr") {
        cat("  ✓ Good for large datasets\n\n")
    } else if (shrink_type == "normal") {
        cat("  ⚠ Legacy method, consider apeglm/ashr\n\n")
    }

    res_shrunk <- lfcShrink(dds, coef = coef_name, type = shrink_type)

    cat("Shrinkage complete\n")
    cat("Use for: ranking genes, visualization (volcano/MA plots)\n")
    cat("Don't use for: hypothesis testing (use unshrunk results())\n\n")

    return(res_shrunk)
}

#' Extract results with fold change threshold
#'
#' @param dds DESeqDataSet object (after DESeq())
#' @param lfc_threshold Log2 fold change threshold (e.g., 1 = 2-fold)
#' @param coef_name Coefficient name (optional)
#' @param alpha Significance threshold (default: 0.05)
#'
#' @return DESeqResults object
#' @export
extract_with_lfc_threshold <- function(dds, lfc_threshold, coef_name = NULL,
                                       alpha = 0.05) {
    cat("Testing for |log2FC| >", lfc_threshold, "\n")
    cat("This tests H1: |log2FC| >", lfc_threshold,
        "vs H0: |log2FC| ≤", lfc_threshold, "\n\n")

    if (!is.null(coef_name)) {
        res <- results(dds,
                      name = coef_name,
                      lfcThreshold = lfc_threshold,
                      altHypothesis = "greaterAbs",
                      alpha = alpha)
    } else {
        res <- results(dds,
                      lfcThreshold = lfc_threshold,
                      altHypothesis = "greaterAbs",
                      alpha = alpha)
    }

    cat("Results summary:\n")
    print(summary(res))

    return(res)
}

#' Filter results by significance and fold change
#'
#' @param res DESeqResults object
#' @param padj_cutoff Adjusted p-value cutoff (default: 0.05)
#' @param lfc_cutoff Log2 fold change cutoff (default: 1)
#'
#' @return Filtered DESeqResults object
#' @export
filter_significant <- function(res, padj_cutoff = 0.05, lfc_cutoff = 1) {
    cat("Filtering results...\n")
    cat("  padj <", padj_cutoff, "\n")
    cat("  |log2FC| >", lfc_cutoff, "\n\n")

    sig <- subset(res, padj < padj_cutoff & abs(log2FoldChange) > lfc_cutoff)

    cat("Significant genes:", nrow(sig), "\n")
    cat("  Upregulated:", sum(sig$log2FoldChange > 0, na.rm = TRUE), "\n")
    cat("  Downregulated:", sum(sig$log2FoldChange < 0, na.rm = TRUE), "\n\n")

    return(sig)
}

#' Get top genes by adjusted p-value
#'
#' @param res DESeqResults object
#' @param n Number of top genes (default: 100)
#'
#' @return Top DESeqResults ordered by padj
#' @export
get_top_genes <- function(res, n = 100) {
    cat("Getting top", n, "genes by adjusted p-value...\n")

    res_ordered <- res[order(res$padj), ]
    top <- head(res_ordered, n)

    cat("Top gene:", rownames(top)[1], "\n")
    cat("  log2FC:", top$log2FoldChange[1], "\n")
    cat("  padj:", top$padj[1], "\n\n")

    return(top)
}

#' List all available coefficients
#'
#' @param dds DESeqDataSet object (after DESeq())
#'
#' @export
show_coefficients <- function(dds) {
    cat("=== Available Coefficients ===\n\n")
    coefs <- resultsNames(dds)

    for (i in seq_along(coefs)) {
        cat(i, ". ", coefs[i], "\n", sep = "")
    }

    cat("\nUse extract_by_coefficient(dds, '", coefs[1], "')\n", sep = "")
    cat("Or apply_lfc_shrinkage(dds, '", coefs[2], "')\n", sep = "")
}

#' Standard results extraction workflow
#'
#' @param dds DESeqDataSet object (after DESeq())
#' @param coef_name Coefficient name (if NULL, shows available coefficients)
#' @param apply_shrinkage Whether to apply LFC shrinkage (default: TRUE)
#' @param padj_cutoff Adjusted p-value cutoff (default: 0.05)
#' @param lfc_cutoff Log2 fold change cutoff (default: 1)
#'
#' @return List with 'results', 'shrunk' (if requested), and 'significant'
#' @export
standard_extraction <- function(dds, coef_name = NULL, apply_shrinkage = TRUE,
                               padj_cutoff = 0.05, lfc_cutoff = 1) {
    cat("=== Extracting DESeq2 Results ===\n\n")

    # Show coefficients if not specified
    if (is.null(coef_name)) {
        show_coefficients(dds)
        cat("\nPlease specify coef_name parameter\n")
        return(NULL)
    }

    # Extract unshrunk results
    cat("1. Extracting results...\n")
    res <- extract_by_coefficient(dds, coef_name, alpha = padj_cutoff)
    cat("\n")

    output <- list(results = res)

    # Apply shrinkage if requested
    if (apply_shrinkage) {
        cat("2. Applying LFC shrinkage...\n")
        res_shrunk <- apply_lfc_shrinkage(dds, coef_name, shrink_type = "apeglm")
        output$shrunk <- res_shrunk
        cat("\n")
    }

    # Filter significant genes
    cat("3. Filtering significant genes...\n")
    sig <- filter_significant(res, padj_cutoff = padj_cutoff, lfc_cutoff = lfc_cutoff)
    output$significant <- sig

    cat("\n=== Extraction Complete ===\n")
    return(output)
}

# Example usage:
# library(DESeq2)
# library(apeglm)
# source("scripts/extract_results.R")
#
# # After DESeq2 analysis
# dds <- DESeq(dds)
#
# # Show available coefficients
# show_coefficients(dds)
#
# # Standard workflow (gets results, shrunk LFC, and significant genes)
# output <- standard_extraction(dds, coef_name = "condition_treated_vs_control")
# res <- output$results
# res_shrunk <- output$shrunk
# sig <- output$significant
#
# # Or extract manually
# res <- extract_by_coefficient(dds, "condition_treated_vs_control")
# res <- extract_by_contrast(dds, "condition", "treated", "control")
# res_shrunk <- apply_lfc_shrinkage(dds, "condition_treated_vs_control")
# sig <- filter_significant(res, padj_cutoff = 0.05, lfc_cutoff = 1)
