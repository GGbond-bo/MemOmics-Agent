# 桑基 / 冲积图布局几何（matplotlib 手绘）

实体案例：`memomics-afd2d418 · 43_sankey_3group_common_deg.py`（三组运动对比共同 DEG × 源亚群，
左节点=亚群、右节点=基因、带宽=该"亚群–基因"对被几个对比共同支持）。

---

## 一、完整失败链（一次典型返工，4 轮才对）

```python
# ❌ 初版：tot 是权重总和（UP 图 = 102），被误当比例系数
gap    = GAP * tot / (n - 1)     # 0.022 * 102 / 9 = 0.2493
usable = 1.0 - gap * (n - 1)     # = 1 - 0.022*102 = -1.244  ❌ 负
```

| 步 | 后果 |
|---|---|
| ① | `usable` 为负 → 每节点高度 `h = usable*w/tot` 为负 |
| ② | `pos[name] = (y-h, y)` 头尾反转、游标 `y -= h+gap` 方向不稳 |
| ③ | **相邻节点区间重叠**：ITIH4 `[1.00,1.27]` 压在 MEF2C-AS1 `[0.89,1.14]` 上 |
| ④ | 后画的色块遮住前一个的下沿（白描边仍在 → 看着像正常分隔，不显眼） |
| ⑤ | 标签画在真实中心 `(y0+y1)/2` → 视觉上"掉"到色块下沿 |

**选择性症状（关键陷阱）**：同脚本 DOWN 图 tot=24 → `usable=0.472` **侥幸为正**、完全正常。
用户只说"up 图里标签把 ITIH4 压下来了" → 极易误判为"个别标签位置问题"去调字号/坐标。
**正确第一动作：算出两张图的 `usable`，是负数就直接改 layout。**

```python
# ✅ 正确
TOTAL_GAP = 0.10
gap    = TOTAL_GAP / (n - 1) if n > 1 else 0
usable = 1.0 - TOTAL_GAP
```

产物：`usable` 从 −1.244（UP）/ 0.472（DOWN）→ 两图统一 0.90；`max|dy| = 0.00px`、`重叠 = 0 对`。

---

## 二、三项几何自检（可直接抄）

```python
fig.canvas.draw(); rend = fig.canvas.get_renderer()
n_l, n_r = len(lorder), len(rorder)

# ① 列标题 vs 顶端标签 / 主标题 的像素间距（>0 = 无重叠）
top_lab = ax.texts[n_l]                  # 右轴第一个标签 = 权重最大元素
t_right = ax.texts[n_l + n_r + 1]        # 右轴列标题
g_gene = t_right.get_window_extent(rend).y0 - top_lab.get_window_extent(rend).y1
g_ttl  = fig.texts[0].get_window_extent(rend).y0 - t_right.get_window_extent(rend).y1

# ② 标签中心 vs 自己元素中心（Bbox 无 get_center → 自己算）
def _tcy(t):
    b = t.get_window_extent(rend); return (b.y0 + b.y1) / 2
dev = []
for i, c in enumerate(lorder):
    y0, y1 = lpos[c]
    cy = ax.transData.transform((LX, (y0 + y1) / 2))[1]
    dev.append((f"L:{c}", _tcy(ax.texts[i]) - cy))
for j, g in enumerate(rorder):
    y0, y1 = rpos[g]
    cy = ax.transData.transform((RX, (y0 + y1) / 2))[1]
    dev.append((f"R:{g}", _tcy(ax.texts[n_l + j]) - cy))
worst = max(dev, key=lambda t: abs(t[1]))
print(f"标签↔色块中心偏差 max|dy| = {abs(worst[1]):.2f}px ({worst[0]})")

# ③ 相邻节点重叠对数（必须 0）
ov = [f"{seq[i]}/{seq[i-1]}" for seq, posd in ((lorder, lpos), (rorder, rpos))
      for i in range(1, len(seq)) if posd[seq[i]][1] > posd[seq[i-1]][0] + 1e-9]
```

