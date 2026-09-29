"""markdown 表格渲染测试。

用户 2026-09 报的 bug：表里写 |coef| 这种「绝对值竖线」，markdown 必须转义成 \\|coef\\|，
但渲染器用 line.split('|') 切单元格，把 `+ \\|coef\\| >0.20` 切成 3 格，
表头于是 9 列、数据行 5 列，整张表看起来是散的。

这里既做静态检查（两个渲染入口必须共用切分器、不许再有裸 split），
也在有 node 时把 index.html 里真实的函数抽出来跑一遍真实数据。
"""
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
INDEX = ROOT / "webui" / "index.html"

# 用户原表（已按 markdown 正确转义 |coef|）
USER_TABLE_MD = "\n".join([
    "| 对比 | FDR<0.05 | + \\|coef\\| >0.20 | + \\|coef\\| >0.25 | 0.20→0.25 再砍 |",
    "|---|---|---|---|---|",
    "| Aging (Y_Pre vs O_Pre) | 59,681 行 / 8,491 基因 | 34,289 / 7,591 | 23,178 / 6,679 | −11,111 行（−32.4%） |",
    "| Ex_Old (O_Pre vs O_Post) | 51,241 / 7,941 | 6,056 / 3,382 | 1,846 / 985 | −4,210（−69.5%） |",
    "| DM (O_Pre vs OD_Pre) | 36,473 / 7,540 | 678 / 319 | 311 / 120 | −367（−54.1%） |",
])


@pytest.fixture(scope="module")
def html():
    return INDEX.read_text(encoding="utf-8")


def _extract_fn(src, name):
    """抽出 index.html 里某个顶层 function 的完整源码（两个函数体内没有字符串花括号）。"""
    at = src.find("function %s(" % name)
    assert at != -1, "index.html 里找不到 %s()" % name
    i = src.index("{", at)
    depth = 0
    for j in range(i, len(src)):
        if src[j] == "{":
            depth += 1
        elif src[j] == "}":
            depth -= 1
            if depth == 0:
                return src[at:j + 1]
    raise AssertionError("%s() 的大括号没闭合" % name)


def _run_in_node(table_md, tmp_path):
    """把 index.html 里真实的 mdSplitRow/mdRenderTable 抽出来，跑生产同款渲染管线。"""
    node = shutil.which("node")
    if not node:
        pytest.skip("本机没有 node，跳过动态表格测试")
    src = INDEX.read_text(encoding="utf-8")
    md_file = tmp_path / "table.md"
    md_file.write_text(table_md, encoding="utf-8")
    run = tmp_path / "run.mjs"
    run.write_text(
        "import fs from 'node:fs'\n"
        "const md = fs.readFileSync(process.argv[2], 'utf8')\n"
        + _extract_fn(src, "mdSplitRow") + "\n"
        + _extract_fn(src, "mdRenderTable") + "\n"
        # 与 renderMarkdown 里一模一样的调用方式
        "const html = md.replace(/\\r\\n?/g, '\\n')\n"
        "  .replace(/((?:^\\|.*\\|[ \\t]*\\n?)+)/gm, mdRenderTable)\n"
        "const th = [...html.matchAll(/<th>(.*?)<\\/th>/g)].map(m => m[1])\n"
        "const trs = [...html.matchAll(/<tr>(.*?)<\\/tr>/g)].map(m => m[1])\n"
        "const tdCounts = trs.slice(1).map(r => (r.match(/<td>/g) || []).length)\n"
        "process.stdout.write(JSON.stringify({th, tdCounts,"
        " tableCount: (html.match(/<table>/g) || []).length, html}))\n",
        encoding="utf-8")
    p = subprocess.run([node, str(run), str(md_file)],
                       capture_output=True, timeout=60)
    assert p.returncode == 0, "node 跑挂了: " + p.stderr.decode("utf-8", "replace")[:400]
    return json.loads(p.stdout.decode("utf-8"))


def test_escaped_pipe_stays_in_one_cell(html, tmp_path):
    """核心回归：\\|coef\\| 必须留在同一格里，表头列数要与数据行一致。"""
    r = _run_in_node(USER_TABLE_MD, tmp_path)
    assert r["tableCount"] == 1, "连续 | 行必须是同一张表，不能拆成 %d 张" % r["tableCount"]
    assert len(r["th"]) == 5, "表头应该是 5 列，实际 %d 列：%s" % (len(r["th"]), r["th"])
    assert r["th"][2] == "+ |coef| >0.20", "第 3 列表头被切开了：%r" % r["th"][2]
    assert r["th"][3] == "+ |coef| >0.25", "第 4 列表头被切开了：%r" % r["th"][3]
    assert r["tdCounts"] and all(n == 5 for n in r["tdCounts"]), \
        "数据行列数应与表头一致：%s" % r["tdCounts"]


def test_row_count_normalized_to_header(html, tmp_path):
    """边界：某行多写一个未转义的 | 时，按表头列数截断，不能把整表撑错位。"""
    md = "\n".join([
        "| a | b | c |",
        "|---|---|---|",
        "| 1 | 2 | 3 | 4 |",          # 多一格 → 截断
        "| 5 | 6 |",                   # 少一格 → 补空
    ])
    r = _run_in_node(md, tmp_path)
    assert len(r["th"]) == 3
    assert r["tdCounts"] == [3, 3], "列数没对齐表头：%s" % r["tdCounts"]


def test_plain_table_still_renders(html, tmp_path):
    """回归：普通表格（没有转义竖线）不能被改坏。"""
    md = "\n".join([
        "| 基因 | log2FC |",
        "|---|---|",
        "| TP53 | 1.5 |",
        "| MYC | -2.1 |",
    ])
    r = _run_in_node(md, tmp_path)
    assert len(r["th"]) == 2 and r["th"] == ["基因", "log2FC"]
    assert r["tdCounts"] == [2, 2]
    assert r["tableCount"] == 1


def test_splitter_understands_escaped_pipe(html):
    r"""静态：切分器必须显式认 | 转义（否则又会退回成裸 split）。"""
    body = _extract_fn(html, "mdSplitRow")
    assert r"ch === '\\'" in body, "mdSplitRow 没识别反斜杠"
    assert r"nx === '|'" in body, "mdSplitRow 没把 \| 当成转义"
    assert r"cur += '|'" in body, "\| 没有还原成真竖线"


def test_both_entry_points_share_the_splitter(html):
    """静态：两个渲染入口（renderTextSegment / renderMarkdown）必须共用同一张表渲染器。

    历史上这个 bug 就是因为两处各写了一份 split('|')。
    """
    assert html.count("/gm, mdRenderTable)") == 2, \
        "表格入口应该有 2 个（renderTextSegment / renderMarkdown），实际 %d 个" % html.count("/gm, mdRenderTable)")
    # 代码里不许再有裸 split('|')（注释里提到不算）
    code = "\n".join(l for l in html.split("\n")
                     if not l.strip().startswith(("//", "——", "*", "/*")))
    assert "split('|')" not in code, "还有地方在用裸 split('|') 切单元格"


def test_renderer_normalizes_column_count(html):
    """静态：渲染器要有按表头补齐/截断的兜底。"""
    body = _extract_fn(html, "mdRenderTable")
    assert "var cols = rows[0].length" in body, "没按表头定列数"
    assert "while (rows[r].length < cols) rows[r].push('')" in body, "缺列没有补空"
    assert "rows[r].length > cols) rows[r].length = cols" in body, "多列没有截断"
