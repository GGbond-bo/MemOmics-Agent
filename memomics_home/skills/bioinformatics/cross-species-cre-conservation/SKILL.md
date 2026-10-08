---
name: cross-species-cre-conservation
category: GWAS/Genetics
python_packages:
  - docx          # python-docx（交底书 docx 生成/校验）
  - pandas
  - numpy
  - matplotlib
  - PIL           # pillow（出图健康检测：单一颜色/空白图判定）
description: >
  Cross-species CRE (cis-regulatory element) conservation assessment: five-layer pipeline
  (sequence → epigenetic → 3D → functional → CRECS) quantifying whether one species'
  regulatory elements (e.g. monkey) can substitute for another's (human) in brain research.
  Patent-ready, A/B/C/D tiers. Data: ENCODE ATAC/ChIP/Hi-C, UCSC phastCons/GERP, GTEx,
  public monkey brain epigenome.
  ⚠️ 09-05 重构：对称 min 已证伪 → 独权改「主-参考非对称」（人侧给强度 Z₁ + 猴侧只给方向 w(Z₂)）；核心元件 = 人侧|Z|≥12 + 猴侧p<0.05 + 同向 = **357（all 口径，09-11 锁死；continuous 为 336）**，见「口径重构」小节。
  ⚠️ 09-12：方向门控前置检验五项**全否**"猴侧方向可信" → claim 分层（方法层留/效果层撤）；引用数字前先确认口径。
  ⚠️ 09-12b/c：同向率归因四探针（主因=网格未对齐）→ `concordance-rate-attribution.md`；三修复实测（①唯一实质修复、③无效）→ `three-fix-results-and-gate-collapse.md`。
  ⚠️ 09-12d：交付件卫生（版本升级须 OCR 内嵌图、循环论证→基线横评三元组、权项分层、统一网格须配 z̄=Z/√n）→ `patent-deliverable-hygiene.md`
  ⚠️ 09-12e：对应性核查+遮挡假阴性（「0 对重叠」≠无遮挡）→ `deliverable-consistency-and-figure-qa.md`
  ⚠️ 09-12f：附图须黑白线条版（指南 2.4 不得着色）+ 送代理形式要件 → `patent-drawing-and-formal-requirements.md`
trigger:
  when:
    # RED — 交付件形式合规（附图黑白 / 送代理前要件）
    - user asks "交底书也要黑白线条图吗" / "出一套黑白版本" / 附图"是不是要黑白" / "不得着色"
    - user asks 送代理前还缺什么 / 检索记录 / 检索式 / IPC 分类号 / 对比文件 D1-D3 / 摘要附图 / 从权实施例落点
    # RED — 对外送阅版交付（给老师/律师看 / 老样式 / 零备注 / 图片核验）
    - user says "参考以前的填写样式" / "按旧版的样子" / "拿给老师看" / "交给律师审核"
    - user says "不要有什么备注之类的" / "不要备注" / "别写版本说明" / "说清楚过程、怎么做的、新颖性"
    - user asks "图片记得确认对不对" / "图都检查一下对不对" / 要求核验内嵌图内容正确性
    - user asks 交付件里"哪个能出专利" / 问某方向"能不能行得通"（→ 先判方向死活，再谈交付形态）
    # RED — 同向率/跨物种一致性归因
    - user asks "跨物种同向率为什么这么低" / "同向率 40% 什么原因" / "是猴子的数据吗"
    - user asks "为什么随机反而更高" / "能不能有更好的算法" / "更好的算法"
    - user asks "当前计算的方法还有可能改变吗" / "能设计更好的办法吗" / "有没有更好的统计量" / "同向率是怎么算的"
    # RED — 定义层单问（「XX 是怎么计算的？简单一点」）→ 只答定义式+代码+数字，禁带归因
    - user asks "同向率是怎么计算的" / "随机是怎么计算的" / "46% 怎么算的" / "这个指标是怎么算的" + "简单一点"（→ `references/concordance-and-null-definition-basics.md`）
    - user asks "当前算法对不对" / "z 值的做法对不对" / "为什么要用 z" / 任何对某个统计量「定义」本身的追问（→ `references/tile-level-da-significance-floor.md` §9）
    - user asks "为什么非得是 12" / "τ_A 怎么定的" / "阈值是不是 1.96"
    - user asks "你确定你用了这个方法了吗" / "需求里这个方法真用了吗" / 点名方法（经验贝叶斯 / local FDR / 五态判定）是否真落地 / "之前的 z 不用了吗"
    - user asks 跨物种衰老保守性/发散的同类文献检索
    # RED — mandatory skill_view triggers
    - user mentions "CRE" / "调控元件" / "cis-regulatory" / "顺式调控"
    - user mentions "enhancer conservation" / "增强子保守性"
    - user mentions "CRECS" / "跨物种CRE" / "cross-species CRE"
    - user mentions "cross-species ATAC" / "跨物种ATAC" / "跨物种染色质"
    - user mentions "chromatin accessibility conservation" / "染色质可及性保守"
    - user mentions "enhancer replaceability" / "enhancer substitutability"
    - user asks "猴脑能替代人脑做调控元件研究吗"
    - user mentions "LiftOver cross-species regulatory"
    - user mentions "phastCons" / "GERP" in cross-species context
    # RED — 实施层执行故障（长任务静默消失 / 配对脚本太慢）
    - user asks 脚本"跑到一半就没了" / "没报错就退出" / "进程消失了" / "是不是卡死了"
    - user asks 跨物种配对脚本"跑得太慢" / "内存爆了" / 如何向量化加速
  rules:
    - Framework assumes no prior CRE knowledge from user — explain concepts with analogies
    - Always start with Part 0 (beginner primer) for users who self-identify as beginners
    - Default comparison pair: human vs rhesus/cynomolgus macaque
    - Patent angle: this is a method invention, not a scientific discovery — frame accordingly
    - Data is public (ENCODE/GEO/UCSC) — no wet-lab experiment needed
---

# 🧬 Cross-Species CRE Conservation Assessment

> 🔴 **当前方向（2026-09-15 v21 定案，先读这行）**：独权承重已从「可替代性 / 跨物种方向一致性」**永久换柱**为**三柱 AND（L1 序列保守 + L2 跨物种可及 + L3 年龄效应）**，创造性锚 = **衰老维度**（五件对比专利 D1–D5 全无年龄梯度）。「可替代性」降为权 10 下游用途，**不得再回头**。发明名称 = 「跨物种保守衰老调控元件的筛选方法」。详细 → `references/v21-three-pillar-reframing.md`（含死方向的负结果铁证、v21 三柱框架、五件对比表、数据落位、四件已交付文件、通用工作流教训）。
>
> ✅ **2026-09-15 实跑完成**：三柱 AND 得 **150 个核心元件**（16,029 → L1 3,180 → L1∧L2 1,604 → AND 150；175 组阈值扫描、19 组落黄金区间 [30,500]）；核心元件中仅 **48/150（32%）**两侧年龄效应同向 ⇒ 实证「本方法不依赖方向一致性」。三项补跑（猴侧 L1 独立对照 2.0 倍富集 / ρ=0.764、衰老签名后验富集 fold 4.53 p=7.7e-05、装置端端到端复现）全部完成。
> 📤 **对外送阅版交付规范（给老师/律师看的件）→ `references/v21-deliverable-and-external-review-spec.md`**：老样式骨架 + **黑白附图** + **零备注** + 图片 QC 两轨 + v21 四文件列归属坑 + **批量核验纪律（防被判循环失控）** + 正本数字全表。

## Overview

A five-layer quantitative framework for evaluating whether cis-regulatory elements (CREs) — enhancers, promoters, silencers, insulators — from one species can substitute for another in brain research. Designed for patent-oriented professional master's students who need an applied, data-driven method with clear industrial value.

**Core insight**: While cell-type composition differs between species (e.g., human vs monkey brain), CRE-level conservation is more fundamental, less confounded, and directly relevant to drug-target validation and model selection.

## Default Assumptions

| Parameter | Default | Notes |
|-----------|---------|-------|
| Species pair | Human (hg38) vs Rhesus macaque (rheMac10) | ~25 Mya divergence |
| Tissue | Brain (hippocampus, prefrontal cortex, etc.) | Expandable to other tissues |
| Data sources | ENCODE, PsychENCODE, GEO, GTEx, UCSC | All public, no wet-lab needed |
| Genome chain | UCSC hg38 ↔ rheMac10 LiftOver | Reciprocal best-hit required |

## Five-Layer Pipeline

```
L0: Data Collection → L0.5: Preprocessing → L1: Sequence → L2: Epigenetic
→ L3: 3D Structure → L4: Functional → L5: CRECS Score → Validation
```

### L0 — Data Collection (all public)
Data needed per species:
1. **ATAC-seq / DNase-seq peaks** (BED) — open chromatin regions = candidate CREs
2. **H3K27ac ChIP-seq** (bigWig) — active enhancer marks
3. **H3K4me3 ChIP-seq** (bigWig) — active promoter marks
4. **CTCF ChIP-seq** (BED) — insulator binding
5. **Hi-C / HiChIP** (optional) — 3D chromatin contacts
6. **RNA-seq** (for L4 validation)

Key human sources: ENCODE, PsychENCODE, GTEx
Key monkey sources: Meng 2026 Nat Commun (cortex ATAC), Luo 2020 Cell (hippocampus Hi-C), monkey brain epigenome project

### L0.5 — Preprocessing
1. Uniform genome versions: human hg38, monkey rheMac10
2. Download UCSC chain files for LiftOver
3. One-to-one ortholog gene pairing (biomaRt / Ensembl)
4. Reciprocal LiftOver of CRE coordinates

### L1 — Sequence Conservation
Metrics:
- **Sequence similarity** (Needleman-Wunsch global alignment)
- **phastCons score** (UCSC 100-way — pre-computed, just query)
- **GERP score** (genomic evolutionary rate — pre-computed)
- **TF binding site conservation** (JASPAR FIMO motif scan)

Orthologous CRE threshold: LiftOver reciprocal overlap ≥ 50% AND sequence similarity ≥ 70%

### L2 — Epigenetic Conservation
Metrics:
- ATAC signal correlation between orthologous CRE pairs
- H3K27ac signal difference (normalized)
- Cell-type specificity conservation (Jaccard of open cell types)

Formula: `E_conservation = 0.6 × cor(ATAC) × (1 - normalized_H3K27ac_diff) + 0.4 × cell_type_Jaccard`

### L3 — 3D Structure Conservation (when Hi-C available)
Metrics:
- Enhancer-promoter loop sharing
- TAD boundary position conservation
- A/B compartment concordance

Fallback (no Hi-C): Use "nearest gene" approximation + ABC model predictions.

### L4 — Functional Conservation
Metrics:
- Target gene expression correlation (snRNA-seq)
- eQTL effect conservation
- GWAS colocalization (coloc)

### L5 — CRECS Composite Score

```
CRECS = 0.20 × S_sequence + 0.35 × S_epigenetic + 0.20 × S_3D + 0.25 × S_functional
```

Four-tier classification:
| Grade | CRECS | Meaning | Application |
|-------|-------|---------|-------------|
| **A** | ≥ 0.75 | High conservation, monkey can fully substitute | 🟢 Drug screening priority |
| **B** | 0.50–0.75 | Moderate, usable with extra validation | 🟡 Use with caution |
| **C** | 0.25–0.50 | Low conservation, limited substitutability | 🟠 Specific conditions only |
| **D** | < 0.25 | Species-specific, not substitutable | 🔴 Find alternative model |

### Validation Layer
1. **Evolutionary anchors**: known ultra-conserved CREs → expected Grade A
2. **Negative controls**: randomly shuffled regions → expected Grade D
3. **GWAS cross-check**: brain disease GWAS loci → expected high conservation in relevant cell types

## Patent Angles

| Innovation Point | Prior Art Gap | Our Advantage |
|-----------------|---------------|---------------|
| CRECS composite scoring | Only single-dimension comparisons exist | 4-dimension weighted, brain-specific |
| Reciprocal LiftOver CRE pairing | Unidirectional mapping, high false positives | Bidirectional + sequence filter |
| A/B/C/D four-tier with cell-type resolution | No systematic output of "which can substitute" | Directly guides model selection |
| GWAS cross-validation | Assessment methods lack independent validation | Human disease genetics validates biological meaning |
| Adaptive weights via debate_analysis | Weights are subjective | Biologically validated post-hoc adjustment |

**Background Art（现有技术定位，2026-09-04 修正，写新颖性/创造性论证前必读）**：真正的题意 prior art 是 **de Mendoza A. "Genome synteny reveals hidden enhancer conservation." Nature Genetics, 2025 Jun, DOI 10.1038/s41588-025-02194-2**——这是一篇 **News & Views 评论**（单作者 de Mendoza，研究 ZF 转录因子/增强子进化），它评论的原始研究讲 TFBS shuffling + 跨物种 ATAC footprinting + 隐藏增强子保守性/共线性 IC 元件。⚠️ 历史上曾有会话把此 prior art **误记为 "Phan 2025 Nat Genet"**——那是记忆转录错误，正确 citation 是 de Mendoza 2025。引用现有技术做专利创造性论证时应以 de Mendoza 2025 为准，声明增量 = "从检出保守元件 → 量化可替代性并分级"。

## Substitutability Scoring (S-score) Method — 可替代性评分（独权核心算法）

**这是"方向预测器"换成"可替代性评估方法"的具体落地公式**（2026-09-04 实测，脚本 `scripts/v5_substitutability_score.py`）：

```
S(g) = min(|Z_monkey|, |Z_human|) × sign(Z_monkey · Z_human)
```

- `|S|` = **较弱一侧**的效应量（双侧都强才可信，天然防"单侧强+另一侧弱"假阳性）
- `符号` = 方向一致性（同向 + / 反向 −）
- 输入：每对 ortholog 已算好的双侧标准效应量 Z_m / Z_h（来自年龄回归 Stouffer 组合）

**四分类（阈值 τ=1.96 对应双侧 p<0.05）**：

| 级 | 条件 | 含义 | 决策 |
|----|------|------|------|
| A | Z_m·Z_h>0 且 min(|Z_m|,|Z_h|)≥τ | 同向保守可替代 | ✅ 可靠可替代元件 |
| B | Z_m·Z_h<0 且 min(|Z_m|,|Z_h|)≥τ | 反向（伪替代） | ⚠️ 方向相反 |
| C | max(|Z_m|,|Z_h|)≥τ 但方向/双侧不齐 | 单侧分歧 | 🔧 仅单物种显著 |
| D | max(|Z_m|,|Z_h|)<τ | 双侧不显著 | 🚫 排除 |

**置换检验校准**：打乱 ortholog 配对 N 次（如 10000），统计 A 级数量的空分布 → 定显著性（`p_two = min(≥obs, ≤obs).mean() × 2`）。

**实测结果（人猴海马，16031 ortholog 基因对）**：A=1904(11.88%) / B=3487(21.75%) / C=7562(47.17%) / D=3078(19.20%)；A 级真实 1904 **显著低于** 随机期望 2012.7（双侧 p=0.0008）。

**关键解读（反直觉 = 方法鉴别力的证据）**：真实 ortholog 关系下 A 级（同向保守）基因**少于**随机配对，说明"跨物种同向保守的衰老脆弱元件是稀缺的（仅 11.88%），绝大多数是物种特异方向"——评分方法能精确筛出这 11.88%，而不是随便抓一堆都判"保守"。A 级 top 基因全是海马谷氨酸能突触/神经元结构核心（SLC1A2/NRXN1/SYT1/EPHA5/EPHA6），双侧同向显著下调。

## ⚠️ 2026-09-05 口径重构：主-参考非对称（取代对称 min，专利独权最终落地）

**上方「S = min(|Z_m|,|Z_h|) × sign」四分类框架已在真实数据上被证伪，专利独权已重构为主-参考非对称结构。** 这一轮是口径大决战的核心教训，写死如下。

### 为什么对称 min 失败（三条踩死的统计事实）

| 事实 | 数据 | 含义 |
|---|---|---|
| 全体基因人猴同向比例 | **0.4156**（16031 基因） | 低于随机 0.5，方向整体非"同向可替代" |
| Z_human vs Z_monkey 相关 | **r = −0.0627** | 略**负**相关，人猴基因级方向近乎无关 |
| 旧公式下的 B(反向) vs A(同向) | **3487 > 1904** | 反向比同向还多 → 旧公式的"判别力 p=0.0008"测的其实是**反向显著多于随机**，是"不可替代"证据，不是"可替代"证据 |

**结论**：旧框架「显著性同向」（|Z|>1.96 且同向）筛不出"同向保守"——双侧 Bonferroni 显著 1207 个里反向 800 > 同向 407。**显著性(p)本身筛不出方向一致性**，这是旧框架被推翻的根本原因。

### 主-参考非对称（独权最终公式）

```
S = Z₁ × w(Z₂)          # Z₁=人侧(主体,大样本)强度; w(Z₂)=猴侧(参考,小样本)方向门控
```
- Z₁（主体物种效应量）= 评分强度**唯一来源**
- w(Z₂) = 方向门控：猴侧方向可信且同向 = +1；反向 = −1；方向不可靠（低于方向可信度阈值）= 0

### 最终口径（唯一数字，写死）

**核心元件（A 级）= 357 个**（**all 口径，2026-09-11 锁死**）= 人侧 |Z_human| ≥ 12（约前 9% 分位）+ 猴侧 p<0.05（方向可信）+ 同向。

> ⚠️ **口径变更（2026-09-11，引用本 skill 任何数字前先确认口径）**：本节下方沿用的 **336** 是 **continuous 猴输入口径**（`monkey_ageDA_continuous.csv`，集群导出、每样本平均可及性、无变换）。用户 2026-09-11 决定把输入切到 **all 版**（`M2/{human,monkey}_ageDA_all.csv`，用户自有导出代码、`getGroupSE` 原始 counts 求和、`log2(CPM+1)`），全套数字按 all 重算后为 **357**；交付件（交底书 v9 + 6 份 md + 图3/图4）已全部改为 357 口径。两版对应关系、影响归因与"能不能只换数字"判据 → 「🔬 口径切换影响归因」小节 + `references/caliber-switch-impact-attribution.md`。

