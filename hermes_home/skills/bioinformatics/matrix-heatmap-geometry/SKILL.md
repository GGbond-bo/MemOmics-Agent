---
name: matrix-heatmap-geometry
description: >-
  R 矩阵热图的几何与版式控制（base graphics / pheatmap / ComplexHeatmap / ggplot2）：按目标纸宽反解色块尺寸、
  边距与画布联动、行列标签对齐、色标与分组色条的绘制顺序、可编辑矢量导出、以及「哪些行/哪根轴该上图」的口径决策。
  触发：热图版式 / 边距 / 标签对齐 / 期刊尺寸 / CNS 热图 / 热图导出 SVG / 色块被裁 / 分组色条没出来。
when_to_use: >-
  出或改**矩阵型热图**（基因集×亚群、基因×样本、GO 词条×亚群、效应值×亚群）并关心版式、期刊尺寸、矢量导出或口径取舍时。
  纯 UMAP/Violin/DotPlot 不需要；调色板选择不需要。
version: 1.0.0
author: MemOmics
license: MIT
platforms: [windows, linux, macos]
metadata:
  hermes:
    tags: [visualization, heatmap, R, base-graphics, publication, geometry, pheatmap]
    difficulty: intermediate
    language: R
    category: bioinformatics
---

# 矩阵热图几何与版式控制

矩阵热图的"难看"几乎从不是配色问题，而是**几何问题**：色块尺寸、边距、画布、标签锚点、绘制顺序。
本 skill 把反复踩过的几何坑固化成铁律 + 核验流程。

## 何时用

- 出/改矩阵型热图：基因集×亚群、基因×样本、通路×亚群、效应值×亚群
- 用户说：热图版式 / 边距 / 标签没对齐 / 期刊尺寸 / CNS 热图 / 出 SVG / 色块没出来 / 分组色条不见了
- 无第三方包（ComplexHeatmap 不可用）需要手绘出版级热图时 → 走 base graphics 路线

## 三条几何铁律（都踩过 ≥2 次）

### 1. 按目标纸宽**反解**色块边长，不要先定色块

```r
CELL <- (TARGET_MM / 25.4 - mai_left - mai_right) / XMAX   # 未知 → 反解
W    <- XMAX * CELL + mai_left + mai_right
H    <- NTOP * CELL + mai_bottom + mai_top
```

- Nature 双栏 = **183 mm**；单栏 89 mm；Cell 同理。总宽必须精确落在栏宽上，审稿人/排版会量。
- 只改边距时：`Δ画布宽 = Δ左右边距`，否则画布不变而绘图区被挤压 → **热图本体变形（用户会当场发现）**。
- 想要"绝对可控"还可锁 `cellwidth`（pheatmap 单位是**磅 pt 不是 cm**），并在 `pdf(NULL)` 里量尺反推画布。

### 2. 全图只用**一个坐标系**——绝不 `par(fig=..., new=TRUE)` 重置

```r
# ❌ 反例：色标内部重置坐标系 → 其后所有 rect 落在画布外被裁
par(fig = c(0.93, 0.95, 0.22, 0.80), new = TRUE); plot.new(); plot.window(c(0,1), c(-2,2))
# ✅ 正解：色标画在同一数据坐标系内（x 超出 XMAX，xpd = NA）
x0 <- XMAX + 0.42; x1 <- XMAX + 0.66; rect(x0, y0, x1, y1, col = ...)
```

这条是"**分组色条/行注释条整条消失**"的唯一根因（症状：成图只有热图本体，`.R` 里明明写了 `rect()`）。
顺序补救法（把 metadata 画在 colorbar 之前）也能用，但**同坐标系是结构性免疫**，优先选它。
👉 推论：任何"主图 + 内嵌小图"的画法都要警惕坐标系重置；能放进同一坐标系就别开 `par(fig)`。

### 3. 标签锚定**行/列中心**，`axis(line=)` 必须实测标定

