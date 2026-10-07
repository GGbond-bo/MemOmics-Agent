# 图形几何自检配方（Figure Geometry Audit）

> 出处：2026-09-22 人骨骼肌特化肌核 UMAP 分面图（11,630 细胞 × 7 亚群 × 6 组，Seurat 5.5.1 + ggplot2 4.0.3）。
> 本文只讲**几何/可读性怎么量**；导出格式与字号合规见 `figure-legibility-audit.md`。

## 0. 为什么要单独做几何自检

出图脚本**不报错**、文件**也真的生成了**，图仍然可能是坏的。已知两类静默失败：

| 症状 | 用户原话 | 几何根因 |
|---|---|---|
| "比原来的代码还要简陋"、点看不见、面板发空 | 抱怨图变差 | 画布缩小 + 点径缩小**叠加** |
| "图被拉变形了"（用户不一定主动说） | — | 无 `coord_fixed`，面板纵横比 ≠ 1 |

两类都可量化，**出图后自检比等用户发现便宜得多**。

## 1. Seurat `DimPlot` 的坐标系（实测结论）

```r
# 核验代码
class(p$coordinates)        # CoordCartesian / Coord / ggproto / gg
str(p$coordinates, max.level = 1)$ratio      # NULL  ← 关键判据
p$theme$aspect.ratio                          # NULL  ← 关键判据
grep("coord_fixed|coord_cartesian", deparse(Seurat::DimPlot), value = TRUE)   # 无命中
grep("coord_fixed|coord_cartesian", deparse(Seurat:::SingleDimPlot), value = TRUE)  # 无命中
```

- **Seurat 5.5.1 的 `DimPlot` 路径不调用 `coord_fixed`** ⇒ 面板纵横比由画布决定，UMAP 会被拉伸。
- ⚠️ **不要用 "类名是 CoordCartesian" 来判断"没有等比例"** —— 新版 ggplot2 把 `coord_fixed()`
  并入 `CoordCartesian` 实现。判据 = **`ratio` 字段是否 NULL** + 源码是否调用。
- **`split.by` 的排布规则（实测）**：6 个水平生成 **1 行 × 6 列**（gtable: `panel-1-1 … panel-6-1` 全部
  ROW=11），**不是** `facet_wrap` 默认的近方形 3×2。⇒ 宽幅画布是匹配的，但面板会被压成竖长条。

### 实测数值（A 版 = 用户原设定 26×8 in）

| 量 | 值 |
|---|---|
| 面板尺寸 | **3.64 in 宽 × 7.2 in 高**（间距 0.3 cm ≈ 11.8 px @100dpi） |
| 面板纵横比 | **1 : 1.98** ⇒ UMAP 纵向拉伸 ≈ **2 倍** |
| 对策 | `+ coord_fixed(ratio = 1)`，画布高度降到 **26×5 in**（B 版） |
| B 版面板 | 3.64 × 3.64 in **方形**；内容纵横比 1.03–1.21（由数据范围决定，正常） |

> 为什么只改高度、不改宽度：面板宽度不变 ⇒ 面板仍是 3.64 in ⇒ `pt.size` 原值继续有效，
> 不必连带调点径。**"只砍高度"是保住用户视觉设定的最小改动路径。**

## 2. gtable 量不出面板尺寸（两个 API 怪癖）

1. **面板是 `null` 单位**：`convertWidth(sum(g$widths[idx]), "cm", TRUE)` 在设备外返回 **0**
   （报错 `Cannot create zero-length unit vector` 往往是子集取空导致的）。
2. **ggplot2 4.0.3 的命名变了**：
   - `names(g$grobs)` 返回 **NULL** ⇒ `grepl("^strip", names(g$grobs))` 取不到任何东西；
     取 grob 要用 `g$grobs[[which(g$layout$name == "strip-t-1-1")]]`。
   - `g$layout$name` 形态是 `panel-1-1` / `strip-t-1-1` / `axis-b-1-1`，
     **`name == "panel"` 取不到任何行**，必须 `grepl("^panel", g$layout$name)`。

**结论：几何量测的权威口径 = 量渲染后的 PNG 像素**，不是 gtable。用
`scripts/measure_figure_geometry.py`。

## 3. 像素量测口径

