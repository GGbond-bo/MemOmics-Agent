#!/usr/bin/env python3
"""
MemOmics ↔ Holographic Memory Bridge
=====================================
直连 SQLite FTS5，与 Hermes Holographic 同 schema，零 Hermes 依赖。

记忆分类 (category):
  - user_pref     — 用户偏好（可视化风格、工具选择、脚本偏好）
  - script_score  — 脚本评分（用户认可/不认可的脚本 + 分数）
  - skill_exp     — skill 经验（proven_params、参数组合、已知错误）
  - project       — 项目上下文（物种/组织/方向/数据路径）
  - general       — 其他

使用方式:
  from memomics.bio_tools.memory_bridge import store_script_score, search_memory, recall_experience
"""

import os
import re
import sqlite3
import threading
import logging
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

# ─── SQLite 连接管理 ────────────────────────────────

_conn = None
_lock = threading.Lock()


def _get_db_path():
    """获取记忆数据库路径（与 Hermes 共用 hermes_home/memory_store.db）。"""
    cur = Path(__file__).resolve().parent.parent.parent  # MEMOMICS_HOME/
    hermes_home = cur / "hermes_home"
    return str(hermes_home / "memory_store.db")


def _get_conn():
    """获取 SQLite 连接（单例，线程安全）。"""
    global _conn
    if _conn is not None:
        return _conn
    with _lock:
        if _conn is not None:
            return _conn
        db_path = _get_db_path()
        _conn = sqlite3.connect(db_path, check_same_thread=False)
        _conn.row_factory = sqlite3.Row
        _conn.execute("PRAGMA journal_mode=WAL")
        _conn.execute("PRAGMA busy_timeout=5000")
        _ensure_schema(_conn)
        return _conn


def _ensure_schema(conn):
    """确保数据库有 facts 表和 FTS5 索引（与 Hermes 兼容）。"""
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS facts (
            fact_id         INTEGER PRIMARY KEY AUTOINCREMENT,
            content         TEXT NOT NULL UNIQUE,
            category        TEXT DEFAULT 'general',
            tags            TEXT DEFAULT '',
            trust_score     REAL DEFAULT 0.5,
            retrieval_count INTEGER DEFAULT 0,
            helpful_count   INTEGER DEFAULT 0,
            created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_facts_trust    ON facts(trust_score DESC);
        CREATE INDEX IF NOT EXISTS idx_facts_category ON facts(category);
    """)
    # FTS5: try to create, ignore if already exists
    try:
        conn.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS facts_fts
                USING fts5(content, tags, content=facts, content_rowid=fact_id)
        """)
    except Exception:
        pass
    # Triggers: try to create, ignore if already exists
    for trigger_sql in [
        """CREATE TRIGGER IF NOT EXISTS facts_ai AFTER INSERT ON facts BEGIN
            INSERT INTO facts_fts(rowid, content, tags)
                VALUES (new.fact_id, new.content, new.tags);
        END""",
        """CREATE TRIGGER IF NOT EXISTS facts_ad AFTER DELETE ON facts BEGIN
            INSERT INTO facts_fts(facts_fts, rowid, content, tags)
                VALUES ('delete', old.fact_id, old.content, old.tags);
        END""",
    ]:
        try:
            conn.execute(trigger_sql)
        except Exception:
            pass
    conn.commit()


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
    """存储用户对脚本的评分。返回 fact_id，-1 表示失败。"""
    try:
        conn = _get_conn()
        content = (
            f"[{skill_name}] script '{script_name}' "
            f"user_score={user_score}/10 auto_score={auto_score}/10 "
            f"approved={'yes' if approved else 'no'}"
        )
        if species or tissue or direction:
            content += f" | species={species} tissue={tissue} direction={direction}"
        if notes:
            content += f" | notes: {notes}"

        tags = f"{skill_name}, script, {script_name}"
        if approved:
            tags += ", user-approved"

        cur = conn.execute(
            "INSERT OR IGNORE INTO facts (content, category, tags, trust_score) VALUES (?, ?, ?, ?)",
            (content, "script_score", tags, user_score / 10.0 if user_score > 0 else 0.5)
        )
        conn.commit()
        if cur.lastrowid:
            return cur.lastrowid
        # already exists — get existing id
        row = conn.execute("SELECT fact_id FROM facts WHERE content=?", (content,)).fetchone()
        return row["fact_id"] if row else -1
    except Exception as e:
        logger.warning(f"memory_bridge: store_script_score failed: {e}")
        return -1


def store_user_pref(content: str, tags: str = "") -> int:
    """存储用户偏好。返回 fact_id。"""
    try:
        conn = _get_conn()
        cur = conn.execute(
            "INSERT OR IGNORE INTO facts (content, category, tags, trust_score) VALUES (?, 'user_pref', ?, 0.8)",
            (content, tags)
        )
        conn.commit()
        if cur.lastrowid:
            return cur.lastrowid
        row = conn.execute("SELECT fact_id FROM facts WHERE content=?", (content,)).fetchone()
        return row["fact_id"] if row else -1
    except Exception as e:
        logger.warning(f"memory_bridge: store_user_pref failed: {e}")
        return -1


def store_skill_exp(skill_name: str, content: str, tags: str = "") -> int:
    """存储 skill 经验（proven_params、已知错误等）。"""
    try:
        conn = _get_conn()
        full_tags = f"{skill_name}, skill-exp"
        if tags:
            full_tags += f", {tags}"
        cur = conn.execute(
            "INSERT OR IGNORE INTO facts (content, category, tags, trust_score) VALUES (?, 'skill_exp', ?, 0.5)",
            (content, full_tags)
        )
        conn.commit()
        if cur.lastrowid:
            return cur.lastrowid
        row = conn.execute("SELECT fact_id FROM facts WHERE content=?", (content,)).fetchone()
        return row["fact_id"] if row else -1
    except Exception as e:
        logger.warning(f"memory_bridge: store_skill_exp failed: {e}")
        return -1


