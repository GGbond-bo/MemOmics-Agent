---
name: sankey-alluvial-layout
description: >-
  桑基图／冲积图（Sankey/Alluvial）的节点布局与带宽保真度：间隙归一化、节点最小高度与高度守恒再分配、
  「带宽 ∝ 权重」被破坏后的量化与图注声明、节点条↔标签的渲染像素级对齐核验。
  触发：桑基图 / 冲积图 / Sankey / alluvial / 流图 / 节点太小 / 标签挂在两块之间 / 带宽 / _node height。
when_to_use: >-
  出或改**桑基图/冲积图**（亚群→基因、细胞类型→通路、多组共同 DEG 流图），
  尤其是节点权重极不均、出现细线节点、或用户说「标签跟色块不对齐」时。
  纯热图/UMAP/Violin 不需要（→ cns-visualization / matrix-heatmap-geometry）。
version: 1.0.0
author: MemOmics
license: MIT
platforms: [windows, linux, macos]
metadata:
  hermes:
    tags: [visualization, sankey, alluvial, geometry, matplotlib, publication]
    difficulty: intermediate
    language: Python+R
    category: bioinformatics
---

# 桑基图／冲积图布局与带宽保真度

桑基图的"难看"和"不对齐"几乎从不是配色问题，而是**节点高度归一化**与**自检口径**问题。
本 skill 固化 2026-10-01 实测（`43_sankey_3group_common_deg.py`，UP 版 10 亚群 × 7 基因 / 56 带，DOWN 版 × 2 基因 / 19 带）踩过的四个坑。

## 何时用

- 出/改桑基图、冲积图、流向图（亚群→基因、cluster→pathway、多组共同 DEG）
- 用户说：标签跟色块不对齐 / 名字掉到色块下面 / 节点太小看不见 / 带宽看不出差别
- 权重分布极不均（`max w / min w ≥ 5`）时**默认要过一遍下面的铁律 2**

## 铁律 1：间隙按「整列固定比例」，绝不用总权重数值当比例

```python
# ❌ 反例：把「总权重数值」当成了比例
gap = GAP * tot / (n - 1)      # UP 图 tot=102 → 间隙总和 2.244 > 1.0
usable = 1.0 - GAP * tot       # → usable = -1.244（负！）
h = usable * w / tot           # → 节点高度为负
```
后果链：节点高度为负 → 相邻节点区间**互相重叠**（`ITIH4 [1.00,1.27]` 压在 `MEF2C-AS1 [0.89,1.14]`）
→ 后画的色块盖住前一个的下半截，而标签仍画在"真实中心" → **顶端几个标签看起来掉到色块下沿**
（权重越大越严重：ITIH4 72 px / MEF2C-AS1 53 px / PALLD 27 px）。
⚠️ 隐蔽点：DOWN 图 `tot=24` 侥幸没变负 → **只有权重大的那张图暴露**，容易误判成"偶发渲染问题"。

```python
# ✅ 正解
gap    = TOTAL_GAP / (n - 1)   # TOTAL_GAP = 0.10（占整列的固定比例）
usable = 1.0 - TOTAL_GAP
```

## 铁律 2：节点最小高度 MIN_H + 高度守恒再分配

小节点按权重等比会被压成细线：`w=1, tot=102` → 高度 `0.90×1/102 = 0.0088` data 单位
≈ **9 px**，而 9.2 pt 标签 ≈ **38 px**（比值 0.24）→ 标签视觉上"挂在两个色块之间"（用户会报"没对齐"，
但中心点其实是**严丝合缝**的——所以只验中心的检查抓不到）。

**单位换算**：`1 data 单位 = axes高(in) / y跨度 × dpi`
例 `figsize=(11.2,7.6)`、`subplots_adjust(top=0.902,bottom=0.21)`、`ylim` 跨度 1.5
→ `1 unit = 7.6×0.692/1.5 × 300 = 1051.8 px`；`MIN_H ≈ 1.5 × 标签字高` → `0.055`。

```python
def layout(items, MIN_H=0.055, TOTAL_GAP=0.10):
    """低于下限的节点钉到 MIN_H，多出的高度按权重从其余节点扣回。
       迭代直到稳定（某节点可能在后一轮才跌破下限）→ 保证 Σh ≡ usable。"""
    tot, n = sum(w for _, w in items), len(items)
    gap, usable = TOTAL_GAP/(n-1) if n > 1 else 0, 1.0 - TOTAL_GAP
    mh = min(MIN_H, usable/n)                # ★ 节点极多时下限自动下压，保证装得下
    h, free, rest = [0.0]*n, list(range(n)), usable
    while free:
        wsum = sum(items[i][1] for i in free)
        pinned = [i for i in free if rest*items[i][1]/wsum < mh]
        if not pinned:
            for i in free: h[i] = rest*items[i][1]/wsum
            break
        for i in pinned: h[i] = mh; rest -= mh; free.remove(i)
    pos, y = {}, 1.0
    for i, (name, w) in enumerate(items):
        pos[name] = (y - h[i], y); y -= h[i] + gap
    return pos, tot
```

