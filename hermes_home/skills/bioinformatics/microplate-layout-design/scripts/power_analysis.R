
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
# Microplate Layout Design - Power Analysis for Plate-Based Assays
# =============================================================================
# General-purpose power analysis using the pwr package for cell-based assays
# (viability, dose-response, ELISA, qPCR). Uses Cohen's d/f effect sizes,
# NOT genomics-specific metrics (for RNA-seq power, use experimental-design-statistics).
# =============================================================================

suppressPackageStartupMessages({
    library(ggplot2)
    library(ggprism)
})

# Prevent R from opening default PDF device (causes crashes in non-interactive sessions)
if (!interactive()) pdf(NULL)

# --- Private helpers ---

.resolve_effect_size <- function(effect_size, test_type) {
    if (is.numeric(effect_size)) {
        return(list(value = effect_size, label = sprintf("%.2f", effect_size)))
    }
    if (test_type == "t") {
        sizes <- c(small = 0.2, medium = 0.5, large = 0.8)
    } else {
        sizes <- c(small = 0.10, medium = 0.25, large = 0.40)
    }
    if (!effect_size %in% names(sizes)) {
        stop("effect_size must be 'small', 'medium', 'large', or a numeric value")
    }
    list(value = sizes[[effect_size]], label = effect_size)
}

# =============================================================================
# effect_from_delta() — convert a raw effect (delta) + SD into Cohen's d (FIX 2)
# =============================================================================
# Power should be driven by the effect you care about (delta, in the assay's
# own units, e.g. ΔΔCt cycles) relative to its variability (sd), not by a bare
# Cohen's value. The returned d carries sd_type as an attribute so callers can
# tell biological from technical power.
#
# sd_type:
#   "biological" - SD across independent preparations/days. Use this for
#                  BIOLOGICAL power (generalizable conclusions).
#   "technical"  - SD across wells within one plate. Only valid for TECHNICAL
#                  (measurement) power; it understates biological variability.
#
# qPCR ΔCt prior: biological SD is typically ~0.5-1.0 Ct, well above the
# ~0.4 Ct technical (pipetting/instrument) floor. Powering a biological claim
# off the 0.4 Ct technical SD overstates power.
effect_from_delta <- function(delta, sd, sd_type = c("biological", "technical")) {
    sd_type <- match.arg(sd_type)
    if (!is.numeric(delta) || length(delta) != 1) stop("delta must be a single number")
    if (!is.numeric(sd) || length(sd) != 1 || sd <= 0) stop("sd must be a single positive number")
    d <- delta / sd
    attr(d, "sd_type") <- sd_type
    attr(d, "delta") <- delta
    attr(d, "sd") <- sd
    d
}

.get_available_wells <- function(plate_format, edge_strategy) {
    if (plate_format == 96) {
        if (edge_strategy %in% c("controls_only", "empty")) return(60)
        else return(96)
    } else if (plate_format == 384) {
        if (edge_strategy %in% c("controls_only", "empty")) return(308)
        else return(384)
    } else {
        stop("Unsupported plate format: ", plate_format)
    }
}

.interpret_power_plate <- function(power) {
    if (power >= 0.9) return("Excellent: High power to detect the specified effect")
    if (power >= 0.8) return("Good: Adequate power for most applications")
    if (power >= 0.7) return("Moderate: Consider adding replicates or plates")
    return("Low: Design is underpowered. Increase replicates or relax effect size expectations")
}

.check_pwr <- function() {
    if (!requireNamespace("pwr", quietly = TRUE)) {
        stop("Package 'pwr' is required for power analysis.\n",
             "Install with: install.packages('pwr')")
    }
}

# Local .save_plot to avoid source-order dependency on visualize_plate.R
.save_plot_power <- function(plot, base_path, width = 8, height = 6, dpi = 300) {
    # Handle missing extensions
    if (!grepl("\\.(svg|png)$", base_path)) {
        png_path <- paste0(base_path, ".png")
        svg_path <- paste0(base_path, ".svg")
    } else {
        png_path <- sub("\\.(svg|png)$", ".png", base_path)
        svg_path <- sub("\\.(svg|png)$", ".svg", base_path)
    }
    ggsave(png_path, plot = plot, width = width, height = height, dpi = dpi, device = "png")
    cat("   Saved:", png_path, "\n")
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
            cat("   (SVG export failed - PNG available)\n")
        })
    })
}

# =============================================================================
# 1. suggest_replicates() — Planning function (use BEFORE define_experiment)
# =============================================================================

