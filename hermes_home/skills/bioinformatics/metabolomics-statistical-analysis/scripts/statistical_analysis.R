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
#      ★ 强制审查项（任一不通过则重新执行）:
#        a. 图片是否生成？无图 → 重新执行
#        b. 图片是否空白（全白/全黑/全单一色）？空白 → 强制重新出图
#        c. 图片是否有 NA/缺失值（>10%像素是NA）？有NA → 强制重新出图
#        d. 图片大小是否过小（<5KB）？过小 → 强制重新出图
#        e. 图片数量是否足够？（每步至少1张图，关键步骤至少2-3张）
#        f. 代码行数是否合理？是否分段执行（禁止&&连接）？
#        g. 数值范围是否合理？跟知识库对应吗？
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
# ★ 参数和结论辩论铁律:
#   - 有参数选择 → 必须调 debate_analysis 辩论
#   - 有结论输出 → 必须调 debate_analysis 辩论
#   - 辩论格式：正方(支持) vs 反方(质疑+替代) → 裁判决断
#   - 最多3轮，3轮后选最优结果
# ============================================================

# ============================================================
# MetaboAnalystR Metabolomics Statistical Analysis Pipeline
# 代谢组学统计分析全流程
#
# 输入: peak_intensity_matrix.csv (行=代谢物, 列=样本)
#       metadata.csv (含 condition 列)
# 输出: figures/, results/, data/ 目录下的所有分析产物
#
# 依赖: MetaboAnalystR (GitHub), ropls, mixOmics, caret, pROC,
#       randomForest, ggplot2, ggprism, ggrepel, ComplexHeatmap,
#       impute, pcaMethods
# ============================================================

suppressPackageStartupMessages({
  library(ggplot2)
  library(ggprism)
  library(ggrepel)
  library(ComplexHeatmap)
  library(circlize)
  library(ropls)
  library(pROC)
  library(randomForest)
  library(caret)
  library(impute)
  library(pcaMethods)
  library(tidyverse)
})

# ============================================================
# 0. Configuration — 用户修改此区域
# ============================================================
CONFIG <- list(
  # 输入文件
  data_file    = "peak_intensity_matrix.csv",   # 代谢物 × 样本 matrix
  metadata_file = "metadata.csv",                # 含 condition 列
  
  # 比较设置
  condition_col = "condition",                   # 分组列名
  ref_group     = "Control",                     # 对照组名
  treat_group   = "Disease",                     # 处理组名
  
  # 归一化与预处理
  normalization = "PQN",    # PQN / Quantile / VSN / Median / SUM / none
  imputation    = "kNN",    # kNN / MinProb / half-min / mean / none
  transform     = "log2",   # log2 / log10 / cube / none
  scaling       = "Pareto", # Pareto / Auto / Range / MeanCenter / none
  
  # 统计阈值
  p_threshold   = 0.05,
  fc_threshold  = 1.5,      # fold change
  vip_threshold = 1.0,
  
  # PLS-DA
  plsda_ncomp   = 3,
  n_permutations = 1000,
  
  # Random Forest
  rf_ntree      = 500,
  
  # 输出
  output_dir    = "."
)

# ============================================================
# 1. Load and validate input data
# ============================================================
load_and_validate <- function(config) {
  # Read peak intensity matrix
  mat <- read.csv(config$data_file, row.names = 1, check.names = FALSE)
  message(sprintf("✓ Loaded matrix: %d metabolites × %d samples", nrow(mat), ncol(mat)))
  
  # Read metadata
  meta <- read.csv(config$metadata_file, row.names = 1)
  stopifnot(config$condition_col %in% colnames(meta))
  message(sprintf("✓ Loaded metadata: %d samples, condition levels: %s", 
                   nrow(meta), paste(unique(meta[[config$condition_col]]), collapse=", ")))
  
  # Align samples between matrix and metadata
  common_samples <- intersect(colnames(mat), rownames(meta))
  mat <- mat[, common_samples, drop = FALSE]
  meta <- meta[common_samples, , drop = FALSE]
  message(sprintf("✓ Aligned %d common samples", length(common_samples)))
  
  # Filter: remove metabolites with >50% missing values
  na_frac <- rowMeans(is.na(mat))
  mat <- mat[na_frac <= 0.5, ]
  message(sprintf("✓ Filtered to %d metabolites (removed >50%% NA)", nrow(mat)))
  
  list(matrix = mat, metadata = meta)
}

