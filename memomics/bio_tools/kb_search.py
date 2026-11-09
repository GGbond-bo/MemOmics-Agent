"""Knowledge base search tool — searches the MemOmics knowledge base.

v4: FTS5 + trigram upgrade
- SQLite FTS5 with trigram tokenizer for fast indexed search
- Native Chinese support ("细胞通讯" matches "CellChat" via trigram)
- BM25-based ranking (FTS5 'rank')
- Retained: path boosting, synonym expansion, file caching
- Fallback to os.walk if FTS5 unavailable
"""
import json
import math
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
        "Search the MemOmics knowledge base for bioinformatics analysis templates, QC parameters, "
        "method recommendations, biological claims, and their source evidence. "
        "ALWAYS call this BEFORE choosing parameters, writing analysis code, making a conclusion, "
        "or starting a debate. It returns claim-level evidence with L0-L3, DOI/quote/locator, "
        "experimental object, cohort, background, annotated markers, wet-lab conditions/reagents, "
        "organoid/3D culture conditions, parameters and conflict candidates. "
        "Pass species, tissue, and direction for targeted search. "
        "支持中英文语义匹配（如 '人' → 'human', '智人', 'Homo sapiens')."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Search query (e.g. 'QC parameters', 'clustering resolution', 'CellChat', '示例组织衰老marker')"
            },
            "species": {"type": "string", "description": "Species (e.g. human, mouse, Homo sapiens, 人)"},
            "tissue": {"type": "string", "description": "Tissue (e.g. skeletal_muscle, brain, heart, 示例组织)"},
            "direction": {"type": "string", "description": "Research direction (e.g. aging, ad, development, 衰老)"},
            "kind": {"type": "string", "enum": ["all", "claims", "parameters", "markers", "wet_lab", "organoids"],
                     "description": "all=all structured knowledge; claims=conclusions/evidence; parameters=methods/QC/software; markers=annotated markers; wet_lab=experimental conditions/reagents; organoids=organoid/3D culture", "default": "all"},
            "level": {"type": "string", "enum": ["", "L0", "L1", "L2", "L3"],
                      "description": "Optional claim evidence level filter", "default": ""},
            "max_claims": {"type": "integer", "description": "Max claims to return (1-20, default 8)", "default": 8},
            "max_parameters": {"type": "integer", "description": "Max parameter rows to return (1-30, default 10)", "default": 10}
        },
        "required": ["query"]
    }
}

# 语义同义词 — 覆盖中英文 + 学名 + 疾病/表型
SYNONYMS = {
    # 物种 — 标准目录名为 Homo_sapiens / Mus_musculus / monkey / zebrafish
    "human": ["human", "智人", "homo sapiens", "人类", "人", "homo_sapiens", "human pbmc"],
    "mouse": ["mouse", "小鼠", "mus musculus", "老鼠", "鼠", "mus_musculus", "mice"],
    "monkey": ["monkey", "猴", "猕猴", "macaque", "rhesus", "macaca mulatta", "macaca_mulatta", "食蟹猴", "cynomolgus", "macaca fascicularis", "玻尾猴", "猴子"],
    "zebrafish": ["zebrafish", "斑马鱼", "danio rerio", "danio", "danio_rerio"],
    "rat": ["rat", "大鼠", "珉鼠", "rattus norvegicus", "rattus_norvegicus"],
    "fly": ["fly", "果蝇", "drosophila", "drosophila melanogaster", "drosophila_melanogaster"],
    "worm": ["worm", "线虫", "c. elegans", "caenorhabditis elegans", "caenorhabditis_elegans"],
    "pig": ["pig", "猪", "sus scrofa", "sus_scrofa", "porcine"],
    # 组织
    "skeletal_muscle": ["skeletal_muscle", "skeletal muscle", "muscle", "肌", "肌肉", "示例组织", "skeletal"],
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
    # 化合物/药物 — 知识库 chemistry/compounds 里全是英文名文件，中文提问必须能对上
    "rapamycin": ["rapamycin", "雷帕霉素", "sirolimus", "西罗莫司"],
    "tamoxifen": ["tamoxifen", "他莫昔芬"],
    "buprenorphine": ["buprenorphine", "丁丙诺啡"],
    "lidocaine": ["lidocaine", "xylocaine", "利多卡因"],
    "gemcitabine": ["gemcitabine", "吉西他滨"],
    "paclitaxel": ["paclitaxel", "紫杉醇"],
    "pemetrexed": ["pemetrexed", "培美曲塞"],
    "vinorelbine": ["vinorelbine", "长春瑞滨"],
    "fexofenadine": ["fexofenadine", "非索非那定"],
    "famotidine": ["famotidine", "法莫替丁"],
    "selinexor": ["selinexor", "塞利尼索"],
    "nmda": ["nmda", "n-methyl-d-aspartate", "谷氨酸"],
    "dmso": ["dmso", "二甲基亚砜"],
    "edta": ["edta", "乙二胺四乙酸"],
    "tmt": ["tmt", "串联质谱标签"],
    "wgcna": ["wgcna", "hdwgcna", "共表达网络", "共表达", "co-expression"],
    "gwas": ["gwas", "全基因组关联", "关联分析"],
}