suggest_replicates <- function(n_treatments,
                               effect_size = "medium",
                               target_power = 0.8,
                               alpha = 0.05,
                               plate_format = 96,
                               edge_strategy = "controls_only",
                               n_control_wells = 12,
                               test_type = "anova") {
    .check_pwr()

    if (n_treatments < 2) stop("n_treatments must be >= 2")
    if (n_treatments == 2 && test_type == "anova") {
        test_type <- "t"
    }

    es <- .resolve_effect_size(effect_size, test_type)

    # Calculate required n per group
    if (test_type == "t") {
        result <- pwr::pwr.t.test(
            d = es$value,
            sig.level = alpha,
            power = target_power,
            type = "two.sample"
        )
        required_n <- ceiling(result$n)
    } else {
        result <- pwr::pwr.anova.test(
            k = n_treatments,
            f = es$value,
            sig.level = alpha,
            power = target_power
        )
        required_n <- ceiling(result$n)
    }

    # Plate geometry
    wells_for_samples <- .get_available_wells(plate_format, edge_strategy)
    if (edge_strategy == "include") {
        wells_for_samples <- wells_for_samples - n_control_wells
    }

    total_sample_wells <- n_treatments * required_n
    n_plates <- ceiling(total_sample_wells / wells_for_samples)
    utilization <- total_sample_wells / (n_plates * wells_for_samples)

    # Recommendation text
    if (n_plates == 1 && total_sample_wells <= wells_for_samples) {
        rec <- sprintf("Fits on 1 plate: %d treatments x %d reps = %d wells (of %d available)",
                        n_treatments, required_n, total_sample_wells, wells_for_samples)
    } else {
        rec <- sprintf("Needs %d plate(s): %d treatments x %d reps = %d wells (%d available per plate)",
                        n_plates, n_treatments, required_n, total_sample_wells, wells_for_samples)
    }

    output <- list(
        required_n = required_n,
        parameters = list(
            n_treatments = n_treatments,
            effect_size = es$value,
            effect_size_label = es$label,
            target_power = target_power,
            alpha = alpha,
            test_type = test_type
        ),
        plate_plan = list(
            plate_format = plate_format,
            edge_strategy = edge_strategy,
            wells_per_plate_for_samples = wells_for_samples,
            total_sample_wells_needed = total_sample_wells,
            n_plates = n_plates,
            utilization = utilization
        ),
        interpretation = .interpret_power_plate(target_power),
        recommendation = rec
    )

    cat("\n✓ Power-based replicate suggestion completed successfully!\n")
    cat(sprintf("  Required: %d replicates per treatment (%d treatments x %d reps = %d wells)\n",
                required_n, n_treatments, required_n, total_sample_wells))
    cat(sprintf("  Plates needed: %d (%d-well, %s)\n", n_plates, plate_format, edge_strategy))
    cat(sprintf("  Utilization: %.0f%%\n", utilization * 100))
    cat(sprintf("  Effect size: %s (%s), Power: %.0f%%, Alpha: %.3f\n",
                es$label, test_type, target_power * 100, alpha))
    cat("    Small=subtle differences, Medium=moderate/typical, Large=obvious differences\n")
    cat("    Tip: Use 'small' if your assay has high variability or you need to detect subtle effects\n")

    return(output)
}

# =============================================================================
# 2. assess_layout_power() — Validation (use AFTER generate_plate_layout)
# =============================================================================