**注意 `ax.texts` 的顺序** = 添加顺序：先 n_l 个左标签 → n_r 个右标签 → 左列标题 → 右列标题。
索引写错会量到别的对象（本案例 `ax.texts[n_l]` 正好是右轴第一个标签）。

---

## 三、像素级核验（纯色段扫描）

```python
import numpy as np; from PIL import Image
a = np.array(Image.open(png).convert("RGB")).astype(int)

def mask_of(rgb, tol=10):
    return (np.abs(a - np.array(rgb)).sum(axis=2) <= tol)

def segments(mask, xcol):                       # 取一列，找连续像素段
    ys = np.where(mask[:, xcol])[0]
    segs, s = [], ys[0]
    for i in range(1, len(ys)):
        if ys[i] != ys[i-1] + 1:
            segs.append((s, ys[i-1])); s = ys[i]
    segs.append((s, ys[-1]))
    return [(y0, y1, y1-y0+1) for y0, y1 in segs]   # 段中心 = (y0+y1)/2
```

判读要点：

1. **OCR 的 y = 文本框顶边**，中心 ≈ y + 半行高（9.2 pt @300dpi ≈ 38 px → 约 +19 px）。口径不统一会白改一轮。
   本案例用统一口径后：下方 4 个基因偏差 −8~−9 px（= 对齐），上方 3 个 +23/+46/+62 px（= 真错位）。
2. **同色相邻元素会被白描边切成多段** —— 段数 = 元素数时才可用段边界当元素边界。
3. **`px_per_unit` 标定**：先用两个"确认不重叠"的元素算比例
   （本案例 LDB3 与 MYH2：Δ坐标 0.3069 → Δ像素 323 → 1052 px/单位），
   再反推可疑元素应有高度（ITIH4 应 282 px，实测段仅 134 px ≈ 50% → 确证被上层盖住）。

---

## 四、定稿版式常量（可当模板）

| 参数 | 值 |
|---|---|
| 画布 | `figsize=(11.2, 7.6)`, `dpi=150` → 保存 `dpi=300` |
| 坐标 | `xlim=(-0.30, 1.30)`、`ylim=(-0.06, 1.44)` |
| 节点 | `NODE_W=0.022`、`TOTAL_GAP=0.10`；节点系总高 1.0（顶 y=1.0 → 底 y=0.0） |
| 列标题 | 轴坐标 `y=1.32`（`va="bottom"`）；主标题 `fig.text(0.5, 0.972, va="top")` |
| 图例 | `bbox_to_anchor=(-0.005, -0.030)` / `(-0.005, -0.125)`，`frameon=False`, `ncol=3` |
| 脚注 | `fig.text(0.5, 0.044)` / `fig.text(0.5, 0.016)`，`ha="center", va="top"` |
| 边距 | `subplots_adjust(left=0.01, right=0.99, top=0.902, bottom=0.21)` |
| 导出 | 循环 4 格式：`png(dpi=300)` / `svg` / `pdf` / `tiff(dpi=300)`，`bbox_inches="tight"`, `facecolor="white"` |
| 字体 | `font.sans-serif = ["Arial","Helvetica","DejaVu Sans"]`；`axes.unicode_minus=False` |

**列标题上移联动**（"顶端标签被列标题压住"的修法）：`ylim` 上沿与列标题 y **同步抬**，
改完用自检 ① 复验（本案例 288 → 394 px，分离 106 px）。

---

## 五、本案例的图注口径（防误读，写进图注）

- 链路宽度 = 该「亚群–基因」对被**几个运动对比共同支持**（1/2/3，图例标注），**不是**效应量
- 基因 = 三组对比的**基因层面严格交集**；链路 = 该基因在哪些亚群中显著
- 阈值 FDR < 0.05 且 |coef| ≥ 0.25（bayesglm / glmer）
- 括号内数字 = 该节点总支持度（跨所有链路的权重和）
- ⚠️ 交集口径的**功效不均衡**要在正文点明：本例 Y_EX 下调仅 19 个基因 vs O_EX 918 个 → 交集被卡到只剩 2 个