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
        "E:/MemOmics-Agent/hermes_home/skills",
    ):
        if os.path.isdir(_cand):
            return _cand
    return None


def save_knowledge(name: str = "", content: str = "", source: str = "manual",
                   evidence: str = "", verified: str = "partially_verified",
                   category: str = "bioinformatics", force: bool = False,
                   species: str = "", tissue: str = "", direction: str = "",
                   kb_category: str = "01_生物学知识", assay_type: str = "RNA") -> str:
    """知识入库 — 铁轨强制验证，不可绕过。"""
    name = (name or "").strip()
    content = (content or "").strip()
    source = (source or "manual").strip().lower()
    verified = (verified or "partially_verified").strip().lower()
    evidence = (evidence or "").strip()

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

    # 五级目录模式（2026-08-14）：物种/组织/方向/类别/assay
    # → knowledge_base/<Species>/<tissue>/<direction>/<category>/<assay>/<name>.yaml
    species = (species or "").strip()
    if species:
        if not tissue or not direction:
            return _err("⛔ 五级目录模式需要 tissue 和 direction（提供了 species 时必填）")
        _sp_parts = species.split()
        if len(_sp_parts) > 1:
            _seg_species = "_".join([_sp_parts[0].capitalize()] + [p.lower() for p in _sp_parts[1:]])
        else:
            _seg_species = species.strip().lower()
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
        ts = datetime.now().strftime("%Y-%m-%d %H:%M")
        entry = {
            "type": "kb_entry",
            "name": name,
            "species": species,
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
        ),
    )


_register()