assess_layout_power <- function(layout,
                                effect_size = "medium",
                                alpha = 0.05,
                                test_type = "anova",
                                # FIX 2: SD-explicit effect specification.
                                # When delta + biological_sd are supplied, the
                                # effect size is computed as delta/SD and the
                                # biological-SD provenance gates biological power.
                                delta = NULL,
                                biological_sd = NULL,
                                technical_sd = NULL) {
    .check_pwr()

    if (!inherits(layout, "plate_layout")) {
        stop("Input must be a 'plate_layout' object from generate_plate_layout()")
    }

    pd <- layout$plate_data
    samples <- pd[!is.na(pd$sample_type) & pd$sample_type == "sample", ]
    treatments <- unique(samples$treatment)
    n_treatments <- length(treatments)

    if (n_treatments < 2) stop("Layout must have at least 2 treatment groups")
    if (n_treatments == 2 && test_type == "anova") {
        test_type <- "t"
    }

    # FIX 2: resolve effect size from delta + SD when provided, otherwise fall
    # back to the existing string/numeric effect_size path (back-compat).
    # Track which SD underpins the effect so biological power can be validated.
    sd_type <- NA_character_      # provenance of the SD used for the effect size
    delta_used <- NA_real_
    sd_used <- NA_real_
    if (!is.null(delta)) {
        # Prefer biological SD; fall back to technical SD with a clear flag.
        if (!is.null(biological_sd)) {
            d_val <- effect_from_delta(delta, biological_sd, sd_type = "biological")
        } else if (!is.null(technical_sd)) {
            d_val <- effect_from_delta(delta, technical_sd, sd_type = "technical")
        } else {
            stop("delta supplied without an SD. Provide biological_sd (preferred) ",
                 "or technical_sd so the effect size delta/SD can be computed.")
        }
        sd_type <- attr(d_val, "sd_type")
        delta_used <- attr(d_val, "delta")
        sd_used <- attr(d_val, "sd")
        es <- list(value = as.numeric(d_val),
                   label = sprintf("delta=%.2f / %s SD=%.2f", delta_used, sd_type, sd_used))
    } else {
        es <- .resolve_effect_size(effect_size, test_type)
    }

    # Count replicates per treatment
    reps_per_trt <- table(samples$treatment)

    # Plate-awareness for pseudoreplication reporting
    n_plates <- layout$experiment$n_plates
    if (n_plates > 1 && "plate" %in% colnames(samples)) {
        reps_per_plate <- table(samples$treatment, samples$plate)
        wells_per_plate_per_trt <- as.integer(min(reps_per_plate))
    } else {
        wells_per_plate_per_trt <- as.integer(min(reps_per_trt))
    }

    # Per-treatment power
    per_treatment <- data.frame(
        treatment = names(reps_per_trt),
        n = as.integer(reps_per_trt),
        power = numeric(length(reps_per_trt)),
        stringsAsFactors = FALSE
    )

    for (i in seq_len(nrow(per_treatment))) {
        n_i <- per_treatment$n[i]
        if (n_i < 2) {
            per_treatment$power[i] <- 0
            next
        }
        if (test_type == "t") {
            per_treatment$power[i] <- pwr::pwr.t.test(
                d = es$value, n = n_i, sig.level = alpha, type = "two.sample"
            )$power
        } else {
            per_treatment$power[i] <- pwr::pwr.anova.test(
                k = n_treatments, n = n_i, f = es$value, sig.level = alpha
            )$power
        }
    }

    # Overall power: conservative (use minimum n)
    min_n <- min(per_treatment$n)
    if (test_type == "t") {
        overall_power <- pwr::pwr.t.test(
            d = es$value, n = min_n, sig.level = alpha, type = "two.sample"
        )$power
    } else {
        overall_power <- pwr::pwr.anova.test(
            k = n_treatments, n = min_n, f = es$value, sig.level = alpha
        )$power
    }

    # Biological power: using n_plates as independent replicates
    biological_power <- NA
    if (n_plates >= 2) {
        if (test_type == "t") {
            biological_power <- pwr::pwr.t.test(
                d = es$value, n = n_plates, sig.level = alpha, type = "two.sample"
            )$power
        } else {
            biological_power <- pwr::pwr.anova.test(
                k = n_treatments, n = n_plates, f = es$value, sig.level = alpha
            )$power
        }
    }

    # FIX 2: validity of the biological-power number.
    # Biological power is only trustworthy if the effect size was scaled by a
    # BIOLOGICAL SD. If a technical SD was used (or the SD provenance is
    # unknown because a bare Cohen's value was supplied), flag it loudly.
    biological_power_valid <- identical(sd_type, "biological")
    biological_power_caveat <- if (identical(sd_type, "technical")) {
        "NOT VALID (technical SD used) - biological variability understated; supply biological_sd."
    } else if (is.na(sd_type)) {
        "UNVERIFIED (no biological SD supplied) - pass delta + biological_sd to validate biological power."
    } else {
        NULL
    }

    # Biological replication plan: how many independent preparations for 80% power?
    required_bio_n <- NA
    bio_power_at_3 <- NA
    bio_power_at_5 <- NA
    if (n_plates >= 1) {
        required_bio_n <- if (test_type == "t") {
            ceiling(pwr::pwr.t.test(d = es$value, power = 0.8, sig.level = alpha,
                                     type = "two.sample")$n)
        } else {
            ceiling(pwr::pwr.anova.test(k = n_treatments, f = es$value, power = 0.8,
                                         sig.level = alpha)$n)
        }
        for (bio_n in c(3, 5)) {
            bp <- if (test_type == "t") {
                pwr::pwr.t.test(d = es$value, n = bio_n, sig.level = alpha,
                                 type = "two.sample")$power
            } else {
                pwr::pwr.anova.test(k = n_treatments, n = bio_n, f = es$value,
                                     sig.level = alpha)$power
            }
            if (bio_n == 3) bio_power_at_3 <- bp
            if (bio_n == 5) bio_power_at_5 <- bp
        }
    }

    # Biological recommendation
    bio_rec <- sprintf(
        "BIOLOGICAL REPLICATION: Repeat on %d+ independent days/preparations for 80%% biological power. Minimum recommended: 3 preparations (power=%.0f%%).",
        min(required_bio_n, 99), bio_power_at_3 * 100)

    # Recommendation
    if (overall_power >= 0.8) {
        rec <- "Design has adequate power. No changes needed."
    } else {
        # Calculate how many more reps needed
        if (test_type == "t") {
            needed <- ceiling(pwr::pwr.t.test(
                d = es$value, sig.level = alpha, power = 0.8, type = "two.sample"
            )$n)
        } else {
            needed <- ceiling(pwr::pwr.anova.test(
                k = n_treatments, f = es$value, sig.level = alpha, power = 0.8
            )$n)
        }
        extra <- needed - min_n
        rec <- sprintf("\u26a0\ufe0f Underpowered (%.0f%%). Need %d more replicates per group (total %d) for 80%% power.",
                        overall_power * 100, max(extra, 1), needed)
    }

    result <- list(
        power = overall_power,
        biological_power = biological_power,
        # FIX 2: provenance + validity of the biological-power number.
        biological_power_valid = biological_power_valid,
        biological_power_caveat = biological_power_caveat,
        sd_type = sd_type,
        delta = delta_used,
        sd = sd_used,
        required_bio_n = required_bio_n,
        bio_power_at_3 = bio_power_at_3,
        bio_power_at_5 = bio_power_at_5,
        min_n_per_group = min_n,
        n_treatments = n_treatments,
        n_plates = n_plates,
        wells_per_plate_per_group = wells_per_plate_per_trt,
        biological_n_note = if (n_plates > 1)
            paste0("Biological n = ", n_plates, " ONLY IF each plate is an independent preparation ",
                   "(different cell passage/batch, separate day). Running all ", n_plates,
                   " plates from the same culture = biological n=1, NOT n=", n_plates, ".")
        else
            "Biological n = 1 (single plate). ALL wells are technical replicates only. You MUST repeat the entire experiment on independent days for biological replication.",
        per_treatment = per_treatment,
        parameters = list(
            effect_size = es$value,
            effect_size_label = es$label,
            alpha = alpha,
            test_type = test_type,
            # FIX 2: record the SD-explicit inputs (NA when string effect_size used).
            delta = delta_used,
            sd = sd_used,
            sd_type = sd_type
        ),
        interpretation = .interpret_power_plate(overall_power),
        recommendation = rec,
        biological_recommendation = bio_rec
    )

    layout$power_analysis <- result

    cat("\n\u2713 Power assessment completed successfully!\n")
    cat(sprintf("  Technical power (well-level, n=%d): %.3f (%s)\n",
                min_n, overall_power, .interpret_power_plate(overall_power)))
    cat(sprintf("  Effect size: %s (%s, Cohen's %s=%.2f), Alpha: %.3f\n",
                es$label, test_type, if (test_type == "t") "d" else "f", es$value, alpha))
    cat("    Small=subtle differences, Medium=moderate/typical, Large=obvious differences\n")

    if (overall_power < 0.80) {
        cat("\n")
        cat("  \u26a0\ufe0f  WARNING: Design is UNDERPOWERED for", es$label, "effects\n")
        cat("  \u26a0\ufe0f  Consider: increase n_replicates, add plates (n_plates), or target larger effects.\n")
    }

    # FIX 2: show the SD basis of the effect size when delta/SD was supplied.
    if (!is.na(sd_type)) {
        cat(sprintf("  Effect basis: delta=%.2f / %s SD=%.2f  =>  Cohen's %s=%.2f\n",
                    delta_used, sd_type, sd_used, if (test_type == "t") "d" else "f", es$value))
    }

    cat("\n  --- Biological Replication Plan ---\n")
    # FIX 2: a biological-power number computed from a TECHNICAL SD (or with no
    # SD provenance) is not a valid biological-power estimate. Say so loudly.
    if (!is.null(biological_power_caveat)) {
        cat("  ⚠️  BIOLOGICAL POWER", biological_power_caveat, "\n")
    }
    if (n_plates > 1) {
        bp_label <- if (biological_power_valid) "" else "  [see caveat above]"
        cat(sprintf("  Current biological power (n=%d plates): %.1f%%%s\n",
                    n_plates, biological_power * 100, bp_label))
    } else {
        cat("  Current biological power: N/A (single plate = 1 biological replicate)\n")
    }
    cat(sprintf("  Power with 3 independent preparations: %.1f%%\n", bio_power_at_3 * 100))
    cat(sprintf("  Power with 5 independent preparations: %.1f%%\n", bio_power_at_5 * 100))
    cat(sprintf("  Required for 80%% biological power:    %d independent preparations\n", required_bio_n))
    cat("  Each preparation = new cell passage/batch on a separate day\n")
    cat("  Average technical replicates within each plate, then analyze with n = # preparations\n")

    # --- Effect Size Sensitivity Table ---
    # Automatically compute power at standard benchmarks for context
    sensitivity_rows <- list()
    if (test_type == "t") {
        benchmarks <- c(small = 0.2, medium = 0.5, large = 0.8)
    } else {
        benchmarks <- c(small = 0.10, medium = 0.25, large = 0.40)
    }
    # Add user's chosen effect size if not already a standard benchmark
    if (!es$value %in% benchmarks) {
        benchmarks <- c(benchmarks, setNames(es$value, "YOUR"))
    }
    for (label in names(benchmarks)) {
        d <- benchmarks[[label]]
        tech_pwr <- if (test_type == "t") {
            pwr::pwr.t.test(d = d, n = min_n, sig.level = alpha, type = "two.sample")$power
        } else {
            pwr::pwr.anova.test(k = n_treatments, n = min_n, f = d, sig.level = alpha)$power
        }
        bio_pwr <- NA
        if (n_plates >= 2) {
            bio_pwr <- if (test_type == "t") {
                pwr::pwr.t.test(d = d, n = n_plates, sig.level = alpha, type = "two.sample")$power
            } else {
                pwr::pwr.anova.test(k = n_treatments, n = n_plates, f = d, sig.level = alpha)$power
            }
        }
        sensitivity_rows[[label]] <- list(effect_size = d, technical_power = tech_pwr,
                                           biological_power = bio_pwr)
    }
    sensitivity_df <- data.frame(
        effect_size_label = names(sensitivity_rows),
        effect_size = sapply(sensitivity_rows, `[[`, "effect_size"),
        technical_power = sapply(sensitivity_rows, `[[`, "technical_power"),
        biological_power = sapply(sensitivity_rows, `[[`, "biological_power"),
        stringsAsFactors = FALSE, row.names = NULL
    )
    result$sensitivity_table <- sensitivity_df
    layout$power_analysis <- result

    es_sym <- if (test_type == "t") "d" else "f"
    cat("\n  --- Effect Size Sensitivity ---\n")
    if (n_plates >= 2) {
        cat(sprintf("  %-18s | Technical Power | Biological Power (n=%d plates)\n",
                    "Effect Size", n_plates))
        cat("  ", strrep("-", 70), "\n", sep = "")
        for (i in seq_len(nrow(sensitivity_df))) {
            cat(sprintf("  %-18s |         %5.1f%%  |         %5.1f%%\n",
                        sprintf("%s (%s=%.2f)", sensitivity_df$effect_size_label[i],
                                es_sym, sensitivity_df$effect_size[i]),
                        sensitivity_df$technical_power[i] * 100,
                        sensitivity_df$biological_power[i] * 100))
        }
    } else {
        cat(sprintf("  %-18s | Technical Power\n", "Effect Size"))
        cat("  ", strrep("-", 40), "\n", sep = "")
        for (i in seq_len(nrow(sensitivity_df))) {
            cat(sprintf("  %-18s |         %5.1f%%\n",
                        sprintf("%s (%s=%.2f)", sensitivity_df$effect_size_label[i],
                                es_sym, sensitivity_df$effect_size[i]),
                        sensitivity_df$technical_power[i] * 100))
        }
    }

    # Warn if medium-effect biological power is low
    med_row <- sensitivity_df[sensitivity_df$effect_size_label == "medium", ]
    if (nrow(med_row) > 0 && n_plates >= 2 && !is.na(med_row$biological_power[1])) {
        if (med_row$biological_power[1] < 0.50) {
            cat(sprintf("\n  \u26a0\ufe0f  NOTE: Biological power at medium effect size is only %.0f%%.\n",
                        med_row$biological_power[1] * 100))
            cat("  If your experiment targets moderate effects, this design may be underpowered.\n")
        }
    }

    # FIX 2: when a raw effect (delta) is supplied, show how BIOLOGICAL power
    # moves as the assumed biological SD varies. This makes the SD assumption
    # explicit instead of hidden inside a single Cohen's value.
    if (!is.na(delta_used)) {
        bio_n_for_sd <- if (n_plates >= 2) n_plates else max(required_bio_n, 3)
        sd_tbl <- sensitivity_over_sd(delta = delta_used, n = bio_n_for_sd,
                                      n_treatments = n_treatments, alpha = alpha,
                                      test_type = test_type, quiet = FALSE)
        result$sensitivity_over_sd <- sd_tbl
        layout$power_analysis <- result
    }

    return(layout)
}

