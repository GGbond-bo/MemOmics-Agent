---
name: scientific-figure-export
description: >-
  发表级科学图表导出优化（Publication-grade figure export optimization）。
  解决三类高频问题：①"图太糊"（scattermore 默认 512 分辨率、点过密过饱和）
  ②"图文件太大"（600dpi 滥用、透明底、未压缩 PNG）③"期刊尺寸/格式怎么定"
  （Nature 单双栏宽度、300dpi 合规下限、文件 <10MB）。覆盖 R（ggsave/ragg/scattermore）
  与 Python（matplotlib）两个栈的导出决策，重点是 50万级大点云 UMAP/散点图的光栅化导出。
  触发词：图太大 / 图很糊 / 导出尺寸 / dpi / 保存格式 / PNG还是PDF / pngquant /
  scattermore / 透明底 / 白底 / 期刊要求 / 投稿图格式 / UMAP导出 / high-dpi export /
  图里字号多大 / 字号合规 / 这张图几pt / 字体改不了 / AI 改不了字体 / 矢量版 / 论文配图字号 /
  **配色选择（给我一个专业好看的颜色 / Nature 级别配色 / 要两三个 / FeaturePlot 上色 / score 配色）**。
  不做：图型选择（走 cns-visualization/scipilot）、示意图形状设计（走 diagram-design）；
  ⚠️ 配色**速查**在本 skill 的 `references/publication-palettes-featureplot.md`（可直接取用，不必再绕道）。
when_to_use: "用户问导出的图太大/太糊/保存尺寸/dpi/格式选择/透明底白底时触发；**也覆盖已渲染位图的字号合规审计与「为什么改不了字体」**（量已发表论文配图或自己导出图的真实 pt 值、判是否达 5pt 下沿、解释位图无字体对象/无矢量母版）。明确面向投稿发表的导出决策，不负责图型选择。"
version: 1.0.0
author: MemOmics
license: MIT
platforms: [windows, linux, macos]
metadata:
  hermes:
    tags: [visualization, export, dpi, umap, png, raster, 07_可视化]
    difficulty: basic
    language: R+Python
    category: Visualization
prerequisites:
  r_packages: [ggplot2, ragg]
  python_packages: [matplotlib]
---

# 发表级科学图表导出优化

科学图的"导出环节"是独立于"画图环节"的专业决策：同一个 p2 对象，
dpi/背景/压缩方式不同，产出可以从 20MB 到 0.5MB、从模糊到锐利。
本 skill 专注导出三元权衡：**清晰度 × 文件大小 × 期刊合规**。

## 核心决策链

```
用户说"图太大 / 太糊 / 怎么存"
  ├─ 太糊  → ① scattermore 默认 512×512 栅格 → 显式设 pixels
  │          ② point 过密 alpha=1 饱和成黑团 → 调小 size + alpha 0.5-0.7
  │          ③ dpi 低于期刊下限 → 提到 300
  ├─ 太大（文件 MB） → ① 是不是设了 600dpi？降到 300 文件立减 75%
  │                     ② 透明底(RGBA) → 白底(RGB) 省 ~1/3
  │                     ③ 分类色图（10-20 色）→ pngquant 256 色索引 PNG，视觉无损 10MB→1MB
  └─ 不知道定什么 → 查下方"期刊导出契约"表
```

## 铁律（本会话 2026-09 实测验证）

1. **scattermore 默认栅格 512×512，导出必糊。** 用户问"为什么 geom_point 比
   scattermore 清晰"的根因就是它。修复必须显式设 `pixels` 匹配最终输出像素：
   ```r
   geom_scattermore(pixels = c(2200, 2000), interpolate = TRUE)
   ```
   旧版参数名是 `resolution = 3000`，视安装版本。

2. **禁止在坐标图上用 jitter 提"清晰度"。** jitter 会移动真实 UMAP/t-SNE/PCA
   坐标，Nature 编辑做图像完整性核查时会查坐标保真。清晰度靠 size+alpha+分辨率，
   不靠抖动。

