#!/usr/bin/env Rscript
# ============================================================================
# CNS 级 DotPlot: hdWGCNA 模块 hub 基因 × 条件 (type) — standalone 单图模板
#
# 适用: 用户贴出 DotPlot(seurat_obj, features=mods, group.by='type') 问
#       "怎么把它做成CNS级别的图" / "我只要这个图的CNS级别代码"
# 升级点 (相对裸 DotPlot):
#   1. 基因按模块分组 + kME 排序 (不再手动传任意 features 向量)
#   2. 左侧模块色条: 一眼看出每个基因属于哪个模块
#   3. coord_flip 基因放 Y 轴 — 50-60 个基因放 X 轴会叠成糊, CNS 图必须基因在 Y 轴
#   4. 发表级配色 (蓝白红 diverging, midpoint=0) + Arial 7pt + 0.4 细轴线统一主题
#   5. 分组按逻辑顺序 (Y_Pre→Y_Post→O_Pre→O_Post→OD_Pre→OD_Post)
#   6. 导出 SVG(矢量可编辑) + PDF + TIFF(600dpi) + PNG(300dpi)
#
# 运行:
#   "C:/Program Files/R/R-4.5.3/bin/x64/Rscript" --vanilla cns_dotplot.R
#   (Windows: PATH 上的 Rscript 可能是新装版本没 Seurat — 用装有包的 R + .libPaths 引导)
# ============================================================================

# ---------- 0. 环境 (你的库路径) ----------
.libPaths("E:/R-libs/R-4.5.3")
suppressPackageStartupMessages({
  library(Seurat)
  library(ggplot2)
  library(grid)
  library(gridExtra)
})

# ---------- 1. 路径 (按需修改) ----------
SEURAT <- "E:/骨骼肌锻炼/MF_subset_2000.rds"
HUB    <- "E:/MemOmics-Agent/results/memomics-2f229850/hdwgcna/data/official_hub_genes.csv"
OUT    <- "results/memomics-552311bd"
dir.create(OUT, recursive = TRUE, showWarnings = FALSE)

# ---------- 2. 参数 ----------
mods_show    <- c("blue","red","brown","turquoise","pink","black","yellow","green","magenta","purple")
k_per_module <- 6                       # 每模块 top-k hub 基因
group_order  <- c("Y_Pre","Y_Post","O_Pre","O_Post","OD_Pre","OD_Post")  # 按你 type 列实际值改

mod_cols <- c(blue="#1F77B4", red="#D62728", brown="#8C564B", turquoise="#2CA02C",
              pink="#FF69B4", black="#333333", yellow="#D4B106", green="#228B22",
              magenta="#CC00CC", purple="#7B2FBE")

# ---------- 3. 数据 ----------
seurat_obj <- readRDS(SEURAT)
if (all(group_order %in% unique(seurat_obj$type)))
  seurat_obj$type <- factor(seurat_obj$type, levels = group_order)

hub <- read.csv(HUB)                    # 列: module / gene_name / kME (若报错先 colnames(hub))
genes_per_mod <- lapply(mods_show, function(m) {
  g <- hub[hub$module == m, ]
  g <- g[order(g$kME, decreasing = TRUE), "gene_name"]
  head(g, k_per_module)
})
mods_feat <- unlist(genes_per_mod)
mods_lab  <- rep(mods_show, sapply(genes_per_mod, length))
mods_feat <- mods_feat[mods_feat %in% rownames(seurat_obj)]   # 只留对象里存在的基因
cat("绘图基因数:", length(mods_feat), "\n")

# ---------- 4. CNS 主题 ----------
theme_cns <- theme_classic(base_size = 7) +
  theme(axis.text = element_text(color = "black", family = "sans"),
        axis.text.x = element_text(angle = 45, hjust = 1, size = 6.5),
        axis.text.y = element_text(size = 5),
        axis.ticks = element_line(color = "black", linewidth = 0.4),
        axis.line  = element_line(color = "black", linewidth = 0.4),
        legend.text = element_text(size = 6),
        legend.title = element_text(size = 6.5),
        legend.key.size = unit(3, "mm"),
        plot.margin = margin(4, 4, 2, 2))

# ---------- 5. 主图: DotPlot + coord_flip (基因在 Y 轴) ----------
p <- DotPlot(seurat_obj, features = rev(mods_feat), group.by = "type") +
  coord_flip() +
  scale_color_gradient2(high = "#B2182B", mid = "#F7F7F7", low = "#2166AC",
                        midpoint = 0, name = "Avg exp\n(scaled)") +
  labs(x = NULL, y = NULL) +
  theme_cns

# ---------- 6. 模块色条 (左侧, 与基因顺序对齐) ----------
strip_df <- data.frame(gene = factor(mods_feat, levels = rev(mods_feat)),
                       mod  = factor(mods_lab, levels = mods_show))
gstrip <- ggplot(strip_df, aes(x = 1, y = gene, fill = mod)) +
  geom_tile(width = 0.9, height = 0.92) +
  scale_fill_manual(values = mod_cols, guide = "none") +
  theme_void()

# ---------- 7. 拼合 + 导出 ----------
final <- grid.arrange(ggplotGrob(gstrip), ggplotGrob(p), ncol = 2, widths = c(0.04, 1))
W <- 100; H <- 150   # mm
ggsave(file.path(OUT, "Fig_DotPlot_hdWGCNA_modules_CNS.svg"),  final, width = W, height = H, units = "mm")
ggsave(file.path(OUT, "Fig_DotPlot_hdWGCNA_modules_CNS.pdf"),  final, width = W, height = H, units = "mm")
ggsave(file.path(OUT, "Fig_DotPlot_hdWGCNA_modules_CNS.png"),  final, width = W, height = H, units = "mm", dpi = 300)
ggsave(file.path(OUT, "Fig_DotPlot_hdWGCNA_modules_CNS.tiff"), final, width = W, height = H, units = "mm", dpi = 600, compression = "lzw")
cat("DONE →", OUT, "\n")

# ============================================================================
# Pre-flight verify 要点 (加载 883MB Seurat 前先跑, ~30s):
#   - 语法 parse
#   - 输入文件存在 (SEURAT rds + hub csv)
#   - 包在 .libPaths 引导下可加载 (Seurat/ggplot2/grid/gridExtra)
#   - hub 表契约: 列 module/gene_name/kME, kME numeric, 全部 mods_show 在表中
#   - 基因提取: 期望数 = length(mods_show) * k_per_module (10*6=60, 不是硬编码!)
#     → 计算 length(mods_feat) == length(mods_show)*k_per_module
#   - 无 NA、无跨模块重复 (DotPlot features 不能重复)
#   - group_order 全部在 unique(seurat_obj$type) 中
#   - 全部 mods_feat %in% rownames(seurat_obj)
# ⚠️ 硬编码期望基因数会误报失败: hub 表每模块基因数可能≠k_per_module,
#   期望值必须从实际数据算 (length(mods_show)*k_per_module), 不是拍脑袋写死.
# ============================================================================
