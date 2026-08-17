# ============================================================
# 🔒 MemOmics 审查铁律 — 执行本脚本前后的强制步骤
# ============================================================
# 执行前必须: rail_review(action="pre")  — 环境检查 + 参数校验 + 代码审查
# 执行后必须: rail_review(action="post") — 结果质量评估 + 图表检查 + 数值检查
# 参数有争议: debate_analysis(topic=..., context=...) — 多角色辩论
# 执行失败:   skill_evolution(action="record_error") — 记录错误
# 修复成功:   skill_evolution(action="update_script") — 替换脚本
# ============================================================
# Generate PDF analysis report for proteomics DE analysis
# Uses rmarkdown with PDF output (optional dependency)

#' Generate PDF analysis report
#'
#' @param deqms_results DEqMS results data.frame
#' @param metadata Sample metadata data.frame
#' @param comparison_name Name of the comparison (e.g., "miR372-ctrl")
#' @param output_dir Directory containing plots and for output
#' @param n_proteins Total number of proteins tested
#' @return Path to generated PDF, or NULL if generation failed
#' @export
generate_report <- function(deqms_results, metadata,
                             comparison_name = "Treatment vs Control",
                             output_dir = "results",
                             n_proteins = NULL,
                             padj_threshold = 0.05,
                             lfc_threshold = 0.58) {

    # Check rmarkdown availability
    if (!requireNamespace("rmarkdown", quietly = TRUE)) {
        cat("   rmarkdown not installed - skipping PDF report\n")
        cat("   Install with: install.packages('rmarkdown')\n")
        return(NULL)
    }

    # Check for LaTeX
    has_latex <- FALSE
    if (requireNamespace("tinytex", quietly = TRUE)) {
        has_latex <- tinytex::is_tinytex() || nchar(Sys.which("xelatex")) > 0
    }
    if (!has_latex) {
        has_latex <- nchar(Sys.which("pdflatex")) > 0 || nchar(Sys.which("xelatex")) > 0
    }

    if (!has_latex) {
        cat("   No LaTeX installation found - skipping PDF report\n")
        cat("   Install with: tinytex::install_tinytex()\n")
        return(NULL)
    }

    cat("   Generating PDF report...\n")

    # Compute summary stats
    if (is.null(n_proteins)) n_proteins <- nrow(deqms_results)
    n_sig <- sum(deqms_results$sca.adj.pval < padj_threshold &
                  abs(deqms_results$logFC) > lfc_threshold, na.rm = TRUE)
    n_up <- sum(deqms_results$sca.adj.pval < padj_threshold &
                 deqms_results$logFC > lfc_threshold, na.rm = TRUE)
    n_down <- sum(deqms_results$sca.adj.pval < padj_threshold &
                   deqms_results$logFC < -lfc_threshold, na.rm = TRUE)
    n_samples <- nrow(metadata)
    conditions <- paste(levels(metadata$condition), collapse = ", ")

    # Top 20 proteins table
    top20 <- head(deqms_results[order(deqms_results$sca.adj.pval), ], 20)
    top20_table <- data.frame(
        Protein = top20$protein,
        logFC = sprintf("%.3f", top20$logFC),
        `DEqMS.adj.pval` = sprintf("%.2e", top20$sca.adj.pval),
        `limma.adj.pval` = sprintf("%.2e", top20$adj.P.Val),
        PSM.count = top20$count,
        check.names = FALSE
    )

    # Find available plot files
    plot_files <- list.files(output_dir, pattern = "\\.png$", full.names = TRUE)

    # Build Rmd content
    rmd_content <- paste0(
'---
title: "Proteomics Differential Expression Report"
subtitle: "limma + DEqMS Analysis"
date: "', format(Sys.Date(), "%B %d, %Y"), '"
output:
  pdf_document:
    toc: true
    toc_depth: 2
    number_sections: true
---

```{r setup, include=FALSE}
knitr::opts_chunk$set(echo = FALSE, warning = FALSE, message = FALSE)
```

# Summary

- **Comparison:** ', comparison_name, '
- **Total proteins tested:** ', format(n_proteins, big.mark = ","), '
- **Significant proteins (DEqMS adj.p < ', padj_threshold, ', |logFC| > ', sprintf("%.2f", lfc_threshold), '):** ', n_sig, '
  - Upregulated: ', n_up, '
  - Downregulated: ', n_down, '
- **Samples:** ', n_samples, '
- **Conditions:** ', conditions, '

# Introduction

This report presents the results of differential protein expression analysis using the
**limma + DEqMS** pipeline. DEqMS extends limma by incorporating PSM (Peptide Spectrum Match)
count information to provide more accurate variance estimation for mass spectrometry
proteomics data, resulting in improved statistical power compared to standard limma analysis.

# Methods

## Analysis Pipeline

1. **PSM-to-protein aggregation:** `medianSweeping()` — median-based summarization of PSM-level
   log2 intensities to protein-level relative abundances
2. **Missing value filtering:** Proteins with >50% missing values in all conditions removed
3. **Missing value imputation:** MinProb method (drawing from low-intensity distribution,
   appropriate for MNAR pattern in MS data)
4. **Normalization:** Median centering (column median subtracted)
5. **Differential expression:** limma linear model (`lmFit` + `contrasts.fit` + `eBayes`)
6. **Variance correction:** DEqMS `spectraCounteBayes()` — PSM-count-aware empirical Bayes
   moderation of protein-level variance

## Software

- **limma** (Ritchie et al., *Nucleic Acids Research*, 2015)
- **DEqMS** (Zhu et al., *Molecular & Cellular Proteomics*, 2020)
- R version: `r paste0(R.version$major, ".", R.version$minor)`

# Results

## Top Differentially Expressed Proteins

```{r top-proteins}
top20 <- data.frame(
    Protein = c(', paste0('"', top20_table$Protein, '"', collapse = ", "), '),
    logFC = c(', paste(top20_table$logFC, collapse = ", "), '),
    DEqMS.adj.pval = c(', paste0('"', top20_table$DEqMS.adj.pval, '"', collapse = ", "), '),
    PSM.count = c(', paste(top20_table$PSM.count, collapse = ", "), '),
    check.names = FALSE
)
knitr::kable(top20, caption = "Top 20 differentially expressed proteins by DEqMS adjusted p-value")
```
')

    # Add figures
    figure_map <- list(
        "volcano_plot.png" = "Volcano plot showing differentially expressed proteins. Red: upregulated, Blue: downregulated.",
        "ma_plot.png" = "MA plot showing log2 fold change vs average expression.",
        "pca_plot.png" = "PCA of normalized protein abundances.",
        "intensity_distribution.png" = "Protein intensity distributions before and after normalization.",
        "sample_correlation_heatmap.png" = "Sample-to-sample Pearson correlation.",
        "missing_values_heatmap.png" = "Missing value pattern across samples.",
        "variance_psm_plot.png" = "Relationship between protein variance and PSM count."
    )

    rmd_content <- paste0(rmd_content, "\n## Figures\n\n")

    for (fname in names(figure_map)) {
        fpath <- file.path(output_dir, fname)
        if (file.exists(fpath)) {
            abs_path <- normalizePath(fpath)
            rmd_content <- paste0(rmd_content,
                '```{r, out.width="100%", fig.cap="', figure_map[[fname]], '"}\n',
                'knitr::include_graphics("', abs_path, '")\n',
                '```\n\n')
        }
    }

    # Conclusions
    rmd_content <- paste0(rmd_content, '
# Conclusions

- **', n_sig, ' proteins** were identified as significantly differentially expressed
  (DEqMS adjusted p-value < ', padj_threshold, ', |log2 fold change| > ', sprintf("%.2f", lfc_threshold), ') in the comparison **', comparison_name, '**.
- Of these, **', n_up, '** were upregulated and **', n_down, '** were downregulated.
- DEqMS variance correction using PSM counts provides more accurate significance estimates
  than standard limma, particularly for proteins with low PSM counts.

## Caveats

- MinProb imputation assumes Missing Not At Random (MNAR) — appropriate for most MS data
  but may not suit all experimental designs.
- Results should be validated with orthogonal methods (e.g., Western blot, targeted proteomics).

# References

1. Zhu Y, et al. DEqMS: A Method for Accurate Variance Estimation in Differential Protein
   Expression Analysis. *Molecular & Cellular Proteomics*. 2020;19(6):1047-1057.
2. Ritchie ME, et al. limma powers differential expression analyses for RNA-sequencing and
   microarray studies. *Nucleic Acids Research*. 2015;43(7):e47.
')

    # Write temp Rmd file
    rmd_path <- file.path(output_dir, "analysis_report.Rmd")
    writeLines(rmd_content, rmd_path)

    # Render PDF
    pdf_path <- file.path(output_dir, "analysis_report.pdf")
    tryCatch({
        rmarkdown::render(
            rmd_path,
            output_file = basename(pdf_path),
            output_dir = output_dir,
            quiet = TRUE
        )
        # Clean up temp files
        file.remove(rmd_path)
        tex_files <- list.files(output_dir, pattern = "\\.(tex|log|aux)$", full.names = TRUE)
        if (length(tex_files) > 0) file.remove(tex_files)

        cat("   Saved:", pdf_path, "\n")
        return(pdf_path)
    }, error = function(e) {
        cat("   PDF rendering failed:", conditionMessage(e), "\n")
        cat("   (Markdown report still available)\n")
        # Clean up
        if (file.exists(rmd_path)) file.remove(rmd_path)
        return(NULL)
    })
}
