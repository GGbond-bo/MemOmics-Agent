# -*- coding: utf-8 -*-
"""P1-3 回归：可点击引用（证据锚点 → 可核对的原文/外链）。

覆盖四层：
A 纯函数（抽取/归一/外链/路径安全/候选匹配/摘录）
B HTTP（POST 解析、GET 按消息下标解析、错误码）
C 安全（目录穿越、盘符、非 http 协议）
D 前端接线静态守卫（锚点真的可点、真的接了接口）
"""
import json
import os
import uuid

import pytest

import server
from conftest import cleanup_session


# --- A. 纯函数 --------------------------------------------------------------

def test_extract_kinds_dedupe_and_order():
    txt = "见 [KB源:tables/a.yaml]，又见 [kb源:TABLES/A.YAML] 重复；" \
          "数据在 [数据:results/x.csv]；文献 [DOI:10.1038/s41586-020-2649-2] 与 [PMID: 12345678]；" \
          "[URL:https://example.org/p]；另外 [仅是推理] 和 [找不到论据]。"
    items = server._cite_extract(txt)
    kinds = [i["kind"] for i in items]
    assert kinds == ["kb", "data", "doi", "pmid", "url", "note", "note"], kinds
    # (类别, 值) 去重且不区分大小写
    assert sum(1 for i in items if i["kind"] == "kb") == 1
    assert items[0]["value"] == "tables/a.yaml"
    assert items[5]["value"] == "仅是推理"


def test_extract_limits_and_truncates():
    txt = "".join("[KB源:f%d.yaml]" % i for i in range(60))
    assert len(server._cite_extract(txt)) == server._CITE_MAX_ITEMS
    long_text = "[KB源:a.yaml]" + "x" * (server._CITE_MAX_TEXT + 5000)
    assert len(server._cite_extract(long_text)) == 1
    assert server._cite_resolve(long_text)["summary"]["truncated_text"] > 0


def test_extract_ignores_plain_text():
    assert server._cite_extract("这里没有任何锚点，只有 [方括号] 和 [1] 这种引用编号") == []
    assert server._cite_extract("") == []
    assert server._cite_extract(None) == []


def test_external_url_rules():
    assert server._cite_external_url("doi", "10.1038/s41586-020-2649-2") == "https://doi.org/10.1038/s41586-020-2649-2"
    assert server._cite_external_url("doi", "https://doi.org/10.1038/abc") == "https://doi.org/10.1038/abc"
    assert server._cite_external_url("doi", "https://doi.org/10.1/abc") == ""   # 已带前缀也要过 DOI 规则
    assert server._cite_external_url("doi", "doi:10.1038/abc") == "https://doi.org/10.1038/abc"
    assert server._cite_external_url("doi", "10.1/x") == ""          # 前缀位数不够
    assert server._cite_external_url("doi", "doi:10.1/abc") == ""    # 同样位数不够
    assert server._cite_external_url("pmid", "PMID 12345678") == "https://pubmed.ncbi.nlm.nih.gov/12345678/"
    assert server._cite_external_url("pmid", "abc") == ""
    assert server._cite_external_url("url", "http://a.b/c") == "http://a.b/c"
    assert server._cite_external_url("url", "HTTPS://A.B/C") == "HTTPS://A.B/C"
    for bad in ("javascript:alert(1)", "file:///C:/Windows/win.ini", "data:text/html,x", "  "):
        assert server._cite_external_url("url", bad) == "", bad
    assert len(server._cite_external_url("url", "http://a.b/" + "c" * 900)) == 500


def test_find_files_rejects_escaping_paths():
    roots = server._cite_safe_roots(None)
    for bad in ("../../../../Windows/win.ini", "..\\..\\x.yaml", "/etc/passwd", "C:\\Windows\\win.ini",
                "knowledge_base/../../../x"):
        assert server._cite_find_files(bad, roots) == [], bad


def test_find_files_exact_then_fuzzy(tmp_path):
    kb = str(tmp_path)
    os.makedirs(os.path.join(kb, "sub"), exist_ok=True)
    real = os.path.join(kb, "sub", "snrna_qc.yaml")
    with open(real, "w", encoding="utf-8") as f:
        f.write("a: 1\n")
    other = os.path.join(kb, "snrna_qc_extra.yaml")
    with open(other, "w", encoding="utf-8") as f:
        f.write("b: 2\n")
    exact = server._cite_find_files("sub/snrna_qc.yaml", [kb])
    assert exact and exact[0][0] == os.path.abspath(real) and exact[0][1] is True
    fuzzy = server._cite_find_files("snrna_qc.yaml", [kb])
    assert fuzzy and fuzzy[0][0] == os.path.abspath(real) and fuzzy[0][1] is True
    # 只有子串命中：标成近似，不能冒充精确
    near = server._cite_find_files("snrna_qc_extra.yaml", [kb])
    assert near and near[0][0] == os.path.abspath(other)
    assert server._cite_find_files("win.ini", [kb]) == []       # 短片断不做模糊匹配


