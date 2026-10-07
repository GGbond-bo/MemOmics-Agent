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
  **单元素改版核验（「只改这一处 / 其他的不变 / 只去掉这个元素」+ 改完怎么证明只动了那一处 / 像素差分 / 跨解释器渲染差分失真）**。
  **配色选择（给我一个专业好看的颜色 / Nature 级别配色 / 要两三个 / FeaturePlot 上色 / score 配色）**。
  **桑基图 / 桑葚图（常见错写）/ Sankey / Alluvial / 冲积图 / 左边X右边Y 流带图的版式与导出**；
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
| 中文字体缺**符号**字形（不止下标） | `Z₁/Z₂`、标题里的 `PCA↔scVI` 之类**静默变方框**；脚本正常退出、图文件照常生成，极易漏检 | `UserWarning: Glyph 8321 missing from font(s) Microsoft YaHei`（下标）/ `Glyph 8596 (\N{LEFT RIGHT ARROW}) missing from font`（箭头，2026-09-24 实测：6 面板指标图 4 处标题全中方框）—— Microsoft YaHei / SimHei **不含** U+2080–2089 与 U+2194 / U+2192；改用 `Z1`、mathtext `$Z_1$`，箭头改 `-` / `vs` / `与`；`①②③`（U+2460–）可用。⚠️ **出图后必须扫 stderr 有无 `Glyph … missing from font`** —— 只看「图文件生成了」＝漏检；含中文的 SVG 交付加 `plt.rcParams["svg.fonttype"]="path"`（字形转路径，不依赖目标机器字体） |

**出图后必做**：① 报像素尺寸并断言在 `figsize×dpi` 的 15% 内；② `vision_describe` 核对 OCR 是否读出全部预期数字 + 有无方框 + 亮度图非全白全黑。详见 `references/matplotlib-canvas-and-font-pitfalls.md`。

### 🔴 撑爆的**硬崩**变体：单位不一致把 artist 丢到数据区外（2026-10-01 实测）

上表第一行是"撑大但不报错"；同一族还有一个**直接崩**的变体，症状完全不同，别当成两回事：

```
ValueError: Image size of 30117798x839 pixels is too large. It must be less than 2^23 in each direction.
```

抛在 `savefig` → `draw` → `RendererAgg` 里（**不在你的绘图逻辑里**）⇒ 别先去读自己的画图代码，先查 artist 坐标。

**根因**：轴已换算成 Mb，偏移常量又乘了一次跨度常量 ——

```python
s = gi['start'] / 1e6          # 88.7 (Mb)
ax.text(s - 0.02 * Mb, ...)    # 88.7 − 20000 = −19911 ← artist 飞到离数据区 2e4 处
```

`bbox_inches='tight'` 把它纳入 bbox ⇒ 画布宽度被撑到 3.0e7 px（PNG/HTML 上限 2^23 = 8,388,608）。

**修法**：偏移量用**同单位** → `ax.text(s - 0.02, ...)`（左移 0.02 Mb）。

**排查纪律（反直觉，务必照做）**：见到 `Image size … too large` ⛔ **不要调 `figsize` / `dpi`** ——
那是改症状不是改根因，图会变小但 artist 仍在域外。正确顺序 = **打印所有 artist 的 x/y 范围找离群坐标**。
通用规则：一个轴里所有坐标常量必须同单位；凡做过 `/1e6`（或任何单位换算）的轴，**禁止再乘跨度常量**。

### 🔴 第四坑：PDF 交付件**字体未嵌入**（R `ggsave` 默认 pdf 设备，2026-09-30 实测）

`ggsave("x.pdf", p3, width = 8, height = 6)` 走 base `pdf()` 设备 ⇒ **字体不嵌入**，
字节里搜不到 `/FontFile`，投稿会被退；本地打开却毫无异常 —— 又一个**静默失败**。
**判据用字节，不用眼看**：

```r
raw <- readBin(f, "raw", file.info(f)$size)
length(grepRaw("/FontFile", raw, all = FALSE)) > 0   # FALSE ⇒ 未嵌入
```