关键取舍：方案 A 初版提「猴侧只要方向同向、不卡强度」→ 得 537，但**猴侧方向是纯噪声**（整体 shuffle p=0.8，强效应基因里同向占比仅 0.38 < 0.5），"只要同向不卡显著性"会混入约一半假同向。所以**"方向可信"的最低可辩护标准 = 猴侧 p<0.05**（这正好对应 claim §3 里 w(Z₂)=+1 的"Z₂ 方向达到预设可信度"）。336 内再分层：37 = 双侧 |Z|≥12 双高（SLC1A2 领衔谷氨酸-突触稳态轴，最高置信子集）；24 = 反向双高（物种分歧，仅观察性证据不 claim）。

### 口径漂移教训（用户强烈不满的根因，见 Pitfall 15）

曾出现 1904/3487/37/537/336 五个不同数字，用户质问"到底是多少？每次回答都是不一样的"。根因 = **阈值口径在轮间漂移 + 交付文件停留在旧口径没跟着结论走**。修复：锁死唯一口径 → 同步重写全部交付文件到该口径 → 数字变化必须显式给出口径对照表（而不是让数字在对话里漂移）。

交付产物（可复现）：`E:/专利/交付_跨物种衰老可替代性专利/`（README.md 为总索引，含 336 复现代码、`结论_口径决策链.md` 为完整演进史）。

## 📐 输入口径对账与复现溯源（口径判定方法论，2026-09-11 实证）

**触发场景**：用户问「专利/论文里这组数字（N / A / B / C / D / ρ / 核心元件数）到底是哪个输入文件跑出来的？」「用我给你的文件能不能复现？」——即**正本数字 ↔ 输入口径的归属判定**。判据要真跑真判，不要预设结论。

### 判定框架：先总量，再逐实体

```
总量对账（N / A / B / C / D / ρ / 置换均值）   ← 只能给"像不像"，不能定性
        ↓ 不吻合时【不要调阈值、不要换参数】
逐实体对账（挑代表性实体的逐字段值：Z / p / n_tiles）  ← 定性的那一刀
        ↓
三判决：
  ① Z 值逐位一致（±1e-4，最大差 0.0000） → 同一输入表；残差只在聚合/桥接取舍（<1% 可接受）
  ② Z 值普遍不等（中位差~1.8，最大差~20） → 输入表不同，调参无用
  ③ 实体数相同但值不同（n_tiles 同为 151，Z 一个 −3.3395 一个 −1.5678）
     → 同一套坐标网格、不同 r/p 值体系 ⇒ 一定是另一张输入表
```

**为什么逐实体比总量硬**：总量是 N 个噪声聚合后的标量，两张不同的输入表也可能撞出相近总量；逐实体比对是 N 个独立观测的联合检验，撞不上。实测判据表（本次）：正本 vs continuous 版复现 = 15965 共有实体 **100.0% 逐位一致（最大差 0.0000）**；正本 vs all 版复现 = **0.0% 一致（最大差 20.10）**。

### 三个廉价且决定性的取证动作

1. **文件名考古**：`ls -lt` 按 mtime 排中间产物找链式关系。中间产物**文件名里常直接写着口径**——本次铁证 `P3_L1_data/v4b_gene_conservation_continuous.csv`、`v4b_conservation_stats_continuous.txt`，`continuous` 是原始作者写进文件名的。
2. **stats / 日志正文考古**：正本数字常原样躺在中间产物正文里。本次 `v4b_conservation_stats_continuous.txt` 正文即「ortholog 基因对: **16031** / 高置信保守相似基因: **1904** / 加权 Spearman **ρ = -0.0810**」= 专利三个数字的原文。
3. **时间链**：`monkey_ageDA_continuous.csv(01:05) → v4b_*_continuous.csv(01:10) → v4b_*_table.csv(02:16) → v5_substitutability_all.csv(12:41)`——正本产物必然晚于其输入且紧邻。

### 单脚本多口径改造（禁止复制脚本）

```python
OUT_DIR    = os.environ.get("OUT_DIR", os.path.join(M2_DIR, "pipeline_out"))
MONKEY_CSV = os.environ.get("MONKEY_CSV") or os.path.join(M2_DIR, "monkey_ageDA_all.csv")
```

一份脚本 + 环境变量注入即可跑多口径，`OUT_DIR` 隔离保证旧产物不被覆盖；默认值保持原口径 ⇒ 向后兼容。复制出 `repro_continuous.py` 之类的"兄弟脚本"= 维护异味（改一处忘另一处，两边以后必然漂移）。
⚠️ **口径对账跑出的多份产物属诊断中间物，只许留在 scratch 目录，不得进交付目录**——交付目录永远只有唯一口径的一套产物（呼应 Pitfall 15 与用户"禁止多版本产物并存、复现不得靠手工修正"的要求）。

### 报告必须如实记录实际输入

对账报告的输入行必须从变量取（`os.path.basename(MONKEY_CSV)`），**禁止写死叙述**——见 Pitfall 17。

### 别假设"两版只是 1-based 差异"

本次两套猴 ageDA 表：continuous 首行 `NC_088375.1, 19500, 19999`（0-based）、all 版首行 `NC_088375.1, 20001, 20500`（1-based），**偏移 501bp、tile 数 5,674,190 vs 5,296,656（差 37 万）**——是两套**独立**的 ageDA 计算结果，不是同一网格的偏移。差异幅度先 `head` + `wc -l` 实测，别从"1-based / 0-based"推断。

### 决定性验证：双输入全流程对照（2026-09-11 实测闭环）

同一脚本、同一 human 输入，**只换猴侧输入**跑全流程 → 直接判定正本归属：

| 指标 | 专利正本 | **continuous（567万 tile）** | all（530万 tile） |
|---|---|---|---|
| ortholog 对 | 16031 | **16012 (−19)** | 16010 (−21) |
| A 同向 | 1904 | **1905 (−1)** | 2335 (+431) |
| B 反向 | 3487 | **3474 (−13)** | 3070 (−417) |
| C 单侧 | 7562 | **7554 (−8)** | 7677 (+115) |
| D 无 | 3078 | **3079 (+1)** | 2928 (−150) |
| 置换均值 A | 2012.71 | **2011.42 (−1.3)** | 2617.14 (+604) |
| 置换双侧 p | 0.0008 | **0.0006** | 0.0000 |
| 加权 ρ | −0.081 | **−0.081（完全一致）** | −0.195 |
| v6 对 | 15178 | **15182** | 15180 |
| v6 A/B | 402/222 | **404/223** | 794/731 |
| v7 R² | 0.2785 | **0.2825** | 0.3472 |

⇒ **正本口径 = `E:/专利/monkey_ageDA_continuous.csv`**（8 项差 ≤13、ρ 完全一致、M6 差个位数 ⇒ 同一输入表）。产物隔离：`pipeline_out/`（all 版）vs `pipeline_out_cont/`（continuous 版），互不覆盖。

**⚠️ 2026-09-11 更正：上述残差不是"坐标网格差 1bp"——该归因已实测证伪，两层都不是坐标问题。**

| 残差 | 实测根因 |
|---|---|
| A/B/C/D 差 ±13（16031 vs 16012）| **锚定实现差异**：早前复现脚本重写了基因锚定；换回正本原版 `P3_L1_data/repro_m3_from_M2.py` 的 `anchor()`（`mid=(s+e)//2` + `WINDOW=2000` + `searchsorted` 反查 + **first-overlap-wins 回溯**）逐字复刻后 → **16031 对逐位一致、残差归零**（Z_monkey / Z_human / n_tiles 全 max\|Δ\|=0） |
| continuous vs all 两个猴表本身 | **数据处理管线不同**，非坐标写法（见下表）|

**判别铁律（本次两度踩中）**：**坐标体系差异只会平移坐标标签，不会改变 r/p 数值。** r 值大面积不同（corr≈0.89、tile 数差 37 万）⇒ 必然是**管线/变换层**差异。迁移到其他任务同样适用：差异先分三层定位——坐标层（值不变）/ 管线层（值大面积变）/ 实现层（实体数差 <1%）。

**两版实测管线对照（差异全表）**：

| 环节 | all 版 `M2/monkey_ageDA_all.csv` | continuous 版 |
|---|---|---|
| 生成链 | `l3_monkey_ageDA_fix_rowData.R` → `fix_ageDA_coords.R` | `export_monkey_tile_matrix_continuous.R`（集群导出）→ `compute_monkey_continuous_age_r.R` |
| 聚合 | `getGroupSE(scaleTo=NULL)` 原始 counts **求和** | `mat %*% J %*% Diagonal(1/colSums(J))` 每样本**平均可及性**（0~1 比例）|
| tile 过滤 | `rowSums(cnt) >= 2*ncol(cnt)`（≥40 counts）| 仅去零方差 |
| **数值变换** | **`log2(CPM + 1)`**（RNA 口径）| **无变换**（原始比例）|
| 坐标 | `(idx−1)*500+1`（1-based，**被就地改写**）| ArchR 原始（0-based）|
| tile 数 / 体积 / mtime | 5,296,656 / 456 MB / 09-03 01:30 | 5,674,190 / 448 MB / 09-04 01:05 |

方法学取舍：TileMatrix 二值化（每细胞 0/1）⇒ tile counts 本质是"细胞数"不是测序 reads 数 ⇒ `log2(CPM+1)` 属口径错配，"每样本开放细胞比例"更贴合 ATAC 语义。

**"修复版"标签反转（用户按字面质疑"你改了我的数据"时必讲）**：被**就地改写**的其实是 all 版——`fix_ageDA_coords.R` 头部自述"6 个文件坐标已就地修正"，用 `fwrite(d, f)` 直接改写 6 个 CSV；continuous 版是**全新计算的新文件**，无就地修改动作。判据 = 看 `fwrite`/`write.csv` 的目标是输入文件本身还是新文件名。

**数据真实性自证（质疑"是不是真实数据"的标准动作）**：不辩解，做复算——① 体量证据（448 MB / 567 万行，物理上无法手改）② 生成脚本原文（零硬编码、纯公式）③ 用用户原始输入独立重算并**逐位比对**（本次 `max|Δr| = 1.11e-16`，double 机器精度量级 ⇒ 等价于完全一致）④ 把命令交给用户自己跑。完整配方 + 判读标准见 `references/data-integrity-self-proof.md`。

**聚合指纹（比逐实体更省的快速判据，先看这个再决定要不要逐实体）**：
**双侧显著总数 A+B 几乎不变、但 A/B 之间的 sign 分裂大幅变化 ⇒ 换的是 r 值体系（另一张输入表），不是阈值也不是桥接。**
本次：A+B = 5391（正本）vs 5405（all 版）只差 **0.26%**，而 A 相差 **+431（23%）** —— 显著性口径一致、方向口径不同，一眼锁定 sign(Z_m·Z_h) 来源（即猴侧 r/p 值体系）。

**已知残差（尚未解释，勿当已解决）**：v7 常数项与斜率仍不吻合——正本 `Z_h = −0.1626 + 1.0437·Z_m` vs continuous `−0.1914 + 1.1975·Z_m`（R² 量级一致 0.2785 / 0.2825）。属遗留项，需再查（回归样本筛选口径、是否只取同向子集等）。

**claim 缺口（与选哪个口径无关，必须补）**：`人侧 |Z|≥12 + 猴侧 p<0.05 + 同向 → 336/37` 这一步**目前没有脚本实现**——专利 claim 的核心数字处于"无脚本可复现"状态。交付前必须补脚本并跑通（呼应 Pitfall 15 的唯一口径锁死原则）。

配套：`scripts/diff_two_runs.py`（逐实体对账脚本，直接跑）、`references/input-provenance-reconciliation.md`（本次完整证据链与命令配方）。

## CRE 级下钻：启动子近端 Promoter-Proximal CRE Scoring（v6）

**基因级 S 评分 → CRE 级下钻的关键一步**（2026-09-04 实测，脚本 `scripts/v6_promoter_cre_score.py`）：

**动机**：基因级 S 评分锚的是"基因本体区域"（same gene 内全部 tile 的 Stouffer 聚合），专利要扩大实质保护范围需下钻到 CRE 级。而猴侧数据染色体命名 `NC_088375.1` = 食蟹猴 T2T-MFA8v1.1，**没有 → hg38 的官方 liftover chain**（2024 新组装，UCSC/Ensembl 未收录），本地只有 `rheMac3ToHg38`（恒河猴旧版，不可混用）。

**正路：ortholog 基因锚定（绕开坐标 liftover）**——复用 v4b 的「基因注释 + tile 锚定 + Stouffer Z 聚合」链路，只把锚定窗口从「全基因 body」收窄到「启动子近端 TSS±2kb」：

```
v4b 全 body 锚定（tile 中点 ±2kb overlap 基因 body）
  → v5  S 评分（min(|Z_m|,|Z_h|) × sign，四分类，基因级）
  → v6  启动子近端锚定（tile 中点 ∈ [TSS−2kb, TSS+2kb]，重新 Stouffer → CRE 级）
```

**TSS 精确定位（关键，否则 ±2kb 窗口错位）**：
- 猴：NCBI feature table `GCF_037993035.2_T2T-MFA8v1.1_feature_table.txt.gz`，gene 行 tab 分隔列 p[6]=chrom(NC_088xxx) / p[7]=start / p[8]=end / **p[9]=strand** / p[14]=symbol / p[15]=GeneID；TSS = strand=='+' ? start : end
- 人：`human_ortholog_hg38_full.csv` 只有 chr/start/end **无 strand**，TSS 用 start 近似（chr 需补 'chr' 前缀）

**实测结果（人猴海马，启动子近端 CRE = TSS±2kb，15178 ortholog 对）**：
A=402(2.65%) / B=222(1.46%) / C=5840(38.48%) / D=8714(57.41%)；置换检验 A 级真实 402 **显著高于** 随机 300.4（双侧 p<0.0001）。

**关键反差（CRE 级优于基因级的实质证据 = 专利创造性论据）**：

| 粒度 | A 级占比 | 置换检验 | 含义 |
|---|---|---|---|
| 全基因 body（v5） | 11.88% | p=0.0008（**稀缺**，1904 < 随机 2013） | 混入物种特异的内含子/远端信号，稀释保守信号 |
| 启动子近端 CRE（v6） | 2.65% | p<0.0001（**富集**，402 > 随机 300） | 调控核心区受进化约束，人猴衰老方向反而更一致 |

**启动子近端 CRE 比全 body 更精准捕获跨物种同向保守信号**——把粒度下沉到启动子近端，去掉了基因 body 的物种特异背景噪声。基因级"稀缺" vs CRE 级"富集"的反向对比，正是"粒度是方法实质进步"的量化证据。A 级 top 基因换成 RFX4/EDNRB/HES5/CXCL14/SLC13A5；v5 榜首 SLC1A2（EAAT2 谷氨酸转运体）在 CRE 级仍是 A 级成员（Z_m=−3.80 / Z_h=−4.80），说明其衰老脆弱性真实落在启动子调控区，非基因 body 统计假象。

**Simpson 悖论警语（答辩必主动声明，防被质疑"符号矛盾=计算错误"）**：gene-body vs intergenic 的衰老方向可能存在真实结构差异——人侧"基因本体区可及性**上升**（基因内负 tile 仅 46.5%）、基因间区下降（68.5%负），导致 tile 级偏负（58.8%）但基因级偏正（ΣZ=+20115）的翻转；猴侧两者一致偏负（基因级 80.4%负）。这是**真实生物学结构，不是脚本 bug**。判别要诀：按"基因内负 tile 占比"分层验证（人 46.5% vs 猴 60.8%），而非只看总体符号占比；同一 pipeline 下猴侧"放大负向"、人侧"基因区域翻正"，分叉点在"基因内负 tile 占比"这一层。

## 方法有效性三重验证与坐标落点（v7–v9，2026-09-04 实测）

S 评分闭环后，用三重验证把「可替代性」从形容词变成可执行、可主张、可辩护的步骤。

### v7 跨物种外推可执行（预测外推 + 误差量化）—— 把「可替代性」变可执行步骤
- 同向基因拟合 `Z_h = −0.163 + 1.044·Z_m`（R²=0.278，pearson r=0.528，n=7502）
- A 级（最保守 402）猴→人相关 r=0.683（slope=1.273，比全体同向 0.528 更强 → **「越保守同向越能外推」是"可替代性"成立的量化证据**）
- LOOCV RMSE 1.642（全体同向）/ 1.509（A 级）
- 可执行外推步骤：S1 算猴 Z_m → S2 预测 Z_h_pred = a + b·Z_m → S3 报告误差。脚本 `scripts/v7_extrapolation_baseline.py`

### v7 A/B baseline 对比 —— 证明 S 非显而易见（创造性论据）
以「猴→人可预测性」为统一标尺：
| 方法 | 猴→人可预测性 |
|---|---|
| 单物种（只用猴 Z_m）| spearman 0.064（无方向外推力）|
| 方向一致性比例 | 0.494（≈随机 0.5）|
| 随机配对（零模型）| −0.0001 |
| **本方法 S（同向）** | **pearson 0.528**（置换 p<0.0001）|

S 同时用「方向 + 双侧弱侧效应量」，外推力远超单物种与随机——这是回答「本领域技术人员能想到」的硬证据。

### v8 年龄标签 shuffle —— 检验年龄效应真实性（置换检验的姊妹检验）
**现有置换检验（打乱 ortholog 配对）验「跨物种同向性是否随机」；年龄标签 shuffle（打乱样本年龄 → 重算相关）验「年龄效应本身是否真实」**——两者是不同问题，缺一不可。前者被打乱会破坏跨物种配对，后者被打乱会破坏年龄↔可及性关联。

**sparse 矩阵向量化 Pearson 相关配方**（R + Matrix，样本×feature `dgCMatrix`，M 为 n 样本 × T feature）：
```r
a <- age - mean(age)                    # 中心化年龄（n 维）
sx  <- colSums(M); sx2 <- colSums(M*M)   # 每 feature 的 sum(x)、sum(x²)
denom <- sqrt((sx2 - sx^2/n) * sum(a^2)) # pearson 分母，shuffle 年龄后不变 → 复用
r_true <- as.vector(a %*% M) / denom     # 一次 sparse 乘向量得全部 feature 的 r
# shuffle 检验：每次只重算分子 as.vector(sample(a) %*% M) / denom（denom 复用，快）
```
统计量用「|r| > 阈值的 feature 数」对比真实 vs null（N 次 shuffle 年龄，经验 p = P(null ≥ obs)）。

