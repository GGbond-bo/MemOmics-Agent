#!/usr/bin/env python3
"""Hybrid skill matching for MemOmics — keyword aliases + TF-IDF fusion.
Loaded as a lightweight add-on to skills_tool.py without modifying it.
"""
import json, os, re, pickle, time
from collections import defaultdict, OrderedDict
import numpy as np


# ===== Chinese + English alias table (curated from 275 skills) =====
# Format: query_keyword -> canonical_skill_name
CHINESE_ALIASES = {
    # ---- RNA / scRNA ----
    "质量控制": "scrna-qc",
    "qc": "scrna-qc",
    "去批次": "create_harmony_embeddings_scRNA",
    "批次效应": "create_harmony_embeddings_scRNA",
    "批次": "create_harmony_embeddings_scRNA",
    "整合": "create_harmony_embeddings_scRNA",
    "harmony": "create_harmony_embeddings_scRNA",
    "batch correction": "create_harmony_embeddings_scRNA",
    "去污染": "scrna-qc",
    "doublet": "scrublet-doublet",
    "双细胞": "scrublet-doublet",
    "细胞通讯": "cellchat-v2",
    "通讯": "cellchat-v2",
    "cellchat": "cellchat-v2",
    "cell communication": "cellchat-v2",
    "配体受体": "cellchat-v2",
    "轨迹": "trajectory-analysis",
    "拟时序": "trajectory-analysis",
    "伪时间": "trajectory-analysis",
    "分化轨迹": "trajectory-analysis",
    "pseudotime": "trajectory-analysis",
    "monocle": "trajectory-analysis",
    "slingshot": "trajectory-analysis",
    "cellrank": "trajectory-analysis",
    "dynverse": "trajectory-analysis",
    "velocity": "rna-velocity",
    "速率": "rna-velocity",
    "差异表达": "deg-analysis",
    "differential expression": "deg-analysis",
    "差异基因": "deg-analysis",
    "deg": "deg-analysis",
    "上调下调": "deg-analysis",
    "富集": "functional-enrichment",
    "go分析": "functional-enrichment",
    "go富集": "functional-enrichment",
    "gsea": "functional-enrichment",
    "gene set enrichment": "functional-enrichment",
    "通路": "functional-enrichment",
    "kegg": "functional-enrichment",
    "拷贝数": "infercnv",
    "cnv": "infercnv",
    "单细胞聚类": "scrna-clustering",
    "聚类": "scrna-clustering",
    "clustering": "scrna-clustering",
    "细胞注释": "annotate_celltype_scRNA",
    "细胞类型": "annotate_celltype_scRNA",
    "celltypist": "annotate_celltype_scRNA",
    "single r": "annotate_celltype_scRNA",
    "scvi": "create_scvi_embeddings_scRNA",
    "细胞周期": "cell-cycle-scoring",
    "cell cycle": "cell-cycle-scoring",
    "线粒体": "scrna-qc",
    "mitochondrial": "scrna-qc",
    "h5ad": "scrna-qc",
    "seurat": "scrna-qc",
    "scanpy": "scrna-qc",
    "cellbender": "cellbender-background-removal",
    "去背景": "cellbender-background-removal",
    "soupx": "soupx-decontamination",
    
    # ---- ATAC ----
    "atac": "atac-peak-calling",
    "peak": "atac-peak-calling",
    "染色质": "atac-peak-calling",
    "motif": "atac-motif-analysis",
    "footprint": "atac-footprinting",
    
    # ---- 空间组 ----
    "空间转录组": "spatial-transcriptomics-analysis",
    "空间组": "spatial-transcriptomics-analysis",
    "spatial": "spatial-transcriptomics-analysis",
    "h&e": "analyze_cns_lesion_histology",
    "he染色": "analyze_cns_lesion_histology",
    "免疫组化": "analyze_immunohistochemistry_image",
    "ihc": "analyze_immunohistochemistry_image",
    "cell2location": "cell2location",
    "反卷积": "cell2location",
    "stereo": "stereo-seq-analysis",
    "华大": "stereo-seq-analysis",
    "merfish": "merfish-analysis",
    "vizgen": "merfish-analysis",
    "xenium": "xenium-analysis",
    "visium": "visium-analysis",
    
    # ---- Bulk ----
    "bulk": "bulk-rnaseq-differential-expression",
    "rnaseq": "bulk-rnaseq-differential-expression",
    "芯片": "microarray-analysis",
    "microarray": "microarray-analysis",
    "甲基化": "methylation-analysis",
    "methylation": "methylation-analysis",
    "表观": "epigenetic-analysis",
    "chip": "chip-atlas-target-genes",
    "chipseq": "chip-atlas-target-genes",
    "gwas": "gwas-phewas",
    "孟德尔": "mendelian-randomization-twosamplemr",
    "mendel": "mendelian-randomization-twosamplemr",
    "eqtl": "eqtl-analysis",
    "sqtl": "sqtl-analysis",
    
    # ---- 蛋白 ----
    "蛋白结构": "alphafold-prediction",
    "alphafold": "alphafold-prediction",
    "对接": "docking_autodock_vina",
    "docking": "docking_autodock_vina",
    "分子对接": "docking_autodock_vina",
    "vina": "docking_autodock_vina",
    "autodock": "docking_autodock_vina",
    "western": "analyze_western_blot",
    "western blot": "analyze_western_blot",
    "免疫沉淀": "immunoprecipitation-analysis",
    "ip": "immunoprecipitation-analysis",
    "coip": "immunoprecipitation-analysis",
    "质谱": "mass-spectrometry-data-analysis",
    "proteomics": "mass-spectrometry-data-analysis",
    "蛋白组": "mass-spectrometry-data-analysis",
    "elisa": "elisa-data-analysis",
    "流式": "facs-analysis",
    "细胞分选": "facs-analysis",
    "facs": "facs-analysis",
    "flow cytom": "facs-analysis",
    "b细胞": "bcr-repertoire-analysis",
    "t细胞": "tcr-repertoire-analysis",
    "bcr": "bcr-repertoire-analysis",
    "tcr": "tcr-repertoire-analysis",
    "抗体": "antibody-analysis",
    "antibody": "antibody-analysis",
    
    # ---- 药物临床 ----
    "生存分析": "survival-analysis",
    "survival": "survival-analysis",
    "kaplan": "survival-analysis",
    "km曲线": "survival-analysis",
    "cox": "survival-analysis",
    "药物靶点": "drug-target-prediction",
    "drug": "drug-target-prediction",
    "靶点": "drug-target-prediction",
    "临床试验": "clinical-trial-analysis",
    "fda": "fda-adverse-event-analysis",
    "不良反应": "fda-adverse-event-analysis",
    
    # ---- 分子生物学 ----
    "引物": "design-primer",
    "pcr": "design-primer",
    "primer": "design-primer",
    "质粒": "plasmid-construction",
    "plasmid": "plasmid-construction",
    "酶切": "find-restriction-enzymes",
    "restriction": "find-restriction-enzymes",
    "orf": "annotate-open-reading-frames",
    "sgrna": "sgrna-design",
    "crispr": "sgrna-design",
    "基因编辑": "sgrna-design",
    "knockout": "sgrna-design",
    "blast": "blast-search",
    "比对": "blast-search",
    "同源": "blast-search",
    
    # ---- 可视化 ----
    "热图": "cns-visualization",
    "heatmap": "cns-visualization",
    "火山图": "cns-visualization",
    "volcano": "cns-visualization",
    "umap": "cns-visualization",
    "tsne": "cns-visualization",
    "小提琴": "cns-visualization",
    "dotplot": "cns-visualization",
    "circos": "cns-visualization",
    "cns": "cns-visualization",
    "nature": "cns-visualization",
    "发表级": "cns-visualization",
    "figure": "cns-visualization",
    
    # ---- 文献 ----
    "查文献": "pubmed-search",
    "pubmed": "pubmed-search",
    "文献": "pubmed-search",
    "下载论文": "paper-download",
    "pdf": "paper-download",
    "论文": "paper-download",
    "paper": "paper-download",
    "综述": "literature-review",
    "literature": "literature-review",
    "文献计量": "bibliometric-analysis",
    "citation": "bibliometric-analysis",
    
    # ---- 报告 ----
    "报告": "bioinformatics-html-report",
    "html报告": "bioinformatics-html-report",
    "生成报告": "bioinformatics-html-report",
    "报告生成": "bioinformatics-html-report",
    "ppt": "bioinformatics-html-report",
    
    # ---- 系统 ----
    "安装": "create-bio-skill",
    "创建skill": "create-bio-skill",
    "新建skill": "create-bio-skill",
    "环境检查": "env-check",
    
    # ---- 多组学 ----
    "多组学": "multi-omics-integration",
    "multiomics": "multi-omics-integration",
    "wgcna": "wgcna-coexpression",
    "共表达": "wgcna-coexpression",
    "调控网络": "grn-pyscenic",
    "grn": "grn-pyscenic",
    "pyscenic": "grn-pyscenic",
    "metabolomics": "metabolomics-analysis",
    "代谢组": "metabolomics-analysis",
    "脂质组": "lipidomics-analysis",
    "lipidomics": "lipidomics-analysis",
    "微生物组": "microbiome-analysis",
    "microbiome": "microbiome-analysis",
    "16s": "microbiome-analysis",
    "宏基因组": "metagenomics-analysis",
    "metagenom": "metagenomics-analysis",
    
    # ---- 遗传/变异 ----
    "snp": "genetic-variant-annotation",
    "snv": "genetic-variant-annotation",
    "基因变异": "genetic-variant-annotation",
    "snp注释": "genetic-variant-annotation",
    "变异注释": "genetic-variant-annotation",
    "gwas": "gwas-phewas",
    "eqtl": "genetic-variant-annotation",
    "基因组关联": "gwas-analysis",
    
    # ---- 其他 ----
    "cca": "create_harmony_embeddings_scRNA",
    "mag": "mageck_analysis",
    "sgrna-seq": "mageck_analysis",
    "guide": "sgrna-design",
        "bulk rna": "bulk-rnaseq-differential-expression",
    "bulk rnaseq": "bulk-rnaseq-differential-expression",
    "deseq": "bulk-rnaseq-differential-expression",
    "rna-seq差异": "bulk-rnaseq-differential-expression",
    "转录组差异": "bulk-rnaseq-differential-expression",
    "hdwgcna": "hdwgcna",
    "高维wgcna": "hdwgcna",
    "bulk聚类": "bulk-omics-clustering",
    "counts to de": "bulk-rnaseq-counts-to-de-deseq2",
    "atac全流程": "atac-seq-memomics",
    "atac-seq": "atac-seq-memomics",
    "chip atlas": "chip-atlas-target-genes",
    "chip-atlas": "chip-atlas-target-genes",
    "homer motif": "find_enriched_motifs_with_homer",
    "chip diff": "chip-atlas-diff-analysis",
    "fda安全": "analyze_fda_safety_signals",
    "药物安全": "analyze_fda_safety_signals",
    "fda safety": "analyze_fda_safety_signals",
    "药物联用": "check_drug_combination_safety",
    "drug combination": "check_drug_combination_safety",
    "fda召回": "check_fda_drug_recalls",
    "clinical trial": "clinicaltrials-landscape",
    "药物反应": "drug-response",
    "drug response": "drug-response",
    "药物标签": "get_fda_drug_label_info",
    "crispr编辑": "analyze_crispr_genome_editing",
    "twas": "gwas-to-function-twas",
    "孟德尔随机化": "mendelian-randomization-twosamplemr",
    "mendelian randomization": "mendelian-randomization-twosamplemr",
    "prs": "polygenic-risk-score-prs-catalog",
    "多基因风险": "polygenic-risk-score-prs-catalog",
    "基因必需": "gene-essentiality",
    "gene essential": "gene-essentiality",
    "质粒注释": "annotate_plasmid",
    "引物设计": "design_primer",
    "primer design": "design_primer",
    "验证引物": "design_verification_primers",
    "限制酶": "find_restriction_enzymes",
    "酶切位点": "find_restriction_sites",
    "enzyme cut": "find_restriction_sites",
    "gwas catalog": "query_gwas_catalog",
    "ppt生成": "ppt-html",
    "生存临床": "survival-analysis-clinical",
    "多组学整合": "multi-omics-integration",
    "multi omics": "multi-omics-integration",
    "整合分析": "multi-omics-integration",
    "diff enriched genes": "functional-enrichment-from-degs",
    "deg go": "functional-enrichment-from-degs",
    "deseq2 pathway": "functional-enrichment-from-degs",
    "clinical survival analysis": "survival-analysis-clinical",
    "single cell disease drug": "scrna-disease-drug",
    "disease drug discovery": "scrna-disease-drug",
    "bulk clustering": "bulk-omics-clustering",
    "bulk dimensionality": "bulk-omics-clustering",
    "cell cycle phase": "estimate_cell_cycle_phase_durations",
    "ebv antibody": "analyze_ebv_antibody_titers",
    "longitudinal progression": "disease-progression-longitudinal",
    "get plasmid": "get_plasmid_sequence",
    "chip differential": "chip-atlas-diff-analysis",
    "chipseq enrichment": "chip-atlas-peak-enrichment",
    "chip target gene": "chip-atlas-target-genes",
    "macs2 calling": "perform_chipseq_peak_calling_with_macs2",
    "homer enrichment": "find_enriched_motifs_with_homer",
    "spatial transcriptome": "spatial-transcriptomics",
    "spatial omics": "spatial-transcriptomics",
    "spatial analysis": "spatial-transcriptomics",
    "multi omics integration": "multi-omics-integration",
    "omics integration": "multi-omics-integration",
    "bulk differential": "bulk-rnaseq-differential-expression",
    "bulk deg analysis": "bulk-rnaseq-differential-expression",
    "counts to deseq": "bulk-rnaseq-counts-to-de-deseq2",
    "variant annotation snp": "genetic-variant-annotation",
    "gwas function": "gwas-to-function-twas",
    "two sample mr": "mendelian-randomization-twosamplemr",
    "polygenic score": "polygenic-risk-score-prs-catalog",
    "risk score prs": "polygenic-risk-score-prs-catalog",
    "dbsnp query": "query_dbsnp",
    "blast search": "blast_sequence",
    "knockout design": "design_knockout_sgrna",
    "generate docx": "docx-generation",
    "transcriptformer embedding": "generate_transcriptformer_embeddings",
    "cellbender background": "cellbender-remove-background",
    "remove background": "cellbender-remove-background",
    "doublet finder": "doubletfinder-remove-doublets",
    "remove doublet": "doubletfinder-remove-doublets",
    "milor pseudobulk": "milor",
"网络药理学": "drug-target-prediction",

    "流式细胞免疫分型": "analyze_flow_cytometry_immunophenotyping",
    "流式数据分析": "analyze_flow_cytometry_immunophenotyping",
    "免疫表型分析": "analyze_flow_cytometry_immunophenotyping",
    "FACS免疫表型": "analyze_flow_cytometry_immunophenotyping",
    "线粒体形态分析": "analyze_mitochondrial_morphology_and_potential",
    "线粒体膜电位": "analyze_mitochondrial_morphology_and_potential",
    "mitochondrial morphology": "analyze_mitochondrial_morphology_and_potential",
    "Bulk RNA-seq差异分析": "bulk-rnaseq-counts-to-de-deseq2",
    "DESeq2差异基因": "bulk-rnaseq-counts-to-de-deseq2",
    "counts转差异表达": "bulk-rnaseq-counts-to-de-deseq2",
    "细胞通讯分析": "cell-cell-communication",
    "细胞间相互作用": "cell-cell-communication",
    "配体受体分析": "cell-cell-communication",
    "共表达网络": "coexpression-network",
    "基因共表达": "coexpression-network",
    "co-expression network": "coexpression-network",
    "MiloR差异丰度": "milor",
    "邻域差异分析": "milor",
    "细胞群体差异分析": "milor",
    "differential abundance": "milor",
    "流式细胞分选": "perform_facs_cell_sorting",
    "FACS分选": "perform_facs_cell_sorting",
    "细胞分选方案": "perform_facs_cell_sorting",
    "荧光激活分选": "perform_facs_cell_sorting",
    "CRISPR筛选分析": "pooled-crispr-screens",
    "pooled CRISPR screen": "pooled-crispr-screens",
    "MAGeCK分析": "pooled-crispr-screens",
    "sgRNA富集分析": "pooled-crispr-screens",
    "细胞运动分析": "quantify_and_cluster_cell_motility",
    "细胞迁移追踪": "quantify_and_cluster_cell_motility",
    "细胞motility": "quantify_and_cluster_cell_motility",
    "time-lapse细胞追踪": "quantify_and_cluster_cell_motility",
    "细胞周期分析": "quantify_cell_cycle_phases_from_microscopy",
    "细胞周期分期": "quantify_cell_cycle_phases_from_microscopy",
    "显微镜细胞周期": "quantify_cell_cycle_phases_from_microscopy",
    "FUCCI": "quantify_cell_cycle_phases_from_microscopy",
    "单细胞分析全流程": "single-cell-analysis-pipeline",
    "scRNA完整分析": "single-cell-analysis-pipeline",
    "单细胞pipeline": "single-cell-analysis-pipeline",
    "空间转录组分析": "spatial-transcriptomics-analysis",
    "spatial transcriptomics": "spatial-transcriptomics-analysis",
    "空间组学流程": "spatial-transcriptomics-analysis",
    "多样本整合": "scrna-multisample-integration",
    "scRNA整合分析": "scrna-multisample-integration",
    "Harmony整合": "scrna-multisample-integration",
    "批次校正整合": "scrna-multisample-integration",
    "细胞类型注释": "cell-type-annotation",
    "自动注释": "cell-type-annotation",
    "SingleR": "cell-type-annotation",
    "细胞鉴定": "cell-type-annotation",
    "拟时序分析": "trajectory-inference",
    "轨迹推断": "trajectory-inference",
    "发育轨迹": "trajectory-inference",
    "RNA velocity": "trajectory-inference",
    "RNA速率分析": "rna-velocity",
    "RNA velocity": "rna-velocity",
    "velocyto": "rna-velocity",
    "scVelo": "rna-velocity",
    "剪接动力学": "rna-velocity",
    "比较基因组": "analyze_comparative_genomics_and_haplotypes",
    "单倍型分析": "analyze_comparative_genomics_and_haplotypes",
    "haplotype": "analyze_comparative_genomics_and_haplotypes",
    "系统发育基因组": "analyze_comparative_genomics_and_haplotypes",
    "CRISPR编辑分析": "analyze_crispr_genome_editing",
    "基因编辑验证": "analyze_crispr_genome_editing",
    "CRISPR结果分析": "analyze_crispr_genome_editing",
    "编辑效率": "analyze_crispr_genome_editing",
    "蛋白质系统发育": "analyze_protein_phylogeny",
    "蛋白进化树": "analyze_protein_phylogeny",
    "系统发育树": "analyze_protein_phylogeny",
    "protein phylogeny": "analyze_protein_phylogeny",
    "贝叶斯精细定位": "bayesian_finemapping_with_deep_vi",
    "GWAS精细定位": "bayesian_finemapping_with_deep_vi",
    "fine-mapping": "bayesian_finemapping_with_deep_vi",
    "DeepVI": "bayesian_finemapping_with_deep_vi",
    "GSEA数据库列表": "get_gene_set_enrichment_analysis_supported_database_list",
    "富集分析数据库": "get_gene_set_enrichment_analysis_supported_database_list",
    "MSigDB": "get_gene_set_enrichment_analysis_supported_database_list",
    "基因集数据库": "get_gene_set_enrichment_analysis_supported_database_list",
    "ARCHS4数据查询": "get_rna_seq_archs4",
    "ARCHS4 RNA-seq": "get_rna_seq_archs4",
    "基因表达ARCHS4": "get_rna_seq_archs4",
    "转录因子结合位点": "identify_transcription_factor_binding_sites",
    "TF结合位点": "identify_transcription_factor_binding_sites",
    "TFBS预测": "identify_transcription_factor_binding_sites",
    "motif扫描": "identify_transcription_factor_binding_sites",
    "IMA单细胞映射": "map_to_ima_interpret_scRNA",
    "单细胞参考映射": "map_to_ima_interpret_scRNA",
    "scRNA投影": "map_to_ima_interpret_scRNA",
    "参考图谱映射": "map_to_ima_interpret_scRNA",
    "ChIP-seq peak calling": "perform_chipseq_peak_calling_with_macs2",
    "MACS2峰值检测": "perform_chipseq_peak_calling_with_macs2",
    "peak calling": "perform_chipseq_peak_calling_with_macs2",
    "PCR扩增": "perform_pcr_and_gel_electrophoresis",
    "凝胶电泳": "perform_pcr_and_gel_electrophoresis",
    "PCR引物设计": "perform_pcr_and_gel_electrophoresis",
    "琼脂糖凝胶": "perform_pcr_and_gel_electrophoresis",
    "主动脉直径分析": "analyze_aortic_diameter_and_geometry",
    "血管几何分析": "analyze_aortic_diameter_and_geometry",
    "主动脉几何测量": "analyze_aortic_diameter_and_geometry",
    "vascular geometry": "analyze_aortic_diameter_and_geometry",
    "骨微CT分析": "analyze_bone_microct_morphometry",
    "骨形态计量": "analyze_bone_microct_morphometry",
    "microCT骨分析": "analyze_bone_microct_morphometry",
    "骨小梁分析": "analyze_bone_microct_morphometry",
    "血栓组织学分析": "analyze_thrombus_histology",
    "血栓图像分析": "analyze_thrombus_histology",
    "thrombus histology": "analyze_thrombus_histology",
    "淀粉样斑块定量": "quantify_amyloid_beta_plaques",
    "Aβ斑块分析": "quantify_amyloid_beta_plaques",
    "amyloid plaque": "quantify_amyloid_beta_plaques",
    "阿尔茨海默斑块": "quantify_amyloid_beta_plaques",
    "甲状腺激素药代": "simulate_thyroid_hormone_pharmacokinetics",
    "thyroid pharmacokinetics": "simulate_thyroid_hormone_pharmacokinetics",
    "激素模拟": "simulate_thyroid_hormone_pharmacokinetics",
    "细胞衰老分析": "analyze_cell_senescence_and_apoptosis",
    "凋亡检测": "analyze_cell_senescence_and_apoptosis",
    "senescence分析": "analyze_cell_senescence_and_apoptosis",
    "SA-β-gal": "analyze_cell_senescence_and_apoptosis",
    "CNV拷贝数分析": "analyze_copy_number_purity_ploidy_and_focal_events",
    "CNVkit分析": "analyze_copy_number_purity_ploidy_and_focal_events",
    "纯度倍性": "analyze_copy_number_purity_ploidy_and_focal_events",
    "拷贝数变异": "analyze_copy_number_purity_ploidy_and_focal_events",
    "DDR网络分析": "analyze_ddr_network_in_cancer",
    "DNA损伤修复": "analyze_ddr_network_in_cancer",
    "DNA damage response": "analyze_ddr_network_in_cancer",
    "癌症DDR": "analyze_ddr_network_in_cancer",
    "FDA安全信号分析": "analyze_fda_safety_signals",
    "药物安全监控": "analyze_fda_safety_signals",
    "不良反应信号": "analyze_fda_safety_signals",
    "pharmacovigilance": "analyze_fda_safety_signals",
    "相互作用机制": "analyze_interaction_mechanisms",
    "蛋白互作": "analyze_interaction_mechanisms",
    "drug-target interaction": "analyze_interaction_mechanisms",
    "结合机制": "analyze_interaction_mechanisms",
    "理化性质计算": "calculate_physicochemical_properties",
    "药物性质": "calculate_physicochemical_properties",
    "logP": "calculate_physicochemical_properties",
    "分子量": "calculate_physicochemical_properties",
    "Lipinski": "calculate_physicochemical_properties",
    "FDA药物召回": "check_fda_drug_recalls",
    "药品召回查询": "check_fda_drug_recalls",
    "FDA enforcement": "check_fda_drug_recalls",
    "recall查询": "check_fda_drug_recalls",
    "药物反应分析": "drug-response",
    "Connectivity Map": "drug-response",
    "药物敏感性": "drug-response",
    "drug sensitivity": "drug-response",
    "α粒子放疗剂量": "estimate_alpha_particle_radiotherapy_dosimetry",
    "alpha radiotherapy": "estimate_alpha_particle_radiotherapy_dosimetry",
    "辐射剂量": "estimate_alpha_particle_radiotherapy_dosimetry",
    "药物替代查询": "find_alternative_drugs_ddinter",
    "DDInter": "find_alternative_drugs_ddinter",
    "药物相互作用替代": "find_alternative_drugs_ddinter",
    "替代药物": "find_alternative_drugs_ddinter",
    "论文写作": "academic-paper-writing",
    "学术论文": "academic-paper-writing",
    "paper writing": "academic-paper-writing",
    "manuscript": "academic-paper-writing",
    "学术研究": "academic-research",
    "实验方案设计": "academic-research",
    "研究规划": "academic-research",
    "research proposal": "academic-research",
    "ClinicalTrials": "clinicaltrials-landscape",
    "试验注册": "clinicaltrials-landscape",
    "trial analysis": "clinicaltrials-landscape",
    "深度研究": "deep-research",
    "系统文献检索": "deep-research",
    "PRISMA": "deep-research",
    "meta分析文献": "deep-research",
    "evidence synthesis": "deep-research",
    "PDF提取": "extract_pdf_content",
    "提取文献内容": "extract_pdf_content",
    "PDF文本提取": "extract_pdf_content",
    "extract PDF text": "extract_pdf_content",
    "补充材料下载": "fetch_supplementary_info_from_doi",
    "Supplementary获取": "fetch_supplementary_info_from_doi",
    "DOI补充": "fetch_supplementary_info_from_doi",
    "supplement DOI": "fetch_supplementary_info_from_doi",
    "PDF翻译": "pdf-translate",
    "论文翻译": "pdf-translate",
    "保持排版翻译": "pdf-translate",
    "PDFMathTranslate": "pdf-translate",
    "pdf2zh": "pdf-translate",
    "PDF阅读": "pdf_reader",
    "读取论文": "pdf_reader",
    "PDF元数据": "pdf_reader",
    "提取论文图表": "pdf_reader",
    "PDF to Markdown": "pdf_reader",
    "arXiv查询": "query_arxiv",
    "arXiv检索": "query_arxiv",
    "预印本搜索": "query_arxiv",
    "arxiv论文": "query_arxiv",
    "PubMed查询": "query_pubmed",
    "PubMed检索": "query_pubmed",
    "pubmed搜索": "query_pubmed",
    "pubmed文献": "query_pubmed",
    "系统综述": "systematic-review",
    "systematic review": "systematic-review",
    "meta分析": "systematic-review",
    "证据整合": "systematic-review",
    "批量图像配准": "batch_register_images",
    "多图对齐": "batch_register_images",
    "图像配准": "batch_register_images",
    "Elastix批量": "batch_register_images",
    "图像相似度": "calculate_similarity_metrics",
    "相似度计算": "calculate_similarity_metrics",
    "Dice coefficient": "calculate_similarity_metrics",
    "medical image similarity": "calculate_similarity_metrics",
    "Word文档生成": "docx-generation",
    "docx报告": "docx-generation",
    "自动生成Word": "docx-generation",
    "报告导出docx": "docx-generation",
    "PDF报告生成": "pdf-report-generation",
    "自动报告": "pdf-report-generation",
    "PDF分析报告": "pdf-report-generation",
    "研究结果PDF": "pdf-report-generation",
    "HTML幻灯片": "ppt-html",
    "演示文稿": "ppt-html",
    "HTML预览": "ppt-html",
    "网页版PPT": "ppt-html",
    "reveal.js": "ppt-html",
    "PPT母版": "ppt-master",
    "企业PPT模板": "ppt-master",
    "演示模板": "ppt-master",
    "主题模板": "ppt-master",
    "公司模板": "ppt-master",
    "pptx报告": "pptx-generation",
    "自动生成PPT": "pptx-generation",
    "演示文稿生成": "pptx-generation",
    "仿射配准": "quick_affine_registration",
    "affine registration": "quick_affine_registration",
    "图像仿射变换": "quick_affine_registration",
    "可变形配准": "quick_deformable_registration",
    "B-spline配准": "quick_deformable_registration",
    "deformable registration": "quick_deformable_registration",
    "刚性配准": "quick_rigid_registration",
    "rigid registration": "quick_rigid_registration",
    "图像刚体对齐": "quick_rigid_registration",
    "网页报告": "html-report",
    "交互报告": "html-report",
    "可分享报告": "html-report",
    "Markdown报告": "markdown-report",
    "MD报告": "markdown-report",
    "技术报告": "markdown-report",
    "文档生成": "markdown-report",
    "Adaptyv API": "adaptyv-api",
    "蛋白质设计API": "adaptyv-api",
    "蛋白工程": "adaptyv-api",
    "序列比对": "align_sequences",
    "引物比对": "align_sequences",
    "short sequence alignment": "align_sequences",
    "primer alignment": "align_sequences",
    "蛋白保守性分析": "analyze_protein_conservation",
    "多序列比对": "analyze_protein_conservation",
    "conservation analysis": "analyze_protein_conservation",
    "BLAST搜索": "blast_sequence",
    "NCBI BLAST": "blast_sequence",
    "序列比对": "blast_sequence",
    "同源搜索": "blast_sequence",
    "代码编写": "code-writer",
    "Python脚本": "code-writer",
    "R脚本": "code-writer",
    "分析脚本": "code-writer",
    "生信编程": "code-writer",
    "数据可视化": "data-viz",
    "科研绘图": "data-viz",
    "UMAP图": "data-viz",
    "热图绘制": "data-viz",
    "小提琴图": "data-viz",
    "Golden Gate引物设计": "design_golden_gate_oligos",
    "Type IIS酶切": "design_golden_gate_oligos",
    "oligo设计": "design_golden_gate_oligos",
    "基因敲除sgRNA": "design_knockout_sgrna",
    "CRISPR sgRNA设计": "design_knockout_sgrna",
    "knockout guide": "design_knockout_sgrna",
    "sgRNA design": "design_knockout_sgrna",
    "oligo设计": "design_oligos",
    "PCR primer": "design_oligos",
    "引物优化": "design_oligos",
    "质粒设计": "design_plasmid",
    "载体构建": "design_plasmid",
    "plasmid design": "design_plasmid",
    "克隆载体": "design_plasmid",
    "SNP检测": "detect_snps",
    "变异检测": "detect_snps",
    "基因突变": "detect_snps",
    "variant calling": "detect_snps",
    "GEO下载": "download_geo",
    "GEO数据": "download_geo",
    "download GEO": "download_geo",
    "GEO accession": "download_geo",
    "SRA下载": "download_sra",
    "SRA数据": "download_sra",
    "fastq-dump": "download_sra",
    "SRA accession": "download_sra",
    "Ensembl查询": "ensembl-api",
    "Ensembl API": "ensembl-api",
    "基因组注释": "ensembl-api",
    "Ensembl gene": "ensembl-api",
    "Entrez查询": "entrez-api",
    "NCBI Entrez": "entrez-api",
    "NCBI API": "entrez-api",
    "efetch": "entrez-api",
    "基因本体": "gene-ontology",
    "GO enrichment": "gene-ontology",
    "gene ontology": "gene-ontology",
    "KEGG查询": "kegg-api",
    "KEGG通路": "kegg-api",
    "KEGG API": "kegg-api",
    "KEGG pathway": "kegg-api",
    "机器学习": "machine-learning",
    "ML分析": "machine-learning",
    "scikit-learn": "machine-learning",
    "random forest": "machine-learning",
    "XGBoost": "machine-learning",
    "虚拟筛选": "molecular-docking",
    "分子模拟": "molecular-docking",
    "PDB查询": "protein-structure",
    "蛋白3D结构": "protein-structure",
    "structure analysis": "protein-structure",
}


