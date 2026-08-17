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
# Basic DESeq2 workflow for differential expression analysis
#
# This script demonstrates the complete DESeq2 workflow using example data.
# For your own data, replace the data loading section with your count matrix and metadata.

library(DESeq2)
library(apeglm)

# =============================================================================
# STEP 1: LOAD DATA
# =============================================================================

# --- OPTION A: Use example dataset (for testing) ---
source("scripts/load_example_data.R")
data <- load_pasilla_data()  # Installs pasilla if needed
counts <- data$counts
coldata <- data$coldata

# Prepare coldata for simple two-group comparison
coldata <- coldata[, "condition", drop = FALSE]  # Keep only condition column

# --- OPTION B: Load your own data (uncomment and modify) ---
# counts <- read.csv("path/to/counts.csv", row.names = 1)
# coldata <- read.csv("path/to/metadata.csv", row.names = 1)
# counts <- as.matrix(counts)  # Ensure counts is a matrix

# --- OPTION C: Use airway dataset (alternative example) ---
# source("scripts/load_example_data.R")
# data <- load_airway_data()
# counts <- data$counts
# coldata <- data$coldata[, "dex", drop = FALSE]
# colnames(coldata) <- "condition"  # Rename for consistency

# =============================================================================
# STEP 2: VALIDATE DATA (CRITICAL - prevents errors downstream)
# =============================================================================

cat("=== Data Validation ===\n")
if (!all(colnames(counts) %in% rownames(coldata))) {
  missing <- setdiff(colnames(counts), rownames(coldata))
  stop("Sample ID mismatch!\n",
       "  Count columns not in metadata: ", paste(head(missing, 5), collapse = ", "))
}

# Reorder coldata to match counts
coldata <- coldata[colnames(counts), , drop = FALSE]

cat("✓ Sample IDs validated\n")
cat("  Dimensions:", nrow(counts), "genes x", ncol(counts), "samples\n")
cat("  Groups:", paste(table(coldata$condition), "samples per group"), "\n\n")

# =============================================================================
# STEP 3: CREATE DESeqDataSet
# =============================================================================

cat("=== Creating DESeqDataSet ===\n")
dds <- DESeqDataSetFromMatrix(
  countData = counts,
  colData = coldata,
  design = ~ condition
)

cat("✓ DESeqDataSet created\n")
cat("  Design: ~ condition\n\n")

# =============================================================================
# STEP 4: PRE-FILTER LOW-COUNT GENES (REQUIRED - improves power)
# =============================================================================

cat("=== Pre-filtering Genes ===\n")
cat("Genes before filtering:", nrow(dds), "\n")

keep <- rowSums(counts(dds)) >= 10
dds <- dds[keep, ]

cat("Genes after filtering:", nrow(dds), "\n")
cat("Genes removed:", sum(!keep), "\n\n")

# =============================================================================
# STEP 5: SET REFERENCE LEVEL (REQUIRED - ensures correct comparison direction)
# =============================================================================

cat("=== Setting Reference Level ===\n")
# Set first level alphabetically as reference (change as needed for your data)
ref_level <- levels(dds$condition)[1]
dds$condition <- relevel(dds$condition, ref = ref_level)

cat("✓ Reference level:", ref_level, "\n")
cat("  Comparison:", levels(dds$condition)[2], "vs", ref_level, "\n")
cat("  (Positive log2FC = higher in", levels(dds$condition)[2], ")\n\n")

# =============================================================================
# STEP 6: RUN DESeq2 ANALYSIS
# =============================================================================

cat("=== Running DESeq2 ===\n")
cat("This performs:\n")
cat("  1. Size factor normalization\n")
cat("  2. Dispersion estimation\n")
cat("  3. Negative binomial GLM fitting\n")
cat("  4. Wald test for differential expression\n\n")

dds <- DESeq(dds)

cat("✓ DESeq2 analysis completed\n\n")

# =============================================================================
# STEP 7: EXTRACT RESULTS
# =============================================================================

cat("=== Extracting Results ===\n")

# Get coefficient name for shrinkage
coef_name <- resultsNames(dds)[2]  # First coefficient after Intercept

# Unshrunk results (for hypothesis testing)
res <- results(dds, name = coef_name)

# Shrunk results (for visualization and ranking)
resLFC <- lfcShrink(dds, coef = coef_name, type = "apeglm")

cat("✓ Results extracted\n")
cat("  Coefficient:", coef_name, "\n\n")

# =============================================================================
# STEP 8: SUMMARIZE RESULTS
# =============================================================================

cat("=== Results Summary ===\n")
summary(res, alpha = 0.05)

# Count significant genes
sig_genes <- subset(resLFC, padj < 0.05 & abs(log2FoldChange) >= 1)
cat("\n=== Significant Genes (padj < 0.05, |log2FC| >= 1) ===\n")
cat("Total significant:", nrow(sig_genes), "\n")
cat("  Upregulated:", sum(sig_genes$log2FoldChange > 0), "\n")
cat("  Downregulated:", sum(sig_genes$log2FoldChange < 0), "\n\n")

# Show top 10 genes by adjusted p-value
cat("Top 10 genes by significance:\n")
sig_genes_sorted <- sig_genes[order(sig_genes$padj), ]
print(head(as.data.frame(sig_genes_sorted[, c("baseMean", "log2FoldChange", "padj")]), 10))

cat("\n✓ Basic workflow completed successfully!\n")
cat("\nNext steps:\n")
cat("  - Check QC plots: use scripts/qc_plots.R\n")
cat("  - Export results: use scripts/export_results.R\n")
cat("  - Filter genes: use de-results-to-gene-lists skill\n")
cat("  - Create plots: use de-results-to-plots skill\n")
