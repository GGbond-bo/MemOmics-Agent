#!/usr/bin/env python3
"""
MemOmics ↔ Holographic Memory Bridge
=====================================
MemOmics 领域逻辑与 Hermes Holographic 外置记忆之间的桥接层。

双层架构：
  1. Agent 层: fact_store / fact_feedback 工具（Hermes 原生提供）
  2. 代码层: 本模块直接操作 MemoryStore（供 skill_evolution 调用）

记忆分类 (category):
  - user_pref     — 用户偏好（可视化风格、工具选择、脚本偏好）
  - script_score  — 脚本评分（用户认可/不认可的脚本 + 分数）
  - skill_exp     — skill 经验（proven_params、参数组合、已知错误）
  - project       — 项目上下文（物种/组织/方向/数据路径）
  - general       — 其他

使用方式:
  代码层: from memomics.bio_tools.memory_bridge import store_script_score, search_memory
  Agent层: SOUL.md 中指示 agent 使用 fact_store/fact_feedback
"""

import os
import json
import logging
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

# ─── 获取 Holographic MemoryStore ────────────────────────

_store = None  # 单例

def _get_store():
    """懒加载 Holographic MemoryStore（单例，防 SQLite lock）。"""
    global _store
    if _store is not None:
        return _store
    
    cur = Path(__file__).resolve().parent.parent.parent
    hermes_home = cur / "hermes_home"
    db_path = str(hermes_home / "memory_store.db")
    
    import sys
    hermes_agent = str(hermes_home.parent / "hermes-agent")
    plugin_dir = str(Path(hermes_agent) / "plugins" / "memory")
    for p in [hermes_agent, plugin_dir]:
        if p not in sys.path:
            sys.path.insert(0, p)
    from plugins.memory.holographic.store import MemoryStore
    _store = MemoryStore(db_path)
    return _store



# ─── 写入接口 ────────────────────────────────────────

def store_script_score(
    skill_name: str,
    script_name: str,
    user_score: int,
    auto_score: int = 0,
    species: str = "",
    tissue: str = "",
    direction: str = "",
    approved: bool = True,
    notes: str = ""
) -> int:
    """存储用户对脚本的评分。

    Args:
        skill_name: 所属 skill 名（如 scrna-seurat-core）
        script_name: 脚本名（如 custom_umap.R）
        user_score: 用户评分 0-10
        auto_score: rail_review 自动评分 0-10
        approved: 用户是否认可
        notes: 额外说明

    Returns:
        fact_id (int), -1 表示存储失败
    """
    try:
        store = _get_store()
        content = (
            f"[{skill_name}] 脚本 '{script_name}' "
            f"用户评分={user_score}/10, 自动评分={auto_score}/10, "
            f"approved={'是' if approved else '否'}"
        )
        if species or tissue or direction:
            content += f" | 物种={species} 组织={tissue} 方向={direction}"
        if notes:
            content += f" | 备注: {notes}"
        
        tags = f"{skill_name}, script, {script_name}"
        if approved:
            tags += ", user-approved"
        
        fid = store.add_fact(
            content=content,
            category="script_score",
            tags=tags
        )
        return fid
    except Exception as e:
        logger.warning(f"memory_bridge: store_script_score failed: {e}")
        return -1


def store_user_pref(content: str, tags: str = "") -> int:
    """存储用户偏好。

    示例:
        store_user_pref("用户希望所有热图用 pheatmap 而非 ComplexHeatmap",
                        tags="heatmap, pheatmap, visualization")
    """
    try:
        store = _get_store()
        return store.add_fact(content=content, category="user_pref", tags=tags)
    except Exception as e:
        logger.warning(f"memory_bridge: store_user_pref failed: {e}")
        return -1


def store_skill_exp(
    skill_name: str,
    content: str,
    tags: str = ""
) -> int:
    """存储 skill 级别的经验（proven_params、已知错误等）。

    由 skill_evolution._record_success / _record_error 调用。
    """
    try:
        store = _get_store()
        full_tags = f"{skill_name}, skill-exp, {tags}" if tags else f"{skill_name}, skill-exp"
        return store.add_fact(content=content, category="skill_exp", tags=full_tags)
    except Exception as e:
        logger.warning(f"memory_bridge: store_skill_exp failed: {e}")
        return -1


def store_project_context(species: str, tissue: str, direction: str, **kwargs) -> int:
    """存储项目上下文信息。"""
    try:
        store = _get_store()
        content = f"项目: 物种={species}, 组织={tissue}, 方向={direction}"
        for k, v in kwargs.items():
            content += f", {k}={v}"
        return store.add_fact(content=content, category="project", tags=f"{species}, {tissue}, {direction}")
    except Exception as e:
        logger.warning(f"memory_bridge: store_project_context failed: {e}")
        return -1


# ─── 读取接口 ────────────────────────────────────────

