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
# Export MOFA+ Analysis Results
# =============================================================================
# Exports factor values, feature weights, variance explained, and analysis
# objects. Generates markdown summary report and optional PDF report.
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

#' Export all MOFA analysis results
#'
#' @param model Trained MOFA model object
#' @param output_dir Directory for output files
export_all <- function(model, output_dir = "mofa_results") {

    cat("\n=== Exporting MOFA Analysis Results ===\n\n")

    .install_if_missing("MOFA2", bioc = TRUE)
    .install_if_missing("reshape2")
    library(MOFA2)

    if (!dir.exists(output_dir)) {
        dir.create(output_dir, recursive = TRUE)
    }

    # -------------------------------------------------------------------------
    # 1. Factor values (samples x factors)
    # -------------------------------------------------------------------------
    cat("1. Exporting factor values...\n")
    factors_df <- get_factors(model, as.data.frame = TRUE)
    factors_wide <- reshape2::dcast(factors_df, sample ~ factor, value.var = "value")
    write.csv(factors_wide, file.path(output_dir, "factor_values.csv"), row.names = FALSE)
    cat(sprintf("   %d samples x %d factors\n", nrow(factors_wide), ncol(factors_wide) - 1))
    cat(sprintf("   Saved: %s\n\n", file.path(output_dir, "factor_values.csv")))

    # -------------------------------------------------------------------------
    # 2. Feature weights per view
    # -------------------------------------------------------------------------
    cat("2. Exporting feature weights per view...\n")
    weights_df <- get_weights(model, as.data.frame = TRUE)
    views <- unique(weights_df$view)
    for (v in views) {
        w_sub <- weights_df[weights_df$view == v, ]
        w_wide <- reshape2::dcast(w_sub, feature ~ factor, value.var = "value")
        fname <- sprintf("weights_%s.csv", gsub("[^a-zA-Z0-9]", "_", tolower(v)))
        write.csv(w_wide, file.path(output_dir, fname), row.names = FALSE)
        cat(sprintf("   %s: %d features x %d factors -> %s\n",
                    v, nrow(w_wide), ncol(w_wide) - 1, fname))
    }
    cat("\n")

    # -------------------------------------------------------------------------
    # 3. Variance explained
    # -------------------------------------------------------------------------
    cat("3. Exporting variance explained...\n")
    r2 <- get_variance_explained(model)
    r2_per_factor <- r2$r2_per_factor[[1]]
    r2_total <- r2$r2_total[[1]]

    # Per-factor per-view
    r2_df <- as.data.frame(r2_per_factor)
    r2_df$Factor <- rownames(r2_df)
    write.csv(r2_df, file.path(output_dir, "variance_explained_per_factor.csv"),
              row.names = FALSE)

    # Total per view
    total_df <- data.frame(View = names(r2_total), Total_R2 = as.numeric(r2_total))
    write.csv(total_df, file.path(output_dir, "variance_explained_total.csv"),
              row.names = FALSE)
    cat("   Saved: variance_explained_per_factor.csv\n")
    cat("   Saved: variance_explained_total.csv\n\n")

    # -------------------------------------------------------------------------
    # 4. Top features per factor per view
    # -------------------------------------------------------------------------
    cat("4. Exporting top features per factor...\n")
    top_list <- list()
    for (f in rownames(r2_per_factor)) {
        for (v in views) {
            w_sub <- weights_df[weights_df$factor == f & weights_df$view == v, ]
            w_sub <- w_sub[order(abs(w_sub$value), decreasing = TRUE), ]
            top <- head(w_sub, 20)
            if (nrow(top) > 0) {
                top$rank <- seq_len(nrow(top))
                top_list[[paste(f, v)]] <- top
            }
        }
    }
    top_features_df <- do.call(rbind, top_list)
    write.csv(top_features_df, file.path(output_dir, "top_features_per_factor.csv"),
              row.names = FALSE)
    cat(sprintf("   %d top features across all factor-view combinations\n",
                nrow(top_features_df)))
    cat("   Saved: top_features_per_factor.csv\n\n")

    # -------------------------------------------------------------------------
    # 5. MOFA model object (RDS) - CRITICAL for downstream
    # -------------------------------------------------------------------------
    cat("5. Saving MOFA model object (RDS)...\n")
    saveRDS(model, file.path(output_dir, "mofa_model.rds"))
    cat("   Saved: mofa_model.rds\n")
    cat("   (Load with: model <- readRDS('mofa_results/mofa_model.rds'))\n\n")

    # -------------------------------------------------------------------------
    # 6. Markdown summary report
    # -------------------------------------------------------------------------
    cat("6. Generating summary report...\n")
    .generate_markdown_report(model, r2_per_factor, r2_total, factors_wide,
                              views, output_dir)

    # -------------------------------------------------------------------------
    # 7. PDF report (optional)
    # -------------------------------------------------------------------------
    cat("7. Generating PDF report...\n")
    tryCatch({
        .generate_pdf_report(model, output_dir)
    }, error = function(e) {
        cat(sprintf("   PDF generation skipped: %s\n", e$message))
        cat("   (Markdown report still available)\n")
    })

    # -------------------------------------------------------------------------
    # Summary
    # -------------------------------------------------------------------------
    all_files <- list.files(output_dir, recursive = FALSE)
    cat(sprintf("\n  Total files in %s/: %d\n", output_dir, length(all_files)))

    cat("\n=== Export Complete ===\n\n")
}


