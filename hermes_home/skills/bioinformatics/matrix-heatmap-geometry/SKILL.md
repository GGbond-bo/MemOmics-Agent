---
name: matrix-heatmap-geometry
description: >-
  R 矩阵热图的几何与版式控制（base graphics / pheatmap / ComplexHeatmap / ggplot2）：按目标纸宽反解色块尺寸、
  边距与画布联动、行列标签对齐、色标与分组色条的绘制顺序、可编辑矢量导出、以及「哪些行/哪根轴该上图」的口径决策。
  触发：热图版式 / 边距 / 标签对齐 / 期刊尺寸 / CNS 热图 / 热图导出 SVG / 色块被裁 / 分组色条没出来 /
  多面板不一致 / 脚注压标签 / 注记位置跑了 / colorbar 崩 / 色标 NaN。
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

## 四条几何铁律（都踩过 ≥2 次）

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

### 4. 色标范围必须**贴合数据实际范围**，否则一侧颜色整体塌陷

```python
# ❌ 反例：固定对称 ±0.5，而数据只有 −0.152 ~ +0.451
norm = TwoSlopeNorm(vmin=-0.5, vcenter=0.0, vmax=0.5)
#   → 负值端最大只用到色标 30% → 该侧色块接近白色，"下降"看不见
#   → 红蓝不对称：正值 90% 饱和红，负值 30% 惨白蓝
# ✅ 正解：按 max|值| 定对称边界（两侧量纲不同时也可按需非对称）
M0 = float(np.max(np.abs(M)))
norm = TwoSlopeNorm(vmin=-M0, vcenter=0.0, vmax=M0)
```

**出图前一行判据**：`util = max|值| / 色标边界`。任一侧 < 0.5 → 该侧塌陷，必须收紧。

`TwoSlopeNorm` 的 `vcenter` 把 0 恒映射到色带中点（白），**收紧边界不改变 0 的颜色**，只放大两侧对比
—— 所以收紧是安全、无副作用的。⚠️ 但收紧后**刻度要同步改**（±0.5 的五档改成贴合边界的三到五档），
否则刻度落在数据范围外，看起来像空轴。

> 这条为什么排进铁律：症状是"用户说图不合格 / 看不出变化"，而几何审计全过（0 越界、0 重叠、格数齐全）。
> 排掉几何后剩下的头号嫌疑就是**色标与数据不匹配** —— 它让全图主结论在视觉上塌掉一半。

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

## 核验三件套（必做，都很便宜）

1. **SVG 色值计数**（svglite SVG 可 grep hex）：每个分组色的命中数应 = 该组**成员数**（组名用同色文字时 +1）。
   实测：Metabolism 5 = 4 成员 + 1 组名文字；类型注释条 4/4/2 = 各型行数。数目对不上就是没画出来或画错组。
   ⚠️ **cairo 生成的 SVG 做同一件事会全假阴性**（颜色写成 `rgb(%)`、文字转 glyph）——不要据此断言"色块没渲染"。
2. **OCR / 图像核验**（`vision_describe` 本地管道）：查标签**数量**、**行距是否恒定**（= 是否按行中心对齐）、**是否被裁**。
   实测判据：行距 91 px 恒定（色块 0.306 in × 300 dpi = 92 px）→ 对齐正确；标签全在画布内 → 无裁切。
   逐张单发容易触发循环检测 → **同一轮并行发多张**，或把机器判据收敛成一个脚本（见 `scripts/verify_heatmap_export.R`）。
3. **几何审计（matplotlib `get_window_extent` 两两比对）的重叠阈值必须 > 2 px，且只报 top-N。**
   本次实测：阈值写成 `ix > 0.5 and iy > 0.5` → 报出 **190 个"重叠"，全部是 1×1 px**，
   真重叠 0 个 —— 相邻文字 bounding box **边界刚好相接**被误判，噪声把真信号淹了。
   改用 `ix > 2 and iy > 2`（或字号的 ~10%），并且只输出最大的几对。
   报告一行写清阈值与三个数字，便于下一轮/用户直接判读：
   `canvas px = 510x550 | text objects = 93 | OUT-OF-CANVAS = 0 | OVERLAPPING(>2px) = 0`

