---
name: cross-species-regulatory-conservation
description: >
  Cross-species gene regulatory element conservation assessment (CRCA) framework.
  Five-layer evaluation: R1 sequence conservation → R2 CRE chromatin accessibility
  (ATAC-driven) → R3 TF binding dynamics (ATAC-driven footprinting) → R4 TF→target
  regulatory network conservation (SCENIC + pseudobulk + mixed model) → R5 integrated
  scoring with data-driven weights. Core innovation: B-class gene detection
  (expression conserved but regulation divergent). Includes BNIP3 gold-standard
  validation design, dual R environment setup (R 4.4.x + R 4.6.x for ArchR),
  and patent claim architecture guidance for cross-species methods.
trigger_keywords:
  - "跨物种调控元件"
  - "CRCA"
  - "调控保守性"
  - "B类基因"
  - "BNIP3验证"
  - "CRE保守性"
  - "TF footprinting跨物种"
  - "regulatory conservation"
  - "cross-species regulatory"
  - "基因调控元件保守性"
  - "调控元件可代替性"
  - "CRECS"
  - "ArchR跨物种"
version: 1.0.0
author: MemOmics
metadata:
  hermes:
    category: GWAS/Genetics
---

# Cross-Species Regulatory Element Conservation Assessment (CRCA)

## Overview

This skill covers the **five-layer CRCA framework** for evaluating whether a gene's regulatory
program is conserved between species — going beyond expression-level comparison to answer:
"is the monkey model's gene regulation sufficiently similar to human for drug target validation?"

**Core insight**: Expression conservation ≠ regulatory conservation. The POU5F1 case from
CroCoNet (2025 preprint) proves this — identical mRNA levels but maximally divergent TF
driver networks. This framework is the first to systematically detect such "B-class genes."

---

## Five-Layer Framework

### R1: Sequence Conservation Layer (no ATAC needed)

```
Input: Genome sequences (GRCh38 + rheMac10) + JASPAR motifs
Methods:
  - Promoter extraction (TSS ±2kb) for 1:1 orthologs
  - liftOver coordinate mapping
  - phastCons/phyloP conservation scoring
  - TF motif scanning (JASPAR): presence/absence, position, copy number
Output: S_seq — per-gene sequence conservation score
```

### R2: CRE Chromatin Accessibility Layer (ATAC-driven)

```
Input: Cross-species ATAC-seq (monkey + human hippocampus)
Methods:
  - Peak calling (MACS2 via Signac/ArchR)
  - liftOver peak coordinates (rheMac10 → hg38)
  - R2a: Peak overlap rate (Jaccard index, bp-level)
  - R2b: Signal intensity correlation (Spearman ρ per peak)
  - R2c: Cell-type specificity conservation (same CRE open in same cell type?)
  - R2d: Aging dynamics — species×age interaction on CRE accessibility change
Output: S_cre — per-gene CRE accessibility conservation score

ArchR advantage over Signac: co-accessibility analysis
(can detect enhancer-promoter linkage conservation — Signac cannot).
```

### R3: TF Binding Dynamics Layer (ATAC-driven)

```
Input: Cross-species ATAC-seq
Methods:
  - TF footprinting (TOBIAS/HINT-ATAC or Signac Footprint)
  - Motif enrichment in age-varying CREs
  - Cross-species comparison of footprint depth/specificity
Output: S_tf — TF binding conservation score
```

### R4: Regulatory Network Conservation Layer (Gene-centric)

```
Input: Cross-species scRNA-seq (monkey + human hippocampus)
Methods:
  - R4a: SCENIC/GRNBoost2 per species → TF→target edge set
         Check: ortholog TF→ortholog target edge exists in other species?
  - R4b: Regulon activity aging dynamics
         pseudobulk per-individual aggregation
         → cos(θ) aging trajectory similarity
         → mixed-effects model: species + age_scaled + species:age_scaled + (1|individual)
  - R4c: Cross-validate with R2 CRE + R3 footprint evidence
Output: S_edge (topology) + S_dyn (aging dynamics)
```

### R5: Integrated Scoring Layer

```
CRECS = data-driven weighted integration of R1-R4
  - Weights determined by logistic regression on evolutionary anchor calibration set
  - Training labels: known conserved vs divergent CREs from cross-species literature
  - Model must be interpretable (logistic regression, not RF/XGBoost/neural net)

A/B/C/D classification:
  A (≥0.75): Regulation fully conserved — monkey model reliable for this gene
  B (0.50-0.75): Expression conserved but regulation DIVERGENT — HIDDEN BOMB, exclude
  C (0.25-0.50): Regulation conserved but expression divergent — use with calibration
  D (<0.25): Both divergent — exclude

B-class genes are the method's killer innovation:
  - Invisible to all existing expression-level replaceability methods
  - Primary cause of drug target translation failure
  - First method that systematically detects them
```

---

## BNIP3 Gold Standard Validation

BNIP3 is the ideal validation case because its upstream regulatory network is well-characterized:

**Known gold standard TF→BNIP3 relationships:**
- HIF-1α → BNIP3: HRE site at -94bp, human-mouse conserved (proven since 2007)
- E2F1 → BNIP3: E2F binding site at -155bp, human-mouse conserved
- FOXO3 → BNIP3: ChIP-validated direct binding
- p53, NF-κB p65 → BNIP3: inhibitory regulation

**Validation workflow (all dry-lab):**
1. R1: Check HRE and E2F motifs in monkey BNIP3 promoter (liftover + phastCons)
2. R2: Check BNIP3 promoter CRE accessibility conservation (human vs monkey ATAC)
3. R4: SCENIC recovery of HIF1A→BNIP3, E2F1→BNIP3, FOXO3→BNIP3 edges in both species
4. R4b: HIF-1α regulon aging trajectory — cos(θ) + species×age interaction