class HybridMatcher:
    """Combines keyword aliases + TF-IDF semantic matching for skill discovery."""
    
    def __init__(self, skills_dir: str, index_path: str = None):
        self.skills_dir = skills_dir
        self.index_path = index_path or os.path.join(skills_dir, '..', 'tools', 'skill_hybrid_index.pkl')
        self._tfidf = None
        self._skills = []
        self._loaded = False
    
    def load(self):
        """Lazy-load the hybrid index."""
        if self._loaded:
            return
        try:
            with open(self.index_path, 'rb') as f:
                idx = pickle.load(f)
            self._tfidf = idx.get('vectorizer')
            self._matrix = idx.get('tfidf_matrix')
            self._skills = idx.get('corpus_skills', [])
            self._skill_info = idx.get('skill_info', {})
            self._loaded = True
        except Exception:
            self._loaded = True  # Mark as loaded to avoid retry
    
    def _load_when_to_use(self):
        import glob as _glob, re as _re
        self._wtu_cache = {}
        for sf in _glob.glob(os.path.join(self.skills_dir, '*', 'SKILL.md')):
            skill_id = os.path.basename(os.path.dirname(sf))
            try:
                with open(sf, 'r', encoding='utf-8') as f:
                    content = f.read(4096)
                m = _re.search(r'^when_to_use:\s*"?(.+?)"?$', content, _re.MULTILINE)
                if m:
                    self._wtu_cache[skill_id] = m.group(1).strip('"').strip()
            except Exception:
                pass
    
    def search(self, query: str, domain_filter: str = None, top_k: int = 5) -> dict:
        """Hybrid search: keyword aliases + TF-IDF fusion."""
        query_lower = query.lower()
        results = {}  # skill_name -> {'score': float, 'source': str}
        
        # === Layer 1: Keyword aliases (high precision) ===
        for alias_key, canonical_name in CHINESE_ALIASES.items():
            if alias_key in query_lower:
                score = 0.7 if len(alias_key) >= 6 else 0.5
                if canonical_name not in results or results[canonical_name]['score'] < score:
                    results[canonical_name] = {'score': score, 'source': 'keyword_alias', 'kw': alias_key}
        
        # === Layer 2: TF-IDF semantic matching (always runs) ===
        self.load()
        if self._tfidf and self._matrix is not None:
            try:
                qvec = self._tfidf.transform([query])
                from sklearn.metrics.pairwise import cosine_similarity
                sims = cosine_similarity(qvec, self._matrix)[0]
                top_indices = np.argsort(sims)[::-1][:min(top_k * 3, 50)]
                
                for idx in top_indices:
                    sim_score = float(sims[idx])
                    if sim_score < 0.1:
                        continue
                    skill_name = self._skills[idx]
                    # Fusion: keyword + TF-IDF
                    if skill_name in results:
                        results[skill_name]['score'] = max(
                            results[skill_name]['score'],
                            round(results[skill_name]['score'] * 0.5 + sim_score * 0.5, 3)
                        )
                        results[skill_name]['source'] += '+tfidf'
                    elif sim_score >= 0.12:
                        results[skill_name] = {'score': round(sim_score * 0.5, 3), 'source': 'tfidf'}
            except Exception:
                pass
        

        # === Layer 3: Directory name direct match (fallback) ===
        if not results:
            import glob as _glob
            skill_dirs = {}
            for _sf in _glob.glob(os.path.join(self.skills_dir, '*', 'SKILL.md')):
                _dn = os.path.basename(os.path.dirname(_sf))
                _sn = _dn.lower()
                _qw = [w.lower() for w in query.split() if len(w) >= 3]
                _hits = sum(1 for w in _qw if w in _sn)
                if _hits > 0:
                    score = 0.3 * _hits / max(len(_qw), 1)
                    results[_dn] = {'score': score, 'source': 'dir_match'}
        # === Sort by score ===
        sorted_results = sorted(results.items(), key=lambda x: -x[1]['score'])
        
        # === Collision expansion: include sibling skills for LLM disambiguation ===
        skill_prefixes = {}
        for name, data in sorted_results:
            prefix = name.split('-')[0]
            if prefix not in skill_prefixes:
                skill_prefixes[prefix] = []
            skill_prefixes[prefix].append(name)
        
        # For any prefix group with 2+ skills, expand: add missing siblings
        import glob as _glob
        expanded = {}
        for name, data in sorted_results:
            expanded[name] = data
            prefix = name.split('-')[0]
            if len(skill_prefixes.get(prefix, [])) >= 2:
                continue  # Already present
            # Find sibling skills with same prefix
            for sf in _glob.glob(os.path.join(self.skills_dir, '*', 'SKILL.md')):
                sibling = os.path.basename(os.path.dirname(sf))
                if sibling == name:
                    continue
                if sibling.split('-')[0] == prefix and sibling not in expanded:
                    # Add sibling with slightly lower score
                    expanded[sibling] = {'score': data['score'] * 0.7, 'source': 'sibling_expand'}
        
        if expanded != dict(sorted_results):
            sorted_results = sorted(expanded.items(), key=lambda x: -x[1]['score'])
        
        # === Domain filter ===
        if domain_filter:
            sorted_results = [r for r in sorted_results if getattr(self, '_skill_info', {}).get(r[0], {}).get('domain') == domain_filter or r[0] in domain_filter]
        
        # === Format output ===
        out = []
        skill_info = getattr(self, '_skill_info', {})
        
        # Lazy-load when_to_use from SKILL.md files
        if not getattr(self, '_wtu_cache', None):
            self._load_when_to_use()
        
        for name, data in sorted_results[:top_k]:
            info = skill_info.get(name, {})
            wtu = getattr(self, '_wtu_cache', {}).get(name, '')
            # For collision groups with close scores, append when_to_use to help LLM choose
            if not wtu:
                wtu = info.get('description', '')
            out.append({
                'name': name,
                'description': info.get('description', ''),
                'when_to_use': wtu,
                'score': data['score'],
                'match_type': data['source'],
            })
        
        return {
            'success': True,
            'query': query,
            'domain': domain_filter,
            'count': len(out),
            'results': out,
        }


# ===== Factory: get a cached matcher instance =====
_matcher = None

def get_matcher() -> HybridMatcher:
    global _matcher
    if _matcher is None:
        skills_dir = os.environ.get('SKILLS_DIR', '')
        if not skills_dir:
            # Auto-detect
            for root in [os.getcwd(), os.path.dirname(os.path.dirname(os.path.abspath(__file__)))]:
                sd = os.path.join(root, 'hermes_home', 'skills', 'bioinformatics')
                if os.path.isdir(sd):
                    skills_dir = sd
                    break
        _matcher = HybridMatcher(
            skills_dir,
            index_path=os.path.join(
                os.path.dirname(os.path.dirname(os.path.dirname(skills_dir))),
                'hermes-agent', 'tools', 'skill_hybrid_index.pkl'
            )
        )
    return _matcher