**但阈值只是次要问题 —— 对象级审计本身会给出假的 PASS。**（2026-10-01 实测，代价是被用户连怼两轮）
- `plt.close(fig)` 之后取 `get_window_extent()` → 刻度标签退化成 **1×1 px** → 一次审计同时报出
  「190 个重叠（全是 1×1 px，= 20 个文字两两组合 C(20,2)）」**和**「标签↔色块 max = 1227.5 px」两个假数字。
- `transData.transform()`（100 dpi canvas）与 `get_window_extent()`（导出 300 dpi）**dpi 不一致时数值不可比**。
- 后果（本次真实事故）：对象级自检修完报 PASS，而图里**每个行标签都偏了半个行高 60.5 px / 5.08 mm**，
  用户一眼看出「字体跟自己的色块不对齐」，我却拿假数字回了「我量过，偏差 0.5 px」。**报告口径错了比不报告更糟。**

> **铁律：任何「标签与色块是否对齐」的判定，必须对最终导出的 PNG 做像素测量。**
> 对象级数字只能当线索，不能当结论。汇报必须给**逐项 Δ 数值 + 容差**，不能只说「已对齐」。
> 完整检测配方与自校准修法（含 band/质心/行高口径与全部实测数字）→
> `references/label-row-alignment-pixel-audit.md`

**第二层假 PASS：把自检从对象级换成像素级之后，它依然会骗你。**（2026-10-01 二次实测，代价是用户第二次说同一句话）
自校准脚本（量 PNG 色带中心 → `transData.inverted()` → `set_y()`）跑完后，内置自检报
「亚群名 ↔ 行色块 max = 0.5 / 3.3 px，容差 6 px → **PASS**」，用户照旧说「字体跟自己的色块不对齐」。
换一条**独立读数**（对同一张成品 PNG 跑 `vision_describe` OCR，取左侧亚群名与**格内数值**的 y）后才看见真信号：
**标签 pitch 与行高都是 120 px，但整列标签比它那一行的格内数值恒偏 ≈59 px = 半个行高。**

- 根因不是数值精度，是**同源**：自检与绘图共用同一套「行中心在哪」的假设（band 起点 + (k+0.5)×pitch）。
  假设错了，两边一起错，Δ 自然恒等于 0。**共源的自检不是证据，是同义反复。**
- 判据升级：当**用户说错位、自检说对齐**时，你手里其实还没有测量结果 —— 先跑独立读数再回话。
  不要在 `ask_user` 的提问文本里先写「我量过，没量出错位」（本次这么写，用户只能重复同一句抱怨）。
- 独立读数配方 + 本次全部实测数字 + 「同一仪器差分比较」口径 →
  `references/independent-verification-of-figure-geometry.md`

## 多面板（panel set）一致性核验 —— 同一脚本的多张图必须量到同一组数字

同一脚本出的多面板图（面板**行数不同**、但色块物理尺寸相同）**必须逐面板量同一组几何数字并要求相等**。
否则"每张单看都对"，并排一看版式乱。（2026-10-03 实测：一张 11 行 / 一张 4 行 / 一张 2 行，
脚注相对定位导致两张的脚注跑到轴名上方、一张在下方。）

最便宜的一次测量 —— **导出 PNG 底部的墨迹带**（一条命令：`scripts/verify_panel_geometry_bands.py`）：

