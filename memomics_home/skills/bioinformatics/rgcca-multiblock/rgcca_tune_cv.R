#!/usr/bin/env Rscript
# rgcca_tune_cv.R — Cross-validation tuning via rgcca_cv().
#
# Usage:
#   Rscript rgcca_tune_cv.R \
#     --blocks_dir   <dir_containing_per_block_csvs> \
#     --connection   <connection_matrix.csv> \
#     --cv_params    <cv_config.json> \
#     --base_params  <base_params.json> \
#     --out_dir      <output_directory> \
#     --seed         <integer>
#
# cv_config.json keys:
#   par_type         : "tau" | "sparsity" | "ncomp"
#   par_value        : array of candidate values
#   k                : number of CV folds (default 5)
#   n_run            : number of CV repetitions (default 1)
#   metric           : "cor" | "rmse" | "accuracy" (default "cor")
#   prediction_model : "lm" | "lda" | etc. (default "lm")
#   response_idx     : 1-based index of response block (required for supervised CV)
#
# Outputs written to <out_dir>/:
#   cv_best_params.json   — best_params from rgcca_cv result
#   cv_stats.csv          — full cv$stats table
#   cv_plot.png           — plot(cv_res)
#   cv_plot.svg           — plot(cv_res)

suppressPackageStartupMessages({
  if (!requireNamespace("RGCCA", quietly = TRUE)) {
    install.packages("RGCCA", repos = "https://cran.r-project.org", quiet = TRUE)
  }
  library(RGCCA)
  library(jsonlite)
  library(ggplot2)
})
.svg_device <- if (requireNamespace("svglite", quietly = TRUE)) "svglite" else if (capabilities("cairo")) "cairo_svg" else "none"

# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------
args <- commandArgs(trailingOnly = TRUE)

get_arg <- function(flag, args, required = TRUE, default = NULL) {
  idx <- which(args == flag)
  if (length(idx) == 0) {
    if (required) stop(paste("Missing required argument:", flag))
    return(default)
  }
  if (idx + 1 > length(args)) stop(paste("No value provided for argument:", flag))
  args[idx + 1]
}

blocks_dir   <- get_arg("--blocks_dir",  args)
conn_file    <- get_arg("--connection",  args)
cv_file      <- get_arg("--cv_params",   args)
base_file    <- get_arg("--base_params", args)
out_dir      <- get_arg("--out_dir",     args)
seed_val     <- as.integer(get_arg("--seed", args, required = FALSE, default = "42"))

dir.create(out_dir, recursive = TRUE, showWarnings = FALSE)
set.seed(seed_val)

# ---------------------------------------------------------------------------
# Load blocks
# ---------------------------------------------------------------------------
block_files <- sort(list.files(blocks_dir, pattern = "\\.csv$", full.names = TRUE))
blocks <- list()
for (bf in block_files) {
  bname <- tools::file_path_sans_ext(basename(bf))
  mat   <- as.matrix(read.csv(bf, row.names = 1, check.names = FALSE))
  storage.mode(mat) <- "double"
  blocks[[bname]] <- mat
}
cat(sprintf("Loaded %d block(s) for CV tuning.\n", length(blocks)))

# ---------------------------------------------------------------------------
# Load connection matrix
# ---------------------------------------------------------------------------
conn_df    <- read.csv(conn_file, row.names = 1, check.names = FALSE)
connection <- as.matrix(conn_df)
storage.mode(connection) <- "double"
block_order <- names(blocks)
connection  <- connection[block_order, block_order]

# ---------------------------------------------------------------------------
# Load parameters
# ---------------------------------------------------------------------------
cv_params   <- fromJSON(cv_file)
base_params <- fromJSON(base_file)

