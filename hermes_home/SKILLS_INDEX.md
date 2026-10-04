# MemOmics SKILLS_INDEX

> LLM startup ephemeral prompt — 由 webui/skills_registry.py 自动生成，请勿手改
> 手改会在下次重建时丢失；要改触发场景请改 SKILL.md frontmatter 或 skill.json

| icon | level | info |
|---|---|---|
| RED | 必触发 | user mentions -> skill_view immediately |
| YEL | 讨论触发 | confirm plan first then trigger |
| GRN | 按需触发 | only on explicit mention |
| WHT | 系统级 | Hermes internal |

> 「触发词」列会被 server._match_red_skill_triggers() 用于消息级自动匹配（RED 行），
> 只写有区分度的词，不要写 rna/scrna 这类分类水词。

---

## 01_RNA - 单细胞转录组 (46 skills)

| # | Skill | 使用场景 | 触发词 | Trigger |
|---|---|---|---|---|
| 1 | analyze_cas9_mutation_outcomes | When you need analyze cas9 mutation outcomes analysis | cas9, mutation, outcomes | YEL 讨论触发 |
| 2 | analyze_ciliary_beat_frequency | When you need analyze ciliary beat frequency analysis | ciliary, beat, frequency | YEL 讨论触发 |
| 3 | analyze_flow_cytometry_immunophenotyping | When you need analyze flow cytometry immunophenotyping analysis | flow, cytometry, immunophenotyping | YEL 讨论触发 |
| 4 | analyze_rna_secondary_structure_features | When you need analyze rna secondary structure features analysis | secondary, structure, features | YEL 讨论触发 |
| 5 | annotate_celltype_scRNA | When you need annotate celltype scRNA analysis | annotate_celltype_scRNA, annotate celltype scRNA, annotate, celltype | YEL 讨论触发 |
| 6 | annotate_celltype_with_panhumanpy | When you need annotate celltype with panhumanpy analysis | annotate, celltype, panhumanpy | YEL 讨论触发 |
| 7 | cell-cell-communication | Infer and visualize cell-cell communication networks from scRNA-seq data using CellChat v2 ligand-receptor interaction analysis. | cell-cell-communication, cell cell communication, communication | YEL 讨论触发 |
| 8 | cellbender-remove-background | 10x scRNA-seq数据有环境RNA污染(高线粒体、跨类型标记共表达、组织解离样本) | CellBender, 去背景, ambient RNA, filtered.h5, ptrepack, 空滴, 背景RNA, 环境RNA | RED 必触发 |
| 9 | cellchat-v2 | 适用于: 多细胞类型, disease, aging, development | CellChat, 细胞通讯, cellchat-v2, cellchat v2 | RED 必触发 |
| 10 | coexpression-network | Build gene co-expression networks to identify modules and hub genes from RNA-seq data. | coexpression-network, coexpression network, coexpression, network | YEL 讨论触发 |
| 11 | create_harmony_embeddings_scRNA | When you need create harmony embeddings scRNA analysis | harmony, embeddings | YEL 讨论触发 |
| 12 | create_scvi_embeddings_scRNA | When you need create scvi embeddings scRNA analysis | scvi, embeddings | YEL 讨论触发 |
| 13 | cross-contrast-deg-integration | 多对比 DEG 结果表的整合分析——手里已有 ≥2 套算好的 DEG（多条件 × 多对比、配对供体） 要回答「共同响应基因」「干预逆转某条件的重合基因」「条件特异响应」「响应是否随条件衰减」时用本 skill。 核心是四条:交集必须方向感知（同向=加剧、反向=逆转）、原始交集数必须先减随机期望 E=/A/×/B//N 并改报 OR/Fisher/Jaccard、交集前先查各对比的功效（一边个位数则 | cross, contrast, deg | YEL 讨论触发 |
| 14 | deg-analysis | 适用于: 有分组的scRNA-seq —— Pseudobulk DESeq2+Wilcoxon+MAST多方法, 含多重检验校正 | DEG, 差异分析, 差异基因, deg-analysis, deg analysis | RED 必触发 |
| 15 | dimred-representation-comparison | 降维/embedding 表示对比与分群质量定级（PCA vs scVI vs Harmony 等）。触发:'哪个分群更干净'、'scVI 和 PCA 对比'、'换个 embedding 会不会更好'、'降维方法对比'、'embedding 对比'、'用 scVI 做个 embedding 和 PCA 的 UMAP 比一下'。含严格同参原则、输入路线解耦归因、指标集与 sklearn 陷阱、多 s | dimred, representation, comparison | YEL 讨论触发 |
| 16 | disease-progression-longitudinal | 当你需要 纵向疾病进展 时触发 —— 纵向数据: LME → 轨迹建模 | disease, progression, longitudinal | YEL 讨论触发 |
| 17 | doublet-detection | 双细胞（doublet）检测与判定:scDblFinder / DoubletFinder（R）与 scrublet（Python）选型与执行，含多样本·每样本细胞数少的数据策略决策、双细胞率判读区间、'要不要剔除'的判定准则与交付口径。触发:'检测双细胞' / '双细胞比例高不高' / '要不要剔除 doublet' / 'doublet rate' / '去双胞'。 | doublet-detection, doublet detection, doublet, detection | YEL 讨论触发 |
| 18 | doublet-detection-validation | 双细胞检测结果的**可信度验证与剔除决策**。触发:检测一下双细胞 / 双细胞比例高不高 / 要不要剔除 / doublet 比例 / DoubletFinder、scrublet、scDblFinder 的结果怎么解读 / 两个方法结论不一致。核心立场:双细胞检出率是需要被验证的量，不是能直接读出来的量 —— 弱信号数据上算法标签可错到 F1≈0.3，据标签直接剔除等于删掉约 2/3 真细胞。 | doublet, detection, validation | YEL 讨论触发 |
| 19 | doubletfinder-remove-doublets | scRNA-seq数据需去除双细胞 —— DoubletFinder双细胞检测: Seurat → 人工双胞 → 检测 → 过滤 | doubletfinder, remove doublets, doublets | YEL 讨论触发 |
| 20 | estimate_cell_cycle_phase_durations | When you need estimate cell cycle phase durations analysis | estimate, cell cycle, cycle, phase | YEL 讨论触发 |
| 21 | functional-enrichment | 当你需要 功能富集 (GSEA + ORA) 时触发 —— GSEA/ORA功能富集分析。clusterProfiler/gseapy。GO/KEGG/Reactome/MSigDB | 富集分析, GO, KEGG, pathway, functional-enrichment, functional enrichment, functional, enrichment | RED 必触发 |
| 22 | gene-essentiality | Guidance for interpreting DepMap essentiality scores and correlations correctly. | gene-essentiality, gene essentiality, gene, essentiality | YEL 讨论触发 |
| 23 | gene_set_enrichment_analysis | When you need gene set enrichment analysis analysis | gene, set, enrichment | YEL 讨论触发 |
| 24 | get_gene_set_enrichment_analysis_supported_database_list | When you need get gene set enrichment analysis supported database list analysis | gene, set, enrichment, supported | YEL 讨论触发 |
| 25 | get_rna_seq_archs4 | When you need get rna seq archs4 analysis | get_rna_seq_archs4, get rna seq archs4, seq, archs4 | YEL 讨论触发 |
| 26 | grn-pyscenic | 当你需要 基因调控网络 (pySCENIC) 时触发 —— pySCENIC基因调控网络推断。TF调控子/aUCell活性评分 | grn-pyscenic, grn pyscenic, grn, pyscenic | YEL 讨论触发 |
| 27 | hdwgcna | 适用于: 异质性高, >5K细胞, disease, aging | hdwgcna | YEL 讨论触发 |
| 28 | immune-deconvolution | 适用于: disease, tumor, immune —— CIBERSORTx+xCell+MCP-counter多方法免疫细胞比例估计 | immune-deconvolution, immune deconvolution, immune, deconvolution | YEL 讨论触发 |
| 29 | infercnv | 当你需要 单细胞CNV推断 时触发 —— inferCNV肿瘤细胞CNV推断+恶性细胞鉴定 | infercnv | YEL 讨论触发 |
| 30 | lasso-biomarker-panel | 当你需要 LASSO 生物标志物 时触发 —— LASSO特征选择 → 生物标志物Panel | lasso-biomarker-panel, lasso biomarker panel, lasso, biomarker, panel | YEL 讨论触发 |
| 31 | pathway-enrichment | Guidance for choosing ORA vs GSEA and interpreting enriched pathways correctly. | pathway-enrichment, pathway enrichment, pathway, enrichment | YEL 讨论触发 |
| 32 | quantify_and_cluster_cell_motility | When you need quantify and cluster cell motility analysis | quantify, cluster, cell motility, motility | YEL 讨论触发 |
| 33 | sasp-scoring | 适用于: aging —— SASP gene set scoring + heatmap + group comparison | sasp-scoring, sasp scoring, sasp, scoring | YEL 讨论触发 |
| 34 | scrna-clustering | 适用于: 所有scRNA-seq —— 从原始数据到细胞注释的完整Seurat v5工作流。含SoupX/DoubletFinder/SCTransform/Harmony/CCA/Pseudobulk DE | 聚类, 分群, cluster, scrna-clustering, scrna clustering, clustering | RED 必触发 |
| 35 | scrna-eda | 有 h5ad 数据但还没做 QC，或用户说'看看数据'/'数据长什么样'/'数据探索'/'概览'时触发 | EDA, 数据探索, 看看数据, 概览, scrna-eda, scrna eda | RED 必触发 |
| 36 | scrna-qc | 适用于: 所有scRNA-seq —— 质控+Doublet去除+Ambient RNA去除, 支持人/鼠, 自动推荐阈值 | QC, 质控, scrna-qc, scrna qc, 线粒体, 批次校正, 批次效应 | RED 必触发 |
| 37 | scrnaseq-scanpy-core-analysis | Scanpy单细胞核心分析:10X数据→QC→归一化→HVG→PCA→邻居图→UMAP→Leiden聚类→marker→注释 | Scanpy, Scanpy流程 | RED 必触发 |
| 38 | scrnaseq-seurat-core-analysis | 用户有scRNA-seq数据需要R/Seurt基础分析 —— Seurat v5 标准分析: QC → SCTransform → PCA → UMAP → 聚类 → 注释 | Seurat, SCTransform, NormalizeData, Seurat流程 | RED 必触发 |
| 39 | sctour-trajectory-inference | scTour VAE 深度潜在时间推断 + 向量场 + 跨数据集预测。无需指定起点，无监督学习细胞动力学。 | sctour, trajectory, inference | YEL 讨论触发 |
| 40 | senescence-detection | 适用于: aging, fibrosis —— SASP scoring + p16/p21 + senescent subpopulation | senescence-detection, senescence detection, senescence, detection | YEL 讨论触发 |
| 41 | single-cell-cellcycle-scoring | 单细胞/单核细胞周期打分的判读与验证（Seurat CellCycleScoring / cc.genes.updated.2019）:先做真实增殖 marker 阴性对照，再决定能否解读相位标签；含推断单位（ICC/设计效应）、供体级置换、n 核重抽样 bootstrap、BH 校正与结论口径。触发:细胞周期打分 / CellCycleScoring / cc.genes / S.Score | single, cellcycle, scoring | YEL 讨论触发 |
| 42 | soupx-remove-background | 需去除环境RNA但无GPU，或CellBender的替代/补充 | soupx-remove-background, soupx remove background, soupx, 环境rna | YEL 讨论触发 |
| 43 | stratified-subsampling | 分层抽样下采样:大数据集→分层(细胞类型/样本)→均衡下采样→代表性数据子集 | stratified-subsampling, stratified subsampling, stratified, subsampling | YEL 讨论触发 |
| 44 | trajectory-analysis | 适用于: development, regeneration, differentiation | 轨迹, trajectory, 拟时序, pseudotime, Monocle, Slingshot, RNA velocity, scVelo | RED 必触发 |
| 45 | trajectory-conclusion-validation | 轨迹/拟时序类结论的定稿前验证（换根枚举、换嵌入独立性、供体级配对统计、固定多重检验族、结论分级措辞）。触发:Monocle3/Slingshot/scVelo 跑出伪时间后要下结论、运动或处理前后细胞在轨迹上的位置比较、判断伪时间轴是「分化轨迹」还是「细胞身份差异」、辩论/审稿要求补稳健性检验。 | trajectory, conclusion, validation | YEL 讨论触发 |
| 46 | upstream-regulator-analysis | 当你需要 上游调控因子分析 时触发 —— 上游调控预测: DEGs → DoRothEA → TF/激酶活性 | upstream, regulator | YEL 讨论触发 |