# =============================================================================
# sensitivity_over_sd() \u2014 power vs assumed biological SD (FIX 2)
# =============================================================================
# Given a raw effect (delta) and a sample size n (number of independent
# biological preparations), tabulate power across a range of biological SDs.
# This surfaces how sensitive the conclusion is to the (often uncertain)
# biological-SD assumption rather than committing to one Cohen's value.
#
# qPCR \u0394Ct prior: biological SD is typically ~0.5-1.0 Ct (vs the ~0.4 Ct
# technical floor), so the default sd_range brackets that realistic window.
sensitivity_over_sd <- function(delta,
                                n,
                                sd_range = c(0.4, 0.6, 0.8, 1.0),
                                n_treatments = 2,
                                alpha = 0.05,
                                test_type = "t",
                                quiet = FALSE) {
    .check_pwr()
    if (!is.numeric(delta) || length(delta) != 1) stop("delta must be a single number")
    if (n_treatments == 2 && test_type == "anova") test_type <- "t"

    powers <- vapply(sd_range, function(sd) {
        d <- delta / sd
        if (test_type == "t") {
            pwr::pwr.t.test(d = d, n = n, sig.level = alpha, type = "two.sample")$power
        } else {
            pwr::pwr.anova.test(k = n_treatments, n = n, f = d, sig.level = alpha)$power
        }
    }, numeric(1))

    tbl <- data.frame(
        biological_sd = sd_range,
        cohens_d = delta / sd_range,
        power = powers,
        stringsAsFactors = FALSE
    )

    if (!quiet) {
        cat("\n  --- Power vs Biological SD (delta =", sprintf("%.2f", delta),
            ", n =", n, "preparations) ---\n")
        es_sym <- if (test_type == "t") "d" else "f"
        cat(sprintf("  %-14s | %-10s | %s\n", "Biological SD", es_sym, "Power"))
        cat("  ", strrep("-", 40), "\n", sep = "")
        for (i in seq_len(nrow(tbl))) {
            cat(sprintf("  %-14s | %-10s | %5.1f%%\n",
                        sprintf("%.2f", tbl$biological_sd[i]),
                        sprintf("%.2f", tbl$cohens_d[i]),
                        tbl$power[i] * 100))
        }
        cat("  (qPCR \u0394Ct biological SD prior ~0.5-1.0 Ct vs ~0.4 Ct technical floor)\n")
    }

    invisible(tbl)
}

