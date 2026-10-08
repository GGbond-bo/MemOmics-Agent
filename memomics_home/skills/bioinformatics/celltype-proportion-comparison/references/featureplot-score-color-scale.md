# FeaturePlot 连续色阶：让打分从 min 到 max 分配（AUCell / UCell / module score）

适用：细胞打分（AUCell、UCell、AddModuleScore）以 metadata 列形式存在 Seurat 对象里
（本项目常见列名：`scoreI_AUC` / `score*_AUC` / `Type_IIA_score`），要在 UMAP 上用 `FeaturePlot` 展示。
用户的两个反复诉求：① 颜色按该图真实 min→max 分配 ② 图例只显示最低值/最高值。

---

## 0. 🔴 最重要的一条：**不要覆盖 FeaturePlot 的 colour scale**（2026-09-21 实测，推翻本文件旧版方案 A/2c）

**症状**：`FeaturePlot(...) + scale_colour_gradientn(colours=pal, limits=range(obj$score), ...)`
→ 图**整张灰掉（grey50）= 黑白图**；把 `oob` 改成 `scales::squish`
→ 图**全部变成同一种颜色**（本次是全黄 `#fde725`）。

**根因（已实证，不是猜测）**：Seurat v5 的 `FeaturePlot` 返回的是 **patchwork** 对象，
且它**内部把 feature 值重缩放到 `1 ~ 2`**，自带的 colour scale `Limits: 1 -- 2`：

```r
p <- FeaturePlot(MF, "scoreI_AUC", cols = pal, pt.size = 0.5, order = TRUE)
class(p)                                    # patchwork/ggplot2::ggplot/...
inner <- p[[1]]
range(inner$data$scoreI_AUC)                # → 1 2        ← 关键！不是 0 ~ 0.974
inner$scales$get_scales("colour")           # <ScaleContinuous>  Limits: 1 -- 2
head(ggplot_build(inner)$data[[1]]$colour)  # 覆盖后 → "grey50" = 全 NA
```

你给 `limits = range(MF$scoreI_AUC)`（例：`0 ~ 0.974`）时，**数据（1~2）全部落在界外** →
默认 `oob = scales::censor` 把越界值全部转成 **NA** → 渲染成 `na.value` 默认色 **`grey50`** → 全图灰。
加 `oob = squish` 则全部压到端点 → 单色。**`limits` 越"真实"，图越坏**。

### ✅ 正确写法：`cols=` 上色 + **原地改内层 scale**（跑通并像素级验证）

```r
pal <- c("#440154", "#3a528a", "#238f8c", "#5ec762", "#fde725")   # viridis 5 色
lim <- range(MF$scoreI_AUC, na.rm = TRUE)   # 真实分数，仅用于图例文字

p <- FeaturePlot(MF, features = "scoreI_AUC", cols = pal, pt.size = 0.5, order = TRUE) +
     ggtitle("Type I score") +
     theme(plot.title = element_text(hjust = 0.5, size = 18))

sc <- p[[1]]$scales$get_scales("colour")   # 内层 scale（R6 引用语义 → 原地改立即生效）
sc$breaks <- sc$limits                     # 内层范围，实测 1~2（动态取，不要写死）
sc$labels <- c(sprintf("%.3f", lim[1]), sprintf("%.3f", lim[2]))   # 图例显示 0.000 / 0.974
sc$name   <- "Score"
p
```

- 低分自动 `#440154`、高分自动 `#fde725`，中间由 `cols` 线性插值——**不需要任何 `scale_*` 覆盖**。
- 图例只标两个端点 = `sc$breaks` 给**两个值**（给 5 个就显示 5 个刻度）。
- **图例写"Min"/"Max"字面文字**（用户上传的参考图就是这个样式）：`sc$labels <- c("Min", "Max")`；
  要显示真实数值就用上面的 `sprintf`。两版只差这一行。
- 验证（必做）：`head(ggplot_build(p[[1]])$data[[1]]$colour)` → 应是 `#440154 ...` 一类调色板 hex；
  **出现 `grey50` 就是 NA 陷阱复发了**。

### 交付前必须实跑 + 像素级验证（用户原话："你要不模拟一下？我现在拿到了黑白图"）

