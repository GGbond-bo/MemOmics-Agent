# Patent Angles: Cross-Species CRE Conservation Assessment

## Patent Title Candidates

1. **方法专利**: 一种跨物种脑组织基因调控元件保守性的定量评估方法
2. **系统专利**: 一种跨物种基因调控元件可代替性评估系统
3. **存储介质**: 一种计算机可读存储介质（存储CRECS程序）
4. **应用专利**: 一种基于跨物种CRE保守性评分的神经药物筛选方法

## Core Invention Points (for independent claims)

### Point 1: CRECS Composite Scoring System
**Claim scope**: A method comprising obtaining ATAC-seq data for two species; identifying orthologous CRE pairs via reciprocal LiftOver; calculating sequence/epigenetic/3D/functional conservation scores; computing a weighted composite score (CRECS); outputting a four-tier classification.

**Why patentable**: No existing method integrates sequence + epigenetic + 3D + functional dimensions with weighted scoring for brain-specific CREs.

### Point 2: Reciprocal LiftOver CRE Pairing with Dual Validation
**Claim scope**: Converting CRE coordinates bidirectionally (species A→B and B→A); requiring reciprocal overlap ≥50% AND sequence similarity ≥70% to confirm orthology.

**Why patentable**: Existing methods use unidirectional LiftOver with no sequence validation, leading to false orthology calls.

### Point 3: Cell-Type-Resolution Substitutability Atlas
**Claim scope**: Computing cell-type-specific CRECS scores; generating a brain-region × cell-type × substitutability-grade matrix; outputting per-cell-type A/B/C/D classifications.

**Why patentable**: Converts bulk CRE comparison to actionable cell-type-level guidance.

### Point 4: GWAS Cross-Validation Layer
**Claim scope**: Validating CRECS scores by intersecting CRE classifications with human brain-disease GWAS loci; expecting Grade A CREs to be enriched at disease-associated regions in relevant cell types.

**Why patentable**: Independent validation that ties the computational method to human disease relevance.

## A25 Defense (Intellectual Activity Rules)

| A25 Risk Factor | Defense |
|----------------|---------|
| "Abstract mathematical method" | CRECS is a technical measurement tied to specific physical data (ATAC-seq, ChIP-seq) — it measures real molecular properties, not abstract rules |
| "Mental act" | Requires computer processing of high-throughput sequencing data (cannot be done mentally) |
| "Presentation of information" | Output is a technical classification for drug development, not mere information display |
| "Computer program as such" | Tied to specific hardware (sequencing instruments) and produces a technical effect (improved model selection for drug screening) |

### Safe Anchors to Include in Claims
1. "Data is a physical measurement result" — explicitly state ATAC-seq/ChIP-seq are physical analyses of chromatin
2. "Clear industrial application" — drug screening model selection, reducing false positives in preclinical trials
3. "Error detection capability" — validation layer (evolutionary anchors + negative controls) demonstrates the method can detect when it's wrong

## Differentiation from Closest Prior Art

| Prior Work | What They Did | Why Not Anticipating |
|-----------|---------------|---------------------|
| Johansen 2025 Cell Genomics | Evaluated enhancer *prediction methods* | Evaluates methods, not conservation; no composite score |
| Keough 2023 Science | HARs 3D genome remodeling | Descriptive, no quantitative assessment framework |
| Meng 2026 Nat Commun | Monkey cortex CRE atlas | Atlas building, no cross-species comparison method |
| Sarropoulos 2026 Science | Mammalian cerebellum regulatory evolution | Evolutionary description, no substitutability framework |

**Bottom line**: All prior work either (a) builds CRE atlases, (b) describes evolutionary patterns, or (c) evaluates prediction tools. None provides a quantitative, multi-dimensional, cell-type-resolved assessment framework for determining substitutability.

## Patent Strategy Recommendation

Two patents filed same day (防抵触):
- **Patent A** (核心方法): CRECS assessment method + system + storage medium
- **Patent C** (应用): Drug screening method using CRECS to filter cross-species-conserved targets

Timeline: ~3 months to filing (school only needs acceptance notice).
