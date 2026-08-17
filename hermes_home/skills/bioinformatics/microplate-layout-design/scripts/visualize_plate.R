
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
#      ★ 强制审查项（任一不通过则重新执行）:
#        a. 图片是否生成？无图 → 重新执行
#        b. 图片是否空白（全白/全黑/全单一色）？空白 → 强制重新出图
#        c. 图片是否有 NA/缺失值（>10%像素是NA）？有NA → 强制重新出图
#        d. 图片大小是否过小（<5KB）？过小 → 强制重新出图
#        e. 图片数量是否足够？（每步至少1张图，关键步骤至少2-3张）
#        f. 代码行数是否合理？是否分段执行（禁止&&连接）？
#        g. 数值范围是否合理？跟知识库对应吗？
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
# ★ 参数和结论辩论铁律:
#   - 有参数选择 → 必须调 debate_analysis 辩论
#   - 有结论输出 → 必须调 debate_analysis 辩论
#   - 辩论格式：正方(支持) vs 反方(质疑+替代) → 裁判决断
#   - 最多3轮，3轮后选最优结果
#
# 日志存储: skill 目录下 .run_logs/ 目录，按 物种_组织_方向_日期 命名
# ============================================================

# ============================================================
# 🔒 MemOmics 审查铁律 — 执行本脚本前后的强制步骤
# ============================================================
# 执行前必须: rail_review(action="pre")  — 环境检查 + 参数校验 + 代码审查
# 执行后必须: rail_review(action="post") — 结果质量评估 + 图表检查 + 数值检查
#   ★ 强制: 图片空白/NA/过小 → 重新出图 | 图片不够 → 补图 | 代码未分段 → 重写
#   ★ 强制: 有参数有结论 → debate_analysis 辩论
# 参数有争议: debate_analysis(topic=..., context=...) — 多角色辩论
# 执行失败:   skill_evolution(action="record_error") — 记录错误
# 修复成功:   skill_evolution(action="update_script") — 替换脚本
# ============================================================


# =============================================================================
# Microplate Layout Design - Plate Visualization
# =============================================================================
# Generates publication-quality plate map visualizations using ggplate
# with platetools/ggplot2 fallback.
# =============================================================================

suppressPackageStartupMessages({
    library(ggplot2)
    library(ggprism)
    library(ggplate)
})

# Prevent R from opening default PDF device (causes crashes in non-interactive sessions)
if (!interactive()) pdf(NULL)

# --- SVG support check ---
.has_svglite <- requireNamespace("svglite", quietly = TRUE)
if (.has_svglite) suppressPackageStartupMessages(library(svglite))

# --- Save plot helper (PNG + SVG with fallback) ---
.save_plot <- function(plot, base_path, width = 10, height = 6, dpi = 300) {
    png_path <- sub("\\.(svg|png)$", ".png", base_path)
    if (!grepl("\\.png$", png_path)) png_path <- paste0(base_path, ".png")

    ggsave(png_path, plot = plot, width = width, height = height, dpi = dpi, device = "png")
    cat("   Saved:", png_path, "\n")

    svg_path <- sub("\\.png$", ".svg", png_path)
    tryCatch({
        ggsave(svg_path, plot = plot, width = width, height = height, device = "svg")
        cat("   Saved:", svg_path, "\n")
    }, error = function(e) {
        tryCatch({
            svg(svg_path, width = width, height = height)
            print(plot)
            dev.off()
            cat("   Saved:", svg_path, "\n")
        }, error = function(e2) {
            cat("   (SVG export failed)\n")
        })
    })
}

