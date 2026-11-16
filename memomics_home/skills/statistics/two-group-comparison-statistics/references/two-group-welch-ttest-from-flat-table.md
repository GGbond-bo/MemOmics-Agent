# 扁平表达表 → 两组独立比较（Welch 双侧 t 检验）+ 固定表头 CSV

**用途**：用户给一张**已经是 per-sample × per-gene** 的表达表（没有 Seurat 对象、没有细胞类型维度、没有 pseudobulk
聚合），只要求「A vs B 两组比较，每个基因两组均值 + p 值，写成指定表头的 CSV，只做这一步」。

**边界判定**：满足任一条 → 用本配方，**不要**走 `deg-analysis` 的 8 步循环 / 参数扫描 / debate / 必出图：
- 输入是扁平表（长格式 `group,gene,expr` 或宽矩阵 samples×genes），而非 scRNA 计数矩阵 + 细胞注释；
- 规模是「每组几个样本」（如每组 6），不是细胞级或 pseudobulk 多样本；
- 用户点名了单一检验（"用 Welch t 检验"）并指定了输出表头。

## 输入格式的两种形态

| 形态 | 长啥样 | 取数方式 |
|---|---|---|
| 长格式 | 列 `<sample_index>, group, gene, expr`，每行一个样本×基因 | `df.groupby("gene")` → 按 `group` 拆两组 |
| 宽矩阵 | 行=基因，列=样本名（如 `Aging_1..Aging_6, T2D_1..T2D_6`） | 按列名前缀/regex 拆两组，先打印匹配到的样本名核对 |

**读入先校验**：
```python
assert {"group", "gene", "expr"}.issubset(df.columns)      # 长格式
assert {G1, G2}.issubset(set(df["group"].unique()))        # 分组齐
df["expr"] = pd.to_numeric(df["expr"], errors="coerce")    # 防字符串/NA
df.groupby(["gene", "group"]).size().unstack()             # 每组 n 写进汇报
```

## 统计口径

- **两组独立** → Welch 双侧 t 检验（不假设方差齐性）：
  - Python `scipy.stats.ttest_ind(a, b, equal_var=False).pvalue`（默认 `alternative='two-sided'`）
  - R `t.test(a, b, var.equal = FALSE)`（默认双侧）
- **两组配对**（同 donor Pre/Post）→ 不是本配方：配对 t / Wilcoxon signed-rank + `d_av` 效应量
  （见 deg-mixed-design 的 `references/dz-vs-dav-and-methods-consistency-audit.md`）。
- 每组 n < 2 → 标 `not_tested_insufficient_n`，**不硬算 p**。
- 多基因是否 BH 校正 = **用户说了算**：只要 `pvalue` 一列就交原始 p；用户要 FDR 才加列。
- 数字格式：均值 `round(...,6)`，p 值 `float(f"{p:.6g}")`。

## 固定表头交付

用户常给死表头，如 `gene,mean_Aging,mean_T2D,pvalue,test_method`：
`pd.DataFrame(rows, columns=[...用户给的顺序...])` 显式定列（不靠 dict 插入序）→ 建目录 → `to_csv(index=False)`
→ **`read_file` 回读**核对表头逐字一致 + 行数 + 字节数 → 再汇报。

```python
rows = []
for gene, sub in df.groupby("gene", sort=False):
    a = sub.loc[sub["group"] == G1, "expr"].dropna().astype(float)
    b = sub.loc[sub["group"] == G2, "expr"].dropna().astype(float)
    if len(a) < 2 or len(b) < 2:
        rows.append({"gene": gene, "mean_Aging": float("nan"), "mean_T2D": float("nan"),
                     "pvalue": float("nan"), "test_method": "not_tested_insufficient_n"})
        continue
    p = stats.ttest_ind(a, b, equal_var=False).pvalue
    rows.append({"gene": gene, "mean_Aging": round(a.mean(), 6), "mean_T2D": round(b.mean(), 6),
                 "pvalue": float(f"{p:.6g}"), "test_method": "Welch two-sided t-test"})

out_df = pd.DataFrame(rows, columns=["gene", "mean_Aging", "mean_T2D", "pvalue", "test_method"])
os.makedirs(os.path.dirname(OUT), exist_ok=True)
out_df.to_csv(OUT, index=False)
```

## 交付与审查（用户说"不配图、不写报告、只做这一步"时）

- 产物 = **只有那一张 CSV**；不配图、不写 HTML、不导 xlsx、不写 README。
- `rail_review(post)` 会因 `figure_count=0` 判 `passed=false` → 如实说明「完整流程门禁 vs 单点表格交付」口径不匹配，
  **⛔ 不补凑数图**（详见 platform-execution-pitfalls 坑 -0.5）。
- `rail_review(post)` 可能 `location_source=inferred` 推断成常驻集群会话（node=node4/env=R4.41）：本机任务显式传
  `location="local"`，并在汇报里点明该结论按集群口径审、不适用本机。
- 门控表单/辩论：方法+路径+表头都已由用户指定 → 跳过，汇报末尾一句说明即可。
- 仍要 `skill_evolution(action="record_run")` 留档（script_name / params_used / result_summary 含达显著项）。
- 脚本落 `results/<sid>/scripts/<语义名>.py`，用 `execute_python` 的 `exec(open(...,encoding="utf-8").read())` 跑。

## 实测记录（2026-10-18，E:/dsh-app/_memomics_check e2e 场景）

- 输入 `e2e_research/expr.csv`：长格式 72 行 = 6 基因 ×（Aging 6 + T2D 6）；输出 `e2e_review/out_r.csv`（389 B）。
- 结果：GENE1 p=3.94e-4（T2D > Aging）、GENE3 p=0.0271；GENE2/4/5/6 不显著。
- 同一 e2e 场景此前还跑过「Welch + Mann-Whitney U + Hedges' g + BH-FDR + 8 列表头 + 双面板图」的加长版
  → 列数与是否出图**每次都由用户当场指定**，不要把上一次的列集合照搬过来。
- 教训：本次被 RED 关键词「差异分析」带进 deg-analysis 全流程心智，实际是单点统计 → 先做边界判定。