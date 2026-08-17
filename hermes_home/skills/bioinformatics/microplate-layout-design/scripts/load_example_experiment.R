
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
# Microplate Layout Design - Example Experiment Definitions
# =============================================================================
# Provides pre-built experiment definitions for testing and demonstration.
# Users can also define experiments interactively with define_experiment().
# =============================================================================

# --- Package check ---
.check_packages <- function() {
    options(repos = c(CRAN = "https://cloud.r-project.org"))
    required <- c("designit", "ggplot2", "jsonlite", "pwr", "ggplate")
    missing <- required[!sapply(required, requireNamespace, quietly = TRUE)]
    if (length(missing) > 0) {
        cat("Installing required packages:", paste(missing, collapse = ", "), "\n")
        install.packages(missing)
    }
    # Optional packages: check availability but do NOT auto-install.
    # Downstream scripts (visualize_plate.R, export_layout.R) handle these
    # gracefully with requireNamespace() checks at point of use.
    optional <- c("openxlsx", "agricolae", "plater", "patchwork")
    available_opt <- sapply(optional, requireNamespace, quietly = TRUE)
    if (!all(available_opt)) {
        missing_opt <- optional[!available_opt]
        cat("  Optional packages not installed:", paste(missing_opt, collapse = ", "), "\n")
        cat("  Install with: install.packages(c('", paste(missing_opt, collapse = "', '"), "'))\n")
        cat("  Core functionality works without them.\n")
    }
}

# --- Plate format definitions ---
.plate_formats <- list(
    "96"  = list(rows = 8,  cols = 12, row_labels = LETTERS[1:8],  col_labels = 1:12),
    "384" = list(rows = 16, cols = 24, row_labels = LETTERS[1:16], col_labels = 1:24)
)

