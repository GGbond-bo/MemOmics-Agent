---
name: bioinformatics-patent-strategy
description: >
  Bioinformatics method patent strategy and drafting. Covers A25 (intellectual activity 
  rules) defense, claim structuring for bioinformatics workflows, dual-patent 
  architectures, differentiation from existing patents, and the four-corner protection 
  system (方法/系统/存储介质/应用). Use when the user discusses patenting a 
  bioinformatics method, needs claim drafting guidance, or asks about patentability 
  of computational biology inventions.
trigger_keywords:
  - "专利"
  - "patent"
  - "权利要求"
  - "claims"
  - "A25"
  - "智力活动"
  - "交底书"
  - "可专利性"
  - "patentability"
  - "受理"
  - "授权"
  - "抵触申请"
  - "同日提交"
  - "优先审查"
  - "方法专利"
  - "专利评委"
  - "能通过吗"
  - "授权前景"
  - "毕业课题"
  - "答辩"
  - "答辩金句"
---

# Bioinformatics Method Patent Strategy

## Overview

This skill covers the end-to-end strategy for patenting bioinformatics methods in China (SIPO),
with focus on the unique challenges of computational biology inventions: A25 rejections,
creative step (非显而易见性) defense, claim structuring, and multi-patent architectures.

---

## 1. The A25 Problem (Most Critical)

**China Patent Law Article 25**: "智力活动的规则和方法" (rules and methods of intellectual activity)
are NOT patentable. This is the #1 rejection reason for bioinformatics method patents.

### 1.1 Five-Dimension Defense Checklist

Every bioinformatics patent说明书 must address ALL five:

| Dimension | Question | Your Answer Must Show |
|-----------|----------|----------------------|
| ① Technical Problem | Does it solve a TECHNICAL problem? | Industry pain point (e.g., "animal model translation failure rate >90%"), not a math problem |
| ② Technical Means | Does it use TECHNICAL means? | Specific computer data processing steps (Harmony correction, pseudobulk aggregation, mixed model fitting), not pure reasoning |
| ③ Technical Effect | Does it achieve TECHNICAL effect? | Output guides industrial decisions (e.g., A/B/C/D classification → IND filing go/no-go) |
| ④ Natural Law | Does it follow natural law? | Cross-species gene expression conservation is objective biology, not arbitrary |
| ⑤ Computer Necessity | Can it be done WITHOUT a computer? | MUST answer NO — 230K cells × 30K genes × mixed model iteration is humanly impossible |

### 1.2 Three Safety Anchors (Write into Every交底书)

**Anchor 1: Data is physical measurement**
> "本方法处理的单细胞转录组数据来自高通量测序仪对脑组织细胞的**物理测量结果**（UMI counts），属于对自然产物的技术测量，而非抽象的数字集合。"

**Anchor 2: Clear industrial application**
> Reference FDA Modernization Act 2.0 (2022.12 signed) or equivalent regulation. Show that the method output feeds directly into industrial decision-making, not academic curiosity.

**Anchor 3: Error detection capability**
> Include a verification step (e.g., UMAP mixing check after batch correction) that actively detects and flags failures. Mathematics doesn't need error handling — technical systems do. This proves your invention is a technical system, not a math formula.

### 1.3 The "Specific Order" Defense (Crucial Wording)

Must include this exact logic in the说明书:

> "单独的[method A]、单独的[method B]、单独的[method C]都是已知方法，但将它们以[S1→S2→S3→S4]的**特定顺序**、应用到[特定数据类型]这一**特定数据类型**上、以[特定统计单位]为分析单位、以[特定目标]为目标——这个整体流程在现有技术中未曾公开，且产生了'[unique output]'这一无法由任何单一已知方法独立实现的技术效果。"

### 1.4 Analogy Defense with Granted Patents

Cite successfully granted bioinformatics patents and map their defense logic to yours:

- **郭国骥 CN115064220A** (granted): "My contribution is not Pearson correlation, but building a 15-species reference database."
- **阮航 CN118298926A** (under review): "My contribution is not Transformer, but constructing a 1-N ortholog heterogeneous graph network."

---

### 1.5 客体判断：实用新型 vs 发明（方法只能走发明）

用户问"这个专利是实用新型还是发明"时，答案对方法类几乎总是**发明**，且**没得选**：

| 维度 | 发明专利 | 实用新型 | 方法类方案 |
|------|---------|---------|-----------|
| 保护客体 | 产品、方法（工艺/算法/流程） | **仅产品的形状、构造或其结合** | → 只能发明 |
| 法律依据 | 专利法第2条第1款 | 专利法第2条第3款 | — |
| 审查 | 实质审查（查新颖性+创造性） | 初步审查（不查创造性） | 发明必走实审 |
| 期限 | 20 年 | 10 年 | — |

方法权利要求（获取数据→评分→置换→分级→输出清单）保护的是"动作过程"，不满足实用新型"形状/构造"要件，审查员会以不符合专利法第2条第3款**直接驳回，无争辩空间**——这是门类错误，不是技术含量问题。生信评分/筛选/评估方法专利在实务上清一色走发明。且走发明反而有利：A25/A22.3 的创造性论证正是发明实审才有的战场，实用新型不查创造性、用不上这些论证。

---

## 2. Patent Naming Conventions

### 2.1 The Four-Corner Protection System

Always append `、系统、存储介质及应用` to method patents:

| Component | What It Protects | Who It Catches |
|-----------|-----------------|----------------|
| **方法** | Using the method | Anyone who runs your workflow internally |
| **系统** | Making/selling a system that executes the method | Software vendors who build a platform |
| **存储介质** | Distributing code/images that implement the method | Docker/GitHub distributors |
| **应用** | Using the output for commercial decisions | CROs selling "replaceability reports" |

### 2.2 Name Scope Rule

**The name describes the method's essential nature, NOT the data you happen to have.**

