# 矩阵热图版式与色标有效性（R base graphics 实测配方）

> 场景：把「程序 × 亚群」（或基因集 × 细胞类型、通路 × 样本）的**打分矩阵**画成 CNS 级热图。
> 本文件记录 2026-09-25 会话（FigA3 program × 10 myofiber subtypes，17 程序 / 5 轴，gene-set AUCell 打分）定稿的版式、几何坑与色标论证。

## 1. 用户既定版式（照此执行，勿自行发明）

左侧栏**自左向右**：

```
程序名(水平, 右对齐) → 分类名(竖排, 黑色 #1A1A1A) → 分类色块(各轴一色, 紧贴热图) → 热图
```

| 用户原话 | 落地 |
|---|---|
| 「从左边应该是基因集名字，分类名字，热图名字」 | 程序名最左；曾做的「竖排轴名 → 色块 → 程序名 → 热图」被明确否掉 |
| 「label 要贴着热图」 | 标签右端距热图 ≤0.02 数据单位（≈0.15 mm），`strwidth()` 实测 |
| 「分类的名字换成黑色字体」 | 分类名 `col="#1A1A1A"`，轴色只留色块 |
| 「头顶的标题和 label 不要重叠」 | 标题 `mtext(side=3)` 走上边距；居中 = `(W/2 - MAI[2]) / CELL` |
| 「亚群→x 轴、基因集→y 轴，长而不宽」 | 转置：10 列 × 17 行；画布 4.250 × 6.122 in = 107.9 × 155.5 mm（比例 1:1.44） |

## 2. 几何常量表（可直接复用）

| 常量 | 值 | 含义 |
|---|---|---|
| `CELL` | 0.255 in | 单元格边长（正方形，= 18.36 pt 边长） |
| `MAI` | c(0.75, 1.35, 0.55, 0.35) in | 下/左/上/右 |
| `GAPY` | 0.24 数据单位 | 轴间纵向间隙 |
| `LB0` / `LB1` | −0.06 / −0.77 | 分类色块右/左边界（宽 0.71 单位 ≈ 4.6 mm） |
| `LNX` | −1.10 | 分类名竖排中心 |
| `LBLX` | −1.45 | 程序名右端（`adj=c(1, 0.5)` 右对齐） |
| `W` / `H` | `NCOL*CELL + MAI[2] + MAI[4]` / `TOP*CELL + MAI[1] + MAI[3]` | 画布英寸 |

自检实测值（v6）：最长标签 `Fatty acid metab.` 左端 −2.737 > 画布左界 −5.294；四段间隙 = 程序名↔分类名 0.18 / 分类名↔色块 0.16 / 色块↔热图 0.06（数据单位）。

## 3. 三个必踩的 R base graphics 坑

### 3.1 y 轴向上增长 ⇒ 行布局必须从 YMAX 向下递减

```r
YMAX <- NROW + GAPY * (length(AXES) - 1)
rowy <- numeric(NROW); span <- list(); yc <- YMAX
for (k in seq_along(AXES)) {
  ax <- AXES[[k]]; s1 <- yc
  for (g in ax$members) { yc <- yc - 1; rowy[g] <- yc }   # 递减！
  span[[ax$name]] <- c(yc, s1)                            # c(下边界, 上边界)
  if (k < length(AXES)) yc <- yc - GAPY
}
stopifnot(abs(yc) < 1e-9)   # 兜住「循环末尾多减一次间隙」这类算术错（实测抓到 yc 期末 = −0.24）
```

按「0 往上累加」写会让**行序整体渲染成反的**——承诺置顶的轴掉到图底（v3 首版即如此，靠 OCR 坐标才发现：轴名 y=1808 vs 263 与设计相反）。

### 3.2 左侧栏绘制：`par(xpd = NA)` + 负 x 数据单位，且**自检先于出图**

```r
draw <- function() {
  par(mai = MAI, ps = 9, xpd = NA, family = "sans", lend = "butt", xaxs = "i", yaxs = "i")
  plot.new(); plot.window(xlim = c(0, NCOL), ylim = c(0, TOP))
  # 1 热图 (white 细格线)  2 分类色块  3 分类名(竖排, col="#1A1A1A")
  # 4 程序名(最左, adj=c(1,0.5))  5 亚群名(srt=45, adj=c(1,1))
  # 6 顶部色标(绘图区内)  7 标题 mtext(side=3)
}
```