**实测结果（重要警示，见 Pitfall 14）**：人侧 peak 级真实 24.3× > null（p=0.005，年龄效应真实）；但猴侧**全 608 万 tile 级**真实仅 0.23× < null（p=0.815，弱于随机）。⚠️ **这不是"猴侧年龄效应必然无"，而是粒度错配**——S 评分用的是「启动子近端 TSS±2kb + Stouffer 聚合」的基因级效应，此次 shuffle 却在「全 tile 级」（含海量基因间/荒漠 tile，信号被稀释）做的。结论必须先回到 S 评分实际粒度复验，再下判断。脚本 `scripts/v8_age_shuffle.R`（或参考 `references/method-validity-age-shuffle.md`）。

### v9 A 类元件坐标落点 —— CRE 级变可主张坐标范围
复用 v6 锚定逻辑，改 anchor 保留「窗口内 |Z| 最强 tile 的坐标」，对 402 个 A 级基因各输出一对「人 hg38 + 猴 T2T-MFA8v1.1」的 chr:start-end。脚本 `scripts/v9_A_class_CRE_coords.py`，产出 `v9_A_class_CRE_coords.csv`。CRE 级从概念变成可主张的具体坐标，扩大实质保护范围。

## Key Tools

| Layer | Tools |
|-------|-------|
| L0.5 | UCSC LiftOver, BEDTools, biomaRt, pybedtools |
| L1 | phastCons (UCSC query), GERP, JASPAR FIMO, Biostrings |
| L2 | deepTools, GenomicRanges (R), rtracklayer, pyBigWig |
| L3 | HiC-Pro, FAN-C, ABC model (python) |
| L4 | DESeq2, coloc (R), statsmodels |
| L5 | Custom Python/R scoring script |

## Pitfalls

1. **Genome version mismatch**: Always verify both species use the SAME UCSC genome version convention (e.g., both hg38 or both GRCh38)
2. **LiftOver chain direction**: hg38→rheMac10 vs rheMac10→hg38 — use the correct chain for each direction
3. **Ortholog mapping gaps**: Not all human genes have a 1:1 monkey ortholog — handle many-to-many separately
4. **Cell-type mixing in bulk data**: If using bulk ATAC-seq, CRE signals are averaged across cell types — use snATAC-seq when possible
5. **phastCons is pre-computed for specific alignments**: Verify the track includes both human and rhesus in the multiple alignment
6. **Don't mix peak callers**: Use the same peak caller (MACS2) and same parameters for both species to avoid caller bias
7. **Hi-C resolution limits**: Most public Hi-C is 5-10kb resolution — fine for TADs but may miss individual E-P loops
8. **复合评分缩放因子陷阱（CRECS 类 C=0 根因，2026-09-03 实证）**: `l3_score = min(1.0, Jaccard×5)` + 固定阈值 0.5 时，up 方向 Jaccard 0.213×5=1.065 → min 后恒 =1.0（永不 <0.5 → 永不落 B），down 方向 0.034×5=0.17（恒 <0.5 → B 全挤在 down 侧），C 类恒=0 —— **分类结果完全由缩放因子 × 固定阈值决定，而非数据驱动**，必须警惕"分布假象"（99.4% 落同一类是缩放数学的必然，不是生物学信号）。诊断法：检查复合分公式中任何常数乘子与方向性 Jaccard/比例的交互（min clamp 是否把一侧压满、另一侧归零）。修复法：用参考集校准（阳性=已知增强子 H3K27ac peaks，阴性=随机基因组 tile）对参考集重算 L3 分布 → ROC/分位数定数据驱动阈值与缩放因子，替换人为常数。
9. **阈值校准必须用参考集而非主观常数**: 校准 L3 阈值/缩放因子时，阳性增强子参考集首选 GSE67978 H3K27ac peaks（人/猴/猩猩 8 脑区，PMID 26807951），阴性=随机基因组 tile（保留 GC 分布匹配）；对两组复用 l3_topN_motif.R 的 matchMotifs→fc 框架算分布 → 交叉点/Youden J 定阈值。详见 `references/external-validation-calibration.md`
10. **锚点平移表不能用于 tile 级精确匹配（L2 猴侧命中恒 0 根因，2026-09-03 实证）**: 基因锚点平移（`monkey_peaks_hg38_map.csv`，5kb 基因窗）的 `hg38_start` 与 500bp DA tile 的 start **坐标网格不对齐**——即使修好 chr 前缀，set 精确匹配数学上必为 0（锚点 272,307 加载成功但 `da_m` 仍全 0）。**判别法**：命中表 key 是"窗级"坐标（基因窗/peak 窗）、查询是"网格级"坐标（500bp tile）→ 精确匹配必失败。**修复**：改用真实实验峰（GSE67978 H3K27ac，猴 rheMac3→hg38 liftover）+ 区间重叠（bisect ± 重叠判定）作活性证据，别用锚点平移做 tile 级命中。
11. **跨物种表 join 前统一 chr 前缀（2026-09-03 实证）**: `hg38_chr` 常为 `'1'`（无前缀）而 DA/peak 表用 `'chr1'`；join/匹配前统一 `'chr'+x if not x.startswith('chr')`，否则静默全 miss。危险点：v2.2 的 m_hit 全 0 被 `l2≥0.5` 恒真容错掩盖——**静默 miss 可能被其他恒真条件掩盖，必须检查原始计数（m_hit 分布）而非只看复合分/分类**。
12. **CRE 级下钻前先确认猴侧 genome assembly 再选 chain（2026-09-04 实证）**: 基因级 S 评分跑通后往下钻到 CRE/tile 级时，人猴 tile 必须按坐标配对，但猴侧 ageDA 数据用 `NC_088375.1` 染色体命名 = **食蟹猴 Macaca fascicularis T2T-MFA8v1.1**，不是恒河猴 rheMac3/rheMac10，更不是 chr1 前缀的 hg38。手里现成的 `rheMac3ToHg38.over.chain.gz`（恒河猴 rheMac3→hg38）与猴侧数据非同物种/版本，**不能混用**。下钻正路三条（按优先级）：① 找食蟹猴 T2T-MFA8v1.1→hg38 的 liftover chain（UCSC/USCS 可能根本没有）；② 复用 p4 旧 tile 产物（基因锚点平移，有坐标网格不对齐缺陷，见 Pitfall 10，精度打折）；③ 用 GSE67978 H3K27ac 峰（人 hg38 + 恒河猴 rheMac3 已对齐，但是尾状核非海马，只能作"方法示范性"CRE 级实施例）。判别法：先 `head` 猴侧 ageDA csv 看 chr 列是 `NC_088xxx` 还是 `chr1`，再决定走哪条路；默认套 rheMac10/hg38 对齐会静默错配。**④ ortholog 基因锚定下钻（v6，已实测跑通，见上方「CRE 级下钻」小节）**——当 ① 无 chain 时这是正路：复用 v4b 锚定+Stouffer 聚合，只把窗口收窄到 TSS±2kb，不需坐标 liftover。🔴 **2026-09-15 复验（L2 八角色辩论 + 数据实测）**：本地仍只有 `rheMac3ToHg38.over.chain.gz`（2010 旧装配），T2T-MFA8v1.1 **确认无官方 →hg38 chain** ⇒ 路线 ① 彻底出局、④ 为唯一主线，**套旧 chain = 静默错映射（不报错）**；且交接文档写「liftOver」而既有产物 `crecs_tile_hg38_monkey_map.csv` 列含 `anchor_dist`（= 锚定产物）——**文档叙述不可信，实现路线只认生成脚本输入常量 + 产物列语义**。**两矩阵事实卡（人 40×6,062,095 / 猴 20×6,085,841，两侧均 0-based 500bp，人侧是 `chr1:0-499` 不是交接文档写的 `chr1:1-500`）/ 🔴 猴侧矩阵 `colnames` 全空、tile 身份须按位置取 `monkey_tile_coords.csv`（nrow=ncol） / 读入配方 / 三项缺陷口径（歧义 1.02%·覆盖 43.8%·长度混杂翻转 −7.55→+5.08）→ `references/tile-matrix-inventory-and-alignment-route.md`**。
13. **启动子近端 TSS 定位需 strand，人侧注释常缺（2026-09-04 实证）**: 猴侧 NCBI feature table 有 strand 列（p[9]），TSS = strand=='+'?start:end 才能精确定位；人侧 `human_ortholog_hg38_full.csv` 只有 chr/start/end **无 strand**，TSS 只能用 start 近似（负链基因 TSS 在 end，错位一个基因长度）。判别法：下钻前先查两侧基因注释表有没有 strand 列；没有就用 start 近似，并在方法描述里明确声明近似口径，别假装精确。
14. **协变量置换检验必须与评分粒度对齐（2026-09-04 实证）**: 用「年龄标签 shuffle」等协变量置换检验验证效应真实性时，shuffle 必须在评分方法**实际使用的粒度**上做。若评分是「启动子近端 TSS±2kb + Stouffer 聚合」的基因级效应，却在「全 tile 级」（6M tile，含大量基因间/荒漠 tile）做 shuffle，真实信号会被稀释到弱于 null，导致**误判真效应为噪声**（猴侧实测：全 tile 级 0.23× vs null，但启动子近端粒度未验）。判别法：先问"评分器在哪个粒度算 Z"（tile / peak / 聚合后基因），再在**同一粒度**做 shuffle；粒度不一致的「真实 < null」不能直接下"效应不真实"结论，只能说"该粒度下被稀释，需回到原粒度复验"。
15. **口径必须一轮锁死并同步所有交付文件，否则数字漂移（2026-09-05 实证，用户强烈不满）**: 阈值口径（如 A 级定义）在多个候选间摇摆时，会出现 1904/3487/37/537/336 多个不同数字，且 claims/disclosure/abstract 三份文件停留在旧口径没跟着结论走——用户质问"到底是多少？每次回答都是不一样的？"。判别法/修复：① 定口径时先想清"猴侧(小样本参考侧)只做方向门控还是强度门槛"——参考侧独立供体不足时，其效应量方向整体是噪声（shuffle p 高），"方向可信"必须卡 p<0.05 而非"只要同向"；② 锁死唯一数字后，用同一数字**重写全部交付文件**（claims/disclosure/abstract/附表 CSV）到一个新目录；③ 数字变化必须显式给出口径对照表（每个旧数字对应什么口径、为何废弃），不留"数字在对话里漂移"的空间。
16. **显著性(p)筛不出"同向保守"（2026-09-05 实证，推翻旧框架的根本）**: 双侧 Bonferroni 显著基因里，反向可能比同向还多（实测 1207 显著中反向 800 > 同向 407），因为显著性只回答"效应多大"，不回答"两物种是否同向"。当人猴基因级方向整体略负相关（r≈−0.06）时，"同向"本身是稀缺信号，不能靠"两侧都显著"当同向门控。修复：同向必须独立成门控条件（w(Z₂)=+1 要求猴侧方向可信 + 同向），与强度阈值 τ_A 正交，不能把"显著"当"同向"。
17. **不得静默更换输入口径，也不得把未证实的溯源结论写进生成的报告（2026-09-11 实证，用户强烈不满）**: 用户指定了输入文件（如"M2 都在这里面"→ `M2/monkey_ageDA_all.csv`）时，若发现该文件复现不出正本数字，**必须报告 + 给证据 + 等裁决**，绝不能悄悄换成另一个文件让数字对上——用户原话："为什么是 continuous 版 567 万 tile？我不是说了吗？用我给你的文件"。同一个错在**报告层面**更隐蔽：生成的 `REPRO_SUMMARY.md` 里写死了一句"专利正本数字来自 continuous 版输入"——当时那只是**推测却被写成结论句**，等于把未验证结论固化进产物。修复三条：① 换口径前先报告、说明理由、等用户裁决；② 报告里的输入/口径字段一律从变量取（实际用了哪个文件就写哪个路径），不写死叙述；③ 叙述句/结论句只写本次**实际观测到**的事实，推测一律标注"待验证"。
18. **复现对账先比逐实体值，不要只比总量（2026-09-11 实证）**: 总量（N/A/B/C/D/ρ）不吻合时，本能反应是调阈值/换参数——错。正解是挑一个代表性实体逐字段比对：本次 AGBL2 人侧 `Z_human / n_tiles_h / p_human` 与正本**逐位相同**，猴侧 `n_tiles_m` 同为 151 但 `Z_monkey` 一个 −3.3395 一个 −1.5678 → 立刻定性为"同一坐标网格、不同 r/p 值体系 ⇒ 另一张输入表"，省掉全部调参弯路。判别法：**实体个数相同而值不同 ⇒ 换输入表；实体值逐位相同只有总数差 ⇒ 桥接/取舍残差**（本次 16031 vs 16012 = 0.12%，不影响口径判定）。完整判决表见上方「输入口径对账与复现溯源」。
19. **已授权即执行，禁止反复审计后才跑（2026-09-11 实证，用户强烈不满）**: 用户已明确授权某个动作后（如"现在用 all 版跑一遍 M3→M7"），不要再花多轮重读脚本、翻旧日志、逐项核对列名——用户原话：**"傻子，你到底跑不跑？跑了就执行任务啊，非要搞半天，一点代码都没跑"**。正确节奏：**启动 → 一次日志确认输入对不对 → 报进度 → 出数再对账**。审计动作压缩进启动前的**单轮**（列名/路径/键名一次性查完），不要跨轮铺开；诊断类追问（"到底哪个文件"）用**一次对照跑**回答，胜过三轮推理。同理：磁盘上的"✅ 全部完成"必须先用对账数字验真——本次 `run2.log` 就是旧进程留下的**假完成**（B=7091 等错值），不可当已完成汇报。
20. **长任务启动与监控走 agent terminal，不用沙箱（2026-09-11 实测）**: 项目外目录（如 `E:/专利/`）不在 `MEMOMICS_ALLOWED_WRITE_ROOTS`，execute_code 里 `open(...)` / `subprocess.Popen` 会被沙箱拒绝（`沙箱 degraded 模式：写入白名单外路径被拒绝`），`nohup ... &` 在 MSYS 下还会静默不建日志文件。**一律 `terminal(background=True, notify_on_complete=True)` 启动 + `process(action='wait', timeout=180)` 阻塞等待**（上限 180s，长任务 wait 2–3 次），不要在循环里反复 tail/poll（会被判循环失控）。日志名冲突报 `Device or resource busy` 时换个新日志名即可。平台坑详见 `platform-execution-pitfalls`。
21. **被质疑"你是不是改了我的数据"时，不辩解、做逐位复算，并把命令交给用户（2026-09-11 实证）**: 用户看到两版输入跑出不同结果、且认为"我这版是代码跑出来的、你那版是修复版"，自然质疑数据真实性。辩解零说服力，正确动作序列 = ① 体量证据（448 MB / 567 万行，物理上无法手改）→ ② 生成脚本原文（零硬编码、纯公式、输入路径指向用户集群导出目录）→ ③ **用用户的原始输入独立重算 + 逐位比对**（本次 `max|Δr| = 1.11e-16`，double 机器精度 eps≈2.2e-16 量级 ⇒ 等价完全一致；少量"不一致"只是 `round(x,6)` 边界）→ ④ **把复算命令交给用户自己跑**（"我跑给你看"仍需他信任你的输出，"给你命令自己跑"才终结质疑）。同时要讲清**"修复版"标签可能被贴反**：本次被**就地改写**的其实是用户那版（`fix_ageDA_coords.R` 以 `fwrite(d, f)` 直接改写 6 个 CSV），我方那版是全新计算的新文件——判据是看写文件操作的目标是输入本身还是新文件名。**严禁**为了"让数字对上"而静默换输入（见 Pitfall 17）。完整配方 + 差异三层归因（坐标层/管线层/实现层）+ 交付时把口径锁死到 md5 文件级 → `references/data-integrity-self-proof.md`。
22. **描述两版差异前必须先分层实测，不得凭"1-based/0-based"推断（2026-09-11 实证）**: 曾把两版猴表的差异轻描淡写成"坐标网格差 1bp"写进 SKILL.md 与交付报告——两处实测都证伪。**坐标体系差异只平移坐标标签、不改变统计值**；r 值大面积不同（corr≈0.89、tile 数差 37 万）必然是**管线层**（聚合方式 / 数值变换 `log2(CPM+1)` vs 原始比例 / 过滤阈值）。差异归因先分三层做实测，再写结论：坐标层（值不变）/ 管线层（值大面积变）/ 实现层（实体数差 <1%，如 anchor() 实现差异）。**轻描淡写实质方法学差异 = 描述失实**，用户会立刻抓住并要求更正。
23. **能推翻 claim 的前置检验必须定为 🔴 阻断级，不能降为 🟡 建议（2026-09-12 实证，用户追问"为什么之前可以、现在要改"的根因）**: 本项目 09-10 的评审**已经精确写明了缺陷**（原话："猴侧方向门控 p<0.05 本身的质量没有任何校准证据；改法：打乱猴侧年龄标签重算方向一致率，给出 +1 方向的错误率"——**这正是两天后跑出 z=−6.27 的检验**），但被排进 **🟡 强烈建议**行而非 **🔴 必改**行，于是没能拦住流程。用户据此问「之前就可以，现在就要改，为什么？」。**根因不是数据变了、也不是翻案，而是门禁等级判错：一个 claim 的前提（precondition）被当成了加分项。** 判据：**若某检验失败会使 claim 的技术效果断言直接不成立 → 它是前提，必须阻断；若失败只是让效果变弱 → 才是建议。** 汇报时把"变了什么"讲清是 **🟡→🔴 的分级跳变**，而不是"数据变了"——否则用户会以为你在翻案。配套两条：① **顺序铁律**：前提检验必须先于一切数字优化（本项目 5 轮返工全在改数字、0 轮检验前提）；② **口径切换救不了既有缺陷**：12.3× / 12.5× 的循环论证（分母含"同向"条件）在 **continuous 版（536）与 all 版（581）里同时存在**，且 continuous 的同向率 **35.7% 比 all 的 40.1% 更差** ⇒ **留在旧口径不动，claim 一样不成立**。凡是"换个口径是不是就好了"的追问，先用这条对照表回答。

