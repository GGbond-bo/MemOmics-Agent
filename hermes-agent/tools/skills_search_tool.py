# -*- coding: utf-8 -*-
"""skill_search / skill_list_by_domain：把 MemOmics 的 406 条技能索引变成可检索工具。

背景（2026-11-06 实测）：MemOmics 的提示词在至少 15 处要求模型“先调用
skill_search 找到合适的 skill”，但运行时注册表里从来没有这两个工具（121 个
工具中只有 skills_list / skill_view / skill_manage / skill_evolution）。模型照
提示词去调，只会拿到 unknown tool，然后退回 skills_list 全量 406 条 dump 或干脆
不用技能——这是「技能触发不了」最主要的断点之一。

实现：真正的检索在 memomics.skill_router（与 webui 候选注入共用同一套打分），
本模块只负责 schema、参数校验和 JSON 返回。两个工具都挂在 skills 工具集下，
并用 check_fn 在“没有 MemOmics 索引”的环境里隐藏，避免污染其他发行版。
"""
from __future__ import annotations

import json
import logging
import os

from tools.registry import registry

logger = logging.getLogger("tools.skills_search")


def _index_available() -> bool:
    """索引存在才暴露工具：没有 MemOmics 技能库的环境不需要它们。"""
    try:
        from memomics.skill_router import index_path

        return os.path.isfile(index_path())
    except Exception:
        return False


def _router():
    from memomics import skill_router

    return skill_router


SKILL_SEARCH_SCHEMA = {
    "name": "skill_search",
    "description": (
        "Search the local skill library (406 indexed skills) by natural-language need. "
        "Use this FIRST when you are unsure which skill covers a task, or when the user's "
        "phrasing is colloquial/Chinese. Returns ranked candidates with the matched evidence "
        "(name/trigger keyword/use-case), then load the chosen one with skill_view(name)."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "用户需求原话或领域术语，例如 '差异表达分析'、'细胞类型注释'、'批次校正'、'审稿'",
            },
            "top_k": {
                "type": "integer",
                "description": "返回条数，默认 8，最大 30",
            },
            "level": {
                "type": "string",
                "description": "只看某级别：RED / YEL / GRN，留空=全部",
            },
            "domain": {
                "type": "string",
                "description": "可选领域过滤词（如 'RNA'、'文献'、'figure'），命中名称/触发词/场景才保留",
            },
            "stage": {
                "type": "string",
                "description": "（已弃用，仅为兼容旧提示词保留）分析阶段提示，当前忽略",
            },
        },
        "required": ["query"],
    },
}


SKILL_LIST_BY_DOMAIN_SCHEMA = {
    "name": "skill_list_by_domain",
    "description": (
        "List skills belonging to a domain keyword (e.g. 'RNA', 'ATAC', '文献', 'figure'). "
        "Use when you want the full landscape of one area instead of ranked search hits."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "domain": {"type": "string", "description": "领域词，例如 'RNA' / 'ATAC' / '文献' / 'figure'"},
            "limit": {"type": "integer", "description": "最多返回条数，默认 40，最大 200"},
        },
        "required": ["domain"],
    },
}


def _handle_skill_search(args, **kw) -> str:
    query = str((args or {}).get("query") or "").strip()
    try:
        result = _router().search(
            query,
            top_k=(args or {}).get("top_k", 8),
            level=str((args or {}).get("level") or ""),
            domain=str((args or {}).get("domain") or ""),
        )
    except Exception as exc:  # 检索失败要给出可操作提示，而不是抛栈
        logger.warning("skill_search failed: %s", exc)
        result = {"success": False, "error": "技能检索失败：%s" % exc,
                  "hint": "检查 SKILLS_INDEX.md 是否存在（python -m webui.skills_registry --build）",
                  "results": []}
    if result.get("success") and result.get("results"):
        result["next_step"] = "选中最匹配的 name 后调用 skill_view(name='<name>') 加载完整指令"
    return json.dumps(result, ensure_ascii=False)


def _handle_list_by_domain(args, **kw) -> str:
    domain = str((args or {}).get("domain") or "").strip()
    try:
        result = _router().list_by_domain(domain, limit=(args or {}).get("limit", 40))
    except Exception as exc:
        logger.warning("skill_list_by_domain failed: %s", exc)
        result = {"success": False, "error": "领域列举失败：%s" % exc, "skills": []}
    return json.dumps(result, ensure_ascii=False)


registry.register(
    name="skill_search",
    toolset="skills",
    schema=SKILL_SEARCH_SCHEMA,
    handler=_handle_skill_search,
    check_fn=_index_available,
    emoji="🔎",
)

registry.register(
    name="skill_list_by_domain",
    toolset="skills",
    schema=SKILL_LIST_BY_DOMAIN_SCHEMA,
    handler=_handle_list_by_domain,
    check_fn=_index_available,
    emoji="🗂️",
)
