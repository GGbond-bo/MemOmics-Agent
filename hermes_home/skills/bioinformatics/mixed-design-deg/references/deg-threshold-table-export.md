# 阈值筛选后的 DEG 结果表交付（多 sheet xlsx）与踩坑

> 来源：2026-09-29 实测（人骨骼肌运动项目，5 个对比组 × 10 亚群，新方法 = 细胞级 glmer + RUVr）。
> 用户原话：「按照 `fdr<0.05, |coef|>0.25` 这个阈值，帮我把五个表合适的基因都筛选出来，然后做成一个表，
> 五个表格分别都是 sheet1,2,3,4,5，然后根据自己的比较组命名。能做吗？」

这是**已定阈值之后**的下游交付动作 —— 属线性操作，⛔ **不要触发辩论**（用户明确要求「不要什么都辩，该做就直接做」）。

---

## 一、标准做法（可直接照抄的骨架）

```python
# 输入：D:/肌肉锻炼/DEG_file/merged_<对比组>.xlsx，sheet='ALL_merged'（10 亚群长表）
# 输出：一个 xlsx 的 5 个 sheet，sheet 名 = 比较组名
FDR_CUT, COEF_CUT = 0.05, 0.25                     # 严格大于，与用户 R 式一致

SHEET_ORDER = [                                     # ⚠ 生物学逻辑序，不是字母序
    "Y_Pre_vs_O_Pre",      # Aging
    "O_Pre_vs_OD_Pre",     # DM（糖尿病）
    "Y_Pre_vs_Y_Post",     # Ex_Young
    "O_Pre_vs_O_Post",     # Ex_Old
    "OD_Pre_vs_OD_Post",   # Ex_DM
]

sig = df[(df.fdr < FDR_CUT) & (df.coef.abs() > COEF_CUT)].copy()
sig = sig.sort_values(["fdr", "coef"], ascending=[True, False])   # 对应 arrange(fdr)
sig.insert(2, "regulation", np.where(sig.coef.values > 0, "Up", "Down"))  # ★ 见第二节

with pd.ExcelWriter(OUT, engine="openpyxl") as w:
    for comp in SHEET_ORDER:
        sheets[comp].to_excel(w, sheet_name=comp, index=False)
        w.sheets[comp].freeze_panes = "A2"           # 表头冻结
        # 数值列 number_format='0.0000'

pd.DataFrame(man_rows).to_csv(MANIFEST, index=False, encoding="utf-8-sig")
```

