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
# Batch Design Validation Functions
# Validate batch assignments to prevent confounding and check balance

#' Internal helper to save plots in both PNG and SVG formats
#' @param plot ggplot object
#' @param base_path Base file path (extension will be replaced)
#' @param width Plot width in inches
#' @param height Plot height in inches
#' @param dpi Resolution for PNG
.save_plot <- function(plot, base_path, width = 8, height = 6, dpi = 300) {
  # Compute paths — handle missing extensions
  if (!grepl("\\.(svg|png)$", base_path)) {
    png_path <- paste0(base_path, ".png")
    svg_path <- paste0(base_path, ".svg")
  } else {
    png_path <- sub("\\.(svg|png)$", ".png", base_path)
    svg_path <- sub("\\.(svg|png)$", ".svg", base_path)
  }

  # Always save PNG
  ggplot2::ggsave(png_path, plot = plot, width = width, height = height, dpi = dpi, device = "png")
  cat("   Saved:", png_path, "\n")

  # Always try SVG - try ggsave first, fall back to svg() device
  tryCatch({
    ggplot2::ggsave(svg_path, plot = plot, width = width, height = height, device = "svg")
    cat("   Saved:", svg_path, "\n")
  }, error = function(e) {
    # If ggsave fails, try base R svg() device directly
    tryCatch({
      svg(svg_path, width = width, height = height)
      print(plot)
      dev.off()
      cat("   Saved:", svg_path, "\n")
    }, error = function(e2) {
      cat("   (SVG export failed - PNG available)\n")
    })
  })
}

#' Check for confounding between batch and condition
#'
#' @param batch_assignment Data frame with batch assignments
#' @param condition_var Name of condition variable column
#' @param batch_var Name of batch variable column (default: "batch")
#' @return List with test results and interpretation
#' @export
#' @examples
#' # Check if batch is confounded with condition
#' # confounding_check <- check_confounding(batch_design, "condition")
check_confounding <- function(batch_assignment,
                              condition_var,
                              batch_var = "batch") {

  # Validate inputs
  if (!condition_var %in% colnames(batch_assignment)) {
    stop(paste0("Condition variable '", condition_var, "' not found in data"))
  }

  if (!batch_var %in% colnames(batch_assignment)) {
    stop(paste0("Batch variable '", batch_var, "' not found in data"))
  }

  # Create contingency table
  cont_table <- table(batch_assignment[[batch_var]], batch_assignment[[condition_var]])

  # Choose test based on expected cell counts
  # Chi-square approximation unreliable when expected counts < 5
  expected_counts <- suppressWarnings(chisq.test(cont_table))$expected
  use_fisher <- any(expected_counts < 5)

  if (use_fisher) {
    test_result <- fisher.test(cont_table,
      simulate.p.value = (nrow(cont_table) > 2 || ncol(cont_table) > 2))
    test_name <- "Fisher's exact test"
    p_value <- test_result$p.value
  } else {
    test_result <- chisq.test(cont_table)
    test_name <- "Chi-square test"
    p_value <- test_result$p.value
  }

  # Interpretation
  is_confounded <- p_value < 0.05

  if (is_confounded) {
    result_message <- paste0(
      "WARNING: Batch is CONFOUNDED with ", condition_var, "!\n",
      test_name, " p-value: ", format(p_value, digits = 4), " < 0.05\n",
      "This design will not allow separation of batch effects from biological effects.\n",
      "RECOMMENDATION: Regenerate batch assignment."
    )
    status <- "FAILED"
  } else {
    result_message <- paste0(
      "PASS: No confounding detected between batch and ", condition_var, "\n",
      test_name, " p-value: ", format(p_value, digits = 4), " > 0.05\n",
      "Batch effects can be separated from biological effects."
    )
    status <- "PASSED"
  }

  if (use_fisher) {
    result_message <- paste0(result_message,
      "\n  (Fisher's exact test used: some expected cell counts < 5)")
  }

  result <- list(
    status = status,
    is_confounded = is_confounded,
    p_value = p_value,
    contingency_table = cont_table,
    message = result_message,
    test_name = test_name,
    test = test_result
  )

  # Print message
  cat(result_message, "\n")

  return(result)
}


