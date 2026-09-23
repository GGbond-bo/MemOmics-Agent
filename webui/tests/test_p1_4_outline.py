# -*- coding: utf-8 -*-
"""P1-4 回归：会话大纲（一轮 = 一条提问 + 它之后的回答，可点跳转）。

覆盖五层：
A 纯函数（摘要清洗、轮次切分、过滤规则、角标统计）
B 接口（GET /api/sessions/{sid}/outline、messages 里的 turn 字段）
C 一致性（目录轮次号 == messages 轮次号，跳转才对得上）
D 前端接线静态守卫（DOM 挂轮次、目录渲染、跳转、滚动高亮、转义）
E 极端输入（几百轮、十万字提问、超长会话、并发、脏数据）
"""
import json
import threading
import time

import pytest

import server
from conftest import cleanup_session


def _seed(sid, msgs):
    """把消息塞进会话内存（等价于真实跑过这些对话，但不触发模型）"""
    sess = server._sessions[sid]
    sess["messages"] = msgs
    sess["_messages_loaded"] = True
    sess["_msg_count"] = len(msgs)
    return sess


def _u(text, **kw):
    m = {"role": "user", "content": text, "time": "10:00:00"}
    m.update(kw)
    return m


def _a(text, **kw):
    m = {"role": "assistant", "content": text, "time": "10:00:01"}
    m.update(kw)
    return m


# --- A. 纯函数 --------------------------------------------------------------

def test_title_takes_first_meaningful_line():
    assert server._outline_title("\n\n  帮我看下这批数据  \n还有别的") == "帮我看下这批数据"
    assert server._outline_title("## 标题行\n正文") == "标题行"
    assert server._outline_title("") == ""
    assert server._outline_title(None) == ""


def test_title_strips_markdown_noise_and_collapses_space():
    t = server._outline_title("看 [这个文件](https://example.org/x) 和 ![图](a.png) 还有 `code`")
    assert "https://example.org" not in t
    assert "这个文件" in t
    assert "a.png" not in t
    assert "`" not in t
    assert server._outline_title("a\r\n\r\nb") == "a"
    assert server._outline_title("多   个\t空格") == "多 个 空格"


def test_title_truncates_and_respects_custom_limit():
    long_line = "很" * 500
    assert len(server._outline_title(long_line)) == server._OUTLINE_TITLE_CHARS
    assert len(server._outline_title(long_line, 10)) == 10


def test_title_keeps_dangerous_text_raw_escaping_is_frontend_job():
    raw = "<script>alert(1)</script> 提问"
    assert server._outline_title(raw) == raw[:server._OUTLINE_TITLE_CHARS]


def test_visible_msgs_filters_system_tool_and_inject():
    sess = {"messages": [
        _u("正常提问"),
        {"role": "system", "content": "系统提示"},
        {"role": "tool", "content": "工具输出"},
        _u("[会话要求] 注入的脚手架"),
        _u("[系统唤醒] 自检"),
        _a("回答"),
    ]}
    vis = server._outline_visible_msgs(sess)
    assert [m["role"] for m in vis] == ["user", "assistant"]
    assert vis[0]["content"] == "正常提问"


def test_outline_groups_turns_and_counts_answers():
    sess = {"messages": [
        _a("开场白：还没有提问"),
        _u("第一问"),
        _a("第一答 A", tool_count=2),
        _a("第一答 B", tool_count=1),
        _u("第二问"),
    ]}
    out = server._session_outline(sess)
    assert out["leading"] == 1                       # 开场白不算一轮
    assert out["total_turns"] == 2
    t1, t2 = out["turns"]
    assert t1["turn"] == 1 and t1["question"] == "第一问"
    assert t1["answers"] == 2 and t1["tools"] == 3
    assert t1["answer_head"].startswith("第一答 A")
    assert t1["chars"] == len("第一答 A") + len("第一答 B")
    assert t2["answers"] == 0 and t2["answer_head"] == ""   # 还没回答的轮次也在目录里


def test_outline_counts_citation_anchors_per_turn():
    sess = {"messages": [
        _u("找证据"),
        _a("见 [KB源:a.yaml] 与 [DOI:10.1038/s41586-020-2649-2]；还有 [仅是推理]"),
    ]}
    out = server._session_outline(sess)
    assert out["turns"][0]["anchors"] == 3


def test_outline_survives_dirty_message_shapes():
    sess = {"messages": [
        {"role": "user", "content": None},
        {"role": "assistant", "content": 12345},
        {"role": "assistant"},                        # 连 content 都没有
        _u("正常"),
        _a("正常答", tool_count="不是数字"),           # 脏元数据不能炸
    ]}
    out = server._session_outline(sess)
    assert out["total_turns"] == 2                    # None 提问也算一轮（内容为空）
    assert out["turns"][1]["question"] == "正常"
    assert out["turns"][1]["tools"] == 0