# --- Main visualization function ---
visualize_all_plates <- function(layout, output_dir = "layout_results") {
    if (!inherits(layout, "plate_layout")) {
        stop("Input must be a 'plate_layout' object from generate_plate_layout()")
    }

    dir.create(output_dir, showWarnings = FALSE, recursive = TRUE)
    cat("\n=== Generating Plate Visualizations ===\n")
    cat("Output directory:", output_dir, "\n\n")

    plate_data <- layout$plate_data
    experiment <- layout$experiment
    is_multi <- experiment$n_plates > 1

    # For multi-plate: use wider combined plots
    combined_width <- if (is_multi)
        .plot_width(experiment) + (experiment$n_plates - 1) * 5
    else
        .plot_width(experiment)

    # 1. Treatment map
    cat("1. Treatment map...\n")
    p1 <- .plot_plate_map(plate_data, experiment, fill_var = "treatment",
                          title = paste(experiment$name, "- Treatment Layout"))
    .save_plot(p1, file.path(output_dir, "plate_treatment_map.png"),
               width = combined_width, height = .plot_height(experiment))
    if (is_multi) .save_per_plate_plots(plate_data, experiment, "treatment",
                                         "Treatment Layout", "plate_treatment_map", output_dir)

    # 2. Sample type map (samples, controls, empty)
    cat("2. Sample type map...\n")
    p2 <- .plot_plate_map(plate_data, experiment, fill_var = "sample_type",
                          title = paste(experiment$name, "- Sample Types"))
    .save_plot(p2, file.path(output_dir, "plate_sample_type_map.png"),
               width = combined_width, height = .plot_height(experiment))
    if (is_multi) .save_per_plate_plots(plate_data, experiment, "sample_type",
                                         "Sample Types", "plate_sample_type_map", output_dir)

    # 3. Replicate map
    cat("3. Replicate distribution map...\n")
    p3 <- .plot_plate_map(plate_data, experiment, fill_var = "replicate",
                          title = paste(experiment$name, "- Replicate Distribution"))
    .save_plot(p3, file.path(output_dir, "plate_replicate_map.png"),
               width = combined_width, height = .plot_height(experiment))
    if (is_multi) .save_per_plate_plots(plate_data, experiment, "replicate",
                                         "Replicate Distribution", "plate_replicate_map", output_dir)

    # 4. Edge effect risk map
    cat("4. Edge effect risk map...\n")
    p4 <- .plot_edge_risk(plate_data, experiment)
    .save_plot(p4, file.path(output_dir, "plate_edge_risk.png"),
               width = combined_width, height = .plot_height(experiment))
    if (is_multi) {
        for (plate_num in 1:experiment$n_plates) {
            plate_subset <- plate_data[plate_data$plate == plate_num, ]
            single_exp <- .single_plate_experiment(experiment)
            p_plate <- .plot_edge_risk(plate_subset, single_exp)
            fname <- paste0("plate_edge_risk_plate", plate_num, ".png")
            .save_plot(p_plate, file.path(output_dir, fname),
                       width = .plot_width(experiment), height = .plot_height(experiment))
            cat("   Per-plate:", fname, "\n")
        }
    }

    # 5. Quality dashboard
    cat("5. Quality dashboard...\n")
    p5 <- .plot_quality_dashboard(layout)
    .save_plot(p5, file.path(output_dir, "plate_quality_dashboard.png"),
               width = 12, height = 8)

    cat("\n\u2713 All plots generated successfully!\n")
    cat("  Files saved to:", output_dir, "\n")

    invisible(list(treatment_map = p1, sample_type_map = p2,
                   replicate_map = p3, edge_risk = p4, dashboard = p5))
}

# --- Helper: create single-plate experiment copy for per-plate rendering ---
.single_plate_experiment <- function(experiment) {
    single_exp <- experiment
    single_exp$n_plates <- 1
    single_exp
}

# --- Helper: generate per-plate plots using ggplate (high quality) ---
.save_per_plate_plots <- function(plate_data, experiment, fill_var, subtitle, base_name, output_dir) {
    single_exp <- .single_plate_experiment(experiment)
    for (plate_num in 1:experiment$n_plates) {
        plate_subset <- plate_data[plate_data$plate == plate_num, ]
        title <- paste(experiment$name, "-", subtitle, "(Plate", plate_num, ")")
        p_plate <- .plot_plate_map(plate_subset, single_exp, fill_var = fill_var, title = title)
        fname <- paste0(base_name, "_plate", plate_num, ".png")
        .save_plot(p_plate, file.path(output_dir, fname),
                   width = .plot_width(experiment), height = .plot_height(experiment))
        cat("   Per-plate:", fname, "\n")
    }
}

# --- Plot dimensions based on plate format ---
.plot_width <- function(experiment) {
    if (experiment$plate_format == 384) 14 else 10
}
.plot_height <- function(experiment) {
    if (experiment$plate_format == 384) 10 else 6
}

