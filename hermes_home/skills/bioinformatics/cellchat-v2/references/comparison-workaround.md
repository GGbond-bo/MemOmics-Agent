# CellChat 多条件比较图替代方案

## 问题
`mergeCellChat()` 后 `compareInteractions()` / `netVisual_diffInteraction()` / `rankComparison()` 经常无法正常出图：
- 通路集不对称（如 Young=22 vs Old=43）→ 空图 (105B)
- `rankComparison` 在某些 CellChat 版本不存在

## 替代方案：柱状图 + 手动排通路

```r
library(CellChat)
library(ggplot2)

cc_y <- readRDS("cellchat_young.rds")
cc_o <- readRDS("cellchat_old.rds")

# 1. 合并通路列表
young_paths <- data.frame(pathway=cc_y@netP$pathways, group="Young")
old_paths <- data.frame(pathway=cc_o@netP$pathways, group="Old")
all_paths <- rbind(young_paths, old_paths)
all_paths$value <- 1

# 2. 交叉表
path_tbl <- as.data.frame(table(all_paths$pathway, all_paths$group))
colnames(path_tbl) <- c("Pathway","Group","Count")

# 3. 柱状图
path_sum <- aggregate(Count ~ Pathway, path_tbl, sum)
path_tbl$Pathway <- factor(path_tbl$Pathway, levels=path_sum$Pathway[order(-path_sum$Count)])

ggplot(path_tbl, aes(x=reorder(Pathway,Count), y=Count, fill=Group)) +
  geom_bar(stat="identity", position="dodge") +
  coord_flip() +
  labs(title="Signaling Pathways: Young vs Old", y="Detected", x="") +
  scale_fill_manual(values=c(Young="#4DBBD5", Old="#E64B35")) +
  theme_minimal(base_size=12)
```

## 互作数对比

```r
young_int <- sum(cc_y@net$count)  # Young 总互作对数
old_int <- sum(cc_o@net$count)    # Old 总互作对数
cat(sprintf("Young: %d pathways, %.0f interactions\n", length(cc_y@netP$pathways), young_int))
cat(sprintf("Old: %d pathways, %.0f interactions\n", length(cc_o@netP$pathways), old_int))
```

## 关键和弦图 + 热图（正常出图）
这两类图不受 merge 影响，分别对 Young/Old 单独调用即可：
- `netVisual_chord_cell(cc, signaling="LAMININ")` — 和弦图
- `netAnalysis_signalingRole_heatmap(cc, pattern="outgoing")` — 信号角色热图

## 验证日期
2026-07-17，human/skeletal_muscle/aging，CellChat v1.6.2
