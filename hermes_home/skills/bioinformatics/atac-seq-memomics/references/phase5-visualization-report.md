# Phase 5: 可视化 + HTML 报告 — 完整配方

> 适用于 ArchR 分析完成 Phase 4 (TileMatrix + getMarkerFeatures) 后。

## 产出清单

| 产出 | 格式 | 预期大小 |
|------|------|---------|
| UMAP (Cluster) | PNG + PDF | 350KB / 2.1MB |
| UMAP (AgeGroup) | PNG + PDF | 489KB / 2.1MB |
| UMAP (Sample) | PNG + PDF | 751KB / 2.1MB |
| Cluster Composition stacked bar | PNG + PDF | 89KB / 5KB |
| Cell Count CSV | CSV | <1KB |
| HTML Report (base64 embedded) | HTML | 2-5MB |

## Step 1: UMAP 面板（3 幅图）

```r
# UMAP by Cluster
p <- plotEmbedding(ArchRProj=proj, colorBy="cellColData", name="Clusters",
                   embedding="UMAP", plotAs="points", size=1.2, baseSize=14)
ggsave("UMAP_Clusters.pdf", p, width=12, height=10)
ggsave("UMAP_Clusters.png", p, width=12, height=10, dpi=200)

# UMAP by AgeGroup (Young vs Old)
p <- plotEmbedding(ArchRProj=proj, colorBy="cellColData", name="AgeGroup",
                   embedding="UMAP", plotAs="points", size=1.2, baseSize=14)
ggsave("UMAP_AgeGroup.pdf", p, width=12, height=10)

# UMAP by Sample
p <- plotEmbedding(ArchRProj=proj, colorBy="cellColData", name="Sample",
                   embedding="UMAP", plotAs="points", size=1.2, baseSize=14)
ggsave("UMAP_Sample.pdf", p, width=12, height=10)
```

## Step 2: Cluster 组成堆叠柱状图

```r
cell_data <- data.frame(
  Cluster = proj$Clusters,
  AgeGroup = proj$AgeGroup
)

comp_table <- table(cell_data$Cluster, cell_data$AgeGroup)
comp_prop <- prop.table(comp_table, margin=1)
comp_df <- as.data.frame(comp_prop)
colnames(comp_df) <- c("Cluster", "AgeGroup", "Proportion")

# 按 Old 比例排序
old_prop <- comp_prop[, "Old"]
comp_df$Cluster <- factor(comp_df$Cluster, 
                          levels=names(sort(old_prop, decreasing=TRUE)))

ggplot(comp_df, aes(x=Cluster, y=Proportion, fill=AgeGroup)) +
  geom_bar(stat="identity", position="stack", width=0.7) +
  scale_fill_manual(values=c("Young"="#4DBBD5", "Old"="#E64B35")) +
  labs(title="Cluster Composition by Age Group", x="Cluster", y="Proportion") +
  theme_minimal(base_size=14) +
  theme(axis.text.x=element_text(angle=45, hjust=1))
```

## Step 3: 细胞计数 CSV

```r
count_table <- table(cell_data$Cluster, cell_data$AgeGroup)
count_df <- as.data.frame.matrix(count_table)
count_df$Total <- rowSums(count_df)
count_df$Old_pct <- round(count_df$Old / count_df$Total * 100, 1)
count_df <- count_df[order(-count_df$Total), ]
write.csv(count_df, "Cell_Counts_by_Cluster.csv")
```

## Step 4: HTML 报告（Python + base64 嵌入）

⚠️ **不要用 MemOmics 内建 `generate_report` 工具** — 它只生成 ~40KB 轻量框架（文字+外部链接），不嵌入图片。多图报告必须手动构建 HTML。

```python
import base64, os

def img_b64(path):
    """Read image → base64 data URI"""
    if not os.path.exists(path) or os.path.getsize(path) < 100:
        return f"<!-- {os.path.basename(path)} not found -->"
    with open(path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode()
    ext = path.rsplit(".",1)[-1].lower()
    mime = "image/png" if ext == "png" else "image/jpeg"
    return f"data:{mime};base64,{b64}"

# 在 HTML 模板中用 {img_b64('file.png')} 嵌入
```

### HTML 模板结构

```
.header (渐变背景 + 标题 + 分析描述)
.cards (6 格：总细胞数、Clusters、Old/Young 计数、Tiles 数、DA tiles 数)
.section: 分析流程 (Phase 1-5 状态 timeline)
.section: UMAP 面板 (3 幅图：Cluster / AgeGroup / Sample)
.section: 细胞组成 (堆叠柱状图 + 排序表格 with Old% 列)
.section: 差异可及性 (Volcano + MA 图 + 关键发现框)
.section: 方法参数表
.section: 产出文件清单
.footer (生成工具 + 版本)
```

### 色彩方案

| 元素 | 颜色 |
|------|------|
| Old | `#E64B35` (红) |
| Young | `#4DBBD5` (蓝) |
| Header bg | `linear-gradient(135deg, #2c3e50, #3498db)` |
| Cards bg | `white, box-shadow` |
| Old-enriched 行 | `background: #fdecea` |
| Young-enriched 行 | `background: #e8f4f8` |

## 验证检查清单

```python
checks = [
    ("HTML report exists", os.path.getsize("ArchR_ATAC_Analysis_Report.html") > 1_000_000),
    ("UMAP_Clusters.png", os.path.getsize("UMAP_Clusters.png") > 100_000),
    ("UMAP_AgeGroup.png", os.path.getsize("UMAP_AgeGroup.png") > 100_000),
    ("UMAP_Sample.png", os.path.getsize("UMAP_Sample.png") > 100_000),
    ("HTML has DOCTYPE", html.startswith("<!DOCTYPE")),
    ("HTML has base64 img", "data:image/png;base64," in html),
]
```

## 参考产出

2026-07-29 猴海马 scATAC (35,879 cells, 21 clusters, Old=5,591 / Young=30,288):
- HTML 报告: 2.4MB, 11/11 checks passed
- C12 95.8% Old-enriched, C1 100% Old, C16 96.6% Young
- 6,085,841 tiles, 50 DA (strict), Volcano+MA plots 均正常