# === 短词黑名单：这些词长度 <=3，在子串匹配中容易误命中 ===
_SHORT_WORD_BLACKLIST = {"ad", "qc", "go", "dm", "ra", "hd", "als"}

# 通用中文词：几乎所有知识文件都"沾"得上，进检索只会稀释排序（问 "GWAS 方法" 时
# 「方法」不该把一堆 default_kb_method.yaml 抬起来）。
_CJK_STOPWORDS = {"方法", "参数", "阈值", "图谱", "分析", "数据", "结果", "流程",
                  "知识", "相关", "研究", "如何", "怎么", "什么", "以及", "进行"}

# === 文件内容缓存 ===
_file_cache = {}
_file_cache_lock = threading.Lock()
_CACHE_TTL = 300  # 缓存5分钟


def invalidate_cache() -> None:
    """清空文件缓存与 FTS 索引，让刚写入的 KB 条目立即可检索。

    FTS5 是进程内内存索引，只在首次检索时构建；save_knowledge 写完后不失效
    会导致新条目在重启前完全查不到。写入端成功落盘后必须调用本函数。
    """
    global _fts_conn, _fts_file_map, _KB_SPECIES_ROOTS_CACHE
    with _fts_lock:
        try:
            if _fts_conn is not None:
                _fts_conn.close()
        except Exception:
            pass
        _fts_conn = None
        _fts_file_map = {}
        _fts_initialized.clear()
    with _file_cache_lock:
        _file_cache.clear()
    _KB_SPECIES_ROOTS_CACHE = None
    logger.info("kb_search cache invalidated")


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
        # 2026-10-26：统一返回绝对路径（此前从安装目录启动时返回相对路径，
        # 与 kb_roots/save_knowledge 的绝对路径形态不一致，排查时容易误判）
        return cwd_path.resolve()

    # 3. 基于本文件位置推导
    this_file = Path(__file__).resolve()
    # 本文件在 memomics/bio_tools/kb_search.py
    # 知识库在 memomics/knowledge_base
    derived_path = this_file.parent.parent / "knowledge_base"
    if derived_path.exists():
        return derived_path

    # 4. 统一真源（2026-10-26）：kb_roots.kb_root_path 会顺带探测 cwd 变体与常见部署路径；
    #    这里只返回"确实存在"的目录（创建交给 ensure_kb_root，写入端用）。
    try:
        from memomics.bio_tools.kb_roots import kb_root_path
        unified = Path(kb_root_path())
        if unified.exists():
            return unified
    except Exception:
        pass

    # 5. 基于项目根目录（老口径保留：项目根/MemOmics-Agent 嵌套形态）
    project_root = this_file.parent.parent.parent
    candidate = project_root / "MemOmics-Agent" / "memomics" / "knowledge_base"
    if candidate.exists():
        return candidate

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


def _load_yaml_doc(content: str) -> dict:
    try:
        import yaml
        doc = yaml.safe_load(content)
        return doc if isinstance(doc, dict) else {}
    except Exception:
        return {}


def _claim_public(c: dict, rel_path: str, idx: int) -> dict:
    src = c.get("source") if isinstance(c.get("source"), dict) else {}
    val = c.get("validation") if isinstance(c.get("validation"), dict) else {}
    return {
        "claim_id": c.get("id") or f"{rel_path}#C{idx:02d}",
        "evidence_level": str(c.get("evidence_level") or "L1"),
        "domain": str(c.get("domain") or "").strip(),
        "subcategory": str(c.get("subcategory") or "").strip(),
        "text": str(c.get("text") or "").strip(),
        "source": {
            "doi": str(src.get("doi") or "").strip(),
            "locator": str(src.get("locator") or c.get("locator") or "").strip(),
            "quote": str(src.get("quote") or c.get("quote") or "").strip(),
            "type": str(src.get("type") or "primary").strip(),
        },
        "assay": str(c.get("assay") or "").strip(),
        "species": c.get("species") or [],
        "tissue": str(c.get("tissue") or "").strip(),
        "experimental_object": str(c.get("experimental_object") or "").strip(),
        "cohort": str(c.get("cohort") or "").strip(),
        "background": str(c.get("background") or "").strip(),
        "validation": {
            "method": str(val.get("method") or "").strip(),
            "locator": str(val.get("locator") or "").strip(),
            "claim_specific": bool(val.get("claim_specific")),
            "design": str(val.get("design") or "").strip(),
        },
        "evidence_type": str(c.get("evidence_type") or "").strip(),
        "evaluation": str(c.get("evaluation") or "").strip(),
        "grading_reason": str(c.get("grading_reason") or "").strip(),
        "source_verified": c.get("source_verified"),
        "review_required": bool(c.get("review_required")),
        "source_file": rel_path.replace("\\", "/"),
    }


