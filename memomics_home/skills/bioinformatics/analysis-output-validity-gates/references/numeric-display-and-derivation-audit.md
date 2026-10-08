# 数值显示完整性 + 派生表溯源 —— 诊断配方（2026-09-30 实测）

用户打开交付的 xlsx 质问「**FDR 怎么全是 0**」时，**不要先怀疑数据算错**，按下面两层分别实证。
两层**互相独立**：显示层可以吞掉 97%+ 的格子，数值层才是真 0。
第二、三节回答另一个高频质问：「**这个表是不是来自那几个文件**」。

---

## 1. 显示层：单元格 number_format（你看到"全是 0"的主因）

pandas / openpyxl 写出的 xlsx 里，数值列的 `number_format` 可能是 `0.0000`（而不是 `General`）。
后果：**凡绝对值小于 5e-5 的格一律渲染成 `0.0000`**，即使底层存的是 1e-51 / 1.63e-307。

唯一可靠的判据是**单元格级**读取：

```python
import openpyxl
wb = openpyxl.load_workbook(xlsx_path, data_only=True)
ws = wb[sheet_name]
hdr = [c.value for c in ws[1]]
j = hdr.index("fdr") + 1
for i in range(2, 9):                                    # 看前几行
    c = ws.cell(row=i, column=j)
    print(c.value, c.data_type, c.number_format)          # 期望: 1e-51, 'n', '0.0000' ← 元凶
```

「会被显示成 0 的格数」＝ `count(abs(v) < 0.5 * 10**-decimals)`（format `0.0000` → 阈值 5e-5）。
**这个数才是用户在 Excel 里看到的 0 的比例**，不是 `(fdr == 0).sum()`。

实测（`DEG_fdr05_coef025_5contrasts.xlsx`，5 个 sheet）：

| 对比组 | 总行 | 显示 0.0000 | 占比 | 真实精确 0 | 最小非零 fdr | 中位 fdr | 最大 |
|---|---:|---:|---:|---:|---:|---:|---:|
| Y_Pre_vs_O_Pre | 23,178 | 22,692 | 97.9% | 4,478 | 1.63e-307 | 1.02e-51 | 4.95e-02 |
| O_Pre_vs_O_Post | 1,846 | 1,820 | 98.6% | 77 | 6.08e-302 | 8.84e-33 | 3.23e-02 |
| OD_Pre_vs_OD_Post | 246 | 233 | 94.7% | 25 | 1.23e-286 | 3.15e-76 | 3.31e-02 |
| Y_Pre_vs_Y_Post | 115 | 110 | 95.7% | 14 | 8.47e-224 | 2.05e-60 | 3.32e-02 |
| O_Pre_vs_OD_Pre | 311 | 291 | 93.6% | 24 | 1.31e-297 | 1.83e-43 | 3.82e-02 |

同时该文件**按 fdr 升序**排列（`(np.diff(fdr) >= 0).mean() == 1.000`）⇒ 那 4,478 个真 0 全挤在最前面，
**打开文件第一屏就是整列 `0.0000`** —— 观感即"全是 0"。这一层"叠加"会把质疑放大。

## 2. 数值层：p 值双精度下溢（abs(z) 阈值判据）

细胞级 glmer / bayesglm 在大 n_cells（实测 4,731–85,865）下 abs(z) 可达 37–264。
`2 * pnorm(-abs(z))` 低于 double 最小正数（≈5e-324）时**精确等于 0**，BH 校正后仍是 0。

**可证伪判据（跨 sheet 复现一致 ⇒ 下溢，而非算错）**：

```python
z = pd.to_numeric(d["z"]); v = pd.to_numeric(d["fdr"])
print(z[v == 0].abs().min(), z[v == 0].abs().max())   # 精确 0 行: 37.5 ~ 264.3
print(z[v > 0].abs().max())                           # 非 0 行  : <= 37.5
```

5 个对比组的边界全部落在 abs(z) ≈ 37.5–38.3，无一例外。
上游（未过滤的 merged 全量）里 `p` 精确 0 的行数与 `fdr` 精确 0 的行数**完全相同**（实测 5,490 = 5,490）
⇒ **0 产生在统计环节，不是导出环节制造或掩盖的**。

影响面（汇报口径）：

- **不影响「哪些基因显著」**：1e-300 与 1e-51 在判显著上等价；
- **影响排序 / 画图**：`-log10(0) = Inf`，按显著性排序或画火山图时这些行会塌成一点；
- `z` 列在表里 ⇒ 可用 z 在**对数尺度**反算 p（不受双精度下限约束），**无需重跑统计**。

## 3. 派生表溯源核查配方（用户问「是不是来自这几个文件」）

三步，全部要落成可证伪证据：

```python
# ① 读导出脚本，确认真实输入 + 过滤规则（search_files 定位）
#    例: 21_export_coef025_by_contrast.py → fdr < 0.05 & abs(coef) >= 0.25，并新增 regulation 列
# ② 列结构比对
print(list(src.columns))        # 源 15 列
print(list(exp.columns))        # 导出 16 列
print(set(exp.columns) - set(src.columns))     # {'regulation'} ← 脚本派生列
# ③ 复现过滤 + 逐值比对（不是"看起来一致"，是数组全等）
f = src[(src["fdr"] < 0.05) & (src["coef"].abs() >= 0.25)] \
        .sort_values(["gene", "celltype"]).reset_index(drop=True)
e = exp_df.sort_values(["gene", "celltype"]).reset_index(drop=True)
ok = (len(f) == len(e)
      and np.allclose(f["coef"], e["coef"], atol=1e-12, equal_nan=True)
      and np.array_equal(f["fdr"].values, e["fdr"].values)
      and np.allclose(f["p"], e["p"]))
```

实测结论：5 个 `merged_*.xlsx`（340,971 行）→ 过滤后 25,696 行 ＝ 导出表 25,696 行，
逐 sheet 行数相等、coef/fdr/p 数组全等 ⇒ 来源确认。
顺带纠偏：这 5 个 merged 文件本身已是**新方法**（`method` 列 = `glmer` / `bayesglm`，含 `nRUV_used`）
的全量输出，**不是**老方法 FindMarkers 的表 —— 不要按文件名或方法名前缀想当然归类。

## 4. 交付自检清单（写进每次导出）

- 小数值列（fdr / p / p_val_adj）导出时设科学计数法或另给对数列，别让 `0.0000` 吞掉量级；
- 交付前跑 `scripts/probe_excel_numeric_display.py <xlsx>`，把「显示成 0 的格数」报出来；
- 报告口径分两句：「**真实精确 0 = X 行**（来自 abs(z) ≥ 37.5 的 p 下溢）；**显示成 0 = Y 格**（格式所致）」
  —— 分清楚，用户就不会以为数据坏了；
- 溯源类质问一律给「逐值一致 = True/False」这种可证伪结论，**不要写"看起来来源一致"**。