# -*- coding: utf-8 -*-
"""save_knowledge — 知识入库工具（铁轨验证，不可绕过）。

P1-8(2026-08-13)：docs/handoff-20260813.md — save_knowledge 工具缺失，
辩论门控的 _DEBATE_HIGH_IMPACT_TOOLS 引用了它但 agent 无法调用，入库铁轨无落点。

铁轨铁律（依据「知识库验证铁轨」设计）：
1. 任何知识条目入库必须有 evidence（引用原文/来源）
2. verified=unverified → 拒绝入库（force 仅限 bootstrap）
3. source=data_driven/domain_convention → 必须带 evidence，否则拒绝
4. 名称白名单（防路径穿越）
"""
import json
import os
import re
import logging
from datetime import datetime

try:
    import yaml
except ImportError:
    yaml = None

logger = logging.getLogger(__name__)

SCHEMA = {
    "name": "save_knowledge",
    "description": (
        "Save a verified knowledge entry into the MemOmics knowledge base "
        "(rail-enforced: evidence required, unverified entries rejected). "
        "Use this to persist paper findings, learned parameters, or analysis "
        "experience. All writes go through the verification rail and cannot "
        "be bypassed."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "description": "Entry name (a-z A-Z 0-9 _ . - only, <=64 chars). Becomes the .md filename."
            },
            "content": {
                "type": "string",
                "description": "Knowledge content (Markdown)."
            },
            "source": {
                "type": "string",
                "description": "Evidence source type: data_driven | domain_convention | manual | bootstrap",
                "default": "manual"
            },
            "evidence": {
                "type": "string",
                "description": "Evidence quote/reference supporting this entry. REQUIRED unless source=manual.",
                "default": ""
            },
            "verified": {
                "type": "string",
                "description": "Verification label: verified | partially_verified | unverified",
                "default": "partially_verified"
            },
            "category": {
                "type": "string",
                "description": "KB category directory (default bioinformatics). 兼容旧版平铺目录；提供 species 时忽略。"
            },
            "species": {
                "type": "string",
                "description": "物种（如 Homo sapiens / Mus musculus）。提供后按五级目录入库: 物种/组织/方向/类别/assay。"
            },
            "tissue": {
                "type": "string",
                "description": "组织（如 skeletal muscle）。五级目录模式必填（提供 species 时）。"
            },
            "direction": {
                "type": "string",
                "description": "方向（如 aging / development / disease）。五级目录模式必填。"
            },
            "kb_category": {
                "type": "string",
                "description": "知识库类别目录: 01_生物学知识 | 02_质控参数 | 03_测序方法（默认 01_生物学知识）"
            },
            "assay_type": {
                "type": "string",
                "description": "测序方法: RNA | ATAC | spatial | bulk（默认 RNA，仅 03_测序方法 下使用）",
                "default": "RNA"
            },
            "force": {
                "type": "boolean",
                "description": "Bootstrap override (bypasses evidence rail). FOR INITIALIZATION ONLY.",
                "default": False
            },
            "domain": {
                "type": "string",
                "enum": ["biology", "common", "chemistry"],
                "description": "知识域: biology=物种五级目录(默认); common=物种无关方法(跨物种生信知识); "
                               "chemistry=化学类文章(chemistry/<类别>/，类别用 direction 传: "
                               "compounds/pharmacology/reactions/reagents/conditions)",
                "default": "biology"
            }
        },
        "required": ["name", "content"]
    }
}

_SAFE_NAME_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_.\-]{0,63}$")
_SAFE_CATEGORY_RE = re.compile(r"^[a-zA-Z0-9_\-]{0,32}$")
# 五级目录模式的路径段白名单（2026-08-14）
_SAFE_PATH_SEG_RE = re.compile(r"^[a-zA-Z0-9_\u4e00-\u9fff\-]{1,64}$")
_KB_CATEGORIES = ("01_生物学知识", "02_质控参数", "03_测序方法", "04_个性化")
_KB_ASSAYS = ("RNA", "ATAC", "spatial", "bulk")
# 化学域类别（批O3 2026-08-16：化学类文章知识库）
_CHEM_CATEGORIES = ("compounds", "pharmacology", "reactions", "reagents", "conditions")

