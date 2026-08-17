# GSE278576 论文官方分析管线（人海马衰老 ATAC 对比流程）

> 来源：2026-08-04 用户要求"找这篇论文的对比流程/方法"实战提取。
> Zemke NR, Lee S, Mamde S, et al. "Epigenetic and 3D genome reprogramming during
> the aging of human hippocampus". Science 2026-07-23, PMID 42490474,
> DOI 10.1126/science.adt8307; bioRxiv 2024-10-17, PMID 39463924.
> 通讯：Bing Ren (UCSD) + Xiangmin Xu (UCI)。数据 = GSE278576（用户已下载 fragments）。

## 数据概况

- 40 海马供体 × 2 平台 = 80 samples
- 10x Multiome (snRNA + snATAC) → 295,033 nuclei
- snm3C-seq (DNA methylome + 3D genome) → 22,240 nuclei
- 4 年龄组: 20-40 / 40-60 / 60-80 / 80-100（跨成年全生命周期）
- 39/40 donors 两平台匹配；WashU Browser: https://epigenome.wustl.edu/seahorse/

## ATAC 处理管线（用户 fragments 数据的官方流程）

```
40 donors 海马 → 10x Multiome (ATAC+GEX) → NextSeq2000 质控 → NovaSeq6000 深测 (~50K reads/cell/模态)
→ cellranger-arc v2.0.0 (hg38 GRCh38 + GENCODE v32)
→ QC: ≥500 ATAC fragments, ≥200 genes, <20% MT RNA, >5 TSS enrichment (SnapATAC2)
→ SCTransform (2000 HVG) → DoubletFinder (每样本去 top 10% doublet score)
→ rPCA 批次校正 (跨 40 donors) → kNN (PC 1:30) → Leiden 聚类 → UMAP
→ 注释: marker genes + reference mapping (Seurat) → 18 亚类
→ Peak calling: MACS2 每细胞类型 × 5 个 peak 集 (全部40供体 + 4年龄组各一)
   macs2 callpeak --shift -75 --ext 150 --bdg -q 0.1 -B -SPMR --call-summits -f BAMPE
→ SPM (score-per-million) ≥ 4 保留 → union 合并 → 500bp 统一 → 去 ENCODE blacklist → bedtools intersect
→ 每细胞类型 cCRE 集合
```

## 年龄对比核心方法（⚠️ 连续年龄相关，非 Young/Old 分组）

- 指标: pseudobulk CPM (log2 CPM+1) vs donor age；DMR 用 mCG fraction
- 过滤: 基因总 counts ≥ 2×剩余供体数（供体 RNA counts ≥ 20,000）；cCRE 供体平均 ≥1 count/cCRE
- 统计: Pearson correlation → FDR 校正, **FDR < 0.1** 判为年龄相关
- 验证: shuffle 供体表达值生成零分布（Fig 3B 密度图）
- 差异 cCRE (Astro1 vs Astro2): Signac 推荐 **logistic regression**, donor 作 latent variable, 10% 细胞可及, p-adj < 0.01
- 差异基因 (Micro1 vs Micro2): **MAST**, age 作 latent variable, p-adj < 0.0001
- TF motif: **HOMER** (FDR<0.1, 背景=该细胞类型可及 peaks)；单细胞 TF activity: **chromVAR**
- 增强子预测: **ABC model** (Hi-C 10kb + ATAC + cCRE, ABC ≥ 0.02) → 36,275 远端增强子 → 14,135 基因
- GO: GSEApy + clusterProfiler；DMR→基因: GREAT
- 3D genome: scHicluster (compartment/TAD) + dcHiC (差异 compartment, Mahalanobis + FDR<0.05)
- 甲基化 clock: Horvath 353 CpG + pyaging (KNN imputation)
- 形态学: LME (MATLAB fitlme) 校正重复测量

## 关键发现（生物学）

1. 星形胶质细胞随年龄下降最显著 (PCC = -0.68, p=1.1e-6)；OPC、内皮细胞也下降
2. 微胶质从稳态 Micro1 → priming 炎症态 Micro2（DNA 甲基化重编程驱动，
   MHC II 上调，HOXA 簇甲基化 PCC=0.84）
3. 衰老细胞 3D genome 结构侵蚀（TAD 减弱、trans 染色质互作增强）
4. NRF1 结合减少 → 星形胶质线粒体功能障碍 → 自噬依赖细胞死亡（机制假设）
5. ABC 增强子年龄相关可及性与其靶基因年龄相关表达显著对应

## 对用户跨物种 ATAC 专利的意义

- ✅ 该论文 = 人侧海马 ATAC 衰老谱**背景技术核心引文**
- ⚠️ 已用 pseudobulk + 连续年龄 Pearson（单物种），与专利 S320/S330 重叠
- ✅ 无跨物种 species×age 交互 → 专利核心创新（猴→人可代替性评估）仍空白
- ⚠️ 用户 fragments 目录当前仅 9/40 样本 → 做 pseudobulk 年龄相关前须确认
  供体年龄跨度够（混合效应模型需 ≥3 年龄组）

## 论文文件位置

- 预印本全文: E:/专利/Human_Hippocampus_ATAC/papers/10.1101_2024.10.14.618338.pdf
- 补充材料 M&M+FigS1-S18: E:/专利/Human_Hippocampus_ATAC/papers/suppl_media1.pdf
- 补充表 S1-S24: E:/专利/Human_Hippocampus_ATAC/papers/suppl_media2.zip
- 提取文本: paper_fulltext.txt / suppl_fulltext.txt
