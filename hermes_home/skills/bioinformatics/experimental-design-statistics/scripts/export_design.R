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
# Export Experimental Design Functions
# Generate lab-ready files and documentation

#' Check if batch design uses demo/placeholder sample IDs
#' @param batch_assignment Data frame with batch assignments
#' @return TRUE if sample IDs look like demo placeholders (S01, S02, ...)
.is_demo_data <- function(batch_assignment) {
  if (!"sample_id" %in% colnames(batch_assignment)) return(FALSE)
  ids <- batch_assignment$sample_id
  # Demo data uses S01-S20 pattern from load_example_data()
  all(grepl("^S\\d{2}$", ids))
}

#' Export batch assignment layout for lab use
#'
#' @param batch_assignment Data frame with batch assignments
#' @param output_file Output CSV file path
#' @export
export_batch_layout <- function(batch_assignment, output_file = "batch_layout_for_lab.csv") {

  # Reorder columns for lab convenience
  priority_cols <- c("sample_id", "batch", "condition", "processing_order",
                     "plate", "well", "overall_sequence")

  # Get columns that exist
  existing_priority <- priority_cols[priority_cols %in% colnames(batch_assignment)]
  other_cols <- setdiff(colnames(batch_assignment), existing_priority)

  # Reorder
  export_data <- batch_assignment[, c(existing_priority, other_cols)]

  # Sort by batch and processing order (if available)
  if ("batch" %in% colnames(export_data)) {
    if ("processing_order" %in% colnames(export_data)) {
      export_data <- export_data[order(export_data$batch, export_data$processing_order), ]
    } else {
      export_data <- export_data[order(export_data$batch), ]
    }
  }

  # Check for demo/placeholder data
  is_demo <- .is_demo_data(export_data)

  if (is_demo) {
    # Write CSV with template header comment (dynamic ID range)
    ids <- export_data$sample_id
    id_range <- sprintf("%s-%s", ids[1], ids[length(ids)])
    header_lines <- c(
      sprintf("# TEMPLATE - This batch layout uses EXAMPLE sample IDs (%s)", id_range),
      "# Replace sample_id column with your actual sample identifiers before lab use"
    )
    writeLines(c(header_lines, readLines(textConnection(
      capture.output(write.csv(export_data, stdout(), row.names = FALSE))
    ))), output_file)
  } else {
    write.csv(export_data, output_file, row.names = FALSE)
  }

  message(paste0("Batch layout exported to: ", output_file))
  if (is_demo) {
    ids <- export_data$sample_id
    id_range <- sprintf("%s-%s", ids[1], ids[length(ids)])
    message(sprintf("  \u26a0\ufe0f  TEMPLATE: Uses example sample IDs (%s).", id_range))
    message("     Replace with your actual sample IDs before using in the lab.")
  }
  message(paste0("Samples: ", nrow(export_data)))
  message(paste0("Batches: ", length(unique(export_data$batch))))

  # Return invisibly
  invisible(export_data)
}