def _extract_claims(content: str, rel_path: str, limit: int = 4) -> list:
    doc = _load_yaml_doc(content)
    claims = doc.get("claims") if isinstance(doc.get("claims"), list) else []
    out = []
    for i, c in enumerate(claims, 1):
        if not isinstance(c, dict) or not str(c.get("text") or "").strip():
            continue
        pub = _claim_public(c, rel_path, i)
        pub["domain"] = doc.get("domain") or pub.get("domain") or ""
        pub["subcategory"] = doc.get("subcategory") or pub.get("subcategory") or ""
        out.append(pub)
        if len(out) >= limit:
            break
    return out


def _extract_parameters(content: str, rel_path: str, limit: int = 30) -> list:
    """Parse parameter/QC/software rows from kb-evidence-v2 Markdown content.

    v2 writes both Markdown tables and compact bullet lines
    (``- Seurat.FindClusters resolution = 0.03（...）``), so support both.
    """
    rows, section, headers = [], "", []
    for line in (content or "").splitlines():
        s = line.strip()
        if s.startswith("## "):
            section = s[3:].strip()
            headers = []
            continue
        if s.startswith("|"):
            cells = [x.strip() for x in s.strip("|").split("|")]
            if not cells or all(set(x) <= set("-: ") for x in cells):
                continue
            if not headers:
                headers = cells
                continue
            row = dict(zip(headers, cells))
            row["section"] = section
            row["source_file"] = rel_path.replace("\\", "/")
            rows.append(row)
        elif s.startswith("- ") and section:
            body = s[2:].strip()
            # sequencing: "- tech | 平台 X | 建库 Y | 深度 Z"
            if " | " in body:
                parts = [p.strip() for p in body.split(" | ") if p.strip()]
                tool = parts[0]
                for part in parts[1:]:
                    if " " in part:
                        k, v = part.split(" ", 1)
                        rows.append({"tool": tool, "param": k, "value": v,
                                     "context": section, "section": section,
                                     "source_file": rel_path.replace("\\", "/")})
            elif " = " in body:
                left, right = body.split(" = ", 1)
                context = ""
                m = re.search(r"[（(]([^）)]*)[）)]\s*$", right)
                if m:
                    context = m.group(1).strip()
                    right = right[:m.start()].strip()
                rows.append({"tool": "", "param": left.strip(), "value": right.strip(),
                             "context": context or section, "section": section,
                             "source_file": rel_path.replace("\\", "/")})
                if "." in left:
                    _tool, _param = left.split(".", 1)
                    rows[-1]["tool"] = _tool.strip()
                    rows[-1]["param"] = _param.strip()
            elif "：" in body or ":" in body:
                left, right = re.split(r"[：:]", body, maxsplit=1)
                rows.append({"tool": "", "param": left.strip(), "value": right.strip(),
                             "context": section, "section": section,
                             "source_file": rel_path.replace("\\", "/")})
        if len(rows) >= 200:
            break
    priority = {"关键参数": 0, "质控参数": 1, "软件/包": 2, "测序方法": 3, "数据库": 4}
    rows.sort(key=lambda r: priority.get(r.get("section", ""), 9))
    return rows[:limit]


def _extract_markers(content: str, rel_path: str, limit: int = 8) -> list:
    doc = _load_yaml_doc(content)
    rows = doc.get("markers") if isinstance(doc.get("markers"), list) else []
    out = []
    for m in rows:
        if not isinstance(m, dict) or not str(m.get("gene") or "").strip():
            continue
        out.append({
            "gene": str(m.get("gene") or "").strip(),
            "cell_type": str(m.get("cell_type") or "").strip(),
            "direction": str(m.get("direction") or "na").strip(),
            "species": m.get("species") or [],
            "assay": str(m.get("assay") or "").strip(),
            "context": str(m.get("context") or "").strip(),
            "source": m.get("source") if isinstance(m.get("source"), dict) else {},
            "source_file": rel_path.replace("\\", "/"),
        })
        if len(out) >= limit:
            break
    return out


def _extract_wet_lab(content: str, rel_path: str, limit: int = 4) -> list:
    doc = _load_yaml_doc(content)
    rows = doc.get("wet_lab") if isinstance(doc.get("wet_lab"), list) else []
    out = []
    for w in rows:
        if not isinstance(w, dict) or not str(w.get("experiment") or "").strip():
            continue
        out.append({
            "experiment": str(w.get("experiment") or "").strip(),
            "model": str(w.get("model") or "").strip(),
            "species": w.get("species") or [],
            "conditions": str(w.get("conditions") or "").strip(),
            "reagents": w.get("reagents") if isinstance(w.get("reagents"), list) else [],
            "readout": str(w.get("readout") or "").strip(),
            "n": str(w.get("n") or "").strip(),
            "source": w.get("source") if isinstance(w.get("source"), dict) else {},
            "source_file": rel_path.replace("\\", "/"),
        })
        if len(out) >= limit:
            break
    return out


