# MemOmics SKILLS_INDEX

> LLM startup ephemeral prompt

| icon | level | info |
|---|---|
| RED | 必触发 | user mentions -> skill_view immediately |
| YEL | 讨论触发 | confirm plan first then trigger |
| GRN | 按需触发 | only on explicit mention |
| WHT | 系统级 | Hermes internal |

---

## 01_RNA - 单细胞转录组 (44 skills)

| # | Skill | Description | Keywords | Trigger |
|---|---|---|---|---|
| 1 | analyze_cas9_mutation_outcomes |  | rna, scrna, scrnaseq | YEL 讨论触发 |
| 2 | analyze_ciliary_beat_frequency |  | rna, scrna, scrnaseq | YEL 讨论触发 |
| 3 | analyze_flow_cytometry_immunophenotyping |  | rna, scrna, scrnaseq | YEL 讨论触发 |
| 4 | analyze_rna_secondary_structure_features |  | rna, scrna, scrnaseq | YEL 讨论触发 |
| 5 | annotate_celltype_scRNA | 基于marker基因和标签转移的LLM细胞类型注释。使用场景：聚类后需要鉴定细胞身份，有已知marker列表，或需从参考数据集转移标签 | rna, scrna, scrnaseq | YEL 讨论触发 |
| 6 | annotate_celltype_with_panhumanpy |  | rna, scrna, scrnaseq | YEL 讨论触发 |
| 7 | cell-cell-communication |  | rna, scrna, scrnaseq | YEL 讨论触发 |
| 8 | cellbender-remove-background | CellBender去除环境RNA污染。使用场景：10X raw h5矩阵，怀疑有空滴/环境RNA污染，需GPU环境，输入raw_feature_bc_matrix | rna, scrna, scrnaseq | RED 必触发 |
| 9 | cellchat-v2 | CellChat v2配体-受体细胞通讯分析。使用场景：已聚类注释的Seurat对象，需分析细胞间信号通路、配体受体互作、信号角色（发出者/接收者），多条件比较 | rna, scrna, scrnaseq | RED 必触发 |
| 10 | coexpression-network |  | rna, scrna, scrnaseq | YEL 讨论触发 |
| 11 | create_harmony_embeddings_scRNA | Harmony批次校正整合。使用场景：多样本scRNA-seq需去批次效应，快速高效，适合中等数据量（<100万细胞），R/Seurat生态 | rna, scrna, scrnaseq | RED 必触发 |
| 12 | create_scvi_embeddings_scRNA |  | rna, scrna, scrnaseq | YEL 讨论触发 |
| 13 | deg-analysis | Pseudobulk DESeq2+Wilcoxon+MAST多方法差异表达分析。使用场景：已注释的scRNA-seq，需找不同条件/群之间的差异基因，含多重检验校正 | rna, scrna, scrnaseq | RED 必触发 |
| 14 | disease-progression-longitudinal |  | rna, scrna, scrnaseq | YEL 讨论触发 |
| 15 | doubletfinder-remove-doublets |  | rna, scrna, scrnaseq | RED 必触发 |
| 16 | estimate_cell_cycle_phase_durations |  | rna, scrna, scrnaseq | YEL 讨论触发 |
| 17 | functional-enrichment |  | rna, scrna, scrnaseq | RED 必触发 |
| 19 | gene-essentiality |  | rna, scrna, scrnaseq | YEL 讨论触发 |
| 20 | gene_set_enrichment_analysis |  | rna, scrna, scrnaseq | RED 必触发 |
| 21 | get_gene_set_enrichment_analysis_supported_database_list |  | rna, scrna, scrnaseq | RED 必触发 |
| 22 | get_rna_seq_archs4 |  | rna, scrna, scrnaseq | YEL 讨论触发 |
| 23 | grn-pyscenic |  | rna, scrna, scrnaseq | YEL 讨论触发 |
| 24 | hdwgcna |  | rna, scrna, scrnaseq | YEL 讨论触发 |
| 25 | immune-deconvolution |  | rna, scrna, scrnaseq | YEL 讨论触发 |
| 26 | infercnv |  | rna, scrna, scrnaseq | RED 必触发 |
| 27 | lasso-biomarker-panel |  | rna, scrna, scrnaseq | YEL 讨论触发 |
| 28 | pathway-enrichment |  | rna, scrna, scrnaseq | RED 必触发 |
| 29 | quantify_and_cluster_cell_motility |  | rna, scrna, scrnaseq | YEL 讨论触发 |
| 30 | sasp-scoring |  | rna, scrna, scrnaseq | YEL 讨论触发 |
| 31 | scrna-eda | EDA数据探索：QC后的数据概览，含分布图/相关性/主成分 | rna, scrna, scrnaseq, 数据探索, 概览 | RED 必触发 |
| scrna-clustering | 完整Seurat v5聚类注释工作流。使用场景：QC后的scRNA-seq，需SCTransform→PCA→UMAP→聚类→注释→Markers，含SoupX/DoubletFinder/Harmo | rna, scrna, scrnaseq | RED 必触发 |
| 34 | scrna-qc | scRNA-seq质控+Doublet+Ambient RNA去除。使用场景：拿到raw矩阵第一步，需过滤低质量细胞/双胞/环境RNA，自动推荐阈值，支持人/鼠 | rna, scrna, scrnaseq | RED 必触发 |
| 37 | scrnaseq-scanpy-core-analysis |  | rna, scrna, scrnaseq | RED 必触发 |
| 38 | scrnaseq-seurat-core-analysis |  | rna, scrna, scrnaseq | RED 必触发 |
| 39 | sctour-trajectory-inference | scTour VAE 深度潜在时间推断 + 向量场 + 跨数据集预测。无需指定起点，无监督学习细胞动力学。 | rna, scrna, scrnaseq | RED 必触发 |
| 40 | senescence-detection |  | rna, scrna, scrnaseq | YEL 讨论触发 |
| 41 | soupx-remove-background |  | rna, scrna, scrnaseq | RED 必触发 |
| 42 | stratified-subsampling |  | rna, scrna, scrnaseq | YEL 讨论触发 |
| 43 | trajectory-analysis |  | rna, scrna, scrnaseq | RED 必触发 |
| 40 | scrna-eda | EDA数据探索：QC后的数据概览，含分布图/相关性/主成分 | rna, scrna, scrnaseq, 数据探索, 概览 | RED 必触发 |
| 44 | upstream-regulator-analysis |  | rna, scrna, scrnaseq | YEL 讨论触发 |
---

