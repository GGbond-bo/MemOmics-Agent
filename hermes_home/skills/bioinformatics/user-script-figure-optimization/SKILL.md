---
name: user-script-figure-optimization
description: >-
  优化【用户已经能跑的绘图脚本】——以用户脚本为唯一基线做最小改动，按期刊标准
  （Nature/CNS/投稿级）做规范增量，不重写用户代码。覆盖：先谈方向再动手的确认协议、
  「Nature 级 ≠ 把图缩小」的绝对尺寸/画布联动原则、自己引入 bug 的直接修复协议，
  以及 R/ggplot2/Seurat 的具体坑（facet 标题居中、metadata 赋值报错、pt.size/raster、
  矢量导出 + Source Data）。触发词：「按 nature 优化」「帮我改一下我的脚本」
  「检查一下这个脚本」「我的画图代码」「CNS 级出图」「改成发表级」「这个图怎么优化」
  「Seurat DimPlot 优化」「UMAP 出图改一下」。适用于任何「用户给脚本 + 要求提升图质量」
  的场景，R 与 Python 均适用，R/ggplot2 侧有专门小节。
  另覆盖**模板化复刻**：用户给「一张参考图 / 一段能跑的代码 + 新数据」要求
  「根据这个火山图直接换个代码，分别做出 N 张」「你自己看看代码」「我只要里面最完整的图」时，
  以他的代码为基线、只换数据源/子集/循环/每图标题，出 N 张同风格图。
  追加触发词：「宽度不够」「亚群名字挤在一块」「标签/文字重叠」→ 先按 strwidth 重算画布宽度；
  「你用的哪个数据」「这个类别不该有」→ 数据源核查（过滤版 vs 全表版）；
  「这个基因为什么没标记」「标记标准是什么」「为什么不标这个点」→ 读脚本 filter→arrange→slice
  的真实顺序做四步审计（gate-then-rank：FDR 是门槛、|coef| 只是门槛内的排序键），
  见 references/volcano-label-rule-audit.md；
  「只补标这一个基因」「补标一下这个点」「规则外补标」→ 白名单单点补标（不动全局门槛），
  见 references/annotation-rule-supplement-execution.md；
  「只要最终版」「把之前错误的去掉」→ 单体交付 + 旧版移入 `_deprecated_*/`；
   「图里的文字变成英文」「图内文字改英文」→ 只改图内可见文字 + 双层 OCR 验收。
when_to_use: >-
  [user-script-figure-optimization] 用户贴出自己的绘图脚本要优化/检查/提到期刊级标准时
version: 1.0.0
author: MemOmics
license: MIT
platforms: [windows, linux, macos]
metadata:
  hermes:
    tags: [visualization, ggplot2, seurat, umap, publication-figure, user-script, 07_可视化]
    difficulty: basic
    language: R+Python
    category: Visualization
---

# 用户已有绘图脚本的优化（以脚本为基线）

用户贴出**自己已经能跑**的绘图脚本，要求「按 Nature 优化 / CNS 级 / 检查脚本 / 改成发表级」。
本 skill 管的是这一类工作，**不是**从零画图。

> 详细事故复盘 + 完整 R/ggplot2/Seurat 代码见 `references/user_script_optimization.md`。

## 何时使用

- 用户消息里含一段**可运行的绘图代码** + 任何风格/级别/期刊字样
- 「帮我改一下我的脚本」「检查一下这个脚本」「这个图怎么优化」
- 「按 nature 风格优化」「CNS 级」「发表级」「投稿用图」（**用在用户已有脚本上**时）
- 用户抱怨「你改的比我原来的还差」「你跑哪去了」→ 立刻回读本 skill 的铁律 0-1
- **最小改动类**：「不需要 a,b 这些符号，其他的不变」「把标题去掉」「改成统一标准」「这一块换成 X」
  —— 用户指着一个**已存在的版本**（不限于他给你的脚本，也包括你上一轮出的图）要求定点修改
- 多轮改图：用户在同一张图上连续提「三个问题」这类清单 → 逐条对应改，逐条给核验证据

**不适用**：用户只给数据不给脚本（走常规出图 skill）；纯知识问答（查文档即可）。

> ⚠️ 本 skill 的基线**不只指"用户贴的脚本"**：只要用户是**指着某个已落盘的版本**说「在这个基础上改」，
> 那个版本（无论谁写的）就是基线 —— 铁律 A/B 同样适用。

---

## 铁律 0：先谈方向，再动手（最高优先级）

用户给脚本 + **风格/标准要求** = **方向选择**，不是「纯代码修改」。动手前至少确认三件事：

1. 保留原画布尺寸 / 面板排布 / 点径吗？（用户往往就喜欢现在的版式）
2. 「优化」= 加投稿规范（矢量导出、字号合规、白底、Source Data），还是重排版式？
3. 只修报错，还是连带做规范增量？

**实测事故**：把用户 26×8 in 的 DimPlot 改成 180×108 mm + `pt.size` 0.25 + `facet_wrap` 后：

> 「我让你按照 nature 风格优化，怎么比原来的代码还要简陋了？」
> 「这才是我的原代码，你跑哪去了？」

**判据：要求里只要带「风格 / 级别 / 期刊」字样，就先问一句再改**，不要自己判成 code-edit 直接跳过去编辑。

---

## 铁律 1：最小改动，逐条列出

| | 允许 | 禁止 |
|---|---|---|
| 参数 | 修 bug、显式化关键参数（如补 `reduction=`） | 改画布尺寸、面板排布（`split.by`→`facet_wrap`）、点径、配色赋值 |
| 结构 | 加导出/源数据块（**新增，不删原有**） | 重写代码结构、删用户写法、按自己风格重构 |
| 输出 | 逐条列「改了 / 为什么 / 风险」 | 只丢一整版新代码让用户自己找差异 |

**刻意不动的地方也要明说**。例：`family="sans"` 在 Windows 下已映射 Arial（符合 Nature 字体要求）不必改；用户脚本里 `cols=` 与 `scale_color_manual()` 重复设色虽会 warning 也不越界删。说明「我没动它，因为…」比默默删掉更有价值。

---

## 铁律 2：Nature 级 ≠ 把图缩小

`pt.size`（ggplot2）/ `s`（matplotlib scatter）是**绝对尺寸**，不是相对量。

