# 火山图标注规则审计 —— 「这个基因效应量这么大，为什么没被标记？」

适用：用户拿着他自己认可的火山图（或你按他脚本复刻的版本）逐个点问。
原则：**用数字回答，不用形容词**。每条结论都要能指到脚本行号或表里某个格子。

---

## 0. 输入侦察（三条，30 秒，先做）

```python
import pandas as pd
p = "<用户指认的路径>"
xl = pd.ExcelFile(p)
print(xl.sheet_names)                                   # ⚠️ 别猜 sheet 名
d = pd.read_excel(p, sheet_name=xl.sheet_names[0])
print(list(d.columns), len(d))
print(f"fdr: {d.fdr.min():.2e} ~ {d.fdr.max():.4f}")    # 过滤生效？max 应 < 阈值
print(f"|coef| min: {d.coef.abs().min():.4f}")          # 过滤生效？min 应 ≈ 效应量阈值
print("celltype 数:", d.celltype.nunique())             # 表里几个 vs 图里几个
```

- **过滤是否真生效**看 `max(fdr)` 与 `min(|coef|)` 两个数，**不看文件名**（另见
  `volcano-panel-canvas-and-data-source.md` 的「过滤版 vs 全表版」）。
- `celltype` 个数常**多于图里的亚群数**（图只画其中 8 个，表里有 10 个）
  → 每个数字都要标口径，否则用户在图里找不到。
- 换文件前 `md5` 核对是否同一份，别把「同名不同版」当成新数据。

## 1. 从脚本里读出标注规则（唯一权威）

不要凭图猜规则，去读产生标签的那几行：

```
filter(fdr <= X)           ← ① 门槛：决定「谁有资格」
group_by(celltype, group)
arrange(desc(abs(coef)))   ← ② 排序键：只在门槛内的池子里排
slice_head(n = N)          ← ③ 取前 N 标名字
```

**filter 在 arrange 之前 ⇒ 门槛优先于效应量。**这一句就是用户问题的答案骨架。

## 2. 该基因自己的四个数

```python
d[d.gene == "<GENE>"][["gene","celltype","regulation","coef","se","z","fdr"]]
```

必看 `se`：效应量大而 FDR 不显著，八成是 SE 大。**拿它和同池已标基因比 SE 倍数** —— 倍数最直观。

## 3. 同一个基因换亚群再查一次

```python
d[d.gene == "<GENE>"][["celltype","regulation","coef","se","z","fdr"]].sort_values("fdr")
```

常见结局：**在亚群 A 显著性不够（门槛外），在亚群 B 过了门槛但 |coef| 排第 6（top5 之外）**
→ 两条路都堵。这个交叉验证比只讲一条路有说服力得多。

## 4. 量化「中等显著带」，判断用户是不是抓到了离群点

```python
MF8 = [...与图一致的亚群...]                    # 口径必须与图一致
for sh, nm in zip(xl.sheet_names, ["Aging","DM","Ex_Young","Ex_Old","Ex_DM"]):
    d  = pd.read_excel(p, sheet_name=sh)
    m8 = d[d.celltype.isin(MF8)]
    med = m8[(m8.fdr > 0.001) & (m8.fdr < 0.05)]
    poolmax = m8[m8.fdr <= 0.001].coef.abs().max()      # 已标池最大 |coef|
    print(nm, "中等显著行数:", len(med), "其中最大|coef|:", round(med.coef.abs().max(),3),
          "已标池最大|coef|:", round(poolmax,3))
```

判据：
- 被挡掉的行里**只有它一个** `|coef|` 超过已标池最大值 → **用户直觉对，是真盲区**，如实承认（不要替规则辩护）。
- 被挡掉的行**一批都差不多大** → 规则合理，把分布摆出来即可。

## 5. 工作实例（2026-09-30 · 人骨骼肌 · 5 对比 × 8 MF 亚群）

- 输入 `D:/我的下载/DEG_fdr05_coef025_5contrasts.xlsx`（已过滤 FDR<0.05 & |coef|≥0.25）
- sheet 名 = 对比字符串：`Y_Pre_vs_O_Pre / O_Pre_vs_OD_Pre / Y_Pre_vs_Y_Post / O_Pre_vs_O_Post / OD_Pre_vs_OD_Post`
- 列：`gene, celltype, regulation, coef, se, z, p, fdr, direction, n_cells, nRUV_used, method, comparison, coef_D, p_D, fdr_D`
- 规则（`task3/scripts/42_volcano5_8sub_FINAL.R:88–93`）：
  `filter(fdr<=0.001)` → `group_by(celltype, group)` → `arrange(desc(abs(coef)))` → `slice_head(n=5)`
- 颜色：过门槛 = `up_high` / `down_high`；`0.001<FDR<0.05` = `mid_sig_black`（图例 `Moderate Sig`）
  → **点在图上，只是没名字**

### 用户抓到的点：TMSB4X

| 基因 | 亚群 | coef | se | z | FDR | 结果 |
|---|---|---:|---:|---:|---:|---|
| TMSB4X | OTUD1+(I) Up | **+1.619** | **0.515** | 3.14 | 2.1e-03 | 门槛外 ✗ |
| PDLIM3 | OTUD1+(I) Up | +0.535 | 0.014 | 37.08 | 3.4e-297 | 同池第一 ✓ |
| MT-ND2 | LRP1B+(I) Down | −1.076 | 0.194 | −5.54 | 7.4e-08 | ✓ |
| TMSB4X | **LRP1B+(I)** Down | −0.651 | 0.109 | −5.99 | **6.5e-09** | 过门槛但排第 6 ✗ |

结论句：**SE 是同类基因的 36 倍 ⇒ z 只有 3.14 ⇒ 是「估算不稳的大效应」，不是确证的大效应**；
换亚群虽过了门槛，又输在 `|coef|` 排位（前 5 = 1.076 / 0.978 / 0.944 / 0.944 / 0.741）。
该点已作为黑点画在 OTUD1+(I) 上方。

### 离群性证据（8 亚群口径）

| 图 | 中等显著行数 | 其中最大 \|coef\| | 已标池最大 \|coef\| |
|---|---:|---:|---:|
| Aging | 10 | 0.564 | 1.379 |
| **DM** | **10** | **1.619（TMSB4X）** | 1.076 |
| Ex_Young | 2 | 0.341 | 0.642 |
| Ex_Old | 5 | 0.342 | 0.812 |
| Ex_DM | 6 | 0.288 | 0.760 |

除 TMSB4X 外，被挡掉的 32 行 `|coef|` 全 ≤0.564 → **只有 TMSB4X 是离群点，其余不标完全合理**。
（全 10 亚群口径下更极端的一例：Aging `AC020651.2`，RSS Down，coef −2.500 / se 1.234 / FDR 0.0495，
比已标池最大 1.379 大 81% —— 但 `RSS` 不属于那 8 个亚群，**不在该图里**，必须主动说明，
否则用户去图上找会找不到，反而更困惑。）

## 6. 收尾规矩

- 规则要不要改属于**会改交付物**的决定 → `ask_user(kind="intent")` 给互斥选项，**不要在正文末尾用问句**
- 重出图时保留旧版目录（如 `figures/_deprecated_8inch_unfiltered/`），别原地覆盖
- 纯查询 / 只读核对回合**不要新增产出文件**，汇报里明确写「本次无新增产出」