def search_memory(query: str, category: str = "", limit: int = 5) -> list[dict]:
    """搜索 Holographic 记忆。

    Args:
        query: 搜索关键词
        category: 限定分类（留空=全搜索）
        limit: 最大结果数

    Returns:
        [{"fact_id": int, "content": str, "category": str, "trust_score": float, ...}, ...]
    """
    try:
        store = _get_store()
        rows = store.search_facts(query, limit=limit)
        if not isinstance(rows, list):
            return []
        results = []
        for row in rows:
            results.append({
                "fact_id": row["fact_id"],
                "content": row["content"],
                "category": row["category"],
                "trust_score": row["trust_score"],
                "tags": row.get("tags", ""),
                "retrieval_count": row.get("retrieval_count", 0),
            })
        return results
    except Exception as e:
        logger.warning(f"memory_bridge: search_memory failed: {e}")
        return []


def recall_experience(
    skill_name: str = "",
    species: str = "",
    tissue: str = "",
    direction: str = ""
) -> dict:
    """召回与当前分析相关的历史经验。

    同时搜索多个维度，合并去重后返回。
    由 skill_evolution.query_logs 调用。

    Returns:
        {
            "proven_scripts": [...],      # 已验证脚本
            "user_prefs": [...],          # 用户偏好
            "known_errors": [...],        # 已知错误
            "related": [...]              # 其他相关
        }
    """
    result = {
        "proven_scripts": [],
        "user_prefs": [],
        "known_errors": [],
        "related": []
    }
    try:
        # 构建多维搜索
        queries = []
        if skill_name:
            queries.append(skill_name)
        if direction:
            queries.append(direction)
        if tissue:
            queries.append(tissue)
        if species:
            queries.append(species)
        
        if not queries:
            return result
        
        seen_ids = set()
        for q in queries:
            hits = search_memory(q, limit=5)
            for h in hits:
                if h["fact_id"] not in seen_ids:
                    seen_ids.add(h["fact_id"])
                    cat = h.get("category", "")
                    if cat == "script_score":
                        result["proven_scripts"].append(h)
                    elif cat == "user_pref":
                        result["user_prefs"].append(h)
                    elif cat == "skill_exp" and "error" in h.get("tags", "").lower():
                        result["known_errors"].append(h)
                    elif cat == "skill_exp":
                        result["proven_scripts"].append(h)
                    else:
                        result["related"].append(h)
        return result
    except Exception as e:
        logger.warning(f"memory_bridge: recall_experience failed: {e}")
        return result


def record_feedback(fact_id: int, helpful: bool) -> None:
    """记录记忆的 helpful/unhelpful 反馈，影响 trust_score。"""
    try:
        store = _get_store()
        store.record_feedback(fact_id, helpful)
    except Exception as e:
        logger.warning(f"memory_bridge: record_feedback failed: {e}")


# ─── 自检 ────────────────────────────────────────────

if __name__ == "__main__":
    print("=== MemOmics Holographic Memory Bridge 自检 ===\n")
    
    # 1. 写
    fid1 = store_user_pref(
        "用户偏好 ggplot2 + theme_minimal() + 深色配色方案",
        tags="ggplot2, theme, dark, visualization"
    )
    print(f"store_user_pref → fact_id={fid1}")
    
    fid2 = store_script_score(
        skill_name="scrna-seurat-core",
        script_name="custom_umap_dark.R",
        user_score=9,
        auto_score=7,
        species="mouse",
        tissue="liver",
        direction="aging",
        approved=True,
        notes="这个 UMAP 脚本配色非常好，每次都用"
    )
    print(f"store_script_score → fact_id={fid2}")
    
    fid3 = store_skill_exp(
        skill_name="scrna-seurat-core",
        content="mouse liver aging: SCTransform(norm.method='SCT', vars.to.regress='percent.mt') 运行成功",
        tags="SCTransform, liver, aging, success"
    )
    print(f"store_skill_exp → fact_id={fid3}")
    
    # 2. 搜索
    print("\n--- search: ggplot2 ---")
    for r in search_memory("ggplot2", limit=3):
        print(f"  [{r['fact_id']}] trust={r['trust_score']:.2f} {r['content'][:80]}")
    
    print("\n--- search: umap liver ---")
    for r in search_memory("umap liver", limit=3):
        print(f"  [{r['fact_id']}] trust={r['trust_score']:.2f} {r['content'][:80]}")
    
    # 3. 召回
    print("\n--- recall_experience(skill='scrna-seurat-core', tissue='liver') ---")
    exp = recall_experience(skill_name="scrna-seurat-core", tissue="liver")
    for key, items in exp.items():
        if items:
            print(f"  {key}: {len(items)} 条")
            for item in items:
                print(f"    [{item['fact_id']}] {item['content'][:80]}")
    
    # 4. 反馈
    if fid2 > 0:
        record_feedback(fid2, helpful=True)
        print(f"\nrecord_feedback(fact_id={fid2}, helpful=True) → OK")
    
    print("\n✅ Holographic Memory Bridge 工作正常")