# --- Define experiment interactively ---
define_experiment <- function(plate_format = 96,
                              treatments = c("Treatment_A", "Treatment_B", "Vehicle"),
                              n_replicates = 3,
                              controls = list(positive = NULL, negative = NULL, blank = NULL),
                              n_controls = list(positive = 4, negative = 4, blank = 4),
                              edge_strategy = "controls_only",
                              n_plates = 1,
                              covariates = NULL,
                              reserved_wells = NULL,
                              experiment_name = "Experiment",
                              assay_type = "general",
                              # --- FIX 3: explicit replicate vocabulary ---
                              # n_technical = technical reps within a plate (well-level precision);
                              # n_biological = independent preparations / days (generalizability).
                              # Back-compat: both default to NULL and are derived from n_replicates
                              # and n_plates so existing callers keep working unchanged.
                              n_biological = NULL,
                              n_technical = NULL,
                              # --- FIX 1: ratiometric / multi-measurand designs ---
                              # measurands: per-sample targets measured (e.g. genes/channels).
                              #   When set, each biological sample x tech rep is expanded across
                              #   every measurand into co-located wells.
                              # normalization: "none" (default) or "ratiometric" (e.g. ddCt).
                              # reference_measurands: subset of measurands used as normalizers
                              #   (e.g. housekeeping genes); must be a subset of measurands.
                              # interplate_calibrator: a shared calibrator sample label added to
                              #   EVERY plate in multi-plate ratiometric designs (bridges plates),
                              #   or TRUE to auto-create one named "InterplateCalibrator".
                              measurands = NULL,
                              normalization = "none",
                              reference_measurands = NULL,
                              interplate_calibrator = NULL) {

    plate_fmt <- .plate_formats[[as.character(plate_format)]]
    if (is.null(plate_fmt)) {
        stop("Unsupported plate format: ", plate_format,
             ". Supported: ", paste(names(.plate_formats), collapse = ", "))
    }

    # --- FIX 3: resolve explicit biological/technical replicate counts ---
    # If the caller did not pass them, derive sensible back-compat values:
    #   - n_technical falls back to n_replicates (wells per group on a plate)
    #   - n_biological falls back to n_plates when multi-plate (each plate = one
    #     independent preparation), else 1 (single plate => biological n=1).
    if (is.null(n_technical)) n_technical <- n_replicates
    if (is.null(n_biological)) n_biological <- if (n_plates > 1) n_plates else 1L
    n_technical <- as.integer(n_technical)
    n_biological <- as.integer(n_biological)

    # --- FIX 1: validate normalization / measurand inputs ---
    normalization <- match.arg(normalization, c("none", "ratiometric"))
    if (!is.null(measurands)) {
        measurands <- as.character(measurands)
        if (anyDuplicated(measurands)) {
            stop("measurands must be unique; got duplicates: ",
                 paste(measurands[duplicated(measurands)], collapse = ", "))
        }
    }
    if (normalization == "ratiometric") {
        if (is.null(measurands) || length(measurands) < 2) {
            stop("Ratiometric normalization requires >= 2 measurands ",
                 "(e.g. a target plus reference gene(s)).")
        }
        if (is.null(reference_measurands) || length(reference_measurands) < 1) {
            stop("Ratiometric normalization requires reference_measurands ",
                 "(the normalizer subset, e.g. housekeeping genes).")
        }
        if (!all(reference_measurands %in% measurands)) {
            missing_ref <- setdiff(reference_measurands, measurands)
            stop("reference_measurands must be a subset of measurands. ",
                 "Not in measurands: ", paste(missing_ref, collapse = ", "))
        }
        if (all(measurands %in% reference_measurands)) {
            stop("At least one measurand must be a non-reference target ",
                 "(reference_measurands cannot equal the full measurand set).")
        }
    } else if (!is.null(reference_measurands) && is.null(measurands)) {
        stop("reference_measurands supplied without measurands. ",
             "Set measurands (and normalization='ratiometric') to use references.")
    }

    # Resolve the inter-plate calibrator label (TRUE => auto-named).
    if (isTRUE(interplate_calibrator)) {
        interplate_calibrator <- "InterplateCalibrator"
    } else if (!is.null(interplate_calibrator)) {
        interplate_calibrator <- as.character(interplate_calibrator)[1]
    }

    total_wells <- plate_fmt$rows * plate_fmt$cols * n_plates

    # Calculate edge wells
    edge_wells <- .get_edge_wells(plate_fmt)

    # Calculate available wells based on edge strategy
    if (edge_strategy == "empty") {
        interior_wells <- total_wells - length(edge_wells) * n_plates
        usable_for_samples <- interior_wells
    } else if (edge_strategy == "controls_only") {
        interior_wells <- total_wells - length(edge_wells) * n_plates
        usable_for_samples <- interior_wells
    } else {
        usable_for_samples <- total_wells
    }

    # Calculate total controls needed
    total_controls <- sum(unlist(n_controls[!sapply(controls, is.null)]))

    # Calculate sample wells needed.
    # FIX 1: when measurands are set, each biological sample x tech rep is
    # measured once per measurand, so sample wells = treatments x n_biological
    # x measurands x n_technical (the multi-measurand path uses the explicit
    # n_biological/n_technical vocabulary). Ratiometric multi-plate designs
    # split biological replicates BY WHOLE SAMPLE across plates (NOT replicated
    # per plate), so they are NOT multiplied by n_plates; every other mode keeps
    # a full replica on each plate. Without measurands the original
    # treatments x n_replicates x n_plates count is preserved for back-compat.
    n_measurands <- if (!is.null(measurands)) length(measurands) else 1L
    ratiometric_split <- identical(normalization, "ratiometric") && n_plates > 1
    if (!is.null(measurands)) {
        per_plate_factor <- if (ratiometric_split) 1L else n_plates
        n_sample_wells <- length(treatments) * n_biological * n_measurands *
                          n_technical * per_plate_factor
    } else {
        n_sample_wells <- length(treatments) * n_replicates * n_plates
    }
    wells_needed <- n_sample_wells + total_controls * n_plates

    # FIX 1: the inter-plate calibrator (when used in a multi-plate design)
    # occupies one block (measurands x n_technical) on EVERY plate.
    n_calibrator_wells <- 0L
    if (!is.null(interplate_calibrator) && n_plates > 1) {
        n_calibrator_wells <- n_measurands * n_technical * n_plates
        wells_needed <- wells_needed + n_calibrator_wells
    }

    # Reserved wells
    n_reserved <- if (!is.null(reserved_wells)) length(reserved_wells) * n_plates else 0

    experiment <- list(
        name = experiment_name,
        assay_type = assay_type,
        plate_format = plate_format,
        plate_dims = plate_fmt,
        n_plates = n_plates,
        treatments = treatments,
        n_replicates = n_replicates,
        # FIX 3: explicit, declared replicate vocabulary (one source of truth).
        n_biological = n_biological,
        n_technical = n_technical,
        controls = controls,
        n_controls = n_controls,
        edge_strategy = edge_strategy,
        edge_wells = edge_wells,
        covariates = covariates,
        reserved_wells = reserved_wells,
        # FIX 1: ratiometric / multi-measurand design fields.
        measurands = measurands,
        normalization = normalization,
        reference_measurands = reference_measurands,
        interplate_calibrator = interplate_calibrator,
        total_wells = total_wells,
        wells_needed = wells_needed,
        n_reserved = n_reserved
    )
    class(experiment) <- "plate_experiment"

    cat("✓ Experiment defined successfully!\n")
    cat("  Name:", experiment_name, "\n")
    cat("  Plate format:", plate_format, "-well (", plate_fmt$rows, "x", plate_fmt$cols, ")\n")
    cat("  Plates:", n_plates, "\n")
    cat("  Treatments:", paste(treatments, collapse = ", "), "\n")
    cat("  Replicates per treatment:", n_replicates, "\n")
    # FIX 3: surface the declared biological/technical split explicitly.
    cat("  Biological reps (independent preps):", n_biological, "\n")
    cat("  Technical reps (within-plate):", n_technical, "\n")
    # FIX 1: surface measurand / normalization configuration.
    if (!is.null(measurands)) {
        cat("  Measurands:", paste(measurands, collapse = ", "), "\n")
        cat("  Normalization:", normalization, "\n")
        if (!is.null(reference_measurands)) {
            cat("  Reference measurands:", paste(reference_measurands, collapse = ", "), "\n")
        }
        if (!is.null(interplate_calibrator)) {
            cat("  Inter-plate calibrator:", interplate_calibrator,
                if (n_plates > 1) "(on every plate)" else "(single plate; not duplicated)", "\n")
        }
    }
    cat("  Edge strategy:", edge_strategy, "\n")
    ctrl_names <- names(controls)[!sapply(controls, is.null)]
    if (length(ctrl_names) > 0) {
        cat("  Controls:", paste(ctrl_names, "=", controls[ctrl_names], collapse = ", "), "\n")
    }
    cat("  Total wells needed:", wells_needed, "of", total_wells, "available\n")

    return(experiment)
}

