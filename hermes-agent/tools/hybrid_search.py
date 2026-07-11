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
    "chip": "perform_chipseq_peak_calling_with_macs2",
    "chipseq": "perform_chipseq_peak_calling_with_macs2",
    "gwas": "gwas-analysis",
    "孟德尔": "mendelian-randomization",
    "mendel": "mendelian-randomization",
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
    "gwas": "gwas-analysis",
    "eqtl": "genetic-variant-annotation",
    "基因组关联": "gwas-analysis",
    
    # ---- 其他 ----
    "cca": "create_harmony_embeddings_scRNA",
    "mag": "mageck_analysis",
    "sgrna-seq": "mageck_analysis",
    "guide": "sgrna-design",
    "网络药理学": "drug-target-prediction",
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
        
        # === Sort by score ===
        sorted_results = sorted(results.items(), key=lambda x: -x[1]['score'])
        
        # === Domain filter ===
        if domain_filter:
            sorted_results = [r for r in sorted_results if getattr(self, '_skill_info', {}).get(r[0], {}).get('domain') == domain_filter or r[0] in domain_filter]
        
        # === Format output ===
        out = []
        skill_info = getattr(self, '_skill_info', {})
        for name, data in sorted_results[:top_k]:
            info = skill_info.get(name, {})
            out.append({
                'name': name,
                'description': info.get('description', ''),
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
