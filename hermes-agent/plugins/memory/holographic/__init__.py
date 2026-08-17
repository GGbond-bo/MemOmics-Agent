"""hermes-memory-store — holographic memory plugin using MemoryProvider interface.

Registers as a MemoryProvider plugin, giving the agent structured fact storage
with entity resolution, trust scoring, and HRR-based compositional retrieval.

Original plugin by dusterbloom (PR #2351), adapted to the MemoryProvider ABC.

Config in $HERMES_HOME/config.yaml (profile-scoped):
  plugins:
    hermes-memory-store:
      db_path: $HERMES_HOME/memory_store.db   # omit to use the default
      auto_extract: false
      default_trust: 0.5
      min_trust_threshold: 0.3
      temporal_decay_half_life: 0
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List

from agent.memory_provider import MemoryProvider
from tools.registry import tool_error
from .store import MemoryStore
from .retrieval import FactRetriever
from hermes_cli.config import cfg_get

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Tool schemas (unchanged from original PR)
# ---------------------------------------------------------------------------

FACT_STORE_SCHEMA = {
    "name": "fact_store",
    "description": (
        "Deep structured memory with algebraic reasoning. "
        "Use alongside the memory tool — memory for always-on context, "
        "fact_store for deep recall and compositional queries.\n\n"
        "ACTIONS (simple → powerful):\n"
        "• add — Store a fact the user would expect you to remember.\n"
        "• search — Keyword lookup ('editor config', 'deploy process').\n"
        "• probe — Entity recall: ALL facts about a person/thing.\n"
        "• related — What connects to an entity? Structural adjacency.\n"
        "• reason — Compositional: facts connected to MULTIPLE entities simultaneously.\n"
        "• contradict — Memory hygiene: find facts making conflicting claims.\n"
        "• update/remove/list — CRUD operations.\n\n"
        "IMPORTANT: Before answering questions about the user, ALWAYS probe or reason first."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["add", "search", "probe", "related", "reason", "contradict", "update", "remove", "list"],
            },
            "content": {"type": "string", "description": "Fact content (required for 'add')."},
            "query": {"type": "string", "description": "Search query (required for 'search')."},
            "entity": {"type": "string", "description": "Entity name for 'probe'/'related'."},
            "entities": {"type": "array", "items": {"type": "string"}, "description": "Entity names for 'reason'."},
            "fact_id": {"type": "integer", "description": "Fact ID for 'update'/'remove'."},
            "category": {"type": "string", "enum": ["user_pref", "project", "tool", "general"]},
            "tags": {"type": "string", "description": "Comma-separated tags."},
            "trust_delta": {"type": "number", "description": "Trust adjustment for 'update'."},
            "min_trust": {"type": "number", "description": "Minimum trust filter (default: 0.3)."},
            "limit": {"type": "integer", "description": "Max results (default: 10)."},
        },
        "required": ["action"],
    },
}

FACT_FEEDBACK_SCHEMA = {
    "name": "fact_feedback",
    "description": (
        "Rate a fact after using it. Mark 'helpful' if accurate, 'unhelpful' if outdated. "
        "This trains the memory — good facts rise, bad facts sink."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": ["helpful", "unhelpful"]},
            "fact_id": {"type": "integer", "description": "The fact ID to rate."},
        },
        "required": ["action", "fact_id"],
    },
}



SEARCH_HISTORY_SCHEMA = {
    "name": "search_history",
    "description": (
        "Full-text search over the CURRENT session past user messages (including compaction-archived turns). "
        "Use when the user refers back to something said earlier in this conversation - scripts, paths, parameters, earlier conclusions. "
        "Results are historical context only; confirm with the user before acting on them."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Search keywords (Chinese ok; verbs are stripped automatically)."},
            "limit": {"type": "integer", "description": "Max results (default: 5, max 10)."},
            "session_id": {"type": "string", "description": "Optional session id to search (default: current session)."},
        },
        "required": ["query"],
    },
}

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

# Verbs / filler words stripped before asset & history search, so that a
# full user sentence like "继续跑热图" degrades to its content keyword 热图.
_RE_NOISE_WORDS = re.compile(
    r"(继续|接着|然后|再|帮我|请|给我|麻烦|跑|做|画|看|计算|执行|整理|总结|生成|"
    r"更新|修改|优化|用|把|将|对|一下|看看|一下|一遍|要|想|希望|现在|重新|开始|停止|"
    r"能不能|可以|怎么|如何|什么|哪些|那个|这个|还是|都|也|了|呢|吗|啊|吧|的|是|"
    r"然后|之后|先|后|每|各|所有|全部|刚才|上次|之前|继续跑|接着跑|重新跑|帮我跑)"
)

def _extract_query_keywords(query: str) -> str:
    """Strip verbs/filler from a user query to get search keywords.

    Preserves file paths (drive-letter prefixes, backslashes, dots) and
    CJK content words. Falls back to the original query when nothing
    substantive remains.
    """
    if not query:
        return ""
    q = query.strip()
    cleaned = _RE_NOISE_WORDS.sub(" ", q)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    if not cleaned:
        return q
    return cleaned


def _search_session_messages(sid: str, query: str, limit: int = 3):
    """Read-only FTS over ONE session user messages (trigram + LIKE fallback).

    Returns list of (timestamp, snippet). Returns [] on any error. Includes compaction-archived turns (active=1 OR compacted=1).
    """
    if not sid or not query:
        return []
    kw = _extract_query_keywords(query)
    if not kw:
        return []
    import sqlite3 as _sqlite3
    from hermes_constants import get_hermes_home
    try:
        conn = _sqlite3.connect(f"file:{str(get_hermes_home() / 'state.db')}?mode=ro", uri=True, timeout=5.0)
    except Exception:
        return []
    try:
        rows = []
        # trigram FTS needs >=3 chars; CJK substring works natively.
        if len(kw) >= 3:
            try:
                rows = conn.execute(
                    """SELECT m.id, m.timestamp,
                              snippet(messages_fts_trigram, 0, '>>>', '<<<', '...', 40) AS snippet
                       FROM messages m
                       JOIN messages_fts_trigram ON messages_fts_trigram.rowid = m.id
                       WHERE messages_fts_trigram MATCH ?
                         AND m.session_id = ?
                         AND m.role IN ('user', 'human')
                         AND (m.active = 1 OR m.compacted = 1)
                       ORDER BY m.timestamp DESC
                       LIMIT ?""",
                    (kw, sid, limit),
                ).fetchall()
            except Exception:
                rows = []
        if not rows:
            like = f"%{kw}%"
            rows = conn.execute(
                """SELECT m.id, m.timestamp, m.content AS snippet
                   FROM messages m
                   WHERE m.session_id = ?
                     AND m.role IN ('user', 'human')
                     AND (m.active = 1 OR m.compacted = 1)
                     AND m.content LIKE ?
                   ORDER BY m.timestamp DESC
                   LIMIT ?""",
                (sid, like, limit),
            ).fetchall()
        out = []
        for r in rows:
            snip = str(r[2] or '')[:120].replace('\n', ' ')
            out.append((r[1], snip))
        return out
    except Exception:
        return []
    finally:
        try:
            conn.close()
        except Exception:
            pass

def _load_plugin_config() -> dict:
    from hermes_constants import get_hermes_home
    config_path = get_hermes_home() / "config.yaml"
    if not config_path.exists():
        return {}
    try:
        import yaml
        with open(config_path, encoding="utf-8-sig") as f:
            all_config = yaml.safe_load(f) or {}
        return cfg_get(all_config, "plugins", "hermes-memory-store", default={}) or {}
    except Exception:
        return {}


# ---------------------------------------------------------------------------
# MemoryProvider implementation
# ---------------------------------------------------------------------------

class HolographicMemoryProvider(MemoryProvider):
    """Holographic memory with structured facts, entity resolution, and HRR retrieval."""

    def __init__(self, config: dict | None = None):
        self._config = config or _load_plugin_config()
        self._store = None
        self._retriever = None
        self._min_trust = float(self._config.get("min_trust_threshold", 0.3))

    @property
    def name(self) -> str:
        return "holographic"

    def is_available(self) -> bool:
        return True  # SQLite is always available, numpy is optional

    def save_config(self, values, hermes_home):
        """Write config to config.yaml under plugins.hermes-memory-store."""
        from pathlib import Path
        config_path = Path(hermes_home) / "config.yaml"
        try:
            import yaml
            existing = {}
            if config_path.exists():
                with open(config_path, encoding="utf-8-sig") as f:
                    existing = yaml.safe_load(f) or {}
            existing.setdefault("plugins", {})
            existing["plugins"]["hermes-memory-store"] = values
            with open(config_path, "w", encoding="utf-8") as f:
                yaml.dump(existing, f, default_flow_style=False)
        except Exception:
            pass

    def get_config_schema(self):
        from hermes_constants import display_hermes_home
        _default_db = f"{display_hermes_home()}/memory_store.db"
        return [
            {"key": "db_path", "description": "SQLite database path", "default": _default_db},
            {"key": "auto_extract", "description": "Auto-extract facts at session end", "default": "true", "choices": ["true", "false"]},
            {"key": "default_trust", "description": "Default trust score for new facts", "default": "0.5"},
            {"key": "hrr_dim", "description": "HRR vector dimensions", "default": "1024"},
        ]

    def initialize(self, session_id: str, **kwargs) -> None:
        from hermes_constants import get_hermes_home
        _hermes_home = str(get_hermes_home())
        _default_db = _hermes_home + "/memory_store.db"
        db_path = self._config.get("db_path", _default_db)
        # Expand $HERMES_HOME in user-supplied paths so config values like
        # "$HERMES_HOME/memory_store.db" or "~/.hermes/memory_store.db" both
        # resolve to the active profile's directory.
        if isinstance(db_path, str):
            db_path = db_path.replace("$HERMES_HOME", _hermes_home)
            db_path = db_path.replace("${HERMES_HOME}", _hermes_home)
        default_trust = float(self._config.get("default_trust", 0.5))
        hrr_dim = int(self._config.get("hrr_dim", 1024))
        hrr_weight = float(self._config.get("hrr_weight", 0.3))
        temporal_decay = int(self._config.get("temporal_decay_half_life", 0))

        self._store = MemoryStore(db_path=db_path, default_trust=default_trust, hrr_dim=hrr_dim)
        self._retriever = FactRetriever(
            store=self._store,
            temporal_decay_half_life=temporal_decay,
            hrr_weight=hrr_weight,
            hrr_dim=hrr_dim,
        )
        self._session_id = session_id

    def system_prompt_block(self) -> str:
        if not self._store:
            return ""
        try:
            total = self._store._conn.execute(
                "SELECT COUNT(*) FROM facts"
            ).fetchone()[0]
        except Exception:
            total = 0
        blocks = []
        if total == 0:
            blocks.append(
                "# Holographic Memory\n"
                "Active. Empty fact store — proactively add facts the user would expect you to remember.\n"
                "Use fact_store(action='add') to store durable structured facts about people, projects, preferences, decisions.\n"
                "Use fact_feedback to rate facts after using them (trains trust scores)."
            )
        else:
            blocks.append(
                f"# Holographic Memory\n"
                f"Active. {total} facts stored with entity resolution and trust scoring.\n"
                f"Use fact_store to search, probe entities, reason across entities, or add facts.\n"
                f"Use fact_feedback to rate facts after using them (trains trust scores)."
            )

        # --- Session asset inventory (compression-immune: rebuilt with the
        # --- volatile system prompt section on every system prompt rebuild).
        try:
            assets = self._store.list_assets(session_id=self._session_id or None, status="confirmed", limit=10)
            if assets:
                lines = [f"- {a['name']} → {a['path'] or '(no path)'}" + (f"（用途：{a['purpose']}）" if a["purpose"] else "")
                         for a in assets]
                blocks.append("📌 会话资产清单（用户在本会话提供的脚本/文件/路径，压缩后依然有效，可直接引用）\n" + "\n".join(lines))
        except Exception as e:
            logger.debug("Holographic asset block failed: %s", e)

        return "\n\n".join(blocks)

    def prefetch(self, query: str, *, session_id: str = "") -> str:
        if not self._retriever or not query:
            return ""
        sid = session_id or self._session_id or ""
        try:
            parts = []
            # Source 1: facts (existing)
            results = self._retriever.search(query, min_trust=self._min_trust, limit=5)
            if results:
                lines = []
                for r in results:
                    trust = r.get("trust_score", r.get("trust", 0))
                    lines.append(f"- [{trust:.1f}] {r.get('content', '')}")
                parts.append("## Holographic Memory\n" + "\n".join(lines))

            # Source 2: confirmed assets (cross-session; scoped to session when
            # the session_id is known and the query is short).
            try:
                assets = self._store.search_assets(
                    _extract_query_keywords(query), session_id=None, status="confirmed", limit=3
                )
                if assets:
                    alines = []
                    for a in assets:
                        alines.append(
                            f"- [{a['name']}] {a['path'] or '(no path)'}"
                            + (f"（用途：{a['purpose']}）" if a["purpose"] else "")
                            + (f"，来自会话 {a['session_id']}" if a["session_id"] and a["session_id"] != sid else "")
                        )
                    parts.append(
                        "## Related Assets（历史会话资产 · 仅供参考，用前请与用户确认）\n" + "\n".join(alines)
                    )
            except Exception as e:
                logger.debug("Holographic asset prefetch failed: %s", e)

            # Source 3: session message history (shared helper; includes
            # compaction-archived turns).
            try:
                hist = _search_session_messages(sid, query, 3) if sid else []
                if hist:
                    hlines = [f"- {snip}" for _ts, snip in hist]
                    parts.append(
                        "## Related History（本会话历史对话 · 仅供参考）\n" + "\n".join(hlines)
                    )
            except Exception as e:
                logger.debug("Holographic history prefetch failed: %s", e)

            # Source 4: current task block + recent user requests (per-session state)
            try:
                st = self._store.get_session_state(sid)
                task = json.loads(st.get("task_json") or "{}")
                reqs = json.loads(st.get("requests_json") or "[]")
                sblocks = []
                if task:
                    t_title = task.get("title") or ""
                    t_step = task.get("step")
                    t_total = task.get("total_steps")
                    t_script = task.get("current_script") or ""
                    t_concl = task.get("last_conclusion") or ""
                    parts_t = [f"- 当前任务：{t_title}"]
                    if t_step:
                        parts_t.append(f"- 进度：第 {t_step} 步" + (f"/共 {t_total} 步" if t_total else ""))
                    if t_script:
                        parts_t.append(f"- 正在使用：{t_script}")
                    if task.get("switched_from") and task.get("entity"):
                        parts_t.append(
                            f"- ⚠️ 话题已切换：{task['switched_from']} → {task['entity']}（旧任务暂停，以用户最新诉求为准）"
                        )
                    if t_concl:
                        parts_t.append(f"- 最近结论：{t_concl}")
                    sblocks.append("📌 当前任务状态（会话内跟踪，仅供参考）\n" + "\n".join(parts_t))
                recent = [r for r in reqs if r.get("ts")][-3:]
                if recent:
                    rlines = [f"- {r.get('text', '')}" for r in recent]
                    sblocks.append("📌 用户最近诉求（本会话 · 仅供参考，需用户确认）\n" + "\n".join(rlines))
                if sblocks:
                    parts.append("\n\n".join(sblocks))
            except Exception as e:
                logger.debug("Holographic session-state prefetch failed: %s", e)

            if not parts:
                return ""
            return "\n\n".join(parts)
        except Exception as e:
            logger.debug("Holographic prefetch failed: %s", e)
            return ""

    def sync_turn(self, user_content: str, assistant_content: str, *, session_id: str = "") -> None:
        # Holographic memory stores explicit facts via tools, not auto-sync.
        # The on_session_end hook handles auto-extraction if configured.
        pass
        # The on_session_end hook handles auto-extraction if configured.
        pass

    def on_session_switch(
        self,
        new_session_id: str,
        *,
        parent_session_id: str = "",
        reset: bool = False,
        rewound: bool = False,
        **kwargs,
    ) -> None:
        """Re-bind per-session state when the agent switches sessions mid-process.

        Without this, ``_session_id`` keeps pointing at the old session after
        /new, /resume, /reset or context compression, so the session asset
        block and prefetch session-state lookups would target the wrong
        session's records.
        """
        self._session_id = new_session_id or ""
        logger.debug("Holographic session switched to %r", self._session_id)

    def get_tool_schemas(self) -> List[Dict[str, Any]]:
        return [FACT_STORE_SCHEMA, FACT_FEEDBACK_SCHEMA, SEARCH_HISTORY_SCHEMA]

    def handle_tool_call(self, tool_name: str, args: Dict[str, Any], **kwargs) -> str:
        if tool_name == "fact_store":
            return self._handle_fact_store(args)
        elif tool_name == "fact_feedback":
            return self._handle_fact_feedback(args)
        elif tool_name == "search_history":
            return self._handle_search_history(args)
        return tool_error(f"Unknown tool: {tool_name}")

    def on_session_end(self, messages: List[Dict[str, Any]]) -> None:
        if not self._config.get("auto_extract", False):
            return
        if not self._store or not messages:
            return
        self._auto_extract_facts(messages)

    def on_memory_write(self, action: str, target: str, content: str) -> None:
        """Mirror built-in memory writes as facts."""
        if action == "add" and self._store and content:
            try:
                category = "user_pref" if target == "user" else "general"
                self._store.add_fact(content, category=category)
            except Exception as e:
                logger.debug("Holographic memory_write mirror failed: %s", e)

    def on_delegation(self, task: str, result: str, *,
                      child_session_id: str = "", **kwargs) -> None:
        """Persist subagent outcomes as facts (category='delegation').

        Called by the parent agent when a delegate_task child completes,
        so subagent conclusions survive even if the parent never summarises
        them inline. add_fact deduplicates on content, so identical
        outcomes are never written twice.
        """
        if not self._store or not result:
            return
        try:
            snippet = str(result).strip()[:300]
            if not snippet:
                return
            content = "[子代理结论] " + snippet
            if task:
                content = "[子代理结论][任务: " + str(task)[:80] + "] " + snippet
            if child_session_id:
                content = content + "（子代理会话: " + child_session_id[:16] + "）"
            self._store.add_fact(content, category="delegation", tags="subagent")
        except Exception as e:
            logger.debug("Holographic on_delegation failed: %s", e)

    def shutdown(self) -> None:
        # Release the shared SQLite connection deterministically on the
        # caller's thread. Dropping the reference alone leaves fd finalization
        # to GC, which keeps the connection (and its write lock) alive on a
        # long-running gateway and prolongs the "database is locked" contention
        # this store's shared-connection refcounting is meant to eliminate.
        # close() is idempotent and refcount-guarded, so siblings stay safe.
        if self._store is not None:
            try:
                self._store.close()
            except Exception as e:
                logger.debug("Holographic shutdown close() failed: %s", e)
        self._store = None
        self._retriever = None

    # -- Tool handlers -------------------------------------------------------

    def _handle_fact_store(self, args: dict) -> str:
        try:
            action = args["action"]
            store = self._store
            retriever = self._retriever

            if action == "add":
                fact_id = store.add_fact(
                    args["content"],
                    category=args.get("category", "general"),
                    tags=args.get("tags", ""),
                )
                return json.dumps({"fact_id": fact_id, "status": "added"})

            elif action == "search":
                results = retriever.search(
                    args["query"],
                    category=args.get("category"),
                    min_trust=float(args.get("min_trust", self._min_trust)),
                    limit=int(args.get("limit", 10)),
                )
                return json.dumps({"results": results, "count": len(results)})

            elif action == "probe":
                results = retriever.probe(
                    args["entity"],
                    category=args.get("category"),
                    limit=int(args.get("limit", 10)),
                )
                return json.dumps({"results": results, "count": len(results)})

            elif action == "related":
                results = retriever.related(
                    args["entity"],
                    category=args.get("category"),
                    limit=int(args.get("limit", 10)),
                )
                return json.dumps({"results": results, "count": len(results)})

            elif action == "reason":
                entities = args.get("entities", [])
                if not entities:
                    return tool_error("reason requires 'entities' list")
                results = retriever.reason(
                    entities,
                    category=args.get("category"),
                    limit=int(args.get("limit", 10)),
                )
                return json.dumps({"results": results, "count": len(results)})

            elif action == "contradict":
                results = retriever.contradict(
                    category=args.get("category"),
                    limit=int(args.get("limit", 10)),
                )
                return json.dumps({"results": results, "count": len(results)})

            elif action == "update":
                updated = store.update_fact(
                    int(args["fact_id"]),
                    content=args.get("content"),
                    trust_delta=float(args["trust_delta"]) if "trust_delta" in args else None,
                    tags=args.get("tags"),
                    category=args.get("category"),
                )
                return json.dumps({"updated": updated})

            elif action == "remove":
                removed = store.remove_fact(int(args["fact_id"]))
                return json.dumps({"removed": removed})

            elif action == "list":
                facts = store.list_facts(
                    category=args.get("category"),
                    min_trust=float(args.get("min_trust", 0.0)),
                    limit=int(args.get("limit", 10)),
                )
                return json.dumps({"facts": facts, "count": len(facts)})

            else:
                return tool_error(f"Unknown action: {action}")

        except KeyError as exc:
            return tool_error(f"Missing required argument: {exc}")
        except Exception as exc:
            return tool_error(str(exc))

    def _handle_search_history(self, args: dict) -> str:
        """Tool handler: full-text search over session user messages."""
        try:
            query = (args.get("query") or "").strip()
            if not query:
                return "search_history: query is required"
            try:
                limit = min(max(int(args.get("limit", 5)), 1), 10)
            except (TypeError, ValueError):
                limit = 5
            sid = (args.get("session_id") or "").strip() or (self._session_id or "")
            if not sid:
                return "search_history: no session bound (session_id is empty)"
            hist = _search_session_messages(sid, query, limit)
            if not hist:
                return "search_history: no matching historical messages in this session"
            lines = []
            for _ts, snip in hist:
                lines.append("- " + snip)
            return "本会话历史对话（仅供参考，用前请与用户确认）：\n" + "\n".join(lines)
        except Exception as e:
            return "search_history failed: %s" % e

    def _handle_fact_feedback(self, args: dict) -> str:
        try:
            fact_id = int(args["fact_id"])
            helpful = args["action"] == "helpful"
            result = self._store.record_feedback(fact_id, helpful=helpful)
            return json.dumps(result)
        except KeyError as exc:
            return tool_error(f"Missing required argument: {exc}")
        except Exception as exc:
            return tool_error(str(exc))

    # -- Auto-extraction (on_session_end) ------------------------------------

    def _auto_extract_facts(self, messages: list) -> None:
        _PREF_PATTERNS = [
            re.compile(r'\bI\s+(?:prefer|like|love|use|want|need)\s+(.+)', re.IGNORECASE),
            re.compile(r'\bmy\s+(?:favorite|preferred|default)\s+\w+\s+is\s+(.+)', re.IGNORECASE),
            re.compile(r'\bI\s+(?:always|never|usually)\s+(.+)', re.IGNORECASE),
        ]
        # Chinese preference / decision patterns (MemOmics UI is Chinese).
        # Conservative: only explicit preference / decision wording triggers;
        # ordinary analysis requests (e.g. 'continue the heatmap') never match.
        _CN_PREF_PATTERNS = [
            re.compile(r"(?:我|本人)(?:喜欢|偏好|习惯|通常|一直|从来|希望|想要|更愿意|倾向于)(?:用|用|以|把|按|的)?", re.IGNORECASE),
            re.compile(r"(?:以后|今后|之后|后续)(?:都|就|一律|默认|统一)(?:用|按|以|选)", re.IGNORECASE),
            re.compile(r"(?:请)?(?:记住|记得|牢记)[:：]?", re.IGNORECASE),
        ]
        _CN_DECISION_PATTERNS = [
            re.compile(r"我们(?:决定|确定|商定|选择|统一)(?:用|了|的|按|以)?", re.IGNORECASE),
            re.compile(r"(?:这个|本)?项目(?:统一|一律)?(?:用|需要|要求|采用|基于)", re.IGNORECASE),
        ]

        _DECISION_PATTERNS = [
            re.compile(r'\bwe\s+(?:decided|agreed|chose)\s+(?:to\s+)?(.+)', re.IGNORECASE),
            re.compile(r'\bthe\s+project\s+(?:uses|needs|requires)\s+(.+)', re.IGNORECASE),
        ]

        extracted = 0
        for msg in messages:
            if msg.get("role") != "user":
                continue
            content = msg.get("content", "")
            if not isinstance(content, str) or len(content) < 6:
                continue

            for pattern in _PREF_PATTERNS:
                if pattern.search(content):
                    try:
                        self._store.add_fact(content[:400], category="user_pref")
                        extracted += 1
                    except Exception:
                        pass
                    break

            for pattern in _CN_PREF_PATTERNS:
                if pattern.search(content):
                    try:
                        self._store.add_fact(content[:400], category="user_pref")
                        extracted += 1
                    except Exception:
                        pass
                    break

            for pattern in _CN_DECISION_PATTERNS:
                if pattern.search(content):
                    try:
                        self._store.add_fact(content[:400], category="project")
                        extracted += 1
                    except Exception:
                        pass
                    break

            for pattern in _DECISION_PATTERNS:
                if pattern.search(content):
                    try:
                        self._store.add_fact(content[:400], category="project")
                        extracted += 1
                    except Exception:
                        pass
                    break

        if extracted:
            logger.info("Auto-extracted %d facts from conversation", extracted)


# ---------------------------------------------------------------------------
# Plugin entry point
# ---------------------------------------------------------------------------

def register(ctx) -> None:
    """Register the holographic memory provider with the plugin system."""
    config = _load_plugin_config()
    provider = HolographicMemoryProvider(config=config)
    ctx.register_memory_provider(provider)