| 量什么 | 取法 | 合格判据（本次实测三面板） |
|--------|------|--------------------------|
| **旋转 X 标签带高度** | 底部区域的连续非白行段（倒数第二条带） | 183 / 183 / 184 px —— **必须相同**（同一转角度 ⇒ 同一带高） |
| **脚注带高度** | 最后一条带 | 32 / 32 / 32 px —— 必须相同（一行 7.5 pt ≈ 31 px @300 dpi） |
| **标签底 → 脚注顶间隙** | 两带之间的空行数 | 77 / 77 / 77 px —— 必须相同。**间隙 0（两带合并成一条）＝脚注压在标签上**，是相对定位踩坑的指纹 |
| **底边是否被裁** | 最后 1 行的墨迹量 | 0 —— 必须为 0 |

- **判据写进汇报**（给数字和容差，不说"已对齐"）；脚本会把四列数字与 PASS/FAIL 直接打印出来。
- 修法与根因见坑表第一行（改 `offset points` 绝对偏移）；改完**必须重跑这张核验**，
  而不是重看一遍图 —— 偏移量只改了几个 pt，肉眼分辨不出，数字能。
- ⚠️ 反例警戒：**不要**用"图看起来差不多"作为通过依据。相对定位的偏移量随轴高连续缩放，
  2 行面板与 11 行面板的差可以是 200+ px，而每张图单看都"没问题"。"把活干漂亮"）

1. **多选确认表单里"顺手勾选"的项 ≠ 完整任务授权**。表单返回多个勾选项时，**用户当下正在说的主题才是主线程**；
   一个被顺手勾上的图不要扩成「补丁 → 重跑 → 像素审计 → rail_review → 辩论 → 量化」的长链。
   2026-10-01 真实事故：用户在同一张 `ask_user` 表单里勾了「47 热图：亚群名 vs 左侧色块」**和**「43 桑基图：标签 vs 节点色块」，
   主线程是 MEF2C；我把桑基图当成主任务连做了十几轮（含像素审计、L1 辩论、带宽量化），被用户直接打断：
   「**关桑基图什么事情？不是要做 MEF2C 和 MEF2C-AS1 吗？**」
   → 勾选项与主线程无关时，先把主线程交付掉；要动第二项，先一句话确认它是不是也在这一轮要做的。
2. **承诺了"只改你点的那项，其余不动"就真的不要顺手改**：不加图注句/声明、不改字体/配色/文案。
   即使辩论裁决要求"图注必须声明该折中"也一样 —— **先 `ask_user`，再动**。
3. **自己量不出 ≠ 用户看错**（见上节三层假 PASS）。禁止在 `ask_user` 的提问文本里先写"我量过，没量出错位"——
   那会让用户只能重复同一句抱怨。改成给"我量了哪几项 / 数值 / 容差"，再请他指认。
4. **改完把产出路径给全**：绝对路径 + WebUI「分析结果 → 🖼️ 图片」面板 + 直链
   `/api/results/<sid>/figure?path=<相对路径>`。别只在正文写 markdown 图片语法当交付手段。
