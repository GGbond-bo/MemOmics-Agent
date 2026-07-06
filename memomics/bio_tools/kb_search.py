"""Knowledge base search tool — searches the MemOmics knowledge base.

v2: 增强搜索逻辑
- 按 species/tissue/direction 定位目录
- 同义词扩展覆盖英文关键词
- 返回完整参数而非片段
- 知识库不存在时返回建议
"""
import json
import os
import logging
import yaml
from pathlib import Path

logger = logging.getLogger(__name__)

SCHEMA = {
    "name": "search_knowledge",
    "description": (
        "Search the MemOmics knowledge base for bioinformatics analysis "
        "templates, QC parameters, method recommendations, and biological knowledge. "
        "ALWAYS call this BEFORE writing any analysis code to get the correct "
        "parameters and templates. "
        "Pass species, tissue, and direction for targeted search. "
        "支持中英文语义匹配（如 '人' → 'human', '智人', 'Homo sapiens')."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Search query (e.g. 'QC parameters', 'clustering resolution', 'CellChat', '骨骼肌衰老marker')"
            },
            "species": {"type": "string", "description": "Species (e.g. human, mouse, Homo sapiens, 人)"},
            "tissue": {"type": "string", "description": "Tissue (e.g. skeletal_muscle, brain, heart, 骨骼肌)"},
            "direction": {"type": "string", "description": "Research direction (e.g. aging, ad, development, 衰老)"}
        },
        "required": ["query"]
    }
}

# 语义同义词 — 覆盖中英文 + 学名
SYNONYMS = {
    # 物种 — 标准目录名为 Homo_sapiens / Mus_musculus / monkey / zebrafish
    "human": ["human", "智人", "homo sapiens", "人类", "人", "homo_sapiens", "human pbmc"],
    "mouse": ["mouse", "小鼠", "mus musculus", "老鼠", "鼠", "mus_musculus", "mice"],
    "monkey": ["monkey", "猴", "猕猴", "macaque", "cynomolgus", "食蟹猴", "玻尾猴", "猴子"],
    "zebrafish": ["zebrafish", "斑马鱼", "danio rerio", "danio"],
    "rat": ["rat", "大鼠", "珉鼠", "rattus norvegicus"],
    "fly": ["fly", "果蝇", "drosophila", "drosophila melanogaster"],
    "worm": ["worm", "线虫", "c. elegans", "caenorhabditis elegans"],
    "pig": ["pig", "猪", "sus scrofa", "porcine"],
    # 组织
    "skeletal_muscle": ["skeletal_muscle", "skeletal muscle", "muscle", "肌", "肌肉", "骨骼肌", "skeletal"],
    "brain": ["brain", "脑", "cerebral", "大脑", "cortex", "皮层", "cerebellum", "小脑", "hippocampus", "海马"],
    "heart": ["heart", "cardiac", "心肌", "心脏", "ventricle", "心室"],
    "liver": ["liver", "肝", "肝脏", "hepatic"],
    "lung": ["lung", "肺", "肺部", "pulmonary"],
    "kidney": ["kidney", "肾", "肾脏", "renal"],
    "pbmc": ["pbmc", "外周血单个核细胞", "peripheral blood", "外周血", "blood", "血液"],
    "bone_marrow": ["bone_marrow", "骨髓", "bone marrow", "hematopoietic"],
    "spleen": ["spleen", "脾", "脾脏", "splenic"],
    "intestine": ["intestine", "肠", "肠道", "gut", "colon", "结肠", "small intestine"],
    "skin": ["skin", "皮肤", "dermal", "epidermal"],
    "fat": ["fat", "脂肪", "adipose", "adipose tissue"],
    # 方向
    "aging": ["aging", "aged", "elderly", "老年", "衰老", "老", "senescence", "老化"],
    "ad": ["alzheimer", "ad", "阿尔茨海默", "alzheimer's disease"],
    "development": ["development", "发育", "发展", "embryonic", "胚胎"],
    "cardiomyopathy": ["cardiomyopathy", "心肌病"],
    "fibrosis": ["fibrosis", "纤维化"],
    "denervation": ["denervation", "去神经", "神经切除"],
    "regeneration": ["regeneration", "再生", "sarcomere regeneration"],
    "disease": ["disease", "疾病", "病理", "pathology"],
    # 分析步骤
    "qc": ["quality control", "质控", "质量过滤", "qc", "filtering"],
    "normalize": ["normalize", "normalization", "sctransform", "归一化", "标准化"],
    "pca": ["pca", "principal component", "降维", "dimensionality reduction"],
    "umap": ["umap", "tsne", "可视化", "visualization"],
    "cluster": ["cluster", "clustering", "聚类", "分群", "resolution", "louvain", "leiden"],
    "annotate": ["annotation", "annotate", "cell type", "注释", "细胞类型", "celltype"],
    "deg": ["differential expression", "差异表达", "差异基因", "deg", "marker", "findmarkers"],
    "enrichment": ["enrichment", "gsea", "go", "kegg", "pathway", "富集"],
    "trajectory": ["trajectory", "pseudotime", "monocle", "cellrank", "轨迹", "拟时序"],
    "cellchat": ["cellchat", "communication", "interaction", "ligand receptor", "通讯", "细胞通讯"],
    "scenic": ["scenic", "regulon", "grn", "gene regulatory", "调控"],
    "doublet": ["doublet", "doubletfinder", "scrublet", "双包", "双胞", "双标"],
    "ambient": ["ambient", "soupx", "cellbender", "ambient rna", "环境RNA"],
    "harmony": ["harmony", "integration", "batch correction", "批次校正", "整合"],
    "decontamination": ["decontamination", "cellbender", "soupx", "去污染"],
    # 测序方法
    "scrna": ["scrna", "scrna-seq", "single cell rna", "单细胞", "single-cell"],
    "atac": ["atac", "scatac", "chromatin", "scatac-seq"],
    "spatial": ["spatial", "空间组", "spatial transcriptomics", "visium", "stereo", "slide-seq"],
    "proteomics": ["proteomics", "蛋白质组", "mass spec"],
    "metabolomics": ["metabolomics", "代谢组"],
    "bulk": ["bulk", "bulk rna", "bulk-seq", "bulk rnaseq"],
    "methylation": ["methylation", "甲基化", "bisulfite", "epigenome"],
    "chipseq": ["chipseq", "chip-seq", "cuttag", "cut&tag"],
    "multiome": ["multiome", "multi-ome", "10x multiome"],
}


