# -*- coding: utf-8 -*-
"""kb-evidence-v3 — claim-level evidence normalization and guardrails.

2026-11-05 分级口径变更（用户确认）：
    L0 = 无来源，或来源无法核实（无 DOI／DOI 核不上／找不到原文／quote 回查不上）
    L1 = 来源已核实（DOI + 原文 + quote 匹配 + 章节/图号可定位），尚无针对该结论的实验验证
    L2 = L1 + 原文有针对该结论的直接湿实验/功能验证
    L3 = L2 + 临床试验或足够规模的独立临床队列
要点：**核实是 L1 的门槛，不是可选项**；任何一环核不了 → 整条降 L0。
摘要级原文（fulltext=abstract）最高 L1；预印本封顶 L1；数据库注释只作线索（L0）。
本模块保持无第三方依赖，网络校验由调用方（source_verifier）完成后再注入。
"""
from __future__ import annotations

import os
import re
import unicodedata
from collections import Counter
from difflib import SequenceMatcher

STANDARD = "kb-evidence-v3"
LEVELS = {
    "L0": "无来源或来源无法核实（无 DOI／DOI 核不上／找不到原文／quote 回查不上）——只作线索，不得作为结论",
    "L1": "来源已核实：DOI 可核实 + 拿到原文（全文，或可定位的摘要段落）+ quote 在原文中匹配 + 章节/图号可定位；尚无针对该结论的实验验证",
    "L2": "在 L1 基础上，原文有针对该结论的直接湿实验/功能验证（IF/IHC/RNAscope/qPCR/流式/敲除/过表达/动物或细胞实验等）",
    "L3": "在 L2 基础上，临床试验或足够规模的独立临床队列验证（含 n 与终点）",
}
LEVEL_ORDER = {"L0": 0, "L1": 1, "L2": 2, "L3": 3}
# 原文可得性：full=全文，abstract=仅摘要/可定位摘要段落，none=没有原文
FULLTEXT_MODES = ("full", "abstract", "none")
# 来源类型对等级的硬上限（与「核实深度」正交）
SOURCE_TYPE_LEVEL_CAP = {
    "secondary": "L1",   # 综述/二手：可用来找原始文献，自身封顶 L1
    "preprint": "L1",    # 预印本：未经同行评审，封顶 L1
    "database": "L0",    # 数据库注释（CellMarker/PanglaoDB 等）：只作线索
}
# L0 内部再分类（2026-11-05 用户要求）：
#   「根本没查到」和「查到了、但原文说这是推测」不是一回事，报告里必须分开。
EVIDENCE_STATUS = {
    "supported": "来源已核实且支持该结论（L1 及以上）",
    "unsupported": "来源已核实，但原文对该结论只有推测/未来工作，无直接支持",
    "contradicted": "来源已核实，但原文给出相反结论",
    "unverified": "有来源线索（DOI/quote）但核实不上（DOI 不符/无原文/quote 回查不上/定位缺失）",
    "no_source": "没有任何来源（模型先验，或未给出处）",
}
VALID_EVIDENCE_TYPES = {"computational", "wet_lab", "clinical", "secondary", "speculation", "observational"}

# These must describe the assay used for THIS claim, not merely another assay in the paper.
WET_KEYWORDS = (
    "immunofluorescence", "immunohistochemistry", "immunostaining", "western blot",
    "western", "qpcr", "rt-qpcr", "elisa", "flow cytometry", "facs", "rnascope",
    "in situ hybridization", "fish", "dot blot", "histology", "histochemistry",
    "h&e", "cubic", "tissue clearing", "confocal", "edU", "edu incorporation",
    "3d imaging", "3d confocal", "three-dimensional imaging", "3d reconstruction",
    "whole-mount", "whole mount", "light sheet", "lightsheet", "electron microscopy",
    "knockout", "knockdown", "overexpression", "crispr", "organoid", "cell culture",
    "animal model", "mouse model", "in vivo", "diphtheria toxin", "dtr",
    "免疫荧光", "免疫组化", "免疫染色", "蛋白印迹", "western", "qpcr", "elisa",
    "流式", "rnascope", "原位杂交", "点印迹", "组织化学", "he染色", "h&e",
    "组织透明化", "共聚焦", "三维成像", "3d成像", "3d 成像", "三维重建",
    "全mount", "全组织成像", "光片", "电镜", "透射电镜", "扫描电镜",
    "edu", "敲除", "敲低", "过表达", "类器官",
    "细胞实验", "动物实验", "动物模型", "小鼠模型", "体内", "白喉毒素",
)
COMPUTATIONAL_KEYWORDS = (
    "snrna", "scrna", "single-nucleus", "single-cell", "umap", "pca", "tsne",
    "cellchat", "cellphonedb", "聚类", "cluster", "差异表达", "differential expression",
    "deg", "富集分析", "enrichment", "转录组", "transcriptome", "蛋白质组", "proteome",
    "空间转录组", "visium", "xenium", "bulk rna", "microarray", "计算", "预测",
    "correlation", "相关分析", "模型推断", "in silico",
)
CLINICAL_DESIGN_KEYWORDS = (
    "clinical trial", "randomized", "randomised", "prospective", "phase i", "phase ii",
    "phase iii", "multicenter", "multi-center", "clinical cohort", "patient cohort",
    "independent validation cohort", "independent cohort", "临床试验", "随机",
    "前瞻", "多中心", "临床队列", "患者队列", "独立验证队列", "独立队列",
)
SECONDARY_SOURCE_TYPES = {"secondary", "review", "meta_analysis", "meta-analysis", "综述", "二手"}
MAX_CLAIMS = 15
MAX_MARKERS = 20
MAX_WET_LAB = 8
MAX_ORGANOIDS = 8

