# -*- coding: utf-8 -*-
"""数据读取配方（Read Recipes）测试：长会话"忘了怎么读文件"的确定性修复。

背景：上下文折叠（rollup/rebuild）与自检唤醒精简上下文都不保留历史工具调用
细节 → 多轮后模型不知道之前用什么命令/路径读取过文件 → 重新摸索或说"不能读取"。
修复：从 tool_calls_log 确定性提取"成功读取"的调用（含路径/参数），注入
折叠 checkpoint 与唤醒上下文。
"""
import os
import sqlite3
import sys
import tempfile

import pytest

pytestmark = pytest.mark.unit


@pytest.fixture(scope="module")
def server():
    import server as _s
    return _s


# ── 纯函数：_extract_read_recipes ───────────────────────────────────────────

def test_extract_keeps_successful_reads_only(server):
    rows = [
        # (tool_name, args_json, result_text, ts)
        ("execute_r", '{"code": "obj <- readRDS(\'E:/data/obj.rds\')"}',
         "[1] 2000 cells loaded OK", "08-24 10:00:00"),
        ("execute_r", '{"code": "df <- read.csv(\'E:/data/meta.csv\', sep=\'\\t\')"}',
         "[1] 340 rows", "08-24 10:05:00"),
        ("execute_r", '{"code": "df <- read.csv(\'E:/data/missing.csv\')"}',
         "Error in file: cannot open file 'E:/data/missing.csv': No such file", "08-24 10:06:00"),
        ("execute_python", '{"code": "import pandas as pd; df = pd.read_parquet(\'E:/data/x.parquet\')"}',
         "shape (1000, 30)", "08-24 10:10:00"),
        ("execute_r", '{"code": "obj2 <- CreateSeuratObject(counts = obj)"}',
         "[1] done", "08-24 10:12:00"),  # 非读取 → 排除
        ("execute_r", '{"code": "x <- 1 + 1"}', "[1] 2", "08-24 10:13:00"),  # 非读取 → 排除
    ]
    out = server._extract_read_recipes(rows, limit=5)
    assert "readRDS" in out
    assert "read.csv" in out
    assert "read_parquet" in out
    assert "missing.csv" not in out, "失败读取不得进入配方"
    assert "CreateSeuratObject" not in out, "非读取调用不得进入配方"
    assert out.startswith("[数据读取配方")


def test_extract_empty_and_limit(server):
    assert server._extract_read_recipes([]) == ""
    rows = [("execute_r", '{"code": "read.csv(\'%d.csv\')"}' % i, "ok", f"t{i}") for i in range(10)]
    out = server._extract_read_recipes(rows, limit=3)
    assert out.count("- [t") == 3, "limit=3 只保留 3 条"
    # 全部失败 → 空
    bad = [("execute_r", '{"code": "read.csv(\'x\')"}', "Error: 失败", "t1")]
    assert server._extract_read_recipes(bad) == ""


def test_extract_case_and_cjk_failure_markers(server):
    rows = [
        ("execute_r", '{"code": "readRDS(\'x\')"}', "Error: 文件不存在", "t1"),
        ("execute_r", '{"code": "read.table(\'y\')"}', "Cannot open file", "t2"),  # 大写 C
        ("execute_r", '{"code": "read.table(\'z\')"}', "loaded 5 rows", "t3"),
    ]
    out = server._extract_read_recipes(rows)
    assert "'z'" in out and "'x'" not in out and "'y'" not in out


# ── 查库：_build_read_recipes（临时 sqlite）─────────────────────────────────

def test_build_read_recipes_from_db(server):
    with tempfile.TemporaryDirectory() as td:
        dbp = os.path.join(td, "state.db")
        conn = sqlite3.connect(dbp)
        conn.execute("CREATE TABLE tool_calls_log (id INTEGER PRIMARY KEY AUTOINCREMENT, "
                     "session_id TEXT, tool_name TEXT, args_json TEXT, result_text TEXT, "
                     "timestamp REAL)")
        conn.execute("INSERT INTO tool_calls_log (session_id, tool_name, args_json, result_text, timestamp) "
                     "VALUES ('sess-1', 'execute_r', '{\"code\": \"a <- readRDS(\\\"E:/d/obj.rds\\\")\"}', "
                     "'loaded 1000 cells', 1756000000)")
        conn.execute("INSERT INTO tool_calls_log (session_id, tool_name, args_json, result_text, timestamp) "
                     "VALUES ('sess-1', 'execute_r', '{\"code\": \"read.csv(\\\"bad\\\")\"}', "
                     "'Error: No such file', 1756000100)")
        conn.execute("INSERT INTO tool_calls_log (session_id, tool_name, args_json, result_text, timestamp) "
                     "VALUES ('sess-2', 'execute_r', '{\"code\": \"read.csv(\\\"other\\\")\"}', 'ok', 1756000200)")
        conn.commit()
        conn.close()

        sess = {"id": "sess-1"}
        out = server._build_read_recipes(sess, db_path=dbp)
        assert "readRDS" in out and "E:/d/obj.rds" in out
        assert "bad" not in out, "失败读取不得进配方"
        assert "other" not in out, "其他会话的记录不得混入"
        # 未知会话 → 空
        assert server._build_read_recipes({"id": "nope"}, db_path=dbp) == ""
        # 无 db → 空
        assert server._build_read_recipes({"id": "sess-1"}, db_path=os.path.join(td, "x.db")) == ""


# ── 接线：唤醒上下文尾部含配方 ──────────────────────────────────────────────

def test_wake_history_appends_read_recipes(server, monkeypatch):
    monkeypatch.setattr(server, "_build_read_recipes",
                        lambda s, db_path=None, limit_rows=40:
                        "[数据读取配方 · 此前成功读取文件的命令]\n- readRDS(...)")
    sess = {"id": "s-x", "results_dir": "", "messages": [
        {"role": "user", "content": "读一下数据"},
        {"role": "assistant", "content": "已读取 1000 细胞"},
    ]}
    hist = server._build_self_check_wake_history(sess)
    assert any(m.get("role") == "system" and "数据读取配方" in m.get("content", "")
               for m in hist), "唤醒上下文必须带读取配方"
    # 无配方时（真实 DB 查不到）不炸、无配方块
    monkeypatch.setattr(server, "_build_read_recipes", lambda *a, **k: "")
    hist2 = server._build_self_check_wake_history(sess)
    assert not any("数据读取配方" in m.get("content", "") for m in hist2)


# ── 接线：折叠 checkpoint 含配方 ────────────────────────────────────────────

def test_rollup_checkpoint_appends_read_recipes(server, monkeypatch):
    monkeypatch.setattr(server, "_extract_read_recipes",
                        lambda rows, limit=5, max_chars=1200:
                        "[数据读取配方 · 此前成功读取文件的命令]\n- read.csv('E:/meta.csv')")
    sess = {"id": "s-y", "results_dir": "", "todos": []}
    head = [{"role": "user", "content": "msg %d" % i} for i in range(5)]
    cp = server._build_rollup_checkpoint(sess, head)
    assert "数据读取配方" in cp, "折叠 checkpoint 必须保留读取配方"
    # 无配方 → 正常 checkpoint 不崩
    monkeypatch.setattr(server, "_extract_read_recipes", lambda *a, **k: "")
    cp2 = server._build_rollup_checkpoint(sess, head)
    assert "数据读取配方" not in cp2 and "会话检查点" in cp2
