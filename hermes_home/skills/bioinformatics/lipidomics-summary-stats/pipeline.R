#!/usr/bin/env Rscript
#
# lipidomics-summary-stats pipeline
# Reads CL + FS Excel files, computes log2FC and p-values for all comparisons,
# and outputs a styled master Excel workbook.
#
# Data layout (both CL and FS):
#   Rows = samples (1 per mouse), Columns = metabolites
#   First 4 columns: SampleID, Genotype, Virus, Condition
#   Remaining columns: metabolite concentrations
#
# Usage:
#   Rscript pipeline.R --cl <cl_file> --fs <fs_file> [--output <outfile>]

# ── Setup ──────────────────────────────────────────────────────────────────────
args <- commandArgs(trailingOnly = TRUE)

parse_args <- function(args) {
  params <- list()
  i <- 1
  while (i <= length(args)) {
    if (startsWith(args[i], "--")) {
      key <- sub("^--", "", args[i])
      if (i + 1 <= length(args) && !startsWith(args[i + 1], "--")) {
        params[[key]] <- args[i + 1]
        i <- i + 2
      } else {
        params[[key]] <- TRUE
        i <- i + 1
      }
    } else {
      i <- i + 1
    }
  }
  params
}

params <- parse_args(args)

cl_file <- params$cl
fs_file <- params$fs
output_file <- params$output

if (is.null(cl_file) || is.null(fs_file)) {
  stop("Usage: Rscript pipeline.R --cl <cl_file> --fs <fs_file> [--output <outfile>]")
}

if (is.null(output_file)) {
  output_file <- "CL_FS_Master_Summary_Statistics.xlsx"
}

# ── Load packages ──────────────────────────────────────────────────────────────
lib_path <- "/mnt/shared-workspace/r-libs"
if (dir.exists(lib_path)) .libPaths(c(lib_path, .libPaths()))

suppressPackageStartupMessages({
  library(readxl)
  library(openxlsx)
})

# ── Default parameters ─────────────────────────────────────────────────────────
sample_key <- data.frame(
  SampleID = as.character(1:21),
  Condition = c("WT","WT","WT","WT","WT","WT",
                "Cpt2/Cpt1-DKO","Cpt2/Cpt1-DKO","Cpt2/Cpt1-DKO",
                "Cpt2/Tsc1-DKO","Cpt2/Tsc1-DKO","Cpt2/Tsc1-DKO",
                "Tsc1-KO","Tsc1-KO","Tsc1-KO",
                "Cpt1-KO","Cpt1-KO","Cpt1-KO",
                "Cpt2-KO","Cpt2-KO","Cpt2-KO"),
  stringsAsFactors = FALSE
)

condition_order <- c("WT","Cpt2-KO","Cpt1-KO","Tsc1-KO","Cpt2/Cpt1-DKO","Cpt2/Tsc1-DKO")
fc_threshold <- 1.0
p_threshold  <- 0.05
min_per_group <- 2

# CL tab-to-class mapping (regex patterns -> class label)
# Uses case-insensitive matching to handle "SM data" vs "SM Data" etc.
cl_tab_patterns <- c(
  "^PC data$"="PC", "^P-PC data$"="P-PC", "^O-PC data$"="O-PC",
  "^LPC data$"="LPC",
  "^PE data$"="PE", "^P-PE data$"="P-PE",
  "^LPE data$"="LPE",
  "^PS data$"="PS", "^LPS data$"="LPS",
  "^PI data$"="PI", "^PG data$"="PG",
  "^SM [Dd]ata$"="SM", "^Cer [Dd]ata$"="Cer",
  "^TG [Dd]ata$"="TG", "^DG [Dd]ata$"="DG",
  "^AC [Dd]ata$"="AC", "^CE [Dd]ata$"="CE"
)

# 9 comparisons: (KO, Reference)
comparisons <- list(
  c("Cpt2-KO",          "WT"),
  c("Cpt1-KO",          "WT"),
  c("Tsc1-KO",          "WT"),
  c("Cpt2/Cpt1-DKO",    "WT"),
  c("Cpt2/Tsc1-DKO",    "WT"),
  c("Cpt1-KO",          "Cpt2-KO"),
  c("Tsc1-KO",          "Cpt2-KO"),
  c("Cpt2/Cpt1-DKO",    "Cpt2-KO"),
  c("Cpt2/Tsc1-DKO",    "Cpt2-KO")
)

comp_names <- sapply(comparisons, function(c) paste0(c[1], "/", c[2]))

