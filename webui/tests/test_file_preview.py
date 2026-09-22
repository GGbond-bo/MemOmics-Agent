# -*- coding: utf-8 -*-
"""P5(2026-09-22) 分析结果文件直读契约测试。

用户原话："分析结果有图片和文件，我希望文件能够直接点开查看，能够按照时间顺序排列，
最新出的文件排在最上面。主要包括 txt, excel, word, md, pdf 等等文件，这些有办法直接
在 webUI 打开吗？"

三组契约（全部走真实实现）：
  A. 转换层  webui/preview_convert.py —— 各格式真能转成前端可显示结构；缺库有兜底；
             扩展名骗人（真机上有 .xlsx 其实是 XML 错误页）不许只丢一句"无法解析"
  B. 接口层  /api/file/preview、/api/file/raw、/api/file/open —— 越权路径必须拒；
             MIME/内联下载语义正确
  C. 排序    /api/results/{sid} 与 /figures 默认"最新在最上面"（用户明确要求）
  D. P5.1   目录永远在上、文件按时间倒序；已查看标记（提醒还有哪些没看）；
            中英双语（切英文不许残留中文）；路径跟着安装位置走、不绑开发机
"""
import io
import json
import os
import sys
import time
import zipfile

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import server  # noqa: E402
from webui import preview_convert as pc  # noqa: E402


# ==================== 夹具 ====================

@pytest.fixture()
def workdir(tmp_path):
    """放各种测试文件的小目录"""
    return tmp_path


def _write_text(p, s, enc="utf-8"):
    with open(p, "w", encoding=enc, newline="") as f:
        f.write(s)
    return str(p)


def _make_xlsx(path, sheet2=True):
    openpyxl = pytest.importorskip("openpyxl")
    from datetime import datetime
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "基因表达"
    ws.append(["基因", "log2FC", "p值"])
    for i, g in enumerate(["TP53", "MYC", "CDKN2A"]):
        ws.append([g, round(1.5 - i * 0.3, 3), 0.001 * (i + 1)])
    if sheet2:
        ws2 = wb.create_sheet("样本信息")
        ws2.append(["样本", "收集日期"])
        ws2.append(["S1", datetime(2026, 3, 1)])
    wb.save(path)
    return str(path)


DOCX_DOCUMENT = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
    "<w:body>"
    '<w:p><w:pPr><w:pStyle w:val="Heading1"/></w:pPr><w:r><w:t>衰老分析报告</w:t></w:r></w:p>'
    '<w:p><w:r><w:rPr><w:b/></w:rPr><w:t>结论：</w:t></w:r><w:r><w:t>TP53 显著上调</w:t></w:r></w:p>'
    '<w:p><w:pPr><w:numPr><w:ilvl w:val="0"/></w:numPr></w:pPr><w:r><w:t>第一条要点</w:t></w:r></w:p>'
    "<w:tbl><w:tr><w:tc><w:p><w:r><w:t>样本</w:t></w:r></w:p></w:tc>"
    "<w:tc><w:p><w:r><w:t>分组</w:t></w:r></w:p></w:tc></w:tr>"
    "<w:tr><w:tc><w:p><w:r><w:t>S1</w:t></w:r></w:p></w:tc>"
    "<w:tc><w:p><w:r><w:t>年轻</w:t></w:r></w:p></w:tc></w:tr></w:tbl>"
    "</w:body></w:document>"
)


def _make_docx(path):
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml",
                    '<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                    '<Default Extension="xml" ContentType="application/xml"/></Types>')
        zf.writestr("word/document.xml", DOCX_DOCUMENT)
    return str(path)


def _make_ipynb(path):
    nb = {"cells": [
        {"cell_type": "markdown", "source": ["# 分析笔记"], "outputs": []},
        {"cell_type": "code", "source": ["import pandas as pd"], "outputs": [
            {"output_type": "stream", "text": ["shape: (3, 3)"]},
            {"output_type": "execute_result", "data": {"text/plain": ["   gene\n0  TP53"]}}]},
        {"cell_type": "code", "source": ["plt.plot([1,2])"], "outputs": [
            {"output_type": "error", "traceback": ["ValueError: boom"]}]},
    ], "metadata": {}, "nbformat": 4, "nbformat_minor": 5}
    with open(path, "w", encoding="utf-8") as f:
        json.dump(nb, f, ensure_ascii=False)
    return str(path)


