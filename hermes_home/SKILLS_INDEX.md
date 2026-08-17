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
| 1 | analyze_cas9_mutation_outcomes | Analyzes and categorizes mutations induced by Cas9 at target sites. | rna, scrna, scrnaseq | YEL 讨论触发 |
| 2 | analyze_ciliary_beat_frequency | Analyze ciliary beat frequency from high-speed video microscopy data using FFT analysis. | rna, scrna, scrnaseq | YEL 讨论触发 |
| 3 | analyze_flow_cytometry_immunophenotyping | Analyze flow cytometry data to identify and quantify specific cell populations based on surface mark | rna, scrna, scrnaseq | YEL 讨论触发 |
| 4 | analyze_rna_secondary_structure_features | Calculate numeric values for various structural features of an RNA secondary structure. | rna, scrna, scrnaseq | YEL 讨论触发 |
| 5 | annotate_celltype_scRNA | 基于marker基因和标签转移的LLM细胞类型注释。使用场景：聚类后需要鉴定细胞身份，有已知marker列表，或需从参考数据集转移标签 | rna, scrna, scrnaseq | YEL 讨论触发 |
| 6 | annotate_celltype_with_panhumanpy | Perform cell type annotation of single-cell RNA-seq data using Panhuman Azimuth Neural Network. This | rna, scrna, scrnaseq | YEL 讨论触发 |
| 7 | cell-cell-communication | 需使用cell cell communication功能，适用于相关生信分析场景 | rna, scrna, scrnaseq | YEL 讨论触发 |
| 8 | cellbender-remove-background | CellBender去除环境RNA污染。使用场景：10X raw h5矩阵，怀疑有空滴/环境RNA污染，需GPU环境，输入raw_feature_bc_matrix | rna, scrna, scrnaseq | RED 必触发 |
| 9 | cellchat-v2 | CellChat v2配体-受体细胞通讯分析。使用场景：已聚类注释的Seurat对象，需分析细胞间信号通路、配体受体互作、信号角色（发出者/接收者），多条件比较 | rna, scrna, scrnaseq | RED 必触发 |
| 10 | coexpression-network | Build weighted gene co-expression networks to identify modules of coordinately expressed genes and d | rna, scrna, scrnaseq | YEL 讨论触发 |
| 11 | create_harmony_embeddings_scRNA | Harmony批次校正整合。使用场景：多样本scRNA-seq需去批次效应，快速高效，适合中等数据量（<100万细胞），R/Seurat生态 | rna, scrna, scrnaseq | RED 必触发 |
| 12 | create_scvi_embeddings_scRNA | Create scVI and scANVI embeddings for single-cell RNA-seq data, saving the results to an AnnData obj | rna, scrna, scrnaseq | YEL 讨论触发 |
| 13 | deg-analysis | Pseudobulk DESeq2+Wilcoxon+MAST多方法差异表达分析。使用场景：已注释的scRNA-seq，需找不同条件/群之间的差异基因，含多重检验校正 | rna, scrna, scrnaseq | RED 必触发 |
| 14 | disease-progression-longitudinal | 疾病进展纵向分析：多样本时间点→轨迹分析→疾病动态→进展标志物→早期预警 | rna, scrna, scrnaseq | YEL 讨论触发 |
| 15 | doubletfinder-remove-doublets | DoubletFinder双细胞检测: Seurat → 人工双胞 → 检测 → 过滤 | rna, scrna, scrnaseq | RED 必触发 |
| 16 | estimate_cell_cycle_phase_durations | Estimate cell cycle phase durations using dual-nucleoside pulse labeling data and mathematical model | rna, scrna, scrnaseq | YEL 讨论触发 |
| 17 | functional-enrichment | GSEA/ORA功能富集分析。使用场景：有DEG基因列表或排序列表，需GO/KEGG/Reactome/MSigDB通路富集，R用clusterProfiler Python用gseapy | rna, scrna, scrnaseq | RED 必触发 |
| 19 | gene-essentiality | 需使用gene essentiality功能，适用于相关生信分析场景 | rna, scrna, scrnaseq | YEL 讨论触发 |
| 20 | gene_set_enrichment_analysis | Perform enrichment analysis for a list of genes, with optional background gene set and plotting func | rna, scrna, scrnaseq | RED 必触发 |
| 21 | get_gene_set_enrichment_analysis_supported_database_list | Returns a list of supported databases for gene set enrichment analysis. | rna, scrna, scrnaseq | RED 必触发 |
| 22 | get_rna_seq_archs4 | Given a gene name, fetch RNA-seq expression data showing the top K tissues with highest transcripts- | rna, scrna, scrnaseq | YEL 讨论触发 |
| 23 | grn-pyscenic | 需使用grn pyscenic功能，适用于相关生信分析场景 | rna, scrna, scrnaseq | YEL 讨论触发 |
| 24 | hdwgcna | WGCNA/hdWGCNA共表达网络分析。模块鉴定/hub基因/模块-性状关联 | rna, scrna, scrnaseq | YEL 讨论触发 |
| 25 | immune-deconvolution | CIBERSORTx+xCell+MCP-counter多方法免疫细胞比例估计 | rna, scrna, scrnaseq | YEL 讨论触发 |
| 26 | infercnv | inferCNV肿瘤细胞CNV推断+恶性细胞鉴定 | rna, scrna, scrnaseq | RED 必触发 |
| 27 | lasso-biomarker-panel | LASSO生物标志物筛选：表达矩阵+分组→LASSO回归→特征选择→标志物panel→ROC评估 | rna, scrna, scrnaseq | YEL 讨论触发 |
| 28 | pathway-enrichment | 需使用pathway enrichment功能，适用于相关生信分析场景 | rna, scrna, scrnaseq | RED 必触发 |
| 29 | quantify_and_cluster_cell_motility | Quantify cell motility features from time-lapse microscopy images and cluster cells based on motilit | rna, scrna, scrnaseq | YEL 讨论触发 |
| 30 | sasp-scoring | SASP gene set scoring + heatmap + group comparison | rna, scrna, scrnaseq | YEL 讨论触发 |
| 31 | scrna-eda | EDA数据探索：QC后的数据概览，含分布图/相关性/主成分 | rna, scrna, scrnaseq, 数据探索, 概览 | RED 必触发 |
| scrna-clustering | 完整Seurat v5聚类注释工作流。使用场景：QC后的scRNA-seq，需SCTransform→PCA→UMAP→聚类→注释→Markers，含SoupX/DoubletFinder/Harmo | rna, scrna, scrnaseq | RED 必触发 |
| 34 | scrna-qc | scRNA-seq质控+Doublet+Ambient RNA去除。使用场景：拿到raw矩阵第一步，需过滤低质量细胞/双胞/环境RNA，自动推荐阈值，支持人/鼠 | rna, scrna, scrnaseq | RED 必触发 |
| 37 | scrnaseq-scanpy-core-analysis | Scanpy单细胞核心分析：10X数据→QC→归一化→HVG→PCA→邻居图→UMAP→Leiden聚类→marker→注释 | rna, scrna, scrnaseq | RED 必触发 |
| 38 | scrnaseq-seurat-core-analysis | Seurat v5单细胞分析：scRNA数据→SCTransform v2→整合(Harmony/CCA)→聚类→UMAP→marker→注释→差异分析 | rna, scrna, scrnaseq | RED 必触发 |
| 39 | sctour-trajectory-inference | scTour VAE 深度潜在时间推断 + 向量场 + 跨数据集预测。无需指定起点，无监督学习细胞动力学。 | rna, scrna, scrnaseq | RED 必触发 |
| 40 | senescence-detection | SASP scoring + p16/p21 + senescent subpopulation | rna, scrna, scrnaseq | YEL 讨论触发 |
| 41 | soupx-remove-background | SoupX环境RNA去污染: 估计soup → 减法去除 | rna, scrna, scrnaseq | RED 必触发 |
| 42 | stratified-subsampling | 分层抽样：3种场景 — 降采样均衡、训练/测试拆分、可视化抽样。Seurat/Scanpy通用 | rna, scrna, scrnaseq | YEL 讨论触发 |
| 43 | trajectory-analysis | 单细胞轨迹推断/拟时序分析：Monocle3 (R)、Slingshot (R)、scVelo RNA velocity (Python)、CellRank 命运映射 (Python)。从 Seura | rna, scrna, scrnaseq | RED 必触发 |
| 40 | scrna-eda | EDA数据探索：QC后的数据概览，含分布图/相关性/主成分 | rna, scrna, scrnaseq, 数据探索, 概览 | RED 必触发 |
| 44 | upstream-regulator-analysis | 上游调控因子分析：差异基因→Ingenuity/DecoupleR→激活/抑制调控因子→机制推测 | rna, scrna, scrnaseq | YEL 讨论触发 |
---

