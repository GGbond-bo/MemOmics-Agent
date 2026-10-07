# 多面板组合图：QA 探针 + 骨架构型（2026-09-29 实测沉淀）

本文件服务 `scientific-figure-export` 的**交付段**：图已画好之后，
怎么证明它真的是对的、以及怎么避免在收尾环节反复折腾。

---

## 一、交付前 QA 探针（三件套，一次跑完，不要重跑）

```python
from PIL import Image
import numpy as np, os

def qa_multipanel(png, grid=(4, 3), ink_min=1.0):
    """返回 (非白占比, 唯一色数, 分块墨量矩阵)。任一块 < ink_min ⇒ 该区空白。"""
    with Image.open(png) as im:
        im.load()
        a = np.asarray(im.convert("RGB"))
    nonwhite = (a < 245).any(axis=2).mean() * 100
    ncol = len(np.unique(a.reshape(-1, 3), axis=0))
    H, W, _ = a.shape
    R, C = grid
    ink = np.array([[(a[i*H//R:(i+1)*H//R, j*W//C:(j+1)*W//C] < 245)
                     .any(axis=2).mean() * 100 for j in range(C)] for i in range(R)])
    print(f"size={a.shape[1]}x{a.shape[0]}  non-white={nonwhite:.2f}%  colors={ncol:,}")
    print("tile ink%:\n", np.round(ink, 2))
    blank = np.argwhere(ink < ink_min)
    if blank.size:
        print("!! 空白 tile（行,列）:", blank.tolist())
    return nonwhite, ncol, ink


# 用法：qa_multipanel("fig_cns_landscape.png")   # 4 行 × 3 列切块
```

### 判据表

| 指标 | 通过 | 失败含义 |
|---|---|---|
| 非白占比 | ≥5% | <1% ⇒ 几乎全白（真空白图） |
| 唯一色数 | >1000 | =1 ⇒ 单一色渲染失败 |
| 文件大小 | ≥5 KB | <5 KB ⇒ 疑似空白（**这个判据单独用不可靠**） |
| **分块墨量** | 每块 ≥1% | 任一块 <1% ⇒ **该 panel 空白**（最灵敏） |
| 输出像素 | 在 `figsize×dpi` 的 15% 内 | 超出 ⇒ `bbox_inches='tight'` 被越界元素撑大 |

### 为什么"文件大小 + 整体非白占比"不够

本会话早前真实踩过：一张 **61.9 KB** 的图，整体**非白 0.0%、唯一色 1 种**（完全空白，
因为出图时从已重启清空的 kernel 内存取数），却被当作"通过健康检查"汇报。
文件大小骗人（61.9 KB 只是 PNG 头的体积），整体占比也被其他 panel 掩盖。
**分块墨量图 + 唯一色数**是能在汇报前抓住这类问题的组合。

---

## 二、收尾纪律：探针通过即停

```
导出 4 格式 → 跑一次 qa_multipanel → 跑一次 rail_review(post)
   → 有数字且全达标 ⇒ 汇报交付，结束
   → 任一指标不达标 ⇒ 修一处 → 重出 → 只再跑一次探针
```

**禁止**：对同一张已通过的图做第二次、第三次像素核对；重复量尺寸；反复重存格式。
本会话因对同一 TIFF 连续重复校验触发系统循环检测强制中断——
重复验证烧 token，且会被判为循环失控。**一次数字 → 报数字 → 交付。**

---

## 三、Windows TIFF 压缩坑（含修复）

| 步骤 | 结果 |
|---|---|
| matplotlib `savefig(..., .tiff, dpi=600)` | 成功，但**不压缩**：183×152 mm → **72 MB**，4649×3877 px |
| `Image.open(p)` → `im.save(p, compression="tiff_lzw")` | ❌ `OSError: [Errno 22] Invalid argument`（句柄占用） |
| tmp 文件 + `os.replace(tmp, p)` | ❌ `PermissionError: [WinError 5] 拒绝访问` |

✅ **修复（按成本从低到高）**

1. **直接交付未压缩 TIFF** —— Nature 位图上限 300 MB，72 MB 完全可用。
   压缩是优化，不是合规必需。（**首选**）
2. **另存新文件名**：`<stem>_lzw.tiff`，不碰原路径。需要两份时用这个。
3. 非得同路径：`with Image.open(p) as im: im.load(); buf = im.copy()` 后写到另一个名字，
   再用系统命令替换。收益 < 成本，默认不做。

> 教训：把"压缩 TIFF"当成必做项会白烧两轮。**先判断它是不是合规必需**。

---

## 四、组合图骨架：hero + 3 证据面板

适用于"定量网格"类论文图（Nature 双栏 183 mm）。

```
┌──────────────────────────────────────────────┐
│  HERO（全宽，语义双编码）                     │  高 ~55%
├──────────────┬──────────────┬────────────────┤
│ 证据面板 1   │ 证据面板 2   │ 证据面板 3     │  高 ~45%
└──────────────┴──────────────┴────────────────┘
```

**hero 面板用语义双编码**（一个 mark 承载两个维度）：

- **面积** = 比例 / 计数（`r = Rmax * sqrt(frac)`，别用线性半径——面积才与量成正比）
- **颜色** = 方向 / 偏倚（发散色阶，如 蓝→中灰→红）
- 加**面积图例**（25% / 50% / 100% 参考圆）+ **色条**，否则读者无法反推数值

**每个证据面板只承担一条独立证据**，不做重复编码。三种通用辅助构型：

| 构型 | 何时用 | 一眼要看出什么 |
|---|---|---|
| 区间堆积条 | 分布被挤到极端（如 p 值塌到下溢） | 某一档吃满 → 分布异常 |
| 分布脊线 | 比较多个分组的同一指标分布 | 峰位置与宽度差异 |
| 分组对比条 | 证明两件事"脱钩" | 两根柱等高 → 无关联 |

**配色克制**：一套中性灰 + 一个信号色族 + 一个强调色族；白底；去 top/right spine；
字号 7 pt 轴标 / 8 pt panel 字母（`A` `B` `C` `D` 加粗，用 `transAxes` 定位）。

**导出契约**：`svg.fonttype="none"`（文字可编辑）+ `pdf.fonttype=42` + PNG 300 dpi
+ TIFF 600 dpi，`bbox_inches="tight"`, `facecolor="white"`。

---

## 五、本会话实例（细胞级 DEG 全景图）

- 输入：5 个对比工作簿，每本 11 个 sheet；**只读 `ALL_merged` 即可**（它已含全部亚群），
  比逐 sheet 读省一个数量级的 IO —— 先确认聚合sheet存在再决定读法
- hero：5 对比（行）× 10 亚群（列）圆矩阵，面积 = FDR<0.05 占比，颜色 = 上调比例
- 辅面板：p 值区间堆积条 / |效应量| 分布脊线 / 「全部基因 vs 显著基因」中位对比条
- 结果：2324×1938 px、非白 17.71%、3034 色、分块墨量 6.94–34.52%（无空白 panel）
- 图传达的结论：显著性由分母驱动而非效应量 —— **图好看 ≠ 结论可用**，
  交付时必须说清哪个面板是"证据"、哪个是"警告"