修法 = 显式换设备：`ggsave(..., device = cairo_pdf)`。
实测同一批 5 张图一次改动：**2.8–3.4 MB 无嵌入 → 1.8–2.2 MB 已嵌入**（子集化后反而更小）。
同族可选设备：`ragg::agg_tiff`、`svglite::svglite`（SVG 记得 `print(p)`）。

同批另两条导出核验（都是一行代码，别只报文件大小）：

- **SVG「文字可编辑」** = 数 `<text` 元素（本例每图 ~100 个）+ 确认各分类色 hex 出现在文件里（8/8）
- **PNG** 报尺寸 / 墨迹占比 / 类别色数（本例 2400×1800 @300dpi、墨迹 13–27%、8 色块 8 色相）

🔴 **一次改完即停，不要为同一批图反复做二次核对**（见 `references/multipanel-figure-qa.md` 的收尾纪律）。

### 🔴 第五坑：底部图例被裁 —— 健康检查全过、只有 OCR 能抓（2026-10-01 实测）

`ax.legend(ncol=1)` 放在 axes 下方（`bbox_to_anchor` 负 y）时，设计 4 行（title + 3 条目）
**导出后只剩 2 行**，后面两条被静默裁掉。`bbox_inches="tight"` **拦不住**：
legend 与画布内其他 artist（`transAxes` 定位的脚注文字）重叠时，tight bbox 仍算不够。

**本例三个健康检查全部通过**：990 KB、非空白、通道极值 0–255、唯一色 3,511 种 ——
**只有 `vision_describe` 逐条数 OCR 文本才暴露「图例条目数 ≠ 设计条目数」**。

修法四条一起做：① 底部图例一律横排 `ncol=3`；② `fig.subplots_adjust(bottom=0.21)`（≥0.20）；
③ 第二个 legend 必须 `ax.add_artist(leg1)` 才叠加得上；④ 多条图例分**两行**排，别一行塞两组。

**通用判据（不限于 Sankey）**：任何 figure，**出图后数 OCR 文本条数 = 预期元素数**；
偏少就是有元素静默没渲染出来。完整配方（零依赖手绘贝塞尔流带、左右各自归一布局、
带宽 = 跨条件支持度语义、Sankey/Alluvial 触发词）→
`references/sankey-alluvial-matplotlib.md`。

### 🔴 第六坑：**顶部**同样会被裁 + OCR「混读」＝文本重叠的确定性判据（2026-10-01 实测）

第五坑是**底部**图例被裁，本坑是**顶部**标题被裁 —— 成因不同，同一张图会先后踩到。

**成因**：主标题写在**轴坐标系**且靠近 `ylim` 上沿（`ax.text(0.5, 1.085, ttl, va="bottom")`
配 `set_ylim(-0.06, 1.10)`）⇒ 文字从 1.085 **往上**排版、越过画布顶 ⇒ 上半被切。
**OCR 证据**：`…对比×来源亚群` 的 `×` 被读成 `?`（笔画被切掉才误读），且标题比第一个节点标签还低。

**修法两条一起做**：① 主标题移到 **figure 坐标系 + `va="top"`**（向下排版，永不越界）
`fig.text(0.5, 0.972, ttl, ha="center", va="top")` + `subplots_adjust(top=0.925)`；
② 轴内列标题与首行标签**留距**：`set_ylim(-0.06, 1.20)`、列标题 `y=1.105`，节点仍从 `1.0` 起。

🔴 **OCR「混读」≠ OCR 出错，而是两个 label 撞在一起**：
`Subcluster`（列标题）与 `Pure Type I (10)`（首行标签）重叠时，OCR **不会**返回两条，
而是返回一条拼接乱串 —— 实测修前 `PurSupe山ster`，修后 `Subcluster` @y348 **与**
`Pure Type I (10)` @y474 **各自独立读出**。
⇒ **判据：某条 OCR 文本若由两个预期标签的片段拼成，就是重叠，别当识别噪声放过。**
这是唯一能廉价抓到「两个 label 撞一起」的探针（文件大小 / 非空白 / 通道极值全都看不出来）。
整图 OCR 已能发现；**裁顶部 20% 并放大 1.6–2×** 再 OCR 置信度更高：
`Image.open(p).crop((0,0,W,int(H*0.20))).resize((int(W*1.6), int(H*0.20*1.6)), Image.LANCZOS)`。

