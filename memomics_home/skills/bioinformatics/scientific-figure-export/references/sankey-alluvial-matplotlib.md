# Sankey / Alluvial（左类别 → 右类别）：零依赖 matplotlib 配方 + 版式坑

场景：把一张**长表**的「A 类别 → B 类别」归属关系画成流带图 ——
亚群 → 基因、cluster → treatment、细胞类型 → 通路、来源 → 结局。
触发词：`桑基图` / `桑葚图`（中文常见错写，同样命中）/ `Sankey` / `Alluvial` / `冲积图` /
`左边X 右边Y`（如「左边亚群、右边基因」）。

> 图型选择的通行做法在 cns-visualization（Sankey 条目）；**本文件是版式与导出段**：
> 布局算法、图例裁切坑、导出后 OCR 自检。

---

## 1. 为什么手绘而不是用库

`plotly`（要 kaleido 导图）/ `ggalluvial`（要装 R 包）/ `networkD3`（要 htmlwidgets）
都能画，但**零依赖方案更稳**：只要 matplotlib，布局、配色、标签位置全部可控，
且不会在多格式导出（SVG/PDF/TIFF）上出意外。2026-10-01 实跑沉淀（见 §7）。

## 2. 数据模型（先聚合，再画）

```python
# 原始长表 [celltype, gene, contrast] → 想表达「哪几个条件同时支持这一对」
agg = (raw.groupby(["celltype", "gene"])
          .agg(n_contrast=("contrast", "nunique"),
               contrasts=("contrast", lambda x: "+".join(sorted(x))),
               mean_coef=("coef", "mean"))
          .reset_index())
```

🔴 **带宽语义 = 该「左-右」对被几个条件共同支持（1/2/3）**，不是简单的出现次数。
一张图同时回答两个问题：①长什么链路 ②哪些链路是跨条件共识（深色粗带）。
比「每个条件画一张小图」信息密度高，比「三张图叠一起」干净。
**共识带的数量本身就是结论**：本例 Down 侧 0 条三条件共识 ⇒ 下调以条件特异为主。

## 3. 布局算法（关键：左右**各自**归一）

```python
def layout(items):            # items = [(name, weight), ...] 已排好序
    tot = sum(w for _, w in items)
    n = len(items)
    gap = GAP_L * tot / max(n - 1, 1) if n > 1 else 0
    usable = 1.0 - gap * (n - 1)
    pos, y = {}, 1.0
    for name, w in items:
        h = usable * w / tot
        pos[name] = (y - h, y)
        y -= h + gap
    return pos, tot
```

- 🔴 两侧**分别**用各自总权重归一 —— 共用全局比例时，节点少的那侧只占一小段，
  整个图歪向一边、流带全部倾斜。
- 节点排序：左侧按**生物学分档**（纯肌纤维型 → 混合型 → 特殊），档内按权重降序；
  右侧按权重降序。按字母序读者看不出结构。

## 4. 流带 = 三次贝塞尔带

```python
def bezier(ax, x0, y0a, y0b, x1, y1a, y1b, color, alpha):
    cx = (x1 - x0) * 0.45          # 控制点水平外扩，0.4~0.5 最自然
    verts = [(x0,y0a), (x0+cx,y0a), (x1-cx,y1a), (x1,y1a),
             (x1,y1b), (x1-cx,y1b), (x0+cx,y0b), (x0,y0b), (x0,y0a)]
    codes = [Path.MOVETO, Path.CURVE4, Path.CURVE4, Path.CURVE4,
             Path.LINETO, Path.CURVE4, Path.CURVE4, Path.CURVE4, Path.CLOSEPOLY]
    ax.add_patch(PathPatch(Path(verts, codes), facecolor=color,
                           edgecolor="none", alpha=alpha, zorder=2))
```

每个 pair 在**左节点内占一段、右节点内占一段**，用游标从上往下分配：

```python
lcur  = {c: lpos[c][1] for c in lorder}                  # 游标 = 节点上沿
lspan = {c: (lpos[c][1]-lpos[c][0]) / lw[c] for c in lorder}
for _, r in agg.sort_values(["n_contrast", "celltype"]).iterrows():
    y0b = lcur[ct]; y0a = y0b - w * lspan[ct]; lcur[ct] = y0a    # 左端向下吃
    y1b = rcur[g];  y1a = y1b - w * rspan[g];  rcur[g]  = y1a    # 右端同法
```

⚠️ **同一节点内的多个 pair 必须排序后再分配**，否则带子交叉打结。
按 `n_contrast` 排能把「共识带」集中到节点上下两端，视觉更整齐。

## 5. 配色