TISSUE_CANONICAL = {
    "skeletal muscle": "skeletal_muscle", "skeletal_muscle": "skeletal_muscle",
    "示例组织": "skeletal_muscle", "肌肉": "skeletal_muscle", "muscle": "skeletal_muscle",
    "cardiac muscle": "cardiac_muscle", "cardiac_muscle": "cardiac_muscle", "心肌": "cardiac_muscle",
    "smooth muscle": "smooth_muscle", "smooth_muscle": "smooth_muscle", "平滑肌": "smooth_muscle",
    "liver": "liver", "肝": "liver", "肝脏": "liver", "hepatic": "liver",
    "brain": "brain", "脑": "brain", "大脑": "brain", "cortex": "brain", "皮层": "brain",
    "lung": "lung", "肺": "lung", "肺部": "lung", "pulmonary": "lung",
    "kidney": "kidney", "肾": "kidney", "肾脏": "kidney", "renal": "kidney",
    "heart": "heart", "心脏": "heart", "cardiac": "heart",
    "blood": "blood", "血液": "blood", "pbmc": "pbmc", "外周血": "pbmc",
    "bone marrow": "bone_marrow", "bone_marrow": "bone_marrow", "骨髓": "bone_marrow",
    "spleen": "spleen", "脾": "spleen", "脾脏": "spleen",
    "intestine": "intestine", "肠道": "intestine", "肠": "intestine", "colon": "colon", "结肠": "colon",
    "skin": "skin", "皮肤": "skin", "dermal": "skin",
    "adipose": "adipose", "fat": "adipose", "脂肪": "adipose",
    "pancreas": "pancreas", "胰腺": "pancreas", "pancreatic": "pancreas",
    "retina": "retina", "视网膜": "retina", "eye": "eye", "眼": "eye",
    "bladder": "bladder", "膀胱": "bladder",
    "uterus": "uterus", "子宫": "uterus", "endometrium": "uterus", "子宫内膜": "uterus",
    "prostate": "prostate", "前列腺": "prostate",
    "ovary": "ovary", "卵巢": "ovary", "testis": "testis", "睾丸": "testis",
    "thymus": "thymus", "胸腺": "thymus",
    "tumor": "tumor", "肿瘤": "tumor", "cancer": "tumor", "癌": "tumor",
    "other": "other", "unknown": "other", "未提及": "other", "n/a": "other",
}
MODEL_TYPES = {"in_vivo", "ex_vivo", "organoid", "cell_line", "primary_cells",
               "human_sample", "other"}

# Canonical biomedical species names used in YAML, retrieval and prompts.
SPECIES_CANONICAL = {
    "human": "Homo_sapiens", "人": "Homo_sapiens", "人类": "Homo_sapiens",
    "智人": "Homo_sapiens", "homo sapiens": "Homo_sapiens", "homo_sapiens": "Homo_sapiens",
    "mouse": "Mus_musculus", "小鼠": "Mus_musculus", "mice": "Mus_musculus",
    "mus musculus": "Mus_musculus", "mus_musculus": "Mus_musculus",
    "rat": "Rattus_norvegicus", "大鼠": "Rattus_norvegicus",
    "rattus norvegicus": "Rattus_norvegicus", "rattus_norvegicus": "Rattus_norvegicus",
    "monkey": "Macaca_mulatta", "macaque": "Macaca_mulatta", "猕猴": "Macaca_mulatta",
    "rhesus": "Macaca_mulatta", "macaca mulatta": "Macaca_mulatta",
    "cynomolgus": "Macaca_fascicularis", "食蟹猴": "Macaca_fascicularis",
    "macaca fascicularis": "Macaca_fascicularis",
    "zebrafish": "Danio_rerio", "斑马鱼": "Danio_rerio", "danio rerio": "Danio_rerio",
    "drosophila": "Drosophila_melanogaster", "果蝇": "Drosophila_melanogaster",
    "drosophila melanogaster": "Drosophila_melanogaster",
    "c. elegans": "Caenorhabditis_elegans", "线虫": "Caenorhabditis_elegans",
    "caenorhabditis elegans": "Caenorhabditis_elegans",
    "pig": "Sus_scrofa", "猪": "Sus_scrofa", "sus scrofa": "Sus_scrofa",
    "rabbit": "Oryctolagus_cuniculus", "兔": "Oryctolagus_cuniculus",
    "oryctolagus cuniculus": "Oryctolagus_cuniculus",
}
# Conservative default; a small case series must not become "clinical-grade" L3.
L3_MIN_TOTAL_N = max(1, int(os.environ.get("MEMOMICS_L3_MIN_N", "100") or "100"))


