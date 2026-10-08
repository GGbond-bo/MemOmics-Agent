# CNS/发表级图的「版式精修」——四类客观硬伤 + 多变体挑选协议

来源：2026-09-29 会话（人骨骼肌 DEG 全景图，183×152 mm CNS 规格，hero 圆矩阵 + 3 证据面板）。
用户第一轮反馈只有四个字「**我觉得不好看**」——本文件的全部内容都是**从图上量出来的**，
不是审美判断。核心教训：收到「不好看」时先量，不要先换配色。

---

## 0. 触发场景

- 用户说「不好看 / 不够惊艳 / 感觉不对」但没说具体改什么
- 用户说「多出几个，我自己挑选」
- 已有一版 CNS 图要精修（**同骨架**，不是换叙事）

---

## 1. 四类客观硬伤：判据 + 修法（都能量，不要凭感觉）

| # | 硬伤 | 实测判据 | 修法 |
|---|---|---|---|
| 1 | **图面写句子** | 3 处长句直接印在画布上：`circle area = FDR<0.05 fraction of tested genes`、`dashed ring = detection-rate (D) component reported`，以及一句**结论式标题** `Significance is decoupled from effect size` | 全部移入 figure legend / caption；标题只留中性描述：`Cell-level DEG landscape (RUV-MAST)` |
| 2 | **字号系统性偏小** | 全图 5.0–6.2 pt 一档到底。**OCR 读错就是直接证据**：`Old`→`PIO`、`OTUD1+(II)`→`OTUDPe(II)`、`LRP1B+(I)`→`LRP1B+()` | 轴标 ≥7 pt、面板标题 8 pt、panel 字母 10 pt、数值标注 5.8–6.4 pt |
| 3 | **圆/点远小于格子（留白）** | `RMAX=0.44` ⇒ 圆面积只占格子 60.8%；成图 **78.4% 像素是灰白底**（主色 `#e0e0e0` 占 78.3%） | `RMAX` 提到 0.47–0.49（0.5 = 圆恰好相切）；同时去掉格底纹 `Rectangle(fc="#FBFBFB")` |
| 4 | **头重脚轻** | hero 面板占 2/3 高但内容稀疏（50 个小圆撒在格子里），3 个证据面板挤在下 1/3，每个都小到看不清 | `height_ratios` 2.05 → 1.38；辅面板随之放大；图例改底部共享 |

### 硬伤 1 的判据细节

CNS 期刊图**不在画布上写结论、不写机制说明**——那些属于 caption/legend。
自查：把图上所有文字列出来，凡出现「A 导致 B」「与…脱钩」「说明…」这类**判断句**，一律删。
面积/圈环等编码的说明也删（caption 里一句话说清），画布上最多留**纯刻度标签 + 变量名**。

### 硬伤 3 的算法

圆面积正比 `frac` 时半径 `r = RMAX·√frac`。留白量 = `1 − π·RMAX²`（格子面积 1×1）：

| RMAX | 圆占格子面积 | 观感 |
|---|---|---|
| 0.44 | 60.8% | 空、散、没有重心（**旧版**） |
| 0.48 | 72.4% | 饱满 |
| 0.50 | 78.5% | 相切（最大值，再大就重叠） |

---

## 2. OCR 作为「字号可读性探针」（免费，比"我觉得小"可辩护）

`vision_describe` 的 OCR 段是本地管道，**读错字符 = 字号已到人眼临界**的直接证据：

```python
vision_describe(image_path=".../fig.png",
                question="列出所有 OCR 到的文字")
# 小字号表现：'Old'->'PIO'  'OTUD1+(II)'->'OTUDPe(II)'  'LRP1B+(I)'->'LRP1B+()'
```

工作流：**改字号前 OCR 一次留证 → 改完再 OCR 一次，标签能读全即达标**。
本会话修完字号后 `RP_high(I)`/`RP_high(II)`/`OTUD1+(II)`/`Specialized MF` 全部读对。

> ⚠️ OCR 读不准也可能来自旋转标签/抗锯齿，不要只看一条判死；**多条同时读错**才说明字号是主因。

---

## 3. 多变体生产配方（一个脚本出全部变体）

用户要「多出几个自己挑」时，**不要单版反复微调**——一次出 3–4 版，差异是**可命名的版式策略**。

### 3.1 面板函数参数化

把每个 panel 写成独立函数，样式全部走参数，不在函数体里写死：

```python
def panel_A(ax, cells, pal, rmax=0.48, ring=True, group_lines=False,
            fs_tick=7.0, title=None):
    ...

def build(variant, df, cells):
    pal = PALETTE[variant]                 # 每变体一套 dict
    if variant == "clean_grid":
        gs = GridSpec(2, 1, height_ratios=[1.90, 1.0], ...)
        panel_A(axA, cells, pal, rmax=0.49, ring=False, title="<中性标题>")
    elif variant == "rebalanced":
        gs = GridSpec(2, 1, height_ratios=[1.38, 1.0], ...)
        ...
```

### 3.2 源数据先缓存（关键效率点）

多个变体共用同一张大表 ⇒ **读一次、pickle 缓存**，别让每个变体重读源文件：

```python
CACHE = ".../results/deg_allraw_cache.pkl"
if os.path.exists(CACHE):
    df = pickle.load(open(CACHE, "rb"))
else:
    df = pd.concat([...])          # 本会话：5 个 18 MB xlsx → 340,971 行
    pickle.dump(df, open(CACHE, "wb"))
```