- 每面板内容 **bbox**（非白像素的 min/max 行/列）、**填充率**（深色像素占比）、**上下留白**。
- **填充率是渲染健康度的单调标尺**：实测 Y_Pre（796 细胞）**3.7%** → OD_Post（3,890 细胞）**19.4%**，
  严格随细胞数递增 ⇒ 点径/raster/配色都正常。**若某面板填充率与细胞数不同向，先查绘图层**。
- ⚠️ 用"等分 6 份"去切面板会**切错边界**（图例占右侧、面板有间距）。
  实测可用边界：条带中心 x = 170/545/922/1296/1669/2043（间距 373–377 px）⇒ 面板宽 ≈364 px、间距 ≈11.8 px。
- 条带居中验证：由条带文字中心推算的面板中心 vs 实际面板中心，实测偏差 **≤10 px / 2600 px = 0.4%** ⇒ 居中成立。

## 4. 条带（strip）标题居中的正确写法

ggplot2 官方 `theme` 文档：facet strip 有 **position-dependent 元素**
（`strip.text.x.top` 等）继承自 `strip.text` / `strip.text.x`，
**部分样式（含位置类）必须写到 position-dependent 元素上**。稳妥写法 = 三层全写：

```r
strip.text       = element_text(face = "bold", size = 9, hjust = 0.5, margin = margin(b = 2)),
strip.text.x     = element_text(face = "bold", size = 9, hjust = 0.5, margin = margin(b = 2)),
strip.text.x.top = element_text(face = "bold", size = 9, hjust = 0.5, margin = margin(b = 2)),
```

验证方式：渲染后量条带文字中心 x 与面板中心 x 的偏差（见 §3）。
⚠️ 若无法 A/B 对照原版，**如实说明"本版实测居中，未证明原版不居中"**，不要声称修好了一个未验证的 bug。

## 5. "空带/空洞"分诊：先查数据，别先改渲染

**流程**：坐标直方图 → 各群坐标范围 → 像素换算对齐（三步定案）。

```r
emb <- Embeddings(obj, "umap"); y <- emb[, 2]
h <- hist(y, breaks = 60, plot = FALSE)
gap <- which(h$counts < 5)          # 稀疏箱
cat(min(h$mids[gap]), "-", max(h$mids[gap]))   # 稀疏区数据范围
tapply(y, obj$subcluster, function(v) sprintf("n=%d median=%.2f range=[%.2f,%.2f]", length(v), median(v), min(v), max(v)))
```

**像素↔数据换算**：`frac = (pixel_y − 面板顶像素) / 面板高像素`；`data_y = max − frac × (max − min)`。

**实测对照（本例）**：

| 量 | 值 |
|---|---|
| `UMAP_2` 全范围 | [-6.77, 9.05] |
| 稀疏区（细胞数<5） | **4.9 – 6.7**（占全范围 11%） |
| 由像素反算的空带 | **4.97 – 6.83** |
| 结论 | 与直方图空段**严丝合缝** ⇒ 真实流形间隙（zone6 中位 8.09 vs zone2/5 中位 3.0/1.9），**非渲染伪影** |

> 把真实结构当 bug 去"修"（裁切/改坐标范围）= 破坏数据。**必须先证伪**。

## 6. 配色灰度可分性

```r
lum <- function(hex) { r <- col2rgb(hex)/255; 0.2126*r[1] + 0.7152*r[2] + 0.0722*r[3] }
L <- sapply(pal, lum); sort(L); min(diff(sort(L)))   # 相邻最小差 < 0.05 ⇒ 灰度不可分
```

实测占位配色：`zone2 = 0.573` vs `zone6 = 0.578` → **ΔL = 0.005**（灰度打印下分不开）。
⚠️ 报告必须写明**测的是哪套配色**——若配色是占位/自造的，结论只对该占位配色成立，
不要拿它替用户宣称"你的配色达标"。

## 7. 几何自检交付话术

给用户的几何结论要带数字，例如：

> 面板实测 3.64 × 7.2 in（1:1.98），`p$coordinates$ratio = NULL`、源码无 `coord_fixed`
> ⇒ UMAP 纵向拉伸约 2 倍；B 版加 `coord_fixed(1)` + 画布 26×5 in ⇒ 面板 3.64 × 3.64 in 方形。
> 填充率 3.7%（796 细胞）→ 19.4%（3,890 细胞）单调 ⇒ 渲染正常。
> y≈175–250 px 空带经直方图核验为真实稀疏区（4.9–6.7），非伪影。

**不要**只说"看起来还行/好看多了"。