def _extract_organoids(content: str, rel_path: str, limit: int = 4) -> list:
    doc = _load_yaml_doc(content)
    rows = doc.get("organoids") if isinstance(doc.get("organoids"), list) else []
    out = []
    for o in rows:
        if not isinstance(o, dict) or not str(o.get("name") or "").strip():
            continue
        out.append({
            "name": str(o.get("name") or "").strip(),
            "species": o.get("species") or [],
            "tissue": str(o.get("tissue") or "").strip(),
            "model_type": str(o.get("model_type") or "organoid").strip(),
            "media": str(o.get("media") or "").strip(),
            "cytokines": o.get("cytokines") if isinstance(o.get("cytokines"), list) else [],
            "matrix": str(o.get("matrix") or "").strip(),
            "duration": str(o.get("duration") or "").strip(),
            "passage": str(o.get("passage") or "").strip(),
            "readout": str(o.get("readout") or "").strip(),
            "source": o.get("source") if isinstance(o.get("source"), dict) else {},
            "source_file": rel_path.replace("\\", "/"),
        })
        if len(out) >= limit:
            break
    return out


def _enrich_hits(results: list, max_claims_per_hit: int = 3,
                 max_params_per_hit: int = 4) -> list:
    root = _find_kb_root()
    if root is None:
        return results
    for hit in results:
        rel = hit.get("file", "")
        if not rel:
            continue
        content = _read_file_cached(Path(root) / rel)
        if not content:
            continue
        hit["claim_count"] = 0
        hit["parameter_count"] = 0
        content_text = content
        if rel.lower().endswith((".yaml", ".yml")):
            doc = _load_yaml_doc(content)
            if isinstance(doc.get("content"), str):
                content_text = doc["content"]
            claims = _extract_claims(content, rel, max_claims_per_hit)
            if claims:
                hit["claims"] = claims
                hit["claim_count"] = len(claims)
        params = _extract_parameters(content_text, rel, max_params_per_hit)
        if params:
            hit["parameters"] = params
            hit["parameter_count"] = len(params)
        markers = _extract_markers(content, rel, 6)
        if markers:
            hit["markers"] = markers
            hit["marker_count"] = len(markers)
        wet = _extract_wet_lab(content, rel, 3)
        if wet:
            hit["wet_lab"] = wet
            hit["wet_lab_count"] = len(wet)
        organoids = _extract_organoids(content, rel, 3)
        if organoids:
            hit["organoids"] = organoids
            hit["organoid_count"] = len(organoids)
    return results


def format_claims_for_prompt(claims: list, max_claims: int = 8) -> str:
    """Compact, citation-ready claim block for analysis/debate prompt injection."""
    order = {"L3": 3, "L2": 2, "L1": 1, "L0": 0}
    picked = sorted(claims or [], key=lambda c: order.get(str(c.get("evidence_level")), 1),
                    reverse=True)[:max_claims]
    lines = ["【知识库 claim 证据（可引用；冲突并列，不要合并）】"]
    for c in picked:
        src = c.get("source") or {}
        lines.append(
            f"- [{c.get('evidence_level', 'L1')}] {c.get('text', '')}\n"
            f"  来源：DOI {src.get('doi') or '未报告'} ｜ {src.get('locator') or '未报告'}\n"
            f"  原文：{str(src.get('quote') or '')[:400]}"
        )
        if c.get("domain") == "ai":
            lines.append(f"  评估：{c.get('evaluation') or '未报告'} ｜ "
                         f"分类：ai/{c.get('subcategory') or 'general'}")
        else:
            lines.append(
                f"  对象/队列/背景：{c.get('experimental_object') or '未报告'} ｜ "
                f"物种：{', '.join(c.get('species') or []) or '未报告'} ｜ "
                f"组织：{c.get('tissue') or '未报告'} ｜ "
                f"{c.get('cohort') or '未报告'} ｜ {c.get('background') or '未报告'}\n"
                f"  验证：{(c.get('validation') or {}).get('method') or '未报告'}"
                + (f"\n  评估：{c.get('evaluation')}" if c.get("evaluation") else "")
            )
    return "\n".join(lines)


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
    # 中文没有空格分词：整串丢给 trigram FTS 几乎零命中（"示例组织衰老" 要求文件里恰好连着出现这五个字）。
    # 这里把连续 CJK 串切成 3-gram、英文/数字按词切开，先把召回抬起来，排序交给 BM25 + 路径权重。
    for run in re.findall(r"[\u4e00-\u9fff]+", query or ""):
        if len(run) <= 3:
            queries.append(run)
        else:
            queries.extend(run[i:i + 3] for i in range(len(run) - 2))
    queries.extend(w.lower() for w in re.findall(r"[A-Za-z0-9_.+-]{2,}", query or ""))
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
    elif matched_key == "rat":
        path_variants.update(["Rattus_norvegicus", "Rattus norvegicus", "rat"])
    elif matched_key == "monkey":
        path_variants.update(["Macaca_mulatta", "Macaca mulatta", "monkey",
                              "Macaca_fascicularis", "Macaca fascicularis"])
    elif matched_key == "zebrafish":
        path_variants.update(["Danio_rerio", "Danio rerio", "zebrafish"])
    elif matched_key == "fly":
        path_variants.update(["Drosophila_melanogaster", "Drosophila melanogaster", "drosophila"])
    elif matched_key == "worm":
        path_variants.update(["Caenorhabditis_elegans", "Caenorhabditis elegans", "c_elegans"])
    elif matched_key == "pig":
        path_variants.update(["Sus_scrofa", "Sus scrofa", "pig"])
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
    # 路径格式: "skeletal_muscle", "skeletal muscle", "示例组织"
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


