# -*- coding: utf-8 -*-
"""memomics_pipeline — 分析管线编排工具（2026-08-15 恢复）。

14 模块多组学管线：方案解析(parse) → 待办生成(todos, 带 skill 绑定)
→ 摘要(summary) → 模态检测(modalities)。
原实现曾位于 hermes-agent/agent/，被备份清理后成为"幻影工具"；
本次按原逻辑恢复并正式注册进 memomics toolset。
"""
import json
import logging

logger = logging.getLogger("memomics.memomics_pipeline")

MODULES = {
    "01": {"id": "01", "name": "深度去污染", "description": "CellBender/SoupX/DoubletFinder", "modality": "scrna", "skills": ["scrna-qc", "cellbender-remove-background"], "note": "探索性分析不建议", "substeps": [{"id": "cellbender", "name": "CellBender去背景", "skill": "cellbender-remove-background"}, {"id": "doublet", "name": "双胞过滤", "skill": "scrna-qc"}]},
    "02": {"id": "02", "name": "基础分析", "modality": "scrna", "description": "QC->SCTransform->Harmony->UMAP->Leiden->Annotation->Markers", "skills": ["scrna-clustering", "annotate_celltype_scRNA"], "substeps": [
        {"id": "qc", "name": "QC", "skill": "scrna-qc"},
        {"id": "sct", "name": "SCTransform", "skill": "scrna-clustering"},
        {"id": "harmony", "name": "Harmony", "skill": "create_harmony_embeddings_scRNA"},
        {"id": "umap", "name": "UMAP", "skill": "scrna-clustering"},
        {"id": "cluster", "name": "Leiden", "skill": "scrna-clustering"},
        {"id": "annotate", "name": "Annotation", "skill": "annotate_celltype_scRNA"},
        {"id": "markers", "name": "Markers", "skill": "deg-analysis"},
    ]},
    "03": {"id": "03", "name": "高级分析(单细胞)", "modality": "scrna", "description": "DEG+Enrichment / CellChat / Trajectory / SCENIC", "substeps": [
        {"id": "deg", "name": "DEG+富集", "skill": "deg-analysis"},
        {"id": "cellchat", "name": "CellChat通讯", "skill": "cellchat-v2"},
        {"id": "trajectory", "name": "轨迹分析", "skill": "trajectory-analysis"},
        {"id": "scenic", "name": "SCENIC调控", "skill": "grn-pyscenic"},
    ]},
    "04": {"id": "04", "name": "个性化分析", "modality": "scrna", "description": "按研究方向定制", "skills": ["sasp-scoring", "immune-deconvolution"], "substeps": [{"id": "sasp", "name": "衰老分泌表型评分", "skill": "sasp-scoring"}, {"id": "immune", "name": "免疫浸润", "skill": "immune-deconvolution"}]},
    "05": {"id": "05", "name": "scATAC分析", "modality": "scatac", "description": "ArchR/Signac: QC->Peak->Motif->Footprinting->差异可及性", "skills": ["atac-seq-memomics", "find_enriched_motifs_with_homer"], "substeps": [
        {"id": "atac_qc", "name": "ATAC QC", "skill": "atac-seq-memomics"},
        {"id": "peak_call", "name": "Peak Calling", "skill": "atac-seq-memomics"},
        {"id": "motif", "name": "Motif富集(HOMER)", "skill": "find_enriched_motifs_with_homer"},
        {"id": "diff_access", "name": "差异可及性", "skill": "atac-seq-memomics"},
        {"id": "gene_activity", "name": "Gene Activity Score", "skill": "atac-seq-memomics"},
    ]},
    "06": {"id": "06", "name": "多组学整合", "modality": "multi_omics", "description": "MOFA+/RGCCA: RNA+ATAC+蛋白跨组学整合", "skills": ["multi-omics-integration", "rgcca-multiblock", "split_modalities"], "substeps": [
        {"id": "peak2gene", "name": "Peak-to-Gene关联", "skill": "atac-seq-memomics"},
        {"id": "mofa", "name": "MOFA+整合", "skill": "multi-omics-integration"},
        {"id": "rgcca", "name": "RGCCA整合", "skill": "rgcca-multiblock"},
    ]},
    "07": {"id": "07", "name": "Bulk RNA-seq", "modality": "bulk_rna", "description": "DESeq2->GSEA/GO/KEGG->WGCNA->Deconvolution->Biomarker", "skills": ["bulk-rnaseq-deseq2", "gene_set_enrichment_analysis", "hdwgcna", "immune-deconvolution", "lasso-biomarker-panel"], "substeps": [
        {"id": "bulk_de", "name": "差异表达(DESeq2)", "skill": "bulk-rnaseq-deseq2"},
        {"id": "bulk_gsea", "name": "GSEA/GO/KEGG", "skill": "gene_set_enrichment_analysis"},
        {"id": "bulk_wgcna", "name": "WGCNA", "skill": "hdwgcna"},
        {"id": "bulk_deconv", "name": "免疫浸润", "skill": "immune-deconvolution"},
        {"id": "bulk_biomarker", "name": "Biomarker Panel", "skill": "lasso-biomarker-panel"},
    ]},
    "08": {"id": "08", "name": "蛋白质组学", "modality": "proteomics", "description": "差异表达->PPI->Docking->AlphaFold->PRIDE", "skills": ["proteomics-diff-exp", "query_stringdb", "docking_autodock_vina", "query_uniprot", "query_alphafold"], "substeps": [
        {"id": "prot_de", "name": "差异蛋白", "skill": "proteomics-diff-exp"},
        {"id": "prot_ppi", "name": "PPI网络", "skill": "query_stringdb"},
        {"id": "prot_dock", "name": "分子对接", "skill": "docking_autodock_vina"},
    ]},
    "09": {"id": "09", "name": "药物分析", "modality": "drug", "description": "药物响应->ADMET->对接->重定位->临床试验", "skills": ["drug-response", "predict_admet_properties", "docking_autodock_vina", "retrieve_topk_repurposing_drugs_from_disease_txgnn", "query_chembl", "clinicaltrials-landscape"], "substeps": [
        {"id": "drug_response", "name": "药物响应", "skill": "drug-response"},
        {"id": "drug_admet", "name": "ADMET预测", "skill": "predict_admet_properties"},
        {"id": "drug_dock", "name": "靶点对接", "skill": "docking_autodock_vina"},
        {"id": "drug_repurpose", "name": "药物重定位", "skill": "retrieve_topk_repurposing_drugs_from_disease_txgnn"},
        {"id": "drug_clinical", "name": "临床试验检索", "skill": "clinicaltrials-landscape"},
    ]},
    "10": {"id": "10", "name": "微生物组", "modality": "microbiome", "description": "Alpha/Beta多样性+差异丰度+系统发育(专用skill较少,AI可用通用代码)", "skills": ["phylogenetics-toolkit", "analyze_bacterial_growth_curve"], "note": "专用skill较少，AI可用通用代码", "substeps": [
        {"id": "micro_diversity", "name": "Alpha/Beta多样性", "skill": "phylogenetics-toolkit"},
        {"id": "micro_diff", "name": "差异丰度(LEfSe/ALDEx2)", "skill": "phylogenetics-toolkit"},
        {"id": "micro_phylo", "name": "系统发育树", "skill": "phylogenetics-toolkit"},
    ]},
    "11": {"id": "11", "name": "空间转录组", "modality": "spatial", "description": "Seurat/Squidpy: 空间特征->区域分割->空间通讯", "skills": ["spatial-transcriptomics", "cell-cell-communication"], "substeps": [
        {"id": "spatial_prep", "name": "预处理", "skill": "spatial-transcriptomics"},
        {"id": "spatial_de", "name": "空间差异表达", "skill": "spatial-transcriptomics"},
        {"id": "spatial_comm", "name": "空间通讯", "skill": "cell-cell-communication"},
    ]},
    "12": {"id": "12", "name": "脂质组学", "modality": "lipidomics", "description": "脂质鉴定+定量+差异分析", "skills": ["lipidomics-summary-stats"], "substeps": [
        {"id": "lipid_summary", "name": "脂质组总结", "skill": "lipidomics-summary-stats"},
    ]},
    "13": {"id": "13", "name": "GWAS/遗传学", "modality": "genetics", "description": "PRS/MR/变异注释/精细定位", "skills": ["polygenic-risk-score-prs-catalog", "mendelian-randomization-twosamplemr", "genetic-variant-annotation", "bayesian_finemapping_with_deep_vi"], "substeps": [
        {"id": "gwas_prs", "name": "PRS风险评分", "skill": "polygenic-risk-score-prs-catalog"},
        {"id": "gwas_mr", "name": "孟德尔随机化", "skill": "mendelian-randomization-twosamplemr"},
        {"id": "gwas_annot", "name": "变异注释", "skill": "genetic-variant-annotation"},
    ]},
    "14": {"id": "14", "name": "生存分析/临床", "modality": "clinical", "description": "Kaplan-Meier/Cox/临床预测模型", "skills": ["survival-analysis", "survival-analysis-clinical", "disease-progression-longitudinal"], "substeps": [
        {"id": "surv_km", "name": "Kaplan-Meier", "skill": "survival-analysis"},
        {"id": "surv_cox", "name": "Cox回归", "skill": "survival-analysis"},
        {"id": "surv_clinical", "name": "临床预测模型", "skill": "survival-analysis-clinical"},
    ]},
}