| 做法 | 后果 |
|---|---|
| 只砍画布、点径不变 | 点占比变大，糊成实心饼 |
| 只砍点径、画布不变 | 点细如尘，看不见 |
| **两个一起砍** | **图整体退化**（事故之错） |

**画布与点径必须联动。** 规范的本体是：

| 规范项 | 内容 |
|---|---|
| 尺寸×字号解耦 | 先定最终 mm 尺寸，字号按该尺寸下可读性定（正文 5–7 pt，≥5 pt 硬线） |
| 矢量导出 | SVG + PDF（+ TIFF 600 dpi 备位图） |
| Source Data | 投稿附件：每类×每组的细胞数/统计量 CSV |
| 组序可控 | 显式 factor levels，否则字母序替你排序（读者把组序读错） |
| 灰度/色盲可辨 | 出灰度预览确认类别仍可区分 |

### 加宽画布类请求（用户说「宽度不够 / 亚群名字挤在一块」）

**先算需要多宽，再决定画布 —— 不要凭感觉放大。** ggplot2 的 `size` 是 pt：`pt = size × 2.845`

```r
pdf(NULL); par(ps = 12)                       # 空设备量字，不落盘
w <- sapply(LAB, function(s) strwidth(s, units = "inches", cex = (6*2.845)/12))
need_panel <- length(LAB) * max(w) * 1.06     # 每类目 1 个色块，留 6% 余量
# 画布宽 = need_panel + 0.55（y 轴标题/刻度余量）
```

| 实测（`size = 6` → 17.1 pt） | 值 |
|---|---|
| `"Pure Type IIA"`（最宽） | **1.415 inch** |
| 8 个色块并排所需面板 | **12.0 inch** |
| 加轴标题余量后的画布 | **≥ 13 inch**（本次定 14×7） |
| 原 8 inch 画布每块实际 | 0.89 inch ⇒ **溢出 1.6 倍**（重叠根因） |

- **加宽画布，不要缩标签字号**：缩字会改用户原稿观感；加宽只动画布一个变量
- **连带影响主动说明**：pt 是绝对值 ⇒ 画布 8→14 inch 后点/字**相对变小**。按铁律 2 正确解法是
  「画布与点径联动放大」；但用户若反复强调「只改指定项」，就**原样保留他的 pt 值**，在交付里
  点明这层影响 + 给出「一条命令联动放大」的选项，**不要默默替他改点径**
- 验收脚本见 `references/volcano-panel-canvas-and-data-source.md`「每块文字墨迹 vs 块宽」
  （本次 5 图 × 8 块全过：墨迹最宽 425 px / 块宽 486 px = 0.87，零溢出零跨块）

---

## 铁律 3：自己引入的 bug 直接修，不要先「核验报错出处」

实测：我给用户加的 `TYPE_LAB[as.character(data$type)]` 导致 `No cell overlap`；用户说「改一下报错」，我却先花两轮做网络查证：

> 「不是让你改一下报错吗？为啥一直卡着啊？你他妈要干什么？」

规则：
- 报错出现在**我刚给出的代码**里 → 优先假设是自己写的，直接定位那一行
- 用户说「修一下这个报错」= 立刻给修正后的完整代码，**不做前置查证、不跑流程**
- 依据/来源补在后面，但不能挡住修复

---

## 重绘类请求：只改色 / 改语言，不重算数据

用户说「把老方法的颜色改一改，换一种」「把图片的展示成英文」「标签换成英文」「这个配色不好看」时，这是**重绘**，不是重分析：

| 项 | 规则 |
|---|---|
| 数据 | **复用已算好的统计量 CSV**（如 `task2/results/*_overview.csv`），一行数据都不重算 |
| 脚本 | 产出到**新脚本**（`16_xxx.py`），不覆盖上一版脚本——保留代次可回溯 |
| 汇报 | 必须写明「**未重算任何统计量**，数字与上一轮完全一致，只有画法变了」——用户会逐位核对数字 |
| 自检 | 像素级：非白占比 + **目标色像素是否真的出现**（改色后要能证明新色上去了，不是凭感觉说改了） |

### 多方法对比图的配色：老方法不要做成新方法的淡版

**事故**：老方法（基线方法）的柱子直接用了新方法颜色的 **55% alpha 淡版** → 两套柱同色系、灰度下几乎同色，用户当场要求换。

修法：

| 方法 | 上调配色 | 下调配色 | 额外 |
|---|---|---|---|
| 新方法 | 红 `#B2182B` | 蓝 `#2166AC` | — |
| 老方法 | 琥珀 `#E8A33D` | 青绿 `#4EA8A0` | 柱加 `//` 斜纹（matplotlib `hatch='//'`） |

- **保留「暖 = 上调 / 冷 = 下调」的跨方法语义** —— 不能为了区分而把上调画成冷色，读者会误读效应方向；同一方法内 up/down 的冷暖约定也要一致
- **斜纹是免费的冗余通道**：灰度打印 / 色觉障碍下仍能一眼分开两种方法；用户不想要就一行删掉，但**先告知再删**
- 独立色对 > 同色系深浅版：深浅版在折线/柱状小尺寸下不可辨，独立色相才稳
- 出图后逐色验证像素：本会话实测「图1 无琥珀/青绿 = 符合预期（那版只有新方法）、图2 四色齐全」——**验证要能解释缺色的正当性**，不是要求所有颜色都出现

### 标签中 → 英切换（字体链一起换）

改英文时**同时换字体链**：CJK 字体（Noto Sans CJK / SimHei）在纯英文场景反而带方框风险，换成
`Arial → Helvetica → DejaVu Sans` 链：

```python
matplotlib.rcParams['font.sans-serif'] = ['Arial', 'Helvetica', 'DejaVu Sans']
matplotlib.rcParams['axes.unicode_minus'] = False   # 负号别变方框
```

- 标题 / 轴名 / 轴刻度 / 图例 / **figure legend 里的方法名**全部改（例：`new = cell-level glmer + RUV; old = pseudobulk dreamlet`）
- **只改展示文本，不改数据列名/变量名**——下游脚本还在用原字段
- 数字格式（千分位 / symlog 刻度标签）也要跟着语言走，别留 `×10⁴` 之外的中文单位

#### 🔴 改动边界：用户说「**图里面的文字**变成英文」= 只动图内可见文字