# ============================================================
# 2. Normalization — Probabilistic Quotient Normalization
# ============================================================
normalize_matrix <- function(mat, method = "PQN") {
  if (method == "none") return(mat)
  
  if (method == "PQN") {
    # PQN: normalize to median spectrum
    ref <- apply(mat, 1, median, na.rm = TRUE)
    quotients <- sweep(mat, 1, ref, "/")
    dilution_factors <- apply(quotients, 2, median, na.rm = TRUE)
    mat_norm <- sweep(mat, 2, dilution_factors, "/")
    message("✓ PQN normalization complete")
    return(mat_norm)
  }
  
  if (method == "SUM") {
    mat_norm <- sweep(mat, 2, colSums(mat, na.rm = TRUE), "/") * 1e6
    message("✓ SUM normalization complete")
    return(mat_norm)
  }
  
  if (method == "Median") {
    medians <- apply(mat, 2, median, na.rm = TRUE)
    mat_norm <- sweep(mat, 2, medians, "/") * median(medians)
    message("✓ Median normalization complete")
    return(mat_norm)
  }
  
  stop(sprintf("Unknown normalization method: %s", method))
}

# ============================================================
# 3. Imputation — kNN missing value estimation
# ============================================================
impute_matrix <- function(mat, method = "kNN") {
  if (method == "none") return(mat)
  
  na_count <- sum(is.na(mat))
  if (na_count == 0) {
    message("✓ No missing values, skipping imputation")
    return(mat)
  }
  
  if (method == "kNN") {
    mat_imp <- impute.knn(as.matrix(mat), k = 10, rowmax = 0.5)$data
    message(sprintf("✓ kNN imputation: filled %d missing values", na_count))
    return(mat_imp)
  }
  
  if (method == "half-min") {
    for (i in 1:nrow(mat)) {
      min_val <- min(mat[i, ], na.rm = TRUE)
      mat[i, is.na(mat[i, ])] <- min_val / 2
    }
    message(sprintf("✓ Half-min imputation: filled %d missing values", na_count))
    return(mat)
  }
  
  stop(sprintf("Unknown imputation method: %s", method))
}

# ============================================================
# 4. Transform and Scale
# ============================================================
transform_scale <- function(mat, transform = "log2", scaling = "Pareto") {
  # Transform
  if (transform == "log2") {
    mat <- log2(mat + 1)
    message("✓ Log2 transformation applied")
  } else if (transform == "log10") {
    mat <- log10(mat + 1)
  } else if (transform == "none") {
    # skip
  }
  
  # Scale (column-wise = features)
  mat_t <- t(mat)  # samples × metabolites for ropls convention
  
  if (scaling == "Pareto") {
    mat_t <- scale(mat_t, center = TRUE, scale = FALSE)  # mean-center
    mat_t <- mat_t / sqrt(apply(mat_t, 2, sd, na.rm = TRUE))  # divide by sqrt(SD)
    message("✓ Pareto scaling applied")
  } else if (scaling == "Auto") {
    mat_t <- scale(mat_t, center = TRUE, scale = TRUE)
    message("✓ Auto scaling applied")
  } else if (scaling == "MeanCenter") {
    mat_t <- scale(mat_t, center = TRUE, scale = FALSE)
    message("✓ Mean-center applied")
  }
  
  list(matrix_t = mat_t, matrix_original = mat)
}

# ============================================================
# 5. Univariate Analysis — t-test + Volcano Plot
# ============================================================
run_univariate <- function(mat, meta, config) {
  groups <- meta[[config$condition_col]]
  g1 <- which(groups == config$ref_group)
  g2 <- which(groups == config$treat_group)
  
  results <- data.frame(
    metabolite = rownames(mat),
    mean_g1 = rowMeans(mat[, g1], na.rm = TRUE),
    mean_g2 = rowMeans(mat[, g2], na.rm = TRUE),
    log2FC = NA,
    p_value = NA,
    stringsAsFactors = FALSE
  )
  
  for (i in 1:nrow(mat)) {
    v1 <- as.numeric(mat[i, g1])
    v2 <- as.numeric(mat[i, g2])
    results$log2FC[i] <- mean(v2, na.rm = TRUE) - mean(v1, na.rm = TRUE)
    if (sum(!is.na(v1)) >= 3 && sum(!is.na(v2)) >= 3) {
      results$p_value[i] <- tryCatch(t.test(v2, v1)$p.value, error = function(e) NA)
    }
  }
  
  results$fdr <- p.adjust(results$p_value, method = "BH")
  results$significant <- results$fdr < config$p_threshold & abs(results$log2FC) > log2(config$fc_threshold)
  results$direction <- ifelse(results$log2FC > 0, "Up", "Down")
  
  message(sprintf("✓ Univariate: %d significant (%d up, %d down)", 
                   sum(results$significant, na.rm=TRUE),
                   sum(results$significant & results$direction=="Up", na.rm=TRUE),
                   sum(results$significant & results$direction=="Down", na.rm=TRUE)))
  
  results
}

