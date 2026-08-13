# 骨骼肌基因集/打分设计：来源评估与缺口分析（2026-08-12 实测）

场景：用户在 `E:\骨骼肌锻炼\pathway_score.xlsx` 有 14 个 AUCell 打分，问
① 自拟 Denervation 基因集怎么样 ② 还缺什么打分。用户明确要求：
**"我要真实文献和数据库的，你看我都提供了来源"——基因集交付必须带真实
PMID/DOI/数据库链接，绝不编造来源**（与"参数必须引用官方文档"偏好同源）。

## 用户的 14 个打分来源表（已核实，可作为同类任务的对照基准）

| Score | 来源 | 类型 |
|-------|------|------|
| Stress index | Machado 2021 (PMID 33609440) | 文献 |
| Type I / II / IIA / IIX | Murgia 2021 (PMID 34727990) | 文献 |
| Sarcomeric | WikiPathways WP383 (https://www.wikipathways.org/instance/WP383_r118423) | 数据库 |
| Atrophy | Taillandier & Polge 2019 (PMID 31325479) | 文献 |
| RegMyon | Chemello 2020 (PMID 33148801) | 文献 |
| OxPhos | MSigDB HALLMARK_OXIDATIVE_PHOSPHORYLATION | 数据库 |
| Insulin signaling | MSigDB KEGG_INSULIN_SIGNALING_PATHWAY | 数据库 |
| ROS | MSigDB HALLMARK_REACTIVE_OXYGEN_SPECIES_PATHWAY | 数据库 |
| SenMayo | MSigDB SAUL_SEN_MAYO | 数据库 |
| Inflammatory / TNFA | （xlsx 内其他行，同样带来源） | — |

用户给的基因集质量基准：每个打分都有 PMID 或数据库链接。Agent 建议新打分
时也必须达到同样标准。

## Denervation 基因集评估（用户自拟 16 基因，逐条核实）

用户基因集：`CHRNA1, CHRNG, CHRND, MYOG, SCN5A, SCN4A, KCNMB1, FBXO32,
TRIM63, CTSL, GABARAPL1, BAG3, DCLK1, VIM, DES, RUNX1`

| 判定 | 基因 | 依据 |
|------|------|------|
| ✅ 黄金标准 | CHRNA1/CHRNG/CHRND（胎儿型 AChR 亚基） | Tang 2009 MBC (PMID 19109424)：HDAC4-MYOG 正反馈环调控去神经后胎儿型 AChR 再表达 |
| ✅ 经典 | MYOG、RUNX1（去神经核心转录因子） | Tang 2009 同上；RUNX1 去神经诱导多篇支持 |
| ✅ 合理 | SCN4A/SCN5A（钠通道重塑） | Magnusson 2005 (PMID 15673457) 去神经基因表达改变 |
| ⚠️ 较弱 | KCNMB1（钾通道亚基） | 支持文献不如 AChR/NCAM 强，可保留 |
| ⚠️ 萎缩通用（非特异） | FBXO32/TRIM63/CTSL/GABARAPL1/BAG3 | 去神经诱导但也是萎缩/自噬 marker——**与 Atrophy score 重叠（FBXO32/TRIM63/CTSL/GABARAPL1）** |
| ⚠️ 再生方向 | DCLK1 | **与 RegMyon score 重叠** |
| ⚠️ 结构基因 | VIM/DES | **DES 与 Sarcomeric score 重叠** |
| ❌ 缺失！ | **NCAM1（CD56）** | **最经典去神经 marker 竟然没有**：Covault & Sanes 1985 PNAS (PMID 3892537, 330 引用奠基文献：NCAM 在去神经和瘫痪肌肉积累)；Illa 1992 (PMID 1371910)；Cashman 1987 (PMID 3296947) |

**修正结论**：核心保留 `CHRNA1, CHRNG, CHRND, MYOG, RUNX1, SCN4A, SCN5A,
KCNMB1` + **NCAM1** + 可加 `GAP43`；剔除与 Atrophy/RegMyon/Sarcomeric 重叠的
基因（或明说它们只是伴随效应）。重叠危害：去神经打分与萎缩打分相关性虚高、不独立。

## 打分缺口分析（14 个已有 vs 专业建议）

已有 14 个覆盖：纤维类型(4)、功能(2)、分解/应激(5)、衰老(1)、再生/代谢(2)。
**缺糖酵解是最致命缺口**——有 OxPhos 没有 Glycolysis，代谢轴只有一半，
而 T2D 肌肉核心病理就是代谢不灵活性（metabolic inflexibility）。

| 优先级 | 缺口 | 建议基因集 | 权威来源 |
|---|---|---|---|
| 🥇 | **Glycolysis 糖酵解**（最缺） | GAPDH, ENO1/3, PFKM, PKM, LDHA, ALDOA, PGK1, TPI1, HK2, SLC2A4 | MSigDB **HALLMARK_GLYCOLYSIS**（与已有 HALLMARK_OXPHOS 同体系补对称）；比值 OxPhos/Glycolysis = 代谢灵活性指数 |
| 🥇 | **Denervation 修正**（加 NCAM1） | 见上表修正版 | Covault 1985 (PMID 3892537)；Soendenbroe 2026 综述 Clin Sci (PMID 42267670) *Muscle fibre denervation in ageing*；Dos Santos 2025 Cell Rep (PMID 40632651) 快肌纤维脆弱性 |
| 🥇 | **AMPK-PGC1α 运动开关** | PRKAA1/2, PPARGC1A, TFAM, NRF1, ESRRA, PPARGC1B | Gundersen 2011 Biol Rev (PMID 21040371) excitation-transcription coupling（174 引用）；Insulin score 里已有 PRKAA1/2/PPARGC1A 可抽子集 |
| 🥈 | 自噬 Autophagy | ATG5, ATG7, ATG12, BECN1, SQSTM1, MAP1LC3B | Chen 2022 JCSM (PMID 35434959)；Picca 2023 Nat Metab (PMID 38036770) mitophagy |
| 🥈 | FAO 脂肪酸氧化 | CPT1B, ACADM, HADHA, PDK4 | Houten & Wanders 2010 (PMID 20195903, 723 引用)；OxPhos score 里已有 ACADM/ACADVL/HADHA/PDK4 可抽 |
| 🥈 | 合成代谢 mTOR-Akt | MTOR, RPS6KB1, EIF4EBP1, AKT1, IGF1R | Ham 2020 Nat Commun (PMID 32908143) NMJ/mTORC1 肌少症（165 引用）；Insulin score 里已有可抽 |

**效率建议**：Autophagy/FAO/Anabolic 可以从已有 Insulin/OxPhos score 抽子集，
不必新增基因集；只有 Glycolysis 和 Denervation 修正需要真新增。

## 核心文献下载（PMC 开放获取，已验证可达）

自动 PDF 下载常被 Cloudflare/EuropePMC 反爬拦截（download_pdf 失败是外部阻碍，
不要反复硬试）——给用户 PMC 链接自行下载即可：

| 文献 | PMID | PMC |
|------|------|-----|
| NCAM 去神经积累（奠基） | 3892537 | pmc.ncbi.nlm.nih.gov/articles/PMC391139/ |
| 人类衰老骨骼肌多模态图谱 | 38649488 | europepmc.org/articles/PMC11062927?pdf=render |
| 快肌纤维去神经脆弱性 | 40632651 | europepmc.org/articles/PMC13276618?pdf=render |
| 去神经肌肉转录响应 (Gramd1) | 40986355 | europepmc.org/articles/PMC12501200?pdf=render |
| NMJ 是肌少症焦点 (mTORC1) | 32908143 | europepmc.org/articles/PMC7481251?pdf=render |
| HDAC4-MYOG 去神经正反馈 | 19109424 | europepmc.org/articles/PMC2642751?pdf=render |
| 去神经肌肉基因表达改变 | 15673457 | europepmc.org/articles/PMC7111415?pdf=render |
| 去神经与衰老（最新综述） | 42267670 | europepmc.org/articles/PMC13266841?pdf=render |
| excitation-transcription coupling | 21040371 | europepmc.org/articles/PMC3170710?pdf=render |

## 关键工作流教训

1. **基因集/打分建议必须先查证再给**（search_papers + query_ncbi），给真实
   PMID/DOI/数据库链接；用户会拿自己的来源对照。绝不凭预训练知识编来源。
2. **评估自拟基因集的套路**：逐基因判定（黄金标准/经典/合理/弱/重叠）→
   找出最经典却缺失的 marker（本例 NCAM1）→ 查与已有打分的重叠基因 →
   给出修正版。重叠基因列表直接决定打分独立性。
3. **"打分建议"要落到优先级 + 可执行**（基因列表 + 来源 + 从已有 score 抽子集），
   不是泛泛说"建议加自噬打分"。
4. **比例分析（组成）之外补打分（状态）**：比例没变 ≠ 功能没变——按亚群×组别
   算打分均值/中位数画同样的 6 组箱线图，组成 + 状态双维度讲同一个故事。