def test_outline_turn_cap_keeps_recent_and_reports_hidden(monkeypatch):
    monkeypatch.setattr(server, "_OUTLINE_MAX_TURNS", 3)
    sess = {"messages": []}
    for i in range(1, 8):
        sess["messages"].append(_u("第%d问" % i))
        sess["messages"].append(_a("第%d答" % i))
    out = server._session_outline(sess)
    assert out["total_turns"] == 7
    assert out["truncated"] is True and out["hidden_turns"] == 4
    assert [t["turn"] for t in out["turns"]] == [5, 6, 7]     # 留最近几轮，编号仍是真的


def test_outline_scan_window_limits_work(monkeypatch):
    monkeypatch.setattr(server, "_OUTLINE_SCAN_MSGS", 4)
    msgs = []
    for i in range(1, 11):
        msgs.append(_u("第%d问" % i))
        msgs.append(_a("第%d答" % i))
    out = server._session_outline({"messages": msgs})
    assert out["total_turns"] == 2                    # 只扫最后 4 条 = 最近 2 轮


# --- B. 接口 ----------------------------------------------------------------

def test_outline_endpoint_404_for_unknown_session(client):
    r = client.get("/api/sessions/no-such-p14-outline/outline")
    assert r.status_code == 404


def test_outline_endpoint_empty_session(client, new_session):
    r = client.get("/api/sessions/%s/outline" % new_session)
    assert r.status_code == 200
    d = r.json()
    assert d["ok"] is True and d["turns"] == []
    assert d["total_turns"] == 0 and d["truncated"] is False


def test_outline_endpoint_returns_real_turns(client, new_session):
    _seed(new_session, [
        _u("帮我做 QC"),
        _a("好的，先看数据 [KB源:x.yaml]"),
        _u("换一批数据"),
        _a("已切换"),
    ])
    d = client.get("/api/sessions/%s/outline" % new_session).json()
    assert d["total_turns"] == 2
    assert d["turns"][0]["question"] == "帮我做 QC"
    assert d["turns"][0]["answers"] == 1
    assert d["turns"][0]["anchors"] == 1
    assert d["turns"][1]["question"] == "换一批数据"
    assert isinstance(d["turns"][0]["turn"], int)


def test_messages_endpoint_carries_turn_numbers(client, new_session):
    _seed(new_session, [
        _a("开场白"),
        _u("第一问"), _a("第一答"),
        _u("第二问"), _a("第二答"), _a("补充"),
    ])
    d = client.get("/api/sessions/%s/messages" % new_session).json()
    turns = [(m["role"], m["turn"]) for m in d["messages"]]
    assert turns == [("assistant", 0), ("user", 1), ("assistant", 1),
                     ("user", 2), ("assistant", 2), ("assistant", 2)]


def test_messages_turn_matches_outline_turns(client, new_session):
    """前端靠 messages.turn 挂 DOM、靠 outline.turn 做目录，两边必须对得上。"""
    _seed(new_session, [_u("甲"), _a("甲答"), _u("乙"), _a("乙答"), _u("丙")])
    msgs = client.get("/api/sessions/%s/messages" % new_session).json()["messages"]
    out = client.get("/api/sessions/%s/outline" % new_session).json()
    user_turns = [m["turn"] for m in msgs if m["role"] == "user"]
    assert user_turns == [1, 2, 3]
    assert [t["turn"] for t in out["turns"]] == user_turns
    for m in msgs:
        if m["role"] == "user":
            hit = [t for t in out["turns"] if t["turn"] == m["turn"]]
            assert hit and hit[0]["question"] == m["content"]


def test_outline_endpoint_hides_inject_messages(client, new_session):
    _seed(new_session, [_u("[会话要求] 系统塞的"), _a("回答"), _u("真实提问"), _a("真实答")])
    d = client.get("/api/sessions/%s/outline" % new_session).json()
    assert d["total_turns"] == 1
    assert d["turns"][0]["question"] == "真实提问"


# --- C. 前端接线静态守卫 -----------------------------------------------------

def _fe():
    import os
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(root, "index.html"), "r", encoding="utf-8") as f:
        return f.read()


def test_panel_has_outline_section():
    html = _fe()
    assert 'id="outline-list"' in html
    assert 'id="outline-count"' in html
    assert "会话大纲" in html
    assert "'outline':'会话大纲'" in html and "'outline':'Chat Outline'" in html