实测原话：「`44_MEF2C_locus_from_GTF` 这个里面的文字变成英文」。用户指的是**图内**，不是整个脚本。

| 层 | 改不改 | 说明 |
|---|---|---|
| 图内可见文字（标题 / 轴名 / 轨道标签 / 注释文字 / 脚注） | ✅ 全改 | 这才是"里面的文字" |
| **脚本注释（`#`）** | ❌ 不动 | 不进图片；顺手英文化 = 越界（与「只改指定清单项」冲突） |
| **终端 `print(...)` 输出** | ❌ 不动 | 不进图片（图是给读者看的，print 是给你看的） |

汇报时**主动写明**：「只改了图内 N 处，注释与终端打印仍是中文（它们不进图片）」——这句话成本极低，
但用户会核对"你有没有偷动别处"。若用户要连注释一起英文化，他会说；**不要替他决定**。

> 扫描合规性时，`grep` 中文关键字会同时命中注释行和 `print(` 行 —— 判断标准是
> **命中的行是否全是 `#` 注释 / `print(`**，是则合规，不需要把它们也翻译掉。

#### 英文化带来的两个版式副作用

1. **英文比中文长 → 长脚注必须拆行**。中文脚注一行 ~85 个汉字，直译成英文常 110+ 字符，
   单行会顶出画布边缘。拆两行并用 `linespacing` 收一下：
   ```python
   fig.text(0.135, 0.052,
            'Exon blocks = merged exon intervals across all transcripts of each gene '
            f'(MEF2C: {n_tx_a} transcripts / MEF2C-AS1: {n_tx_b});\n'          # ← 手动换行
            'arrowheads = transcription direction; source file: ...',
            fontsize=5.6, color='#555555', ha='left', linespacing=1.5)
   ```
   ⚠️ `fig.text` 默认 **`va='baseline'`**：多行文本的锚点在**第一行基线**，后续行挂在锚点**下方**
   —— 所以 y 要按"第一行"给，别按整块中心给，否则整块会被顶到画布外。
2. **字体链换拉丁体**：CJK 字体（Microsoft YaHei / SimHei / Noto CJK）在纯英文图里会带来
   拉丁字形不一致（粗细/字宽跳变）。改用 `['DejaVu Sans', 'Arial', 'Helvetica']` ——
   **`DejaVu Sans` 可放首位**（matplotlib 自带，不依赖系统装没装 Arial；Windows 下 Arial 也在，
   两者都合规）。⛔ 无论如何都要**把 CJK 字体从链里摘掉**。
   `axes.unicode_minus = False` 照留（负号/`−` 别变方框）。

#### 验收：中文残留 = 0 必须被**两层**证明

```bash
# ① 脚本层：图内文字域的 grep（命中全为注释/print 即合规）
grep -n "链\|重叠\|位置\|外显子块\|三角示" scripts/44_xxx.py
```
② 图像层：`vision_describe` 全图 OCR → 断言"返回清单里 0 个中文字符"；
**小字号脚注另做裁切放大二次 OCR**（见上方 OCR 三个失效场景表 —— 全图 OCR 会漏读它，
不能拿"没读到"当成"改失败"或"没渲染"，两个方向都会误判）。
③ 改动只碰文字时，**数据口径必须一模一样**：重跑后逐项对比上一版数字
（本次 MEF2C 56 tx / 36 外显子块、MEF2C-AS1 15 tx / 22 块、重叠 20,930 bp 与上版完全一致），
汇报里写明"数值与上一版完全一致，只换了语言文字"。

> 完整配方（6 处替换清单、字体链、脚注拆行、双层 OCR 验收命令、实测数值）见
> `references/figure-text-language-switch-and-ocr-verification.md`。

---

## 最小改动类请求：「只删一个图元 / 只改一处，其他不变」

用户原话形如：**「不需要 a,b 这些符号，其他的不变」「把标题去掉」「轴名改一下」**。
判据：**改动点可数（1–3 处）且用户明确冻结其余全部版式**。这类请求**不是重绘、更不是重排**。

### 铁律 A：绝不重写脚本，`cp` + 定点 patch

| 步 | 做法 |
|---|---|
| 1 | `cp 33_xxx_v3.py 34_xxx_v4_no_letters.py`（**新代次文件**，不覆盖上一版） |
| 2 | 只对目标行做定点 patch（V4A 或 replace），**不碰其他行** |
| 3 | 汇报时给出脚本层面的改动量（本次：删 5 个面板字母 = **改 2 行，253 行里 251 行零改动**） |

- 代次命名递进、可回溯：`v2_optimized` → `v3_unified_symlog` → `v4_no_letters`
- 为什么不能重写：重写会顺手漂移字体 / 坐标 / 导出参数（用户要的恰恰是"其他不变"），且丢代次、无法对照
- 用户会看有没有偷动别处 —— 所以要说得出「脚本只改了哪几行」

### 铁律 B：「其他不变」必须被**证明**，不能只是声明

用**两版像素差分**，不用 OCR（OCR 验不了"删掉了没"，见下）。

```python
A = np.asarray(Image.open(v_prev).convert("RGB"), dtype=np.int16)
B = np.asarray(Image.open(v_new).convert("RGB"),  dtype=np.int16)
d = (np.abs(A - B).max(axis=2) > 8)      # 前提：同 figsize + 同 dpi → 同 px 尺寸
```

报四个数，缺一不可：

| 检验项 | 本次实测 | 说明 |
|---|---|---|
| diff 像素数 / 占画布比 | 2,229 px = **0.057%** | 改动极小 |
| diff bbox（y-frac / x-frac） | 行 169–203（y-frac 0.122–0.147） | 正是被删元素所在的纵向带 |
| **x 方向簇数** | **5 簇**，每簇宽 23–24 px | 5 个孤字母各占一簇 |
| **数据区 diff**（如 y-frac 0.25–0.80） | **0 px** | **数据面一个像素都没碰** |

> 「数据区 diff = 0」是这套证据里最值钱的一行 —— 它把「我没动柱子」从口头承诺变成实测数字。
> 现成脚本：**`scripts/pixel_diff_verify.py`**，`python pixel_diff_verify.py A.png B.png --expect-clusters 5` 即出全部四项 + verdict。

### OCR 的三个已知失效场景（别拿它验"删掉了没"）