- **守恒验证**：`Σh` 必须 ≡ `usable`（实测两图均 947 px = 0.90 data 单位）→ 不溢出、不重叠。
- **色带无需另改**：`lspan = (y1−y0)/w` 是**逐节点**算的 → 钉底后色带自动跟随、仍精确填满节点。
- **效果实测**：最矮节点 `34 px → 54 px`（节点/标签比 `1.00 → 1.59`）；中心偏差仍 ≤1.0 px、重叠 0 对。

## 铁律 3：加 MIN_H = 牺牲「带宽 ∝ 权重」的严格性 → 必须量化 + 声明

钉底节点的「单位权重带宽」被放大，**跨节点比带宽不再等价于比权重**。这是 MUST 主动披露的副作用：

```python
base = usable * PX / tot          # 严格等比基线：1 单位权重 = 多少 px
amp  = (h_px / w) / base          # 节点实际 ÷ 基线 = 放大倍数
```

实测（MIN_H=0.055）：

| 列 | 触发钉底的节点 | 放大倍数 |
|---|---|---|
| UP 右·基因 | MYH2 (w=4) | **1.56×** |
| UP 左·亚群 | RSS (w=5) | 1.25× |
| DOWN 左·亚群 | RP_high(I) (w=1) | 1.47× |
| DOWN 右·基因 | 未触发 | 1.00× |

**交付口径（必须说出口）**：带宽**只在节点内部严格可比**，跨节点比较有 ≤N× 偏差；
论文正文已给括号数字（`基因 (22)`）时也必须写清。⚠️ 但**不要擅自往图里加图注声明**——先问用户
（"只改你点的那项，其余不动"的承诺优先）。

## 铁律 4：对齐只认「渲染成品像素」，恒等式自检会假 PASS

```python
# ❌ 恒等式：标签就是用同一个 (y0+y1)/2 画的 → 差值恒为 0，永远 PASS
dev = text_bbox_center_y - ax.transData.transform((LX, (y0+y1)/2))[1]
# ❌ 只验中心、不验高度：9 px 节点 vs 38 px 标签，中心对齐但视觉"挂着"
```
✅ 改为量交付的 300 dpi PNG（不看脚本变量）：
- 节点条定位：**整列最长竖向连续同色段**（图例小色块最长连续远小于节点条 → 不会被误选）
- 标签定位：墨迹色（`#222222`）在条带外侧 x 区间取行 band → ink bbox
- 判据：`|标签 band 中心 − 条带中心| ≤ 3 px`、**`节点高 ≥ 1.5 × 标签字高`**、相邻条带 0 重叠
- **A/B 量旧版备份**，把"修复前 → 修复后"的像素数字一起报（本例 34→54 px、1.00→1.59）
- 可复跑探针 → `scripts/render_pixel_audit.py`；完整配方与实测数字 → `references/sankey-node-layout-and-bandwidth.md`

⚠️ 右列若节点条与色带**同色**（本例 `cmap[3]` 两者共用），必须在条带自身 x 范围取样
（色带在 `RX−NODE_W` 处已收敛 → 条带中线处只有条带，不会被色带污染）。

## 交付与灰度

- 导出四格式：`png(300dpi) / svg(可编辑) / pdf(矢量) / tiff(300dpi)`，命名 `NN_<图名>_<UP|DOWN>.<ext>`
- 改名/改版前先备份旧产出到 `figures/_backup_<图名>_<版本>/`，便于 A/B 像素对照
- 黑白打印可辨性：相对亮度 `L*` 差 <10 即灰度下不可分（hex 必须 `int(hx[i:i+2],16)` 转 RGB，
  直接 `np.array('#7A7A7A')` 会得 `<U7` 字符串数组 → `ufunc 'divide' not supported` TypeError）

## 配套文件

- `references/sankey-node-layout-and-bandwidth.md` — 四个铁律的完整推导、全部实测数字（含 gap 负高度案例链、MIN_H 守恒证明、放大倍数表）、以及"用户说不对齐但中心实测 0.5 px"的排查顺序
- `scripts/render_pixel_audit.py` — 可直接复跑：从 PNG 里找条带列与标签 band，输出逐项中心偏差 / 高度比 / 重叠对数（不需要脚本任何变量）

## 交叉参考

- 热图（矩阵型）的同类几何问题、自校准修法、独立读数仲裁 → skill `matrix-heatmap-geometry`
- 用户脚本为基线的最小改动原则 → skill `user-script-figure-optimization`