def _make_pdf(path):
    try:
        from pypdf import PdfWriter
    except Exception:
        pytest.skip("pypdf 未安装")
    w = PdfWriter()
    w.add_blank_page(width=200, height=200)
    with open(path, "wb") as f:
        w.write(f)
    return str(path)


# ==================== A. 转换层 ====================

@pytest.mark.unit
def test_kind_matrix():
    cases = {
        "a.txt": "text", "a.log": "text", "a.py": "code", "a.R": "code", "a.sh": "code",
        "a.json": "code", "a.yaml": "code", "a.md": "markdown", "a.markdown": "markdown",
        "a.csv": "table", "a.tsv": "table", "a.xlsx": "excel", "a.xlsm": "excel",
        "a.docx": "word", "a.ipynb": "notebook", "a.pdf": "pdf",
        "a.png": "image", "a.JPG": "image", "a.svg": "image",
        "a.html": "html", "a.htm": "html",
        "a.rds": "binary", "a.h5ad": "binary", "a.bam": "binary", "a.unknownxyz": "binary",
    }
    for name, want in cases.items():
        assert pc.kind_of(name) == want, name


@pytest.mark.unit
def test_text_preview_and_gbk_fallback(workdir):
    p = _write_text(os.path.join(workdir, "a.txt"), "第一行\n第二行\n")
    d = pc.preview(p)
    assert d["kind"] == "text" and d["total_lines"] == 2 and "第二行" in d["text"]
    g = os.path.join(workdir, "gbk.txt")
    with open(g, "wb") as f:
        f.write("中文 GBK 测试\n第二行\n".encode("gb18030"))
    d2 = pc.preview(g)
    assert d2["kind"] == "text" and "中文 GBK 测试" in d2["text"]
    assert d2["encoding"] in ("gb18030", "utf-8")


@pytest.mark.unit
def test_utf8_truncation_is_not_mojibake(workdir):
    """截断处切断多字节字符时，不许误判成 latin-1（否则满屏乱码）。"""
    p = os.path.join(workdir, "big.txt")
    with open(p, "w", encoding="utf-8") as f:
        for i in range(30000):
            f.write("行%d 中文内容测试\n" % i)
    d = pc.preview(p)
    assert d["kind"] == "text" and d["truncated"] is True
    assert d["encoding"] == "utf-8", d["encoding"]
    assert "行1 中文内容测试" in d["text"]
    assert "\ufffd" not in d["text"][:5000]


@pytest.mark.unit
def test_markdown_and_code_preview(workdir):
    m = _write_text(os.path.join(workdir, "r.md"), "# 标题\n\n- 要点\n")
    d = pc.preview(m)
    assert d["kind"] == "markdown" and "# 标题" in d["text"]
    c = _write_text(os.path.join(workdir, "s.py"), "def f(x):\n    return x\n")
    d2 = pc.preview(c)
    assert d2["kind"] == "code" and "def f(x)" in d2["text"]


@pytest.mark.unit
def test_csv_table_with_quoted_comma(workdir):
    p = _write_text(os.path.join(workdir, "t.csv"), 'gene,desc,fc\nTP53,"a, b",2.5\nMYC,x,1.1\n')
    d = pc.preview(p)
    assert d["kind"] == "table" and d["engine"] == "csv"
    sh = d["sheets"][0]
    assert sh["columns"] == ["gene", "desc", "fc"]
    assert sh["rows"][0] == ["TP53", "a, b", "2.5"]
    assert sh["total_rows"] == 2


@pytest.mark.unit
def test_tsv_table(workdir):
    p = _write_text(os.path.join(workdir, "t.tsv"), "cell\tcount\nT细胞\t1200\nB细胞\t800\n")
    d = pc.preview(p)
    assert d["kind"] == "table" and d["sheets"][0]["columns"] == ["cell", "count"]
    assert d["sheets"][0]["rows"][1] == ["B细胞", "800"]


@pytest.mark.unit
def test_xlsx_via_openpyxl(workdir):
    p = _make_xlsx(os.path.join(workdir, "t.xlsx"))
    d = pc.preview(p)
    assert d["kind"] == "excel" and d["engine"] == "openpyxl", d.get("error")
    names = [s["name"] for s in d["sheets"]]
    assert names == ["基因表达", "样本信息"], names
    s0 = d["sheets"][0]
    assert s0["columns"] == ["基因", "log2FC", "p值"]
    assert s0["rows"][0][0] == "TP53"
    assert "2026-03-01" in d["sheets"][1]["rows"][0][1]