## 02_ATAC - ATAC/染色质 (10 skills)

| # | Skill | Description | Keywords | Trigger |
|---|---|---|---|---|
| 1 | analyze_chromatin_interactions |  | atac, chipseq, atacseq | YEL 讨论触发 |
| 2 | atac-seq | ArchR scATAC-seq 全流程: 环境搭建→Arrow文件→QC→降维→聚类→Peak calling→Motif→Footprinting→差异可及性→共可及性→导出 | atac, chipseq, atacseq | RED 必触发 |
| 3 | chip-atlas-diff-analysis |  | atac, chipseq, atacseq | YEL 讨论触发 |
| 4 | chip-atlas-peak-enrichment |  | atac, chipseq, atacseq | RED 必触发 |
| 5 | chip-atlas-target-genes |  | atac, chipseq, atacseq | YEL 讨论触发 |
| 6 | find_enriched_motifs_with_homer |  | atac, chipseq, atacseq | YEL 讨论触发 |
| 7 | get_genes_near_ccre |  | atac, chipseq, atacseq | YEL 讨论触发 |
| 8 | identify_transcription_factor_binding_sites |  | atac, chipseq, atacseq | YEL 讨论触发 |
| 9 | perform_chipseq_peak_calling_with_macs2 |  | atac, chipseq, atacseq | YEL 讨论触发 |
| 10 | region_to_ccre_screen |  | atac, chipseq, atacseq | YEL 讨论触发 |
---

## 03_空间组 - 空间转录组 (18 skills)

| # | Skill | Description | Keywords | Trigger |
|---|---|---|---|---|
| 1 | analyze_aortic_diameter_and_geometry |  | spatial transcriptomics, visium, merfish | YEL 讨论触发 |
| 2 | analyze_bone_microct_morphometry |  | spatial transcriptomics, visium, merfish | YEL 讨论触发 |
| 3 | analyze_cns_lesion_histology |  | spatial transcriptomics, visium, merfish | RED 必触发 |
| 4 | analyze_hemodynamic_data |  | spatial transcriptomics, visium, merfish | YEL 讨论触发 |
| 5 | analyze_immunohistochemistry_image |  | spatial transcriptomics, visium, merfish | YEL 讨论触发 |
| 6 | batch_register_images |  | spatial transcriptomics, visium, merfish | YEL 讨论触发 |
| 7 | calculate_brain_adc_map |  | spatial transcriptomics, visium, merfish | YEL 讨论触发 |
| 8 | calculate_similarity_metrics |  | spatial transcriptomics, visium, merfish | YEL 讨论触发 |
| 9 | create_registration_visualization |  | spatial transcriptomics, visium, merfish | RED 必触发 |
| 10 | create_segmentation_visualization |  | spatial transcriptomics, visium, merfish | RED 必触发 |
| 11 | prepare_input_for_nnunet |  | spatial transcriptomics, visium, merfish | YEL 讨论触发 |
| 12 | quick_affine_registration |  | spatial transcriptomics, visium, merfish | YEL 讨论触发 |
| 13 | quick_deformable_registration |  | spatial transcriptomics, visium, merfish | YEL 讨论触发 |
| 14 | quick_rigid_registration |  | spatial transcriptomics, visium, merfish | YEL 讨论触发 |
| 15 | reconstruct_3d_face_from_mri |  | spatial transcriptomics, visium, merfish | YEL 讨论触发 |
| 16 | segment_and_quantify_cells_in_multiplexed_images |  | spatial transcriptomics, visium, merfish | YEL 讨论触发 |
| 17 | segment_with_nn_unet |  | spatial transcriptomics, visium, merfish | YEL 讨论触发 |
| 18 | spatial-transcriptomics |  | spatial transcriptomics, visium, merfish | YEL 讨论触发 |
---