```r
axis(2, at = NROW - seq_len(NROW) + 0.5, labels = labels, las = 1, tick = FALSE, line = 0.40)
#        ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^ 行中心
# ❌ NROW - 1 - i 是单元格【底边】 → 整列标签偏下半格
```

`axis(line=)` 实测（`ps=9`，cairo 设备）：

| line | 标签右缘距绘图区 | 结果 |
|------|-----------------|------|
| 1.30 | **0.67 in** | 左侧一大片死白（图看着"散"） |
| 0.40 | ≈ 0.21 in | 恰好贴住左侧注释条（推荐） |

改完 `line` 要**同步收紧 `mai` 左边距**（1.30 → 1.00 in），省下的宽度会让色块变大（0.285 → 0.306 in）。

## CNS 版式清单（默认照做）

| 元素 | 做法 |
|------|------|
| 单元格分隔 | `rect(..., border = "white", lwd = 0.45)` —— 期刊热图惯例，顺带消掉抗锯齿缝 |
| 顶部组色条 | 每个成员一格 `rect(colx[g], NSUB+0.10, colx[g]+1, NSUB+0.34, col = axis_color)`；组名 `text(mean(span), NSUB+0.46, adj=c(0.5,0), font=2, col=axis_color)` |
| 轴间间隔 | 组间留 `GAPX ≈ 0.22` 数据单位（列连续、组间断开） |
| 行注释条 | 左侧负数据单位处 `rect(-0.34, ..., -0.16, ...)` + 类型名 `srt = 90`；颜色用中性族（如 `#3F3F3F / #B0B0B0 / #C98A3C`），避免与组色族撞色 |
| 色标 | 竖放右缘、同坐标系绘制、刻度 ±2、`srt=90` 的 `row z-score` 标签 |
| 字号 | `ps = 9` 为基准，`cex = X / 9`：标签 5.5–6.3 pt、轴名 6.3 pt 粗体、标题 7.5 pt 粗体 |
| 标题 | 期刊正文通常无需标题（图注承担），保留时压到 7.5 pt 并留 `TITLE <- ""` 开关 |
| 数值标度 | 对称两斜率：`TwoSlopeNorm(-2, 0, 2)` 等价实现 + `RdBu_r` 分档 LUT（**同一项目内与其他图逐字节同色**） |

## 导出与字体

```r
png  = function(f) png(f, width=W, height=H, units="in", res=300, bg="white", type="cairo", family=FAM)
pdf  = function(f) cairo_pdf(f, width=W, height=H, bg="white", family=FAM)
svg  = function(f) if (requireNamespace("svglite", quietly=TRUE)) svglite::svglite(f, W, H, bg="white")
                   else svg(f, width=W, height=H, bg="white", family=FAM)
tiff = function(f) tiff(f, width=W, height=H, units="in", res=300, bg="white", compression="lzw", type="cairo", family=FAM)
```

- **用户本机偏好：所有出图默认 300 dpi + 必附 SVG**（别用 150 dpi）。
- **SVG 必须走 svglite**：cairo 的 `svg()` 会把文字转成 glyph 路径（后期不可编辑，且 hex 值 grep 不到颜色）。
- 字体探测别硬编码：`fam_ok <- function(f) tryCatch({pdf(NULL); par(family=f); dev.off(); TRUE}, error=function(e) FALSE, warning=function(w) FALSE)`，失败回退 `"sans"`。

## 核验两件套（必做，都很便宜）

1. **SVG 色值计数**（svglite SVG 可 grep hex）：每个分组色的命中数应 = 该组**成员数**（组名用同色文字时 +1）。
   实测：Metabolism 5 = 4 成员 + 1 组名文字；类型注释条 4/4/2 = 各型行数。数目对不上就是没画出来或画错组。
   ⚠️ **cairo 生成的 SVG 做同一件事会全假阴性**（颜色写成 `rgb(%)`、文字转 glyph）——不要据此断言"色块没渲染"。