@pytest.mark.unit
def test_xlsx_stdlib_fallback_without_openpyxl(workdir, monkeypatch):
    """随包环境万一没有 openpyxl：zipfile+XML 兜底也必须能读出表。"""
    p = _make_xlsx(os.path.join(workdir, "t2.xlsx"))
    real_import = __builtins__["__import__"] if isinstance(__builtins__, dict) else __builtins__.__import__

    def blocked(name, *a, **k):
        if name == "openpyxl":
            raise ImportError("blocked for test")
        return real_import(name, *a, **k)

    monkeypatch.setattr("builtins.__import__", blocked)
    d = pc.preview(p)
    assert d["kind"] == "excel" and d["engine"] == "stdlib-zip", d.get("error")
    assert [s["name"] for s in d["sheets"]] == ["基因表达", "样本信息"]
    assert d["sheets"][0]["rows"][0][0] == "TP53"
    assert d["sheets"][0]["columns"] == ["基因", "log2FC", "p值"]
    assert "2026-03-01" in d["sheets"][1]["rows"][0][1], d["sheets"][1]["rows"]


@pytest.mark.unit
def test_docx_to_html(workdir):
    p = _make_docx(os.path.join(workdir, "t.docx"))
    d = pc.preview(p)
    assert d["kind"] == "word" and d.get("error") == "", d.get("error")
    html = d["html"]
    assert "<h1>衰老分析报告</h1>" in html
    assert "<strong>结论：</strong>" in html
    assert "TP53 显著上调" in html
    assert "dx-table" in html and "年轻" in html
    assert d["tables"] == 1 and d["paragraphs"] >= 3


@pytest.mark.unit
def test_docx_corrupt_does_not_raise(workdir):
    p = os.path.join(workdir, "bad.docx")
    with open(p, "wb") as f:
        f.write(b"not a zip at all")
    d = pc.preview(p)
    assert d["kind"] in ("word", "text")          # 走内容嗅探 → 文本
    assert d.get("error") == "" and d["text"].startswith("not a zip")


@pytest.mark.unit
def test_ipynb_cells_and_outputs(workdir):
    p = _make_ipynb(os.path.join(workdir, "n.ipynb"))
    d = pc.preview(p)
    assert d["kind"] == "notebook" and len(d["cells"]) == 3
    assert d["cells"][0]["type"] == "markdown" and "分析笔记" in d["cells"][0]["source"]
    assert d["cells"][1]["outputs"][0]["text"].startswith("shape")
    assert d["cells"][2]["outputs"][0]["type"] == "error"


@pytest.mark.unit
def test_pdf_meta(workdir):
    p = _make_pdf(os.path.join(workdir, "t.pdf"))
    d = pc.preview(p)
    assert d["kind"] == "pdf" and d["pages"] == 1


@pytest.mark.unit
def test_image_and_html_are_inline(workdir):
    png = os.path.join(workdir, "a.png")
    with open(png, "wb") as f:
        f.write(bytes.fromhex("89504e470d0a1a0a") + b"0" * 32)
    d = pc.preview(png)
    assert d["kind"] == "image" and d["inline"] is True
    h = _write_text(os.path.join(workdir, "r.html"), "<html><body>报告</body></html>")
    d2 = pc.preview(h)
    assert d2["kind"] == "html" and d2["inline"] is True


@pytest.mark.unit
def test_binary_hint(workdir):
    p = os.path.join(workdir, "x.rds")
    with open(p, "wb") as f:
        f.write(b"\x1f\x8b\x08\x00" + bytes(range(256)) * 4)
    d = pc.preview(p)
    assert d["kind"] == "binary" and "RDS" in (d.get("hint") or "")


@pytest.mark.unit
def test_wrong_extension_falls_back_to_text(workdir):
    """真机案例：results 里的 senmayo_supp.xlsx 其实是 GCS AccessDenied 的 XML。"""
    p = os.path.join(workdir, "fake.xlsx")
    with open(p, "w", encoding="utf-8") as f:
        f.write("<?xml version='1.0'?><Error><Code>AccessDenied</Code></Error>")
    d = pc.preview(p)
    assert d["kind"] == "text" and "AccessDenied" in d["text"]
    assert d["original_kind"] == "excel" and d["note"]


@pytest.mark.unit
def test_missing_and_directory(workdir):
    d = pc.preview(os.path.join(workdir, "nope.txt"))
    assert d["kind"] == "missing" and "不存在" in d["error"]
    d2 = pc.preview(str(workdir))
    assert d2["kind"] == "missing" and "目录" in d2["error"]


