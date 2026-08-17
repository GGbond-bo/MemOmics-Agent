"""Knowledge base search tool — searches the MemOmics knowledge base.

v4: FTS5 + trigram upgrade
- SQLite FTS5 with trigram tokenizer for fast indexed search
- Native Chinese support ("细胞通讯" matches "CellChat" via trigram)
- BM25-based ranking (FTS5 'rank')
- Retained: path boosting, synonym expansion, file caching
- Fallback to os.walk if FTS5 unavailable
"""
import json
import os
import re
import time
import sqlite3
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
    # 可能是 MEMOMICS_HOME 或 E:/MemOmics 等
    project_root = this_file.parent.parent.parent
    for candidate in [
        project_root / "memomics" / "knowledge_base",
        project_root / "MemOmics-Agent" / "memomics" / "knowledge_base",
    ]:
        if candidate.exists():
            return candidate

    # 5. 常见部署路径（最后手段）
    for fallback in [
        Path("MEMOMICS_HOME/memomics/knowledge_base"),
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


# === FTS5 索引 (in-memory, built once at first search) ===
_fts_conn = None
_fts_lock = threading.Lock()
_fts_initialized = threading.Event()
_fts_file_map = {}  # rowid → {path, content}


def _init_fts() -> bool:
    """Build FTS5 index from KB files. Thread-safe, idempotent."""
    global _fts_conn, _fts_file_map
    if _fts_initialized.is_set() and _fts_conn is not None:
        return True

    with _fts_lock:
        if _fts_initialized.is_set():
            return _fts_conn is not None

        kb_root = _find_kb_root()
        if kb_root is None:
            _fts_initialized.set()
            return False

        try:
            conn = sqlite3.connect(":memory:", check_same_thread=False)
            conn.execute("CREATE VIRTUAL TABLE kb_fts USING fts5(path, content, tokenize='trigram')")

            rowid = 0
            file_map = {}
            for root, dirs, files in os.walk(kb_root):
                for fname in files:
                    if not fname.endswith(('.yaml', '.yml', '.json', '.md')):
                        continue
                    fpath = Path(root) / fname
                    try:
                        rel_path = str(fpath.relative_to(kb_root))
                    except ValueError:
                        continue
                    content = _read_file_cached(fpath)
                    if not content or len(content) < 10:
                        continue
                    rowid += 1
                    conn.execute(
                        "INSERT INTO kb_fts(rowid, path, content) VALUES (?, ?, ?)",
                        (rowid, rel_path, content)
                    )
                    file_map[rowid] = {"path": rel_path, "content": content}

            _fts_conn = conn
            _fts_file_map = file_map
            _fts_initialized.set()
            logger.info(f"kb_search FTS5 index built: {rowid} documents")
            return True
        except Exception as e:
            logger.warning(f"kb_search FTS5 init failed: {e}, falling back to os.walk")
            _fts_conn = None
            _fts_initialized.set()
            return False


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

    # === v4: Try FTS5 first ===
    if _init_fts() and _fts_conn is not None:
        fts_terms = []
        short_terms = []
        for q in queries:
            q_clean = q.strip().replace('"', '').replace("'", "")
            if not q_clean:
                continue
            if len(q_clean) < 3:
                # P1-9(2026-08-13): trigram tokenizer 对 <3 字符的词（中文双字词
                # 如"质控/聚类"、英文缩写如"qc"）生成不了 token，MATCH 静默零命中。
                # 短词不能进 FTS —— 记录并让整条查询回落 v3 os.walk 子串匹配。
                short_terms.append(q_clean)
            elif q_clean.lower() in _SHORT_WORD_BLACKLIST:
                fts_terms.append(f'"{q_clean}"')
            else:
                fts_terms.append(q_clean)
        if fts_terms and not short_terms:
            fts_query = " OR ".join(fts_terms)
            # 查询串行化：_fts_conn 是跨线程共享的内存库连接
            _fts_lock.acquire()
            try:
                rows = _fts_conn.execute(
                    "SELECT rowid, rank FROM kb_fts WHERE kb_fts MATCH ? ORDER BY rank LIMIT 30",
                    (fts_query,)
                ).fetchall()
                for row in rows:
                    rowid, rank = row
                    info = _fts_file_map.get(rowid, {})
                    rel_path = info.get("path", "")
                    content = info.get("content", "")
                    # Path boosting
                    path_boost = 0
                    if species_variants:
                        for sv in species_variants:
                            if sv.lower() in rel_path.lower():
                                path_boost += 25; break
                    if tissue_variants:
                        for tv in tissue_variants:
                            if tv.lower() in rel_path.lower():
                                path_boost += 15; break
                    if direction_variants:
                        for dv in direction_variants:
                            if dv.lower() in rel_path.lower():
                                path_boost += 10; break
                    fts_score = max(0, 100 + int(rank))
                    content_lower = content.lower()
                    matched_terms = [q for q in queries if _word_match(q, content_lower)][:5]
                    snippet = content[:2000]
                    results.append({
                        "file": rel_path, "score": fts_score + path_boost,
                        "matched_terms": matched_terms, "path_boost": path_boost,
                        "snippet": snippet[:1500]
                    })
                # Deduplicate and sort
                seen = {}
                for r in results:
                    key = r["file"]
                    if key not in seen or r["score"] > seen[key]["score"]:
                        seen[key] = r
                results = sorted(seen.values(), key=lambda x: x["score"], reverse=True)
                return {"query": query, "species": species, "tissue": tissue, "direction": direction,
                        "total": len(results), "results": results[:15], "engine": "fts5"}
            except sqlite3.OperationalError:
                logger.debug("FTS5 query failed, falling back to os.walk")
            finally:
                _fts_lock.release()

    # === v3 fallback: os.walk ===
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


def kb_coverage(species: str = "", tissue: str = "", direction: str = "", assay: str = "") -> str:
    """知识库覆盖度自检（2026-08-14）。

    检查 物种/组织/方向/类别/assay 五级目录的已有内容 vs 缺失，
    缺失时给出补充建议（触发 literature-param-extraction 收集文献）。
    """
    kb_root = _find_kb_root()
    if kb_root is None:
        return json.dumps({"ok": False, "error": "知识库目录未找到"}, ensure_ascii=False)
    _sp_parts = (species or "").strip().split()
    if len(_sp_parts) > 1:
        _seg_species = "_".join([_sp_parts[0].capitalize()] + [p.lower() for p in _sp_parts[1:]])
    else:
        _seg_species = (species or "").strip().lower()
    _seg_tissue = (tissue or "").strip().lower().replace(" ", "_").replace("-", "_")
    _seg_dir = (direction or "").strip().lower().replace(" ", "_").replace("-", "_")
    _seg_assay = (assay or "RNA").strip().upper()

    found = {"species": False, "tissue": False, "direction": False,
             "categories": {}, "assay": {}, "path": ""}
    suggestions = []

    if _seg_species and os.path.isdir(os.path.join(kb_root, _seg_species)):
        found["species"] = True
        if _seg_tissue and os.path.isdir(os.path.join(kb_root, _seg_species, _seg_tissue)):
            found["tissue"] = True
            _dir_base = os.path.join(kb_root, _seg_species, _seg_tissue, _seg_dir) if _seg_dir else ""
            if _seg_dir and os.path.isdir(_dir_base):
                found["direction"] = True
                found["path"] = _dir_base.replace("\\", "/")
                for _cat in ("01_生物学知识", "02_质控参数", "03_测序方法"):
                    _cd = os.path.join(_dir_base, _cat)
                    _fs = []
                    if os.path.isdir(_cd):
                        if _cat == "03_测序方法":
                            # 方法类目下按 assay 子目录组织 → 递归计数
                            _fs = sorted(str(f.relative_to(_cd)).replace("\\", "/")
                                         for f in Path(_cd).rglob("*.yaml") if f.is_file())
                        else:
                            _fs = sorted(f for f in os.listdir(_cd) if f.endswith((".yaml", ".yml", ".md")))
                    found["categories"][_cat] = {"count": len(_fs), "sample": _fs[:6]}
                _md = os.path.join(_dir_base, "03_测序方法", _seg_assay)
                if os.path.isdir(_md):
                    _fs = sorted(f for f in os.listdir(_md) if f.endswith((".yaml", ".yml")))
                    found["assay"][_seg_assay] = {"count": len(_fs), "sample": _fs[:6]}

    if not found["species"] and _seg_species:
        suggestions.append(f"知识库中没有物种 {_seg_species} — 全新覆盖，建议触发 literature-param-extraction 从文献收集起步")
    if found["species"] and not found["tissue"] and _seg_tissue:
        try:
            _tissues = sorted(d for d in os.listdir(os.path.join(kb_root, _seg_species))
                              if os.path.isdir(os.path.join(kb_root, _seg_species, d)))
        except OSError:
            _tissues = []
        suggestions.append(f"该物种下已有组织: {', '.join(_tissues)}；缺少 {_seg_tissue} — 建议触发文献收集补充")
    if found["tissue"] and not found["direction"] and _seg_dir:
        try:
            _dirs = sorted(d for d in os.listdir(os.path.join(kb_root, _seg_species, _seg_tissue))
                           if os.path.isdir(os.path.join(kb_root, _seg_species, _seg_tissue, d)))
        except OSError:
            _dirs = []
        suggestions.append(f"该组织下已有方向: {', '.join(_dirs)}；缺少 {_seg_dir} — 建议触发文献收集补充")
    _missing = [k for k, v in found["categories"].items() if v.get("count", 0) == 0]
    if _seg_assay and _seg_assay not in found["assay"]:
        _missing.append(f"03_测序方法/{_seg_assay}")
    _covered = (found["direction"] and not _missing)
    _total_files = sum(v.get("count", 0) for v in found["categories"].values())

    return json.dumps({
        "ok": True,
        "species": _seg_species, "tissue": _seg_tissue, "direction": _seg_dir, "assay": _seg_assay,
        "found": found,
        "missing": _missing,
        "covered": _covered,
        "total_files_in_direction": _total_files,
        "suggestions": suggestions,
        "next": ("覆盖充分，可直接 search_knowledge 查参数" if _covered else
                 "覆盖不足 → 触发 literature-param-extraction skill 收集文献补充知识库"),
    }, ensure_ascii=False, indent=2)


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
            max_result_size_chars=20_000,
        )
        registry.register(
            name="kb_coverage",
            toolset="memomics",
            schema={
                "name": "kb_coverage",
                "description": (
                    "知识库覆盖度自检：检查 物种/组织/方向/类别/assay 五级目录已有内容与缺失。"
                    "新项目启动分析前调用，缺失时按建议触发文献收集补充知识库。"
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "species": {"type": "string", "description": "物种，如 'Homo sapiens'"},
                        "tissue": {"type": "string", "description": "组织，如 'skeletal muscle'"},
                        "direction": {"type": "string", "description": "方向，如 'aging'"},
                        "assay": {"type": "string", "description": "测序方法: RNA/ATAC/spatial/bulk", "default": "RNA"},
                    },
                    "required": ["species", "tissue", "direction"],
                },
            },
            handler=lambda args, **kw: kb_coverage(
                args.get("species", ""),
                args.get("tissue", ""),
                args.get("direction", ""),
                args.get("assay", "RNA"),
            ),
            emoji="🗺️",
            max_result_size_chars=8_000,
        )
    except ImportError:
        pass  # 不在 Hermes 环境中时不注册

_register()