## 02_ATAC - ATAC/染色质 (10 skills)

| # | Skill | Description | Keywords | Trigger |
|---|---|---|---|---|
| 1 | analyze_chromatin_interactions | Analyze chromatin interactions from Hi-C data to identify enhancer-promoter interactions and TADs. | atac, chipseq, atacseq | YEL 讨论触发 |
| 2 | atac-seq | ArchR scATAC-seq 全流程: 环境搭建→Arrow文件→QC→降维→聚类→Peak calling→Motif→Footprinting→差异可及性→共可及性→导出 | atac, chipseq, atacseq | RED 必触发 |
| 3 | chip-atlas-diff-analysis | 有ChIP-Atlas实验组/对照组peak数据，需做差异peak分析，找出组间显著变化peak的基因组位置和邻近基因 | atac, chipseq, atacseq | YEL 讨论触发 |
| 4 | chip-atlas-peak-enrichment | ChIP-Atlas peak富集分析：peak列表→基因组区域注释→motif富集→GO/KEGG通路富集→调控网络 | atac, chipseq, atacseq | RED 必触发 |
| 5 | chip-atlas-target-genes | 有ChIP-Atlas peak坐标或transcription factor名，需查询这些peak调控的靶基因列表，输出TF→target调控表 | atac, chipseq, atacseq | YEL 讨论触发 |
| 6 | find_enriched_motifs_with_homer | Find DNA sequence motifs enriched in genomic regions using the HOMER motif discovery software. | atac, chipseq, atacseq | YEL 讨论触发 |
| 7 | get_genes_near_ccre | Given a cCRE accession, return k nearest genes sorted by distance. | atac, chipseq, atacseq | YEL 讨论触发 |
| 8 | identify_transcription_factor_binding_sites | Identifies binding sites for a specific transcription factor in a genomic sequence. | atac, chipseq, atacseq | YEL 讨论触发 |
| 9 | perform_chipseq_peak_calling_with_macs2 | Perform ChIP-seq peak calling using MACS2 to identify genomic regions with significant binding. | atac, chipseq, atacseq | YEL 讨论触发 |
| 10 | region_to_ccre_screen | Given genomic coordinates, retrieve intersecting ENCODE SCREEN cCREs. | atac, chipseq, atacseq | YEL 讨论触发 |
---

## 03_空间组 - 空间转录组 (18 skills)

| # | Skill | Description | Keywords | Trigger |
|---|---|---|---|---|
| 1 | analyze_aortic_diameter_and_geometry | Analyze aortic diameter and geometry from cardiovascular imaging data to measure aortic root diamete | spatial transcriptomics, visium, merfish | YEL 讨论触发 |
| 2 | analyze_bone_microct_morphometry | Analyze bone microarchitecture parameters from 3D micro-CT images to calculate bone mineral density, | spatial transcriptomics, visium, merfish | YEL 讨论触发 |
| 3 | analyze_cns_lesion_histology | Analyzes histological images of CNS lesions to quantify immune cell infiltration, demyelination, and | spatial transcriptomics, visium, merfish | RED 必触发 |
| 4 | analyze_hemodynamic_data | Analyzes raw blood pressure data to calculate key hemodynamic parameters. | spatial transcriptomics, visium, merfish | YEL 讨论触发 |
| 5 | analyze_immunohistochemistry_image | Analyzes immunohistochemistry images to quantify protein expression and spatial distribution. | spatial transcriptomics, visium, merfish | YEL 讨论触发 |
| 6 | batch_register_images | Perform batch registration of multiple images to a single reference image. Automatically processes a | spatial transcriptomics, visium, merfish | YEL 讨论触发 |
| 7 | calculate_brain_adc_map | Calculate Apparent Diffusion Coefficient (ADC) map from diffusion-weighted MRI data using monoexpone | spatial transcriptomics, visium, merfish | YEL 讨论触发 |
| 8 | calculate_similarity_metrics | Calculate similarity metrics between two medical images. Supports mutual information, mean squared e | spatial transcriptomics, visium, merfish | YEL 讨论触发 |
| 9 | create_registration_visualization | Create visualization plots for registration results. Generates comparison plots, difference images,  | spatial transcriptomics, visium, merfish | RED 必触发 |
| 10 | create_segmentation_visualization | Create and save visualization of segmentation results using nilearn. Generates overlay plots and mul | spatial transcriptomics, visium, merfish | RED 必触发 |
| 11 | prepare_input_for_nnunet | Prepare input data for nnUNet by handling both 4D and pre-split modality files. Automatically detect | spatial transcriptomics, visium, merfish | YEL 讨论触发 |
| 12 | quick_affine_registration | Perform affine image registration between two medical images using SimpleITK. Affine registration ha | spatial transcriptomics, visium, merfish | YEL 讨论触发 |
| 13 | quick_deformable_registration | Perform deformable (B-spline) image registration between two medical images using SimpleITK. Deforma | spatial transcriptomics, visium, merfish | YEL 讨论触发 |
| 14 | quick_rigid_registration | Perform rigid image registration between two medical images using SimpleITK. Rigid registration hand | spatial transcriptomics, visium, merfish | YEL 讨论触发 |
| 15 | reconstruct_3d_face_from_mri | Generate a 3D model of facial anatomy from MRI scans of the head and neck. | spatial transcriptomics, visium, merfish | YEL 讨论触发 |
| 16 | segment_and_quantify_cells_in_multiplexed_images | Segment cells and quantify protein expression levels from multichannel tissue images. | spatial transcriptomics, visium, merfish | YEL 讨论触发 |
| 17 | segment_with_nn_unet | Segment images using nnUNet with proper environment setup. Supports brain tumor segmentation and oth | spatial transcriptomics, visium, merfish | YEL 讨论触发 |
| 18 | spatial-transcriptomics | 需使用spatial transcriptomics功能，适用于相关生信分析场景 | spatial transcriptomics, visium, merfish | YEL 讨论触发 |
---

## 04_Bulk - Bulk/表观 (18 skills)

