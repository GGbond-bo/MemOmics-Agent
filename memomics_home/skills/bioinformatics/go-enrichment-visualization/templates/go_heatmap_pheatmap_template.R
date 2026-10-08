# ============================================================
# GO 富集热图 — pheatmap 用户参考代码模板 (可复用 · 2026-09-08 验收版)
# 输入: xlsx 表 (Cluster|Path|Genes|Log(q-value))
# 规则(用户 2026-09-08 明确要求, 全部照做):
#   ① 列序 = unique(d$Cluster)  ← Excel 出现顺序即用户排好的左→右/高→低, 禁止自排序
#   ② 行序 = 每个词条按所属最靠前亚群定位(共享词条跟亚群顺序走)
#   ③ 基因: 单亚群词条 2-3 个; 跨亚群合并词条 4 个(重合/代表性), 从数据真实基因列表按亚群生物学挑选
#   ④ 配色: colorRampPalette(c("#FDE0DD","#FF9999","#8B0000"))(100)  ← 低端是浅粉红 #FDE0DD, 不是纯白!
#   ⑤ legend 必须同时传 legend_breaks=c(0,5,10) + legend_labels=c("0","5","10"), 否则刻度变 10/8/6/4/2
#   ⑥ 行\列不聚类, angle_col=45, display_numbers=FALSE, border_color=NA
# 用法: execute_r (R 4.5.3, 自带 openxlsx + pheatmap, 无需 CSV bridge)
#       source(".../go_heatmap_pheatmap_template.R", encoding="UTF-8")
# ============================================================
suppressMessages({library(pheatmap); library(RColorBrewer); library(openxlsx)})

setwd("E:/MemOmics-Agent/results/<SESSION_DIR>")   # ← 改

d <- read.xlsx("输入路径.xlsx", sheet = "Sheet1")  # ← 改
d$logq_abs  <- abs(d$`Log(q-value)`)
d$logq_clip <- pmin(d$logq_abs, 10)

# ---------- 1. 列顺序 = Excel 亚群出现顺序 (用户已排好, 禁止重新排序) ----------
clusters <- unique(d$Cluster)

# ---------- 2. 行顺序 = 词条按所属最靠前亚群 index 排序 ----------
cl_idx <- setNames(seq_along(clusters), clusters)
terms  <- unique(d$Path)
first_idx <- sapply(terms, function(p) min(cl_idx[d$Cluster[d$Path == p]]))
path_order <- terms[order(first_idx, match(terms, d$Path))]

# ---------- 3. 每词条代表性基因 (示例; 按新数据重新挑选, 从真实基因列表选) ----------
path_genes <- list(
  # 单亚群词条→3个; 跨亚群合并词条→4个(重合/代表优先)
  "glycolytic process"            = c("ENO3","PFKM","GPI","PKM"),        # IIA+IIX 共享
  "striated muscle contraction"   = c("TNNT3","TNNI2","TPM1","CACNB2"),  # IIA+I 共享
  "neuromuscular junction"        = c("CHRNA1","MUSK","LRP4"),           # NMJ 单亚群→3
  "translation"                   = c("EEF2","RPL7A","RPS6","FAU")       # RP_high(I/II) 共享
)

# ---------- 4. 构建矩阵 (0 填充稀疏矩阵; 无数据格=0) ----------
path_order <- path_order[path_order %in% d$Path]
m <- matrix(0, nrow = length(path_order), ncol = length(clusters),
            dimnames = list(path_order, clusters))
for (i in seq_along(path_order)) {
  sub <- d[d$Path == path_order[i], ]
  for (j in seq_len(nrow(sub))) m[i, sub$Cluster[j]] <- sub$logq_clip[j]
}
row_lbl <- sapply(path_order, function(p)
  paste0(p, "\n(", paste(path_genes[[p]], collapse = ", "), ")"))
rownames(m) <- row_lbl
cat("矩阵:", nrow(m), "x", ncol(m), "| 非零:", round(sum(m > 0)/length(m)*100, 1), "%\n")

# ---------- 5. 绘制 (用户参考代码原样 + legend_breaks 锁刻度) ----------
my_colors <- colorRampPalette(c("#FDE0DD", "#FF9999", "#8B0000"))(100)

png("figures/GO_heatmap_MF_SMF.png", width = 2600, height = 3200, res = 300)
pheatmap(m,
  color = my_colors,
  cluster_rows = FALSE, cluster_cols = FALSE, display_numbers = FALSE,
  fontsize_row = 9, fontsize_col = 10, angle_col = 45, border_color = NA,
  legend = TRUE,
  legend_breaks = c(0, 5, 10),
  legend_labels = c("0", "5", "10"),
  legend_title = "-log10 Q")
dev.off()
pdf("figures/GO_heatmap_MF_SMF.pdf", width = 9, height = 11)
pheatmap(m,
  color = my_colors,
  cluster_rows = FALSE, cluster_cols = FALSE, display_numbers = FALSE,
  fontsize_row = 9, fontsize_col = 10, angle_col = 45, border_color = NA,
  legend = TRUE, legend_breaks = c(0,5,10), legend_labels = c("0","5","10"),
  legend_title = "-log10 Q")
dev.off()
svg("figures/GO_heatmap_MF_SMF.svg", width = 9, height = 11)
pheatmap(m,
  color = my_colors,
  cluster_rows = FALSE, cluster_cols = FALSE, display_numbers = FALSE,
  fontsize_row = 9, fontsize_col = 10, angle_col = 45, border_color = NA,
  legend = TRUE, legend_breaks = c(0,5,10), legend_labels = c("0","5","10"),
  legend_title = "-log10 Q")
dev.off()
cat("✔ figures/GO_heatmap_MF_SMF.{png,pdf,svg}\n")