### 🔴 第七坑：标签"跑位"到色块之外 —— 根因在**布局**，不在标签（2026-10-01 实测）

用户报「**亚群和基因要跟自己对应的色块对齐**」时 **先别去改 `ax.text`** ——
本会话实测标签本来就画在节点真实中点 `(y0+y1)/2` 上，画错的是**节点区间本身**：

```python
gap    = GAP_L * tot / (n - 1)   # ❌ 把"总权重数值"当成了比例系数
usable = 1 - gap                 # UP 图 tot=102 ⇒ gap=0.022×102=2.244 ⇒ usable = −1.244（负！）
```

`usable` 为负 ⇒ **每个节点高度为负** ⇒ 相邻节点区间互相重叠
（实测 ITIH4 `[1.00, 1.27]` 与 MEF2C-AS1 `[0.89, 1.14]` 叠了 0.14 单位）；
后画的色块盖住前一个的下半截，而标签仍按真实中心绘制 ⇒ **越靠该端偏得越多**
（实测 72 / 53 / 27 px），下方没重叠的基因看着"完全正常"，极具误导性。

⇒ **判据：只有部分标签跑位、且越靠某一端越严重 ⇒ 是布局溢出，不是标签绘制错。**
（对照：若标签是按节点高度百分比定位的，那才会整体偏——那是另一类 bug。）

✅ **修法**：间隙改成**整列固定比例** —— `gap = 0.10/(n-1)`、`usable = 0.90`，节点高度恢复正常且不再重叠。
✅ **自检硬指标（写进脚本，别靠肉眼）**：① 标签中心 ↔ 其色块中心偏差 = **0.00 px**；
② 相邻节点区间重叠 = **0 对**。两项都过才算修好，报数字不报"看起来对齐了"。

⚠️ **别被"另一张图看着没问题"误导**：同批 DOWN 图 `tot=24` 侥幸没算成负值 ⇒ 只有 UP 图暴露。
**一份数据出多张同族图时，布局溢出的检查必须逐图做**，一张过不代表另一张过。

### 🔴 图内文字一律英文（用户定稿偏好，2026-10-01）

用户明确要求「**把图中说明文字改成英文**」⇒ 本类图**默认直接出英文版**，
不要再先出中文版等用户回来改：标题 / 列名 / 图例 title + 条目 / 脚注 / 单位，一处不留。
字体同步换 `["Arial", "Helvetica", "DejaVu Sans"]`（英文图不必挂中文字体，
顺带规避「中文字体缺符号字形」那一坑，见上文静默失败三坑）。
完整中→英对照表（本例实译，可直接复用）在
`references/sankey-alluvial-matplotlib.md` §6b。

## 多面板图的空白面板探针 & 导出环节两个 Windows 坑（2026-09-29 实测）

### 🔴 分块墨量图：抓"某个 panel 是空的"（比整体非白占比灵敏得多）

整体"非白占比 17.7%"完全可以由另外 3 个 panel 撑起来，第 4 个空白时**照样通过**。
**必须按 tile 分块量**：把成图切成 4×3（或按 panel 数）网格，逐块报墨量。

```python
from PIL import Image; import numpy as np
a = np.asarray(Image.open(png).convert("RGB")); H, W, _ = a.shape
ink = [[(a[i*H//4:(i+1)*H//4, j*W//3:(j+1)*W//3] < 245).any(axis=2).mean()*100
        for j in range(3)] for i in range(4)]     # 任一块 <1% ⇒ 该区几乎是空白，去查
```

判据：任何 tile 墨量 **<1%** ⇒ 该区域空白，回到数据/绘图层查；
同时报 `unique colors`（>1000 才算有真实内容，单一色 = 渲染失败）。
本会话实测：4×3 分块墨量 6.94–34.52% 全达标 ⇒ 4 个 panel 都有内容。

> 为什么必须分块：本会话早前就吃过一次亏——一张 61.9 KB 的图**非白 0.0%、
> 唯一色 1 种**（真空白）却被当成"通过健康检查"汇报了，因为当时只看了文件大小。
> 分块墨量图是能在**汇报前**抓住这类问题的探针。

### 🔴 校验通过就停手——不要反复重跑验证