3. **300 dpi 是 Nature 位图硬性下限——600 是超配不是标配。** 89mm@600dpi=2102px，
   @300dpi=1051px。600 的文件是 300 的 4 倍，编辑收益为零。用户抱怨"图太大"时
   90% 是先降到 300，再谈压缩。

4. **分类色大点云图 = pngquant 调色板压缩，视觉无损。** UMAP 若只有 10-20 个
   亚群色，256 色索引 PNG 可以把 5-20MB 压到 <1MB：
   `pngquant --quality=70-95 -f in.png -o out.png`（pngquant.org 有 Windows exe）。

5. **ragg 设备参数是 `background=`，不是 ggsave 的 `bg=`。**
   ```r
   ragg::agg_png("out.png", width=120, height=100, units="mm", res=300,
                 background="transparent")   # ← ragg 用 background=
   ggsave(... bg="white")                     # ← ggsave 用 bg=
   ```
   混用会静默失效。透明底只用于组图合成；投稿主图用白底（透明在部分 PDF
   管线会渲染成黑底）。

6. **点云所需像素经验法则：N 个点需要 ≥ N×2 像素。** 50万点 → ~100万像素
   （89×80mm @ 300dpi = 1051×945 ≈ 100万，恰好够）。导出远小于此 → 图会密糊；
   远大于此 → 文件臃肿无清晰度增益。

## 推荐配方（50 万细胞 UMAP，分类色）

```r
ggsave("MF_umap_nolegend.png", p2,
       width = 89, height = 80, units = "mm",
       dpi = 300,            # Nature 下限，不是 600
       bg = "white",         # 白底 = 无 alpha = 文件更小
       limitsize = FALSE)
# 还嫌大 → pngquant --quality=70-95 -f MF_umap_nolegend.png -o MF_umap_final.png
```

## 期刊导出契约

| 项目 | Nature 规范 |
|---|---|
| 单栏宽 | 89 mm (3.5 in) |
| 双栏宽 | 183 mm |
| 位图 dpi | ≥300（硬性下限；300 是标准，600 是超配） |
| 文件大小 | <10 MB（建议 ≤5 MB） |
| 位图格式 | TIFF 或 PNG；**不用 JPEG**（有压缩伪影） |
| 矢量 | PDF/SVG（仅非点云图/小数据点图） |
| **最小字号** | **5 pt（终稿尺寸硬性下限）**；推荐 7 pt 轴标/基因名、8 pt panel 字母 |
| 字体 | Arial / Helvetica（无衬线；规范细节见 academic-figure-skill） |

> 50万级点云千万不要存矢量（PDF/SVG）——文件会到几百 MB，InDesign/AI 直接卡死；
> raster 是正确选择。

## 字号合规审计 &「字体改不了」

导出后**要量，不要假定**——在 7 pt 画好再缩放到 89 mm 栏宽，就不再是 7 pt。
`scripts/measure_figure_fontsize.py` 量已渲染位图里的**真实字号**（同样适用于
用户拿来的已发表论文配图）：

```bash
python scripts/measure_figure_fontsize.py fig.png --from-pdf article.pdf   # 精确
python scripts/measure_figure_fontsize.py fig.png --width-mm 183           # 已知栏宽
python scripts/measure_figure_fontsize.py fig.png --dpi 300                # 已知 dpi
```

- **缩放基准 = 出版社 PDF 里该图的显示宽度**（`fitz` 的 `page.get_image_rects`，
  单位是 pt），**不是**文件头的 dpi 标签，也不是内嵌像素数 → `1 px = 72 / dpi`
- 量到的是**墨迹高度**不是字号：Arial cap height = 0.716 em、x-height = 0.519 em
  → `字号 = 墨迹px × pt/px ÷ 比值`；大写标签与刻度数字用 cap 读法最准