## 04_Bulk - Bulk/表观 (18 skills)

| # | Skill | Description | Keywords | Trigger |
|---|---|---|---|---|
| 1 | analyze_comparative_genomics_and_haplotypes |  | bulk, gwas, variant | YEL 讨论触发 |
| 2 | analyze_copy_number_purity_ploidy_and_focal_events |  | bulk, gwas, variant | YEL 讨论触发 |
| 3 | analyze_ddr_network_in_cancer |  | bulk, gwas, variant | YEL 讨论触发 |
| 4 | analyze_genomic_region_overlap |  | bulk, gwas, variant | YEL 讨论触发 |
| 5 | bayesian_finemapping_with_deep_vi |  | bulk, gwas, variant | YEL 讨论触发 |
| 6 | bulk-omics-clustering |  | bulk, gwas, variant | RED 必触发 |
| 7 | bulk-rnaseq-counts-to-de-deseq2 |  | bulk, gwas, variant | YEL 讨论触发 |
| 8 | bulk-rnaseq-differential-expression |  | bulk, gwas, variant | RED 必触发 |
| 9 | detect_and_annotate_somatic_mutations |  | bulk, gwas, variant | YEL 讨论触发 |
| 10 | detect_and_characterize_structural_variations |  | bulk, gwas, variant | YEL 讨论触发 |
| 11 | find_sequence_mutations |  | bulk, gwas, variant | YEL 讨论触发 |
| 12 | fit_genomic_prediction_model |  | bulk, gwas, variant | YEL 讨论触发 |
| 13 | genetic-variant-annotation |  | bulk, gwas, variant | YEL 讨论触发 |
| 14 | gwas-to-function-twas |  | bulk, gwas, variant | RED 必触发 |
| 15 | liftover_coordinates |  | bulk, gwas, variant | YEL 讨论触发 |
| 16 | mendelian-randomization-twosamplemr |  | bulk, gwas, variant | RED 必触发 |
| 17 | milor |  | bulk, gwas, variant | YEL 讨论触发 |
| 18 | polygenic-risk-score-prs-catalog |  | bulk, gwas, variant | YEL 讨论触发 |
---

## 05_蛋白 - 蛋白/免疫 (26 skills)