def store_project_context(species: str, tissue: str, direction: str, **kwargs) -> int:
    """存储项目上下文。"""
    try:
        conn = _get_conn()
        content = f"project: species={species}, tissue={tissue}, direction={direction}"
        for k, v in kwargs.items():
            content += f", {k}={v}"
        cur = conn.execute(
            "INSERT OR IGNORE INTO facts (content, category, tags, trust_score) VALUES (?, 'project', ?, 0.8)",
            (content, f"{species}, {tissue}, {direction}")
        )
        conn.commit()
        if cur.lastrowid:
            return cur.lastrowid
        row = conn.execute("SELECT fact_id FROM facts WHERE content=?", (content,)).fetchone()
        return row["fact_id"] if row else -1
    except Exception as e:
        logger.warning(f"memory_bridge: store_project_context failed: {e}")
        return -1


# ─── 读取接口 ────────────────────────────────────────

def search_memory(query: str, category: str = "", limit: int = 5) -> list:
    """FTS5 搜索记忆。返回 [{fact_id, content, category, trust_score, tags, retrieval_count}, ...]"""
    try:
        conn = _get_conn()
        # Normalize query for FTS5
        q = query.strip().replace("'", "''")
        q = q.replace('-', ' ').replace('.', ' ')  # FTS5: dashes/dots break MATCH
        if category:
            sql = """
                SELECT f.* FROM facts f
                JOIN facts_fts ft ON f.fact_id = ft.rowid
                WHERE facts_fts MATCH ? AND f.category = ?
                ORDER BY f.trust_score DESC, f.retrieval_count DESC
                LIMIT ?
            """
            rows = conn.execute(sql, (q, category, limit)).fetchall()
        else:
            sql = """
                SELECT f.* FROM facts f
                JOIN facts_fts ft ON f.fact_id = ft.rowid
                WHERE facts_fts MATCH ?
                ORDER BY f.trust_score DESC, f.retrieval_count DESC
                LIMIT ?
            """
            rows = conn.execute(sql, (q, limit)).fetchall()

        results = []
        for row in rows:
            results.append({
                "fact_id": row["fact_id"],
                "content": row["content"],
                "category": row["category"],
                "trust_score": row["trust_score"],
                "tags": row["tags"] or "",
                "retrieval_count": row["retrieval_count"],
            })
            # Update retrieval count
            conn.execute(
                "UPDATE facts SET retrieval_count=retrieval_count+1, updated_at=CURRENT_TIMESTAMP WHERE fact_id=?",
                (row["fact_id"],)
            )
        conn.commit()
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
    """多维召回历史经验。

    Returns:
        {"proven_scripts": [...], "user_prefs": [...], "known_errors": [...], "related": [...]}
    """
    result = {"proven_scripts": [], "user_prefs": [], "known_errors": [], "related": []}

    try:
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
                fid = h.get("fact_id", 0)
                if fid and fid not in seen_ids:
                    seen_ids.add(fid)
                    cat = h.get("category", "")
                    tags = (h.get("tags") or "").lower()
                    if cat == "script_score":
                        result["proven_scripts"].append(h)
                    elif cat == "user_pref":
                        result["user_prefs"].append(h)
                    elif cat == "skill_exp" and "error" in tags:
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
    """记录反馈，影响 trust_score。"""
    try:
        conn = _get_conn()
        delta = 0.1 if helpful else -0.1
        conn.execute(
            "UPDATE facts SET trust_score=MAX(0,MIN(1,trust_score+?)), "
            "helpful_count=helpful_count+?, updated_at=CURRENT_TIMESTAMP WHERE fact_id=?",
            (delta, 1, fact_id)
        )
        conn.commit()
    except Exception as e:
        logger.warning(f"memory_bridge: record_feedback failed: {e}")


# ─── 自检 ────────────────────────────────────────────

if __name__ == "__main__":
    print("=== MemOmics Holographic Memory Bridge (direct SQLite) ===\n")

    fid1 = store_user_pref(
        "User prefers ggplot2 + theme_minimal() + dark color scheme",
        tags="ggplot2, theme, dark, visualization"
    )
    print(f"store_user_pref → fact_id={fid1}")

    fid2 = store_script_score(
        skill_name="scrna-seurat-core",
        script_name="custom_umap_dark.R",
        user_score=9, auto_score=7,
        species="mouse", tissue="liver", direction="aging",
        approved=True,
        notes="Excellent UMAP script, use every time"
    )
    print(f"store_script_score → fact_id={fid2}")

    fid3 = store_skill_exp(
        skill_name="scrna-seurat-core",
        content="mouse liver aging: SCTransform(norm.method='SCT', vars.to.regress='percent.mt') worked",
        tags="SCTransform, liver, aging, success"
    )
    print(f"store_skill_exp → fact_id={fid3}")

    print("\n--- search: ggplot2 ---")
    for r in search_memory("ggplot2", limit=3):
        print(f"  [{r['fact_id']}] trust={r['trust_score']:.2f} {r['content'][:80]}")

    print("\n--- recall_experience(skill='scrna-seurat-core', tissue='liver') ---")
    exp = recall_experience(skill_name="scrna-seurat-core", tissue="liver")
    for key, items in exp.items():
        if items:
            print(f"  {key}: {len(items)} items")
            for item in items:
                print(f"    [{item['fact_id']}] {item['content'][:80]}")

    print("\n✅ Direct SQLite memory_bridge works")