def test_excerpt_hits_line_and_marks_truncation(tmp_path):
    p = os.path.join(str(tmp_path), "big.txt")
    with open(p, "w", encoding="utf-8") as f:
        for i in range(1, 201):
            f.write("line %d\n" % i)
    exc, why = server._cite_excerpt(p, "line 150")
    assert why == ""
    assert exc["hit_line"] == 150
    assert exc["lines"][0]["n"] == 148 and exc["lines"][-1]["n"] == 171
    assert exc["truncated"] is True and exc["total_lines"] == 200
    assert "[KB源:x]" not in exc["text"]
    # 二进制/缺失/超大都要给出人话原因
    b = os.path.join(str(tmp_path), "bin.dat")
    with open(b, "wb") as f:
        f.write(b"\x00\x01\x02binary")
    assert server._cite_excerpt(b)[0] is None and server._cite_excerpt(b)[1]
    assert server._cite_excerpt(os.path.join(str(tmp_path), "nope.txt"))[0] is None


def test_resolve_item_note_and_empty():
    note = server._cite_resolve_item({"kind": "note", "label": "仅是推理", "value": "仅是推理", "raw": "[仅是推理]"})
    assert note["status"] == "note" and "推理" in note["reason"]
    empty = server._cite_resolve_item({"kind": "kb", "label": "KB源", "value": "", "raw": "[KB源:]"})
    assert empty["status"] == "missing" and empty["reason"]


# --- B. HTTP ---------------------------------------------------------------

def test_post_resolve_roundtrip(client, new_session):
    sid = new_session
    try:
        body = {"text": "结论见 [KB源:not-a-real-file.yaml] 与 [PMID:12345678]", "session_id": sid}
        r = client.post("/api/citations/resolve", json=body)
        assert r.status_code == 200
        d = r.json()
        assert d["ok"] is True and d["session_id"] == sid
        assert d["summary"]["total"] == 2
        assert d["summary"]["external"] == 1 and d["summary"]["missing"] == 1
        miss = [i for i in d["items"] if i["status"] == "missing"][0]
        assert miss["reason"] and miss["lines"] == []
        ext = [i for i in d["items"] if i["status"] == "external"][0]
        assert ext["url"].startswith("https://pubmed.ncbi.nlm.nih.gov/")
        # 内部字段不许漏出去
        assert "_before_text" not in r.text
    finally:
        cleanup_session(sid)


def test_post_resolve_rejects_huge_text(client):
    r = client.post("/api/citations/resolve", json={"text": "x" * (server._CITE_MAX_TEXT * 5 + 10)})
    assert r.status_code == 413
    assert "上限" in r.json()["error"]


def test_post_resolve_empty_text_ok(client):
    r = client.post("/api/citations/resolve", json={"text": ""})
    assert r.status_code == 200
    assert r.json()["summary"]["total"] == 0


def test_get_citations_by_message_index(client, new_session):
    sid = new_session
    try:
        sess = server._sessions[sid]
        sess.setdefault("messages", []).append({"role": "user", "content": "问题 [KB源:x.yaml]"})
        sess["messages"].append({"role": "assistant", "content": "答案见 [KB源:no-such.yaml] 和 [DOI:10.1038/s41586-020-2649-2]"})
        r = client.get("/api/sessions/%s/citations?msg=-1" % sid)
        assert r.status_code == 200
        d = r.json()
        assert d["msg_index"] == 1 and d["total_messages"] == 2
        assert d["summary"]["total"] == 2
        # 指定下标（助手消息）
        r2 = client.get("/api/sessions/%s/citations?msg=1" % sid)
        assert r2.status_code == 200 and r2.json()["msg_index"] == 1
        # 下标 0 是用户消息 → 400
        r3 = client.get("/api/sessions/%s/citations?msg=0" % sid)
        assert r3.status_code == 400
        # 越界 → 404
        assert client.get("/api/sessions/%s/citations?msg=99" % sid).status_code == 404
        assert client.get("/api/sessions/%s/citations?msg=-5" % sid).status_code in (200, 404)
    finally:
        cleanup_session(sid)


def test_get_citations_unknown_session_404(client):
    assert client.get("/api/sessions/no-such-session-xyz/citations").status_code == 404


def test_get_citations_empty_session_404(client, new_session):
    sid = new_session
    try:
        server._sessions[sid]["messages"] = []
        assert client.get("/api/sessions/%s/citations" % sid).status_code == 404
    finally:
        cleanup_session(sid)


# --- C. 安全 ----------------------------------------------------------------

