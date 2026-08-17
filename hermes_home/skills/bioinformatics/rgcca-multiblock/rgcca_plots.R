#!/usr/bin/env Rscript
# rgcca_plots.R — Generate all requested plots for one fitted RGCCA object.
#
# Usage:
#   Rscript rgcca_plots.R \
#     --blocks_dir  <dir_containing_per_block_csvs> \
#     --connection  <connection_matrix.csv> \
#     --params      <run_params.json> \
#     --plot_config <plot_config.json> \
#     --out_dir     <plots_output_directory> \
#     --seed        <integer>
#
# plot_config.json keys:
#   n_mark   : integer — top-N loadings shown per block (default 10)
#   comp     : [i, j]  — two component indices to plot (default [1, 2])
#   response : optional string — sample grouping variable name (for colouring)
#   response_values : optional array — one value per sample for colouring
#
# Plot types produced (for each block × component pair):
#   plot_samples_<block>_comp<i>_<j>.png/.svg   — type="samples"
#   plot_loadings_<block>_comp<i>_<j>.png/.svg  — type="loadings"
#   plot_cor_circle_<block>_comp<i>_<j>.png/.svg — type="cor_circle"
#   plot_ave.png/.svg                            — type="ave" (once per run)
#
# All plots are ggplot objects saved with ggsave() at 300 dpi (PNG) and SVG.

suppressPackageStartupMessages({
  if (!requireNamespace("RGCCA", quietly = TRUE)) {
    install.packages("RGCCA", repos = "https://cran.r-project.org", quiet = TRUE)
  }
  library(RGCCA)
  library(jsonlite)
  library(ggplot2)
})

# Determine SVG device: prefer svglite, fall back to cairo_svg, then skip SVG
.svg_device <- if (requireNamespace("svglite", quietly = TRUE)) {
  "svglite"
} else if (capabilities("cairo")) {
  "cairo_svg"
} else {
  "none"
}
cat(sprintf("SVG device: %s\n", .svg_device))

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
params_file  <- get_arg("--params",      args)
plot_file    <- get_arg("--plot_config", args)
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

# ---------------------------------------------------------------------------
# Load connection matrix
# ---------------------------------------------------------------------------
conn_df    <- read.csv(conn_file, row.names = 1, check.names = FALSE)
connection <- as.matrix(conn_df)
storage.mode(connection) <- "double"
block_order <- names(blocks)
connection  <- connection[block_order, block_order]

# ---------------------------------------------------------------------------
# Load run parameters and refit
# ---------------------------------------------------------------------------
params <- fromJSON(params_file)

expand_param <- function(val, n) {
  if (is.null(val)) return(NULL)
  if (length(val) == 1) return(rep(val, n))
  val
}
J <- length(blocks)

tau       <- expand_param(params$tau,       J)
ncomp     <- expand_param(params$ncomp,     J)
sparsity  <- expand_param(params$sparsity,  J)
scheme    <- if (!is.null(params$scheme))      params$scheme      else "factorial"
method    <- if (!is.null(params$method))      params$method      else "rgcca"
scale     <- if (!is.null(params$scale))       params$scale       else TRUE
scale_block <- if (!is.null(params$scale_block)) params$scale_block else "inertia"
NA_method <- if (!is.null(params$NA_method))   params$NA_method   else "na.ignore"
superblock <- if (!is.null(params$superblock)) params$superblock  else FALSE
comp_orth  <- if (!is.null(params$comp_orth))  params$comp_orth   else TRUE
response   <- if (!is.null(params$response_idx)) as.integer(params$response_idx) else NULL

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
  error = function(e) stop(paste("rgcca() refitting for plots failed:", conditionMessage(e)))
)

# ---------------------------------------------------------------------------
# Load plot config
# ---------------------------------------------------------------------------
plot_cfg <- fromJSON(plot_file)
n_mark   <- if (!is.null(plot_cfg$n_mark)) as.integer(plot_cfg$n_mark) else 10L
comp     <- if (!is.null(plot_cfg$comp))   as.integer(plot_cfg$comp)   else c(1L, 2L)

