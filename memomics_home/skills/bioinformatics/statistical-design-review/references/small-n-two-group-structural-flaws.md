# 小样本两组比较：结构缺陷分诊与结论分级（2026-10-18 实测）

**数据**：`expr_flawed.csv`（人，3 基因 × 6 vs 6，long format `sample,group,gene,expr`，样本名 `Aging_1..6` / `T2D_1..6`，36 行）。
同门课的另一份数据（`e2e_research/expr.csv`，6 基因、数据干净）见 `small-n-two-group-comparison.md`。
本文件的数字**绑定本次数据**，引用前先回看当次脚本输出。

## 一句话教训

naive Welch p 值只在**功效足够（≥0.80）**时才有资格作阴性证据。功效不足时 p 大是**功效问题，不是阴性结论**。
而"功效不足"最常见的成因**不是 n 小**，而是**组内结构缺陷把噪声估计抬高**——本例组内 SD 从层内 0.085 虚高到 1.570，功效从 >0.99 掉到 **0.198**。

## 三个基因的原始值与结果

| 基因 | Aging (n=6) | T2D (n=6) | 结论 |
|---|---|---|---|
| GENEDUP | 9.0, 9.2, 8.8, 9.1, 8.9, 9.05 | 10.0, 10.2, 9.8, 9.8, 10.1, 10.05 | 分布干净、无缺陷 |
| GENEBATCH | 6.0, 6.1, 5.9, 6.05, **9.0, 9.1** | 7.2, 7.3, 7.1, 7.25, **10.2, 10.3** | 两组内均双峰（4 低 + 2 高） |
| GENEMIS | 5.0, 5.1, 4.9, 5.05, 5.0, **8.0** | 7.9, 8.1, 7.8, 8.0, 7.95, 8.05 | Aging 单点离群，且恰落在 T2D 区间内 |

| 基因 | diff (T2D−Aging) [95%CI] | naive p | BH q | Hedges g [95%CI] | power | 留一最不利 p | 裁决 |
|---|---|---|---|---|---|---|---|
| GENEDUP | 0.983 [0.786, 1.181] | **6.8e-7** | 2.0e-6 | 5.93 [2.82, 9.04] | 1.000 | 1.4e-5 | `confirmatory_supported` |
| GENEMIS | 2.458 [1.176, 3.740] | **4.3e-3** | 6.4e-3 | 2.61 [0.91, 4.32] | 0.982 | 0.0168 | `directional_conditional` |
| GENEBATCH | 1.200 [−0.820, 3.220] | 0.215 | 0.215 | 0.705 [−0.48, 1.89] | **0.198** | 0.394 | `naive_negative_invalid + exploratory` |

基准：n=6 vs 6、α=0.05、power=0.80 → **MDES(|Hedges g|) = 1.796**（非中心 t 精确解）。

## 缺陷 1：组内双峰（层 / 批次 / 亚结构）—— GENEBATCH

**识别**：间隙法。组内最大相邻差 **2.9** = 层内 SD 的 **34 倍**、中位间隙的 29 倍；Shapiro-Wilk p=0.0042。
两组都是 4 低 + 2 高，**层在两组中平衡**（层与分组无共线性），层系数 3.0375。

🔴 **Grubbs 陷阱（本次核心发现）**：Grubbs G=**1.321** < 临界 **1.887** → 判"无离群"。
原因：两端**对称**偏离把 SD 抬到 1.570，每个点的标准化偏差反而变小。
⇒ **Grubbs 对对称双峰结构性失明**，不能因 Grubbs 阴性就排除层结构。双峰只能靠间隙法看。

**后果**：naive Welch p=0.2151（不显著）vs 分层 OLS **p=3.10e-8**。
`group:layer` 交互 coef=**−0.0000**、p=**1.000**，两层内效应**完全相同**（均 1.2000）：
- 低层 4v4：效应 1.200，p<1e-6
- 高层 2v2：效应 1.200，p=3.4e-3

