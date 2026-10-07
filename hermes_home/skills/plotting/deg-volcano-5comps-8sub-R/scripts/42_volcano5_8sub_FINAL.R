# -*- coding: utf-8 -*-
# =============================================================================
# 42_volcano5_8sub_FINAL.R   ← 最终版（替代 41 号）
# 用户三条指示：
#   ① 画布宽度不够 → 亚群名挤在一起  → 加宽到 14 x 7 inch（300dpi = 4200x2100）
#      依据：标签最大宽 "Pure Type IIA" = 1.415 inch @17.1pt(size=6)
#            8 个色块并排每块 = 1.66 inch > 1.415 inch → 不再重叠
#   ② 用的数据不对：应使用已过滤表 DEG_fdr05_coef025_5contrasts.xlsx
#      （新方法 bayesglm+RUV，FDR<0.05 且 |coef|>=0.25；与用户 D:/我的下载/ 那份 md5 相同）
#      → 表里不存在 fdr>=0.05 的行，故【不显著(灰)类别整类删除】
#   ③ 只要最终版五个图
# 样式：一字不改地复刻用户 notebook（cell#3/#4/#6/#7）
#       背景灰柱 + 全部基因抖动点 + top5 基因标注 + y=0 彩色亚群标签块 + p3 主题
#       点径 1.5 / 标签 size=6 / 轴标题 13 / 图例 15 —— 全部沿用原稿，未改
# =============================================================================
suppressPackageStartupMessages({
  library(openxlsx); library(ggplot2); library(ggrepel); library(dplyr)
})

## ---- 输入：用户指定的已过滤表（优先用户路径，缺失则用会话内同 md5 副本）----
F1 <- "D:/我的下载/DEG_fdr05_coef025_5contrasts.xlsx"
F2 <- "E:/MemOmics-Agent/results/memomics-afd2d418/task2/results/DEG_fdr05_coef025_5contrasts.xlsx"
SRC_FILE <- if (file.exists(F1)) F1 else F2
cat("#TASK:PARAM 输入表=", SRC_FILE, "\n", sep = "")

OUT <- "E:/MemOmics-Agent/results/memomics-afd2d418/task3/figures"
SRC <- "E:/MemOmics-Agent/results/memomics-afd2d418/task3/results"
dir.create(OUT, showWarnings = FALSE, recursive = TRUE)
dir.create(SRC, showWarnings = FALSE, recursive = TRUE)

W_IN <- 14; H_IN <- 7          # 加宽（原 8 x 6）
cat("#TASK:PARAM 画布=", W_IN, "x", H_IN, " inch @300dpi\n", sep = "")

ORDER <- c("Pure Type I", "Pure Type IIA", "Pure Type IIX", "LRP1B+(I)",
           "RP_high(I)", "RP_high(II)", "OTUD1+(I)", "OTUD1+(II)")

# 用户原色板（9 色取前 8）+ 对应文字色（labelcol 前 8）
mycol    <- c("#2f3084", "#76a5d9", "#43a8a8", "#3c75a9", "#197638",
              "#a44395", "#f9a213", "#dba478")
labelcol <- c("white", "black", "black", "black", "white", "white", "black", "black")

COMPS <- list(
  list(label = "Aging",    sheet = "Y_Pre_vs_O_Pre"),
  list(label = "DM",       sheet = "O_Pre_vs_OD_Pre"),
  list(label = "Ex_Young", sheet = "Y_Pre_vs_Y_Post"),
  list(label = "Ex_Old",   sheet = "O_Pre_vs_O_Post"),
  list(label = "Ex_DM",    sheet = "OD_Pre_vs_OD_Post")
)

# ===== 用户 2026-09-30 确认的补丁：仅补标 TMSB4X 一处 =====
# 背景：TMSB4X 在 DM / OTUD1+(I) / up 的 |coef|=1.619（DM 全表最大），
#       但 FDR=2.09e-03，被 fdr<=0.001 硬门槛挡在 top5 候选池外 → 图上无标签。
# 用户明确选择「只补标 TMSB4X 一处」→ 其余 4 张图、其余中等显著行一律不动。
# 说明：该点本来就已经画在图上（mid_sig_black 黑点），此处只是补上基因名标签，
#       不改变任何点的颜色/位置，也不改变 y 轴范围（点已存在）。
EXTRA_LABELS <- data.frame(
  sheet    = "O_Pre_vs_OD_Pre",    # DM 对比
  celltype = "OTUD1+(I)",
  group    = "up",
  gene     = "TMSB4X",
  stringsAsFactors = FALSE
)

