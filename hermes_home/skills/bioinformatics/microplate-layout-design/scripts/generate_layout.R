
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
# Microplate Layout Design - Core Layout Generation Engine
# =============================================================================
# Generates optimized plate layouts using designit (OSAT + spatial scoring),
# agricolae (Latin square), or block randomization.
# =============================================================================

suppressPackageStartupMessages({
    library(designit)
    library(ggplot2)
})

# --- Main layout generation function ---
generate_plate_layout <- function(experiment,
                                   method = "osat_spatial",
                                   balance_vars = NULL,
                                   seed = 42,
                                   max_iter = 1000,
                                   quiet = FALSE) {

    if (!inherits(experiment, "plate_experiment")) {
        stop("Input must be a 'plate_experiment' object from define_experiment()")
    }

    set.seed(seed)
    if (!quiet) cat("\n=== Generating Plate Layout ===\n")
    if (!quiet) cat("Method:", method, "\n")
    if (!quiet) cat("Seed:", seed, "\n\n")

    # FIX 1: latin_square assigns treatments by grid POSITION and ignores the
    # per-sample/per-measurand sample table, so it cannot honor co-location or
    # place the inter-plate calibrator. Reject it early for multi-measurand /
    # ratiometric designs with a clear, actionable message.
    if (method == "latin_square" &&
        !is.null(experiment$measurands) && length(experiment$measurands) > 0) {
        stop("method='latin_square' is not supported for multi-measurand / ",
             "ratiometric designs (it assigns by grid position and cannot keep ",
             "a sample's measurands co-located or place the inter-plate calibrator). ",
             "Use method='osat_spatial' or 'block_random' instead.")
    }

    # Build the sample table
    samples <- .build_sample_table(experiment)

    # Build the plate grid
    plate_grid <- .build_plate_grid(experiment)

    # Mark edge wells, reserved wells
    plate_grid <- .mark_special_wells(plate_grid, experiment)

    # Generate layout based on method
    layout <- switch(method,
        "osat_spatial" = .layout_osat_spatial(plate_grid, samples, experiment,
                                              balance_vars, max_iter, quiet),
        "block_random" = .layout_block_random(plate_grid, samples, experiment,
                                              balance_vars, seed, quiet),
        "latin_square" = .layout_latin_square(plate_grid, samples, experiment, seed, quiet),
        "manual_template" = .layout_manual_template(plate_grid, samples, experiment, quiet),
        stop("Unknown method: ", method,
             ". Use: osat_spatial, block_random, latin_square, manual_template")
    )

    # Place controls
    layout <- .place_controls(layout, experiment, seed, quiet)

    # FIX 1: map the biological-sample key back into plate_data via sample_id,
    # then HARD-ERROR if a ratiometric design ended up splitting a sample's
    # measurand wells (or its calibrator) across plates.
    layout$plate_data <- .attach_bio_sample(layout$plate_data, samples)
    .assert_colocation(layout$plate_data, experiment)

    # Score quality
    quality <- .score_layout_quality(layout, experiment)
    layout$quality <- quality

    # Attach experiment metadata
    layout$experiment <- experiment
    layout$method <- method
    layout$seed <- seed
    class(layout) <- "plate_layout"

    if (!quiet) {
        cat("\n✓ Layout generated successfully!\n")
        cat("  Method:", method, "\n")
        cat("  Wells assigned:", sum(!is.na(layout$plate_data$sample_id)), "of",
            nrow(layout$plate_data), "\n")
        cat("  Quality score:", round(quality$overall_score, 2), "/ 1.00\n")
        cat("  Spatial balance:", round(quality$spatial_score, 2), "/ 1.00\n")
        cat("  Control distribution:", round(quality$control_score, 2), "/ 1.00\n")
    }

    return(layout)
}