| 场景 | OCR 表现 | 正确做法 |
|---|---|---|
| 孤立小字母（a/b/c/d/e） | 整图 OCR 吐一堆小写字母，**无法区分**标题里的小写与面板字母 → 证明不了删除 | 用像素差分（铁律 B） |
| 旋转文字（y 轴名 / 旋转模块名） | 输出乱码片段 —— **这不是渲染失败**，是 OCR 伪影 | 裁切 → `Image.rotate(90, expand=True)` 转正 → 放大 2× → 再 OCR（本次转正后即读出 `Pure fiber types` / `Derived`） |
| **小字号长脚注（5–6 pt）** | **整行被静默漏读** —— 全图 OCR 返回的清单里根本没有这行，看起来像"文字没渲染出来 / 被裁掉了" | 裁出该区域 → **放大 2×（LANCZOS）** → 再 OCR。实测：`fig.text(..., "...\n...", linespacing=1.5)` 的两行脚注，全图 OCR 只读到第 2 行，**裁底部 140 px + 2× 后第 1 行完整读出** ⇒ 两行都在，是漏读不是没画。并用 vision 输出里的 **ASCII 亮度图**佐证（该带出现两条满宽文字行 = 两行都在） |

结论：**删除类改动用像素差分；文字渲染完整性用「裁切+转正/放大」OCR**。两者不要混用。
**🔑 铁律：OCR 缺失 ≠ 渲染失败。** 在断言"这行没画出来"之前，必须先**裁切放大复核一次** ——
否则会去修一个根本不存在的 bug（本次差点把正确的两行脚注当成"第 1 行丢了"重改一轮）。
现成工具：`scripts/ocr_crop_upscale.py`（裁区域 + 放大，输出可直接喂 `vision_describe`）。

### 区域留墨率：证明"你优化过的那块真有东西"

出图同轮做像素健康自检时，**按用户点名的区域分带统计**，不要只报整图非白比：

```python
print(nonwhite, len(np.unique(a.reshape(-1,3), axis=0)))          # 整图：非空白、非黑底、色彩数
top  = a[int(H*0.03):int(H*0.16)]                                  # 顶部条带
left = a[int(H*0.30):int(H*0.85), int(W*0.001):int(W*0.13)]        # 左侧条带
print(((top<245).any(axis=2)).mean(), ((left<245).any(axis=2)).mean())   # 本次 9.59% / 29.61%
```

同时报物理尺寸：`W/400*25.4`（@400dpi）→ 本次 **180.0 × 87.6 mm**。用户会核对 mm 尺寸与"那块区域有没有内容"。

---

## 长尾柱的数值标签：「贴近，但是又不重合」（用户原话）

用户要「每根柱都标自己的数、贴近、但不重合」时，**不能按数值比例判位置** —— log / symlog 轴下会判错。
要用 **axis transform 之后的像素比例**：

```python
tr   = ax.xaxis.get_transform()
f0   = float(tr.transform(0.0)); f1 = float(tr.transform(XMAX))
frac = (float(tr.transform(v)) - f0) / (f1 - f0)      # 负值侧对称处理
```

| 条件 | 标签位置 |
|---|---|
| `frac <= 0.80` | 柱**外** 2.5 pt offset（贴近，用柱色） |
| `frac > 0.80` | 改柱**内**白字、右对齐（不越界、不压相邻柱） |
| `v == 0` | 单独给 4.2 pt 偏移，否则标签压在轴线上 |

这样**任何柱长组合下都不重叠、不越出面板** —— 比"统一放外侧"或"统一切到轴外"都稳。
（本次 5 面板 × 8 亚群 × 2 方向 = 80 个标签全按此规则落位。）

---

## 版式冲突的算前预检：别画完才发现压叠

用户报「亚群名跟来源重合了」时，根因是**两个元素的 x 区间本身重叠**，不是字太小：

> 实测：亚群名 6.4–6.6 pt × 13 字符，右对齐基准 x=0.090 → **左缘 ≈ 0.094**；
> 家族括号画在 x=0.150 → 括号落在文字**左侧**，两者**必然压叠**。

规则：
- 新增或移动任何**文字 / 装饰线 / 色条**前，先把两者的 x 区间摆出来比一比，重叠就别画
- 已压叠的正确修法是**重排或合并**，不是"再挪 1 mm"：本次把「双家族彩色括号 + 旋转家族名」整体换成**单一模块竖带（如 `MF`）**，
  阅读顺序固定为 `轴名 → 亚群名（右对齐）→ 模块竖带 → 柱形图`
- 无色无字的极浅虚线（`#D0D0D0`，`linestyle=(0,(1,1.6))`）可留作分块，它不参与文字冲突

> 本类请求的完整实测复盘（三个问题的根因、统一 symlog 阶梯刻度配方、像素差分原始输出）见
> `references/figure_edit_verification.md`。

---

## 复用用户脚本到新数据：多对比模板化复刻（「根据这张图换个代码」）

用户给的不是「要优化的脚本」，而是**一张已定型的参考图 / 一段能跑的代码 + 新数据**，
要求「照着这个样式，分别做出 N 张」（实测：5 个 DEG 对比 × 8 亚群火山图）。
基线仍是**用户的代码**，不是你的审美 —— 铁律 1 照旧适用，只是「最小改动」的对象变成
「只换数据源 + 子集 + 循环 + 每图标题」。

### 0. 开工前先验数据源：**过滤版 vs 全表版**（本类任务第一大坑）

用户给「新数据 + 他的图样式」时，磁盘上常**同时躺着两份同系列的表**：上游 pipeline 的
全量输出（未过滤）与**已卡过阈值的导出**。用错一份，整批图全废。

**事故**：用户原图的数据是已过滤 sDEG 表（图里没有「不显著」类别）；我用未过滤全表复刻，
图上冒出 9,420–36,541 个灰点、图例多出一行 `Not Significant` → 用户当场质疑
「**你用的哪个数据？**」。

| 判据 | 未过滤全表 | 已过滤导出 |
|---|---|---|
| `max(fdr)` | 可到 **1.0** | < 阈值（本次 0.039） |
| `min(abs(coef))` | ≈ **1e-5**（近 0） | = 效应量阈值（本次 0.25） |
| 无效类别 | 存在（灰点/不显著） | **恒不存在** |