# 只保留 3 类（不显著整类删除：输入已过滤，无 fdr>=0.05 行）
color_values <- c(
  "down_high"     = "blue",
  "up_high"       = "red",
  "mid_sig_black" = "black"
)

wb <- loadWorkbook(SRC_FILE)
summary_rows <- list()

for (cs in COMPS) {
  cat("#TASK:STAGE 读入 ", cs$label, "\n", sep = "")
  dd <- as.data.frame(openxlsx::read.xlsx(wb, sheet = cs$sheet))
  # 数据自检：regulation 列 vs coef 符号是否一致（不一致则以下游为准并报警）
  mm <- sum((dd$coef > 0) != (dd$regulation == "Up"), na.rm = TRUE)
  stopifnot(mm == 0)
  stopifnot(max(dd$fdr[dd$celltype %in% ORDER]) < 0.05)   # 确认已过滤：无 fdr>=0.05

  aging <- dd %>%
    filter(celltype %in% ORDER) %>%
    mutate(celltype = factor(celltype, levels = ORDER),
           group    = ifelse(coef > 0, "up", "down")) %>%
    select(gene, celltype, coef, fdr, group)

  # ===== 以下为用户原代码（cell#3 / #4 / #6 / #7），逻辑照抄；仅去掉 not_sig_grey =====
  aging <- aging %>%
    mutate(
      sig = case_when(
        fdr <= 0.001 ~ "fdr <= 0.001",
        fdr > 0.001 & fdr < 0.05 ~ "0.001 < fdr < 0.05"
      ),
      color_group = case_when(
        fdr <= 0.001 & group == "up"   ~ "up_high",
        fdr <= 0.001 & group == "down" ~ "down_high",
        TRUE                           ~ "mid_sig_black"
      )
    )

  top_genes <- aging %>%
    filter(fdr <= 0.001) %>%
    group_by(celltype, group) %>%
    arrange(desc(abs(coef))) %>%
    slice_head(n = 5) %>%
    ungroup()
  top_genes$source <- "top5"          # 溯源列：规则内 top5
  # tibble → 普通 data.frame（base::rbind 对 tbl_df 校验严格，必须先降级）
  top_genes <- as.data.frame(top_genes, stringsAsFactors = FALSE)

  # ---- 补标（用户确认的 TMSB4X 一处）：从数据里取真实 coef/fdr，不写死数值 ----
  ex <- EXTRA_LABELS[EXTRA_LABELS$sheet == cs$sheet, , drop = FALSE]
  if (nrow(ex) > 0) {
    for (i in seq_len(nrow(ex))) {
      hit <- which(aging$gene == ex$gene[i] &
                   as.character(aging$celltype) == ex$celltype[i] &
                   aging$group == ex$group[i])
      stopifnot(length(hit) == 1)     # 硬校验：必须精确命中 1 行，否则直接报错
      supp <- data.frame(gene = aging$gene[hit], celltype = aging$celltype[hit],
                         coef = aging$coef[hit], fdr = aging$fdr[hit],
                         group = aging$group[hit], source = "manual_supplement",
                         stringsAsFactors = FALSE)
      cat("#TASK:PARAM 追加前 top_genes=", nrow(top_genes), "x", ncol(top_genes),
          " | supp=", nrow(supp), "x", ncol(supp), "\n", sep = "")
      # 用 dplyr::bind_rows（base::rbind 对 tbl_df 会校验失败：numbers of columns ...）
      top_genes <- dplyr::bind_rows(top_genes, supp)
      cat("#TASK:PARAM 追加后 top_genes=", nrow(top_genes), "x", ncol(top_genes), "\n", sep = "")
      cat("#TASK:PARAM 补标=", ex$gene[i], " | ", ex$celltype[i], " | ", ex$group[i],
          " | coef=", round(aging$coef[hit], 4), " | fdr=", signif(aging$fdr[hit], 3),
          " (规则外补标)\n", sep = "")
    }
  }

  dfbar <- aging %>%
    group_by(celltype) %>%
    summarise(up = max(coef), down = min(coef), .groups = "drop")

  p <- ggplot() +
    geom_col(data = dfbar, mapping = aes(x = celltype, y = up),
             fill = "#f0f0f0", alpha = 0.7, width = 0.6) +
    geom_col(data = dfbar, mapping = aes(x = celltype, y = down),
             fill = "#f0f0f0", alpha = 0.7, width = 0.6) +
    geom_jitter(data = aging,
                aes(x = celltype, y = coef, color = color_group),
                size = 1.5, width = 0.25, height = 0, alpha = 0.7) +
    geom_text_repel(data = top_genes,
                    aes(x = celltype, y = coef, label = gene),
                    force = 1.2, segment.color = NA,
                    max.overlaps = 30, max.iter = 10000,
                    color = ifelse(top_genes$group == "up", "red4", "blue4")) +
    scale_color_manual(
      name = "Regulation & FDR",
      values = color_values,
      labels = c(
        "down_high"     = "Down (FDR <= 0.001)",
        "up_high"       = "Up (FDR <= 0.001)",
        "mid_sig_black" = "Moderate Sig (0.001 < FDR < 0.05)"
      )
    ) +
    labs(x = "Cell Type", y = "Coefficient (log2FC)") +
    theme_bw() +
    theme(
      axis.text.x = element_text(angle = 45, hjust = 1),
      axis.line.y = element_line(color = "black", linewidth = 1.2),
      legend.position = "right"
    )

  dfcol <- data.frame(
    x = factor(ORDER, levels = ORDER),
    y = 0,
    label = ORDER,
    labelcol = labelcol
  )

  p2 <- p +
    geom_tile(data = dfcol, aes(x = x, y = y),
              height = 0.5 * 2 * 0.4, color = "black",
              fill = mycol, show.legend = FALSE) +
    geom_text(data = dfcol, aes(x = x, y = y, label = label),
              size = 6, color = dfcol$labelcol)

  p3 <- p2 +
    labs(x = "Celltype", y = "Coefficient (log2FC)") +
    theme_minimal() +
    theme(
      axis.title = element_text(size = 13, color = "black", face = "bold"),
      axis.line.y = element_line(color = "black", size = 1.2),
      axis.line.x = element_blank(),
      axis.text.x  = element_blank(),
      panel.grid = element_blank(),
      legend.position = "top",
      legend.direction = "vertical",
      legend.justification = c(0, 0),
      legend.text = element_text(size = 15),
      legend.spacing.y = unit(0.2, "cm"),
      legend.title = element_text(face = "bold")
    ) +
    guides(color = guide_legend(override.aes = list(size = 4.5)))

  stem <- paste0("fig_volcano_", cs$label, "_8sub_FINAL")
  cat("#TASK:STAGE 出图 ", cs$label, "\n", sep = "")
  ggsave(file.path(OUT, paste0(stem, ".png")), p3, width = W_IN, height = H_IN, dpi = 300)
  ggsave(file.path(OUT, paste0(stem, ".pdf")), p3, width = W_IN, height = H_IN, device = cairo_pdf)
  ggsave(file.path(OUT, paste0(stem, ".svg")), p3, width = W_IN, height = H_IN)
  ggsave(file.path(OUT, paste0(stem, ".tiff")), p3, width = W_IN, height = H_IN,
         dpi = 300, device = "tiff", compression = "lzw", type = "cairo")

  write.csv(top_genes[, c("celltype", "group", "gene", "coef", "fdr", "source")],
            file.path(SRC, paste0(stem, "_toplabels.csv")), row.names = FALSE)

  cat("#TASK:OUTPUT ", file.path(OUT, paste0(stem, ".png")), "\n", sep = "")
  summary_rows[[cs$label]] <- data.frame(
    comparison = cs$label, sheet = cs$sheet,
    n_points = nrow(aging), n_celltype = nlevels(aging$celltype),
    down_FDR001 = sum(aging$color_group == "down_high"),
    up_FDR001   = sum(aging$color_group == "up_high"),
    mid_sig     = sum(aging$color_group == "mid_sig_black"),
    not_sig     = 0L,
    n_labels    = nrow(top_genes),
    ymin = round(min(aging$coef), 3), ymax = round(max(aging$coef), 3)
  )
  cat("   ", cs$label, ": ", nrow(aging), " points x ", nlevels(aging$celltype),
      " subclusters\n", sep = "")
}

sm <- bind_rows(summary_rows)
write.csv(sm, file.path(SRC, "fig_volcano_5comps_8sub_FINAL_summary.csv"), row.names = FALSE)
cat("#TASK:STAGE 完成\n")
print(sm)