_NON_SPECIES_DIRS = {"common", "chemistry", "error_memory", "other"}

# 工具/流程同名文件（cellchat.yaml / wgcna.yaml / gwas.yaml ...）—— 问工具就是问它们
_TOOL_FILES = {"cellchat", "cellchat-v2", "trajectory", "wgcna", "hdwgcna", "gwas", "deg",
               "spatial", "scrna_qc", "atac_seq", "scenic", "monocle", "harmony", "doublet",
               "soupx", "cellbender", "scvi", "velocyto", "infercnv", "spatialde", "cellranger"}


def _archetype_weight(fname: str) -> float:
    """按知识条目「原型」微调排序（与 validate_kb.py 的原型划分对齐）。

    论文/经验条目（paper_*、*_empirical）擅长回答「有没有人做过」，不擅长回答「参数是多少」；
    问 CellChat 参数时，cellchat.yaml 应该压过一篇恰好反复提到 CellChat 的论文条目。

    ⚠️ 这是**固定量级**的微调（±20/30），在 BM25 量级（几百上千）面前基本等于没有；
    方法类查询真正靠得住的是 _intent_factor() 的乘子。这里保留是因为 os.walk 兜底路径的
    content_score 是纯词频（几十的量级），±20/30 在那里仍然有效。
    """
    n = (fname or "").lower()
    if n.startswith("paper_") or n.endswith("_empirical.yaml"):
        return -20.0
    stem = n[:-5] if n.endswith(".yaml") else n
    if "method" in n or stem in _TOOL_FILES:
        return 30.0
    if stem == "index":
        return 10.0
    if any(k in n for k in ("key_findings", "biology_knowledge", "gene_sets", "cell_types", "atlas")):
        return 15.0
    return 0.0


# 方法意图词：用户问的是「怎么做 / 参数多少 / 步骤」，不是「有没有人做过」。
_METHOD_INTENT_WORDS = ("方法", "参数", "步骤", "流程", "阈值", "如何", "怎么", "教程", "手册",
                        "protocol", "pipeline", "parameter", "tutorial", "workflow", "steps", "method")


def _has_method_intent(query: str) -> bool:
    q = (query or "").lower()
    return any(w in q for w in _METHOD_INTENT_WORDS)


def _intent_factor(fname: str, method_intent: bool) -> float:
    """按查询意图缩放「原型」权重（v6, 2026-10-07）——乘子，不是加数。

    事故：2026-10-07 20:12 建库新写入一批 paper_* 卡后，查「差异表达分析 方法」的前五名
    被论文卡占满（bm25×10≈388，扣掉固定的 −20 仍是 368），真正的 deg.yaml（27.7 + 路径 90
    = 117.7）掉到第六 —— 黄金集 kb-15 变红。根因和物种/组织/方向曾经踩过的坑同源
    （见 _structured_boost）：固定权重压不住 BM25 的量级。

    方法类查询下改成乘子，量级跟着 BM25 一起缩放：方法/工具卡 ×3、论文/经验卡 ×0.3
    （不是乘 0，论文卡仍留在结果里，只是不再霸榜）。非方法类查询不动（×1），
    避免影响「有没有人做过」这类问法。
    """
    if not method_intent:
        return 1.0
    n = (fname or "").lower()
    if n.startswith("paper_") or n.endswith("_empirical.yaml"):
        return 0.3
    stem = n[:-5] if n.endswith(".yaml") else n
    if "method" in n or stem in _TOOL_FILES:
        return 3.0
    return 1.0
_KB_SPECIES_ROOTS_CACHE = None