# --- Build sample table from experiment ---
# Each row is ONE well. Columns:
#   sample_id   - unique label for the well (treatment + rep [+ measurand] [+ plate])
#   treatment   - treatment/condition the well belongs to
#   replicate   - replicate index within the treatment on its plate
#   measurand   - measured target (gene/channel) for the well; "" when not used
#   bio_sample  - biological-sample key: every measurand x tech-rep well of ONE
#                 biological sample shares this key (used to enforce co-location)
#   sample_type - "sample" or "calibrator"
#   target_plate- the plate this well is assigned to
#
# FIX 1: when experiment$measurands is set, expand each biological sample x
# technical replicate across every measurand into co-located wells. In
# ratiometric mode the multi-plate split is BY WHOLE BIOLOGICAL SAMPLE (a
# sample's full measurand x rep block stays on one plate) and the inter-plate
# calibrator is added to every plate. Without measurands the original
# per-plate-replica behaviour is preserved exactly for back-compat.
.build_sample_table <- function(experiment) {
    measurands <- experiment$measurands
    has_measurands <- !is.null(measurands) && length(measurands) > 0
    ratiometric <- identical(experiment$normalization, "ratiometric")
    n_plates <- experiment$n_plates
    multi <- n_plates > 1
    rows <- list()

    if (!has_measurands) {
        # ---- Back-compat path: one well per (treatment, rep, plate) ----
        # Preserves the original "each plate is a replica" semantics.
        for (trt in experiment$treatments) {
            for (rep in 1:experiment$n_replicates) {
                for (plate in 1:n_plates) {
                    rows[[length(rows) + 1]] <- data.frame(
                        sample_id   = paste0(trt, "_rep", rep, if (multi) paste0("_P", plate) else ""),
                        treatment   = trt,
                        replicate   = rep,
                        measurand   = "",
                        bio_sample  = paste0(trt, "_rep", rep, if (multi) paste0("_P", plate) else ""),
                        sample_type = "sample",
                        target_plate = plate,
                        stringsAsFactors = FALSE
                    )
                }
            }
        }
        return(do.call(rbind, rows))
    }

    # ---- Multi-measurand path ----
    # A "biological sample" = one (treatment, biological-replicate). The bio
    # loop uses the DECLARED n_biological and the tech loop uses n_technical
    # (FIX 3 vocabulary), so wells = treatments x n_biological x measurands x
    # n_technical. In ratiometric mode biological replicates are split across
    # plates BY WHOLE SAMPLE; otherwise every plate carries a full replica.
    # n_biological/n_technical always exist on the experiment (define_experiment
    # derives them from n_replicates/n_plates for back-compat callers).
    n_bio <- if (!is.null(experiment$n_biological)) experiment$n_biological
             else experiment$n_replicates
    n_tech <- if (!is.null(experiment$n_technical)) experiment$n_technical
              else experiment$n_replicates
    add_block <- function(trt, bio_rep, plate, sample_type) {
        # One co-located block = every measurand x technical replicate for a
        # single biological sample, all on the same plate.
        bio_key <- paste0(trt, "_bio", bio_rep, if (multi) paste0("_P", plate) else "")
        for (tech in 1:n_tech) {
            for (m in measurands) {
                rows[[length(rows) + 1]] <<- data.frame(
                    sample_id   = paste0(trt, "_bio", bio_rep, "_", m, "_t", tech,
                                         if (multi) paste0("_P", plate) else ""),
                    treatment   = trt,
                    replicate   = tech,
                    measurand   = m,
                    bio_sample  = bio_key,
                    sample_type = sample_type,
                    target_plate = plate,
                    stringsAsFactors = FALSE
                )
            }
        }
    }

    for (trt in experiment$treatments) {
        for (bio_rep in 1:n_bio) {
            if (ratiometric && multi) {
                # Split by whole sample: assign each biological replicate to a
                # single plate (round-robin), keeping its full block intact.
                plate <- ((bio_rep - 1) %% n_plates) + 1
                add_block(trt, bio_rep, plate, "sample")
            } else {
                # Non-ratiometric (or single plate): replicate block per plate.
                for (plate in 1:n_plates) {
                    add_block(trt, bio_rep, plate, "sample")
                }
            }
        }
    }

    # FIX 1: add the inter-plate calibrator's full block to EVERY plate so it
    # bridges plate-to-plate batch effects in multi-plate ratiometric designs.
    if (!is.null(experiment$interplate_calibrator) && multi) {
        cal <- experiment$interplate_calibrator
        for (plate in 1:n_plates) {
            bio_key <- paste0(cal, "_P", plate)
            for (tech in 1:n_tech) {
                for (m in measurands) {
                    rows[[length(rows) + 1]] <- data.frame(
                        sample_id   = paste0(cal, "_", m, "_t", tech, "_P", plate),
                        treatment   = cal,
                        replicate   = tech,
                        measurand   = m,
                        bio_sample  = bio_key,
                        sample_type = "calibrator",
                        target_plate = plate,
                        stringsAsFactors = FALSE
                    )
                }
            }
        }
    }

    do.call(rbind, rows)
}