| # | Skill | Description | Keywords | Trigger |
|---|---|---|---|---|
| 1 | analyze_atp_luminescence_assay |  | protein, proteome, proteomics | YEL 讨论触发 |
| 2 | analyze_circular_dichroism_spectra |  | protein, proteome, proteomics | YEL 讨论触发 |
| 3 | analyze_cytokine_production_in_cd4_tcells |  | protein, proteome, proteomics | YEL 讨论触发 |
| 4 | analyze_ebv_antibody_titers |  | protein, proteome, proteomics | YEL 讨论触发 |
| 5 | analyze_endolysosomal_calcium_dynamics |  | protein, proteome, proteomics | YEL 讨论触发 |
| 6 | analyze_enzyme_kinetics_assay |  | protein, proteome, proteomics | YEL 讨论触发 |
| 7 | analyze_fatty_acid_composition_by_gc |  | protein, proteome, proteomics | YEL 讨论触发 |
| 8 | analyze_interaction_mechanisms |  | protein, proteome, proteomics | YEL 讨论触发 |
| 9 | analyze_intracellular_calcium_with_rhod2 |  | protein, proteome, proteomics | YEL 讨论触发 |
| 10 | analyze_itc_binding_thermodynamics |  | protein, proteome, proteomics | YEL 讨论触发 |
| 11 | analyze_mitochondrial_morphology_and_potential |  | protein, proteome, proteomics | YEL 讨论触发 |
| 12 | analyze_protease_kinetics |  | protein, proteome, proteomics | YEL 讨论触发 |
| 13 | analyze_protein_colocalization |  | protein, proteome, proteomics | RED 必触发 |
| 14 | analyze_protein_conservation |  | protein, proteome, proteomics | RED 必触发 |
| 15 | analyze_protein_phylogeny |  | protein, proteome, proteomics | RED 必触发 |
| 16 | analyze_radiolabeled_antibody_biodistribution |  | protein, proteome, proteomics | YEL 讨论触发 |
| 17 | analyze_western_blot |  | protein, proteome, proteomics | RED 必触发 |
| 18 | compare_protein_structures |  | protein, proteome, proteomics | RED 必触发 |
| 19 | docking_autodock_vina |  | protein, proteome, proteomics | RED 必触发 |
| 20 | generate_gene_embeddings_with_ESM_models |  | protein, proteome, proteomics | YEL 讨论触发 |
| 21 | model_protein_dimerization_network |  | protein, proteome, proteomics | RED 必触发 |
| 22 | predict_binding_affinity_protein_1d_sequence |  | protein, proteome, proteomics | RED 必触发 |
| 23 | proteomics-diff-exp |  | protein, proteome, proteomics | YEL 讨论触发 |
| 24 | run_autosite |  | protein, proteome, proteomics | YEL 讨论触发 |
| 25 | run_diffdock_with_smiles |  | protein, proteome, proteomics | YEL 讨论触发 |
| 26 | simulate_protein_signaling_network |  | protein, proteome, proteomics | RED 必触发 |
---

## 06_微生物植物 - 微生物/植物 (5 skills)

| # | Skill | Description | Keywords | Trigger |
|---|---|---|---|---|
| 1 | analyze_bacterial_growth_curve |  | bacterial, bacteria, yeast | YEL 讨论触发 |
| 2 | get_bacterial_transformation_protocol |  | bacterial, bacteria, yeast | YEL 讨论触发 |
| 3 | perform_flux_balance_analysis |  | bacterial, bacteria, yeast | YEL 讨论触发 |
| 4 | simulate_demographic_history |  | bacterial, bacteria, yeast | YEL 讨论触发 |
| 5 | simulate_metabolic_network_perturbation |  | bacterial, bacteria, yeast | YEL 讨论触发 |
---

## 07_药物临床 - 药物/临床 (23 skills)


| # | Skill | Description | Keywords | Trigger |
|---|---|---|---|---|
| 1 | analyze_abr_waveform_p1_metrics |  | drug, clinical, fda | YEL 讨论触发 |
| 2 | analyze_accelerated_stability_of_pharmaceutical_formulations |  | drug, clinical, fda | YEL 讨论触发 |
| 3 | analyze_fda_safety_signals |  | drug, clinical, fda | RED 必触发 |
| 4 | analyze_xenograft_tumor_growth_inhibition |  | drug, clinical, fda | YEL 讨论触发 |
| 5 | calculate_physicochemical_properties |  | drug, clinical, fda | YEL 讨论触发 |
| 6 | check_drug_combination_safety |  | drug, clinical, fda | RED 必触发 |
| 7 | check_fda_drug_recalls |  | drug, clinical, fda | RED 必触发 |
| 8 | clinicaltrials-landscape |  | drug, clinical, fda | YEL 讨论触发 |
| 9 | drug-response |  | drug, clinical, fda | RED 必触发 |
| 10 | estimate_alpha_particle_radiotherapy_dosimetry |  | drug, clinical, fda | YEL 讨论触发 |
| 11 | find_alternative_drugs_ddinter |  | drug, clinical, fda | RED 必触发 |
| 12 | get_fda_drug_label_info |  | drug, clinical, fda | RED 必触发 |
| 13 | grade_adverse_events_using_vcog_ctcae |  | drug, clinical, fda | YEL 讨论触发 |
| 14 | open-targets |  | drug, clinical, fda | YEL 讨论触发 |
| 15 | open-targets-graphql |  | drug, clinical, fda | YEL 讨论触发 |
| 16 | perform_cosinor_analysis |  | drug, clinical, fda | YEL 讨论触发 |
| 17 | perform_mwas_cyp2c19_metabolizer_status |  | drug, clinical, fda | YEL 讨论触发 |
| 18 | predict_admet_properties |  | drug, clinical, fda | YEL 讨论触发 |
| 19 | retrieve_topk_repurposing_drugs_from_disease_txgnn |  | drug, clinical, fda | RED 必触发 |
| 20 | simulate_thyroid_hormone_pharmacokinetics |  | drug, clinical, fda | YEL 讨论触发 |
| 21 | survival-analysis |  | drug, clinical, fda | RED 必触发 |
| 22 | survival-analysis-clinical |  | drug, clinical, fda | RED 必触发 |
---
| 23 | scrna-disease-drug-discovery | 疾病scRNA+遗传证据整合的药物靶点优先级排序 | drug, disease, target, 药物靶点 | RED 必触发 |

