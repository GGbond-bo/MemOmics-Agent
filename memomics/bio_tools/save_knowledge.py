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
                "description": "KB category directory (default bioinformatics)",
                "default": "bioinformatics"
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
                   category: str = "bioinformatics", force: bool = False) -> str:
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
        handler=save_knowledge,
    )


_register()
