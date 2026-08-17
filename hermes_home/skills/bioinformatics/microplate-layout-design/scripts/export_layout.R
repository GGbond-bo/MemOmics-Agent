
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
# Microplate Layout Design - Export Results
# =============================================================================
# Exports plate layouts in multiple formats for lab use and downstream analysis.
# =============================================================================

suppressPackageStartupMessages({
    library(jsonlite)
})

# --- Main export function ---
export_all <- function(layout, experiment = NULL, output_dir = "layout_results") {
    if (!inherits(layout, "plate_layout")) {
        stop("Input must be a 'plate_layout' object from generate_plate_layout()")
    }

    if (is.null(experiment)) experiment <- layout$experiment
    dir.create(output_dir, showWarnings = FALSE, recursive = TRUE)

    cat("\n=== Exporting Plate Layout ===\n")
    cat("Output directory:", output_dir, "\n\n")

    plate_data <- layout$plate_data

    # FIX 4: track export status so failures surface in the return value and
    # the quality report instead of being silently swallowed.
    export_status <- list(excel = "not_attempted", warnings = character(0))

    # 1. Tidy CSV (one row per well)
    cat("1. Tidy CSV (plate_layout.csv)...\n")
    # FIX 1: include measurand + bio_sample columns when present so the tidy
    # export captures the full multi-measurand design.
    tidy_cols <- c("plate", "well", "row_label", "col_label",
                   "row", "col", "is_edge", "well_role",
                   "sample_id", "treatment", "replicate", "sample_type")
    if ("measurand" %in% colnames(plate_data)) tidy_cols <- c(tidy_cols, "measurand")
    if ("bio_sample" %in% colnames(plate_data)) tidy_cols <- c(tidy_cols, "bio_sample")
    tidy_df <- plate_data[, tidy_cols]
    write.csv(tidy_df, file.path(output_dir, "plate_layout.csv"), row.names = FALSE)
    cat("   Saved:", file.path(output_dir, "plate_layout.csv"), "\n")

    # 2. Plate-shaped grid CSV (one per plate)
    cat("2. Grid CSV (plate_layout_grid.csv)...\n")
    for (p in 1:experiment$n_plates) {
        plate_subset <- plate_data[plate_data$plate == p, ]
        dims <- experiment$plate_dims

        # Create a matrix with well contents
        grid <- matrix("", nrow = dims$rows, ncol = dims$cols)
        rownames(grid) <- dims$row_labels
        colnames(grid) <- dims$col_labels

        for (i in seq_len(nrow(plate_subset))) {
            r <- plate_subset$row[i]
            c <- plate_subset$col[i]
            content <- plate_subset$sample_id[i]
            if (is.na(content)) {
                if (plate_subset$well_role[i] == "empty") {
                    content <- "[EMPTY]"
                } else {
                    content <- ""
                }
            }
            grid[r, c] <- content
        }

        suffix <- if (experiment$n_plates > 1) paste0("_plate", p) else ""
        grid_path <- file.path(output_dir, paste0("plate_layout_grid", suffix, ".csv"))
        write.csv(grid, grid_path)
        cat("   Saved:", grid_path, "\n")
    }

    # 3. Excel with color-coded cells (if openxlsx available)
    cat("3. Excel workbook (plate_layout.xlsx)...\n")
    xlsx_path <- file.path(output_dir, "plate_layout.xlsx")
    if (requireNamespace("openxlsx", quietly = TRUE)) {
        # FIX 4: do NOT silently swallow Excel failures. .export_excel() verifies
        # the file exists and is non-empty; on failure we fall back to CSV-only
        # and RECORD the failure so it appears in export_all()'s return and the
        # quality report.
        export_status$excel <- tryCatch({
            .export_excel(layout, experiment, output_dir)
            "ok"
        }, error = function(e) {
            msg <- conditionMessage(e)
            cat("   ⚠️  Excel export FAILED:", msg, "\n")
            cat("   Falling back to CSV-only (plate_layout.csv + grid CSVs).\n")
            # Remove any truncated/partial file so .verify_outputs() is accurate.
            if (file.exists(xlsx_path) && (is.na(file.info(xlsx_path)$size) ||
                                           file.info(xlsx_path)$size <= 1000)) {
                unlink(xlsx_path)
            }
            export_status$warnings <<- c(export_status$warnings,
                                         paste("Excel export failed:", msg))
            paste0("failed: ", msg)
        })
    } else {
        cat("   (openxlsx not available - skipping Excel export; CSV exports cover this)\n")
        export_status$excel <- "skipped (openxlsx not installed)"
    }

    # 4. Layout object (RDS)
    cat("4. Layout object (layout_object.rds)...\n")
    saveRDS(layout, file.path(output_dir, "layout_object.rds"))
    cat("   Saved:", file.path(output_dir, "layout_object.rds"), "\n")
    cat("   (Load with: layout <- readRDS('layout_object.rds'))\n")

    # 5. Experiment parameters (JSON)
    cat("5. Experiment parameters (experiment_parameters.json)...\n")
    params <- list(
        experiment_name = experiment$name,
        assay_type = experiment$assay_type,
        plate_format = experiment$plate_format,
        n_plates = experiment$n_plates,
        treatments = experiment$treatments,
        n_replicates = experiment$n_replicates,
        # FIX 3: persist the DECLARED biological/technical replicate vocabulary.
        n_biological = experiment$n_biological,
        n_technical = experiment$n_technical,
        # FIX 1: persist ratiometric / measurand design fields when present.
        measurands = experiment$measurands,
        normalization = experiment$normalization,
        reference_measurands = experiment$reference_measurands,
        interplate_calibrator = experiment$interplate_calibrator,
        controls = experiment$controls,
        n_controls = experiment$n_controls,
        edge_strategy = experiment$edge_strategy,
        method = layout$method,
        seed = layout$seed,
        quality_scores = layout$quality,
        power_analysis = if (!is.null(layout$power_analysis))
            layout$power_analysis[c("power", "biological_power",
                                     "biological_power_valid", "biological_power_caveat",
                                     "sd_type", "delta", "sd", "required_bio_n",
                                     "bio_power_at_3", "bio_power_at_5",
                                     "parameters", "interpretation",
                                     "recommendation", "biological_recommendation")] else NULL,
        # FIX 4: record export status (e.g. Excel ok / failed / skipped).
        export_status = export_status,
        timestamp = Sys.time()
    )
    write_json(params, file.path(output_dir, "experiment_parameters.json"),
               pretty = TRUE, auto_unbox = TRUE)
    cat("   Saved:", file.path(output_dir, "experiment_parameters.json"), "\n")

    # 6. Quality report (text)
    cat("6. Quality report (layout_quality_report.txt)...\n")
    # FIX 4: pass export status so the report surfaces any export failure.
    .write_quality_report(layout, experiment, output_dir, export_status = export_status)

    # 7. Plater-format CSV (if plater available)
    cat("7. Plater-format CSV...\n")
    if (requireNamespace("plater", quietly = TRUE)) {
        tryCatch({
            .export_plater_format(layout, experiment, output_dir)
        }, error = function(e) {
            cat("   Plater export failed:", conditionMessage(e), "\n")
            export_status$warnings <<- c(export_status$warnings,
                                         paste("Plater export failed:", conditionMessage(e)))
        })
    } else {
        cat("   (plater not available - grid CSV serves same purpose)\n")
    }

    # FIX 4: verify every written file is non-empty; list offenders.
    verification <- .verify_outputs(output_dir)
    if (length(verification$offenders) > 0) {
        export_status$warnings <- c(export_status$warnings,
            paste("Empty/missing output files:",
                  paste(verification$offenders, collapse = ", ")))
    }

    cat("\n=== Export Complete ===\n")
    cat("All files saved to:", output_dir, "\n")
    if (length(export_status$warnings) > 0) {
        cat("\n⚠️  Export completed WITH WARNINGS:\n")
        for (w in export_status$warnings) cat("   -", w, "\n")
    }

    # FIX 4: return a status object (not just the dir) so callers can detect
    # partial/failed exports programmatically.
    invisible(list(
        output_dir = output_dir,
        excel = export_status$excel,
        warnings = export_status$warnings,
        verified_files = verification$ok,
        offenders = verification$offenders
    ))
}