## 02_ATAC - ATAC/染色质 (11 skills)

| # | Skill | 使用场景 | 触发词 | Trigger |
|---|---|---|---|---|
| 1 | analyze_chromatin_interactions | When you need analyze chromatin interactions analysis | chromatin, interactions | YEL 讨论触发 |
| 2 | atac-seq | ArchR scATAC-seq 全流程: 环境搭建→Arrow文件→QC→降维→聚类→Peak calling→Motif→Footprinting→差异可及性→共可及性→导出 | atac-seq, atac seq, seq | YEL 讨论触发 |
| 3 | chip-atlas-diff-analysis | 当你需要 ChIP-seq 差异分析 时触发 —— ChIP差异Peak: DiffBind → 差异结合位点 | chip-atlas-diff-analysis, chip atlas diff analysis, chip, atlas, diff | YEL 讨论触发 |
| 4 | chip-atlas-peak-enrichment | ChIP-Atlas peak富集分析:peak列表→基因组区域注释→motif富集→GO/KEGG通路富集→调控网络 | chip, atlas, peak, enrichment | YEL 讨论触发 |
| 5 | chip-atlas-target-genes | 当你需要 ChIP-seq 靶基因 时触发 —— ChIP Peak靶基因注释: Peak → 基因组注释 → 靶基因 | chip-atlas-target-genes, chip atlas target genes, chip, atlas, target, genes | YEL 讨论触发 |
| 6 | find_enriched_motifs_with_homer | When you need find enriched motifs with homer analysis | find, enriched, motifs, homer | YEL 讨论触发 |
| 7 | get_genes_near_ccre | When you need get genes near ccre analysis | get_genes_near_ccre, get genes near ccre, genes, near, ccre | YEL 讨论触发 |
| 8 | identify_transcription_factor_binding_sites | When you need identify transcription factor binding sites analysis | identify, transcription, factor, binding | YEL 讨论触发 |
| 9 | overlapping-gene-assignment-audit | 回答「重叠 / 反义基因之间，reads 或 UMI 到底算谁的」类方法学质疑，并产出可复现审计包 （BED6 + 一条命令复现 + 诚实边界 + 索引图）。触发词:反义 lncRNA / antisense / head-to-head 重叠基因 / gene-span overlap / "how can we distinguish A vs B reads" / reads 归属 / UM | 反义 lncRNA, antisense, head-to-head | YEL 讨论触发 |
| 10 | perform_chipseq_peak_calling_with_macs2 | When you need perform chipseq peak calling with macs2 analysis | peak, calling, macs2 | YEL 讨论触发 |
| 11 | region_to_ccre_screen | When you need region to ccre screen analysis | region_to_ccre_screen, region to ccre screen, region, ccre, screen | YEL 讨论触发 |

## 03_空间组 - 空间转录组 (18 skills)

| # | Skill | 使用场景 | 触发词 | Trigger |
|---|---|---|---|---|
| 1 | analyze_aortic_diameter_and_geometry | When you need analyze aortic diameter and geometry analysis | aortic, diameter, geometry | YEL 讨论触发 |
| 2 | analyze_bone_microct_morphometry | When you need analyze bone microct morphometry analysis | bone, microct, morphometry | YEL 讨论触发 |
| 3 | analyze_cns_lesion_histology | When you need analyze cns lesion histology analysis | cns, lesion, histology | YEL 讨论触发 |
| 4 | analyze_hemodynamic_data | When you need analyze hemodynamic data analysis | analyze_hemodynamic_data, analyze hemodynamic data, hemodynamic | YEL 讨论触发 |
| 5 | analyze_immunohistochemistry_image | When you need analyze immunohistochemistry image analysis | immunohistochemistry, image | YEL 讨论触发 |
| 6 | batch_register_images | When you need batch register images analysis | batch_register_images, batch register images, batch, register, images | YEL 讨论触发 |
| 7 | calculate_brain_adc_map | When you need calculate brain adc map analysis | calculate_brain_adc_map, calculate brain adc map, brain, adc, map | YEL 讨论触发 |
| 8 | calculate_similarity_metrics | When you need calculate similarity metrics analysis | similarity, metrics | YEL 讨论触发 |
| 9 | create_registration_visualization | When you need create registration visualization analysis | registration, visualization | YEL 讨论触发 |
| 10 | create_segmentation_visualization | When you need create segmentation visualization analysis | segmentation, visualization | YEL 讨论触发 |
| 11 | prepare_input_for_nnunet | When you need prepare input for nnunet analysis | prepare_input_for_nnunet, prepare input for nnunet, prepare, input, nnunet | YEL 讨论触发 |
| 12 | quick_affine_registration | When you need quick affine registration analysis | quick, affine, registration | YEL 讨论触发 |
| 13 | quick_deformable_registration | When you need quick deformable registration analysis | quick, deformable, registration | YEL 讨论触发 |
| 14 | quick_rigid_registration | When you need quick rigid registration analysis | quick_rigid_registration, quick rigid registration, quick, rigid, registration | YEL 讨论触发 |
| 15 | reconstruct_3d_face_from_mri | When you need reconstruct 3d face from mri analysis | reconstruct, face, mri | YEL 讨论触发 |
| 16 | segment_and_quantify_cells_in_multiplexed_images | When you need segment and quantify cells in multiplexed images analysis | segment, quantify, cells, multiplexed | YEL 讨论触发 |
| 17 | segment_with_nn_unet | When you need segment with nn unet analysis | segment_with_nn_unet, segment with nn unet, segment, unet | YEL 讨论触发 |
| 18 | spatial-transcriptomics | 适用于: spatial, Visium/MERFISH/Slide-seq | 空间转录组, 空间转录组分析, spatial-transcriptomics, spatial transcriptomics, transcriptomics | RED 必触发 |

## 04_Bulk - Bulk/表观 (19 skills)

| # | Skill | 使用场景 | 触发词 | Trigger |
|---|---|---|---|---|
| 1 | analyze_comparative_genomics_and_haplotypes | When you need analyze comparative genomics and haplotypes analysis | comparative, genomics, haplotypes | YEL 讨论触发 |
| 2 | analyze_copy_number_purity_ploidy_and_focal_events | When you need analyze copy number purity ploidy and focal events analysis | copy, number, purity, ploidy | YEL 讨论触发 |
| 3 | analyze_ddr_network_in_cancer | When you need analyze ddr network in cancer analysis | ddr, network, cancer | YEL 讨论触发 |
| 4 | analyze_genomic_region_overlap | When you need analyze genomic region overlap analysis | genomic, region, overlap | YEL 讨论触发 |
| 5 | bayesian_finemapping_with_deep_vi | When you need bayesian finemapping with deep vi analysis | bayesian, finemapping, deep vi | YEL 讨论触发 |
| 6 | bulk-omics-clustering | 当你需要 Bulk 多组学聚类 时触发 —— 多组学数据聚类: ConsensusClustering → 亚型发现 | bulk-omics-clustering, bulk omics clustering, clustering | YEL 讨论触发 |
| 7 | bulk-rnaseq-counts-to-de-deseq2 | 当你需要 Bulk RNA-seq DESeq2 时触发 —— Bulk RNA-seq差异表达: 计数矩阵 → DESeq2 → 差异基因 → 富集 | rnaseq, counts, deseq2 | YEL 讨论触发 |
| 8 | bulk-rnaseq-differential-expression | 有bulk RNA-seq counts矩阵+实验设计表(treat vs control)，需做差异化(GO/KEGG/火山图/热图) | rnaseq, differential, expression | YEL 讨论触发 |
| 9 | deg-threshold-and-false-discovery-audit | DEG 效应量阈值的溯源与假发现审计:任何 /logFC///coef/ 阈值取多少、要不要筛、为什么显著基因数异常多时使用。含 Seurat FindMarkers 默认值的版本差异、MAST 官方无阈值参数的源码级实证、pseudobulk vs 细胞级方法的权威文献结论、正对照校准法。 | deg, threshold, false, discovery | YEL 讨论触发 |
| 10 | detect_and_annotate_somatic_mutations | When you need detect and annotate somatic mutations analysis | detect, annotate, somatic, mutations | YEL 讨论触发 |
| 11 | detect_and_characterize_structural_variations | When you need detect and characterize structural variations analysis | detect, characterize, structural, variations | YEL 讨论触发 |
| 12 | find_sequence_mutations | When you need find sequence mutations analysis | find_sequence_mutations, find sequence mutations, find, sequence, mutations | YEL 讨论触发 |
| 13 | fit_genomic_prediction_model | When you need fit genomic prediction model analysis | fit, genomic, prediction, model | YEL 讨论触发 |
| 14 | genetic-variant-annotation | Annotate genomic variants in VCF files with functional effects, clinical significance, and pathogenicity predictions. | genetic, variant, annotation | YEL 讨论触发 |
| 15 | gwas-to-function-twas | 当你需要 GWAS TWAS 分析 时触发 —— GWAS → TWAS功能分析: 关联信号 → 基因优先级 → 功能验证 | gwas-to-function-twas, gwas to function twas, gwas, function, twas | YEL 讨论触发 |
| 16 | liftover_coordinates | When you need liftover coordinates analysis | liftover_coordinates, liftover coordinates, liftover, coordinates | YEL 讨论触发 |
| 17 | mendelian-randomization-twosamplemr | 当你需要 孟德尔随机化 时触发 —— 两样本MR: 工具变量 → MR分析 → 敏感性分析 | GWAS, 孟德尔, MR, mendelian, randomization, twosamplemr | RED 必触发 |
| 18 | milor | 适用于: 有分组的scRNA-seq, aging, disease, >5样本 | milor | YEL 讨论触发 |
| 19 | polygenic-risk-score-prs-catalog | 当你需要 多基因风险评分 时触发 —— PRS计算: GWAS → PRS → 风险分层 | polygenic, risk, score, prs | YEL 讨论触发 |

## 05_蛋白 - 蛋白/免疫 (26 skills)