本会话实测：5 个 18 MB xlsx 读一次后，4 个变体各渲染**秒级**。

### 3.3 导出分层

| 阶段 | 导出 | 理由 |
|---|---|---|
| 挑选用 | **PNG 300 dpi + PDF** | 够看版式；文件小 |
| 用户选定后 | SVG（可编辑文字）+ TIFF 600 dpi | 投稿定稿 |

⛔ 不要一次造 4 份 TIFF——600 dpi 的 183×152 mm TIFF 约 **70 MB/张**，4 张 280 MB 全是浪费。

---

## 4. 本会话四变体规格表（可直接复用）

| 变体 | 策略 | 关键参数 |
|---|---|---|
| `clean_grid` | 极简画布 | `RMAX=0.49`、`ring=False`、格底纹去掉（纯白）、`height_ratios=[1.90,1.0]`、183×150 mm |
| `rebalanced` | 比例重排 | `RMAX=0.47`、`height_ratios=[1.38,1.0]`、辅面板 `fs=7.2`、图例移到底部共享（`fig.legend(ncol=5)`）、183×162 mm |
| `grouped` | 语义分区 | `RMAX=0.48`、`group_lines=True`（类别间虚线分隔 + 组标签）、183×152 mm |
| `mono_accent` | 低饱和高级调 | 莫兰迪红蓝（`#5B7C99` 下调 / `#9E6B5E` 上调）、178×140 mm 紧凑框、去掉冗余注记 |

配色 `PALETTE` 按变体给 dict，`cmap_ud(pal)` 动态建离散色图：

```python
PALETTE = {
  "clean_grid":  dict(down="#2166AC", up="#B2182B", grid="#FFFFFF", edge="#FFFFFF", ring="#2B2B2B", accent="#B2182B"),
  "mono_accent": dict(down="#5B7C99", up="#9E6B5E", grid="#FCFCFC", edge="#FFFFFF", ring="#4A4A4A", accent="#9E6B5E"),
}
```

> ⚠️ 低饱和配色仍需保留「暖 = 上调 / 冷 = 下调」语义，不能为了好看把上调画成冷色。

---

## 5. 🔴 matplotlib 倒置轴：轴内文字越界会掉到刻度标签行上

**真 bug 实例（本会话）**：组标签写在 `ax.text(x, nrow - 0.13, ...)`，
但该轴 `ax.invert_yaxis()` 且 `set_ylim(-0.55, nrow - 0.20)`：

```
y = nrow - 0.13 = 4.87  >  ylim 上界 4.80   ⇒ 超出可见范围
```

文字**被挤到轴外、正好压住 x 轴刻度标签**。OCR 读出 `Pure` / `types` 散落在亚群名那一行
（`Pure` @(562,856) 与 `Pure Type I` @(384,857) 同一 y）才发现——**不看 OCR 就会当成"标签渲染正常"发出去**。

**修法**：用组标签时预留头部空间，文字放**负 y**：

```python
# 预留头部（倒置轴里"更靠上" = 更小的 y）
ax.set_ylim(-0.80 if group_lines else -0.55, nrow - 0.20)
ax.invert_yaxis()
...
# 组标签放顶部，不是 nrow-0.13
ax.text((start + stop - 1) / 2.0, -0.62, lab,
        fontsize=6.9, ha="center", va="center", color="#5A5A5A")
```

**通用判据**：倒置轴里任何贴着矩阵外缘的标注，y 必须落在 `ylim` 内**且符号与直觉相反**；
写完先心算一遍 `标y ∈ [ylim_lo, ylim_hi]`。

---

## 6. 收尾：多产物用**一次批量探针**，不要逐张分轮验证

4 个变体在**一个工具调用**里出体检表（尺寸 / 非白占比 / 唯一色数 / 分块墨量）：

```python
from PIL import Image; import numpy as np, os
for f in sorted(os.listdir(d)):
    if not f.endswith(".png"): continue
    a = np.asarray(Image.open(os.path.join(d, f)).convert("RGB")).astype(np.int16)
    nonwhite = float(np.mean(~np.all(a > 245, axis=2))) * 100
    ncol = len(np.unique(a.reshape(-1, 3), axis=0))
    H, W, _ = a.shape
    tiles = [float(np.mean(~np.all(a[i*H//6:(i+1)*H//6, j*W//4:(j+1)*W//4] > 245, axis=2)))*100
             for i in range(6) for j in range(4)]
    print(f"{f:<48s} nonwhite={nonwhite:5.2f}% colors={ncol:6d} blank={sum(t<0.15 for t in tiles)}/24")
```

本会话 4 张全部 PASS（非白 16.4–17.4%、色数 2700–3522、空白 tile 0/24）。

⛔ **不要**每张各跑一次 `vision_describe` 跨轮核对——本会话因逐张反复核对被系统循环检测强制中断。
OCR 只在「版式被改动的那一个变体」上做一次复核即可（用于验证定向修复是否生效）。

---

## 7. 明确不要做的

| 反例 | 为什么 |
|---|---|
| 收到「不好看」先换配色 | 本会话四类硬伤没有一类是配色问题；换色后用户还会说不好看 |
| 把结论句留在标题里 | CNS 图表标题是描述性的，判断留给正文 |
| 给用户一版让他继续提意见 | 用户明确要「多出几个自己挑」——一次给够可选项 |
| 一次导出全部变体的 TIFF/SVG | 280 MB 浪费；定稿只出选定的一版 |
| 变体之间只差配色 | 那叫同一版；变体差异必须是**版式策略**（留白/比例/分区/紧凑度） |