# 物种标准化：俗名/学名/中文 → 知识库标准目录名（批O3 2026-08-16）
# 与 kb_search.SYNONYMS 的检索变体兼容（human→Homo_sapiens、mouse→Mus_musculus、monkey→monkey）
_SPECIES_CANONICAL = {
    "human": "Homo_sapiens", "homo sapiens": "Homo_sapiens", "homo_sapiens": "Homo_sapiens",
    "智人": "Homo_sapiens", "人": "Homo_sapiens", "人类": "Homo_sapiens", "患者": "Homo_sapiens",
    "mouse": "Mus_musculus", "mus musculus": "Mus_musculus", "mus_musculus": "Mus_musculus",
    "小鼠": "Mus_musculus", "mice": "Mus_musculus",
    "rat": "rat", "rattus norvegicus": "rat", "rattus": "rat", "大鼠": "rat",
    "monkey": "monkey", "macaque": "monkey", "rhesus": "monkey", "cynomolgus": "monkey",
    "猕猴": "monkey", "食蟹猴": "monkey", "玻尾猴": "monkey",
    "zebrafish": "zebrafish", "danio rerio": "zebrafish", "danio": "zebrafish", "斑马鱼": "zebrafish",
    "drosophila": "drosophila", "drosophila melanogaster": "drosophila", "fly": "drosophila", "果蝇": "drosophila",
    "c.elegans": "c_elegans", "c. elegans": "c_elegans", "caenorhabditis elegans": "c_elegans",
    "worm": "c_elegans", "线虫": "c_elegans",
    "pig": "pig", "sus scrofa": "pig", "porcine": "pig", "猪": "pig",
    "rabbit": "rabbit", "oryctolagus cuniculus": "rabbit", "兔": "rabbit",
    "other": "other", "unknown": "other", "未提及": "other", "na": "other", "n/a": "other",
}


def canonical_species(name: str) -> str:
    """物种 → 知识库标准目录名（human→Homo_sapiens；未知→other）。

    多值（如 'human;mouse' / 'human, mouse'）只取第一个合法段。
    """
    raw = (name or "").strip()
    for seg in re.split(r"[;,，、/；|]", raw):
        seg = seg.strip()
        if not seg:
            continue
        key = seg.lower().replace("_", " ")
        canon = _SPECIES_CANONICAL.get(key)
        if canon:
            return canon
        canon = _SPECIES_CANONICAL.get(seg.lower())
        if canon:
            return canon
        # 学名形式 "Homo Sapiens" / 已有目录名直通（做基本规范化）
        if re.fullmatch(r"[A-Za-z]+ [a-z]+", seg) and not canon:
            return seg.replace(" ", "_").capitalize()
    return "other"


def _kb_root():
    """KB 根目录：MEMOMICS_KB_DIR → kb_search 推导 → hermes_home/skills。"""
    try:
        from memomics.bio_tools.kb_search import _find_kb_root
        root = _find_kb_root()
        if root is not None:
            return str(root)
    except Exception:
        pass
    env_dir = os.environ.get("MEMOMICS_KB_DIR")
    if env_dir and os.path.isdir(env_dir):
        return env_dir
    # 最后兜底：hermes_home/skills（agent 实际加载的技能目录）
    here = os.path.dirname(os.path.abspath(__file__))
    for _cand in (
        os.path.normpath(os.path.join(here, "..", "..", "hermes_home", "skills")),
        "MEMOMICS_HOME/hermes_home/skills",
    ):
        if os.path.isdir(_cand):
            return _cand
    return None


