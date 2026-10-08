# matplotlib 热图脚本 → R base graphics 忠实复刻（实测清单）

> 场景：用户已有 Python/matplotlib 出图脚本（手工 Rectangle 热图、自定义 TwoSlopeNorm 色标、subplots_adjust 手工版式），要求给出 R 版且**颜色/版式必须对得上**。
> 结论：**用 base graphics 手工 `rect()` 1:1 复刻**比 ComplexHeatmap/pheatmap 更可控（后者的 cellwidth/cellheight/间距是另一套几何系统，改起来反而更难对齐）。零第三方依赖，`png/pdf/svg/tiff` 全支持。
> 实测标本：`fig_split_v10.py` → `fig_split_v10.R`（18+4 打分 × 3 版式，6 图 × 4 格式 @300dpi）。

## 1. 三个必须做对的换算

| 项目 | matplotlib | R base graphics | 要点 |
|------|-----------|-----------------|------|
| 边距 | `subplots_adjust(left,right,bottom,top)` 图幅分数 | `par(mai=c(bottom,left,top,right))` **英寸** | `mai[1]=bottom*H`, `mai[2]=left*W`, `mai[3]=(1-top)*H`, `mai[4]=(1-right)*W`；顺序别写错 |
| 字号 | `fontsize=pt` | `cex = pt / par("ps")` | 设 `par(ps=9)` 后 `cex=7/9` 即 7pt |
| 子图/色标区域 | `fig.add_axes([x0,y0,w,h])` 图幅分数 | `par(fig=c(x0, x0+w, y0, y0+h), new=TRUE)` | R 的 `fig` 是 `c(x1,x2,y1,y2)`，y 从下往上，与 add_axes 语义一致 |

**文字出界**：matplotlib 的 text 默认 `clip_on=False`；R 必须 `par(xpd=NA)`，否则标题/45°标签被裁掉。
**旋转+对齐**：`ha='right' va='top' srt=45` → `text(x, y, s, srt=45, adj=c(1,1))`（adj 顺序 = x,y）。

## 2. 两个致命坑（本次实际踩中）

### 坑 1：`par(xaxs/yaxs)` 默认 `"r"` 会把坐标外扩 4%
matplotlib 的 `set_xlim/set_ylim` 是**精确**的；R 的 `plot.window()` 受 `xaxs/yaxs` 影响，默认 `"r"` 会在两端各加 4% 空白 → 实测色块列间距 138px 掉到 128px（压缩 7%），整版错位。

```r
par(mai = mai, ps = 9, xpd = NA, xaxs = "i", yaxs = "i")   # xaxs/yaxs='i' = internal，精确映射
plot.new(); plot.window(xlim = c(...), ylim = c(...))
```
**验证方法**：数色块列边界像素位置与 pitch，必须与 matplotlib 版逐项相同。

### 坑 2：色表索引公式差一位 → 整体偏一档（±1~2/255）
matplotlib 连续 colormap 渲染路径是 `LUT[int(b*N)]`（N=256，`b∈[0,1]`）；R 数组 1-based，要写成：

```r
n <- ifelse(v <= vc, 0.5*(v-vmin)/(vc-vmin), 0.5 + 0.5*(v-vc)/(vmax-vc))  # TwoSlopeNorm
n <- pmin(pmax(n, 0), 1)
PAL256[pmin(floor(n * 256), 255) + 1]        # ✅ 不要写 floor(n*255)+1（会整体偏一档）
```

## 3. 生成与 matplotlib 完全一致的 256 级色表
`colorRampPalette()` 的量化与 matplotlib 的 `LinearSegmentedColormap(N=256)` 不完全一致；要逐像素对齐就自己做锚点线性插值（R 与 numpy 的 round 都是 round-half-to-even）：

