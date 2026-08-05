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
- 技术要点: R 4.5.3 + E:/R-libs/R-4.5.3 库；MACS2 不可用 → 用 TileMatrix (500bp) 替代；
  JASPAR2020 (非 2024) + GC-matched 背景 + score fold-change 排名 (Fisher 对 48 tiles 无统计效力)
- 猴基因组: **Macaca fascicularis 食蟹猴 T2T-MFA8v1.1**（NCBI nuccore NC_088375.1 确认；
  非 Macaca mulatta 恒河猴！21 chr NC_088375.1–NC_088395.1, ~3.04GB），需手动建 genomeAnnotation。
  跨物种 chain 必须用 fascicularis T2T-MFA8v1.1 → hg38，不能用 rheMac10 (mulatta)。

### 人侧 ⏳ 下载中（用户手动下载, 阻塞点）
- **选定数据集: GSE278576** (Science 2026, "Epigenetic and 3D genome reprogramming
  during aging of human hippocampus") — 40 ATAC + 40 RNA 样本, 40 独立供体, 4 年龄组 (20-40/40-60/60-80/80-100)
- 文件: fragments.tsv.gz + .tbi.gz 可直喂 ArchR createArrowFiles()（无需 bam）
- 命名模式: GSM8549615_hc77_atac_fragments.tsv.gz
- **下载进度: 9/40 已下** (hc77/hc78/hc5579/hc76/hc29/hc6052/hc5614/hc13344/hc935)
- **⚠️ 9 个已下样本全部在 20-38 岁 Young 组**（Table_S1: 20/20/25/26/28/28/31/33/38）→
  无老年样本 → 对比流程跑通但 FDR 全空（预期结果，无统计力）
- 下载目录: E:/专利/Human_Hippocampus_ATAC/fragments/
- 官方脚本克隆: E:/专利/Human_Hippocampus_ATAC/official_scripts/aging_human_hippocampus-main/
- 论文+补充材料: E:/专利/Human_Hippocampus_ATAC/papers/
- ⚠️ 带宽 ~6KB/s → Agent 无法自动下载, 必须用户手动下载

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