@pytest.mark.unit
def test_human_size():
    assert pc.human_size(0) == "0 B"
    assert pc.human_size(1024) == "1.0 KB"
    assert pc.human_size(1536) == "1.5 KB"
    assert pc.human_size(5 * 1024 * 1024) == "5.0 MB"


# ==================== B. 接口层 ====================

@pytest.fixture()
def res_dir(new_session):
    """在真实 results/<sid>/ 下造文件（越权路径必须走真实根目录才有意义）"""
    d = os.path.join(server.RESULTS_DIR, new_session)
    os.makedirs(d, exist_ok=True)
    return new_session, d


def _touch(path, content, mtime=None):
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(content)
    if mtime is not None:
        os.utime(path, (mtime, mtime))
    return str(path)


@pytest.mark.api
def test_preview_endpoint_markdown(client, res_dir):
    sid, d = res_dir
    _touch(os.path.join(d, "报告.md"), "# 结论\n\nTP53 上调\n")
    r = client.get("/api/file/preview", params={"path": os.path.join(d, "报告.md")})
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["kind"] == "markdown" and "TP53 上调" in j["text"]
    assert j["download_url"].startswith("/api/file/download?path=")
    assert j["raw_url"].startswith("/api/file/raw?path=")
    assert "\\" not in j["path"]          # 统一正斜杠，前端拼接不用管反斜杠


@pytest.mark.api
def test_preview_endpoint_csv_and_xlsx(client, res_dir):
    sid, d = res_dir
    _touch(os.path.join(d, "t.csv"), "gene,fc\nTP53,2.5\n")
    _make_xlsx(os.path.join(d, "t.xlsx"))
    j1 = client.get("/api/file/preview", params={"path": os.path.join(d, "t.csv")}).json()
    assert j1["kind"] == "table" and j1["sheets"][0]["rows"][0][0] == "TP53"
    j2 = client.get("/api/file/preview", params={"path": os.path.join(d, "t.xlsx")}).json()
    assert j2["kind"] == "excel" and len(j2["sheets"]) == 2


@pytest.mark.api
def test_preview_endpoint_rejects_outside_roots(client, tmp_path):
    outside = tmp_path / "outside.txt"
    outside.write_text("secret", encoding="utf-8")
    r = client.get("/api/file/preview", params={"path": str(outside)})
    assert r.status_code == 403, r.text
    # 目录穿越写法也不行
    sneaky = os.path.join(server.RESULTS_DIR, "..", "..", "Windows", "win.ini")
    assert client.get("/api/file/preview", params={"path": sneaky}).status_code in (403, 404)


@pytest.mark.api
def test_preview_endpoint_missing_and_directory(client, res_dir):
    sid, d = res_dir
    assert client.get("/api/file/preview", params={"path": os.path.join(d, "nope.txt")}).status_code == 404
    j = client.get("/api/file/preview", params={"path": d}).json()
    assert j["kind"] == "missing" and "目录" in j["error"]
    assert client.get("/api/file/preview").status_code == 400


@pytest.mark.api
def test_raw_endpoint_inline_and_download(client, res_dir):
    sid, d = res_dir
    _touch(os.path.join(d, "t.csv"), "a,b\n1,2\n")
    r = client.get("/api/file/raw", params={"path": os.path.join(d, "t.csv")})
    assert r.status_code == 200 and r.text.startswith("a,b")
    assert "text/csv" in r.headers["content-type"]
    assert r.headers["content-disposition"].startswith("inline")
    r2 = client.get("/api/file/raw", params={"path": os.path.join(d, "t.csv"), "dl": 1})
    assert r2.headers["content-disposition"].startswith("attachment")
    assert r2.headers.get("x-content-type-options") == "nosniff"


@pytest.mark.api
def test_raw_endpoint_rejects_outside_roots(client, tmp_path):
    p = tmp_path / "x.txt"
    p.write_text("secret", encoding="utf-8")
    assert client.get("/api/file/raw", params={"path": str(p)}).status_code == 403


@pytest.mark.api
def test_open_endpoint_disabled_by_switch(client, res_dir, monkeypatch):
    sid, d = res_dir
    f = _touch(os.path.join(d, "a.txt"), "x")
    monkeypatch.setattr(server, "_SYSOPEN_ENABLED", False)
    r = client.post("/api/file/open", json={"path": f, "action": "system"})
    assert r.status_code == 403 and "禁用" in r.json()["error"]