# --- FIX 4: verify all written outputs are non-empty ---
# Walks the output directory and flags any zero-byte (or, for .xlsx, sub-1KB)
# files as offenders. Returns the list of good files and the offenders.
.verify_outputs <- function(output_dir, min_xlsx_bytes = 1000) {
    files <- list.files(output_dir, full.names = TRUE, recursive = FALSE)
    files <- files[!dir.exists(files)]
    ok <- character(0)
    offenders <- character(0)
    for (f in files) {
        sz <- file.info(f)$size
        is_xlsx <- grepl("\\.xlsx$", f, ignore.case = TRUE)
        bad <- is.na(sz) || sz == 0 || (is_xlsx && sz <= min_xlsx_bytes)
        if (bad) offenders <- c(offenders, basename(f)) else ok <- c(ok, basename(f))
    }
    cat(sprintf("   Output verification: %d file(s) OK", length(ok)))
    if (length(offenders) > 0) {
        cat(sprintf(", %d EMPTY/INVALID: %s\n",
                    length(offenders), paste(offenders, collapse = ", ")))
    } else {
        cat(", 0 empty.\n")
    }
    list(ok = ok, offenders = offenders)
}

# --- Excel export with colors ---
.export_excel <- function(layout, experiment, output_dir) {
    library(openxlsx)

    wb <- createWorkbook()
    plate_data <- layout$plate_data
    dims <- experiment$plate_dims

    # Color palette for treatments
    all_treatments <- unique(plate_data$treatment[!is.na(plate_data$treatment)])
    colors <- c("#4CAF50", "#2196F3", "#FF9800", "#9C27B0", "#F44336",
                "#00BCD4", "#795548", "#607D8B", "#E91E63", "#CDDC39",
                "#3F51B5", "#009688", "#FF5722", "#8BC34A", "#673AB7")
    if (length(all_treatments) > length(colors)) {
        colors <- rep(colors, ceiling(length(all_treatments) / length(colors)))
    }
    treatment_colors <- setNames(colors[seq_along(all_treatments)], all_treatments)

    for (p in 1:experiment$n_plates) {
        sheet_name <- if (experiment$n_plates > 1) paste("Plate", p) else "Plate Layout"
        addWorksheet(wb, sheet_name)

        plate_subset <- plate_data[plate_data$plate == p, ]

        # Create grid matrix
        grid <- matrix("", nrow = dims$rows, ncol = dims$cols)
        for (i in seq_len(nrow(plate_subset))) {
            r <- plate_subset$row[i]
            c <- plate_subset$col[i]
            content <- plate_subset$sample_id[i]
            if (is.na(content)) {
                grid[r, c] <- if (plate_subset$well_role[i] == "empty") "[EMPTY]" else ""
            } else {
                grid[r, c] <- content
            }
        }

        # Write with headers
        header <- c("", dims$col_labels)
        writeData(wb, sheet_name, t(header), startRow = 1, startCol = 1, colNames = FALSE)

        for (r in 1:dims$rows) {
            row_data <- c(dims$row_labels[r], grid[r, ])
            writeData(wb, sheet_name, t(row_data), startRow = r + 1, startCol = 1, colNames = FALSE)

            # Color cells
            for (c in 1:dims$cols) {
                well_idx <- which(plate_subset$row == r & plate_subset$col == c)
                if (length(well_idx) == 1) {
                    trt <- plate_subset$treatment[well_idx]
                    if (!is.na(trt) && trt %in% names(treatment_colors)) {
                        style <- createStyle(fgFill = treatment_colors[trt],
                                             halign = "center", fontSize = 9)
                        addStyle(wb, sheet_name, style, rows = r + 1, cols = c + 1)
                    } else if (plate_subset$well_role[well_idx] == "empty") {
                        style <- createStyle(fgFill = "#E0E0E0",
                                             halign = "center", fontSize = 9)
                        addStyle(wb, sheet_name, style, rows = r + 1, cols = c + 1)
                    }
                }
            }
        }

        # Auto-width
        setColWidths(wb, sheet_name, cols = 1:(dims$cols + 1), widths = "auto")

        # Add legend sheet
        if (p == experiment$n_plates) {
            addWorksheet(wb, "Legend")
            legend_data <- data.frame(
                Treatment = all_treatments,
                Color = treatment_colors[all_treatments],
                stringsAsFactors = FALSE
            )
            writeData(wb, "Legend", legend_data, startRow = 1)
            for (i in seq_len(nrow(legend_data))) {
                style <- createStyle(fgFill = legend_data$Color[i])
                addStyle(wb, "Legend", style, rows = i + 1, cols = 2)
            }
        }
    }

    xlsx_path <- file.path(output_dir, "plate_layout.xlsx")
    saveWorkbook(wb, xlsx_path, overwrite = TRUE)

    # FIX 4: verify the workbook actually landed on disk and is non-trivial.
    # A valid .xlsx (zip container) is always well over 1 KB; a 0-byte or tiny
    # file means saveWorkbook silently failed.
    if (!file.exists(xlsx_path)) {
        stop("Excel file was not written: ", xlsx_path)
    }
    fsize <- file.info(xlsx_path)$size
    if (is.na(fsize) || fsize <= 1000) {
        stop(sprintf("Excel file is empty/too small (%s bytes): %s",
                     ifelse(is.na(fsize), "NA", fsize), xlsx_path))
    }
    cat("   Saved:", xlsx_path, sprintf("(%d bytes, verified)\n", fsize))
    invisible(xlsx_path)
}