# =============================================================================
# 3. plot_power_curve() — Power vs replicates visualization
# =============================================================================

plot_power_curve <- function(n_treatments,
                             effect_size = "medium",
                             alpha = 0.05,
                             test_type = "anova",
                             current_n = NULL,
                             output_dir = "layout_results",
                             output_name = "power_curve") {
    .check_pwr()

    if (n_treatments == 2 && test_type == "anova") test_type <- "t"
    es <- .resolve_effect_size(effect_size, test_type)

    # Extend range beyond current_n to prevent text cutoff at edges
    max_n <- if (!is.null(current_n)) max(25, current_n + 10) else 25
    n_range <- 2:max_n
    power_values <- sapply(n_range, function(n) {
        if (test_type == "t") {
            pwr::pwr.t.test(d = es$value, n = n, sig.level = alpha, type = "two.sample")$power
        } else {
            pwr::pwr.anova.test(k = n_treatments, n = n, f = es$value, sig.level = alpha)$power
        }
    })

    plot_data <- data.frame(n_per_group = n_range, power = power_values)

    # Adaptive x-axis breaks to prevent overplotting
    break_interval <- if (max_n <= 30) 2 else if (max_n <= 60) 5 else 10

    p <- ggplot(plot_data, aes(x = n_per_group, y = power)) +
        geom_line(linewidth = 1.2, color = "#2196F3") +
        geom_hline(yintercept = 0.8, linetype = "dashed", color = "gray40") +
        annotate("text", x = max_n - 2, y = 0.82, label = "80% power",
                 color = "gray40", size = 3.5) +
        labs(
            title = "Statistical Power vs. Replicates per Group",
            subtitle = sprintf("Effect size: %s (%s), k=%d groups, alpha=%.2f",
                               es$label, test_type, n_treatments, alpha),
            x = "Replicates per Group",
            y = "Statistical Power"
        ) +
        scale_x_continuous(breaks = seq(0, max_n, break_interval)) +
        scale_y_continuous(limits = c(0, 1), breaks = seq(0, 1, 0.2)) +
        theme_prism(base_size = 12) +
        theme(
            plot.title = element_text(hjust = 0.5, face = "bold", size = 14),
            plot.subtitle = element_text(hjust = 0.5, size = 10)
        )

    # Only add individual points when range is small enough to avoid clutter
    if (max_n <= 30) {
        p <- p + geom_point(size = 2, color = "#2196F3")
    }

    # Highlight current design point
    if (!is.null(current_n) && current_n >= 2 && current_n <= max_n) {
        current_power <- if (test_type == "t") {
            pwr::pwr.t.test(d = es$value, n = current_n, sig.level = alpha, type = "two.sample")$power
        } else {
            pwr::pwr.anova.test(k = n_treatments, n = current_n, f = es$value, sig.level = alpha)$power
        }
        # Place label to left of point when near right edge, otherwise right
        near_right_edge <- current_n > (max_n * 0.7)
        label_x <- if (near_right_edge) current_n - 2 else current_n + 2
        label_hjust <- if (near_right_edge) 1 else 0

        p <- p +
            geom_point(data = data.frame(n_per_group = current_n, power = current_power),
                       size = 5, color = "#F44336", shape = 18) +
            annotate("text", x = label_x, y = current_power,
                     label = sprintf("Your design\nn=%d, power=%.0f%%", current_n, current_power * 100),
                     color = "#F44336", size = 3, fontface = "bold", hjust = label_hjust)
    }

    dir.create(output_dir, showWarnings = FALSE, recursive = TRUE)
    output_path <- file.path(output_dir, paste0(output_name, ".png"))
    .save_plot_power(p, output_path, width = 8, height = 6)

    cat("✓ Power curve generated successfully!\n")
    invisible(p)
}