def _text(value) -> str:
    return str(value or "").strip()


def canonical_tissue(value) -> str:
    """Canonical tissue name used in KB paths and claims (skeletal_muscle, liver, ...)."""
    s = _text(value)
    if not s:
        return "other"
    key = s.lower().replace("-", " ").replace("_", " ").strip()
    if key in TISSUE_CANONICAL:
        return TISSUE_CANONICAL[key]
    key2 = s.lower().replace(" ", "_").replace("-", "_").strip()
    if key2 in TISSUE_CANONICAL:
        return TISSUE_CANONICAL[key2]
    # Infer from a free-text object such as "mouse plantaris muscle".
    low = " " + key + " "
    for token, name in sorted(TISSUE_CANONICAL.items(), key=lambda kv: -len(kv[0])):
        if f" {token} " in low or token in key:
            return name
    if any(t in key for t in ("musc", "myo", "sarcomere", "plantaris", "soleus",
                              "gastrocnemius", "tibialis", "nmj", "synm", "schwann")):
        return "skeletal_muscle"
    return "other"


def canonical_model_type(value) -> str:
    s = _text(value).lower().replace("-", "_").replace(" ", "_")
    return s if s in MODEL_TYPES else "other"


def normalize_species_list(value) -> list:
    """Return canonical biomedical species names (Homo_sapiens, Mus_musculus, ...)."""
    raw = value if isinstance(value, (list, tuple, set)) else re.split(r"[;,，、/；|]", str(value or ""))
    out = []
    for item in raw:
        s = _text(item)
        if not s:
            continue
        key = s.lower().replace("_", " ")
        canon = SPECIES_CANONICAL.get(key) or SPECIES_CANONICAL.get(s.lower())
        if not canon:
            # Infer from a free-text object such as "mouse plantaris muscle".
            low = s.lower()
            for token, name in sorted(SPECIES_CANONICAL.items(), key=lambda kv: -len(kv[0])):
                if token in low:
                    canon = name
                    break
        if canon and canon not in out:
            out.append(canon)
    return out


def _canonical(text: str) -> str:
    s = unicodedata.normalize("NFKC", _text(text))
    s = (s.replace("“", '"').replace("”", '"').replace("‘", "'").replace("’", "'")
         .replace("–", "-").replace("—", "-").replace("−", "-"))
    s = re.sub(r"\r\n?", "\n", s)
    s = re.sub(r"(?im)^\s*(?:page\s+\d+|author manuscript|dev cell\. author manuscript;.*|"
               r"campanario et al\.)\s*$", "", s)
    s = re.sub(r"\s+", " ", s)
    # PDF/MD line-break hyphenation and hyphenation variants.
    s = re.sub(r"(?<=[A-Za-z])-\s+(?=[A-Za-z])", "", s)
    s = re.sub(r"(?<=[A-Za-z])-(?=[A-Za-z])", "", s)
    return s.strip().lower()


def quote_match(quote: str, source_text: str) -> tuple[bool, float]:
    """Return (matched, best_similarity). Exact normalized match first, then 0.92 fuzzy."""
    q = _canonical(quote)
    if not q or not source_text:
        return False, 0.0
    src = _canonical(source_text)
    if q in src:
        return True, 1.0
    lines = [ln for ln in _text(source_text).splitlines() if ln.strip()]
    best = 0.0
    # Sliding windows tolerate page headers and line wrapping; exact match is preferred.
    for i in range(0, len(lines), 4):
        window = _canonical(" ".join(lines[i:i + 8]))
        if not window:
            continue
        ratio = SequenceMatcher(None, q, window).ratio()
        if ratio > best:
            best = ratio
        if best >= 0.92:
            return True, best
    return best >= 0.92, best


def normalize_level(value, default: str = "L0") -> str:
    """未知/缺失等级一律 L0（2026-11-05：不能因为模型没说清就默认 L1）。"""
    s = _text(value).upper()
    if s in LEVEL_ORDER:
        return s
    m = re.search(r"L\s*([0-3])", s)
    return f"L{m.group(1)}" if m else default