#' Export statistical analysis plan
#'
#' @param design_params List with experimental design parameters
#' @param output_file Output markdown file path
#' @export
export_statistical_plan <- function(design_params, output_file = "statistical_analysis_plan.md") {

  # Create markdown document
  plan_text <- paste0(
    "# Statistical Analysis Plan\n\n",
    "**Generated:** ", format(Sys.time(), "%Y-%m-%d %H:%M:%S"), "\n\n",
    "---\n\n",
    "## Experimental Design\n\n",
    "**Assay Type:** ", design_params$assay, "\n\n",
    "**Experimental Groups:**\n",
    "- ", paste(design_params$conditions, collapse = "\n- "), "\n\n",
    "**Sample Size:** ", design_params$n_per_group, " biological replicates per group (",
    design_params$n_per_group * length(design_params$conditions), " total samples)\n\n"
  )

  # Add batch information if present
  if (!is.null(design_params$batches)) {
    plan_text <- paste0(
      plan_text,
      "**Batch Structure:** ", design_params$batches, " processing batches\n",
      "- Each batch contains all experimental conditions to prevent confounding\n\n"
    )
  }

  # Add power analysis results
  if (!is.null(design_params$power)) {
    plan_text <- paste0(
      plan_text,
      "## Power Analysis\n\n",
      "**Statistical Power:** ", round(design_params$power, 3), "\n",
      "**Minimum Detectable Effect:** ", design_params$effect_size, "-fold change\n",
      "**Significance Threshold:** α = ", design_params$alpha, "\n\n"
    )
  }

  # Build model formula from design parameters
  formula_parts <- character()
  if (!is.null(design_params$batches) && design_params$batches > 1) {
    formula_parts <- c(formula_parts, "batch")
  }
  if (!is.null(design_params$covariates)) {
    formula_parts <- c(formula_parts, design_params$covariates)
  }
  formula_parts <- c(formula_parts, "condition")
  model_formula <- paste0("~ ", paste(formula_parts, collapse = " + "))

  # Add statistical methods
  plan_text <- paste0(
    plan_text,
    "## Statistical Methods\n\n",
    "### Differential Expression Analysis\n",
    "- **Method:** DESeq2 (negative binomial model)\n",
    "- **Model formula:** `", model_formula, "`\n",
    "- **Significance threshold:** α = ", design_params$alpha, "\n",
    "- **Multiple testing correction:** ", design_params$multiple_testing, "\n",
    "- **FDR threshold:** < 0.05\n",
    "- **Alternative correction:** Independent Hypothesis Weighting (IHW) for ~5-10% more discoveries at same FDR\n",
    "  - Weights p-values by an independent covariate (e.g., mean expression)\n",
    "  - Recommended when testing >5,000 features\n\n"
  )

  # Add batch correction if needed
  if (!is.null(design_params$batches) && design_params$batches > 1) {
    plan_text <- paste0(
      plan_text,
      "### Batch Effect Correction\n",
      "- **Design:** Batch included in DESeq2 design formula\n",
      "- **Formula:** `", model_formula, "`\n",
      "- Include batch as a covariate to account for batch effects. The batch design ensures batch and condition are not confounded, making this correction valid.\n",
      "- **Alternative methods if needed:** SVA, ComBat, RUVSeq\n\n"
    )
  }

  # Add quality control criteria
  plan_text <- paste0(
    plan_text,
    "## Quality Control Criteria\n\n",
    "### Sample-level QC\n",
    "- **Library size:** > 10 million reads per sample\n",
    "- **Alignment rate:** > 80%\n",
    "- **rRNA contamination:** < 10%\n",
    "- **Sample correlation:** > 0.8 within groups\n\n",
    "### Gene-level QC\n",
    "- **Minimum expression:** CPM > 1 in at least n samples per group\n",
    "- **Filter low-count genes** before differential expression\n\n"
  )

  # Add analysis workflow
  plan_text <- paste0(
    plan_text,
    "## Analysis Workflow\n\n",
    "1. **Quality Control**\n",
    "   - FastQC on raw reads\n",
    "   - Alignment QC (STAR/HISAT2)\n",
    "   - Check library sizes and alignment rates\n\n",
    "2. **Normalization**\n",
    "   - DESeq2 size factor normalization\n",
    "   - Alternative: TMM normalization (edgeR)\n\n",
    "3. **Batch Effect Assessment**\n",
    "   - PCA visualization\n",
    "   - Check for batch-condition confounding\n",
    "   - Apply correction if needed\n\n",
    "4. **Differential Expression**\n",
    "   - DESeq2 analysis\n",
    "   - Multiple testing correction: ", design_params$multiple_testing, "\n",
    "   - Volcano plots and MA plots\n\n",
    "5. **Downstream Analysis**\n",
    "   - GO enrichment analysis\n",
    "   - GSEA pathway analysis\n",
    "   - Validation of top hits\n\n"
  )

  # Add reproducibility section
  plan_text <- paste0(
    plan_text,
    "## Reproducibility\n\n",
    "- **Random seed:** Set to ", if (!is.null(design_params$seed)) design_params$seed else 42, " for all analyses\n",
    "- **Software versions:** Record all R/Bioconductor package versions\n",
    "- **Code repository:** All analysis code version controlled\n",
    "- **Data archiving:** Raw data archived with appropriate accession (GEO/SRA)\n\n",
    "---\n\n",
    "*This statistical analysis plan was generated using the experimental-design-statistics workflow.*\n"
  )

  # Write to file
  writeLines(plan_text, output_file)

  message(paste0("Statistical analysis plan exported to: ", output_file))

  invisible(plan_text)
}