# =============================================================================
# 4. check_layout_confounding() — Chi-square positional confounding test
# =============================================================================

check_layout_confounding <- function(layout, position_var = "quadrant") {
    if (!inherits(layout, "plate_layout")) {
        stop("Input must be a 'plate_layout' object from generate_plate_layout()")
    }

    pd <- layout$plate_data
    samples <- pd[!is.na(pd$sample_type) & pd$sample_type == "sample", ]

    if (nrow(samples) < 4) stop("Too few samples for confounding check")

    # Derive position variable
    if (position_var == "quadrant") {
        mid_row <- max(samples$row) / 2
        mid_col <- max(samples$col) / 2
        samples$position <- paste0("Q",
            ifelse(samples$row <= mid_row, ifelse(samples$col <= mid_col, 1, 2),
                                           ifelse(samples$col <= mid_col, 3, 4)))
    } else if (position_var == "row") {
        samples$position <- samples$row_label
    } else if (position_var == "col") {
        samples$position <- as.character(samples$col_label)
    } else if (position_var == "is_edge") {
        samples$position <- ifelse(samples$is_edge, "edge", "interior")
    } else if (position_var == "plate") {
        if (length(unique(samples$plate)) < 2) {
            cat("Single-plate design: plate-level confounding check not applicable.\n")
            cat("✓ Confounding check completed successfully!\n")
            return(list(status = "SKIPPED", is_confounded = FALSE,
                        p_value = NA, position_var = "plate",
                        message = "Single-plate design: plate-level check not applicable."))
        }
        samples$position <- paste0("Plate_", samples$plate)
    } else {
        stop("position_var must be 'quadrant', 'row', 'col', 'is_edge', or 'plate'")
    }

    cont_table <- table(samples$position, samples$treatment)

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

    is_confounded <- p_value <= 0.05
    status <- if (is_confounded) "FAILED" else "PASSED"

    if (is_confounded) {
        msg <- sprintf("WARNING: %s is confounded with treatment (%s p=%.4f)",
                        position_var, test_name, p_value)
    } else {
        msg <- sprintf("PASS: No confounding detected between %s and treatment (p=%.4f)",
                        position_var, p_value)
    }
    if (use_fisher) {
        msg <- paste0(msg, "\n  (Fisher's exact test used: some expected cell counts < 5)")
    }

    result <- list(
        status = status,
        is_confounded = is_confounded,
        p_value = p_value,
        contingency_table = cont_table,
        position_var = position_var,
        message = msg,
        test_name = test_name,
        test = test_result
    )

    cat(msg, "\n")
    cat("✓ Confounding check completed successfully!\n")
    return(result)
}