@pytest.mark.api
def test_open_endpoint_validates_action_and_path(client, res_dir, monkeypatch):
    sid, d = res_dir
    f = _touch(os.path.join(d, "a.txt"), "x")
    monkeypatch.setattr(server, "_SYSOPEN_ENABLED", True)
    assert client.post("/api/file/open", json={"path": f, "action": "explode"}).status_code == 400
    assert client.post("/api/file/open", json={"path": os.path.join(d, "gone.txt")}).status_code == 404


@pytest.mark.api
def test_open_endpoint_calls_os_startfile(client, res_dir, monkeypatch):
    """真实代码路径：确认调用了系统打开，但不真的弹窗。"""
    if os.name != "nt":
        pytest.skip("仅 Windows")
    sid, d = res_dir
    f = _touch(os.path.join(d, "a.txt"), "x")
    calls = []
    monkeypatch.setattr(server, "_SYSOPEN_ENABLED", True)
    monkeypatch.setattr(os, "startfile", lambda p: calls.append(p), raising=False)
    r = client.post("/api/file/open", json={"path": f, "action": "system"})
    assert r.status_code == 200 and r.json()["ok"] is True
    assert calls and os.path.samefile(calls[0], f)


# ==================== C. 排序：最新在最上面 ====================

@pytest.mark.api
def test_results_listing_newest_first_by_default(client, res_dir):
    sid, d = res_dir
    _touch(os.path.join(d, "old.txt"), "1", mtime=1_600_000_000)
    _touch(os.path.join(d, "mid.csv"), "1", mtime=1_700_000_000)
    _touch(os.path.join(d, "new.md"), "1", mtime=1_800_000_000)
    j = client.get("/api/results/" + sid).json()
    assert j["sort"] == "time_desc"
    assert [i["name"] for i in j["items"]] == ["new.md", "mid.csv", "old.txt"]
    j2 = client.get("/api/results/" + sid, params={"sort": "name"}).json()
    assert [i["name"] for i in j2["items"]] == ["mid.csv", "new.md", "old.txt"]
    assert all(i["mtime_str"] for i in j["items"])


@pytest.mark.api
def test_results_dirs_first_never_mixed_with_files(client, res_dir):
    """P5.1 用户原话：目录优先，目录都在最上面，按照26字母的顺序。然后文件放在目录下面，
    按照生成时间，最新的在上面。不要把目录和文件混了。
    对抗性 mtime：就算某个目录比所有文件都旧、某个文件比目录新，也不许越位。"""
    sid, d = res_dir
    for n in ("z_dir", "a_dir", "m_dir"):
        os.makedirs(os.path.join(d, n), exist_ok=True)
    os.utime(os.path.join(d, "z_dir"), (1_900_000_000, 1_900_000_000))   # 目录里最新
    os.utime(os.path.join(d, "a_dir"), (1_500_000_000, 1_500_000_000))   # 目录里最旧
    os.utime(os.path.join(d, "m_dir"), (1_600_000_000, 1_600_000_000))
    _touch(os.path.join(d, "m_new.md"), "1", mtime=1_800_000_000)        # 文件里最新
    _touch(os.path.join(d, "b_old.txt"), "1", mtime=1_400_000_000)       # 比所有目录都旧
    j = client.get("/api/results/" + sid).json()
    assert [i["name"] for i in j["items"]] == ["a_dir", "m_dir", "z_dir", "m_new.md", "b_old.txt"], \
        "目录必须全部排在文件前面，目录之间按 A->Z，文件按时间倒序"
    assert [i["is_dir"] for i in j["items"]] == [True, True, True, False, False]
    j2 = client.get("/api/results/" + sid, params={"sort": "name"}).json()
    assert [i["name"] for i in j2["items"]] == ["a_dir", "m_dir", "z_dir", "b_old.txt", "m_new.md"]


@pytest.mark.api
def test_results_subdir_listing_also_dirs_first(client, res_dir):
    """子目录里同样：目录在上、文件在下（别只在根目录生效）。"""
    sid, d = res_dir
    sub = os.path.join(d, "00_task")
    os.makedirs(os.path.join(sub, "inner"), exist_ok=True)
    _touch(os.path.join(sub, "r1.txt"), "1", mtime=1_700_000_000)
    _touch(os.path.join(sub, "r2.txt"), "1", mtime=1_800_000_000)
    j = client.get("/api/results/" + sid, params={"path": "00_task"}).json()
    assert [i["name"] for i in j["items"]] == ["inner", "r2.txt", "r1.txt"]
    assert j["items"][0]["is_dir"] is True