| # | Skill | Description | Keywords | Trigger |
|---|---|---|---|---|
| 1 | analyze_comparative_genomics_and_haplotypes | Perform comparative genomics and haplotype analysis on multiple genome samples. Aligns genome sample | bulk, gwas, variant | YEL 讨论触发 |
| 2 | analyze_copy_number_purity_ploidy_and_focal_events | CNVkit-based copy number workflow performing CNV segmentation, purity & ploidy approximation, simpli | bulk, gwas, variant | YEL 讨论触发 |
| 3 | analyze_ddr_network_in_cancer | Analyze DNA Damage Response (DDR) network alterations and dependencies in cancer samples. | bulk, gwas, variant | YEL 讨论触发 |
| 4 | analyze_genomic_region_overlap | Analyze overlaps between two or more sets of genomic regions. | bulk, gwas, variant | YEL 讨论触发 |
| 5 | bayesian_finemapping_with_deep_vi | Performs Bayesian fine-mapping from GWAS summary statistics using deep variational inference to comp | bulk, gwas, variant | YEL 讨论触发 |
| 6 | bulk-omics-clustering | Bulk组学样本聚类：bulk RNA表达矩阵→PCA/t-SNE/UMAP→样本分群→WGCNA共表达网络→模块-性状关联 | bulk, gwas, variant | RED 必触发 |
| 7 | bulk-rnaseq-counts-to-de-deseq2 | 有raw counts矩阵(从featureCounts/HTSeq输出)，仅需用DESeq2做差异(不包含后续富集/可视化)，作为pipeline的第一步 | bulk, gwas, variant | YEL 讨论触发 |
| 8 | bulk-rnaseq-differential-expression | 有bulk RNA-seq counts矩阵+实验设计表(treat vs control)，需做差异化(GO/KEGG/火山图/热图) | bulk, gwas, variant | RED 必触发 |
| 9 | detect_and_annotate_somatic_mutations | Detects and annotates somatic mutations in tumor samples compared to matched normal samples using GA | bulk, gwas, variant | YEL 讨论触发 |
| 10 | detect_and_characterize_structural_variations | Detects and characterizes structural variations (SVs) in genomic sequencing data using LUMPY for SV  | bulk, gwas, variant | YEL 讨论触发 |
| 11 | find_sequence_mutations | Compare query sequence against reference sequence to identify mutations. | bulk, gwas, variant | YEL 讨论触发 |
| 12 | fit_genomic_prediction_model | Fit a linear mixed model for genomic prediction using genotype and phenotype data. | bulk, gwas, variant | YEL 讨论触发 |
| 13 | genetic-variant-annotation | 需使用genetic variant annotation功能，适用于相关生信分析场景 | bulk, gwas, variant | YEL 讨论触发 |
| 14 | gwas-to-function-twas | 需使用gwas to function twas功能，适用于相关生信分析场景 | bulk, gwas, variant | RED 必触发 |
| 15 | liftover_coordinates | Perform liftover of genomic coordinates between hg19 and hg38 formats with detailed intermediate ste | bulk, gwas, variant | YEL 讨论触发 |
| 16 | mendelian-randomization-twosamplemr | 需使用mendelian randomization twosamplemr功能，适用于相关生信分析场景 | bulk, gwas, variant | RED 必触发 |
| 17 | milor | MiloR邻域差异丰度检验, 适用于多条件比较 | bulk, gwas, variant | YEL 讨论触发 |
| 18 | polygenic-risk-score-prs-catalog | 需使用polygenic risk score prs catalog功能，适用于相关生信分析场景 | bulk, gwas, variant | YEL 讨论触发 |
---

## 05_蛋白 - 蛋白/免疫 (26 skills)