# =============================================================================
# 5. check_normalization_colocation() — Ratiometric co-location guard (FIX 1)
# =============================================================================
# Ratiometric readouts (e.g. ddCt) form a ratio of a target measurand to a
# reference measurand on the SAME biological sample. If those wells land on
# different plates, plate batch effects contaminate the ratio. This check
# FAILS when:
#   (a) any biological sample's measurand wells span >1 plate, or
#   (b) a multi-plate ratiometric design lacks the inter-plate calibrator on
#       every plate.
# It is a no-op (PASSED) for non-ratiometric designs.

check_normalization_colocation <- function(layout) {
    if (!inherits(layout, "plate_layout")) {
        stop("Input must be a 'plate_layout' object from generate_plate_layout()")
    }

    exp <- layout$experiment
    ratiometric <- identical(exp$normalization, "ratiometric")

    if (!ratiometric) {
        return(list(status = "PASSED", is_violated = FALSE,
                    position_var = "colocation",
                    message = "Non-ratiometric design: co-location check not applicable."))
    }

    pd <- layout$plate_data
    wells <- pd[!is.na(pd$sample_id) &
                !is.na(pd$sample_type) &
                pd$sample_type %in% c("sample", "calibrator"), , drop = FALSE]

    # (a) every biological sample must occupy exactly one plate.
    split_samples <- character(0)
    if ("bio_sample" %in% colnames(wells) && nrow(wells) > 0) {
        plates_per_sample <- tapply(wells$plate, wells$bio_sample,
                                    function(x) length(unique(x)))
        split_samples <- names(plates_per_sample)[plates_per_sample > 1]
    }

    # (b) multi-plate ratiometric designs need the calibrator on every plate.
    n_plates <- exp$n_plates
    calibrator_ok <- TRUE
    calibrator_msg <- NULL
    if (n_plates > 1) {
        if (is.null(exp$interplate_calibrator)) {
            calibrator_ok <- FALSE
            calibrator_msg <- "Multi-plate ratiometric design has NO inter-plate calibrator."
        } else {
            cal_wells <- wells[wells$sample_type == "calibrator", , drop = FALSE]
            plates_with_cal <- unique(cal_wells$plate)
            if (length(plates_with_cal) < n_plates) {
                calibrator_ok <- FALSE
                missing_p <- setdiff(seq_len(n_plates), plates_with_cal)
                calibrator_msg <- sprintf(
                    "Inter-plate calibrator '%s' missing from plate(s): %s",
                    exp$interplate_calibrator, paste(missing_p, collapse = ", "))
            }
        }
    }

    is_violated <- length(split_samples) > 0 || !calibrator_ok
    status <- if (is_violated) "FAILED" else "PASSED"

    if (is_violated) {
        msg <- "WARNING: ratiometric co-location violated."
        if (length(split_samples) > 0) {
            msg <- paste0(msg, sprintf(
                "\n  %d biological sample(s) span >1 plate: %s",
                length(split_samples),
                paste(utils::head(split_samples, 5), collapse = ", ")))
        }
        if (!is.null(calibrator_msg)) msg <- paste0(msg, "\n  ", calibrator_msg)
    } else {
        msg <- sprintf(
            "PASS: all biological samples co-located%s",
            if (n_plates > 1) "; inter-plate calibrator present on every plate." else ".")
    }

    cat(msg, "\n")
    list(status = status, is_violated = is_violated,
         position_var = "colocation",
         split_samples = split_samples,
         calibrator_ok = calibrator_ok,
         message = msg)
}

