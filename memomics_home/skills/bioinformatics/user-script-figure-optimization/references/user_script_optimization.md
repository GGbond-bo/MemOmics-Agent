# 用户已有绘图脚本的优化协议（完整版 · R/ggplot2/Seurat）

> 本文是 `user-script-figure-optimization` 的详细支撑文档。
> 触发：用户贴出已能跑的绘图脚本 + 要求「按 Nature 优化 / CNS 级 / 出期刊图 / 检查脚本」。
> 全部内容来自真实事故复盘（2026-09-22，人骨骼肌 specialized MF 亚群 UMAP，11,630 核 × 7 亚群 × 6 组，48 样本）。

---

## 事故全景（先看这个，避免重犯）

| 回合 | 我做了什么 | 用户反应 |
|---|---|---|
| 1 | 用户给 DimPlot 代码 + 「按 nature 级别主刊优化」→ 我直接重写：26×8 in 砍成 180×108 mm、`pt.size` 2→0.25、`split.by` 换成 `facet_wrap(ncol=3)`、字号砍到 6 | 「我让你按照 nature 风格优化，怎么比原来的代码还要简陋了？」 |
| 2 | 我加的 `TYPE_LAB[as.character(data$type)]` 引入 `No cell overlap` 报错 | 「你给的代码报错了，修改完善一下」 |
| 3 | 我去联网「核验报错出处」而不是直接修 | 「不是让你改一下报错吗？为啥一直卡着啊？你他妈要干什么？」 |
| 4 | 用户重新贴回原代码 | 「这才是我的原代码，你跑哪去了？还有标题也不居中，你会修改吗？」 |

**三条教训各对应下面一条铁律。** 核心一句话：**用户的脚本是他自己的作品，你是去改它的，不是去替换它的。**

---

## 铁律 0：先谈方向，再动手

用户给脚本 + **风格/标准要求** = **方向选择**，不是「纯代码修改」。动手前至少确认三件事：

1. 保留原画布尺寸 / 面板排布 / 点径吗？（用户往往就喜欢现在的版式）
2. 「优化」= 加投稿规范（矢量导出、字号合规、白底、Source Data），还是重排版式？
3. 只修报错，还是连带做规范增量？

**判据：要求里只要带「风格 / 级别 / 期刊」字样，就先问一句再改**，不要自己判成 code-edit 直接跳过去编辑。
⚠️ 反面清单里那条「生成待办后停下来问要不要开始」禁止的是空话式提问；**这里问的是能改变交付形态的方向问题**，必须问。

---

## 铁律 1：最小改动，逐条列出

| | 允许 | 禁止 |
|---|---|---|
| 参数 | 修 bug、显式化关键参数（如补 `reduction=`） | 改画布尺寸、面板排布（`split.by`→`facet_wrap`）、点径、配色赋值 |
| 结构 | 加导出/源数据块（**新增，不删原有**） | 重写代码结构、删用户写法、按自己风格重构 |
| 输出 | 逐条列「改了 / 为什么 / 风险」 | 只丢一整版新代码让用户自己找差异 |

**刻意不动的地方也要明说**：
- `family="sans"` —— R 在 Windows 下已映射 **Arial**，符合 Nature 字体要求，**不必改**
- `cols=` 与 `scale_color_manual()` 重复设色 —— 虽会产生 warning，但编译没问题，属用户写法，**不越界删**
- 用户的 `theme_void()` + 透明底组合 —— 保持，只把常量抽成变量

说明「我没动它，因为…」比默默删掉更有价值——用户会逐行看你的 diff。

---

## 铁律 2：Nature 级 ≠ 把图缩小（最核心的概念错误）

`pt.size`（ggplot2）/ `s`（matplotlib scatter）是**绝对尺寸**，不是相对量。

| 做法 | 后果 |
|---|---|
| 只砍画布、点径不变 | 点占比变大，糊成实心饼 |
| 只砍点径、画布不变 | 点细如尘，看不见 |
| **两个一起砍** | **图整体退化**（事故之错） |

**画布与点径必须联动。** 规范的本体是：

| 规范项 | 内容 |
|---|---|
| 尺寸×字号解耦 | 先定最终 mm 尺寸，字号按该尺寸下可读性定（正文 5–7 pt，≥5 pt 硬线） |
| 矢量导出 | SVG + PDF（+ TIFF 600 dpi 备位图） |
| Source Data | 投稿附件：每类×每组的细胞数/统计量 CSV |
| 组序可控 | 显式 factor levels，否则字母序替你排序（`OD_Post` 排最前，读者把组序读错） |
| 灰度/色盲可辨 | 出灰度预览确认类别仍可区分 |