| # | Skill | 使用场景 | 触发词 | Trigger |
|---|---|---|---|---|
| 1 | analyze_atp_luminescence_assay | When you need analyze atp luminescence assay analysis | atp, luminescence, assay | YEL 讨论触发 |
| 2 | analyze_circular_dichroism_spectra | When you need analyze circular dichroism spectra analysis | circular, dichroism, spectra | YEL 讨论触发 |
| 3 | analyze_cytokine_production_in_cd4_tcells | When you need analyze cytokine production in cd4 tcells analysis | cytokine, production, cd4, tcells | YEL 讨论触发 |
| 4 | analyze_ebv_antibody_titers | When you need analyze ebv antibody titers analysis | ebv, antibody, titers | YEL 讨论触发 |
| 5 | analyze_endolysosomal_calcium_dynamics | When you need analyze endolysosomal calcium dynamics analysis | endolysosomal, calcium, dynamics | YEL 讨论触发 |
| 6 | analyze_enzyme_kinetics_assay | When you need analyze enzyme kinetics assay analysis | enzyme, kinetics, assay | YEL 讨论触发 |
| 7 | analyze_fatty_acid_composition_by_gc | When you need analyze fatty acid composition by gc analysis | fatty, acid, composition | YEL 讨论触发 |
| 8 | analyze_interaction_mechanisms | When you need analyze interaction mechanisms analysis | interaction, mechanisms | YEL 讨论触发 |
| 9 | analyze_intracellular_calcium_with_rhod2 | When you need analyze intracellular calcium with rhod2 analysis | intracellular, calcium, rhod2 | YEL 讨论触发 |
| 10 | analyze_itc_binding_thermodynamics | When you need analyze itc binding thermodynamics analysis | itc, binding, thermodynamics | YEL 讨论触发 |
| 11 | analyze_mitochondrial_morphology_and_potential | When you need analyze mitochondrial morphology and potential analysis | mitochondrial, morphology, potential | YEL 讨论触发 |
| 12 | analyze_protease_kinetics | When you need analyze protease kinetics analysis | protease, kinetics | YEL 讨论触发 |
| 13 | analyze_protein_colocalization | When you need analyze protein colocalization analysis | colocalization | YEL 讨论触发 |
| 14 | analyze_protein_conservation | When you need analyze protein conservation analysis | conservation | YEL 讨论触发 |
| 15 | analyze_protein_phylogeny | When you need analyze protein phylogeny analysis | phylogeny | YEL 讨论触发 |
| 16 | analyze_radiolabeled_antibody_biodistribution | When you need analyze radiolabeled antibody biodistribution analysis | radiolabeled, antibody, biodistribution | YEL 讨论触发 |
| 17 | analyze_western_blot | When you need analyze western blot analysis | analyze_western_blot, analyze western blot, western, blot | YEL 讨论触发 |
| 18 | compare_protein_structures | When you need compare protein structures analysis | compare, structures | YEL 讨论触发 |
| 19 | docking_autodock_vina | When you need docking autodock vina analysis | docking_autodock_vina, docking autodock vina, docking, autodock, vina | YEL 讨论触发 |
| 20 | generate_gene_embeddings_with_ESM_models | When you need generate gene embeddings with ESM models analysis | gene, embeddings, esm, models | YEL 讨论触发 |
| 21 | model_protein_dimerization_network | When you need model protein dimerization network analysis | model, dimerization, network | YEL 讨论触发 |
| 22 | predict_binding_affinity_protein_1d_sequence | When you need predict binding affinity protein 1d sequence analysis | predict, binding, affinity, sequence | YEL 讨论触发 |
| 23 | proteomics-diff-exp | 当你需要 蛋白质组差异分析 时触发 —— 蛋白质组差异: 定量 → limma → 差异蛋白 → 富集 | proteomics-diff-exp, proteomics diff exp, diff, exp | YEL 讨论触发 |
| 24 | run_autosite | When you need run autosite analysis | run_autosite, run autosite, autosite | YEL 讨论触发 |
| 25 | run_diffdock_with_smiles | When you need run diffdock with smiles analysis | run_diffdock_with_smiles, run diffdock with smiles, diffdock, smiles | YEL 讨论触发 |
| 26 | simulate_protein_signaling_network | When you need simulate protein signaling network analysis | simulate, signaling, network | YEL 讨论触发 |

## 06_微生物植物 - 微生物/植物 (5 skills)

| # | Skill | 使用场景 | 触发词 | Trigger |
|---|---|---|---|---|
| 1 | analyze_bacterial_growth_curve | When you need analyze bacterial growth curve analysis | bacterial, growth, curve | YEL 讨论触发 |
| 2 | get_bacterial_transformation_protocol | When you need get bacterial transformation protocol analysis | bacterial, transformation, protocol | YEL 讨论触发 |
| 3 | perform_flux_balance_analysis | When you need perform flux balance analysis analysis | flux, balance | YEL 讨论触发 |
| 4 | simulate_demographic_history | When you need simulate demographic history analysis | simulate, demographic, history | YEL 讨论触发 |
| 5 | simulate_metabolic_network_perturbation | When you need simulate metabolic network perturbation analysis | simulate, metabolic, network, perturbation | YEL 讨论触发 |

## 07_药物临床 - 药物/临床 (23 skills)

| # | Skill | 使用场景 | 触发词 | Trigger |
|---|---|---|---|---|
| 1 | analyze_abr_waveform_p1_metrics | When you need analyze abr waveform p1 metrics analysis | abr, waveform, metrics | YEL 讨论触发 |
| 2 | analyze_accelerated_stability_of_pharmaceutical_formulations | When you need analyze accelerated stability of pharmaceutical formulations analysis | accelerated, stability, pharmaceutical, formulations | YEL 讨论触发 |
| 3 | analyze_fda_safety_signals | When you need analyze fda safety signals analysis | fda, safety, signals | YEL 讨论触发 |
| 4 | analyze_xenograft_tumor_growth_inhibition | When you need analyze xenograft tumor growth inhibition analysis | xenograft, tumor, growth, inhibition | YEL 讨论触发 |
| 5 | calculate_physicochemical_properties | When you need calculate physicochemical properties analysis | physicochemical, properties | YEL 讨论触发 |
| 6 | check_drug_combination_safety | When you need check drug combination safety analysis | drug, combination, safety | YEL 讨论触发 |
| 7 | check_fda_drug_recalls | When you need check fda drug recalls analysis | check_fda_drug_recalls, check fda drug recalls, fda, drug, recalls | YEL 讨论触发 |
| 8 | clinicaltrials-landscape | 当你需要 临床试验全景 时触发 —— ClinicalTrials.gov数据挖掘 | clinicaltrials-landscape, clinicaltrials landscape, clinicaltrials, landscape | YEL 讨论触发 |
| 9 | drug-response | 适用于: disease, tumor, 有药敏数据 —— Connectivity Map+药物敏感性+联合用药预测 | drug-response, drug response, drug, response | YEL 讨论触发 |
| 10 | estimate_alpha_particle_radiotherapy_dosimetry | When you need estimate alpha particle radiotherapy dosimetry analysis | estimate, alpha, particle, radiotherapy | YEL 讨论触发 |
| 11 | find_alternative_drugs_ddinter | When you need find alternative drugs ddinter analysis | find, alternative, drugs, ddinter | YEL 讨论触发 |
| 12 | get_fda_drug_label_info | When you need get fda drug label info analysis | get_fda_drug_label_info, get fda drug label info, fda, drug, label, info | YEL 讨论触发 |
| 13 | grade_adverse_events_using_vcog_ctcae | When you need grade adverse events using vcog ctcae analysis | grade, adverse, events, vcog | YEL 讨论触发 |
| 14 | open-targets | Open Targets平台查询:疾病/靶点→靶点-疾病关联证据→遗传/组学/文献→药物开发管线 | open-targets, open targets, open, targets | YEL 讨论触发 |
| 15 | open-targets-graphql | 当你需要 Open Targets GraphQL API 时触发 | open-targets-graphql, open targets graphql, open, targets, graphql | YEL 讨论触发 |
| 16 | perform_cosinor_analysis | When you need perform cosinor analysis analysis | perform_cosinor_analysis, perform cosinor analysis, cosinor | YEL 讨论触发 |
| 17 | perform_mwas_cyp2c19_metabolizer_status | When you need perform mwas cyp2c19 metabolizer status analysis | mwas, cyp2c19, metabolizer, status | YEL 讨论触发 |
| 18 | predict_admet_properties | When you need predict admet properties analysis | predict_admet_properties, predict admet properties, predict, admet, properties | YEL 讨论触发 |
| 19 | retrieve_topk_repurposing_drugs_from_disease_txgnn | When you need retrieve topk repurposing drugs from disease txgnn analysis | retrieve, topk, repurposing, drugs | YEL 讨论触发 |
| 20 | scrna-disease-drug-discovery | scRNA疾病药物发现pipeline:scRNA数据→靶点识别→化合物筛选→已有药重定位→候选药物+证据强度→结果排序 | 药物靶点, 靶点发现, drug target, 药物重定位, disease, drug, discovery | RED 必触发 |
| 21 | simulate_thyroid_hormone_pharmacokinetics | When you need simulate thyroid hormone pharmacokinetics analysis | simulate, thyroid, hormone, pharmacokinetics | YEL 讨论触发 |
| 22 | survival-analysis | 适用于: disease, 有生存数据 —— KM曲线+Cox回归+风险评分模型+时间依赖ROC | 生存分析, KM, 预后, survival-analysis, survival analysis, survival | RED 必触发 |
| 23 | survival-analysis-clinical | 临床生存分析:临床信息+表达→Kaplan-Meier→Cox回归→log-rank test→预后标志物 | survival, clinical | YEL 讨论触发 |

## 08_报告 - 报告/可视化 (106 skills)

