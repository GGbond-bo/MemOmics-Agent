---
name: user-script-figure-optimization
description: >-
  优化【用户已经能跑的绘图脚本】——以用户脚本为唯一基线做最小改动，按期刊标准
  （Nature/CNS/投稿级）做规范增量，不重写用户代码。覆盖：先谈方向再动手的确认协议、
  「Nature 级 ≠ 把图缩小」的绝对尺寸/画布联动原则、自己引入 bug 的直接修复协议，
  以及 R/ggplot2/Seurat 的具体坑（facet 标题居中、metadata 赋值报错、pt.size/raster、
  矢量导出 + Source Data）。触发词：「按 nature 优化」「帮我改一下我的脚本」
  「检查一下这个脚本」「我的画图代码」「CNS 级出图」「改成发表级」「这个图怎么优化」
  「Seurat DimPlot 优化」「UMAP 出图改一下」。适用于任何「用户给脚本 + 要求提升图质量」
  的场景，R 与 Python 均适用，R/ggplot2 侧有专门小节。
when_to_use: >-
  [user-script-figure-optimization] 用户贴出自己的绘图脚本要优化/检查/提到期刊级标准时
version: 1.0.0
author: MemOmics
license: MIT
platforms: [windows, linux, macos]
metadata:
  hermes:
    tags: [visualization, ggplot2, seurat, umap, publication-figure, user-script, 07_可视化]
    difficulty: basic
    language: R+Python
    category: Visualization
---

# 用户已有绘图脚本的优化（以脚本为基线）

用户贴出**自己已经能跑**的绘图脚本，要求「按 Nature 优化 / CNS 级 / 检查脚本 / 改成发表级」。
本 skill 管的是这一类工作，**不是**从零画图。

> 详细事故复盘 + 完整 R/ggplot2/Seurat 代码见 `references/user_script_optimization.md`。

## 何时使用

- 用户消息里含一段**可运行的绘图代码** + 任何风格/级别/期刊字样
- 「帮我改一下我的脚本」「检查一下这个脚本」「这个图怎么优化」
- 「按 nature 风格优化」「CNS 级」「发表级」「投稿用图」（**用在用户已有脚本上**时）
- 用户抱怨「你改的比我原来的还差」「你跑哪去了」→ 立刻回读本 skill 的铁律 0-1

**不适用**：用户只给数据不给脚本（走常规出图 skill）；纯知识问答（查文档即可）。

---

## 铁律 0：先谈方向，再动手（最高优先级）

用户给脚本 + **风格/标准要求** = **方向选择**，不是「纯代码修改」。动手前至少确认三件事：

1. 保留原画布尺寸 / 面板排布 / 点径吗？（用户往往就喜欢现在的版式）
2. 「优化」= 加投稿规范（矢量导出、字号合规、白底、Source Data），还是重排版式？
3. 只修报错，还是连带做规范增量？

**实测事故**：把用户 26×8 in 的 DimPlot 改成 180×108 mm + `pt.size` 0.25 + `facet_wrap` 后：

> 「我让你按照 nature 风格优化，怎么比原来的代码还要简陋了？」
> 「这才是我的原代码，你跑哪去了？」

**判据：要求里只要带「风格 / 级别 / 期刊」字样，就先问一句再改**，不要自己判成 code-edit 直接跳过去编辑。

---

## 铁律 1：最小改动，逐条列出

| | 允许 | 禁止 |
|---|---|---|
| 参数 | 修 bug、显式化关键参数（如补 `reduction=`） | 改画布尺寸、面板排布（`split.by`→`facet_wrap`）、点径、配色赋值 |
| 结构 | 加导出/源数据块（**新增，不删原有**） | 重写代码结构、删用户写法、按自己风格重构 |
| 输出 | 逐条列「改了 / 为什么 / 风险」 | 只丢一整版新代码让用户自己找差异 |

**刻意不动的地方也要明说**。例：`family="sans"` 在 Windows 下已映射 Arial（符合 Nature 字体要求）不必改；用户脚本里 `cols=` 与 `scale_color_manual()` 重复设色虽会 warning 也不越界删。说明「我没动它，因为…」比默默删掉更有价值。

---

## 铁律 2：Nature 级 ≠ 把图缩小

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
| 组序可控 | 显式 factor levels，否则字母序替你排序（读者把组序读错） |
| 灰度/色盲可辨 | 出灰度预览确认类别仍可区分 |

---

## 铁律 3：自己引入的 bug 直接修，不要先「核验报错出处」

实测：我给用户加的 `TYPE_LAB[as.character(data$type)]` 导致 `No cell overlap`；用户说「改一下报错」，我却先花两轮做网络查证：

> 「不是让你改一下报错吗？为啥一直卡着啊？你他妈要干什么？」

规则：
- 报错出现在**我刚给出的代码**里 → 优先假设是自己写的，直接定位那一行
- 用户说「修一下这个报错」= 立刻给修正后的完整代码，**不做前置查证、不跑流程**
- 依据/来源补在后面，但不能挡住修复

---

## R / ggplot2 / Seurat 高频坑（速查）