# --- Quality report ---
.write_quality_report <- function(layout, experiment, output_dir, export_status = NULL) {
    quality <- layout$quality
    plate_data <- layout$plate_data

    assigned <- plate_data[!is.na(plate_data$sample_id), ]

    # FIX 3: read the DECLARED replicate vocabulary (single source of truth).
    n_bio <- if (!is.null(experiment$n_biological)) experiment$n_biological
             else if (experiment$n_plates > 1) experiment$n_plates else 1L
    n_tech <- if (!is.null(experiment$n_technical)) experiment$n_technical
              else experiment$n_replicates

    lines <- c(
        paste("=== Plate Layout Quality Report ==="),
        paste("Generated:", Sys.time()),
        "",
        paste("Experiment:", experiment$name),
        paste("Plate format:", experiment$plate_format, "-well"),
        paste("Method:", layout$method),
        paste("Edge strategy:", experiment$edge_strategy),
        paste("Seed:", layout$seed),
        "",
        "--- Replication Design (declared) ---",
        # FIX 3: report DECLARED n_biological/n_technical; these are the single
        # source of truth and must agree across this report and the JSON params.
        sprintf("Biological replicates (independent preps): %d", n_bio),
        sprintf("Technical replicates (within-plate):       %d", n_tech),
        sprintf("Plates:                                    %d", experiment$n_plates),
        if (!is.null(experiment$normalization) &&
            identical(experiment$normalization, "ratiometric"))
            sprintf("Normalization:                             ratiometric (measurands: %s; references: %s)",
                    paste(experiment$measurands, collapse = ", "),
                    paste(experiment$reference_measurands, collapse = ", "))
        else NULL,
        if (!is.null(experiment$interplate_calibrator) && experiment$n_plates > 1)
            sprintf("Inter-plate calibrator:                    %s (on every plate)",
                    experiment$interplate_calibrator)
        else NULL,
        "",
        "--- Quality Scores ---",
        sprintf("Overall score:        %.0f%% %s",
                quality$overall_score * 100,
                if (quality$overall_score >= 0.8) "(GOOD)" else "(NEEDS REVIEW)"),
        sprintf("Spatial balance:      %.0f%%", quality$spatial_score * 100),
        sprintf("Control distribution: %.0f%%", quality$control_score * 100),
        sprintf("Edge protection:      %.0f%%", quality$edge_score * 100),
        "",
        "--- Well Counts ---",
        sprintf("Total wells:          %d", nrow(plate_data)),
        sprintf("Sample wells:         %d", sum(assigned$sample_type == "sample", na.rm = TRUE)),
        # FIX 1: surface inter-plate calibrator wells when present.
        if (any(assigned$sample_type == "calibrator", na.rm = TRUE))
            sprintf("Calibrator wells:     %d", sum(assigned$sample_type == "calibrator", na.rm = TRUE))
        else NULL,
        sprintf("Positive controls:    %d", sum(assigned$sample_type == "positive", na.rm = TRUE)),
        sprintf("Negative controls:    %d", sum(assigned$sample_type == "negative", na.rm = TRUE)),
        sprintf("Blanks:               %d", sum(assigned$sample_type == "blank", na.rm = TRUE)),
        sprintf("Empty (edge buffer):  %d", sum(plate_data$well_role == "empty")),
        sprintf("Unassigned:           %d",
                sum(is.na(plate_data$sample_id) & plate_data$well_role != "empty")),
        sprintf("Plate utilization:    %.0f%% (%d of %d wells assigned)",
                (nrow(assigned) / nrow(plate_data)) * 100, nrow(assigned), nrow(plate_data)),
        "",
        "--- Treatments ---"
    )

    trt_counts <- table(assigned$treatment[assigned$sample_type == "sample"])
    for (trt in names(trt_counts)) {
        lines <- c(lines, sprintf("  %-25s %d wells", trt, trt_counts[trt]))
    }

    lines <- c(lines, "",
        "--- Recommendations ---")

    if (quality$spatial_score < 0.7) {
        lines <- c(lines,
            "  WARNING: Low spatial balance. Consider using 'osat_spatial' method",
            "  or increasing max_iter for better optimization.")
    }
    if (quality$control_score < 1) {
        lines <- c(lines,
            "  WARNING: Controls not distributed across all quadrants.",
            "  Add more controls or adjust edge_strategy.")
    }
    if (quality$overall_score >= 0.8) {
        lines <- c(lines, "  Layout quality is GOOD. Ready for use.")
    }

    # Edge strategy utilization note
    n_unassigned <- sum(is.na(plate_data$sample_id) & plate_data$well_role != "empty")
    if (experiment$edge_strategy %in% c("controls_only", "empty") && n_unassigned > 0) {
        utilization_pct <- round((nrow(assigned) / nrow(plate_data)) * 100)
        lines <- c(lines,
            sprintf("  NOTE: %d edge wells are intentionally unassigned for edge effect protection.", n_unassigned),
            sprintf("  Plate utilization is %d%%. This is a deliberate tradeoff — outer wells", utilization_pct),
            "  have 10-30% higher evaporation rates that can confound treatment effects.",
            "  To use all wells, set edge_strategy='include' (lower protection).")
    }

    # Power analysis section (if assessed via assess_layout_power())
    if (!is.null(layout$power_analysis)) {
        pa <- layout$power_analysis
        # FIX 2: label the biological-power number with its validity (a value
        # computed from a technical SD is not a valid biological-power estimate).
        bio_valid_tag <- if (isTRUE(pa$biological_power_valid)) "(biological SD)"
                         else if (!is.null(pa$biological_power_caveat)) "[INVALID/UNVERIFIED]"
                         else ""
        bio_power_str <- if (!is.null(pa$biological_power) && !is.na(pa$biological_power))
            sprintf("Biological power:     %.3f (plate-level, n=%d) %s",
                    pa$biological_power, pa$n_plates, bio_valid_tag)
        else NULL

        lines <- c(lines, "",
            "--- Power Analysis ---",
            sprintf("Technical power:      %.3f (well-level, n=%d) %s",
                    pa$power, pa$min_n_per_group,
                    if (pa$power >= 0.8) "(ADEQUATE)" else "(UNDERPOWERED)"),
            bio_power_str,
            # FIX 2: when the effect came from delta/SD, show that basis.
            if (!is.null(pa$sd_type) && !is.na(pa$sd_type))
                sprintf("Effect basis:         delta=%.2f / %s SD=%.2f", pa$delta, pa$sd_type, pa$sd)
            else NULL,
            if (!is.null(pa$biological_power_caveat))
                paste("Biological power note:", pa$biological_power_caveat)
            else NULL,
            sprintf("Effect size:          %.2f (%s)",
                    pa$parameters$effect_size,
                    pa$parameters$effect_size_label),
            sprintf("Test type:            %s", pa$parameters$test_type),
            sprintf("Alpha:                %.3f", pa$parameters$alpha),
            sprintf("Min replicates/group: %d", pa$min_n_per_group),
            sprintf("Treatments:           %d", pa$n_treatments),
            "",
            "Per-treatment power:")
        for (i in seq_len(nrow(pa$per_treatment))) {
            lines <- c(lines, sprintf("  %-25s n=%-3d power=%.3f",
                        pa$per_treatment$treatment[i],
                        pa$per_treatment$n[i],
                        pa$per_treatment$power[i]))
        }
        lines <- c(lines, "", paste("Assessment:", pa$interpretation),
                   paste("Recommendation:", pa$recommendation))

        # FIX 3: design-aware pseudoreplication section using DECLARED counts.
        # Reports the declared n_biological/n_technical and, for multi-plate
        # designs that DISTRIBUTE biological reps across plates (ratiometric
        # split-by-sample), states which biological reps each plate holds
        # instead of mislabeling every plate as "biological n=1".
        ratiometric_split <- identical(experiment$normalization, "ratiometric") &&
                             experiment$n_plates > 1
        if (!is.null(pa$n_plates) && pa$n_plates > 1) {
            lines <- c(lines, "",
                "IMPORTANT - Replication & Pseudoreplication:",
                sprintf("  Declared design: n_biological=%d, n_technical=%d across %d plates.",
                        n_bio, n_tech, pa$n_plates))
            if (ratiometric_split) {
                # Distribute-by-sample: report the bio reps per plate from the data.
                lines <- c(lines,
                    "  Biological replicates are DISTRIBUTED across plates (split by whole sample);",
                    "  each plate holds a subset of the biological replicates, not a full replica.")
                # Derive which biological reps landed on each plate from sample_ids.
                samp_wells <- plate_data[!is.na(plate_data$sample_type) &
                                         plate_data$sample_type == "sample", ]
                bio_idx <- suppressWarnings(as.integer(sub(".*_bio([0-9]+)_.*", "\\1",
                                                           samp_wells$sample_id)))
                for (p in sort(unique(samp_wells$plate))) {
                    reps_here <- sort(unique(bio_idx[samp_wells$plate == p & !is.na(bio_idx)]))
                    if (length(reps_here) > 0) {
                        lines <- c(lines, sprintf(
                            "    Plate %d holds biological reps %s of the n_biological=%d design.",
                            p, paste(reps_here, collapse = ","), n_bio))
                    }
                }
                lines <- c(lines,
                    "  Analyze with n = number of biological replicates (NOT total wells).")
            } else {
                lines <- c(lines,
                    sprintf("  n=%d above is total wells per treatment across %d plates.",
                            pa$min_n_per_group, pa$n_plates),
                    sprintf("  Wells per plate per treatment: ~%d (technical replicates)",
                            pa$wells_per_plate_per_group),
                    sprintf("  Biological n = %d ONLY IF each plate is an independent preparation.",
                            pa$n_plates),
                    "  Do NOT use total well count as n in publication statistics.")
            }
        } else {
            lines <- c(lines, "",
                "IMPORTANT - Replication & Pseudoreplication:",
                sprintf("  Declared design: n_biological=%d, n_technical=%d (single plate).",
                        n_bio, n_tech),
                if (n_bio <= 1)
                    "  Single plate: all wells are technical replicates (biological n=1)."
                else
                    sprintf("  Single plate holds technical reps; biological n=%d requires independent preparations.",
                            n_bio),
                "  For biological power, repeat the experiment on independent days/passages.")
        }

        if (!is.null(pa$required_bio_n)) {
            lines <- c(lines, "",
                "BIOLOGICAL REPLICATION PLAN:",
                sprintf("  Power with 3 independent preparations: %.1f%%", pa$bio_power_at_3 * 100),
                sprintf("  Power with 5 independent preparations: %.1f%%", pa$bio_power_at_5 * 100),
                sprintf("  Required for 80%% biological power: %d independent preparations", pa$required_bio_n),
                "  Each preparation = new cell passage/batch on a separate day.",
                "  Average technical replicates within each plate, analyze with n = # preparations.")
        }

        # FIX 2: power vs assumed biological SD (only when delta/SD was given).
        if (!is.null(pa$sensitivity_over_sd)) {
            sd_tbl <- pa$sensitivity_over_sd
            lines <- c(lines, "",
                "POWER vs BIOLOGICAL SD (effect size depends on the assumed SD):")
            for (i in seq_len(nrow(sd_tbl))) {
                lines <- c(lines, sprintf("  biological SD=%.2f  ->  d=%.2f  ->  power=%.1f%%",
                            sd_tbl$biological_sd[i], sd_tbl$cohens_d[i], sd_tbl$power[i] * 100))
            }
            lines <- c(lines,
                "  (qPCR dCt biological SD prior ~0.5-1.0 Ct vs ~0.4 Ct technical floor)")
        }
    }

    # FIX 4: surface export status so an Excel failure is visible in the report,
    # not silently swallowed.
    if (!is.null(export_status)) {
        lines <- c(lines, "", "--- Export Status ---",
                   sprintf("  Excel (.xlsx): %s", export_status$excel))
        if (length(export_status$warnings) > 0) {
            lines <- c(lines, "  WARNINGS:")
            for (w in export_status$warnings) lines <- c(lines, paste("   -", w))
        } else {
            lines <- c(lines, "  No export warnings; all files written.")
        }
    }

    report_path <- file.path(output_dir, "layout_quality_report.txt")
    writeLines(lines, report_path)
    cat("   Saved:", report_path, "\n")
}