COMBOS = {
    "quick": {"name": "快速组合(scRNA)", "modalities": ["scrna"], "modules": ["02"], "description": "仅基础分析"},
    "standard": {"name": "标准组合(scRNA,推荐)", "modalities": ["scrna"], "modules": ["02", "03"], "description": "基础+高级"},
    "sc_atac_rna": {"name": "ATAC+RNA整合", "modalities": ["scrna", "scatac", "multi_omics"], "modules": ["02", "03", "05", "06"], "description": "scRNA+scATAC全流程+整合"},
    "bulk_multi": {"name": "Bulk RNA+多组学", "modalities": ["bulk_rna", "multi_omics"], "modules": ["07", "06"], "description": "Bulk RNA-seq + 多组学整合"},
    "drug_discovery": {"name": "药物发现", "modalities": ["drug", "proteomics"], "modules": ["08", "09"], "description": "蛋白质组+药物分析"},
    "biomarker": {"name": "Biomarker发现", "modalities": ["scrna", "bulk_rna", "clinical"], "modules": ["03", "07", "14"], "description": "单细胞+bulk+临床验证"},
}

MODALITY_ROUTE = {
    "scrna": ["02", "03"],
    "scatac": ["05"],
    "bulk_rna": ["07"],
    "proteomics": ["08"],
    "drug": ["09"],
    "microbiome": ["10"],
    "spatial": ["11"],
    "lipidomics": ["12"],
    "genetics": ["13"],
    "clinical": ["14"],
    "multi_omics": ["06"],
}