| # | Skill | Description | Keywords | Trigger |
|---|---|---|---|---|
| 1 | analyze_atp_luminescence_assay | Analyze luminescence-based ATP assay data to determine intracellular ATP concentration. | protein, proteome, proteomics | YEL 讨论触发 |
| 2 | analyze_circular_dichroism_spectra | Analyzes circular dichroism (CD) spectroscopy data to determine secondary structure and thermal stab | protein, proteome, proteomics | YEL 讨论触发 |
| 3 | analyze_cytokine_production_in_cd4_tcells | Analyze cytokine production (IFN-γ, IL-17) in CD4+ T cells after antigen stimulation. | protein, proteome, proteomics | YEL 讨论触发 |
| 4 | analyze_ebv_antibody_titers | Analyze ELISA data to quantify EBV antibody titers in plasma/serum samples. | protein, proteome, proteomics | YEL 讨论触发 |
| 5 | analyze_endolysosomal_calcium_dynamics | Analyze calcium dynamics in endo-lysosomal compartments using ELGA/ELGA1 probe data. | protein, proteome, proteomics | YEL 讨论触发 |
| 6 | analyze_enzyme_kinetics_assay | Performs in vitro enzyme kinetics assay and analyzes the dose-dependent effects of modulators. | protein, proteome, proteomics | YEL 讨论触发 |
| 7 | analyze_fatty_acid_composition_by_gc | Analyzes fatty acid composition in tissue samples using gas chromatography data. | protein, proteome, proteomics | YEL 讨论触发 |
| 8 | analyze_interaction_mechanisms | Analyze interaction mechanisms between two specific drugs providing detailed mechanistic insights an | protein, proteome, proteomics | YEL 讨论触发 |
| 9 | analyze_intracellular_calcium_with_rhod2 | Analyzes intracellular calcium concentration using Rhod-2 fluorescent indicator from microscopy imag | protein, proteome, proteomics | YEL 讨论触发 |
| 10 | analyze_itc_binding_thermodynamics | Analyzes isothermal titration calorimetry (ITC) data to determine binding affinity and thermodynamic | protein, proteome, proteomics | YEL 讨论触发 |
| 11 | analyze_mitochondrial_morphology_and_potential | Quantifies metrics of mitochondrial morphology and membrane potential from fluorescence microscopy i | protein, proteome, proteomics | YEL 讨论触发 |
| 12 | analyze_protease_kinetics | Analyze protease kinetics data from fluorogenic peptide cleavage assays, fit the data to Michaelis-M | protein, proteome, proteomics | YEL 讨论触发 |
| 13 | analyze_protein_colocalization | Analyze colocalization between two fluorescently labeled proteins in microscopy images. | protein, proteome, proteomics | RED 必触发 |
| 14 | analyze_protein_conservation | Perform multiple sequence alignment and phylogenetic analysis to identify conserved protein regions. | protein, proteome, proteomics | RED 必触发 |
| 15 | analyze_protein_phylogeny | Perform phylogenetic analysis on a set of protein sequences. This function aligns sequences, constru | protein, proteome, proteomics | RED 必触发 |
| 16 | analyze_radiolabeled_antibody_biodistribution | Analyze biodistribution and pharmacokinetic profile of radiolabeled antibodies. | protein, proteome, proteomics | YEL 讨论触发 |
| 17 | analyze_western_blot | Performs densitometric analysis of Western blot images to quantify relative protein expression. | protein, proteome, proteomics | RED 必触发 |
| 18 | compare_protein_structures | Compares two protein structures to identify structural differences and conformational changes. | protein, proteome, proteomics | RED 必触发 |
| 19 | docking_autodock_vina | Performs molecular docking using AutoDock Vina to predict binding affinities between small molecules | protein, proteome, proteomics | RED 必触发 |
| 20 | generate_gene_embeddings_with_ESM_models | Generate average protein embeddings for a list of Ensembl gene IDs using ESM (Evolutionary Scale Mod | protein, proteome, proteomics | YEL 讨论触发 |
| 21 | model_protein_dimerization_network | Model protein dimerization networks to find equilibrium concentrations of dimers. | protein, proteome, proteomics | RED 必触发 |
| 22 | predict_binding_affinity_protein_1d_sequence | Predicts binding affinity between small molecules and a protein sequence using pre-trained deep lear | protein, proteome, proteomics | RED 必触发 |
| 23 | proteomics-diff-exp | Differential protein expression analysis for mass spectrometry proteomics data using limma and DEqMS | protein, proteome, proteomics | YEL 讨论触发 |
| 24 | run_autosite | Runs AutoSite on a PDB file to identify potential binding sites and returns a research log with the  | protein, proteome, proteomics | YEL 讨论触发 |
| 25 | run_diffdock_with_smiles | Run DiffDock molecular docking using a protein PDB file and a SMILES string for the ligand, executin | protein, proteome, proteomics | YEL 讨论触发 |
| 26 | simulate_protein_signaling_network | Simulate protein signaling network dynamics using ODE-based logic modeling with normalized Hill func | protein, proteome, proteomics | RED 必触发 |
---

## 06_微生物植物 - 微生物/植物 (5 skills)

| # | Skill | Description | Keywords | Trigger |
|---|---|---|---|---|
| 1 | analyze_bacterial_growth_curve | Analyzes bacterial growth curve data to determine growth parameters such as doubling time, growth ra | bacterial, bacteria, yeast | YEL 讨论触发 |
| 2 | get_bacterial_transformation_protocol | Return a standard protocol for bacterial transformation. | bacterial, bacteria, yeast | YEL 讨论触发 |
| 3 | perform_flux_balance_analysis | Perform Flux Balance Analysis (FBA) on a genome-scale metabolic network model and return a research  | bacterial, bacteria, yeast | YEL 讨论触发 |
| 4 | simulate_demographic_history | Simulate DNA sequences with specified demographic and coalescent histories using msprime. | bacterial, bacteria, yeast | YEL 讨论触发 |
| 5 | simulate_metabolic_network_perturbation | Construct and simulate kinetic models of metabolic networks and analyze their responses to perturbat | bacterial, bacteria, yeast | YEL 讨论触发 |
---

## 07_药物临床 - 药物/临床 (23 skills)


| # | Skill | Description | Keywords | Trigger |
|---|---|---|---|---|
| 1 | analyze_abr_waveform_p1_metrics | Extracts P1 amplitude and latency from Auditory Brainstem Response (ABR) waveform data. | drug, clinical, fda | YEL 讨论触发 |
| 2 | analyze_accelerated_stability_of_pharmaceutical_formulations | Analyzes the stability of pharmaceutical formulations under accelerated storage conditions. | drug, clinical, fda | YEL 讨论触发 |
| 3 | analyze_fda_safety_signals | Analyze safety signals across multiple drugs using OpenFDA adverse event data to identify patterns a | drug, clinical, fda | RED 必触发 |
| 4 | analyze_xenograft_tumor_growth_inhibition | Analyze tumor growth inhibition in xenograft models across different treatment groups. | drug, clinical, fda | YEL 讨论触发 |
| 5 | calculate_physicochemical_properties | Calculate key physicochemical properties of a drug candidate molecule. | drug, clinical, fda | YEL 讨论触发 |
| 6 | check_drug_combination_safety | Analyze safety of a drug combination for potential interactions using DDInter database with comprehe | drug, clinical, fda | RED 必触发 |
| 7 | check_fda_drug_recalls | Check for FDA drug recalls and enforcement actions from the OpenFDA database to identify safety conc | drug, clinical, fda | RED 必触发 |
| 8 | clinicaltrials-landscape | 需使用clinicaltrials landscape功能，适用于相关生信分析场景 | drug, clinical, fda | YEL 讨论触发 |
| 9 | drug-response | Connectivity Map+药物敏感性+联合用药预测 | drug, clinical, fda | RED 必触发 |
| 10 | estimate_alpha_particle_radiotherapy_dosimetry | Estimate radiation absorbed doses to tumor and normal organs for alpha-particle radiotherapeutics us | drug, clinical, fda | YEL 讨论触发 |
| 11 | find_alternative_drugs_ddinter | Find alternative drugs that don't interact with contraindicated drugs using DDInter database for saf | drug, clinical, fda | RED 必触发 |
| 12 | get_fda_drug_label_info | Retrieve FDA drug label information including indications, contraindications, warnings, and dosage i | drug, clinical, fda | RED 必触发 |
| 13 | grade_adverse_events_using_vcog_ctcae | Grade and monitor adverse events in animal studies using the VCOG-CTCAE standard. | drug, clinical, fda | YEL 讨论触发 |
| 14 | open-targets | Open Targets平台查询：疾病/靶点→靶点-疾病关联证据→遗传/组学/文献→药物开发管线 | drug, clinical, fda | YEL 讨论触发 |
| 15 | open-targets-graphql | Open Targets Platform GraphQL API查询。靶点-疾病-药物关联 | drug, clinical, fda | YEL 讨论触发 |
| 16 | perform_cosinor_analysis | Performs cosinor analysis on physiological time series data to characterize circadian rhythms. | drug, clinical, fda | YEL 讨论触发 |
| 17 | perform_mwas_cyp2c19_metabolizer_status | Perform a Methylome-wide Association Study (MWAS) to identify CpG sites significantly associated wit | drug, clinical, fda | YEL 讨论触发 |
| 18 | predict_admet_properties | Predicts ADMET (Absorption, Distribution, Metabolism, Excretion, Toxicity) properties for a list of  | drug, clinical, fda | YEL 讨论触发 |
| 19 | retrieve_topk_repurposing_drugs_from_disease_txgnn | Computes TxGNN model predictions for drug repurposing and returns the top predicted drugs with their | drug, clinical, fda | RED 必触发 |
| 20 | simulate_thyroid_hormone_pharmacokinetics | Simulates the transport and binding of thyroid hormones across different tissue compartments using a | drug, clinical, fda | YEL 讨论触发 |
| 21 | survival-analysis | KM曲线+Cox回归+风险评分模型+时间依赖ROC | drug, clinical, fda | RED 必触发 |
| 22 | survival-analysis-clinical | 临床生存分析：临床信息+表达→Kaplan-Meier→Cox回归→log-rank test→预后标志物 | drug, clinical, fda | RED 必触发 |
---
| 23 | scrna-disease-drug-discovery | 疾病scRNA+遗传证据整合的药物靶点优先级排序 | drug, disease, target, 药物靶点 | RED 必触发 |

## 08_报告 - 报告/可视化 (75 skills)

| scipilot-figure-skill | 可视化顾问：先剖析数据→推荐图型→期刊规范→绘制→程序+AI视觉自检 | figure, plot, 画图, 可视化, publication | RED 必触发 |

| # | Skill | Description | Keywords | Trigger |
|---|---|---|---|---|
| 1 | analysis-summary-report | Generate comprehensive analysis summary reports | report, html, ppt | RED 必触发 |
| 2 | bioinformatics-html-report | A zero-dependency Python toolkit for generating publication-quality interactive HTML reports from bi | report, html, ppt | RED 必触发 |
| 3 | cns-visualization | Nature/Cell/Science级别出图模板: UMAP+DotPlot+Violin+Heatmap+Sankey | report, html, ppt | RED 必触发 |
| 4 | docx-generation | Generate professional, Phylo-branded Word documents from scientific analysis results using python-do | report, html, ppt | YEL 讨论触发 |
| 5 | html-report | 生成精美的HTML分析报告，支持图表画廊、响应式布局、打印友好 | report, html, ppt | RED 必触发 |
| 6 | pdf-report-generation | Generate professional, Phylo-branded PDF reports from scientific analysis results using ReportLab. U | report, html, ppt | RED 必触发 |
| 7 | pdf-translate | 使用PDFMathTranslate(pdf2zh)进行学术论文保留排版翻译，公式/图/表格完整保留，支持Google/OpenAI/DeepSeek等24种引擎 | report, html, ppt | YEL 讨论触发 |
| 8 | pdf_reader | 读取 PDF 论文，提取正文、图表、表格、元数据，支持批量处理和 Markdown 转换 | report, html, ppt | YEL 讨论触发 |
| 9 | ppt-generator | AI驱动的PPT生成系统，支持16:9暗色主题，自动布局，图表插入 | report, html, ppt | RED 必触发 |
| 10 | ppt-html | 图文并茂的HTML文献报告生成，支持9项结构化总结+Figure展示 | report, html, ppt | RED 必触发 |
| 11 | ppt-master | AI驱动的SVG-PPT生成系统，多角色协作：策划→执行→质量检查→导出 | report, html, ppt | RED 必触发 |
| 12 | pptx-generation | Generate professional, Phylo-branded PowerPoint presentations from scientific analysis results using | report, html, ppt | RED 必触发 |
| 13 | summarize | 智能总结分析结果/文献/对话/数据：自动识别用户想总结什么（分析结果、文献、对话历史、数据概况），生成结构化摘要。支持生信分析结果总结、文献要点提取、长对话浓缩、数据统计概览。 | report, html, ppt | YEL 讨论触发 |
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
| hdwgcna-official-workflow | hdWGCNA 官方 workflow 端到端运行：SetupForWGCNA→Metacells→SetDatExpr→TestSoftPowers→ConstructNetwork→ModuleE |  | YEL 讨论触发 |
| image-ocr-fallback | >- |  | YEL 讨论触发 |
| multi-role-debate | >- |  | YEL 讨论触发 |
| mesh-decs-tag-extraction | 从文献（title/abstract/PMID）提取 MeSH/DeCS 受控词表标签，用于语义索引类任务与 benchmarker 试卷（TaskA 语义索引 / MESINESP 多语言检索）。触 |  | YEL 讨论触发 |
| pubmed-mesh-indexing | 从 NCBI E-utilities 检索官方 MeSH 标签与 DeCS 编码。使用场景：为文献输出 MeSH 主要标签（语义索引 benchmark）、西班牙语文献输出 DeCS 编码（MESIN |  | YEL 讨论触发 |
| bio-db-benchmark-qa | 作答生物信息学数据库问答 benchmark 考试（LABBench2 dbqa2、MESINESP DeCS、MeSH 语义索引、以及任何"题目给出问题→用真实公共数据库 API 检索→输出结构化答 |  | YEL 讨论触发 |
| mesh-decs-semantic-indexing | Extract MeSH/DeCS semantic indexing labels from biomedical literature (English PubMed MeSH major lab |  | YEL 讨论触发 |
| mesh-semantic-indexing | Generate and verify MeSH/DeCS semantic indexing labels for biomedical articles using NCBI E-utilitie |  | YEL 讨论触发 |
| molecular-cloning-design | Design complete cloning strategies for plasmid engineering (Gibson, Golden Gate, restriction-ligatio |  | YEL 讨论触发 |
| pubmed-mesh-annotation | MeSH 语义索引/文献 MeSH 标签标注：给定文献 title+abstract（或 PMID），从 PubMed 官方索引输出 MeSH 主要标签。适用于语义索引 benchmark（如 试卷1 |  | YEL 讨论触发 |
| atac-paper-reproduction | > |  | YEL 讨论触发 |
| gse278576-atac-aging-comparison | > |  | YEL 讨论触发 |
| competitor-agent-research | 调研/对比其他科研 AI Agent（Biomni/BiOmics 等）的能力与架构。触发词：'XX agent 差距'/'调研一下 XX 的能力和架构'/'竞品分析'/'biomini'/'Biom |  | YEL 讨论触发 |
| wakeup-progress-check | 系统唤醒/进度询问时的任务状态核查规程。定位活跃 task_plan → 终态验证 → 三源交叉验证 → 汇报。触发："[系统唤醒]"、"还在跑吗"、"进度"、cron 唤醒、跨会话恢复。 |  | YEL 讨论触发 |
| alphafold2 | Predict protein structure for monomers and multimers with AlphaFold2 via the ColabFold runner (Mirdi |  | YEL 讨论触发 |
| boltz | Structure prediction for protein, nucleic-acid, and small-molecule complexes with Boltz-2 (Passaro & |  | YEL 讨论触发 |
| borzoi | Predict genome-wide functional tracks (RNA-seq, CAGE, DNase, ChIP) from DNA sequence with Borzoi. Us |  | YEL 讨论触发 |
| chai1 | Structure prediction for protein, nucleic-acid, and small-molecule complexes with the Chai-1 foundat |  | YEL 讨论触发 |
| evo2 | Score, embed, and generate DNA sequences with Evo 2, a long-context genomic foundation model. Use th |  | YEL 讨论触发 |
| openfold3 | Structure prediction using OpenFold3, an open-weights PyTorch reproduction of AlphaFold3 from the Al |  | YEL 讨论触发 |
| proteinmpnn | Inverse-fold a protein backbone (PDB structure) into amino-acid sequence with ProteinMPNN (Dauparas  |  | YEL 讨论触发 |
| scgpt | Embed and annotate single-cell expression data with scGPT, a foundation model for single-cell biolog |  | YEL 讨论触发 |
| debate-core | >- |  | YEL 讨论触发 |
| metabolomics-full-pipeline | 代谢组学全流程分析：LC-MS/GC-MS 峰表 QC → 归一化 → 缺失值填充 → 差异代谢物（t检验/火山图）→ 通路富集（MetaboAnalyst 风格）→ 可视化。输入 peak inte |  | YEL 讨论触发 |
| grill-me | >- | grill, 拷问, 面试方案, 挑毛病, 方案打磨, 设计审查 | RED 必触发 |
| academic-paper-reviewer | Multi-perspective academic paper review with dynamic reviewer personas. Simulates 5 independent revi | 审稿, 论文审稿, 同行评审, 审稿意见, 帮我审论文, 帮我审一下, 审一下这篇, 模拟审稿, 审稿人, 帮我评评, 评一评, referee, peer review, review paper, review this, review the, critique paper, editorial review, manuscript review | RED 必触发 |
| idea-evaluator | 研究想法5维评估（Higher/Faster/Stronger/Cheaper/Broader）+生命周期/能力匹配/范式突破/致命缺陷审计，输出审稿人式裁决；触发词：评估研究想法、这个想法值得做吗、 | 评估研究想法, 评估一下, 这个想法, 研究想法, 研究方向评估, 新点子, 靠不靠谱, novelty check, 评估可行性, score this idea, is this a good research direction, idea evaluation, research idea, evaluate this idea | RED 必触发 |
| nature-response | Nature风格修回信套件：逐点回复（按审稿人隔离）、rebuttal、修回cover letter、LaTeX模板、标红修改稿；触发词：修回信、返修、rebuttal、response to rev | 修回信, 返修, rebuttal, response to reviewers, 审稿意见回复, 逐点回复, 大修回复, 小修回复, 回复审稿人, 修改稿回复, 标红修改, cover letter, 编辑邮件, 返修邮件 | RED 必触发 |
| nature-reviewer | Nature风格投稿前预审（审稿人视角）：原创性/科学重要性/跨学科读者/技术严谨性/非专业可读性五轴评估，输出Major/Minor/blocking；触发词：Nature审稿、预审、投稿前自审、审 | Nature审稿, 预审, 投稿前自审, 审稿人视角, 审稿意见模拟, 帮我审一下论文, referee, mock peer review, manuscript critique, novelty assessment, pre-submission review, review this paper | RED 必触发 |
| paper-polish | 学术论文润色：语法/流畅度修复、语气按证据强度校准、去除AI腔、中译英投稿级改写；绝不编造数据/引用/主张；触发词：润色、论文润色、去AI腔、中译英、polish | 润色, 论文润色, 去AI腔, 去除AI味, AI味, 像AI写的, 读着像AI, AI写的, polish, 中译英, 翻译成英文, 语言修改, awkward wording, overclaiming | RED 必触发 |
| nature-paper-card | 单篇论文深度拆解卡片（固定01-16节：文献定位/研究问题/核心洞见/方法模块逻辑/关键公式/实验→主张证据链/结论边界/批判分析/知识连接/可测试研究想法）；触发词：拆解文献、文献拆解、paper  | 拆解文献, 文献拆解, 拆解论文, paper card, 论文卡片, 深度拆解, 单篇论文分析, evidence chain, 证据链分析, critical analysis of paper, 拆解这篇文献, 拆一下, 帮我拆 | RED 必触发 |
| nature-reader | 全文中英对照精读器：PDF/DOI/arXiv/HTML/粘贴文本 → 双语对照Markdown（图表/公式感知、源锚定、术语表），绝不降级为摘要；触发词：读论文、精读论文、论文翻译、文献阅读、帮我读 | 读论文, 精读论文, 论文翻译, 文献翻译, 文献阅读, 帮我读这篇文章, 帮我读这篇, 帮我读一下, 读一下这篇, 翻译这篇paper, 全文对照, paper translation, read this paper, deep reading, read this | RED 必触发 |
| nature-shared | Internal shared-reference support package for installed nature-writing, nature-polishing, nature-rea |  | YEL 讨论触发 |
| celltype-proportion-comparison | 细胞类型/亚群比例跨组比较箱线图全流程（配对前后 + 独立跨组）。触发词："亚群比例"、"L3 boxplot"、"Proportion (%)"、"6组箱线图"、"FDR标注"、"p值标注"、"画哪 |  | YEL 讨论触发 |
| platform-execution-pitfalls | MemOmics 平台执行层（execute_r/execute_code/skill_view/rail_review 交互）的实测坑与规避。触发：execute_r 报 could not fin |  | YEL 讨论触发 |
| diagram-design | Create branded architecture, IT current-state, flowchart, sequence, state machine, ER/data model, ti |  | YEL 讨论触发 |
| literature-full-summary | 文献全文思路提炼（给人看的方向）：逐篇提取思路/背景/物种/组织/问题/解决方法/方法/结论/验证 9 项结构化摘要，写入文献库 summaries/ 并可跨会话查看。与 literature-par |  | YEL 讨论触发 |
| pre-submission-reviewer | 投稿前审查：以审稿人视角在投稿截止前对论文做五维全面体检（宏观逻辑/写作细节/英语语法/LaTeX格式/图表质量），CRITICAL/MAJOR/MINOR 分级 + 逐条改写建议 + AI腔禁用词与 | 投稿前审查, 投稿前检查, 投前审, 查草稿, 检查草稿, 投稿前体检, 找问题, proofread, check the draft, find issues, 语法检查, 图表质量, AI腔 | RED 必触发 |
| figure-designer | 论文图设计顾问：对三张核心图（Motivated Example动机图/解决方案总览图/实验结果图）给设计范式、布局草图、标注指南、工具选型与QC审计建议。只给设计建议、不实际出图。触发词：设计图、图 | 设计图, 图设计, 图不好看, 图不专业, 选什么图, 图型选择, 布局建议, 图布局, 作图建议, 设计一张图, figure design, design a figure, choose the right chart, figure looks unprofessional, plot design | RED 必触发 |
## 09_内置 - Hermes系统 (15 skills)


| # | Skill | Description | Keywords | Trigger |
|---|---|---|---|---|
| 1 | adaptyv-api | 需使用adaptyv api功能，适用于相关生信分析场景 | code, file, convert | WHT 系统级 |
| 2 | code-writer | 编写Python/R脚本，数据分析代码，函数封装，程序开发 | code, file, convert | WHT 系统级 |
| 3 | computer-use | 控制电脑: 截屏+鼠标点击/拖拽+键盘输入+窗口管理+OCR文字识别。让LLM能操作任何桌面软件。 | code, file, convert | WHT 系统级 |
| 4 | create-bio-skill | 当 skill_view 返回 not found 且没有相似 skill，或用户指定了特定包时触发。自动查询官方文档+文献，按 BioMinI 标准格式创建新的生信 skill（含 SKILL.md | code, file, convert | WHT 系统级 |
| 5 | data-analysis-best-practices | 需使用data analysis best practices功能，适用于相关生信分析场景 | code, file, convert | WHT 系统级 |
| 6 | data-viz | 绘制高质量数据可视化图表：UMAP/tSNE/热图/火山图/小提琴图等 | code, file, convert | WHT 系统级 |
| 7 | experimental-design-statistics | 需使用experimental design statistics功能，适用于相关生信分析场景 | code, file, convert | WHT 系统级 |
| 8 | file-convert | 数据格式转换：CSV/Excel/TSV/H5AD/MTX等常见格式互转 | code, file, convert | WHT 系统级 |
| 9 | find-skill | 智能搜索可用技能：当用户需要某个分析功能但不确定有没有现成技能时，自动搜索239个内置技能+外部蓝图，找到最匹配的并推荐安装。也支持用户说'有没有XXX的技能'时触发。 | code, file, convert | WHT 系统级 |
| 10 | heart-conference-monitor | Monitor and analyze heart conference presentations | code, file, convert | WHT 系统级 |
| 11 | ml-classification | LASSO+RandomForest+SVM+SHAP解释, 支持bulk和scRNA | code, file, convert | WHT 系统级 |
| 12 | phylo-create-skill | Create, test, package, and present reusable skills for Phylo's Biomni platform and bioinformatics wo | code, file, convert | WHT 系统级 |
| 13 | self-improving-agent | 自进化能力：分析成功后自动沉淀经验为新技能；分析失败后自动学习错误模式避免重复犯错；根据使用频率自动优化参数。包括技能沉淀、错误学习、参数进化三大子系统。 | code, file, convert | WHT 系统级 |
---
| 14 | error-recovery | 错误自动修复：根据报错信息查找解决方案 | error, fix, debug, 报错, 修复 | RED 必触发 |

| heartbeat-monitor | 长任务心跳监控 — 独立后台进程持续记录进度，Agent 随时读取汇报 |  | RED 必触发 |
## 10_多组学整合 - 多组学整合 (11 skills)

| # | Skill | Description | Keywords | Trigger |
|---|---|---|---|---|
| 1 | generate_embeddings_with_state | Generate State embeddings for single-cell RNA-seq data using the SE-600M model. This function downlo | multi_omics, multi-omics, rgcca | YEL 讨论触发 |
| 2 | generate_transcriptformer_embeddings | Generate Transcriptformer embeddings for single-cell RNA-seq data. This function downloads model che | multi_omics, multi-omics, rgcca | YEL 讨论触发 |
| 3 | get_uce_embeddings_scRNA | Generate UCE embeddings for single-cell RNA-seq data and map them to a reference dataset for cell ty | multi_omics, multi-omics, rgcca | YEL 讨论触发 |
| 4 | lipidomics-summary-stats | Statistical analysis of lipidomics data | multi_omics, multi-omics, rgcca | YEL 讨论触发 |
| 5 | map_to_ima_interpret_scRNA | Map cell embeddings from the input dataset to the Integrated Megascale Atlas reference dataset using | multi_omics, multi-omics, rgcca | YEL 讨论触发 |
| 6 | multi-omics-integration | 多组学数据整合：scRNA+scATAC+蛋白→MOFA/WNN/seurat5→联合降维→跨组学聚类 | multi_omics, multi-omics, rgcca | RED 必触发 |
| 7 | perform_gene_expression_nmf_analysis | Performs Non-negative Matrix Factorization (NMF) on gene expression data to extract metagenes and th | multi_omics, multi-omics, rgcca | YEL 讨论触发 |
| 8 | rgcca-multiblock | Regularized Generalized Canonical Correlation Analysis for multi-omics | multi_omics, multi-omics, rgcca | YEL 讨论触发 |
| 9 | simulate_renin_angiotensin_system_dynamics | Simulate the time-dependent concentrations of renin-angiotensin system (RAS) components. | multi_omics, multi-omics, rgcca | YEL 讨论触发 |
| 10 | split_modalities | Split a 4D NIfTI file into separate modality files for nnUNet processing. Handles BRATS dataset form | multi_omics, multi-omics, rgcca | YEL 讨论触发 |
| 11 | unsupervised_celltype_transfer_between_scRNA_datasets | Transfer cell type labels from an annotated reference scRNA-seq dataset to an unannotated query data | multi_omics, multi-omics, rgcca | YEL 讨论触发 |
---

## 11_文献搜索 - 文献/数据库 (61 skills)


| # | Skill | Description | Keywords | Trigger |
|---|---|---|---|---|
| 1 | academic-paper-writing | 12-agent论文写作流水线，从大纲到完稿 | query, literature, paper | RED 必触发 |
| 2 | academic-research | 综合学术研究技能：实验方案设计、文献检索、研究规划 | query, literature, paper | GRN 按需触发 |
| 3 | advanced_web_search_claude | Initiate an advanced web search by launching a specialized agent to collect relevant information and | query, literature, paper | GRN 按需触发 |
| 4 | deep-research | 13-agent深度研究团队，系统性文献检索+综述+PRISMA | query, literature, paper | GRN 按需触发 |
| 5 | extract_pdf_content | Extract text content from a PDF file. | query, literature, paper | GRN 按需触发 |
| 6 | extract_url_content | Extract the text content of a webpage using requests and BeautifulSoup. | query, literature, paper | GRN 按需触发 |
| 7 | fetch_supplementary_info_from_doi | Fetches supplementary information for a paper given its DOI and saves it to a specified directory. | query, literature, paper | GRN 按需触发 |
| 8 | knowledge-base-curation | 端到端构建组织特异性多组学知识库。从文献搜索→生物知识提取→基因集构建→ 测序方法参数→多物种同步→YAML验证的完整流程。覆盖 scRNA-seq / ATAC-seq / spatial / bu | query, literature, paper | GRN 按需触发 |
| 9 | literature-param-extraction | 从文献 PDF 提取生信参数并写入知识库。触发场景：拿到真实数据做分析时、知识库缺少对应方法/参数时、需要验证参数来源时。 | query, literature, paper | GRN 按需触发 |
| 10 | literature-preclinical | Preclinical (non-clinical) evidence synthesis. Aligns with the user through a short clarification st | query, literature, paper | GRN 按需触发 |
| 11 | literature-review | General-purpose literature review and evidence synthesis for any scientific topic. Aligns with the u | 综述, 文献综述, systematic review, literature review, 总结文献, 查文献, evidence synthesis | RED 必触发 |
| 12 | omics-dataset-retrieval | 需使用omics dataset retrieval功能，适用于相关生信分析场景 | query, literature, paper | GRN 按需触发 |
| 13 | paper-download | 搜索并下载学术论文PDF，支持arXiv/PubMed/bioRxiv等平台 | query, literature, paper | RED 必触发 |
| 14 | paper-summary | 两级文献解读：Tier1交互框展示(含Mermaid技术路线图+关键图表) → Tier2深度HTML报告(15字段+全部图表) | query, literature, paper | RED 必触发 |
| 15 | paper-translate | 保留排版的PDF全文翻译，支持中英互译 | query, literature, paper | RED 必触发 |
| 16 | query_alphafold | Query the AlphaFold Database API for protein structure predictions or metadata; optionally download  | query, literature, paper | GRN 按需触发 |
| 17 | query_arxiv | Query arXiv for papers based on the provided search query. | query, literature, paper | GRN 按需触发 |
| 18 | query_cbioportal | Query the cBioPortal REST API using natural language or a direct endpoint. | query, literature, paper | GRN 按需触发 |
| 19 | query_chatnt | Answer functions and properties questions for DNA sequences  | query, literature, paper | GRN 按需触发 |
| 20 | query_chembl | Query the ChEMBL REST API via natural language, direct endpoint, or identifiers (chembl_id, smiles,  | query, literature, paper | GRN 按需触发 |
| 21 | query_clinicaltrials | Query the ClinicalTrials.gov API v2 using natural language or a direct endpoint. | query, literature, paper | GRN 按需触发 |
| 22 | query_clinvar | Convert a natural language prompt into a structured ClinVar search query and run it. | query, literature, paper | GRN 按需触发 |
| 23 | query_dailymed | Query the DailyMed RESTful API using natural language or a direct endpoint. | query, literature, paper | GRN 按需触发 |
| 24 | query_dbsnp | Query the NCBI dbSNP database using natural language or direct search term. | query, literature, paper | GRN 按需触发 |
| 25 | query_drug_interactions | Query drug-drug interactions from DDInter database to identify potential interactions, mechanisms, a | query, literature, paper | RED 必触发 |
| 26 | query_emdb | Query the Electron Microscopy Data Bank (EMDB) using natural language or a direct endpoint. | query, literature, paper | GRN 按需触发 |
| 27 | query_encode | Query the ENCODE Portal API to locate functional genomics data (experiments, files, biosamples, data | query, literature, paper | GRN 按需触发 |
| 28 | query_ensembl | Query the Ensembl REST API using natural language or a direct endpoint. | query, literature, paper | GRN 按需触发 |
| 29 | query_fda_adverse_events | Query FDA adverse event reports for specific drugs from the OpenFDA database to identify potential s | query, literature, paper | RED 必触发 |
| 30 | query_geo | Query the NCBI GEO database (GDS/GEOPROFILES) using natural language or direct search term. | query, literature, paper | GRN 按需触发 |
| 31 | query_gnomad | Query gnomAD for variants in a gene using natural language or direct gene symbol. | query, literature, paper | GRN 按需触发 |
| 32 | query_gtopdb | Query the Guide to PHARMACOLOGY (GtoPdb) database using natural language or a direct endpoint. | query, literature, paper | GRN 按需触发 |
| 33 | query_gwas_catalog | Query the GWAS Catalog API using natural language or a direct endpoint. | query, literature, paper | RED 必触发 |
| 34 | query_interpro | Query the InterPro REST API using natural language or a direct endpoint. | query, literature, paper | GRN 按需触发 |
| 35 | query_iucn | Query the IUCN Red List API using natural language or a direct endpoint. | query, literature, paper | GRN 按需触发 |
| 36 | query_jaspar | Query the JASPAR REST API for transcription factor binding profiles. | query, literature, paper | GRN 按需触发 |
| 37 | query_kegg | Take a natural language prompt and convert it to a structured KEGG API query. | query, literature, paper | RED 必触发 |
| 38 | query_monarch | Query the Monarch Initiative API using natural language or a direct endpoint. | query, literature, paper | GRN 按需触发 |
| 39 | query_mpd | Query the Mouse Phenome Database (MPD) using natural language or a direct endpoint. | query, literature, paper | GRN 按需触发 |
| 40 | query_openfda | Query the OpenFDA API using natural language or direct parameters. | query, literature, paper | RED 必触发 |
| 41 | query_opentarget | Query the OpenTargets Platform API using natural language or a direct GraphQL query. | query, literature, paper | GRN 按需触发 |
| 42 | query_paleobiology | Query the Paleobiology Database (PBDB) API using natural language or a direct endpoint. | query, literature, paper | GRN 按需触发 |
| 43 | query_pdb | Query the RCSB PDB database using natural language or a direct structured query. | query, literature, paper | GRN 按需触发 |
| 44 | query_pdb_identifiers | Retrieve detailed data and/or download files for PDB identifiers. | query, literature, paper | GRN 按需触发 |
| 45 | query_pride | Query the PRIDE proteomics database using natural language or a direct endpoint. | query, literature, paper | GRN 按需触发 |
| 46 | query_pubchem | Query the PubChem PUG-REST API using natural language or a direct endpoint. | query, literature, paper | GRN 按需触发 |
| 47 | query_pubmed | Query PubMed for papers based on the provided search query. | query, literature, paper | GRN 按需触发 |
| 48 | query_quickgo | Query the QuickGO API using natural language or a direct endpoint. | query, literature, paper | GRN 按需触发 |
| 49 | query_reactome | Query the Reactome database using natural language or a direct endpoint; optionally download pathway | query, literature, paper | GRN 按需触发 |
| 50 | query_regulomedb | Query the RegulomeDB database using natural language or direct endpoint. | query, literature, paper | GRN 按需触发 |
| 51 | query_remap | Query the ReMap database for regulatory elements and transcription factor binding. | query, literature, paper | GRN 按需触发 |
| 52 | query_scholar | Query Google Scholar for papers based on the provided search query and return the first search resul | query, literature, paper | GRN 按需触发 |
| 53 | query_stringdb | Query the STRING protein interaction database using natural language or direct endpoint. | query, literature, paper | GRN 按需触发 |
| 54 | query_synapse | Query Synapse REST API for biomedical datasets/files using natural language or structured search par | query, literature, paper | GRN 按需触发 |
| 55 | query_ucsc | Query the UCSC Genome Browser API using natural language or a direct endpoint. | query, literature, paper | GRN 按需触发 |
| 56 | query_unichem | Query the UniChem 2.0 REST API using natural language or a direct endpoint. | query, literature, paper | GRN 按需触发 |
| 57 | query_uniprot | Query the UniProt REST API using either natural language or a direct endpoint. | query, literature, paper | GRN 按需触发 |
| 58 | query_worms | Query the World Register of Marine Species (WoRMS) REST API using natural language or a direct endpo | query, literature, paper | GRN 按需触发 |
| 59 | search_google | Search using Google search and return formatted results. | query, literature, paper | GRN 按需触发 |
| 60 | web-research | 网络搜索和调研，获取最新信息，综合多个来源生成报告 | query, literature, paper | GRN 按需触发 |
---
| 61 | research-plan | Mermaid技术路线图+模块映射表生成 | 技术路线, 分析路线, 研究方案, research plan | RED 必触发 |

## 12_分子生物学 - 分子克隆 (21 skills)


| # | Skill | Description | Keywords | Trigger |
|---|---|---|---|---|
| 1 | align_sequences | Align short sequences (primers) to a longer sequence, allowing for one mismatch. Checks both forward | primer, plasmid, pcr | GRN 按需触发 |
| 2 | annotate_open_reading_frames | Find all Open Reading Frames (ORFs) in a DNA sequence using Biopython, searching both forward and re | primer, plasmid, pcr | GRN 按需触发 |
| 3 | annotate_plasmid | Annotate a DNA sequence using pLannotate's command-line interface. | primer, plasmid, pcr | RED 必触发 |
| 4 | blast_sequence | Identify a DNA or protein sequence using NCBI BLAST. | primer, plasmid, pcr | GRN 按需触发 |
| 5 | design_golden_gate_oligos | Design complementary oligonucleotides with Type IIS restriction enzyme overhangs for Golden Gate ass | primer, plasmid, pcr | GRN 按需触发 |
| 6 | design_primer | Design a single primer within the given sequence window. | primer, plasmid, pcr | RED 必触发 |
| 7 | design_verification_primers | Design Sanger sequencing primers to verify a specific region in a plasmid. First tries to use primer | primer, plasmid, pcr | RED 必触发 |
| 8 | digest_sequence | Simulates restriction enzyme digestion of a DNA sequence and returns the resulting fragments with th | primer, plasmid, pcr | GRN 按需触发 |
| 9 | find_restriction_enzymes | Finds common restriction enzyme sites in a DNA sequence and returns their cut positions. | primer, plasmid, pcr | GRN 按需触发 |
| 10 | find_restriction_sites | Identifies restriction enzyme sites in a given DNA sequence for specified enzymes. | primer, plasmid, pcr | GRN 按需触发 |
| 11 | get_gene_coding_sequence | Retrieves the coding sequence(s) of a specified gene from NCBI Entrez. | primer, plasmid, pcr | GRN 按需触发 |
| 12 | get_golden_gate_assembly_protocol | Return a customized protocol for Golden Gate assembly based on the number of inserts and specific DN | primer, plasmid, pcr | GRN 按需触发 |
| 13 | get_oligo_annealing_protocol | Return a standard protocol for annealing oligonucleotides without phosphorylation. | primer, plasmid, pcr | GRN 按需触发 |
| 14 | get_plasmid_sequence | Unified function to retrieve plasmid sequences from either Addgene or NCBI. If is_addgene is True or | primer, plasmid, pcr | RED 必触发 |
| 15 | golden_gate_assembly | Simulate Golden Gate assembly to predict final construct sequences from backbone and fragment sequen | primer, plasmid, pcr | GRN 按需触发 |
| 16 | interspecies_gene_conversion | Convert ENSEMBL gene IDs between different species using BioMart homology mapping. This function con | primer, plasmid, pcr | GRN 按需触发 |
| 17 | microplate-layout-design | 需使用microplate layout design功能，适用于相关生信分析场景 | primer, plasmid, pcr | GRN 按需触发 |
| 18 | pcr-primer-design | PCR引物设计：DNA模板序列→Primer3→引物对(正向/反向)→Tm/GC含量→特异性检查→PCR条件优化 | primer, plasmid, pcr | RED 必触发 |
| 19 | pcr_simple | Simulate PCR amplification with given primers and sequence. | primer, plasmid, pcr | RED 必触发 |
| 20 | perform_pcr_and_gel_electrophoresis | Performs PCR amplification of a target transgene and visualizes results using agarose gel electropho | primer, plasmid, pcr | RED 必触发 |
---
| 21 | phylogenetics-toolkit | 系统发育树构建+MCMC+祖先状态重建 | phylogenetics, tree, 系统发育, 进化 | YEL 讨论触发 |

## 13_组织学病理 - 组织学/病理 (5 skills)

| # | Skill | Description | Keywords | Trigger |
|---|---|---|---|---|
| 1 | analyze_thrombus_histology | Analyze histological images of thrombus samples stained with H&E to identify and quantify different  | histology, h&e, stain | GRN 按需触发 |
| 2 | quantify_amyloid_beta_plaques | Analyzes an image to detect and quantify amyloid-beta plaques, returning a detailed analysis log. | histology, h&e, stain | GRN 按需触发 |
| 3 | quantify_cell_cycle_phases_from_microscopy | Quantify the percentage of cells in each cell cycle phase using Calcofluor white stained microscopy  | histology, h&e, stain | GRN 按需触发 |
| 4 | quantify_corneal_nerve_fibers | Quantify the volume/density of immunofluorescence-labeled corneal nerve fibers. | histology, h&e, stain | GRN 按需触发 |
| 5 | run_3d_chondrogenic_aggregate_assay | Generates a detailed protocol for performing a 3D chondrogenic aggregate culture assay to evaluate c | histology, h&e, stain | GRN 按需触发 |
---

## 14_细胞生物学实验 - 细胞生物学 (6 skills)

| # | Skill | Description | Keywords | Trigger |
|---|---|---|---|---|
| 1 | analyze_cell_senescence_and_apoptosis | Analyze flow cytometry data to quantify senescent and apoptotic cell populations. | flow cytometry, facs, cell sorting | GRN 按需触发 |
| 2 | analyze_cfse_cell_proliferation | Analyze CFSE-labeled cell samples to quantify cell division and proliferation. | flow cytometry, facs, cell sorting | GRN 按需触发 |
| 3 | isolate_purify_immune_cells | Simulates the isolation and purification of immune cells from tissue samples. | flow cytometry, facs, cell sorting | GRN 按需触发 |
| 4 | perform_facs_cell_sorting | Performs Fluorescence-Activated Cell Sorting (FACS) to enrich cell populations based on fluorescence | flow cytometry, facs, cell sorting | GRN 按需触发 |
| 5 | track_immune_cells_under_flow | Track immune cells under flow conditions and classify their behaviors. | flow cytometry, facs, cell sorting | GRN 按需触发 |
---

| secretome-classification | > |  | YEL 讨论触发 |
## 15_CRISPR基因编辑 - CRISPR (4 skills)

| # | Skill | Description | Keywords | Trigger |
|---|---|---|---|---|
| 1 | analyze_crispr_genome_editing | Analyzes CRISPR-Cas9 genome editing results by comparing original and edited sequences. | crispr, sgrna, knockout | RED 必触发 |
| 2 | design_knockout_sgrna | Design sgRNAs for CRISPR knockout by searching pre-computed sgRNA libraries. Returns optimized guide | crispr, sgrna, knockout | RED 必触发 |
| 3 | pooled-crispr-screens | CRISPR Pooled筛选分析：sgRNA计数→MAGeCK→gene essentiality→正/负选择→通路富集→候选基因 | crispr, sgrna, knockout | RED 必触发 |
| 4 | sgrna-design | CRISPR sgRNA design with three-tiered scoring | crispr, sgrna, knockout | RED 必触发 |

---
*274 skills, 15 domains*