5. **引用路径前 `search_files` 核实真名**：本次把 `47_..._10subclusters.png` 写成不带后缀的名字 → 用户"看不到"。

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
| **多面板图的注记/脚注在各面板间上下顺序颠倒**（同一脚本、同一行代码，只是面板行数不同） | 注记用 `transAxes` / `axes fraction` **相对**定位（`text(0, -0.34, transform=ax.transAxes)`）⇒ 偏移量随**轴高**缩放：11 行面板偏 −337 px、4 行面板只偏 −122 px，于是落到旋转刻度标签的不同侧（实测三图里两张是「标签→脚注→轴名」、一张是「标签→轴名→脚注」） | 改**绝对偏移**：`ax.annotate(..., xy=(0.5, 0), xycoords="axes fraction", xytext=(0, -70), textcoords="offset points")` —— `offset points` 与轴高无关 ⇒ 各面板版式自动一致；同步加大 `fig_h` 预留，多余空白由 `bbox_inches="tight"` 裁掉。判定靠量不靠看 → 见「多面板一致性核验」节 |
| colorbar 创建 / `tight_layout()` 时抛 `ValueError: cannot convert float NaN to integer` | 统一色标上界对**含 NaN（缺格）的矩阵**用了 `.max()` —— NaN 传播 ⇒ `M0 = nan` ⇒ colorbar 刻度全是 NaN ⇒ `format_ticks` 里 `log10(loc_range)` 得 NaN | 一律 `np.nanmax(np.abs(M))`（多矩阵：`max(np.nanmax(np.abs(m)) for m in mats)`）。**缺格矩阵必踩这条**，且报错发生在 `tight_layout` 里、看着像布局问题 |
| 分组色条/行注释条整条消失 | 色标 `par(fig)+plot.window` 重置坐标系，其后数据坐标 `rect` 落在画布外 | 铁律 2：同坐标系画色标 |
| 行标签整体偏半格 | `at = N - 1 - i`（单元格底边） | `at = N - seq_len(N) + 0.5`（行中心） |
| 左侧大片死白 | `axis(line=1.30)` 把标签推离 0.67 in | `line = 0.40` + 同步收紧 `mai` 左边距 |
| 改边距后热图本体变形/被裁 | 画布宽没跟着边距变 | `Δ画布宽 = Δ左右边距`；或按纸宽反解色块 |
| SVG 里 grep 不到分组色 | cairo 颜色写成 `rgb(%)`、文字转 glyph | 改用 svglite 生成 SVG；或改看栅格层像素计数 |
| pheatmap 几何不可控 | `cellwidth/cellheight` 单位是**磅 pt**；不传则矩阵宽随画布 npc 缩放 | 显式传 cellwidth/cellheight，并在 `pdf(NULL)` 里量尺反推画布 |
| `par(xaxs/yaxs)` 默认 "r" | 默认外扩 4% → 色块被压缩约 7% | 显式 `par(xaxs="i", yaxs="i")` |
| 色表取整整体偏一档 | 索引写成 `floor(b*256)` | `PAL[floor(b*256)+1]`（255 档 → 索引 256） |
| 行标签整体偏**半个行高**，名字落在两行之间的格线上 | 假定行中心在 data y = 0..9；实际渲染在 **0.517…9.517**（恒差 0.5 行 = 60.5 px = 5.08 mm） | 别去"推" ylim —— 对导出 PNG 量出每行色带中心 → `transData.inverted()` 反算 → `set_y()` 直接钉上去（自校准） |
| 自检报「标签已对齐」而用户看图仍说错位 | 审计量的是 matplotlib 对象：`plt.close` 后 bbox 退化 1×1 px、canvas(100 dpi) 与导出(300 dpi) 坐标系混用 → 假数字 | 改为**对导出 PNG 做像素测量**；汇报必须给逐项 Δ + 容差，禁止只说「已对齐」 |
| **换成像素级自检后仍报 PASS，用户仍说错位** | 自检与绘图**同源**：共用「行中心 = band 起点 + (k+0.5)×行高」假设 → 假设错则两边同错，Δ 恒等于 0 | 跑**独立读数**：对成品 PNG 做 `vision_describe` OCR，比较「亚群名 y」与**该行格内数值 y**（数值不经标签布局路径，是图内基准尺）；本次实测 ≈59 px = 半行高 |
| 逐行统计标签时数目对不上（10 个名数成 12/13） | 按 y 连通分组：名称里的括号/下延字符留 1 px 空隙被拆成两组 | 改为**逐行开窗取墨迹质心**（±0.4 行高窗口），不依赖分组 |
| **整列色块发白、该侧看不出变化** | 色标边界远大于数据范围（±0.5 vs ±0.15 → 该侧只用 30%） | 铁律 4：按 `max\|值\|` 收紧边界 + 同步改刻度 |
| 审计报大量"重叠"但肉眼无异常 | 重叠阈值设成 `> 0.5 px`，相邻 bbox 边界相接被误判（190 个 1×1 px 假阳性） | 阈值提到 `> 2 px`，只输出 top-N |
| 用户说"图不合格"但几何审计全过 | 只查了排版，没查**色标/数据匹配度、格宽高比、字号与画布比** | 见 `references/effect-matrix-heatmap-pitfalls.md` §四「先量后猜」顺序 |
| 用户打断"这跟刚才那件事什么关系？" | 把 `ask_user` 多选表单里顺手勾选的第二项当成了任务授权，扩成长链（补丁→重跑→审计→辩论→量化） | 主线程优先；勾选项与主线程无关时先交付主线程，要动第二项先确认（见上节边界纪律 1） |
| 用户说"看不到图" | 引用了不存在的文件名（漏后缀）；或只在正文写 markdown 图片语法当交付手段 | 报路径前 `search_files` 核实真名与大小；给绝对路径 + WebUI「结果→🖼️ 图片」面板 + 直链 |