## 08_报告 - 报告/可视化 (31 skills)

| scipilot-figure-skill | 可视化顾问：先剖析数据→推荐图型→期刊规范→绘制→程序+AI视觉自检 | figure, plot, 画图, 可视化, publication | RED 必触发 |

| # | Skill | Description | Keywords | Trigger |
|---|---|---|---|---|
| 1 | analysis-summary-report |  | report, html, ppt | RED 必触发 |
| 2 | bioinformatics-html-report | A zero-dependency Python toolkit for generating publication-quality interactive HTML reports from bi | report, html, ppt | RED 必触发 |
| 3 | cns-visualization |  | report, html, ppt | RED 必触发 |
| 4 | docx-generation | Generate professional, Phylo-branded Word documents from scientific analysis results using python-do | report, html, ppt | YEL 讨论触发 |
| 5 | html-report |  | report, html, ppt | RED 必触发 |
| 6 | pdf-report-generation | Generate professional, Phylo-branded PDF reports from scientific analysis results using ReportLab. U | report, html, ppt | RED 必触发 |
| 7 | pdf-translate |  | report, html, ppt | YEL 讨论触发 |
| 8 | pdf_reader |  | report, html, ppt | YEL 讨论触发 |
| 9 | ppt-generator |  | report, html, ppt | RED 必触发 |
| 10 | ppt-html |  | report, html, ppt | RED 必触发 |
| 11 | ppt-master |  | report, html, ppt | RED 必触发 |
| 12 | pptx-generation | Generate professional, Phylo-branded PowerPoint presentations from scientific analysis results using | report, html, ppt | RED 必触发 |
| 13 | summarize |  | report, html, ppt | YEL 讨论触发 |
---

| patent-analysis | 生物信息学/方法类专利深度分析：竞品拆解、权利解读、规避策略、创新点空白识别 |  | YEL 讨论触发 |
| proteomics-secretome-analysis | > |  | YEL 讨论触发 |
| bioinformatics-patent-strategy | > |  | YEL 讨论触发 |
| cross-species-cre-conservation | > |  | YEL 讨论触发 |
| atac-seq-memomics | ArchR scATAC-seq 全流程: 环境搭建→Arrow文件→QC→降维→聚类→Peak calling→Motif→Footprinting→差异可及性→共可及性→导出 |  | YEL 讨论触发 |
| cross-species-regulatory-conservation | > |  | YEL 讨论触发 |
| cellbender-batch-pipeline | CellBender 批量样本可靠执行方案 — PyTorch 2.12 weakref 修复 + 磁盘追踪式后台运行 + 进度监控。触发词：批量cellbender / 多样本去污染 / 后台运行c |  | YEL 讨论触发 |
| metabolomics-functional-enrichment | 代谢组学功能富集分析：输入差异代谢物列表 → MSEA代谢物集富集 → MetPA代谢通路分析 → mummichog通路推断 → ORA过表达分析。基于 MetaboAnalystR 4.0 + K |  | YEL 讨论触发 |
| metabolomics-statistical-analysis | 代谢组学统计分析全流程：输入 peak intensity matrix → 归一化 → 缺失值填充 → PCA → PLS-DA/OPLS-DA → VIP筛选 → 火山图 → Random For |  | YEL 讨论触发 |
| windows-bioinformatics-batch-processing | Windows生信批量任务执行规程：进程生命周期管理、GPU内存、进度监控、错误恢复。适用于CellBender/scanpy/Seurat等需要在Windows上用GPU跑大批量样本的场景 |  | YEL 讨论触发 |
| agent-loop-engineering | 防止 LLM '叙事代替执行'的框架级防御。触发：长链修复任务中 Agent 输出动作动词但无 tool call，或 rail_review(post) code_executed 过短。已部署 G |  | YEL 讨论触发 |
| scrna-trajectory-analysis | 单细胞轨迹推断/拟时序分析：Monocle3 (R)、Slingshot (R)、scVelo RNA velocity (Python)、CellRank 命运映射 (Python)。从 Seura |  | YEL 讨论触发 |
| cross-species-atac-conservation | > |  | YEL 讨论触发 |
| archr-atac-analysis | > |  | YEL 讨论触发 |
| nature-figure | >- |  | YEL 讨论触发 |
| public-data-download | 精确下载公共组学数据集（指定物种+组织+assay类型）。不做全量调查，直接搜最佳候选并开始下载。 |  | YEL 讨论触发 |
| scrna-cns-figure-design | >- |  | YEL 讨论触发 |
## 09_内置 - Hermes系统 (15 skills)