- 带宽颜色 = **支持度**（红系 Up：`{3:'#A50026',2:'#F46D43',1:'#FDBE85'}`；
  蓝系 Down：`{3:'#08519C',2:'#4292C6',1:'#C6DBEF'}`），透明度 3 组 0.80 / 其余 0.55。
- 左节点颜色 = **类别分档**（纯肌纤维型 `#7A7A7A` / 混合型 `#B08A5A` / 特殊 `#5A8AA5`），
  让读者一眼看出「共识链路集中在哪一类」。
- 节点条 `edgecolor="white", linewidth=0.7` 做视觉分隔。

## 6. 🔴 图例裁切坑（本配方踩过，通用，必看）

**症状**：`ax.legend(ncol=1)` 放在 axes 下方（`bbox_to_anchor` 负 y），
设计 4 行（title + 3 条目），**导出 PNG 里只有 2 行**，后两条被裁掉。

🔴 `bbox_inches="tight"` **拦不住**这种裁切 —— 因为 legend 与画布内其他 artist
（如 `transAxes` 定位的脚注文字）重叠，tight bbox 算出来仍不够。
（本例文件 990 KB、非空白、通道极值正常 —— **一切健康检查都过**，只有 OCR 能抓到。）

**修法（四条一起做）**：

```python
leg = ax.legend(handles=h, loc="upper left", bbox_to_anchor=(-0.005, -0.030),
                frameon=False, fontsize=8.8, ncol=3,          # ← ① 一律横排
                title="...", title_fontsize=9)
leg.get_title().set_fontweight("bold")
leg.get_title().set_position((0, 0))                           # ← ② 标题左对齐
ax.add_artist(leg)                                             # ← ③ 叠加第二个 legend 必须这行
fig.subplots_adjust(left=0.01, right=0.99, top=0.99, bottom=0.21)   # ← ④ 底部留 ≥0.20
```

多组图例用**两行**（第一行支持度、第二行类别）；别指望一行塞两组横排 —— 会横向重叠。
（可选：图例信息并入画布内 `ax.text`，用 fig/axes 坐标手工排，更抗裁。）

## 6b. 🔴 顶部裁切 & 文本重叠（2026-10-01 v2 实测，与 §6 是一对）

§6 是「底部图例被裁」，**顶部同样会裁**，但成因完全不同 —— 同一张图会先后踩到两次。

### (1) 主标题被画布顶裁掉

v1 写法：主标题在**轴坐标系**、贴近 `ylim` 上沿

```python
ax.set_ylim(-0.06, 1.10)
ax.text(0.5, 1.085, ttl, ha="center", va="bottom")   # ← v1：文字从 1.085 往上画，越过画布顶
```

`va="bottom"` 让文字**向上**排版，1.085 之上只剩 0.015 数据单位 ⇒ 上半被切。

**OCR 证据**（不看 OCR 会以为标题正常）：`…共同上调基因×来源亚群` 里的 `×`
被读成 `?`（笔画被切掉才误读），且 OCR 报的标题 y 坐标比**第一个节点标签**还大（更靠下）。

✅ **v2 修法（两条一起做）**

```python
# ① 主标题移到 figure 坐标系 + va="top"（向下排版，永不越界）
fig.text(0.5, 0.972, ttl, ha="center", va="top",
         fontsize=13.5, fontweight="bold", color="#111111")
fig.subplots_adjust(left=0.01, right=0.99, top=0.925, bottom=0.21)   # top 让出 7.5%

# ② 轴内列标题与首行标签留距
ax.set_ylim(-0.06, 1.20)          # v1 是 1.14；上沿留 0.20 余量
ax.text(LX - 0.014, 1.105, "Subcluster", ha="right", va="bottom", ...)   # v1 是 1.045
# 节点布局仍从 y=1.0 开始不动 ⇒ 列标题与首行标签中心相隔 ≥0.10 数据单位
```

### (2) 🔴 OCR「混读」= 两个文本重叠的**确定性判据**

列标题与首行标签撞在一起时，OCR **不会**返回两条文本，而是返回**一条拼接乱串**：

| 状态 | OCR 输出 | 判读 |
|---|---|---|
| 修前 | `PurSupe山ster` @(331,221) | = `Subcluster` + `Pure Type I (10)` 叠在同一 y ⇒ **重叠** |
| 修后 | `Subcluster` @(632,348) **与** `Pure Type I (10)` @(532,474) | 各自独立、y 拉开 ⇒ 通过 |

⇒ **判据：某条 OCR 文本若由两个预期标签的片段拼接而成，就是重叠，不是 OCR 识别噪声。**
不要把它当噪声放过 —— 这是唯一能廉价抓到「两个 label 撞一起」的探针：
文件大小、非空白判定、通道极值、唯一色数**全都看不出来**（本例三项健康检查全过）。

