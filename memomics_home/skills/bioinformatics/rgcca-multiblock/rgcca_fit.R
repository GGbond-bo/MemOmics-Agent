#!/usr/bin/env Rscript
# rgcca_fit.R — Single RGCCA fit for one parameter combination.
#
# Usage:
#   Rscript rgcca_fit.R \
#     --blocks_dir  <dir_containing_per_block_csvs> \
#     --connection  <connection_matrix.csv> \
#     --params      <run_params.json> \
#     --out_dir     <output_directory> \
#     --seed        <integer>
#
# Outputs written to <out_dir>/:
#   manifest.json            — run metadata, AVE metrics, convergence info
#   summary.txt              — captured summary(res) output
#   scores_<block>.csv       — sample × component score matrix per block
#   weights_a_<block>.csv    — outer weights (a) per block
#   weights_astar_<block>.csv — block weights / loadings (astar) per block

suppressPackageStartupMessages({
  if (!requireNamespace("RGCCA", quietly = TRUE)) {
    install.packages("RGCCA", repos = "https://cran.r-project.org", quiet = TRUE)
  }
  library(RGCCA)
  library(jsonlite)
})

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

blocks_dir  <- get_arg("--blocks_dir", args)
conn_file   <- get_arg("--connection",  args)
params_file <- get_arg("--params",      args)
out_dir     <- get_arg("--out_dir",     args)
seed_val    <- as.integer(get_arg("--seed", args, required = FALSE, default = "42"))

dir.create(out_dir, recursive = TRUE, showWarnings = FALSE)

set.seed(seed_val)

# ---------------------------------------------------------------------------
# Load blocks
# ---------------------------------------------------------------------------
block_files <- list.files(blocks_dir, pattern = "\\.csv$", full.names = TRUE)
if (length(block_files) == 0) {
  stop(paste("No CSV files found in blocks_dir:", blocks_dir))
}

blocks <- list()
for (bf in sort(block_files)) {
  bname <- tools::file_path_sans_ext(basename(bf))
  mat   <- read.csv(bf, row.names = 1, check.names = FALSE)
  mat   <- as.matrix(mat)
  storage.mode(mat) <- "double"
  blocks[[bname]] <- mat
}
cat(sprintf("Loaded %d block(s): %s\n", length(blocks), paste(names(blocks), collapse = ", ")))

# ---------------------------------------------------------------------------
# Load connection matrix
# ---------------------------------------------------------------------------
conn_df <- read.csv(conn_file, row.names = 1, check.names = FALSE)
connection <- as.matrix(conn_df)
storage.mode(connection) <- "double"

# Reorder connection matrix rows/cols to match block order
block_order <- names(blocks)
if (!all(block_order %in% rownames(connection))) {
  stop(paste(
    "Connection matrix row/col names do not match block names.\n",
    "Connection:", paste(rownames(connection), collapse = ", "), "\n",
    "Blocks:", paste(block_order, collapse = ", ")
  ))
}
connection <- connection[block_order, block_order]

# ---------------------------------------------------------------------------
# Load run parameters
# ---------------------------------------------------------------------------
params <- fromJSON(params_file)

# Helper: expand scalar param to per-block list if needed
expand_param <- function(val, n_blocks) {
  if (is.null(val)) return(NULL)
  if (length(val) == 1) return(rep(val, n_blocks))
  if (length(val) == n_blocks) return(val)
  stop(sprintf(
    "Parameter length %d does not match number of blocks %d.",
    length(val), n_blocks
  ))
}

J <- length(blocks)

tau       <- expand_param(params$tau,       J)
ncomp     <- expand_param(params$ncomp,     J)
sparsity  <- expand_param(params$sparsity,  J)
scheme    <- if (!is.null(params$scheme))    params$scheme    else "factorial"
method    <- if (!is.null(params$method))    params$method    else "rgcca"
scale     <- if (!is.null(params$scale))     params$scale     else TRUE
scale_block <- if (!is.null(params$scale_block)) params$scale_block else "inertia"
NA_method <- if (!is.null(params$NA_method)) params$NA_method else "na.ignore"
superblock <- if (!is.null(params$superblock)) params$superblock else FALSE
comp_orth  <- if (!is.null(params$comp_orth))  params$comp_orth  else TRUE
response   <- if (!is.null(params$response_idx)) as.integer(params$response_idx) else NULL

cat(sprintf(
  "Fitting RGCCA: method=%s, scheme=%s, ncomp=%s, tau=%s, sparsity=%s\n",
  method, scheme,
  paste(ncomp, collapse = "/"),
  paste(tau, collapse = "/"),
  paste(sparsity, collapse = "/")
))