- **两种独立方法交叉验证**（连通域 + 分块行投影），众数差 >1 px ⇒ 抗锯齿占主导
- 实测（Nat Cancer 2026 Fig 2，2163×2698 px 显示 181.8 mm ⇒ 1px = 0.238 pt）：
  主标签 ≈6–7 pt、最小刻度 ≈5 pt，正好压在 Nature 下限上。**报区间 + 误差**
  （±1 px = ±0.33 pt），不要给单一小数
- ⚠️ **位图里没有字体对象**：用户说「放到 AI 里改不了字体」时根因不是文件坏了。
  出版社 `MediaObjects` 只发位图（`.jpg` 变体常 404，无矢量母版可下），且
  14–20 px 墨迹的字本来也无法经济修描。要可编辑 = 拿原始数据重画

完整方法与实测数据见 `references/figure-legibility-audit.md`；源码在手时用
`academic-figure-skill/scripts/check_fontsize.py`（量声明值，精确）。

## 色阶范围：颜色按 min→max 分配 + 图例标真实分数值（2026-09-21 用户诉求）

给连续型 score（AUCell / UCell / module score）上色时，用户常追问"**能不能从 min 到 max 分配颜色，图例也这么显示**"——这是**色阶范围**问题，不是配色问题：先把范围答清，再谈配色。

- **默认范围会漂移**：R 侧 `FeaturePlot` 未给 `min.cutoff` / `max.cutoff` 时，色阶范围取自当前绘制数据 ⇒ 换 `subset()` / 换 slot / 换子集就变。显式锚定 `min.cutoff = min(score)`、`max.cutoff = max(score)`（等价百分位写法 `"q0"` / `"q100"`）。
- 🔴 **绝对不要叠 `+ scale_color_gradientn(limits = rng, ...)` 去\"接管色阶\"（2026-09-21 实测：整图变黑白）**：Seurat v5 的 `FeaturePlot` 返回 **patchwork**，内部把 feature 重缩放到 `1~2`（自带 colour scale `Limits: 1 -- 2`）⇒ 你传 `limits = range(obj$score)`（如 0~0.974）时数据全在界外 → 默认 `oob = censor` 全变 NA → `na.value` 默认 **`grey50`** → **黑白灰图**；`oob = squish` 则全压到端点 → **单色图**。诊断：`class(p)`=patchwork / `range(p[[1]]$data$<feature>)`=`1 2` / `head(ggplot_build(p[[1]])$data[[1]]$colour)`=`grey50`。
- ✅ **图例文字改\"内层 scale\"，不覆盖**：`sc <- p[[1]]$scales$get_scales("colour"); sc$breaks <- sc$limits; sc$labels <- sprintf("%.3f", range(score)); sc$name <- "Score"`（R6 引用语义，原地生效）。**只标最低/最高 = `breaks` 给两个值**；要字面 `"Min"/"Max"` 只改 `sc$labels`。Python 侧对应 `vmin/vmax` + `colorbar.set_ticks`。AUCell 分数尺度小（0.05–0.35）→ 图例用 **3 位小数**；`order = TRUE` 必开（高分细胞画在上层）。**交付前实跑 + PIL 取主色验证（主色为 `#7f7f7f` = 失败）**。
- 🔴 **逐图 min→max 与"跨图可比"只能选一个**：各图各自 `range()` 好看，但同一分数在 A/B 图颜色不同；要做跨亚群/跨组比较必须统一 `limits` / colorbar 范围并在图注声明，两者都要就**拆两套图**，禁止一套图混用。
- 完整配方（方案 A 接管色阶 / 方案 B 仅用 cutoff、图例 guide 微调、发表级导出）→ `celltype-proportion-comparison` 的 `references/featureplot-score-color-scale.md`。

## 图形几何自检：面板纵横比 / `coord_fixed` / `pt.size`↔画布联动（2026-09-22 实测）