**结论边界**：
- ✅ 能下：naive p 不可作阴性证据（MDES=1.796 ≫ 实测 |g|=0.705；CI 上界 3.220 > MDES；留一 p 全在 0.099–0.394 = "稳定无力"而非"稳定阴性"）
- ⛔ 不能下：把事后分层当**确认阳性**——层是从数据双峰模式**事后推断**的，非预注册，且无批次元数据可证。只能作**探索性待验证信号、不可外报**

## 缺陷 2：单点离群且落在另一组区间内 —— GENEMIS

**识别**：Grubbs G=2.038 > 临界 1.887（判离群）；Shapiro p=1e-4；Aging_6=8.0 而其余 4.9–5.1。
关键信号：**该值恰落在 T2D 区间 7.9–8.1 内** ⇒ 先疑标签错标，不要当"高反应者"。

**处理：不争论"删 or 不删"，跑三情景**

| 情景 | n | diff | p | Hedges g | 方向 |
|---|---|---|---|---|---|
| S1 保持原点（真高反应者） | 6v6 | 2.458 | 4.266e-3 | 2.615 | T2D>Aging |
| S2 剔除（QC 不合格） | 5v6 | 2.957 | <1e-10 | 28.613 | T2D>Aging |
| S3 标签错误（8.0 归入 T2D） | 5v7 | 2.961 | <1e-10 | 30.320 | T2D>Aging |

三情景方向一致、全部显著（最大 p=4.27e-3）⇒ **方向结论不依赖该点归属**。
注：离群点让差异被**低估**（2.458→2.957），剔除反而更强——所以"剔除后更强"不能证明原结论，但能证明方向稳健。

**结论边界**：
- ✅ 能下：T2D > Aging（方向）
- ⛔ 不能下："Aging 组存在 5.0–8.0 的表达异质性 / 个体差异大"——异常检测只能证明"该点异常"，**无法区分真高反应者与记录错误**

## 缺陷 3：组内重复值 —— 先算期望，别直接当缺陷

GENEDUP T2D_3 = T2D_4 = 9.8，是全数据集唯一重复值。

**期望重复对数**（分辨率 `res` 下 n 个正态点的期望对数）：
`E[ties] ≈ res · n(n−1) / (4√π · s)`

本例 res=0.05、s=0.163、n=6 → **E=1.30 对**，实测 **1 对** ⇒ **落在随机期望内，不构成缺陷**。

**"干净"的完整量化判据（GENEDUP 两组各 6 值全过）**：

| 检查项 | Aging | T2D | 判据 |
|---|---|---|---|
| 极差 ÷ SD | 2.80 | 2.46 | n=6 正态期望 **2.534** |
| Grubbs G | 1.458 | 1.282 | 临界 1.887 |
| Shapiro-Wilk p | 0.987 | 0.407 | 无偏态（偏度 −0.14/−0.14） |
| 重复值对数 | 0 | 1 | 期望 1.30 |
| 组间重叠 | 最大 9.2 < T2D 最小 9.8 → 完全分离 | — | — |

## 敏感性三件套（每次都要给全）

| 分析 | 说明 |
|---|---|
| S1 `naive` Welch 6v6 | 基准 |
| S2 **分层 OLS** `expr ~ group + layer` | 取公共组效应；层指示变量从结构诊断来 |
| S3 **留一法 jackknife 最不利 p** | 逐一剔除 12 个样本，取**最大** p（+ 记录最小 p） |
| 基因特异 | 分层基因→层内 4v4 / 2v2；离群基因→剔点、三情景 |

交互项是分层的必给项：`expr ~ group + layer + group:layer`，交互≈0 ⇒ 层内效应一致。

## 结论分级三档（落进产物表，别只写散文）