### 1. facet 标题不居中 → 必须写 `strip.text.x.top`

ggplot2 **4.0.3** 官方 `theme()` 文档原文：

> Facet strips have dedicated position-dependent theme elements (`strip.text.x.top`, `strip.text.x.bottom`, `strip.text.y.left`, `strip.text.y.right`) that inherit from `strip.text.x` and `strip.text.y`, respectively. **As a consequence, some theme stylings need to be applied to the position-dependent elements rather than to the parent elements.**

只写 `strip.text` / `strip.text.x` 时，**位置类样式（`hjust` / `margin`）不保证生效**。三行都写（跨版本兼容）：

```r
theme(
  strip.text       = element_text(face = "bold", size = 9, hjust = 0.5, margin = margin(b = 2)),
  strip.text.x     = element_text(face = "bold", size = 9, hjust = 0.5, margin = margin(b = 2)),
  strip.text.x.top = element_text(face = "bold", size = 9, hjust = 0.5, margin = margin(b = 2)),  # ← 真正生效的一层
  strip.background = element_blank(),
  strip.placement  = "outside"
)
```

排查第一步：`cat(as.character(packageVersion("ggplot2")))`——strip 继承行为在 3.5 / 4.x 之间有变化。
相关：`legend.title`（继承自 `title`，对齐用 `hjust`）、`legend.title.position`（**3.5+ 才有**，低版本可能报未知元素）。

### 2. Seurat `No cell overlap between new meta data and Seurat object` → 向量必须 `unname()`

`vec[as.character(x)]` 返回**带 names 的向量**，Seurat 把 names 当 barcode 匹配 → 零重叠。

```r
# ✓
data$type_lab <- factor(unname(TYPE_LAB[as.character(data$type)]), levels = unname(TYPE_LAB))
```

**通杀**：任何赋给 `obj$col <-` / `AddMetaData()` 的向量先 `unname()`。带 names 的来源：查表索引、`setNames()`、`table()`、`tapply()`。

### 3. 高清点图：`pt.size` / `raster` / `raster.dpi`

- `pt.size` 是**最终尺寸下**的点径，与画布英寸联动（铁律 2）
- `raster=TRUE` + `raster.dpi=c(300,300)` —— **必须长度 2 的向量**（X/Y 各一）
- 图例单独 `get_legend()` 必须复用**同一 reduction + 同一 pt.size**：原脚本常漏 `reduction=`（依赖 `DefaultDimReduction` 兜底，改过对象后可能取错降维），漏 `pt.size` 则默认 1 → **图例点比图上点小**

### 4. 投稿导出三件套 + Source Data（R）

```r
W_IN <- 26; H_IN <- 8        # 与预览一致，所见即所得
base_file <- file.path(out_dir, "UMAP_subcluster_by_type")

svglite::svglite(paste0(base_file, ".svg"), width = W_IN, height = H_IN)
print(final_plot); dev.off()

grDevices::cairo_pdf(paste0(base_file, ".pdf"), width = W_IN, height = H_IN, family = "sans")
print(final_plot); dev.off()

ragg::agg_tiff(paste0(base_file, ".tiff"), width = W_IN, height = H_IN, units = "in", res = 600)
print(final_plot); dev.off()

write.csv(as.data.frame.matrix(table(data$subcluster, data$type)),
          file.path(out_dir, "SourceData_subcluster_by_type.csv"))
```

- R 在 Windows 下 `family="sans"` 已映射 **Arial** → 符合 Nature 字体要求，**不必改**
- 透明底适合拼 PPT，投稿需白底 → **用变量控制、默认保持用户原值**：`BG <- "transparent"`（投稿改 `"white"`）

### 5. 预览尺寸 = 导出尺寸

`options(repr.plot.width = 26, repr.plot.height = 8, repr.plot.res = 100)`
字号按真实尺寸定，**预览与导出必须一致**，否则看到的字号/点径都是假的。

---

## 交付模板

回复里给出：

1. **完整可运行代码**（一个代码块，直接复制能跑，不要只给 diff 片段）
2. **改动说明表**：

| # | 改动 | 原因 / 影响 |
|---|---|---|
| 1 | `strip.text.x.top = element_text(hjust=0.5, …)` | 标题不居中的真正原因（position-dependent 元素）；风险：无 |
| 2 | 图例补 `reduction=` + `pt.size=` | 不依赖默认降维；图例点与图上点一致；风险：无 |
| 3 | 矢量导出 + Source Data（**新增，没删任何东西**） | Nature 硬性要求；原画布尺寸原样沿用；风险：需 svglite/ragg |
| 4 | 常量抽成变量（默认仍是用户原值） | 保持原行为；投稿改一个词；风险：无 |

3. **刻意没动的地方**（逐条说明理由）
4. 落盘路径（`results/<sid>/scripts/`）+ 一句「要不要我实跑」

---

## 参考来源

- `references/user_script_optimization.md` —— 完整事故复盘 + R/ggplot2/Seurat 详细代码 + 交付模板
- ggplot2 官方 `theme()` 参考页（ggplot2 4.0.3）— https://ggplot2.tidyverse.org/reference/theme.html