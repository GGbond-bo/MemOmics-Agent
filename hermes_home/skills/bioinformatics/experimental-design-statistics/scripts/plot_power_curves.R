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
# Power and Sample Size Visualization Functions
# Create publication-quality plots using ggplot2 + ggprism

# Prevent Rplots.pdf creation in non-interactive/container environments
if (!interactive() && is.null(grDevices::dev.list())) {
  grDevices::pdf(NULL)
}

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

#' Plot power vs. sample size for different fold-changes
#'
#' @param cv Coefficient of variation
#' @param fold_changes Vector of fold-changes to plot
#' @param depth Sequencing depth in millions
#' @param alpha Significance threshold
#' @param max_n Maximum sample size for x-axis (NULL = auto-detect from smallest FC reaching 90% power)
#' @param output_file Output file path (SVG format)
#' @export
plot_power_vs_samplesize <- function(cv = 0.4,
                                     fold_changes = c(1.5, 2, 3, 4),
                                     depth = 20,
                                     alpha = 0.05,
                                     max_n = NULL,
                                     output_file = "power_vs_samplesize.svg") {

  if (!requireNamespace("ggplot2", quietly = TRUE) || !requireNamespace("ggprism", quietly = TRUE)) {
    stop("Packages 'ggplot2' and 'ggprism' are required.")
  }

  if (!requireNamespace("RNASeqPower", quietly = TRUE)) {
    stop("Package 'RNASeqPower' is required.")
  }

  # Auto-detect max_n if not specified: find where smallest FC reaches 90% power
  if (is.null(max_n)) {
    min_fc <- min(fold_changes)
    # Find n where power >= 0.90 for the smallest fold change
    for (test_n in 2:100) {
      pwr <- RNASeqPower::rnapower(depth = depth, n = test_n, cv = cv, effect = min_fc, alpha = alpha)
      if (pwr >= 0.90) {
        max_n <- min(max(test_n + 5, 15), 50)  # Add padding, min 15, cap at 50
        break
      }
    }
    if (is.null(max_n)) max_n <- 50  # Cap if 90% never reached
  }

  # Generate data for plot
  n_range <- 2:max_n
  plot_data <- data.frame()

  for (fc in fold_changes) {
    for (n in n_range) {
      power <- RNASeqPower::rnapower(
        depth = depth,
        n = n,
        cv = cv,
        effect = fc,
        alpha = alpha
      )

      plot_data <- rbind(plot_data, data.frame(
        n_per_group = n,
        power = power,
        fold_change = paste0(fc, "-fold"),
        fc_numeric = fc
      ))
    }
  }

  # Convert fold_change to factor with proper ordering
  plot_data$fold_change <- factor(plot_data$fold_change,
                                   levels = paste0(sort(fold_changes), "-fold"))

  # Create plot
  p <- ggplot2::ggplot(plot_data, ggplot2::aes(x = n_per_group, y = power, color = fold_change)) +
    ggplot2::geom_line(linewidth = 1.2) +
    ggplot2::geom_point(size = 2) +
    ggplot2::geom_hline(yintercept = 0.8, linetype = "dashed", color = "gray40", linewidth = 0.5) +
    ggplot2::annotate("text", x = max_n - 1, y = 0.82, label = "80% power", color = "gray40", size = 3, hjust = 1) +
    ggplot2::geom_hline(yintercept = 0.9, linetype = "dotted", color = "gray60", linewidth = 0.5) +
    ggplot2::annotate("text", x = max_n - 1, y = 0.92, label = "90% power", color = "gray60", size = 3, hjust = 1) +
    ggprism::theme_prism() +
    ggplot2::scale_color_manual(values = c("#E64B35FF", "#4DBBD5FF", "#00A087FF", "#3C5488FF")) +
    ggplot2::labs(
      title = "Statistical Power vs. Sample Size",
      subtitle = paste0("CV = ", cv, ", Depth = ", depth, "M reads, alpha = ", alpha),
      x = "Replicates per Group",
      y = "Statistical Power",
      color = "Effect Size"
    ) +
    ggplot2::theme(
      plot.title = ggplot2::element_text(hjust = 0.5, face = "bold", size = 14),
      plot.subtitle = ggplot2::element_text(hjust = 0.5, size = 10),
      legend.position = "right"
    ) +
    ggplot2::scale_x_continuous(breaks = seq(2, max_n, by = max(1, round(max_n / 10)))) +
    ggplot2::scale_y_continuous(limits = c(0, 1), breaks = seq(0, 1, 0.2))

  # Save plot in both PNG and SVG formats
  message("Saving power curve plots:")
  .save_plot(p, output_file, width = 8, height = 6, dpi = 300)

  return(p)
}