# --- FIX 1: attach biological-sample key to assigned wells via sample_id ---
# The optimizer paths carry sample_id but not bio_sample; we re-join it here so
# downstream co-location checks know which wells belong to one biological sample.
.attach_bio_sample <- function(plate_data, samples) {
    plate_data$bio_sample <- NA_character_
    if (!"bio_sample" %in% colnames(samples)) return(plate_data)
    lut <- setNames(samples$bio_sample, samples$sample_id)
    assigned <- !is.na(plate_data$sample_id)
    plate_data$bio_sample[assigned] <- unname(lut[plate_data$sample_id[assigned]])
    plate_data
}

# --- FIX 1: hard co-location guard for ratiometric designs ---
# Raises a clear error if any biological sample's wells span >1 plate, or if a
# multi-plate ratiometric design is missing the inter-plate calibrator on a
# plate. No-op for non-ratiometric designs.
.assert_colocation <- function(plate_data, experiment) {
    if (!identical(experiment$normalization, "ratiometric")) return(invisible(TRUE))

    wells <- plate_data[!is.na(plate_data$sample_id) &
                        !is.na(plate_data$bio_sample), , drop = FALSE]
    if (nrow(wells) > 0) {
        plates_per_sample <- tapply(wells$plate, wells$bio_sample,
                                    function(x) length(unique(x)))
        split_samples <- names(plates_per_sample)[plates_per_sample > 1]
        if (length(split_samples) > 0) {
            stop("Ratiometric co-location violated: biological sample(s) ",
                 paste(utils::head(split_samples, 5), collapse = ", "),
                 " have measurand wells on >1 plate. Ratiometric designs must keep ",
                 "every measurand x replicate of one biological sample on the SAME plate ",
                 "(split multi-plate designs by whole sample, not by measurand).")
        }
    }

    if (experiment$n_plates > 1 && !is.null(experiment$interplate_calibrator)) {
        cal_wells <- plate_data[!is.na(plate_data$sample_type) &
                                plate_data$sample_type == "calibrator", , drop = FALSE]
        plates_with_cal <- unique(cal_wells$plate)
        if (length(plates_with_cal) < experiment$n_plates) {
            missing_p <- setdiff(seq_len(experiment$n_plates), plates_with_cal)
            stop("Ratiometric multi-plate design is missing the inter-plate ",
                 "calibrator '", experiment$interplate_calibrator,
                 "' on plate(s): ", paste(missing_p, collapse = ", "),
                 ". The calibrator must appear on EVERY plate to bridge batch effects.")
        }
    }
    invisible(TRUE)
}

# --- Build plate grid ---
.build_plate_grid <- function(experiment) {
    dims <- experiment$plate_dims
    grids <- list()
    for (p in 1:experiment$n_plates) {
        for (r in 1:dims$rows) {
            for (c in 1:dims$cols) {
                well <- paste0(dims$row_labels[r], dims$col_labels[c])
                grids[[length(grids) + 1]] <- data.frame(
                    plate = p,
                    row = r,
                    col = c,
                    row_label = dims$row_labels[r],
                    col_label = as.character(dims$col_labels[c]),
                    well = well,
                    well_id = if (experiment$n_plates > 1) paste0("P", p, "_", well) else well,
                    stringsAsFactors = FALSE
                )
            }
        }
    }
    do.call(rbind, grids)
}

# --- Mark special wells ---
.mark_special_wells <- function(plate_grid, experiment) {
    dims <- experiment$plate_dims
    plate_grid$is_edge <- plate_grid$row == 1 | plate_grid$row == dims$rows |
                          plate_grid$col == 1 | plate_grid$col == dims$cols
    plate_grid$well_role <- "available"

    # Apply edge strategy
    if (experiment$edge_strategy == "empty") {
        plate_grid$well_role[plate_grid$is_edge] <- "empty"
    } else if (experiment$edge_strategy == "controls_only") {
        plate_grid$well_role[plate_grid$is_edge] <- "control_reserved"
    }

    # Mark reserved wells
    if (!is.null(experiment$reserved_wells)) {
        plate_grid$well_role[plate_grid$well %in% experiment$reserved_wells] <- "reserved"
    }

    # Initialize assignment columns
    plate_grid$sample_id <- NA_character_
    plate_grid$treatment <- NA_character_
    plate_grid$replicate <- NA_integer_
    plate_grid$sample_type <- NA_character_
    # FIX 1: measurand column (gene/channel per well); NA when not a multi-measurand design.
    plate_grid$measurand <- NA_character_

    return(plate_grid)
}