MODALITY_KW = {
    "scrna": ["scrna", "single cell", "单细胞", "10x", "seurat", "scanpy"],
    "scatac": ["scatac", "single cell atac", "开放染色质", "chromatin accessibility", "archr", "signac"],
    "spatial": ["空间转录", "spatial", "空间组", "visium", "merfish", "xenium"],
    "bulk_rna": ["bulk rna", "bulk-rna", "转录组测序", "rna-seq", "rnaseq", "deseq2", "edger", "limma"],
    "proteomics": ["蛋白", "proteom", "质谱", "mass spectr", "蛋白质", "docking"],
    "drug": ["药物", "drug", "靶点", "靶向", "admet", "临床试验", "clinical trial"],
    "microbiome": ["微生物", "microbiom", "菌群", "16s", "宏基因", "metagenom"],
    "lipidomics": ["脂质", "lipid", "lipidom"],
    "genetics": ["gwas", "遗传", "变异", "variant", "mendelian", "prs", "多基因风险"],
    "clinical": ["生存分析", "survival", "cox", "kaplan", "临床", "预后", "prognosis"],
    "multi_omics": ["多组学", "multiom", "multi-om", "整合组学", "多模态", "联合分析", "整合分析"],
}

_MULTI_MODALITY_PAIRS = [
    ({"scrna", "scatac"}, "scRNA+ATAC"),
    ({"scrna", "spatial"}, "scRNA+spatial"),
    ({"scrna", "bulk_rna"}, "scRNA+bulk"),
    ({"scrna", "proteomics"}, "scRNA+proteomics"),
    ({"bulk_rna", "proteomics"}, "bulk+proteomics"),
    ({"genetics", "clinical"}, "genetics+clinical"),
    ({"scrna", "drug"}, "scRNA+drug"),
    ({"microbiome", "drug"}, "microbiome+drug"),
]