#' Check balance of covariates across batches
#'
#' @param batch_assignment Data frame with batch assignments
#' @param covariates Vector of covariate column names to check
#' @param batch_var Name of batch variable column (default: "batch")
#' @return Data frame with balance statistics for each covariate
#' @export
#' @examples
#' # Check balance of sex and age across batches
#' # balance_check <- check_balance(batch_design, c("sex", "age_group"))
check_balance <- function(batch_assignment,
                         covariates,
                         batch_var = "batch") {

  if (!batch_var %in% colnames(batch_assignment)) {
    stop(paste0("Batch variable '", batch_var, "' not found in data"))
  }

  missing_covars <- covariates[!covariates %in% colnames(batch_assignment)]
  if (length(missing_covars) > 0) {
    stop(paste0("Covariates not found: ", paste(missing_covars, collapse = ", ")))
  }

  # Check balance for each covariate
  balance_results <- data.frame(
    covariate = character(),
    test_used = character(),
    p_value = numeric(),
    is_balanced = logical(),
    interpretation = character(),
    stringsAsFactors = FALSE
  )

  for (covar in covariates) {
    # Create contingency table
    cont_table <- table(batch_assignment[[batch_var]], batch_assignment[[covar]])

    # Choose appropriate test based on expected cell counts
    expected_counts <- suppressWarnings(chisq.test(cont_table))$expected
    use_fisher <- any(expected_counts < 5)

    if (use_fisher) {
      test_result <- fisher.test(cont_table,
        simulate.p.value = (nrow(cont_table) > 2 || ncol(cont_table) > 2))
      test_name <- "Fisher's exact"
      p_val <- test_result$p.value
    } else {
      test_result <- chisq.test(cont_table)
      test_name <- "Chi-square"
      p_val <- test_result$p.value
    }

    # Interpret balance (less stringent than confounding check)
    is_balanced <- p_val > 0.05

    if (is_balanced) {
      interpretation <- "Well balanced"
    } else if (p_val > 0.01) {
      interpretation <- "Moderately balanced"
    } else {
      interpretation <- "Poorly balanced - consider regenerating"
    }

    balance_results <- rbind(balance_results, data.frame(
      covariate = covar,
      test_used = test_name,
      p_value = p_val,
      is_balanced = is_balanced,
      interpretation = interpretation,
      stringsAsFactors = FALSE
    ))
  }

  # Print summary
  cat("\nCovariate Balance Summary:\n")
  cat("==========================\n")
  for (i in 1:nrow(balance_results)) {
    cat(sprintf("%s: %s (p = %.4f, %s)\n",
                balance_results$covariate[i],
                balance_results$interpretation[i],
                balance_results$p_value[i],
                balance_results$test_used[i]))
  }

  return(balance_results)
}


#' Visualize batch design
#'
#' @param batch_assignment Data frame with batch assignments
#' @param condition_var Name of condition variable
#' @param batch_var Name of batch variable (default: "batch")
#' @param output_file Output file path (default: NULL, displays plot)
#' @export
visualize_batch_design <- function(batch_assignment,
                                   condition_var,
                                   batch_var = "batch",
                                   output_file = NULL) {

  if (!requireNamespace("ggplot2", quietly = TRUE) || !requireNamespace("ggprism", quietly = TRUE)) {
    stop("Packages 'ggplot2' and 'ggprism' are required for visualization.")
  }

  # Create summary table
  summary_table <- as.data.frame(table(
    Batch = batch_assignment[[batch_var]],
    Condition = batch_assignment[[condition_var]]
  ))

  # Create plot
  p <- ggplot2::ggplot(summary_table, ggplot2::aes(x = Batch, y = Freq, fill = Condition)) +
    ggplot2::geom_bar(stat = "identity", position = "dodge") +
    ggprism::theme_prism() +
    ggplot2::labs(
      title = "Batch Design: Samples per Batch by Condition",
      x = "Batch",
      y = "Number of Samples",
      fill = "Condition"
    ) +
    ggplot2::theme(
      legend.position = "right",
      plot.title = ggplot2::element_text(hjust = 0.5, face = "bold")
    )

  # Save or display
  if (!is.null(output_file)) {
    message("Saving batch design plots:")
    .save_plot(p, output_file, width = 8, height = 6, dpi = 300)
  } else {
    print(p)
  }

  return(p)
}


