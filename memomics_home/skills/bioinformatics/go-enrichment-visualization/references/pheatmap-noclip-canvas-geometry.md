# pheatmap 零裁切画布几何（2026-09-15 实测定稿）

用户诉求原文：*"V12就可以，但是把左右边距再调大一点，确认所有词条被容纳"*。
本文件记录为什么 v12 其实一直在被裁、怎么一次性根治、以及验证探针。

---

## 1. 症状与误判

| 观察 | 错误归因 | 真实原因 |
|---|---|---|
| 改了好几轮画布宽度，Type IIA / 词条仍"被截断" | 画布不够宽 | 见下 §2 |
| 第一次像素扫描说"左边缘干净"，第二次说"x=0 有内容" | 检测代码不稳 | 两次测的是**不同量**（列名区 vs 全内容 bbox） |
| 空白 PNG 但 `exit_code == 0` | 代码报错 | 隐式设备吞掉绘制，见 §4 |

---

## 2. 根因：`cellwidth` 未指定 → 矩阵宽度按设备 npc 缩放

`pheatmap(cellwidth = NA)`（默认）时矩阵宽度**不是固定物理尺寸**，而是跟随当前设备宽度的比例。
后果：
- gtable 总宽 = 行名区(文本fixed) + 矩阵(npc) + padding → **不可预测**；
- 内容超过设备时，`grid.draw` 默认居中 → **左右各裁一半**（不是只裁右边）；
- 实测 v12：内容 17.78 cm + 边距(左2.8+右1.8) 4.6 cm = **22.38 cm**，画布 8.5 in = **21.59 cm** → 超出 0.79 cm → 每侧裁 ≈0.4 cm。

**像素证据（判定"是否被裁"的可靠判据）**：
```
左边缘 dark (x<10): 60   右边缘 dark (x>w-10): 43   → 两侧都贴边 = 被裁
```

---

## 3. 修复：锁死 pt → null 设备量 → 反推画布

```r
suppressMessages({library(pheatmap); library(grid); library(gtable)})

CW  <- 24.66                 # 格子宽 pt = 0.87 cm   (cm × 28.35 = pt)
CH  <- 9.0                   # 格子高 pt = 0.32 cm
PAD <- c(1.2, 3.5, 2.0, 4.5) # 上/右/下/左 cm  ← 左右边距加大

build <- function(){
  p <- pheatmap(m, color = cols, cluster_rows = FALSE, cluster_cols = FALSE,
                display_numbers = FALSE, fontsize_row = 8, fontsize_col = 9,
                angle_col = 45, border_color = NA, legend = FALSE, main = "",
                silent = TRUE,                 # silent=TRUE 才返回 gtable
                cellwidth = CW, cellheight = CH)
  gtable_add_padding(p$gtable, unit(PAD, "cm"))
}

# ⚠️ 量尺寸必须包在 null 设备里（见 §4）
pdf(NULL)
gt <- build()
tot_w <- convertWidth(sum(gt$widths),   "cm", valueOnly = TRUE)
tot_h <- convertHeight(sum(gt$heights), "cm", valueOnly = TRUE)
dev.off()

Wi <- (tot_w + 0.20)/2.54    # +0.2 cm 缓冲
Hi <- (tot_h + 0.20)/2.54

draw <- function(){ grid.newpage(); grid.draw(build()); make_legend() }
png("figs/x.png", width = Wi, height = Hi, units = "in", res = 300, bg = "white"); draw(); dev.off()
pdf("figs/x.pdf", width = Wi, height = Hi, bg = "white"); draw(); dev.off()
svg("figs/x.svg", width = Wi, height = Hi, bg = "white"); draw(); dev.off()
```

**为什么可行**：`cellwidth/cellheight` 一旦显式给出，gtable 所有宽度/高度都是**固定单位**，
`convertWidth(sum(gt$widths))` 量到的就是真实物理尺寸 → 反推出的画布必然容得下全部内容 → 零裁切。

