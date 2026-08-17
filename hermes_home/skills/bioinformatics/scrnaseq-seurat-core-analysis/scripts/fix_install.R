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
#!/usr/bin/env Rscript

cat("=== Fixing Installation Issues ===\n\n")

# Set CRAN mirror
options(repos = c(CRAN = "https://cloud.r-project.org"))

# Fix 1: Install remotes (lighter than devtools)
cat("1. Installing remotes (alternative to devtools)...\n")
if (!requireNamespace("remotes", quietly = TRUE)) {
  install.packages("remotes", dependencies = TRUE)
}
cat("✓ remotes installed\n\n")

# Fix 2: Install DoubletFinder from GitHub
cat("2. Installing DoubletFinder from GitHub...\n")
if (!requireNamespace("DoubletFinder", quietly = TRUE)) {
  tryCatch({
    remotes::install_github('chris-mcginnis-ucsf/DoubletFinder', upgrade = "never")
    cat("✓ DoubletFinder installed from GitHub\n")
  }, error = function(e) {
    cat("⚠ DoubletFinder install failed:", conditionMessage(e), "\n")
    cat("  Continuing without DoubletFinder (can skip doublet detection)\n")
  })
} else {
  cat("✓ DoubletFinder already installed\n")
}

cat("\n3. Installing SeuratData from GitHub...\n")
if (!requireNamespace("SeuratData", quietly = TRUE)) {
  tryCatch({
    remotes::install_github('satijalab/seurat-data', upgrade = "never")
    cat("✓ SeuratData installed from GitHub\n")
  }, error = function(e) {
    cat("⚠ SeuratData install failed:", conditionMessage(e), "\n")
  })
} else {
  cat("✓ SeuratData already installed\n")
}

cat("\n=== Fix Complete ===\n\n")

# Verify critical packages
cat("Verifying installation:\n")
critical_packages <- c("Seurat", "SeuratData", "DoubletFinder")
all_ok <- TRUE

for (pkg in critical_packages) {
  if (requireNamespace(pkg, quietly = TRUE)) {
    version <- as.character(packageVersion(pkg))
    cat("✓", pkg, version, "\n")
  } else {
    cat("✗", pkg, "NOT INSTALLED\n")
    if (pkg == "SeuratData") all_ok <- FALSE
  }
}

if (!all_ok) {
  cat("\n⚠ SeuratData is required for example data. Trying alternative approach...\n")

  # Alternative: Download pbmc3k directly
  cat("\nAttempting direct pbmc3k download...\n")
  if (!requireNamespace("Seurat", quietly = TRUE)) {
    stop("Seurat is required")
  }

  library(Seurat)

  # Create a function to download pbmc3k directly
  cat("Downloading PBMC 3k dataset from 10X Genomics...\n")
  pbmc_url <- "https://cf.10xgenomics.com/samples/cell/pbmc3k/pbmc3k_filtered_gene_bc_matrices.tar.gz"

  if (!dir.exists("temp_data")) dir.create("temp_data")

  tryCatch({
    download.file(pbmc_url, "temp_data/pbmc3k.tar.gz", mode = "wb")
    untar("temp_data/pbmc3k.tar.gz", exdir = "temp_data")
    cat("✓ Downloaded and extracted pbmc3k data\n")
    cat("  Data location: temp_data/filtered_gene_bc_matrices/hg19/\n")
  }, error = function(e) {
    cat("✗ Download failed:", conditionMessage(e), "\n")
  })
}

cat("\nReady for testing!\n")