def _is_true(value) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "yes", "y", "是", "已"}


def _present(value) -> bool:
    s = _text(value)
    return bool(s) and s.lower() not in {"none", "null", "n/a", "na", "-", "—"}


def _contains(blob: str, words) -> bool:
    low = (blob or "").lower()
    return any(w.lower() in low for w in words)


def validation_text(item: dict) -> str:
    """Compatibility helper: old entries store validation as a string."""
    v = (item or {}).get("validation")
    if isinstance(v, dict):
        return _text(v.get("method"))
    return _text(v)


def validation_locator(item: dict) -> str:
    v = (item or {}).get("validation")
    if isinstance(v, dict):
        return _text(v.get("locator"))
    return _text((item or {}).get("validation_locator"))


def _cohort_n(text: str) -> int:
    s = _text(text)
    vals = [int(x) for x in re.findall(r"\bn\s*[=:]\s*(\d{1,7})", s, re.I)]
    if not vals:
        vals = [int(x) for x in re.findall(
            r"(\d{1,7})\s*(?:patients?|participants?|subjects?|cases?|例|人|名)", s, re.I)]
    return max(vals or [0])


def _locator_ok(value: str) -> bool:
    s = _text(value)
    if not s:
        return False
    if re.search(r"(summary|abstract|etoc|highlights?|graphical abstract)", s, re.I) \
            and not re.search(r"(fig(?:ure)?|table|results?|p\.?\s*\d|page\s*\d|图\s*\d|表\s*\d)",
                              s, re.I):
        return False
    return bool(re.search(
        r"(fig(?:ure)?|table|supplement|results?|methods?|discussion|abstract|summary|"
        r"p\.?\s*\d|page\s*\d|第\s*\d+\s*[段节]|图\s*\d|表\s*\d|L\d+)", s, re.I))


_DOI_PLACEHOLDERS = {"原文未报告", "未报告", "not reported", "n/a", "na", "none",
                     "unknown", "—", "-", "无", "未提供"}


def _clean_doi(value) -> str:
    doi = _text(value)
    if doi.lower() in _DOI_PLACEHOLDERS or "未报告" in doi:
        return ""
    return doi


def _normalize_source(raw: dict) -> dict:
    src = raw.get("source") if isinstance(raw.get("source"), dict) else {}
    stype = _text(src.get("type") or src.get("source_type") or raw.get("source_type")
                  or raw.get("study_type") or "primary").lower()
    if stype in SECONDARY_SOURCE_TYPES or "review" in stype or "综述" in stype:
        stype = "secondary"
    elif "preprint" in stype or "biorxiv" in stype or "medrxiv" in stype or "预印本" in stype:
        stype = "preprint"
    elif ("database" in stype or "数据库" in stype or "cellmarker" in stype
          or "panglao" in stype or "annotation" in stype):
        stype = "database"
    elif stype not in {"primary", "secondary"}:
        stype = "primary"
    return {
        "doi": _clean_doi(src.get("doi") or raw.get("doi")),
        "locator": _text(src.get("locator") or raw.get("locator")),
        "quote": _text(src.get("quote") or raw.get("quote")),
        "type": stype,
    }


def _normalize_verification(raw: dict, source: dict, source_text: str,
                            expected_doi: str = "", fulltext: str = "") -> dict:
    """来源可核实性校验 —— 决定这条证据能不能进 L1。

    2026-11-05（用户口径）：L1 = 核实到文献、找到原文。
    只有同时满足以下四条才算「已核实」：
      1) 有原文（full 或 abstract；没有 source_text 且没声明 → none）
      2) quote 能在原文里逐字回查（允许页眉/换行噪声）
      3) 章节/图号可定位
      4) DOI 不自相矛盾（给了 expected_doi 时必须一致；显式 doi_resolved=false 直接否）
    任一不满足 → 该条证据只能是 L0。
    """
    v = raw.get("verification") if isinstance(raw.get("verification"), dict) else {}
    mode = _text(v.get("fulltext") or fulltext or raw.get("fulltext")).lower().strip()
    if not mode:
        mode = "full" if _text(source_text) else "none"
    if mode not in FULLTEXT_MODES:
        mode = "none"

    quote_ok = None
    quote_ratio = 0.0
    if mode != "none" and _text(source_text):
        if source.get("quote"):
            ok, ratio = quote_match(source.get("quote"), source_text)
            quote_ok, quote_ratio = bool(ok), float(ratio or 0.0)
        else:
            quote_ok = False

    loc_ok = bool(source.get("locator")) and _locator_ok(source.get("locator"))

    doi_given = _text(source.get("doi"))
    doi_match = None
    if expected_doi and doi_given:
        doi_match = doi_given.lower().strip() == _text(expected_doi).lower().strip()
    elif doi_given:
        # 未给「本文 DOI」时只要求 DOI 存在；能否解析由上层 source_verifier 判定
        doi_match = True
    else:
        doi_match = False

    doi_resolved = _is_true(v.get("doi_resolved")) if "doi_resolved" in v else None
    # 幂等：再次归一化一条已经归一化过的 claim（没有新的原文可比）时，
    # 沿用上一次的核实结论，不能因为「这次没传 source_text」就把它打到 L0。
    if not _text(source_text) and v.get("verified") is not None:
        verified = _is_true(v.get("verified"))
        if v.get("quote_matched") is not None:
            quote_ok = bool(_is_true(v.get("quote_matched")))
    else:
        verified = bool(
            mode != "none"
            and quote_ok is True
            and loc_ok
            and doi_match is not False
            and doi_resolved is not False
        )
    return {
        "verified": verified,
        "fulltext": mode,
        "quote_matched": quote_ok,
        "quote_ratio": round(float(quote_ratio or 0.0), 3),
        "locator_ok": loc_ok,
        "doi_present": bool(doi_given),
        "doi_match": doi_match,
        "doi_resolved": doi_resolved,
    }