#' Generate lab protocol checklist
#'
#' @param batch_design Data frame with batch assignments (optional)
#' @param metadata_to_record Vector of metadata fields to record
#' @param output_file Output markdown file path
#' @export
generate_lab_protocol <- function(batch_design = NULL,
                                  metadata_to_record = c("date", "operator", "reagent_lots", "instrument"),
                                  output_file = "lab_protocol_checklist.md") {

  protocol_text <- paste0(
    "# Lab Protocol Checklist\n\n",
    "**Generated:** ", format(Sys.time(), "%Y-%m-%d %H:%M:%S"), "\n\n",
    "---\n\n",
    "## Sample Processing Protocol\n\n",
    "Follow this checklist for each processing batch to ensure proper documentation and prevent batch effects.\n\n"
  )

  if (!is.null(batch_design)) {
    n_batches <- length(unique(batch_design$batch))
    protocol_text <- paste0(
      protocol_text,
      "**Total Samples:** ", nrow(batch_design), "\n",
      "**Number of Batches:** ", n_batches, "\n",
      "**Batch Assignment File:** batch_layout_for_lab.csv\n\n"
    )
  }

  protocol_text <- paste0(
    protocol_text,
    "## Before Starting\n\n",
    "- [ ] Review batch assignment file\n",
    "- [ ] Verify all samples are available\n",
    "- [ ] Prepare reagents and check expiration dates\n",
    "- [ ] Record reagent lot numbers\n",
    "- [ ] Calibrate instruments if needed\n",
    "- [ ] Randomize sample positions within plates\n\n",
    "## For Each Batch\n\n",
    "### Documentation (CRITICAL)\n\n",
    "Record the following for each batch:\n\n"
  )

  # Add metadata fields
  metadata_checklist <- c(
    "date" = "- [ ] **Processing date:** YYYY-MM-DD\n",
    "operator" = "- [ ] **Operator/technician:** Name\n",
    "reagent_lots" = "- [ ] **Reagent lot numbers:** All lots used\n",
    "instrument" = "- [ ] **Instrument/equipment ID:** \n",
    "plate" = "- [ ] **Plate/chip barcode:** \n",
    "library_prep" = "- [ ] **Library prep kit:** Name and lot\n",
    "protocol_deviations" = "- [ ] **Protocol deviations:** Note any changes\n"
  )

  for (field in metadata_to_record) {
    if (field %in% names(metadata_checklist)) {
      protocol_text <- paste0(protocol_text, metadata_checklist[[field]])
    }
  }

  protocol_text <- paste0(
    protocol_text,
    "\n### Sample Processing\n\n",
    "- [ ] Samples processed according to batch assignment\n",
    "- [ ] Randomized within batch (avoid systematic patterns)\n",
    "- [ ] Avoid plate edge wells when possible\n",
    "- [ ] Include positive and negative controls\n",
    "- [ ] Record any sample failures or issues\n\n",
    "### Quality Checks During Processing\n\n",
    "- [ ] RNA quality (RIN score if applicable)\n",
    "- [ ] Concentration measurements\n",
    "- [ ] Visual inspection for contamination\n",
    "- [ ] Volume checks\n\n",
    "### Post-Processing\n\n",
    "- [ ] Library QC (Bioanalyzer/TapeStation)\n",
    "- [ ] Quantification (Qubit)\n",
    "- [ ] Pooling calculations\n",
    "- [ ] Submit for sequencing\n\n",
    "## Critical Rules\n\n",
    "1. **NEVER process all samples from one condition in a single batch**\n",
    "   - Each batch must contain samples from all experimental conditions\n",
    "   - This prevents confounding of batch with biological effects\n\n",
    "2. **Document everything**\n",
    "   - Better to record too much than too little\n",
    "   - Metadata essential for diagnosing batch effects later\n\n",
    "3. **Randomize when possible**\n",
    "   - Randomize sample order within batches\n",
    "   - Randomize plate positions\n",
    "   - Avoid processing samples in same order as conditions\n\n",
    "4. **Use controls**\n",
    "   - Process same control sample(s) in each batch\n",
    "   - Enables batch effect correction later\n\n",
    "## Troubleshooting\n\n",
    "**Sample failure:**\n",
    "- Document which sample(s) failed and why\n",
    "- Do NOT replace with different sample from same condition\n",
    "- If replacement needed, process in new batch or proportionally across batches\n\n",
    "**Batch delay:**\n",
    "- Record date and duration of delay\n",
    "- Note any storage condition changes\n",
    "- Document as potential batch covariate\n\n",
    "**Protocol deviation:**\n",
    "- Record exact deviation\n",
    "- Note which samples affected\n",
    "- Discuss with statistician if major deviation\n\n",
    "---\n\n",
    "*This checklist was generated using the experimental-design-statistics workflow.*\n"
  )

  # Write to file
  writeLines(protocol_text, output_file)

  message(paste0("Lab protocol checklist exported to: ", output_file))

  invisible(protocol_text)
}


