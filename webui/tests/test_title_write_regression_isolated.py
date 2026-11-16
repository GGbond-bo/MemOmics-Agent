"""Isolated regressions for title-write atomicity.

This module deliberately does not import ``webui.server``: importing the full
server initializes MemOmics home state.  It extracts the real title helpers
from the source AST and executes them against an in-memory SQLite database.
Run directly with ``python webui/tests/test_title_write_regression_isolated.py``.
"""

import ast
import pathlib
import re
import sqlite3
import threading
import unittest


SERVER = pathlib.Path(__file__).resolve().parents[1] / "server.py"


def _title_helper_namespace():
    tree = ast.parse(SERVER.read_text(encoding="utf-8"), filename=str(SERVER))
    wanted = {
        "_title_write_lock",
        "_title_source_from_conn",
        "_manual_title_source_in_lineage",
        "_set_session_title_with_source",
        "_persist_title_source",
        "_load_title_source",
    }
    funcs = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in wanted]
    if {node.name for node in funcs} != wanted:
        raise AssertionError("title helper functions missing from server.py")
    ns = {
        "re": re,
        "_threading": threading,
        "_TITLE_WRITE_LOCKS": tuple(threading.RLock() for _ in range(8)),
    }
    exec(compile(ast.Module(body=funcs, type_ignores=[]), str(SERVER), "exec"), ns)
    return ns