DIRECTION_MAP = {
    "aging": ["衰老", "aging", "aged", "老年", "elderly", "senescence", "寿命", "longevity"],
    "cancer": ["肿瘤", "cancer", "tumor", "癌", "oncology", "malignant", "转移", "metastasis"],
    "neurodegeneration": ["神经", "neuro", "AD", "ALS", "FSHD", "Alzheimer", "Parkinson", "脑", "brain", "认知", "cognitive"],
    "fibrosis": ["纤维化", "fibrosis", "瘢痕", "scarring"],
    "immunology": ["免疫", "immune", "inflammation", "炎症", "自免疫", "autoimmune", "微环境", "microenvironment", "tme"],
    "development": ["发育", "development", "embryo", "胚胎", "再生", "regeneration", "干细胞", "stem cell"],
    "metabolism": ["代谢", "metabolic", "diabetes", "糖尿病", "obesity", "肥胖", "脂质", "lipid"],
    "cardiovascular": ["心脏", "cardiac", "heart", "心血管", "cardiovascular", "血管", "vascular", "动脉", "atherosclerosis"],
    "hepatology": ["肝脏", "liver", "hepatic", "肝细胞", "hepatocyte", "肝硬化", "cirrhosis"],
    "muscle_biology": ["骨骼肌", "muscle", "skeletal", "肌肉", "myogenesis", "肌萎缩", "atrophy"],
    "microbiome": ["微生物", "microbiome", "菌群", "microbiota", "16s", "metagenom", "宏基因组"],
    "infectious": ["感染", "infection", "病毒", "virus", "细菌", "bacteria", "宿主", "host", "covid", "SARS"],
    "drug_response": ["药物", "drug", "耐药", "resistance", "敏感性", "sensitivity", "药靶", "target"],
    "epigenetics": ["表观", "epigenetic", "甲基化", "methylation", "组蛋白", "histone", "chromatin"],
}

SPECIES_MAP = {
    "human": ["human", "homo sapiens", "人", "patient"],
    "mouse": ["mouse", "mus musculus", "小鼠", "老鼠"],
    "zebrafish": ["zebrafish"],
    "rat": ["rat", "rattus"],
}


def extract_direction(user_input: str) -> dict:
    text = user_input.lower()
    species = "auto"
    for sp, keywords in SPECIES_MAP.items():
        for kw in keywords:
            if kw in text:
                species = sp
                break
        if species != "auto":
            break
    directions = []
    for direction, keywords in DIRECTION_MAP.items():
        for kw in keywords:
            if kw in text:
                directions.append(direction)
                break
    return {"species": species, "directions": directions, "has_direction": len(directions) > 0}


