# 骨骼肌 MF 打分分析实测（2026-08-13）

## 数据背景
- 输入：`E:/骨骼肌锻炼/MF_L3_meta_new.csv`（508,662 细胞 × 14 打分列 + samplename + annotation_L3 + type）
- 14 打分：scoreI/II/IIa/IIx（纤维类型）、Sarcomeric、OxPhos、Atrophy、RegMyon、Stress、ROS、TNFA、Inflammatory、SenMayo、Insulin
- 6 组：Y_Pre/Y_Post/O_Pre/O_Post/OD_Pre/OD_Post，base_id 配对（3 条件 × 干预前后）

## 执行管道（scripts/）
- `03_score_diff.R`：细胞级 → 样本级均值聚合 → 同一配对框架检验 → `score_diff_all_14scores.csv`（score, group1, group2, p.value, method, effect_size, es_metric, FDR_per_score, FDR_global）
- `05_score_analysis.R`：聚合缓存 `score_sample_level.rds` → Spearman 相关矩阵热图 → 6 关键打分箱线图（p 值标注从差异 CSV 读）
- `check_cor.R`：输出高相关对（|r|>0.7）与独立打分（max|r|<0.5）

## 关键实测结果

### 相关性结构（样本级 Spearman）
- 冗余（|r|>0.7）：Sarcomeric↔I (0.71)、Sarcomeric↔II (0.71)、ROS↔I (0.77)
- 独立打分（与其他打分 max|r|<0.5）：**RegMyon (0.47)、Inflammatory (0.46)**
- 解读规则：冗余对不能都当独立信号讲；独立打分是正交维度

### 打分差异（FDR_per_score < 0.05，15 个显著）
- **衰老轴（Y vs O）**：scoreIIa ↓ (FDR=0.0006 最显著)、OxPhos ↓ (0.0006)、Sarcomeric ↓ (0.006)、SenMayo ↓ (0.007)、Insulin ↓ (0.019)、scoreII ↓ (0.033)
- **糖尿病轴（O vs OD / Y vs OD）**：scoreI ↓ (0.004)、OxPhos ↓ (0.002)、Sarcomeric ↓ (0.006)、scoreII **↑** (0.033 反向！)、ROS ↓ (0.028)
- **运动轴（唯一显著）**：O 组 scoreIIa **↑** (FDR=0.031，0.177→0.278 接近年轻 0.260)；Y 组 Insulin ↑ (0.039)；O 组 RegMyon 边缘 (0.188)
- **结论一句话**：衰老 = 氧化慢肌程序整体萎缩（IIa+OxPhos+Sarcomeric↓）；糖尿病 = 在衰老基础上 Type I 程序再↓ + Type II 程序反向↑（代谢不灵活性）；老年运动唯一逆转信号 = IIa 程序回升。

### SenMayo 解读陷阱
scoreSenMayo 在肌纤维衰老组 FDR=0.007 下降。SenMayo 是衰老细胞打分，肌纤维里下降 ≠ 更年轻。合理解读：衰老肌纤维丢失年轻表达谱但未进入典型衰老细胞态；SenMayo 高表达主要在免疫/基质细胞。**写论文时这个打分在肌纤维里要谨慎或放补充**。

## 亚群×打分热图实测（2026-08-13 后半段新增）

脚本 `06_subtype_score_heatmap.R` → `heatmap_subtype_x_score.png`（主图）+ `heatmap_subtype_x_score_by_group.png`（60 列按组别 split）+ `data/subtype_score_means.csv`

### 亚群特征指纹（top3 打分 + low，全组平均）
- Pure Type I: TypeI 0.82/Sarc 0.43/TypeII 0.33；low 恒为 SenMayo≈0.03
- Pure Type IIA: TypeII 0.78/Sarc 0.44/TypeI 0.41
- Pure Type IIX: TypeII 0.85/Sarc 0.43/TypeI 0.34
- OTUD1+(I): TypeI 0.81/Sarc 0.45/TypeII 0.35
- OTUD1+(II): TypeII 0.74/Sarc 0.45/TypeI 0.44
- RP_high(I): TypeI 0.85/TypeII 0.54/Sarc 0.50
- RP_high(II): TypeII 0.82/TypeI 0.53/Sarc 0.49
- LRP1B+(I): TypeI 0.85/Sarc 0.43/TypeIIa 0.28
- Specialized MF: TypeII 0.66/TypeI 0.46/Sarc 0.43
- RSS: TypeII 0.53/TypeI 0.42/Sarc 0.38

**模式**：所有亚群 top1-2 都是纤维类型打分（I 或 II）+ Sarcomeric 泛肌节结构程序；low 恒为 SenMayo（0.03）——肌纤维亚群间 SenMayo 无区分度。