改色阶/图例这类**版式关键项**，不跑一遍就交付 = 把黑白图丢给用户。跑完用像素直方图自证：

```python
from PIL import Image; import numpy as np
a = np.array(Image.open("fig.png").convert("RGB")).reshape(-1, 3).astype(int)
pts = a[a.sum(1) < 690]; u, c = np.unique(pts, axis=0, return_counts=True)
print(["#%02x%02x%02x(n=%d)" % (*t, c[np.where((u == t).all(1))[0][0]])
       for t in u[np.argsort(-c)][:3]])
```

判据：主色应是调色板两端 hex（高值黄 `#fde725` + 低值深紫 `#440154` 都在）；
**主色是 `#7f7f7f`(grey50) / 单一色 / 大面积纯黑 = 失败**（实测失败版：`#7f7f7f n=64,297`）。
交付时附这一行结果（主色 hex + 计数），让用户不必自己开图验。

### 诊断探针（脚本没报错但图不对时按序跑这三行）

```r
class(p)                                     # patchwork → 不能整体加 scale
inner <- p[[1]]; range(inner$data[[<feature>]])   # 1~2 = Seurat 内部重缩放
head(ggplot_build(inner)$data[[1]]$colour)   # grey50 = 全 NA（limits/oob 错位）
```

---

## 1. 为什么默认看着"没按 min 到 max"

`FeaturePlot` 未显式给 `min.cutoff` / `max.cutoff`（默认 `NA`）时，色阶范围来自**当前绘制数据的实际范围**——
这一范围随三件事改变，所以你看到的"min→max"并不稳定：

| 变动 | 后果 |
|---|---|
| `subset()` 换细胞子集 | 分数 min/max 变了 → 同一个分数在新图里颜色不同 |
| 换 `slot` / `layer` / 换 assay | 取到的数值向量不同 |
| 图例小数位（默认 2 位） | AUCell 分数常是 0.05–0.35 量级，2 位小数把刻度压成 0.05/0.10/0.15，"看不出端点" |

`order = TRUE`（高分细胞后画、压在上层）是**打分图必开**的绘制顺序参数，不影响色阶，
但不开就会被低分细胞盖住、看着"没上色"。

`keep.scale` **只在 `features=` 传多个 feature 时生效**（决定各 feature 独立 scaling 还是统一）；
单 feature 传它是噪声参数，会让人误以为它在控制 min→max。

---

## 2. 🔴 跨图可比性：min→max 与"可比较"只能选一个

逐图各自 min→max ⇒ **每张图都好看，但彼此不可比**：同一分数在 A 图是浅蓝、在 B 图可能是深蓝。

| 论证目标 | 色阶设置 | 图注要求 |
|---|---|---|
| **单图内**看空间/亚群分布形态 | 该图 `range()` 锚定 min→max | 写明"色阶为该图内 min–max" |
| **跨亚群 / 跨组 / 跨时间点比较** | 所有 panel **同一 `limits`**（全体分数范围，或统一 0–1） | 写明统一范围，并给绝对值刻度 |

两者不可兼得。若用户既要比较又要清晰 → **拆成两套图**（各图 min→max 讲形态 + 统一 limits 讲比较），
不要在一套图里混用。这是出多面板打分图时最容易被审稿人抓住的点。

---

## 3. 三套 Nature 级连续配色（可直接粘）

| 方案 | hex 锚点（5 点） | 气质 / 适用 |
|---|---|---|
| **A viridis**（感知均匀 + 色盲友好） | `#440154` `#3b528b` `#21918c` `#5ec962` `#fde725` | 通用首选；灰度打印下仍分得开。**投 Nature/Cell/Science 系的安全牌** |
| **B Blues**（浅灰→深蓝单色阶） | `#deebf7` `#a7cee4` `#58a1cf` `#1b6aaf` `#08306b` | 最"干净"，低背景干扰；适合主图旁要放多张、不想抢眼 |
| **C YlOrRd**（黄→橙→红，"发热"感） | `#ffeda0` `#febb56` `#fd7034` `#da141e` `#800026` | 高值视觉冲击强；适合"高表达=要强调"的图，**不适合与暖色系其它面板并排** |

- B / C 的 5 个锚点取自 RColorBrewer（Blues / YlOrRd）9 级色的等距采样，A 取自 viridis 采样——
  都是**程序化提取**的准确值，不是肉眼调的。
