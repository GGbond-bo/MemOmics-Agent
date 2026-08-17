# 项目状态: 猴-人海马 ATAC 跨物种 CRE 保守性评估（2026-08-04 更新）

> 会话 memomics-1c1890da 的 task_plan.md 是权威状态源。本文件给跨物种项目
> 提供数据集选择依据 + 续跑路径，避免未来 session 重新调研。

## 数据侧状态

### 猴侧 ✅ 已完成 (Phase 1-6 全部 complete, 2026-08-02 验证)
- 数据: 3 Arrow 文件 (O1_Hip_1 / Y3_Hip_1 / Y3_Hip_2), E:/专利/ArrowFiles/
- ArchR 输出: E:/专利/ArchR_Output/
  - project_raw/qc/lsi/clustered/tilemat.rds (clustered = 21 clusters, 29MB)
  - markers_age_tiles.rds (192MB) / da_tiles.rds
  - motif_enrichment_results.rds + Motif_Top_Old/Young.png + motif_rank_*.csv
  - ArchR_ATAC_Analysis_Report.html (2.5MB, base64 图全嵌入)
- 关键结论: Old:Young = 5,591:30,288 (15.6%)；C12 95.8% Old-enriched, C1 仅 Old
- Motif: Old 富集 ZFP57(FC=6.14)/CEBPB(5.28)/MLX(4.41)/VENTX(4.39)；
  Young 富集 HOXB8(8.38)/BHLHE41(3.63)/FOSL1::JUND(3.40)；PITX1/ZFP57/GBX1 两侧共享
- 技术要点: R 4.5.3 + USER_R_LIBS/R-4.5.3 库；MACS2 不可用 → 用 TileMatrix (500bp) 替代；
  JASPAR2020 (非 2024) + GC-matched 背景 + score fold-change 排名 (Fisher 对 48 tiles 无统计效力)
- 猴基因组: **Macaca fascicularis 食蟹猴 T2T-MFA8v1.1**（NCBI nuccore NC_088375.1 确认；
  非 Macaca mulatta 恒河猴！21 chr NC_088375.1–NC_088395.1, ~3.04GB），需手动建 genomeAnnotation。
  跨物种 chain 必须用 fascicularis T2T-MFA8v1.1 → hg38，不能用 rheMac10 (mulatta)。