def _normalize_validation(raw: dict) -> dict:
    v = raw.get("validation")
    if isinstance(v, dict):
        method = _text(v.get("method"))
        locator = _text(v.get("locator"))
        if "claim_specific" in v:
            claim_specific = _is_true(v.get("claim_specific"))
        else:
            # Compatibility with older rich validation objects: only an explicit
            # independent=true can stand in for the new claim_specific flag.
            # Legacy validation strings still fail (the original L2 bug).
            claim_specific = _is_true(v.get("independent"))
        design = _text(v.get("design") or raw.get("validation_design"))
    else:
        method = _text(v)
        locator = _text(raw.get("validation_locator"))
        claim_specific = _is_true(raw.get("validation_claim_specific"))
        design = _text(raw.get("validation_design"))
    return {"method": method, "locator": locator,
            "claim_specific": claim_specific, "design": design}


def _infer_evidence_type(level: str, source: dict, validation: dict, raw: dict) -> str:
    given = _text(raw.get("evidence_type") or raw.get("type")).lower()
    if given in VALID_EVIDENCE_TYPES:
        return given
    if source["type"] == "secondary":
        return "secondary"
    blob = " ".join((validation.get("method", ""), validation.get("design", ""),
                     _text(raw.get("text"))))
    if _contains(validation.get("design", ""), CLINICAL_DESIGN_KEYWORDS):
        return "clinical"
    if _contains(validation.get("method", ""), WET_KEYWORDS):
        return "wet_lab"
    if _contains(blob, COMPUTATIONAL_KEYWORDS):
        return "computational"
    return "speculation" if level == "L0" else "observational"


def _cap(level: str, cap: str) -> str:
    return level if LEVEL_ORDER[level] <= LEVEL_ORDER[cap] else cap


def _classify_evidence_status(ver: dict, level: str, raw: dict, source: dict):
    """把 L0 再拆成 no_source / unverified / unsupported / contradicted。

    - contradicted：原文核实过，但结论相反（LLM 显式标 contradicted 或 evidence_status）
    - no_source   ：连线索都没有（纯先验）
    - unverified  ：有 DOI/quote 线索，但核不上
    - unsupported ：核实通过，但原文对这条结论只有推测/未来工作
    - supported   ：核实通过且支持（L1+）
    """
    explicit = _text(raw.get("evidence_status")).lower()
    if _is_true(raw.get("contradicted")) or explicit in ("contradicted", "contradicts", "against"):
        return "contradicted", "原文给出相反结论"
    if not ver.get("verified"):
        has_lead = bool(ver.get("doi_present") or source.get("quote"))
        if has_lead:
            return "unverified", "有来源线索但核实不上（DOI/原文/quote/定位）"
        return "no_source", "没有任何来源（模型先验或未给出处）"
    if level == "L0":
        return "unsupported", "来源已核实，但原文对该结论只有推测/未来工作，无直接支持"
    return "supported", ""