图已导出、分块探针已通过、`rail_review(post)` 已 passed ⇒ **任务完成，立即汇报**。
**不要再做第二次/第三次像素核对、不要再重算尺寸**。本会话因对同一张 TIFF 连续重复校验
被系统循环检测强制中断——重复验证不仅烧 token，还会被判定为循环失控。
一次探针出数字 → 报数字 → 交付。

### ⚠️ Windows：600 dpi TIFF 想事后压缩，不要就地覆盖同一路径

- matplotlib 存 600 dpi TIFF 不压缩（183×152 mm → 实测 **72 MB**，4649×3877 px）。
- 想用 PIL 转 LZW **重写同一个路径会失败**：`OSError: [Errno 22] Invalid argument`（句柄占用）；
  改用 tmp 文件 + `os.replace` 仍被拒：`PermissionError: [WinError 5] 拒绝访问`。
- ✅ **正确做法 = 另存新文件名**（不要原地覆盖），例如 `<stem>_lzw.tiff`；或
  **直接交付未压缩 TIFF**——Nature 位图上限 300 MB，72 MB 完全可用。
  压缩是优化不是必需，**不要为压缩反复折腾**（本会话在此烧掉两轮）。
- 若确实必须同一路径：先 `with Image.open(p) as im: im.load(); buf = im.copy()`
  再写到**另一个名字**。但收益远小于折腾成本，默认放弃。

### 组合图常用骨架（hero + 3 证据面板）

宽幅 hero 面板 + 一行三等分证据面板，是"定量网格"类论文图的稳妥骨架：
**hero 用语义双编码**（面积 = 比例/计数，颜色 = 方向/偏倚），辅助面板各只承担**一条**
独立证据，不做重复编码。本会话实例（细胞级 DEG 全景）：hero = 5 对比 × 10 亚群圆矩阵
（面积 = FDR<0.05 占比、颜色 = 上调比例），辅面板 = p 值区间堆积条 / |效应量| 分布 /
"全部基因 vs 显著基因"中位对比。完整配方见 `references/multipanel-figure-qa.md`。

## CNS 图「不好看」的四类客观硬伤 + 变体挑选协议（2026-09-29 实测）

用户说「我觉得不好看」时**先量，不要先换配色**——本会话从图上读出的四类硬伤全部可判定，
**没有一类是配色问题**。完整判据、代码与四变体规格见
`references/cns-figure-refinement-variants.md`。

| # | 硬伤 | 判据（实测） | 修法 |
|---|---|---|---|
| 1 | 图面写句子 | 3 处长句印在画布上，含**结论式标题** `Significance is decoupled from effect size` | 全部移入 caption；标题只留中性描述 |
| 2 | 字号系统性偏小 | 全图 5.0–6.2 pt；**OCR 读错即证据**：`Old`→`PIO`、`OTUD1+(II)`→`OTUDPe(II)` | 轴标 ≥7 pt、面板标题 8 pt、panel 字母 10 pt |
| 3 | 圆远小于格子（留白） | `RMAX=0.44` ⇒ 只占格子 60.8%；成图 **78.4% 像素是灰白底** | 提到 0.47–0.49（0.5=相切）+ 去掉格底纹 |
| 4 | 头重脚轻 | hero 占 2/3 高但内容稀疏，3 个证据面板挤在下 1/3 | `height_ratios` 2.05 → 1.38 |

🔴 **OCR 是免费的字号探针**：`vision_describe` 读错标签字符（把 `Old` 认成 `PIO`）= 字号已到人眼临界，
比「我觉得小」可辩护得多。改前 OCR 留证 → 改后 OCR 复核，标签能读全即达标。
（多条同时读错才说明字号是主因；单条可能是旋转/抗锯齿。）

### 变体挑选协议（用户说「多出几个，我自己挑选」时）

**不要单版反复微调**——一次出 3–4 版**同骨架**变体，差异必须是**可命名的版式策略**
（留白 / 比例 / 分区 / 紧凑度），不是只换配色（那只叫同一版）。

