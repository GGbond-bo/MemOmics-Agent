# 病例：桑基图标签↔色块不对齐（UP 图专属）

> 2026-10-01 实测，memomics-afd2d418，`scripts/43_sankey_3group_common_deg.py`
> （三组共同 DEG 流向图，亚群 ↔ 基因，UP/DOWN 成对）。
> 用户原话：「亚群和基因，要跟自己对应的色块对齐啊」——**只有 UP 图看着不对**。

## 症状

基因名标签"掉"到自己色块的**下沿**，越靠列顶越严重（实测偏差 ITIH4 **72 px**、
MEF2C-AS1 **53 px**、PALLD **27 px**）；列下方 4 个基因完全对齐。
DOWN 图（同样的代码、同样的节点数）**看起来正常**。

⚠️ 第一反应会去调"标签偏移量" —— **错**。标签画在节点的真实中心，没有偏移。

## 根因（一行数学）

```python
GAP = 0.022
gap    = GAP * tot / (n - 1)     # tot = 权重之和：UP 图 = 102
usable = 1.0 - gap * (n - 1)     # = 1.0 - 0.022 * 102 = -1.244
```

- `usable = -1.244`（负）⇒ 每节点高度 = `weight/tot * usable` < 0
  ⇒ **相邻节点区间互相重叠**：ITIH4 `[1.00, 1.27]` 与 MEF2C-AS1 `[0.89, 1.14]` 叠了 0.14。
- 绘制顺序是"先算区间、再逐个画色块" ⇒ 后画的色块盖住前一个的下半截；
  而标签在**后处理阶段按真实中心**画 ⇒ 视觉表现为"标签没跟色块对齐"。
- **为什么 DOWN 没事**：`tot = 24` ⇒ `usable = 1.0 - 0.022*24 = 0.472 > 0`，无重叠。
  ⇒ 「只错一张图」正是**布局归一化 bug 的签名**（病例具有 `tot` 依赖），不是标签 bug 的签名。

## 修复

```python
gap    = 0.10 / (n - 1)   # 全列固定 10% 用于间隙
usable = 0.90             # 其余 90% 按权重分配
```

UP（tot=102）与 DOWN（tot=24）**同一套参数**都稳定，无需按图分别调。

## 内置自检（修完就固化进脚本，防止静默回归）

```python
# 在布局函数内部：算出每个节点的 [y0, y1] 与色块中心
# ① 相邻重叠对数
overlaps = sum(1 for i in range(n - 1) if spans[i][0] < spans[i+1][1])
# ② 标签中心 vs 色块中心（像素）
for i, name in enumerate(names):
    dev_px = abs(label_center_px[i] - block_center_px[i])
    assert dev_px <= 1, f"{name}: label/block 偏差 {dev_px:.2f}px"
# ③ 列标题与顶端节点间距 > 0
assert title_gap_px > 0
assert overlaps == 0
```

实测结果：两图标签↔色块中心偏差 **0.00 px**、相邻节点重叠 **0 对**、
列标题间距 210 / 287 px 无重叠 → 通过后才 `savefig`。

✅ **断言通过即视为完成**：本轮之后又反复裁剪/重看图片，触发了系统的循环检测强制干预
（"连续多轮重复几乎相同的操作"）。像素级断言是比肉眼更强的证据 —— 通过就交付。

## 定位痕迹（可复用的调试手法）

| 手法 | 具体做法 |
|---|---|
| 局部裁剪 | 裁顶部区域成 `figures/_tmp_up_top.png`、`_tmp_up_topleft/topright.png` 放大看 |
| 打印区间 | 在 `layout_dbg(w, tag)` 里打印 `usable` 与每节点 `[y0,y1]`，重叠一眼可见 |
| 逐版备份 | 重出前 `figures/_backup_sankey_v5/`（此前已有 v2/v4）→ 可逐版对照 |

## 交付（本用户惯例）

- 四格式 ×2 图、300 dpi：`43_sankey_3group_common_{UP,DOWN}.{png,svg,pdf,tiff}`
- 汇报口径 = 根因 + 修复 + 自检数字 + 产物路径（不要只说"已修好"）