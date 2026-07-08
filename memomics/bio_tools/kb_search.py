"""Knowledge base search tool — searches the MemOmics knowledge base.

v3: 全面增强
- 按 species/tissue/direction 定位目录
- 同义词扩展覆盖英文关键词 + 疾病/表型术语
- 词边界匹配（防止短词误命中）
- 动态路径检测（不硬编码）
- 文件内容缓存（避免每次 os.walk 重新读取）
- 返回完整参数而非片段
- 知识库不存在时返回建议
"""
import json
import os
import re
import time
import logging
import threading
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

# 语义同义词 — 覆盖中英文 + 学名 + 疾病/表型
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
    "pancreas": ["pancreas", "胰", "胰腺", "pancreatic"],
    "eye": ["eye", "眼", "视网膜", "retina", "ocular"],
    "bladder": ["bladder", "膀胱", "urinary"],
    "uterus": ["uterus", "子宫", "endometrium", "子宫内膜"],
    "prostate": ["prostate", "前列腺", "prostatic"],
    "ovary": ["ovary", "卵巢", "ovarian"],
    "testis": ["testis", "睾丸", "testicular"],
    "thymus": ["thymus", "胸腺", "thymic"],
    # 方向
    "aging": ["aging", "aged", "elderly", "老年", "衰老", "老", "senescence", "老化", "sarcopenia", "肌少症", "frailty", "衰弱"],
    "ad": ["alzheimer", "alzheimer's disease", "阿尔茨海默", "ad"],
    "development": ["development", "发育", "发展", "embryonic", "胚胎"],
    "cardiomyopathy": ["cardiomyopathy", "心肌病"],
    "fibrosis": ["fibrosis", "纤维化", "pulmonary fibrosis", "肺纤维化"],
    "denervation": ["denervation", "去神经", "神经切除"],
    "regeneration": ["regeneration", "再生", "sarcomere regeneration"],
    "disease": ["disease", "疾病", "病理", "pathology"],
    "cancer": ["cancer", "癌", "肿瘤", "tumor", "tumour", "oncology", "neoplasm", "malignancy"],
    "inflammation": ["inflammation", "炎症", "inflammatory", "炎"],
    "injury": ["injury", "损伤", "injured", "damage", "wound", "创伤"],
    "diabetes": ["diabetes", "糖尿病", "diabetic", "dm", "t2d", "type 2 diabetes"],
    "obesity": ["obesity", "肥胖", "obese"],
    "neurodegeneration": ["neurodegeneration", "神经退行", "neurodegenerative", "als", "parkinson", "帕金森", "hd", "huntington"],
    "ischemia": ["ischemia", "缺血", "ischemic", "hypoxia", "缺氧", "reperfusion", "再灌注"],
    "infection": ["infection", "感染", "infectious", "viral", "bacterial", "covid", "sars"],
    "autoimmune": ["autoimmune", "自身免疫", "lupus", "狼疮", "ra", "rheumatoid", "类风湿"],
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
    "cite_seq": ["cite-seq", "cite_seq", "adt", "antibody", "蛋白质抗体"],
    "vdj": ["vdj", "vdj-seq", "tcr", "bcr", "immune repertoire", "免疫组库"],
}


# === 短词黑名单：这些词长度 <=3，在子串匹配中容易误命中 ===
_SHORT_WORD_BLACKLIST = {"ad", "qc", "go", "dm", "ra", "hd", "als"}

# === 文件内容缓存 ===
_file_cache = {}
_file_cache_lock = threading.Lock()
_CACHE_TTL = 300  # 缓存5分钟


def _find_kb_root() -> Path:
    """动态检测知识库根目录，不硬编码路径。

    搜索策略（按优先级）：
    1. 环境变量 MEMOMICS_KB_DIR
    2. 相对路径 memomics/knowledge_base（当前工作目录）
    3. 基于 memomics 包安装位置推导
    4. 常见部署路径
    """
    # 1. 环境变量
    env_dir = os.environ.get("MEMOMICS_KB_DIR")
    if env_dir and Path(env_dir).exists():
        return Path(env_dir)

    # 2. 相对路径
    cwd_path = Path("memomics/knowledge_base")
    if cwd_path.exists():
        return cwd_path

    # 3. 基于本文件位置推导
    this_file = Path(__file__).resolve()
    # 本文件在 memomics/bio_tools/kb_search.py
    # 知识库在 memomics/knowledge_base
    derived_path = this_file.parent.parent / "knowledge_base"
    if derived_path.exists():
        return derived_path

    # 4. 基于项目根目录
    # 可能是 E:/MemOmics-Agent 或 E:/MemOmics 等
    project_root = this_file.parent.parent.parent
    for candidate in [
        project_root / "memomics" / "knowledge_base",
        project_root / "MemOmics-Agent" / "memomics" / "knowledge_base",
    ]:
        if candidate.exists():
            return candidate

    # 5. 常见部署路径（最后手段）
    for fallback in [
        Path("E:/MemOmics-Agent/memomics/knowledge_base"),
        Path("E:/MemOmics/memomics/knowledge_base"),
    ]:
        if fallback.exists():
            return fallback

    return None  # 未找到