2. **OCR / 图像核验**（`vision_describe` 本地管道）：查标签**数量**、**行距是否恒定**（= 是否按行中心对齐）、**是否被裁**。
   实测判据：行距 91 px 恒定（色块 0.306 in × 300 dpi = 92 px）→ 对齐正确；标签全在画布内 → 无裁切。
   逐张单发容易触发循环检测 → **同一轮并行发多张**，或把机器判据收敛成一个脚本（见 `scripts/verify_heatmap_export.R`）。

## 口径决策：哪些行 / 哪根轴该上图

矩阵热图常被要求"删掉某某打分"，别只凭生物学印象，用两个数字说话：

1. **别用"与 QC 复杂度相关高"判定技术伪影**。AUCell 类打分随检出基因数上升是**方法学通用性质**（实测大基因集 rho ≈ 0.4–0.57，小基因集 ≈ 0.14–0.23）。必须拿**合法程序做对照**：rho 不高于对照就不构成伪影证据（实测某"疑似伪影"程序 0.548 < 对照 OxPhos 0.555，percent.mt 关联 0.185 < 0.392 → 伪影说法被推翻）。
2. **用跨亚群（或跨样本）动态范围决定能否上图**。行内 z-score 能吸收全局复杂度效应，但动态范围极小时 z 化会把噪声放大成图案：实测某程序 0.122–0.145（相对幅度 **15%**）vs OxPhos 0.149–0.241（**55%**）→ 前者不宜单列成轴。
3. 结论写进图注：**行内 z-score 只反映行内相对差异，不代表绝对水平**（辩论裁决强制项）。

## 版本化交付（用户点名归档版本时）

用户可能点名一个**归档**文件名（如 `..._pre_v3.png`）。此时：

1. `search_files` 定位 + `vision_describe` **读它的分组标签/程序数**，确认口径（本例：归档 = 18 程序/6 组含灰轴，现行 = 17 程序/5 轴）。
2. **不要猜**。把 `draw_one(axes, progs, base)` 写成**参数化函数**，同一脚本并行出两套（主图 + 归档口径对照），并在汇报里点名哪套建议作主图。
3. 出图前 grep 是否还有旧的未修 bug（标签底边约定、色块调用顺序）——**同一 bug 常散落在多个版本脚本里**。

## 坑表

| 现象 | 根因 | 处置 |
|------|------|------|
| 分组色条/行注释条整条消失 | 色标 `par(fig)+plot.window` 重置坐标系，其后数据坐标 `rect` 落在画布外 | 铁律 2：同坐标系画色标 |
| 行标签整体偏半格 | `at = N - 1 - i`（单元格底边） | `at = N - seq_len(N) + 0.5`（行中心） |
| 左侧大片死白 | `axis(line=1.30)` 把标签推离 0.67 in | `line = 0.40` + 同步收紧 `mai` 左边距 |
| 改边距后热图本体变形/被裁 | 画布宽没跟着边距变 | `Δ画布宽 = Δ左右边距`；或按纸宽反解色块 |
| SVG 里 grep 不到分组色 | cairo 颜色写成 `rgb(%)`、文字转 glyph | 改用 svglite 生成 SVG；或改看栅格层像素计数 |
| pheatmap 几何不可控 | `cellwidth/cellheight` 单位是**磅 pt**；不传则矩阵宽随画布 npc 缩放 | 显式传 cellwidth/cellheight，并在 `pdf(NULL)` 里量尺反推画布 |
| `par(xaxs/yaxs)` 默认 "r" | 默认外扩 4% → 色块被压缩约 7% | 显式 `par(xaxs="i", yaxs="i")` |
| 色表取整整体偏一档 | 索引写成 `floor(b*256)` | `PAL[floor(b*256)+1]`（255 档 → 索引 256） |

## 配套文件

- `references/base-graphics-cns-heatmap.md` — 零第三方包手绘 CNS 热图的完整配方与本次实测数字（含代码骨架、双路核验命令、口径决策实证）
- `scripts/verify_heatmap_export.R` — 出图后一键核验：PNG 尺寸/DPI（解析 IHDR + pHYs）、四格式文件大小、svglite SVG 的分组色计数、并按"命中数=成员数"给判定