出图**不报错** ≠ 几何是对的。用户投诉里高频的两类是"图比原来还简陋/点看不见"和"图被拉变形了"——
**这两类都不是审美问题，是几何问题**，且都能用工具量出来。出图后按下面六步自检，别等用户说"你自己看看"。

### 🔴 1. 先判坐标系：Seurat `DimPlot` 默认**没有**等比例约束

- 实测（Seurat 5.5.1）：`deparse(Seurat::DimPlot)` / `Seurat:::SingleDimPlot` 中**搜不到 `coord_fixed`**；
  `p$coordinates` 类为 `CoordCartesian` 且 **`ratio = NULL`**，`p$theme$aspect.ratio = NULL`。
- ⇒ 面板纵横比**完全由画布逼出来**。横排 N 面板时面板 ≈ `(画布宽−图例宽)/N` × `画布高−条带边距`。
  实测 26×8 in + 6 面板单排 → 面板 **3.64 in 宽 × 7.2 in 高 = 1 : 1.98**，UMAP 纵向被拉伸约 **2 倍**。
- **UMAP/t-SNE/PCA 必须等比例**（两轴无非度量意义，拉伸会改变簇形状与视觉距离）。修复 = `+ coord_fixed(ratio = 1)`
  或 `theme(aspect.ratio = 1)`；**加完必须重算画布高度**（面板变方后原高度会留大片空白，见第 3 步）。
- ⚠️ `p$coordinates` 显示 `CoordCartesian` **不能**据此断定"没有等比例"——新版 ggplot2 把 `coord_fixed()`
  并入 `CoordCartesian` 实现。**判据 = `ratio` 字段是否 NULL + 源码里有没有调用**，不是类名。
- **`split.by` 的排布**：N 个水平生成 **1 行 × N 列** 单排（实测 6 水平 → gtable `panel-1-1 … panel-6-1` 全在
  同一 ROW），**不是** `facet_wrap` 默认的近方形排布。⇒ 宽幅画布匹配，但面板会被压成竖长条。

### 🔴 2. `pt.size` 是**绝对点径**，画布与点径必须联动——只砍一个必然出事

- 现象：26×8 in 改到 183 mm、**同时**把 `pt.size` 从 2 降到 0.25 → 点几乎看不见、面板发空，
  用户当场判"比原来的代码还要简陋"。**两次缩水叠加**是根因。
- 规则：**点径是最终尺寸下的绝对长度**，画布缩小 k 倍，点在面板里的相对占比也缩 k 倍。
  ⇒ 要么**保持画布**（点径不动），要么**画布与点径同时换算**。
- 实用"保持不动"技巧：**只改画布高度、不改宽度**——面板宽度不变 ⇒ `pt.size` 原值继续有效。
  实测 26×8 → **26×5** 后 6 个面板仍各 3.64 in 宽，`pt.size = 2` 视觉不变，只是高度收紧到刚好装下方面板。
- 真要投 183 mm 双栏（面板 ≈28 mm）时，点径同步降到 **0.35–0.5**、条带字号 5–7 pt。
- 🔴 **"按 Nature 级别优化" ≠ 把图缩小**。Nature 的本体 = 尺寸/字号规范 + 白底 + 矢量导出 + Source Data；
  缩小是**结果**不是手段。把画布和点径一起砍了 = 把图改坏，不是优化。

### 🔴 3. gtable 量不出面板尺寸——**必须量渲染后的像素**

- ggplot 面板是 **`null` 单位**（填充式）：`convertWidth(sum(g$widths[...]), "cm", TRUE)` 在设备外返回 **0**
  （伴随 `Cannot create zero-length unit vector` 报错时，多半是子集取空了）。
- ggplot2 4.0.3 命名变了：`names(g$grobs)` 返回 **NULL**；`g$layout$name` 形态是 `panel-1-1` / `strip-t-1-1`
  ⇒ `name == "panel"` 取不到任何行，必须 `grepl("^panel", ...)`；取 grob 用 `g$grobs[[which(...)]]`。
