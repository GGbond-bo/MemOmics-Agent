#!/usr/bin/env Rscript
# rgcca_tune_perm.R — Permutation-based tuning via rgcca_permutation().
#
# Usage:
#   Rscript rgcca_tune_perm.R \
#     --blocks_dir   <dir_containing_per_block_csvs> \
#     --connection   <connection_matrix.csv> \
#     --perm_params  <perm_config.json> \
#     --base_params  <base_params.json> \
#     --out_dir      <output_directory> \
#     --seed         <integer>
#
# perm_config.json keys:
#   par_type   : "tau" | "sparsity"
#   par_value  : array of candidate values
#   n_perms    : number of permutations (default 100)
#
# Outputs written to <out_dir>/:
#   perm_best_params.json   — best_params from rgcca_permutation result
#   perm_stats.csv          — permcrit table
#   perm_plot.png           — plot(perm_res)
#   perm_plot.svg           — plot(perm_res)
#   perm_summary.txt        — summary(perm_res)

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

blocks_dir  <- get_arg("--blocks_dir",  args)
conn_file   <- get_arg("--connection",  args)
perm_file   <- get_arg("--perm_params", args)
base_file   <- get_arg("--base_params", args)
out_dir     <- get_arg("--out_dir",     args)
seed_val    <- as.integer(get_arg("--seed", args, required = FALSE, default = "42"))

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
cat(sprintf("Loaded %d block(s) for permutation tuning.\n", length(blocks)))

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
perm_params <- fromJSON(perm_file)
base_params <- fromJSON(base_file)

par_type  <- perm_params$par_type
par_value <- as.numeric(perm_params$par_value)
n_perms   <- if (!is.null(perm_params$n_perms)) as.integer(perm_params$n_perms) else 100L

J <- length(blocks)

method      <- if (!is.null(base_params$method))      base_params$method      else "rgcca"
scheme      <- if (!is.null(base_params$scheme))      base_params$scheme      else "factorial"
scale       <- if (!is.null(base_params$scale))       base_params$scale       else TRUE
scale_block <- if (!is.null(base_params$scale_block)) base_params$scale_block else "inertia"
NA_method   <- if (!is.null(base_params$NA_method))   base_params$NA_method   else "na.ignore"
superblock  <- if (!is.null(base_params$superblock))  base_params$superblock  else FALSE
comp_orth   <- if (!is.null(base_params$comp_orth))   base_params$comp_orth   else TRUE
response_idx <- if (!is.null(base_params$response_idx)) as.integer(base_params$response_idx) else NULL

expand_param <- function(val, n) {
  if (is.null(val)) return(NULL)
  if (length(val) == 1) return(rep(val, n))
  val
}
ncomp    <- expand_param(base_params$ncomp,    J)
tau      <- expand_param(base_params$tau,      J)
sparsity <- expand_param(base_params$sparsity, J)

cat(sprintf(
  "Running rgcca_permutation: par_type=%s, %d candidate values, n_perms=%d\n",
  par_type, length(par_value), n_perms
))

# ---------------------------------------------------------------------------
# Run permutation tuning
# ---------------------------------------------------------------------------
perm_args <- list(
  blocks      = blocks,
  connection  = connection,
  par_type    = par_type,
  par_value   = par_value,
  n_perms     = n_perms,
  quiet       = TRUE,
  scale       = scale,
  scale_block = scale_block,
  method      = method,
  scheme      = scheme,
  ncomp       = ncomp,
  tau         = tau,
  sparsity    = sparsity,
  NA_method   = NA_method,
  superblock  = superblock,
  comp_orth   = comp_orth
)
if (!is.null(response_idx)) perm_args$response <- response_idx

perm_res <- tryCatch(
  do.call(rgcca_permutation, perm_args),
  error = function(e) stop(paste("rgcca_permutation() failed:", conditionMessage(e)))
)

cat("Permutation tuning complete.\n")

# ---------------------------------------------------------------------------
# Save outputs
# ---------------------------------------------------------------------------

# Best params
best <- as.list(perm_res$best_params)
write(toJSON(best, auto_unbox = TRUE, pretty = TRUE),
      file.path(out_dir, "perm_best_params.json"))

# Permutation criterion table
if (!is.null(perm_res$permcrit)) {
  perm_df <- as.data.frame(perm_res$permcrit)
  write.csv(perm_df, file.path(out_dir, "perm_stats.csv"), row.names = FALSE)
}

# Stats table (params × criterion)
if (!is.null(perm_res$stats)) {
  write.csv(perm_res$stats, file.path(out_dir, "perm_params_stats.csv"), row.names = FALSE)
}

# Summary
summary_text <- capture.output(summary(perm_res))
writeLines(summary_text, file.path(out_dir, "perm_summary.txt"))

# Plots
p <- tryCatch(plot(perm_res), error = function(e) NULL)
if (!is.null(p)) {
  ggsave(file.path(out_dir, "perm_plot.png"), plot = p, width = 8, height = 5, dpi = 300)
  if (.svg_device != "none") {
    tryCatch({
      dev_fn <- if (.svg_device == "svglite") svglite::svglite else "svg"
      ggsave(file.path(out_dir, "perm_plot.svg"), plot = p, width = 8, height = 5, device = dev_fn)
    }, error = function(e) cat("NOTE: SVG save skipped:", conditionMessage(e), "\n"))
  }
  cat("Permutation plot saved.\n")
}

cat(sprintf("Permutation best params: %s\n",
    paste(names(best), round(unlist(best), 4), sep = "=", collapse = ", ")))