def _expand_query(query: str) -> list:
    """Expand query with synonyms for semantic matching."""
    query_lower = query.lower()
    queries = [query_lower]
    for key, syns in SYNONYMS.items():
        # 如果 query 包含 key 或任何 synonym，加入所有 synonyms
        all_terms = [key] + syns
        for term in all_terms:
            if term in query_lower:
                queries.extend(all_terms)
                break
    # 去重
    return list(dict.fromkeys(queries))


def _normalize_species(species: str) -> list:
    """标准化物种名，返回可能的路径名列表。
    
    语义映射: 人/智人/human/Homo sapiens -> Homo_sapiens
              鼠/小鼠/mouse/Mus musculus -> Mus_musculus
              猴/猕猴/monkey/macaque -> monkey
              斑马鱼/zebrafish -> zebrafish
    """
    if not species:
        return []
    s = species.lower().strip()
    variants = set([species.strip()])
    matched_key = None
    for key, syns in SYNONYMS.items():
        # 只匹配物种同义词
        if key not in ("human", "mouse", "monkey", "zebrafish", "rat", "fly", "worm", "pig"):
            continue
        all_terms = [key] + syns
        if s in [x.lower() for x in all_terms]:
            variants.update(all_terms)
            variants.add(key)
            matched_key = key
            break
    
    # 路径格式: 标准目录名
    path_variants = set()
    for v in variants:
        path_variants.add(v)
        path_variants.add(v.lower())
        path_variants.add(v.title())
    
    # 映射到实际知识库目录名
    if matched_key == "human" or s in ("人", "人类", "智人", "homo sapiens"):
        path_variants.update(["Homo_sapiens", "Homo sapiens", "human"])
    elif matched_key == "mouse" or s in ("鼠", "小鼠", "老鼠", "mus musculus"):
        path_variants.update(["Mus_musculus", "Mus musculus", "mouse"])
    elif matched_key == "monkey":
        path_variants.update(["monkey", "Monkey"])
    elif matched_key == "zebrafish":
        path_variants.update(["zebrafish", "Zebrafish"])
    return list(path_variants)