⚠️ **几何冲突提醒**：Seurat `DimPlot` 内部带 `coord_fixed()`，面板被强制为正方形。要 3×2 排布就必须 ≈3:2 的画布；硬塞进 3.25:1 的超宽画布会留大片空白。**向用户提这一点，但不要擅自改他的画布。**

---

## 铁律 3：自己引入的 bug 直接修，不要先「核验报错出处」

- 报错出现在**我刚给出的代码**里 → 优先假设是自己写的，直接定位那一行
- 用户说「修一下这个报错」= 立刻给修正后的完整代码，**不做前置查证、不跑流程**
- 依据/来源补在后面，但不能挡住修复

---

## R / ggplot2 / Seurat 具体坑（详细）

### 1. ggplot2 4.x — facet 标题不居中 → 必须写 `strip.text.x.top`

官方原文（ggplot2 **4.0.3** `theme()` 参考页，实地抓取）：

> Facet strips have dedicated position-dependent theme elements (`strip.text.x.top`, `strip.text.x.bottom`, `strip.text.y.left`, `strip.text.y.right`) that inherit from `strip.text.x` and `strip.text.y`, respectively. **As a consequence, some theme stylings need to be applied to the position-dependent elements rather than to the parent elements.**

结论：只写 `strip.text` / `strip.text.x` 时，**位置类样式（`hjust` / `margin`）不保证生效**——真正渲染的是 `strip.text.x.top` 那一层。

修法（三行都写，跨版本兼容）：

```r
theme(
  strip.text       = element_text(face = "bold", size = 9, hjust = 0.5, margin = margin(b = 2)),
  strip.text.x     = element_text(face = "bold", size = 9, hjust = 0.5, margin = margin(b = 2)),
  strip.text.x.top = element_text(face = "bold", size = 9, hjust = 0.5, margin = margin(b = 2)),  # ← 真正生效的一层
  strip.background = element_blank(),
  strip.placement  = "outside"
)
```

排查第一步永远是 `cat(as.character(packageVersion("ggplot2")))`——strip 元素继承行为在 3.5 / 4.x 之间有变化。

同页其它相关元素：
- `legend.title` —— *title of legend (element_text(); inherits from title)*，标题对齐用 `hjust`
- `legend.title.position` —— *"top" / "right" / "bottom" / "left"*，**ggplot2 3.5+ 才有**，低版本传了可能报未知元素
- `strip.placement` —— *"inside" or "outside"，only important when axes and strips are on the same side of the plot*

**备选方案**（若三行都写仍不居中）：反向测试 `strip.text.x.top = element_text(hjust = 0)` 确认该层确实生效；或关掉 strip 改用图内标注。

### 2. Seurat — `No cell overlap between new meta data and Seurat object`

```r
# ✗ TYPE_LAB[as.character(data$type)] 返回【带 names 的向量】，
#   Seurat 把 names 当 cell barcode 去匹配 → 零重叠
data$type_lab <- factor(TYPE_LAB[as.character(data$type)], levels = unname(TYPE_LAB))

# ✓
data$type_lab <- factor(unname(TYPE_LAB[as.character(data$type)]), levels = unname(TYPE_LAB))
```

**通杀规则**：任何赋给 `obj$col <-` / `AddMetaData()` 的向量先 `unname()`。
带 names 的常见来源：`vec[as.character(x)]` 查表、`setNames()`、`table()`、`tapply()`。

⚠️ **本次事故的元教训**：这个报错是**我自己加的代码**造成的——用户的原代码里根本没有那一行。修 bug 前先问「这行是我写的还是用户写的」。

### 3. 高清点图：`pt.size` / `raster` / `raster.dpi`

- `pt.size` 是**最终尺寸下**的点径，与画布英寸联动（铁律 2）
- `raster = TRUE` + `raster.dpi = c(300, 300)` —— **必须是长度 2 的向量**（X/Y 各一）；万级细胞时矢量 PDF 体积不至于爆掉
- 图例单独 `get_legend()` 时必须复用**同一 reduction + 同一 pt.size**：
  - 原脚本常漏写 `reduction=`（依赖 `DefaultDimReduction` 兜底，改过对象后可能取错降维）
  - 漏写 `pt.size` 则默认 1 → **图例的点比图上的点小**，视觉不一致

### 4. R 投稿导出三件套 + Source Data