**从用户成品图反证他当初的输入**（比问他更快、更硬）：统计他图里「无效类别」填充色的像素数。
本次 `grey80 (#CCCCCC)` 仅 **22 px / 276 万 px** ⇒ 他输入的是已过滤表。
⇒ **图上多出一个用户说「不该存在」的类别 = 数据源错了，不是画错了。**

定位过滤表：按名字片段全盘搜（别只搜工作目录，含用户「下载」目录）

```bash
for root in "D:/" "E:/" "C:/Users/<user>"; do
  find "$root" -maxdepth 6 \( -iname "*fdr05*" -o -iname "*coef025*" -o -iname "*<用户说出的表名>*" \) 2>/dev/null
done
```

命中后 **`md5sum` 与我方会话副本比对**（本次两份 md5 相同 = 同源，放心用；用户「下载」目录
那份常常正是我早先导出的副本）。**锁口径**：脚本里写死断言防漂移
（`stopifnot(max(dd$fdr[dd$celltype %in% ORDER]) < 0.05)`），并把「不显著」类别**整类删掉**
（不是设透明/不画点 —— 否则图例会把空类别自动加回来）。

### 1. 用户说「你自己看看代码」时：去把原文扒出来，别再问

参考物常见形态是 **Jupyter nbconvert 导出的 HTML**（几 MB / 几万行），里面同时藏着
① 他的代码单元 ② 渲染好的成品图 ③ 单元格输出文本，三者都能提：

| 要的东西 | 提取方式 |
|---|---|
| 代码单元 | `<div class="highlight[^"]*"><pre>(.*?)</pre></div>`（re.S）→ 去标签 + `html.unescape` |
| 内嵌成品图 | `data:image/(png\|jpeg);base64,([A-Za-z0-9+/=\s]{200,})`（re.S）—— **必须允许空白**：base64 里带换行，严格字符集正则会 0 命中（本会话踩过，误判成「没有内嵌图」） |
| 源表列名 | 找输出区 `<pre>` 文本（他的 `print(head(df))` 留下列名与类型）—— 由此得知源 CSV 还带 `group` / `type` 列，省一轮猜测 |

### 2. 「我只要里面最完整的图」= 取他代码里**最靠后的那版累积结果**

他的 notebook 常是 `p → p2 → p3` 递进精修（p 基础图 → p2 加装饰 → p3 加终版主题）。
「最完整的图」= **最后累积的那版**（p3），不是「随便挑一张」，也不是「全部都要」。
判据：哪一版同时带 图层 + 装饰 + 终版 theme，就复刻那一版。

### 3. 参考图里的类目名可能**不是当前数据的类目** —— 先比名字再对齐

实测：从参考图色块 OCR 出的亚群名是 `Type_I/II/IIX`、`GALNTL6_I/II`、`ANKRD1_II`、
`BMPR1B_MF`，与现存表的 `Pure Type I / RP_high / OTUD1+…` **不是同一代标注**
⇒ 那张图只是**样式模板**，它的 x 顺序与配色映射**本来就无从套用**。
⇒ 别硬复原参考图顺序；改用**本项目内用户已定稿的同类图顺序**（本例沿用他多轮改过的柱子图 `ORDER`），
并把这一决定连同「原顺序不可复原（原始 CSV 已不在磁盘）」的理由**写进交付说明**。

### 4. 从**已渲染的 PNG** 反向还原参考图的顺序与配色（比 OCR 可靠）

| 目标 | 做法 |
|---|---|
| 定位「标签色块带」 | 逐行统计饱和像素的**色相种类数**：某行同时出现 ~N 种色相、每种各占 ~等量像素 ⇒ 就是色块带（实测 y≈700–796、9 色 ×200 px）。**别用饱和像素总数找**——散点云会把 y=870 之类误判成带 |
| 每块的颜色 | 沿该行按色变（三通道差和 >90）或近黑边框切段，取段内众数色 → 与已知色板比对 |
| 块内文字 | 裁该带 → **放大 3×** → OCR（原始尺寸读不出）；读不全没关系，**够判断「是不是同一套命名」即可** |

### 5. 一处非逐字改动 = 一条说明；不要悄悄替用户做决定

本类任务必然有几处**非逐字**改动（子集范围、x 顺序、配色映射、每图标题）。做法：逐条列
「改了什么 / 为什么 / 风险」，并点明哪些是**硬约束**（例：N 张分开的文件必须带对比名标题，
否则无法区分）。用户可能只认可其中一部分 —— 给 `ask_user` 勾选项比替他决定便宜。

### 6. 交付版本卫生：用户说「把之前错误的去掉」

- **移到 `_deprecated_<原因>/`，不要 `rm`**：本次把 15 个旧文件（8 inch / 未过滤 / 带灰类）
  移进 `figures/_deprecated_8inch_unfiltered/`，交付目录只剩终版；汇报写明「旧版已移出，
  要彻底删除说一声」—— 可回溯 + 目录干净，两头都占
- 新旧文件名要能一眼分代：旧 `..._userstyle.*` → 终版 `..._FINAL.*`
- 「只要最终版」= 交付**一个**版本，别自作聪明并列两版让用户挑

> 完整配方（HTML 提取正则、色块带定位代码、backend-adaptive xlsx 读取、导出核验、本轮
> 实测数值与坑）见 `references/user-code-and-figure-recovery.md`。

## 复刻后必答的一类追问：「这个基因效应量这么大，为什么没标记？」

用户交图后会**逐个点问**（实测原话：「标记上调和下调的五个基因，你是怎么选的？按照什么标准？」
「我看到 DM 有一个亚群有个基因的效应量很大，但是中等显著性，为什么不把它标记？」）。
**用数字回答，不要凭印象，也不要说「因为标准只看显著性」这种含糊话。**

### 标注规则的形态 = gate-then-rank

```r
top_genes <- df %>%
  filter(fdr <= 0.001) %>%            # ① 门槛（准入）
  group_by(celltype, group) %>%       # ② 按 亚群 × 上/下调 分池
  arrange(desc(abs(coef))) %>%        # ③ 池内按 |coef| 降序
  slice_head(n = 5)                   # ④ 取前 5 标名字
```

**这个顺序本身就是答案**：FDR 是**门槛**、`|coef|` 只是**门槛内的排序键** ⇒
**大效应 + 大 SE 的基因永远进不了候选池**（`z = coef/se` 被大 SE 除小，FDR 落到门槛外），
哪怕它的 `|coef|` 是全表第一。

