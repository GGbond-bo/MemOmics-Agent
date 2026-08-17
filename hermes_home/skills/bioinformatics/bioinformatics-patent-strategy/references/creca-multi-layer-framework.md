# CRECA: Cross-Species Regulatory Element Conservation Assessment

> v1.0 — 2026-07-28 — extracted from Kimi K3 + MemOmics synthesis session
> Framework for patenting multi-layer regulatory conservation assessment methods

## Key Insight

"Expression conservation ≠ Regulatory conservation" — a gene can have identical expression levels across species but be driven by completely different transcription factors and regulatory elements. This makes B-class gene detection the single most powerful differentiator for regulatory conservation patents.

## Five-Layer Framework Summary

| Layer | Name | Data Required | Key Methods |
|-------|------|--------------|-------------|
| R1 | Sequence Conservation | Genome sequences (public) | liftover, phastCons, JASPAR motif scan |
| R2 | CRE Accessibility Conservation | ATAC-seq (both species) | Peak overlap (Jaccard), signal Spearman ρ, cell-type specificity, aging dynamics (mixed model) |
| R3 | TF Binding Dynamics | ATAC-seq (both species) | TOBIAS/HINT-ATAC footprinting, chromVAR, binding intensity × species×age interaction |
| R4 | TF→Target Network Conservation | scRNA-seq (both species) | SCENIC regulon edge conservation, regulon activity aging trajectory (cos(θ) + species×age) |
| R5 | Integrated Scoring | All above | Logistic regression weight calibration, A/B/C/D classification |

## B-Class Gene: The Patent Gold

B-class genes: expression conserved (would fool all existing methods), but regulatory drivers completely divergent. CroCoNet (2025) proved POU5F1 is a real B-class gene in primate neural differentiation.

**Patent narrative**: "现有方法对某一类关键基因系统性失明——这些基因的表达水平跨物种高度一致，但上游调控程序完全不同。本发明第一次提供了系统检出这类基因的方法。"

## BNIP3 Validation Template

BNIP3 is the ideal validation case:
- Known gold standard: HIF-1α→BNIP3 (HRE -94bp), E2F1→BNIP3 (-155bp), FOXO3→BNIP3, p53/NF-κB→BNIP3
- Human-mouse verified conserved, but human-macaque NEVER compared → new finding opportunity
- Four-step validation: R1 (sequence) → R2/R3 (ATAC+footprint) → R4 (SCENIC edge recovery) → R4b (aging dynamics)
- One positive (BNIP3, expected A-class) + one negative (known divergent gene, expected B/D-class)

## A′ + C Sister Patent Architecture

- A′: Regulatory conservation assessment (R1→R2→R3→R4→R5, A/B/C/D classification)
- C: Anti-aging compound screening (cross-species conservative signature + reversal score + D-class exclusion)
- Weld point: D-class exclusion list from A′ feeds into C
- Same-day filing

## Data Requirements

| Data | Species | Source | Status | Used In |
|------|---------|--------|:---:|---------|
| scRNA-seq | Monkey hippocampus | User's data | ✅ | R4 |
| ATAC-seq | Monkey hippocampus | User's data | ✅ | R2, R3 |
| scRNA-seq | Human hippocampus | GSE278576 | ⬜ | R4 |
| ATAC-seq | Human hippocampus | ENCODE | ⬜ | R2, R3 |
| Genome + liftover | Human + Macaque | UCSC | ✅ | R1 |
| JASPAR motifs | — | JASPAR 2024 | ✅ | R1, R3 |
| Public brain cCREs | Human + Macaque | ENCODE + macaque brain atlas | ✅ | R1 |

## Key Claim Patterns

**Independent claim (draft)**:
```
S1(R1): 对1:1直系同源基因启动子区进行序列保守性分析
S2(R2): 获取两物种ATAC-seq数据，比较染色质可及性保守性
S3(R3): 基于ATAC-seq进行TF足迹分析，比较结合模式保守性
S4(R4): 基于scRNA-seq构建基因调控网络，比较TF-靶基因关系保守性
S5(R5): 加权整合S1-S4得分，生成CRECS评分，按A/B/C/D四级分类
       其中B级为表达保守但调控分歧的基因
```

**Weight-dependent claim**:
```
"权重系数通过进化锚点校准方法确定：
 (a) 选取至少三对已知进化距离的物种对
 (b) 收集已知保守/不保守调控元件作为训练集
 (c) 以各维度得分为特征、保守性为标签，训练逻辑回归模型
 (d) 回归系数归一化作为权重系数"
```

## 3-Month Sprint Timeline

| Week | Task | Deliverable |
|------|------|------------|
| 1-2 | Download human ATAC+scRNA, set up ArchR | Unified data format |
| 3-4 | R1 sequence + R2 ATAC conservation | Per-layer scores |
| 5-6 | R3 TF footprint + R4 SCENIC networks | Cross-species integration |
| 7-8 | R5 weight training + A/B/C/D + BNIP3 validation | B-class gene list |
| 9-12 | Write 2 交底书, internal review, submit | 受理通知书 |