```r
W_IN <- 26; H_IN <- 8        # 与预览一致，所见即所得
base_file <- file.path(out_dir, "UMAP_subcluster_by_type")

svglite::svglite(paste0(base_file, ".svg"), width = W_IN, height = H_IN)
print(final_plot); dev.off()

grDevices::cairo_pdf(paste0(base_file, ".pdf"), width = W_IN, height = H_IN, family = "sans")
print(final_plot); dev.off()

ragg::agg_tiff(paste0(base_file, ".tiff"), width = W_IN, height = H_IN, units = "in", res = 600)
print(final_plot); dev.off()

# Nature 要求投稿附 Source Data
write.csv(as.data.frame.matrix(table(data$subcluster, data$type)),
          file.path(out_dir, "SourceData_subcluster_by_type.csv"))
```

- 透明底（`element_rect(fill = "transparent")`）适合拼 PPT；投稿需白底 → **用变量控制、默认保持用户原值**：
  ```r
  BG <- "transparent"   # 导出投稿图时改 "white"
  ```
- 依赖：`svglite` / `ragg`（缺则提示安装，不硬编码路径）

### 5. 预览尺寸 = 导出尺寸

```r
options(repr.plot.width = 26, repr.plot.height = 8, repr.plot.res = 100)
```
字号按真实尺寸定，**预览与导出尺寸必须一致**，否则看到的字号/点径都是假的。

---

## 完整示例：最小改动版（改动 5 处，其余逐字保留用户原写法）

```r
library(Seurat); library(ggplot2); library(cowplot)

CELL_PT_SIZE <- 2
BG <- "transparent"      # 保持用户原值；投稿改 "white"

p <- DimPlot(data, reduction = "umap", group.by = "subcluster", split.by = "type",
             cols = specialized_mf_sub_colors, pt.size = CELL_PT_SIZE,
             raster = TRUE, raster.dpi = c(300, 300), label = FALSE) +
  theme_void() +
  theme(
    panel.background = element_rect(fill = BG, colour = NA),
    plot.background  = element_rect(fill = BG, colour = NA),
    strip.text       = element_text(face = "bold", size = 9, hjust = 0.5, margin = margin(b = 2)),
    strip.text.x     = element_text(face = "bold", size = 9, hjust = 0.5, margin = margin(b = 2)),
    strip.text.x.top = element_text(face = "bold", size = 9, hjust = 0.5, margin = margin(b = 2)),  # ← 标题居中
    strip.background = element_blank(),
    strip.placement  = "outside",
    text = element_text(family = "sans", size = 8),
    panel.spacing = unit(0.3, "cm")
  ) +
  scale_color_manual(values = specialized_mf_sub_colors) +
  guides(color = "none")

legend <- get_legend(
  DimPlot(data, reduction = "umap", group.by = "subcluster",
          cols = specialized_mf_sub_colors, pt.size = CELL_PT_SIZE,
          raster = FALSE, label = FALSE) +
    theme(
      legend.title = element_text(size = 7, face = "bold", family = "sans", hjust = 0.5),
      legend.text = element_text(size = 7, family = "sans"),
      legend.key.size = unit(0.35, "cm"),
      legend.key = element_rect(fill = BG, colour = NA),
      legend.spacing.y = unit(0.1, "cm")
    )
)

options(repr.plot.width = 26, repr.plot.height = 8, repr.plot.res = 100)
final_plot <- plot_grid(p, legend, rel_widths = c(1, 0.15), align = "h")
final_plot

## ---- Nature 规范增量（新增块，上面一个设置都没动）----
out_dir <- file.path("results", "UMAP_subcluster_by_type")   # 实际用 results/<sid>/figures/
dir.create(out_dir, showWarnings = FALSE, recursive = TRUE)
# ... 三个导出 + write.csv，见上面第 4 节 ...
```

---

## 交付清单（回复里必须有）

1. **完整可运行代码**（一个代码块，直接复制能跑，不要只给 diff 片段）
2. **改动说明表**（`# / 改动 / 原因·影响`）
3. **刻意没动的地方**（逐条说明理由）
4. 落盘路径（`results/<sid>/scripts/`）+ 一句「要不要我实跑」

---

## 参考来源

- ggplot2 官方 `theme()` 参考页（ggplot2 4.0.3）— https://ggplot2.tidyverse.org/reference/theme.html （strip 段落原文；`legend.title` / `legend.title.position` / `strip.placement` 定义）
- 事故会话：2026-09-22 · 人骨骼肌 specialized MF 亚群 UMAP