# ============================================================================
# EVALUATION HELPERS FOR SCRNASEQ-SEURAT-CORE-ANALYSIS
# ============================================================================
#
# This script contains helper functions for evaluating and testing the skill.
# These functions are NOT part of the core skill - they are only for demos,
# testing, and validation.
#
# Functions:
#   - load_seurat_data(): Load example data from SeuratData package (for testing)
#
# Usage:
#   source("assets/eval/eval_helpers.R")
#   seurat_obj <- load_seurat_data("pbmc3k")

#' Load data from SeuratData package (FOR TESTING/DEMO ONLY)
#'
#' This function is for evaluation and testing purposes only.
#' Users analyzing their own data should use the import functions in
#' scripts/setup_and_import.R instead.
#'
#' @param dataset_name Name of dataset (e.g., "pbmc3k", "ifnb")
#' @param type Type of data to load (default: auto-detect for dataset)
#' @return Seurat object
#' @export
load_seurat_data <- function(dataset_name, type = NULL) {

  # Check if SeuratData is installed
  if (!requireNamespace("SeuratData", quietly = TRUE)) {
    message("Installing SeuratData package...")
    if (!requireNamespace("remotes", quietly = TRUE)) {
      install.packages("remotes")
    }
    remotes::install_github('satijalab/seurat-data')
  }

  library(SeuratData)

  message("Loading ", dataset_name, " dataset from SeuratData")

  # Install dataset if not available
  if (!dataset_name %in% InstalledData()$Dataset) {
    message("Installing ", dataset_name, " dataset...")
    InstallData(dataset_name)
  }

  # Auto-detect type for specific datasets
  if (is.null(type)) {
    if (dataset_name == "pbmc3k") {
      type <- "default"  # pbmc3k uses "default" not "filtered"
    } else {
      type <- "filtered"
    }
  }

  # Load dataset
  LoadData(dataset_name, type = type)

  # Get the object
  seurat_obj <- get(dataset_name)

  # Update object for Seurat v5 compatibility
  if (packageVersion("Seurat") >= "5.0.0") {
    message("Updating object for Seurat v5 compatibility...")
    # SeuratObject v5 compatibility fix
    if (!".cache" %in% slotNames(seurat_obj)) {
      seurat_obj <- UpdateSeuratObject(seurat_obj)
    }
  }

  message(sprintf("Loaded Seurat object: %d genes x %d cells",
                  nrow(seurat_obj), ncol(seurat_obj)))

  return(seurat_obj)
}