# --- Method: OSAT + Spatial scoring (via designit) ---
.layout_osat_spatial <- function(plate_grid, samples, experiment, balance_vars, max_iter, quiet) {
    if (!quiet) cat("Using OSAT + spatial scoring optimization (designit)...\n")

    # Get assignable wells (available or control_reserved for controls_only strategy)
    assignable <- plate_grid$well_role == "available"

    if (is.null(balance_vars)) {
        balance_vars <- "treatment"
    }

    if (experiment$n_plates > 1) {
        # Multi-plate: optimize each plate independently to keep samples on
        # their assigned plate. Each plate is a self-contained experimental unit.
        if (!quiet) cat("  Multi-plate design: optimizing each plate independently...\n")

        for (p in 1:experiment$n_plates) {
            plate_samples <- samples[samples$target_plate == p, , drop = FALSE]
            plate_avail <- plate_grid[assignable & plate_grid$plate == p, , drop = FALSE]

            if (nrow(plate_samples) > nrow(plate_avail)) {
                stop("Not enough available wells on plate ", p, " (",
                     nrow(plate_avail), ") for samples (", nrow(plate_samples), ")")
            }

            # Single-plate context for per-plate optimization
            locations <- data.frame(
                plate = 1L,
                row = plate_avail$row,
                col = plate_avail$col,
                stringsAsFactors = FALSE
            )

            bc <- BatchContainer$new(locations = locations)
            # FIX 1: carry measurand + sample_type through the optimizer so
            # multi-measurand designs and the inter-plate calibrator survive.
            sample_df <- plate_samples[, c("sample_id", "treatment", "replicate",
                                           "measurand", "sample_type"), drop = FALSE]
            sample_df$treatment <- as.factor(sample_df$treatment)

            bc <- assign_random(bc, sample_df)

            scoring <- mk_plate_scoring_functions(
                bc,
                plate = "plate",
                row = "row",
                column = "col",
                group = balance_vars[1]
            )

            bc <- optimize_design(
                bc,
                scoring = scoring,
                max_iter = max_iter,
                n_shuffle = 2,
                quiet = quiet
            )

            result <- bc$get_samples(assignment = TRUE, include_id = TRUE)

            for (i in seq_len(nrow(result))) {
                if (is.na(result$treatment[i])) next
                idx <- which(plate_avail$row == result$row[i] &
                             plate_avail$col == result$col[i])
                if (length(idx) == 1) {
                    grid_idx <- which(plate_grid$well_id == plate_avail$well_id[idx])
                    plate_grid$treatment[grid_idx] <- as.character(result$treatment[i])
                    plate_grid$replicate[grid_idx] <- result$replicate[i]
                    plate_grid$sample_type[grid_idx] <- result$sample_type[i]
                    plate_grid$sample_id[grid_idx] <- result$sample_id[i]
                    plate_grid$measurand[grid_idx] <-
                        if (!is.na(result$measurand[i]) && nzchar(result$measurand[i]))
                            result$measurand[i] else NA_character_
                }
            }

            if (!quiet) cat("  Plate", p, ":", nrow(plate_samples), "samples assigned to",
                            nrow(plate_avail), "available wells\n")
        }
    } else {
        # Single plate: global optimization
        avail_grid <- plate_grid[assignable, , drop = FALSE]

        if (nrow(samples) > nrow(avail_grid)) {
            stop("Not enough available wells (", nrow(avail_grid),
                 ") for samples (", nrow(samples), ")")
        }

        locations <- data.frame(
            plate = avail_grid$plate,
            row = avail_grid$row,
            col = avail_grid$col,
            stringsAsFactors = FALSE
        )

        bc <- BatchContainer$new(locations = locations)
        # FIX 1: carry measurand + sample_type through the optimizer.
        sample_df <- samples[, c("sample_id", "treatment", "replicate",
                                 "measurand", "sample_type"), drop = FALSE]
        sample_df$treatment <- as.factor(sample_df$treatment)

        bc <- assign_random(bc, sample_df)

        scoring <- mk_plate_scoring_functions(
            bc,
            plate = "plate",
            row = "row",
            column = "col",
            group = balance_vars[1]
        )

        bc <- optimize_design(
            bc,
            scoring = scoring,
            max_iter = max_iter,
            n_shuffle = 2,
            quiet = quiet
        )

        result <- bc$get_samples(assignment = TRUE, include_id = TRUE)

        for (i in seq_len(nrow(result))) {
            if (is.na(result$treatment[i])) next
            idx <- which(avail_grid$plate == result$plate[i] &
                         avail_grid$row == result$row[i] &
                         avail_grid$col == result$col[i])
            if (length(idx) == 1) {
                grid_idx <- which(plate_grid$well_id == avail_grid$well_id[idx])
                plate_grid$treatment[grid_idx] <- as.character(result$treatment[i])
                plate_grid$replicate[grid_idx] <- result$replicate[i]
                plate_grid$sample_type[grid_idx] <- result$sample_type[i]
                plate_grid$sample_id[grid_idx] <- result$sample_id[i]
                plate_grid$measurand[grid_idx] <-
                    if (!is.na(result$measurand[i]) && nzchar(result$measurand[i]))
                        result$measurand[i] else NA_character_
            }
        }
    }

    return(list(plate_data = plate_grid))
}