# ---------------------------------------------------------------------------
# Fit RGCCA
# ---------------------------------------------------------------------------
fit_args <- list(
  blocks      = blocks,
  connection  = connection,
  tau         = tau,
  ncomp       = ncomp,
  scheme      = scheme,
  scale       = scale,
  scale_block = scale_block,
  method      = method,
  sparsity    = sparsity,
  superblock  = superblock,
  NA_method   = NA_method,
  comp_orth   = comp_orth,
  verbose     = FALSE,
  quiet       = TRUE
)
if (!is.null(response)) fit_args$response <- response

res <- tryCatch(
  do.call(rgcca, fit_args),
  error = function(e) {
    stop(paste("rgcca() failed:", conditionMessage(e)))
  }
)

cat("Fit complete.\n")

# ---------------------------------------------------------------------------
# Extract and save scores
# ---------------------------------------------------------------------------
for (bname in names(res$Y)) {
  scores_df <- as.data.frame(res$Y[[bname]])
  colnames(scores_df) <- paste0("comp", seq_len(ncol(scores_df)))
  rownames(scores_df) <- rownames(blocks[[1]])
  write.csv(scores_df, file.path(out_dir, paste0("scores_", bname, ".csv")))
}

# ---------------------------------------------------------------------------
# Extract and save weights (a = outer weights, astar = block weights/loadings)
# ---------------------------------------------------------------------------
for (bname in names(res$a)) {
  wa <- as.data.frame(res$a[[bname]])
  colnames(wa) <- paste0("comp", seq_len(ncol(wa)))
  write.csv(wa, file.path(out_dir, paste0("weights_a_", bname, ".csv")))
}

for (bname in names(res$astar)) {
  ws <- as.data.frame(res$astar[[bname]])
  colnames(ws) <- paste0("comp", seq_len(ncol(ws)))
  write.csv(ws, file.path(out_dir, paste0("weights_astar_", bname, ".csv")))
}

# ---------------------------------------------------------------------------
# Extract AVE metrics
# ---------------------------------------------------------------------------
ave <- res$AVE

# AVE_X per block per component
ave_x_list <- list()
for (bname in names(ave$AVE_X)) {
  ave_x_list[[bname]] <- as.numeric(ave$AVE_X[[bname]])
}

# Scalar summaries for ranking
n_comp_actual <- length(ave$AVE_outer)
ave_inner_vec  <- as.numeric(ave$AVE_inner)
ave_outer_vec  <- as.numeric(ave$AVE_outer)

metrics <- list(
  AVE_inner_mean  = mean(ave_inner_vec),
  AVE_outer_mean  = mean(ave_outer_vec),
  AVE_inner_comp1 = ave_inner_vec[1],
  AVE_outer_comp1 = ave_outer_vec[1],
  AVE_inner_all   = ave_inner_vec,
  AVE_outer_all   = ave_outer_vec,
  AVE_X           = ave_x_list,
  crit_final      = {
    # res$crit is a list (one element per component) when ncomp > 1
    cl <- res$crit
    if (is.list(cl)) as.numeric(tail(cl[[length(cl)]], 1))
    else             as.numeric(tail(cl, 1))
  }
)

# ---------------------------------------------------------------------------
# Save summary.txt
# ---------------------------------------------------------------------------
summary_text <- capture.output(summary(res))
writeLines(summary_text, file.path(out_dir, "summary.txt"))

# ---------------------------------------------------------------------------
# Save manifest.json
# ---------------------------------------------------------------------------
manifest <- list(
  params_used = list(
    method      = method,
    scheme      = scheme,
    tau         = tau,
    ncomp       = ncomp,
    sparsity    = sparsity,
    scale       = scale,
    scale_block = scale_block,
    NA_method   = NA_method,
    superblock  = superblock,
    comp_orth   = comp_orth,
    response_idx = response,
    seed        = seed_val
  ),
  blocks      = names(blocks),
  n_samples   = nrow(blocks[[1]]),
  n_features  = sapply(blocks, ncol),
  n_comp      = n_comp_actual,
  metrics     = metrics,
  primal_dual = res$primal_dual,
  converged   = (length(res$crit) < 1000)  # heuristic: didn't hit max iterations
)

write(toJSON(manifest, auto_unbox = TRUE, pretty = TRUE),
      file.path(out_dir, "manifest.json"))

cat(sprintf(
  "Saved: scores, weights, manifest. AVE_inner_mean=%.4f, AVE_outer_mean=%.4f\n",
  metrics$AVE_inner_mean, metrics$AVE_outer_mean
))