def _kb_species_roots() -> set:
    """知识库顶层里哪些目录算「物种根」（用来给别的物种文件降权）。"""
    global _KB_SPECIES_ROOTS_CACHE
    if _KB_SPECIES_ROOTS_CACHE is not None:
        return _KB_SPECIES_ROOTS_CACHE
    roots = set()
    kb_root = _find_kb_root()
    if kb_root is not None:
        try:
            for name in os.listdir(kb_root):
                if os.path.isdir(os.path.join(kb_root, name)) and name.lower() not in _NON_SPECIES_DIRS:
                    roots.add(name.lower())
        except OSError:
            pass
    _KB_SPECIES_ROOTS_CACHE = roots
    return roots


def _structured_boost(rel_path, species_variants, tissue_variants, direction_variants,
                      fname="", queries=()) -> int:
    """结构化路径权重（v5）。

    旧值 species+25 / tissue+15 / direction+10 远小于 BM25 的量级（FTS5 原始分在 100 上下），
    实测后果：问「人示例组织衰老」，第一名是 exercise 目录、第三名是肝；问「小鼠肝衰老」，
    人肝排在小鼠肝前面；问「小鼠肺纤维化」，回来一堆小鼠肝。只给几十点权重是压不住的，
    所以物种 +400 / 组织 +200 / 方向 +120，并且**指定了物种时给别的物种根降权**，
    让「同物种 > 通用目录（common/chemistry）> 别的物种」这个顺序稳定成立。
    """
    boost = _archetype_weight(fname)
    rel_lower = rel_path.lower()
    # 用 _word_match 而不是裸子串：方向 "ad" 只有 2 字符，裸子串会命中 academic-thesis-docx
    # 这种文件名，把整个 Homo_sapiens/brain/aging 目录顶到 Homo_sapiens/brain/ad 前面。
    if species_variants:
        if any(_word_match(sv, rel_lower) for sv in species_variants):
            boost += 400
        else:
            top = rel_path.replace("\\", "/").split("/", 1)[0].lower()
            if top and top in _kb_species_roots():
                boost -= 200
    if tissue_variants and any(_word_match(tv, rel_lower) for tv in tissue_variants):
        boost += 200
    if direction_variants and any(_word_match(dv, rel_lower) for dv in direction_variants):
        boost += 120
    if fname:
        # 文件名命中是强信号：问 "CellChat"/"wgcna" 时，叫这个名字的文件应该压过任何正文里
        # 恰好提过一嘴的长文。只算 >=4 字符的词，避免 "qc"/"deg" 这类短词把一堆文件抬上来。
        fname_lower = fname.lower()
        boost += min(300, 60 * sum(1 for q in queries if len(q) >= 3 and q.lower() in fname_lower))
    return boost