# --- Core plate map using ggplot2 grid ---
.plot_plate_map <- function(plate_data, experiment, fill_var = "treatment",
                            title = "Plate Layout") {
    dims <- experiment$plate_dims
    df <- plate_data

    # Create display label
    df$display <- ifelse(is.na(df[[fill_var]]),
                         ifelse(df$well_role == "empty", "", ""),
                         as.character(df[[fill_var]]))

    # Use ggplate for single-plate data (required package)
    # Multi-plate combined views use ggplot2 grid (ggplate doesn't support faceting)
    if (fill_var %in% c("treatment", "sample_type", "replicate") &&
        length(unique(df$plate)) == 1) {
        plot_df <- df[!is.na(df[[fill_var]]), ]
        if (nrow(plot_df) > 0) {
            p <- tryCatch({
                ggplate::plate_plot(
                    data = plot_df,
                    position = well,
                    value = !!rlang::sym(fill_var),
                    plate_size = experiment$plate_format,
                    plate_type = "round",
                    title = title,
                    label = well,
                    label_size = if (experiment$plate_format == 384) 1.5 else 2.5,
                    silent = TRUE
                ) + theme_prism(base_size = 12) +
                    theme(plot.title = element_text(size = 14, face = "bold", hjust = 0.5))
            }, error = function(e) {
                warning("ggplate::plate_plot() failed: ", conditionMessage(e),
                        "\n  Falling back to ggplot2 grid for this plot.")
                NULL
            })
            if (!is.null(p)) return(p)
        }
    }

    # Fallback: ggplot2 grid for multi-plate combined views or ggplate errors
    .plot_plate_grid(df, dims, fill_var, title, experiment)
}

# --- ggplot2 grid fallback ---
.plot_plate_grid <- function(df, dims, fill_var, title, experiment) {
    # Create a fill column that handles NAs gracefully
    df$fill_value <- as.character(df[[fill_var]])
    df$fill_value[is.na(df$fill_value)] <- ifelse(
        df$well_role[is.na(df$fill_value)] == "empty", "Empty", "Unassigned"
    )

    # Reverse row order so A is on top
    df$row_rev <- max(df$row) - df$row + 1

    # Add well labels
    df$well_label <- ifelse(df$fill_value %in% c("Empty", "Unassigned"), "",
                            substr(df$fill_value, 1, 6))

    p <- ggplot(df, aes(x = col, y = row_rev)) +
        geom_point(aes(fill = fill_value), shape = 21, size = .well_size(experiment),
                   stroke = 0.3, color = "grey30") +
        scale_x_continuous(breaks = 1:dims$cols, labels = dims$col_labels,
                           position = "top", expand = expansion(mult = 0.05)) +
        scale_y_continuous(breaks = 1:dims$rows, labels = rev(dims$row_labels),
                           expand = expansion(mult = 0.05)) +
        labs(title = title, fill = fill_var, x = NULL, y = NULL) +
        theme_prism(base_size = 12) +
        theme(
            plot.title = element_text(size = 14, face = "bold", hjust = 0.5),
            axis.text = element_text(face = "bold"),
            legend.position = "right"
        ) +
        coord_fixed(ratio = 1)

    # Add well labels for 96-well plates
    if (experiment$plate_format <= 96) {
        p <- p + geom_text(aes(label = well_label), size = 2, color = "grey20")
    }

    # Facet by plate if multi-plate
    if (experiment$n_plates > 1) {
        p <- p + facet_wrap(~plate, labeller = labeller(plate = function(x) paste("Plate", x)))
    }

    return(p)
}

# --- Well size based on plate format ---
.well_size <- function(experiment) {
    switch(as.character(experiment$plate_format),
        "96" = 8,
        "384" = 4,
        6
    )
}

# --- Edge effect risk heatmap ---
.plot_edge_risk <- function(plate_data, experiment) {
    dims <- experiment$plate_dims
    df <- plate_data

    # Calculate edge risk: distance from nearest edge (normalized 0-1)
    df$edge_distance <- pmin(
        df$row - 1, dims$rows - df$row,
        df$col - 1, dims$cols - df$col
    )
    max_dist <- min(floor(dims$rows / 2), floor(dims$cols / 2))
    df$edge_risk <- 1 - (df$edge_distance / max_dist)

    df$row_rev <- max(df$row) - df$row + 1

    # Overlay what's in each well
    df$content <- ifelse(is.na(df$sample_type), df$well_role,
                         df$sample_type)

    p <- ggplot(df, aes(x = col, y = row_rev)) +
        geom_tile(aes(fill = edge_risk), color = "white", linewidth = 0.5) +
        geom_text(aes(label = substr(content, 1, 4)),
                  size = if (experiment$plate_format == 384) 1.5 else 2.5,
                  color = "black", alpha = 0.7) +
        scale_fill_gradient2(low = "#2166AC", mid = "#F7F7F7", high = "#B2182B",
                             midpoint = 0.5, limits = c(0, 1),
                             name = "Edge Risk") +
        scale_x_continuous(breaks = 1:dims$cols, labels = dims$col_labels,
                           position = "top", expand = expansion(mult = 0.02)) +
        scale_y_continuous(breaks = 1:dims$rows, labels = rev(dims$row_labels),
                           expand = expansion(mult = 0.02)) +
        labs(title = paste(experiment$name, "- Edge Effect Risk Map"),
             subtitle = "Red = higher risk of edge effects | Blue = lower risk",
             x = NULL, y = NULL) +
        theme_prism(base_size = 12) +
        theme(
            plot.title = element_text(size = 14, face = "bold", hjust = 0.5),
            plot.subtitle = element_text(size = 10, hjust = 0.5, color = "grey40"),
            axis.text = element_text(face = "bold"),
            legend.position = "right"
        ) +
        coord_fixed(ratio = 1)

    if (experiment$n_plates > 1) {
        p <- p + facet_wrap(~plate, labeller = labeller(plate = function(x) paste("Plate", x)))
    }

    return(p)
}

