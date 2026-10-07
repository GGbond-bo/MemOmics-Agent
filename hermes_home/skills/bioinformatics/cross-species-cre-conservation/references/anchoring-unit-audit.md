# 锚定单元审计 —— 重复计数 / 归属歧义 / 覆盖率分母

> 2026-09-13 实测（`memomics-7839e23a`）。触发场景：① 要报「锚定单元数 n」（如 1–4952）进 claim / 说明书之前；
> ② 用户或审查员问「跨物种同源窗口与基因窗口重叠会不会导致重复计数」；③ 需要为 n 的分母口径辩护。

---

## 一、现行锚定机制（`scripts/06_repro_full_pipeline.py::anchor()` L173–212）

```
tile (chr, start, end, r, p)  ← 人/猴 ageDA 表，宽度恒定 499bp
  mid = (start + end) // 2
  lo, hi = mid - WINDOW, mid + WINDOW          # WINDOW = 2000（±2kb）
  idx = searchsorted(starts, hi, 'right') - 1   # 从 start ≤ hi 的最后一个基因起，向前扫
  while idx >= 0:
      if ge_ < lo: break                        # 越出窗口 → 停
      if gs_ <= hi and ge_ >= lo:
          found = gid; break                    # ★ 命中即 break → 单次赋值
      idx -= 1
  acc.setdefault(found, []).append((r, p))      # 每 tile 至多进一个基因的列表
```

**关键点**：窗口是**围绕 tile 中点**开的（不是围绕基因 TSS）；人侧基因表只取**正交基因子集**
（`HUMAN_BED = human_ortholog_hg38_full.csv`，16,158 个）。

---

## 二、审计三问（报 n 之前必须能回答）

### ① 重复计数？—— 不存在，且可证

| 检查 | 方法 | 实测（2026-09-13） |
|---|---|---|
| 正交表多对一 | `monkey_human_orthologs_full.csv` 26,501 行计数去重 | 猴 gene 唯一 26,501（**0 重复**）；人 gene 唯一 16,161，唯一重复项 = **空字符串（10,341 行）**，非空人 gene **全部唯一** |
| 输出表基因重复 | `v5_substitutability_all.csv`（16,010 行）`symbol` 去重 | **0** |
| 输出表配对重复 | `(Z_monkey, Z_human)` 完全重复 | **0** |
| Σn 守恒 | Σ`n_tiles_h` vs 全基因组 tile 数 | **2,432,901 ≤ 5,555,247** ✓（Σ`n_tiles_m` = 1,610,487 ✓） |

**代码级证明**：`anchor()` 命中即 `break` ⇒ 每 tile 至多写入一个 `acc[gid]` ⇒ 同一 tile 不可能进入两个基因的 Z 聚合。
跨物种侧 `bridge_and_pairs()` 遍历 `bridge.items()`（dict，键 = 猴 gene，天然唯一）⇒ 每猴 gene 恰产出一行。
⇒ **`Σ n ≤ tile 总数` 恒成立。**

> ⚠️ **空 human_gene_id 的正确解读**：10,341 行（39.0%）空值 = **未匹配的猴基因**（静默丢弃），
> **不是**多对一重复。因为 26,501 − 10,341 = 16,160 ≈ 非空唯一人 gene 数 16,160 ⇒ 非空部分是严格 1:1。

### ② 归属歧义？—— 存在，1.02%

复刻 `anchor()` 逻辑但**去掉 break**，统计每个 tile 的候选基因数（chr1 全量 443,121 tiles）：

| 状态 | tile 数 | 占比 |
|---|---|---|
| 未锚定（候选 0） | 230,809 | 52.1% |
| 唯一命中（候选 1） | 207,774 | 46.9% |
| **归属歧义（候选 ≥2）** | **4,538** | **1.02%** |
| 最大候选数 | 3 | — |

⇒ ±2kb 窗口落在 ≥2 个正交基因内的 tile（典型成因：双向启动子、嵌套/重叠基因、基因密集区）。
`anchor()` 按「start 最大者优先」贪心挑一个 ⇒ **归属取决于基因表排序，不取决于生物学**。

**处置建议（写进统一网格权项 S1.5）**：网格单元唯一编号；多基因归属时打 `multi_map=1` 标记；
把「剔除 `multi_map` 单元」作为敏感性分析一档报出。

### ③ 覆盖率 / n 的分母口径？—— 43.8%

`Σ n_tiles_h` = **2,432,901** / 全基因组 5,555,247 = **43.8%**（chr1 实测未锚定率 52.1%，两者一致）。
原因 = 锚定仅在**正交基因子集**（16,158 个）内进行，非正交基因邻近的 tile 全部丢弃。

⇒ **说明书写「锚定单元数在 1–4952 间变化」时必须写明分母口径**（仅正交基因窗口内 tiles），
否则会被质疑为选择偏置（未锚定区并非随机分布，偏向低基因密度/基因间区）。

---

## 三、n 分布与量级自检（`v5_substitutability_all.csv`，16,010 基因）

| 列 | min | P25 | P50 | P75 | P90 | P99 | max | sum | 均值 |
|---|---|---|---|---|---|---|---|---|---|
| `n_tiles_h`（人） | 1 | 28 | 65 | 158 | 347 | 1,384 | **4,952** | 2,432,901 | 152.0 |
| `n_tiles_m`（猴） | 1 | 22 | 50 | 112 | 228 | 789 | **3,011** | 1,610,487 | 100.6 |

- max/min = **4,952 倍**，与「1–4952 间变化（5000 倍）」的口径声明一致 ✓
- tile 宽度恒 **499bp**（min = P50 = 均值 = 499）⇒ **n ∝ 基因跨度**；n=4,952 ⇒ 跨度 ≈ **2.47Mb**
  （与 DMD / RBFOX1 / CNTNAP2 量级相符）—— 这是「n 大 ⇒ 长基因」的独立佐证