def detect_modality(text: str) -> list:
    t = text.lower()
    modalities = []
    has_scrna = False
    for mod, keywords in MODALITY_KW.items():
        for kw in keywords:
            if kw in t:
                if mod == "scrna":
                    has_scrna = True
                modalities.append(mod)
                break
    if has_scrna and "bulk_rna" in modalities and "bulk" not in t:
        modalities.remove("bulk_rna")
    mod_set = set(modalities)
    for pair, _desc in _MULTI_MODALITY_PAIRS:
        if pair.issubset(mod_set) and "multi_omics" not in modalities:
            modalities.append("multi_omics")
            break
    return modalities if modalities else ["scrna"]


def resolve_modules(modalities=None, user_input: str = "") -> list:
    if not modalities:
        modalities = detect_modality(user_input)
    modules = []
    for m in modalities:
        for r in MODALITY_ROUTE.get(m, []):
            if r not in modules:
                modules.append(r)
    return modules if modules else ["02"]


def build_module_options() -> list:
    options = []
    for mid, mod in MODULES.items():
        note = mod.get("note", "")
        desc = mod["description"] + (" (" + note + ")" if note else "")
        options.append({"id": f"module:{mid}", "label": f"{mid} {mod['name']}", "description": desc})
    for cid, combo in COMBOS.items():
        options.append({"id": f"combo:{cid}", "label": combo["name"], "description": combo["description"]})
    return options


def parse_module_selection(raw_input: str) -> list:
    text = raw_input.strip().lower()
    for cid, combo in COMBOS.items():
        if cid in text or combo["name"].lower() in text:
            return combo["modules"]
    modules = []
    kw_map = {
        "01": ["去污染", "cellbender", "soupx", "doublet", "去背景"],
        "02": ["基础", "qc", "聚类", "cluster", "umap", "sctransform", "harmony"],
        "03": ["高级", "deg", "cellchat", "trajectory", "scenic", "monocle"],
        "04": ["个性化", "定制", "custom"],
        "05": ["atac", "开放性", "染色质", "peak", "motif", "footprint"],
        "06": ["整合", "多组学", "multiom", "multi-om", "多模态"],
        "07": ["bulk", "bulk rna", "bulk-rna", "rna-seq", "rnaseq", "deseq2", "edger", "limma"],
        "08": ["蛋白", "proteom", "质谱", "蛋白质组", "docking", "ppi"],
        "09": ["药物", "drug", "靶点", "靶向", "admet", "重定位", "repurpos"],
        "10": ["微生物", "microbiom", "菌群", "16s", "宏基因"],
        "11": ["空间", "spatial", "visium"],
        "12": ["脂质", "lipidom"],
        "13": ["gwas", "遗传", "prs", "mendelian", "多基因"],
        "14": ["生存", "survival", "临床", "预后", "cox", "kaplan"],
    }
    for mid, keywords in kw_map.items():
        for kw in keywords:
            if kw in text and mid not in modules:
                modules.append(mid)
    return sorted(modules) if modules else ["02"]


def modules_to_todos(selected_modules, direction_info=None) -> list:
    """模块列表 → 待办（带 skill 绑定）。与 server.py plan_refine 兜底调用兼容。"""
    todos = []
    for mid in selected_modules:
        mod = MODULES.get(mid)
        if not mod:
            continue
        modality = mod.get("modality", "unknown")
        if "substeps" in mod and mid != "04":
            for step in mod["substeps"]:
                todos.append({
                    "id": f"{modality}_{step['id']}",
                    "title": f"[{mod['name']}] {step['name']}",
                    "module": mid,
                    "modality": modality,
                    "skill": step.get("skill", ""),
                    "status": "pending",
                })
        else:
            d = (direction_info or {}).get("directions", [])
            extra = ("(" + "/".join(d) + ")" if d else "")
            todos.append({
                "id": f"{modality}_{mid}",
                "title": f"[{mod['name']}] {mod['description']}{extra}",
                "module": mid,
                "modality": modality,
                "skill": (mod.get("skills") or [""])[0],
                "status": "pending",
            })
    return todos