class _TestSessionDB:
    """Small SessionDB-compatible transactional façade backed by real SQLite."""

    def __init__(self):
        self._conn = sqlite3.connect(":memory:", check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        # Production SessionDB exposes a non-reentrant lock.  Keep this fixture
        # faithful so a helper accidentally nesting its lock would deadlock.
        self._lock = threading.Lock()
        self.fail_after_callback = False
        self._conn.executescript(
            "CREATE TABLE sessions (id TEXT PRIMARY KEY, title TEXT UNIQUE, "
            "parent_session_id TEXT, end_reason TEXT);"
            "CREATE TABLE kv (key TEXT PRIMARY KEY, value TEXT);"
        )

    def sanitize_title(self, title):
        title = re.sub(r"\s+", " ", str(title or "")).strip()
        if not title:
            return None
        if len(title) > 120:
            raise ValueError("too long")
        return title

    def _is_compression_ancestor(self, conn, *, ancestor_id, descendant_id):
        # The title helper keeps SessionDB's collision-transfer contract; this
        # fixture has no ancestor title collision, so the answer is false.
        return False

    def _execute_write(self, fn):
        with self._lock:
            self._conn.execute("BEGIN IMMEDIATE")
            try:
                result = fn(self._conn)
                if self.fail_after_callback:
                    raise sqlite3.OperationalError("commit failed")
                self._conn.commit()
                return result
            except BaseException:
                self._conn.rollback()
                raise


class TitleWriteRegressionTests(unittest.TestCase):
    def setUp(self):
        self.db = _TestSessionDB()
        self.db._conn.execute("INSERT INTO sessions (id, title) VALUES (?, ?)", ("s1", "旧名称"))
        self.db._conn.execute("INSERT INTO sessions (id, title) VALUES (?, ?)", ("s2", "占用名称"))
        self.db._conn.commit()
        self.events = []
        self.ns = _title_helper_namespace()
        self.ns["_sessions"] = {"s1": {"id": "s1", "title": "旧名称", "title_source": "auto"}}
        self.ns["_get_session_db"] = lambda: self.db
        self.ns["_sync_meta_display_name"] = lambda session, title: self.events.append(("meta", title))
        self.ns["_append_rename_event"] = lambda sid, old, new, source: self.events.append(("audit", sid, old, new, source))
        self.ns["_session_emit"] = lambda session, message: self.events.append(("emit", message))

    def tearDown(self):
        self.db._conn.close()

    def _write(self, title, source="manual", **kwargs):
        return self.ns["_set_session_title_with_source"]("s1", title, source, **kwargs)

    def test_manual_rename_commits_title_and_source_together(self):
        result = self._write("手动固定名称")

        self.assertTrue(result["ok"])
        self.assertEqual("手动固定名称", self.db._conn.execute("SELECT title FROM sessions WHERE id='s1'").fetchone()[0])
        self.assertEqual("manual", self.db._conn.execute("SELECT value FROM kv WHERE key='title_source:s1'").fetchone()[0])
        self.assertEqual("manual", self.ns["_sessions"]["s1"]["title_source"])
        self.assertEqual("manual", [event for event in self.events if event[0] == "emit"][0][1]["source"])

    def test_duplicate_manual_rename_does_not_change_memory_or_kv(self):
        result = self._write("占用名称")

        self.assertFalse(result["ok"])
        self.assertEqual("旧名称", self.ns["_sessions"]["s1"]["title"])
        self.assertEqual("auto", self.ns["_sessions"]["s1"]["title_source"])
        self.assertIsNone(self.db._conn.execute("SELECT value FROM kv WHERE key='title_source:s1'").fetchone())
        self.assertFalse(self.events)

    def test_failed_persistence_never_reports_or_applies_manual_rename(self):
        self.db.fail_after_callback = True
        result = self._write("不能假成功")
        self.db.fail_after_callback = False

        self.assertFalse(result["ok"])
        self.assertIn("写入失败", result["error"])
        self.assertEqual("旧名称", self.ns["_sessions"]["s1"]["title"])
        self.assertIsNone(self.db._conn.execute("SELECT value FROM kv WHERE key='title_source:s1'").fetchone())

    def test_auto_suffix_treats_sql_pattern_characters_as_literal_title_text(self):
        base = "RNA[1]_%?*"
        self.db._conn.execute("UPDATE sessions SET title = ? WHERE id = ?", (base, "s2"))
        self.db._conn.execute("INSERT INTO sessions (id, title) VALUES (?, ?)", ("s3", base + " #2"))
        self.db._conn.commit()

        result = self._write(base, "auto", allow_memory_fallback=True)

        self.assertTrue(result["ok"])
        self.assertEqual(base + " #3", result["title"])
        self.assertEqual(base + " #3", self.db._conn.execute("SELECT title FROM sessions WHERE id='s1'").fetchone()[0])

    def test_auto_write_respects_persisted_manual_source(self):
        self.db._conn.execute("INSERT INTO kv (key, value) VALUES (?, ?)", ("title_source:s1", "manual"))
        self.db._conn.commit()
        result = self._write("自动摘要名称", "auto", allow_memory_fallback=True)

        self.assertFalse(result["ok"])
        self.assertTrue(result["blocked"])
        self.assertEqual("旧名称", self.db._conn.execute("SELECT title FROM sessions WHERE id='s1'").fetchone()[0])
        self.assertEqual("manual", self.ns["_sessions"]["s1"]["title_source"])
        self.assertFalse(self.events)

    def test_intermediate_compression_manual_name_blocks_new_tip_auto_title(self):
        self.db._conn.execute(
            "INSERT INTO sessions (id, title, end_reason) VALUES (?, ?, ?)",
            ("root", "最初名称", "compression"),
        )
        self.db._conn.execute(
            "INSERT INTO sessions (id, title, parent_session_id, end_reason) VALUES (?, ?, ?, ?)",
            ("mid", "中间手动名称", "root", "compression"),
        )
        self.db._conn.execute(
            "INSERT INTO sessions (id, title, parent_session_id) VALUES (?, ?, ?)",
            ("tip", "最新续写", "mid"),
        )
        self.db._conn.execute("INSERT INTO kv (key, value) VALUES (?, ?)", ("title_source:mid", "manual"))
        self.db._conn.commit()
        self.ns["_sessions"]["tip"] = {"id": "tip", "title": "最新续写", "title_source": "auto"}

        result = self.ns["_set_session_title_with_source"](
            "tip", "不应覆盖", "auto", allow_memory_fallback=True
        )

        self.assertFalse(result["ok"])
        self.assertTrue(result["blocked"])
        self.assertEqual("最新续写", self.db._conn.execute("SELECT title FROM sessions WHERE id='tip'").fetchone()[0])
        self.assertEqual("manual", self.db._conn.execute("SELECT value FROM kv WHERE key='title_source:tip'").fetchone()[0])
        self.assertEqual("manual", self.ns["_sessions"]["tip"]["title_source"])

    def test_parallel_auto_and_manual_writes_leave_manual_title_authoritative(self):
        start = threading.Barrier(3)
        outcomes = []

        def auto_writer():
            start.wait()
            outcomes.append(self._write("自动标题", "auto", allow_memory_fallback=True))

        def manual_writer():
            start.wait()
            outcomes.append(self._write("并发手动名称", "manual"))

        auto_thread = threading.Thread(target=auto_writer)
        manual_thread = threading.Thread(target=manual_writer)
        auto_thread.start()
        manual_thread.start()
        start.wait()
        auto_thread.join(timeout=3)
        manual_thread.join(timeout=3)

        self.assertFalse(auto_thread.is_alive())
        self.assertFalse(manual_thread.is_alive())
        self.assertEqual(2, len(outcomes))
        self.assertEqual("并发手动名称", self.db._conn.execute("SELECT title FROM sessions WHERE id='s1'").fetchone()[0])
        self.assertEqual("manual", self.db._conn.execute("SELECT value FROM kv WHERE key='title_source:s1'").fetchone()[0])

    def test_title_source_helpers_use_sessiondb_lock_and_transaction(self):
        self.ns["_persist_title_source"]("s1", "manual")
        self.assertEqual("manual", self.ns["_load_title_source"]("s1"))

        source = SERVER.read_text(encoding="utf-8")
        persist_start = source.index("def _persist_title_source")
        load_start = source.index("def _load_title_source")
        resolve_start = source.index("def _resolve_title_source")
        self.assertIn("db._execute_write(_write)", source[persist_start:load_start])
        self.assertIn("with db_lock:", source[load_start:resolve_start])

    def test_source_routes_use_shared_writer_and_llm_rechecks_identity(self):
        source = SERVER.read_text(encoding="utf-8")
        self.assertGreaterEqual(source.count('_set_session_title_with_source('), 5)
        self.assertIn('if _sessions.get(sid) is not s:', source)
        self.assertIn('"source": result["source"]', source)


if __name__ == "__main__":
    unittest.main(verbosity=2)