### 人侧 ✅ 测试版 4 样本已到位（2026-08-08 更新）
- **选定数据集: GSE278576** (Science 2026, "Epigenetic and 3D genome reprogramming
  during aging of human hippocampus") — 40 ATAC + 40 RNA 样本, 40 独立供体, 4 年龄组 (20-40/40-60/60-80/80-100)
- 文件: fragments.tsv.gz + .tbi.gz 可直喂 ArchR createArrowFiles()（无需 bam）
- 命名模式: GSM8549615_hc77_atac_fragments.tsv.gz
- **40/40 全下齐 + 40/40 QC Filtered Arrow 全在**: E:/专利/Human_Hippocampus_ATAC/ArchR_Arrow_QC_Filtered/
- **测试版选定 4 样本**: hc78=20M + hc5579=25F (Young) / hc98=82F + hc9=95F (Old)
  → merge 后 35,787 cells, 17 clusters, 8 大类注释 (OPC 12032/ODC 7752/Ex 7001/Astro 4557/Micro 1661/Inh 1321/VS 887/ChP 576)
- 下载目录: E:/专利/Human_Hippocampus_ATAC/fragments/ + ArchR_Arrow_QC_Filtered/
- 官方脚本克隆: E:/专利/Human_Hippocampus_ATAC/official_scripts/aging_human_hippocampus-main/
- 论文+补充材料: E:/专利/Human_Hippocampus_ATAC/papers/

### 测试版执行状态（2026-08-08, session memomics-1c1890da）
- P0 人侧 merge+LSI+UMAP+聚类+注释 ✅ (22:18, human_proj_annotated.rds)
- P1 人侧 Young vs Old DA ✅ (22:32, PID 17648 EXIT=0)
  - strict (FDR≤0.05, |log2FC|≥0.5): **Old 2,955 / Young 563** tiles (5.2:1)
  - loose (FDR≤0.1, |log2FC|≥0.25): Old 5,037 / Young 972
  - 产出: results/memomics-1c1890da/patent_test/markers_age_tiles.rds (348MB)
    + da_tiles_strict_{Old,Young}.bed + volcano_{Young,Old}_DA.png + da_summary.csv
  - 方向: 人海马衰老打开远多于关闭 → **与猴侧一致**（交叉验证有效）
- P3 (L1/L2/L3) pending — 阻塞点见下
- **P3 L1 数据准备已启动 (22:44-22:47, E:/专利/P3_L1_data/)**: 后续会话直接从这续跑，勿重新导出
  - 猴 GTF 已下载: GCF_037993035.2_T2T-MFA8v1.1_genomic.gtf.gz (442KB)
  - 猴 DA tiles 已导出 CSV: macaque_da_strict/loose_{Old,Young}.csv (strict Old 50 行, NC_088xxx.1 500bp tile 坐标)
    - 列 schema: `seqnames, idx, start, Log2FC, FDR, MeanDiff`（idx=tile 索引, start=tile 起点坐标）→ liftover 时按 seqnames+start 映射即可
  - 脚本: download_gtf.sh / export_macaque_da.R / probe_motif.R / probe_motif2.R
- **猴 motif_enrichment_results.rds 结构已探明 (2026-08-08 22:49 probe 实测)**:
  `list(old, young, n_old, n_young, n_bg)`; old/young = data.frame **633×4** (motif | fg_mean | bg_mean | fc)，
  fc 是 fold-change 排名（GC-matched 背景）。→ P3 L3 猴侧 motif 输入直接用，无需重新探结构。

### 🔴 P3 阻塞: 食蟹猴 T2T-MFA8v1.1 → hg38 liftover chain 获取路径实测（2026-08-08）
**结论: 目前无现成 chain，需要备选方案。** 逐路径实测:
- UCSC goldenPath: `mfa8ToHg38.over.chain.gz` → **404**（UCSC 无 T2T-MFA8v1.1 组装链）
- UCSC 仅有食蟹猴旧组装: `hg38ToMacFas5.over.chain.gz`（200 OK, 但猴侧 Arrow 是 T2T 坐标，不匹配）
- UCSC 恒河猴链 `rheMac10ToHg38`（200 OK, 但 = Macaca mulatta，**禁止用于食蟹猴**）
- NCBI GRS API `api.ncbi.nlm.nih.gov/genome/remap/*` → **410 Gone / 404**（已废弃）
- NCBI Datasets v2alpha remap → 404
- UCSC genArk → 无 fascicularis 条目
- MFA8v1.1 的 NCBI accession 已确认: **GCF_037993035.2** (RefSeq reference, 22 chr, 注释 RS_2025_03)
- 备选方向（未实测）: 自建 chain（minimap2/lastz + chain 工具，需 3GB 基因组下载）、
  NCBI Remap 网页版手动提交、Ensembl 组装转换（若已收录 T2T）、或用 JASPAR motif 序列比对绕开 liftover

## 对比流程状态（2026-08-04 完成 pilot）

- **skill**: `gse278576-atac-aging-comparison`（官方复现 skill）+ `atac-paper-reproduction`（class 级 umbrella）
- **官方来源**: GitHub nrzemke/aging_human_hippocampus (Zenodo 10.5281/zenodo.19391232);
  补充材料 suppl_media1.pdf (M&M) + suppl_media2 (Tables S1-S24)
- **关键发现**: 官方 Table_S7.tsv = **472,859 个官方 cCRE 全集**（含 18 亚类归属）→
  **不需要自己 call peaks**（免装 MACS3/snapatac2，snapatac2 全版本无 Windows wheel）
- **pilot 结果**: 9 样本 15.5 亿 fragments，45.4% 落在官方 cCRE；Pearson cor 分布 -0.97~0.94；
  最小 pval 8.2e-6 → FDR 全 >0.7 无显著 cCRE（全 Young 组，统计力不足，预期）
- 产出: results/memomics-8857f1c1/gse278576_comparison/
  (cpm_matrix.tsv 90MB + all_celltypes_pcc_full.tsv 68MB + figures/)
- **等 40 样本下齐 → 同一 skill 脚本直接全量重跑（~25 分钟）**

## 续跑路径（人侧数据到齐后）

1. 核对 E:/专利/Human_Hippocampus_ATAC/fragments/ 样本数 ≥ 40（fragments + tbi 完整）
2. 人侧完整分析：fragments → 聚类 → 年龄相关 cCRE（官方 Table_S7 或自 call peaks）
3. ArchR createArrowFiles() 构建人海马 Arrow（fragments 直喂）
4. 猴-人 liftover (fascicularis T2T-MFA8v1.1 → hg38) → 三层评估:
   L1 序列保守 → L2 可及性保守 (species×age 混合效应) → L3 TF footprinting
5. A/B/C/D 四级 CRE 分类 → CRECS 综合评分（专利框架, 见 bclass-cre-detection.md）
6. ⚠️ 猴侧 3 个体不够 species×age 混合效应模型（需 ≥6 个体 × ≥3 年龄组）——专利实施例硬伤，需补数据

## 唤醒检查经验

- 任务阻塞在外部依赖（用户手动下载）时, 唤醒只做三源验证（task_plan + 产出目录 +
  process list）后如实汇报阻塞点, 不创建新 task、不自动下载、不跨 session 接管。
- 检查产出目录用 E:/专利/ArchR_Output/（rds 在专利目录, 不在 session results/ 下）。
- 用户说"对比流程"须先澄清：比对(fastq→fragments, 已完成) vs 分析(fragments→年龄相关)。
