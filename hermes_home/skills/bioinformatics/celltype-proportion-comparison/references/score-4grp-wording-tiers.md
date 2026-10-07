# 打分四组模式 + 结论措辞定档 — 实测规格卡

**来源**：2026-09-24 会话 `memomics-04edf5b0`，数据 `E:/release/_memtest/data/MF_2000.rds`
**用户原话**：「E:\release\_memtest\data\MF_2000.rds 的 meta 里有 scoreSenMayo_AUC 这一列，帮我评估衰老评分在四组之间的差异，出图并给结论。」
**性质**：analysis_exec（有数据 + 明确交付「图 + 结论」）→ 走完整链：skill_view → rail_review(pre) → execute_r → rail_review(post) → L2 辩论 → 裁决落地 → record_run

---

## 1. 数据与四组口径

| 项 | 值 |
|---|---|
| 对象 | Seurat v5，**51,227 genes × 2,132 cells**（`dim()` = genes × cells，勿读反），48 样本 |
| 抽样特征 | 每样本细胞数 min 17 / median 45 / max 45 ⇒ **每样本取 45 细胞的抽样版** |
| 性别 | 全 Female（外推硬伤，必须写进交付） |
| 四组 | `Y_Pre`(450 cells/10 样本) / `Y_Post`(450/10) / `O_Pre`(315/7) / `O_Post`(287/7)；`OD_Pre`/`OD_Post` 各 315 细胞作**补充描述**（六组图），不进主结论 |
| 层级 | `celltype`(3: TypeI/TypeII/RSS) ⊂ `annotation_L2`(4) ⊂ `annotation`(5) ⊂ `annotation_L3`(10) |
| 被检验列 | `scoreSenMayo_AUC`（细胞级，0.0019–0.0711，中位 0.0308） |

**4 个重点比较**（与比例四组模式同）：`Y_Pre vs O_Pre`、`Y_Post vs O_Post`（独立 Mann-Whitney）+ `Y_Pre vs Y_Post`、`O_Pre vs O_Post`（配对 Wilcoxon，`base_id = sub('_(Pre|Post)$','',samplename)`）。
另算 2 个对角线独立比较（`Y_Pre vs O_Post`、`Y_Post vs O_Pre`）**只入表不画**。

---

## 2. 主结果（样本级均值，All cells）

```
比较                  类型 n    均值变化               相对    p        FDR(区块内) Cliffδ  Cohen d  功效   判定
Y_Pre vs O_Pre       独立 10/7 0.03389→0.02910      −14.1% 0.00728  0.0437      −0.80  −1.75   0.86  区块内提示性下降
Y_Post vs O_Post     独立 10/7 0.03092→0.02915       −5.7% 0.40681  0.4882      −0.26  −0.80   0.23  未检出（功效不足）
Y_Pre vs Y_Post      配对 10   0.03389→0.03092       −8.8% 0.03711* 0.0682        —    −1.22   0.47  探索性提示（不入主结论）
O_Pre vs O_Post      配对 7    0.02910→0.02915       +0.2% 0.93750  0.9375        —     0.02   0.035 未检出
```
\* 精确 Wilcoxon p=0.03711；近似口径 p=0.04149。**bootstrap CI 跨 0（[−5.8e-3, +9.1e-4]）** ⇒ 只能探索性。

**逐纤维型分层（组成无关的内部对照）**：TypeI −14.3%（p=0.00728, FDR=0.0437, δ=−0.80, d=−1.52）、
TypeII −15.4%（p=0.01680, FDR=0.0391, δ=−0.71, d=−1.67）、RSS −8.7%（p=0.417, ns；Y_Pre 仅 5/10 样本含 RSS）。

**FDR 家族**：全表 **24 行**（`all` 6 + `celltype` 3×6），`FDR_global` **无一行 <0.05**，最小 p=0.00728 → **q=0.0582**（边缘未过）。
⚠️ 我曾按「32 行」估并把 `q≈0.23` 写进 debate context —— **实算 24 行后是 0.0582**。教训：**context 里的每个数字都要能从产出表里指出来**。

---

## 3. 裁决要求补做、且实测全部成立的四件证据

| 证据 | 办法 | 实测结果 |
|---|---|---|
| bootstrap 95% CI | B=2000，**组内重抽样本**（非重抽细胞） | mean diff **[−6.95e-3, −2.46e-3]**（不含 0，P(≥0)=0）；Cliff δ **[−1.00, −0.40]** |
| 精确置换 | 小 n 用 `combn(n, n1)` **枚举全部**标签置换 | choose(17,10)=**19448** 种，秒级；**p=0.00437**（Y_Post vs O_Post 同时算得 p=0.127，与不显著一致） |
| 组成敏感性 | `lm(score ~ type)` vs `lm(score ~ type + TypeI_prop + TypeII_prop)` | β **+0.00480 → +0.00583**、p **0.0029 → 0.0040**、R² **0.458 → 0.589** ⇒ **校正后增强 = 非组成驱动** ✅ |
| 打分共变 | 样本级 Spearman（SenMayo vs 其余 17 打分） | OxPhos 0.56 / TNFA 0.52 / ROS 0.50 / Sarcomeric 0.49 / scoreII 0.46 ⇒ 与整体程序共变，**不支持「特异性衰老信号」** |