# --- Method: Block randomization ---
.layout_block_random <- function(plate_grid, samples, experiment, balance_vars, seed, quiet) {
    if (!quiet) cat("Using block randomization...\n")

    if (experiment$n_plates > 1) {
        # Multi-plate: randomize within each plate independently
        if (!quiet) cat("  Multi-plate design: randomizing each plate independently...\n")
        set.seed(seed)

        for (p in 1:experiment$n_plates) {
            plate_samples <- samples[samples$target_plate == p, , drop = FALSE]
            plate_assignable <- which(plate_grid$well_role == "available" & plate_grid$plate == p)

            if (length(plate_assignable) < nrow(plate_samples)) {
                stop("Not enough available wells on plate ", p, " (",
                     length(plate_assignable), ") for samples (", nrow(plate_samples), ")")
            }

            shuffled_idx <- sample(plate_assignable, nrow(plate_samples))

            for (i in seq_len(nrow(plate_samples))) {
                gi <- shuffled_idx[i]
                plate_grid$sample_id[gi] <- plate_samples$sample_id[i]
                plate_grid$treatment[gi] <- plate_samples$treatment[i]
                plate_grid$replicate[gi] <- plate_samples$replicate[i]
                # FIX 1: preserve sample_type (sample vs calibrator) + measurand.
                plate_grid$sample_type[gi] <- plate_samples$sample_type[i]
                plate_grid$measurand[gi] <-
                    if (nzchar(plate_samples$measurand[i])) plate_samples$measurand[i] else NA_character_
            }

            if (!quiet) cat("  Plate", p, ":", nrow(plate_samples), "samples assigned\n")
        }
    } else {
        # Single plate: global randomization
        assignable <- which(plate_grid$well_role == "available")

        if (length(assignable) < nrow(samples)) {
            stop("Not enough available wells (", length(assignable),
                 ") for samples (", nrow(samples), ")")
        }

        set.seed(seed)
        shuffled_idx <- sample(assignable, nrow(samples))

        for (i in seq_len(nrow(samples))) {
            gi <- shuffled_idx[i]
            plate_grid$sample_id[gi] <- samples$sample_id[i]
            plate_grid$treatment[gi] <- samples$treatment[i]
            plate_grid$replicate[gi] <- samples$replicate[i]
            # FIX 1: preserve sample_type (sample vs calibrator) + measurand.
            plate_grid$sample_type[gi] <- samples$sample_type[i]
            plate_grid$measurand[gi] <-
                if (nzchar(samples$measurand[i])) samples$measurand[i] else NA_character_
        }
    }

    return(list(plate_data = plate_grid))
}