```r
RDBU_R <- c("#053061","#2166AC","#4393C3","#92C5DE","#D1E5F0","#F7F7F7",
            "#FDDBC7","#F4A582","#D6604D","#B2182B","#67001F")   # RdBu_r = RdBu 反转
ANCHOR <- t(col2rgb(RDBU_R)); APOS <- seq(0, 1, length.out = nrow(ANCHOR))
LUT256 <- do.call(rbind, lapply(seq(0, 1, length.out = 256), function(t) {
  j <- findInterval(t, APOS, rightmost.closed = TRUE); j <- min(max(j, 1), length(APOS) - 1)
  f <- (t - APOS[j]) / (APOS[j+1] - APOS[j]); round(ANCHOR[j,]*(1-f) + ANCHOR[j+1,]*f) }))
PAL256 <- rgb(LUT256[,1], LUT256[,2], LUT256[,3], maxColorValue = 255)
```
TwoSlopeNorm 在 `vcenter` 恰为中点时 = 线性归一化；`vmin=-2,vcenter=0,vmax=2` 直接 `(v+2)/4` 等价。

## 4. 数据口径对齐（最容易静默出错的地方）
- **行内 z-score**：numpy `std(ddof=0)` → R `sqrt(mean((v-mean(v))^2))`（不是 `sd()`，`sd()` 是 n−1）。
- **展平顺序**：Python `[(t,s) for t in TYPES for s in SUBS]` 是「子类最快」；R 的 `as.vector()` 是**列优先（第一维最快）**，所以矩阵要建成 `matrix(nrow=length(SUBS), ncol=length(TYPES))` 再 `as.vector()`，否则单元格数值错位（z 值集合相同但位置错，图看起来"正常"其实全错）。
- **分组均值**：pandas `groupby().mean()` → R `aggregate(df[, cols, drop=FALSE], by=list(...), FUN=mean)`；`tapply()` 可对应 `pivot_table`。
- **大 CSV 只读所需列**（400MB/50 万行级）：`read.csv(colClasses=<NULL for unwanted>)`，比 `fread` 更少依赖，也避免 rail 的包探测问题。

## 5. 交付前必须做的客观核验（别只肉眼看图）
1. **矩阵数值**：R 侧把矩阵导出 CSV，Python 侧同口径重算，逐格比 `max|Δ|`（应 ≤1e-13）。
2. **取色**：抽若干数值（如 −2…2）经 norm 后比 matplotlib 与 R 的 RGB，单通道差应为 **0**。
3. **几何**：检测色块列边界像素与 pitch，逐项比对（本例 FigA1 914→4306 / pitch 49.0px；FigA3 738→2252 / pitch 138.0px）。
4. **成图尺寸**：`png(width=W, height=H, units="in", res=300)` → 像素数必须与 matplotlib `figsize*dpi` 完全一致。
5. 残余差异只应来自**字体族**（matplotlib DejaVu Sans vs R 默认 Arial）→ 文字区域像素差；非文字区域 mean|ΔRGB| ≈ 0–2。若要求严格像素等价，需在 R 侧指定同一字体族（见 §6）或在交付说明中书面声明替代字体。

## 6. 字体归一（可选项）
matplotlib 自带 DejaVu 系列：`<venv>/Lib/site-packages/matplotlib/mpl-data/fonts/ttf/DejaVuSans.ttf`。
Windows 未安装 DejaVu 时，cairo 设备用 `family="DejaVu Sans"` 会静默回退到 Arial。要真正归一需先安装该字体（或 `systemfonts::register_font()` + `showtext`，但会引入依赖）——若用户的优先级是零依赖，就在交付说明里明确"字体族差异，版式/配色/几何一致"。

## 7. 输出与目录纪律
- 用户偏好：**300dpi + 必须附 SVG**（本条为其长期要求）；PDF/SVG 为矢量、TIFF/PNG 为位图，四格式齐备最稳。
- **不要与原脚本写同名同目录**：R 版请落到 `figures/R_version/` 之类的独立目录，否则会静默覆盖已交付的 Python 版产物（本次踩过：需重跑 Python 脚本恢复原图）。
- 输出目录里补 `figures_manifest_QA.csv`（逐文件 exists+bytes）+ `QA_verification.txt`（核验数字），既方便交付也满足 rail_review(post) 的"产出登记"检查。