---

## 4. ⚠️ 空白 PNG 的真凶：测量留下的隐式设备

```
症状：PNG 8818 B（≈ PDF 大小），PIL extrema = (255, 255) 全白；同一脚本的 SVG 321 KB 内容完整。
```

- **原因**：在无设备上下文里执行 `build()` / `convertWidth()` 会隐式打开一个设备；随后 `png()` 开的新设备拿不到绘制指令（图形落到隐式设备上）。
- **修复**：量尺寸整段包进 `pdf(NULL) … dev.off()`。
- **注意**：把导出放进**独立 Rscript 进程**并不能解决这个症状（本会话实测仍全白）——独立进程解决的是另一个问题（持久内核设备状态串扰）。两个坑要分别处理。

**空白判据（最快）**：
```python
Image.open(p).convert("L").getextrema()   # (255,255) = 全白坏图
```

---

## 5. PNG 是 `mode P`（调色板模式）——阈值化前必须 convert

`png()` 出来的图常是 `mode P`；直接 `np.array(im)` 得到索引而不是 RGB → 阈值/非白检测全错，甚至抛
`ValueError: zero-size array to reduction operation minimum`（因为没有任何像素满足条件）。

```python
im = Image.open(p).convert("RGB")     # ← 必做
a  = np.array(im); h, w, _ = a.shape
r, g, b = a[:,:,0].astype(int), a[:,:,1].astype(int), a[:,:,2].astype(int)
nw = (r < 248) | (g < 248) | (b < 248)

cols = np.where(nw.sum(axis=0) > 0)[0]; rows = np.where(nw.sum(axis=1) > 0)[0]
margins = (cols.min(), w - 1 - cols.max(), rows.min(), h - 1 - rows.max())  # 左/右/上/下 px
zero_clip = cols.min() > 0 and cols.max() < w-1 and rows.min() > 0 and rows.max() < h-1
```

v12b 实测（3576×2500 px）：`cols 479–3385 / rows 230–2457` → 边距 `左479 右190 上230 下42` → `zero_clip = True`。
（右下角自绘 legend 会伸到内容 bbox 的右下端，故"右边距"实测值小于 PAD 的 3.5 cm——这是正常的，判据只看"是否贴边"。）

---

## 6. 诊断阶梯（按顺序，别跳步）

1. `ls -la` 三格式文件大小 + `PIL .size/.mode/getextrema()` → 排除空白/坏图（只看 extrema 一行）。
2. **结构化量尺寸**：`pdf(NULL)` 内 `convertWidth(sum(gt$widths))` → 与画布英寸尺寸对照，**一次性判出有没有溢出**。
   ⚠️ 不要用"反复跑像素扫描"来替代这一步（本会话因重复像素分析触发了系统循环干预）。
3. 溢出 → 按 §3 反推画布重跑。
4. 只跑**一次** `scripts/verify_figure_no_clip.py` 确认零裁切，然后交付。

---

## 7. 终版参数（用户认可，可直接复用）

| 项 | 值 |
|---|---|
| `cellwidth` / `cellheight` | 24.66 pt / 9 pt（0.87 × 0.32 cm） |
| PAD（上/右/下/左） | 1.2 / 3.5 / 2.0 / 4.5 cm |
| 画布 | 11.92 × 8.33 in（3576 × 2500 px @300dpi） |
| 配色 | YlOrRd 5 档 `#FFF7EC → #FDD49E → #FC8D59 → #D7301F → #7F0000` |
| 值域 / 聚类 / 列名 | 0–10 / 均不聚类 / 45° |
| legend | 右下角横放 3.6 cm，刻度 0/5/10 |
| 内容 | 48 词条 × 15 亚群，全部展示不筛选 |
| 导出 | png@300dpi + pdf + svg（用户拿去 Illustrator 手工调） |
