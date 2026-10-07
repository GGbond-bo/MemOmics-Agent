# -*- coding: utf-8 -*-
"""用 WPS / Word 的 COM 接口取学位论文 DOCX 的**真实分页**（目录、插图清单、附表清单页码的唯一可信来源）。

用法（需 pywin32；用装了它的解释器跑，例如系统 Python + PYTHONPATH 指向其 site-packages）：
    python wps_pages.py <docx路径> [输出json路径]

环境变量：
    WPS_PROGID  默认 KWPS.Application（WPS 文字）；装了微软 Word 可设为 Word.Application

产出：
    <json>        {total_pages, front_page, body_page, fig:{号:页}, tab:{}, sec:{}, head:{}, _abs:{...}}
    同名 .pdf     顺手导出，便于人翻页复核

⚠️ 两个必须保留的过滤（否则页码整体偏移，见 references/pagination-with-wps-com.md）：
    ① 跳过含「……」的目录行；② 标题键加长度上限（章级 ≤20 / 节 ≤30 字）；
    ③ 节标题取末次出现（真实节标题必在目录之后），章级标题取首次。
"""
import json
import os
import re
import sys

DOCX = sys.argv[1] if len(sys.argv) > 1 else r"E:/path/to/thesis.docx"
OUT = sys.argv[2] if len(sys.argv) > 2 else os.path.join(os.path.dirname(DOCX), "_wps_pages.json")
PDF = os.path.splitext(DOCX)[0] + ".pdf"
PROGID = os.environ.get("WPS_PROGID", "KWPS.Application")

import win32com.client as wc  # noqa: E402

app = wc.Dispatch(PROGID)
for attr, val in (("Visible", False), ("DisplayAlerts", 0)):
    try:
        setattr(app, attr, val)
    except Exception:
        pass

doc = app.Documents.Open(DOCX, ReadOnly=True)      # 只读：避免格式确认框卡死
try:
    doc.Fields.Update()
except Exception as e:
    print("[warn] Fields.Update:", e)

CAP_RE = re.compile(r"^(图|表)(\d+\.\d+)[\s\u3000]")
HEAD_RE = re.compile(
    r"^(第\s*\d+\s*章|摘\s*要|Abstract|目\s*录|插图和附表清单|符号、缩略词注释表|"
    r"参考文献|附录\s*[A-C]|作者简介|后记和致谢)"
)
SEC_RE = re.compile(r"^(\d+\.\d+(?:\.\d+)?)[\s\u3000]")

figs, tabs, secs, heads = {}, {}, {}, {}
n = doc.Paragraphs.Count
for i in range(1, n + 1):
    para = doc.Paragraphs(i)
    t = para.Range.Text.replace("\r", "").replace("\x07", "").strip()
    if not t or "……" in t:                          # ★ 目录行必须跳过
        continue
    try:
        pg = int(para.Range.Information(3))          # wdActiveEndPageNumber（绝对页）
    except Exception:
        continue
    core = re.sub(r"[\s\u3000]+", "", t)
    m = CAP_RE.match(t)
    if m:
        (figs if m.group(1) == "图" else tabs)[m.group(2)] = pg
    elif HEAD_RE.match(t) and len(core) <= 20:       # ★ 长度上限排除格式说明长句
        heads.setdefault(core, pg)                   # 章级/前置标题取首次
    else:
        m2 = SEC_RE.match(t)
        if m2 and len(core) <= 30:
            secs[m2.group(1)] = pg                   # ★ 节标题取末次

try:
    total = int(doc.ComputeStatistics(2))            # wdStatisticPages
except Exception:
    total = max(list(figs.values()) + list(tabs.values()) or [0])

try:
    doc.ExportAsFixedFormat(PDF, 17)
    print("[pdf] 已导出", PDF)
except Exception as e:
    print("[warn] 导出 PDF 失败:", e)

doc.Close(0)
app.Quit()


def roman(x):
    v = [(1000, 'M'), (900, 'CM'), (500, 'D'), (400, 'CD'), (100, 'C'), (90, 'XC'),
         (50, 'L'), (40, 'XL'), (10, 'X'), (9, 'IX'), (5, 'V'), (4, 'IV'), (1, 'I')]
    s = ''
    for k, r in v:
        while x >= k:
            s += r
            x -= k
    return s


front = heads.get("摘要")
body = heads.get("第1章绪论") or next(
    (v for k, v in heads.items() if k.startswith("第") and "章" in k and len(k) <= 20), None)
print(f"[定位] 摘要=p{front}  第1章=p{body}  总页数={total}")


def label(pg):
    """装订页码：前置罗马（摘要起 I），主体阿拉伯（第1章起重起算）"""
    if pg is None or pg < 0:
        return "—"
    if body and pg >= body:
        return str(pg - body + 1)
    if front and pg >= front:
        return roman(pg - front + 1)
    return "—"


res = {
    "total_pages": total, "front_page": front, "body_page": body,
    "fig": {k: label(v) for k, v in figs.items()},
    "tab": {k: label(v) for k, v in tabs.items()},
    "sec": {k: label(v) for k, v in secs.items()},
    "head": {k: label(v) for k, v in heads.items()},
    "_abs": {"fig": figs, "tab": tabs, "sec": secs, "head": heads},
}
json.dump(res, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("[插图]", res["fig"])
print("[附表]", res["tab"])
print("[写入]", OUT)

# 自检：第1章必须显示为 1
assert body, "未定位到第1章标题页 —— 检查过滤条件（目录行/长度上限）"
assert res["fig"] or res["tab"], "未取到任何图表页码 —— 检查 CAP_RE 与题注写法"
