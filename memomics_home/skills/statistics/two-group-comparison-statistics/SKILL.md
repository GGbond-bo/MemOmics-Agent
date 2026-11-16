---
name: two-group-comparison-statistics
description: "两组/多组比较统计的执行与交付（独立 vs 配对口径、Welch t / Mann-Whitney U / Wilcoxon signed-rank、效应量、可选 FDR），含「固定表头 CSV」交付规范与 rail_review(post) 口径不匹配的如实处理。触发：A 组 vs B 组比较、两组均值+p值、算显著性、细胞比例检验、Welch t 检验、扁平表达表两组统计、指定表头输出 CSV。"
when_to_use: "用户给一张已经是 per-sample × per-gene / per-sample × per-feature 的扁平表（或细胞比例一类单点指标），要求『A vs B 两组比较 + 各组均值 + p 值 → 指定表头 CSV』时用本 skill。若对象是 scRNA 计数矩阵 + 细胞注释、要做 pseudobulk DESeq2/MAST 多方法 DEG → 走 deg-analysis；若明确是组内配对+组间独立混合设计 → 走 deg-mixed-design。"
version: 1.0.0
author: MemOmics
license: MIT
platforms: [windows, linux, macos]
metadata:
  memomics:
    tags: [statistics, welch-t-test, two-group, effect-size, fixed-header-csv, user-script]
    difficulty: basic
    language: Python+R
    category: statistics
---

# 两组比较统计（执行 + 交付口径）

## 何时用 / 何时不用（边界先行，别被 RED 关键词带偏）

| 情形 | 用什么 |
|------|--------|
| 扁平表（长格式 `group,gene,expr` 或宽矩阵 samples×genes），每组几个样本，A vs B | **本 skill** |
| 细胞比例 / 单点指标跨组比较（每组若干样本的比例值） | **本 skill**（检验按下面的口径表选） |
| scRNA 计数矩阵 + 细胞注释，要 pseudobulk / DESeq2 / MAST / 火山图热图 | `deg-analysis` |
| 组间独立 + 组内配对/重复测量同存的混合设计 | `deg-mixed-design`（效应量 `d_av` 口径） |

> ⚠️ 用户说「差异分析 / 两组比较」时，先看**输入是扁平表还是单细胞对象**。扁平表上硬套 DEG 全流程
> （8 步循环、参数扫描、debate、必出图）会空转，还会把用户「只做这一步 / 不配图 / 不写报告」的口径冲掉。

## 选择检验

| 设计 | 主检验 | 备注 |
|------|--------|------|
| 两组**独立**（不同个体/来源） | **Welch 双侧 t 检验**（不假设方差齐性） | 偏态/小 n 可并列 Mann-Whitney U 作敏感性分析；两者不一致时如实并列报告 |
| 两组**配对**（同 donor Pre/Post） | 配对 t / **Wilcoxon signed-rank** | 效应量用 `d_av`，**禁用 `d_z` 作主口径**（受组内 r 影响、不可共用色标）；配对数 n≥6 才有意义 |
| 多组 | 按用户指定（单因素 ANOVA + 事后 / kruskal） | 多重比较校正 = 用户说了算 |

实现：
- Python：`scipy.stats.ttest_ind(a, b, equal_var=False).pvalue`（默认双侧）；MANN：`scipy.stats.mannwhitneyu`
- R：`t.test(a, b, var.equal = FALSE)`（默认双侧）

**多基因 FDR 不要自作主张**：用户只要 `pvalue` 一列 → 交原始 p，**不加** `padj`、**不改**表头；
用户点名要 FDR 才加列（BH 按族口径说明，见统计口径记忆 / deg-mixed-design 的 d_av 审计参考）。

## 输入校验（省掉后面所有静默错误）

```python
assert {"group", "gene", "expr"}.issubset(df.columns)      # 长格式
assert {G1, G2}.issubset(set(df["group"].unique()))        # 分组齐
df["expr"] = pd.to_numeric(df["expr"], errors="coerce")    # 防字符串/NA
df.groupby(["gene", "group"]).size().unstack()             # 打印每组 n，写进汇报
```

- 每组 n < 2 → 该行标 `not_tested_insufficient_n`，**不硬算 p**；
- 汇报时明确「每组 n = 几个样本」，且区分「原始多少 / subset 后多少」（用户对数值精度敏感）；
- 宽矩阵要按列名前缀/regex 拆组，先打印匹配到的样本名核对。

## 交付规范（用户给死表头时，表头就是契约）

1. 用 `pd.DataFrame(rows, columns=[...用户给的顺序...])` **显式**定列，不靠 dict 插入序；
2. `os.makedirs(os.path.dirname(OUT), exist_ok=True)` → `to_csv(OUT, index=False)`；
3. 数字格式：均值 `round(...,6)`，p 值 `float(f"{p:.6g}")`（小 p 不塌成 0、不写成长科学计数）；
4. `test_method` 写人类可读名（`Welch two-sided t-test` / `paired t-test` / `Wilcoxon signed-rank`），方便对方核对口径；
5. 落盘后 **`read_file` 回读**：逐字核对表头 + 行数 + 字节数，再汇报结果表。

**用户说「只做这一步」= 零额外产物**：不配图、不写 HTML 报告、不写 README、不导出 xlsx。
汇报正文给 Markdown 管道表格（gene / 各组均值 / p / 检验名）+ 一句「哪些达 p<0.05」。

## 审查与门控口径（实测踩点，别为流程牺牲交付）

| 环节 | 处理 |
|------|------|
| 用户已给全 方法+输入+输出+表头，并说「现在就跑 / 不要再问 / 直接做」 | **跳过** ask_user 确认表单与 L1 辩论，按指定范围直跑；汇报末尾一句说明「方法/输出已由用户指定，无待澄清分歧」 |
| `rail_review(post)` 因 `figure_count=0` 判 `passed=false`（用户明令不配图） | 如实说明「完整流程门禁 vs 单点表格交付」的口径不匹配，**⛔ 禁止补凑数图**；产物照交付 |
| `rail_review(post)` 回报 `location_source=inferred` 且 node=集群 | 本机任务显式传 `location="local"`；核对 `location_line`，与本次真实执行位置不符就在汇报里点明该结论不适用 |
| 脚本落盘 | `results/<sid>/scripts/<语义名>.py`，用 `execute_python` 的 `exec(open(...,encoding="utf-8").read())` 跑（持久内核，重跑秒级） |
| 自进化 | 跑通后 `skill_evolution(action="record_run")`：script_name / params_used / result_summary（含达显著的项目）；报错则 `record_error` |

## 常犯错误

- ❌ 把独立设计当配对（或反之）——口径错了 p 值全错；先问清「同一个人测两次 = 配对」「两组不同个体 = 独立」。
- ❌ 扁平表任务去 load 重型 DEG skill 并跑 8 步循环 → 空转 + 冲掉用户口径。
- ❌ 为了过 `figure_count` 门禁临时画一张凑数图（造假产物，禁止）；正确做法是说明口径不匹配。
- ❌ 擅自加 `padj` / 改表头 / 改列序 → 用户按固定表头解析下游，列变动即返工。
- ❌ 只报 p 值不报每组的 n 与单位（细胞 vs 样本）——推断单位错误会让整个结论失效。

## 支持文件

- `references/two-group-welch-ttest-from-flat-table.md` —— 长格式/宽矩阵两种输入的完整可复用脚本（含校验、Welch 循环、固定表头落盘、回读核对、门控说明）与实测记录。