#' Check if covariates are confounded with condition (not batch)
#'
#' Batch balancing cannot fix covariate-condition confounds. If sex is imbalanced
#' across conditions (e.g., more females in treated), this must be addressed in the
#' DE model, not the batch design.
#'
#' @param metadata Data frame with sample metadata
#' @param condition_var Name of condition variable column
#' @param covariates Vector of covariate column names to check
#' @return Data frame with test results for each covariate
#' @export
check_covariate_condition_balance <- function(metadata,
                                               condition_var,
                                               covariates) {

  if (!condition_var %in% colnames(metadata)) {
    stop(paste0("Condition variable '", condition_var, "' not found in data"))
  }

  missing_covars <- covariates[!covariates %in% colnames(metadata)]
  if (length(missing_covars) > 0) {
    stop(paste0("Covariates not found: ", paste(missing_covars, collapse = ", ")))
  }

  results <- data.frame(
    covariate = character(),
    test_used = character(),
    p_value = numeric(),
    is_balanced = logical(),
    interpretation = character(),
    stringsAsFactors = FALSE
  )

  for (covar in covariates) {
    cont_table <- table(metadata[[condition_var]], metadata[[covar]])
    expected_counts <- suppressWarnings(chisq.test(cont_table))$expected
    use_fisher <- any(expected_counts < 5)

    if (use_fisher) {
      test_result <- fisher.test(cont_table,
        simulate.p.value = (nrow(cont_table) > 2 || ncol(cont_table) > 2))
      test_name <- "Fisher's exact"
      p_val <- test_result$p.value
    } else {
      test_result <- chisq.test(cont_table)
      test_name <- "Chi-square"
      p_val <- test_result$p.value
    }

    is_balanced <- p_val > 0.05

    if (is_balanced) {
      interpretation <- "Balanced across conditions"
    } else {
      interpretation <- "CONFOUNDED with condition - include in DE model"
    }

    results <- rbind(results, data.frame(
      covariate = covar,
      test_used = test_name,
      p_value = p_val,
      is_balanced = is_balanced,
      interpretation = interpretation,
      stringsAsFactors = FALSE
    ))
  }

  # Print summary
  cat("\nCovariate-Condition Balance:\n")
  cat("============================\n")
  any_confounded <- FALSE
  for (i in 1:nrow(results)) {
    status <- if (results$is_balanced[i]) "\u2713" else "\u26a0\ufe0f"
    cat(sprintf("%s %s: %s (p = %.4f, %s)\n",
                status,
                results$covariate[i],
                results$interpretation[i],
                results$p_value[i],
                results$test_used[i]))
    if (!results$is_balanced[i]) any_confounded <- TRUE
  }

  if (any_confounded) {
    confounded <- results$covariate[!results$is_balanced]
    cat("\n\u26a0\ufe0f  WARNING: ", paste(confounded, collapse = ", "),
        " confounded with condition.\n", sep = "")
    cat("  Batch balancing CANNOT fix this. You must either:\n")
    cat("  1. Balance covariates within each condition group, OR\n")
    cat("  2. Include confounded covariates in the DE model (e.g., ~ ", paste(confounded, collapse = " + "), " + condition)\n", sep = "")
  }

  return(results)
}