def save_knowledge(name: str = "", content: str = "", source: str = "manual",
                   evidence: str = "", verified: str = "partially_verified",
                   category: str = "bioinformatics", force: bool = False,
                   species: str = "", tissue: str = "", direction: str = "",
                   kb_category: str = "01_生物学知识", assay_type: str = "RNA",
                   domain: str = "biology") -> str:
    """知识入库 — 铁轨强制验证，不可绕过。

    domain（批O3 2026-08-16）:
      biology   默认。五级目录: <Species>/<tissue>/<direction>/<category>/<assay>/<name>.yaml
                （物种经 canonical_species 标准化，human→Homo_sapiens 等，不再产生重复目录）
      common    物种无关的方法/参数（跨物种文献的生信知识）:
                common/<direction|general>/<category>/<assay|na>/<name>.yaml
      chemistry 化学类文章: chemistry/<chem_category>/<name>.yaml
                chem_category 用 direction 传入 ∈ compounds/pharmacology/reactions/reagents/conditions
    """
    name = (name or "").strip()
    content = (content or "").strip()
    source = (source or "manual").strip().lower()
    verified = (verified or "partially_verified").strip().lower()
    evidence = (evidence or "").strip()
    domain = (domain or "biology").strip().lower()

    def _err(msg: str) -> str:
        return json.dumps({"status": "error", "error": msg}, ensure_ascii=False)

    # 铁轨 0: 名称白名单（防路径穿越）
    if not _SAFE_NAME_RE.match(name):
        return _err(f"⛔ 入库拒绝：非法名称 '{name}' — 仅允许字母/数字/_.-，不超过 64 字符")
    if not _SAFE_CATEGORY_RE.match(category):
        return _err(f"⛔ 入库拒绝：非法分类目录 '{category}'")
    if not content:
        return _err("⛔ 入库拒绝：content 为空")

    # 铁轨 1: unverified → 拒绝（force 仅限 bootstrap 初始化）
    if verified == "unverified" and not force:
        return _err("⛔ 入库拒绝：verified=unverified 的条目禁止入库（铁轨铁律）。"
                    "请补充验证后改为 verified/partially_verified，或确认后重试。")

    # 铁轨 2: data_driven/domain_convention → 必须带 evidence
    if source in ("data_driven", "domain_convention") and not evidence:
        return _err(f"⛔ 入库拒绝：source={source} 必须提供 evidence（引用原文/数据来源），"
                    "否则拒绝写入（铁轨铁律）。")

    root = _kb_root()
    if not root:
        return _err("⛔ 入库失败：知识库根目录未找到（MEMOMICS_KB_DIR 未设置且无默认路径）")

    ts = datetime.now().strftime("%Y-%m-%d %H:%M")

    # ── 化学域（批O3 2026-08-16）：chemistry/<类别>/<name>.yaml ──
    if domain == "chemistry":
        chem_cat = (direction or "compounds").strip().lower().replace(" ", "_")
        if chem_cat not in _CHEM_CATEGORIES:
            return _err(f"⛔ 入库拒绝：chemistry 域 direction(类别) 必须是 {_CHEM_CATEGORIES} 之一，"
                        f"收到 '{chem_cat}'")
        entry_dir = os.path.join(root, "chemistry", chem_cat)
        entry_path = os.path.join(entry_dir, f"{name}.yaml")
        entry = {
            "type": "kb_entry", "domain": "chemistry", "name": name,
            "chem_category": chem_cat, "last_updated": ts,
            "source": source, "verified": verified,
            "quality": "high" if verified == "verified" else "medium",
            "auto_trigger": [name], "content": content,
        }
        if evidence:
            entry["evidence"] = evidence
        if yaml is None:
            return _err("⛔ 入库失败：PyYAML 不可用，无法写 YAML 条目")
        try:
            os.makedirs(entry_dir, exist_ok=True)
            with open(entry_path, "w", encoding="utf-8") as f:
                yaml.safe_dump(entry, f, allow_unicode=True, sort_keys=False)
        except OSError as e:
            return _err(f"⛔ 入库失败：写入 {entry_path} 失败: {e}")
        logger.info("save_knowledge(chemistry): %s → %s", name, entry_path)
        return json.dumps({"status": "success", "path": entry_path, "name": name,
                           "verified": verified, "source": source, "mode": "chemistry_yaml"},
                          ensure_ascii=False)

    # ── 物种无关域（批O3 2026-08-16）：common/<direction|general>/<category>/<assay|na>/<name>.yaml ──
    if domain == "common":
        _seg_dir = (direction or "general").strip().lower().replace(" ", "_").replace("-", "_")
        _seg_cat = (kb_category or "03_测序方法").strip()
        _seg_assay = (assay_type or "na").strip().upper()
        for _seg in (_seg_dir, _seg_cat, _seg_assay):
            if not _SAFE_PATH_SEG_RE.match(_seg):
                return _err(f"⛔ 入库拒绝：路径段 '{_seg}' 非法（仅字母/数字/下划线/中文，≤64 字符）")
        if _seg_cat not in _KB_CATEGORIES:
            return _err(f"⛔ 入库拒绝：kb_category 必须是 {_KB_CATEGORIES} 之一，收到 '{_seg_cat}'")
        if _seg_assay not in _KB_ASSAYS + ("NA",):
            return _err(f"⛔ 入库拒绝：assay_type 必须是 {_KB_ASSAYS} 之一或 NA，收到 '{_seg_assay}'")
        entry_dir = os.path.join(root, "common", _seg_dir, _seg_cat, _seg_assay)
        entry_path = os.path.join(entry_dir, f"{name}.yaml")
        entry = {
            "type": "kb_entry", "domain": "common", "name": name,
            "direction": _seg_dir, "assay_type": _seg_assay, "last_updated": ts,
            "source": source, "verified": verified,
            "quality": "high" if verified == "verified" else "medium",
            "auto_trigger": [name], "content": content,
        }
        if evidence:
            entry["evidence"] = evidence
        if yaml is None:
            return _err("⛔ 入库失败：PyYAML 不可用，无法写 YAML 条目")
        try:
            os.makedirs(entry_dir, exist_ok=True)
            with open(entry_path, "w", encoding="utf-8") as f:
                yaml.safe_dump(entry, f, allow_unicode=True, sort_keys=False)
        except OSError as e:
            return _err(f"⛔ 入库失败：写入 {entry_path} 失败: {e}")
        logger.info("save_knowledge(common): %s → %s", name, entry_path)
        return json.dumps({"status": "success", "path": entry_path, "name": name,
                           "verified": verified, "source": source, "mode": "common_yaml"},
                          ensure_ascii=False)

    # 五级目录模式（2026-08-14；批O3 物种标准化）：
    # → knowledge_base/<Species>/<tissue>/<direction>/<category>/<assay>/<name>.yaml
    species = (species or "").strip()
    if species:
        if not tissue or not direction:
            return _err("⛔ 五级目录模式需要 tissue 和 direction（提供了 species 时必填）")
        _seg_species = canonical_species(species)
        _seg_tissue = tissue.strip().lower().replace(" ", "_").replace("-", "_")
        _seg_dir = direction.strip().lower().replace(" ", "_").replace("-", "_")
        _seg_cat = (kb_category or "01_生物学知识").strip()
        _seg_assay = (assay_type or "RNA").strip().upper()
        for _seg in (_seg_species, _seg_tissue, _seg_dir, _seg_cat, _seg_assay):
            if not _SAFE_PATH_SEG_RE.match(_seg):
                return _err(f"⛔ 入库拒绝：路径段 '{_seg}' 非法（仅字母/数字/下划线/中文，≤64 字符）")
        if _seg_cat not in _KB_CATEGORIES:
            return _err(f"⛔ 入库拒绝：kb_category 必须是 {_KB_CATEGORIES} 之一，收到 '{_seg_cat}'")
        if _seg_assay not in _KB_ASSAYS:
            return _err(f"⛔ 入库拒绝：assay_type 必须是 {_KB_ASSAYS} 之一，收到 '{_seg_assay}'")
        entry_dir = os.path.join(root, _seg_species, _seg_tissue, _seg_dir, _seg_cat, _seg_assay)
        entry_path = os.path.join(entry_dir, f"{name}.yaml")
        entry = {
            "type": "kb_entry",
            "name": name,
            "species": _seg_species,
            "tissue": tissue.strip(),
            "direction": direction.strip(),
            "assay_type": _seg_assay,
            "last_updated": ts,
            "source": source,
            "verified": verified,
            "quality": "high" if verified == "verified" else "medium",
            "auto_trigger": [name],
            "content": content,
        }
        if evidence:
            entry["evidence"] = evidence
        if yaml is None:
            return _err("⛔ 入库失败：PyYAML 不可用，无法写 YAML 条目")
        try:
            os.makedirs(entry_dir, exist_ok=True)
            with open(entry_path, "w", encoding="utf-8") as f:
                yaml.safe_dump(entry, f, allow_unicode=True, sort_keys=False)
        except OSError as e:
            return _err(f"⛔ 入库失败：写入 {entry_path} 失败: {e}")
        logger.info("save_knowledge(五级): %s → %s (source=%s, verified=%s)", name, entry_path, source, verified)
        return json.dumps({
            "status": "success", "path": entry_path, "name": name,
            "verified": verified, "source": source, "mode": "five_level_yaml",
        }, ensure_ascii=False)

    category_dir = os.path.join(root, category) if category else root
    try:
        os.makedirs(category_dir, exist_ok=True)
    except OSError as e:
        return _err(f"⛔ 入库失败：无法创建目录 {category_dir}: {e}")

    # 条目格式：md 文件（kb_search 扫描 .md），追加式（不覆盖已有知识）
    entry_path = os.path.join(category_dir, f"{name}.md")
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")
    header = (f"# {name}\n\n"
              f"> saved {ts} | source={source} | verified={verified}"
              f"{' | FORCE_BOOTSTRAP' if force else ''}\n\n")
    evidence_block = f"\n\n## Evidence\n\n{evidence}\n" if evidence else "\n"
    entry = header + content + evidence_block

    existing = ""
    if os.path.exists(entry_path):
        try:
            with open(entry_path, "r", encoding="utf-8") as f:
                existing = f.read()
        except OSError:
            pass
    if existing.strip():
        entry = existing.rstrip() + "\n\n---\n\n" + entry

    try:
        with open(entry_path, "w", encoding="utf-8") as f:
            f.write(entry)
    except OSError as e:
        return _err(f"⛔ 入库失败：写入 {entry_path} 失败: {e}")

    logger.info("save_knowledge: %s → %s (source=%s, verified=%s)", name, entry_path, source, verified)
    return json.dumps({
        "status": "success",
        "path": entry_path,
        "name": name,
        "verified": verified,
        "source": source,
        "appended": bool(existing.strip()),
    }, ensure_ascii=False)


def _register():
    from tools.registry import registry
    registry.register(
        name="save_knowledge",
        toolset="memomics",
        schema=SCHEMA,
        handler=lambda args, **kw: save_knowledge(
            args.get("name", ""),
            args.get("content", ""),
            args.get("source", "manual"),
            args.get("evidence", ""),
            args.get("verified", "partially_verified"),
            args.get("category", "bioinformatics"),
            args.get("force", False),
            args.get("species", ""),
            args.get("tissue", ""),
            args.get("direction", ""),
            args.get("kb_category", "01_生物学知识"),
            args.get("assay_type", "RNA"),
            args.get("domain", "biology"),
        ),
    )


_register()
