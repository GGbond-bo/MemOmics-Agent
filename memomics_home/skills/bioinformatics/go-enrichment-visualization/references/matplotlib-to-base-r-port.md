# matplotlib → base R 1:1 复刻（色块矩阵 / 热图类脚本）

**场景**：用户手上有一个跑通的 matplotlib 出图脚本（`ax.add_patch(Rectangle(...))` 拼格子 +
`TwoSlopeNorm` + `plt.cm.RdBu_r` + 手动 `subplots_adjust` + `fig.add_axes` 色标），
说「**能不能把这个脚本变成 R**」，并且明确要求「**颜色这些都要对的上**」。

**目标不是"意思差不多"，而是逐格颜色一致、几何一致。** 这是一类可复用的移植工作，
不是一次性改写——下面全部数值来自 2026-09-15 实测（`fig_split_v10.py` → `fig_split_v10.R`，
6 张图 × 4 格式，363 行 R）。

---

## 0. 先确认"R 版是否已经存在"再开工

**动手写之前先 `search_files(target='files', pattern='<脚本名>.R')` 扫会话 `scripts/` 目录。**
本轮实测：用户问"能不能变成 R"时，`fig_split_v10.R` 已经躺在 `scripts/` 里（上一轮已写好并跑通），
产物在 `figures/R_version/`（6 图 × 4 格式 = 24 文件 + `figures_manifest_QA.csv` + `QA_verification.txt`）。
差点重复劳动。判据：`ls -la scripts/` 看有无同名 `.R`、`ls -la figures/*R_version*/` 看产出是否齐全
⇒ 齐全就直接汇报，不重写。

## 1. 技术选型：base graphics，**不要** ggplot2

| | base graphics（`rect`/`text`/`axis`） | ggplot2 |
|---|---|---|
| 与 matplotlib 的对应 | `Rectangle((x,y),w,h)` → `rect(x,y,x+w,y+h)` **逐参数 1:1** | 需重构成长表 + `geom_tile`，语义变了 |
| 几何控制 | `plot.window(xlim, ylim)` + `par(mai=)` 精确复刻 | 面板宽度/格子尺寸由布局算法决定，难锁 |
| 组色条 / 竖排组名 / 非等距行间隙 | 直接 `rect` + `text(srt=90)` | 都要绕（`coord_fixed`、伪造 y 数值） |
| 依赖 | 零第三方包 | 至少 ggplot2 |

**结论**：原作者用"低级图元拼格子"时，base graphics 是唯一能保证 1:1 的路子。
要做的是读懂 matplotlib 的坐标系并翻译，不是把图"重新设计"一遍。

## 2. 🔴 必踩坑（缺一个颜色/几何就对不上）

### 2.1 `par(xaxs="i", yaxs="i")` —— 最高优先级，没有它色块被压缩 ~7%

R 默认 `xaxs="r"` 给坐标范围**外扩 4%**（matplotlib 的 axes 不会），
于是 1 数据单位的色块在画布上比预期窄 → 整个矩阵被压缩约 7%，与 Python 版**列边界逐步错位**。
所有 `plot.window()` 前一律 `par(..., xaxs="i", yaxs="i")`。

### 2.2 边距换算：`subplots_adjust` → `par(mai)`（英寸，不是行数）

matplotlib `subplots_adjust(left, right, bottom, top)` 是**图宽/图高的比例**；
R 的 `mai` 是**英寸**，`mar` 才是行数。换算：

```r
mai <- c(bottom * H, left * W, (1 - top) * H, (1 - right) * W)   # c(下, 左, 上, 右)
# 实测：subplots_adjust(0.16, 0.88, 0.13, 0.92) + 16.5 × 8.4 in
#   → mai = c(0.13*8.4, 0.16*16.5, 0.08*8.4, 0.12*16.5)
#        = c(1.092,    2.640,    0.672,    1.980)  英寸
```

⚠️ `par(mai=)` 与 `par(mar=)` 会互相覆盖——`mai` 里同时写 `mar` 时后写的生效，别混用。
⚠️ `par(fig=..., new=TRUE)` 叠加色标后 `mai` 按新 fig 区域重算 → 色标那段必须显式 `mai = rep(0,4)`。

### 2.3 字号：`cex = pt / 9`，配 `par(ps = 9)`

matplotlib 字号是**磅（pt）**；R 的 `cex` 是**相对 `ps` 的倍数**。统一 `par(ps = 9)` 后
每个字号可一一换算、100% 对齐原脚本：`fontsize=8.5` → `cex = 8.5/9`；`9.5` → `9.5/9`；`11.5` → `11.5/9`。
没有这一步，所有文字大小都是随手拍的，验收时"字号不一样"必然被抓。

### 2.4 调色板：手写 11 锚点 + 自建 256 LUT（**别依赖 RColorBrewer**）