par_type         <- cv_params$par_type
par_value        <- as.numeric(cv_params$par_value)
k                <- if (!is.null(cv_params$k))                as.integer(cv_params$k)                else 5L
n_run            <- if (!is.null(cv_params$n_run))            as.integer(cv_params$n_run)            else 1L
metric           <- if (!is.null(cv_params$metric))           cv_params$metric                       else "RMSE"
prediction_model <- if (!is.null(cv_params$prediction_model)) cv_params$prediction_model             else "lm"
response_idx     <- if (!is.null(cv_params$response_idx))     as.integer(cv_params$response_idx)     else NULL

J <- length(blocks)

# Base RGCCA params (used as fixed context for CV)
method      <- if (!is.null(base_params$method))      base_params$method      else "rgcca"
scheme      <- if (!is.null(base_params$scheme))      base_params$scheme      else "factorial"
scale       <- if (!is.null(base_params$scale))       base_params$scale       else TRUE
scale_block <- if (!is.null(base_params$scale_block)) base_params$scale_block else "inertia"
NA_method   <- if (!is.null(base_params$NA_method))   base_params$NA_method   else "na.ignore"
superblock  <- if (!is.null(base_params$superblock))  base_params$superblock  else FALSE
comp_orth   <- if (!is.null(base_params$comp_orth))   base_params$comp_orth   else TRUE

# ncomp and tau/sparsity: use base values as fixed when not the tuned parameter
expand_param <- function(val, n) {
  if (is.null(val)) return(NULL)
  if (length(val) == 1) return(rep(val, n))
  val
}
ncomp    <- expand_param(base_params$ncomp,    J)
tau      <- expand_param(base_params$tau,      J)
sparsity <- expand_param(base_params$sparsity, J)

cat(sprintf(
  "Running rgcca_cv: par_type=%s, %d candidate values, k=%d, n_run=%d, metric=%s\n",
  par_type, length(par_value), k, n_run, metric
))

# ---------------------------------------------------------------------------
# Run CV
# ---------------------------------------------------------------------------
cv_args <- list(
  blocks           = blocks,
  method           = method,
  par_type         = par_type,
  par_value        = par_value,
  k                = k,
  n_run            = n_run,
  metric           = metric,
  prediction_model = prediction_model,
  quiet            = TRUE,
  scale            = scale,
  scale_block      = scale_block,
  NA_method        = NA_method,
  superblock       = superblock,
  comp_orth        = comp_orth,
  ncomp            = ncomp,
  tau              = tau,
  sparsity         = sparsity
)
if (!is.null(response_idx)) cv_args$response <- response_idx

cv_res <- tryCatch(
  do.call(rgcca_cv, cv_args),
  error = function(e) stop(paste("rgcca_cv() failed:", conditionMessage(e)))
)

cat("CV tuning complete.\n")

# ---------------------------------------------------------------------------
# Save outputs
# ---------------------------------------------------------------------------

# Best params
best <- as.list(cv_res$best_params)
write(toJSON(best, auto_unbox = TRUE, pretty = TRUE),
      file.path(out_dir, "cv_best_params.json"))

# Stats table
if (!is.null(cv_res$stats)) {
  write.csv(cv_res$stats, file.path(out_dir, "cv_stats.csv"), row.names = FALSE)
}

# Summary
summary_text <- capture.output(summary(cv_res))
writeLines(summary_text, file.path(out_dir, "cv_summary.txt"))

# Plots
p <- tryCatch(plot(cv_res), error = function(e) NULL)
if (!is.null(p)) {
  ggsave(file.path(out_dir, "cv_plot.png"), plot = p, width = 8, height = 5, dpi = 300)
  if (.svg_device != "none") {
    tryCatch({
      dev_fn <- if (.svg_device == "svglite") svglite::svglite else "svg"
      ggsave(file.path(out_dir, "cv_plot.svg"), plot = p, width = 8, height = 5, device = dev_fn)
    }, error = function(e) cat("NOTE: SVG save skipped:", conditionMessage(e), "\n"))
  }
  cat("CV plot saved.\n")
}

cat(sprintf("CV best params: %s\n",
    paste(names(best), unlist(best), sep = "=", collapse = ", ")))
