---
name: flow-diagram-geometry
description: >-
  桑基 / 流向图（Sankey、Alluvial、冲击图）的几何与文字碰撞控制：两侧节点数悬殊时的独立归一化布局、
  链路流量守恒与交叉控制、宽度语义的图注防误读、列标题 / 图例 / 脚注三类文字碰撞的修法，
  以及用 OCR 坐标 + 像素行带法验收文字是否重叠。触发：桑基图 / 桑葚图 / 桑基 / Sankey / alluvial /
  流向图 / 冲击图 / 两侧节点数悬殊 / 标签被压住 / 文字重叠 / 列标题重叠 / 图例和脚注挤在一起。
when_to_use: >-
  画或改「左=类别A、右=类别B」的流向图（亚群→基因、细胞类型→通路、条件→marker 等），
  尤其是两侧节点数悬殊、标签多、或需要把链路宽度编码成共现数/支撑度时。
  矩阵热图走 matrix-heatmap-geometry；UMAP / Violin / DotPlot 不需要本 skill。
version: 1.0.0
author: MemOmics
license: MIT
platforms: [windows, linux, macos]
metadata:
  hermes:
    tags: [visualization, sankey, alluvial, flow, geometry, publication, matplotlib]
    difficulty: intermediate
    language: Python
    category: bioinformatics
---

# 流向图（桑基）几何与文字碰撞控制

桑基图"难看"几乎从不是配色问题，而是**几何问题**：两侧高度怎么定、链路怎么排、标签往哪放。
本 skill 把实测踩过的坑固化成铁律 + 核验流程。

> 用户口中的 **"桑葚图" = 桑基图（Sankey）** —— 按此理解，不要反问。

## 何时用

- 画/改 Sankey、Alluvial、冲击图：左=亚群/细胞类型，右=基因/通路/marker，宽度=共现或支撑度
- 用户说：桑葚图 / 桑基图 / 流向图 / "基因来自哪个亚群" / "左边X右边Y"
- 图已出但标签被压住、图例和脚注挤一行、右轴窄成一条缝
- 需要把"几组条件共同支持"这种离散量编码成宽度

## 三条布局铁律

### 1. 两侧**各自独立归一化**，不要用全局总权重

⛔ 统一定高度 → 节点少的一侧缩成缝（实测：右轴 2 个基因 vs 左轴 10 个亚群时几乎不可读）。
✅ 左右各自按本侧总权重归一填满 0→1：

```python
def layout(items):                     # items: [(name, weight)]
    tot = sum(w for _, w in items); n = len(items)
    gap = 0.022 * tot / max(n - 1, 1) if n > 1 else 0
    usable = 1.0 - gap * (n - 1)
    pos, y = {}, 1.0
    for name, w in items:
        h = usable * w / tot
        pos[name] = (y - h, y); y -= h + gap
    return pos, tot
```

实测收益：右轴仅 2 节点时各占约 **44%** 高度，标签清晰可读。

### 2. 流量守恒靠**每侧游标从节点顶部推进**

```python
lcur = {c: lpos[c][1] for c in lorder}          # 左节点内游标（从上往下）
rcur = {g: rpos[g][1] for g in rorder}
lspan = {c: (lpos[c][1]-lpos[c][0]) / lw[c] for c in lorder}
rspan = {g: (rpos[g][1]-rpos[g][0]) / rw[g] for g in rorder}
for _, r in agg.sort_values(["n_contrast", "celltype"]).iterrows():
    y0b = lcur[ct]; y0a = y0b - w*lspan[ct]; lcur[ct] = y0a      # 左
    y1b = rcur[g];  y1a = y1b - w*rspan[g];  rcur[g] = y1a      # 右
    bezier(ax, LX+NODE_W, y0a, y0b, RX-NODE_W, y1a, y1b, cmap[w], alpha)
```

链路**先按 `(宽度, 左节点名)` 排序再画** —— 同名链路在节点内连续，长距离交叉显著减少。
链路用三次贝塞尔带（`Path.CURVE4` ×3 + `CLOSEPOLY`），`edgecolor="none"` 防抗锯齿缝。

### 3. y 轴要**预留三段独立空间**

```
[主标题 fig.text(0.5, 0.972)]
        ↕  ≥0.20 数据单位
[列标题 y ≈ 1.21]      ← 左"类别"列名 / 右"Shared … genes (n=)"
        ↕  ≥0.20 数据单位
[节点区 y 1.0 → 0]     ← ylim 上沿必须 ≥1.30，否则最高节点标签顶到列标题
[图例 1（宽度语义）] → [图例 2（类别配色）]  ← 占 axes 负空间
[脚注 1 / 2]           ← 必须走 figure 坐标，别塞 axes 负空间
```

## 三类文字碰撞（全部实测踩到，逐条给修法与验收）