工程做法：**一个脚本参数化出全部变体**（面板函数收 `rmax/ring/group_lines/palette/fs`）
+ 源数据 `pickle` **缓存一次**（本会话 5 个 18 MB xlsx → 340,971 行，缓存后 4 变体各渲染秒级）。
挑选用 **PNG 300 dpi + PDF**；**SVG/TIFF 定稿等用户选定后再出**
（4 张 600 dpi TIFF ≈ 280 MB，全是浪费）。

### 🔴 倒置轴：轴内文字越界会掉到刻度标签行上（本会话真 bug）

`ax.invert_yaxis()` + `set_ylim(-0.55, nrow-0.20)` 时，组标签写在 `y = nrow-0.13 = 4.87`
**超出上界 4.80** ⇒ 文字被挤到轴外、**正好压住 x 轴刻度标签**
（OCR 读出 `Pure` 与 `Pure Type I` 同一 y 才发现——不看 OCR 就会当成"标签渲染正常"发出去）。

修法：用组标签时预留头部空间，文字放**负 y**：

```python
ax.set_ylim(-0.80 if group_lines else -0.55, nrow - 0.20)
ax.invert_yaxis()
ax.text(x, -0.62, lab, ha="center", va="center")     # 顶部，不是 nrow-0.13
```

**通用判据**：倒置轴里"更靠上" = **更小的 y**；任何贴矩阵外缘的标注，
y 必须落在 `ylim` 内**且符号与直觉相反**。

## 多面板同轴背离柱大图：刻度策略 + 顶部/左侧 frame（2026-09-29 实测）

N 个面板并排、共用同一行轴（亚群 / 细胞类型 / 组别），每面板 = 水平背离柱（右=上调 左=下调）。
版式常量、`yfrac()` 公式与可复用清单见 `references/multipanel-diverging-bar-frame.md`。

### 🔴 刻度策略（**用户已定稿的偏好——别再默认共享刻度**）

先算 `max(各面板极值) / min(各面板极值)`：

| 量级比 | 选择 |
|---|---|
| ≤ ~10× | 共享刻度（含 symlog），跨组直读 |
| > ~10×（本例 Aging 5,218 vs Ex_Young 15 ≈ **350×**） | **每面板独立绝对刻度（freescale）** |

本会话用户明确选了独立绝对刻度版（`..._combined_freescale`）并否掉共享 symlog 版——
共享刻度下小面板的柱全塌成 0。⇒ **跨数量级的多面板柱图默认独立刻度**，
且必须写进图注 `Independent absolute scale per panel`（否则读者会跨面板比柱长）；
独立刻度下**柱长 = 数值一比一**，不要再叠 symlog（比例墨迹违规）。

> ⚠️ **2026-09-29 后续演化 —— 原先写死的「不要再叠 symlog」已被用户自己推翻，勿再据旧文拒绝请求。**
> 用户看过 freescale 版后又提出：「Aging 这里，x 轴改成统一标准……然后刻度有梯度，
> **这样 Aging 衰老的才能展示出来**」，并点名参照 `fig_deg_updown_8sub_CNS_v2_minimal` 的 Aging。
> ⇒ **跨数量级默认仍是独立刻度，但当本轮叙事目标是「哪一组是主导效应」时，用户会要求统一轴。**
> **统一 symlog + 逐柱数值标签是合法组合**：标签补回被 symlog 压掉的精确值，
> 长度比承担「衰老 ≫ 运动」这个结论；判据是**有没有逐柱数值标签**（有 → 放心统一轴）。
> 图注相应改成 `Unified symmetric-log scale across panels · decade ticks`。
> 🔴 两条硬约束：① `symlog` 的 `linthresh` **取 1，不要取 10** —— lt=10 时线性段吃掉半轴宽 77%，
> 十倍刻度全挤在最外侧 13%（`线性段占比 = adj·lt / (adj·lt + log10(t/lt))`，`adj = 1/(1-10⁻¹) = 1.111`）；
> ② **`TMAX` 取单行最大值，不是面板合计**（曾把 Aging 面板合计 16,535 当 max 而算错刻度上限）。

### 顶部 / 左侧两个区域的升级套路（用户点名"优化上面和左侧"时照此做）

- **顶部**：家族超标题 + 同色细线（横跨该家族全部面板）→ 面板字母 a–e → 组名 → 标题下 1.5pt
  家族色条 → `ΣUp ↑ / ΣDown ↓` 彩色计数 → 贯穿全宽的分割线 → **右上共享图例（只画一次，禁每面板重复）**
