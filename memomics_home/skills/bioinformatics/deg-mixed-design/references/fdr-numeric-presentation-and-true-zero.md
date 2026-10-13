# FDR 数值呈现陷阱：「0.0000」≠ 无显著（DEG 交付表）

**来源**：2026-10-01 用户确认（本类项目 `D:/肌肉锻炼/DEG_file/merged_*_vs_*.xlsx`，5 比较组 × 8 亚群），
用户原话大意：「FDR 列 97.9% 的格在 Excel 里显示 0.0000，**我以后可能会用到，这些你沉淀了嘛**」。

## 1. 症状

用户打开交付的 `.xlsx`，FDR 列**几乎整列都是 `0.0000`**，目视像「这个分析什么都没检出来 / 表是空的」。
而实际：真值小到 **1e-51** 量级，只是 Excel 的默认「常规」格式**显示不出来**。

## 2. 三个必须分开的候选解释（先判别再解释）

| 候选 | 判别 | 处置 |
|---|---|---|
| **A. 显示问题**（最常见）：值很小但非 0，Excel 常规格式对 `< 0.00005` 一律显示 `0.0000` | 读原始值是否 `> 0` 且极小 | **只改显示层**（列格式 / 导出格式），⛔ 不动数值 |
| **B. 双精度下溢真 0**：极端小的 p 在下溢后存成字面 `0.0`（本次约 **4.5k 行**） | `(v == 0).sum()` 严格相等 | 保留为 0（它表达的就是「小到测不出」），汇报时说明口径 |
| **C. 检验本身能产出真 0**：小样本非参数检验在完全分离时 p 可等于最小可达值甚至 0（见 `nonparametric-discrete-floor-and-null-defense.md`） | 与设计字典 / 检验族对照 | 属**正常结果**，不是数据缺失 |

> ⚠️ 三种解释的界面上**长得完全一样**，只能靠原始值判别 —— 这正是本坑的杀伤力来源。

## 3. 判别代码（一次跑完，别逐列肉眼比）

```python
import numpy as np, pandas as pd

df = pd.read_excel(path, sheet_name=None)          # 多 sheet（每对比一片）时全读
for name, d in df.items():
    col = [c for c in d.columns if "FDR" in c.upper() or "adj" in c.lower()]
    for c in col:
        v = pd.to_numeric(d[c], errors="coerce").dropna()
        n, z = len(v), int((v == 0).sum())
        nz = v[v > 0]
        print(f"{name:28s} {c:12s} n={n:6d} 真0={z:5d} ({z/n*100:5.1f}%) "
              f"非零最小={nz.min() if len(nz) else float('nan'):.3e} "
              f"log10min={np.log10(nz.min()) if len(nz) else float('nan'):.1f} "
              f"q<0.05格数={(v < 0.05).sum()}")
```

本次实测形态：**显示为 `0.0000` 的格 ≈ 97.9%**；其中非零最小 ≈ `1e-51`；真 0 ≈ **4,478 行（合计约 4.5k）**。

## 4. 导出配方（交付给用户打开的表）

```python
# 方案 1：导出时该列字符串化（最稳，任何 Excel/WPS 版本都显示对）
out[c] = v.map(lambda x: f"{x:.3e}" if pd.notna(x) else "")

# 方案 2：保留数值 + 设单元格格式（可继续排序/筛选）
from openpyxl import load_workbook
wb = load_workbook(path); ws = wb["Sheet1"]
for row in ws.iter_rows(min_col=ci, max_col=ci, min_row=2):
    for cell in row:
        cell.number_format = "0.00E+00"
```

⛔ **不要把真 0 改写成 `1e-300` 之类的占位值** —— 那会改变数值语义（下溢 0 与「小到不可表示」都该保留原样）；
⛔ 也不必重跑分析 —— 这是**呈现层**问题，与统计结果无关。

## 5. 交付话术（一句话把歧义消掉）

> 「FDR 列的 `0.0000` 不是『没显著』：真值多在小到 1e-51 量级（Excel 常规格式显示不出来），另有约 4.5k 行是双精度下溢的
> 真 0。本对比 **q<0.05 共 N 格**，以原始值为准。」

汇报显著数**一律给 `q<0.05` 的格数**（代码算），⛔ 不目视表格数、不写「大部分不显著」。

## 6. 与 FDR 检验族的关系

本文件只解决**呈现**；判「谁该带星号」仍走 SKILL.md 的检验族口径（族名必须从**代码**核验、
族不得切到 <20 格、离散下界与两堵墙）—— 两件事不要混：**呈现错会让人以为没信号，族口径错会让人以为有信号。**