def get_module_summary(selected_modules) -> str:
    lines = []
    for mid in sorted(selected_modules):
        mod = MODULES.get(mid, {})
        lines.append(f"**{mid} {mod.get('name', mid)}**: {mod.get('description', '')}")
    if "03" in selected_modules:
        lines.append("\n高级分析包含: DEG+Enrichment, CellChat, Trajectory, SCENIC")
    return "\n".join(lines)


def memomics_pipeline(action: str = "parse", user_input: str = "",
                      selected_modules=None, direction_info=None) -> str:
    """方案解析与待办编排。action: parse / todos / summary / modalities。"""
    try:
        selected_modules = selected_modules or []
        if action == "parse":
            direction = extract_direction(user_input) if user_input else {}
            modalities_detected = detect_modality(user_input) if user_input else ["scrna"]
            default_modules = resolve_modules(modalities_detected, user_input or "")
            options = build_module_options()
            return json.dumps({
                "success": True,
                "direction": direction,
                "modalities": modalities_detected,
                "default_modules": default_modules,
                "module_options": options,
            }, ensure_ascii=False, indent=2)
        if action == "todos":
            if not selected_modules:
                return json.dumps({"success": False, "error": "selected_modules required"}, ensure_ascii=False)
            todos = modules_to_todos(selected_modules, direction_info or {})
            summary = get_module_summary(selected_modules)
            return json.dumps({
                "success": True,
                "todos": todos,
                "summary": summary,
                "total_todos": len(todos),
            }, ensure_ascii=False, indent=2)
        if action == "summary":
            if not selected_modules:
                return json.dumps({"success": False, "error": "selected_modules required"}, ensure_ascii=False)
            return json.dumps({"success": True, "summary": get_module_summary(selected_modules)}, ensure_ascii=False)
        if action == "modalities":
            modalities_list = detect_modality(user_input) if user_input else ["scrna"]
            return json.dumps({
                "success": True,
                "modalities": modalities_list,
                "modules": resolve_modules(modalities_list, user_input or ""),
            }, ensure_ascii=False, indent=2)
        return json.dumps({"success": False, "error": f"Unknown action: {action}"}, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False)


SCHEMA = {
    "name": "memomics_pipeline",
    "description": (
        "MemOmics 分析管线编排：从用户需求提取物种/方向/数据模态，展示 14 模块多组学方案，"
        "生成带 skill 绑定的待办清单。支持 scRNA/ATAC/Bulk RNA/蛋白/药物/微生物/空间/脂质/遗传/临床。"
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": ["parse", "todos", "summary", "modalities"],
                       "description": "parse=解析方向+模态+默认模块; todos=按模块生成带skill的待办; summary=模块摘要; modalities=检测数据类型"},
            "user_input": {"type": "string", "description": "用户原始需求文本"},
            "selected_modules": {"type": "array", "items": {"type": "string"},
                                 "description": "模块 ID，如 ['02','03']"},
            "direction_info": {"type": "object", "description": "预先提取的方向信息（可选）"},
        },
        "required": ["action"],
    },
}


def _register():
    try:
        from tools.registry import registry
        registry.register(
            name="memomics_pipeline",
            toolset="memomics",
            schema=SCHEMA,
            handler=lambda args, **kw: memomics_pipeline(
                args.get("action", "parse"),
                args.get("user_input", ""),
                args.get("selected_modules", []),
                args.get("direction_info"),
            ),
            emoji="🧬",
            max_result_size_chars=30_000,
        )
    except Exception as e:
        logger.warning(f"memomics_pipeline register failed: {e}")


_register()
