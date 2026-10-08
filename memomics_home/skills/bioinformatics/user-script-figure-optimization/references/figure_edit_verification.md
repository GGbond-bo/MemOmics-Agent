# 最小改动类改图的核验实录（像素差分 / OCR 边界 / 版式预检）

本文件是 SKILL.md「最小改动类请求」「长尾柱数值标签」「版式冲突算前预检」三节的实测细节。
场景：一张 5 面板 × 8 亚群的双向（Up/Down）柱图，用户连续四轮提改动 —— 每轮都必须证明"只改了我要改的地方"。

---

## 0. 四轮演进（每轮独立代次文件，不覆盖）

| 轮次 | 用户原话 | 改法 | 脚本 |
|---|---|---|---|
| 1 | 「在这个基础上做成 CNS 级别」「整体结构不变」 | 顶部家族带 + 左侧两级括号 + a–e 面板字母 + 共享图例 | `32_freescale_v2_top_left_optimized.py` |
| 2 | 「三个问题：①亚群跟来源重合 ②Aging 的 x 轴要统一标准有梯度 ③每根柱标基因数，贴近又不重合」 | 删双家族括号→单一 `MF` 模块竖带；统一 symlog 轴；80 个柱值标签按轴变换比例落位 | `33_MF_v3_unified_symlog_barvalues.py` |
| 3 | 「不需要 a,b 这些符号，其他的不变」 | `cp` 上一版 → 删 2 行 | `34_MF_v4_no_panel_letters.py` |

**代次命名**：`v2_optimized` → `v3_unified_symlog` → `v4_no_letters`（名字里带改动语义，回看时不用猜）。

---

## 1. 像素差分：本次的原始输出（可直接照抄格式）

```python
A = np.asarray(Image.open(v_prev).convert("RGB"), dtype=np.int16)
B = np.asarray(Image.open(v_new).convert("RGB"),  dtype=np.int16)
d = (np.abs(A - B).max(axis=2) > 8)
```

实测输出：

```
shapes: (1380, 2834, 3) (1380, 2834, 3) same: True
diff pixels = 2,229  (0.0570% of canvas)
diff bbox   = rows 169–203 (y-frac 0.122–0.147) | cols 364–2367 (x-frac 0.128–0.835)
x-clusters  = 5  -> widths/positions: [[364,387],[861,884],[1355,1378],[1850,1874],[2344,2367]]
bar-zone diff = 0 px   |   bottom-area diff = 0 px
VERDICT: 只有面板字母区域发生变化 ✓
```

**怎么读**：
- 5 簇、每簇 **23–24 px 宽** = 5 个孤立字母本体（宽 24 px ≈ 8.4 pt 粗体单字 @400dpi，合理）
- 簇间距均匀 ≈ 495 px = 面板等距（`PW + GAP`），进一步确认是"每面板一个字母"
- rows 169–203 对应 y-frac 0.122–0.147 → figure fraction 0.862 处的文字带 ✓
- **bar-zone = 0 和 bottom = 0 是硬指标**：柱区（y 0.25–0.80）与脚注区一个像素没动

**阈值**：`> 8`（单通道）。PNG 同参数重绘理论上可做到逐位相同；留 8 是为了吸收抗锯齿/压缩噪声。

**前提**：同 `figsize` + 同 `dpi` 才同 px 尺寸。画布被改过 → 先对齐再比，否则报"尺寸不一致"直接退出。

现成脚本：`scripts/pixel_diff_verify.py`。

---

## 2. OCR 的两个失效场景（本次实测）

### 2.1 孤立小字母 —— OCR 无法证明"删掉了"

删除前整图 OCR 能读出 `a b c d e`（与组名混在一起）；删除后**仍会读出一堆小写字母**
（`Up-regulated`、`Condition contrast`、轴名里全是小写）。**无法区分** → 证明不了删除。
→ 结论：**删除类改动一律用像素差分**。

### 2.2 旋转文字 —— 乱码 ≠ 渲染失败

左侧旋转 90° 的分组标签，整图 OCR 打出乱码片段（如 `Pure ƒber types` 被切碎）。
这是 **OCR 伪影**，不是字体缺失。验证方法：

```python
crop = img.crop((0, int(H*0.28), int(W*0.16), int(H*0.86)))   # 先裁到目标区
crop = crop.rotate(90, expand=True)                            # 转正（也可 -90，取决于方向）
crop = crop.resize((crop.width*2, crop.height*2), Image.LANCZOS)  # 放大 2×
crop.save("_check_left_band.png")                              # 再送 OCR
```

转正放大后即正常读出 `Pure fiber types` / `Derived` → 证明**文字真实渲染、无方块乱码**。

同理，顶部密集小字（家族超标题）也建议先裁带 + 放大 2.5× 再 OCR，否则整图 OCR 会漏读。

### 2.3 判断顺序（省时）

1. 要证明"**删掉了没 / 有没有多改**" → 像素差分（确定性）
2. 要证明"**文字渲染对不对 / 有没有方块**" → 裁切 + 转正 + 放大 → OCR
3. 两者都做不了（如矢量图无法直接读）→ 退到像素留墨率 + 颜色直方图 + 尺寸

---

## 3. 区域留墨率 + 尺寸自检（与出图同轮跑）

```python
a = np.asarray(Image.open(png).convert("RGB"))
nonwhite = (a < 245).any(axis=2).mean()
ncol = len(np.unique(a.reshape(-1, 3), axis=0))
W, H = Image.open(png).size
print(f"{W}x{H}px  {W/400*25.4:.1f} x {H/400*25.4:.1f} mm @400dpi")
print(f"non-white {nonwhite*100:.2f}%  colors {ncol}")
top  = a[int(H*0.03):int(H*0.16)]
left = a[int(H*0.30):int(H*0.85), int(W*0.001):int(W*0.13)]
print(f"top-band {((top<245).any(axis=2)).mean()*100:.2f}%  "
      f"left-band {((left<245).any(axis=2)).mean()*100:.2f}%")
```