# ── Helper: match sheet names to class labels ─────────────────────────────────
match_sheets_to_classes <- function(sheets, patterns) {
  result <- character(0)
  for (s in sheets) {
    for (pat in names(patterns)) {
      if (grepl(pat, s, ignore.case = TRUE)) {
        result[s] <- patterns[pat]
        break
      }
    }
  }
  result
}

# ── Helper: compute FC and p-value for one comparison ───────────────────────────
compute_fc_pv_one <- function(vals_by_sample, ko_cond, ref_cond, skey, min_n = 2) {
  ko_ids  <- skey$SampleID[skey$Condition == ko_cond]
  ref_ids <- skey$SampleID[skey$Condition == ref_cond]

  ko_vals  <- as.numeric(vals_by_sample[ko_ids])
  ref_vals <- as.numeric(vals_by_sample[ref_ids])
  ko_vals  <- ko_vals[!is.na(ko_vals)  & ko_vals > 0]
  ref_vals <- ref_vals[!is.na(ref_vals) & ref_vals > 0]

  fc <- NA_real_
  pv <- NA_real_
  if (length(ko_vals) >= min_n && length(ref_vals) >= min_n) {
    fc <- mean(log2(ko_vals)) - mean(log2(ref_vals))
    tryCatch({
      pv <- t.test(log2(ko_vals), log2(ref_vals))$p.value
    }, error = function(e) { pv <- NA_real_ })
  }
  list(fc = fc, pv = pv)
}

# ── Helper: read one CL tab and return metabolite-level data ──────────────────
read_cl_tab <- function(path, sheet_name, skey) {
  raw <- suppressWarnings(read_excel(path, sheet = sheet_name, skip = 7))

  # Row 1 is the real header (metabolite names)
  hdr <- as.character(raw[1, ])
  hdr[1:4] <- c("SampleID", "Genotype", "Virus", "Condition")
  df <- raw[-1, ]
  names(df) <- hdr

  # Filter to numeric sample IDs only
  df <- df[!is.na(df$SampleID) & grepl("^[0-9]+$", df$SampleID), ]

  # Identify metabolite columns (skip first 4 metadata + any Total columns)
  all_cols <- names(df)[5:length(names(df))]
  metab_cols <- all_cols[!grepl("^Total", all_cols)]

  # Build transposed matrix: rows = metabolites, cols = samples
  sample_ids <- as.character(df$SampleID)
  n_met <- length(metab_cols)

  mat <- data.frame(matrix(NA_real_, nrow = n_met, ncol = length(sample_ids)))
  colnames(mat) <- sample_ids
  rownames(mat) <- metab_cols

  for (j in seq_along(metab_cols)) {
    mat[j, ] <- as.numeric(df[[metab_cols[j]]])
  }

  conc_unit <- rep("pmol/mg", n_met)

  list(metab_names = metab_cols, mat = mat, conc_unit = conc_unit)
}

# ── Helper: read FS data ──────────────────────────────────────────────────────
read_fs_data <- function(path, skey) {
  raw <- suppressWarnings(read_excel(path, sheet = 1, skip = 8))

  # FS has proper headers already
  df <- raw[!is.na(raw[[1]]) & grepl("^[0-9]+$", as.character(raw[[1]])), ]

  all_cols <- names(df)[5:length(names(df))]
  metab_cols <- all_cols[!grepl("^Total", all_cols)]

  sample_ids <- as.character(df[[1]])
  n_met <- length(metab_cols)

  mat <- data.frame(matrix(NA_real_, nrow = n_met, ncol = length(sample_ids)))
  colnames(mat) <- sample_ids
  rownames(mat) <- metab_cols

  for (j in seq_along(metab_cols)) {
    mat[j, ] <- as.numeric(df[[metab_cols[j]]])
  }

  conc_unit <- rep("ng/mg", n_met)

  list(metab_names = metab_cols, mat = mat, conc_unit = conc_unit)
}