# --- Plater-format export ---
.export_plater_format <- function(layout, experiment, output_dir) {
    plate_data <- layout$plate_data
    dims <- experiment$plate_dims

    for (p in 1:experiment$n_plates) {
        plate_subset <- plate_data[plate_data$plate == p, ]

        # Plater format: first row is column headers, subsequent rows start with row label
        lines <- character(0)
        lines <- c(lines, paste(c("", dims$col_labels), collapse = ","))

        for (r in 1:dims$rows) {
            row_vals <- character(dims$cols)
            for (c in 1:dims$cols) {
                idx <- which(plate_subset$row == r & plate_subset$col == c)
                if (length(idx) == 1 && !is.na(plate_subset$treatment[idx])) {
                    row_vals[c] <- plate_subset$treatment[idx]
                } else {
                    row_vals[c] <- ""
                }
            }
            lines <- c(lines, paste(c(dims$row_labels[r], row_vals), collapse = ","))
        }

        suffix <- if (experiment$n_plates > 1) paste0("_plate", p) else ""
        plater_path <- file.path(output_dir, paste0("plate_plater_format", suffix, ".csv"))
        writeLines(lines, plater_path)
        cat("   Saved:", plater_path, "\n")
    }
}

cat("✓ export_layout.R loaded\n")
cat("  Use: export_all(layout, experiment, output_dir = 'layout_results')\n")
