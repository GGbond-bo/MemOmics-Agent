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
# Batch Assignment Functions
# Create balanced batch designs preventing confounding
# Primary method: anticlust (anticlustering optimization)
# Fallback: stratified random assignment
#
# Based on: Leek et al. (2010) Nat Rev Genet
# anticlustering: Papenberg & Klau (2021) Psychol Methods

#' Assign samples to batches with optimal balance
#'
#' Uses anticlust's anticlustering algorithm to create maximally balanced
#' batch assignments across specified variables. Falls back to stratified
#' random assignment if anticlust is not available.
#'
#' @param metadata Data frame with sample metadata (must include sample IDs)
#' @param batch_size Number of samples per batch
#' @param balance_vars Vector of column names to balance across batches
#' @param sample_id_col Name of sample ID column (default: "sample_id")
#' @return Data frame with batch assignments added
#' @export
#' @examples
#' # Create sample metadata
#' metadata <- data.frame(
#'   sample_id = paste0("S", 1:24),
#'   condition = rep(c("Control", "Treatment"), each = 12),
#'   sex = rep(c("M", "F"), 12),
#'   age_group = rep(c("Young", "Old"), each = 12)
#' )
#'
#' # Generate balanced batch assignment
#' batch_design <- assign_samples_to_batches(
#'   metadata = metadata,
#'   batch_size = 8,
#'   balance_vars = c("condition", "sex", "age_group")
#' )
assign_samples_to_batches <- function(metadata,
                                      batch_size,
                                      balance_vars,
                                      sample_id_col = "sample_id") {

  # Validate inputs
  if (!sample_id_col %in% colnames(metadata)) {
    stop(paste0("Column '", sample_id_col, "' not found in metadata"))
  }

  missing_vars <- balance_vars[!balance_vars %in% colnames(metadata)]
  if (length(missing_vars) > 0) {
    stop(paste0("Balance variables not found in metadata: ", paste(missing_vars, collapse = ", ")))
  }

  if (batch_size <= 0 || batch_size > nrow(metadata)) {
    stop("Invalid batch_size: must be positive and <= number of samples")
  }

  # Calculate number of batches
  n_batches <- ceiling(nrow(metadata) / batch_size)

  message("Generating optimal batch assignment...")

  tryCatch({
    if (!requireNamespace("anticlust", quietly = TRUE)) {
      stop("anticlust not available")
    }

    # Prepare features for anticlustering
    # Convert categorical variables to numeric for distance computation
    feature_matrix <- data.frame(row.names = seq_len(nrow(metadata)))
    for (var in balance_vars) {
      if (is.numeric(metadata[[var]])) {
        feature_matrix[[var]] <- scale(metadata[[var]])
      } else {
        # One-hot encode categorical variables
        levels_var <- unique(metadata[[var]])
        for (lev in levels_var[-1]) {  # drop first level (reference)
          col_name <- paste0(var, "_", lev)
          feature_matrix[[col_name]] <- as.numeric(metadata[[var]] == lev)
        }
      }
    }

    # Primary categorical constraint: first balance variable (usually condition)
    primary_categories <- as.factor(metadata[[balance_vars[1]]])

    # Run anticlustering
    batch_assignments <- anticlust::anticlustering(
      x = feature_matrix,
      K = n_batches,
      categories = primary_categories,
      method = "exchange"
    )

    metadata$batch <- batch_assignments

    # Reorder by batch
    metadata <- metadata[order(metadata$batch), ]

    attr(metadata, "method") <- "anticlust"
    cat("\n✓ Batch design generated successfully! (method: anticlust)\n")
    batch_sizes <- table(metadata$batch)
    if (length(unique(batch_sizes)) == 1) {
      cat(sprintf("  Created %d batches of %d samples each\n", n_batches, batch_sizes[1]))
    } else {
      cat(sprintf("  Created %d batches (%d-%d samples each)\n", n_batches, min(batch_sizes), max(batch_sizes)))
    }
    cat(sprintf("  Balanced variables: %s\n", paste(balance_vars, collapse = ", ")))

    return(metadata)

  }, error = function(e) {
    # Fallback to stratified random assignment
    if (grepl("anticlust not available", e$message)) {
      cat("\n⚠️  anticlust not installed. Using stratified random assignment.\n")
    } else {
      cat("\n⚠️  anticlust optimization failed. Falling back to stratified random assignment.\n")
      cat("   Reason:", conditionMessage(e), "\n")
    }
    cat("   Note: Verify balance with check_confounding() from batch_validation.R\n")
    return(assign_samples_stratified(metadata, n_batches, balance_vars, sample_id_col))
  })
}