#' Plot power vs. fold-change for different sample sizes
#'
#' @param n_per_group Vector of sample sizes to plot
#' @param cv Coefficient of variation
#' @param depth Sequencing depth in millions
#' @param alpha Significance threshold
#' @param output_file Output file path
#' @export
plot_power_vs_foldchange <- function(n_per_group = c(3, 5, 8, 10),
                                     cv = 0.4,
                                     depth = 20,
                                     alpha = 0.05,
                                     output_file = "power_vs_foldchange.svg") {

  if (!requireNamespace("ggplot2", quietly = TRUE) || !requireNamespace("ggprism", quietly = TRUE)) {
    stop("Packages 'ggplot2' and 'ggprism' are required.")
  }

  if (!requireNamespace("RNASeqPower", quietly = TRUE)) {
    stop("Package 'RNASeqPower' is required.")
  }

  # Generate data
  fc_range <- seq(1.25, 4, by = 0.25)
  plot_data <- data.frame()

  for (n in n_per_group) {
    for (fc in fc_range) {
      power <- RNASeqPower::rnapower(
        depth = depth,
        n = n,
        cv = cv,
        effect = fc,
        alpha = alpha
      )

      plot_data <- rbind(plot_data, data.frame(
        fold_change = fc,
        power = power,
        n_label = paste0("n = ", n),
        n_numeric = n
      ))
    }
  }

  # Convert to factor
  plot_data$n_label <- factor(plot_data$n_label,
                               levels = paste0("n = ", sort(n_per_group)))

  # Create plot
  p <- ggplot2::ggplot(plot_data, ggplot2::aes(x = fold_change, y = power, color = n_label)) +
    ggplot2::geom_line(linewidth = 1.2) +
    ggplot2::geom_point(size = 2) +
    ggplot2::geom_hline(yintercept = 0.8, linetype = "dashed", color = "gray40", linewidth = 0.5) +
    ggplot2::annotate("text", x = max(fc_range) - 0.3, y = 0.82, label = "80% power", color = "gray40", size = 3) +
    ggplot2::geom_hline(yintercept = 0.9, linetype = "dotted", color = "gray60", linewidth = 0.5) +
    ggplot2::annotate("text", x = max(fc_range) - 0.3, y = 0.92, label = "90% power", color = "gray60", size = 3) +
    ggprism::theme_prism() +
    ggplot2::scale_color_manual(values = c("#E64B35FF", "#4DBBD5FF", "#00A087FF", "#3C5488FF")) +
    ggplot2::labs(
      title = "Statistical Power vs. Fold-Change",
      subtitle = paste0("CV = ", cv, ", Depth = ", depth, "M reads, alpha = ", alpha),
      x = "Fold-Change Threshold",
      y = "Statistical Power",
      color = "Sample Size"
    ) +
    ggplot2::theme(
      plot.title = ggplot2::element_text(hjust = 0.5, face = "bold", size = 14),
      plot.subtitle = ggplot2::element_text(hjust = 0.5, size = 10),
      legend.position = "right"
    ) +
    ggplot2::scale_y_continuous(limits = c(0, 1), breaks = seq(0, 1, 0.2))

  # Save plot in both PNG and SVG formats
  message("Saving power vs fold-change plots:")
  .save_plot(p, output_file, width = 8, height = 6, dpi = 300)

  return(p)
}


