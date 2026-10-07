# R base graphics：热图外侧装饰（分类色块 / 竖排轴名 / 标题）与几何自检

适用：期刊级 base-graphics 矩阵热图（零第三方包），需要把分类色块、竖排轴名、长标题放到
绘图区**之外**，并保证「标题不与顶部标签重叠、标签不画出画布」。
实测脚本：`results/memomics-2274ab75/scripts/fig_A3_CNS_v4.R`（17 程序 × 10 亚群转置热图，
版式自左向右 = 竖排轴名 | 分类色块 | 程序名 | 热图；顶部只剩色标）。

## 1 核心公式：英寸 ↔ 数据单位

`plot.window(xlim=c(0,NCOL), ylim=c(0,TOP))` 之后，x 方向 1 数据单位 = `CELL` 英寸，
绘图区左边界 = `MAI[2]` 英寸。把物理位置换算成数据坐标：

```r
x_data = (target_in - MAI[2]) / CELL
y_data = (target_in_from_bottom - MAI[1]) / CELL
```

⚠️ **不要把 `(MAI[2] + NCOL*CELL/2)/CELL` 当"图幅中心"** —— 那是「热图区中心的物理位置」再除以
CELL，量纲混用，算出 10.29 > xlim 上限 10；`mtext`/`text` 会把标题画到画布右边界之外，
**右半截被裁**（OCR 只读到标题前半句、缺 `(row z-score, all samples)` 就是这个症状）。
图幅中心（含左栏装饰，整幅图居中）应为：

```r
at = (W/2 - MAI[2]) / CELL      # W = NCOL*CELL + MAI[2] + MAI[4]
```

## 2 外侧装饰：xpd=NA + 负数据坐标

`par(xpd=NA)` 后用负 x 在左边距里画元素，所有元素仍在同一坐标系，**不要用 par(fig) 重置坐标系**
（重置正是历史上色块被裁的根因）：

```r
LB0 <- -3.40; LB1 <- -4.11          # 色块右/左边界（先按英寸算好再换算）
LNX <- -4.30                        # 竖排轴名中心
rect(LB0, rowy[g], LB1, rowy[g]+1, col=ax$color, border=NA)
text(LNX, mean(span[[ax$name]]), ax$name, srt=90, adj=c(0.5,0.5), col=ax$color)
text(-0.10, rowy[g]+0.5, DISP[g], adj=c(1,0.5))   # 程序名右对齐紧贴热图
```

左栏总宽（英寸）= 轴名半高 + 间隙 + 色块宽 + 间隙 + 最长程序名 + `0.10*CELL`；
据此反解 `MAI[2]`（本例 1.35 in）。**改动任一元素必须同步改 MAI[2]**，否则元素被挤出画布。

## 3 标题与顶部色标不重叠：分居两层（用户明确要求"标题和 label 不要重叠"）

- 绘图区**内**顶部预留色标带：`TOP <- YMAX + 0.95`；色标条 `y0=YMAX+0.60, y1=YMAX+0.88`，
  刻度标签 `text(..., y0-0.08, adj=c(0.5,1))` —— 6pt 文字向下占约 0.37 数据单位，务必留够
  （留不够时刻度数字会压住第一行热图）。
- 标题画在绘图区**外**的上边距：`mtext(TITLE, side=3, line=0.60, at=..., cex=7.5/9)`；
  行高按 `ps*1.2/72` 英寸估算，`MAI[3]` 至少 0.55 in。

这样标题与色标/刻度标签在物理上不可能重叠（实测标题 y=109 px vs 色标标签 y=171 px）。

## 4 出图前的文字宽度自检（必做）

用**目标字体**在真实设备上量，不要用 `pdf(NULL)`：

```r
tf <- tempfile(fileext = ".png")
png(tf, width=W, height=H, units="in", res=72, type="cairo", family=FAM)
par(ps = 9)
tw <- strwidth(TITLE, units="inches", cex=7.5/9)
lw <- max(strwidth(DISP[PROGS], units="inches", cex=6.0/9))
sh <- max(strheight(axis_names, units="inches", cex=6.3/9))   # 竖排文字量 strheight
dev.off(); unlink(tf)
stopifnot(tw <= W - 0.10,
          lw <= (-0.10 - LB0) * CELL,          # 程序名可用宽度
          sh/2 <= MAI[2] + LNX*CELL - 0.02)    # 轴名中心到画布左边界
```

坑：
- `pdf(NULL)` 是 PostScript 设备，`family="Arial"` 会警告「PostScript字体数据库里找不到'Arial'」
  并回退到未知字宽度 → 量出来的数不可信；改用 cairo 临时 png。
- 自检块要放在**出图循环之前**，否则 `stopifnot` 失败时坏图已经落盘。
- 可用宽度别写反符号：是 `(-0.10 - LB0)`，不是 `(LB0 + 0.10)`。
- 竖排（`srt=90`）文字占位方向变了，量 `strheight` 而非 `strwidth`。

## 5 纵向行布局（R 的 y 轴向上增长）

自上而下的轴顺序必须从 `YMAX` 向下递减赋值；循环里只在"非最后一个轴"之后减 `GAPY`，
否则总高多算一个间隙。保留 `stopifnot(abs(yc) < 1e-9)` 这条断言，它会抓住这算术错。

## 6 迭代改图纪律（用户偏好，实测有效）

- **每次改图新建 vN 脚本**（如 `fig_A3_CNS_v4.R`），旧版连同 4 种格式一起 copy 到
  `archive_superseded/`（带版本后缀），不覆盖、不删除上一版。
- **用户说"其他不变"时必须给像素级证据**，不能只说"没动"：逐列色值多重集一致 = 纯置换
  （本次 18/18 列一致、逐行值不变仅位置变动）；删除元素用颜色命中数反向验证
  （左侧色条 5115/5104/2542 px → 0/0/0 px）。
- **交付前 `vision_describe` 核验成图 PNG**（行/列顺序、是否在画布内、新增或删除元素是否生效）
  —— OCR 是发现「标题被裁、标签重叠、元素没删干净」的唯一手段，光读脚本看不出来。
- **一次出图 + 一次核验即可**：命令成功、产物非空之后不要再反复重跑同一张图做确认
  （重复验证会触发循环干预）；要再改就直接改脚本重出。
- 版式元素（分类色块在左/右侧、标签位置、是否画某条注释条）按用户**逐图指定**执行，
  不套用上一张图的默认；汇报用「你要的 → 我的落地 → 核验证据」三列表。