- **左侧**（🔴 2026-09-29 v3 修正版式）：旋转轴名 → 亚群名**右对齐** → **模块竖带**（如 `MF`）→ 柱区。
  ⛔ **不要再放"两级分组竖括号 + 旋转家族名"** —— 用户 v3 明确点出「右侧亚群跟来源重合了」，
  根因是**算术问题**：右对齐基准 0.170、13 字符名字宽 ≈0.085 ⇒ 名字左缘 ≈0.085，
  必然穿过 x=0.150 的括号与 x=0.137 的旋转家族名。
  ✅ 改法：把家族分组做成**一条模块竖带**（浅底矩形 `#F4F4F4` + 右缘竖线 + 居中旋转模块名），
  亚群名右对齐基准移到竖带**左侧**（本例 0.090，竖带 0.098–0.126，柱区 LM 0.126）；
  想保留 Pure/Derived 分块信息 → 用极浅虚线分隔（`#D0D0D0`, `lw=0.6`, `(0,(1,1.6))`），不写文字就不争位置。
  **改版前先做宽度的 fig-fraction 算术**：`字符数 × 0.5em × 字号pt ÷ 72 ÷ 图宽in`。详见 references §4。
- 🔴 **每根柱都要标自身数值**（用户 v3 第三问："贴近，但是又不重合"）：一律用
  `textcoords="offset points"`，外侧 2.5 pt；柱端进入轴最外 20%（`ax.xaxis.get_transform()` 算 frac > 0.80）
  时改**柱内白字右对齐**。值为 0 的柱 pad 提到 4.2 pt（否则左右两个 `"0"` 贴一起）。
  刻度标签在轴下方、柱值标签在轴内 → 不同纵向带，天然不互撞。详见 references §4b。
- **家具一律画在 figure 坐标**：`fig.text(...)` + `fig.add_artist(Line2D(...))` —— 不裁切、
  不需 `bbox_inches` 补偿，比 `ax.plot(clip_on=False, transform=ax.transAxes)` 稳
- **分组只能取现有行序里的连续段**；若逻辑分组要求重排行序 ⇒ **先问用户**（重排 = 改结构，
  超出"整体结构不变"的授权）

### 🔴 结构不变的改图纪律 + 两个自检反例

- 用户说"在这个基础上优化，整体结构不变" ⇒ 复用已算好的计数表、柱区零改动，
  并**用总量复核证明结构没变**（本例 `ΣUp/ΣDown` 与基线逐项吻合：16,535/380、125/144、
  61/38、231/1,091、107/119）——比"看起来一样"硬得多。
  **把这次汇总打印留在脚本里**，改版重跑即自动对照
- **像素带墨率必要但不充分**：只证明"那里有东西"，**证明不了"那里是什么"** ⇒ 必须接裁切 OCR
- 🔴 **旋转文字必须先转正再 OCR**：`im.crop(...).rotate(-90, expand=True)`；未转正只会回乱码片段
  （本例 `srefik` / `Jeriv` / `ndn`），**看到旋转乱码先怀疑没转正，别怀疑渲染失败**
- 🔴 **禁止用"精确颜色像素计数"判定文字是否存在**：按 teal `#0F5F6E` + 三通道差和容差 40 计数
  命中 **0**，差点误判"家族标题没渲染"；实际渲染在案（抗锯齿把核心色压深成 `#004060`，
  差和 60 > 40）。验"有没有字"用 OCR；验色只能作辅助且必须宽容差 / 色相距离

## 🔴 单元素改版（"只去掉 a–e / 只对调一处"）：像素差分核验协议（2026-09-29 v4→v5 实测）

用户说"这张图还有个小问题，只改 X，其他的不变"时，交付前**必须用逐像素差分证明"其余零改动"**，
不能说"看着没变"。完整配方 + 实测数值见 `references/single-element-revision-pixel-diff.md`，
探针 = `scripts/pixel_diff_single_change.py`（可直接跑）。