def test_message_renderers_attach_turn():
    html = _fe()
    assert "function addUserMsg(text, imageUrls, turn)" in html
    assert "_registerTurnEl(div, (turn && turn > 0) ? turn : (_turnSeq + 1), 'user');" in html
    assert "_registerTurnEl(div, (meta && meta.turn && meta.turn > 0) ? meta.turn : _turnSeq, 'assistant');" in html
    # 历史回放要把后端的 turn 传下去
    assert "addUserMsg(m.content, null, m.turn);" in html
    # 开场白（还没有提问）不能算成第 1 轮
    assert "if (t < 1) t = 0;" in html


def test_outline_render_and_jump_are_wired():
    html = _fe()
    for frag in ("function refreshOutline()", "function jumpToTurn(turn)", "function _outlineTurns()",
                 "function _markActiveTurn()", "function _syncActiveTurnFromScroll()"):
        assert frag in html, frag
    assert "onclick=\"jumpToTurn(' + item.turn + ')\"" in html
    assert "if (typeof refreshOutline === 'function') refreshOutline();" in html
    # 跳转要停掉自动滚动，否则流式输出会把用户拽回底部
    jump = html.split("function jumpToTurn(turn)")[1].split("function _markActiveTurn")[0]
    assert "_autoScroll = false;" in jump
    assert "scrollIntoView" in jump
    assert "turn-flash" in jump


def test_outline_render_escapes_text():
    html = _fe()
    blk = html.split("function refreshOutline()")[1].split("function jumpToTurn(")[0]
    assert "escapeHtml(q || '（无提问）')" in blk
    assert "escapeHtml(a.length > 90" in blk
    # 摘要不能裸拼进 innerHTML
    assert ">'+ q +" not in blk and ">'+ a +" not in blk


def test_outline_css_present():
    html = _fe()
    assert "#outline-list .out-row.active" in html
    assert ".message.turn-flash .bubble" in html
    assert "@keyframes turnFlash" in html
    assert "#outline-list .out-title" in html


# --- D. 极端输入 ------------------------------------------------------------

def test_huge_question_is_truncated_and_fast(client, new_session):
    _seed(new_session, [_u("巨" * 100000), _a("答")])
    t0 = time.time()
    d = client.get("/api/sessions/%s/outline" % new_session).json()
    dt = time.time() - t0
    assert len(d["turns"][0]["question"]) == server._OUTLINE_TITLE_CHARS
    assert dt < 5, dt


def test_hundreds_of_turns_through_http(client, new_session):
    msgs = []
    for i in range(1, 501):
        msgs.append(_u("第%d问" % i))
        msgs.append(_a("第%d答" % i))
    _seed(new_session, msgs)
    d = client.get("/api/sessions/%s/outline" % new_session).json()
    assert d["total_turns"] == 500
    assert len(d["turns"]) == server._OUTLINE_MAX_TURNS
    assert d["truncated"] is True
    assert d["turns"][-1]["turn"] == 500


def test_very_long_session_hits_scan_window(client, new_session):
    msgs = []
    for i in range(1, 3000):
        msgs.append(_u("问%d" % i))
        msgs.append(_a("答%d" % i))
    _seed(new_session, msgs)
    t0 = time.time()
    d = client.get("/api/sessions/%s/outline" % new_session).json()
    assert time.time() - t0 < 10
    assert d["total_turns"] == server._OUTLINE_SCAN_MSGS // 2      # 只扫窗口内的消息
    assert d["turns"][-1]["turn"] == min(2999, server._OUTLINE_SCAN_MSGS // 2)


def test_concurrent_outline_reads_are_consistent(client, new_session):
    _seed(new_session, [_u("并发问%d" % i) if i % 2 == 0 else _a("并发答%d" % i) for i in range(1, 41)])
    results, errors = [], []

    def worker():
        try:
            results.append(client.get("/api/sessions/%s/outline" % new_session).json())
        except Exception as e:                                  # pragma: no cover
            errors.append(repr(e))

    ths = [threading.Thread(target=worker) for _ in range(8)]
    [t.start() for t in ths]
    [t.join() for t in ths]
    assert not errors
    assert len(results) == 8
    sig = {(r["total_turns"], tuple(t["question"] for t in r["turns"])) for r in results}
    assert len(sig) == 1


def test_outline_question_with_emoji_and_newlines(client, new_session):
    _seed(new_session, [_u("🧬 单细胞\n\n第二行\t带制表符"), _a("收到")])
    d = client.get("/api/sessions/%s/outline" % new_session).json()
    assert d["turns"][0]["question"] == "🧬 单细胞"
