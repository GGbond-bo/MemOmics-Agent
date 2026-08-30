# -*- coding: utf-8 -*-
"""Pending-question tracker unit tests (2026-08-31)."""
import sqlite3
import sys
import os

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import server  # noqa: E402


def _make_db(tmp_path):
    db = tmp_path / "state.db"
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE messages (id INTEGER PRIMARY KEY, session_id TEXT, role TEXT, content TEXT)")
    conn.execute("INSERT INTO messages (session_id, role, content) VALUES (?, ?, ?)",
                ("s1", "assistant",
                 "...说明：把你的保守性评分挂在这篇原始文献上，审稿人是认的。需要我把这套解释整理进专利结论表的方法学部分吗？"))
    conn.commit()
    conn.close()
    return db


def test_detects_confirmed_pending_question(tmp_path, monkeypatch):
    db = _make_db(tmp_path)
    monkeypatch.setattr(server, "HERMES_HOME_DIR", str(tmp_path))
    ctx = server._build_pending_question_context({"id": "s1"}, "1.需要。 2.为什么你在电脑上做不了？")
    assert "待确认任务提醒" in ctx
    assert "整理进专利结论表" in ctx
    assert "用户已确认" in ctx


def test_no_acceptance_returns_empty(tmp_path, monkeypatch):
    _make_db(tmp_path)
    monkeypatch.setattr(server, "HERMES_HOME_DIR", str(tmp_path))
    ctx = server._build_pending_question_context({"id": "s1"}, "为什么你看不到我的文件？")
    assert ctx == ""


def test_negative_answer_returns_empty(tmp_path, monkeypatch):
    _make_db(tmp_path)
    monkeypatch.setattr(server, "HERMES_HOME_DIR", str(tmp_path))
    ctx = server._build_pending_question_context({"id": "s1"}, "不用了，先算了")
    assert ctx == ""