| 档 | criteria | 本次 |
|---|---|---|
| `confirmatory_supported` | 所有敏感性一致显著 + 结构审计全过 | GENEDUP |
| `directional_conditional` | 方向稳健（多情景一致），但机制/异质性解读不可下 | GENEMIS |
| `naive_negative_invalid + exploratory` | naive 阴性无效（功效不足）；正面证据仅探索、不可外报 | GENEBATCH |

## 报告七件套（缺一即不合格）

naive p / **MDES** / **power** / 效应量 + 95%CI / 留一最不利 p / 分层前后 p / 结构审计（组内间隙、Grubbs、Shapiro、重复值期望）。

## 交付格式（用户偏好，2026-10-18）

- 每条"**能下**"的结论**并排**给出"**不能下 + 原因**"。用户原话是"哪些真有差异、**哪条结论不能下、为什么**"——只报阳性发现 = 没答完。
- 说某基因/样本"**干净/无异常**"时，**当轮就把两组 6 个原始值逐条列出**并附量化判据。用户会追问"再确认一次原始数值有没有异常"（原话）——一次说全，别让人问第二遍。
- 长表格用 Markdown 管道表格（抗截断）；流程图用独立 mermaid 围栏。

## 平台机制（本次踩到）

- 裁决 `next_actions` 中 `owner=ai` 的条目**必须真执行**，并在 `todo` 里把对应项（id 形如 `debate_todo_<n>_<i>`）标 `status='completed'`；否则 `save_knowledge` / `generate_report` 等入库类工具被硬拦：
  `⛔ 辩论裁决的硬约束还没满足，本次 save_knowledge 被拦下（裁决要求先完成下列动作才允许产出高影响结果）`
- `record_run(script_name=...)` 里的脚本名**必须真实落盘**——先 `write_file` 写脚本再 record_run，否则运行记录指向不存在的文件（本次已补写 `expr_flawed_scenario_sim_and_grading.py` 修正）。

## 辩论（scenario=stats_design, L2）

裁决 = **modify / confidence=medium**。rubrics：`power_error_control=9`、`data_integrity=8`、`effect_robustness=7`、`multiplicity_grading=7`、`confounding_structure=6`、`reporting_boundary=6`、`design_validity=5`（扣分全在缺元数据）。
裁判认可"naive 阴性无效"证据链完整，但指出"分层 = 可确认差异"写过头，降为探索性。
`missing` 清单（= 交付里要写的待补证据）：样本 5/6 的 batch/plate/date/treatment 元数据、Aging_6 标签链与原始 QC、GENEDUP 重复值来源、独立队列/技术重复复现、分层预注册计划。

⚠️ 两轮 `search_papers`（"small sample two-group power MDES" / "batch bimodal masking DE"）**均未命中对口文献**，返回的是不相关的空间组学/蛋白组/甲基化论文。故"样本 5/6 是批次结构""Aging_6 是错标"这类归因**属推断而非文献支持**——交付里必须如实标注，不得虚构引证。

## 产物清单（本次）

```
results/memomics-d9c42d45/
  scripts/expr_flawed_three_gene_two_group_stats.py      # 主分析（含异常审计 + 4 面板图）
  scripts/expr_flawed_scenario_sim_and_grading.py        # 三情景模拟 + 分级表
  figures/expr_flawed_two_group_stats.png / .svg         # (a)原始值 (b)森林图 (c)敏感性 (d)功效曲线
  results/expr_flawed_two_group_stats.csv                # 主表
  results/expr_flawed_final_graded.csv                   # 定稿分级表（judge_status/report_scope/reason）
  results/expr_flawed_sensitivity.csv                    # naive / 分层 / 留一 / 层内
  results/expr_flawed_anomaly_audit.csv                  # 间隙/Grubbs/Shapiro/重复值期望
  results/expr_flawed_jackknife.csv                      # 36 条留一明细
  results/expr_flawed_genemis_scenarios.csv              # 三情景
```