# ============================================================
# 5b. Volcano Plot
# ============================================================
plot_volcano <- function(results, config) {
  plot_data <- results[!is.na(results$p_value), ]
  plot_data$neg_log10_p <- -log10(plot_data$p_value)
  
  top_label <- plot_data %>% 
    filter(significant) %>% 
    arrange(p_value) %>% 
    head(20)
  
  p <- ggplot(plot_data, aes(x = log2FC, y = neg_log10_p)) +
    geom_point(aes(color = significant), size = 1.5, alpha = 0.6) +
    geom_hline(yintercept = -log10(config$p_threshold), linetype = "dashed", color = "grey50") +
    geom_vline(xintercept = c(-log2(config$fc_threshold), log2(config$fc_threshold)), 
               linetype = "dashed", color = "grey50") +
    geom_text_repel(data = top_label, aes(label = metabolite), 
                    max.overlaps = 20, size = 3, box.padding = 0.5) +
    scale_color_manual(values = c("FALSE" = "grey70", "TRUE" = "#E64B35")) +
    labs(x = "log2(Fold Change)", y = "-log10(p-value)",
         title = paste(config$treat_group, "vs", config$ref_group)) +
    theme_prism(base_size = 12) +
    theme(legend.position = "none")
  
  ggsave(file.path(config$output_dir, "figures", "volcano_plot.png"), 
         p, width = 8, height = 7, dpi = 300)
  ggsave(file.path(config$output_dir, "figures", "volcano_plot.svg"), 
         p, width = 8, height = 7)
  
  message("✓ Volcano plot saved")
  p
}

# ============================================================
# 6. PCA — Unsupervised Dimension Reduction
# ============================================================
run_pca <- function(mat_t, meta, config) {
  pca_res <- prcomp(mat_t, center = FALSE, scale. = FALSE)
  scores <- as.data.frame(pca_res$x)
  scores$sample <- rownames(scores)
  scores$condition <- meta[[config$condition_col]]
  
  var_exp <- round(100 * pca_res$sdev^2 / sum(pca_res$sdev^2), 1)
  
  p <- ggplot(scores, aes(x = PC1, y = PC2, color = condition)) +
    geom_point(size = 4, alpha = 0.8) +
    stat_ellipse(level = 0.95, linewidth = 1) +
    labs(x = sprintf("PC1 (%.1f%%)", var_exp[1]),
         y = sprintf("PC2 (%.1f%%)", var_exp[2]),
         title = "PCA Score Plot") +
    theme_prism(base_size = 12) +
    theme(legend.position = "right")
  
  ggsave(file.path(config$output_dir, "figures", "pca_score.png"), 
         p, width = 8, height = 6, dpi = 300)
  ggsave(file.path(config$output_dir, "figures", "pca_score.svg"), 
         p, width = 8, height = 6)
  
  message(sprintf("✓ PCA: PC1=%.1f%%, PC2=%.1f%%", var_exp[1], var_exp[2]))
  list(scores = scores, var_exp = var_exp)
}

# ============================================================
# 7. PLS-DA — Supervised Classification
# ============================================================
run_plsda <- function(mat_t, meta, config) {
  y <- as.numeric(factor(meta[[config$condition_col]])) - 1
  
  pls_res <- opls(mat_t, y, 
                  predI = min(config$plsda_ncomp, ncol(mat_t)),
                  orthoI = 0,  # PLS-DA (not OPLS)
                  permI = config$n_permutations,
                  crossvalI = 7,
                  fig.pdfC = "none",
                  info.txtC = "none")
  
  # VIP scores
  vip <- data.frame(
    metabolite = colnames(mat_t),
    VIP = pls_res@vipVn,
    stringsAsFactors = FALSE
  ) %>% arrange(desc(VIP))
  
  message(sprintf("✓ PLS-DA: %d components, R2Y=%.3f, Q2=%.3f",
                   pls_res@summaryDF$pre, pls_res@summaryDF$`R2Y(cum)`, pls_res@summaryDF$`Q2(cum)`))
  message(sprintf("  VIP ≥ %.1f: %d metabolites", config$vip_threshold, sum(vip$VIP >= config$vip_threshold)))
  
  list(model = pls_res, vip = vip)
}

