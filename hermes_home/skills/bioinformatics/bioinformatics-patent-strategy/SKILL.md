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

- `references/patent-defense-wording.md` — Exact Chinese wording templates for A25 defense
- `references/claim-templates.md` — Boilerplate claim structures for bioinformatics methods
- `references/s100-s600-framework.md` — Expression-level cross-species replaceability framework (S100-S600)
- `references/creca-multi-layer-framework.md` — Regulatory-element conservation assessment framework (R1-R5 CRECA), B-class gene detection, BNIP3 validation

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