24. **向量化区间锚定的三个静默失败：只表现为"数量不对"，永不抛异常（2026-09-12 实证，本次连踩三坑）**: 重写任何「tile/peak → 基因」的 numpy/pandas 向量化锚定前，先自查这三条——① **`np.isin(gg, python_set)` 恒 False**（`np.asarray(set)` 退化成 0 维 object 数组 ⇒ 逐元素拿元素和整个 set 比 ⇒ 全 False），实测症状 `tiles anchored: 0 genes: 0`，修复 = 先 `np.asarray(sorted(keep_gids), dtype=object)`；② **并行数组"部分过滤"**：`sel, idx = sel[ok], idx[ok]` 漏掉同长度的派生数组 `m`（`m = mid[sel]`）⇒ `IndexError: index 979923 out of bounds for axis 0 with size 259785`，更危险的是 `sel` 语义是"原始 chunk 行索引"而非位置索引，长度错配**不一定立刻越界、有机会静默取到错误行**，修复 = **一次过滤全部同长度派生数组**（`sel, idx, m = sel[ok], idx[ok], m[ok]`）；③ **`searchsorted` 输入未排序**：`groupby('chrom')` **不保证**组内按 start 有序，直接用 `gsub['start'].values` ⇒ 二分查找结果无意义，实测 5,555,247 tile 只锚定 **4,147 / 78 基因**（正确 **2,439,577 / 16,104**）——**塌约 1000 倍**，修复 = `df.sort_values(['chrom','start'], kind='mergesort')`。对照：正本 `repro_m3_from_M2.py` 的 `load_gene_coords()` 里就有 `chroms[c].sort(key=lambda x: x[0])` 这一行，**它正是防坑③的**，重写实现时最容易漏掉。**唯一防线 = 跑完立刻打印 `tiles anchored / genes` 并与预期量级对比**——本次三个 bug 全部靠这一个打印暴露，没有它错误结果会一路流进下游统计而不被发现。另附两条同类原则：**任何"派生数组 + 布尔掩码"的过滤，掩码必须广播到所有同长度数组**；**上线前给自己留一个量级断言**（如 `assert 1e6 < n_anchored < 1e7`）。

25. **🔴 门控塌缩陷阱：改动统计单元划分后，绝对阈值不可复用（2026-09-12 实证，本次差点误报"方法修复成功"）**: 修复 ① 把统计单元从基因级重划为 (gene,bin) 级（16,010 → 221,069 单元）后，沿用绝对阈值 τ_A=12，**门控后 n 从 890 塌到 82（−91%）**（② 更只剩 55）。此时直接报"同向率 40.1% → 63.4%，修复有效"是错的——**tau 是规模门槛、不是显著性门槛（见 Pitfall 23b/探针 4），单元重划后同一绝对阈值切的是完全不同的分位**，等于把"阈值收紧"的效应记在"方法修复"账上。**三条合法对照，报表必须并排给**：① **全量口径**（不门控，比 obs/base/Δpp/z——本次 −3.80pp → −0.84pp，仍 z=−8.04）；② **topK 配对数量对齐**（各条件取 |Z| 前 K，统一 K 再比——本次 K=890 时 0.401→0.530，修复侧 z=+1.30 不显著）；③ **分位数匹配阈值**（跨层同分位）。**门控后 n<100 时禁止用 z 主张"方向翻转"**——本次 ① ② 的 z=+1.67/+1.89 对应 p≈0.06–0.10，正确表述是"符号反转但未达显著，需扩大参考侧样本量复验"。推广判据：**任何改动了统计单元划分、聚合层数或分布形状的"修复"，都必须放弃绝对阈值改用上述对照之一；只报门控后指标 = 伪增益。**

23b. **同向率/concordance 的基准不是 50%，必须现算边际保持的独立配对期望（2026-09-12 实证）**: `base = p₊ᵐ·p₊ʰ + (1−p₊ᵐ)(1−p₊ʰ)`。本次 890 子集人侧 58.3% 正 / 猴侧 54.2% 正 ⇒ **基准 50.7%**，观测 40.1% 是**显著低于随机（z=−6.44）**而非"没超过随机"——两者结论强度完全不同。报表**永远同时给 `obs / base / delta_pp / z` 四列，缺一不可**。另：**跨聚合层（tile 级 / bin 级 / 基因级）的 τ 绝对值不可直接比**——bin 级 Z 因 tile 数少而整体偏小，沿用 τ_A=12 会几乎筛空，跨层比较必须改用**分位数匹配阈值**。

26. **附图交付前必须逐张体检：遮挡 / 裁切 / 标签缺失 / OCR 误读 四件事必须分开判（2026-09-12 实证，触发句「交底书的图是不是正确的？每张都检查一下，有没有遮挡」）**: **禁止只查空白图**（那只是最低一档）。三级检测 + 一次反证，脚本 `scripts/check_figure_occlusion.py` + `scripts/check_docx_figure_pairing.py`，完整配方 → `references/deliverable-consistency-and-figure-qa.md`：① **边缘裁切**（最外 2px 非白像素计数，期望全 0；本次 5 张全 0）；② **文字框遮挡**（rapidocr bbox 两两相交 > 较小框 15%）——⚠️ **同一 y 刻度标签的两行文字天然交叠 17–20%、但 IoU<0.1，是假阳性，勿报**；③ **缺失标签**（"按代码应画"的标签集 vs OCR 实得集求差）→ **放大 3× 定向重 OCR**，仍只读到别的文字（如图例文字）才是真遮挡；④ 🔴 **OCR 误读反证（最容易假维修的一步）**：报告图内文字错误前，**必须用同一字体同一字号把正确字符串重新渲染再 OCR** —— 本次源脚本第 136 行原文是 `'⑤置换定阈+分级'`（编号与"阈"字都对），内嵌图 OCR 三次（含 5× 放大）都读成 `'③置换定阀+分级'`，而**干净重渲染同样被读成 `'③置换定阔+分级'`** ⇒ 纯 OCR 字形误认，**图本身无误，不得报为缺陷**。真实缺陷的根因定位范例：图4 面板A 末行标签被压住 = 「逐行 `ax.text` 画标签（其实都画了）」+「`tab.iloc[::-1]` 把该行翻到最底」+「`legend(loc='lower right')` 落在底行末端」三者叠加 ⇒ **凡出图脚本里有 `legend(loc='lower ...')` / `loc='best'`，都要回头确认哪些数据行落在该角落**，修复用 `loc='upper right'` 或 `bbox_to_anchor=(1,-0.12)` 移出绘图区。**Windows 坑**：`vision_describe` 需要 Windows 绝对路径，MSYS 的 `/tmp/...` 会报"图片不存在"——先 `cp` 到项目目录再读。
   **配套：交付目录 ↔ 交底书 docx 对应性核查要下五刀**（用户问"是不是完全对应"时）——① 口径数字/命名跨文件一致；② **复现脚本清单 ↔ 实际文件**（最常漂移：文档写 `07_age_shuffle.R` 而实际是 `07_age_shuffle_permutation.R`；生成器写 v10 而当前是 v11；声称"出图脚本产出附图 1–5"而读脚本只有 **3 处 `savefig`**）；③ 图号 ↔ PNG 数；④ **表 vs 图 行数成员一致**（表1 列 7 个方法，而图4 与 `results/*.csv` 都是 9 个）；⑤ **图内标题 ↔ 文档用词一致**（图内 `suptitle` 写"四方法横评"，正文/表/图注一律"三基线横评"——**图内文字也算交付文本**）。报告用「✅一致项表 → ❌不一致清单（文档写的/实际是/照表跑会怎样）→ 逐图结论 → 真实缺陷+根因代码行 → 修复选项」骨架。
   **🔴 09-12e 加两刀（存在性通过 ≠ 数字来源正确）**：⑥ **引用脚本 ≠ 产出该数字的脚本** —— 表3 把「24.3× / p=0.005」挂在置换脚本名下，而该脚本（实际名 `07_age_shuffle_permutation.R`）的真实产出 `l2_permutation_1000.rds` 是 `n_obs=16` / `null_mean=73.96` / `perm_p=0.017`（方向相反、数字完全不同；其 200 次版 `l2_permutation_test.rds` 又是第三组 `obs=16`/`mean=7.32`/`p=0.01`）⇒ **必须读被引用脚本的真实产出物逐字段比对**，只查文件名 = 假阴性；连带核对 `run_all.sh` 的**调用清单**（实测完全没调任何 `07_*` 脚本，M8 置换环节在复现链里整体缺失）。⑦ **头条数字溯源 + 分析层口径核对**（数字对得上 ≠ 口径对得上）—— 24.3× 一路查到 `P3_L1_data/v8_age_shuffle_stats.rds` 的 `human` 段，逐项吻合；同段 `n_peaks = 525,137` == `human_Hf_peaks.csv` 行数 − 1 ⇒ **peak 级**，而文档方法学段落写的是 500bp tile（555 万）→ 基因级（16,029）⇒ **层不一致**；同文件的 `macaque` 段是 **0.231× 亏损 / p=0.815**（文档只引用有利的一半，从未披露猴侧）；且 `p = 0.005` 恰等于 `1/(200+1)` ⇒ **经验 p 值地板效应**（零次置换达标，p 被锁在下限、不是算出来的分位点），而 `obs=6285 / null_mean=258.4 / null_sd=1075.14` ⇒ z≈5.6 与 p=0.005 互相矛盾（空分布重尾）。**三条通用判据：① 源产物的 `n_peaks`/`n_tiles`/`n_samples` 是分辨"这张图讲哪一层"的最快指纹，拿它对文档方法学段落；② `p == 1/(N+1)` ⇒ p 是地板不是分位点，不得当显著性证据引用；③ 同源 .rds 往往含多物种/多条件段，引用前必须整段读。**
   **🔴 遮挡检测器假阴性盲区（同一会话实测踩中）**：文字框两两相交检测对**被完全盖住**的文字**恒返回 0 对**——OCR 检测不到它，就没有框可与之求交 ⇒ **「0 对重叠」≠「无遮挡」**。本次正是先报"无文本框重叠 OK"，靠"应有标签集合 − OCR 实得集合"的**清单求差**（9 个 y 轴标签 vs 8 个数值标签）才抓到图4 末行缺失。**遮挡定案必须靠清单差分，相交检测只能证明"无部分交叠"**；推广：凡「先找到目标、再检查其邻域」型检测器，被全遮目标对它天然不可见，一律配清单差分。
   **孤儿图排查**：逐张 PNG 反查写出它的脚本；**PNG 存在 + 反查无命中生成脚本 + mtime 早于最近一次口径切换 = 孤儿图**（实测图2/图3 在交付目录内**没有任何生成脚本**，grep 只命中 docx 生成器对文件名的引用；图2 mtime 早于口径切换 ⇒ 拷贝进来的旧文件，`bash run_all.sh` 跑完只有图1/图4/图5）。

27. **锚定单元审计三问：重复计数 / 归属歧义 / 覆盖率分母（2026-09-13 实证）**: 任何「tile/peak → 基因」锚定后、要把 **n（锚定单元数）** 报进 claim / 说明书之前，必须能回答三问，否则该 n 不可用于技术效果断言：① **重复计数**——`anchor()` 命中即 `break`（L206）⇒ 每单元至多归属 1 基因 ⇒ **`Σn ≤ 单元总数` 恒成立**；核对三处（正交表多对一 / 输出表 `symbol` 与 `(Z_m,Z_h)` 去重 / Σn vs 总 tile 数）。实测：猴 gene 26,501 全唯一；人 gene 唯一重复项 = **空字符串 10,341 行 = 未匹配猴基因（静默丢弃），不是多对一**（26,501−10,341 = 16,160 ≈ 非空唯一人 gene 数 ⇒ 非空部分严格 1:1）；`symbol` 重复 0、`(Z_m,Z_h)` 重复 0；Σ`n_tiles_h` 2,432,901 ≤ 5,555,247 ✓。② **归属歧义**——chr1 443,121 tile 中 **1.02%（4,538）** 其「中点 ±2kb」窗口落在 **≥2 个正交基因**内（最大候选 3），贪心按「start 最大者」选 ⇒ **归属取决于基因表排序而非生物学**；统一网格权项须打 `multi_map` 标记 + tie-break 敏感性分析。③ **覆盖率分母**——Σ`n_tiles_h` / 全基因组 tiles = **43.8%**（锚定仅在 16,158 个正交基因子集内，chr1 未锚定率 52.1%）⇒ **说明书写 n 必须写明分母口径**，否则被质疑选择偏置（未锚定区偏向低基因密度/基因间区，非随机）。
    ⚠️ **先读列名再算**：`v5_substitutability_all.csv` 实际列 = `symbol / Z_monkey / Z_human / p_monkey / p_human / n_tiles_m / n_tiles_h / same_direction / S / class`，**不是** `Zm/Zh`/`n`。本轮按记忆假设列名 → `duplicated(subset=['Zm','Zh'])` 抛 `ValueError: not enough values to unpack (expected 2, got 0)` 中断一次。**任何 DataFrame 操作前先 `print(list(df.columns))`**（同 Pitfall 18 的「先读真实字段」原则）。
    💡 **顺手即可完成审查要求的阈值依赖核查**：同一脚本算完 —— `n_tiles_h` 全量倍数 **4.51×**（524.0 vs 116.2，复现 4.49）、**剔除 top1%(>1384) 后仍 3.73×（>2）** ⇒ 判定「非少数超大元件驱动」，省掉独立实验一轮。附量级自检：tile 宽度恒 **499bp** ⇒ n ∝ 基因跨度，n=4,952 ⇒ ≈2.47Mb（DMD 量级）。完整配方 + 可跑代码骨架 + 本次踩坑表 → `references/anchoring-unit-audit.md`。

### 🔴 方向门控有效性前置检验（2026-09-12 实测，本方法最严重的一次证伪）

**背景**：独权核心特征「人侧 Z₁ 强度 + 猴侧 w(Z₂) 方向门控」的全部效力，取决于一个未被验证的前提 —— **猴侧方向可信**。专利 A22.3 创造性的唯一量化论据是「元件级富集 12.3 倍」。三项独立检验**全部否定该前提**，交付前必须跑。

**检验一：分母口径是否构成循环论证（零成本，先跑）**
```python
# 专利原文：在"人侧强效应 |Z₁|≥12 且同向"的 582 个候选元件里，
#           若猴侧方向纯为噪声则 p<0.05 期望命中 ≈ 582×5% ≈ 29.1，实际 357 → 富集 12.3 倍
strong = d[d.Z_human.abs() >= 12]                       # 1404(管线口径) / 1409(锚定表口径)
pool   = strong[strong.Z_monkey*strong.Z_human > 0]     # 581(管线) / 582(锚定表) ← 分母已含"同向"条件
conc   = strong[(strong.p_monkey<0.05) & (strong.Z_monkey*strong.Z_human>0)]  # 357(两口径一致)
# ⚠️ 两组数只差 ~5 个实体、结论相同;引用时必须注明取自哪份文件——见本小节「数字来源依赖」
```
**判据：分母定义里若已出现分子所依赖的条件（本例"同向"在 582 与 357 中同时出现），富集倍数被共同条件抬高，不构成独立证据。** 且该"零假设"假设猴侧噪声下 p<0.05 = 5%，而实测强元件池里猴侧显著率 **63.4%**（890/1404）—— 零假设与数据不符；分母 29.1 不含方向、分子 357 含方向，还差一个 50%。

**检验二：方向配对是否携带信息（保持边际、只破配对）**
```python
# 符号置换零假设：打乱 Z_monkey 的符号，保 |Z_m| 与 p_m 不变、破方向配对
obs = 357   # 人侧强 & 猴侧 p<0.05 & 同向
# N=20000 → null 449.7 ± 14.8 → z = −6.27, p = 1.0
# coverage 分层内置换 → null 443.1 ± 14.3 → z = −6.02（结论不变）
```
**对称判别（最有力的一击）**：同向 357 vs null 449.7 = **0.79×（亏损）**；反向 533 vs 440.3 = **1.21×（富集）**。同向率 357/890 = **40.1%**，二项 p = 3.6e-9 ⇒ **真实数据比随机打乱方向还要更不同向**。

**检验三：猴侧年龄效应是否真实存在（年龄标签 shuffle，破坏处理变量）**
```r
# 常量与年龄顺序无关，可复用（关键加速：1000 次置换仅需一次 colSums）
denom <- sqrt(pmax(sx2 - sx^2/n, 0) * sum((age-mean(age))^2))
calc <- function(av){ a <- av-mean(av); r <- as.vector(a %*% M)/denom; ... }
obs <- calc(age); perm <- replicate(1000, calc(sample(age)))
```
实测（20 样本 × 6,085,841 tile，r_crit=0.4438）：mean_r 观测 −0.028 vs null 0.0015±0.1409（z=−0.21）、负向占比 57.3% vs 49.4%±24.9（z=+0.32）、显著 tile 数 86,312 vs 284,183±375,408（z=−0.53）—— **三项全部不显著 ⇒ 猴侧 tile 级年龄效应无法与随机区分**。

**检验四：混杂定位（为什么"方向可信"是假的）**
`spearman(n_tiles_m, |Z_m|) = +0.290`；按 n_tiles_m 五分位分层，猴侧显著率 **33.9% → 41.5% → 44.2% → 52.5% → 67.1%** 单调上升。⇒ 猴侧 p<0.05（文档里叫"方向可信"）**是覆盖度/检验力，不是年龄信号**。