**四步协议**
1. `cp 脚本N.py 脚本N+1.py` → 只 patch 目标行并改 `STEM`（**旧版文件永不覆盖**，逐版留档）
2. 用**会话持久内核**重渲染（`execute_python` + `exec(open(脚本, encoding="utf-8").read())`）
3. 逐像素差分旧版 vs 新版：①差异像素数②包围盒行范围 + y-frac③x 方向簇数与簇宽④**静区差异**（柱区/底部应为 0）
4. 结论口径：**静区 0 + 簇数 = 改动元素个数 ⇒ 只改了那一处**（本例 v3→v4 删 5 个面板字母：
   2,229 px = 画布 0.057%、行 169–203、x 恰好 5 簇各 23–24 px、柱区 0、底部 0）

### 🔴 陷阱：跨解释器渲染会让这套核验**彻底失真**（本会话真踩）

| 渲染解释器 | matplotlib | 与 v4 的差分 |
|---|---|---|
| `.venv` 持久内核（v4 本来就是它渲的） | **3.10.9** | **13,320 px，全部落在 Σ 行（行 274–306）· 柱区 0 · 底部 0** ✅ |
| 系统 `Python312`（误用冷启动 `python x.py`） | 3.11.0 | 111,449 px **散布全画布** · 柱区 33,277 · 底部 41,022 ❌ |

两者都解析到 Arial，**版本不同 ⇒ 字形/hinting 细节全变**。差分的有效性以"两版同渲染器"为前提。
看到大范围差异先跑 `--probe` 查解释器与 matplotlib 版本，**别急着怀疑版式被改坏**；不一致就用内核重渲覆盖再重跑差分。

**fig 坐标 → 图像行的换算**（判读差分的钥匙）：图像 y 自上而下 ⇒ `y_img = (1 − y_fig) × H`。
本例 Σ 行写于 `y_fig = 0.789` ⇒ 图像 y-frac 0.211，与差分包围盒 0.199–0.222 吻合。

### 🔴 文字顺序必须与空间编码同向（本轮用户抓出的真 bug）

顶部 `ΣUp ↑ | ΣDown ↓` 把 **Up 写在中心线左侧**，而柱子是"蓝 Down 向左伸、红 Up 向右伸"
⇒ 同一张图里两套编码互相矛盾。**判据：计数文字的左右顺序 = 柱子的左右几何顺序**（左 = Down 蓝、右 = Up 红）。
用户给的例子 `380 | 16535`（而不是 `16535 | 380`）就是这个意思。
- ⚠️ 用户原话出现**互相矛盾的两句**时（"不应该红色数值在左边吗" vs 例子里"应该是 380|16535"）：
  按**具体例子 + 图内几何一致性**执行，并在回复里**明说按哪句做的**，附一句"要反过来就说一声"。
- ⚠️ 冗余编码：`#B2182B` / `#2166AC` 在灰度下亮度接近，且 `↑/↓` 是**竖直**箭头而柱是**水平**的
  ⇒ 辩论席位一致建议数字旁用**横向 ←/→** 或同侧微型色块；**顺序类元素 ≥3 处（柱 / 右上图例 / 计数条）
  必须统一**，改一处要顺带检查其余两处（本例图例仍是 Up 在上，与柱子相反）。
- 🔴 **密集小号数字行别指望 OCR**（本例 6.6 pt，整条只读出一个"一"）⇒ 改量**颜色簇的 x 位置**：
  按面板区段切带、取红/蓝掩膜（容差 ~90）、报簇的 x 范围与面板中心的关系。
  这是"顺序对不对"这类问题的**确定性判据**，比 OCR 可靠。
- ⚠️ 冗余改动超出"只改一处"的授权 ⇒ 用 `ask_user` 给可勾选选项（要不要换横向箭头 / 要不要顺带统一图例），
  不要擅自把用户没点名的元素一起改掉。

## 参考文档

- `references/cns-figure-refinement-variants.md` — **CNS 图版式精修**：四类硬伤判据与修法、OCR 字号探针、
  多变体生产配方（面板参数化 + 源数据缓存 + 导出分层）、四变体规格表（可直接复用）、
  倒置轴标签越界坑、多产物批量探针（**一次调用**出 4 张体检表）