- **正确做法 = 导出一张预览 PNG，用像素量**：`scripts/measure_figure_geometry.py`（本 skill 自带）
  逐面板报内容宽高、纵横比、填充率、上下留白。
- **填充率是渲染健康度的单调标尺**：实测 796 细胞(3.7%) → 3,890 细胞(19.4%) 严格随细胞数递增
  ⇒ 点径/raster/配色都正常。**若某面板填充率与细胞数不同向，先查绘图层**。
- 矢量（PDF/SVG）适合交付但不适合量几何——量几何一律用 PNG 预览。

### 🔴 4. 图里的"空带/空洞"先查数据，别先怀疑渲染

- 实测：UMAP 分面图 y≈175–250 px 有一条横贯全图的近空带。**先做坐标直方图再下结论**。
- **像素↔数据换算**：`frac = (pixel_y − 面板顶) / 面板高`；`data_y = max − frac × (max − min)`。
- 实测结果：直方图显示 `UMAP_2 ∈ [4.9, 6.7]` 段细胞数 < 5（真稀疏），换算得空带 = 数据 **4.97–6.83**，
  **与直方图空段严丝合缝** ⇒ 是 zone6（中位 8.09）与主体（zone2/5 中位 3.0/1.9）之间的**真实流形间隙**，
  **不是**渲染伪影。**查清再交付**——把真实结构当 bug 去"修"会破坏数据。
- 排查顺序：坐标直方图 → 各群坐标范围 → 像素换算对齐，三步定案。

### 🔴 5. 配色可读性：灰度可分性一眼量化

- 灰度亮度 `L = 0.2126R + 0.7152G + 0.0722B`；**相邻两色 |ΔL| < 0.05 ⇒ 灰度打印下分不开**。
- 实测占位配色 `zone2 = 0.573` vs `zone6 = 0.578`（ΔL **0.005**）⇒ 灰度不可分，需换色或加形状编码。
- 命令：`python scripts/measure_figure_geometry.py --palette "NMK=#D62728,zone1=#1F77B4,..."`。
- ⚠️ 报告须写明**测的是哪套配色**——占位色测出的结论不能替用户宣称"你的配色达标"。

### 🔴 6. 改用户脚本的纪律（2026-09-22 用户两次发火，本 skill 硬约束）

- **用户贴的代码就是基线**：只改他**点名**的那一处，其余逐字保留（画布/点径/底色/字号一个不动）。
  曾把用户的 `split.by` 改成 `facet_wrap`、透明底改白底、9pt 改 6.5pt → 被质问"这才是我的原代码，你跑哪去了？"
- **风格变更 = 方向选择 → 先谈再改**。用户说"按 Nature 优化"时，先给"改哪几处 + 为什么"，
  **不要**直接重写整版。曾因跳过这一步被质问"你为什么在修改代码之前不弹窗询问我呢？"
- **报错要直接修，不要绕去"核验错误出处"**。曾去查错误来源文档，被"不是让你改一下报错吗？为啥一直卡着啊"。
  根因能一句话说清就直接给修复代码。
- **交付前自查有没有引入用户原代码里没有的变量**——曾自己加了 `TYPE_LAB[...]` 命名向量，引发
  `No cell overlap between new meta data and Seurat object`，然后把这个自造 bug 当成"用户的报错"修了两轮。
  ⚠️ **赋给 Seurat metadata 的向量必须 `unname()`**（命名向量的 names 会被拿去匹配 barcode → 零重叠报错）。
- **先出"用户原版"再出"优化版"两版对比**，不要只给一版（用户明确偏好两版对照）。
  同一纪律已在 `celltype-proportion-comparison` 的箱线图场景写明（勿 CNS 化、勿重写用户脚本），此处为通用化。