#' Stratified random assignment (fallback)
#'
#' Splits samples of each level of the primary variable evenly across batches,
#' then randomizes within strata. Guarantees perfect balance on the primary
#' variable when group sizes are divisible by n_batches.
#'
#' @keywords internal
assign_samples_stratified <- function(metadata, n_batches, balance_vars, sample_id_col) {

  primary_var <- balance_vars[1]
  metadata$batch <- NA

  set.seed(123)  # For reproducibility

  # For each level of the primary variable, distribute evenly across batches
  for (level in unique(metadata[[primary_var]])) {
    level_idx <- which(metadata[[primary_var]] == level)
    n_level <- length(level_idx)

    # Create balanced batch assignments for this stratum
    batch_assign <- rep(1:n_batches, length.out = n_level)
    # Randomize within this stratum
    metadata$batch[level_idx] <- sample(batch_assign)
  }

  # Reorder by batch
  metadata <- metadata[order(metadata$batch), ]

  attr(metadata, "method") <- "stratified_random"
  cat("\n✓ Batch design generated successfully! (method: stratified_random)\n")
  batch_sizes <- table(metadata$batch)
  if (length(unique(batch_sizes)) == 1) {
    cat(sprintf("  Created %d batches of %d samples each\n", n_batches, batch_sizes[1]))
  } else {
    cat(sprintf("  Created %d batches (%d-%d samples each)\n", n_batches, min(batch_sizes), max(batch_sizes)))
  }
  cat(sprintf("  Balanced on '%s'\n", primary_var))

  return(metadata)
}


#' Generate incomplete block design when complete balance is impossible
#'
#' @param metadata Data frame with sample metadata
#' @param batch_size Number of samples per batch
#' @param primary_var Primary variable that MUST be balanced (no confounding)
#' @param secondary_vars Secondary variables to balance as much as possible
#' @param constraints List of additional constraints
#' @return Data frame with batch assignments
#' @export
incomplete_block_design <- function(metadata,
                                    batch_size,
                                    primary_var,
                                    secondary_vars = NULL,
                                    constraints = NULL) {

  # Validate that primary variable exists
  if (!primary_var %in% colnames(metadata)) {
    stop(paste0("Primary variable '", primary_var, "' not found in metadata"))
  }

  # Get levels of primary variable
  primary_levels <- unique(metadata[[primary_var]])
  n_levels <- length(primary_levels)

  # Check if complete balance is possible
  if (batch_size %% n_levels != 0) {
    message("Batch size not evenly divisible by number of conditions.")
    message("Creating incomplete block design...")
  }

  # Ensure each batch has all levels of primary variable
  n_samples <- nrow(metadata)
  n_batches <- ceiling(n_samples / batch_size)

  # Create stratified assignment
  metadata$batch <- NA

  batch_num <- 1
  samples_in_current_batch <- 0

  # Cycle through conditions
  while (any(is.na(metadata$batch))) {
    for (level in primary_levels) {
      # Find unassigned samples for this level
      eligible <- which(metadata[[primary_var]] == level & is.na(metadata$batch))

      if (length(eligible) > 0 && samples_in_current_batch < batch_size) {
        # Assign one sample from this level to current batch
        metadata$batch[eligible[1]] <- batch_num
        samples_in_current_batch <- samples_in_current_batch + 1

        if (samples_in_current_batch >= batch_size) {
          batch_num <- batch_num + 1
          samples_in_current_batch <- 0
        }
      }
    }
  }

  message("Incomplete block design created")
  message(paste0("Primary variable '", primary_var, "' is balanced across batches"))

  return(metadata)
}