# ── Helper: build full data.frame for one class ───────────────────────────────
build_class_df <- function(class_name, mat, conc_units, skey, cond_order,
                           comp_list, comp_nms, min_n = 2) {
  n_met <- nrow(mat)
  met_names <- rownames(mat)

  # n per condition
  n_cols <- list()
  for (cond in cond_order) {
    ids <- skey$SampleID[skey$Condition == cond]
    cols <- which(colnames(mat) %in% ids)
    n_cols[[paste0("n.", cond)]] <- apply(mat[, cols, drop = FALSE], 1, function(r) {
      v <- as.numeric(r)
      sum(!is.na(v) & v > 0)
    })
  }
  n_df <- as.data.frame(n_cols, check.names = FALSE)

  # Sample columns
  sample_cols <- list()
  for (sid in skey$SampleID) {
    cond <- skey$Condition[skey$SampleID == sid]
    colname <- paste0("Sample.", sid, "(", cond, ")")
    if (sid %in% colnames(mat)) {
      sample_cols[[colname]] <- as.numeric(mat[, sid])
    } else {
      sample_cols[[colname]] <- rep(NA_real_, n_met)
    }
  }
  sample_df <- as.data.frame(sample_cols, check.names = FALSE)

  # Means per condition
  mean_cols <- list()
  for (cond in cond_order) {
    ids <- skey$SampleID[skey$Condition == cond]
    cols <- which(colnames(mat) %in% ids)
    mean_cols[[paste0("Mean.", cond)]] <- apply(mat[, cols, drop = FALSE], 1, function(r) {
      v <- as.numeric(r)
      v <- v[!is.na(v) & v > 0]
      if (length(v) > 0) mean(v) else NA_real_
    })
  }
  mean_df <- as.data.frame(mean_cols, check.names = FALSE)

  # Log2 means per condition
  log2_mean_cols <- list()
  for (cond in cond_order) {
    ids <- skey$SampleID[skey$Condition == cond]
    cols <- which(colnames(mat) %in% ids)
    log2_mean_cols[[paste0("Log2.Mean.", cond)]] <- apply(mat[, cols, drop = FALSE], 1, function(r) {
      v <- as.numeric(r)
      v <- v[!is.na(v) & v > 0]
      if (length(v) > 0) mean(log2(v)) else NA_real_
    })
  }
  log2_mean_df <- as.data.frame(log2_mean_cols, check.names = FALSE)

  # Log2FC and p-value for each comparison
  fc_cols <- list()
  pv_cols <- list()
  for (j in seq_along(comp_list)) {
    ko  <- comp_list[[j]][1]
    ref <- comp_list[[j]][2]
    fc_vec <- rep(NA_real_, n_met)
    pv_vec <- rep(NA_real_, n_met)
    for (i in seq_len(n_met)) {
      vals <- as.numeric(mat[i, ])
      names(vals) <- colnames(mat)
      res <- compute_fc_pv_one(vals, ko, ref, skey, min_n)
      fc_vec[i] <- res$fc
      pv_vec[i] <- res$pv
    }
    fc_cols[[paste0("Log2.FC.", comp_nms[j])]] <- fc_vec
    pv_cols[[paste0("p-value.", comp_nms[j])]] <- pv_vec
  }
  fc_df <- as.data.frame(fc_cols, check.names = FALSE)
  pv_df <- as.data.frame(pv_cols, check.names = FALSE)

  # Assemble
  out <- data.frame(
    Class = class_name,
    Metabolite = met_names,
    Concentration.Unit = conc_units,
    stringsAsFactors = FALSE
  )
  out <- cbind(out, n_df, sample_df, mean_df, log2_mean_df, fc_df, pv_df)
  out
}

# ── Step 1: Read Complex Lipid Data ────────────────────────────────────────────
cat("Reading complex lipid data from:", cl_file, "\n")
cl_sheets <- excel_sheets(cl_file)

cl_tab_map <- match_sheets_to_classes(cl_sheets, cl_tab_patterns)
cat("  Matched tabs:", paste(names(cl_tab_map), "->", cl_tab_map, collapse=", "), "\n")

class_dfs <- list()

for (s in names(cl_tab_map)) {
  class_name <- cl_tab_map[s]
  cat("  Processing tab:", s, "-> Class:", class_name, "\n")

  res <- read_cl_tab(cl_file, s, sample_key)
  mat <- res$mat
  conc_units <- res$conc_unit

  # Drop metabolites where ALL values are NA (completely undetected)
  all_na <- apply(mat, 1, function(r) all(is.na(r)))
  mat <- mat[!all_na, , drop = FALSE]
  conc_units <- conc_units[!all_na]

  df <- build_class_df(class_name, mat, conc_units, sample_key,
                       condition_order, comparisons, comp_names, min_per_group)
  class_dfs[[class_name]] <- df
  cat("    ", nrow(df), "metabolites\n")
}

# ── Step 2: Read Free Sterol Data ─────────────────────────────────────────────
cat("Reading free sterol data from:", fs_file, "\n")

fs_res <- read_fs_data(fs_file, sample_key)
mat_fs <- fs_res$mat
conc_units_fs <- fs_res$conc_unit

# Keep all FS metabolites (even those with all-zero values)
# The original analysis retained them with Mean=0, n=0

df_fs <- build_class_df("FS", mat_fs, conc_units_fs, sample_key,
                        condition_order, comparisons, comp_names, min_per_group)
class_dfs[["FS"]] <- df_fs
cat("  FS:", nrow(df_fs), "metabolites\n")

# ── Step 3: Combine into Unified DataFrames ────────────────────────────────────
cat("Combining data into unified data frames...\n")