| 碰撞 | 根因 | 修法 | 验收 |
|---|---|---|---|
| **顶部节点标签 ↔ 列标题** | 节点区 y 从 1.0 起，列标题仅在其上 0.105 | `ylim` 上沿 1.20→**1.34**；列标题 y 1.105→**1.21** | OCR 坐标从重叠 11px → **分离 106px** |
| **脚注 ↔ 图例第二行** | 脚注写在 axes 负坐标(-0.19)，而图例同占 axes 负空间(-0.125 / -0.030) | 脚注改 **figure 坐标**锚底：`fig.text(0.5, 0.044 / 0.016, …, va="top")` | 图例 y=2044 → 脚注 y=2150 / 2206，三行分离 |
| 主标题 ↔ 轴顶 | 主标题走 `fig.text(0.5, 0.972)` 在轴外 | `subplots_adjust(top=0.925→0.902)` 调低轴顶 | 主标题与列标题不再拥挤 |

**口诀：axes 负空间是图例的默认地盘，脚注不要往里塞。** `bbox_inches="tight"` 会自动扩展画布（不会截断），所以脚注锚 figure 底部是安全的。

## 宽度语义必须写进图内图例（防误读）

宽度用离散量（"该类别对被几个条件共同支持"，1–3 三档）时：

- 图例标题写成**完整句子**：`Ribbon width = number of exercise contrasts supporting the subcluster–gene pair`
- 脚注补口径：`Genes = intersection of all 3 …; ribbons = subclusters in which the gene is significant`
- 否则读者/审稿人会把宽度读成**效应量或强度** —— 这是该图型最常被攻击的点

## 口径决策：严格交集 + 功效不均衡必须明示

多个条件取交集时（"三组都显著"），**不要因为结果太少就静默放宽**：

1. 保持用户原话的口径（严格交集）画主图；
2. 在图注写明是**严格交集**（防被读成全基因组/全条件结论）；
3. 在汇报里**主动给出两侧样本量差**——实测：年轻组下调基因仅 19 个 vs 老年组 918 个，
   交集被样本量小的那组卡到只剩 2 个基因。这是功效差异，不是"共同调控弱"；
4. 把"是否放宽到 ≥2 组"作为**用户的选项**提出，不擅自改主图。

## 核验：OCR 坐标法 + 像素行带法（纯文本模型可用）

`vision_describe` 返回的 OCR 条目带 (x, y) —— **同类文字两条 y 差 < ~25px 即判重叠**
（9pt 文字在 300dpi 下高约 38px）。

- 全图 OCR **漏掉**某个标签 = 强信号：它被邻近文字压住了。实测权重最大的标签 `ITIH4 (22)` 起初完全没被检出，正是被列标题压住。
- 拿不准就裁局部放大 2–3x 单独 OCR（`Image.crop(...).resize((w*2, h*2), Image.LANCZOS)`），坐标更干净。
- **修完必须复跑 OCR 比对坐标**，不能凭"看起来好了"下结论。
- 配套 `scripts/figure_health_check.py`：一次给出尺寸 / ink 占比 / 唯一色数 / 文字行带区间，
  行带间距 < 阈值自动报警（我实测就是靠"右轴顶部只有一条 48px 行带却要装两行文字"定位到重叠的）。

判读参考值（桑基图）：节点多的一侧 `ink ≈ 0.25–0.30 / uniq ≈ 6000+`；节点少的一侧
`ink ≈ 0.14 / uniq ≈ 900` 属正常（留白多），**不判空白**。

## 迭代纪律

1. **重跑前先查是否已有产出**：`ls -l figures/ | grep <关键词>` 看 mtime —— 实测发现"新任务"其实 2 分钟前已出过 v2，先核验现状再决定改什么，避免整轮重画。
2. 改版前备份 `figures/_backup_<名>_vN/`，脚本头注明 `vN: 改了什么`，可回退。
3. 交付四格式：`png(300dpi)` + `svg` + `pdf` + `tiff(300dpi)`，统一 `bbox_inches="tight", facecolor="white"`。
4. 顺手导出链路明细 CSV（`类别A, 类别B, n_共同, 支持组合, mean_coef`）—— 图上看不出的支撑度数字都在表里，也便于复核。

## 抗锯齿与导出一致性

```python
ax.add_patch(PathPatch(Path(verts, codes), facecolor=color, edgecolor="none", alpha=alpha, zorder=2))
fig.savefig(f, bbox_inches="tight", facecolor="white", dpi=300)   # png/tiff 传 dpi；svg/pdf 不传
```

- 节点条 `edgecolor="white", linewidth=0.7` —— 期刊惯例，消除相邻节点粘连。
- 链路 `zorder=2`、节点 `zorder=3`，保证节点压住链路端头。
- 右轴节点用**最深档**色（如 `cmap[3]`），避免整列浅色看不清。

## 配套文件

- `references/sankey-3group-common-deg.md` — 完整实战案例（人骨骼肌三组运动共同 DEG「亚群→基因」桑基图）：确切参数、坐标实测表、碰撞定位全过程、结果数字
- `scripts/figure_health_check.py` — 出图后一键体检：尺寸 / ink / 唯一色 / 文字行带区间 + 行带过近报警