@pytest.mark.api
def test_viewed_mark_persists_and_counts(client, res_dir):
    """P5.1 已查看：打开过的文件打标记，未查看计数要准（提醒用户还有哪些没看）。"""
    sid, d = res_dir
    f1 = _touch(os.path.join(d, "one.txt"), "1")
    _touch(os.path.join(d, "two.txt"), "2")
    j = client.get("/api/results/" + sid).json()
    assert j["unread"] == 2 and j["viewed_count"] == 0
    assert all(i["viewed"] is False for i in j["items"])
    assert all(i["rel_path"] for i in j["items"])       # 前端要用 rel_path 做标记 key

    r = client.post("/api/results/%s/viewed" % sid, json={"path": f1, "viewed": True})
    assert r.status_code == 200 and r.json()["viewed"] is True and r.json()["rel"] == "one.txt"
    assert os.path.isfile(os.path.join(d, ".viewed.json"))   # 真的落盘（换浏览器也记得）
    j = client.get("/api/results/" + sid).json()
    assert j["unread"] == 1 and j["viewed_count"] == 1
    assert [i["viewed"] for i in j["items"] if i["name"] == "one.txt"] == [True]
    assert ".viewed.json" not in [i["name"] for i in j["items"]]   # 点开头的不许出现在列表

    r = client.post("/api/results/%s/viewed" % sid, json={"path": f1, "viewed": False})
    assert r.json()["viewed"] is False
    j = client.get("/api/results/" + sid).json()
    assert j["unread"] == 2 and j["viewed_count"] == 0

    r = client.post("/api/results/%s/viewed" % sid, json={"path": "two.txt"})   # 相对路径也认
    assert r.status_code == 200 and r.json()["rel"] == "two.txt"
    sub = os.path.join(d, "00_task")
    os.makedirs(sub, exist_ok=True)
    f3 = _touch(os.path.join(sub, "deep.csv"), "a,b")
    assert client.post("/api/results/%s/viewed" % sid, json={"path": f3}).status_code == 200
    assert client.post("/api/results/%s/viewed" % sid, json={"path": "00_task/deep.csv"}).status_code == 200


@pytest.mark.api
def test_viewed_mark_validation(client, res_dir, workdir):
    """越权/不存在/空的 path 一律拒；目录不接受标记。"""
    sid, d = res_dir
    assert client.post("/api/results/%s/viewed" % sid, json={"path": ""}).status_code == 400
    outside = _touch(os.path.join(workdir, "outside.txt"), "x")
    assert client.post("/api/results/%s/viewed" % sid, json={"path": outside}).status_code == 403
    assert client.post("/api/results/%s/viewed" % sid, json={"path": os.path.join(d, "nope.txt")}).status_code == 404
    os.makedirs(os.path.join(d, "adir"), exist_ok=True)
    assert client.post("/api/results/%s/viewed" % sid, json={"path": os.path.join(d, "adir")}).status_code == 400
    r = client.post("/api/results/no-such-session-xyz/viewed", json={"path": os.path.join(d, "one.txt")})
    assert r.status_code == 404


@pytest.mark.api
def test_viewed_expires_when_file_is_rewritten(client, res_dir):
    """看过之后文件又被重新生成（同名新结果）→ 重新算「未查看」，别让用户以为已经看过了。"""
    sid, d = res_dir
    f = _touch(os.path.join(d, "rep.txt"), "v1", mtime=1_700_000_000)
    assert client.post("/api/results/%s/viewed" % sid, json={"path": f}).status_code == 200
    j = client.get("/api/results/" + sid).json()
    assert [i["viewed"] for i in j["items"] if i["name"] == "rep.txt"] == [True]
    assert j["unread"] == 0 and j["viewed_count"] == 1
    _touch(os.path.join(d, "rep.txt"), "v2 rewritten", mtime=time.time() + 5)
    j = client.get("/api/results/" + sid).json()
    assert [i["viewed"] for i in j["items"] if i["name"] == "rep.txt"] == [False]
    assert j["unread"] == 1 and j["viewed_count"] == 0


@pytest.mark.api
@pytest.mark.skipif(bool(os.environ.get("MEMOMICS_DATA_DIR")),
                    reason="环境变量已覆盖数据目录，默认值断言不适用")