#' Generate comprehensive batch validation report
#'
#' @param batch_assignment Data frame with batch assignments
#' @param condition_var Name of condition variable
#' @param covariates Vector of covariate names (optional)
#' @param output_file Optional file to save report (markdown format)
#' @return List with all validation results
#' @export
generate_batch_report <- function(batch_assignment,
                                  condition_var,
                                  covariates = NULL,
                                  output_file = NULL) {

  report <- list()

  # 1. Confounding check (CRITICAL)
  cat("\n=== CRITICAL: Confounding Check ===\n")
  report$confounding <- check_confounding(batch_assignment, condition_var)

  # 2. Covariate-condition confound check (IMPORTANT)
  if (!is.null(covariates)) {
    cat("\n\n=== Covariate-Condition Confound Check ===\n")
    report$covariate_condition <- check_covariate_condition_balance(
      batch_assignment, condition_var, covariates)
  }

  # 3. Covariate-batch balance checks
  if (!is.null(covariates)) {
    cat("\n\n=== Covariate-Batch Balance Checks ===\n")
    report$balance <- check_balance(batch_assignment, covariates)
  }

  # 4. Sample size summary
  cat("\n\n=== Sample Size Summary ===\n")
  report$sample_summary <- as.data.frame(table(
    Batch = batch_assignment$batch,
    Condition = batch_assignment[[condition_var]]
  ))
  print(report$sample_summary)

  # 5. Overall summary
  cat("\n\n=== Overall Assessment ===\n")
  if (report$confounding$status == "PASSED") {
    cat("\u2713 PASS: No batch-condition confounding detected\n")

    if (!is.null(covariates)) {
      # Check covariate-condition confounds
      if (!is.null(report$covariate_condition)) {
        cond_confounded <- report$covariate_condition$covariate[!report$covariate_condition$is_balanced]
        if (length(cond_confounded) > 0) {
          cat("\u26a0\ufe0f  WARNING: ", paste(cond_confounded, collapse = ", "),
              " confounded with condition — include in DE model\n", sep = "")
        }
      }

      # Check covariate-batch balance
      all_balanced <- all(report$balance$is_balanced)
      if (all_balanced) {
        cat("\u2713 All covariates well balanced across batches\n")
      } else {
        poorly_balanced <- report$balance$covariate[!report$balance$is_balanced]
        cat("\u26a0 Some covariates poorly balanced across batches:", paste(poorly_balanced, collapse = ", "), "\n")
        cat("  Consider: (1) regenerating assignment, or (2) including as covariates in analysis\n")
      }
    }
  } else {
    cat("\u2717 FAIL: Design has batch-condition confounding - DO NOT USE\n")
    cat("  MUST regenerate batch assignment\n")
  }

  # Save report if requested
  if (!is.null(output_file)) {
    sink(output_file)
    cat("# Batch Design Validation Report\n\n")
    cat("Generated:", format(Sys.time(), "%Y-%m-%d %H:%M:%S"), "\n\n")
    cat("## Confounding Check\n")
    cat(report$confounding$message, "\n\n")
    if (!is.null(covariates)) {
      cat("## Covariate Balance\n")
      print(report$balance)
    }
    sink()
    message(paste0("Report saved to: ", output_file))
  }

  return(report)
}


#' Check for recommended metadata to record
#'
#' @param batch_assignment Data frame with batch assignments
#' @return List of recommended metadata fields and which are present
#' @export
check_metadata_completeness <- function(batch_assignment) {

  # Recommended metadata fields to always record
  recommended_fields <- c(
    "sample_id",
    "batch",
    "processing_date",
    "operator",
    "reagent_lot",
    "instrument",
    "plate",
    "well",
    "library_prep_batch",
    "sequencing_run",
    "flowcell"
  )

  # Check which are present
  present_fields <- recommended_fields[recommended_fields %in% colnames(batch_assignment)]
  missing_fields <- recommended_fields[!recommended_fields %in% colnames(batch_assignment)]

  cat("\n=== Metadata Completeness Check ===\n")
  cat("Present fields (", length(present_fields), "/", length(recommended_fields), "):\n", sep = "")
  cat("  ", paste(present_fields, collapse = ", "), "\n\n")

  if (length(missing_fields) > 0) {
    cat("Missing recommended fields:\n")
    cat("  ", paste(missing_fields, collapse = ", "), "\n\n")
    cat("RECOMMENDATION: Record these fields during sample processing\n")
    cat("They are essential for:\n")
    cat("  1. Diagnosing batch effects if detected\n")
    cat("  2. Batch effect correction (SVA, ComBat)\n")
    cat("  3. Reproducibility and troubleshooting\n")
  } else {
    cat("✓ All recommended metadata fields present\n")
  }

  result <- list(
    present = present_fields,
    missing = missing_fields,
    completeness = length(present_fields) / length(recommended_fields)
  )

  return(result)
}