**附带发现**：纤维型组成随衰老变化 = RSS 比例 **1.3% → 9.2%（p=0.0019）**，TypeI（p=0.77）/TypeII（p=0.15）无显著变化。
⇒ 结构性变化在 RSS，而 **SenMayo 的组间差在 TypeI/TypeII 内部同样成立**（故不是组成假象）。

---

## 4. 措辞定档文本（可直接复用，`results/RESULTS_wording.md`）

- **默认（保守）**：样本级均值分析中，老年组运动前 SenMayo_AUC 低于青年组运动前 −14.1%，p=0.00728，区块内 FDR=0.0437，Cliff δ=−0.80，Cohen d=−1.75，功效 0.86，观测差/MDE=1.19 ⇒ **区块内提示性下降**（全局 FDR 不显著，最小 q=0.0582）。
- **条件升级**（**仅当** 6 比较家族被预锁定为主分析）：预设区块内老年 Pre 显著低于青年 Pre（FDR_within=0.0437）。
- **⛔ 禁用**：全局显著降低 / 「衰老程序显著减弱」/「肌纤维更年轻」/「衰老负担降低」。
- **外推边界**：仅限全 Female、每样本中位 45 细胞、n=10/7 的样本级内部假设生成。

---

## 5. 产物结构（照搬）

```
data/score_senmayo_sample_level.csv                  # 样本级聚合（48 样本 × level/celltype）
results/score_senmayo_significance_4grp.csv          # 6 比较 × (all + 3 celltype) = 24 行 + 双 FDR
results/score_senmayo_mde.csv / _power_curve.csv     # MDE（MC + 解析）与功效曲线数据
results/score_senmayo_bootstrap_permutation.csv      # 裁决三件套之一
results/score_senmayo_composition_sensitivity.csv    # 组成回归 + 逐型分层 + 组成差
results/score_senmayo_score_correlations.csv         # 与其余打分共变
results/score_senmayo_group_summary.csv / _sixgroup_summary.csv
results/RESULTS_wording.md                           # 措辞定档（保守/条件升级/禁用词/外推边界）
figures/score_senmayo_4grp_{p,fdr}.{png,pdf,svg}     # 主图 4 柱 26×32mm（p/FDR 两版）
figures/score_senmayo_bycelltype_{p,fdr}.*           # 逐 celltype 总览
figures/score_senmayo_celllevel_violin.*             # 细胞级 violin（描述性）
figures/score_senmayo_power_MDE.*                    # 功效曲线（0.8 线 + 观测量）
figures/score_senmayo_sixgroup.*                     # 六组补充（含 OD，描述性）
figures/score_senmayo_robustness.*                   # bootstrap 分布 + 精确置换零分布
scripts/01_score_senmayo_4grp.R                      # 提取 + 聚合 + 检验 + MDE + 出图
scripts/02_verdict_actions.R                         # 裁决可执行项（CI/置换/组成/共变/措辞）
```

**绘图要点**：`theme_bw(base_size=6)`、四色 `#B2DF8A/#33A02C/#80B1D3/#1F78B4`、配对虚线 `#909090`、
散点 jitter ±0.15（Pre 左 / Post 右）、手动括号（`geom_segment` 三段 + 白底 `geom_label`，按 p 升序防重叠）、
`egg::set_panel_size(26mm × 32mm)` 后**必须按 gtable 真实宽高 `ggsave`**（否则 178mm 大画布）、
PNG(300dpi) + PDF(cairo) + SVG(svglite) 三联。

---

## 6. 复用检查单（下次同类请求）

- [ ] 确认「四组」= `Y_Pre/Y_Post/O_Pre/O_Post`（本数据集既定约定；OD 组作补充描述，不进主结论）
- [ ] 分析单位 = **样本级均值**；报告里显式写 n（青年 10 / 老年 7，不是「每组 10 样本」）
- [ ] 双 FDR 都报，且**先 `nrow(res)` 实算家族行数**（本次 24 行）→ 写进 debate context 前核对
- [ ] 四个比较各报：均值/相对变化/p/区块内 FDR/Cliff δ/Cohen d/功效/观测差÷MDE
- [ ] 主比较补 bootstrap CI + 精确置换；组成敏感性回归（校正后增强 = 非组成驱动）
- [ ] 措辞按三档定档；禁用词逐条避开；外推边界（抽样细胞数 + 性别 + n）写进结论
- [ ] 出图 4 柱 26×32mm + p/FDR 两版 + PNG/PDF/SVG；图后跑 rail_review(post)
- [ ] L2 裁决的 `next_actions` 逐条落地（本次 2 条 owner=ai 全部执行，1 条 owner=user 转为向用户提出的三个问题）