# --- Get edge wells for a plate format ---
.get_edge_wells <- function(plate_fmt) {
    edge <- character(0)
    for (r in 1:plate_fmt$rows) {
        for (c in 1:plate_fmt$cols) {
            if (r == 1 || r == plate_fmt$rows || c == 1 || c == plate_fmt$cols) {
                well <- paste0(plate_fmt$row_labels[r], plate_fmt$col_labels[c])
                edge <- c(edge, well)
            }
        }
    }
    return(edge)
}

# --- Pre-built example experiments ---
load_example_experiment <- function(example = "dose_response_96") {
    .check_packages()

    examples <- list(
        "dose_response_96" = function() {
            define_experiment(
                plate_format = 96,
                treatments = c("Drug", "Vehicle"),
                n_replicates = 5,
                controls = list(positive = "Staurosporine", negative = "DMSO", blank = "Media"),
                n_controls = list(positive = 4, negative = 4, blank = 4),
                edge_strategy = "controls_only",
                experiment_name = "Dose-Response Assay",
                assay_type = "dose_response",
                n_plates = 6
            )
        },
        # FIX 1: proper ratiometric qPCR ΔΔCt design.
        # A target gene (MYC) is normalized to housekeeping references
        # (GAPDH, ACTB) on the SAME biological sample (the ΔCt), then compared
        # Treated vs Untreated (the ΔΔCt). Measurands are co-located per sample;
        # 6 biological reps (per treatment) are split across 2 plates BY WHOLE
        # SAMPLE, with an inter-plate calibrator on every plate to bridge runs.
        "qpcr_96" = function() {
            define_experiment(
                plate_format = 96,
                treatments = c("Treated", "Untreated"),
                n_replicates = 6,             # biological reps per treatment (split across plates)
                measurands = c("MYC", "GAPDH", "ACTB"),
                reference_measurands = c("GAPDH", "ACTB"),
                normalization = "ratiometric",
                interplate_calibrator = TRUE, # shared cDNA on every plate (inter-run calibrator)
                n_biological = 6,
                n_technical = 3,              # technical (well) replicates per measurand
                controls = list(positive = NULL, negative = "NTC", blank = NULL),
                n_controls = list(positive = 0, negative = 4, blank = 0),
                edge_strategy = "include",    # sealed qPCR plates tolerate edge wells
                experiment_name = "qPCR ddCt (ratiometric)",
                assay_type = "qpcr",
                n_plates = 2
            )
        },
        "cell_viability_384" = function() {
            define_experiment(
                plate_format = 384,
                treatments = c(paste0("Compound_", 1:8, "_High"),
                               paste0("Compound_", 1:8, "_Mid"),
                               paste0("Compound_", 1:8, "_Low"),
                               "Vehicle"),
                n_replicates = 4,
                controls = list(positive = "Staurosporine", negative = "DMSO", blank = "Media"),
                n_controls = list(positive = 8, negative = 8, blank = 8),
                edge_strategy = "empty",
                experiment_name = "384-well Cell Viability Screen",
                assay_type = "cell_viability"
            )
        },
        "simple_96" = function() {
            define_experiment(
                plate_format = 96,
                treatments = c("Treatment", "Control"),
                n_replicates = 6,
                controls = list(positive = "Pos_Ctrl", negative = "Neg_Ctrl", blank = "Blank"),
                n_controls = list(positive = 3, negative = 3, blank = 3),
                edge_strategy = "controls_only",
                experiment_name = "Simple 2-Group Comparison",
                assay_type = "general"
            )
        }
    )

    if (!example %in% names(examples)) {
        cat("Available examples:\n")
        for (nm in names(examples)) cat("  -", nm, "\n")
        stop("Unknown example: ", example)
    }

    cat("Loading example experiment: ", example, "\n\n")
    experiment <- examples[[example]]()
    return(experiment)
}

cat("✓ load_example_experiment.R loaded\n")
cat("  Use: experiment <- load_example_experiment('dose_response_96')\n")
cat("  Or:  experiment <- define_experiment(...)\n")
cat("  Available examples: dose_response_96, qpcr_96 (ratiometric ddCt), cell_viability_384, simple_96\n")