matplotlib 的 `RdBu_r` = ColorBrewer `RdBu` **反转**，且 matplotlib 内部把这 11 个锚点
**等距**放在 0…1 上线性插值 → R 侧照抄即可，无需装包：

```r
RDBU_R <- c("#053061","#2166AC","#4393C3","#92C5DE","#D1E5F0","#F7F7F7",
            "#FDDBC7","#F4A582","#D6604D","#B2182B","#67001F")   # 蓝→白→红
ANCHOR <- t(col2rgb(RDBU_R)); APOS <- seq(0, 1, length.out = 11)
LUT256 <- do.call(rbind, lapply(seq(0, 1, length.out = 256), function(t) {
  j <- min(max(findInterval(t, APOS, rightmost.closed = TRUE), 1), 10)
  f <- (t - APOS[j]) / (APOS[j + 1] - APOS[j])
  round(ANCHOR[j, ] * (1 - f) + ANCHOR[j + 1, ] * f)      # 四舍五入同 numpy，避免 ±1 差
}))
PAL256 <- rgb(LUT256[,1], LUT256[,2], LUT256[,3], maxColorValue = 255)
```

`RColorBrewer::brewer.pal(11,"RdBu")` 只有 11 色，`colorRampPalette` 虽近似，
但拿不到 matplotlib 那套 256 级 LUT 的取整行为——要"逐格逐值对得上"就得自建 LUT。

### 2.5 🔴 取色索引：`LUT[floor(b*256)]`，R 数组 1-based 要 **+1**

matplotlib 是 `LUT[int(b * N)]`（N=256，`int()` 截断）。R 里照抄必须补 1-based 偏移：

```r
n <- ifelse(v <= vc, 0.5*(v-vmin)/(vc-vmin), 0.5 + 0.5*(v-vc)/(vmax-vc))
PAL256[pmin(floor(pmin(pmax(n,0),1) * 256), 255) + 1]
```

不 `+1` 会整体偏一档（±1~2/255，肉眼勉强看不出，但"颜色对得上"的验收会挂）。
`TwoSlopeNorm` 在 **vcenter 对称时就是线性**（−2/0/2、−3/0/3 都对称），
所以 R 侧按上下限线性映射即可，不必真写分段函数。

### 2.6 色标：用 `par(fig=..., new=TRUE)` 叠加，不要改主图坐标系

matplotlib 的 `fig.add_axes([0.905, 0.14, 0.018, 0.60])` 是**图归一化坐标**；
R 对应 `par(fig = c(x0, x1, y0, y1), new = TRUE, mai = rep(0,4))` + 独立 `plot.new()`。
色标用 257 个 `rect` 拼渐变（取 `cmap_fn(中点值)` 上色），`axis(4, ...)` 摆右侧刻度，
`text(..., srt = 90)` 写竖排 label。**主图 `par(mai=)` 不受影响**——这是 base R 里
唯一能把色标放"画布级"位置、又不动主图几何的写法。

## 3. 跨语言模板陷阱（把 .py 习惯带进 .R 会直接崩）

| 陷阱 | 后果 | 对策 |
|---|---|---|
| 头部写 Python 三引号 `"""..."""` docstring | `source()` **解析期**报 `unexpected string constant`，一行不跑 | .R 头部一律 `#` 行注释 |
| `.libPaths()` 排在 `library()` 之后 | 先按默认库加载 → 包不存在 | `.libPaths()` 必须是**第一条**语句 |
| R 字符串里写 `"\."` 正则转义 | `unrecognized escape`，解析期崩 | 用 `"[.]arrow$"` 字符类 / `fixed=TRUE` |
| 沿用 `&&` 标量逻辑 | rail_review 的 `&&` 启发式会误判成"shell 多步串联" | 改 `&`（标量等价），见 `platform-execution-pitfalls` |
| 复用 Python 的 `if val is None` | R 里是 `is.null` / `is.na` | 格子里判空用 `is.na(val)`（矩阵 NA），不是 `is.null` |

## 4. 输出：用户偏好 **300dpi + SVG**，且**独立目录**别覆盖 Python 版

```r
save_fig <- function(base, W, H, draw_fn) {
  open_dev <- list(
    png  = function(f) png(f, width=W, height=H, units="in", res=300, bg="white", type="cairo"),
    pdf  = function(f) pdf(f, width=W, height=H, bg="white"),
    svg  = function(f) svg(f, width=W, height=H, bg="white"),
    tiff = function(f) tiff(f, width=W, height=H, units="in", res=300, bg="white",
                            compression="lzw", type="cairo"))
  for (ext in names(open_dev)) { f <- file.path(OUT, paste0(base,".",ext))
    open_dev[[ext]](f); draw_fn(); dev.off() }
}
```

- `OUT` 指到 `.../figures/R_version/`（**新目录**）——R 版与 Python 版并存供比对，不互相覆盖。