**检验五：留一法稳健性（元数据核查的正确终点）**
元数据本身可能完全干净（本例 20/20 年龄标注一致、QC 指标与年龄相关全部 p>0.1），**但方向仍不稳健**：全样本 mean r = −0.028；高质量样本子集（覆盖率>85%，n=11）= **+0.194**，低质量子集（n=9）= +0.003（两子集皆正、合并为负 = Simpson 悖论）；LOO 删 M3/V4/V5/V6 **任一**即翻正；**仅 V 组内部（28–31 岁，跨度仅 3 年，n=6）mean r = −0.468，比 26 年跨度全样本强 16 倍** ⇒ 所谓"年龄效应"来自样本身份而非年龄。

**根因**：不是错标、不是批次，是 **n=20 + 巨大个体技术异质性**（同年龄段内 tile 覆盖率落差达 30 个百分点：Y3 91.1% vs Y5 73.7%；V1–V3 90–91% vs V4–V6 60.6–70.9%）。**20 个样本不足以估计方向。**

**检验六：Z 标定核验（经验零假设 vs N(0,1)）—— 2026-09-12 实测，最容易漏的一刀**
```python
def emp_null(z):                      # Efron 25–75 百分位稳健估计
    q25, q50, q75 = np.percentile(z, [25, 50, 75])
    return q50, (q75-q25)/(norm.ppf(.75)-norm.ppf(.25))
```
实测 all 口径 16,010 元件：人侧 `mu=+1.063, sigma=4.856`（**不是 1**）、猴侧 `mu=+0.072, sigma=2.765`、中心区 `rho0=-0.057`、`pi0=0.917`；`|Z_human|` 中位 **3.36**（N(0,1) 下应 ≈0.674）。
⇒ **`|Z₁|≥12` 在经验零假设下只相当于 (12−1.06)/4.86 ≈ 2.25σ（双侧 p≈0.024），不是"12σ 铁证"。** 与探针 4 独立互证：它是**规模门槛**，文档里"高置信"字样不得当统计显著性主张用。
⇒ **凡 `Z=Φ⁻¹(1−p/2)` 这类正态分位换算量，阈值前必须先估经验零假设**；`sigma>1` 的倍数 ≈ p 被夸大的倍数（本例 **4.86×**）。可疑来源按序排查：① p 用的 n 是**供体数**还是 tile/细胞数；② Stouffer `ΣZ/√n` 的**独立性前提**在多次聚合后是否还成立；③ 是否做过全局居中（`median Z=+1.06` 应≈0）。**未查清前不得把 `|Z|≥12` 写成高置信。**

**检验七（新颖性用，非阻断）：二维经验贝叶斯 + local FDR 探针 —— 触发句"你确定你用了这个方法了吗？"**
用户需求里点名的方法，**必须在交付件里真的存在**——先 grep **三层**（正文 md / docx 表格单元格 / 内嵌图像素），再做**双路判决**（需求清单 ↔ claims 动词链逐条比对，禁止凭印象答"用了/没用"）。随后把该方法真跑一遍，看它救什么。实测（all 口径 16,010 元件，lfdr≤0.05，**5.8 s**，脚本 `scripts/ebayes_lfdr_probe.py`）：

| 状态 | 元件数 | 占比 |
|---|---|---|
| A 同向可信 | **106** | 0.66% |
| B 反向可信 | **168** | 1.05% |
| C 单侧可判定 | 2,528 | 15.79% |
| D 双侧但证据不足 | 146 | 0.91% |
| E 无信号 | 13,062 | 81.59% |

双侧过阈 420 中同号仅 **156（37.1%）**；符号置换 null 209.8±10.1 → **z=−5.33**。
⇒ **可复用判读：EB+lfdr 把"逐元件误差控制"补上了（不依赖被否的循环分母），但补完之后"同向"仍少于"反向"（106 < 168）——它救的是新颖性/方法可实施性，救不了效果层。** 汇报时**科学轴（信号是否成立）与专利轴（方法是否有未披露增量）必须分开讲**，不要混成一句"这个方案没用"。
⚠️ 本探针属**只读可行性评估**：**禁止在用户拍板前**把结果写进权项/交付件。必须给并列选项（本次三条：①补实现进权项 ②删需求那句维持现状 ③**先查 Z 标定**），并说明倾向理由。

完整配方（docx 正文取证两个坑 / 经验零假设标定 / 四步 lfdr 实现 / 处置纪律）→ `references/empirical-null-and-lfdr-probe.md`。

**方法论铁律（教训）**：参考侧（小样本）做方向门控前，必须先跑完这六项（①–⑥ 为阻断级前提检验，⑦ 为可选的新颖性探针）；**"参考侧方向可信"是一个需要独立证明的假设，不能从"参考侧强度测不准"推出**——强度与方向是两种统计性质。① 分母含分子条件 = 循环论证；② 检验"配对是否携带信息"要保边际破配对；③ 检验"效应是否存在"要破坏处理变量；④ 已显著子集里的方向一致性可能整段跑在检验力上；⑤ 元数据干净 ≠ 结论稳健，LOO + 分层子集必跑。

**前提被否之后怎么走 → `references/premise-falsified-disposition.md`（不要继续改数字；含顺序铁律、收敛信号判据、claim 分层重定位、四段式回答骨架）。** 一句话：前提一旦被否，正确的下一步**不是换口径重算，而是重新定位 claim** —— 方法层可以留，效果层的"保守集/可替代"必须撤。

### 🔬 口径切换影响归因（"能不能只换数字"判据，2026-09-12 实测）

**触发**：用户拿着旧版交付件问「换成新口径，难道全都变了？如果没变，为什么不只是替换一些数值就可以了呢？」「为什么一直在变？」

**三刀定位法**（完整配方 + 本次证据全文 → `references/caliber-switch-impact-attribution.md`）：

1. **第一刀 · 字段一致率**（先定位，别只比总量）：取两版输出清单的**共同实体**，逐字段比一致率。本次 159 个共同基因：`Z_human` **159/159 (100%)**、`n_tiles_h` **159/159**，而 `Z_monkey` **0/159 (0%)**、`n_tiles_m` 46.5% ⇒ **口径切换只动了猴侧，人侧一字未改**（人侧铁证 24.3×/p=0.005/图1/图2 逐字不变）。推广判别式：单侧字段 100% 一致 + 另侧 0% ⇒ 换的是**单侧输入表**；两侧都大面积不等 ⇒ 换的是**实现层**（三层归因见 `data-integrity-self-proof.md`）。
2. **第二刀 · 三类分桶**（决定动什么）：① **机械连锁数字**（16,031→16,029、537→582、26.9→29.1、12.5×→12.3×、89%→95.5%…）→ 成组替换，**禁只改一半**；② **名单换血 → 图须重画**（图3 扇区 `37+299`→`16+341`）；③ **正文点名实体 → 文案须重写**（有益效果4 点名的 GRIA1/GRIA2/SYT1/EPHA5/EPHA6 **全部掉出 16 子集**，SYT1/EPHA6 连 357 都离开）。
3. **第三刀 · 重合率阈值**：最高置信子集 37→16 只重合 **9 (24%)**；A 级清单 336→357 只重合 **159 (47%)**。**阈值：≥90% 可 find-replace；50–90% 必须附差异清单；<50% 禁止 find-replace**（交出去的清单文件必须一起换，否则与正文对不上）。
4. **第四刀 · 缩水幅度 → 判定"阈值边界集合"**（给出机制，让归因可证伪）：只报"哪一侧变了"还不够，必须报**变多少**。本次 159 个共同基因：`|Z_human|` 中位 **15.381 → 15.381（Δ = +0.000）** vs `|Z_monkey|` 中位 **6.346 → 5.098（−19.7%）**；全表 16,010 基因同向复验：`|Z_human|` **3.360 → 3.360（Δ=0）**、`|Z_monkey|` 1.822 → 1.859。⇒ **名单换血的机制 = 小样本侧效应量整体缩水约 20%，把元件从 `|Z_m|≥12` / `p_m<0.05` 门槛的一侧挤到另一侧**。**判据（可推广）**：交集率 <50% **且** 变化侧效应量缩水 ≥15% ⇒ 该名单是**阈值边界集合（threshold-boundary set）**，不是生物学本体——真实的生物学类别不会因换一次小样本导出就换掉一半成员。汇报时明确写出"阈值边界集合"这一判定，并据此禁止把该名单写成 claim 的技术效果断言。
5. **⚠️ 数字来源依赖（引用前先锁定文件）**：同一结论在不同产出上有 ±5 个实体的残差。循环论证检验从**锚定表** `P3_L1_data/M2_repro_gene_conservation_all.csv` 实算得 `|Z_h|≥12`=**1409** / 同向=**582** / 同向且 p_m<0.05=**357** / 猴侧显著(不分方向)=**894** / 同向:反向=**357:537** / 实测÷随机符号期望=**0.80×**；而**管线** `b1_gate_null.py` 产出为 **1404 / 581 / 357 / 890 / 357:533 / 0.79×**（null 449.7±14.8, z=−6.27）。**结论完全一致**（两项独立检验均判定同向为亏损而非富集），但**引用具体数字时必须注明取自哪份文件**——用户对"数字老是变"零容忍，同一结论报出两组数字会被当成新的漂移。**本 SKILL.md 与 `references/` 统一采用锚定表口径**（1409 / 582 / 894 / 537 / 0.80×，与 A22.3 交付件写的 582 一致）；`b1_gate_null.json` 的 1404 系列标注为管线口径。

**铁律**：口径切换后**先归因、再谈替换**。只报"537→582、336→357"没有信息量——用户真正要问的是**哪些实体进/出**（把数字翻译成基因/样本名单再汇报）。归因结论必须连到 claim 分层：重合率 <50% 说明这些名单**卡在小样本侧门槛上、不具口径稳健性**，只能作"实施例输出"，claim 压方法层。

### 🔬 同向率归因诊断（"为什么只有 40%？是猴子数据吗？" —— 2026-09-12 实测四探针）

**触发**：用户问「跨物种同向率为什么这么低？」「是猴子的数据吗？」「为什么随机反而更高？」「能不能有更好的算法？」——**禁止只回答"猴侧样本少"**（实测那只是次要因素，单因归因会被数据推翻）。四探针按顺序跑，脚本 `scripts/concordance_diagnostics.py` 可直接复用；完整证据 + 同类文献对照 → `references/concordance-rate-attribution.md`。

**探针 0 · 基准不是 50%，是"边际保持的独立配对期望"**（最易错，必须最先算）
```python
ph = (np.sign(Zh[m]) > 0).mean(); pm = (np.sign(Zm[m]) > 0).mean()
base = ph*pm + (1-ph)*(1-pm)          # 独立配对期望同向率
```
本次（890 子集）：人 58.3% 正 / 猴 54.2% 正 ⇒ **基准 50.7%，不是 50%**。观测 357/890 = 40.1%；符号置换 null 451.2±14.6 → **z = −6.44**。
⚠️ **不可把 40.1% 直接与 50% 相减**——边际偏斜本身就值 0.7pp。"随机更高"的正确表述是**观测低于独立配对基准**，不是"随机特别高"。

**探针 1 · 元件网格是否对齐（本次最大单一杠杆，也是方法缺陷所在）**

| 组 | 基因数 | 同向率 |
|---|---|---|
| 两物种 tile 网格**完全一致** | 1,544 (9.6%) | **50.5%** |
| 网格不一致（两侧各自 liftOver 重建） | 14,466 (90.4%) | **46.0%** |

排除小 tile 数巧合后差距扩大：tile≥30 → **51.9% vs 45.4%（差 +6.4pp）**。
⇒ **网格一致时同向率回到基准（=无关系）；网格不一致时掉到 46%。即至少 5–6pp 的"不一致"来自在比不同的物理区域，属方法缺陷而非生物学。** 判据：按 `n_tiles_h == n_tiles_m` 分组比同向率，并用 tile 数下限过滤排除小样本巧合。

**探针 2 · 排除"功效不足"解释（同向率是否随参考侧强度上升？）**

|Z_m| 四分位同向率 = 43.5% / 38.3% / 40.5% / 38.1% —— **几乎不动**。
⇒ 若真因是"样本不够"，同向率应随 |Z_m| 单调上升。**平坦 ⇒ 不是单纯功效问题**，必须往探针 1/3 找。
⚠️ 反例警示：**不要用"显著率随覆盖度单调上升"当功效证据**——那条链证明的是"p<0.05 是检验力、不是方向信号"（见上方检验四），语义相反。

**探针 3 · 大样本侧是否存在全局方向漂移**

人侧 Z **中位 +1.06 / 均值 +1.25**（无信号 Z 分布应以 0 为中心）；猴侧 +0.07 / +0.09。
⇒ 人侧存在**全局性方向偏移**，`|Z₁|≥τ_A` 筛出的强效应池有相当部分是"被全局漂移推上去的"，非实体特异衰老信号。**拿这批去问"参考侧是否同向"，问的其实是两套漂移是否对得上。** 判据：任一侧 `|median(Z)| > 0.3` 即为漂移信号，须先居中/分位数标准化再谈富集。

**探针 4 · 阈值敏感性扫描（直接回应"为什么非得是 12"）**

扫 τ ∈ {1.96, 2, 3, 4, 5, 6, 8, 10, 12, 15, 20, 30}，每档报 n_strong / 同向率 / 独立基准 / 差：

| τ | n_strong | 同向率 | 基准 | 差 |
|---|---|---|---|---|
| 1.96 | 10,836 | 43.2% | 50.9% | −7.7pp |
| 4 | 6,951 | 42.6% | 51.3% | −8.7pp |
| **12** | **1,404** | **40.1%** | 50.7% | **−10.6pp** |
| 20 | 338 | 41.0% | 50.5% | −9.6pp |
| 30 | 70 | 55.3% | 54.4% | **+0.9pp** |

⇒ **从 1.96 到 20 的每一档都低于基准；只有 τ=30（n=47）翻正。** 结论：**这不是 τ_A=12 选得不好，而是该统计量在任何切割下都不支持"同向保守"。** τ_A=12 的真实身份是**规模门槛**（把清单压到几百个），1.96 才是显著性门槛；12.3× 富集的落脚点恰恰是这个可自由选择的规模门槛 ⇒ 同时中"循环论证"与"阈值自由度"两枪。

**归因结论模板（四句话）**：① 主因是**元件网格未对齐**（占 5–6pp，属方法缺陷）② 次因是**大样本侧全局漂移**污染了强度筛选 ③ 参考侧 n=20 给不出可靠方向（趋势存在，但 corr(age, coverage)=−0.32、**p=0.175 不显著**，**不得声称已证实混杂**）④ **真实一致性未知**——当前 40% 是"方法噪声 + 生物学解耦"的混合物，做完网格统一/深度校正/漂移消除才知道真实值，**不可当生物学结论直接使用**。

**"更好的算法"六条（按回报排序，可直接回答用户）**：① **统一元件网格**（两侧 liftOver 到同一坐标系 / 只用双向可映射的 orthologous tile）② **深度校正**（零膨胀模型，如 PACS）③ **消除全局漂移**（中位数/分位数居中）④ **收缩估计替代极端阈值**（经验贝叶斯 / limma-voom 型 shrinkage，弃用 |Z|≥12 这类规模门槛）⑤ **换统计单元**（tile → 调控域/基因体聚合，或上提到细胞类型层）⑥ **跨物种正交投影**（SATURN / scGPT 类共享潜空间）。**①+②+③ 必做**——它们不改结论方向，作用是把技术噪声从生物学解耦中剥离。

**🔁 后继：用户再问「当前计算的方法还有可能改变吗？能设计更好的办法吗？」→ 分层裁决法**（完整配方 → `references/layered-concordance-diagnostics.md`）
上表回答「改什么」；但当用户开始质疑**主指标本身能不能信**（而不只是"再加个校正"）时，
还要判定这个一致率**是生物学还是统计量产物**。四探针 + 两条判据：

- **探针 A · 按主体侧强度分层**：弱池 ≈50% + 强池 <50%、单调下降 ⇒ **真实梯度，不是稀释**。
  ⚠️ 本次弱池 **0.4938** 最接近 50% —— 与"被噪声基因稀释到 46%"的直觉**正好相反**，不做分层就会归因全错。
- **探针 B · 长度混杂分解**：`corr(|Z_h|, n_tiles_h)=0.506`、`corr(n_h,n_m)=0.726`
  ⇒ Stouffer `ΣZ/√n` 假定 tile 独立，而同一基因内 tile 相关 ⇒ **长基因 |Z| 系统性膨胀**，
  两物种长度相关 0.726 ⇒ 真实配对"共同触发"必然多于随机 ⇒ 置换的 1.33× 里含长度成分。
- 🔴 **恒等式陷阱（本次实际踩中）**：按 `n_tiles` 分层后把各层率**按 n 加权平均，必然恒等于全局率** ——
  这是加权平均的**恒等式，不是检验**。（本次第一版输出"长度匹配后同向率 = 0.4636 = 全局 0.4636"就是它。）
  **真正的检验 = 层内强-弱差（−0.0186）对比全局强-弱差（−0.0554）⇒ 长度解释约 2/3。**
  推广：任何"分层后重算率"的操作，先问一句"这个加权平均是不是恒等于总体率"。
- **探针 C · 决定性判据 —— 层内符号翻转**：本次短基因层 **+0.0303** / 长基因层 **−0.0766 / −0.0506**
  ⇒ **现行"系统性反向"大概率是「Stouffer sum 型 Z × 基因长度」造出来的技术假象**。
  判据（可推广）：**效应符号随混杂层翻转 ⇒ 统计量×混杂的交互产物，不是生物学结论。**
- **探针 D · 加权旁证**：加权同向率 `min(|Z_h|,|Z_m|)` = 0.4393、`|Z_h|·|Z_m|` = 0.4277，
  **比等权 0.4636 更低** ⇒ 幅度加权放大的正是"反向"成分 ⇒ "逐基因等权 + 全局平均"不该当主指标。

