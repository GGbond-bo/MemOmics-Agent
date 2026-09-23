# -*- coding: utf-8 -*-
"""P1-2 回归：改动复核（跑前跑后快照 + unified diff + 单文件回滚）。

设计来源（照抄形状、不照抄实现）：
  · deer-flow 的 WorkspaceFileChange（workspace_changes/types.py:63-116）给了字段形状
    path/change_type/lines_added/lines_removed/sha，:18-26 给了体积上限，api.py:18-48
    是「轻量列表 + 完整内容分两次取」。
  · deer-flow 没有的部分是自己设计的：单文件回滚 + sha 一致性闸门 + 跳过项也要可见。

本文件既测纯函数（diff/读取/路径解析），也走真实 HTTP 端点（列表/详情/回滚），
并用真实文件系统（临时目录 + 会话 results_dir）而非 mock。
"""
import json
import os
import re
import uuid

import pytest

import server
from conftest import cleanup_session


def _cleanup_kv(sid):
    """清掉本测试写进 state.db kv 表的改动记录行。"""
    server._kv_set(server._kv_ns("changes", sid), "")


def _unit_session(tmpdir):
    """不起会话服务的最小 session（够 _session_emit 用）。"""
    return {
        "id": "p1_2_unit_" + uuid.uuid4().hex[:8],
        "results_dir": str(tmpdir),
        "messages": [],
        "progress_log": [],
        "todos": [],
    }