### 4.1 🔴 输出目录隔离不是"最佳实践"，是实测踩过的坑（2026-09-15）

首版 R 脚本沿用了 Python 版的 `OUT` 常量 → 跑完后 **Python 定稿图被同名 R 图覆盖**（`figures/Fig*_v10.*` 全被重写，字体从 DejaVu 变 Arial），只能**重跑 Python 脚本恢复 + 手工清掉误留的 `.tiff`**。代价 = 一次无谓的恢复跑 + 用户定稿被动过。**这不是假想风险，是已经发生过一次的事故。**

→ **跑之前先机械化核对两边输出目录，别靠"我记得改了"**：
```bash
grep -nE '^(OUT|OUT_DIR|OUTDIR)' scripts/fig_xxx.py scripts/fig_xxx.R   # 两边常量并排看
```
判据：两个 `OUT` **字符串不相同**才允许跑；相同 → 先改 R 版为 `<原目录>_R/` 或 `R_version/` 再跑。（本类脚本常把 `OUT` 定义在文件头部，一条 grep 即可。）
→ 恢复路径（万一已覆盖）：重跑原 Python 脚本重建定稿图，然后清掉原目录里 R 版多出来的格式（Python 版通常不出 `.tiff`，多出来的必是 R 版残留）。
→ 与 §0「先查 R 版是否已存在」配对使用：**先查有无（省一次重写）→ 再查 OUT 是否撞车（省一次覆盖）**，两步都在开工前、都只要一条命令。
- 用户要求"出图默认 300dpi 并附 SVG"：**png/tiff 必须 `res=300` + `units="in"`；pdf/svg 是矢量，给英寸尺寸即可。**
- `png(type="cairo")` 为跨平台字体/透明处理稳定；Windows 上不写 cairo 有时字体回退不同。

## 5. 交付前必做两道验证（"颜色对得上"要靠证据，不能靠肉眼）

### 5.1 矩阵口径：两边 dump 出来逐格比

Python 侧与 R 侧都把最终绘图矩阵写成 CSV（R 侧用脚本尾部 `DUMP_DIR` 开关，本例 `Rcheck_Z6.csv` 等），
再逐格求 `max|Δ|`。实测：`Z6 = 1.0e-14`、`ZS = 1.4e-14`、`D = 5.1e-15`、`Q = 5.6e-16`
（全在双精度噪声量级 ⇒ 聚合 / z-score / Cohen's d 的**口径完全一致**，差异只可能来自绘图层）。

⚠️ R 的 `aggregate()` 返回顺序与 pandas `groupby().reindex()` **不保证一致**——必须显式
`match()` 到目标顺序，否则是"对的数字配错的格子"，比颜色偏一档严重得多。

### 5.2 像素层：颜色直方图 + 色块列边界

- **主要颜色重合度**：取两版 PNG 各自最高频 RGB，实测 `FigA1 240/240`、`FigA2 159/159`、`FigA3 113/115` 完全重合。
- **几何**：测同一行色块的**列边界 x 坐标**与 pitch，实测 `FigA1 914→4306 pitch 49.0px`、`FigA3 738→2252 pitch 138.0px` 逐项相同。
- **抽样取色**：抽 13 个值比对 matplotlib 与 R 的单通道最大差 = **0**。
- **可接受差异**：字体族不同（matplotlib DejaVu Sans vs R 系统 Arial）→ 只有文字区域有像素差，
  全图 `mean|ΔRGB| ≈ 4–5`，**色块区域 ≈ 0–2**。这个量级才叫"对得上"。

把这四条写进 `QA_verification.txt` 与交付说明——**用户说"颜色要对得上"时，交付物必须自带可核对证据**。

## 6. 完整实测模板

`E:/MemOmics-Agent/results/memomics-2274ab75/scripts/fig_split_v10.R`（363 行，6 图 × 4 格式）
与 Python 原版 `fig_split_v10.py`（300 行）逐项对应，是本类任务的完整可抄模板：
§2.2 边距 → `maiA`/`maiS`/`maiB` 三组常量；§2.6 色标 → `draw_cbar()`；
§2.4/2.5 取色 → `LUT256` + `cmap_fn()`；§3 陷阱 → 头部 `#` 注释 + 零第三方依赖；
§5 验证 → 尾部 `DUMP_DIR` + `figures_manifest_QA.csv` + `QA_verification.txt`。

另一条可复用的兄弟教训见 `references/pheatmap-margin-only-adjustment.md`：
**改边距时本体绝不能联动变宽**——pheatmap 的 `cellwidth/cellheight` 单位是磅（pt）不是 cm，
不显式传值则矩阵宽度随画布 npc 缩放，几何不可控。两处的共同根因是同一个：
**R 的画图设备里"比例"与"绝对尺寸"是两套口径，跨语言移植/调边距时必须换算清楚。**