**方法学依据（已回原文核实，勿凭记忆引用）**：`ΣZ/√n` 的独立性假定与 **LD** 问题结构同构
（SNP 之于基因 ≈ tile 之于基因）→ **Brown's method 对基因特征最稳健**
（**PMID 35601489**, Cinar & Viechtbauer, Front Genet 2022，原文逐字："standard methods for this
purpose (e.g., Fisher's method) do not account for the dependence among the tests due to linkage
disequilibrium"）；相关 p 值合并的现代实现见 **metacp（PMID 40253343, BMC Bioinformatics 2025）**。

**诚实边界（汇报必须一并给，缺一即过度声称）**：层内加权差**仍为负（−0.0186）** ⇒ 正确表述是
「**现行"系统性反向"这个强结论站不住**」，**不是**「正向已成立」；换口径后出现的"翻正"
若来自**临时构造的探索性统计量**，**过匹配零假设前只是假设，不是结论**。

### 🔧 三修复实施配方（用户点名要做 ①②③ 时读这一节）

用户读完上面六条后说「这三个你做一下，你记得把文件都标记好，对应的目录」= 进入**实施**阶段，
完整配方（含可直接复用的 `anchor_tiles()` 实现）→ `references/three-fix-implementation-recipe.md`。

**① 统一元件网格** —— liftOver chain 官方不存在时的通行替代 = **基因体相对坐标**：
```python
rel = (tile_mid - gene_start) / (gene_end - gene_start)   # ∈[0,1]
bin = min((rel * 20).astype(int), 19)                     # 20 个 5% 相对位置 bin
```
只保留**两侧同一 (基因对, bin) 都有 tile** 的位置 → (gene, bin) 级配对表（1.6 万基因 → 约 30 万单元）。
⚠️ bin 级 Z 整体偏小，**沿用 τ_A=12 会几乎筛空** ⇒ 跨聚合层比较必须改用**分位数匹配阈值**。

**② 深度校正（PACS 一类）** —— `d0 = median(z)`；`s0 = 1.4826 × MAD(z)`；`z2 = (z − d0) / s0`。
**σ0 > 1 即过度离散**（低深度/稀疏贡献的虚假显著性）。方法出处 PACS, Miao 2025 Nat Commun **PMID 39757254**。
🔴 **诚实边界**：完整 PACS 需 **tile×sample 计数矩阵**；只有 `(chr,start,end,r,p,q)` 汇总表时只能在 summary 层做经验零分布校正，
**不得说成"用了 PACS"**。配套做**深度分层稳健性**：按每元素 tile 数分 Q1–Q4 报同向率，稳定 ⇒ 深度非驱动因素；单调 ⇒ 须回计数层。

**③ 消除全局漂移** —— 聚合前 tile 级 signed Z **中位数居中**（`z -= median(z)`，按物种分别做）。
人侧实测 median Z = **+1.06**（应≈0）⇒ `|Z₁|≥τ_A` 筛出的强效应池有相当部分是被全局漂移推上去的。

**✅ 实测结果（2026-09-12 已跑完，完整表 → `references/three-fix-results-and-gate-collapse.md`）**：

| 条件 | 门控 n | 门控同向率 | 全量 Δpp | 全量 z |
|---|---|---|---|---|
| 条件0 基线 v9 | 890 | 0.4011 | −3.80 | −9.78 |
| ① 统一网格 | **82** | **0.6341** | **−0.84** | −8.04 |
| ② 深度校正 | **55** | 0.5818 | −0.82 | −7.72 |
| ③ 漂移消除 | 844 | 0.3922 | −3.90 | −10.04 |

**三条结论（可直接答用户"这三个做完结果呢"）**：① **统一网格是唯一有实质作用的修复**（符号翻转、全量背离幅度缩小 **4.6 倍**），
证实探针 1 的"网格未对齐是最大杠杆"，但杠杆只有 5–8pp，**不足以翻正**；② 深度校正方向一致但**门控后只剩 n=55**，仅作一致性证据；
③ **漂移消除基本无效**（门控/全量都比基线略差）——**但它确实修掉了漂移本身**（人侧正比例 0.583→0.486 回到 ~50%）⇒
**修掉一个混杂 ≠ 修掉结论，漂移不是同向率低的成因**。三条独立口径（门控 / 全量 / topK 配对数量对齐）一致：
**修复使估计向正移动、从未达显著；不设门控时结论仍显著为负** ⇒ 与「前提被否」结论**独立互证**，claim 效果层仍须撤。
⚠️ **门控塌缩陷阱**：网格化后单元 16,010→221,069，沿用绝对阈值 τ_A=12 会让 n 从 890 塌到 **82（−91%）**，
直接把"阈值收紧"的效应算成"方法收益"——**改动单元划分/分布形状的修复必须放弃绝对阈值**，改用
①全量口径 ②**topK 配对数量对齐** ③分位数匹配阈值**三选一并并排报**；**门控后 n<100 时禁止用 z 主张"方向翻转"**（本次 z=+1.67/+1.89 均 p≈0.06–0.10，属证据不足）。

**🔴 三个静默失败 bug（写向量化锚定代码时必查，全部只表现为"数量不对"、不抛异常）**：

| bug | 症状 | 修复 |
|---|---|---|
| `np.isin(gg, python_set)` | 锚定数 **0**（`np.asarray(set)` → 0 维 object 数组，逐元素比较恒 False） | `keep_np = np.asarray(sorted(keep_gids), dtype=object)` 再传 |
| 并行数组**部分过滤** | IndexError，或**静默取错行**（只过滤 `sel/idx` 漏掉同长度的派生数组 `m`） | 一次过滤**全部**同长度派生数组：`sel, idx, m = sel[ok], idx[ok], m[ok]` |
| `searchsorted` 输入**未排序** | 锚定数塌约 **1000 倍**（5,555,247 tile 只锚定 4,147 / 78 基因，正确 2,439,577 / 16,104） | `hdf.sort_values(['chrom','start'])`——`groupby` **不保证**组内有序 |

**唯一防线 = 跑完立刻打印 `tiles anchored / genes` 并与预期量级对比**（本次三个 bug 全靠它暴露）。
另：**同向率基准必须现算，不是 50%** —— `base = p₊ᵐ·p₊ʰ + (1−p₊ᵐ)(1−p₊ʰ)`（本次 50.7%），
报表永远同时给 `obs / base / delta_pp / z` 四列。

### ⚠️ 实施层的两种"静默死法"（2026-09-12 实测：进程跑了 17 min 后消失、**无 traceback**）

首次实施 ①②③ 时脚本打印完 `条件0 基线` 就消失，log 无 traceback、进程表为空。
**「log 尾部无 traceback + 进程消失」= 被外部杀掉（OOM / 父进程回收），不是代码报错**——此时不要再去"修报错"，要查复杂度与内存。
完整配方（可跑代码 + 判活/判死表 + 目录映射）→ `references/vectorized-anchoring-and-long-run-survival.md`。

| 死法 | 写法 | 复杂度 | 修复 |
|---|---|---|---|
| **逐组 DataFrame 布尔扫描** | `for mg,(hg,sym) in bridge.items(): msub = m_bin[m_bin.gid == mg]` | 16,160 × 10⁶ ≈ **数百亿次比较** | 改 **两次 merge 向量化配对**：`m_bin.merge(br, left_on='gid', right_on='m_gid').merge(h_bin, left_on=['h_gid','bin'], right_on=['gid','bin'], suffixes=('_m','_h'))`（O(n log n)，秒级）|
| **大 n 上的蒙特卡洛置换** | `N_PERM=20000` 套到全量数组（n≈10⁵–10⁶）| **2×10¹⁰ 次** | `perm_eff = min(N_PERM, max(2000, 2e7/n))`；或对"同向计数"直接用**解析零分布**（保边际的独立配对模型 = 符号置换的期望）|

**判据**：只要出现 `for x in 万级列表: df[df.col == x]` → 立即改 `merge`/`map`（`groupby().apply()` 逐组同样不行）。
**另**：`terminal(background=True) ... | tee log` 的退出码是 **tee 的（恒 0）** —— "exit code 0" 不代表脚本成功，必须看 log 尾部有无 traceback/完成行。

**存活性设计（任何 >10 分钟脚本的开工前清单）**：① 昂贵中间件（锚定表）落 `00_cache/*.parquet` 缓存（pyarrow 24.0 本机可用；本次人/猴侧各 ~4 min，崩一次就白跑）；② **逐阶段 `to_csv`**，崩溃时前面阶段不丢；③ `print(..., flush=True)`（管道到 tee 时 stdout 块缓冲，不 flush 会丢掉一半日志）；④ 用 `execute_python` 持久内核分步跑看真实异常，别 `terminal python xx.py` 冷启动长脚本；⑤ 加量级断言（`assert 1e6 < n_anchored < 1e7`）。

**跨聚合层的阈值陷阱（实施 ① 必踩）**：网格化后统计单元从基因级 → **(gene, bin) 级**，bin 内 tile 少 ⇒ Z 整体偏小，**沿用 τ_A=12 会把网格结果几乎筛空**（看起来像"方法没效果"，实际是阈值不可比）⇒ 跨层比较**必须改分位数匹配阈值**（各层取同分位），并在报告里写明"阈值按层分位数匹配"。

### 📦 交付件卫生：版本升级完整性 / 证据合规 / 权项落位（2026-09-12 v9→v10 交付重做）

用户说「把目录内容更新成最新的方法、结论、步骤」「升版本号」「这份交底书能不能过审」时读
`references/patent-deliverable-hygiene.md`。四条可直接复用：

| # | 铁律 | 本次实证 |
|---|---|---|
| A | **版本升级必须扫三层，缺一层就漏**：① 正文 grep ② **docx 表格单元格**（段落扫描扫不到）③ **内嵌图的像素**（**必须逐张 OCR**）——判据：声明"零残留"时要说明**扫了几层**，只说"grep 过没有"是假阴性 | 🔴 正文/图3/图4 已换新口径，**图1 仍画着旧数字 336/37**；根因 = 源图生成于口径切换**之前**，docx 只是**引用**它 ⇒ **只重建 docx 是无效动作，必须重出源图** |
| B | **循环论证的识别 = 分母定义里出现分子所依赖的条件** → 删除，改为**基线横评三元组**（`输出数 / 反向混入 / 精度 / 召回`），并落成**两条独立效果主张**（安全性：唯一在 100% 精度下把反向混入压到 0 的做法，不设门控者会把 57–60% 反向元件当真阳交付；有效性：同为"零混入"时对称 min 召回 1.1% vs 本方法 25.3% = **22.2×**） | 原"12.3× 富集"分子分母同含"同向"⇒ 循环论证，审查员一看即塌；v10 已全删并替换（见 Pitfall 23 / 检验一） |
| C | **权项分层的交付件落位**：塌掉的那层**不是删权项，而是改句子类型**——定性词（"跨物种同向保守"）、作为**效果**的实例数字、"有益效果"里的富集倍数 → 一律改中性表述（"提供逐元件方向一致性的判定与不确定性标注"）；旧倍数降为"已作废标注"（审计句保留、结论句删除） | 方法层 ✅ 保留（双实现互证）+ 效果层 ❌ 改中性 |
| D | **统一网格权项必须配 `z̄ = Z/√n`**，否则该权项是**负资产** | 单元 16,010 → 221,069、bin 内 tile 中位仅 **4**，沿用 `\|Z\|≥12`：人侧仅 **0.077%** 通过、猴侧 **0.0005%** → 几乎筛空（= Pitfall 25 门控塌缩陷阱） |

**召回率诚实边界（必与效果主张同时写）**：25.3% = 人侧 1409 个强效应元件只覆盖 357 个，**不是"全部检出"**——是"强度+方向双门槛"换 100% 精度的代价。答辩稿不得说成"全部检出"。

### 📐 附图形式合规 + 送代理前形式要件（2026-09-12 新增，与「交付件卫生」成对使用）

> 上文 `patent-deliverable-hygiene.md` 管**内容**（数字/口径/论证）；本节管**形式**（附图形式 / 法定要件）。
> 触发句：「交底书也要黑白线条图吗？」「可以出一套黑白版本」。
> 完整配方 + 法规原文 + 实现代码 → `references/patent-drawing-and-formal-requirements.md`。

**① 附图必须另备黑白线条版 —— 这是条款不是偏好**：《专利审查指南》第一部分第一章 **2.4 说明书附图**「应当使用制图工具和**黑色墨水**绘制，线条应当均匀清晰、足够深，**不得着色**和涂改」。实测 5 张附图彩色像素占 **4.8%–37.4%**（`fig_pipeline` 最高）⇒ 必须改造。
**改造原则**：区分系列只能靠 **hatch 影线 / 实虚线型 / 空心实心标记 / 黑白色阶**；标题条改**黑底白字**；并显式设 6 项 `rcParams`（`axes.edgecolor` / `text.color` / `xtick.color` / `ytick.color` / `axes.labelcolor` / `hatch.linewidth`）——**只设 `facecolor='white'` 会漏色**，改完必须用彩色像素实测复验（`scripts/check_figure_bw.py`，判据 **0.000%**），不要凭"我改了配色"宣布黑白。

**② 送代理前形式要件清单（8 项，逐项打勾）**：摘要 ≤300 字 / **摘要附图指定**（grep「摘要附图」须有命中）/ **附图标记说明** / **检索记录**（检索式 + IPC 分类号 + 对比文件 D1–D3）/ **每条从权的实施例落点**（从权写了 N 种方式，实施例须各有落点）/ 下游用途从权要有实施例 / 小样本从权补配对 z / 数字格式统一（`1,409` vs `1409`）。
🔴 **教训（本项目实测）**：这 8 项在 v9→v14 六轮内容修订里**从未进过修订清单**——每轮都在改数字与论证，**形式要件属于"送代理前必做、但内容迭代期不浮现"的一类**，用户最终逐项点名才做。⇒ **交付件收尾时先把本清单当 checklist 过一遍**，别等用户点。

**③ 法规查证路径（网络受限时）**：不要逐源 curl（会触发循环检测），**一次写多源探测脚本**（`urllib` + 桌面 UA + 多编码 fallback `utf-8/gb18030/gbk` + 按关键词打印 ±150 字上下文）；URL 含中文必须 `urllib.parse.quote()`；拿到法规**摘要**即可用，引用时写条款号并注明"建议代理人复核"，不要断言读了官方 PDF 原文。

### 📤 对外送阅版交底书（给老师/律师看的件）—— 老样式 + 黑白附图 + 零备注（2026-09-15 实测）

> 触发：「参考以前的填写样式」「黑白图片」「不要有什么备注之类的」「就是把现有的专利拿给老师看的，
> 说清楚专利的过程、怎么做的、新颖性」「图片记得确认对不对」。
> 完整规范（骨架逐节对照 / 零备注清单 / 五图数字对照 / QC 两轨 / 列归属坑 / 成品路径）→ `references/v21-deliverable-and-external-review-spec.md`。

**四条硬规则**：

1. **样式照抄老版模板，不另起格式**。参照件 = `E:/专利/_archive_交底书旧版/技术交底书_已填写_附图版_v16.docx`；
   结构 = 零摘要 → 一题目方向 → 二运用场景 → 三技术简介（五步）→ 三（补充）框架表 → 四有益效果 →
   四（补充）**区别与新颖性** → 五附图说明 → 六装置/存储介质 → 七下游用途 → 八申请人。
   生成器沿用 `section() / add_table(caption) / add_fig(width=Inches(6.0))` 三个 helper（与 v16 同源）。
2. **删掉全部备注性内容**（一条不留）：方向标记（`【方向标记：✅ B】`）、版本/口径元信息、版本变更对照表、
   口径切换史、答辩术语（A22.3/A25/A26.4/命门处置）、待跑项表、「供代理人参考」、「（请申请人本人填写）」占位、
   正文里的 markdown 标记（python-docx 不解析 `**粗体**`）。**判断口径：这份内容会不会让审阅者问
   「这是什么流程的一部分？」会 → 删。** 注意「与现有技术的区别与新颖性」是**实质**（用户点名要），不要当备注删掉。
3. **附图全部黑白线条版**并逐张核验（`scripts/check_figure_bw.py` + OCR 数值对账），
   配方与五图 ↔ 数字对照见 reference §4–§5。
4. **核验一次做完，不跨轮重复**：一个脚本跑全目录纯度/空白/尺寸 → **一批并行** `vision_describe` OCR 对账 →
   直接产出交付件。把一次核验拆成多轮近重复动作会被判「循环失控」并强制干预（本次实际发生）。
   另：路径存在性告警是**提示不是结论**，先 `ls` 实测再答（本次 `_archive_交底书旧版` 告警「不存在」但真实有 23 个文件）。

**v21 正本数字（对外件全篇引用的唯一一套）**：16,029 单元 → L1 3,180（19.8%）→ L1∧L2 1,604（50.44%）→
三柱 AND **150**（9.35%）；175 组扫描 / 19 组落 [30,500]；核心元件仅 **32%（48/150）**两侧同向；
猴侧独立对照 2.0 倍富集（0.4348 vs 0.2187）、ρ=0.764；衰老签名富集 fold 4.53、p=7.7×10⁻⁵、单库 FDR 0.0219
（⚠️ 经典衰老通路 Reactome/KEGG/SASP **不显著**，必须并列披露）。

## Beginner Teaching Pattern

When the user self-identifies as a beginner ("小白"), start with Part 0 analogies:
- CRE = "sticky notes on architectural blueprints" telling which page to read
- ATAC-seq = "scanning which pages are open"
- LiftOver = "converting page numbers between two different editions of the same book"
- phastCons = "a pre-calculated score you look up in a database — no math needed"

Then use the `references/beginner-quickstart.md` for concrete first steps.

## Integration with Other Skills

- **research-plan**: Generates Mermaid roadmap + module table for this framework
- **bioinformatics-patent-strategy**: Maps CRECS innovation points to patent claims
- **deep-research**: Multi-round literature search to verify patent gaps before execution
- **atac-seq-memomics**: Single-species ATAC-seq QC and peak calling (L0 prerequisite)


## Common Issues

| Error | Cause | Solution |
|-------|-------|----------|
| 可达性探针用 HTTP 200 判定"源可用"→ 假阳性：PatentsView 旧 API 已退役 | 只测了 HTTP 层（状态码/连通性），没有测协议层（返回体是否为预期 sche | 探针判据从"状态码"改为"内容签名"：检查 body 首字符是否为 { 或 [、content_ty |
| curl 调 api.patentsview.org/patents/query 返回 301 Mo | PatentsView API 走了 https 层的 301 跳转（http→ | curl 必须加 -L 跟随重定向；判活探针与原数据请求必须用同一套 flag（探针有 -L 得 2 |
| curl GSE67978_family.soft.gz 下载得 990 字节非 gzip（not  | GEO FTP miniml 路径不存在或已迁移；990B 是错误页 | 换用 web 端 series GSM 列表 + eutils esummary 批量拉标题；SUP |


## References

| File | Content |
|------|---------|
| `references/framework-full.md` | Complete 8-part technical framework from 2026-07-21 session |
| `references/beginner-quickstart.md` | Step-by-step first analysis for CRE beginners |
| `references/patent-angles.md` | Detailed patent claim mapping and A25 defense strategy |
| `references/data-sources.md` | Curated list of ENCODE/GEO accessions for human and monkey brain CRE data |
| `references/external-validation-calibration.md` | 外部验证数据源（GSE67978 人/猴/猩猩 H3K27ac ChIP-seq，2026-09-03 实证修正：无海马、人=hg38、猴=rheMac3）+ 阈值校准配方（ROC 定阈值，修复 C=0 缩放陷阱）+ **v3 实测修复：真实 H3K27ac 逐 tile 命中替换池级常量 → B 364→49，含锚点平移网格不对齐教训** |
| `references/method-validity-age-shuffle.md` | 年龄标签 shuffle（协变量置换检验）完整配方：sparse 向量化 Pearson 相关 + null 分布 + 粒度陷阱 + 覆盖度预检（2026-09-04 实测：人 peak 级 24.3× 真实 / 猴全 tile 级 0.23× 粒度错配警示） |
| `references/input-provenance-reconciliation.md` | **输入口径对账与溯源**：正本数字↔输入文件归属判定的完整取证链（逐实体比对判决表、文件名/时间戳考古、单脚本多口径改造、实测证据全文）——2026-09-11 定论：专利 v5 正本猴输入 = `monkey_ageDA_continuous.csv` |
| `references/data-integrity-self-proof.md` | **数据真实性自证**（被质疑"你改了我的数据"时的标准动作）：体量证据 → 脚本零硬编码核验 → 用用户原始输入独立重算 + 逐位比对（判读标准 max\|Δ\| vs double eps）→ 把命令交给用户自己跑；含**差异三层归因**（坐标层/管线层/实现层）、两版管线对照全表、"修复版"标签反转判据、交付时把口径锁死到 md5 文件级 |
| `references/premise-falsified-disposition.md` | 🔴 **前提被否之后的处置 —— 不要继续改数字**（用户问"为什么一直在变""到底哪个口径""**这件事究竟能不能作为总体思路**"时读；即上方五项检验任一否定前提后的收尾流程）：① **顺序铁律**（前提检验先于数字优化；本项目 5 轮返工全在改数字、0 轮检验前提）+ **收敛信号判据**（连续 ≥3 轮单向变弱 = 收敛非摇摆 → 停手重估 claim）；② **口径切换不是万能药**实测对照（all 同向率 40.1%/p=3.99e-9 vs continuous 35.7%/p=1.82e-18，两版都远低于随机 → 停止口径纠结的判据）；③ **claim 分层重定位**（方法层✅ / 效果层❌ 两层判定表 + 三条可保留技术效果 + 必须一起改的三处 + 必须向用户点明的硬性降级）；④ **四段式回答骨架** |
| `references/caliber-switch-impact-attribution.md` | 🔬 **口径切换影响归因 —— "能不能只换数字"判据**（用户问「换成新口径难道全都变了？」「为什么不只是替换数值就可以了呢？」时读）：① **第一刀字段一致率**（共同实体逐字段比对：本次 `Z_human` 159/159=100% vs `Z_monkey` 0/159=0% ⇒ 只动了猴侧；含可推广判别式：单侧 100%/另侧 0% ⇒ 换单侧输入表；两侧都变 ⇒ 换实现层）；② **第二刀三类分桶**（机械连锁数字 / 名单换血→图须重画 / 点名实体→文案须重写）；③ **第三刀重合率阈值**（≥90% 可 find-replace，50–90% 附差异清单，**<50% 禁止 find-replace**；本次 37→16 重合 24%、336→357 重合 47%）；④ 把数字翻译成**实体进出名单**的四分类表（含 9+28=37 / 9+7=16 自检恒等式）；⑤ 隐患讲清（名单卡在小样本侧门槛 ⇒ 不具口径稳健性）+ 六段式回答骨架 |
| `references/concordance-rate-attribution.md` | 🔬 **同向率归因诊断 —— "为什么只有 40%？是猴子数据吗？"**（用户问「同向率为什么这么低」「为什么随机反而更高」「能不能有更好的算法」「检索同类型的文章」时读）：① 探针 0 **边际保持的独立配对基准**（本次 50.7% 而非 50%，z=−6.44）+ 符号置换实现；② 探针 1 **元件网格同源性**（同源 51.9% vs 异源 45.4%，差 +6.4pp ⇒ 主因是方法缺陷）；③ 探针 2 排除功效解释（\|Z_m\| 四分位平坦）；④ 探针 3 全局漂移（人侧 median Z=+1.06 应≈0）；⑤ 探针 4 **τ_A 敏感性扫描全表**（1.96→20 全低于基准，只有 τ=30 翻正）；⑥ 四句话归因结论模板；⑦ **"更好的算法"六条**（统一网格/深度校正/消除漂移/收缩估计/换单元/正交投影）；⑧ **同类文献对照 16 篇**（保守派 Tyshkovskiy 2026 Nature PMID 42203874 / Takasugi 2023 NAR 37351606；发散派 Wennmalm 2005 Genome Biol 16420669 / Hwang 2026 Aging 42172440 / Beilina 2026 Mol Neurodegener 41851867；方法学 PACS 39757254 / Sarropoulos 2026 Science 41610256 / Meng 2026 Nat Commun 41839854）+ 层级依赖结论句。脚本 `scripts/concordance_diagnostics.py` |
| `references/layered-concordance-diagnostics.md` | 🧪 **分层诊断：一致性统计量的结论是「生物学」还是「统计量产物」**（触发句「**当前计算的方法还有可能改变吗？能设计更好的办法吗？**」「同向率是怎么算的？为什么这么低」）：先把现行定义抓成一行（**三个隐含选择**：Stouffer 聚合 `ΣZ/√n` / 基因级单点 / 全局等权）；**探针 A** 按主体侧强度分层（分清「稀释」vs「真实梯度」——本次弱池 0.4938 最接近 50%，**不是稀释**）；**探针 B** 长度混杂分解（corr(\|Z_h\|,n_tiles)=0.506 / corr(n_h,n_m)=0.726）**+ 🔴 恒等式陷阱：按 n 加权平均各层率必然恒等于全局率——那是恒等式不是检验；真正的检验 = 层内强-弱差 −0.0186 vs 全局 −0.0554 ⇒ 长度解释 2/3**；**探针 C 决定性判据（层内符号翻转：短基因层 +0.03 / 长基因层 −0.08 ⇒ 统计量×长度交互产物，非生物学）**；**探针 D** 加权旁证（加权后更低 0.4277）；**5 个可替换环节 + 推荐三步设计**；方法学依据 **PMID 35601489（Brown's method，`ΣZ/√n` 独立性假定与 LD 同构）+ PMID 40253343（metacp）**；诚实边界四条 |
| `references/concordance-and-null-definition-basics.md` | 📏 **定义层答法：同向率与「随机」怎么算（用户问「46% 怎么计算的？随机怎么计算的？简单一点」时读）**：① **铁律：定义层问题只答定义层**——一行定义式 + 3 行可跑代码 + 数字（+ 一句已知弱点），**禁带归因/方案/多个 offer**（用户会在连续多轮长回答后专门回头问定义并加「简单一点」作为降噪信号）；② 同向率 = `(sign(Z_h)==sign(Z_m)).mean()` = **7431/16029 = 0.4636**，与 \|Z\| 大小无关（唯一弱点，加权版反而更低 0.4393/0.4277）；③ 随机 = **打乱猴侧符号 2000 次** → 均值 **0.5021**（理论 0.5）、sd 0.0039、观测 z = **−9.99**；④ 三条引用纪律（「随机」≠恒等 50%，边际偏斜时基准 50.7%；**本定义 0.4636 与门控三档 z **严禁互相引用**——一个比绝对 50%、一个比层内基准**；问「怎么算」时不给归因）；⑤ **附带技巧：脚本找不到时用产物反解公式**（逐 thr 复现 → 看期望列是否随规模漂移 → 找「率<0.5 但 z>0」的符号反例，三招即可无脚本定案）；⑥ 与既有 20 篇 references 的分工表（定义层/归因层/分层诊断层/统计量审计层/零假设审计层各归哪篇） |
| `references/three-fix-implementation-recipe.md` | 🔧 **三修复实施配方（①②③ 落地代码）**（用户点名「这三个你做一下」时读）：① **统一元件网格** = 基因体相对坐标 20-bin 配同源 tile（1.6 万基因 → 约 30 万 (gene,bin) 单元；liftOver chain 不存在时的通行替代）+ 跨层阈值须分位数匹配；② **深度校正** = 经验零分布 `z'=(z−δ₀)/σ₀`（δ₀=median、σ₀=1.4826×MAD；σ₀>1 = 过度离散）+ **诚实边界**（完整 PACS 需 tile×sample 计数矩阵，summary 层校正不得说成"用了 PACS"）+ 深度分层稳健性 Q1–Q4；③ **消除全局漂移** = tile 级 signed Z 中位数居中（人侧 median +1.06 应≈0）；④ **三个静默失败 bug**（`np.isin(x,set)` 恒 False / 并行数组部分过滤静默取错行 / `searchsorted` 未排序塌 1000 倍）+ **可直接复用的 `anchor_tiles()` 实现**；⑤ 同向率基准须现算（50.7% 非 50%）+ τ vs τ_A 辨析 + 按修复项分目录带 `fixN_*_stats.json` 的交付约定 |
| `references/vectorized-anchoring-and-long-run-survival.md` | ⚙️ **实施层：向量化配对 & 长任务存活性**（重写任何「万级基因 × 百万级 tile」配对脚本、或长任务"没报错就消失"时读）：① **死法一 O(n²)** —— `for mg in bridge: df[df.gid==mg]`（16,160 × 10⁶ ≈ 数百亿次比较）→ 改两次 `merge` 向量化配对（秒级），含可直接抄的 `pair_bin()` / `pair_gene()`；② **死法二 大 n 置换** —— `N_PERM=20000` 套到 n≈10⁵–10⁶ 全量 = 2×10¹⁰ 次 → `perm_eff = min(N_PERM, max(2000, 2e7/n))`，或对同向计数用**解析零分布**（保边际独立配对模型）；③ **判活/判死三条**（log mtime / `psutil` 按 cmdline 匹配——Windows `wmic` 可能不存在、`tasklist` 看不到命令行 / **无 traceback 而进程消失 = 被杀不是报错**；`\| tee` 退出码恒 0 不代表成功）；④ **存活性设计五条**（parquet 缓存 / 逐阶段落盘 / `flush=True` / 持久内核分步跑 / 量级断言）；⑤ **修复项→目录映射表**（`00_cache` → `01_unified_grid` → `02_depth_correction` → `03_drift_removal` → `04_combined` → `99_report`）；⑥ **跨聚合层阈值陷阱**（(gene,bin) 级 Z 偏小 ⇒ τ_A=12 会筛空，须分位数匹配）|
| `references/three-fix-results-and-gate-collapse.md` | ✅ **三修复实测结果 + 门控塌缩判据**（用户问「这三个做完结果呢」/「结果呢？」时先读这篇）：① **门控总对照表**（基线 40.11% z=−6.42 → ①统一网格 63.41% z=+1.67 → ②深度 58.18% z=+1.89 → ③漂移 39.22% z=−6.50；解析 z 与置换 z 逐条吻合 ≤0.03 = 双实现互证）；② **全量口径表**（−3.80pp → ①③ −0.84pp，**仍 z=−8.04** ⇒ 修复削弱缺陷未反转结论）；③ **topK 配对数量对齐表**（K=890/2000/5000 三档，修复侧一致为正但 z<1.4 不显著）；④ 结论四条（①是唯一实质修复、②n=55 仅一致性、③无效但**确实修掉了漂移本身** ⇒ 修掉混杂≠修掉结论、三条口径独立互证 claim 效果层仍须撤）；⑤ 🔴 **门控塌缩判据**（单元重划 16,010→221,069 后绝对阈值使 n 塌 91%；三条合法对照：全量/topK匹配/分位数匹配；n<100 禁止用 z 主张"方向翻转"）；⑥ **汇报纪律**（用户说"结果呢？"→ 第一句上对照表，禁以"我先判断出一个缺陷"开头）；⑦ 产物坐标 + **v3 收尾技巧**（锚定落 parquet 缓存，改门控只重建配对表 0.1 min，绝不重跑锚定）|
| `references/patent-deliverable-hygiene.md` | 📦 **交付件卫生：版本升级完整性 + 证据合规 + 权项落位**（用户说「更新成最新的方法/结论/步骤」「升版本号」「交底书能不能过审」时读）：① **版本升级三层扫描**——正文 grep / **docx 表格单元格**（段落扫描扫不到）/ **内嵌图像素必须逐张 OCR**；含图1 硬伤根因（**源图早于口径切换生成、docx 只是引用它 ⇒ 只重建 docx 无效，须重出源图**）+ 可复用收尾检查单五步；② **循环论证识别法**（分母定义里出现分子所依赖的条件）+ **替换配方：基线横评三元组**（v10 实测六法对照表 `输出数/反向混入/精度/召回`）+ **两条独立效果主张**（安全性：唯一在 100% 精度下把反向混入压到 0；有效性：对称 min 召回 1.1% vs 25.3% = 22.2×）+ 主体侧真实性 24.3× shuffle；③ **权项分层的交付件落位**（塌掉那层不删权项、改**句子类型**：定性词/效果性实例数字/有益效果倍数 → 中性表述；旧倍数降为"已作废标注"）；④ **统一网格必须配 `z̄=Z/√n`** 否则是负资产（221,069 bin、bin 内 tile 中位 4、`\|Z\|≥12` 人侧仅 0.077% 通过）；⑤ **交付前诚实边界清单**（不主张"人猴共享衰老程序" 0.4636<0.5 / 召回 25.3%≠全部检出 / 猴侧 n=20 只能作方向参考、不要试图用参数救）|

| `references/deliverable-consistency-and-figure-qa.md` | 🔍 **交付目录 ↔ 交底书 双向对应性核查 + 内嵌附图逐张 QA**（用户问「交付目录的内容是不是跟交底书 docx 完全对应」「交底书的图是不是正确的？每张都检查一下，有没有遮挡」时读）：① **对应性六刀**（口径数字跨文件一致 / **复现脚本清单 ↔ 实际文件 + 引用脚本的真实产出物**——最常漂移，照表跑会报文件不存在 / 图号↔PNG 数 + **孤儿图反查** / **表 vs 图行数成员一致** / **图内标题 vs 文档用词一致** / **头条数字溯源 + 分析层口径核对**）；② **抽 docx 内嵌图 + 校验图↔图注配对**（读 `document.xml` 的 `r:embed` 顺序与图片段落前后文字，**不能靠文件名猜**；实测本文档为"图在前、图注在后"）；③ **三级检测**（边缘裁切 / 文字框遮挡含假阳性阈值 IoU<0.1 / 缺失标签放大 3× 定向复核）；④ 🔴 **OCR 误读反证**（同字体重渲染同一字符串再 OCR——本次证明"③置换定阀"是 OCR 误认、图本身无误）；⑤ **真实遮挡的代码行级根因**（`iloc[::-1]` + `legend(loc='lower right')` 叠加压住末行标签）+ 通用排查法 + 修复方案；⑥ Windows `vision_describe` 路径坑（`/tmp` 不可用，须 Windows 绝对路径）；⑦ 报告骨架（一致项表 → 不一致清单 → 逐图结论 → 真实缺陷+根因 → 修复选项）；⑧ **09-12e 新增**：**引用脚本 ≠ 产出该数字的脚本**（须读真实产出物逐字段比对）+ **数字溯源三判据**（源产物 `n_*` 指纹定分析层 / 经验 p 地板 `p==1/(N+1)` 不可当显著性 / 同源 .rds 多物种段必须整段读）+ **遮挡检测器假阴性盲区**（「0 对重叠」≠「无遮挡」，须配"应有集合−实得集合"清单差分）+ **孤儿图判据**（PNG 存在 + 反查无生成脚本 + mtime 早于口径切换）|
| `scripts/check_figure_occlusion.py` · `scripts/check_docx_figure_pairing.py` | 🛠 **交付前体检可直接跑**：前者 = 边缘裁切检测（最外 2px 非白像素）+ 文字框两两相交检测（含 IoU<0.1 假阳性提示）；后者 = 抽 docx 内嵌图 + 按 `document.xml` 校验图↔图注配对 + **复核文档"复现脚本清单"里每个文件名是否真实存在**（含表格单元格文本，段落扫描扫不到）|
| `references/empirical-null-and-lfdr-probe.md` | 🔬 **经验零假设标定 + 二维经验贝叶斯/local FDR 探针**（触发句「你确定你用了这个方法了吗？」「需求里点名的那个方法真用了吗」）：① **docx 正文取证两个坑**——`~$xxx.docx` Word 锁文件不是 zip（`sorted(glob)[-1]` 必中 → `BadZipFile`，须过滤 `~$` 前缀）+ docx 是 zip，正文要读 `word/document.xml` 后 `re.sub(r"<[^>]+>","",xml)`；② **Efron 25–75 百分位经验零假设标定**（实测人侧 μ=+1.063/σ=4.856 ⇒ `\|Z\|≥12` 仅 ≈2.25σ；σ>1 的倍数 = p 被夸大的倍数）+ 疑因排查三条（n 是供体还是 tile / Stouffer 独立性 / 全局居中）；③ **lfdr 四步实现 + 五态实测表**（A 同向 106 < B 反向 168、同号率 37.1%、符号置换 z=−5.33、5.8 s 跑完）；④ **判读：救新颖性/误差控制，不救效果层**；⑤ **处置纪律**（只读探针，拍板前禁写进交付件；给三条并列选项）|
| `scripts/ebayes_lfdr_probe.py` · `scripts/grep_docx_text.py` | 🛠 前者 = 二维经验贝叶斯 + lfdr 五态判定探针（输入 = 带 `Z_human/Z_monkey/p_monkey` 的元件表，输出五态分布 + 符号置换 z + 散点/热图，秒级）；后者 = docx 正文/表格取文本 + 多关键词计数与上下文打印（自动跳过 `~$` 锁文件），用于"交付件里到底有没有这句话"的三层扫描 |

| `references/patent-drawing-and-formal-requirements.md` | 📐 **专利附图形式合规 + 送代理前形式要件**（触发句「交底书也要黑白线条图吗」「可以出一套黑白版本」）：① **法规原文**——《审查指南》第一部分第一章 **2.4**「应当使用制图工具和黑色墨水绘制…不得着色和涂改」+ 三条实测判据（彩色像素 0.000% / 墨迹 4%–20% / 尺寸清单）；② **黑白化实现配方**——hatch 影线 / 实虚线型 / 空心实心标记 / 黑底白字标题条 / 6 项必设 `rcParams`（只设 `facecolor='white'` 会漏色的排查清单）；③ **送代理前 8 项形式要件清单**（摘要≤300字 / 摘要附图 / 附图标记 / 检索记录含 IPC+D1–D3 / 每条从权实施例落点 / 下游用途实施例 / 小样本从权补 z / 数字格式）+ 🔴 **教训：形式要件在六轮内容修订里从未进过清单**；④ **中文法规在线查证路径**（不逐源 curl、多源探测脚本骨架、`urllib.parse.quote` 中文 URL、引用口径"建议代理人复核"） |
| `scripts/check_figure_bw.py` | 🛠 **附图黑白形式体检可直接跑**：`python check_figure_bw.py <目录或图>` → 逐图打印 彩色像素% / 墨迹% / 尺寸(cm@300dpi) / 判定，退出码 1 = 有不合格。判据：彩色像素须 0.000%（阈值 `max(|R−G|,|G−B|,|R−B|)>12`）、墨迹 1%–30%（<1% 判疑似空白/过淡）。彩色/黑白两目录同时传可作对照 |

| `references/tile-level-da-significance-floor.md` | 🧱 **Tile 级 DA 的显著性天花板 + 统计量自证纪律**（触发：分阶段/连续 age-DA 跑完 **Up=0 Down=0**、用户问「为什么 up 和 down 都是 0」、**或准备把某个统计量报成 bug 之前**）：① **tile 级 FDR 硬地板**——BH 门槛 = α/N，5000bp tile（人 5,555,162）需 **p<9e-9**，启动子级（~2×10⁴）只需 2.5e-6；**症状指纹 = 各行 p 差几倍而 q 一字不差是常数**（本次 6 行 q 全 `0.9999978`）⇒ 先打 `min(q)/min(p)/sum(q<α)` 三个数，`min(q)≈1` 即判定**判据问题、非生物学结论**；出路按推荐度 = 换粒度（唯一根治）> 效应量分位阈值（须方法披露）> 对趋势 p 做 FDR；② **判据列须与设计匹配**（有序设计用趋势 p，不用 r 的 t 检验 p，两列常差 4–5 个数量级）；③ 🔴 **报"实现有 bug"前的三条最小合成实验**（`class(X[,i])` → `numeric`、稀疏 `==0` 语义正确、已知答案合成 tile 上 `jt_mid` = 298.5 vs EJ 300）——本轮两个"bug"假设（ties 丢失 / z 负号硬编码）**全被实测推翻**，其中一个是把**代数恒等式**当证据（`p=2pnorm(−|z|)` ⟹ `|z|=−qnorm(p/2)`）；④ **统计量正确 ⇒ 先怀疑对齐**：`r` 被 `valid` 过滤而 `J/zJ/pJ` 未过滤 ⇒ 静默错位，铁律 = 所有派生向量同一 mask 一起过滤 + `lengths()` 断言；⑤ **JT 有序趋势检验完整配方**（显式 `ORD` levels 防字母序反转、mid-rank ties 半分、`EJ=(N²−Σni²)/4`、`VJ` 公式、**量纲自查 EJ = 跨组配对数/2**：人 4×10 → 600 对/EJ=300/√VJ=41.43）+ 判读（z 中位数 ≈ ±4 ⇒ 系统性偏置非生物学；"同向=100%" 在 z 单边时是同义反复）；⑥ **汇报纪律**（用户原话「去死吧，那么久找不出一点问题」：先跑再开口、每轮给根因、说错当轮撤回）；**⑦ z 值定义审计（§9，2026-09-13 新增）** —— 「当前算法对不对 / z 值的做法」的标准答法：**框架对、实现错**（`z=qnorm(p/2)` 是从双侧 p 反推，与 p 严格单调一一对应 ⇒ **零信息增量**、且**符号已被 `\|·\|` 吃掉**）；**四条退化指纹**（① 同行 `r` 与 `z` 符号矛盾 ② z 分位全负不以 0 为中心 ③ 「同向(r,z)=100%」是同义反复 ④ `\|z\|` 依赖 n ⇒ 跨粒度阈值不可比），②③ 属**定义假象必须当轮撤回**；**§3a 已修订**（代数恒等式不是 bug 证据，**但它可能是另一个缺陷的证据 —— 两条必须一起说，否则真缺陷会被连带撤回**）；正确写法三条（`(J−EJ)/√VJ` / `sign(r)·qnorm(1−p/2)` / `atanh(r)·√(n−3)`）；🔴 **回答前先 `read_file` 读交付脚本正本**（本次交付的 `01_l3_*_ageDA.R` **根本没有 z 列**，带 z 的只在对话里）；**✅ 09-13 已闭合：门控三档 z=+3.85/+3.09/+3.27 的来源 = `scripts/03_three_baseline_comparison.py` L39–42/L59–62/L96–105**（由 `obs`/`exp` 两个**观测率**构造 ⇒ **非 p 反推**，不受 §9.1 退化缺陷波及）；但 `exp` 恒 < 0.5（0.4459/0.4377/0.4289）⇒ 它们是「**层内条件富集**」而非「优于随机」，**不得读成\"门控能挑出同向/可迁移元件\"**；决策性反例 = `thr=0.5` 档 obs **0.4781(<0.5)** 而 z=**+1.83**。探针 `scripts/repro_pertile_gate_z.py`（复现 + 零假设语义三问判决，可直接跑） |\n| 🔬 **零假设语义审计四问（跨项目通用，09-13）** | 拿到任何\"匹配零假设 z\"先问：① 期望从哪儿来（外部先验 / 置换 / **观测自估**）；② 被检验集合落在其所属层的比例（**≈100% 在单层 ⇒ 恒等式，数值即不可用**；<1% ⇒ 条件检验，不可冤判为循环）；③ **`exp` 是否低于无信息基准**（低于 ⇒ **禁称\"优于随机\"**）；④ 同一常数是否复用到规模不同的多个集合（是 ⇒ 伪匹配）。完整判据表 + 两区间划分 → `patent-analysis` 的 `references/null-hypothesis-selection-and-circular-null-audit.md` §2 |

| `references/anchoring-unit-audit.md` | 🔍 **锚定单元审计：重复计数 / 归属歧义 / 覆盖率分母**（要把 **n（锚定单元数）** 报进 claim / 说明书之前、或用户/审查员问「同源窗口与基因窗口重叠会不会重复计数」时读）：① **重复计数不存在且可证**——`anchor()` 命中即 `break` ⇒ 每单元至多归属 1 基因 ⇒ `Σn ≤ 单元总数`；四处核对实测表（**空 human_gene_id 10,341 行 = 未匹配猴基因、非多对一**：26,501−10,341 = 16,160 ≈ 非空唯一人 gene 数 ⇒ 严格 1:1）；② **归属歧义 1.02%**（chr1 443,121 tile 中 4,538 个 ±2kb 窗口落在 ≥2 基因内、最大候选 3，贪心按 start 最大者选 ⇒ 排序依赖而非生物学 ⇒ 网格须打 `multi_map` 标记）；③ **覆盖率 43.8%**（Σ`n_tiles_h` 2,432,901 / 全基因组 5,555,247；锚定仅在 16,158 正交基因子集内，chr1 未锚定 52.1%）⇒ **说明书写 n 必须写明分母口径**；④ n 分布全表（`n_tiles_h` max 4,952 / `n_tiles_m` max 3,011 ⇒ 4,952 倍；tile 恒 499bp ⇒ n ∝ 基因跨度，n=4,952 ⇒ ≈2.47Mb）；⑤ **顺手完成审查要求的阈值依赖核查**（全量 4.51× → 剔 top1% 仍 **3.73× > 2** ⇒ 非少数超大元件驱动）；⑥ 可直接复用的代码骨架（含正交表多对一 / Σn 守恒 / chr1 多重性三查）+ 量级断言 + 本次踩坑表（**按记忆假设列名 `Zm/Zh`/`n` 报错 → 实际是 `Z_monkey/Z_human`/`n_tiles_m/h`**） |

| `references/v21-three-pillar-reframing.md` | 🧬 **v21 三柱重构（2026-09-15 定案，方向已被否决后先读这篇）**：可替代性/方向一致性承重永久换柱为三柱 AND（L1 序列保守 5.2% peak 级 + L2 跨物种可及 *仅 8 基因探路待全量* + L3 年龄效应 16,029 基因对）；创造性锚=衰老维度（五件对比专利 D1–D5 全无年龄梯度，逐件公布号/申请人/核心维度表）；A26.4 措辞（名称改「筛选方法」、可替代性降权10）；三柱数据落位 + 数量级粗算（几十到几百）；四件已交付文件路径；**通用工作流教训**（交接文档是时间切片、负结果是决策级事实非待重试 bug、文档叙述只认脚本常量+产物列语义） |
| `references/v21-deliverable-and-external-review-spec.md` | 📤 **v21 交付规范：对外送阅版交底书 + 黑白附图 QC**（触发：「参考以前的填写样式」「黑白图片」「不要有什么备注之类的」「拿给老师看的，说清楚过程、怎么做的、新颖性」「图片记得确认对不对」）：① **v21 正本数字全表**（16,029 → L1 3,180 → L1∧L2 1,604 → AND **150**；175 组扫描 19 组落 [30,500]；仅 **32%（48/150）**两侧同向；猴侧独立对照 2.0 倍富集 / ρ=0.764；衰老签名 fold 4.53 p=7.7e-05、单库 FDR 0.0219，**经典衰老通路不显著须并列披露**）；② **老样式骨架逐节对照**（照 v16 模板 + `section/add_table/add_fig` 三 helper）；③ **零备注清单**（方向标记/版本元信息/版本变更表/口径切换史/A22.3·A25·A26.4 答辩术语/待跑项/「供代理人参考」/markdown 标记；判据 = 「会不会让审阅者问这是什么流程的一部分」；⚠️「区别与新颖性」是实质不是备注）；④ **黑白五图 ↔ 内含数字对照表** + `legend(loc='lower ...')` 压标签坑；⑤ **图片 QC 两轨**（程序化：彩色像素须 0 + 非白 5%–30% 判非空白；OCR：数字与源 CSV 对账，勿凭「看着像对」）+ OCR 误认反证纪律；⑥ **v21 四文件列归属坑**（`v21_gene_base.csv` **无 `p100_mean`** → KeyError；L1 列在 `v21_gene_L1.csv`，合并版 `v21_gene_three_pillar.csv`）；⑦ **批量核验纪律**（一次脚本 + 一批并行 vision_describe → 直接交付；拆成多轮近重复会被判循环失控）+ **路径告警是提示不是结论**（先 `ls` 实测） |

## Proven Scripts

> Auto-generated from actual analysis runs. Each row records a successful execution.

| 物种 | 组织 | 方向 | 日期 | 脚本 | auto | user | ✔ |
|------|------|------|------|------|------|------|----|
| - | - | - | 2026-08-31 | find P1_da_young_old.R across drives | - | - |  |
| Homo sapiens; Macaca mulatta; Pan troglodytes | hippocampus | aging | 2026-09-03 | p4_crecs_v2_2.py recon + GSE67978 curl | - | - |  |
| Homo sapiens; Macaca mulatta; Pan troglodytes | hippocampus | aging | 2026-09-03 | GSE67978_dl + l3_topN_motif.R recon | - | - |  |
| human, rhesus macaque | hippocampus vs caudate nucleus | cross-species aging | 2026-09-03 | - | - | - |  |
| Homo sapiens; Macaca fascicularis | hippocampus | aging | 2026-09-04 | v5_substitutability_score.py | - | - |  |
| - | - | - | 2026-09-04 | v7_extrapolation_baseline.py | - | - |  |
| human | hippocampus | aging | 2026-09-10 | v5_substitutability_verification.py | - | - |  |
| human | hippocampus | aging | 2026-09-10 | gen_disclosure_docx_v6.py | - | - |  |
| Homo sapiens; Macaca fascicularis | hippocampus | aging | 2026-09-11 | repro_full_pipeline.py | - | - |  |
| - | - | - | 2026-09-11 | repro_full_pipeline.py | - | - |  |
| - | - | - | 2026-09-11 | repro_full_pipeline.py | - | - |  |
| - | - | - | 2026-09-11 | repro_full_pipeline.py | - | - |  |
| - | - | - | 2026-09-11 | repro_full_pipeline.py | - | - |  |
| - | - | - | 2026-09-11 | repro_continuous.py | - | - |  |
| - | - | - | 2026-09-11 | repro_continuous.py | - | - |  |
| - | - | - | 2026-09-11 | repro_full_pipeline.py | - | - |  |
| - | - | - | 2026-09-11 | repro_full_pipeline.py | - | - |  |
| - | - | - | 2026-09-11 | repro_full_pipeline.py | - | - |  |
| Macaca fascicularis | hippocampus | aging | 2026-09-11 | ） | - | - |  |
| Macaca fascicularis | hippocampus | aging | 2026-09-11 | v4_anchor_continuous_check.py（正本 anchor 逐字复刻 + continuous 猴输入） | - | - |  |
| - | - | - | 2026-09-12 | b2_age_shuffle_null.R + b1_gate_null.py + c2_confound_check.R | - | - |  |
| - | - | - | 2026-09-12 | plot_diagnostic_C_B.R | - | - |  |
| human | brain | aging | 2026-09-12 | wakeup_check_memomics-7839e23a | - | - |  |
| human | brain | aging | 2026-09-12 | fix_v10_unified_grid_and_drift.py | - | - |  |
| human | brain | aging | 2026-09-12 | fix_v10_unified_grid_and_drift.py | - | - |  |
| human | brain | aging | 2026-09-12 | locate_session_store.sh | - | - |  |
| human | brain | aging | 2026-09-12 | locate_session_store.sh | - | - |  |
| human | brain | aging | 2026-09-12 | locate_session_store.sh | - | - |  |
| human | brain | aging | 2026-09-12 | _dump_msg.py | - | - |  |
| human | brain | aging | 2026-09-12 | _dump_msg.py | - | - |  |
| human | brain | aging | 2026-09-12 | 09_gen_disclosure_docx_v11.py | - | - |  |
| human | brain | aging | 2026-09-12 | 09_gen_disclosure_docx_v11.py | - | - |  |
| human | brain | aging | 2026-09-12 | archive_blank_figure.py | - | - |  |
| human | brain | aging | 2026-09-12 | validate_v11_deliverables.py | - | - |  |
| human | brain | aging | 2026-09-12 | clean_word_lockfiles.sh | - | - |  |
| human | brain | aging | 2026-09-12 | verify_scope_check.sh | - | - |  |
| human | brain | aging | 2026-09-12 | cleanup_temp_script.sh | - | - |  |
| human | brain | aging | 2026-09-12 | pytest_offline_suite.log | - | - |  |
| human | brain | aging | 2026-09-12 | pytest_offline_suite.log | - | - |  |
| human | brain | aging | 2026-09-12 | pytest_offline_suite.log | - | - |  |
| monkey | brain | aging | 2026-09-13 | monkey_ageDA_FDR_diagnosis | - | - |  |
| monkey | brain | aging | 2026-09-13 | monkey_ageDA_FDR_diagnosis | - | - |  |
| monkey | brain | aging | 2026-09-13 | monkey_ageDA_FDR_diagnosis_fig | - | - |  |
| - | - | aging | 2026-09-13 | patent_db_reachability_probe.sh | - | - |  |
| human | brain | aging | 2026-09-13 | wakeup_check_memomics-7839e23a_dupcount | - | - |  |
| human | brain | aging | 2026-09-13 | dupcount_chr1_mult_and_v5_n_dist | - | - |  |
| human | brain | aging | 2026-09-13 | dupcount_diagnostic_figures | - | - |  |
| human | brain | aging | 2026-09-14 | v20_step1_confounder_inventory.py | - | - |  |
| human | brain | aging | 2026-09-14 | trace_4636_provenance.py | - | - |  |
| human | brain | aging | 2026-09-14 | read_three_baseline_script.py | - | - |  |
| human | brain | aging | 2026-09-14 | v20_01_confounder_check.py | - | - |  |
| human | brain | aging | 2026-09-14 | trace_null_conventions.py | - | - |  |
| human | brain | aging | 2026-09-14 | v20_01_confounder_check.py | - | - |  |
| human | hippocampus | aging | 2026-09-14 | v21蓝图_三根柱子数据就绪性盘点（只读核实） | - | - |  |
| - | - | - | 2026-09-14 | v21蓝图修订版_换柱+创造性锚重立（整合用户五条判断） | - | - |  |
| human,macaque | hippocampus | aging | 2026-09-15 | phase0_handoff_recon.sh | - | - |  |
| human | hippocampus | aging | 2026-09-15 | phase0a_verify_human_matrix.py | - | - |  |
| human | hippocampus | aging | 2026-09-15 | phase0a_verify_human_matrix.py | - | - |  |
| macaque | hippocampus | aging | 2026-09-15 | phase0b_verify_monkey_matrix.R | - | - |  |
| macaque | hippocampus | aging | 2026-09-15 | phase0b_verify_monkey_matrix.R | - | - |  |