- 2 色极简版：`c("lightgrey", "#08306b")`（浅灰→深蓝）。**避免纯红-绿组合**（色盲不友好）。
- 选型一句话：**要安全投刊 → A；要干净 → B；要强调高值 → C。**
- 已出过对比色卡 + 三张上色演示图：`results/memomics-b145cef6/figures/palette_card_featureplot.png`、
  `demo_palette_{A_viridis,B_blues,C_ylorrd}.png`；配色可访问性自检脚本
  `results/memomics-b145cef6/scripts/palette_accessibility_check.R`（灰度可分性 / CVD 模拟）。

---

## 4. 回答纪律（本类请求的铁律，2026-09-21 用户发火级信号）

用户贴一段自己的绘图代码问"能不能改好看/给专业配色"、或说"帮我改这个代码"时：

- **回复 = 代码块 + ≤2 句说明**。禁止附：改动理由表格、原理长段落、`ggsave` 导出代码、
  三套配色全展开、"要不要我跑一下"的追问。
- 用户原话"**这是啥啊？你只要给我代码就可以，搞那么复杂干什么？**" / "**给我代码就可以**" = 硬信号
  → 立刻瘦身到最小版，不再解释为什么之前的复杂是必要的。
- **代码要短 ≠ 不验证**：瘦身的是解释和加码参数，**不是验证**。用户在数据上拿到过黑白图后会直接质疑
  （"我现在拿到了黑白图。你煞笔吧"）——见 §0 的实跑 + 像素验证。
- 用户说"不需要跑"→ 只给代码，不动 R 内核、不建 task_plan、不 rail_review、不 debate。
- 递进顺序：① 只给配色 hex + 指出改哪一行 → ② 问 min→max / label 时给 `cols` + 内层 `sc$breaks/sc$labels`
  → ③ 嫌复杂就瘦身 → ④ 明确说"用真实数据跑"才执行（执行则必附像素验证结果）。

### 别加的东西（2026-09-21 被用户当场否决的过度工程）

| 加的东西 | 为什么不该进第一版 |
|---|---|
| `na.rm=TRUE` + `floor()/ceiling()` 向外取整到 3 位小数 | AUCell 少 NA 时纯冗余。**只在**实测范围过窄（多个标签显示成同一个数）时才提 |
| `oob = scales::squish` | **不是"可选优化"——它会和 Seurat 内部的 1~2 缩放冲突，把整图压成单色**（§0） |
| `na.value = "grey85"` | 同上；还会把"低分"与"缺失"混成一片灰 |
| `guide_colourbar(barwidth=…, barheight=…, title.position=…)` | 图例规格化是 AI 自认为的"发表级"，用户不需要 |
| `coord_fixed()` | UMAP 等比例确实更严谨，但**只在用户说"图被拉变形/椭了"时再提**，不要塞进第一版 |
| `suppressWarnings()` 包住 "Scale for colour is already present" 警告 | 覆盖是 ggplot2 官方语义、不是错误；包住反而掩盖信息。**本类图根本不该覆盖 scale（§0）** |

---

## 5. 导出（发表级）

```r
ggsave("figures/FeaturePlot_Type_I.pdf", p, width = 3.5, height = 3.2, units = "in", dpi = 300)
ggsave("figures/FeaturePlot_Type_I.png", p, width = 3.5, height = 3.2, units = "in", dpi = 300)
ggsave("figures/FeaturePlot_Type_I.svg", p, width = 3.5, height = 3.2, units = "in")
```

尺寸先定死再导出（不要导出后在 Word/PPT 里缩放）。整套发表级成图（尺寸/字号/多面板/灰度检查）
走 `nature-figure` skill；本文件只管**色阶范围与图例**这一层。

---

## 6. 相关

- `celltype-proportion-comparison` SKILL.md —— 本项目 AUCell 打分的另一主力呈现（比例箱线图 / 跨组差异）
- `plotting/fig-split-program-heatmap-R` —— 同一批程序打分的矩阵热图版
- `scipilot-figure-skill` / `nature-figure` —— 配色选型与整套发表级成图
- `platform-execution-pitfalls` —— 一次性 `execute_r` 合并出图、避免多轮往返拖慢（用户问过"为什么这么久"）