## 配套文件

- 桑基图/冲积图（非矩阵型）的节点布局、最小节点高度与带宽保真度 → skill **`sankey-alluvial-layout`**
- `references/base-graphics-cns-heatmap.md` — 零第三方包手绘 CNS 热图的完整配方与本次实测数字（含代码骨架、双路核验命令、口径决策实证）
- `references/effect-matrix-heatmap-pitfalls.md` — **效应值矩阵热图（logFC × 亚群）的诊断与配方**：色标失配的量化判据与修法（铁律 4 实证）、每格标数值/`†`/最小 FDR 虚线框的画法、脚注五要素、用户说"不合格"时的「先量后猜」顺序、SVG 源码级定位脚本
- `scripts/verify_heatmap_export.R` — 出图后一键核验：PNG 尺寸/DPI（解析 IHDR + pHYs）、四格式文件大小、svglite SVG 的分组色计数、并按"命中数=成员数"给判定
- `scripts/verify_panel_geometry_bands.py` — **多面板一致性核验**（纯 Pillow+numpy，可直接跑）：量导出 PNG 底部的墨迹带 —— 末带高（脚注）/ 次末带高（旋转标签）/ 两带间隙 / 底边墨迹，跨面板要求同一组数字，自动打印 PASS/FAIL。判据数字见「多面板一致性核验」节
- `references/label-row-alignment-pixel-audit.md` — **「标签 ↔ 色块行对齐」的像素级审计与自校准**：对象级自检为何会报假 PASS（bbox 退化 1×1 px + dpi 混用）、非白色带/墨迹质心/行高口径的检测配方及两条反直觉选择（别用白格线、别按 y 连通分组）、`transData.inverted()` 自校准代码、以及「半个行高 60.5 px」的完整实测数字
- `references/independent-verification-of-figure-geometry.md` — **图几何声明的独立验证（自检为何自证清白）**：三层假 PASS 的演进、用 `vision_describe` OCR 对成品 PNG 做仲裁的配方、「同一仪器差分比较」口径（只做组间差分，不与计算出来的布局数字比绝对 px）、半行高恒定偏置的签名、47 图全部实测数字（120 px pitch / ≈59 px 偏置）、汇报与 `ask_user` 提问纪律

## Proven Scripts

> Auto-generated from actual analysis runs. Each row records a successful execution.

| 物种 | 组织 | 方向 | 日期 | 脚本 | auto | user | ✔ |
|------|------|------|------|------|------|------|----|
| human | skeletal_muscle | aging | 2026-09-25 | fig_A3_CNS_v5.R | - | - |  |
| human | skeletal_muscle | aging | 2026-09-25 | get_official_aucell_doc.sh | - | - |  |
| human | skeletal_muscle | aging | 2026-09-25 | parse_aucell_vignette.py | - | - |  |
| human | skeletal_muscle | aging | 2026-10-04 | hsp_direction_by_subcluster.py | - | - |  |
