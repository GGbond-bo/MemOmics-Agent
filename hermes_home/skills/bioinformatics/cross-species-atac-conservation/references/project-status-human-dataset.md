# 项目状态: 猴-人海马 ATAC 跨物种 CRE 保守性评估（2026-08-02 快照）

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
- 猴基因组: Macaca mulatta T2T, 21 chr NC_088375.1–NC_088395.1 (~3.04GB), 需手动建 genomeAnnotation

### 人侧 ⏳ 下载中 (用户手动下载, 阻塞点)
- **选定数据集: GSE278576** (Science 2026, "Epigenetic and 3D genome reprogramming
  during aging of human hippocampus") — 40 ATAC + 40 RNA 样本, 40 独立供体
- 文件: fragments.tsv.gz + .tbi.gz 可直喂 ArchR createArrowFiles()（无需 bam）
- 命名模式: GSM8549615_hc77_atac_fragments.tsv.gz (hc77, hc78 已就位, 2/40)
- 下载目录: E:/human_hippocampus_atac/GSE278576/
- 下载脚本已验证可用 (6项check全pass): E:/MemOmics-Agent/results/memomics-3c672f0a/
- ⚠️ 带宽 ~6KB/s → Agent 无法自动下载, 必须用户手动下载

## 续跑路径（人侧数据到齐后）

1. 核对 E:/human_hippocampus_atac/GSE278576/ 样本数 ≥ 40
2. ArchR createArrowFiles() 构建人海马 Arrow（fragments 直喂）
3. 人侧 QC → LSI → UMAP → 聚类（同猴侧参数: TSS≥4, nFrags>1000）
4. 猴-人 liftover (rheMac10 → hg38) → 三层评估:
   L1 序列保守 → L2 可及性保守 (species×age 混合效应) → L3 TF footprinting
5. A/B/C/D 四级 CRE 分类 → CRECS 综合评分（专利框架, 见 bclass-cre-detection.md）

## 唤醒检查经验

- 任务阻塞在外部依赖（用户手动下载）时, 唤醒只做三源验证（task_plan + 产出目录 +
  process list）后如实汇报阻塞点, 不创建新 task、不自动下载、不跨 session 接管。
- 检查产出目录用 E:/专利/ArchR_Output/（rds 在专利目录, 不在 session results/ 下）。
