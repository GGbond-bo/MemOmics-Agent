# v5 正本零差异复现配方（2026-09-11 收官）

**结论**：专利 v5 正本 `v5_substitutability_all.csv` 的猴输入 = `E:/专利/monkey_ageDA_continuous.csv`（5,674,190 tiles，0-based half-open），
配 **正本原版 `anchor()`**（first-overlap-wins 语义）。零差异复现达成：**16031 / 1904 / 3487 / 7562 / 3078**。
all 版（`M2/monkey_ageDA_all.csv`，5,296,656 tiles，1-based）已被证伪。

---

## 一、复现配方（全量路径）

| 组件 | 路径 |
|---|---|
| 复现脚本 | `results/<sid>/scripts/v4_anchor_continuous_check.py`（正本 anchor 逐字复刻） |
| 猴 tile 输入 | `E:/专利/monkey_ageDA_continuous.csv` |
| 人 tile 输入 | `E:/专利/M2/human_ageDA_all.csv` |
| ortholog 表 | `E:/专利/P3_L1_data/monkey_human_orthologs_full.csv`（3 列：macaque_gene_id / human_gene_id / human_symbol） |
| 猴基因坐标 | `E:/专利/P3_L1_data/GCF_037993035.2_T2T-MFA8v1.1_feature_table.txt.gz`（`gene` 行：p[6]=chrom, p[7]=start, p[8]=end, p[14]=symbol, p[15]=GeneID） |
| 人基因坐标 | `E:/专利/P3_L1_data/human_ortholog_hg38_full.csv`（有 cid 的行才可用；空坐标行须跳过） |
| 正本原脚本 | `E:/专利/P3_L1_data/repro_m3_from_M2.py`（V4 跨物种衰老可替代性算法，anchor 语义的 ground truth） |

**关键常量**：`WINDOW = 2000`（±2kb，与 L1 一致）。

## 二、正本 anchor 语义（逐字照抄，禁止自创）

```python
mid = (s + e) // 2                 # tile 中点
lo, hi = mid - WINDOW, mid + WINDOW
idx = np.searchsorted(starts[chrom], hi, side='right') - 1
found = None
while idx >= 0:                    # 向前回溯
    gs_, ge_, (gid, sym) = starts[chrom][idx], ends[chrom][idx], meta[chrom][idx]
    if ge_ < lo:
        break
    if gs_ <= hi and ge_ >= lo:    # 首个重叠基因即中选（first-overlap-wins）
        found = gid
        break
    idx -= 1
```

聚合：`Z = Σ sign(r)·Φ⁻¹(1 − p/2) / √n`（Stouffer，`p = max(p, 1e-300)` 防下溢）；
`class`：A=同向且双侧 |Z|≥1.96；B=反向且双侧 |Z|≥1.96；C=仅一侧 |Z|≥1.96；D=双侧均 <1.96。

## 三、逐位核验脚本（验收标准）

```python
import pandas as pd, numpy as np
p   = pd.read_csv(".../v4anchor_continuous_pairs.csv")          # 复现产出
can = pd.read_csv("E:/专利/P3_L1_data/v5_substitutability_all.csv")  # 正本
m = can.merge(p, on='symbol', how='outer', suffixes=('_can','_new'), indicator=True)
print(dict(m._merge.value_counts()))          # 期望 {'both': 16031}（独有两侧均 0）
b = m[m._merge == 'both']
for c in ['Z_monkey','Z_human','n_tiles_m','n_tiles_h']:
    d = (b[c+'_can'] - b[c+'_new']).abs()
    print(c, d.max(), int((d > 1e-9).sum()))  # 期望 max|Δ|=0、非零个数 0
Zm, Zh = b.Z_monkey_new.values, b.Z_human_new.values
sig = (np.abs(Zm) >= 1.96) & (np.abs(Zh) >= 1.96)
cls = np.where(sig & (Zm*Zh > 0), 'A', np.where(sig & (Zm*Zh < 0), 'B',
      np.where((np.abs(Zm) >= 1.96) ^ (np.abs(Zh) >= 1.96), 'C', 'D')))
print(dict(pd.Series(cls).value_counts()))    # 期望 7562/3487/3078/1904（C/B/D/A）
```

**实测结果**：merge `{'both': 16031, 'left_only': 0, 'right_only': 0}`；四个统计列 max|Δ| 全 0；
`p_monkey / p_human` max|Δ| ≤ 3.4e-21（纯浮点存储精度）；class 不一致 0 个。

## 四、残差归因三判据（19 对残差的完整闭环）

| 判据 | 实测 | 推论 |
|---|---|---|
| 缺失 symbol 是否在 ortholog 表 | 66/66 在 | ❌ 不是 ortholog 表缺行 |
| 是否出现在另一输入版本输出（all 版） | 0 个 | ❌ 不是输入表差异 |
| 换回正本 `anchor()` 后残差 | 归零（16012 → 16031） | ✅ **属锚定实现层** |

## 五、两输入文件"非同一测量"的判定

两文件是**两次独立 DA 计算**，不是同一数据的两种坐标写法：

- 0-based 对齐后，all 的 5,296,656 个 tile **全部**能在 continuous 找到坐标对应（continuous 另多 377,534 个 tile）
- 但 tile 级 `r`: **corr = 0.8906、mean|Δr| = 0.1063、max|Δr| = 0.611**；r/p/q 三列 **99.99% 数值不同**
- all 做坐标修正（`fix_ageDA_coords.R`）后**行数不变**（5,296,656）⇒ 坐标改写**不产生新 tile**，continuous 不可能由 all 坐标换算得到
- 时间链自洽：`monkey_ageDA_continuous.csv`(9/4 01:05) → 正本 v5 写入(9/4 12:41)

## 六、all 版证伪对照表

| 指标 | 正本 | continuous（正本 anchor） | all 版 |
|---|---|---|---|
| ortholog 对 | 16031 | **16031（零差异）** | 16010 |
| A / B / C / D | 1904 / 3487 / 7562 / 3078 | **逐项一致** | 2335 / 3070 / 7677 / 2928（A +431, +22.6%） |
| 加权 Spearman ρ | −0.081 | — | −0.1949 |
| perm_mean_A | 2012.71 | — | 2617.1（Δ +604.4） |
| 与正本 class 不一致 | — | 0 / 16031 | 6803 / 15963（42.6%） |

## 七、L2 辩论裁决（用作结论背书）

8 角色（正 3 / 反 4 / 裁判 1）：`verdict = support`，`confidence = medium`
（rubrics：证据质量 7 / 效应量 9 / 可重复性 6）。裁判 missing 清单中
「生成脚本血缘、66 残差溯源、比对键唯一性」已由本文档的零差异复现补齐。

## 八、对外复现说明的写法

必写：正本使用 **0-based continuous 猴 tile 表 + first-overlap-wins 锚定语义**；
并注明风险边界——**改用 1-based all 表或改写锚定语义，A 类将偏差 +431 对（+22.6%）**。