# --- Method: Latin square ---
.layout_latin_square <- function(plate_grid, samples, experiment, seed, quiet) {
    if (!quiet) cat("Using Latin square design...\n")

    treatments <- experiment$treatments
    n_trt <- length(treatments)
    dims <- experiment$plate_dims

    # Generate Latin square
    if (requireNamespace("agricolae", quietly = TRUE)) {
        ls_design <- agricolae::design.lsd(treatments, seed = seed)
        ls_matrix <- ls_design$sketch
    } else {
        # Fallback: simple cyclic Latin square
        if (!quiet) cat("  (agricolae not available, using cyclic Latin square)\n")
        ls_matrix <- matrix(NA, nrow = n_trt, ncol = n_trt)
        for (i in 1:n_trt) {
            for (j in 1:n_trt) {
                ls_matrix[i, j] <- treatments[((i + j - 2) %% n_trt) + 1]
            }
        }
    }

    # Tile the Latin square across the plate
    assignable <- which(plate_grid$well_role == "available")
    rep_counter <- list()

    for (gi in assignable) {
        p <- plate_grid$plate[gi]
        r <- plate_grid$row[gi]
        c <- plate_grid$col[gi]

        # Map plate position to Latin square position
        ls_r <- ((r - 1) %% n_trt) + 1
        ls_c <- ((c - 1) %% n_trt) + 1
        trt <- ls_matrix[ls_r, ls_c]

        # Track replicates
        key <- paste0(p, "_", trt)
        if (is.null(rep_counter[[key]])) rep_counter[[key]] <- 0
        rep_counter[[key]] <- rep_counter[[key]] + 1

        plate_grid$treatment[gi] <- trt
        plate_grid$replicate[gi] <- rep_counter[[key]]
        plate_grid$sample_type[gi] <- "sample"
        plate_grid$sample_id[gi] <- paste0(trt, "_rep", rep_counter[[key]])
    }

    return(list(plate_data = plate_grid))
}

# --- Method: Manual template ---
.layout_manual_template <- function(plate_grid, samples, experiment, quiet) {
    if (!quiet) cat("Using manual template (block randomization fallback)...\n")
    # For manual template, fall back to block randomization
    # Users would typically modify the result
    return(.layout_block_random(plate_grid, samples, experiment, NULL, 42, quiet))
}

# --- Place controls ---
.place_controls <- function(layout, experiment, seed, quiet) {
    plate_data <- layout$plate_data
    controls <- experiment$controls
    n_controls <- experiment$n_controls

    set.seed(seed + 1)  # Different seed from sample placement

    active_controls <- names(controls)[!sapply(controls, is.null)]
    if (length(active_controls) == 0) {
        if (!quiet) cat("No controls to place.\n")
        return(layout)
    }

    if (!quiet) cat("Placing controls...\n")

    for (ctrl_type in active_controls) {
        ctrl_name <- controls[[ctrl_type]]
        n_needed <- n_controls[[ctrl_type]]

        for (p in 1:experiment$n_plates) {
            # Find candidate wells for controls
            if (experiment$edge_strategy == "controls_only") {
                # Place controls in edge wells first
                candidates <- which(plate_data$plate == p &
                                    plate_data$well_role == "control_reserved" &
                                    is.na(plate_data$sample_id))
            } else {
                # Place controls in any unassigned well
                candidates <- which(plate_data$plate == p &
                                    is.na(plate_data$sample_id) &
                                    plate_data$well_role != "empty" &
                                    plate_data$well_role != "reserved")
            }

            if (length(candidates) < n_needed) {
                warning("Not enough wells for ", ctrl_type, " controls on plate ", p,
                        " (need ", n_needed, ", have ", length(candidates), ")")
                n_needed <- min(n_needed, length(candidates))
            }

            if (n_needed == 0) next

            # Distribute controls across quadrants for spatial coverage
            selected <- .distribute_across_quadrants(
                candidates, n_needed, plate_data, experiment
            )

            for (i in seq_along(selected)) {
                gi <- selected[i]
                plate_data$sample_id[gi] <- paste0(ctrl_name, "_", ctrl_type, "_", i,
                                                     if (experiment$n_plates > 1) paste0("_P", p) else "")
                plate_data$treatment[gi] <- ctrl_name
                plate_data$replicate[gi] <- i
                plate_data$sample_type[gi] <- ctrl_type
                plate_data$well_role[gi] <- ctrl_type
            }
        }
        if (!quiet) cat("  Placed", n_needed * experiment$n_plates, ctrl_type,
                        "controls (", ctrl_name, ")\n")
    }

    layout$plate_data <- plate_data
    return(layout)
}