# Optional: sample colours from response values
sample_colors <- NULL
if (!is.null(plot_cfg$response_values)) {
  rv <- plot_cfg$response_values
  if (is.numeric(rv)) {
    # Continuous: use a gradient palette
    pal <- colorRampPalette(c("#0279EE", "#E9ED4C", "#FF9400"))(100)
    breaks <- seq(min(rv, na.rm = TRUE), max(rv, na.rm = TRUE), length.out = 101)
    sample_colors <- pal[findInterval(rv, breaks, rightmost.closed = TRUE)]
  } else {
    # Categorical
    lvls <- unique(rv)
    base_pal <- c("#0279EE", "#FF9400", "#75A025", "#FD9BED", "#E9ED4C", "#000000")
    col_map  <- setNames(base_pal[seq_along(lvls)], lvls)
    sample_colors <- col_map[as.character(rv)]
  }
}

# ---------------------------------------------------------------------------
# Helper: save a ggplot as PNG + SVG
# ---------------------------------------------------------------------------
save_plot <- function(p, stem, width = 7, height = 6) {
  if (is.null(p)) {
    cat(sprintf("  Skipped (NULL plot): %s\n", stem))
    return(invisible(NULL))
  }
  png_path <- file.path(out_dir, paste0(stem, ".png"))
  # PNG (always)
  tryCatch(
    ggsave(png_path, plot = p, width = width, height = height, dpi = 300),
    error = function(e) cat(sprintf("  WARNING: PNG save failed for %s: %s\n", stem, conditionMessage(e)))
  )
  # SVG (best-effort)
  if (.svg_device != "none") {
    svg_path <- file.path(out_dir, paste0(stem, ".svg"))
    tryCatch({
      if (.svg_device == "svglite") {
        ggsave(svg_path, plot = p, width = width, height = height, device = svglite::svglite)
      } else {
        ggsave(svg_path, plot = p, width = width, height = height, device = "svg")
      }
    }, error = function(e) {
      cat(sprintf("  NOTE: SVG save skipped for %s (%s)\n", stem, conditionMessage(e)))
    })
  }
  cat(sprintf("  Saved: %s\n", stem))
}

# ---------------------------------------------------------------------------
# Determine which blocks to plot (exclude superblock if present)
# ---------------------------------------------------------------------------
block_names <- names(res$Y)
# Superblock is typically named "superblock" in RGCCA 3.x
plot_blocks <- block_names[block_names != "superblock"]

cat(sprintf("Generating plots for %d block(s), comp=[%s], n_mark=%d\n",
    length(plot_blocks), paste(comp, collapse = ","), n_mark))

# ---------------------------------------------------------------------------
# 1. AVE plot (once per run)
# ---------------------------------------------------------------------------
p_ave <- tryCatch(
  plot(res, type = "ave"),
  error = function(e) { cat("  AVE plot error:", conditionMessage(e), "\n"); NULL }
)
save_plot(p_ave, "plot_ave", width = 8, height = 5)

# ---------------------------------------------------------------------------
# 2. Per-block plots: samples, loadings, cor_circle
# ---------------------------------------------------------------------------
for (bname in plot_blocks) {
  b_idx <- which(names(res$Y) == bname)

  # --- Samples ---
  p_samp <- tryCatch(
    plot(res,
         type             = "samples",
         block            = b_idx,
         comp             = comp,
         show_sample_names = (nrow(blocks[[1]]) <= 30),
         sample_colors    = sample_colors),
    error = function(e) { cat(sprintf("  samples plot error [%s]: %s\n", bname, conditionMessage(e))); NULL }
  )
  save_plot(p_samp,
            sprintf("plot_samples_%s_comp%d_%d", bname, comp[1], comp[2]))

  # --- Loadings ---
  p_load <- tryCatch(
    plot(res,
         type   = "loadings",
         block  = b_idx,
         comp   = comp,
         n_mark = n_mark),
    error = function(e) { cat(sprintf("  loadings plot error [%s]: %s\n", bname, conditionMessage(e))); NULL }
  )
  save_plot(p_load,
            sprintf("plot_loadings_%s_comp%d_%d", bname, comp[1], comp[2]),
            width = 7, height = max(4, n_mark * 0.4))

  # --- Correlation circle ---
  # Requires at least 2 components
  if (length(comp) >= 2 && max(ncomp) >= 2) {
    p_cor <- tryCatch(
      plot(res,
           type  = "cor_circle",
           block = b_idx,
           comp  = comp,
           n_mark = n_mark),
      error = function(e) { cat(sprintf("  cor_circle plot error [%s]: %s\n", bname, conditionMessage(e))); NULL }
    )
    save_plot(p_cor,
              sprintf("plot_cor_circle_%s_comp%d_%d", bname, comp[1], comp[2]))
  }
}

cat("Plot generation complete.\n")