### 四步审计（每步都要能指到行号或表里的格子）

| 步 | 查什么 | 判据 |
|---|---|---|
| 1 | 脚本里 filter→group_by→arrange→slice 的**真实顺序与行号** | filter 在 arrange 之前 = 门槛优先 |
| 2 | 该基因 `coef/se/z/fdr`，与**同池已标基因比 SE** | 常见 10~40 倍差距；z 刚好卡在门槛外 |
| 3 | 同一基因在**其他亚群**的表现 | 常见「另一亚群过门槛但 \|coef\| 排第 6」→ 两条路都堵，要说清 |
| 4 | 该图**中等显著带**（0.001<FDR<0.05）行数 + 其中最大 \|coef\| | 它是唯一离群点 → 真盲区，如实承认；一批都差不多 → 规则合理 |

### 三个容易答错的点

1. **「点没了」vs「只是没名字」**：`0.001 < FDR < 0.05` 的点通常仍以第三色
   （`mid_sig_black`、图例写 `Moderate Sig`）**画在图上**，缺的只是基因名标签。
   先用图例 + 该颜色的像素数确认点到底在不在 —— 这一步说错，整段解释就废了。
2. **口径必须标明**「图里的 N 个亚群」还是「全表」：表里 `celltype` 常比图多
   （实测表里 10 个 = 图里 8 个 MF 亚群 + `RSS` + `Specialized MF`）。给出图上找不到的数字等于没答。
3. **xlsx sheet 名是「对比字符串」，不是组别名**：`Worksheet named 'DM' not found`。
   一律先 `pd.ExcelFile(p).sheet_names`（实测表名 = `Y_Pre_vs_O_Pre / O_Pre_vs_OD_Pre /
   Y_Pre_vs_Y_Post / O_Pre_vs_O_Post / OD_Pre_vs_OD_Post`，对应 Aging / DM / Ex_Young / Ex_Old / Ex_DM）。

### 规则要不要改 = 会改交付物的决定

**用 `ask_user(kind="intent")` 给互斥选项，不要在正文末尾用问句**（正文问句的答复无法与问题绑定）。
选项范式：① 不改（保持用户原稿）② 只补标该基因 ③ 加「大效应无条件标注」特例规则
④ 门槛放宽到 FDR<0.05 后仍在池内按 |coef| 排 top5（影响最大，要重出全部图）。
另：纯只读核查的回合**不要新增产出文件**，汇报里写明「本次无新增产出」。

#### 用户勾选「② 只补标该基因」之后：白名单补标协议（实测 2026-09-30）

**不要改全局门槛** —— 改门槛会把该图**全部**标签重排（本例另有 31 个中等显著行会被放进池，
Aging 还会冒出 |coef|=2.500 的 RSS 点），远超「只改指定项」授权。走白名单：

| 步 | 做法 |
|---|---|
| 1 | 顶层 `EXTRA_LABELS` 四元组 `sheet / celltype / group / gene`（写成可扩展表，不是 if 硬编码） |
| 2 | 循环内 top_genes 算完后按 sheet 过滤白名单，`stopifnot(length(hit) == 1)` **精确命中校验** |
| 3 | 补标行的 `coef/fdr` **从数据里取，不写死数值**；加 `source` 列（`top5` / `manual_supplement`）溯源 |
| 4 | 追加用 **`dplyr::bind_rows()`**，不用 `base::rbind()`（见下方 R 坑 6） |
| 5 | 补标**不改样式**（同 repel 层、同色）；**只补点名那个，不顺手补别的**；说明「该点原本就在图上，坐标轴范围未变」 |
| 6 | 覆盖前**先备份老版**：`figures/_v1_top5only/` + 脚本 `.v1.bak.R`（用户说「老版保留」= 交付前动作，不是事后补救） |

**验收三件套（全部要数字）**：① 图上 OCR 直读检出该基因名 ② 汇总 `n_labels` 恰好 **+1**（其余图不变）
③ 全库 `source == "manual_supplement"` 行数 **== 1**（证明无越权补标）。

> 完整实现代码 + 验收脚本 + 两个 R 坑（`base::rbind` 追加 tibble、R 脚本静默失败的逐表达式定位配方）
> 见 `references/annotation-rule-supplement-execution.md`。

> 完整审计脚本 + 实测实例（TMSB4X 逐项数字、5 张图的中等显著带分布）见
> `references/volcano-label-rule-audit.md`。

## 文字↔图元「对不齐 / 压住了」类追问（几何类：先量，再改）

触发语（用户原话，2026-10-01 实测）：**「往上挪动一点，他把 ITIH4 这个基因压下来了」**
**「亚群和基因，要跟自己对应的色块对齐啊」**。

🔑 **铁律：这类追问先量几何、再查布局公式，不要直接去挪文字位置** —— 本次「标签没对齐」的根因
**100% 在 `layout()` 的间隙公式**里，标签坐标本身没写错；直接挪标签只会掩盖 bug。

| 判据 | 做法 |
|---|---|
| 标签 y | 一律 = 节点**真实中心** `(y0+y1)/2` |
| **节点区间不重叠是前提** | 区间重叠 ⇒ 后画的色块盖住前一个下半截，标签看着就"掉"出色块（**越靠顶端越明显**） |
| 间隙公式 | ⛔ **绝不能与权重数值相乘**：`gap = 0.022*tot/(n-1)` 在 `tot=102` 时算出 `usable = -1.244`（节点高为负）。实测 UP 图顶部 3 个标签偏 **72 / 53 / 27 px**，而 DOWN 图 `tot=24` 侥幸正常 ⇒ **同一脚本可能只有一半的图出问题，两轴/两图都要测** |
| 修法 | 间隙改**整列固定比例**（`GAP_RATIO/(n-1)`，`usable=0.90`）⇒ 标签↔色块中心偏差实测 **0.00 px**、相邻节点重叠 **0 对** |
| 列标题压住顶端节点 | 标题 y 与 `set_ylim` 上沿**联动抬高**（实测 110 → 177 px）；只抬标题不抬 ylim 会顶到主标题 |
| **几何自检写进脚本** | `fig.canvas.draw()` + `Text.get_window_extent(renderer=r)` 量三项：标签↔色块中心偏差(px) / 相邻节点重叠对数 / 列标题↔顶端标签间距 —— **出图即出证据，汇报里给这三个数** |
| ⚠️ 两个小坑 | `Bbox` **没有** `get_center()`（用 `(bb.y0+bb.y1)/2`）；display 坐标**自下而上**，打印时别把符号写反（把"无重叠"报成负数会多改一轮） |
| 改法 | 只 patch 对应常量（标题 y / ylim / `GAP_RATIO`），不重写脚本（铁律 A）；重出图前把旧版备份到 `figures/_backup_*` |