本次实测：`2834x1380 px = 180.0 × 87.6 mm`，非白 **21.56%**，1319 色，
顶部条带 **9.59%**、左侧条带 **29.61%** → 两处"用户要求优化过的区域"确实有内容（不是空白）。

> 意义：用户会问"你优化过的那块地方到底有没有东西"。整图非白比回答不了这个问题，**分带留墨率才能**。

---

## 4. 统一 symlog 轴 + 十倍阶梯刻度（"刻度要有梯度"）

用户要「Aging 的衰老幅度要显出来」且「x 轴统一标准」时：**共享一根 symlog 轴 + 十倍阶梯**，
而不是每组独立 freescale（独立刻度会让 16,535 和 15 各自铺满面板，跨组不可比）。

```python
TMAX = float(max(UP_M.max(), DN_M.max()))       # 全局最大 = 16,535
XMAX = TMAX * 1.30
LINTHRESH = 1.0
LADDER = [0.0]
for k in range(1, 7):
    if 10.0 ** k <= TMAX:
        LADDER.append(10.0 ** k)
TICKS = sorted(set(LADDER + [-v for v in LADDER if v > 0]))   # 0,±10,±100,±1,000
TLAB  = [f"{abs(v):,.0f}" for v in TICKS]

ax.set_xscale("symlog", linthresh=LINTHRESH, linscale=1.0, base=10)
ax.set_xlim(-XMAX, XMAX)
```

- **注意**：`XMAX` 会打印成 6,783（≈ 5,218×1.3），这是**正确的** —— 16,535 是面板**合计**，
  单行最大值是 5,218，所以阶梯到 1,000 封顶。别把"合计"误当"最大柱"去配轴。
- `linthresh=1.0`：0 附近线性、两侧对数 → 0 值柱与 15 值柱都能看见。
- 对称轴（`±XMAX`）让 Up/Down 共用一把尺，双向可比。
- 底部脚注写上比例说明：`Unified symmetric-log scale across panels · decade ticks (0/10/10²/10³/10⁴) · |coef| > 0.25 & FDR < 0.05 · RSS and Specialized MF excluded`。

---

## 5. 柱值标签「贴近但不重合」的实现

```python
tr = ax.xaxis.get_transform()
f0 = float(tr.transform(0.0)); f1 = float(tr.transform(XMAX))
def frac(v, plus=True):
    fv = float(tr.transform(v if plus else -v))
    return (fv - f0) / (f1 - f0) if plus else (f0 - fv) / (f0 - float(tr.transform(-XMAX)))
```

- `frac(v) > 0.80` → 标签移入柱内（白字、右对齐、`xytext=(-2.2, 0)` offset points）
- 否则 → 柱外（柱色、`xytext=(+2.5, 0)`）—— 2.5 pt 是"贴近"的实测手感值
- `v == 0` → 4.2 pt 偏移，避开轴线

为什么必须用轴变换比例：symlog 轴下，数值 0.80 的"视觉位置"远不是画布宽度的 80%；
按数值比例判会把长尾标签全判到柱外 → 越界压轴 / 或全判到柱内 → 短柱白字看不见。

---

## 6. 版式冲突的算前预检（本次根因）

用户报「右侧亚群跟来源重合了」。根因不是字号，是**坐标区间重叠**：

- 亚群名 6.4–6.6 pt × 13 字符（如 `Pure Type IIX`、`OTUD1+(II)`），右对齐基准 `x = 0.090`
  → 文字**左缘 ≈ 0.094**
- 家族括号画在 `x = 0.150` → **括号在文字左侧**，两者必然压叠（实测已越过）

**修法（重排，不是微调）**：删掉「双家族彩色括号 + 旋转家族名」，改为**单一模块竖带**：

```python
X_AXNAME = 0.008        # 旋转轴名 "Subpopulation"
X_NAMES  = 0.090        # 亚群名右对齐基准
MF_L, MF_R = 0.098, LM  # 模块竖带（浅底 #F4F4F4 + 右缘 1.7pt 竖线 + 上下 0.8pt 横脚）
```

阅读顺序 = `轴名 → 亚群名（右对齐）→ MF 模块 → 柱形图`。
模块名旋转 90° 居中放在竖带里，与亚群名**不同 x 区间** → 结构上不可能压叠。

**通用判据**：新增文字/装饰线前，把两者的 x 区间（或 y 区间）列出来比一比；有交集就别画。
`figure fraction` 下估文字宽：`≈ 字号pt / 72 * 25.4 / 画布宽mm * 字符数 / 1000`（粗估，宁可留余量）。

---

## 7. 交付话术（用户会逐条核对）

每轮回复给出：
1. **改了什么**（对照表：用户问题 → 改法 → 核验证据）
2. **没动什么**（"柱区一个像素没动" + 数据总计逐项复核）
3. **数据复核**：面板总计逐项列出（本次 Aging 16,535↑/380↓、DM 125/144、Ex_Young 61/38、
   Ex_Old 231/1,091、Ex_DM 107/119），并给一条合计校验（Aging 8 亚群合计 16,915 ✓）
4. **产出清单**：PNG/PDF/SVG/TIFF + `_source_data.csv` + 脚本名，**带字节数**
5. **审查结果**：`rail_review(post)` passed / 警告（如 matplotlib 子模块未注册属误报，说明即可）
6. **跳过辩论的理由**（若跳过）：纯重绘、零新增参数、同议题已辩过