def _do_write(sess, path, content, tool="write_file"):
    """走真实两段钩子：执行前抓快照 → 写文件 → 执行后结算。"""
    args = {"path": path}
    server._snapshot_before_change(sess, tool, args)
    d = os.path.dirname(path)
    if d:
        os.makedirs(d, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(content)
    return server._finalize_file_change(sess, tool, args)


# --- A. 纯函数 -------------------------------------------------------------

def test_change_path_from_args_variants():
    assert server._change_path_from_args({"path": " a.py "}) == "a.py"
    assert server._change_path_from_args({"file_path": '"b.py"'}) == "b.py"
    assert server._change_path_from_args({"file": "c.py"}) == "c.py"
    assert server._change_path_from_args({"filename": "d.py"}) == "d.py"
    assert server._change_path_from_args({"target": "e.py"}) == "e.py"
    # 没有路径参数 → 空串（不记改动）
    assert server._change_path_from_args({"command": "ls"}) == ""
    assert server._change_path_from_args(None) == ""


def test_read_text_for_change_kinds(tmpdir):
    p = os.path.join(str(tmpdir), "x.txt")
    assert server._read_text_for_change(p)[0] == "missing"
    with open(p, "w", encoding="utf-8") as f:
        f.write("中文内容\n")
    kind, text = server._read_text_for_change(p)
    assert kind == "exists" and "中文内容" in text
    # 目录 → 当成不可读
    assert server._read_text_for_change(str(tmpdir))[0] == "binary"
    # 二进制（含 NUL）
    b = os.path.join(str(tmpdir), "bin.dat")
    with open(b, "wb") as f:
        f.write(b"\x00\x01\x02PNG")
    assert server._read_text_for_change(b)[0] == "binary"
    # 超大（真写 300KB）
    big = os.path.join(str(tmpdir), "big.txt")
    with open(big, "w", encoding="utf-8") as f:
        f.write("A" * (server._CHANGE_MAX_FILE_BYTES + 1024))
    assert server._read_text_for_change(big)[0] == "toolarge"


def test_unified_diff_counts_and_truncation():
    diff, added, removed, trunc = server._unified_diff_text("m.py", "a=1\n", "a=1\nb=2\nc=3\n")
    assert added == 2 and removed == 0 and trunc is False
    assert "-a=1" not in diff and "+b=2" in diff

    # 极端：一次改 500 行 → diff 截断到上限
    before = "".join(f"line{i}\n" for i in range(500))
    after = "".join(f"LINE{i}\n" for i in range(500))
    diff2, added2, removed2, trunc2 = server._unified_diff_text("big.py", before, after)
    assert trunc2 is True
    assert len(diff2.splitlines()) <= server._CHANGE_MAX_DIFF_LINES
    # 计数是截断前统计的（否则会误导用户"只改了 400 行"）
    assert added2 > server._CHANGE_MAX_DIFF_LINES and removed2 > server._CHANGE_MAX_DIFF_LINES


def test_unified_diff_crlf_and_missing_trailing_newline():
    crlf_before = "a=1\r\nb=2\r\n"
    crlf_after = "a=1\r\nb=3\r\n"
    diff, added, removed, _ = server._unified_diff_text("c.py", crlf_before, crlf_after)
    assert added == 1 and removed == 1
    # 末行无换行也不炸
    diff2, _, _, _ = server._unified_diff_text("d.py", "x=1", "x=2")
    assert "+x=2" in diff2


def test_sha12_chinese_and_none():
    assert server._sha12(None) == ""
    assert len(server._sha12("中文")) == 12
    assert server._sha12("中文") != server._sha12("中文 ")


# --- B. 记录周期（真实文件） ------------------------------------------------

def test_new_file_records_added(tmpdir):
    sess = _unit_session(tmpdir)
    p = os.path.join(str(tmpdir), "scripts", "qc.py")
    rec = _do_write(sess, p, "print('hi')\n")
    assert rec is not None
    assert rec["status"] == "added"
    assert rec["added"] == 1 and rec["removed"] == 0
    assert rec["revertible"] is True
    assert rec["sha_before"] == "" and len(rec["sha_after"]) == 12
    assert rec["rel_path"].replace("\\", "/") == "scripts/qc.py"
    assert rec["preview"], "轻量列表要带预览行"
    assert "hi" in rec["diff"]


def test_modify_file_records_modified(tmpdir):
    sess = _unit_session(tmpdir)
    p = os.path.join(str(tmpdir), "a.txt")
    _do_write(sess, p, "one\ntwo\n")
    rec = _do_write(sess, p, "one\nTWO\nthree\n")
    assert rec["status"] == "modified"
    assert rec["added"] == 2 and rec["removed"] == 1
    assert len(sess["changes"]) == 2


def test_rewrite_identical_content_no_record(tmpdir):
    sess = _unit_session(tmpdir)
    p = os.path.join(str(tmpdir), "same.txt")
    _do_write(sess, p, "same\n")
    assert _do_write(sess, p, "same\n") is None
    assert len(sess["changes"]) == 1


def test_deleted_file_records_deleted(tmpdir):
    sess = _unit_session(tmpdir)
    p = os.path.join(str(tmpdir), "gone.txt")
    _do_write(sess, p, "bye\n")
    args = {"path": p}
    server._snapshot_before_change(sess, "write_file", args)
    os.remove(p)
    rec = server._finalize_file_change(sess, "write_file", args)
    assert rec["status"] == "deleted"
    assert rec["removed"] == 1


def test_skips_binary_oversize_and_cache_dirs(tmpdir):
    sess = _unit_session(tmpdir)
    # __pycache__ 直接跳过
    assert _do_write(sess, os.path.join(str(tmpdir), "__pycache__", "m.pyc"), "x") is None
    # 二进制
    b = os.path.join(str(tmpdir), "fig.png")
    args = {"path": b}
    server._snapshot_before_change(sess, "write_file", args)
    with open(b, "wb") as f:
        f.write(b"\x00\x89PNG")
    assert server._finalize_file_change(sess, "write_file", args) is None
    # 超大
    big = os.path.join(str(tmpdir), "big.h5ad")
    args2 = {"path": big}
    server._snapshot_before_change(sess, "write_file", args2)
    with open(big, "w", encoding="utf-8") as f:
        f.write("A" * (server._CHANGE_MAX_FILE_BYTES + 10))
    assert server._finalize_file_change(sess, "write_file", args2) is None

    assert not sess.get("changes"), "跳过的文件不该产生改动记录"
    reasons = {s["reason"] for s in sess["_changes_skipped"]}
    assert any("缓存" in r for r in reasons), reasons
    assert any("二进制" in r for r in reasons), reasons
    assert any("KB" in r for r in reasons), reasons


def test_non_writer_tool_not_recorded(tmpdir):
    sess = _unit_session(tmpdir)
    p = os.path.join(str(tmpdir), "read.txt")
    with open(p, "w", encoding="utf-8") as f:
        f.write("z")
    server._snapshot_before_change(sess, "read_file", {"path": p})
    assert server._finalize_file_change(sess, "read_file", {"path": p}) is None
    assert not sess.get("changes")


def test_cap_keeps_newest_200(tmpdir, monkeypatch):
    """极端：一次分析改 210 个文件 → 只留最近 200 条，且留的是最新的。"""
    sess = _unit_session(tmpdir)
    p = os.path.join(str(tmpdir), "loop.txt")
    for i in range(server._CHANGE_MAX_KEEP + 10):
        _do_write(sess, p, f"v{i}\n")
    assert len(sess["changes"]) == server._CHANGE_MAX_KEEP
    assert sess["changes"][-1]["diff"].strip().endswith("+v209")


# --- C. HTTP 端点 ----------------------------------------------------------

def test_changes_endpoints_roundtrip(client, new_session):
    sid = new_session
    sess = server._sessions[sid]
    try:
        r = client.get(f"/api/sessions/{sid}/changes")
        assert r.status_code == 200
        assert r.json()["summary"]["changes"] == 0

        p = os.path.join(sess["results_dir"], "scripts", "step1.py")
        rec = _do_write(sess, p, "print(1)\n")
        r = client.get(f"/api/sessions/{sid}/changes")
        body = r.json()
        assert body["summary"]["changes"] == 1 and body["summary"]["files"] == 1
        assert body["summary"]["added"] == 1
        item = body["changes"][0]
        # 轻量列表刻意不下发 diff，也不许泄漏内部字段
        assert "diff" not in item
        assert not any(k.startswith("_") for k in item)
        assert "_before_text" not in r.text
        assert item["preview"]

        r2 = client.get(f"/api/sessions/{sid}/changes/{rec['id']}")
        assert r2.status_code == 200
        detail = r2.json()["change"]
        assert "print(1)" in detail["diff"]
        assert "_before_text" not in r2.text
    finally:
        _cleanup_kv(sid)
        cleanup_session(sid)


def test_revert_restores_before_content(client, new_session):
    sid = new_session
    sess = server._sessions[sid]
    try:
        p = os.path.join(sess["results_dir"], "cfg.yaml")
        _do_write(sess, p, "lr: 0.1\n")
        rec = _do_write(sess, p, "lr: 0.9\n")
        r = client.post(f"/api/sessions/{sid}/changes/{rec['id']}/revert")
        assert r.status_code == 200, r.text
        with open(p, encoding="utf-8") as f:
            assert f.read() == "lr: 0.1\n"
        # 回滚过的不允许再回滚（避免把后续编辑当成本次改动覆盖）
        assert client.post(f"/api/sessions/{sid}/changes/{rec['id']}/revert").status_code == 409
        item = [c for c in client.get(f"/api/sessions/{sid}/changes").json()["changes"] if c["id"] == rec["id"]][0]
        assert item["status"] == "reverted" and item["revertible"] is False
    finally:
        _cleanup_kv(sid)
        cleanup_session(sid)


def test_revert_refuses_to_clobber_later_edits(client, new_session):
    """安全闸：改动之后别人又改过这个文件 → 拒绝回滚，绝不覆盖。"""
    sid = new_session
    sess = server._sessions[sid]
    try:
        p = os.path.join(sess["results_dir"], "shared.py")
        _do_write(sess, p, "v1\n")
        rec = _do_write(sess, p, "v2\n")
        with open(p, "w", encoding="utf-8") as f:
            f.write("v3-别人改的\n")
        r = client.post(f"/api/sessions/{sid}/changes/{rec['id']}/revert")
        assert r.status_code == 409
        assert "又被修改" in r.json()["error"]
        with open(p, encoding="utf-8") as f:
            assert f.read() == "v3-别人改的\n", "拒绝回滚时绝不能动文件"
    finally:
        _cleanup_kv(sid)
        cleanup_session(sid)


def test_revert_added_file_deletes_it(client, new_session):
    sid = new_session
    sess = server._sessions[sid]
    try:
        p = os.path.join(sess["results_dir"], "tmp_new.py")
        rec = _do_write(sess, p, "print(1)\n")
        assert os.path.exists(p)
        r = client.post(f"/api/sessions/{sid}/changes/{rec['id']}/revert")
        assert r.status_code == 200 and r.json()["restored"] is False
        assert not os.path.exists(p), "改动前不存在的文件，回滚 = 删除"
    finally:
        _cleanup_kv(sid)
        cleanup_session(sid)


def test_revert_outside_allowed_root_403(client, new_session):
    """伪造一条仓库外的改动记录 → 即使 sha 对得上也必须 403。"""
    sid = new_session
    sess = server._sessions[sid]
    try:
        outside = os.path.join(os.environ.get("TEMP", str(sess["results_dir"])), "p1_2_outside.txt")
        with open(outside, "w", encoding="utf-8") as f:
            f.write("after\n")
        rec = {"id": "chg_forged", "path": outside, "status": "modified",
               "sha_after": server._sha12("after\n"), "revertible": True,
               "_before_text": "before\n", "_before_exists": True}
        sess.setdefault("changes", []).append(rec)
        r = client.post(f"/api/sessions/{sid}/changes/chg_forged/revert")
        assert r.status_code == 403
        with open(outside, encoding="utf-8") as f:
            assert f.read() == "after\n"
    finally:
        _cleanup_kv(sid)
        cleanup_session(sid)


def test_changes_404s(client, new_session):
    sid = new_session
    try:
        assert client.get(f"/api/sessions/{sid}/changes/chg_nope").status_code == 404
        assert client.post(f"/api/sessions/{sid}/changes/chg_nope/revert").status_code == 404
        assert client.get("/api/sessions/p1-2-nope/changes").status_code == 404
        assert client.post("/api/sessions/p1-2-nope/changes/x/revert").status_code == 404
    finally:
        _cleanup_kv(sid)
        cleanup_session(sid)


def test_changes_survive_restart_but_not_revertible(client, new_session):
    """重启（内存丢）后：列表仍能复核，但只能看不能回滚——诚实降级。"""
    sid = new_session
    sess = server._sessions[sid]
    try:
        p = os.path.join(sess["results_dir"], "keep.py")
        _do_write(sess, p, "x=1\n")
        rec = _do_write(sess, p, "x=2\n")
        blob = client.get(f"/api/sessions/{sid}/changes").json()
        assert blob["summary"]["changes"] == 2

        # 模拟进程重启：清掉内存里的记录与改前全文
        sess["changes"] = []
        r = client.get(f"/api/sessions/{sid}/changes")
        body = r.json()
        assert body["summary"]["changes"] == 2, "重启后仍应能从 state.db 读回"
        assert all(c["revertible"] is False for c in body["changes"])
        assert all(c.get("restored") for c in body["changes"])
        assert client.post(f"/api/sessions/{sid}/changes/{rec['id']}/revert").status_code == 409
    finally:
        _cleanup_kv(sid)
        cleanup_session(sid)


def test_persisted_blob_is_metadata_only(client, new_session):
    """落库体积：kv 里只有元数据 + diff，没有改前全文（diff 里出现被删行是 diff 的职责）。

    极端用例：改前 3000 行、只改 1 行 → 落库体积必须远小于原文件，
    否则一个大会话能把 state.db 撑爆。
    """
    sid = new_session
    sess = server._sessions[sid]
    try:
        p = os.path.join(sess["results_dir"], "big.py")
        before = "".join(f"SECRET_LINE_{i} = {i}\n" for i in range(3000))
        after = before.replace("SECRET_LINE_2999 = 2999", "SECRET_LINE_2999 = -1")
        _do_write(sess, p, before)
        _do_write(sess, p, after)
        raw = server._kv_get(server._kv_ns("changes", sid))
        assert raw, "应已落库"
        parsed = json.loads(raw)
        assert parsed["schema"] == "memomics.changes/1"
        assert "_before_text" not in raw
        assert len(raw) <= server._CHANGE_MAX_STORE_BYTES
        # 只改了 1 行 → 上下文各 3 行，落库文本必须远小于 3000 行的原文
        assert len(raw) < len(before) / 5, f"落库 {len(raw)}B vs 原文 {len(before)}B"
        assert not any(k.startswith("_") for k in parsed["changes"][-1])
    finally:
        _cleanup_kv(sid)
        cleanup_session(sid)

# --- D. 前端接线（静态守卫） -----------------------------------------------
# 后端对了但前端没接上 = 用户看不到，所以这一节把「接线」本身也当契约测。

def _index_html():
    p = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "index.html")
    with open(p, encoding="utf-8") as f:
        return f.read()