def test_data_paths_follow_install_location():
    """P6-3：work/results 默认就在安装目录下，代码里不许出现开发机绝对路径。"""
    assert server.DATA_DIR == server.MEMOMICS_DIR
    assert server.WORK_DIR == os.path.join(server.MEMOMICS_DIR, "work")
    assert server.RESULTS_DIR == os.path.join(server.MEMOMICS_DIR, "results")
    assert server._PREVIEW_ROOTS == [server.WORK_DIR, server.RESULTS_DIR, server.MEMOMICS_DIR]
    src = io.open(os.path.join(server.MEMOMICS_DIR, "webui", "server.py"), encoding="utf-8").read()
    for bad in ("E:/MemOmics-Agent", "E:\\\\MemOmics-Agent", "C:\\\\Users\\\\23136"):
        assert bad not in src, "server.py 里还留着开发机路径: " + bad


# ==================== D. P5.1 中英双语 ====================

@pytest.mark.api
def test_results_listing_note_localized(client, res_dir):
    sid, d = res_dir
    j = client.get("/api/results/" + sid, params={"lang": "en"}).json()
    assert "no analysis results yet" in j["note"] and not any("\u4e00" <= c <= "\u9fff" for c in j["note"])
    j2 = client.get("/api/results/" + sid).json()
    assert "尚未产生分析结果" in j2["note"]
    j3 = client.get("/api/results/" + sid, params={"lang": "zh-CN"}).json()
    assert "尚未产生分析结果" in j3["note"]


@pytest.mark.api
def test_preview_and_open_messages_localized(client, res_dir):
    sid, d = res_dir
    r = client.get("/api/file/preview", params={"path": os.path.join(d, "nope.txt"), "lang": "en"})
    assert r.status_code == 404 and r.json()["error"].startswith("File not found")
    r = client.get("/api/file/preview", params={"path": d, "lang": "en"})
    assert r.status_code == 200 and r.json()["kind"] == "missing" and "directory" in r.json()["error"]
    r = client.get("/api/file/preview", params={"path": d})               # 默认中文
    assert "这是一个目录" in r.json()["error"]
    r = client.get("/api/file/preview")                                   # 缺 path
    assert r.status_code == 400 and "缺少 path" in r.json()["error"]
    r = client.get("/api/file/preview", params={"lang": "en"})
    assert r.status_code == 400 and r.json()["error"] == "Missing path parameter"

    f = _touch(os.path.join(d, "x.txt"), "hi")
    r = client.post("/api/file/open", json={"path": f, "action": "explode", "lang": "en"})
    assert r.status_code == 400 and r.json()["error"] == "action must be system or folder"
    r = client.post("/api/file/open", json={"path": f, "action": "explode"})
    assert r.status_code == 400 and "只支持" in r.json()["error"]


@pytest.mark.api
def test_preview_body_and_note_localized(client, res_dir):
    """真正转出来的 hint 也要跟着语言走，不能只有报错双语。"""
    sid, d = res_dir
    p = _touch(os.path.join(d, "big.txt"), "line\n" * 10)
    en = client.get("/api/file/preview", params={"path": p, "lang": "en"}).json()
    zh = client.get("/api/file/preview", params={"path": p, "lang": "zh"}).json()
    assert en["kind"] == zh["kind"] == "text"
    assert en["text"] == zh["text"]                         # 文件内容本身不翻译
    binp = os.path.join(d, "blob.bin")
    with open(binp, "wb") as fh:
        fh.write(bytes(range(256)) * 4)
    en = client.get("/api/file/preview", params={"path": binp, "lang": "en"}).json()
    zh = client.get("/api/file/preview", params={"path": binp, "lang": "zh"}).json()
    assert en["hint"] != zh["hint"] and "Binary" in en["hint"]


# ==================== E. 语言状态线程安全 + 前端零硬编码中文 ====================

def test_preview_convert_lang_is_thread_local():
    """server.py 用 run_in_executor 调 preview()：两个线程同时用不同语言，不许串。"""
    import threading
    from webui import preview_convert as _pc
    assert hasattr(_pc, "_LANG_LOCAL"), "语言状态必须是 threading.local，不能是模块全局"
    results, barrier = {}, threading.Barrier(2, timeout=10)

    def worker(lang):
        _pc.set_lang(lang)
        barrier.wait()
        seen = set()
        for _ in range(400):
            seen.add(_pc.T("中文", "English"))
            seen.add(_pc.lang_now())
        results[lang] = seen

    ts = [threading.Thread(target=worker, args=(x,)) for x in ("zh", "en")]
    [t.start() for t in ts]
    [t.join(15) for t in ts]
    assert results["zh"] == {"中文", "zh"}
    assert results["en"] == {"English", "en"}
    _pc.set_lang("zh")