### 打分区分度（CV = sd/mean 跨 10 亚群）
- **高区分（CV>0.2，亚群特征打分）**：TypeI 0.36（range 0.344-0.852）、TypeII 0.36、TypeIIx 0.29、TypeIIa 0.19
- **低区分（CV<0.07，状态打分）**：Stress 0.04、Inflam 0.03、TNFA 0.05、SenMayo 0.07、Atrophy 0.06、Insulin 0.06
- **解读规则**：纤维类型打分 CV 高 → 讲\"组成差异\"；应激/炎症/衰老打分 CV 极低 → \"组别敏感、亚群不敏感\"的状态信号，两者不要混为一谈。亚群×打分热图的价值 = 一眼看出哪些打分真正区分亚群（行 CV 高），哪些只是背景状态。

### 热图实现要点
- 主图：行=亚群、列=打分，按**亚群行** z-score（`t(apply(mat_all, 1, zscore))`），cluster 全关，打分列按类别固定顺序
- 进阶版：`column_split = grp`（6 组块）+ `HeatmapAnnotation(Group=...)`，列名 `paste(subtype, grp, sep=' | ')` 用 `dcast` 或逐列填 matrix
- 聚合 CSV 导出用 `fwrite(row.names=TRUE)` → 首列空表头 `""`，pandas 读要 `index_col=0`



用户提供的 Denervation = CHRNA1, CHRNG, CHRND, MYOG, SCN5A, SCN4A, KCNMB1, FBXO32, TRIM63, CTSL, GABARAPL1, BAG3, DCLK1, VIM, DES, RUNX1

评估结论：
1. **方向相反坑**：SCN4A 是成人骨骼肌钠通道，**去神经时下调**（被胚胎型 SCN5A 替换，SCN4A→SCN5A 转换）；与 SCN5A 同时放进打分会互相抵消 → 删 SCN4A 或单独作反向 marker
2. **缺经典 marker**：必须加 **NCAM1**（去神经最经典组织学 marker，Covault & Sanes 1985 PNAS PMID 3892537；Lai 2024 Nature 用 NCAM1+ 定义人肌去神经纤维）；建议补 MYH8（胚胎 MyHC）、NGFR/p75NTR
3. **与已有打分重叠**：FBXO32/TRIM63/CTSL/GABARAPL1/BAG3 与 Atrophy score 重叠，DCLK1 与 RegMyon 重叠，DES 与 Sarcomeric 重叠 → 去神经打分与萎缩打分共线性高，解读不能都讲；可保留但注明"伴随效应"
4. **保留核心**：CHRNA1/CHRNG/CHRND（AChR 亚基黄金标准）、MYOG、RUNX1、SCN5A、NCAM1

## 缺失打分建议（骨骼肌衰老 + 糖尿病运动研究）
- **P0 必加**：Glycolysis（与已有 OxPhos 配对，HALLMARK_GLYCOLYSIS gmt 下载）、去神经化（修正版）、AMPK-PGC1α 线粒体生物发生（PPARGC1A/TFAM/NRF1/ESRRA/PPARD，运动核心通路）、Autophagy、Adipogenesis（肌内脂肪浸润！）、Fibrosis
- **P1**：Angiogenesis、mTOR/蛋白合成、FAO（与 Glycolysis 配对）、Mitophagy（PINK1/PRKN/BNIP3）
- **思路提示**：比例没变 ≠ 功能没变——IIA 比例衰老↓ 但**剩余 IIA 细胞的 OxPhos/Glycolysis 打分**可能已经改善，这是"运动改善肌肉功能"的更深证据（组成 + 状态双维度）
- 用户认可的来源形式：每个打分带 PMID 或数据库链接（如 MSigDB HALLMARK_GLYCOLYSIS systematic name M5937，下载 gmt 或 grp 格式）

## 文献支撑（真实来源，PMC 可下载）
- Covault & Sanes 1985 PNAS PMID 3892537 — NCAM 去神经积累（奠基）
- Lai 2024 Nature PMID 38649488 — 人肌衰老多模态图谱（NCAM1 去神经纤维）
- Dos Santos 2025 Cell Rep PMID 40632651 — 快肌纤维去神经脆弱性
- Liu 2022 Nat Med — 去神经化/纤维类型重塑
- Soendenbroe 2026 Clin Sci PMID 42267670 — 去神经与衰老综述
- Gundersen 2011 Biol Rev PMID 21040371 — excitation-transcription coupling（运动分子开关）
- Liberzon 2016 PMID 26771021 — MSigDB Hallmark（HALLMARK_GLYCOLYSIS M5937）