def test_frontend_change_review_wired():
    html = _index_html()
    for need in ('id="changes-list"', 'id="changes-summary"', 'id="change-overlay"',
                 'id="chg-ov-diff"', 'id="chg-ov-revert"'):
        assert need in html, f"缺少 {need}"
    for fn in ("async function refreshChanges()", "function renderChanges(", "function _renderDiffHtml(",
               "async function openChangeDiff(", "async function revertChange()", "function closeChangeDiff()",
               "function _chgStatusText("):
        assert fn in html, f"缺少 {fn}"
    # 三条真实数据通道必须都接上：WS 推送 / 会话切换与初始化 / 回滚接口
    assert "msg.type === 'changes_update'" in html
    assert "refreshTodos(); refreshChanges();" in html
    assert "/changes/' + c.id + '/revert'" in html
    assert "/api/sessions/' + currentSid + '/changes/'" in html
    # 会话切换丢弃过期响应（避免串台）
    assert "d.session_id !== currentSid" in html
    # diff 四类着色：CSS 选择器 + JS 产出的类名都要在（只写 CSS 或只写 JS 都不算接上）
    for sel in (".chg-line.add", ".chg-line.del", ".chg-line.hunk", ".chg-line.hdr"):
        assert sel in html, f"缺少样式 {sel}"
    assert "'<div class=\"chg-line ' + cls + '\">'" in html, "缺少 diff 行渲染"
    for cls in ("cls = 'add'", "cls = 'del'", "cls = 'hunk'", "cls = 'hdr'"):
        assert cls in html, f"缺少分类 {cls}"