| # | Skill | Description | Keywords | Trigger |
|---|---|---|---|---|
| 1 | adaptyv-api |  | code, file, convert | WHT 系统级 |
| 2 | code-writer |  | code, file, convert | WHT 系统级 |
| 3 | computer-use |  | code, file, convert | WHT 系统级 |
| 4 | create-bio-skill | 当 skill_view 返回 not found 且没有相似 skill，或用户指定了特定包时触发。自动查询官方文档+文献，按 BioMinI 标准格式创建新的生信 skill（含 SKILL.md | code, file, convert | WHT 系统级 |
| 5 | data-analysis-best-practices |  | code, file, convert | WHT 系统级 |
| 6 | data-viz |  | code, file, convert | WHT 系统级 |
| 7 | experimental-design-statistics |  | code, file, convert | WHT 系统级 |
| 8 | file-convert |  | code, file, convert | WHT 系统级 |
| 9 | find-skill |  | code, file, convert | WHT 系统级 |
| 10 | heart-conference-monitor |  | code, file, convert | WHT 系统级 |
| 11 | ml-classification |  | code, file, convert | WHT 系统级 |
| 12 | phylo-create-skill | Create, test, package, and present reusable skills for Phylo's Biomni platform and bioinformatics wo | code, file, convert | WHT 系统级 |
| 13 | self-improving-agent |  | code, file, convert | WHT 系统级 |
---
| 14 | error-recovery | 错误自动修复：根据报错信息查找解决方案 | error, fix, debug, 报错, 修复 | RED 必触发 |

| heartbeat-monitor | 长任务心跳监控 — 独立后台进程持续记录进度，Agent 随时读取汇报 |  | RED 必触发 |
## 10_多组学整合 - 多组学整合 (11 skills)

| # | Skill | Description | Keywords | Trigger |
|---|---|---|---|---|
| 1 | generate_embeddings_with_state |  | multi_omics, multi-omics, rgcca | YEL 讨论触发 |
| 2 | generate_transcriptformer_embeddings |  | multi_omics, multi-omics, rgcca | YEL 讨论触发 |
| 3 | get_uce_embeddings_scRNA |  | multi_omics, multi-omics, rgcca | YEL 讨论触发 |
| 4 | lipidomics-summary-stats |  | multi_omics, multi-omics, rgcca | YEL 讨论触发 |
| 5 | map_to_ima_interpret_scRNA |  | multi_omics, multi-omics, rgcca | YEL 讨论触发 |
| 6 | multi-omics-integration |  | multi_omics, multi-omics, rgcca | RED 必触发 |
| 7 | perform_gene_expression_nmf_analysis |  | multi_omics, multi-omics, rgcca | YEL 讨论触发 |
| 8 | rgcca-multiblock |  | multi_omics, multi-omics, rgcca | YEL 讨论触发 |
| 9 | simulate_renin_angiotensin_system_dynamics |  | multi_omics, multi-omics, rgcca | YEL 讨论触发 |
| 10 | split_modalities |  | multi_omics, multi-omics, rgcca | YEL 讨论触发 |
| 11 | unsupervised_celltype_transfer_between_scRNA_datasets |  | multi_omics, multi-omics, rgcca | YEL 讨论触发 |
---

## 11_文献搜索 - 文献/数据库 (61 skills)


