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

# Install all required packages for scrnaseq-seurat-core-analysis skill
cat("=== Installing Required Packages ===\n\n")
cat("This will take 10-15 minutes...\n\n")

# Set CRAN mirror
options(repos = c(CRAN = "https://cloud.r-project.org"))

# Install BiocManager if needed
if (!requireNamespace("BiocManager", quietly = TRUE)) {
  cat("Installing BiocManager...\n")
  install.packages("BiocManager", quiet = TRUE)
}

# Core packages
core_packages <- c(
  "Seurat",
  "ggplot2",
  "ggprism",
  "dplyr",
  "patchwork"
)

cat("Installing core packages...\n")
for (pkg in core_packages) {
  if (!requireNamespace(pkg, quietly = TRUE)) {
    cat("  Installing", pkg, "...\n")
    install.packages(pkg, quiet = TRUE)
  } else {
    cat("  ✓", pkg, "already installed\n")
  }
}

# Analysis packages
analysis_packages <- c(
  "DoubletFinder",
  "harmony",
  "SoupX"
)

cat("\nInstalling analysis packages...\n")
for (pkg in analysis_packages) {
  if (!requireNamespace(pkg, quietly = TRUE)) {
    cat("  Installing", pkg, "...\n")
    install.packages(pkg, quiet = TRUE)
  } else {
    cat("  ✓", pkg, "already installed\n")
  }
}

# Bioconductor packages
bioc_packages <- c(
  "DESeq2",
  "muscat",
  "SingleR",
  "celldex"
)

cat("\nInstalling Bioconductor packages...\n")
for (pkg in bioc_packages) {
  if (!requireNamespace(pkg, quietly = TRUE)) {
    cat("  Installing", pkg, "...\n")
    BiocManager::install(pkg, update = FALSE, ask = FALSE, quiet = TRUE)
  } else {
    cat("  ✓", pkg, "already installed\n")
  }
}

# Install SeuratData for example datasets
if (!requireNamespace("SeuratData", quietly = TRUE)) {
  cat("\nInstalling SeuratData...\n")
  if (!requireNamespace("devtools", quietly = TRUE)) {
    install.packages("devtools", quiet = TRUE)
  }
  devtools::install_github('satijalab/seurat-data', quiet = TRUE, upgrade = "never")
} else {
  cat("\n✓ SeuratData already installed\n")
}

cat("\n=== Installation Complete ===\n\n")

# Verify installations
cat("Verifying package versions:\n")
packages_to_check <- c("Seurat", "ggplot2", "dplyr", "DESeq2", "SeuratData")
for (pkg in packages_to_check) {
  if (requireNamespace(pkg, quietly = TRUE)) {
    version <- as.character(packageVersion(pkg))
    cat("  ✓", pkg, version, "\n")
  } else {
    cat("  ✗", pkg, "NOT INSTALLED\n")
  }
}

cat("\nAll packages ready for testing!\n")