# --- Markdown report ---
.generate_markdown_report <- function(model, r2_per_factor, r2_total,
                                       factors_wide, views, output_dir) {
    report_path <- file.path(output_dir, "analysis_report.md")

    # Get parameters
    params <- tryCatch(model@cache[["analysis_params"]], error = function(e) list())

    lines <- c(
        "# MOFA+ Multi-Omics Integration Report",
        "",
        sprintf("**Date:** %s", Sys.Date()),
        sprintf("**MOFA2 version:** %s", as.character(packageVersion("MOFA2"))),
        "",
        "---",
        "",
        "## 1. Introduction",
        "",
        "Multi-Omics Factor Analysis (MOFA+) was used to identify latent factors",
        "capturing the major sources of variation across multiple omics layers.",
        "MOFA decomposes the data into a small number of interpretable factors,",
        "each explaining variation in one or more omics views.",
        "",
        "## 2. Dataset Summary",
        "",
        sprintf("- **Samples:** %d", nrow(factors_wide)),
        sprintf("- **Views:** %s", paste(views, collapse = ", ")),
        sprintf("- **Factors inferred:** %d", ncol(factors_wide) - 1),
        ""
    )

    # View details
    lines <- c(lines,
        "| View | Features | Likelihood |",
        "|------|----------|------------|"
    )
    likelihoods <- tryCatch(params$likelihoods, error = function(e) NULL)
    for (v in views) {
        n_feat <- model@dimensions$D[[v]]
        lik <- if (!is.null(likelihoods)) likelihoods[v] else "gaussian"
        lines <- c(lines, sprintf("| %s | %d | %s |", v, n_feat, lik))
    }

    # Variance explained
    lines <- c(lines, "",
        "## 3. Variance Explained",
        "",
        "### Total variance per view",
        "",
        "| View | R² (%) |",
        "|------|--------|"
    )
    for (v in names(r2_total)) {
        lines <- c(lines, sprintf("| %s | %.1f |", v, r2_total[v]))
    }

    # Top factors
    factor_importance <- apply(r2_per_factor, 1, sum)
    top_factors <- names(sort(factor_importance, decreasing = TRUE))[1:min(5, length(factor_importance))]
    lines <- c(lines, "",
        "### Top factors by total variance",
        "",
        "| Factor | Total R² (%) | Dominant View |",
        "|--------|-------------|---------------|"
    )
    for (f in top_factors) {
        total_r2 <- sum(r2_per_factor[f, ])
        dominant <- names(which.max(r2_per_factor[f, ]))
        lines <- c(lines, sprintf("| %s | %.1f | %s |", f, total_r2, dominant))
    }

    # Parameters
    lines <- c(lines, "",
        "## 4. Methods",
        "",
        "MOFA+ (Argelaguet et al., 2020) was applied with the following parameters:",
        "",
        sprintf("- **Number of factors:** %s", ifelse(is.null(params$n_factors), "15", params$n_factors)),
        sprintf("- **Convergence mode:** %s", ifelse(is.null(params$convergence_mode), "slow", params$convergence_mode)),
        sprintf("- **Scale views:** %s", ifelse(is.null(params$scale_views), "TRUE", params$scale_views)),
        sprintf("- **Random seed:** %s", ifelse(is.null(params$seed), "42", params$seed)),
        "",
        "## 5. Output Files",
        "",
        "| File | Description |",
        "|------|-------------|",
        "| `factor_values.csv` | Sample factor scores (samples x factors) |",
        "| `weights_*.csv` | Feature weights per view (features x factors) |",
        "| `variance_explained_per_factor.csv` | R² per factor per view |",
        "| `variance_explained_total.csv` | Total R² per view |",
        "| `top_features_per_factor.csv` | Top 20 features per factor per view |",
        "| `mofa_model.rds` | Complete MOFA model (load with `readRDS()`) |",
        "",
        "## 6. References",
        "",
        "- Argelaguet R, et al. (2020) MOFA+: a statistical framework for comprehensive",
        "  integration of multi-modal single-cell data. *Genome Biology* 21:111.",
        "- Argelaguet R, et al. (2018) Multi-Omics Factor Analysis—a framework for",
        "  unsupervised integration of multi-omics data sets. *Molecular Systems Biology* 14:e8124."
    )

    writeLines(lines, report_path)
    cat(sprintf("   Saved: %s\n\n", report_path))
}


