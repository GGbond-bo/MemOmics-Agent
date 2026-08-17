# CUT&Tag Bioinformatics Analysis — Literature Survey

> 📅 2026-07-14 | 来源: PubMed/Europe PMC 文献搜索
> 用途: 未来创建 CUT&Tag skill 时的参考基准

## 核心文献

| # | 文献 | 期刊 | PMID | 核心价值 |
|---|------|------|------|----------|
| 1 | Cheng et al. 2024 — "Review and Evaluate the Bioinformatics Analysis Strategies of ATAC-seq and CUT&Tag Data" | *Genomics Proteomics Bioinformatics* | 39255248 | 🔥 最直接参考: 系统比较 ATAC/CUT&Tag 所有分析策略 |
| 2 | Yashar et al. 2022 — "GoPeaks: histone modification peak calling for CUT&Tag" | *Genome Biology* | 35788238 | CUT&Tag 专用 peak caller |
| 3 | Abbasova et al. 2025 — "CUT&Tag recovers up to half of ENCODE ChIP-seq histone acetylation peaks" | *Nature Communications* | 40148272 | CUT&Tag vs ChIP-seq 验证 |
| 4 | Janssens et al. 2024 — "Scalable single-cell profiling of chromatin modifications with sciCUT&Tag" | *Nature Protocols* | 37935964 | scCUT&Tag 协议 |

## 行业标准工具链

```
FastQ → Bowtie2 → SEACR/GoPeaks → ChIPseeker/HOMER → deepTools → DiffBind
```

| 步骤 | 首选工具 | 备选 | 说明 |
|------|----------|------|------|
| **比对** | **Bowtie2** | BWA | CUT&Tag 短片段(~150bp)最优 |
| **Peak calling** | **SEACR** (通用) / **GoPeaks** (组蛋白) | MACS2 `--nomodel` | SEACR 是 Henikoff 实验室开发, CUT&Tag 原始协议自带 |
| **注释** | **ChIPseeker** (R) / **HOMER annotatePeaks** | — | 基因组区域注释 |
| **可视化** | **deepTools** (bamCoverage→computeMatrix→plotHeatmap) | IGV | 热图/剖面图 |
| **Motif** | **HOMER findMotifsGenome** | MEME-ChIP | 转录因子结合位点 |
| **差异分析** | **DiffBind** (R) | DESeq2 直接对 count | 多样本 peak 差异 |

## CUT&Tag vs ChIP-seq 关键差异

| | ChIP-seq | CUT&Tag |
|---|---|---|
| **背景噪声** | 高 (需要 input) | 极低 (Tn5 靶向) |
| **Peak caller** | MACS2 默认 | **SEACR** / **GoPeaks** |
| **Input control** | ✅ 必须 | ❌ 不需要 (IgG 替代) |
| **FRiP 预期** | 5-20% | **20-60%** |
| **QC** | ENCODE 标准 | Henikoff lab 协议 |

## 拟创建 Skill 需包含的工具

```
Bowtie2, samtools, bedtools, SEACR, GoPeaks, deepTools,
ChIPseeker (R), HOMER, DiffBind (R), DESeq2 (R)
```

## Skill 覆盖步骤

1. FastQ QC (FastQC)
2. Bowtie2 比对 → BAM
3. BAM 处理 (samtools sort/index, markdup)
4. SEACR peak calling (broad/narrow)
5. GoPeaks (组蛋白标记备选)
6. FRiP + TSS enrichment QC
7. ChIPseeker 注释 (promoter/exon/intron/intergenic)
8. deepTools 可视化 (bigWig, heatmap, profile)
9. HOMER motif enrichment
10. DiffBind 差异 peak (多样本)