def test_hooks_wired_into_agent_loop():
    """守卫：两个钩子必须真的挂在**每一条** agent 通道上（否则功能等于没接）。

    只测纯函数不够——之前的教训就是"函数写好了但没人调"（死分支 bug）。
    主通道（WebUI /ws）与微信通道各有一条 tool_start/tool_complete 推送，
    漏掉任何一条，那条通道里产生的文件改动就不会被记录。
    """
    p = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "server.py")
    with open(p, encoding="utf-8") as f:
        src = f.read()
    starts = [m.start() for m in re.finditer(r'"type": "tool_start"', src)]
    completes = [m.start() for m in re.finditer(r'"type": "tool_complete"', src)]
    assert len(starts) >= 2 and len(completes) >= 2, "agent 通道数量变了，请重新核对钩子"
    for i in starts:
        assert "_snapshot_before_change(" in src[i:i + 1200], "某条 tool_start 通道没抓改前快照"
    for i in completes:
        assert "_finalize_file_change(" in src[i:i + 1800], "某条 tool_complete 通道没结算 diff"


def test_finalize_without_args_batches_pending(tmpdir):
    """微信通道的 complete 回调不带 args → 必须能结算该工具留下的全部待结算项。"""
    sess = _unit_session(tmpdir)
    a = os.path.join(str(tmpdir), "a.txt")
    b = os.path.join(str(tmpdir), "b.txt")
    server._snapshot_before_change(sess, "write_file", {"path": a})
    server._snapshot_before_change(sess, "write_file", {"path": b})
    with open(a, "w", encoding="utf-8") as f:
        f.write("A\n")
    with open(b, "w", encoding="utf-8") as f:
        f.write("B\n")
    rec = server._finalize_file_change(sess, "write_file")
    assert rec is not None
    assert len(sess["changes"]) == 2
    assert not sess.get("_changes_pending"), "结算后不应残留待结算项"
