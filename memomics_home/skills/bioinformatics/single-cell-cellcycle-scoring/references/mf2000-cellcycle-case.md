# 案例：MF_2000（人骨骼肌 snRNA-seq）细胞周期打分 —— 为什么结论是「无可靠差异 + 标签不可解读」

> 会话 `memomics-9d3f3791`，2026-09-24。产物：`E:/MemOmics-Agent/results/memomics-9d3f3791/`
> （`scripts/01–07*.R`、`figures/fig1–7`（PNG+PDF）、`results/13 个 CSV`、`data/cellcycle_metadata.rds`）。

## 1. 数据事实（实测）
- `E:/release/_memtest/data/MF_2000.rds`：Seurat，RNA 51227 × 2132 核（counts+data，data 已 log-norm，max 7.87），
  另有 SCT assay；已存在 pca / harmony / umap
- 设计：48 样本 × **每样本 45 核平衡抽样**（Old_2C_Post = 17）；6 组 = Y/O/OD × Pre/Post
  （Y 10 供体、O 7、OD 7，每供体 Pre/Post 配对；全 Female）；样本名列 `samplename`，组列 `type`
- celltype：TypeI 797 / TypeII 1173 / RSS 162
- cc.genes.updated.2019 覆盖 43/43（S）+ 54/54（G2M）

## 2. 打分结果
| 指标 | 值 |
|------|----|
| 相位 | G1 934 (43.8%) / S 661 (31.0%) / G2M 537 (25.2%) → S+G2M = 56.2% |
| S.Score 范围 | −0.107 ~ +0.150（均值 −0.011） |
| G2M.Score 范围 | −0.074 ~ +0.140（均值 −0.010） |
| 各组 S+G2M | 48.7%（Y_Pre）→ 63.2%（OD_Post） |

## 3. 阴性对照（决定性证据）
| marker | G1 / S / G2M 检出率 (%) | 6 组检出率 (%) |
|--------|------------------------|----------------|
| **MKI67** | **0.00 / 0.00 / 0.00** | **全部 0.00（48 供体亦全 0；mean log-norm = 0.0000）** |
| PCNA | 1.07 / 5.45 / 1.30 | 1.90 – 2.86（供体级 0 – 8.89） |
| TOP2A | 0.43 / 0.30 / 2.23 | 0.35 – 1.27 |
| HIST1H4C | 2.57 / 0.91 / 1.30 | 0.63 – 3.78 |
| CCNB1 | 0.32 / 0.30 / 0.37 | ≤ 0.95 |
| CDK1 | 0.11 / 0.00 / 0.37 | ≤ 0.35 |
| MCM2 | 0.75 / 0.61 / 0.74 | ≤ 1.11 |
| PAX7 / MYOD1 | 12.10 / 9.83 / 9.68 ；7.07 / 6.05 / 4.66 | PAX7 5.40 – 16.22 |

- 基线表达失衡：S 集 0.0623 vs G2M 集 0.0427 → **朴素均值比较得 %S = 64.5%**（说明相位划分受基因集基线表达差驱动）
- 结论：终末分化肌核，**不存在增殖细胞** ⇒ 相位标签不可作表型解读

## 4. 组间统计（样本级，n = 48）
| 检验 | 结果 |
|------|------|
| 样本级 KW（6 组） | pct_S 0.156 / pct_G2M 0.103 / pct_Cyc 0.052 / S.Score 0.067 / **G2M.Score 0.018** / diff_Score 0.088；**两两 Wilcoxon-BH 无任何显著对** |
| Pre 独立（Y/O/OD） | pct_G2M 0.028（中位 15.6→26.7→31.1）/ pct_Cyc 0.061 / G2M.Score 0.065 / S.Score 0.848；无显著两两对 |
| 配对 Pre vs Post（每条件） | 6 指标 BH 后 p **全部 ≥ 0.69** |
| Δ(Post−Pre) 组间 | KW p 全部 ≥ 0.12 |
| celltype 分层（TypeI/II/RSS） | 卡方 0.087–0.395、KW 0.116–0.263，BH 后 > 0.15 |
| 细胞级卡方 | 6 组 0.0025（cycling vs G1 0.0024）——**与样本级冲突，是本例最易误判处** |
| ICC / deff | **ICC 0.0175，deff 1.76，有效 n 1212**（⇒ 并非 44 倍膨胀） |
| 供体级置换（2000×） | 细胞级卡方 0.0255 / pct_Cyc 0.040 / G2M.Score 0.0145 / Pre pct_G2M 0.0215（名义显著，6 指标未过 BH，q≈0.09） |
| 45 核 bootstrap（500×） | pct_Cyc KW p 中位 0.147（仅 20.4% < 0.05）；G2M.Score 中位 0.069（42.6% < 0.05）⇒ 不稳 |
| 技术混杂 | cor(S.Score, nCount) −0.16 ~ +0.05；cor(S, percent.mt) −0.09 ~ −0.02（弱） |

## 5. 辩论裁决
`debate_analysis` 场景 = `stats_design`，裁决 `need_more_info` / 置信度 **low**，rubrics：
unit_of_inference 6 / multiplicity 7 / effect_size 4 / confounding 4 / **negative_control 8** / hierarchical 3。
`next_actions`（owner=ai）：① donor 随机效应 GLMM/GEE + ICC/设计效应 ② donor 级置换 + n 核重抽样 ③ 匹配随机基因集阴性对照 + 真增殖标志矩阵。
⇒ 最终结论只能作**假设生成**，并如实说明未完成项。

## 6. 执行坑（本案例踩到的，已归入平台 skill）
- **R 持久内核崩 3 次**：exit `3221225794`（0xC0000142），stdout 全丢；触发点在 `AddModuleScore()` 连跑（随机基因集对照）。
  处方 = `sink()` 日志（崩溃保住 ICC/置换/检出率等结果）+ 拆脚本 + 改独立 `Rscript` 进程。
  见 `platform-execution-pitfalls/references/persistent-kernel-crash-and-standalone-rscript.md`
- `cmd //c "\"...Rscript.exe\" ..."` 引号被 MSYS 吃掉 → 只起 cmd banner、**exit=0 却一行没跑**；改 bash 直调绝对路径
- 表达分位匹配随机基因时 `which(binid == x)` 空集 → `sample.int` 报"第一个参数无效"（该对照未跑完，已在交付中如实说明）
- `rail_review(pre)` 报 ggpubr / ggrepel "Missing packages"（与 `check_env` 结果不一致）→ 收敛依赖集为 Seurat+ggplot2，
  p 值用 `annotate()` 手写；`rail_review(post)` 的 `output_dir` 传**会话根目录**

## 7. 可复用要点
1. 这类数据（终末分化组织）再来做细胞周期：**直接跑 `scripts/cellcycle_validity_controls.R`**，先看 MKI67 那一行；
   若仍为 0%，结论一步到位（不做组间解读），不必再展开全套统计
2. 想研究肌肉增殖，需在**完整数据**里先分出 PAX7+/MYF5+ MuSC 亚群再打分；45 核/样本的子集不够
3. 交付措辞：**"被打分判为 S 相的比例"**，不要写"正在增殖"