| # | Skill | Description | Keywords | Trigger |
|---|---|---|---|---|
| 1 | academic-paper-writing |  | query, literature, paper | RED 必触发 |
| 2 | academic-research |  | query, literature, paper | GRN 按需触发 |
| 3 | advanced_web_search_claude |  | query, literature, paper | GRN 按需触发 |
| 4 | deep-research |  | query, literature, paper | GRN 按需触发 |
| 5 | extract_pdf_content |  | query, literature, paper | GRN 按需触发 |
| 6 | extract_url_content |  | query, literature, paper | GRN 按需触发 |
| 7 | fetch_supplementary_info_from_doi |  | query, literature, paper | GRN 按需触发 |
| 8 | knowledge-base-curation | 端到端构建组织特异性多组学知识库。从文献搜索→生物知识提取→基因集构建→ 测序方法参数→多物种同步→YAML验证的完整流程。覆盖 scRNA-seq / ATAC-seq / spatial / bu | query, literature, paper | GRN 按需触发 |
| 9 | literature-param-extraction | 从文献 PDF 提取生信参数并写入知识库。触发场景：拿到真实数据做分析时、知识库缺少对应方法/参数时、需要验证参数来源时。 | query, literature, paper | GRN 按需触发 |
| 10 | literature-preclinical | Preclinical (non-clinical) evidence synthesis. Aligns with the user through a short clarification st | query, literature, paper | GRN 按需触发 |
| 11 | literature-review | General-purpose literature review and evidence synthesis for any scientific topic. Aligns with the u | query, literature, paper | RED 必触发 |
| 12 | omics-dataset-retrieval |  | query, literature, paper | GRN 按需触发 |
| 13 | paper-download |  | query, literature, paper | RED 必触发 |
| 14 | paper-summary |  | query, literature, paper | RED 必触发 |
| 15 | paper-translate |  | query, literature, paper | RED 必触发 |
| 16 | query_alphafold |  | query, literature, paper | GRN 按需触发 |
| 17 | query_arxiv |  | query, literature, paper | GRN 按需触发 |
| 18 | query_cbioportal |  | query, literature, paper | GRN 按需触发 |
| 19 | query_chatnt |  | query, literature, paper | GRN 按需触发 |
| 20 | query_chembl |  | query, literature, paper | GRN 按需触发 |
| 21 | query_clinicaltrials |  | query, literature, paper | GRN 按需触发 |
| 22 | query_clinvar |  | query, literature, paper | GRN 按需触发 |
| 23 | query_dailymed |  | query, literature, paper | GRN 按需触发 |
| 24 | query_dbsnp |  | query, literature, paper | GRN 按需触发 |
| 25 | query_drug_interactions |  | query, literature, paper | RED 必触发 |
| 26 | query_emdb |  | query, literature, paper | GRN 按需触发 |
| 27 | query_encode |  | query, literature, paper | GRN 按需触发 |
| 28 | query_ensembl |  | query, literature, paper | GRN 按需触发 |
| 29 | query_fda_adverse_events |  | query, literature, paper | RED 必触发 |
| 30 | query_geo |  | query, literature, paper | GRN 按需触发 |
| 31 | query_gnomad |  | query, literature, paper | GRN 按需触发 |
| 32 | query_gtopdb |  | query, literature, paper | GRN 按需触发 |
| 33 | query_gwas_catalog |  | query, literature, paper | RED 必触发 |
| 34 | query_interpro |  | query, literature, paper | GRN 按需触发 |
| 35 | query_iucn |  | query, literature, paper | GRN 按需触发 |
| 36 | query_jaspar |  | query, literature, paper | GRN 按需触发 |
| 37 | query_kegg |  | query, literature, paper | RED 必触发 |
| 38 | query_monarch |  | query, literature, paper | GRN 按需触发 |
| 39 | query_mpd |  | query, literature, paper | GRN 按需触发 |
| 40 | query_openfda |  | query, literature, paper | RED 必触发 |
| 41 | query_opentarget |  | query, literature, paper | GRN 按需触发 |
| 42 | query_paleobiology |  | query, literature, paper | GRN 按需触发 |
| 43 | query_pdb |  | query, literature, paper | GRN 按需触发 |
| 44 | query_pdb_identifiers |  | query, literature, paper | GRN 按需触发 |
| 45 | query_pride |  | query, literature, paper | GRN 按需触发 |
| 46 | query_pubchem |  | query, literature, paper | GRN 按需触发 |
| 47 | query_pubmed |  | query, literature, paper | GRN 按需触发 |
| 48 | query_quickgo |  | query, literature, paper | GRN 按需触发 |
| 49 | query_reactome |  | query, literature, paper | GRN 按需触发 |
| 50 | query_regulomedb |  | query, literature, paper | GRN 按需触发 |
| 51 | query_remap |  | query, literature, paper | GRN 按需触发 |
| 52 | query_scholar |  | query, literature, paper | GRN 按需触发 |
| 53 | query_stringdb |  | query, literature, paper | GRN 按需触发 |
| 54 | query_synapse |  | query, literature, paper | GRN 按需触发 |
| 55 | query_ucsc |  | query, literature, paper | GRN 按需触发 |
| 56 | query_unichem |  | query, literature, paper | GRN 按需触发 |
| 57 | query_uniprot |  | query, literature, paper | GRN 按需触发 |
| 58 | query_worms |  | query, literature, paper | GRN 按需触发 |
| 59 | search_google |  | query, literature, paper | GRN 按需触发 |
| 60 | web-research |  | query, literature, paper | GRN 按需触发 |
---
| 61 | research-plan | Mermaid技术路线图+模块映射表生成 | 技术路线, 分析路线, 研究方案, research plan | RED 必触发 |