#' Export all design files in one call
#'
#' @param batch_design Data frame with batch assignments
#' @param design_params List with experimental design parameters
#' @param output_dir Directory for output files (default: current directory)
#' @export
export_complete_design <- function(batch_design,
                                   design_params,
                                   output_dir = ".") {

  # Create output directory if needed
  if (!dir.exists(output_dir)) {
    dir.create(output_dir, recursive = TRUE)
  }

  message("\n=== Exporting Complete Experimental Design ===\n")

  # Export batch layout
  batch_file <- file.path(output_dir, "batch_layout_for_lab.csv")
  export_batch_layout(batch_design, batch_file)

  # Export statistical plan
  plan_file <- file.path(output_dir, "statistical_analysis_plan.md")
  export_statistical_plan(design_params, plan_file)

  # Export lab protocol
  protocol_file <- file.path(output_dir, "lab_protocol_checklist.md")
  generate_lab_protocol(batch_design, output_file = protocol_file)

  # Save design objects as RDS for downstream use (CRITICAL)
  batch_rds <- file.path(output_dir, "batch_design.rds")
  saveRDS(batch_design, batch_rds)
  message(paste0("Saved: ", batch_rds))
  message("  (Load with: batch_design <- readRDS('batch_design.rds'))")

  params_rds <- file.path(output_dir, "design_parameters.rds")
  saveRDS(design_params, params_rds)
  message(paste0("Saved: ", params_rds))
  message("  (Load with: design_params <- readRDS('design_parameters.rds'))")

  # Export power analysis results CSV if power table available
  power_csv <- NULL
  if (!is.null(design_params$power_table)) {
    power_csv <- file.path(output_dir, "power_analysis_results.csv")
    write.csv(design_params$power_table, power_csv, row.names = FALSE)
    message(paste0("Saved: ", power_csv))
  }

  # Also save parameters as JSON for easier reading
  params_json <- file.path(output_dir, "design_parameters.json")
  if (requireNamespace("jsonlite", quietly = TRUE)) {
    jsonlite::write_json(design_params, params_json, pretty = TRUE, auto_unbox = TRUE)
    message(paste0("Saved: ", params_json))
  } else {
    # Fallback: save as text representation if jsonlite not available
    writeLines(capture.output(str(design_params)), params_json)
    message(paste0("Saved: ", params_json, " (as text format)"))
  }

  # Check if demo data
  is_demo <- .is_demo_data(batch_design)

  message("\n=== Export Complete ===")
  message("Files created:")
  if (is_demo) {
    message(paste0("  1. ", batch_file, " - TEMPLATE batch assignments (replace sample IDs with your own)"))
  } else {
    message(paste0("  1. ", batch_file, " - Lab-ready sample assignments"))
  }
  message(paste0("  2. ", plan_file, " - Pre-registration analysis plan"))
  message(paste0("  3. ", protocol_file, " - Lab processing checklist"))
  message(paste0("  4. ", batch_rds, " - Batch design object (for downstream use)"))
  message(paste0("  5. ", params_rds, " - Design parameters (for downstream use)"))
  message(paste0("  6. ", params_json, " - Design parameters (human-readable)"))
  if (!is.null(power_csv)) {
    message(paste0("  7. ", power_csv, " - Power analysis results"))
  }
  if (is_demo) {
    message("\n\u26a0\ufe0f  NOTE: Batch layout uses example/template sample IDs.")
    message("  Regenerate with your actual sample metadata before handing to your lab team.")
  } else {
    message("\nShare these files with your lab team and analysis collaborators.")
  }

  # Return file paths
  invisible(list(
    batch_layout = batch_file,
    statistical_plan = plan_file,
    lab_protocol = protocol_file,
    batch_design_rds = batch_rds,
    design_params_rds = params_rds,
    design_params_json = params_json,
    power_analysis = power_csv
  ))
}