def normalize_conclusion(raw, index: int = 1, source_text: str = "",
                         expected_doi: str = "", fulltext: str = "") -> dict:
    """Normalize one LLM claim and apply claim-specific evidence guardrails."""
    if isinstance(raw, str):
        raw = {"text": raw}
    if not isinstance(raw, dict):
        raw = {"text": str(raw)}
    source = _normalize_source(raw)
    validation = _normalize_validation(raw)
    level = normalize_level(raw.get("evidence_level") or raw.get("level"))
    evidence_type = _infer_evidence_type(level, source, validation, raw)
    text = _text(raw.get("text") or raw.get("claim") or raw.get("conclusion"))
    assay = _text(raw.get("assay") or raw.get("sequencing_method") or raw.get("method"))
    obj = _text(raw.get("experimental_object") or raw.get("object") or raw.get("model"))
    cohort = _text(raw.get("cohort") or raw.get("cohorts") or raw.get("sample"))
    background = _text(raw.get("background") or raw.get("context"))
    species = normalize_species_list(raw.get("species") or [obj, cohort])
    tissue = canonical_tissue(raw.get("tissue") or obj)
    if expected_doi and not source["doi"]:
        source["doi"] = expected_doi

    reasons = []
    review = bool(raw.get("review_required"))
    if raw.get("level_cap_reason"):
        reasons.append(_text(raw.get("level_cap_reason")))

    # 2026-11-05（用户口径）：核不了来源 → 一律 L0；L1 起必须「来源已核实」。
    ver = _normalize_verification(raw, source, source_text, expected_doi, fulltext)
    source_verified = bool(ver["verified"])
    if not source_verified:
        if ver["fulltext"] == "none":
            reasons.append("无原文可核实（fulltext=none）")
        elif ver["quote_matched"] is False:
            reasons.append(f"缺 quote 或 quote 未在原文匹配（best={ver['quote_ratio']:.2f}）")
        elif not ver["locator_ok"]:
            reasons.append("缺可定位的章节/图号")
        if ver["doi_match"] is False:
            reasons.append("source DOI 与本文不一致")
        review = True
        level = "L0"
    elif level in ("L2", "L3") and ver["fulltext"] != "full":
        reasons.append("仅摘要级原文：L2 需全文")
        review = True
        level = _cap(level, "L1")

    missing = []
    for label, value in (("assay", assay), ("experimental_object", obj),
                         ("cohort", cohort), ("background", background)):
        if not _present(value):
            missing.append(label)
    if missing:
        reasons.append("缺上下文: " + ",".join(missing))
        review = True
        if level in ("L2", "L3"):
            level = _cap(level, "L1")

    if source["type"] == "secondary" and level in ("L2", "L3"):
        reasons.append("二手/综述来源最高 L1")
        review = True
        level = "L1"

    # 来源类型的硬上限（预印本 L1、数据库 L0）——与「核实深度」正交。
    _type_cap = SOURCE_TYPE_LEVEL_CAP.get(source["type"])
    if _type_cap and LEVEL_ORDER[level] > LEVEL_ORDER[_type_cap]:
        if source["type"] == "preprint":
            reasons.append("预印本未经同行评审，最高 L1")
        elif source["type"] == "database":
            reasons.append("数据库注释只作线索（不算证据）")
        review = True
        level = _cap(level, _type_cap)

    # L2: claim-specific wet/clinical validation only. A paper-level wet assay
    # or an unrelated RNAscope validation must not promote this claim.
    if level == "L2":
        wet = _contains(validation["method"], WET_KEYWORDS)
        if evidence_type not in ("wet_lab", "clinical"):
            reasons.append("evidence_type 不是湿实验/临床")
            level = "L1"
        elif not wet:
            reasons.append("validation 未写针对该结论的湿实验")
            level = "L1"
        elif not validation["claim_specific"]:
            reasons.append("validation 未声明 claim_specific")
            level = "L1"
        elif not validation["locator"]:
            reasons.append("validation 缺图号/定位")
            level = "L1"
        if level == "L1":
            review = True

    # L3: clinical trial/independent clinical cohort, reported n >= threshold.
    if level == "L3":
        design = validation["design"] or validation["method"]
        clinical = _contains(design, CLINICAL_DESIGN_KEYWORDS)
        n = _cohort_n(cohort)
        if evidence_type != "clinical":
            reasons.append("L3 的 evidence_type 不是 clinical")
            level = "L2"
        elif not clinical:
            reasons.append("L3 无临床试验/前瞻/独立临床队列设计")
            level = "L2"
        elif n < L3_MIN_TOTAL_N:
            reasons.append(f"L3 临床样本量不足（解析 n={n}, 阈值={L3_MIN_TOTAL_N}）")
            level = "L2"
        if level == "L2":
            # Re-run the L2 gate after L3 downgrade; the old code skipped this.
            if (evidence_type not in ("wet_lab", "clinical")
                    or not _contains(validation["method"], WET_KEYWORDS)
                    or not validation["claim_specific"] or not validation["locator"]):
                reasons.append("L3 降级后也不满足 L2")
                level = "L1"
            review = True

    if not _text(raw.get("grading_reason")):
        reasons.append("缺分级理由")
        review = True

    # Only claims whose quote/context/locator are verifiable may enter the formal KB.
    # Review-only claims stay in the index/human report but must not pollute retrieval.
    kb_eligible = bool(
        source_verified is True
        and not missing
        and source["locator"]
        and _locator_ok(source["locator"])
        and text
    )

    # L0 内部再分类：查不到 / 核不了 / 查到但不支持 / 查到但相反。
    ev_status, status_reason = _classify_evidence_status(ver, level, raw, source)

    return {
        "id": _text(raw.get("id")) or f"C{index:02d}",
        "text": text,
        "evidence_level": level,
        "evidence_status": ev_status,
        "status_reason": status_reason,
        "source": source,
        "species": species,
        "tissue": tissue,
        "assay": assay,
        "experimental_object": obj,
        "cohort": cohort,
        "background": background,
        "validation": validation,
        "evidence_type": evidence_type,
        "grading_reason": _text(raw.get("grading_reason")),
        "source_verified": source_verified,
        "verification": ver,
        "review_required": bool(review),
        "kb_eligible": kb_eligible,
        "level_cap_reason": "；".join(reasons),
        # Compatibility aliases for existing UI/renderers.
        "locator": source["locator"],
        "quote": source["quote"],
    }