# =============================================================================
# 6. check_all_confounding() — Comprehensive confounding check
# =============================================================================

check_all_confounding <- function(layout) {
    if (!inherits(layout, "plate_layout")) {
        stop("Input must be a 'plate_layout' object from generate_plate_layout()")
    }

    n_plates <- layout$experiment$n_plates
    vars_to_check <- c("quadrant", "row", "col", "is_edge")
    if (n_plates > 1) vars_to_check <- c(vars_to_check, "plate")

    cat("\n=== Comprehensive Confounding Check ===\n")
    results <- list()
    any_confounded <- FALSE

    for (v in vars_to_check) {
        cat(sprintf("\n--- %s ---\n", v))
        res <- check_layout_confounding(layout, position_var = v)
        results[[v]] <- res
        if (isTRUE(res$is_confounded)) any_confounded <- TRUE
    }

    # FIX 1: ratiometric co-location check (only meaningful when normalization
    # is ratiometric; otherwise reports PASSED/not-applicable).
    cat("\n--- colocation (ratiometric) ---\n")
    coloc <- check_normalization_colocation(layout)
    results[["colocation"]] <- coloc
    if (isTRUE(coloc$is_violated)) any_confounded <- TRUE

    cat("\n=== Summary ===\n")
    for (v in names(results)) {
        status <- results[[v]]$status
        # colocation has no p-value; positional checks do.
        p <- if (!is.null(results[[v]]$p_value)) results[[v]]$p_value else NA
        symbol <- if (status == "PASSED") "PASS" else if (status == "FAILED") "FAIL" else "SKIP"
        p_str <- if (is.na(p)) "N/A" else sprintf("%.4f", p)
        cat(sprintf("  [%s] %-10s (p = %s)\n", symbol, v, p_str))
    }

    if (any_confounded) {
        cat("\n  WARNING: Confounding or co-location issue detected. Re-run generate_plate_layout() with different seed/settings.\n")
    } else {
        cat("\n  All checks passed. No positional confounding detected.\n")
    }

    cat("✓ Comprehensive confounding check completed successfully!\n")
    return(list(results = results, any_confounded = any_confounded))
}

# =============================================================================
cat("✓ power_analysis.R loaded\n")
cat("  Use: suggest_replicates(n_treatments = 3, effect_size = 'medium')\n")
cat("  Use: layout <- assess_layout_power(layout, effect_size = 'medium')\n")
cat("       assess_layout_power(layout, delta = 1.0, biological_sd = 0.7)  # SD-explicit\n")
cat("  Use: effect_from_delta(delta = 1.0, sd = 0.7, sd_type = 'biological')\n")
cat("  Use: sensitivity_over_sd(delta = 1.0, n = 4)\n")
cat("  Use: plot_power_curve(n_treatments = 3, current_n = 6)\n")
cat("  Use: check_all_confounding(layout)  # includes ratiometric co-location\n")
cat("  Use: check_normalization_colocation(layout)\n")
