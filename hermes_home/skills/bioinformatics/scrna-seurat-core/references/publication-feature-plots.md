# Publication-Quality UMAP Feature Plots (Nature/Cell/Style)

## When to Use

When you need UMAP feature plots (gene expression overlaid on UMAP) for **publication in high-impact journals** (Nature, Cell, Science, etc.). These plots have specific requirements different from exploratory/default matplotlib/Seurat plots.

## Key Parameters

### Nature-Style Color Scheme (most common)

| Element | Value | Reason |
|---------|-------|--------|
| **Low expression** | `#F5F5F5` (light grey) | Invisible background, no distraction |
| **High expression** | `#CC0000` or `#f32a1f` (deep red) | Nature most common choice |
| **Background** | Transparent | For figure panel compositing |
| **Point size** | 0.3–0.8 (per cell count) | Smaller for 10k+ cells |
| **Point border** | `edgecolor='none'` or `linewidth=0` | No dot borders |
| **Axes** | None (`axis('off')` or `theme_void()`) | Clean panels |
| **Title** | Italic, 14–16pt, centered | Gene symbol, italicized |
| **Legend** | None (single-panel) or external color bar | Save space |

### Code Templates

#### R / ggplot2 (most flexible, no Seurat needed)

```r
library(ggplot2)

df <- read.csv("smf_plot_data.csv")

ggplot(df, aes(x = UMAP_1, y = UMAP_2)) +
  geom_point(aes(color = RUNX1), size = 0.4, alpha = 1) +
  scale_color_gradient(low = "grey", high = "#f32a1f") +
  theme_void() +
  theme(
    plot.title = element_text(hjust = 0.5, size = 16, face = "italic"),
    legend.position = "none",
    panel.border = element_blank(),
    panel.grid = element_blank(),
    panel.background = element_blank(),
    plot.background = element_blank()
  ) +
  ggtitle("RUNX1")
```

#### R / scCustomize (Seurat FeaturePlot wrapper)

```r
library(Seurat)
library(scCustomize)

FeaturePlot_scCustom(
  seurat_object = obj,
  features = "RUNX1",
  order = TRUE,
  pt.size = 0.4
) + 
  scale_color_gradient(low = "grey", high = "#f32a1f") +
  theme_void() +
  theme(
    plot.title = element_text(hjust = 0.5, size = 16, face = "italic"),
    legend.position = "none",
    panel.background = element_blank(),
    plot.background = element_blank()
  )
```

#### Python / matplotlib (fallback when R is unstable)

```python
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap
import numpy as np

# Nature-style red colormap
colors = [(0.93, 0.93, 0.93), (0.95, 0.0, 0.12)]
nature_red = LinearSegmentedColormap.from_list('nature_red', colors, N=256)

fig, ax = plt.subplots(figsize=(4, 4))
order = np.argsort(df[gene].values)

ax.scatter(
    df['UMAP_1'].values[order], df['UMAP_2'].values[order],
    c=df[gene].values[order], cmap=nature_red,
    s=0.4, edgecolors='none', linewidth=0, rasterized=True
)
ax.set_title(gene, fontsize=16, fontstyle='italic')
ax.axis('off')
fig.patch.set_alpha(0); ax.patch.set_alpha(0)

fig.savefig(f"{gene}_umap.png", dpi=300, bbox_inches='tight',
            pad_inches=0, transparent=True)
fig.savefig(f"{gene}_umap.pdf", bbox_inches='tight',
            pad_inches=0, transparent=True)
```

### Common Pitfalls

| Pitfall | Solution |
|---------|----------|
| **viridis/rainbow colormap** | ❌ Rejected by reviewers. Use single-color gradient (grey→red, grey→blue) |
| **Non-transparent background** | ❌ Can't composite panels. Set `transparent=True` or `plot.background = element_blank()` |
| **Axis ticks/labels showing** | ❌ Clutters the figure. Use `theme_void()` / `axis('off')` |
| **Dot borders visible** | ❌ Makes dots look like bubbles. Set `edgecolor='none'`, `linewidth=0` |
| **Too small resolution** | ❌ Reviewers will see pixelation. Use **300 dpi minimum** |
| **Only PNG, no PDF** | ❌ Journals need vector formats. Always save both PNG + PDF |
| **R memory crash on large data** | ⚠️ Fallback: extract data via Python/scanpy backed mode, save CSV, plot in Python matplotlib |
| **Order not set (order=F)** | ❌ Low-exp cells hide high-exp cells. Always order=T |

### The "4-in" Rule (Nature Editor Standard)

For a panel to be publication-ready:
1. **4 inches × 4 inches** (common panel size, 1-column width)
2. **300 dpi** (print resolution)
3. **Transparent background** (for compositing in Illustrator/Inkscape)
4. **Both PNG + PDF** (preview + vector editable)

### Fallback Strategy: When R Crashes on h5ad Data

1. Use Python scanpy with `backed='r'` mode to extract expression data
2. Save as CSV (UMAP coords, subcluster, expression of target genes)
3. Plot in Python matplotlib with the Nature-style parameters above
4. Or restart R session and try with smaller data chunks

### Session Example: SMF UMAP Feature Plots

In the SMF analysis session, 3 genes were plotted on full UMAP:
- **RUNX1** (去神经核心TF) — high in zone1/zone3
- **COL19A1** (NMJ重塑基底层) — high in zone1→zone2 boundary + NMJ
- **ANKRD1** (机械应力) — high in zone4 (97% cells)

The grey→red gradient revealed zone-specific patterns that viridis would have obscured.