def normalize_marker(raw, index: int = 1, expected_doi: str = "") -> dict:
    """Normalize an annotated marker (gene -> cell type/region) from Results."""
    if not isinstance(raw, dict):
        raw = {"gene": str(raw)}
    src = _normalize_source(raw)
    if expected_doi and not src["doi"]:
        src["doi"] = expected_doi
    return {
        "id": _text(raw.get("id")) or f"M{index:02d}",
        "gene": _text(raw.get("gene") or raw.get("marker")),
        "cell_type": _text(raw.get("cell_type") or raw.get("region") or raw.get("population")),
        "direction": _text(raw.get("direction") or "na").lower(),
        "assay": _text(raw.get("assay") or raw.get("method")),
        "context": _text(raw.get("context") or raw.get("note")),
        "species": normalize_species_list(raw.get("species") or [
            raw.get("model"), raw.get("experimental_object"), raw.get("context"),
            src.get("quote")]),
        "source": src,
    }


def normalize_wet_lab(raw, index: int = 1, expected_doi: str = "") -> dict:
    """Normalize wet-lab conditions/reagents/readout for experimental papers."""
    if not isinstance(raw, dict):
        raw = {"experiment": str(raw)}
    src = _normalize_source(raw)
    if expected_doi and not src["doi"]:
        src["doi"] = expected_doi
    reagents = []
    for r in raw.get("reagents") or []:
        if isinstance(r, str):
            r = {"name": r}
        if not isinstance(r, dict):
            continue
        reagents.append({
            "name": _text(r.get("name") or r.get("reagent")),
            "vendor": _text(r.get("vendor") or r.get("source")),
            "catalog": _text(r.get("catalog") or r.get("cat_no")),
            "dose": _text(r.get("dose") or r.get("concentration") or r.get("dilution")),
        })
        if len(reagents) >= 12:
            break
    return {
        "id": _text(raw.get("id")) or f"W{index:02d}",
        "experiment": _text(raw.get("experiment") or raw.get("assay")),
        "model": _text(raw.get("model") or raw.get("experimental_object")),
        "conditions": _text(raw.get("conditions") or raw.get("groups")),
        "species": normalize_species_list(raw.get("species") or [
            raw.get("model"), raw.get("experimental_object"), src.get("quote")]),
        "reagents": reagents,
        "readout": _text(raw.get("readout") or raw.get("measurement")),
        "n": _text(raw.get("n") or raw.get("cohort")),
        "source": src,
    }


def normalize_organoid(raw, index: int = 1, expected_doi: str = "") -> dict:
    """Normalize organoid/3D culture conditions with canonical species/tissue."""
    if not isinstance(raw, dict):
        raw = {"name": str(raw)}
    src = _normalize_source(raw)
    if expected_doi and not src["doi"]:
        src["doi"] = expected_doi
    cytokines = []
    for x in raw.get("cytokines") or raw.get("growth_factors") or []:
        s = _text(x)
        if s and s not in cytokines:
            cytokines.append(s)
    return {
        "id": _text(raw.get("id")) or f"O{index:02d}",
        "name": _text(raw.get("name") or raw.get("organoid")),
        "species": normalize_species_list(raw.get("species") or [raw.get("model")]),
        "tissue": canonical_tissue(raw.get("tissue") or raw.get("source_tissue") or raw.get("name")),
        "model_type": canonical_model_type(raw.get("model_type") or "organoid"),
        "media": _text(raw.get("media") or raw.get("medium")),
        "cytokines": cytokines[:15],
        "matrix": _text(raw.get("matrix") or raw.get("ecm")),
        "duration": _text(raw.get("duration") or raw.get("culture_time")),
        "passage": _text(raw.get("passage") or raw.get("p")),
        "readout": _text(raw.get("readout") or raw.get("assay")),
        "source": src,
    }