## 12_分子生物学 - 分子克隆 (21 skills)


| # | Skill | Description | Keywords | Trigger |
|---|---|---|---|---|
| 1 | align_sequences |  | primer, plasmid, pcr | GRN 按需触发 |
| 2 | annotate_open_reading_frames |  | primer, plasmid, pcr | GRN 按需触发 |
| 3 | annotate_plasmid |  | primer, plasmid, pcr | RED 必触发 |
| 4 | blast_sequence |  | primer, plasmid, pcr | GRN 按需触发 |
| 5 | design_golden_gate_oligos |  | primer, plasmid, pcr | GRN 按需触发 |
| 6 | design_primer |  | primer, plasmid, pcr | RED 必触发 |
| 7 | design_verification_primers |  | primer, plasmid, pcr | RED 必触发 |
| 8 | digest_sequence |  | primer, plasmid, pcr | GRN 按需触发 |
| 9 | find_restriction_enzymes |  | primer, plasmid, pcr | GRN 按需触发 |
| 10 | find_restriction_sites |  | primer, plasmid, pcr | GRN 按需触发 |
| 11 | get_gene_coding_sequence |  | primer, plasmid, pcr | GRN 按需触发 |
| 12 | get_golden_gate_assembly_protocol |  | primer, plasmid, pcr | GRN 按需触发 |
| 13 | get_oligo_annealing_protocol |  | primer, plasmid, pcr | GRN 按需触发 |
| 14 | get_plasmid_sequence |  | primer, plasmid, pcr | RED 必触发 |
| 15 | golden_gate_assembly |  | primer, plasmid, pcr | GRN 按需触发 |
| 16 | interspecies_gene_conversion |  | primer, plasmid, pcr | GRN 按需触发 |
| 17 | microplate-layout-design |  | primer, plasmid, pcr | GRN 按需触发 |
| 18 | pcr-primer-design |  | primer, plasmid, pcr | RED 必触发 |
| 19 | pcr_simple |  | primer, plasmid, pcr | RED 必触发 |
| 20 | perform_pcr_and_gel_electrophoresis |  | primer, plasmid, pcr | RED 必触发 |
---
| 21 | phylogenetics-toolkit | 系统发育树构建+MCMC+祖先状态重建 | phylogenetics, tree, 系统发育, 进化 | YEL 讨论触发 |

## 13_组织学病理 - 组织学/病理 (5 skills)

| # | Skill | Description | Keywords | Trigger |
|---|---|---|---|---|
| 1 | analyze_thrombus_histology |  | histology, h&e, stain | GRN 按需触发 |
| 2 | quantify_amyloid_beta_plaques |  | histology, h&e, stain | GRN 按需触发 |
| 3 | quantify_cell_cycle_phases_from_microscopy |  | histology, h&e, stain | GRN 按需触发 |
| 4 | quantify_corneal_nerve_fibers |  | histology, h&e, stain | GRN 按需触发 |
| 5 | run_3d_chondrogenic_aggregate_assay |  | histology, h&e, stain | GRN 按需触发 |
---

## 14_细胞生物学实验 - 细胞生物学 (6 skills)

| # | Skill | Description | Keywords | Trigger |
|---|---|---|---|---|
| 1 | analyze_cell_senescence_and_apoptosis |  | flow cytometry, facs, cell sorting | GRN 按需触发 |
| 2 | analyze_cfse_cell_proliferation |  | flow cytometry, facs, cell sorting | GRN 按需触发 |
| 3 | isolate_purify_immune_cells |  | flow cytometry, facs, cell sorting | GRN 按需触发 |
| 4 | perform_facs_cell_sorting |  | flow cytometry, facs, cell sorting | GRN 按需触发 |
| 5 | track_immune_cells_under_flow |  | flow cytometry, facs, cell sorting | GRN 按需触发 |
---

| secretome-classification | > |  | YEL 讨论触发 |
## 15_CRISPR基因编辑 - CRISPR (4 skills)

| # | Skill | Description | Keywords | Trigger |
|---|---|---|---|---|
| 1 | analyze_crispr_genome_editing |  | crispr, sgrna, knockout | RED 必触发 |
| 2 | design_knockout_sgrna |  | crispr, sgrna, knockout | RED 必触发 |
| 3 | pooled-crispr-screens |  | crispr, sgrna, knockout | RED 必触发 |
| 4 | sgrna-design |  | crispr, sgrna, knockout | RED 必触发 |

---
*274 skills, 15 domains*