# ============================================================
# 7b. PLS-DA Score Plot
# ============================================================
plot_plsda <- function(pls_res, meta, config) {
  scores <- as.data.frame(pls_res@scoreMN)
  colnames(scores) <- paste0("t", 1:ncol(scores))
  scores$sample <- rownames(scores)
  scores$condition <- meta[[config$condition_col]]
  
  p <- ggplot(scores, aes(x = t1, y = t2, color = condition)) +
    geom_point(size = 4, alpha = 0.8) +
    stat_ellipse(level = 0.95, linewidth = 1) +
    labs(title = "PLS-DA Score Plot",
         x = paste0("t1 (", round(pls_res@modelDF$R2X[1]*100, 1), "%)"),
         y = paste0("t2 (", round(pls_res@modelDF$R2X[2]*100, 1), "%)")) +
    theme_prism(base_size = 12) +
    theme(legend.position = "right")
  
  ggsave(file.path(config$output_dir, "figures", "plsda_score.png"), 
         p, width = 8, height = 6, dpi = 300)
  ggsave(file.path(config$output_dir, "figures", "plsda_score.svg"), 
         p, width = 8, height = 6)
  message("✓ PLS-DA plot saved")
  p
}

# ============================================================
# 8. Random Forest — Feature Selection
# ============================================================
run_random_forest <- function(mat, meta, config) {
  y <- factor(meta[[config$condition_col]])
  
  rf <- randomForest(x = t(mat), y = y, 
                     ntree = config$rf_ntree, 
                     importance = TRUE)
  
  imp <- data.frame(
    metabolite = rownames(rf$importance),
    MeanDecreaseAccuracy = rf$importance[, "MeanDecreaseAccuracy"],
    stringsAsFactors = FALSE
  ) %>% arrange(desc(MeanDecreaseAccuracy))
  
  # Plot top 30
  imp_top <- head(imp, 30)
  p <- ggplot(imp_top, aes(x = reorder(metabolite, MeanDecreaseAccuracy), 
                            y = MeanDecreaseAccuracy)) +
    geom_col(fill = "#4472C4") +
    coord_flip() +
    labs(x = "", y = "Mean Decrease Accuracy",
         title = "Random Forest Variable Importance") +
    theme_prism(base_size = 11)
  
  ggsave(file.path(config$output_dir, "figures", "rf_importance.png"), 
         p, width = 8, height = 8, dpi = 300)
  ggsave(file.path(config$output_dir, "figures", "rf_importance.svg"), 
         p, width = 8, height = 8)
  
  message(sprintf("✓ Random Forest: OOB error = %.3f", rf$err.rate[config$rf_ntree, 1]))
  list(model = rf, importance = imp)
}

# ============================================================
# 9. ROC Analysis — Single & Multi-Marker
# ============================================================
run_roc <- function(mat, meta, results_sig, config) {
  groups <- meta[[config$condition_col]]
  y_true <- ifelse(groups == config$treat_group, 1, 0)
  
  roc_list <- list()
  
  # Single biomarker ROC for top 15
  top_metabs <- head(results_sig %>% filter(significant) %>% arrange(p_value), 15)
  
  for (i in 1:nrow(top_metabs)) {
    met <- top_metabs$metabolite[i]
    vals <- as.numeric(mat[met, ])
    roc_obj <- roc(y_true, vals, quiet = TRUE)
    roc_list[[met]] <- roc_obj
  }
  
  # Plot top 5 ROC curves
  top5 <- head(names(roc_list), 5)
  p <- ggroc(roc_list[top5], linewidth = 1) +
    geom_abline(intercept = 1, slope = 1, linetype = "dashed", color = "grey50") +
    labs(title = "ROC Curves — Top 5 Metabolites",
         color = "Metabolite") +
    theme_prism(base_size = 12)
  
  ggsave(file.path(config$output_dir, "figures", "roc_curves.png"), 
         p, width = 8, height = 6, dpi = 300)
  ggsave(file.path(config$output_dir, "figures", "roc_curves.svg"), 
         p, width = 8, height = 6)
  
  # Summary
  roc_summary <- data.frame(
    metabolite = top_metabs$metabolite,
    AUC = sapply(roc_list, function(r) as.numeric(auc(r))),
    stringsAsFactors = FALSE
  ) %>% arrange(desc(AUC))
  
  message(sprintf("✓ ROC: Best AUC = %.3f (%s)", roc_summary$AUC[1], roc_summary$metabolite[1]))
  roc_summary
}