def normalize_knowledge_evidence(knowledge: dict, source_text: str = "",
                                 expected_doi: str = "", fulltext: str = "",
                                 doi_resolved=None) -> dict:
    """Normalize/dedupe/cap conclusions and apply the strict L0-L3 guardrails.

    doi_resolved: 联网核实的结果（True/False/None），由 source_verifier 提供；
        注入到没有自带 verification 的 claim 上。None = 未核实（不等于通过）。
    """
    if not isinstance(knowledge, dict) or "biology" not in knowledge:
        return knowledge
    bio = knowledge.get("biology") or {}
    if not isinstance(bio, dict):
        return knowledge
    out, seen = [], set()
    for idx, raw in enumerate(bio.get("conclusions") or [], 1):
        if doi_resolved is not None and isinstance(raw, dict):
            _v = raw.get("verification") if isinstance(raw.get("verification"), dict) else {}
            if "doi_resolved" not in _v:
                raw = dict(raw)
                _v = dict(_v)
                _v["doi_resolved"] = bool(doi_resolved)
                raw["verification"] = _v
        c = normalize_conclusion(raw, index=idx, source_text=source_text,
                                 expected_doi=expected_doi, fulltext=fulltext)
        if not c["text"]:
            continue
        key = re.sub(r"[\W_]+", "", c["text"].lower())
        if key in seen:
            continue
        seen.add(key)
        out.append(c)
        if len(out) >= 200:  # hard safety cap before ranking
            break
    # Keep the highest-value claims when a paper yields more than MAX_CLAIMS.
    # Otherwise early Results sections fill the quota and later RNAscope/clinical
    # L2 evidence is silently dropped.
    out.sort(key=lambda c: (
        LEVEL_ORDER.get(c.get("evidence_level"), 1),
        c.get("source_verified") is True,
        c.get("kb_eligible") is True,
    ), reverse=True)
    out = out[:MAX_CLAIMS]
    for i, c in enumerate(out, 1):
        c["id"] = f"C{i:02d}"
    bio["conclusions"] = out

    markers, seen_m = [], set()
    for i, raw in enumerate(bio.get("markers") or [], 1):
        m = normalize_marker(raw, index=i, expected_doi=expected_doi)
        if not m["gene"]:
            continue
        key = (m["gene"].upper(), m["cell_type"].lower())
        if key in seen_m:
            continue
        seen_m.add(key)
        markers.append(m)
        if len(markers) >= MAX_MARKERS:
            break
    bio["markers"] = markers

    wet, seen_w = [], set()
    for i, raw in enumerate(bio.get("wet_lab") or [], 1):
        w = normalize_wet_lab(raw, index=i, expected_doi=expected_doi)
        if not w["experiment"]:
            continue
        key = (w["experiment"].lower(), w["model"].lower())
        if key in seen_w:
            continue
        seen_w.add(key)
        wet.append(w)
        if len(wet) >= MAX_WET_LAB:
            break
    bio["wet_lab"] = wet

    organoids, seen_o = [], set()
    for i, raw in enumerate(bio.get("organoids") or [], 1):
        o = normalize_organoid(raw, index=i, expected_doi=expected_doi)
        if not o["name"]:
            continue
        key = (o["name"].lower(), o["tissue"], tuple(o["species"]))
        if key in seen_o:
            continue
        seen_o.add(key)
        organoids.append(o)
        if len(organoids) >= MAX_ORGANOIDS:
            break
    bio["organoids"] = organoids

    knowledge["biology"] = bio
    return knowledge


def evidence_chain_stats(knowledge: dict) -> dict:
    """Aggregate claim-level levels and verification status for the YAML header."""
    bio = (knowledge or {}).get("biology") or {}
    dist = {"L0": 0, "L1": 0, "L2": 0, "L3": 0}
    verified = review = eligible = 0
    for c in bio.get("conclusions") or []:
        if not isinstance(c, dict):
            continue
        dist[normalize_level(c.get("evidence_level"))] += 1
        if c.get("source_verified") is True:
            verified += 1
        if c.get("review_required") is True:
            review += 1
        if c.get("kb_eligible") is True:
            eligible += 1
    max_lv = "L0"
    for lv in ("L3", "L2", "L1"):
        if dist[lv]:
            max_lv = lv
            break
    return {
        "standard": STANDARD,
        "level_distribution": dist,
        "max_level": max_lv,
        "graded_conclusions": sum(dist.values()),
        "source_verified": verified,
        "review_required": review,
        "kb_eligible": eligible,
        "markers": len(bio.get("markers") or []),
        "wet_lab": len(bio.get("wet_lab") or []),
        "organoids": len(bio.get("organoids") or []),
        "level_meaning": LEVELS,
    }