def _normalize_tissue(tissue: str) -> list:
    """标准化组织名。"""
    if not tissue:
        return []
    t = tissue.lower().strip()
    variants = set([tissue.strip()])
    for key, syns in SYNONYMS.items():
        if t == key or t in syns or any(t == x for x in syns):
            variants.update(syns)
            variants.add(key)
    # 路径格式: "skeletal_muscle", "skeletal muscle", "骨骼肌"
    path_variants = set()
    for v in variants:
        path_variants.add(v)
        path_variants.add(v.replace(" ", "_"))
        path_variants.add(v.replace("_", " "))
    return list(path_variants)


def _search_kb(query: str, species: str = "", tissue: str = "", direction: str = "") -> dict:
    """Search knowledge base files with enhanced logic."""
    kb_paths = [
        Path("E:/MemOmics-Agent/memomics/knowledge_base"),
        Path("memomics/knowledge_base"),
        Path("E:/MemOmics/knowledge_base"),
    ]

    results = []
    queries = _expand_query(query)
    species_variants = _normalize_species(species)
    tissue_variants = _normalize_tissue(tissue)

    for kb_path in kb_paths:
        if not kb_path.exists():
            continue
        for root, dirs, files in os.walk(kb_path):
            for fname in files:
                if not fname.endswith(('.yaml', '.yml', '.json', '.md')):
                    continue
                fpath = Path(root) / fname
                rel_path = str(fpath.relative_to(kb_path))

                # 路径优先匹配 — 如果指定了 species/tissue，优先匹配路径
                path_boost = 0
                if species_variants:
                    for sv in species_variants:
                        if sv.lower() in rel_path.lower():
                            path_boost += 10
                if tissue_variants:
                    for tv in tissue_variants:
                        if tv.lower() in rel_path.lower():
                            path_boost += 10
                if direction:
                    dir_lower = direction.lower()
                    if dir_lower in rel_path.lower():
                        path_boost += 5
                    # 同义词扩展 direction
                    for key, syns in SYNONYMS.items():
                        if dir_lower == key or dir_lower in syns:
                            for syn in syns:
                                if syn.lower() in rel_path.lower():
                                    path_boost += 5
                                    break

                try:
                    content = fpath.read_text(encoding='utf-8', errors='ignore')
                    content_lower = content.lower()
                    # 检查 query 匹配
                    matched_terms = [q for q in queries if q in content_lower]
                    if matched_terms or path_boost > 0:
                        # 综合评分: 内容匹配 + 路径加权
                        content_score = sum(content_lower.count(q) for q in matched_terms) if matched_terms else 0
                        score = content_score + path_boost

                        if score == 0:
                            continue

                        # 提取相关片段 — 对于 YAML 返回完整内容
                        snippet = ""
                        if fname.endswith(('.yaml', '.yml')):
                            # 对于 YAML，返回完整内容（通常不超过几百行）
                            snippet = content[:2000]
                        else:
                            for line in content.split('\n'):
                                if any(q in line.lower() for q in matched_terms):
                                    snippet += line.strip() + "\n"
                                    if len(snippet) > 500:
                                        break

                        results.append({
                            "file": rel_path,
                            "score": score,
                            "matched_terms": matched_terms[:5],
                            "path_boost": path_boost,
                            "snippet": snippet[:1500]
                        })
                except Exception:
                    continue

    # 去重（按文件名），保留高分
    seen = {}
    for r in results:
        key = r["file"]
        if key not in seen or r["score"] > seen[key]["score"]:
            seen[key] = r
    results = sorted(seen.values(), key=lambda x: x["score"], reverse=True)

    return {"query": query, "species": species, "tissue": tissue, "direction": direction,
            "total": len(results), "results": results[:15]}


def search_knowledge(query: str, species: str = "", tissue: str = "", direction: str = "") -> str:
    """Search knowledge base and return JSON results."""
    result = _search_kb(query, species, tissue, direction)
    if result["total"] == 0:
        result["suggestion"] = (
            "知识库未找到匹配。请用 web 工具搜索相关文献，"
            "提取方法和参数后存入知识库。"
            "搜索建议: 在 PubMed/Google Scholar 搜 '"
            + query + " " + species + " " + tissue
            + "'"
        )
    return json.dumps(result, ensure_ascii=False, indent=2)


def _register():
    from tools.registry import registry
    registry.register(
        name="search_knowledge",
        toolset="memomics",
        schema=SCHEMA,
        handler=lambda args, **kw: search_knowledge(
            args.get("query", ""),
            args.get("species", ""),
            args.get("tissue", ""),
            args.get("direction", "")
        ),
        emoji="📚",
        max_result_size_chars=50_000,
    )

_register()