**Expected**: BNIP3 should score A-class (all layers confirm conservation).
**Negative control**: Pick a known primate-divergent gene (e.g., from CroCoNet's POU5F1 module)
and show the method correctly classifies it as B-class.

---

## Data Requirements

| Data | Species | Source | Status | Layer |
|------|---------|--------|:------:|-------|
| scRNA-seq | Monkey hippocampus | User's data | ✅ | R4 |
| scRNA-seq | Human hippocampus | GSE278576 | ⬜ | R4 |
| ATAC-seq | Monkey hippocampus | User's data | ✅ | R2, R3 |
| ATAC-seq | Human hippocampus | ENCODE | ⬜ | R2, R3 |
| Genome + liftOver | Human + macaque | UCSC | ✅ | R1 |
| phastCons/phyloP | Primates | UCSC | ✅ | R1 |
| JASPAR motifs | — | JASPAR | ✅ | R1, R3 |
| Public brain cCREs | Human + macaque | ENCODE + macaque brain atlas | ✅ | R1 |

---

## Dual R Environment Setup (Windows)

ArchR requires R ≥ 4.5.0. Keep existing R 4.4.x for Seurat/Signac/SCENIC.

```
R 4.4.2 (default): Seurat, Signac, SCENIC, CellChat, monocle3
R 4.6.1 (ArchR): ArchR + Bioconductor dependencies

Installation:
  1. Download R from CRAN → install to C:\Program Files\R\R-4.6.1\
  2. Install ArchR: "C:/Program Files/R/R-4.6.1/bin/Rscript.exe" install_archr.R
  3. Call: "C:/Program Files/R/R-4.6.1/bin/Rscript.exe" archr_atac.R

Cross-environment: output rds/h5 from ArchR → read by Seurat/Signac (R 4.4.2)
Orchestration: Python subprocess calls both Rscript versions, filesystem as bridge.
```

---

## Patent Claim Architecture

### Independent Claim (regulation-centric)

> 一种跨物种基因调控保守性评估方法，其特征在于包括：
> (a) 序列调控元件保守性层(R1)，计算启动子区域序列保守性和转录因子结合位点保守性；
> (b) 染色质可及性保守性层(R2)，基于跨物种ATAC-seq数据比较峰值重叠率和信号强度相关性；
> (c) 转录因子结合动态保守性层(R3)，基于TF足迹分析比较跨物种结合模式；
> (d) 转录因子-靶基因调控关系保守性层(R4)，比较跨物种基因调控网络的边保守性和衰老动态轨迹保守性；
> (e) 整合R1-R4得分，通过数据驱动方法确定权重，生成综合调控保守性评分；
> (f) 按预设阈值将基因分类为调控保守(A)、表达保守但调控分歧(B)、调控保守但表达分歧(C)、均分歧(D)。

### Dependent claims (layered):

- R4b pseudobulk + mixed model (species×age interaction as core statistical innovation)
- Data-driven weight calibration via evolutionary anchors (logistic regression)
- B-class gene detection as the distinguishing feature from all prior art
- BNIP3-type gold standard validation procedure
- ATAC optional layers (from dependent claims: "in embodiments where ATAC-seq is available...")
- Co-accessibility analysis via ArchR (dependent claim)

### Relationship to original Patent A (expression-level replaceability)

Two patents, same-day filing:
- **Patent A′** (this one): Regulation-centric — "the machine is the same?"
- **Patent A** (original): Expression-centric — "the output is the same?"
- Shared core: pseudobulk + mixed model + species×age + A/B/C/D classification
- Differentiated claims: A′ adds R1-R3 layers; A focuses on expression variance decomposition

---

## Key References

- CroCoNet (2025 preprint): POU5F1 as proof that expression conservation ≠ regulatory conservation
- Keough 2023 Science (PMID: 37104599): HARs 3D genome reorganization
- Meng 2026 Nat Commun: Macaque cortex cis-regulatory element atlas
- BNIP3 literature: HIF-1α HRE site characterization (2007 onwards)

---

## Common Pitfalls

| Pitfall | Consequence | Solution |
|---------|------------|----------|
| Comparing cells instead of individuals | Pseudoreplication, inflated significance | Always pseudobulk per individual before cross-species comparison |
| Using species-specific motif databases | Artificial asymmetry in R1/R3 | Use JASPAR human motifs for both species (forward search) |
| Fixed weights in claims | A25 rejection | Claim the calibration method, not the weight values |
| Black-box model for weights | Insufficient disclosure | Use logistic regression; RF/XGBoost in dependent claims only |
| No negative control in validation | Weakens method credibility | Always include one known-divergent gene alongside BNIP3 |
| ATAC cross-species comparison without cell-type matching | Confounded by cell composition | Match by conserved cell-type labels before CRE conservation comparison |
---

## ⛔ Terminal 完成后强制协议（铁律 26）

```
1. rail_review(phase='post')
2. debate_analysis(
     topic="ATAC-seq 分析 —— {样本}",
     context="方法: {ArchR/Signac} | 参数: {peak calling参数} | 结果: {n} peaks {m} motifs",
     knowledge_base_info=<KB内容>,
   )
   辩论: peak质量如何？FRiP分数？motif富集合理吗？与RNA数据一致吗？
3. save_conclusions(module="03_advanced", topic="ATAC", ...)
4. skill_evolution(action="record_run")
5. 更新 task_plan.md
```