> 完整配方（错误/正确公式对照、节点重叠实测区间表、自检代码、脚注锚底与图注语义）见
> `platform-execution-pitfalls` 的 `references/sankey-alluvial-node-geometry.md`。

## R / ggplot2 / Seurat 高频坑（速查）

### 1. facet 标题不居中 → 必须写 `strip.text.x.top`

ggplot2 **4.0.3** 官方 `theme()` 文档原文：

> Facet strips have dedicated position-dependent theme elements (`strip.text.x.top`, `strip.text.x.bottom`, `strip.text.y.left`, `strip.text.y.right`) that inherit from `strip.text.x` and `strip.text.y`, respectively. **As a consequence, some theme stylings need to be applied to the position-dependent elements rather than to the parent elements.**

只写 `strip.text` / `strip.text.x` 时，**位置类样式（`hjust` / `margin`）不保证生效**。三行都写（跨版本兼容）：

```r
theme(
  strip.text       = element_text(face = "bold", size = 9, hjust = 0.5, margin = margin(b = 2)),
  strip.text.x     = element_text(face = "bold", size = 9, hjust = 0.5, margin = margin(b = 2)),
  strip.text.x.top = element_text(face = "bold", size = 9, hjust = 0.5, margin = margin(b = 2)),  # ← 真正生效的一层
  strip.background = element_blank(),
  strip.placement  = "outside"
)
```

排查第一步：`cat(as.character(packageVersion("ggplot2")))`——strip 继承行为在 3.5 / 4.x 之间有变化。
相关：`legend.title`（继承自 `title`，对齐用 `hjust`）、`legend.title.position`（**3.5+ 才有**，低版本可能报未知元素）。

### 2. Seurat `No cell overlap between new meta data and Seurat object` → 向量必须 `unname()`

`vec[as.character(x)]` 返回**带 names 的向量**，Seurat 把 names 当 barcode 匹配 → 零重叠。

```r
# ✓
data$type_lab <- factor(unname(TYPE_LAB[as.character(data$type)]), levels = unname(TYPE_LAB))
```

**通杀**：任何赋给 `obj$col <-` / `AddMetaData()` 的向量先 `unname()`。带 names 的来源：查表索引、`setNames()`、`table()`、`tapply()`。

### 3. 高清点图：`pt.size` / `raster` / `raster.dpi`

- `pt.size` 是**最终尺寸下**的点径，与画布英寸联动（铁律 2）
- `raster=TRUE` + `raster.dpi=c(300,300)` —— **必须长度 2 的向量**（X/Y 各一）
- 图例单独 `get_legend()` 必须复用**同一 reduction + 同一 pt.size**：原脚本常漏 `reduction=`（依赖 `DefaultDimReduction` 兜底，改过对象后可能取错降维），漏 `pt.size` 则默认 1 → **图例点比图上点小**

### 4. 投稿导出三件套 + Source Data（R）

```r
W_IN <- 26; H_IN <- 8        # 与预览一致，所见即所得
base_file <- file.path(out_dir, "UMAP_subcluster_by_type")

svglite::svglite(paste0(base_file, ".svg"), width = W_IN, height = H_IN)
print(final_plot); dev.off()

grDevices::cairo_pdf(paste0(base_file, ".pdf"), width = W_IN, height = H_IN, family = "sans")
print(final_plot); dev.off()

ragg::agg_tiff(paste0(base_file, ".tiff"), width = W_IN, height = H_IN, units = "in", res = 600)
print(final_plot); dev.off()

write.csv(as.data.frame.matrix(table(data$subcluster, data$type)),
          file.path(out_dir, "SourceData_subcluster_by_type.csv"))
```

- R 在 Windows 下 `family="sans"` 已映射 **Arial** → 符合 Nature 字体要求，**不必改**
- 透明底适合拼 PPT，投稿需白底 → **用变量控制、默认保持用户原值**：`BG <- "transparent"`（投稿改 `"white"`）

### 5. 预览尺寸 = 导出尺寸

`options(repr.plot.width = 26, repr.plot.height = 8, repr.plot.res = 100)`
字号按真实尺寸定，**预览与导出必须一致**，否则看到的字号/点径都是假的。

### 6. `base::rbind()` 追加 dplyr tibble → `numbers of columns of arguments do not match`

`top_genes` 经 dplyr 管道产出是 `tbl_df`；**即使两边列数一致**，`base::rbind()` 也会在校验阶段 `stop()`。
⇒ 追加行一律用 **`dplyr::bind_rows()`**（可安全混用 tibble / data.frame）；
兜底先 `as.data.frame(top_genes, stringsAsFactors = FALSE)` 降级。同类混用（`merge`/列顺序）也适用此原则。

### 7. R 脚本「静默失败」定位：逐表达式 eval + 调用栈

`source(script)` 抛错时，stdout 里**看不到脚本前面已打印的 `cat`**（输出随错误丢弃）⇒ 看不出挂在第几步。
**不要盲猜、不要原样重跑**，用 `parse()` 拆成表达式逐个 `eval`，并打印 `sys.calls()`：

```r
exprs <- parse("脚本.R", encoding = "UTF-8")
env <- new.env(parent = globalenv())
for (i in seq_along(exprs)) {
  ok <- TRUE
  withCallingHandlers(                     # ⚠️ 必须在 tryCatch 内侧，否则永不触发
    tryCatch(eval(exprs[[i]], envir = env), error = function(e) ok <<- FALSE),
    error = function(e) for (k in seq_len(min(20, length(sys.calls()))))
      cat(sprintf("[%02d] %s\n", k, paste(deparse(sys.calls()[[k]])[1], collapse = ""))))
  if (!ok) break
}
```