- **条带标题居中**：ggplot2 官方 theme 文档指出 strip 有 **position-dependent 元素**
  （`strip.text.x.top` 等），位置类样式**必须写到 position-dependent 元素**才可靠生效 ⇒ `strip.text` /
  `strip.text.x` / `strip.text.x.top` **三层全写**。验证 = 量条带文字中心与面板中心的偏差
  （实测 ≤10 px / 2600 px = 0.4%）。⚠️ 没做 A/B 对照就**不要声称"修好了原版不居中"**，只能说"本版实测居中"。

### 配套支持文件（本 skill）
- `references/figure-geometry-audit.md` — 几何自检完整配方：gtable 取值怪癖、像素测量口径、像素↔数据换算、坐标直方图分诊、灰度亮度表、A/B 两版实测数值
- `scripts/measure_figure_geometry.py` — 可复跑探针：量面板几何/填充率/留白；`--palette` 量配色灰度可分性

## 与其他 skill 分工

- **图型选择/整体规范** → cns-visualization、scipilot-figure-skill、nature-figure
- **配色选择（连续型 score / FeaturePlot 上色）** → 本 skill 的
  `references/publication-palettes-featureplot.md` 直接取用三套 Nature 级锚点 hex；
  分类色/整体配色规范仍走 cns-visualization
- **画什么图来论证** → figure-designer
- **本 skill 只解决导出段 + 配色速查**：多大、什么 dpi、什么格式、怎么压缩、用什么色

## 静默失败三坑（图保存成功但交付件是坏的）

出图**不报错**≠图是对的。三类必须靠自检抓：

| 坑 | 症状 | 判据 |
|---|---|---|
| 元素超出 xlim | 画布被 `bbox_inches='tight'` 撑大 | 输出宽度 > `figsize×dpi` 的 15%（实测 8416 px vs 应有 4050 px） |
| 比值 >100% 被画上轴 | 柱/标注渲染到坐标轴外 | 召回/命中率等比值指标的分子集合 > 分母池 ⇒ 跨方法**不可比**，须先按精度筛选 |
| 中文字体缺下标字形 | `Z₁/Z₂` 静默变方框，脚本正常退出 | `UserWarning: Glyph 8321 missing from font` —— Microsoft YaHei **不含** U+2080–2089，改用 `Z1` 或 mathtext `$Z_1$`；`①②③`（U+2460–）可用 |

**出图后必做**：① 报像素尺寸并断言在 `figsize×dpi` 的 15% 内；② `vision_describe` 核对 OCR 是否读出全部预期数字 + 有无方框 + 亮度图非全白全黑。详见 `references/matplotlib-canvas-and-font-pitfalls.md`。

## 参考文档

- `references/matplotlib-canvas-and-font-pitfalls.md` — 画布越界撑爆 / 比值 >100% 不可比 / 中文字体缺下标字形 / 出图后读图核验 / 换数字必重出源图（含断言代码）
- `references/high-cell-count-raster-export.md` — 50万点云导出的完整细节与
  Nature 契约表（本会话沉淀，含 ragg/ggsave 参数差异、pngquant 配方、经验法则）
- `references/publication-palettes-featureplot.md` — **发表级配色速查**：FeaturePlot / 连续型 score 上色的三套 Nature 级锚点 hex（viridis / Blues / YlOrRd，可直接粘 `cols=`）、为何弃用 `c("lightyellow","darkblue")`、配色包探测回退（不装包也能用）、**以及"探测→计算→出图写成一次 execute_r"的加速配方**、**§2b 图例改字必须改内层 scale（🔴 禁叠 `scale_*_gradientn`：Seurat v5 内部 `1~2` 缩放 → `limits` 错位 → `grey50` 黑白图；正确 = `p[[1]]$scales$get_scales("colour")` 原地改 breaks/labels）+ 交付前像素验证（主色不得为 `#7f7f7f`）**。用户说「给我个专业好看的颜色 / Nature 级别配色 / 要两三个」时先读它