| # | Skill | 使用场景 | 触发词 | Trigger |
|---|---|---|---|---|
| 1 | academic-figure-skill | 用户提供出图脚本（未强调 CNS 级）时默认用本 skill 检查出图规范并优化；用户未提供脚本但要专业/期刊级出图时用本 skill；脚本不成熟时优先识别脚本类型并匹配本 skill 的 29 种图型规范。CNS 级（发表级/Nature style/SCI figure）才用 nature-figure。 | 学术图, 学术级, 专业出图, 期刊出图, 论文配图, 出图规范, 检查脚本, 脚本优化, academic figure, publication figure, 期刊图, 论文图, 投稿图, 脚本检查, 检查出图, academic-figure | RED 必触发 |
| 2 | academic-paper-reviewer | 多视角学术审稿:自动识别论文领域，动态配置5个独立审稿人（期刊匹配/方法学/领域专家/跨学科/魔鬼代言人）+主编合成，支持完整审稿/复审/快速评估/苏格拉底引导/校准模式 | 审稿, 论文审稿, 同行评审, 审稿意见, 帮我审论文, 模拟审稿, 审稿人, referee, peer review, review paper, critique paper, editorial review | RED 必触发 |
| 3 | academic-thesis-docx | 用户给出学校论文撰写/装帧规范文件（.doc/.pdf）与写作素材（专利、项目、数据），要求按该规范撰写学位论文并产出可编辑 Word 交付物时使用。也用于已交付论文的按规范修订（补章、改格式、重出版次）。 | academic-thesis-docx, academic thesis docx, academic, thesis, docx | YEL 讨论触发 |
| 4 | agent-loop-engineering | 防止 LLM '叙事代替执行'的框架级防御。触发:长链修复任务中 Agent 输出动作动词但无 tool call，或 rail_review(post) code_executed 过短。已部署 Guardian 快照回滚 + Planner/Executor 双阶段协议。 | loop engineering, agent reliability, tool call audit, narrative hallucination, 铁律 -1, 铁律 -2, 铁律 -3, 铁律 3b | YEL 讨论触发 |
| 5 | alphafold2 | OpenAI4S 移植:Predict protein structure for monomers and multimers with Al... | alphafold2 | YEL 讨论触发 |
| 6 | analysis-summary-report | 当已完成真实分析（有terminal执行结果+figures）且用户要求总结/报告时触发。文献综述/整理结果不触发。 | 生成总结, 分析总结, 跑完总结, analysis-summary-report, analysis summary report, Excel, 结果汇总 | RED 必触发 |
| 7 | animation-first-showcase | 用户要做一个给人看/演示/汇报的 HTML（展示自己、展示项目、演示功能、答辩、行业调研汇总）时；或用户抱怨已有 HTML 交付物「字太多、不直观」时 | animation-first-showcase, animation first showcase, animation, first, showcase | YEL 讨论触发 |
| 8 | archr-atac-analysis | ArchR scATAC-seq 全流程:环境搭建 → Arrow 加载 → QC → LSI → 聚类 → Peak Calling → 差异可及性 → TF footprinting → motif 富集。支持跨物种 CRE 保守性评估。 Signac 作为备选方案… | archr-atac-analysis, archr atac analysis, archr | YEL 讨论触发 |
| 9 | atac-paper-reproduction | ATAC-seq 论文对比/年龄相关流程复现。核心原则:官方路径优先——去论文官方代码仓库 （GitHub/Zenodo）、官方补充表（Table_S*）、GEO 找方法，不自行发明。 关键技巧:官方补充表含 cCRE/peak 全集时直接复用坐标做片段计数，跳过本地 peak calling（免装 MACS3/snapatac2）… | 论文复现, 对比流程, 官方路径, official code, ATAC 复现 | YEL 讨论触发 |
| 10 | atac-seq-memomics | ArchR scATAC-seq 全流程: 环境搭建→Arrow文件→QC→降维→聚类→Peak calling→Motif→Footprinting→差异可及性→共可及性→导出 | atac-seq-memomics, atac seq memomics, seq, memomics | YEL 讨论触发 |
| 11 | bio-db-benchmark-qa | 用户给出 E:\benchmarker\...\*_考试题.json 路径，要求"作答/测试/开始完成"，随后可能提供 *_密封答案.json 要求"对一下/评分"。这类考试的特点:每道题是一个事实型问题… | benchmarker, 密封答案, 考试题, TaskA, TaskB, TaskC, dbqa2, MESINESP | YEL 讨论触发 |
| 12 | bioinformatics-html-report | 当需要生成生信分析HTML报告时触发 — 包含图表、辩论记录、参数来源、生物结论的完整报告 | html | RED 必触发 |
| 13 | bioinformatics-patent-strategy | Bioinformatics method patent strategy and drafting. Covers A25 (intellectual activity rules) defense, claim structuring for bioinformatics workflows, dual-patent architectures… | 专利, patent, 权利要求, claims, A25, 智力活动, 交底书, 可专利性 | YEL 讨论触发 |
| 14 | boltz | OpenAI4S 移植:Structure prediction for protein, nucleic-acid, and small-mo... | boltz | YEL 讨论触发 |
| 15 | borzoi | OpenAI4S 移植:Predict genome-wide functional tracks (RNA-seq, CAGE, DNase,... | borzoi | YEL 讨论触发 |
| 16 | cellbender-batch-pipeline | 10+ 样本需要串行跑 CellBender（总时长 > 1 小时） | 批量cellbender, 多样本去污染, 后台运行cellbender | YEL 讨论触发 |
| 17 | celltype-proportion-comparison | scRNA-seq 注释后比较各亚群在 6 组（3 条件×Pre/Post，个体配对）中的比例变化，判断"逆转衰老/逆转糖尿病/运动共同趋势"，并对已有 AUCell 打分列做同样的跨组差异分析。包含:分组映射、base_id 配对检验、Cliff's delta 效应量方向约定、双 FDR（亚群内+全局）、探索用 raw p 值/定稿用 FDR 标注、egg::set_panel_size 固定… | 亚群比例, L3 boxplot, Proportion (%, 6组箱线图, FDR标注, p值标注, 画哪几组, 逆转衰老 | YEL 讨论触发 |
| 18 | chai1 | OpenAI4S 移植:Structure prediction for protein, nucleic-acid, and small-mo... | chai1 | YEL 讨论触发 |
| 19 | cn-degree-thesis-writing | 中文学位论文（本科/硕士/博士毕业论文）撰写与「校内格式规范」合规。用于:读取学校《学位论文撰写及装帧规范》 原件 → 按硕/博适用性标注 → 按规范骨架撰写章节 → 格式自查 → 产出符合规范的 .docx / 标注版速查… | 毕业论文, 学位论文, 硕士论文, 撰写规范, 装帧规范, 论文格式, 封面扉页, 原创性声明 | YEL 讨论触发 |
| 20 | cns-visualization | 当你需要 CNS级可视化 时触发 —— Nature/Cell/Science级别出图模板: UMAP+DotPlot+Violin+Heatmap+Sankey | UMAP, DotPlot, 小提琴图, 火山图, 热图, Sankey, Violin, FeaturePlot, SpatialPlot | RED 必触发 |
| 21 | competitor-agent-research | 用户问自己(MemOmics)与另一个科研/生信 AI Agent 的差距，要求从能力和架构上调研对比 | XX agent 差距, 调研一下 XX 的能力和架构, 竞品分析, biomini, Biomni, 架构双维对比。 | YEL 讨论触发 |
| 22 | cross-species-annotation | 跨物种单细胞RNA-seq细胞类型注释方法 | cross-species-annotation, cross species annotation, cross, species, annotation | YEL 讨论触发 |
| 23 | cross-species-atac-annotation | Cross-species ATAC-seq cell type annotation strategy: align fine-grained subclusters where possible keep species-specific names for non-overlapping populations… | cross, species, annotation | YEL 讨论触发 |
| 24 | cross-species-atac-conservation | 纯 ATAC-seq 跨物种 CRE 保守性定量评估方法（专利方案）。 三层递进:L1 序列保守 → L2 染色质可及性保守 → L3 TF 结合动态保守。 核心创新:B 类 CRE 检出（序列+可及性保守，但 TF 足迹分歧）。 不需要 RNA/Hi-C/ChIP——纯 ATAC 数据即可运行完整评估… | 跨物种 CRE, ATAC 保守性, CRE 可代替性, 调控元件保守性评估 | YEL 讨论触发 |
| 25 | cross-species-cre-conservation | Cross-species CRE (cis-regulatory element) conservation assessment: five-layer pipeline (sequence → epigenetic → 3D → functional → CRECS) quantifying whether one species' regulatory elements (e.g… | cross, species, cre, conservation | YEL 讨论触发 |
| 26 | cross-species-regulatory-conservation | Cross-species gene regulatory element conservation assessment (CRCA) framework. Five-layer evaluation: R1 sequence conservation → R2 CRE chromatin accessibility (ATAC-driven) → R3 TF binding dynamics… | 跨物种调控元件, CRCA, 调控保守性, B类基因, BNIP3验证, CRE保守性, TF footprinting跨物种, regulatory conservation | YEL 讨论触发 |
| 27 | debate-core | 任何涉及结论/参数裁决的时刻:rail_review(post) 后、结论合成前、入库/报告前 参数候选≥2 或结果冲突/重试失败时。SOUL.md 铁律 #5 强制场景。 | debate-core, debate core, debate | YEL 讨论触发 |
| 28 | deg-mixed-design | 多组独立比较 + 组内前后/多点配对取样的 DEG。用户提到'配对'、'运动前后'、'前后比较'、'重复测量'、'独立+配对'、'随机效应'、'组×时间交互'时优先本 skill；纯两组简单比较走 deg-analysis | deg-mixed-design, deg mixed design, deg, mixed | YEL 讨论触发 |
| 29 | diagram-design | 示意图/流程图/架构图/技术路线图/专利方案图/研究设计图(非数据统计图; 数据图走 nature-figure) | diagram-design, diagram design, diagram | YEL 讨论触发 |
| 30 | dnbc4tools-analysis-workflow | 用户提到 DNBelab/dnbc4tools/华大BGI/华大基因 单细胞 RNA 或 ATAC 的比对/分析流程 | dnbc4tools, workflow | YEL 讨论触发 |
| 31 | dnbc4tools-index-building | 华大BGI DNBelab C系列高通量单细胞数据分析软件 dnbc4tools 的参考基因组索引构建流程（rna mkref=STAR 2.7.2b genomeGenerate + atac mkref=chromap + tools mkgtf GTF过滤校正）… | dnbc4tools, index, building | YEL 讨论触发 |
| 32 | docx-generation | 需产出或读取 Word 文档（.docx / 旧版 .doc / 扫描版文档）时使用 | Word, docx, word文档, docx-generation, docx generation, 导出Word | RED 必触发 |
| 33 | enrichment-conclusion-validation | DEG→GO/KEGG/GSEA 结论的定稿前四项验证:推断单位（细胞 vs 样本）、多重检验可达性、细胞类型构成混杂、通路冗余合并。触发:富集结果要下结论/出图/入库前，debate 判 need_more_info，样本级与细胞级显著性冲突，KEGG 榜单出现一堆疾病名通路，跨组富集出线粒体/能量代谢类通路。 | enrichment, conclusion, validation | YEL 讨论触发 |
| 34 | evo2 | OpenAI4S 移植:Score, embed, and generate DNA sequences with Evo 2, a long-... | evo2 | YEL 讨论触发 |
| 35 | figure-designer | 用户想表达某个结论但不知怎么设计图/图被说不好看不专业/要选图型或布局建议时使用。路由纪律:本技能只输出设计建议与QC审计，绝不代替出图；用户说'画个热图/帮我出图/生成图'一律按 SOUL.md 画图 Skill 选择策略走 academic-figure-skill（专业/期刊出图默认）/ nature-figure（CNS 级）/ cns-visualization（生信快速图）/ scip… | 设计图, 图设计, 图不好看, 图不专业, 选什么图, 图型选择, 布局建议, 图布局, 作图建议, 设计一张图, figure design, design a figure, choose the right chart, plot design | RED 必触发 |
| 36 | figure-layout-geometry | 程式化出图的版式几何与对齐自检（matplotlib / node-link / Sankey / 冲积图 / 手绘示意图 / 自定义绘制）: 「标签与图形元素不对齐」「色块被盖住」「节点重叠」「顶部被裁」「图例与脚注撞行」的根因定位 布局函数硬约束、三项 renderer 几何自检、像素级核验（纯色段扫描 + OCR 口径校准 + px_per_unit 标定）。 触发:标签没对齐 / 标签压住 | 标签没对齐, 标签压住元素, 色块被盖住, 节点重叠, 顶端标签掉了, 看着歪了, 顶部被截断, 版式自检, 像素核验, 出图版式, 对齐色块, 文字重叠, 文字压字, 图里文字叠在一起, 标注撞行, 糊成一团 | RED 必触发 |
| 37 | flow-diagram-geometry | 桑基 / 流向图（Sankey、Alluvial、冲击图）的几何与文字碰撞控制:两侧节点数悬殊时的独立归一化布局 链路流量守恒与交叉控制、宽度语义的图注防误读、列标题 / 图例 / 脚注三类文字碰撞的修法 以及用 OCR 坐标 + 像素行带法验收文字是否重叠。触发:桑基图 / 桑葚图 / 桑基 / Sankey / alluvial 流向图 / 冲击图 / 两侧节点数悬殊 / 标签被压住 / 文字 | flow-diagram-geometry, flow diagram geometry, flow, diagram, geometry | YEL 讨论触发 |
| 38 | gene-set-overlap-analysis | 基因集合交并分析（韦恩图 / 多对比共表达交集 / 逆转分析）——建集合、出交集表、**做富集显著性检验**、画可交付韦恩图。触发:韦恩图/venn/画个韦恩图/交集/共表达/三组交集/共同基因/重叠基因/上调和下调分别多少/逆转分析/衰老上调运动后下调/DM上调运动后下调/交集有没有意义/UpSet。 | gene, set, overlap | YEL 讨论触发 |
| 39 | genui | 回答中需要结构化呈现（要点/对比/流程/状态/数据/操作）时输出 dsh-ui 围栏，webui 自动渲染。纯文字问答不需要。 | 结构化展示, 可视化呈现, UI组件, 要点卡片, dsh-ui, genui, 交互面板, 数据图表, 流程步骤展示, 状态一览, render ui, interactive ui | RED 必触发 |
| 40 | go-enrichment-visualization | User has a curated enrichment table (Cluster / GO term / Log(q-value)) and wants a CNS-level enrichment heatmap or dotplot. e.g… | enrichment, visualization | YEL 讨论触发 |
| 41 | grill-me | 方案打磨/设计审查:方案/设计/计划刚产出时、重大决策落地前 debate/rail_review 前的预检、多方案选型时。用户说"拷问一下""帮我挑毛病" "这个方案行不行"时必触发。 | 拷问, 挑毛病, grill, 方案打磨, 设计审查, 帮我审方案, 面试方案 | RED 必触发 |
| 42 | gse278576-atac-aging-comparison | GSE278576 人海马衰老 ATAC 对比流程复现（Zemke/Lee/Mamde et al., Science 2026 bioRxiv 2024.10.14.618338）。官方代码仓库 nrzemke/aging_human_hippocampus… | GSE278576, 人海马ATAC, hippocampus aging ATAC, 对比流程复现 | YEL 讨论触发 |
| 43 | hdwgcna-official-workflow | [hdwgcna-official] 需要跑 hdWGCNA 官方完整 workflow、出官方标准图集、或遇到 hdWGCNA 加载失败/ModuleTraitCorrelation 报错/ModuleUMAPPlot future 超限/TOM 路径问题。 | hdwgcna, official, workflow | YEL 讨论触发 |
| 44 | html-report | 当你需要 HTML报告 时触发 —— 生成精美的HTML分析报告，支持图表画廊、响应式布局、打印友好 | html-report, html report, html | YEL 讨论触发 |
| 45 | human-skill | 用户要求对中文论文/报告做去 AI 味处理，或要求查重（重复率）、检查自我抄袭（如学位论文 vs 专利交底书同源）、投稿前 AI 痕迹自检。 | 去AI味, 去AI腔, human-skill, 查重, 重复率, 自我抄袭, AI痕迹, 像AI写的, AI腔, 降AI味 | RED 必触发 |
| 46 | idea-evaluator | 研究想法5维评估（Higher/Faster/Stronger/Cheaper/Broader）+生命周期/能力匹配/范式突破/致命缺陷审计，输出审稿人式裁决 | 评估研究想法, 这个想法值得做吗, 研究方向评估, novelty check, 评估可行性, score this idea, idea evaluation, research idea, 值得做吗, 可行性 | RED 必触发 |
| 47 | image-ocr-fallback | User uploads a screenshot/table/figure-caption image and expects the text read back | image-ocr-fallback, image ocr fallback, image, ocr, fallback | YEL 讨论触发 |
| 48 | input-data-integrity-audit | 拿到任何分析输入定义文件（基因集定义、通路清单、打分矩阵、样本元数据表）准备用它做打分/富集/溯源前；或用户问「这个是不是？」「该用哪份文件」；或你发现某组条目数整齐得可疑时。 | input, integrity, audit | YEL 讨论触发 |
| 49 | interactive-html-deliverables | 用户要一个**给人看**的交互式网页交付物（汇报、展示、介绍、看板、评审演示），而不是分析报告的结论页时。若目标是「把分析结果写成报告」→ 用 bioinformatics-html-report。 | interactive, html, deliverables | YEL 讨论触发 |
| 50 | literature-full-summary | 文献全文思路提炼。触发场景:用户要求'总结/解读/提炼这篇文章的思路'、'这篇文章讲了什么'、文献库一键全文提炼。 | literature-full-summary, literature full summary, full | YEL 讨论触发 |
| 51 | matrix-heatmap-geometry | 出或改**矩阵型热图**（基因集×亚群、基因×样本、GO 词条×亚群、效应值×亚群）并关心版式、期刊尺寸、矢量导出或口径取舍时。 纯 UMAP/Violin/DotPlot 不需要；调色板选择不需要。 | matrix-heatmap-geometry, matrix heatmap geometry, matrix, heatmap, geometry | YEL 讨论触发 |
| 52 | mesh-decs-semantic-indexing | [MeSH/DeCS语义索引] 提取PubMed文献MeSH主要标签 / MESINESP西语文献DeCS编码 / 语义索引benchmark / 文献标引 / semantic indexing / meshMajor / decsCodes | mesh, decs, semantic, indexing | YEL 讨论触发 |
| 53 | mesh-decs-tag-extraction | 用户给论文 title/abstract/PMID，要求输出 MeSH 主要标签 / MeSH 词 / 语义索引标签 | 语义索引, MeSH标签, MeSH主要标签, DeCS编码, meshMajor, decsCodes, benchmarker, 试卷作答 | YEL 讨论触发 |
| 54 | mesh-semantic-indexing | User provides PMIDs (or title+abstract) and wants MeSH major topics (typically 5-10 labels/article) | mesh-semantic-indexing, mesh semantic indexing, mesh, semantic, indexing | YEL 讨论触发 |
| 55 | metabolomics-full-pipeline | 用户提供代谢组峰表（LC-MS/GC-MS/NMR 导出），需要完整流程（QC→归一化→差异→富集→可视化）时触发。 | metabolomics, full, pipeline | YEL 讨论触发 |
| 56 | metabolomics-functional-enrichment | 代谢组功能富集 / 代谢通路 / MetPA / MSEA / mummichog / 代谢物通路富集 / metabolite set enrichment / metabolic pathway analysis / KEGG代谢通路 / HMDB富集 | metabolomics, functional, enrichment | YEL 讨论触发 |
| 57 | metabolomics-statistical-analysis | 代谢组学统计分析 / 代谢物差异分析 / LC-MS差异 / GC-MS差异 / PLS-DA / OPLS-DA / VIP / 代谢标志物 / 代谢组火山图 / metabolomics / metabolic biomarker / peak intensity matrix 差异对比 | metabolomics, statistical | YEL 讨论触发 |
| 58 | metascape-gene-list-prep | 用户有 FindMarkers / DEG 结果 CSV（含 cluster、gene、avg_log2FC 列），需要构建 Metascape 导入格式的基因列表: | metascape, 基因列表, top100, DEG转Metascape, 按亚群取基因, 合并Metascape表。 | YEL 讨论触发 |
| 59 | mixed-design-deg | 多受试者实验含两组独立比较 + 同一受试者重复测量（pre/post、多时间点）时找 DEG:如 三组（Y/O/OD）× 运动前后、干预前后配对 + 组间比较、纵向随访组间对比。触发词:独立+配对、混合设计、配对比较、pre/post、重复测量、随机效应 donor | 混合设计, 配对比较, pre, post, 重复测量, 随机效应 donor | YEL 讨论触发 |
| 60 | molecular-cloning-design | [molecular cloning] 克隆策略设计:Gibson Assembly / Golden Gate / Restriction-Ligation / Addgene质粒改造 / 慢病毒·细菌·酵母·IVT载体构建 / LABBench2 cloning考试 | molecular-cloning-design, molecular cloning design, molecular, cloning | YEL 讨论触发 |
| 61 | multi-role-debate | 需要跑多角色辩论、debate_analysis 连续失败、参数/结论需要 多角色裁决、用户要求"先正方再反方最后LLM判决"时。 | multi-role-debate, multi role debate, role, debate | YEL 讨论触发 |
| 62 | nature-data | Draft or audit manuscript Data/Code Availability statements, dataset access routes, repository plans, and FAIR metadata. Use for 数据可用性声明、数据共享、数据仓库选择 and dataset citations; not general data cleaning or | 数据可用性, 数据可得性声明, 代码可用性, 数据仓储, 登录号, FAIR, availability statement | RED 必触发 |
| 63 | nature-experiment-log | 标准化实验日志记录——直接上传或读取本地图片、语音和文字，产出带 YAML frontmatter 的 Markdown；可选集成飞书 CLI 与 Obsidian。 | 实验日志, 实验记录, 记录实验, 日志模板, 语音记录 | RED 必触发 |
| 64 | nature-figure | User needs publication-ready figures for journals. Not for EDA or quick exploration plots. | CNS级别, 发表级, 投稿, 投稿配图, Nature style, 期刊, SCI figure, 发表, publication figure, SCI, paper figure, figure contract, SVG editable, TIFF 600dpi, 顶刊, Nature风格 | RED 必触发 |
| 65 | nature-paper-card | 单篇论文深度拆解卡片:固定01-16节（文献定位/研究问题/背景路线/核心洞见/方法模块逻辑/关键公式/实验→主张证据链/结论边界/作者局限/批判分析/知识连接/可测试研究想法） | 拆解文献, 文献拆解, 拆解论文, paper card, 论文卡片, 深度拆解, 单篇论文分析, evidence chain, 证据链分析, 拆解这篇文献 | RED 必触发 |
| 66 | nature-paper2ppt | Create or improve a Chinese academic PPTX from a scientific paper or research reading notes, with source figures and speaker notes. Use for 论文做PPT、文献汇报、组会PPT and paper-based conference or defense pres | 论文转PPT, 文献做成PPT, 组会PPT, 学术PPT, paper2ppt | RED 必触发 |
| 67 | nature-polishing | Polish, translate, or tighten existing academic prose while preserving facts, terminology, and evidence boundaries. Use for 论文润色、学术翻译、正文精简, or manuscript LaTeX layout fixes. Use nature-writing when th | 英文润色, 学术润色, 期刊语言, 语言打磨, 收紧表达, polish manuscript | RED 必触发 |
| 68 | nature-proposal-writer | Compose, revise, or audit research proposals, opening reports, and research plans from supporting evidence. Use for 研究计划、开题报告、科研项目申请书. Invoked as researchwrite for compatibility; use nature-writing fo | 开题报告, 申报书, 标书, 研究计划, 立项依据, 基金申请, proposal | RED 必触发 |
| 69 | nature-reader | 全文中英对照精读:PDF/DOI/arXiv/HTML/粘贴文本 → 双语对照 Markdown（图表/公式感知、源锚定、术语表），绝不降级为摘要 | 总结这篇文章, 解读这篇文献, 这篇文章的研究思路, 作者做了什么, 精读, 复现这篇, 读论文, 精读论文, 论文翻译, 文献翻译, 文献阅读, 帮我读这篇文章, 翻译这篇paper, 全文对照, paper translation, read this paper | RED 必触发 |
| 70 | nature-response | Nature风格修回信套件:逐点回复（按审稿人隔离）、rebuttal、修回cover letter、LaTeX模板、标红修改稿 | 修回信, 返修, rebuttal, response to reviewers, 审稿意见回复, 逐点回复, 大修回复, 小修回复, 回复审稿人, 修改稿回复, 标红修改, cover letter, 编辑邮件, 返修邮件 | RED 必触发 |
| 71 | nature-reviewer | Nature风格投稿前预审（审稿人视角）:原创性/科学重要性/跨学科读者/技术严谨性/非专业可读性五轴评估，输出Major/Minor/blocking | Nature审稿, 预审, 投稿前自审, 审稿人视角, 审稿意见模拟, 帮我审一下论文, referee, mock peer review, manuscript critique, novelty assessment, pre-submission review, manuscript review, peer review, referee report | RED 必触发 |
| 72 | nature-shared | Internal shared-reference support package for installed nature-writing, nature-polishing, nature-reader, and nature-paper2ppt skills. Do not invoke it as a standalone user workflow. Load only the spec | nature-shared, nature shared, shared | YEL 讨论触发 |
| 73 | nature-statistics | Audit or improve manuscript statistical reporting, including experimental units, replication, uncertainty, tests, and figure statistics. Use for 统计审查、统计方法小节、图注统计 and reviewer concerns; compute new ana | 统计审查, 统计报告, 样本量, 重复数, 误差棒, 伪重复, pseudoreplication, 统计方法审查 | RED 必触发 |
| 74 | nature-writing | Draft or restructure scientific manuscript arguments, sections, and initial-submission materials from author-provided evidence. Use for 论文写作、章节起草、论证重构、正文压缩、首次投稿材料. Use nature-polishing for language-on | 写论文, 手稿撰写, 起草摘要, 写引言, 写讨论, 投稿信, manuscript drafting, 章节起草, 正文压缩, 论证重构, Methods小节, 写方法学, 首次投稿材料 | RED 必触发 |
| 75 | openfold3 | OpenAI4S 移植:Structure prediction using OpenFold3, an open-weights PyTorc... | openfold3 | YEL 讨论触发 |
| 76 | paper-polish | 学术论文润色:语法/流畅度修复、语气按证据强度校准、去除AI腔、中译英投稿级改写；绝不编造数据/引用/主张 | 润色, 论文润色, 去AI腔, 去除AI味, AI味, 中译英, 翻译成英文, 语言修改, awkward wording, overclaiming, 语言润色 | RED 必触发 |
| 77 | patent-analysis | 用户说"分析这篇专利""拆解这个专利""专利详细解读""解读专利""分析权利要求""竞品专利分析"等时触发。 | patent-analysis, patent analysis, patent | YEL 讨论触发 |
| 78 | pdf-report-generation | PDF报告生成:分析结果/图表/表格→LaTeX/HTML→PDF报告→自动排版→可重复生成 | pdf-report-generation, pdf report generation, pdf | YEL 讨论触发 |
| 79 | pdf-translate | 适用于: 学术论文翻译, 保留排版PDF翻译, 公式和图表保留翻译, 中英对照PDF生成 | pdf-translate, pdf translate, pdf, translate | YEL 讨论触发 |
| 80 | pdf_reader | 当你需要 PDF 文献读取器 时触发 —— 读取 PDF 论文，提取正文、图表、表格、元数据，支持批量处理和 Markdown 转换 | pdf_reader, pdf reader, pdf, reader | YEL 讨论触发 |
| 81 | platform-execution-pitfalls | 任何会话遇到 execute_r / execute_code / skill_view / rail_review / terminal 门禁相关的非数据类报错时先查本 skill；写 R/Python 分析代码前快速扫一遍坑表。 | platform, execution, pitfalls | YEL 讨论触发 |
| 82 | ppt-generator | 当你需要 PPT生成 时触发 —— AI驱动的PPT生成系统，支持16:9暗色主题，自动布局，图表插入 | PPT, 幻灯片, 演示文稿, 组会, ppt-generator, ppt generator, 做PPT | RED 必触发 |
| 83 | ppt-html | 适用于: 文献解读后生成HTML报告 —— 图文并茂的HTML文献报告生成，支持9项结构化总结+Figure展示 | ppt-html, ppt html, ppt, html | YEL 讨论触发 |
| 84 | ppt-master | 适用于: 文献解读后生成PPT, 分析报告制作PPT —— AI驱动的SVG-PPT生成系统，多角色协作:策划→执行→质量检查→导出 | ppt-master, ppt master, ppt, master | YEL 讨论触发 |
| 85 | pptx-generation | PPTX文件生成:内容/图表→python-pptx→专业排版→图表嵌入→PowerPoint文件 | pptx-generation, pptx generation, pptx | YEL 讨论触发 |
| 86 | pre-submission-reviewer | 论文已写完、临近投稿（1周内），需要投稿前全面体检时使用。路由纪律:nature-reviewer 判科学质量（Nature五轴:原创性/重要性/技术严谨性，用户说'Nature预审/预审科学质量'走它），academic-paper-reviewer 是模拟完整同行评审（用户说'审稿/模拟审稿人'走它）… | 投稿前审查, 投稿前检查, 投前审, 查草稿, 检查草稿, 投稿前体检, 找问题, proofread, check the draft, find issues, 语法检查, 图表质量, AI腔 | RED 必触发 |
| 87 | professional-paper-interpretation | 专业编辑视角论文解读:叙事逻辑分析 + 研究思路拆解 + 结构化写作逻辑。区别于 paper-summary 的字段导向提取，本 skill 侧重'作者为什么这样做、逻辑链是什么、文章怎么组织的'。触发词:专业编辑角度、编辑视角、研究思路、这篇文章讲了什么、帮我解读一下、这篇文章做了什么、帮我从编辑角度分析 | 专业编辑角度, 编辑视角, 研究思路, 这篇文章讲了什么, 帮我解读一下, 这篇文章做了什么, 帮我从编辑角度分析 | YEL 讨论触发 |
| 88 | proteinmpnn | OpenAI4S 移植:Inverse-fold a protein backbone (PDB structure) into amino-a... | proteinmpnn | YEL 讨论触发 |
| 89 | proteomics-secretome-analysis | conditioned medium secretome, supernatant proteomics | 分泌蛋白组, secretome, 条件培养基, 上清蛋白, conditioned medium | YEL 讨论触发 |
| 90 | public-data-download | 精确下载公共组学数据集（指定物种+组织+assay类型）。不做全量调查，直接搜最佳候选并开始下载。 | public-data-download, public data download, public | YEL 讨论触发 |
| 91 | pubmed-mesh-annotation | 用户要求给文献输出 MeSH 标签 / MeSH 主要主题词 / 语义索引标注 / 给论文打 MeSH 词时加载。核心知识:query_ncbi esummary 不含 MeSH，必须用 efetch MEDLINE 格式提取 MH 行，* 前缀 = Major Topic。 | pubmed-mesh-annotation, pubmed mesh annotation, pubmed, mesh, annotation | YEL 讨论触发 |
| 92 | pubmed-mesh-indexing | 为论文输出官方 MeSH 主要标签（TaskA 式语义索引 benchmark） | MeSH, DeCS, 语义索引, 主要标签, mesh tags, MESINESP | YEL 讨论触发 |
| 93 | sankey-alluvial-figures | 桑基图/冲积图（Sankey / Alluvial / 流向图）的布局归一化与几何自检:节点高度必须按「可用高度」归一而非按数据权重 列间隙用固定比例、相邻节点禁止重叠，标签中心必须与所属色块中心重合（像素级断言）。含多组共同 DEG 流向图 （亚群 ↔ 基因、三组共同上/下调）的版式惯例、四格式导出与改版备份规程。 触发:桑基图 / 冲积图 / sankey / alluvial / 流向图 | sankey-alluvial-figures, sankey alluvial figures, sankey, alluvial, figures | YEL 讨论触发 |
| 94 | sankey-alluvial-layout | 桑基图／冲积图（Sankey/Alluvial）的节点布局与带宽保真度:间隙归一化、节点最小高度与高度守恒再分配 「带宽 ∝ 权重」被破坏后的量化与图注声明、节点条↔标签的渲染像素级对齐核验。 触发:桑基图 / 冲积图 / Sankey / alluvial / 流图 / 节点太小 / 标签挂在两块之间 / 带宽 / _node height。 | sankey-alluvial-layout, sankey alluvial layout, sankey, alluvial, layout | YEL 讨论触发 |
| 95 | scgpt | OpenAI4S 移植:Embed and annotate single-cell expression data with scGPT, a... | scgpt | YEL 讨论触发 |
| 96 | scientific-figure-export | 用户问导出的图太大/太糊/保存尺寸/dpi/格式选择/透明底白底时触发；**也覆盖已渲染位图的字号合规审计与「为什么改不了字体」**（量已发表论文配图或自己导出图的真实 pt 值、判是否达 5pt 下沿、解释位图无字体对象/无矢量母版）。明确面向投稿发表的导出决策，不负责图型选择。 | 图太大, 图很糊, 导出尺寸, dpi, 保存格式, PNG还是PDF, pngquant | YEL 讨论触发 |
| 97 | scipilot-figure-skill | 用户给了一个 CSV / Excel / DataFrame 说"帮我画一下"或"用什么图好" | 柱状图, 箱线图, 散点图, 折线图, 分布图, 相关性矩阵, 画图, 数据可视化, 发表级, 作图, 出图, 画个图 | RED 必触发 |
| 98 | scrna-cns-figure-design | CNS-level single-cell RNA-seq figure architecture and implementation. Covers condition-resolved UMAP with density contours, continuum scoring multi-condition perturbation vector fields… | scrna-cns-figure-design, scrna cns figure design, cns | YEL 讨论触发 |
| 99 | scrna-trajectory-analysis | [trajectory-analysis] scRNA-seq 轨迹推断/拟时序分析/RNA velocity/发育分化。使用场景:已聚类的 scRNA-seq 数据，需重建发育/衰老/分化轨迹，伪时间排序，RNA velocity 分析。 | trajectory | YEL 讨论触发 |
| 100 | skill-registration-and-routing | 新建/改动词技能后让它真的能被触发:SKILLS_INDEX 重建、trigger_keywords 优先级与回填覆盖、WebUI 扫描根、路由矩阵用例、skills-gate 提交门禁。触发:新技能注册后命不中 / matcher 返回空 / 触发不生效 / 索引重建 / 技能门禁。 | 技能注册, 触发生效, 触发不生效, 命不中, 索引重建, SKILLS_INDEX, trigger_keywords, 技能门禁, skills-gate, skill_routing_matrix, register_skill, 路由矩阵, 技能没被触发, 新建技能, 触发词回填, matcher命中为空 | RED 必触发 |
| 101 | statistical-design-review | 审查/审计已提出的统计方案与实验设计:分析单位（伪重复）、多重比较校正、比例/组成数据的相关分析、样本量与功效、预注册。触发:\"审一下这个统计方案\" / \"指出问题并给出正确做法\" / \"这样用 t 检验两两比较合适吗\" / \"Pearson 分析相关性对不对\" / \"每组 6 只够吗\" / 统计设计审查 / statistical plan review / pseudore | 审统计方案, 统计方案审查, 统计设计审查, 实验单位, 伪重复, pseudoreplication, 多重比较, 两两 t 检验, 每组 6 只, Pearson 相关, 比例相关, 功效不足, 统计方法审查, statistical plan review | RED 必触发 |
| 102 | summarize | 智能总结分析结果/文献/对话/数据:自动识别用户想总结什么（分析结果、文献、对话历史、数据概况），生成结构化摘要。支持生信分析结果总结、文献要点提取、长对话浓缩、数据统计概览。 | summarize | YEL 讨论触发 |
| 103 | user-script-figure-optimization | 用户消息里含一段**可运行的绘图代码** + 任何风格/级别/期刊字样 | 按 nature 优化」「帮我改一下我的脚本 | YEL 讨论触发 |
| 104 | wakeup-progress-check | 新唤醒验证与上条**有细节差异**（基线组件 14→12、PID 名单变化）但结论同为终态；此时 #109 的「合并正文为最新」会丢 #117 的独立证据、#107 的「扩块加 bullet」又仅为合并块设计 → 混合变体 = 单条块转范围块 + 双 bullet，一个 patch（锚点 = 标题行 + 原 bullet 两行连续）完成，块数不增、两组验证细节都在… | wakeup-progress-check, wakeup progress check, wakeup, progress | YEL 讨论触发 |
| 105 | windows-bioinformatics-batch-processing | 在Windows上启动长时间运行的生信批量任务（10+样本，每样本>5分钟）时加载，确保进程不因会话中断而死亡，LLM主动监控进度。系统唤醒(#N)主线进度检查也适用 — 协议见 references/agent-side-wakeup-check.md | windows, batch, processing | YEL 讨论触发 |
| 106 | windows-com-app-automation | 用 Windows COM + 脚本引擎确定性地驱动桌面应用（Illustrator/Photoshop/InDesign/Word/Excel）:cscript→VBScript→CreateObject→DoJavaScriptFile/DoScript 桥，ExtendScript ES3 手拼 JSON、隔离文档写操作的安全模式、可复制的 doctor/探测脚手架。 | Illustrator自动化, 操控Illustrator, 批量改Illustrator, Illustrator脚本, ExtendScript, JSX脚本, COM自动化, Photoshop自动化, InDesign自动化, 脚本控制软件, 软件没有CLI, 桌面软件自动化, 图内文字批量改, cscript, DoJavaScriptFile, 画板操作 | RED 必触发 |

## 09_内置 - Hermes系统 (20 skills)

| # | Skill | 使用场景 | 触发词 | Trigger |
|---|---|---|---|---|
| 1 | adaptyv-api | Complete API reference for Adaptyv Bio's protein characterization platform. Use when the user wants to run experiments on Adaptyv. | adaptyv-api, adaptyv api, adaptyv, api | GRN 按需触发 |
| 2 | analysis-output-validity-gates | 生信流程「跑完 ≠ 结果有效」的产出有效性自证门 + 失败归因（内存 vs 代码）。覆盖静默无效产出（exit 0、日志全 ✓、文件齐全但数值全是垃圾，如 AUCell 矩阵全 0、regulon 基因变单字符）与归因错层（把 dask worker OOM 当代码 bug 反复改）。触发:跑完了/为什么全是0/结果可疑/AUCell全0/产出无效/exit 0 但没结果/FutureCancel | output, validity, gates | YEL 讨论触发 |
| 3 | cli-anything | 通过 CLI-Anything（HKUDS）把桌面/后端软件变成 agent-native CLI 来操控:用 cli-hub 装现成 CLI（gimp/inkscape/blender/freecad/qgis/zotero/obsidian/blender…71 个），或按官方 7 阶段规范自建 harness（含 Illustrator COM/ExtendScript 实战范例）… | CLI-Anything, cli-hub, 操控软件, 操控, 软件自动化, 批量控制桌面软件, agent-native CLI, harness, 做个CLI, 做个命令行, 包装成CLI, 批量改, 统一字号, inkscape, 矢量图批量, 批处理软件 | RED 必触发 |
| 4 | code-writer | 当你需要 代码编写 时触发 —— 编写Python/R脚本，数据分析代码，函数封装，程序开发 | code-writer, code writer, code, writer | GRN 按需触发 |
| 5 | computer-use | 用户要截屏、看屏幕、点按钮、在桌面软件里输入文字、切换窗口时触发；唯一入口是 Hermes 的 computer_use 工具 | computer-use, computer use, computer, 截屏, 截图, 截个屏, 屏幕截图, 看屏幕, 操作电脑, 控制电脑, 桌面软件, 键盘输入, 点击按钮 | GRN 按需触发 |
| 6 | create-bio-skill | 当 skill_view 返回 not found 且没有相似 skill，或用户指定了特定包需要创建新 skill 时触发 | 安装, 创建skill, 没有这个工具, 新工具, 做一个skill, 建个skill, 没有对应的skill, create-bio-skill | RED 必触发 |
| 7 | data-analysis-best-practices | Best practices for data analyses with focused on user supplied data. | 最佳实践, best practice, guideline, practices | RED 必触发 |
| 8 | data-viz | 当你需要 数据可视化 时触发 —— 绘制高质量数据可视化图表:UMAP/tSNE/热图/火山图/小提琴图等 | data-viz, data viz, viz | GRN 按需触发 |
| 9 | deg-updown-counts-by-subcluster | 已有算好的「比较组 × 亚群 × 方向」基因计数矩阵，要出各亚群上下调基因数量对比柱状图（如 5 个比较组并排展示） | DEG 各比较组亚群基因数量图, updown 8sub 柱状图, 上调下调数量柱状图, 五面板统一 symlog 柱状图 | GRN 按需触发 |
| 10 | deg-volcano-5comps-8sub-R | 已有多个比较组的 DEG 表（每 sheet 一对比），要出「一对比一张、图内含 8 个亚群色块」的火山图；或需要给某基因补标 | 火山图 R 版, 5 比较组 8 亚群火山图, DEG 火山图带亚群标签块, volcano 8sub FINAL | GRN 按需触发 |
| 11 | error-recovery | 当终端运行脚本报错，或用户说'报错了'/'error'/'出错了'/'报错怎么修'/'这什么错'时触发 | 报错, 报错信息, 出错, 报错怎么修, 不工作, 跑不了, 调试, traceback, error message | RED 必触发 |
| 12 | experimental-design-statistics | 当你需要 实验设计统计 时触发 —— 实验设计+统计检验: 样本量估算 → 方法选择 → 结果检验 | 样本量, 功效分析, power analysis, 实验设计, 统计方法, 统计检验 | RED 必触发 |
| 13 | fig-split-program-heatmap-R | 用户要求把 fig_split_v10.py 式矩阵热图（18 程序打分 × 6组/5效应/亚群）转成 R，或直接用 R 出这套图 | fig_split_v10 的 R 版, 18 程序打分热图出 R 版, 6组×亚群矩阵热图 R | GRN 按需触发 |
| 14 | file-convert | 当你需要 格式转换 时触发 —— 数据格式转换:CSV/Excel/TSV/H5AD/MTX等常见格式互转 | file-convert, file convert, file, convert | GRN 按需触发 |
| 15 | find-skill | 智能搜索可用技能:当用户需要某个分析功能但不确定有没有现成技能时，自动搜索239个内置技能+外部蓝图，找到最匹配的并推荐安装。也支持用户说'有没有XXX的技能'时触发。 | find-skill, find skill, find | GRN 按需触发 |
| 16 | heart-conference-monitor | 心脏会议监控:追踪心脏病学会议→提取关键发现→监控研究趋势→生成报告 | heart-conference-monitor, heart conference monitor, heart, conference, monitor | GRN 按需触发 |
| 17 | heartbeat-monitor | 长任务心跳监控 — 独立后台进程持续记录进度，Agent 随时读取汇报 | 心跳, 监控, heartbeat, 进度汇报, 跑多久了, 还在跑吗, heartbeat-monitor, heartbeat monitor | RED 必触发 |
| 18 | ml-classification | 适用于: disease, 有标签数据, 分类/预测 —— LASSO+RandomForest+SVM+SHAP解释, 支持bulk和scRNA | ml-classification, ml classification, classification | GRN 按需触发 |
| 19 | phylo-create-skill | Create, test, package, and present reusable skills for Phylo's Biomni platform and bioinformatics workflows. | phylo-create-skill, phylo create skill, phylo | GRN 按需触发 |
| 20 | self-improving-agent | 自进化能力:分析成功后自动沉淀经验为新技能；分析失败后自动学习错误模式避免重复犯错；根据使用频率自动优化参数。包括技能沉淀、错误学习、参数进化三大子系统。 | self-improving-agent, self improving agent, self, improving, agent | GRN 按需触发 |

## 10_多组学整合 - 多组学整合 (11 skills)

| # | Skill | 使用场景 | 触发词 | Trigger |
|---|---|---|---|---|
| 1 | generate_embeddings_with_state | When you need generate embeddings with state analysis | embeddings, state | YEL 讨论触发 |
| 2 | generate_transcriptformer_embeddings | When you need generate transcriptformer embeddings analysis | transcriptformer, embeddings | YEL 讨论触发 |
| 3 | get_uce_embeddings_scRNA | When you need get uce embeddings scRNA analysis | get_uce_embeddings_scRNA, get uce embeddings scRNA, uce, embeddings | YEL 讨论触发 |
| 4 | lipidomics-summary-stats | 脂质组学统计汇总:脂质定量数据→描述统计→差异分析→脂质类别分布→可视化 | lipidomics-summary-stats, lipidomics summary stats, lipidomics, stats | YEL 讨论触发 |
| 5 | map_to_ima_interpret_scRNA | When you need map to ima interpret scRNA analysis | map, ima, interpret | YEL 讨论触发 |
| 6 | multi-omics-integration | 当你需要 多组学整合 (MOFA+) 时触发 —— MOFA+/DIABLO多组学整合。RNA+ATAC+Protein联合分析 | 多组学, multi-omics, 多组学整合, multi-omics-integration, multi omics integration, 联合分析 | RED 必触发 |
| 7 | perform_gene_expression_nmf_analysis | When you need perform gene expression nmf analysis analysis | gene, expression, nmf | YEL 讨论触发 |
| 8 | rgcca-multiblock | RGCCA多组学整合分析:多个数据块→正则化典型相关→共享变异→跨组学关联→组分可视化 | rgcca-multiblock, rgcca multiblock, rgcca, multiblock | YEL 讨论触发 |
| 9 | simulate_renin_angiotensin_system_dynamics | When you need simulate renin angiotensin system dynamics analysis | simulate, renin, angiotensin, dynamics | YEL 讨论触发 |
| 10 | split_modalities | When you need split modalities analysis | split_modalities, split modalities, split, modalities | YEL 讨论触发 |
| 11 | unsupervised_celltype_transfer_between_scRNA_datasets | When you need unsupervised celltype transfer between scRNA datasets analysis | unsupervised, celltype, transfer, between | YEL 讨论触发 |

## 11_文献搜索 - 文献/数据库 (66 skills)

| # | Skill | 使用场景 | 触发词 | Trigger |
|---|---|---|---|---|
| 1 | academic-paper-writing | 适用于: 学术论文写作 —— 12-agent论文写作流水线，从大纲到完稿 | 写论文, 写文章, 论文写作, 论文初稿, academic-paper-writing, academic paper writing, academic, 英文论文写作 | RED 必触发 |
| 2 | academic-research | 适用于: 实验方案设计, 研究规划, 文献综述 —— 综合学术研究技能:实验方案设计、文献检索、研究规划 | 基金申请, 课题申请, 立项依据, 开题报告, 标书, grant proposal, academic-research, academic research | RED 必触发 |
| 3 | advanced_web_search_claude | When you need advanced web search claude analysis | advanced, web, search, claude | YEL 讨论触发 |
| 4 | deep-research | 适用于: 深度文献研究, 系统性综述 —— 13-agent深度研究团队，系统性文献检索+综述+PRISMA | 深度调研, 全面调研, deep research, deep-research | RED 必触发 |
| 5 | extract_pdf_content | When you need extract pdf content analysis | extract_pdf_content, extract pdf content, extract, pdf, content | YEL 讨论触发 |
| 6 | extract_url_content | When you need extract url content analysis | extract_url_content, extract url content, extract, url, content | YEL 讨论触发 |
| 7 | fetch_supplementary_info_from_doi | When you need fetch supplementary info from doi analysis | supplementary, info, doi | YEL 讨论触发 |
| 8 | knowledge-base-curation | Auto-generated for knowledge-base-curation | knowledge-base-curation, knowledge base curation, knowledge, base, curation | YEL 讨论触发 |
| 9 | literature-param-extraction | 拿到真实数据要分析但知识库无参数时；search_knowledge 返回 0 条或 confidence=low 时；用户要求从文献提取参数时 | 提取参数, 文献参数, parameter extraction, 实验参数, 参数提取 | RED 必触发 |
| 10 | literature-preclinical | 当你需要 临床前文献提取 时触发 —— 从临床前文献提取关键发现、方法、模型、剂量。PubMed+LLM | literature-preclinical, literature preclinical, preclinical | YEL 讨论触发 |
| 11 | literature-review | Auto-generated for literature-review | 文献综述, literature review, 综述, systematic review, 总结文献, 查文献, evidence synthesis | RED 必触发 |
| 12 | nature-academic-search | Search literature across sources, verify or manage citations, and build MeSH strategies or citation-impact audits. Use for 文献检索、引文核对、参考文献管理、严格他引 and evidence-backed citer profiles; not for translating | 多源文献检索, 引文核对, 参考文献管理, 严格他引, MeSH词表, 检索桥, 查PubMed和Crossref, 多源检索 | RED 必触发 |
| 13 | nature-citation | Find and verify Nature/CNS-family literature supporting manuscript claims, with claim-to-source mapping and reference-manager export. Use for Nature系列引用、CNS支撑文献、分段补引用 when this journal scope is reques | 找引用, 补引用, 引用匹配, 论点找文献, 引用溯源, claim引用, citation | RED 必触发 |
| 14 | nature-literature-pipeline | Complete automated literature discovery pipeline: multi-source search → six-dimension scoring → fine reading → formatted delivery → archival. Combines a configurable engine with daily cron-driven appl | 文献流水线, 文献追踪, 每日文献, 文献筛选, 文献打分, 批量筛文献, 文献推送 | RED 必触发 |
| 15 | nature-ref-verifier | 对学术文献逐条执行多源交叉验证，逐字段对比作者、标题、年份、卷期、页码 标记卷年/DOI年冲突、作者顺序异常、页码偏差等问题，输出结构化验证报告。 可批量处理整篇论文/开题报告的参考文献列表，也可单条校验，支持与 Zotero 同步修正。 | 核对参考文献, 参考文献核对, 校验文献, 文献验证, 引用核对, 参考文献错误, DOI校验, reference check | RED 必触发 |
| 16 | omics-dataset-retrieval | 当你需要 组学数据集检索 (GEO/SRA) 时触发 —— GEO/SRA数据集检索和下载。元数据解析和筛选 | 公共数据, 下载数据集, GEO数据, omics-dataset-retrieval, omics dataset retrieval, 公共数据集, GEO数据集 | RED 必触发 |
| 17 | paper-download | 当你需要 文献下载 时触发 —— 搜索并下载学术论文PDF，支持arXiv/PubMed/bioRxiv等平台 | 搜文献, 找论文, 下载论文, paper-download, paper download, 下载文献, PDF下载 | RED 必触发 |
| 18 | paper-summary | 当你需要 AI文献总结 时触发 —— 深度AI文献解读:全文提取→结构化总结(15字段)→图表提取→报告生成 | 总结论文, 解读, summarize paper, 精读, 论文要点, 讲一下这篇 | RED 必触发 |
| 19 | paper-translate | 当你需要 PDF翻译 时触发 —— 保留排版的PDF全文翻译，支持中英互译 | paper-translate, paper translate, translate | YEL 讨论触发 |
| 20 | query_alphafold | When you need query alphafold analysis | query_alphafold, query alphafold, alphafold | YEL 讨论触发 |
| 21 | query_arxiv | When you need query arxiv analysis | query_arxiv, query arxiv, arxiv | YEL 讨论触发 |
| 22 | query_cbioportal | When you need query cbioportal analysis | query_cbioportal, query cbioportal, cbioportal | YEL 讨论触发 |
| 23 | query_chatnt | When you need query chatnt analysis | query_chatnt, query chatnt, chatnt | YEL 讨论触发 |
| 24 | query_chembl | When you need query chembl analysis | query_chembl, query chembl, chembl | YEL 讨论触发 |
| 25 | query_clinicaltrials | When you need query clinicaltrials analysis | query_clinicaltrials, query clinicaltrials, clinicaltrials | YEL 讨论触发 |
| 26 | query_clinvar | When you need query clinvar analysis | query_clinvar, query clinvar, clinvar | YEL 讨论触发 |
| 27 | query_dailymed | When you need query dailymed analysis | query_dailymed, query dailymed, dailymed | YEL 讨论触发 |
| 28 | query_dbsnp | When you need query dbsnp analysis | query_dbsnp, query dbsnp, dbsnp | YEL 讨论触发 |
| 29 | query_drug_interactions | When you need query drug interactions analysis | query_drug_interactions, query drug interactions, drug, interactions | YEL 讨论触发 |
| 30 | query_emdb | When you need query emdb analysis | query_emdb, query emdb, emdb | YEL 讨论触发 |
| 31 | query_encode | When you need query encode analysis | query_encode, query encode, encode | YEL 讨论触发 |
| 32 | query_ensembl | When you need query ensembl analysis | query_ensembl, query ensembl, ensembl | YEL 讨论触发 |
| 33 | query_fda_adverse_events | When you need query fda adverse events analysis | query_fda_adverse_events, query fda adverse events, fda, adverse, events | YEL 讨论触发 |
| 34 | query_geo | When you need query geo analysis | query_geo, query geo, geo | YEL 讨论触发 |
| 35 | query_gnomad | When you need query gnomad analysis | query_gnomad, query gnomad, gnomad | YEL 讨论触发 |
| 36 | query_gtopdb | When you need query gtopdb analysis | query_gtopdb, query gtopdb, gtopdb | YEL 讨论触发 |
| 37 | query_gwas_catalog | When you need query gwas catalog analysis | query_gwas_catalog, query gwas catalog, gwas, catalog | YEL 讨论触发 |
| 38 | query_interpro | When you need query interpro analysis | query_interpro, query interpro, interpro | YEL 讨论触发 |
| 39 | query_iucn | When you need query iucn analysis | query_iucn, query iucn, iucn | YEL 讨论触发 |
| 40 | query_jaspar | When you need query jaspar analysis | query_jaspar, query jaspar, jaspar | YEL 讨论触发 |
| 41 | query_kegg | When you need query kegg analysis | query_kegg, query kegg, kegg | YEL 讨论触发 |
| 42 | query_monarch | When you need query monarch analysis | query_monarch, query monarch, monarch | YEL 讨论触发 |
| 43 | query_mpd | When you need query mpd analysis | query_mpd, query mpd, mpd | YEL 讨论触发 |
| 44 | query_openfda | When you need query openfda analysis | query_openfda, query openfda, openfda | YEL 讨论触发 |
| 45 | query_opentarget | When you need query opentarget analysis | query_opentarget, query opentarget, opentarget | YEL 讨论触发 |
| 46 | query_paleobiology | When you need query paleobiology analysis | query_paleobiology, query paleobiology, paleobiology | YEL 讨论触发 |
| 47 | query_pdb | When you need query pdb analysis | query_pdb, query pdb, pdb | YEL 讨论触发 |
| 48 | query_pdb_identifiers | When you need query pdb identifiers analysis | query_pdb_identifiers, query pdb identifiers, pdb, identifiers | YEL 讨论触发 |
| 49 | query_pride | When you need query pride analysis | query_pride, query pride, pride | YEL 讨论触发 |
| 50 | query_pubchem | When you need query pubchem analysis | query_pubchem, query pubchem, pubchem | YEL 讨论触发 |
| 51 | query_pubmed | When you need query pubmed analysis | query_pubmed, query pubmed, pubmed | YEL 讨论触发 |
| 52 | query_quickgo | When you need query quickgo analysis | query_quickgo, query quickgo, quickgo | YEL 讨论触发 |
| 53 | query_reactome | When you need query reactome analysis | query_reactome, query reactome, reactome | YEL 讨论触发 |
| 54 | query_regulomedb | When you need query regulomedb analysis | query_regulomedb, query regulomedb, regulomedb | YEL 讨论触发 |
| 55 | query_remap | When you need query remap analysis | query_remap, query remap, remap | YEL 讨论触发 |
| 56 | query_scholar | When you need query scholar analysis | query_scholar, query scholar, scholar | YEL 讨论触发 |
| 57 | query_stringdb | When you need query stringdb analysis | query_stringdb, query stringdb, stringdb | YEL 讨论触发 |
| 58 | query_synapse | When you need query synapse analysis | query_synapse, query synapse, synapse | YEL 讨论触发 |
| 59 | query_ucsc | When you need query ucsc analysis | query_ucsc, query ucsc, ucsc | YEL 讨论触发 |
| 60 | query_unichem | When you need query unichem analysis | query_unichem, query unichem, unichem | YEL 讨论触发 |
| 61 | query_uniprot | When you need query uniprot analysis | query_uniprot, query uniprot, uniprot | YEL 讨论触发 |
| 62 | query_worms | When you need query worms analysis | query_worms, query worms, worms | YEL 讨论触发 |
| 63 | research-plan | 用户询问"怎么分析"、"用什么方法"、"实验方案"、"技术路线"时自动触发 | 技术路线, 分析路线, 怎么分析, 研究方案, research plan, research-plan, 研究计划, 分析方案 | RED 必触发 |
| 64 | search_google | When you need search google analysis | search_google, search google, search, google | YEL 讨论触发 |
| 65 | translate-book | 用户要求翻译整本书、翻译大段内容、把这本书翻译成中文时使用；需提供文件路径（PDF/DOCX/EPUB）和目标语言 | 翻译整本书, 整书翻译, 翻译这本书, 整本翻译, 把这本书翻译, 翻译全书, 全书翻译, 翻译大段, 大段内容翻译, 大段翻译, 这本书翻译成, translate book, translate the book, translate this book, book translation, 整本书翻成 | RED 必触发 |
| 66 | web-research | 当你需要 网络调研 时触发 —— 网络搜索和调研，获取最新信息，综合多个来源生成报告 | web-research, web research, web, 网络调研 | YEL 讨论触发 |

## 12_分子生物学 - 分子克隆 (21 skills)

| # | Skill | 使用场景 | 触发词 | Trigger |
|---|---|---|---|---|
| 1 | align_sequences | When you need align sequences analysis | align_sequences, align sequences, align, sequences | YEL 讨论触发 |
| 2 | annotate_open_reading_frames | When you need annotate open reading frames analysis | annotate, open, reading, frames | YEL 讨论触发 |
| 3 | annotate_plasmid | When you need annotate plasmid analysis | annotate_plasmid, annotate plasmid, annotate, plasmid | YEL 讨论触发 |
| 4 | blast_sequence | When you need blast sequence analysis | blast_sequence, blast sequence, blast, sequence | YEL 讨论触发 |
| 5 | design_golden_gate_oligos | When you need design golden gate oligos analysis | golden gate, golden, gate, oligos | YEL 讨论触发 |
| 6 | design_primer | When you need design primer analysis | design_primer, design primer, primer | YEL 讨论触发 |
| 7 | design_verification_primers | When you need design verification primers analysis | verification primers, verification, primers | YEL 讨论触发 |
| 8 | digest_sequence | When you need digest sequence analysis | digest_sequence, digest sequence, digest, sequence | YEL 讨论触发 |
| 9 | find_restriction_enzymes | When you need find restriction enzymes analysis | find_restriction_enzymes, find restriction enzymes, find, restriction, enzymes | YEL 讨论触发 |
| 10 | find_restriction_sites | When you need find restriction sites analysis | find_restriction_sites, find restriction sites, find, restriction, sites | YEL 讨论触发 |
| 11 | get_gene_coding_sequence | When you need get gene coding sequence analysis | get_gene_coding_sequence, get gene coding sequence, gene, coding, sequence | YEL 讨论触发 |
| 12 | get_golden_gate_assembly_protocol | When you need get golden gate assembly protocol analysis | golden, gate, assembly, protocol | YEL 讨论触发 |
| 13 | get_oligo_annealing_protocol | When you need get oligo annealing protocol analysis | oligo, annealing, protocol | YEL 讨论触发 |
| 14 | get_plasmid_sequence | When you need get plasmid sequence analysis | get_plasmid_sequence, get plasmid sequence, plasmid, sequence | YEL 讨论触发 |
| 15 | golden_gate_assembly | When you need golden gate assembly analysis | golden_gate_assembly, golden gate assembly, golden, gate, assembly | YEL 讨论触发 |
| 16 | interspecies_gene_conversion | When you need interspecies gene conversion analysis | interspecies, gene, conversion | YEL 讨论触发 |
| 17 | microplate-layout-design | Design optimized microplate layouts with randomization, edge effect mitigation, and covariate balancing. | microplate-layout-design, microplate layout design, microplate, layout | YEL 讨论触发 |
| 18 | pcr-primer-design | 当你需要 PCR 引物设计 时触发 —— PCR引物设计: Primer3 → 特异性验证 | pcr-primer-design, pcr primer design, pcr, primer | YEL 讨论触发 |
| 19 | pcr_simple | When you need pcr simple analysis | pcr_simple, pcr simple, pcr, simple | YEL 讨论触发 |
| 20 | perform_pcr_and_gel_electrophoresis | When you need perform pcr and gel electrophoresis analysis | pcr, gel, electrophoresis | YEL 讨论触发 |
| 21 | phylogenetics-toolkit | 系统发育分析工具包:序列比对→建树(ML/NJ/MP)→树可视化→进化距离→祖先重建 | phylogenetics-toolkit, phylogenetics toolkit, phylogenetics, toolkit | YEL 讨论触发 |

## 13_组织学病理 - 组织学/病理 (5 skills)

| # | Skill | 使用场景 | 触发词 | Trigger |
|---|---|---|---|---|
| 1 | analyze_thrombus_histology | When you need analyze thrombus histology analysis | thrombus, histology | YEL 讨论触发 |
| 2 | quantify_amyloid_beta_plaques | When you need quantify amyloid beta plaques analysis | quantify, amyloid, beta, plaques | YEL 讨论触发 |
| 3 | quantify_cell_cycle_phases_from_microscopy | When you need quantify cell cycle phases from microscopy analysis | quantify, cell cycle, cycle, phases | YEL 讨论触发 |
| 4 | quantify_corneal_nerve_fibers | When you need quantify corneal nerve fibers analysis | quantify, corneal, nerve, fibers | YEL 讨论触发 |
| 5 | run_3d_chondrogenic_aggregate_assay | When you need run 3d chondrogenic aggregate assay analysis | chondrogenic, aggregate, assay | YEL 讨论触发 |

## 14_细胞生物学实验 - 细胞生物学 (6 skills)

| # | Skill | 使用场景 | 触发词 | Trigger |
|---|---|---|---|---|
| 1 | analyze_cell_senescence_and_apoptosis | When you need analyze cell senescence and apoptosis analysis | cell senescence, senescence, apoptosis | YEL 讨论触发 |
| 2 | analyze_cfse_cell_proliferation | When you need analyze cfse cell proliferation analysis | cfse, cell proliferation, proliferation | YEL 讨论触发 |
| 3 | isolate_purify_immune_cells | When you need isolate purify immune cells analysis | isolate, purify, immune, cells | YEL 讨论触发 |
| 4 | perform_facs_cell_sorting | When you need perform facs cell sorting analysis | facs, cell sorting, sorting | YEL 讨论触发 |
| 5 | secretome-classification | ✅ Conditioned medium / supernatant proteomics (LC-MS/MS, label-free, TMT) | secretome-classification, secretome classification, secretome, classification | YEL 讨论触发 |
| 6 | track_immune_cells_under_flow | When you need track immune cells under flow analysis | track, immune, cells, under | YEL 讨论触发 |

## 15_CRISPR基因编辑 - CRISPR (4 skills)

| # | Skill | 使用场景 | 触发词 | Trigger |
|---|---|---|---|---|
| 1 | analyze_crispr_genome_editing | When you need analyze crispr genome editing analysis | crispr, genome, editing | YEL 讨论触发 |
| 2 | design_knockout_sgrna | When you need design knockout sgrna analysis | design_knockout_sgrna, design knockout sgrna, knockout, sgrna | YEL 讨论触发 |
| 3 | pooled-crispr-screens | 当你需要 CRISPR 筛选分析 时触发 —— Pooled CRISPR: MAGeCK → 基因必需性 | pooled-crispr-screens, pooled crispr screens, pooled, crispr, screens | YEL 讨论触发 |
| 4 | sgrna-design | sgRNA设计:基因序列→CRISPR靶点扫描→效率+脱靶评分→最优sgRNA推荐→文库设计 | sgrna-design, sgrna design, sgrna | YEL 讨论触发 |