def _p5_regions():
    """(完整 html, [(名字, 代码)]) —— 前端 P5 区块"""
    with io.open(os.path.join(server.MEMOMICS_DIR, "webui", "index.html"), encoding="utf-8") as f:
        html = f.read()
    out = []
    for name, a, b in (("P5-VIEWER", "// === P5-VIEWER-BEGIN", "// === P5-VIEWER-END ==="),
                       ("P5-SORT", "// === P5-SORT-BEGIN", "// === P5-SORT-END ==="),
                       # P6-2：意图确认弹窗（P3 P4 用的就是它）也纳入扫描
                       ("P3-ASKFORM", "// === P3(2026-09-22): 意图确认弹窗", "// === 停止 agent ===")):
        i, j = html.find(a), html.find(b)
        assert i > 0 and j > i, name + " 区块找不到"
        out.append((name, html[i:j]))
    return html, out


def test_p5_frontend_has_no_hardcoded_chinese():
    """P5 前端区块（含 P3/P4 的意图确认弹窗）里不许再有硬编码中文。

    文案必须走 t()/tf()，否则切英文界面会残留中文。
    """
    import re
    html, regions = _p5_regions()
    cjk = re.compile(r"[\u4e00-\u9fff]")
    bad = []
    for name, body in regions:
        body = re.sub(r"/\*.*?\*/", "", body, flags=re.S)
        body = re.sub(r"^\s*//.*$", "", body, flags=re.M)
        body = re.sub(r"\s+//[^\n]*$", "", body, flags=re.M)   # 行尾注释（注释里可以有中文）
        for line in body.split("\n"):
            if cjk.search(line):
                bad.append("%s: %s" % (name, line.strip()[:120]))
    assert not bad, "还有硬编码中文：\n" + "\n".join(bad)


def test_i18n_dicts_have_identical_p5_keys():
    """zh / en 两本字典键必须完全一致，且前端用到的键都得存在（缺一个英文界面就露中文）。"""
    import re
    html, _ = _p5_regions()
    i = html.find("var I18N = {")
    j = html.find("var UI_LANG", i)
    block = html[i:j]
    zh_i, en_i = block.find("zh: {"), block.find("en: {")
    zh = set(re.findall(r"'([A-Za-z0-9_]+)'\s*:", block[zh_i:en_i]))
    en = set(re.findall(r"'([A-Za-z0-9_]+)'\s*:", block[en_i:]))
    assert zh and len(zh) == len(en), "zh=%d en=%d" % (len(zh), len(en))
    assert zh == en, "键不一致: %s" % sorted(zh ^ en)
    used = set(re.findall(r"\btf?\(\s*'([A-Za-z0-9_]+)'", html))
    used |= set(re.findall(r'data-i18n(?:-title|-ph)?="([A-Za-z0-9_]+)"', html))
    missing = sorted(k for k in used if k not in zh)
    assert not missing, "前端用到但字典里没有的键: %s" % missing
    need = {"rs_up", "rs_root", "rs_viewed", "rs_unread", "rs_unread_only", "rs_unread_done",
            "rs_session", "rs_count_figs", "rs_count_items", "rs_count_unread", "rs_figs_empty",
            "rs_figs_failed", "rv_opening", "rv_sys", "rv_folder", "rv_download", "rv_cannot_show"}
    assert not (need - zh), "缺少键: %s" % sorted(need - zh)


@pytest.mark.api
def test_figures_newest_first_by_default(client, res_dir):
    sid, d = res_dir
    for n, t in (("f_old.png", 1_600_000_000), ("f_new.png", 1_800_000_000), ("f_mid.png", 1_700_000_000)):
        p = os.path.join(d, n)
        with open(p, "wb") as f:
            f.write(bytes.fromhex("89504e470d0a1a0a") + b"0" * 16)
        os.utime(p, (t, t))
    j = client.get("/api/results/" + sid + "/figures").json()
    assert j["sort"] == "time_desc"
    assert [f["name"] for f in j["figures"]] == ["f_new.png", "f_mid.png", "f_old.png"]
    j2 = client.get("/api/results/" + sid + "/figures", params={"sort": "time_asc"}).json()
    assert [f["name"] for f in j2["figures"]] == ["f_old.png", "f_mid.png", "f_new.png"]