# --- PDF report (optional, via rmarkdown) ---
.generate_pdf_report <- function(model, output_dir) {
    if (!requireNamespace("rmarkdown", quietly = TRUE)) {
        cat("   rmarkdown not installed — skipping PDF\n")
        cat("   Install with: install.packages('rmarkdown')\n")
        return(invisible(NULL))
    }

    # Check for LaTeX
    has_latex <- tryCatch({
        system2("pdflatex", "--version", stdout = TRUE, stderr = TRUE)
        TRUE
    }, error = function(e) FALSE, warning = function(w) FALSE)

    if (!has_latex && requireNamespace("tinytex", quietly = TRUE)) {
        has_latex <- tinytex::is_tinytex()
    }

    if (!has_latex) {
        cat("   LaTeX not available — skipping PDF\n")
        cat("   Install with: tinytex::install_tinytex()\n")
        return(invisible(NULL))
    }

    # Use absolute paths so knitr can find files regardless of working directory
    abs_output <- normalizePath(output_dir, mustWork = FALSE)

    # Build Rmd with paste0 to avoid sprintf percent-escaping issues
    rmd_content <- paste0('---
title: "MOFA+ Multi-Omics Integration Report"
date: "', Sys.Date(), '"
output: pdf_document
---

```{r setup, include=FALSE}
knitr::opts_chunk$set(echo = FALSE, warning = FALSE, message = FALSE)
output_dir <- "', abs_output, '"
```

## Dataset Summary

```{r}
model <- readRDS(file.path(output_dir, "mofa_model.rds"))
library(MOFA2)
r2 <- get_variance_explained(model)
knitr::kable(as.data.frame(r2$r2_total[[1]]), col.names = "Total R2 (%)",
             digits = 1)
```

## Variance Explained

```{r, out.width="100%"}
knitr::include_graphics(file.path(output_dir, "mofa_variance_per_factor.png"))
```

## Factor Scatter

```{r, out.width="85%"}
knitr::include_graphics(file.path(output_dir, "mofa_factor_scatter.png"))
```

\\newpage

## Factor Heatmap

```{r, out.width="100%"}
knitr::include_graphics(file.path(output_dir, "mofa_factor_heatmap.png"))
```

## Top Feature Weights

```{r, out.width="100%"}
knitr::include_graphics(file.path(output_dir, "mofa_top_weights.png"))
```

## References

- Argelaguet R, et al. (2020) MOFA+. *Genome Biology* 21:111.
- Argelaguet R, et al. (2018) Multi-Omics Factor Analysis. *Mol Syst Biol* 14:e8124.
')

    rmd_path <- file.path(output_dir, "analysis_report.Rmd")
    writeLines(rmd_content, rmd_path)

    tryCatch({
        rmarkdown::render(rmd_path, output_dir = output_dir, quiet = TRUE)
        cat("   Saved: analysis_report.pdf\n")
        unlink(rmd_path)  # Clean up Rmd
    }, error = function(e) {
        cat(sprintf("   PDF rendering failed: %s\n", e$message))
        unlink(rmd_path)
    })
}