---

## 四、顺手完成审查要求的「阈值依赖核查」（4.49 倍核查）

同一脚本即可算完，**无需独立实验**（这是审查意见「4.49 倍均值单独核查是否被少数超大元件驱动」的直接答案）：

| 口径 | 强效应池 \|Z_h\|≥12 均值 | 非强效应池均值 | 倍数 |
|---|---|---|---|
| 全量 | **524.0** | **116.2** | **4.51×**（复现专利声称的 4.49） |
| **剔除 `n_tiles_h` top1%（>1384）** | — | — | **3.73×**（仍 > 2 门槛） |

⇒ **判定：不是被少数超大元件驱动**，该审查项可结题。

---

## 五、可直接复用的代码骨架

```python
import os, csv
import numpy as np, pandas as pd

L1, M2 = r"E:/专利/P3_L1_data", r"E:/专利/M2"

# ---- ① 正交表多对一 ----
mc, hc = Counter(), Counter()
with open(os.path.join(L1, "monkey_human_orthologs_full.csv"), encoding='utf-8-sig') as f:
    for row in csv.DictReader(f):
        mc[row['macaque_gene_id'].strip()] += 1
        hc[row['human_gene_id'].strip()]   += 1
print("猴 gene 重复:", sum(1 for v in mc.values() if v > 1),
      "| 人 gene 唯一重复项:", hc.most_common(1))     # ('', 10341) = 未匹配，非多对一

# ---- ② ③ 输出表 n 分布 + Σn 守恒 ----
v5 = pd.read_csv(os.path.join(M2, "pipeline_out/v5_substitutability_all.csv"))
print(list(v5.columns))       # ★ 先读列名！实际是 Z_monkey/Z_human/n_tiles_m/n_tiles_h
print("symbol 重复:", v5['symbol'].duplicated().sum(),
      "| (Z_m,Z_h) 重复:", v5.duplicated(subset=['Z_monkey','Z_human']).sum())
print("Σn_h =", v5['n_tiles_h'].sum(), "vs 总 tile 5,555,247")

# ---- ④ chr1 归属多重性（复刻 anchor 但去掉 break）----
chroms = {}
with open(os.path.join(L1, "human_ortholog_hg38_full.csv"), encoding='utf-8-sig') as f:
    rd = csv.reader(f); next(rd)
    for row in rd:
        try: gid, chrom, st, en = row[0], 'chr'+row[1], int(float(row[2])), int(float(row[3]))
        except (ValueError, IndexError): continue
        chroms.setdefault(chrom, []).append((st, en, gid))
for c in chroms: chroms[c].sort()                     # ★ 必须 sort（searchsorted 前提）
g = chroms['chr1']
starts = np.array([x[0] for x in g]); ends = np.array([x[1] for x in g])
W, mids = 2000, []
for ch in pd.read_csv(os.path.join(M2, "human_ageDA_all.csv"),
                      usecols=['chr','start','end'], chunksize=1_000_000):
    q = ch[ch['chr'] == 'chr1']
    if len(q): mids.append(((q['start'].values + q['end'].values)//2).astype(np.int64))
mid = np.concatenate(mids)

mult = np.zeros(len(mid), dtype=np.int16)
for i, m in enumerate(mid):
    lo, hi = m - W, m + W
    k = int(np.searchsorted(starts, hi, side='right')) - 1
    cnt, step = 0, 0
    while k >= 0 and step < 60:                       # ★ 上限防嵌套基因长扫
        if ends[k] < lo: break
        if starts[k] <= hi: cnt += 1
        k -= 1; step += 1
    mult[i] = min(cnt, 32767)
print("未锚定 %.1f%% | 唯一 %.1f%% | 歧义 %d (%.2f%%) | 最大候选 %d"
      % ((mult==0).mean()*100, (mult==1).mean()*100, (mult>=2).sum(),
         (mult>=2).mean()*100, mult.max()))
```

**量级断言（上线前必加）**：`assert 1e6 < Σn_h < 6e6`、`assert (mult>=2).mean() < 0.05`
—— 任一不过 = 锚定实现有问题（参见 SKILL.md 的「三个静默失败 bug」）。

---

## 六、本次踩到的坑

| 坑 | 症状 | 修复 |
|---|---|---|
| **按记忆假设列名** | `v5.duplicated(subset=['Zm','Zh'])` → `ValueError: not enough values to unpack (expected 2, got 0)`（0 列匹配）中断一次 | 任何 DataFrame 操作前先 `print(list(df.columns))`；实际列 = `symbol / Z_monkey / Z_human / p_monkey / p_human / n_tiles_m / n_tiles_h / same_direction / S / class` |
| `mult` 扫描无上限 | 嵌套/重叠基因处可能长距离回扫 | `while ... and step < 60` 上限 |
| 基因坐标表未排序 | `searchsorted` 结果无意义（可塌约 1000 倍） | 载入后立即 `chroms[c].sort()`（`groupby` 不保证组内有序） |

---

## 七、产物坐标（本次）

| 类型 | 路径 |
|---|---|
| 报告 | `results/memomics-7839e23a/results/待补项5_重复计数核查_20260913.md` |
| 中间数据 | `results/memomics-7839e23a/data/chr1_tile_mult.npy` |
| 图 | `results/memomics-7839e23a/figures/Fig_dupcheck_A_n_tiles_distribution.png`（n 分布 + 倍数对比）<br>`results/memomics-7839e23a/figures/Fig_dupcheck_B_assignment_multiplicity.png`（归属多重性） |