自检（**放在 `open_dev()` 出图循环之前**，坏几何不落盘）：

```r
pdf(NULL); par(mai = MAI, ps = 9, family = "sans")
plot.new(); plot.window(xlim = c(0, NCOL), ylim = c(0, TOP))
lw  <- strwidth(DISP[PROGS], cex = 6.0 / 9)     # 各标签宽度（数据单位）
AXW <- 6.3 / 9 * 9 / 72 / CELL                  # 竖排分类名的 x 向占宽 ≈ 一行文字高
dev.off()
lbl_left <- min(LBLX - lw); canvas_left <- -MAI[2] / CELL
cat(if (lbl_left > canvas_left + 0.1) "画布内 OK" else "⚠️ 出界", "\n")
```

⚠️ `pdf(NULL)` 量不到 Arial（PostScript 设备）——字体宽度要用真设备或按名义值近似，别把量尺误差当成版式错。

### 3.3 版本化交付与归档

每版新文件名 `..._CNS_v{n}.{png,pdf,svg,tiff}`，上一版 `file.copy` 入 `archive_superseded/<名>_<改动标签>.*`（v5→`_axleft`、v4→`_labelfar`），**只归档不删除**（用户会回头比对）。归档标签要语义化，别用日期。

## 4. 色标口径：行内 z-score 站得住，但必须标注

用户提问「已经 AUCell 打分了，再 z-score 真的合理吗？」——官方依据（AUCell vignette 原文）：

- `The AUC is not an absolute value` ⇒ 原始 AUC 分**跨样本/细胞类型不可直接比**，做尺度可比处理是通行做法；
- 因此「per-program 跨亚群 z-score」不是多余步骤，而是**让色标可解释的必要环节**。

⚠️ 两个必须同时交代的边界：

1. **图注/色标标签写明口径**（含 ±2 截断），否则审稿人会问「这些色块强度能横向比吗」。
2. **低动态范围程序会被放大**：本会话实测 17 个程序跨 10 亚群的动态范围 15%–55%（最低 15%）。行内标准化把 15% 的微小波动拉成满色阶，**可能被误读为强结构** ⇒ 不得据色块强度对低动态程序下强生物学结论。

## 5. 灰度 / 色觉可达性审计（实测取代"看着能分"）

辩论反方唯一有数据支撑的质疑就是「低动态行被拉伸后灰度/色觉不可辨」。用 `scripts/audit_heatmap_gray_cvd.py` 实测（按几何反推每格中心 → 5×5 中位数取样）：

| 指标 | 实测（v6，17 行 × 10 格） |
|---|---|
| 相对亮度（灰度打印）Δ | min **0.639**（SenMayo，最低动态行）/ 中位 0.869 |
| Viénot 红绿色盲 Δ | min 1.183 / 中位 1.354 |
| Viénot 红色盲 Δ | min 1.169 / 中位 1.323 |

⇒ RdBu_r 在灰度与 CVD 下均可辨，该质疑不成立。**判据：先跑审计再回答可辨性问题**，别用「RdBu 是标准色标」当论据。

## 6. 与辩论引擎打交道的注意点

- `debate_analysis` 用 `auto_kb=false`（默认 `auto_kb` 路径在本平台会抛 `TypeError: 'in <string>' requires string as left operand, not list`）。
- `level="L1"` 下角色**可能只回传 reasoning 草稿**（回执带 `pro_draft_only / con_draft_only: true`）⇒ 裁决可用，但**引用时必须如实说明「角色未按契约输出、仅草稿，不构成否决依据」**，不要包装成正式对抗论证。
- figure_layout 场景裁判会开「宽度预算 / 灰度色觉模拟 / 期刊规范原文」类 `next_actions`；前两项可用本文 §2 §5 数据直接回填，第三项（目标期刊版式规范原文）属外部检索，缺它时裁决停在 `need_more_info (low)` 属正常，如实说明即可。