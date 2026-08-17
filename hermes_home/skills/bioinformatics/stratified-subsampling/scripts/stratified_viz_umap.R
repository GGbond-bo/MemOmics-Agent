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

# ==== 场景3: 分层可视化抽样 ====
# 每个sample随机抽N个细胞画UMAP，避免overplotting
# 依赖: Seurat对象已有UMAP降维结果

library(Seurat)
library(ggplot2)
library(dplyr)

set.seed(42)

# ---- 配置 ----
SEURAT_RDS <- "path/to/seurat_pca_umap.rds"
N_PER_SAMPLE <- 200          # 每样本最大细胞数
SAMPLE_COL <- "sample_id"    # 样本列名
OUTPUT_DIR <- "results/stratified_viz"

# ---- 加载 ----
seu <- readRDS(SEURAT_RDS)
cat("Total cells:", ncol(seu), "\n")
cat("Samples:", length(unique(seu@meta.data[[SAMPLE_COL]])), "\n")

# ---- 分层抽样 ----
set.seed(42)
cells_to_keep <- c()
for (s in unique(seu@meta.data[[SAMPLE_COL]])) {
  cells_in_sample <- WhichCells(seu, expression = !!sym(SAMPLE_COL) == s)
  n_sample <- length(cells_in_sample)
  n_pick <- min(N_PER_SAMPLE, n_sample)
  picked <- sample(cells_in_sample, n_pick)
  cells_to_keep <- c(cells_to_keep, picked)
  cat(sprintf("  %s: %d -> %d cells\n", s, n_sample, n_pick))
}

seu_sub <- subset(seu, cells = cells_to_keep)
cat(sprintf("\nSubsampled: %d cells (from %d)\n", ncol(seu_sub), ncol(seu)))

# ---- UMAP by celltype ----
umap_df <- Embeddings(seu_sub, "umap") |> as.data.frame()
umap_df$celltype <- seu_sub$celltype
umap_df$sample <- seu_sub@meta.data[[SAMPLE_COL]]

# ---- 绘图 ----
# 按celltype着色
p1 <- ggplot(umap_df, aes(x = umap_1, y = umap_2, color = celltype)) +
  geom_point(size = 0.3, alpha = 0.7) +
  theme_classic(base_size = 12) +
  theme(
    panel.border = element_rect(color = "black", fill = NA, linewidth = 0.8),
    legend.position = "right",
    legend.key.size = unit(0.3, "cm"),
    legend.text = element_text(size = 8),
    axis.text = element_blank(),
    axis.ticks = element_blank(),
    plot.title = element_text(hjust = 0.5, face = "bold", size = 14)
  ) +
  labs(
    title = sprintf("Stratified Sampling UMAP (%d cells/sample)", N_PER_SAMPLE),
    subtitle = sprintf("%d cells | %d samples", ncol(seu_sub), length(unique(umap_df$sample))),
    x = "UMAP 1", y = "UMAP 2"
  ) +
  guides(color = guide_legend(override.aes = list(size = 2.5, alpha = 1)))

# 按sample着色
p2 <- ggplot(umap_df, aes(x = umap_1, y = umap_2, color = sample)) +
  geom_point(size = 0.3, alpha = 0.7) +
  theme_classic(base_size = 12) +
  theme(
    panel.border = element_rect(color = "black", fill = NA, linewidth = 0.8),
    legend.position = "right",
    legend.key.size = unit(0.3, "cm"),
    legend.text = element_text(size = 7),
    axis.text = element_blank(),
    axis.ticks = element_blank(),
    plot.title = element_text(hjust = 0.5, face = "bold", size = 14)
  ) +
  labs(
    title = "UMAP by Sample (stratified subsample)",
    subtitle = sprintf("%d cells | %d/sample", ncol(seu_sub), N_PER_SAMPLE),
    x = "UMAP 1", y = "UMAP 2"
  ) +
  guides(color = guide_legend(override.aes = list(size = 2.5, alpha = 1)))

# ---- 保存 ----
dir.create(file.path(OUTPUT_DIR, "figures"), recursive = TRUE, showWarnings = FALSE)
dir.create(file.path(OUTPUT_DIR, "data"), recursive = TRUE, showWarnings = FALSE)

ggsave(file.path(OUTPUT_DIR, "figures", "umap_celltype_stratified.png"),
       p1, width = 10, height = 7, dpi = 300)
ggsave(file.path(OUTPUT_DIR, "figures", "umap_sample_stratified.png"),
       p2, width = 12, height = 7, dpi = 300)

saveRDS(seu_sub, file.path(OUTPUT_DIR, "data", "seurat_stratified_subsample.rds"))

cat("\nDone!\n")