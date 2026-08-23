# -*- coding: utf-8 -*-
"""test_lit_flows.py — 文献库批量跳过逻辑 + 会话绑定 12h 行为（批K，2026-08-16）。

确定性测试：临时 HERMES_HOME + 桩函数，不产生真实 LLM 调用。
"""
import json
import os
import sys
import tempfile
import time

os.environ["HERMES_HOME"] = tempfile.mkdtemp(prefix="lit_flows_")
sys.path.insert(0, ".")
sys.path.insert(0, "hermes-agent")

import memomics.bio_tools.literature_library as ll  # noqa: E402

LIB = ll._library_dir()
os.makedirs(LIB, exist_ok=True)


def _mk_lib(entries):
    with open(os.path.join(LIB, ".pdf_index.json"), "w", encoding="utf-8") as f:
        json.dump(entries, f, ensure_ascii=False)


def _fake_paper(name):
    return {"file": name, "title": f"Paper {name}", "path": f"{LIB}/{name}",
            "journal": "", "year": "2025", "doi": "", "downloaded_at": "2026-08-16",
            "source": "user_import", "tags": {}}


PASS, FAIL = 0, 0


def check(label, got, expected):
    global PASS, FAIL
    ok = got == expected
    PASS += ok
    FAIL += (not ok)
    print(f"{'PASS' if ok else 'FAIL'} | {label} | got={got!r} expected={expected!r}")


# ── 1. 一键全文提炼只处理未提炼 ──
_mk_lib([
    {**_fake_paper("a.pdf"), "summary_done": True},
    {**_fake_paper("b.pdf"), "summary_done": False},
    {**_fake_paper("c.pdf"), "summary_done": False},
])
called = []
ll.summarize_paper = lambda name, progress_cb=None: called.append(name) or json.dumps(
    {"ok": True, "summary": {"idea": "x"}, "file": name})
r = json.loads(ll.summarize_all_papers())
check("summarize_all pending=2", r.get("pending"), 2)
check("summarize_all 只调用未提炼", sorted(called), ["b.pdf", "c.pdf"])

# 全部已提炼 → 不调用任何
_mk_lib([{**_fake_paper("a.pdf"), "summary_done": True}])
called.clear()
r = json.loads(ll.summarize_all_papers())
check("summarize_all 全已提炼 pending=0", r.get("pending"), 0)
check("summarize_all 全已提炼不调用", called, [])

# ── 2. 一键入库只处理未入库 ──
_mk_lib([
    {**_fake_paper("a.pdf"), "kb_done": True},
    {**_fake_paper("b.pdf"), "kb_done": False},
])
called.clear()
ll.kb_extract_from_paper = lambda name, progress_cb=None: called.append(name) or json.dumps(
    {"ok": True, "written": [{"name": "x", "path": "p"}]})
r = json.loads(ll.extract_all_papers())
check("extract_all pending=1", r.get("pending"), 1)
check("extract_all 只调用未入库", called, ["b.pdf"])

# ── 3. 会话绑定 12h 行为 ──
ll.bind_session("session-A", force=True)
b1 = ll.get_binding()
check("绑定A后 session_id", b1.get("session_id"), "session-A")
check("绑定A后未过期", b1.get("expired"), False)
r = ll.bind_session("session-B", force=False)
check("未过期时B不换绑", r.get("session_id"), "session-A")
# 过期 → 自动换绑 B
bp = os.path.join(LIB, ".binding.json")
b = json.load(open(bp, encoding="utf-8"))
b["bound_at_ts"] = time.time() - 13 * 3600
json.dump(b, open(bp, "w", encoding="utf-8"))
b2 = ll.get_binding()
check("13h 后过期", b2.get("expired"), True)
r = ll.bind_session("session-B", force=False)
check("过期后B自动换绑", r.get("session_id"), "session-B")
check("换绑后剩余12h", r.get("remaining_hours"), 12.0)

# ── 4. 查看摘要不改绑定 ──
before = open(bp, "rb").read()
_mk_lib([{**_fake_paper("a.pdf"), "summary": {"idea": "想法"}, "summary_done": True}])
r = json.loads(ll.get_summary("a.pdf"))
check("get_summary ok", r.get("ok"), True)
check("get_summary 不影响绑定文件", open(bp, "rb").read(), before)
check("get_summary kb_done 独立", r.get("kb_done"), False)

print(f"\nRESULT: {PASS} PASS / {FAIL} FAIL")
sys.exit(1 if FAIL else 0)