# --- Quality dashboard ---
.plot_quality_dashboard <- function(layout) {
    quality <- layout$quality
    experiment <- layout$experiment
    plate_data <- layout$plate_data

    # Build summary data
    scores_df <- data.frame(
        metric = c("Spatial\nBalance", "Control\nDistribution", "Edge\nProtection", "Overall"),
        score = c(quality$spatial_score, quality$control_score,
                  quality$edge_score, quality$overall_score),
        stringsAsFactors = FALSE
    )
    scores_df$metric <- factor(scores_df$metric,
                               levels = c("Spatial\nBalance", "Control\nDistribution",
                                          "Edge\nProtection", "Overall"))
    scores_df$color <- ifelse(scores_df$score >= 0.8, "#2E7D32",
                              ifelse(scores_df$score >= 0.6, "#F57F17", "#C62828"))

    p_scores <- ggplot(scores_df, aes(x = metric, y = score, fill = color)) +
        geom_col(width = 0.6) +
        geom_text(aes(label = sprintf("%.0f%%", score * 100)),
                  vjust = -0.5, fontface = "bold", size = 5) +
        scale_fill_identity() +
        scale_y_continuous(limits = c(0, 1.15), labels = scales::percent_format()) +
        labs(title = "Layout Quality Scores", x = NULL, y = NULL) +
        theme_prism(base_size = 12) +
        theme(
            plot.title = element_text(size = 14, face = "bold", hjust = 0.5)
        )

    # Summary table as text
    assigned <- plate_data[!is.na(plate_data$sample_id), ]
    n_samples <- sum(assigned$sample_type == "sample", na.rm = TRUE)
    n_pos <- sum(assigned$sample_type == "positive", na.rm = TRUE)
    n_neg <- sum(assigned$sample_type == "negative", na.rm = TRUE)
    n_blank <- sum(assigned$sample_type == "blank", na.rm = TRUE)
    n_empty <- sum(plate_data$well_role == "empty")
    n_unassigned <- sum(is.na(plate_data$sample_id) & plate_data$well_role != "empty")

    total_wells <- nrow(plate_data)
    n_assigned <- n_samples + n_pos + n_neg + n_blank
    actual_util <- round(n_assigned / total_wells * 100)
    expected_util <- switch(experiment$edge_strategy,
        "controls_only" = "~62%",
        "empty" = "~62%",
        "include" = "~100%",
        "unknown"
    )

    summary_text <- paste0(
        "Experiment: ", experiment$name, "\n",
        "Plate format: ", experiment$plate_format, "-well\n",
        "Method: ", layout$method, "\n",
        "Plates: ", experiment$n_plates, "\n",
        "Edge strategy: ", experiment$edge_strategy, "\n\n",
        "Sample wells: ", n_samples, "\n",
        "Positive controls: ", n_pos, "\n",
        "Negative controls: ", n_neg, "\n",
        "Blanks: ", n_blank, "\n",
        "Empty (edge buffer): ", n_empty, "\n",
        "Unassigned interior: ", n_unassigned, "\n\n",
        "Utilization: ", actual_util, "% (", n_assigned, "/", total_wells, ")\n",
        "Expected for '", experiment$edge_strategy, "': ", expected_util
    )

    p_summary <- ggplot() +
        annotate("text", x = 0.5, y = 0.5, label = summary_text,
                 hjust = 0.5, vjust = 0.5, size = 4, family = "mono") +
        labs(title = "Layout Summary") +
        theme_prism(base_size = 12) +
        theme(
            plot.title = element_text(size = 14, face = "bold", hjust = 0.5),
            axis.line = element_blank(),
            axis.text = element_blank(),
            axis.ticks = element_blank(),
            axis.title = element_blank()
        )

    # Combine
    if (requireNamespace("patchwork", quietly = TRUE)) {
        library(patchwork)
        p <- p_scores + p_summary + plot_layout(widths = c(2, 1))
    } else {
        p <- p_scores  # Just show scores if patchwork not available
    }

    return(p)
}

cat("✓ visualize_plate.R loaded\n")
cat("  Use: visualize_all_plates(layout, output_dir = 'layout_results')\n")