- `references/matplotlib-canvas-and-font-pitfalls.md` — 画布越界撑爆 / 比值 >100% 不可比 / 中文字体缺下标字形 / 出图后读图核验 / 换数字必重出源图（含断言代码）
- `references/multipanel-figure-qa.md` — **多面板组合图交付三件套**：分块墨量探针（可复跑，抓空白 panel）、收尾纪律（探针通过即停，禁止重复校验）、Windows TIFF 压缩坑与修复、hero+3 证据面板骨架构型、语义双编码规则
- `references/multipanel-diverging-bar-frame.md` — **多面板同轴背离柱大图的 frame 配方**（2026-09-29 v3 修订）：刻度策略**两阶段演化史**（独立绝对刻度 → 统一 symlog，含"round 2 用户推翻 round 1"的完整判据与图注写法）、**统一 symlog 配方**（`linthresh` 线性段占比公式、纯十倍阶梯、`TMAX` 取单行 max 的陷阱）、**左侧"模块竖带"版式**（取代旧的两级家族括号；含文字宽度的 fig-fraction 压叠算术与反面案例）、**逐柱数值标签**（`frac>0.80 → 内嵌白字` 分流 + `offset points` 纪律）、顶部标题带 figure 坐标常量、`yfrac()` 与 `set_ylim` 镜像公式、结构不变的改图纪律（总量复核 + 按文件名定位生成脚本）、裁切+转正 OCR 双验与「精确颜色计数」假阴性反例、四格式 + source data 导出清单
- `references/sankey-alluvial-matplotlib.md` — **Sankey / Alluvial（左类别→右类别）版式与导出**（2026-10-01 实测）：
  零依赖手绘三次贝塞尔流带、**左右各自归一**的布局算法（共用比例会让图歪向一边）、
  **带宽语义 = 该「左-右」对被几个条件共同支持**（共识带数量本身就是结论）、
  节点分档配色、**底部图例裁切坑**（`ncol=1` 竖排被静默裁掉，健康检查全过）、
  **§6b 顶部标题裁切**（figure 坐标 + `va="top"` 修法）与 **OCR「混读」= 文本重叠判据**、
  **图内文字一律英文**（用户定稿偏好 + 中→英对照表）、
  出图后 OCR 数条目自检、触发词「桑基图 / **桑葚图**（常见错写）/ Sankey / Alluvial」
- `references/high-cell-count-raster-export.md` — 50万点云导出的完整细节与
  Nature 契约表（本会话沉淀，含 ragg/ggsave 参数差异、pngquant 配方、经验法则）
- `references/publication-palettes-featureplot.md` — **发表级配色速查**：FeaturePlot / 连续型 score 上色的三套 Nature 级锚点 hex（viridis / Blues / YlOrRd，可直接粘 `cols=`）、为何弃用 `c("lightyellow","darkblue")`、配色包探测回退（不装包也能用）、**以及"探测→计算→出图写成一次 execute_r"的加速配方**、**§2b 图例改字必须改内层 scale（🔴 禁叠 `scale_*_gradientn`：Seurat v5 内部 `1~2` 缩放 → `limits` 错位 → `grey50` 黑白图；正确 = `p[[1]]$scales$get_scales("colour")` 原地改 breaks/labels）+ 交付前像素验证（主色不得为 `#7f7f7f`）**。用户说「给我个专业好看的颜色 / Nature 级别配色 / 要两三个」时先读它
- `references/single-element-revision-pixel-diff.md` — **单元素改版核验**（2026-09-29 v4→v5）：
  "只改一处、其他不变"的四步协议与两轮实测数值（v3→v4 删面板字母 2,229 px / 5 簇；v4→v5 Σ 对调 13,320 px / 1 簇）、
  **跨解释器渲染使差分失真**的完整对照表（mpl 3.10.9 vs 3.11.0 → 13,320 vs 111,449 px）、
  fig 坐标↔图像行换算、顺序类问题的颜色簇判据、用户矛盾表述的处理、冗余编码候选（含 3 篇 PMID）
- `scripts/pixel_diff_single_change.py` — 可复跑探针：`--probe` 打印解释器/matplotlib 版本/字体链；
  `OLD.png NEW.png --quiet 0.25 0.80 0.85 1.0` 报差异像素数、包围盒行+y-frac、x 簇数与簇宽、静区差异、健康检查