def _search_kb(query: str, species: str = "", tissue: str = "", direction: str = "",
               include_details: bool = False, max_claims_per_hit: int = 3,
               max_params_per_hit: int = 4) -> dict:
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
    method_intent = _has_method_intent(query)
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
            if q_clean in _CJK_STOPWORDS:
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
        # 短词（<3 字符）trigram 造不出 token，但**不能因此整条查询退回 os.walk 子串打分**：
        # 同义词表里有「人/鼠/肝/肺/肌」这类单字，中文查询几乎条条都带一个，于是几乎条条退回，
        # 退回去的评分是纯词频，"谁的文件大谁赢"（biology_knowledge.yaml 永远第一）。
        # 现在改成：能进 FTS 的词照常走 BM25，短词降级成候选过滤条件。
        short_terms = [t for t in short_terms if len(t) >= 2]  # 单字同义词噪声太大，直接丢
        if fts_terms:
            fts_query = " OR ".join(fts_terms)
            # 查询串行化：_fts_conn 是跨线程共享的内存库连接
            _fts_lock.acquire()
            try:
                rows = _fts_conn.execute(
                    "SELECT rowid, rank FROM kb_fts WHERE kb_fts MATCH ? ORDER BY rank LIMIT 200",
                    (fts_query,)
                ).fetchall()
                for row in rows:
                    rowid, rank = row
                    info = _fts_file_map.get(rowid, {})
                    rel_path = info.get("path", "")
                    content = info.get("content", "")
                    path_boost = _structured_boost(
                        rel_path, species_variants, tissue_variants, direction_variants,
                        os.path.basename(rel_path), queries)
                    # FTS5 的 rank 是 bm25()：**越负越相关**。旧代码 100+int(rank) 把强匹配算成了低分，
                    # 排序整个反过来（实测：问 CellChat，真正命中 cellchat.yaml 的候选排在只沾了一个
                    # 通用词的 default_kb_method.yaml 后面）。
                    # v6: 方法类查询再乘一次原型意图乘子（论文卡 ×0.3 / 方法卡 ×3），
                    #     否则新写入的论文卡会靠 BM25 量级把方法卡挤出前五（见 _intent_factor）。
                    fts_score = (max(0.0, -float(rank)) * 10.0
                                 * _intent_factor(os.path.basename(rel_path), method_intent))
                    content_lower = content.lower()
                    # 短词只加分、不过滤：过滤会直接零召回（问 "GWAS 方法"，gwas.yaml 正文里没有
                    # 「方法」两个字，就被一刀切掉了）。
                    short_hits = sum(1 for t in short_terms if _word_match(t, content_lower))
                    matched_terms = [q for q in queries if _word_match(q, content_lower)][:5]
                    snippet = content[:2000]
                    results.append({
                        "file": rel_path, "score": fts_score + path_boost + 4 * short_hits,
                        "matched_terms": matched_terms, "path_boost": path_boost,
                        "snippet": snippet[:1500]
                    })
                # 结构化兜底：调用方点名了 species/tissue/direction，就把对应目录的文件也纳入候选。
                # 知识库是按物种/组织/方向组织的，路径命中本身就是强信号；只靠正文词命中会漏掉
                # 那些用英文写、正文里根本没出现中文查询词的目录（实测：问「小鼠肺纤维化」，
                # 正文命中把一堆小鼠肝文件抬了上来，而 Mus_musculus/lung/fibrosis/ 一个都没进候选）。
                if species_variants or tissue_variants or direction_variants:
                    have = {r["file"] for r in results}
                    for root, _dirs, files in os.walk(kb_root):
                        for fname in files:
                            if not fname.endswith(('.yaml', '.yml', '.json', '.md')):
                                continue
                            try:
                                rel_path = str((Path(root) / fname).relative_to(kb_root))
                            except ValueError:
                                continue
                            if rel_path in have:
                                continue
                            rel_lower = rel_path.lower()
                            if species_variants and not any(sv.lower() in rel_lower for sv in species_variants):
                                continue
                            if tissue_variants and not any(tv.lower() in rel_lower for tv in tissue_variants):
                                continue
                            if direction_variants and not any(dv.lower() in rel_lower for dv in direction_variants):
                                continue
                            boost = _structured_boost(rel_path, species_variants, tissue_variants,
                                                      direction_variants, fname, queries)
                            content = _read_file_cached(Path(root) / fname) or ""
                            results.append({
                                "file": rel_path, "score": 50 + boost,
                                "matched_terms": [], "path_boost": boost,
                                "snippet": content[:1500]
                            })

                # Deduplicate and sort
                seen = {}
                for r in results:
                    key = r["file"]
                    if key not in seen or r["score"] > seen[key]["score"]:
                        seen[key] = r
                results = sorted(seen.values(), key=lambda x: x["score"], reverse=True)
                if include_details:
                    results = _enrich_hits(results, max_claims_per_hit, max_params_per_hit)
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

            # 路径优先匹配 — 如果指定了 species/tissue/direction，优先匹配路径（v5 权重见 _structured_boost）
            path_boost = _structured_boost(rel_path, species_variants, tissue_variants,
                                           direction_variants, fname, queries)

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
                # v6: 兜底路径同样应用「方法意图」乘子（论文卡在纯词频里也常靠篇幅霸榜）
                content_score = content_score * _intent_factor(fname, method_intent)
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
    if include_details:
        results = _enrich_hits(results, max_claims_per_hit, max_params_per_hit)

    return {"query": query, "species": species, "tissue": tissue, "direction": direction,
            "total": len(results), "results": results[:15]}


def _claim_terms(text: str) -> set:
    genes = {g.upper() for g in re.findall(r"\b[A-Z][A-Z0-9-]{2,}\b", text or "")}
    words = {w.lower() for w in re.findall(r"[A-Za-z]{4,}", text or "")
             if w.lower() not in {"with", "from", "that", "this", "were", "using", "into",
                                  "muscle", "cells", "cell", "nuclei", "mice", "human"}}
    return genes | words


def _conflict_candidates(claims: list, limit: int = 5) -> list:
    out = []
    for i in range(len(claims)):
        for j in range(i + 1, len(claims)):
            a, b = claims[i], claims[j]
            if a.get("text") == b.get("text"):
                continue
            if (a.get("source") or {}).get("doi") == (b.get("source") or {}).get("doi"):
                continue
            shared = _claim_terms(a.get("text", "")) & _claim_terms(b.get("text", ""))
            if len(shared) < 2:
                continue
            out.append({
                "a": {"claim_id": a.get("claim_id"), "text": a.get("text"),
                      "level": a.get("evidence_level"), "doi": (a.get("source") or {}).get("doi"),
                      "cohort": a.get("cohort"), "object": a.get("experimental_object")},
                "b": {"claim_id": b.get("claim_id"), "text": b.get("text"),
                      "level": b.get("evidence_level"), "doi": (b.get("source") or {}).get("doi"),
                      "cohort": b.get("cohort"), "object": b.get("experimental_object")},
                "shared_terms": sorted(shared)[:8],
                "note": "同主题不同来源：按 cohort/object/background 并列比较，不要合并成单一结论。",
            })
            if len(out) >= limit:
                return out
    return out