all_data <- do.call(rbind, class_dfs)
rownames(all_data) <- NULL

# Significant FC Summary
sig_rows <- list()
for (class_name in names(class_dfs)) {
  df <- class_dfs[[class_name]]
  for (j in seq_along(comparisons)) {
    comp <- comp_names[j]
    fc_col <- paste0("Log2.FC.", comp)
    pv_col <- paste0("p-value.", comp)
    if (fc_col %in% colnames(df) && pv_col %in% colnames(df)) {
      fc_vals <- df[[fc_col]]
      pv_vals <- df[[pv_col]]
      sig <- which(!is.na(fc_vals) & !is.na(pv_vals) &
                   abs(fc_vals) > fc_threshold & pv_vals < p_threshold)
      if (length(sig) > 0) {
        sig_rows[[length(sig_rows) + 1]] <- data.frame(
          Class = df$Class[sig],
          Metabolite = df$Metabolite[sig],
          Comparison = comp,
          Log2.FC = fc_vals[sig],
          P.value = pv_vals[sig],
          Direction = ifelse(fc_vals[sig] > 0, "Up", "Down"),
          stringsAsFactors = FALSE
        )
      }
    }
  }
}
sig_summary <- do.call(rbind, sig_rows)
rownames(sig_summary) <- NULL

cat("  Total metabolites:", nrow(all_data), "\n")
cat("  Significant hits:", nrow(sig_summary), "\n")

# ── Step 4: Write Styled Excel Workbook ────────────────────────────────────────
cat("Writing styled Excel workbook...\n")

wb <- createWorkbook()

header_style <- createStyle(
  fontColour = "#FFFFFF",
  fgFill = "#4472C4",
  halign = "center",
  textDecoration = "bold",
  border = "TopBottomLeftRight",
  borderColour = "#B4C6E7",
  borderStyle = "thin"
)

data_style <- createStyle(
  border = "TopBottomLeftRight",
  borderColour = "#D9D9D9",
  borderStyle = "thin",
  halign = "center"
)

num_style_4 <- createStyle(
  border = "TopBottomLeftRight",
  borderColour = "#D9D9D9",
  borderStyle = "thin",
  halign = "center",
  numFmt = "0.0000"
)

num_style_2 <- createStyle(
  border = "TopBottomLeftRight",
  borderColour = "#D9D9D9",
  borderStyle = "thin",
  halign = "center",
  numFmt = "0.00"
)

add_data_sheet <- function(wb, sheet_name, df) {
  addWorksheet(wb, sheet_name)
  writeData(wb, sheet_name, df, headerStyle = header_style, withFilter = FALSE)

  n_rows <- nrow(df) + 1
  for (col_idx in seq_len(ncol(df))) {
    col_name <- colnames(df)[col_idx]
    if (grepl("^(Log2\\.FC\\.|p-value\\.|Log2\\.Mean\\.)", col_name)) {
      addStyle(wb, sheet_name, style = num_style_4,
               rows = 2:n_rows, cols = col_idx, gridExpand = TRUE)
    } else if (grepl("^(Mean\\.|Sample\\.|n\\.)", col_name)) {
      addStyle(wb, sheet_name, style = num_style_2,
               rows = 2:n_rows, cols = col_idx, gridExpand = TRUE)
    } else {
      addStyle(wb, sheet_name, style = data_style,
               rows = 2:n_rows, cols = col_idx, gridExpand = TRUE)
    }
  }

  setColWidths(wb, sheet_name, cols = seq_len(ncol(df)), widths = "auto")
  freezePane(wb, sheet_name, firstRow = TRUE)
}

add_data_sheet(wb, "All Data", all_data)
add_data_sheet(wb, "Significant FC Summary", sig_summary)

class_order <- c("PC","P-PC","O-PC","LPC","PE","P-PE","LPE","PS","LPS",
                 "PI","PG","SM","Cer","TG","DG","AC","CE","FS")
for (cn in class_order) {
  if (cn %in% names(class_dfs)) {
    add_data_sheet(wb, cn, class_dfs[[cn]])
  }
}

# Write to /workspace first, then shell cp to /mnt/results
tmp_path <- file.path("/workspace", output_file)
saveWorkbook(wb, tmp_path, overwrite = TRUE)

dest <- file.path("/mnt/results", output_file)
system(paste0("cp ", shQuote(tmp_path), " ", shQuote(dest)))

cat("Done! Output:", dest, "\n")
cat("  Sheets:", length(wb$sheet_names), "\n")
cat("  All Data rows:", nrow(all_data), "\n")
cat("  Significant hits:", nrow(sig_summary), "\n")