def _read_file_cached(fpath: Path) -> str:
    """读取文件内容，带缓存（TTL 5分钟），避免每次搜索重新读磁盘。"""
    now = time.time()
    cache_key = str(fpath)

    with _file_cache_lock:
        if cache_key in _file_cache:
            content, ts = _file_cache[cache_key]
            if now - ts < _CACHE_TTL:
                return content

    try:
        content = fpath.read_text(encoding='utf-8', errors='ignore')
    except Exception:
        return ""

    with _file_cache_lock:
        _file_cache[cache_key] = (content, now)

    # 清理过期缓存（简单策略：超过2倍TTL的条目清理）
    if len(_file_cache) > 200:
        with _file_cache_lock:
            expired = [k for k, (_, ts) in _file_cache.items() if now - ts > _CACHE_TTL * 2]
            for k in expired:
                del _file_cache[k]

    return content


def _word_match(term: str, text: str) -> bool:
    """词边界匹配：检查 term 是否作为独立词出现在 text 中。

    对于短词（<=3字符，如 'ad', 'qc', 'go'），
    使用正则词边界防止误匹配（'ad' 不匹配 'read', 'had' 等）。
    对于长词，保持子串匹配（兼容性）。
    """
    term_lower = term.lower()
    text_lower = text.lower()

    # 短词且在黑名单中 → 必须词边界匹配
    if len(term_lower) <= 3 and term_lower in _SHORT_WORD_BLACKLIST:
        # 使用正则词边界：\b 在英文中工作，对中文无害
        try:
            pattern = r'\b' + re.escape(term_lower) + r'\b'
            return bool(re.search(pattern, text_lower))
        except re.error:
            return term_lower in text_lower

    # CJK 字符不做词边界检查（中文没有空格分词）
    has_cjk = any('\u4e00' <= c <= '\u9fff' for c in term_lower)
    if has_cjk:
        return term_lower in text_lower

    # 长英文词：子串匹配即可（"aging" 不会误匹配其他常见词）
    return term_lower in text_lower


def _word_count(term: str, text: str) -> int:
    """统计 term 在 text 中的匹配次数（短词用词边界，长词用子串）。"""
    term_lower = term.lower()
    text_lower = text.lower()

    if len(term_lower) <= 3 and term_lower in _SHORT_WORD_BLACKLIST:
        try:
            pattern = r'\b' + re.escape(term_lower) + r'\b'
            return len(re.findall(pattern, text_lower))
        except re.error:
            return text_lower.count(term_lower)

    return text_lower.count(term_lower)


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


def _normalize_direction(direction: str) -> list:
    """标准化研究方向名。"""
    if not direction:
        return []
    d = direction.lower().strip()
    variants = set([direction.strip(), d])
    for key, syns in SYNONYMS.items():
        if d == key or d in [x.lower() for x in syns]:
            variants.update(syns)
            variants.add(key)
            break
    return list(variants)


def _search_kb(query: str, species: str = "", tissue: str = "", direction: str = "") -> dict:
    """Search knowledge base files with enhanced logic (v3)."""
    kb_root = _find_kb_root()
    if kb_root is None:
        return {
            "query": query, "species": species, "tissue": tissue, "direction": direction,
            "total": 0, "results": [],
            "suggestion": "知识库目录未找到。请设置 MEMOMICS_KB_DIR 环境变量或确认项目安装路径。"
        }

    results = []
    queries = _expand_query(query)
    species_variants = _normalize_species(species)
    tissue_variants = _normalize_tissue(tissue)
    direction_variants = _normalize_direction(direction)

    for root, dirs, files in os.walk(kb_root):
        for fname in files:
            if not fname.endswith(('.yaml', '.yml', '.json', '.md')):
                continue
            fpath = Path(root) / fname
            try:
                rel_path = str(fpath.relative_to(kb_root))
            except ValueError:
                continue

            # 路径优先匹配 — 如果指定了 species/tissue/direction，优先匹配路径
            # 权重设置：species > tissue > direction，因为物种匹配最重要
            path_boost = 0
            if species_variants:
                for sv in species_variants:
                    if sv.lower() in rel_path.lower():
                        path_boost += 25  # 物种匹配权重最高
                        break  # 每类最多加一次
            if tissue_variants:
                for tv in tissue_variants:
                    if tv.lower() in rel_path.lower():
                        path_boost += 15  # 组织匹配次之
                        break
            if direction_variants:
                for dv in direction_variants:
                    if dv.lower() in rel_path.lower():
                        path_boost += 10  # 方向匹配再次之
                        break

            # 读取文件内容（带缓存）
            content = _read_file_cached(fpath)
            if not content:
                continue

            content_lower = content.lower()

            # 词边界匹配（防止短词误命中）
            matched_terms = [q for q in queries if _word_match(q, content_lower)]
            if matched_terms or path_boost > 0:
                # 综合评分: 内容匹配 + 路径加权
                content_score = sum(_word_count(q, content_lower) for q in matched_terms) if matched_terms else 0
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
                        if any(_word_match(q, line) for q in matched_terms):
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
    try:
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
    except ImportError:
        pass  # 不在 Hermes 环境中时不注册

_register()