def search_knowledge(query: str, species: str = "", tissue: str = "", direction: str = "",
                     kind: str = "all", level: str = "", max_claims: int = 8,
                     max_parameters: int = 10) -> str:
    """Search KB and return citation-ready claims + parameters + conflict candidates."""
    kind = (kind or "all").strip().lower()
    if kind not in ("all", "claims", "parameters", "markers", "wet_lab", "organoids"):
        kind = "all"
    try:
        max_claims = max(1, min(20, int(max_claims)))
        max_parameters = max(1, min(30, int(max_parameters)))
    except Exception:
        max_claims, max_parameters = 8, 10

    result = _search_kb(query, species, tissue, direction, include_details=True,
                        max_claims_per_hit=4, max_params_per_hit=6)
    claims, params = [], []
    markers, wet, organoids = [], [], []
    for hit in result.get("results", []):
        claims.extend(hit.get("claims") or [])
        params.extend(hit.get("parameters") or [])
        markers.extend(hit.get("markers") or [])
        wet.extend(hit.get("wet_lab") or [])
        organoids.extend(hit.get("organoids") or [])
    # Dedupe claims across species-duplicated YAML entries.
    seen, uniq = set(), []
    for c in claims:
        key = (c.get("text", ""), (c.get("source") or {}).get("doi", ""))
        if key in seen:
            continue
        seen.add(key)
        if level and c.get("evidence_level") != level:
            continue
        uniq.append(c)
    order = {"L3": 3, "L2": 2, "L1": 1, "L0": 0}
    uniq.sort(key=lambda c: order.get(str(c.get("evidence_level")), 1), reverse=True)
    claims = uniq[:max_claims] if kind in ("all", "claims") else []
    if kind == "parameters":
        claims = []

    seen_p, uniq_p = set(), []
    for p in params:
        key = tuple(str(p.get(k, "")) for k in ("tool", "param", "value", "section", "source_file"))
        if key in seen_p:
            continue
        seen_p.add(key)
        uniq_p.append(p)
    params = uniq_p[:max_parameters] if kind in ("all", "parameters") else []

    _seen_m, _uniq_m = set(), []
    for m in markers:
        key = (m.get("gene"), m.get("cell_type"), m.get("source_file"))
        if key in _seen_m:
            continue
        _seen_m.add(key)
        _uniq_m.append(m)
    _seen_w, _uniq_w = set(), []
    for w in wet:
        key = (w.get("experiment"), w.get("model"), w.get("source_file"))
        if key in _seen_w:
            continue
        _seen_w.add(key)
        _uniq_w.append(w)
    _seen_o, _uniq_o = set(), []
    for o in organoids:
        key = (o.get("name"), o.get("tissue"), o.get("source_file"))
        if key in _seen_o:
            continue
        _seen_o.add(key)
        _uniq_o.append(o)
    result["claims"] = claims
    result["parameters"] = params
    result["markers"] = _uniq_m[:20] if kind in ("all", "markers") else []
    result["wet_lab"] = _uniq_w[:8] if kind in ("all", "wet_lab") else []
    result["organoids"] = _uniq_o[:8] if kind in ("all", "organoids") else []
    result["conflict_candidates"] = _conflict_candidates(claims) if claims else []
    result["claim_level_counts"] = {
        lv: sum(1 for c in claims if c.get("evidence_level") == lv)
        for lv in ("L3", "L2", "L1", "L0")
    }
    result["evidence_policy"] = (
        "KB claim 可直接作为论据，但引用时必须带 DOI/quote/locator，并写清 experimental_object、"
        "cohort 和 background；多篇结论冲突时并列呈现，不得合并或隐去队列差异。"
        "markers/wet_lab/organoids 是 source_only 方法证据，引用时写来源文件/图号。"
    )
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
                        # 2026-10-26 修复：五级目录下条目统一落在 <category>/<assay>/，
                        # 此前 01/02 用非递归 listdir → 子目录里的条目被数成 0
                        # （用户实测：已有 1 条生物学知识却显示缺）。统一递归计数。
                        _fs = sorted(str(f.relative_to(_cd)).replace("\\", "/")
                                     for f in Path(_cd).rglob("*")
                                     if f.is_file() and f.suffix.lower() in (".yaml", ".yml", ".md"))
                    found["categories"][_cat] = {"count": len(_fs), "sample": _fs[:6]}
                _md = os.path.join(_dir_base, "03_测序方法", _seg_assay)
                if os.path.isdir(_md):
                    _fs = sorted(str(f.relative_to(_md)).replace("\\", "/")
                                 for f in Path(_md).rglob("*")
                                 if f.is_file() and f.suffix.lower() in (".yaml", ".yml"))
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
                args.get("direction", ""),
                args.get("kind", "all"),
                args.get("level", ""),
                args.get("max_claims", 8),
                args.get("max_parameters", 10),
            ),
            emoji="📚",
            max_result_size_chars=60_000,
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
        pass  # 不在 MemOmics 环境中时不注册

_register()