**定位技巧**：整图 OCR 已能发现；**裁顶部 20% 并放大 1.6–2×** 再 OCR，置信度更高、坐标更准：

```python
from PIL import Image
im = Image.open(png); W, H = im.size
im.crop((0, 0, W, int(H*0.20))).resize((int(W*1.6), int(H*0.20*1.6)), Image.LANCZOS)\
  .save("_tmp_top.png")      # 交给 vision_describe
```

（用完删临时图，别留在 figures/ 里。）

### (3) 图内文字一律英文 —— 用户定稿偏好（2026-10-01）

用户明确要求「**把图中说明文字改成英文**」⇒ **本类图默认直接出英文版**，
不要先出中文版再等用户回来改。标题 / 列名 / 图例 title + 条目 / 脚注 / 单位，一处不留。
字体同步换成 `["Arial", "Helvetica", "DejaVu Sans"]` —— 英文图不必挂中文字体，
也顺带规避「中文字体缺符号字形」那类静默失败（见 SKILL.md 静默失败三坑）。

**中→英对照表（本例实译，可直接复用）**

| 中文 | 英文 |
|---|---|
| 三组运动共同上调基因 × 来源亚群 | Upregulated genes shared by 3 exercise contrasts × source subclusters |
| 亚群 / Subcluster | Subcluster |
| 共同上调基因（Up, n=7） | Shared up genes (Up, n=7) |
| 流带宽度 = 共同支持度（该「亚群–基因」对被几个条件同时支持） | Ribbon width = number of exercise contrasts supporting the subcluster–gene pair |
| 3 个条件同时显著（三组共同） | Significant in all 3 contrasts |
| 2 个条件同时显著 / 1 个条件显著（单组） | Significant in 2 contrasts / Significant in 1 contrast |
| 亚群类别 | Subcluster category |
| 纯肌纤维型亚群 / 混合型亚群 / 特殊亚群 | Pure fiber type / Mixed fiber type / Specialized |
| 括号内数字 = 该亚群/基因在所有流带中的总支持度｜数据：FDR<0.05 且 \|coef\|≥0.25（bayesglm/glmer） | Numbers in parentheses = total support across all ribbons \| Data: FDR < 0.05 and \|coef\| ≥ 0.25 (bayesglm / glmer) |

## 7. 字体与导出

```python
plt.rcParams["font.sans-serif"] = ["Arial", "Helvetica", "DejaVu Sans"]   # 英文图（默认）
plt.rcParams["axes.unicode_minus"] = False
# 中文图才需要：["Microsoft YaHei", "SimHei", "DejaVu Sans"]
for ext, kw in [("png", dict(dpi=300)), ("svg", {}), ("pdf", {}), ("tiff", dict(dpi=300))]:
    fig.savefig(f"{name}.{ext}", bbox_inches="tight", facecolor="white", **kw)
```

四格式齐出（矢量 SVG+PDF 投稿 / 300dpi 栅格 PNG+TIFF）＝用户对出图的默认要求。

## 8. 出图后必须自检（本配方就是靠它抓出裁切 bug）

```python
vision_describe(image_path="<导出 png>", question="列出图中所有文字标签与图例条目")
```

逐条核对：

| 核对项 | 判据 |
|---|---|
| 左/右侧标签数 | = 实际类别数（漏一个就是被裁或重叠） |
| 图例条目数 | = 设计条目数（**不是**「看到几条算几条」） |
| **标题完整性** | 全文能逐字读出，**且特殊符号（`×`、`–`、`≥`）没被读成 `?` 之类** —— 笔画缺失才会误读，是顶部被裁的信号（§6b） |
| **有无「混读」** | 任何 OCR 字符串若由两个预期标签片段拼成（如 `PurSupe山ster`）= **两个 label 重叠**，不是识别噪声（§6b） |
| 标题 / 脚注 | 在不在（顶部问题裁 20% 放大 1.6× 再 OCR 更准） |
| 空白面板 | 通道极值 + 唯一色数（`Image.open(f).convert("RGB").getextrema()`） |

**只看「文件 >5KB / 非空白」不够** —— 残图也能有 472–990 KB。
判读参考：`vision_describe` 返回的 OCR 文本条数应与「预期文字总数」可比，
条数偏少就是有元素没渲染出来。

## 9. 可复现实例

`results/<sid>/scripts/43_sankey_3group_common_deg.py`（2026-10-01，human skeletal_muscle）：
三组运动对比（Young/Old/DM × Pre/Post）**共同显著 DEG** × 来源亚群。
- Up：7 基因 / 56 带（6 条三组共识）
- Down：2 基因 / 19 带（**0 条三组共识** → 下调以条件特异为主）
- 附 `results/43_sankey_links_3group_common.csv`（链路明细：哪几组支持 + 平均 coef）