#' Generate randomization scheme within batches
#'
#' @param batch_metadata Data frame with batch assignments
#' @param randomize_within Should samples be randomized within batches? (default: TRUE)
#' @return Data frame with processing order added
#' @export
add_processing_order <- function(batch_metadata,
                                 randomize_within = TRUE) {

  if (!"batch" %in% colnames(batch_metadata)) {
    stop("Metadata must contain 'batch' column")
  }

  # Add processing order within each batch
  batch_metadata$processing_order <- NA

  for (b in unique(batch_metadata$batch)) {
    batch_rows <- which(batch_metadata$batch == b)

    if (randomize_within) {
      # Randomize order within batch
      set.seed(b)  # Different seed per batch for reproducibility
      shuffled_order <- sample(seq_along(batch_rows))
      batch_metadata$processing_order[batch_rows] <- shuffled_order
    } else {
      # Keep existing order
      batch_metadata$processing_order[batch_rows] <- seq_along(batch_rows)
    }
  }

  # Add overall processing sequence
  batch_metadata <- batch_metadata[order(batch_metadata$batch, batch_metadata$processing_order), ]
  batch_metadata$overall_sequence <- 1:nrow(batch_metadata)

  return(batch_metadata)
}


#' Add plate position assignments to avoid edge effects
#'
#' @param batch_metadata Data frame with batch assignments
#' @param plate_format Plate format (default: "96-well")
#' @return Data frame with well positions added
#' @export
add_plate_positions <- function(batch_metadata,
                                plate_format = "96-well") {

  if (!"batch" %in% colnames(batch_metadata)) {
    stop("Metadata must contain 'batch' column")
  }

  # Define plate dimensions
  plate_formats <- list(
    "96-well" = list(rows = 8, cols = 12),
    "384-well" = list(rows = 16, cols = 24),
    "48-well" = list(rows = 6, cols = 8)
  )

  if (!plate_format %in% names(plate_formats)) {
    stop(paste0("Plate format not recognized. Choose from: ", paste(names(plate_formats), collapse = ", ")))
  }

  dims <- plate_formats[[plate_format]]

  # Generate well positions (avoid edges)
  row_letters <- LETTERS[1:dims$rows]
  col_numbers <- 1:dims$cols

  # Create all positions
  all_positions <- expand.grid(row = row_letters, col = col_numbers, stringsAsFactors = FALSE)
  all_positions$well <- paste0(all_positions$row, sprintf("%02d", all_positions$col))

  # Mark edge positions
  all_positions$is_edge <- (
    all_positions$row == row_letters[1] |
    all_positions$row == row_letters[dims$rows] |
    all_positions$col == 1 |
    all_positions$col == dims$cols
  )

  # Assign positions to samples (prefer non-edge)
  batch_metadata$plate <- NA
  batch_metadata$well <- NA
  batch_metadata$is_edge_well <- NA

  plate_num <- 1
  position_idx <- 1

  # First assign non-edge positions
  non_edge_positions <- all_positions[!all_positions$is_edge, ]

  for (i in 1:nrow(batch_metadata)) {
    if (position_idx > nrow(non_edge_positions)) {
      # Start new plate or use edge positions
      plate_num <- plate_num + 1
      position_idx <- 1
    }

    batch_metadata$plate[i] <- plate_num
    batch_metadata$well[i] <- non_edge_positions$well[position_idx]
    batch_metadata$is_edge_well[i] <- FALSE
    position_idx <- position_idx + 1
  }

  message(paste0("Assigned samples to ", plate_num, " plates (", plate_format, ")"))
  message("Avoided edge wells when possible")

  return(batch_metadata)
}