# ============================================================
# ============================================================
# MAIN — Execute Pipeline
# ============================================================
# ============================================================

main <- function() {
  # Create output directories
  dir.create(file.path(CONFIG$output_dir, "figures"), showWarnings = FALSE, recursive = TRUE)
  dir.create(file.path(CONFIG$output_dir, "results"), showWarnings = FALSE, recursive = TRUE)
  dir.create(file.path(CONFIG$output_dir, "data"), showWarnings = FALSE, recursive = TRUE)
  
  message("========================================")
  message(" Metabolomics Statistical Analysis")
  message("========================================")
  
  # Step 1: Load & Validate
  message("\n[1/9] Loading data...")
  data <- load_and_validate(CONFIG)
  
  # Step 2: Normalize
  message(sprintf("\n[2/9] Normalization: %s ...", CONFIG$normalization))
  mat_norm <- normalize_matrix(data$matrix, CONFIG$normalization)
  
  # Step 3: Imputation
  message(sprintf("\n[3/9] Imputation: %s ...", CONFIG$imputation))
  mat_imp <- impute_matrix(mat_norm, CONFIG$imputation)
  
  # Step 4: Transform & Scale
  message(sprintf("\n[4/9] Transform: %s, Scaling: %s ...", CONFIG$transform, CONFIG$scaling))
  mat_proc <- transform_scale(mat_imp, CONFIG$transform, CONFIG$scaling)
  
  # Step 5: Univariate
  message("\n[5/9] Univariate analysis (t-test)...")
  uv_results <- run_univariate(mat_proc$matrix_original, data$metadata, CONFIG)
  
  # Volcano plot
  plot_volcano(uv_results, CONFIG)
  
  # Step 6: PCA
  message("\n[6/9] PCA...")
  pca_res <- run_pca(mat_proc$matrix_t, data$metadata, CONFIG)
  
  # Step 7: PLS-DA
  message(sprintf("\n[7/9] PLS-DA (ncomp=%d, perm=%d)...", CONFIG$plsda_ncomp, CONFIG$n_permutations))
  pls_res <- run_plsda(mat_proc$matrix_t, data$metadata, CONFIG)
  plot_plsda(pls_res$model, data$metadata, CONFIG)
  
  # Step 8: Random Forest
  message(sprintf("\n[8/9] Random Forest (ntree=%d)...", CONFIG$rf_ntree))
  rf_res <- run_random_forest(mat_proc$matrix_original, data$metadata, CONFIG)
  
  # Step 9: ROC
  message("\n[9/9] ROC Analysis...")
  roc_res <- run_roc(mat_proc$matrix_original, data$metadata, uv_results, CONFIG)
  
  # --- Export Results ---
  message("\n========================================")
  message(" Exporting Results")
  message("========================================")
  
  # Univariate results
  write.csv(uv_results, 
            file.path(CONFIG$output_dir, "results", "univariate_results.csv"), 
            row.names = FALSE)
  
  # PLS-DA VIP
  write.csv(pls_res$vip,
            file.path(CONFIG$output_dir, "results", "plsda_vip.csv"),
            row.names = FALSE)
  
  # RF importance
  write.csv(rf_res$importance,
            file.path(CONFIG$output_dir, "results", "rf_importance.csv"),
            row.names = FALSE)
  
  # ROC summary
  write.csv(roc_res,
            file.path(CONFIG$output_dir, "results", "roc_summary.csv"),
            row.names = FALSE)
  
  # Normalized matrix
  write.csv(mat_imp,
            file.path(CONFIG$output_dir, "data", "normalized_matrix.csv"))
  
  # Save R objects
  saveRDS(list(normalized = mat_imp, univariate = uv_results, 
               plsda = pls_res, rf = rf_res, pca = pca_res),
          file.path(CONFIG$output_dir, "data", "analysis_object.rds"))
  
  message("\n✓ All results exported!")
  message("  figures/ : volcano_plot, pca_score, plsda_score, rf_importance, roc_curves")
  message("  results/ : univariate_results.csv, plsda_vip.csv, rf_importance.csv, roc_summary.csv")
  message("  data/    : normalized_matrix.csv, analysis_object.rds")
  message("========================================")
}

# Execute if sourced
if (sys.nframe() == 0) {
  main()
}