| Wrong (too narrow) | Right (method's true scope) |
|-------------------|---------------------------|
| 跨物种海马可代替性 | 跨物种脑组织可代替性 |
| 基于猴海马衰老... | 基于灵长类海马细胞类型特异衰老签名... |

Exception: If user has only 3 months and needs 受理, narrow is safer (lower驳回 risk).
Can always broaden via divisional application (分案申请) later.

### 2.3 When to Drop "系统、存储介质及应用"

Drop for application patents where the system/storage is already covered by a companion patent:
- Patent A: Full four-corner (方法、系统、存储介质及应用)
- Patent C (application-specific): Just 方法 (the screening method). Keeps the name short and the protection is already covered by A's system claims.

---

## 3. Claim Architecture

### 3.1 Independent Claim Structure (the "Specific Combination" Pattern)

Independent claim 1 should be a SPECIFIC combination of known methods in a SPECIFIC order applied to a SPECIFIC data type:

```
独立权利要求 1：
一种基于[X技术特征]的[Y领域]评估方法，其特征在于，包括：

S1: [数据获取 + 特定预处理步骤]
S2: [核心创新步骤 1 — must be computable, not abstract]
S3: [核心创新步骤 2 — must produce a measurable index]
S4: [输出步骤 — must guide a concrete decision]
```

### 3.2 Dependent Claim Narrowing Layers

Layer the dependent claims from broadest to most specific:

```
权利要求 2: 限定组织类型 (e.g., 脑组织)
权利要求 3: 限定子区域 (e.g., 海马)
权利要求 4: 限定物种 (e.g., 非人灵长类)
权利要求 5: 限定条件 (e.g., 衰老)
权利要求 6: 参数区间 (e.g., SDI阈值 0.5-3)
权利要求 7: 备选实施例 (e.g., ESM-2嵌入)
```

### 3.3 The SDI Principle (Statistics in Independent, Thresholds in Dependent)

```
独立权利要求: "计算物种分歧指数 SDI = |β_species|² / σ²_individual"
从属权利要求: "所述阈值范围为 0.5-3，优选 1"

Reason: The statistic is objectively defined; the threshold is empirically chosen.
The former should be protected; the latter should remain flexible.
```

### 3.4 Black-Box Algorithms: NEVER in Independent Claims

ESM-2, deep learning embeddings, transformer models — these are:
- Unverifiable by patent examiners (black box)
- Subject to "insufficient disclosure" (充分公开) rejections
- Unexplainable in the "how does it work" sense

**Rule**: Put them in dependent claims + alternative embodiments in the说明书.
Independent claims use transparent, verifiable methods (ortholog matching, linear models).

### 3.5 Fixed Weights/Numerical Parameters: NEVER in Independent Claims

Numerical weights (e.g., "0.20×L1 + 0.35×L2"), thresholds, and tuning parameters are subjective
and invite A25 rejection ("intellectual activity rule" — examiner asks: "why 0.20 and not 0.25?").

**Rule**: Independent claims describe the *method of determining* weights/parameters, not the values themselves.
Dependent claims specify the *calibration mechanism*.

Pattern for weight claims:
```
独立权利要求: "对S1-S4各维度得分进行加权整合，生成综合评分，
              其中所述加权整合的权重系数通过数据驱动方法确定。"

从属权利要求: "所述数据驱动方法为进化锚点校准方法，包括：
              (a) 选取至少三对已知进化距离的物种对；
              (b) 收集已知保守/不保守调控元件作为训练集；
              (c) 以各维度得分为特征、保守性为标签，训练可解释分类模型；
              (d) 将模型的特征重要性归一化作为权重系数。"
```

**Why this works**: The innovation is not "0.20 vs 0.35" — it's "using evolutionary distance as training
labels to calibrate a multi-dimensional scoring system." That's a verifiable, reproducible technical
method, not a subjective tuning knob. Use logistic regression (transparent) for the calibration model,
not random forest or neural networks (black boxes).

This principle extends to ANY threshold/parameter in bioinformatics claims: the method of determination
belongs in independent claims; specific values belong in dependent claims (or stay out of claims entirely
as implementation details in实施例).

---

## 4. Creative Step (创造性) Defense

### 4.1 The "Three Innovations in Series" Pattern

The strongest创造性 defense: three innovations that EACH have low probability of appearing in prior art, connected in series:

```
Innovation 1 (pseudobulk individual aggregation) 
    × 
Innovation 2 (mixed model SDI + species×age interaction)
    × 
Innovation 3 (A/B/C/D four-level gene classification)

→ Probability all three appear together in prior art ≈ 0
→ Examiner cannot construct "obvious combination"
```

### 4.2 Write the Examiner's Hypothetical Rejection FIRST

Anticipate and preemptively refute in the说明书:

> "单独的 pseudobulk 聚合、单独的混合效应模型、单独的基因分类在各自领域都是已知的，但将它们以 S320→S340→S400 的特定顺序应用到跨物种脑组织单细胞数据上，以个体而非细胞为统计单位，以区分物种效应和个体效应为目标——这一整体方案在现有技术中未曾公开。"

---

## 4.3 现有技术是"文章"≠被专利占位（改进型发明合法）

**用户常问的致命误判**："我们是申请专利，他们（学术文章作者）只发文章，我们在他们基础上优化，不就是专利吗？"——**用户是对的**。

| 事实 | 结论 |
|------|------|
| 学术文章 = prior art（现有技术） | 阻断"同样方案"的新颖性，但**不阻断改进型发明** |
| 文章作者不申请专利 | 不代表该技术领域不能被别人申请 |
| "把他们的方法套到新物种" | 显而易见套用 → 驳回（"本领域技术人员能想到"） |
| "发明了新的量化可替代性评分方法" | 新方法，有创造性 → 可授权 |

**检索必须区分两个维度**：① 专利检索（Google Patents）查"有没有人已占位"；② 文献检索（PubMed）查"最强现有技术是谁"。**两者结论要分开下**——文献命中 ≠ 专利死亡。

**改进型发明成立的三要件**（缺一不可）：非显而易见 + 有技术效果 + 可验证。反直觉/负向的实测结果往往是创造性论证的最佳锚点（见 4.5）。

### 4.4 独权重心：从"预测器"换成"评估方法"（A25 客体适格核心）

**反面（必驳）**：
> "一种跨物种衰老方向迁移预测方法，用猴侧预测人侧方向……"
> — 效果若实测"预测准确率 41.55% < 随机 44.29%"，审查员一句"无有益技术效果"即驳（A22.3 硬门槛）。

**正面（能活）**：
> "一种跨物种衰老[某效应]可替代性的分级筛选方法：S1 逐元件做年龄相关检验得双侧标准效应量 Z；S2 以主-参考非对称评分 S=Z₁×w(Z₂) 计算可替代性评分（主体物种大样本侧效应量 Z₁ 承担强度，参考物种小样本侧 Z₂ 仅经方向门控 w(Z₂) 贡献符号——同向 +1/反向 −1/方向不可靠 0，强度与方向解耦；**2026-09 独权已从对称 min 升级为此式**，旧 min 法漏检 89% 是本次升级的动机）；S3 以置换检验导出的阈值 τ 做四分类（保守/反向/单侧/伪替代）；S4 输出保守可替代子集作为跨物种可迁移的脆弱元件清单。"

**技术效果重心**：从"预测准确率"换成"筛选出 N 个双侧同向下调元件 + 富集某通路"——**实测数据就从"打脸"变成"铁证"**。

### 4.5 负向/反直觉结果的专利化（创造性锚点）

实测发现"真实 ortholog 关系下同向保守基因数**显著低于**随机配对"（如 1904 vs 置换均值 2013，双尾 p=0.0008）——这**不是失败数据，是专利灵魂**：

1. 它证明方法**有鉴别力**（能检出真实关系下的稀缺结构，不是随便抓一堆基因都"保守"）；
2. 它构成**反直觉、可复现、有实用价值**的技术发现（"多数衰老元件物种特异，仅少数跨物种保守"）；
3. 审查员最认"用数据推翻常识 + 给了可操作筛选方法"的组合。

**但前提**：必须把负向预测结果**重新框定**为正向的"筛选子集 + 生物学富集"效果，否则落入 4.4 的"无有益技术效果"死穴。同一组数据的两面，写法决定生死。

### 4.6 无湿实验的四层验证论证（方法专利不要求湿实验）

用户追问"没有实验验证算法的准确性，怎么证明算法是对的？"——先拆两个"对"，这是回答的钥匙：

| 含义 | 问的是 | 谁需要证明 |
|------|--------|-----------|
| **方法正确性** | 算法逻辑自洽、结果非巧合、优于旧法 | **专利只需证明这个** |
| **生物学真实性** | 筛出的元件在体内真调控衰老 | 论文/后续转化才需证明 |

**专利法不要求湿实验**：《专利审查指南》对方法专利的"有益效果"认可**实验数据、对比数据、仿真/模拟数据**，不要求生物活性/临床/湿实验证据。方法权利要求只要 (1) 本领域技术人员能照做（公开充分 A26.3）、(2) 声称的效果有数据支撑即可。用户用"没有湿实验"质疑时，先纠正是用"生物学真实性"的标准要求"方法正确性"。

四层非实验验证（由强到弱，逐层回答审查员质疑）：

| 层次 | 问什么 | 怎么验 | 本例结果 |
|------|--------|--------|---------|
| ① 零假设检验 | 结果是否靠运气 | 置换年龄标签 N 次构造空分布 | 真实信号 24× 于随机 p=0.005 |
| ② 独立富集 | 是否从噪声里捞 | 强效应集合内命中率 vs 随机基线(5%) | 336 vs 期望27 → 12.5× |
| ③ 方法 PK | 是否真比旧法强 | 旧法 vs 本方法同数据对比 | 漏检 89%(37→336) 修复 |
| ④ 生物自洽 | 筛出来是否说得通 | 功能富集 vs 已知生物学轴 | 谷氨酸-突触稳态轴 |

若还想加第五层（非专利必需），按性价比排序：模拟数据回测（造已知 ground truth 看找回率）> 独立公开数据集外部验证 > 已知标志基因命中率 > 最小湿实验(qPCR/原位杂交)。前三个纯计算、零成本、不碰动物伦理。

## 5. Multi-Patent Architecture (A + C Pattern)

### 5.1 When to Use A + C

When the invention forms a pipeline: "Select Model → Screen Compounds"

- **Patent A**: Model evaluation method (选模型)
- **Patent C**: Application method using A's output (筛药物)

### 5.2 The "Weld Point" (串联点)

A and C must share a concrete data dependency. This turns two separate patents into a "combination invention" (组合发明):

```
A's output → C's input:
  A: A/B/C/D gene classification
  C: D-class exclusion list → filters out unreliable drug targets
```

Without this weld point, the examiner sees two unrelated patents sharing data.
With it, the examiner sees a cohesive methodology pipeline.

### 5.3 Same-Day Filing (同日提交)

**CRITICAL**: File A and C on the SAME DAY. Reason:
- If A is filed first and published before C is filed → A becomes prior art against C (抵触申请)
- Same-day filing → mutual non-prejudice

### 5.4 Claim Differentiation

```
A's independent claims: SI + SDI + classification (评估框架)
C's independent claims: Reversal Score + perturbation matching (筛选框架)

A's core: "how replaceable is the model?"
C's core: "which compounds survive cross-species filtering?"
```

### 5.5 Emergency Plan

If time runs out (common for students with thesis deadlines):
- Submit A first
- C can use A's priority right (优先权, 12 months) to file later

---

## 6. Prior Art Search Strategy

### 6.1 Search in Multiple Domains

Don't just search your exact field. Also search:
- Adjacent methods (跨物种注释, cross-species annotation)
- Cross-domain analogs (生物等效性 in pharma, 测量不变性 in psychometrics)
- Different data types (bulk RNA-seq doing the same thing)
- Software copyright registrations (软著)

### 6.2 Key Search Terms

```
Chinese: 跨物种 可代替性 | 动物模型 转化 评估 | 物种差异 定量 指数
English: cross-species translatability | animal model predictive validity | 
         species divergence index | preclinical translation scoring
```

### 6.3 Track Applicants

Once you find one relevant patent (e.g., 郭国骥 CN115064220A), track the inventors:
- What else did they file?
- Who cites them (Google Patents "Cited By")?

---

## 7. Common Pitfalls

| Pitfall | Consequence | Fix |
|---------|------------|-----|
| Patent name too narrow (限定海马) | Lose protection for all other brain regions | Use "脑组织" |
| Pure math description (纯数学) | A25 rejection | Add three safety anchors |
| No verification step | Weakened "technical system" argument | Add S205 UMAP check |
| Black-box in independent claims | 充分公开 rejection | Move to dependent claims |
| Filing A then C months later | A destroys C's novelty | Same-day filing |
| Pretending QC differences don't exist | Reviewer spots uncontrolled confounders | Add batch correction step + acknowledge limitations |
| 说明书引用张冠李戴（citation mismatch）——作者+年份对上，但内容不支撑所引论点 | 答辩/审查被点名为硬伤，比不引更糟；如 2026-09-02 L2 文档把 \"Andrews et al. 2023\"（实为 AD 遗传学综述 *EBioMedicine*）挂给\"哺乳动物全基因组可及性秩保守弱\"论点，用户当场抓出 | 引用前必须核对原文（PubMed 摘要+全文首段）是否真的支持该论点；**同作者同年唯一命中 ≠ 内容支撑**。查证不到或内容无关 → **宁可删除，用我方实测数据（ρ/CI）支撑结论**，也不要挂无关文献撑场 |

> 🔴 **引用卫生铁律（2026-09-02 实锤）**：所有进入说明书/章节稿（L1/L2 draft）的文献引用，必须满足两级验证——① 引用存在（PMID/DOI/作者+年份可检索到）② **内容支撑论点**（原文确实得出该结论）。两级中任何一级不过 → 删除该引用并从数据实测重述结论；用户面对\"删除 vs 换文献\"时优先选删除（不引入新引用负担，消除被点名风险）。

---

## 8. Timeline for Student Patent Filing (3-Month Sprint)

```
M1: Lock data → Run analysis → Produce实施例 figures/tables
M2: Write交底书 ×2 → Internal review
M3: Submit → Receive受理通知书 → Graduation condition met ✅

Critical: Confirm whether school requires 受理通知书 or 授权证书.
If 授权证书 is required, MUST use优先审查 (12-month turnaround for 
bio-tech inventions).
```

---

## 9. Key References

- `references/literature-support-archive.md` — 🔴 **"方法来源 + 文献支撑"目录交付配方**（用户说"方法来源、文献支撑都要下载下来，放在一个目录下，为毕业论文做准备"时启用）：固定四类目录（01 现有技术对标 / 02 方法学来源 / 03 领域背景_组织与方向 / 04 统计与算法）+ 总表四要素（模块/方法/来源文献/本地文件/**状态**）+ 建表前必读已有 `references.md`（**引文条目 ≠ PDF**；注意 News&Views 评论者 vs 原始研究作者的 PMID 张冠李戴）+ 方法清单取自 `全流程溯源档案.md` 的 M0–M10（不凭记忆列）+ 订阅缺口诚实清单 + 汇报口径。与"数字溯源"（`全流程溯源档案.md`）互补：一个管方法出处，一个管数字出处。批量下载与付费墙判定见 `platform-execution-pitfalls` 的 `references/oa-batch-download-and-paywall-triage.md`
- `references/patent-defense-wording.md` — Exact Chinese wording templates for A25 defense
- `references/claim-templates.md` — Boilerplate claim structures for bioinformatics methods
- `references/s100-s600-framework.md` — Expression-level cross-species replaceability framework (S100-S600)
- `references/creca-multi-layer-framework.md` — Regulatory-element conservation assessment framework (R1-R5 CRECA), B-class gene detection, BNIP3 validation
- `references/s-scoring-substitutability.md` — 跨物种衰老可替代性 S=min(|Z|)×sign 评分的落地算法 + 真实数字(1904/3487/7562/3078, p=0.0008) + 数据粒度=保护范围硬伤 + min() 尺度敏感陷阱
- `references/patent-grantability-evaluation.md` — 🔴 专利评委视角的授权前景评估 + 答辩准备（第三类专利任务：评估自己专利能否过 + 能否当毕业课题）。五维授权判定表（A22.2/A22.3/A2/25/A26.4/A26.3）+ "评委先验数据再听故事"原则 + 三个最尖锐问题生成套路 + 关键答辩金句（"整体测不准≠逐元件 p 值无信息"用 62.6% vs 5% 命中率反证门槛有鉴别力）。用户说"作为专利评委/能通过吗/能当毕业课题吗"时启用
- `references/disclosure-evaluation-recipe.md` — 🔴 交底书版本评估完整配方（v5→v6→v7 全流程实测）：read_file→OCR→MD5 附图比对→落实核查表→Strong Accept 裁决框架→四坑+新增 h/i/j 检查项→交付格式。用户说"这是最新的，评估一下/你再评估一下/改了这几个地方你看看"时启用
- `references/m2-m7-repro-pipeline.md` — 🔴 M2→M7 端到端复现流水线配方：输入身份核对表（同名 CSV 行数/首行坐标/MD5）、坐标网格溯源技术（0/1-based 判别、r 值不一致=口径问题而非坐标问题）、流水线骨架、列名陷阱（human_gene_id vs gene_id）、pipeline_out 空目录判定。用户说"用我重跑的数据把分析做成流水线/复现一下"时启用
- `references/input-caliber-adjudication.md` — 🔴 输入口径判定法（input-substitution test）：两份候选输入各跑一遍全流程 → 三列对账表（正本/候选A/候选B）→ 按"效应量偏差 >5% 淘汰、ρ 逐位一致最强、置换均值是分布指纹"判定正本口径 → 残差归因（残差随输入变化小 ⇒ 来自下游步骤而非输入表）。含专利 v5 实测三列对账表（16031/1904/3487/7562/3078 vs all 16010/2335/3070/7677/2928 ρ−0.195 证伪 vs continuous 16012/1905/3474/7554/3079 ρ−0.081 确认）+ 与用户沟通的四段结论写法。用户说"用 all 版跑一遍对账""正本到底是哪个输入口径"时启用
- `references/caliber-swap-deliverable-replacement.md` — 🔴 **输入口径切换 → 交付件全套数字替换 playbook**。前置门禁（宣告 claim 失效前先 grep 确认它在交付件里——本次误报 v6 的教训）；数字分「口径相关 vs 口径无关」避免无谓重算；同名文件命名陷阱清单（`v5_substitutability_all.csv` 名带 all 实为 continuous、`..._continuous.csv` 装 all 结果）；两套独立实现互证；6 件交付件逐件替换点；基因名单按层级重挂；交付件内复现代码原样跑通验收。用户说「改用 all / 换成 XX 版重算 / 把交付件数字都换掉」时启用
- `references/figure-qa-and-doc-consistency-audit.md` — 🔴 **附图质检与交付件一致性审计配方**（§11「三期」的完整版）：三类缺陷（伪曲线 / 文字遮挡 / 图表·脚本清单不一致）、伪曲线的脚本判据与"保留统计量换图形、禁止重算"处置、遮挡根因模式（`barh`+`iloc[::-1]`+`loc='lower right'`+逐行标注）与修法、**OCR 误读 vs 图真错的决定性判别（渲染正确字符串再 OCR）**、多行刻度标签假阳性规则、复现链完整性 grep、两处 `figures/` 目录陷阱、docx media SHA256 比对、修后自检清单。用户说「交付目录是不是交底书的来源」「图对不对/有没有遮挡」「都修」时启用。配套探针 `scripts/check_figure_occlusion.py`（边缘裁切+空白+标签命中+文字框求交+docx SHA256，可进验证脚本）
- `references/print-legibility-and-figure-refresh.md` — 🔴 **附图缩印可读性 + 图源变更后 docx 重出配方（§11「四期」完整版）**：填充图案在缩印后退化成灰块的分图定性（单链流程图删图案 / 多系列对比图保留）、修法（纯白底黑框 + 反白标题条 + 字号上调）、**双指标客观验收**（PIL 墨迹占比 19.77%→15.65% + OCR 条数 12→23 / 置信度 0.53–0.98→0.98–1.00）、源图变更后探针必然 FAIL 是设计意图、**别用文件大小判断 docx 是否被替换**（WPS 保存可把 1.45MB→1.22MB 同时换掉全部内嵌图）、**「文件被占用」的决定性判据 = 改名测试**（`mv` 成功即无真锁，`~$` 可能是 0 字节残留）。用户说「图看不清 / 一堆小点点 / 干净一些 / 印出来是灰的」时启用
- `references/effect-size-transform-layering-and-preregistration.md` — 🔴 **效应量变换分层 + 冗余参数预注册**（§12.11–12.13 的完整版）：三量对照表（Fisher-Z / p 反推 z / Stouffer / Stouffer+n_eff）+ **"先定单元统计量是什么再谈改哪个"的判定程序** + 命名纪律（`ΣZᵢ/√n` 本身就是 Stouffer，n_eff 修正 ≠ "Fisher-Z 变体"）+ p 机器零饱和实测（人 19.07%）+ Fisher-Z 落地参数 + **跑前冻结 ρ 估计法**的协议模板 + 阳性/阴性三对照 + 改定位的取舍与"为什么不显然"四段抗辩链 + 外部专家评审意见吸收规程。用户贴出**统计/方法学逐条评审意见**、或要把某个统计量写进权项时启用

---

## 10. CRECA: Cross-Species Regulatory Element Conservation Assessment

### 10.1 When to Use This Pattern

When the invention concerns **evaluating whether an animal model's gene regulatory machinery is conserved** — not just whether gene expression levels are similar. This pattern applies when:

- The user has ATAC-seq/ChIP-seq data (or can access public datasets)
- The problem is "表达保守 ≠ 调控保守" (expression conservation ≠ regulatory conservation)
- The goal is to detect **B-class genes**: genes whose expression appears conserved but whose upstream regulatory drivers are divergent

### 10.2 The B-Class Gene — Patent Narrative Gold

**B-class genes** are the single most powerful differentiator for regulatory conservation patents:

> Expression is conserved between species, but the transcription factors and regulatory elements driving that expression are completely different. These genes are invisible to all existing expression-level replaceability assessment methods. They are the hidden cause of animal model translation failure.

**Literature anchor**: CroCoNet (2025 preprint) demonstrated that POU5F1 (OCT4) shows perfectly conserved expression between human and cynomolgus macaque neural differentiation — yet its upstream regulatory module is among the most divergent. This proves B-class genes exist and are not rare edge cases.

**Patent narrative structure**:
```
"现有方法对某一类关键基因系统性失明——
 这些基因的表达水平跨物种高度一致，
 但上游调控程序完全不同。
 本发明第一次提供了系统检出这类基因的方法。"
```

### 10.3 The Five-Layer CRECA Framework (R1-R5)

```
R1: Sequence Conservation (pure computation, no ATAC needed)
    ├─ Promoter liftover + phastCons/phyloP
    ├─ Public brain cCRE cross-validation (ENCODE + macaque brain atlas)
    └─ Key TF motif presence/absence/position/copy number (JASPAR)

R2: CRE Chromatin Accessibility Conservation (ATAC-driven)
    ├─ Peak overlap rate (Jaccard index after liftover)
    ├─ Signal intensity conservation (cross-species Spearman ρ)
    ├─ Cell-type specificity (same CRE open in matched cell types?)
    └─ Aging dynamics (species × age interaction in mixed model)

R3: TF Binding Dynamics Conservation (ATAC-driven)
    ├─ TF footprinting across species (TOBIAS / HINT-ATAC)
    ├─ Motif enrichment aging trajectories (chromVAR)
    └─ Binding intensity dynamics (species × age mixed model)

R4: TF→Target Regulatory Network Conservation (scRNA-driven)
    ├─ SCENIC regulon edge conservation (ortholog TF→ortholog target)
    ├─ Regulon activity aging dynamics (pseudobulk + cos(θ) + species×age)
    └─ Cross-validation: R2 CRE + R3 footprint evidence for R4 regulon edges

R5: Integrated Scoring
    ├─ CRECS = w₁×S_seq + w₂×S_ATAC + w₃×S_footprint + w₄×S_network
    ├─ Weights via evolutionary anchor calibration (logistic regression)
    └─ A/B/C/D four-level classification
```

### 10.4 Evolutionary Anchor Calibration for Weights

The weights w₁-w₄ are NOT fixed numbers — they are determined by a data-driven calibration method:

```
Training data: thousands of CRE pairs across species
Labels: evolutionary distance → conservation expectation
  • Human-Chimpanzee (6 Mya) → label = conserved
  • Human-Macaque (25 Mya) → label = intermediate
  • Human-Mouse (90 Mya) → label = not conserved

Model: logistic regression (transparent, each weight maps to one dimension)
Output: normalized regression coefficients → w₁, w₂, w₃, w₄
Validation: MPRA functional validation data as independent test set
```

**Patent claim pattern**: The *method of determining weights* goes in the independent claim. Specific weight values NEVER go in claims. This follows the same SDI principle (Section 3.3): statistics in independent claims, thresholds/values in dependent claims.

### 10.5 A/B/C/D Classification Table

| Grade | CRECS | Meaning | Decision |
|-------|-------|---------|----------|
| **A** | ≥0.75 | Fully conserved regulation | ✅ Safe to use monkey model |
| **B** | 0.50-0.75 | Expression conserved, regulation divergent | ⚠️ Hidden bomb — core detection target |
| **C** | 0.25-0.50 | Regulation conserved, expression divergent | 🔧 Usable with dose/baseline calibration |
| **D** | <0.25 | Both divergent | 🚫 Exclude from regulatory studies |

### 10.6 BNIP3 Validation Template (Four-Step, All Dry-Lab)

BNIP3 is the ideal validation gene because its upstream regulatory network is a published gold standard:

- HIF-1α → BNIP3: HRE site at -94bp (validated 2007)
- E2F1 → BNIP3: E2F site at -155bp (validated 2007)
- FOXO3 → BNIP3: ChIP-validated direct binding
- p53, NF-κB p65 → BNIP3: inhibitory regulation

**Validation steps**:
1. R1: Extract BNIP3 promoter (TSS±2kb), liftover human→macaque, verify HRE/E2F site presence and phastCons scores
2. R2/R3: Check BNIP3 promoter accessibility in both species' ATAC, perform HIF1A footprinting
3. R4: Run SCENIC on both species, verify all 4 known TF→BNIP3 edges are independently recovered
4. R4b: Regulon activity aging trajectory comparison (cos(θ) + species×age interaction)

**Plus negative control**: Select a gene with known primate regulatory divergence (from CroCoNet's POU5F1 module) and run the same pipeline — it should be classified as B or D. One positive + one negative = method discrimination power proven.

### 10.7 A′ + C Sister Patent Architecture (Regulatory Layer)

```
Patent A′: Regulatory conservation assessment method ("evaluate the machine")
  Independent claim core: R1 sequence → R2 ATAC → R3 footprint 
                         → R4 network → R5 CRECS + A/B/C/D
  Authorization probability: 65-75%

Patent C: Anti-aging compound screening ("screen the drugs")
  Independent claim core: Cross-species conservative filter signature 
                         + cell-type-specific reversal score 
                         + D-class target exclusion
  Authorization probability: 55-65%

Weld point: A′'s D-class exclusion list → C's screening input
Same-day filing → mutual non-prejudice
```

### 10.8 CRECA-Specific A25 Defense

The "B-class gene detection" capability is the strongest A25 defense for regulatory conservation patents:

> "本方法不是对基因表达的简单比较，而是通过ATAC-seq数据的染色质可及性分析、
> 转录因子足迹分析和SCENIC基因调控网络推断等多层技术手段，
> 实现对'表达保守但调控分歧'基因的系统性检出——
> 这一技术效果无法通过任何单一已知方法独立实现。"

The additional safety anchor specific to CRECA:

> "R2步骤包含liftover质量验证：若人-猴峰重叠率显著低于人-黑猩猩
> 重叠率，则自动标记该基因组区域为'比对质量存疑'。
> 本方法不是纯粹的数学演算，而是包含错误检测和风险控制的技术系统。"

---

## 11. 技术交底书填写规范

律师发来的标准交底书模板通常 6 个栏目，发明人填写后律师据此撰写正式申请文件：

1. **专利技术题目方向** — 发明名称（四角保护：方法、系统、存储介质及应用）+ 技术领域
2. **技术运用场景** — 解决什么技术问题（现有技术空白逐条列）+ 得到什么提升（可量化）
3. **技术方案简介** — 总体思路 + 分步技术组成（数据获取→核心评分→置换检验→分级输出）
4. **明显的有益效果** — 逐条量化（非随机性/富集倍数/对比漏检率/生物学自洽/应用可迁移）
5. **附图说明** — 列已有真实图 + 建议补充的流程示意图
6. **申请人** — 姓名/电话/身份证/地址

**填写铁律**：
- **无 AI 幻觉**：所有数字（元件数、富集倍数、p 值、样本量）必须来自真实数据文件，禁止编造；填前先 read 交付目录的核心文件（README/disclosure/abstract）拿准确口径，不要凭记忆写数字；
- **无 AI 味**：禁用"值得注意的是/综上所述/赋能/闭环/抓手"等套话，用平实准确的技术语言，交底书是给律师看的法律文件不是营销文案；
- **🔴 章节标题禁"备注感"（2026-09-10 v7→v8 用户实锤）**：面向 Agent/律师的备注说明**不得出现在交底书正式标题里**。用户当场质疑"三（补）、算法实现原理说明（**供理解技术方案**）""权利要求搭建提示（**供代理人直接修改使用**）"这类后缀"是有必要写上去的吗？"。处理规则：内容保留（算法原理说明是 A26.3 公开充分的证据、权项框架是行业通行做法），但标题用正式法律术语替换备注——"三（补）、算法实现原理（具体实施方式）"（用《专利法》正式章名）、"七、权利要求框架建议（供代理人撰写参考）"（突出参考性质不越俎代庖）；同理"四（补）、与最接近现有技术的区别特征及**协同效果**对照"中的"协同效果"与表格列"协同（量化）效果"重复表述，合并为"量化效果"。生成 docx 后自查：grep 标题中是否残留"供理解/供直接修改/备注/提示（供…）"等字样。
- **申请人隐私信息留空**：姓名/电话/身份证号/地址是用户个人隐私，Agent **必须用"（请申请人本人填写）"占位**，绝不编造——这是"无幻觉"的底线；
- **申请人信息页必须做成醒目独立表格（2026-09-10 v8 实锤）**：用 `doc.add_heading("六、申请人（请申请人本人填写）", level=1)` + 表 3（项目/内容两列：姓名/电话/居民身份证号码/联系地址，四行占位）独立成节，不要用普通 section 段落列表——用户会专门问"申请人信息页在哪里呢？"说明段落形式不够醒目难以定位。标题里带"（请申请人本人填写）"让用户一眼知道这是唯一需要本人完成的部分。
- **现有技术引用精确**：区分"评论文章(News&Views)作者"与"被评论的原始研究作者"（如 de Mendoza 是评论者 PMID 40425825，Phan MHQ 才是原始研究 PMID 40425826），避免背景技术引用张冠李戴被退回。

- **附图逐张核对（图文一致性铁律，2026-09-09 实锤）**：生成含附图 docx 后，**禁止只确认"图嵌进去了"就声称完成**——必须核对每张图的实际内容与"附图说明"文字是否一致。三步：① 解包 docx（`zipfile` 读 `word/media/`）确认图片数量 == 说明条数；② 用 `vision_describe` 逐张查图是否**有实际内容**（OCR 有无文字、亮度图是否全空白/纯色——空白图是致命缺陷）；③ 核对图内标题/坐标轴/关键数字与说明文字是否**对应**（数字、方向、概念三者一致）。2026-09-09 实际翻车案例（用户当场质疑"你确定能代表整个专利吗"）：图2 把负向置换检验（observed A=1904 < null mean 2012.7，p=0.0008）错配给"24倍富集 p=0.005"描述；图3 把"n=16031 四分类的 A(surrogate)=7562"错标成"336 核心元件分布"；图4 是空白图。三者都是"只嵌图不核图"导致。
- **🔴 图文一致性铁律二期：源图漏重出（2026-09-11 v9 实锤）**：**换了数据口径重出交付件时，必须同步重出全部源 PNG** —— 图里的数字是**像素**，文本 `grep` 与 python-docx 提段落/表格**都拿不到**，所以"旧数字零残留"**不能**当图文一致的证据。判定法：解包 `word/media/*`，把每张内嵌图的**字节数**与候选源图目录比对，**字节数一模一样 = 该源图没重出 = 头号嫌疑**。标本：v9 的 `image1.png` 171,779B 与 `fig_main_reference_asymmetric_scoring.png` 完全一致 → 判定它是 9-9 生成（早于 9-11 口径切换）而漏重出，正文已写 A 级 357/最高置信 16、图 1 末箱仍写 336/37；图 3/图 4 字节数与 9-11 新图一致 → 正常。修法：改源图（或改生成脚本里的数字常量 336→357、37→16）后**重跑文档生成脚本**；若源图是某次内联生成、**没有脚本留存**，只能按 `vision_describe` 的 OCR + 颜色分布复刻版式重出，并把重出脚本固化进 `scripts/`。换件后**必须重新从磁盘正本解 `word/media/*` 算 md5 + 再识图一次**复验（换的不是你核验过的那个临时件）。核验清单与探针见 `patent-analysis` 的 `references/deliverable-caliber-switch-traceability.md` §S4b + `scripts/verify_docx_embedded_figures.py`。
- **🔴 图文一致性铁律三期：伪曲线 / 遮挡 / 脚本清单（2026-09-12 v11→v12 实锤）**——用户问「交付目录是不是交底书的来源？图对不对？有没有遮挡？」时的**三项必查**（一期管"图有没有内容"，二期管"图有没有重出"，三期管"图里的东西是不是真的"）：
  - **① 伪曲线（最高危）**：出图脚本里 `pdf = stats.gamma.pdf(xs, a=k, scale=theta)` 而 `obs, null_mean, null_sd, p, ratio = 6285, 258, 1075, 0.005, 24.3` **是五个硬编码常数** ⇒ 曲线是矩匹配拟合出来的，**不是实测空分布**。判据 = 绘图数据源是**字面量**而非数据列。修法：**保留真统计量、换掉图形**（改为只呈现归档统计量 + 每图数字可回溯），**禁止重算**（原始置换脚本已丢失时重算必对不上归档值，反而制造新漂移）；顺带以归档 rds 为准订正叙述性 md（本次 `结论_口径决策链.md` 记猴侧「1.17×/p=0.267」，归档 `v8_age_shuffle_stats.rds` 实为 `0.23×/p=0.815`，方向相反）。
  - **② 遮挡（客观检测，别肉眼看）**：跑本 skill 的 `scripts/check_figure_occlusion.py <图.png> --expect "58.7%" "827/1409"`（边缘裁切 + 空白 + 关键标签命中 + 文字框两两求交）。**根因模式**：`barh` + `tab.iloc[::-1]` 行序反转 + 图例 `loc='lower right'` + 逐行 `ax.text()` ⇒ 必然压住最底行标签（本次 58.7% (827/1409) 被压、三次 OCR 读不到）。修法 `fig.legend(..., loc='lower center', bbox_to_anchor=(0.5,-0.055), ncol=4)` 移到绘图区外 + `bbox_inches='tight'`。**必须排除的假阳性**：多行 y 轴刻度标签自身的上下行天然相交（'基线①a' ↔ '对称min+同向'），脚本已内置抑制规则。
  - **③ OCR 误读 vs 图真错——决定性判别**：OCR 把 ⑤ 读成 ③ 时**不要改图**，先用**同一字体渲染「正确字符串」再 OCR 一次**——正确字符串也被误读 ⇒ OCR 字形缺陷，图无误（本次实证）。字形像素 IoU（0.294）**只能作提示不能作判据**（裁切宽度不固定有干扰）。承接 f)/h)：把"需人工确认"升级为"5 分钟内把责任判给 OCR 还是图"。
  - **④ 复现链完整性**：对每个「附图 N」全目录 `grep` 其输出文件名，**零命中 = 没有生成脚本 = 违反端到端复现**（本次图2/图3 零命中，图2 实为 `patent/figures/` **09-09 旧副本**）；顺带查源图时间戳 vs 口径切换日。另查**表体行数 ↔ 源 CSV 行数**（本次表1 列 7 个方法而图4/CSV 是 9 个）。
  - **⚠️ 两处 `figures/` 目录陷阱**：docx 生成脚本的 `FIG` 指向 `E:/专利/patent/figures/`，而交付目录另有自己的 `figures/`——出图脚本必须**同一个 `save()` 写两处**，只写交付目录会导致交底书仍嵌入旧图。改图后必须解包 `word/media/*` 与磁盘源图做 **SHA256 逐字节比对**（本次 5/5 一致）。
  - 完整配方（检测命令、假阳性规则、代码模式、修后自检清单、本次产出模板）→ `references/figure-qa-and-doc-consistency-audit.md` + `scripts/check_figure_occlusion.py`
  - **版本升级做法**：`cp 09_gen_..._v11.py 10_gen_..._v12.py` 后**只 spot-patch 变更点**（docstring/版本行/输出路径/表体行/图注），不重写 31KB 生成器——省 token 且不会漏改无关段落。
  - **改图不该改数字**：本次 357/16/19/16,029/16,010/221,069 **一个都没动**；验收 38 PASS / 0 FAIL + 陈旧字符串零命中 + `rail_review(post)` passed + L1 辩论 verdict=support(high)。
- **🔴 图文一致性铁律四期：缩印可读性（2026-09-12 v15 实锤）**——三期全过（图有内容、已重出、无伪曲线无遮挡）的图**仍可能在 A4 尺寸下糊成一团**。用户上传渲染图说「**看不清楚，一堆小点点，干净一些**」时即此情形。核心判据一句话：**问「这个填充图案在替我表达什么信息？」——答不上来就删**。
  - **分图定性**：**单链流程图**（方框靠 ①②③④⑤ 序号区分先后）→ 图案**纯冗余**，删填充、改**纯白底黑框 + 反白（黑底白字）标题条**、字号同步上调（标题 10.5→11.5pt、正文 8.4→9.4pt）；**多系列对比图**（基线①②③ vs 本方法同轴并列）→ 影线**必要**、保留，但优先改用「**线型 + 空心/实心标记**」替代点纹/交叉纹。⛔ 不要一刀切删光——会让多系列不可区分。
  - **⭐ 客观验收双指标（肉眼评"清楚了没"无法进验收脚本）**：① PIL 墨迹占比 `(arr.mean(axis=2)<250).mean()` + 白桶占比：本次 **19.77%→15.65%**、白底 **61.9%→71.0%**、彩色像素 0.000%→**0.0000%**（黑白合规未破）；② `vision_describe` OCR 条数/置信度：**12 条（置信 0.53–0.98，关键框乱码 `MA`）→ 23 条（0.98–1.00，五框标题+副标题全读出）**。**三指标同向才算变清楚，只报"我改干净了"不算。**
  - **改源图 → docx 必须重出，且探针会立刻 FAIL（设计意图，别去改断言）**：验收脚本的「内嵌图字节 = 黑白版源文件」在源图更新后必然报错（273,564 vs 245,274 B）——它正是「源图改了但 docx 没跟上」的报警器；重跑成文脚本 → 恢复 48 PASS / 0 FAIL，再解包 `word/media/*` 做 **SHA256 逐字节比对**（本次 5/5 全等）。
  - **⛔ 别用「文件大小没变」判断 docx 有没有被替换**：本次 WPS 保存过一次，docx **1,452,866 → 1,217,101 B**，但内嵌 5 图**全被换成新图**（压缩被重排）。判定"docx 里是哪一版图"只能解包比字节/SHA，文件大小与 mtime 都不可靠。
  - **「文件被占用」的决定性判据 = 改名测试**：`~$xxx.docx` 存在 + `open(p,'r+b')` 报 `PermissionError [Errno 13]` **不等于真锁**（本次据此误判"被 WPS 锁住、等用户关闭"，白等一轮）。`mv <docx> _tmp.docx` **成功即无真锁**（`~$` 是 0 字节残留孤儿）→ 立刻改回原名再写测试即通过；`mv` 失败才是真锁、才需要用户关编辑器。
  - 完整配方（双指标测量代码、改前改后对照表、四期自检清单）→ `references/print-legibility-and-figure-refresh.md`
  - **📁 交付件定位速查（2026-09-12 v15 复核实测——别再猜路径）**：
    - 交底书正本 = `E:/专利/技术交底书_已填写_附图版_vNN.docx`（**在项目根，不在子目录**）
    - **改前备份 = 前缀式** `_bak_vNN_before_<改动名>_<HHMMSS>.docx`（同样在根目录）⇒ 检索用 `ls -1 | grep -i bak` 或 `find . -name "*bak*"`，**不是** `<主名>*bak*`（v15 复核按后缀式搜过、0 命中，差点误判"备份不存在"——**首查未命中 ≠ 不存在**）
    - **黑白线条版附图 = 两处**：`E:/专利/patent/figures_bw/`（docx 生成器 `FIG` 常量指向此处）**与** `E:/专利/交付_跨物种衰老可替代性专利/figures_bw/`；彩色版在对应 `figures/`。⛔ `E:/专利/figures_bw`（项目根）**不存在** ⇒ 先 `find . -maxdepth 3 -type d -name "*figures*"` 探布局。⛔ **这两处是设计双写、不是残留重复，禁止去重**——`scripts/15_make_figures_bw.py` 第 37 行 `OUT = [r'E:/专利/patent/figures_bw', os.path.join(DELIV,'figures_bw')]`（第 7 行 docstring 亦明写两个输出目录），5 张图两处 SHA256 **逐字节相同**（2026-09-13 实测：fig1 `37b7a8fd…` / fig2 `fda92d1a…` / fig3 `d4b5cc88…` / fig4 `1211d098…` / fig5 `9f727183…`）。删任一处即破坏「脚本直接生成全部产物」的复现链。判「交付目录里有没有重复残留/该不该清理」前，**先读生成脚本的输出路径常量**，再谈去重
    - 成文/出图脚本 = `results/memomics-7839e23a/scripts/`（`15_make_figures_bw.py`、`16_gen_disclosure_docx_v15.py`、`validate_vNN_deliverables.py` 验收探针）；交付目录另有 `run_all.sh` 复现链
    - 判"docx 里是哪一版图"**只能解包比 SHA256**（文件大小/mtime 都不可靠，见上条 WPS 陷阱）；"好了没有？"式的完成度复核四件套（含 `awk` 扫主线未勾选）见 `wakeup-progress-check` 陷阱 C5
- **"A"字母复用警示**：专利里 "A" 在多个体系复用（CRECA 四分类 A/B/C/D 的 A=surrogate 类 ≈7562 vs "A 级核心元件"=336），写附图说明/正文时**不能裸写"A 级"或"336 个基因"**，必须写"基因锚定的核心调控元件（由同源基因锚定其 ±2kb 内 CRE tile 经 Stouffer 聚合）"，否则律师/审查员按 A26.4 打"元件 vs 基因关系不清"。

- **元件/tile/基因三阶口径统一（2026-09-10 v5 定稿，A26.4 清楚性）**：生信专利里"tile / 元件 / CRE / 基因"四个词代表**不同数据层级**，交底书正文、权利要求、附图说明必须统一到同一层级，否则读者（律师/审查员）在四词间反复跳、A26.4"关系不清"。本专利真实层级：**tile（500bp 可及性窗口）→ 基因窗口锚定（±2kb）→ 基因级调控元件（经 Stouffer 聚合）**——"336 个核心元件""537 个候选""37 个最高置信"都是**基因级**计数，不是 tile 级。典型错误：前文刚说 Z 是"基因级效应量"，后文却写"tile 判定为核心元件"，自相矛盾。修复 = 交底书新增"数据单元口径说明"小节，明确"本专利所述'元件'均指基因锚定的调控元件"，并写清三阶层级（tile → 基因窗口 → 基因级元件）。配套两处记号/结构修正：① 方向门控函数应写 `w(Z₁, Z₂)` 而非 `w(Z₂)`——"同向/反向"是猴侧相对人侧 Z₁ 的方向，不是纯 Z₂ 的函数（严谨的审查员会抓公式自洽性）；② 若发明名称含"方法、装置及存储介质"，正文**必须**补一段"处理器+存储器执行程序 + 计算机可读存储介质"的描述以支撑装置/介质权利要求——名称与正文不对称时律师无法撰写装置/介质 claim（前几轮一直漏补）。

- **年龄梯度必须写全 + 明示是算法前提（2026-09-09 用户实锤）**：涉及"随年龄变化效应/年龄相关性"的方法，交底书/说明书**禁止只写"猴 n=20"**——必须写清实际年龄梯度（如 20 例食蟹猴分 4 梯度：青年 5 岁×4 / 中年 10–12 岁×4 / 老年 22–23 岁×6 / 极老 28–31 岁×6，覆盖约 30–38 年自然寿命）。并明示一句"年龄梯度的存在是本方法成立的前提"——只有连续/多梯度年龄（而非仅"年轻—年老"两组）才能算每个元件的"随年龄变化效应"做跨物种方向比较。用户当场质问"为什么没写清猴子年龄？我们有猴子的年龄"——年龄数据是算法根基，漏写等于自废武功。

- **算法符号必须溯源到原始数据写通俗说明（2026-09-09 用户实锤）**：技术方案的抽象数学符号（Z₁、w(Z₂)、S=Z₁×w(Z₂)、τ、τ_A）会让非生信背景读者（律师/发明人/答辩委员）看不懂。用户当场说"这部分我没看懂，Z₁ 是怎么来的？w(Z₂) 是怎么回事？"。交底书必须在技术方案后补一段"算法实现原理说明"，把每个符号**溯源到原始数据**：原始数据是每个 500bp tile 的"可及性随年龄 Pearson 相关系数 r"（人 555 万 tile / 猴 530 万 tile）→ Z = Σ[sign(r)·Φ⁻¹(1−p/2)] / √n（Stouffer 法聚合 tile 到基因级，Φ⁻¹ 为标准正态分位数函数，sign(r) 标方向，√n 归一化）→ w(Z₂) 丢弃猴侧数值只留方向(+1/−1/0) → S=Z₁×w(Z₂) 同时编码"人侧强度+猴侧方向"。用真实数字串联（537 候选→336 核心→37 最高置信），让读者一眼看懂"Z₁、w(Z₂) 到底在算什么"。

> 🔴 **公式溯源铁律（2026-09-10 实锤，比附图硬伤更致命）**：交底书/说明书里的每一个数学公式，**禁止凭对话记忆写入**——必须先 `search_files` 或 `grep` 源文件（`disclosure.md` / `disclosure_substitutability.md` / `claims.md`）里的原始公式定义，确认公式名称和表达式后再写入 docx。2026-09-10 实际翻车案例：Agent 在对话早期误将 Z 说成"Fisher Z 变换 0.5×ln((1+r)/(1−r))"，后来自己纠正成 Stouffer 法，但生成 v3 docx 时又把错误版本写了进去——因为写 docx 时**凭对话记忆而不是源文件**。三份权威源文件（`disclosure.md` §5.2、`disclosure_substitutability.md` §83/127、`claims.md`）全部写的是 Stouffer Z `Σ[sign(r)·Φ⁻¹(1−p/2)]/√n`，唯独 docx 写了 Fisher Z。**Fisher Z 是把单个 r 变换，Stouffer 是把多个 tile 的 p 值聚合到基因级——两者是完全不同的统计操作，写错等于 A26.3 公开不充分**。根因 = 生成 docx 前没有 cross-check 源文件公式。修复 = 写公式前必查源文件，写后必在 docx 生成后读回核对。

> 🔴 **核心元件数量口径冲突铁律（2026-09-10 实锤）**：同一专利的"核心元件"数量在不同文档里可能代表**不同定义的筛选门槛**——非对称门槛（人侧强效应 + 猴侧方向 p<0.05）得 336 个，双侧强效应门槛（min(|Z₁|,|Z₂|)>12）得 37 个。两者**不是同一批元件的不同表述，是两套不同门槛筛出的不同集合**。2026-09-10 实际冲突：`disclosure_substitutability.md` v2.1（2026-09-05）把 A 级收紧为双侧强效应同向 37 个，但交底书 v3 docx 仍写 336 个为"核心元件"，且"对称 min 法 37 → 本方法 336，修复 89% 漏检"的创造性论证**在收紧口径下不再成立**（收紧后本方法也是 37）。**铁律**：生成交底书前必须先读最新版源文件确认"核心元件"的**当前定义**，并在交底书里明确标注采用的是哪套门槛、数量是多少。两套口径不能并存于同一份文件——如果口径已收紧，旧口径下的对比实验论证也必须同步调整或删除。

> 🔴 **文档宣称公式 vs 数据实际实现必须核对（2026-09-10 全量验证实锤，结论稳定性总根源）**：交底书/说明书里写的**公式**，必须与**实际生成数据的 CSV/脚本**核对——不能只信文档文字。2026-09-10 实测 `v5_substitutability_all.csv`（16,031 行）：S 列**实际实现** = `sign(同向)·min(|Z_h|,|Z_m|)`（same_direction=True 子集 S==min 100%，False 时 S==−min），即**数据文件用的是旧版对称 min 公式，不是交底书宣称的非对称 `S=Z₁×w(Z₂)`**。这是文档-数据不一致的硬证据：文档写了新方案，数据还是旧方案。**铁律**：① 声称方案前，用 `pandas` 全量验证 CSV 关键列（S 列的数学定义、class 筛选条件逐条复现），禁止只看前几行/单子集就下结论；② 文档公式与数据列冲突时**不得自作主张改文件**，必须把两选项（A=按数据现状改文档 / B=按文档方案重跑数据）摆给用户拍板，像 336 vs 37 一样等用户定夺；③ 复现筛选链时注意列名混淆（本会话曾把 `Z_monkey` 误当 `Z_human` 读、导致"|Z|≥12 只有 133 个"的假结论，实际人侧 1409 个）。

> 🔴 **结论稳定性：局部验证通过 ≠ 全局结论正确（2026-09-10 用户终极质问"你的结论怎么老是变"）**：任何"某列/某项等于某公式"的结论，**必须全量验证**（`np.isclose` 全表匹配率 + 分子集），禁止抽样/看头部若干行就断言"100%"。2026-09-10 翻车案例：上一轮结论记录"S==min 100%"（id:80），全量验证实际只有 41.56%——因为 same_direction=False 时 S 是负的 min，|S|==min 但 S≠min。**"子集 100%" ≠ "全量 100%"**。用户对结论反复变化零容忍，一旦发现上一轮结论被本轮数据推翻，必须：① 当场承认哪一轮错、错在哪、为什么（列名混用/符号问题/只验子集）；② 给出全量验证的新结论；③ 把验证代码贴进结论让用户可复核。宁可说"还在查"也不给未经全量验证的"精确数字"。

> 🔴 **同名 CSV ≠ 同一份数据（2026-09-11 用户自跑复现实锤，数字漂移总根源）**：用户按旧脚本自己重跑 M2 要复现专利数字时，磁盘上存在**两个同名/近名但内容不同的"猴子 ageDA"文件**——`E:/专利/M2/monkey_ageDA_all.csv`（用户自跑，5,296,656 行，首行坐标 20001）vs `E:/专利/monkey_ageDA_continuous.csv`（历史 v4b 正本输入，5,674,191 行，首行坐标 19500）——**两版不是「同一计算的两种坐标写法」，而是两次独立的 DA 计算**（2026-09-11 逐项实测更正：旧表述「坐标网格相差 501bp」已作废，勿再引用）。四项实质差异：① **聚合方式**（all = `getGroupSE(scaleTo=NULL, divideN=FALSE)` 原始 counts 求和 vs continuous = 每样本平均可及性 0~1 比例）；② **数值变换**（all = `log2(CPM+1)` vs continuous = 无变换）← **决定性差异**；③ **tile 过滤**（all = `rowSums >= 2×样本数` vs continuous = 仅去零方差）；④ 坐标基数（all = 1-based / 5,296,656 tile vs continuous = 0-based / 5,674,190 tile）。**判据**：坐标修正后 all 行数不变（5,296,656）→ 坐标改写不产生新行；两版 tile 级 r 相关仅 **0.89**、99.99% 数值不同 → 确证是两次独立计算而非坐标换算。用同一 Stouffer 锚定脚本、仅换猴侧输入，结果全面漂移：加权 Spearman ρ −0.081→−0.196、方向一致 6662→7431、高置信保守基因 1904→2336（+23%）→ 专利所有核心数字（336/37/12.5×/富集倍数）全部受影响。**铁律**：① 用户说"我重跑了一遍你看看/按我的数据复现"时，**第一步核对输入文件身份**（行数 + 首行坐标 + MD5），与历史生成专利数字的正本比较，不一致先查"哪份是专利正本"，二选一摆给用户拍板（像 336 vs 37 一样等定夺），**禁止自作主张选一份继续**；② 复现核对明细见 `cross-species-atac-conservation` 的 `references/M2-M3-reproducibility-checkpoints.md`（M2 输出对照表、坐标漂移表、fix_ageDA_coords.R 坐标坑、M3 输入输出清单）；③ "修复"要先弄清**修的是什么**——2026-09-11 澄清：`fix_ageDA_coords.R` 修的是 ArchR 1.0.3 getGroupSE rowData 的坐标（start 列实际是 tile index，真实 start=(idx-1)*500+1），**不是年龄类型**（用户自跑本就是连续年龄），r/p/q 统计列不动。向用户解释"为什么修复"前先读修复脚本原文，禁止凭记忆编修复理由。

> 🔴 **口径终局：用户 2026-09-11 拍板「改用 all」（本条覆盖本 skill 及 `references/input-caliber-adjudication.md` 中一切「all 版已证伪/废弃」的旧表述）**。交付口径 = `M2/monkey_ageDA_all.csv` + `M2/human_ageDA_all.csv`（两物种对称，log2(CPM+1)）。全套替换数字：16,029 对 / A=2336 / B=3070 / C=7677 / D=2928 / 加权 ρ=−0.1955；**核心元件 336→357**（人侧 \|Z_h\|≥12 + 猴侧 p<0.05 + 同向）；**双侧铁证 37→16**（+ \|Z_m\|≥12）；反向双高 24→19；v7 `Z_h = 1.0335 + 1.2931·Z_m`，R²=0.3472（**优于** continuous 的 0.2825）；**v6 promoter-proximal CRE 置换 p 0.0000→0.261**（富集 1.34×→1.035×）——但 2026-09-11 全目录 grep 证实 **v6/v7 从未进入任何交付件**（`promoter|启动子|TSS|v6` 在 `交付_跨物种衰老可替代性专利/` 零命中，含 docx/json），v6/v7 只是内部管线阶段，**不构成 claim 失效、不阻塞交付**。⚠️ 教训（Agent 本次自犯）：宣告某 claim「失效/章节不能用」之前**必须先 grep 确认它真的写进了交付件**——本次因未先确认而误报，向用户抛出「删 v6 章节 / 改口径 / 留 TODO」三选一，制造了不存在的阻塞点。判定顺序永远是**先查它在不在，再谈它成不成立**。两个独立锚定器（`P3_L1_data/repro_m3_from_M2.py` 与 `M2/repro_full_pipeline.py`）在 all 输入下互证一致（A=2336 / 2335）→ 结论对锚定实现不敏感。核心元件名单换血 53%（交集仅 159，正本独有 177，all 新增 198）。重算范围/交付件逐章节清单见 `E:/MemOmics-Agent/results/memomics-7839e23a/results/ALL版替换对照表.md`。
>
> ⚠️ **换口径前必做「结论稳健性对照」**：口径差不是细节——本案例中它把一条 claim 的置换 p 从 0.0000 打到 0.261。两口径并排跑全套、先列出会失效的 claim，再决定是否切换。

> 🔴 **口径切换「能不能只换数字」判据（2026-09-12 v8→v9 实测；用户直问「难道换到 all 版本全都变了？如果没变，为什么不只是替换一些数值就可以了呢？」）**：口径切换**先归因、再谈替换**——只报「537→582、336→357」没有信息量，用户真正要问的是**哪些实体进/出**。三刀定交付方式：
> ① **字段一致率定位**（别只比总量）：取两版输出清单的**共同实体**逐字段比一致率。本例 159 个共同基因：`Z_human` **159/159 (100%，两版 r=1.0000)**、`n_tiles_h` 159/159，而 `Z_monkey` **0/159 (0%，r=0.8842)**、`n_tiles_m` 46.5% ⇒ **只动了猴侧输入表，人侧一字未改**（人侧铁证 24.3×/p=0.005/图1/图2 逐字不变）。判别式：**单侧 100% / 另侧 0% ⇒ 换的是单侧输入表；两侧都大面积不等 ⇒ 换的是实现层**。
> ② **三类分桶**：**(a) 机械连锁数字**（16,031→16,029、537→582、26.9→29.1、12.5×→12.3×、89%→95.5%…）→ 成组替换，**禁只改一半**；**(b) 名单换血 → 图必须重画**（图3 扇区构成 `37+299`→`16+341`，图4 `537/26.9/12.5`→`582/29.1/12.3`）；**(c) 正文点名实体 → 文案必须重写**（有益效果4 点名的 **GRIA1 / GRIA2 / SYT1 / EPHA5 / EPHA6 全部掉出 16 子集**，其中 SYT1、EPHA6 连 357 都离开——这句**没法靠替换数字修**）。
> ③ **重合率阈值**：最高置信子集 37→16 **只重合 9 (24%)**（掉出 28 / 新增 7；四分类：重合 9、掉出但仍在 357 共 22、掉出且离开 357 共 6、新增 7，恒等式 9+28=37、9+7=16 交付前自检）；A 级清单 336→357 只重合 **159 (47%)**。**≥90% 可 find-replace；50–90% 必须随件交差异清单；<50% 禁止 find-replace**（清单文件必须一起换，否则「交出去的清单」与正文对不上）。
>
> ⚠️ **由此得出的 claim 铁律**：**口径稳健性 <50% 的实体名单（最高置信子集、核心元件清单）只能作「实施例输出」，不得写成权要的技术效果断言**——名单换一次输入就换掉一半，「本发明筛出 N 个元件构成 XX 轴」这类效果句随时会被自己的数据推翻。**claim 压方法层（四步 + w 门控 + 置换定阈值：两版逐字稳定、双实现互证），效果层的「保守集 / 可替代清单」必须降级或撤掉。**
>
> 🔴 **判定这条铁律是否适用：查「是否阈值边界集合」（threshold-boundary set，2026-09-12 定性概念）**——两个可实测判据同时成立即判定成立：① **新旧名单交集率 <50%**（本例 37→16 重合 24%、336→357 重合 47%）；② **变化侧效应量缩水 ≥15%**（本例 `|Z_monkey|` 中位 6.346→5.098 = **−19.7%**，而 `|Z_human|` 15.381→15.381 = **Δ0.000 零位移**）。机制 = 小样本侧效应量整体缩水，把元件从 `|Z_m|≥12` / `p_m<0.05` 门槛的一侧挤到另一侧——**换血不是「结论变了」，是「阈值上的站位重排」**。⇒ 真实的生物学类别不会因换一次小样本导出就换掉一半成员；一旦判定为阈值边界集合，**该名单的 claim 资格立即归零**（只能进实施例，禁进权项技术效果句），无需再逐条争辩成员是否合理。完整配方见 `cross-species-cre-conservation` 的 `references/caliber-switch-impact-attribution.md`（第四刀 + 数字来源依赖表）。
>
> ⚠️ **引用检验数字前先锁定来源文件**：同一结论在不同产出上会有 ±5 个实体残差——**锚定表** `P3_L1_data/M2_repro_gene_conservation_all.csv` 实算 `|Z_h|≥12`=**1409** / 同向=**582**（= A22.3 交付件采用的分母）/ 猴侧显著不分方向=**894** / 同向:反向=**357:537** / 实测÷随机符号期望=**0.80×**；**管线** `b1_gate_null.py` 产出 **1404 / 581 / 890 / 357:533 / 0.79×**（null 449.7±14.8，z=−6.27）。**结论一致（同向为亏损、非富集），但两组数字不能在同一份材料里混用**——用户对「数字老是变」零容忍，同一结论报出两组数字会被当成新的漂移。交付件（A22.3）采用锚定表口径。

> 🔴 **输入口径溯源方法（交付数字被质疑「你改过数据 / 别人无法复现」时必读）** → 见 `cross-species-atac-conservation` 的 `references/input-convention-provenance-and-version-swap.md`：血缘三问（同一计算 vs 两次独立计算 / 哪一版逐位复现交付表 / 差异在数据还是在实现）、**零差异自证法**（用用户手上的原始输入现场重算目标文件，报 max\|Δ\|≈1e-16 机器精度 + 行数 + 零硬编码脚本路径 + 耗时，让用户可自行复跑——比任何辩解有力）、换口径的**裁剪原则**（纯筛选类指标如「\|Z_h\|≥12 + p_m<0.05 + 同向」不必重跑管线，直接在新表套同一公式）、交付件三件套（产物 + 生成脚本 + 输入 md5；中间文件命名**禁带 `fix`/`repair`/`corrected`**，否则被审阅者直接读成「人工改过」）。

> 🔴 **端到端流水线交付规范（2026-09-11 用户终极质问\"你修改了脚本，为什么不能直接用脚本生成出来呢？不然人家复现，还要修正一下吗？\"）**：分析/复现交付**禁止以\"多版本分散脚本\"形态给出**——历史上\"每次修复只改被点名的文件/那一步\"导致版本并存、口径不同、数字对不上，用户拿到的是一堆要自己拼装的脚本。**铁律**：① 用户拍板输入（如\"用 M2 的 monkey_ageDA_all 完成分析\"）后，**立即固化成一条端到端流水线脚本**（M2→M7 单文件：输入路径写死为已确认版本 → 内置全部历史修复点：divideN=FALSE、坐标修复公式、Stouffer 聚合、方向门控、置换、分级、富集 → 输出全部核心数字 + REPRO_SUMMARY.md 对账报告），任何人 clone 下来一行命令跑完、零手动修正；② 流水线必须**内置输入身份自检**（行数 + 首行坐标 + MD5，与专利正本比对，不一致即报错提示），把\"哪份是正本\"的判断从人工前移进脚本；③ **列名必须与磁盘文件核对后写死**（2026-09-11 反面案例：基因坐标表列名是 `human_gene_id`，脚本写 `gene_id` → 运行时 KeyError，打断整条执行）；④ 交付后验证：`pipeline_out/` 是否真有产出文件（空目录 = 脚本启动过但没跑完，禁止声称\"已生成\"）；⑤ 依赖只写标准库（pandas/numpy/scipy），注释标明专利公式出处，别人可复核；⑥ 用户问\"下一步怎么走\"时给出 pipeline 阶段图（M1→M2→M3→…M7 当前在哪一步、输入输出是什么），不要嘴说\"我接着写脚本\"。

**docx 生成环境提示**：`python-docx` 在本机 `execute_python` 持久内核和项目 `.venv` 均未安装，但**系统 Python（`C:/Users/23136/AppData/Local/Programs/Python/Python312/python.exe`）已装 docx 1.2.0**——生成交底书/报告 docx 时用系统 Python 直接跑脚本，无需安装。

> 🔴 **docx 生成后必须读回核对（2026-09-10 实锤，比附图硬伤更致命）**：生成 docx 后**禁止只确认"文件大小正常"就声称完成**——可先跑 `scripts/verify_disclosure_docx.py <docx路径>` 自动检查公式/图片/数字/年龄/引用 5 项，再人工读回全文核对——必须读回 docx 全文（`python -c "from docx import Document; ..."` 打印每段），与源文件逐项核对：① 公式名称和表达式是否与 `disclosure.md`/`disclosure_substitutability.md` 一致（Fisher Z vs Stouffer Z 是最常见错误）；② 核心数字（336/37/537/89%/12.5×）是否与源文件一致且口径统一；③ 核心元件定义是否与最新版源文件一致（口径可能已收紧）。2026-09-10 实际翻车：Agent 生成 v3 docx 后直接交付，用户质疑"你确定能代表整个专利吗"时才发现正文公式写错（Fisher Z 应为 Stouffer Z）+ 口径冲突（336 vs 37 两套门槛并存）。根因 = 生成 docx 时凭对话记忆而非源文件，且生成后未读回核对。

- **外部专利老师审查 → 落实流程（2026-09-10 v6 定稿）**：用户（或用户贴的专利老师）给出逐条审查意见后，实现流程必须是：① 先 `execute_python` 读真实数据文件（`v5_substitutability_all.csv`）**逐条核实审查意见引用的每个数字**（537 候选=人侧\|Z_h\|≥12 且 same_direction；336 核心=其中 p_monkey<0.05；201/537=37.4%=方向不可判定被 w=0 剔除；富集 12.51×=336/(537×0.05)；37 最高置信=双侧\|Z\|≥12+同向）——核实吻合才动手，禁止拿审查意见的数字直接当事实写；② 产出**新版本 docx（v3→v4→v5→v6）**，绝不原地改旧文件，版本号递增、脚本存 `scripts/gen_disclosure_docx_vN.py`；③ 生成后 `python -c "from docx import Document ..."` 读回验证每个修改点落地（检查被删字符串计数=0、新增关键词存在）；④ 若旧版被 Word 打开存在 `~$` 锁文件，改输出新文件名（v6=技术交底书_已填写_附图版_v6.docx，644KB，4图+2表）。
- **专利老师审查"五件套"（行级编辑审查清单）**：① **术语定义**：核心概念（如"可替代"）必须在开头定义 = 方向一致性，明确排除（效应量外推/功能等效/生理替代），全文评分术语二选一（"可替代性评分 S" vs "跨物种同向保守评分 S"）不混用；② **弱信号侧门控可靠性**：小样本侧方向门控（猴 p<0.05）必须有实测证据证明门控在工作——201/537=37.4% 方向不可判定被剔除 + 富集检验证明保留的 336 非随机；③ **阈值关系写死**：τ_A 是空分布高分位、\|Z\|≥12 是实施例观测落点，写明"分布阈值—观测值"关系防 A26.4 "阈值确定方式不清楚"；④ **富集倍数分母保守口径**：5% 是单侧 p<0.05 保守估计（若计入随机方向 50% 则期望 2.5%、富集约 25×——刻意用保守的 5% 堵"方向约束夸大富集"质疑）；⑤ **区别特征+协同效果对照表**（现有技术各自缺什么→本方法补什么→协同量化效果，直接给代理人引用）+ **独权/从权框架表**（防 A25：窗口化—聚合—置换全绑定真实数据）。

- **🔴 版本迭代评估流程（v5→v6 增量审查，2026-09-10 实锤，与上面"落实流程"是同一循环的另一半）**：用户改版后再交"你再评估一下"时，流程与输出结构必须固定：① `read_file` 读新版全文（docx 自动提取）；② 逐条对照上一轮审查意见做**落实核查表**（意见 → vN 落实位置 → 质量评价"满分/超预期/不到位"）——落实质量要分级，代理人最怕"补了字但没补证据"；③ **🔴 附图版本比对铁律：解包新旧两个 docx 的 `word/media/`，逐文件 MD5 对比**——用户说"改了新版"≠附图真的换了。2026-09-10 实证：v6 与 v5 的 4 张图 MD5 全部相同（171779/166549/216338/105298 字节级一致），只有文字更新，导致"图1 五框 vs 正文四步骤"图-文矛盾原样保留。判断附图是否真更新，MD5 对比比 OCR 快且铁证；④ 输出裁决（Strong Accept / Accept with Revisions，借 idea-evaluator 框架落到专利语境）+ 遗留问题清单（按优先级 🔴🟡🟢）。**版本迭代自检四坑**：a) 旧数字残留——上一轮已把"24 倍"改成"24.3 倍"后，必须全文 grep（正文/图说/表）确认没有漏改（v6 第 39 行仍残留"24 倍"）；b) 子集/额外歧义——"另有 37 个"（37 是 336 的子集）必须写"其中 37 个"，"另有"会让律师/审查员误读为额外集合（A26.4 清楚性）；c) 随机对照表述要先写清假设——"随机替换猴侧 p 值 → 命中数跌回 26.9"必须注明"保留方向只换 p 值"；若同时打乱方向期望跌到 537×50%×5%≈13.4，不写清会被审查员算出这笔账（保守口径反而穿帮）；d) 离散年龄组的相关计算口径——猴 4 梯度（4/4/6/6）如何算"随年龄 Pearson r"（各猴实际年龄值 vs 组均值）必须写明，实施例审查必问此项；
e) 图注与正文同步修改（2026-09-10 v7 实锤）——正文步骤表述改动后（如"四步骤（第二步含'效应量计算'与'非对称评分'两个子环节）"），**图 1 图注必须同步为四步①②③④结构**，否则图文矛盾只是从"5 框 vs 四步"换成"四步 vs 旧图注"；改版时正文、图注、表格三方都要过一遍；
f) 外部审查意见中的图断言须 OCR 核实再采纳（2026-09-10 v7 实证）——另一个 AI 断言"图 1 仍是 5 个流程框"，但本会话 OCR 实测图 1 实际为 4 框（误判）。收到外部审查说"图上有几个框/几个元素"时必须先 Vision/OCR 核实图的实际内容再决定是否重画；若图框数与正文表述确实不一致，**优先改正文表述对齐图**（或同步更新图），不要因为外部断言就盲目重画成它说的框数。
g) **评估闭环门禁：评估≠自动改版（2026-09-10 v6→v7 实践）**——交付评估裁决+遗留问题清单后，**停在该轮，不自动产出下一版、不自动重画图**。给用户三选一菜单：① 出下一版修遗留 ② 收尾归档 ③ 有其他调整一并纳入。用户确认才动手产出 vN+1。MD5 证实附图未换 = 在遗留清单里报告"图未更新"并等用户决定是否重画，禁止擅自按外部断言或自行判断重画。
h) **跨轮次图断言自校验（2026-09-10 v7 实锤，连自己的上一轮也不能信）**：前几轮判定"图1 是 5 框 vs 正文四步骤矛盾"——本会话 OCR 复核实测图 1 实际为 **4 框**，历史误判。教训：图结构断言（几个框/几列/几个元素）**一旦进入跨轮次传播就必须每轮 OCR 复核一次**，无论来自外部 AI 断言（见 f）还是自己之前轮次的结论——误判会随轮次固化，甚至被当作后续修改的依据。另外 **OCR 盲区标注**：小字号下标（`|Z₁|` vs `|Zl|`）OCR 无法区分数字 1 与字母 l，凡结论依赖下标渲染的，必须标"需人工打开确认"，禁止断言。OCR 对"框数量/大布局"可靠，对"小字/下标/公式细节"不可靠。
i) **图未换的三条出路（不要默认重画）**：MD5 证明附图未更新时，按成本从低到高选：① **改正文+图注兼容实际图**（v7 成功案例：正文写"四步骤（第二步含效应量计算与非对称评分两个子环节）"、图注加"[第二步两个子环节]"注释 → 四步表述与 4 框实际图语义兼容，硬矛盾消除，不再阻塞提交）；② 若发现图内标号与图注编号**错位一格**（v7 案例：框内 ②效应量计算/③非对称评分/④置换 vs 图注 ②合并/③置换/④分级），重画时把图内标号改为与图注一致——这是第②类图文一致性检查，跟"框数量一致"是两码事；③ 真重画。正文能兼容就不重画，省一轮交付。
j) **可证伪对照实验 = 教科书级真实性验证写法（v7 值得抄的防御）**：证明"门控保留的是真信号而非随机"，用三档对照而不是口头论证：随机替换 p 值（保留方向）→ 命中跌回 26.9；同时打乱方向 → 537×50%×5%≈13.4；真实命中 336。三档数字自洽可验，审查员无法用"随机过滤"质疑门控。配套 c) 的要求：每档对照的假设（换了什么/保留了什么）必须写透，防止保守口径穿帮。评审时遇到"验证全是论据没有对照组"的写法，主动建议补此三档。

- **🔴 交底书形式要件四件（2026-09-12 v14→v15 第三轮，用户点名"这几个也做一下"）**——**形式补全轮不动技术方案、不动口径数字**，只补：
  ① **附图必须黑白线条版**：审查指南第一部分第一章 2.4"应当使用制图工具和黑色墨水绘制……不得着色"。另建 `patent/figures_bw/` 由独立脚本重出（线型/影线/空心·实心替代颜色），docx 生成器 `FIG` 常量指向它；**校验靠实测**——PIL 数彩色像素 = **0.000%** + 解包 `word/media/*` 与 `figures_bw/` 源图**字节数逐个相等**（复用"图文一致性二期"的字节比对法）。彩色版另存供答辩 PPT、不随申请提交。⚠️ **合规 ≠ 可读**：黑白线条版常靠影线区分系列，但**填充图案（点纹/斜纹/交叉纹）缩印后退化成灰块**——用户会直接说「一堆小点点，看不清」。**单链流程图的方框图案纯冗余，删掉改纯白底黑框 + 反白标题条**；影线只保留在「必须用图案代替颜色」的多系列对比图上。详见下方「图文一致性铁律**四期**」+ `references/print-legibility-and-figure-refresh.md`
  ② **摘要附图必须显式指定**（"摘要附图：图 X" + 理由，惯例选技术链/流程图）；全文 grep"摘要附图"零命中 = 没指定。
  ③ **检索记录三件套**：中文/英文/分类号三组检索式 + IPC/CPC 建议分类号（**只写主组级**如 G16B 40/00，**子组留代理人按最新版核定**）+ 对比文件 D1–D3 对照表（D1/D2 取说明书 §四（补充）已点名的现有技术不另创，D3 取公认方法族，无文献对应的公知做法编号留"—"）。末尾加"本交底书不替代正式检索报告"。
  ④ **数字限定语写全**：本次"猴侧方向可信的 **894** 个元件"实为**主体侧强效应池（1,409）内**的数（缺限定语会被读成全基因组口径，全库实为 **7,651**，差 8.6 倍）。写任何计数前问"**分母是什么**"，子集条件必须同句写出。
- **🔴 纸面从权体检 + 用实跑补实施例（2026-09-12，用户点名"权 5 / 权 10 实施例、权 12 支撑力"）**：逐条从权问"它的每个特征说明书里有实施例落点吗"，无落点 = **纸面从权**。本次三处缺口与补法：权 5(2) **同源对应关系置换**（**实跑** 200 次：打乱跨物种同源配对、保持边缘分布不变）→ 一正两负结果**全部写入**并绑定权项原文用途词"**校准**门控与 τ"（⇒ 负结果与权项自洽、反成方法层证据）；权 10 下游用途 → 用途一/二实测、用途三标"实施方式（未执行）"；权 12 → 补配对 z + 明写规模边界（`|z̄|≥1.5` 档仅 8 单元，规模化应取 ≥1.0～1.2 档）。**铁律：用实跑补实施例，不用文字补**——文字补的实施例经不起审查员追问数字。⚠️ 只披露对主体侧有利的置换、不披露参考侧负结果 = **选择性披露风险**（本次审查意见 N2 即此项：审查员问"参考侧年龄效应本身的证据呢"时无话可答）。
- **版本迭代三件套（改版 ≠ 手改 docx）**：① 生成器 `cp` 上一版后**只 spot-patch 变更点**（docstring/版本行/输出路径/图名/新增节/CHANGELOG），**不重写 43KB 生成器**；② **独立验收探针**读回 docx 断言——表数·图数 + 必备串 + **陈旧串零命中**（上一版版本号/脚本名/旧图名/旧图数"共 12 步"/旧措辞原句，这是抓"改了一半"的唯一有效手段）+ 口径数字不变 + 内嵌图字节比对 + 摘要字数（本次 **48 PASS / 0 FAIL**）；③ 一个脚本集中同步交付 md 的版本标识与指向（**断言 `count>=1` 再替换**，幂等可续跑）+ **同步 `run_all.sh` 复现链**（本次新增 [C3.5] 黑白附图 / [C3.6] 同源置换 / [C4] 成文 / [C5] 验收 / [C6] md 同步），否则复现链与交付件脱节。收尾还要扫"现行版指向"残留（`现行版为 v1x` / `请以 v1x 为准` / `配套交底书：…v1x.docx` / `附图（与交底书 v1x 同源）`）到零命中。
- **🟡 L1 裁决 need_more_info 的处置（2026-09-12）**：形式/支撑类改动也会触发辩论提醒。裁判 missing 分两类——**可当场自补的立刻补进交付件**（随机种子 + 脚本路径 = 可复现细节；率类 Wilson 95%CI），**超出 Agent 职责的转成"送代理前待办"**（审查指南/判例法律锚点、门控 τ 的训练/验证划分与预注册、阳性对照、多重检验 FDR、权项-说明书映射稿）。⛔ 不要为"让辩论好看"把法律判断自己写进交底书（裁判明确指出"把本案数据外推到 A26.3/A26.4/创造性但无审查指南锚点，属推理"）。
- 完整配方（黑白附图校验、检索记录/分类号写法、纸面从权体检表、同源置换代码模板与两面结果写法、Wilson CI、版本迭代三件套、探针断言清单）→ `references/disclosure-form-requirements-and-claim-embodiment-completion.md`

---

## 12. claim 效果层三铁律：先证伪门禁 / 循环论证分母 / 粒度层选择

> 来源：跨物种衰老可替代性专利（memomics-7839e23a，2026-09-12）。三件事都在同一份专利上实锤，且**都不是数据问题，是判定流程问题**。

### 12.1 🔴 先证伪门禁：前提检验必须排在所有数字工作之前

**症状（用户原话）**：「为什么一直在变呢？到底是什么问题，导致你一直在变？」
连续 5 轮口径替换（continuous→all→复核→再切 all→重算 v5/v6/v7）**全在执行层，0 轮在判断层**——把一条能推翻 claim 的前提检验（参考物种侧方向门控 p<0.05 到底可不可信）判成了 🟡 **建议级**，流程因此没拦截它；一跑，claim 效果层当场塌。

| 判据 | 定级 |
|---|---|
| 该检验的结论是「前提成立/不成立」 | 🔴 阻断，**排在一切数字工作之前** |
| 该检验只是「加分项/优化空间」 | 🟡 建议 |

- **单向漂移 = 收敛信号**：连续多轮检验**每轮都让 claim 变弱、从没变强** → 不是噪声/摇摆，是收敛到「claim 不成立」。此时立刻停止补丁式修补，改做正面判定。
- **汇报纪律**：报「更新后 claim 更强还是更弱」，不是报「数字已更新」。前者是判断，后者只是执行——用户要的是前者。
- **答案模板**：「不是之前可以、现在要改；是之前我把一条致命问题判成了建议级，所以它没拦住流程。」——把定级错误说成定级错误，不要说成数据反复无常。

### 12.2 🔴 循环论证分母：一切「富集 N×」先验分子分母条件独立

本文档 §11「专利老师审查五件套」曾把「富集 12.51× = 336/(537×0.05)」当保守口径解释——**2026-09-12 修正：该分母含方向条件，构成循环论证**。

- 分母 = 「人侧 \|Z₁\|≥12 **且同向**」的候选数（582 / continuous 版 536）；分子 = 同向元件数 ⇒ **方向条件在分子分母同现**，倍数恒 >1，等于自己证明自己。
- **检查法（30 秒）**：把分母筛选条件逐条写出，问「这条条件在分子里也出现吗？」出现 → 循环。
- **零假设比例必须实测**：专利写「噪声下显著率 5%」，实测参考物种侧 p<0.05 比例 = **63.4%**（错 12.7 倍）。
- **修法二选一**：① 换独立分母（只用「人侧 \|Z₁\|≥τ 全集」，不含方向条件）；② 直接报**率**（同向率 40.1%，随机基准 50% 明确、不可循环）；③ **换成三基线横评**（推荐，2026-09-12 v10 实做）。
- ⚠️ 冲突条款：本条**覆盖** §11 中「用 5% 是保守口径没问题」的旧表述；生成交底书时若仍在用该分母，必须重算或删除。
- 🔴 **删掉富集倍数之后拿什么顶上 → 三基线横评**（2026-09-12 v10 已实做）：按「**反向混入率 + 精度 + 召回**」三元组横评本方法与三种现有做法（① 两队列各自筛选取交集 ② 合并 Z 做 meta ③ 单物种筛选）。实测本方法 357 输出 / **0 反向混入** / 精度 100% / 召回 25.3%，对称 min 法 16 / 0 / 100% / **1.1%**（⇒ **22.2 倍**），不设方向门控的取交集 894 / **537 反向（60.1%）**。两个指标都能被审查员独立复算、分母不含被检验条件。含 6 条设计规则（召回仅在**同精度**方法间比、**mask 内含被检验量会自证循环**、matched base-rate 解析方差避免 OOM）+ A22.4 实用性答辩口径 + 「**验收尺子**」警告（方法专利的尺子是「有没有增量」，不是「生物学结论是否为真」——本会话 Agent 用错尺子导致多轮反复、用户不满）→ `references/three-baseline-evaluation-harness.md`

### 12.3 🔴 阈值边界集合：逐字段一致率是「变异来源探针」

本文档已给阈值边界集合判据（新旧名单交集率 <50% + 变化侧效应量缩水 ≥15%）。补充**反向用途**——逐字段一致率用来**定位变异来源**：

| 模式 | 判读 |
|---|---|
| 单侧 100% 一致、另侧 0% 一致 | 换的是**单侧输入表**（本例人侧 159/159 r=1.0000；猴侧 0/159 r=0.8842） |
| 两侧都大面积不等 | 换的是**实现层** |

据此可把「换口径影响面」分侧回答，而不是笼统说「数字变了」。

### 12.4 🔴 粒度层选择：同一 claim 命题在不同粒度层结论可相反

同一「跨物种可替代性」命题，本例两层给出**相反**答案：

| 粒度层 | 指标 | 结果 |
|---|---|---|
| 元件层（500bp tile / 基因锚定 Z） | 同向率 40.1% | ❌ 低于随机 50% |
| 细胞类型层（snATAC 聚类比例） | Astro ↓、OPC ↓ **两物种都显著** | ✅ 正向一致 |

机制：元件级被 ① 500bp 窗口噪声 ② 数十万次多重检验 ③ 个体异质性 三重稀释；细胞类型级聚合把噪声平均掉。

**规则**：定 claim 落点前，先横向比较候选粒度层的统计性质（效应量、多重检验负担、聚合单元数），**不要默认压在最细的那一层**。「在哪一层谈可替代性」本身是可辩护的技术选择，写进说明书可同时回应 A26.4 清楚性与 A22.3 技术效果。

### 12.5 claim 两级判定的操作顺序

判定 claim 该不该改时，**分两层独立问**（否则结论含糊）：

1. **方法层**：「能不能做出来」→ 步骤链可实施？双实现互证？→ 本例 ✅（锚定器 16,029 × 管线 16,010 同结论）
2. **效果层**：「做出来是什么/有什么用」→ 技术效果句、定性词、用途句是否被实测支撑？→ 本例 ❌（同向率 40.1% < 随机）

**改 claim 只动效果层**（权利要求效果句 + 摘要 + 有益效果段 + 用途权要），**方法步骤链一字不改**。凡由被否前提派生的数字（富集倍数、「保守」定性词、整体替代声称）必须一起改掉。

### 12.6 完整配方

→ 见 `cross-species-atac-conservation` 的 `references/claim-premise-precheck-and-circularity-traps.md`（六条铁律 + 动手前 6 项检查清单）。

### 12.7 🔴 自己的论文也是现有技术：权项必须落在论文未披露的步骤上

论文一旦 online（**含 bioRxiv 预印本**），申请人自己的公开即构成现有技术 ⇒ "专利 vs 论文"的分界**不是"谁先做"，而是权项步骤链里有没有论文没写的那一环**。论文只用硬阈值判定时，"二维经验贝叶斯五态 + local FDR"这类**判定引擎本身**就是论文未披露的增量 → 独权支点。

**评估方法建议的正确标尺**：权项过的是"**有没有增量**（新颖性/创造性）"，不是"能不能得出生物学结论"——用后者当唯一标尺会误杀有新颖性价值的方案（本次 Agent 自犯并自行更正：先按"能否出结论"给 EB 方案打低分，后修正为"它救的不是信号，是新颖性"）。汇报时把**科学轴 / 专利轴分开讲**，不要混成一句"这个方案没用"。

**✅ 实测已补（2026-09-12，用户追问「你确定你用了这个方法了吗？二维经验贝叶斯五态判定 + local FDR……之前的 z 不用了吗？」）**——不要停在"这是个候选支点"的推演层，**先把"到底用没用"查实、再真跑一遍**：

| 问题 | 实测答案 |
|---|---|
| 交付件里有没有这个方法？ | **没有**。grep **三层**（正文 md / **docx 表格与正文** / 内嵌图像素）零命中 ⇒ 独权动词链里根本没有经验贝叶斯 / lfdr / 五态，只剩 `Z₁`（强度，\|Z₁\|≥12=τ_A）+ `w(Z₂)`（只给方向）+ 全局置换阈值 τ。**回答"用没用过"前必须先查三层，禁止凭印象**——本次首答只 grep 了 md/py，补扫 docx 正文才算完整取证（docx 是 zip，读 `word/document.xml`；`~$xxx.docx` 锁文件不是 zip 且 mtime 最新，`sorted(glob)[-1]` 必中它）。 |
| 真把 EB+lfdr 跑起来呢？ | 5.8 s 跑通（16,010 元件）→ 五态 A 同向 **106** / B 反向 **168** / C 单侧 2,528 / D 证据不足 146 / E 无信号 13,062；双侧过阈 420 中同号仅 **37.1%**，符号置换 **z=−5.33**。 |
| 结论 | **EB+lfdr 救的是「新颖性 + 逐元件误差控制」**（lfdr 不依赖那条被否的循环分母），**救不了效果层**（同向仍少于反向）——与 §12.1/12.2 的独立判定一致，构成第 3 条互证。 |
| 附带发现（更要紧） | 经验零假设 σ_human = **4.86**（不是 1）⇒ 文档里的 `\|Z₁\|≥12` 只相当于 **2.25 个经验 σ**（双侧 p≈0.024），"高置信"字样缺统计依据；Z 标定本身存疑（疑因：p 用的 n 是供体数还是 tile/细胞数）。**阈值要先在经验零假设下标定，再写进说明书。** |

**动作纪律**：这类探针属**只读可行性评估**，**禁止在用户拍板前**把结果写进权项/交付件；必须给**并列选项**（①补实现进权项 ②删需求那句维持现状 ③先查 Z 标定），并说明倾向理由。完整配方（docx 三层取证两个坑 + 经验零假设标定 + lfdr 四步实现 + 五态表）→ `cross-species-cre-conservation` 的 `references/empirical-null-and-lfdr-probe.md` + `scripts/ebayes_lfdr_probe.py` + `scripts/grep_docx_text.py`。

### 12.8 🔴 宽限期只有三种情形：期刊发表与预印本都不在内

《专利法》第 24 条六个月宽限期**仅**适用：① 中国政府主办或承认的国际展览会**首次展出** ② **规定的学术会议**首次发表 ③ **他人未经同意**泄露。

⛔ **期刊论文（含 Nature/Science 系列）与 bioRxiv/medRxiv 预印本均不在其列** ⇒ "尽快申请"的真实时限 = **论文上线之前**，不是"发表后 6 个月内"。提示时间风险时**必须说准**，笼统说"有宽限期"会直接导致错过窗口。
→ 完整判读表 + 配套时限机制（同日提交 / 优先权 12 个月 / 优先审查）→ `references/paper-publication-vs-patent-novelty.md`

### 12.9 🔴 交付件「介绍/宣讲」类问题的回答规程（2026-09-12 用户实问「能跟我解释一下当前这个专利吗？介绍」）

用户会反复问「介绍下这个专利 / 讲讲我们的专利 / 答辩时我怎么说」——这**不是**读一遍交付件复述，而是一次**带裁决的介绍**。规程：

**① 先读最新裁决，再读交付件。** 顺序固定：`task_plan.md`（看最新 Phase 是否有晚于交付件的结论）→ 交付目录 `README.md` / `结论_口径决策链.md` / `全流程溯源档案.md`。**交付件版本号高 ≠ 它的结论最新**——本案 README 标 v10、写满 357 口径数字，但 Phase 6 已否证效果层前提；只读 README 会把已倒的结论当卖点讲出去。

**② ⛔ 禁止照抄交付件里的自荐式表述。** 交付件（尤其 README / A22.3 / 摘要）的写法天然偏自荐（本案原句：「本方法是唯一在保持 100% 精度同时把反向混入率压到 0 的做法」「召回 25.3% vs 对称 min 法 1.1%」）。这些句子在**内部**是论据，搬去做**对外介绍**时必须按最新裁决加限定——本案该论证的分母已含分子条件（循环论证），符号置换零假设 z=−6.27 判同向为**亏损**而非富集。**介绍 = 陈述 + 状态 + 风险，不等于宣传。**

**③ 固定五段结构**（本案实测一次讲清）：
1. **一句话定位**——方法专利还是发现专利？保护的是哪一步？（本案：保护「怎么判定元件能否跨物种替代」的流程，不是「发现了共享衰老程序」这个结论）
2. **流程图**（`mermaid` flowchart，S1→S5 步骤链 + 样本量 + 关键阈值，节点内嵌数字）
3. **核心数字**（`keyvalue`/短表：输入口径 / 网格规模 / 双实现互证 / 阈值 / 核心元件数 / 一致性 ρ）
4. **⚠️ 当前真实状态——两层判定**（方法层 ✅ / 效果层 ❌ + 否证依据 3–4 条 + 辩论裁决 + **对申请的具体影响**：哪些权项能写、哪段说明书必须改中性口径）。**这段是介绍的核心价值**，缺了它介绍就是误导
5. **交付件清单 + 下一步选项**（让用户选：改效果段为中性口径 / 出修订版 / 收尾归档）

**④ 渲染纪律：长 `dsh-ui` JSON 会被截断。** 本案实际翻车：一次回复内塞了含多个长字符串组件的 `dsh-ui` 围栏，输出在 JSON 中途被切断（`…召回仅 1.1%（16/1409` 处断），整块降级为坏代码块、回答看起来是坏的。规则：**一个 `dsh-ui` 围栏 ≤3 个紧凑组件、单围栏 JSON ≈1500 字符内；流程/架构图一律用独立 ```mermaid 围栏（零 JSON 风险）；内容多就拆成多个小围栏分开发。**

### 12.10 🔴 评审/核查结论的交付规程 + 数字回盘铁律（2026-09-13 用户实锤）

用户原话：**「所以结论是什么呢？我看了你一大堆东西，结论呢？说那么多有什么用呢？下一步的解决方案呢？」**
——这是**交付形态**问题，不是内容问题。专利评审 / 数字核查 / 口径复核类回合一律按下面四段式交付，**顺序不可换**：

| 段 | 内容 | 篇幅 |
|---|---|---|
| ① 结论 | ≤3 句：什么成立 / 什么不成立 / 哪句话被写宽了 | 1 段 |
| ② 判据 | 撑住结论的**最小**证据集（一张 ≤6 行表，逐行可指到文件） | 1 张表 |
| ③ 能守 / 不能守 | 双列：主张 → ✅守 / ❌弃 → 一句依据 | 1 张表 |
| ④ 下一步方案 | **3–5 条编号**，每条写「动作 → 产出物」 | ≤5 行 |

⛔ 禁止：把推理链、历轮口径演变、工具调用过程写进结论段；禁止只给「已核查/已完成」而不给可执行的下一步；④ 末尾**必须**用一句话问用户选哪条（不要留开放结尾）。
（与用户既有偏好一致：「下一步怎么办」类问题只给 3–5 条简洁编号列表，不要长篇方案/表格/文献清单。）

**🔴 数字回盘铁律（2026-09-13 Agent 自犯并当场自纠）**：结论里出现的**每一个数字**，本轮必须能指到**具体文件 + 具体列**；本轮没回盘到源的数字**一律不得以陈述句出现**——要么当场读文件回盘，要么显式标注「本轮未回盘，待核」。

- 实例：同一份结论里同时引用了已核数字（`concordance=0.4781` / `z=+1.83`，来自刚读的 `pertile_gate_sweep.csv`）与**六项未回盘数字**（`39.93%` / `p=1.9e-9` / `exp_rate 0.4459·0.4377·0.4289` / `0.23×` / `p=0.815` / `p=0.164`）——后者不在该文件里，本轮亦未在其余 results 文件中定位。
- **发现即当场撤回并声明「请先允许我回盘再动笔」**，不要因为「上轮说过」就默认它仍成立；更不要为了结论完整而把未回盘数字写成事实。
- 判据一句话：**「这个数字我这一轮是从哪个文件的哪一列读到的？」答不上来 → 不许写进结论。**
- 同族铁律：本文档「引用检验数字前先锁定来源文件」「结论稳定性：局部验证通过 ≠ 全局结论正确」。

**给结论时先自查「用户会据此动手吗」**：凡结论要用户拿去改权项 / 改交付件 / 拍板口径 → 数字门槛提到最高（全部回盘）；纯方向性讨论可放宽，但仍须标注来源。

→ 逐档 z 复现表、条件零假设口径、`z>0 ≠ 同向率>50%` 的反例、未回盘清单与待查文件表：`references/z-statistic-and-conditional-null-audit.md`

### 12.11 🔴 效应量变换分层：先定"单元统计量是什么"，再谈改哪个（2026-09-13 外部统计评审实锤）

**用户（以领域统计专家身份）指出 claim 里三个统计量被混用**，并给了正确的判定框架：
"若单元统计量**是相关系数** → Fisher-Z 变换再 Stouffer 合并，背书成立；
若单元统计量**是回归 t/z** → **Fisher-Z 根本不适用**，应改用 p 截断/对数域 或 逆方差加权。"

| 量 | 输入 | 层次 | 适用 |
|---|---|---|---|
| **Fisher-Z** `atanh(r)·√(n−3)` | **相关系数 r** | **单元层**（效应量方差稳定变换） | 单元统计量是相关性时可用 |
| **p 反推 z** `sign(r)·Φ⁻¹(1−p/2)` | **p 值** | 单元层 | 单元统计量是 p 时可用，但**该换的不是 Fisher-Z** |
| **Stouffer 合并** `Σzᵢ/√n` | 各单元 z | **聚合层** | 标准做法 |
| **Stouffer + 有效自由度** `Σzᵢ/√(n(1+(n−1)ρ))` | 各单元 z + ρ | **聚合方差层** | 单元间自相关时的正确形式 |

**🔴 命名纪律（写进权项前必查）**：`ΣZᵢ/√n` **本身就是 Stouffer 合并**；有效自由度修正是**聚合方差层**的事
⇒ 准确命名 **"Stouffer + 有效自由度"**。⛔ **不要把"Fisher-Z"与"n_eff 校正"并列写成一条从属权**
（如"权 2 增加 Fisher-Z 变体"）——层次不同，混写 = 在权项里写一个统计上不成立的表述。
✅ **拆成两条独立从属权**：`权 2a` 单元层 Fisher-Z（n = **供体数**，`|r|` winsorize 0.999）；
`权 2b` 聚合方差层 Stouffer + 有效自由度（ρ 估计法写明）。

**判定程序（做任何"改公式"动作之前必走）**：**第一步不是讨论公式，是去磁盘确认锚定单元的统计量到底是什么。**
本案实读：`claims.md` 权 2 原文写"进行 **Pearson 相关分析**，得到相关系数 r 与双侧显著性 p"
+ `06_repro_full_pipeline.py` L219 `np.sign(r)*norm_ppf(1-p/2.0)` ⇒ 单元统计量 = r ⇒ **分支①（Fisher-Z 适用）**。

**"p 机器零饱和"要实测，不要当理论担忧说**：本案 `M2_..._all.csv`（16,029 基因）人侧基因级 p 落机器 eps 占 **19.07%**、
猴侧 2.10%；脚本 `p=max(p,1e-300)` **只防下溢、不恢复信息** ⇒ `atanh(r)` 不依赖 p 分辨率是其实质价值。

**Fisher-Z 落地参数**：`zᵢ = atanh(rᵢ)·√(n_donor−3)`（n 是**供体数**不是 tile 数；人 40→√37=6.08、猴 20→√17=4.12，均满足 n≥4）。

### 12.12 🔴 冗余参数预注册：跑校正实验之前必须冻结（否则结论"调到能通过"）

凡校正/调参类实验依赖一个**估计出来的**冗余参数（如 ρ），该参数的估计方法**本身是可调自由度** ⇒
存在"调到能通过"的嫌疑，是审查员与无效宣告最会咬的地方。**跑前写死，跑后禁改**：

| 路 | 方法 | 地位 |
|---|---|---|
| **路 A** 变异函数核（拟合 `ρ(d)=exp(−d/λ)`，λ 由数据决定） | **无自由参数** | 🔴 **主口径来源** |
| **路 B** 空间块置换（B ∈ 1/5/25/100kb） | 四档**全报** | 敏感性分析 |

⛔ 禁止跑完后换块大小/换 λ/换阈值/换主口径；只报最好一档。
⚠️ **本案 Agent 自犯并自纠**：草案里预设 `B=5kb` 当主口径，被 L1 裁决否掉（"5kb 需独立依据，若无依据主口径应待定"）
⇒ 撤销，主口径改为由 λ（数据）决定。**教训：主口径不该由 agent 挑一个数**；物理锚点只用于事后合理性检查。
另必须报**影响量曲线**（ρ 0→1 时目标指标随 n_eff 的响应 + 与 50% 的交点），不只报单一数字——
否则无法区分"校正有效"与"ρ 调到刚好"。

**阳性/阴性对照三件（缺一不可）**：同物种拆分半样本（**≥65%**）/ 同侧 bootstrap / 年龄标签置换（**50%±2%**）。
🔴 **阳性对照未达 ≥65% ⇒ 流水线本身失能，校正实验结果无解释力，不得用于改写权项**。
方向一致率报**分位数分布**（P10–P90）不只报均值；均值异常先查是否被少数超大元件驱动（去掉 top 1% 后倍数是否仍 >2）。

### 12.13 🔴 改定位的取舍 + 外部专家评审意见的吸收规程（2026-09-13）

**改定位 = 拿新颖性换安全性，但别把商业价值一起换掉**：只写"校正手段" ⇒ 保护范围缩水成"一个统计校正方法"，
换一种校正即设计绕过。✅ **命题 = 偏置校正；技术效果 = 输出可替代性判定** —— 独权必须**同时含两个限定**，
技术效果作为**用途限定留在独权里**，不降级为应用场景。

**创造性论证不能只"罗列差异"**：D2 已有"局部背景校正"、D1 已有"跨物种对齐"、D5 已有"统一表示" ⇒
审查员最可能走"显然组合"。必须写出**为什么组合不显然**的四点抗辩链（手段维度不同 / D2 完全不碰空间结构 /
D1 的对齐 ≠ 统一网格（不含效应量）/ 组合无技术启示），并把非显而易见的**三点写死**（统一网格下的按粒度分层、
有效自由度对空间自相关的校正、主-参考非对称方向门控）。

**外部专家评审意见的吸收规程**（用户以审查员身份给逐条意见时）：
① 回应形态 = **逐条判定表**（意见 → 判定 → 落地位置），不写散文式复述；
② **每条判定先做实证闭合** —— 能当场用磁盘证据判定的（如"单元统计量到底是什么"）先去读文件再表态，
不要凭印象说"接受/不适用"；
③ 产出**新版本草案文件**（v18→v19），⛔ **不覆盖旧版本**（保留便于对照）；
④ **裁决可以否掉自己草案里的预设** —— 接受并**显式写"撤销"**，不要悄悄改掉；
⑤ 剩余项分两类：可当场自补的立刻补，超 agent 职责的转"**送代理前待办**"
（⛔ 不要为"让评审好看"把法律/程序判断自己写进交底书）。

→ 完整配方（三量对照表、分支判定程序、Fisher-Z 参数表、冻结协议模板、三对照设计、抗辩链模板）：
`references/effect-size-transform-layering-and-preregistration.md`
（与 `z-statistic-and-conditional-null-audit.md` 分工：那份管**零假设口径与 z 复现**，这份管**变换层归属与跑前预注册**）

### 12.14 🔴 不翻转只收敛：上提前先查现行 claims 是否已覆盖（2026-09-13 v20 定案）

**触发**：agent 连续两轮（v18/v19）打算把某两件东西「上提为独权核心」（分层背景校正 / 粒度归一化），用户一句定案：
「**不做定位翻转，只做收敛——因为 v18/v19 想上提为独权核心的两件东西，v15 其实早就写好了。**」

| 问 | 判据（用工具，不凭印象） | 本案 |
|---|---|---|
| ① 拟上提之物现行 claims 里有吗 | 逐条回读 `claims.md` **独权 + 从权原文** | 「分层背景校正」= 独权 **S1.5** + 权 **11**（层内匹配基准率）；「粒度归一化」= 权 **12**（`z̄=Z/√n`，已有 +3.85/+3.09/+3.27）⇒ **早已写好** |
| ② 真新的才吸收 | 只并入「现行确实没有的」 | 仅 3 件：Fisher-Z 单元变换（→权 2）、五件专利对比（→交底书 §十）、§2.5 抗辩链（→A22.3） |
| ③ 上提的代价 | 问「命题会不会被换掉、范围会不会缩水」 | 会（漂成「一个统计校正方法」，换种校正即绕过）⇒ **独权/权 11/权 12 一字不动** |

**三条必须同时执行的统计判定**（不做，v20 只是把 v19 的错误藏起来）：

1. **符号保持的操作改不动方向一致率** —— 任何**正均匀缩放**（如 `Z/√(1+(n−1)ρ)`）**保持符号** ⇒ 基因级同向率**精确不变**；n_eff 只能改**显著性**不能改**率**。⇒ 用 n_eff 救「同向率 < 50%」数学上不可能（**本条修正 v19 草案「校正后同向率回到 ~50%」的错误声称**）。
2. **但删除理由必须写全，不能写「无意义」** —— 完整理由 = **置换零假设（S4）已在经验层面吸收单元间相关性、直接给出零分布 ⇒ n_eff 冗余**。写「无意义」→ 审查员问「那你的 z 显著性靠什么？」；写「由置换零假设接管」→ 问不出来。
3. **阈值型筛选对变换敏感 ⇒ 换变换必须重标定 τ** —— 分级是 `S=Z₁×w(Z₂)` 在 **|Z₁| 量级**上过阈 τ_A，而 Fisher-Z（`atanh` 有界）与 p 反推 z（p→0 无界）**不是同一量级** ⇒ 过阈集合会变。**「预期基本不变」不得假定**；复跑须**在新口径下重新标定 τ_A**（沿用旧 τ_A ≠ 同口径对照）；变化了就是变化了，作为「效应量口径敏感性」合法披露。
   ⚠️ 连带：**权 12 的解析 z 三档 + 「删除 n_eff」= 同一说明书两套口径**；修法零成本——权 12 结构一字不动，只把三档改为**置换校准口径**。

**🔴 写「读 X 目录的协变量」之前先把 X 目录列出来**：本案计划第一优先动作是混杂溯源「读 M2 协变量」，实测扫 `E:/专利/M2`（可见 60 个文件）= `FIX_v10/` 各阶段 + `pipeline_out*` **全是计算产物，无样本表/供体年龄/批次/细胞组成/死亡间隔** ⇒ 该步必须回**上游样本表**（GEO 元数据 / source h5ad 的 `obs`），照计划写步骤会直接落空。**判「该实验能不能做」前先列输入目录。**

→ 完整配方（三问决策表、三判定推导、τ 重标定流程、混杂溯源前置核查、执行纪律自检清单）：`references/claim-promotion-vs-convergence.md`

## Proven Scripts

> Auto-generated from actual analysis runs. Each row records a successful execution.

| 物种 | 组织 | 方向 | 日期 | 脚本 | auto | user | ✔ |
|------|------|------|------|------|------|------|----|
| human | hippocampus | aging | 2026-09-12 | 16_gen_disclosure_docx_v15.py | - | - |  |
| human | hippocampus | aging | 2026-09-12 | 15_make_figures_bw.py | - | - |  |
| human+macaque | hippocampus | aging | 2026-09-13 | verify_fisherz_branch.py | - | - |  |