- 循环体整体是一个 expr ⇒ 先 `eval` 前置语句，再把 `env$COMPS` 覆写成**只含问题那一项**单独 eval
- `sys.calls()` 里的字面调用（如 `[17] rbind(top_genes, ...)`）就是答案
- ⚠️ `withCallingHandlers` 若包在 `tryCatch` **外面**：错误被 tryCatch 直接 unwind，handler 永不触发 ⇒
  症状是「循环好像跑完却没打印 FAIL」而产物缺失，会白绕好几轮

---

## 交付模板

回复里给出：

1. **完整可运行代码**（一个代码块，直接复制能跑，不要只给 diff 片段）
2. **改动说明表**：

| # | 改动 | 原因 / 影响 |
|---|---|---|
| 1 | `strip.text.x.top = element_text(hjust=0.5, …)` | 标题不居中的真正原因（position-dependent 元素）；风险：无 |
| 2 | 图例补 `reduction=` + `pt.size=` | 不依赖默认降维；图例点与图上点一致；风险：无 |
| 3 | 矢量导出 + Source Data（**新增，没删任何东西**） | Nature 硬性要求；原画布尺寸原样沿用；风险：需 svglite/ragg |
| 4 | 常量抽成变量（默认仍是用户原值） | 保持原行为；投稿改一个词；风险：无 |

3. **刻意没动的地方**（逐条说明理由）
4. 落盘路径（`results/<sid>/scripts/`）+ 一句「要不要我实跑」

### 5. 沉淀：脚本交付**当轮**就做完，别等用户问「你沉淀了吗？」

本类任务的终点不只是「图交付了」，还包括**把这套用户脚本存进用户 skill 库**（用户会复用：
实测原话「我以后可能会用到，**这些你沉淀了嘛？**」→ 下一轮「**你沉淀了吗？**」）。
交付时至少问一句「要不要沉淀成用户 skill」，或直接沉淀后汇报触发词。

- 入库：`hermes_home/skills/plotting/<名>/` → `SKILL.md`（`metadata.hermes.category: user-skill` + `source`）
  + `skill.json` + `scripts/<脚本>`（**`cp` 保字节**）+ 登记 `hermes_home/skills/user-scripts/INDEX.md`
- **变体脚本必须硬编码另存为独立可跑版**：靠内核注入 `MF_VARIANT` 之类开关跑出来的图，
  磁盘上只留默认态的脚本本体 ⇒ 用户问「这张图的脚本是什么？」时会发现**没有那个文件**
  （实测原话「你好像没给我脚本呢」）
- 🔴 **收尾门禁：`git add` 新增的 skill.json / SKILL.md / scripts/ + 跑 4 个 skill 测试**
  （不 add 会红 `test_skills_registry.py::test_index_is_reproducible_from_committed_metadata`）
- 被问「沉淀了吗」时，**先 `read_file` 读 `INDEX.md` 的实际行数再答**，不要凭印象
- 完整配方见 `platform-execution-pitfalls` 的 `references/user-script-sedimentation-completion.md`

---

## 参考来源

- `references/user_script_optimization.md` —— 完整事故复盘 + R/ggplot2/Seurat 详细代码 + 交付模板
- `references/figure-text-language-switch-and-ocr-verification.md` —— **图内文字「中→英」定点切换**：6 处替换清单实样、改动边界（注释/`print` 不动）、拉丁字体链、英文变长的脚注拆行与 `fig.text` 默认 `va='baseline'` 坑、**双层 OCR 验收**（全图查中文残留 + 小字号裁切放大二次 OCR）、脚本层 grep 合规判据、数据口径逐项对齐（20,930 bp 等实测数字）
- `scripts/ocr_crop_upscale.py` —— 裁区域 + 旋转 + 放大，产出可直接喂 `vision_describe` 的临时图（`--strip bottom --px 140 --scale 2` / `--box` / `--rotate 90`）；用于小字号文字二次 OCR、旋转文字转正
- `scripts/pixel_diff_verify.py` —— 两版像素差分四指标（diff 像素数 / bbox / x 簇数 / 数据区 diff），用于证明「其他不变」
- `references/user-code-and-figure-recovery.md` —— **模板化复刻配方**：从 nbconvert HTML 扒用户代码/成品图/输出文本的正则、从渲染 PNG 反推色块带位置与配色的像素判据、参考图与当前数据「不同命名代」的识别与处置、多对比单脚本循环骨架、R 读 xlsx 后端自适应 + 导出字体嵌入核验
- `references/volcano-panel-canvas-and-data-source.md` —— **标签不重叠的画布宽度算法（strwidth 实测）**、每块文字墨迹 vs 块宽验收脚本、**过滤版 vs 全表版数据源判定 + 从用户成品图反证**、图例内容用「裁切+OCR」而不是按色找键、`_deprecated_*` 版本卫生、箭头别用字形用矢量（含像素 run-length 验方向）
- `references/volcano-label-rule-audit.md` —— **标注规则审计**：gate-then-rank（FDR 门槛 → 池内 \|coef\| top N）、回答「为什么这个基因没标记」的四步审计脚本、同池 SE 倍数对比、跨亚群交叉验证、中等显著带离群性量化、TMSB4X 实测案例（coef +1.619 / se 0.515 / z 3.14 / FDR 2.1e-03）、`pd.ExcelFile(p).sheet_names` 别名坑、口径（图内 8 亚群 vs 全表 10 celltype）声明规矩
- `references/annotation-rule-supplement-execution.md` —— **补标执行协议**（用户勾选「只补标该基因」后怎么办）：白名单四元组代码、`stopifnot` 精确命中校验、`source` 溯源列、验收三件套（OCR 直读标签名 + `n_labels` 恰好 +1 + 补标行数 == 1）、老版备份 `_v1_*/`、`base::rbind` 追加 tibble 坑、**R 脚本静默失败的逐表达式定位配方**
- ggplot2 官方 `theme()` 参考页（ggplot2 4.0.3）— https://ggplot2.tidyverse.org/reference/theme.html

## Proven Scripts

> Auto-generated from actual analysis runs. Each row records a successful execution.

| 物种 | 组织 | 方向 | 日期 | 脚本 | auto | user | ✔ |
|------|------|------|------|------|------|------|----|
| human | skeletal_muscle | aging | 2026-09-29 | 16_deg_updown_en_recolor.py | - | - |  |