#' Plot CV estimates by tissue type (reference visualization)
#'
#' @param cv_database_path Path to CV database CSV
#' @param output_file Output file path
#' @export
plot_cv_by_tissue <- function(cv_database_path = "references/cv_tissue_database.csv",
                              output_file = "cv_by_tissue.svg") {

  if (!requireNamespace("ggplot2", quietly = TRUE) || !requireNamespace("ggprism", quietly = TRUE)) {
    stop("Packages 'ggplot2' and 'ggprism' are required.")
  }

  # Check if database exists
  if (!file.exists(cv_database_path)) {
    message("CV database not found. Creating example plot with typical values.")

    # Create example data
    cv_data <- data.frame(
      Tissue = c("Cell lines", "Inbred mice", "Primary cells", "Human samples"),
      CV_min = c(0.1, 0.2, 0.3, 0.3),
      CV_max = c(0.2, 0.3, 0.4, 0.5),
      CV_typical = c(0.15, 0.25, 0.35, 0.4)
    )

  } else {
    # Load database
    cv_data <- read.csv(cv_database_path)

    # Aggregate by tissue type
    cv_data <- aggregate(CV ~ Tissue, data = cv_data, FUN = function(x) {
      c(min = min(x), max = max(x), typical = median(x))
    })

    cv_data <- data.frame(
      Tissue = cv_data$Tissue,
      CV_min = cv_data$CV[, "min"],
      CV_max = cv_data$CV[, "max"],
      CV_typical = cv_data$CV[, "typical"]
    )
  }

  # Create plot
  p <- ggplot2::ggplot(cv_data, ggplot2::aes(x = Tissue, y = CV_typical)) +
    ggplot2::geom_point(size = 4, color = "#4DBBD5FF") +
    ggplot2::geom_errorbar(ggplot2::aes(ymin = CV_min, ymax = CV_max),
                           width = 0.2, size = 1, color = "#4DBBD5FF") +
    ggprism::theme_prism() +
    ggplot2::labs(
      title = "Coefficient of Variation by Tissue Type",
      subtitle = "Typical ranges for RNA-seq experiments",
      x = "Tissue/Sample Type",
      y = "Coefficient of Variation (CV)",
      caption = "Points show typical CV, error bars show range"
    ) +
    ggplot2::theme(
      plot.title = ggplot2::element_text(hjust = 0.5, face = "bold", size = 14),
      plot.subtitle = ggplot2::element_text(hjust = 0.5, size = 10),
      axis.text.x = ggplot2::element_text(angle = 45, hjust = 1)
    ) +
    ggplot2::scale_y_continuous(limits = c(0, 0.6), breaks = seq(0, 0.6, 0.1))

  # Save plot in both PNG and SVG formats
  message("Saving CV reference plots:")
  .save_plot(p, output_file, width = 8, height = 6, dpi = 300)

  return(p)
}


#' Plot sample size requirements for different scenarios
#'
#' @param output_file Output file path
#' @export
plot_sample_size_table <- function(output_file = "sample_size_reference.svg") {

  if (!requireNamespace("ggplot2", quietly = TRUE) || !requireNamespace("ggprism", quietly = TRUE)) {
    stop("Packages 'ggplot2' and 'ggprism' are required.")
  }

  if (!requireNamespace("RNASeqPower", quietly = TRUE)) {
    stop("Package 'RNASeqPower' is required.")
  }

  # Generate sample size matrix for different CVs and fold-changes
  cvs <- c(0.2, 0.3, 0.4, 0.5)
  fcs <- c(1.5, 2, 3, 4)

  plot_data <- expand.grid(
    CV = cvs,
    FoldChange = fcs
  )

  plot_data$SampleSize <- apply(plot_data, 1, function(row) {
    ceiling(RNASeqPower::rnapower(
      depth = 20,
      cv = row["CV"],
      effect = row["FoldChange"],
      alpha = 0.05,
      power = 0.8
    ))
  })

  # Create heatmap
  p <- ggplot2::ggplot(plot_data, ggplot2::aes(x = factor(FoldChange), y = factor(CV), fill = SampleSize)) +
    ggplot2::geom_tile(color = "white", linewidth = 1) +
    ggplot2::geom_text(ggplot2::aes(label = SampleSize), size = 5, fontface = "bold") +
    ggplot2::scale_fill_gradient(low = "#00A087FF", high = "#E64B35FF", name = "n per\ngroup") +
    ggprism::theme_prism() +
    ggplot2::labs(
      title = "Required Sample Size for 80% Power",
      subtitle = "Depth = 20M reads, alpha = 0.05",
      x = "Fold-Change to Detect",
      y = "Coefficient of Variation (CV)"
    ) +
    ggplot2::theme(
      plot.title = ggplot2::element_text(hjust = 0.5, face = "bold", size = 14),
      plot.subtitle = ggplot2::element_text(hjust = 0.5, size = 10),
      axis.title = ggplot2::element_text(face = "bold")
    )

  # Save plot in both PNG and SVG formats
  message("Saving sample size reference plots:")
  .save_plot(p, output_file, width = 8, height = 6, dpi = 300)

  return(p)
}