# --- Distribute wells across quadrants ---
.distribute_across_quadrants <- function(candidates, n_needed, plate_data, experiment) {
    dims <- experiment$plate_dims
    mid_row <- dims$rows / 2
    mid_col <- dims$cols / 2

    # Assign candidates to quadrants
    q1 <- candidates[plate_data$row[candidates] <= mid_row & plate_data$col[candidates] <= mid_col]
    q2 <- candidates[plate_data$row[candidates] <= mid_row & plate_data$col[candidates] > mid_col]
    q3 <- candidates[plate_data$row[candidates] > mid_row & plate_data$col[candidates] <= mid_col]
    q4 <- candidates[plate_data$row[candidates] > mid_row & plate_data$col[candidates] > mid_col]

    quadrants <- list(q1, q2, q3, q4)

    # Round-robin selection from each quadrant
    selected <- integer(0)
    qi <- 1
    while (length(selected) < n_needed) {
        q <- quadrants[[qi]]
        available_in_q <- setdiff(q, selected)
        if (length(available_in_q) > 0) {
            pick <- sample(available_in_q, 1)
            selected <- c(selected, pick)
        }
        qi <- (qi %% 4) + 1
        # Safety: if all quadrants exhausted, take from any remaining
        if (length(selected) < n_needed &&
            all(sapply(quadrants, function(q) length(setdiff(q, selected)) == 0))) {
            remaining <- setdiff(candidates, selected)
            if (length(remaining) > 0) {
                n_still <- min(n_needed - length(selected), length(remaining))
                selected <- c(selected, sample(remaining, n_still))
            }
            break
        }
    }

    return(selected)
}

# --- Score layout quality ---
.score_layout_quality <- function(layout, experiment) {
    plate_data <- layout$plate_data
    dims <- experiment$plate_dims

    scores <- list()

    # 1. Spatial distribution score: how evenly are treatments spread?
    assigned <- plate_data[!is.na(plate_data$treatment) & plate_data$sample_type == "sample", ]
    if (nrow(assigned) > 1) {
        treatments <- unique(assigned$treatment)
        dist_scores <- numeric(length(treatments))
        for (i in seq_along(treatments)) {
            trt_wells <- assigned[assigned$treatment == treatments[i], ]
            if (nrow(trt_wells) > 1) {
                # Calculate mean pairwise distance (normalized)
                coords <- cbind(trt_wells$row / dims$rows, trt_wells$col / dims$cols)
                dists <- as.matrix(dist(coords))
                mean_dist <- mean(dists[upper.tri(dists)])
                # Max possible distance is sqrt(2) for normalized coords
                dist_scores[i] <- min(mean_dist / 0.5, 1)  # 0.5 is a good target
            } else {
                dist_scores[i] <- 1
            }
        }
        scores$spatial_score <- mean(dist_scores)
    } else {
        scores$spatial_score <- 1
    }

    # 2. Control distribution score: are controls in all quadrants?
    controls <- plate_data[!is.na(plate_data$sample_type) &
                           plate_data$sample_type %in% c("positive", "negative", "blank"), ]
    if (nrow(controls) > 0) {
        mid_row <- dims$rows / 2
        mid_col <- dims$cols / 2
        in_q1 <- any(controls$row <= mid_row & controls$col <= mid_col)
        in_q2 <- any(controls$row <= mid_row & controls$col > mid_col)
        in_q3 <- any(controls$row > mid_row & controls$col <= mid_col)
        in_q4 <- any(controls$row > mid_row & controls$col > mid_col)
        scores$control_score <- mean(c(in_q1, in_q2, in_q3, in_q4))
    } else {
        scores$control_score <- 1
    }

    # 3. Edge utilization score
    edge_samples <- plate_data[plate_data$is_edge & plate_data$sample_type == "sample" &
                               !is.na(plate_data$sample_type), ]
    if (experiment$edge_strategy %in% c("empty", "controls_only")) {
        # Good: no samples in edge wells
        scores$edge_score <- if (nrow(edge_samples) == 0) 1 else 0.5
    } else {
        scores$edge_score <- 1  # All wells used, no penalty
    }

    # Overall score
    scores$overall_score <- mean(c(scores$spatial_score, scores$control_score, scores$edge_score))

    return(scores)
}

cat("✓ generate_layout.R loaded\n")
cat("  Use: layout <- generate_plate_layout(experiment, method = 'osat_spatial')\n")
cat("  Methods: osat_spatial, block_random, latin_square, manual_template\n")