def test_resolution_stays_inside_allowed_roots(client, new_session, tmp_path):
    """结果目录外的文件读不到，即使写成绝对路径。"""
    sid = new_session
    try:
        outside = tmp_path / "outside_secret.txt"
        outside.write_text("SECRET-OUTSIDE", encoding="utf-8")
        r = client.post("/api/citations/resolve", json={"text": "[数据:%s]" % str(outside), "session_id": sid})
        assert r.status_code == 200
        it = r.json()["items"][0]
        assert it["status"] == "missing"
        assert "SECRET-OUTSIDE" not in r.text
    finally:
        cleanup_session(sid)


def test_traversal_is_refused_and_not_leaked(client):
    r = client.post("/api/citations/resolve", json={"text": "[KB源:../../../../Windows/win.ini]"})
    assert r.status_code == 200
    it = r.json()["items"][0]
    assert it["status"] == "missing" and it["lines"] == []


def test_real_kb_file_resolves_with_excerpt(client, new_session):
    """用真实知识库文件跑一遍：必须解析到具体路径并给出摘录。"""
    cand = None
    for dirpath, dirnames, filenames in os.walk(server.KB_DIR):
        for fn in filenames:
            if fn.lower().endswith((".yaml", ".yml", ".md")):
                p = os.path.join(dirpath, fn)
                try:
                    if 200 < os.path.getsize(p) < 40000:
                        cand = p
                        break
                except OSError:
                    continue
        if cand:
            break
    if not cand:
        pytest.skip("知识库为空，跳过")
    rel = os.path.relpath(cand, server.KB_DIR).replace(os.sep, "/")
    sid = new_session
    try:
        r = client.post("/api/citations/resolve", json={"text": "[KB源:%s]" % rel, "session_id": sid})
        it = r.json()["items"][0]
        assert it["status"] == "resolved", it
        assert it["rel"].startswith("knowledge_base/")
        assert it["lines"] and it["lines"][0]["n"] == 1
        assert it["approx"] is False
    finally:
        cleanup_session(sid)


# --- D. 前端接线 ------------------------------------------------------------

def _index_html():
    p = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "index.html")
    with open(p, encoding="utf-8") as f:
        return f.read()


def test_frontend_citations_wired():
    html = _index_html()
    for need in ('id="cite-overlay"', 'id="cite-ov-body"', 'class="anchor cite"'):
        assert need in html, need
    for fn in ("function _citeWrapHtml(", "async function openCitation(",
               "function renderCitation(", "function closeCitation()",
               "function citeOpenKb()", "function citeOpenUrl()", "function citeCopy("):
        assert fn in html, fn
    # 三条数据通道：解析接口 / 助手消息 / 流式输出
    assert "'/api/citations/resolve'" in html
    assert "_citeWrapHtml(renderMarkdown(text))" in html, "助手消息没接引用渲染"
    assert "_citeWrapHtml(renderMarkdown(fullText))" in html, "流式输出没接引用渲染"
    # 深度思考面板的锚点也可点
    assert "onclick=\"openCitation(this)\"" in html
    assert "data-cite=" in html
    # 样式存在
    for sel in (".anchor.cite", "#cite-overlay", ".cite-line.hit", ".cite-code"):
        assert sel in html, sel


# --- E. 极端输入 ------------------------------------------------------------

def test_extract_truncates_long_values():
    items = server._cite_extract("[KB源:" + "a" * 5000 + ".yaml]")
    assert len(items) == 1 and len(items[0]["value"]) == server._CITE_MAX_VALUE
    # 整个锚点超过文本上限 → 截断后连右括号都没了，本来就不该算锚点
    assert server._cite_extract("[KB源:" + "a" * 50000 + ".yaml]") == []


def test_extract_dirty_anchors_do_not_crash():
    for txt in ("[KB源:]", "[KB源:   ]", "[[KB源:a.yaml]]", "[KB源:[a].yaml]",
                "[PMIDs: 123]", "[链接:http://a.b]", "[来源:知识库文件]"):
        assert len(server._cite_extract(txt)) == 1, txt
    r = server._cite_resolve("[KB源:a\u0000b.yaml] [KB源:c\r\nd.yaml] [URL:https://a.b/<script>x</script>]")
    assert isinstance(r["summary"], dict)
    # 带 HTML/空白/引号的“网址”直接判非法，脏串不许出现在任何字段里
    assert all("<script>" not in ((i["rel"] or "") + (i["path"] or "") + (i["title"] or "") + (i["url"] or ""))
               for i in r["items"])
    assert server._cite_external_url("url", "https://a.b/<script>x</script>") == ""
    assert server._cite_external_url("url", 'https://a.b/"onmouseover="x') == ""
    assert server._cite_external_url("url", "https://a.b/x y") == ""


def test_resolve_caps_item_count():
    r = server._cite_resolve("".join("[KB源:f%d.yaml]" % i for i in range(200)))
    assert len(r["items"]) == server._CITE_MAX_ITEMS