**参数约定**
- `sheet_name` **必须 ≤31 字符**且不含 `[]:*?/\`（`Y_Pre_vs_O_Pre` 这类没问题）
- **sheet 名从文件名派生**，不要信表内的 `comparison` 列（文件名的可靠性更高；本项目文件名本身就是
  `merged_<对比组>.xlsx`，天然对齐）
- 列顺序：关键列前置（`gene, celltype, regulation, coef, se, z, p, fdr, …`），`coef_D/p_D/fdr_D` 等**保留**（下游要用）
- manifest CSV 记：`n_tested_rows / n_genes_unique_all / n_fdr05_rows / n_fdr05_unique_genes /
  n_kept_rows / n_kept_unique_genes / n_subclusters_present / pct_kept_of_fdr05`
  ⇒ **行数与去重基因数两个口径都出**（同一基因在 10 个亚群被计 10 次，只报一个口径必被追问）

---

## 二、🔴 最大的坑：源表的 `direction` 列是**组级常量**，不是逐行方向

实测 5 个表的 `direction` 列 **`nunique() == 1`**（每 sheet 只有一个值）：

| sheet | `direction` 唯一值 |
|---|---|
| Y_Pre_vs_O_Pre | `O_Pre > Y_Pre (coef>0)` |
| O_Pre_vs_OD_Pre | `OD_Pre > O_Pre (coef>0)` |
| Y_Pre_vs_Y_Post | `Y_Post > Y_Pre (coef>0)` |
| O_Pre_vs_O_Post | `O_Post > O_Pre (coef>0)` |
| OD_Pre_vs_OD_Post | `OD_Post > OD_Pre (coef>0)` |

它只是**「该对比组的正向定义」的说明文本**。实测 Aging sheet：`coef>0` 22,709 行、`coef<0` 469 行，
而 `direction` 对这 23,178 行是**同一个值** ⇒ 拿它判逐行上下调会**全错**，
而且**不会报错**（用户看到的大概率是"怎么全是上调"）。

⇒ **交付前必须自己派生逐行方向列**（本 skill 用 `regulation` = Up/Down，由 `coef` 符号决定），
并在汇报里**显式提醒**「判上下调请用 regulation 列，原 direction 列是组级常量说明」。

⚠️ 同类陷阱的通用判据：**交付任何表之前，对每一列算一次 `nunique()`**，等于 1 的列
要么是常量说明、要么是上游 bug —— 都不该被当成逐行属性使用。

---

## 三、其它必须知道的表特性

### 3.1 `fdr` / `p` 下溢为 0 是**真实极小值**，不是缺失

float64 下限约 `1e-308`。实测本轮：

| sheet | `fdr==0` 行数占比 | 非零最小 fdr |
|---|---:|---|
| Y_Pre_vs_O_Pre | 4,478 / 23,178（**19.3%**） | 1.6e-307 |
| O_Pre_vs_OD_Pre | 24 / 311（7.7%） | 1.3e-297 |
| Y_Pre_vs_Y_Post | 14 / 115（12.2%） | 8.5e-224 |
| O_Pre_vs_O_Post | 77 / 1,846（4.2%） | 6.1e-302 |
| OD_Pre_vs_OD_Post | 25 / 246（10.2%） | 1.2e-286 |

⇒ **交付说明里写清「0 = 下溢，不是缺失」**，否则用户会以为数据丢了。
同时它本身就是**失校指纹**（p 值塌到下溢极限 ↔ SE 被压低，见 `analysis-output-validity-gates` §6）。

### 3.2 导出后**强制自检**（4 条，全部要算出数字）

```python
assert all((v.fdr < FDR_CUT).all() and (v.coef.abs() > COEF_CUT).all() for v in chk.values())  # 阈值合规
assert len(chk) == 5                                                                            # sheet 数
assert all(v.shape[0] > 0 for v in chk.values())                                                # 无空 sheet
# ④ 行数必须与上游统计脚本（如 19_coef_threshold_stats.py）一致 —— 两处数字打架是本类事故常客
```

抽查时打印每 sheet 的 `rows / genes / subclusters / |coef|min / fdr_max` 一行，
`|coef|min` 会是 **0.2499–0.2503**（阈值边界），这是"筛干净了"的最快证据。

### 3.3 方向指纹顺手报

Aging sheet `up:down = 22,709 : 469 ≈ 48:1`（运动四组 ~1:1）⇒ **极端不对称 = 失校指纹**，
不要再解释成生物学（详见 `enrichment-conclusion-validation` §门禁 5c）。

---

## 四、交付目录整洁（用户明确要求）

用户原话：「**把不关 DEG 的图给我去掉，垃圾文件**」—— 结果目录里非主题产物会被当成垃圾。

- 交付前扫一遍 `figures/`，**只保留与当前分析主题相关的图**；非相关图**移入 `_archive_not_deg/`**
  （或同名归档目录），不要直接删——用户可能之后要引用
- 真要删：**先逐文件记 SHA256 + 大小到 log**，再删，并独立复核"已删 N/N、残留 0"
- 删除/移动这类操作同样**不辩论**；但要留一个幂等清理脚本（`cleanup_*.sh`）便于复现
- ⚠️ `rail_review(post)` 会拿「分析脚本」标准去评一条 `mv` 命令（嫌代码短、嫌用 `&&`）→ 属误判，
  补一个带注释、分步的幂等脚本重跑即可通过（别为此改分析逻辑）

---

## 五、把这一套串起来的顺序

```
阈值定稿（该辩 → enrichment-conclusion-validation 门禁5）
        ↓
按阈值筛选 + 派生 regulation + 多 sheet 导出（本节，⛔ 不辩）
        ↓
4 条自检 + 抽查一行数字 + 下溢/方向指纹说明
        ↓
汇报：sheet 表 + 用表提醒（regulation 才是方向；0 = 下溢）+ 产物路径 + manifest
```