# Nature 风格 UMAP 特征图（Publication-Quality Feature Plots）

> 生成 Nature 期刊风格的 UMAP 基因表达特征图。适用于任何 scRNA-seq 数据，可与 scanpy 或 scTour 分析配合使用。

## 规格要求

| 参数 | 值 | 说明 |
|:----|:---|:----|
| 尺寸 | **4×4 inches** | 单图标准尺寸 |
| DPI | **300** | 出版级分辨率 |
| 背景 | **透明** | 透明 PNG/PDF，方便排版 |
| 格式 | **PNG + PDF 双格式** | PNG 用于展示，PDF 用于矢量编辑 |
| 色图 | 蓝→白→红渐变 | 低表达（蓝）→中（白）→高（红） |
| 轴 | 无刻度/无标签/无边框 | Nature 极简风格 |
| 点大小 | 0.5-1.0（视细胞数而定） | 11,630 cells → 0.8 |

## Python 实现

```python
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import LinearSegmentedColormap

# 构建 Nature 风格色图
colors_nature = [
    (0, '#053061'),       # 深蓝（低表达）
    (0.25, '#4393C3'),    # 中蓝
    (0.5, '#F7F7F7'),     # 白（中值）
    (0.75, '#D6604D'),    # 鲑鱼色（高）
    (1.0, '#67001F'),     # 深红（最高）
]
nature_cmap = LinearSegmentedColormap.from_list('nature_heat', colors_nature, N=256)

# Nature 风格设置
plt.rcParams.update({
    'font.family': 'sans-serif',
    'font.sans-serif': ['Arial', 'Helvetica', 'DejaVu Sans'],
    'font.size': 8,
    'axes.linewidth': 0.5,
    'axes.spines.top': False,
    'axes.spines.right': False,
    'figure.dpi': 300,
    'savefig.dpi': 300,
    'savefig.transparent': True,
})

def nature_feature_plot(adata, gene, umap_key='X_umap',
                         figsize=(4, 4), dpi=300,
                         cmap=nature_cmap,
                         point_size=0.8,
                         title_size=10,
                         output_dir='.'):
    """生成 Nature 风格 UMAP 特征图。"""
    umap_coords = adata.obsm[umap_key]
    exp = adata[:, gene].X
    if hasattr(exp, 'toarray'):
        exp = exp.toarray().flatten()
    else:
        exp = np.array(exp).flatten()

    # 按表达值排序（低表达画在底层）
    order = np.argsort(exp)

    fig, ax = plt.subplots(figsize=figsize, dpi=dpi)
    fig.patch.set_alpha(0)
    ax.patch.set_alpha(0)

    scatter = ax.scatter(
        umap_coords[order, 0], umap_coords[order, 1],
        c=exp[order], cmap=cmap, s=point_size,
        rasterized=True, linewidths=0, alpha=1.0,
    )

    # 移除轴元素
    ax.set_xticks([])
    ax.set_yticks([])
    ax.spines['left'].set_visible(False)
    ax.spines['bottom'].set_visible(False)

    # 基因名作为标题（左上角，Nature 风格）
    ax.set_title(gene, fontsize=title_size, fontweight='bold',
                 pad=2, loc='left', color='#2D2D2D')

    # 色标
    cbar = plt.colorbar(scatter, ax=ax, shrink=0.4, aspect=12,
                        pad=0.02, fraction=0.05)
    cbar.outline.set_visible(False)
    cbar.ax.tick_params(labelsize=6, colors='#555555', width=0.5, length=2)
    cbar.ax.locator_params(nbins=4)

    plt.tight_layout(pad=0.1)

    # 保存 PNG + PDF（透明底）
    fig.savefig(f"{output_dir}/{gene}_umap_nature.png",
                dpi=dpi, bbox_inches='tight', transparent=True, pad_inches=0.05)
    fig.savefig(f"{output_dir}/{gene}_umap_nature.pdf",
                dpi=dpi, bbox_inches='tight', transparent=True, pad_inches=0.05, format='pdf')
    plt.close(fig)
```

## 输出文件

| 文件 | 格式 | 用途 |
|:----|:----|:----|
| `{gene}_umap_nature.png` | PNG (300 DPI) | PPT 展示/快速预览 |
| `{gene}_umap_nature.pdf` | PDF (矢量) | Illustrator 编辑/论文投稿 |
| `{gene}_umap_nature_with_labels.png` | PNG | 带亚群标签的预览版 |
| `{gene}_umap_dark.png` | PNG | 深色背景版（Nature Methods 风格） |
| `{gene1}_{gene2}_{gene3}_combined.png` | PNG | 多基因组合排版 |

## 色图选择

| 风格 | 色图 | 适用场景 |
|:----|:----|:--------|
| Nature 标准 | 蓝→白→红 | 论文正文图 |
| Nature Methods | 黑→蓝→黄→橙 | 深色背景预览 |
| Viridis | 紫→蓝→绿→黄 | scanpy 默认 |
| 单色渐变 | 白→蓝 | 保守型审稿人友好 |

## 验证标准

生成后运行以下检查：

```python
from PIL import Image
img = Image.open(f"{output_dir}/{gene}_umap_nature.png")
assert os.path.getsize(f"{output_dir}/{gene}_umap_nature.png") > 50000, "图太小"
dpi = img.info.get('dpi', (0, 0))
assert dpi[0] >= 300, f"DPI {dpi[0]} < 300"
# 检查是否透明（RGBA 模式 = 透明）
assert img.mode == 'RGBA', f"模式 {img.mode} 不是透明 RGBA"
```

## 实战案例

2026-07-09 人类骨骼肌 SMF 数据（11,630 cells）：生成 RUNX1、COL19A1、ANKRD1 三基因的 Nature 风格 UMAP 特征图，20 个文件（10 PNG + 10 PDF），全部通过健康度检查。