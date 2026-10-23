# -*- coding: utf-8 -*-
"""📓 Notebook 总端（webui/index.html + 集群常驻 R 会话）守卫测试 —— 2026-10-09。

用户要的是「像接了个 Jupyter」：输入框最上方一条总端条 → 点开看常驻 R 会话里跑过的 cell
（代码 + 输出 + 图）与正在跑的活。这一层没有真浏览器，所以分两段：

- 静态接线：条/面板 DOM 在、位置对（goal-bar 之上的最上面）、只走既有的 /api/cluster/exec
  五个动作（不新增路由）、面板打开才轮询、图按 data URI 内联；
- node 实测：把 nb* 纯函数从 index.html **原样抽出来**跑真代码（格式、状态行、cell HTML、
  转义、投递 payload、边跑边冒图的筛选），断言给的是真结果不是「看着像」。

node 不在就 skip。
"""
import json
import os
import re
import shutil
import subprocess
import tempfile
from html.parser import HTMLParser

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
INDEX = os.path.join(ROOT, "webui", "index.html")
NODE = shutil.which("node")

PURE_FUNCS = ["nbEsc", "nbFmtMs", "nbStatusLine", "nbStatusClass", "nbBuildExecArgs",
              "nbSessionOptions", "nbRunningPlots", "nbPlotsOfCells", "nbCellHtml",
              "nbRunningHtml", "nbPendingHtml"]


def _html() -> str:
    with open(INDEX, encoding="utf-8") as f:
        return f.read()


def _fn(html: str, name: str) -> str:
    m = re.search(r"function %s\([^)]*\) \{.*?\n\}" % re.escape(name), html, re.S)
    assert m, "index.html 里找不到 %s —— Notebook 总端被改坏或删了" % name
    return m.group(0)


def _nb_js() -> str:
    html = _html()
    parts = ["var _nbPending = [];",
             # 2026-10-23：Notebook 文案走通用翻译层 T()；沙箱里给身份函数（断言中文口径）
             "var UI_LANG = 'zh';",
             "function T(s) { return s; }"]
    parts += [_fn(html, n) for n in PURE_FUNCS]
    parts.append("module.exports = {%s, setPending: function (p) { _nbPending = p; }};"
                 % ", ".join("%s: %s" % (n, n) for n in PURE_FUNCS))
    return "\n\n".join(parts)


_TMPDIR = None


def _module_path() -> str:
    global _TMPDIR
    if _TMPDIR is None:
        _TMPDIR = tempfile.mkdtemp(prefix="memomics_nb_")
    path = os.path.join(_TMPDIR, "_nb.js")
    with open(path, "w", encoding="utf-8") as f:
        f.write(_nb_js())
    return path


def _run_node(js: str, *args):
    tmp = os.path.join(HERE, "_nb_driver.js")
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(js)
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    try:
        return subprocess.run([NODE, tmp] + list(args), capture_output=True, text=True,
                              encoding="utf-8", errors="replace", timeout=120, env=env)
    finally:
        try:
            os.remove(tmp)
        except OSError:
            pass


# ------------------------------------------------------------------ 静态接线


def test_notebook_entry_lives_in_top_bar_next_to_tasks():
    """用户口径（2026-10-09 修正）：入口放**最上面**，在「后台任务」旁边，不是在输入框上方。"""
    html = _html()
    assert 'id="nav-bar"' not in html  # 防呆：不要出现和已有 id 冲突的名字
    i_chip = html.index('id="nav-notebook"')
    i_tasks = html.index('id="nav-tasks"')
    i_header_end = html.index('</div>\n    <div class="chat-messages"', i_tasks)
    assert i_tasks < i_chip < i_header_end, "「📓 总端」应在顶部横栏里、且排在「后台任务」后面"
    assert 'onclick="openNotebook()"' in html[i_chip - 200:i_chip + 400]
    for token in ('class="nb-dot" id="nb-dot"', 'id="nb-session-mini"', 'id="nb-badge"',
                  "data-i18n=\"nav_notebook\"", 'id="nb-mask"', 'id="nb-cells"', 'id="nb-code"',
                  'id="nb-session-sel"'):
        assert token in html, "Notebook 总端缺 DOM：%s" % token
    # 旧的「输入框上方长条」必须已经不在了（用户明确否掉了那个位置）
    assert 'id="nb-bar"' not in html, "输入框上方的总端条该撤掉（用户要顶部横栏）"
    # 两套 i18n 词典都要有键
    assert "'nav_notebook':" in html, "i18n 少了 nav_notebook"
    assert html.count("'nav_notebook':") >= 2, "中英两套词典都要有 nav_notebook"


def test_notebook_only_uses_existing_cluster_actions():
    """不新增 HTTP 路由（server.py 白名单就那 20 个动作）；面板只准使唤既有动作名。"""
    html = _html()
    nb_js = html[html.index("// === 📓 Notebook 总端"):]
    nb_js = nb_js[:nb_js.index("// 启动后检测")]
    assert "/api/cluster/exec" in nb_js
    assert "/api/notebook" not in html and "/api/nb" not in html, "不该偷偷加新路由"
    for act in ("session_list", "session_status", "session_cells", "session_plot", "session_exec"):
        assert "'%s'" % act in nb_js, "Notebook 少了动作：%s" % act
    assert "async: true" in nb_js or "async:true" in nb_js, "投 cell 必须异步（长 cell 不能挂死浏览器请求）"
    # 面板开着才轮询；关掉要停
    assert re.search(r"_nbTimer = setInterval\(function \(\) \{ nbRefresh\(false\); \}, 2500\)", nb_js)
    assert "clearInterval(_nbTimer)" in nb_js, "关面板没停轮询（会一直 ssh 打集群）"
    # 图：按需取 + data URI + 缓存
    assert "data_uri_prefix" in nb_js and "r.b64" in nb_js
    assert "_nbPlotCache" in nb_js and "_nbPlotOrder" in nb_js
    assert "budget = 4" in nb_js, "一次取图没设上限（一次拖几 MB 会卡）"


def test_notebook_refreshes_bar_after_console_actions():
    html = _html()
    body = _fn(html, "clusterExec")
    assert "nbInit" in body, "控制台跑完（开会话/投代码）后总端胶囊不会跟着刷新"
    assert re.search(r"setTimeout\(function \(\) \{ if \(typeof nbInit === 'function'\) nbInit\(\); \}, 1500\)", html), \
        "启动时没初始化总端胶囊"
    upd = _fn(html, "nbUpdateBar")
    for token in ("nb-dot", "nb-session-mini", "nb-badge", "nav-notebook"):
        assert token in upd, "nbUpdateBar 没更新顶部胶囊的 %s" % token


def test_notebook_honest_limits_are_documented():
    """诚实边界写在代码注释里：秒级轮询 / 不能中断 / 本地内核不在这个面板。"""
    html = _html()
    seg = html[html.index("// === 📓 Notebook 总端"):]
    seg = seg[:seg.index("// 启动后检测")]
    for token in ("秒级轮询", "不能中断", "本地内核"):
        assert token in seg, "Notebook 注释里少了边界说明：%s" % token


class _DomChecker(HTMLParser):
    """轻量 DOM 结构检查：用来抓「我新插的 <div> 没闭合」这类会让整页崩掉的手误。"""

    VOID = {"br", "img", "input", "meta", "link", "hr", "source", "area", "base", "col",
            "embed", "param", "track", "wbr"}

    def __init__(self):
        HTMLParser.__init__(self, convert_charrefs=True)
        self.stack = []
        self.problems = []

    def handle_starttag(self, tag, attrs):
        if tag in self.VOID:
            return
        self.stack.append((tag, self.getpos()[0]))

    def handle_startendtag(self, tag, attrs):
        return

    def handle_endtag(self, tag):
        if tag in self.VOID:
            return
        for i in range(len(self.stack) - 1, -1, -1):
            if self.stack[i][0] == tag:
                if i != len(self.stack) - 1:
                    self.problems.append("第 %d 行：</%s> 之前 %s 还开着"
                                         % (self.getpos()[0], tag, self.stack[-1]))
                del self.stack[i:]
                return
        self.problems.append("第 %d 行：多出来的 </%s>" % (self.getpos()[0], tag))

    def unmatched(self):
        return [(t, ln) for t, ln in self.stack]


def test_notebook_dom_is_well_formed():
    """新插的胶囊/面板/放大层不能把 index.html 的标签结构搞坏（整页白屏级别的风险）。"""
    html = _html()
    i_head = html.index('<div class="chat-header">')
    seg_chip = html[i_head:html.index('<div class="chat-messages"', i_head)]
    seg_panel = html[html.index('<!-- === 📓 Notebook 总端（2026-10-09）'):html.index('<!-- === 添加节点向导')]
    for name, seg in (("顶部胶囊", seg_chip), ("面板", seg_panel)):
        c = _DomChecker()
        c.feed(seg)
        assert c.problems == [], "%s 的 DOM 结构有问题：%s" % (name, c.problems)
        assert c.unmatched() == [], "%s 有没闭合的标签：%s" % (name, c.unmatched())


# ------------------------------------------------------------------ node 实测


@pytest.mark.skipif(not NODE, reason="本机没有 node，跳过页面 JS 实测")
def test_nb_format_status_and_args():
    cases = {
        "fmt": [["500", "500 ms"], ["38900", "38.9 s"], ["95000", "1 分 35 秒"], ["", ""],
                [None, ""], ["1500", "1.5 s"]],
        "status": [
            [{"node": "node4", "pid": "109595", "busy": False, "rss_h": "2.9GB", "objects": "20",
              "readrds_calls": "1", "plots_total": "4"},
             ["node4", "pid 109595", "空闲", "RSS 2.9GB", "对象 20", "readRDS 1", "图 4"]],
            [{"node": "node4", "pid": "109595", "busy": True, "current_request": "r-20261009-020000-aa11"},
             ["node4", "pid 109595", "跑 r-20261009-020000-aa11"]],
            [{"status": "stopped", "node": "node1"}, ["node1", "已停止"]],
            [None, ["未接会话"]],
        ],
        "cls": [[None, ""], [{"status": "stopped"}, "dead"], [{"busy": True}, "busy"],
                [{"busy": False, "alive": True}, "on"]],
        "args": [["plot(1)\n", "s-1",
                  {"action": "session_exec", "session_id": "s-1", "code": "plot(1)\n", "async": True}],
                 ["x", "", {"action": "session_exec", "session_id": "", "code": "x", "async": True}]],
        "opts": [[[{"id": "s-1", "node": "node4", "title": "MuSC", "last_active": "2026-10-09 01:43"}],
                  ["s-1 · node4 · MuSC · 2026-10-09 01:43"]], [[], []]],
    }
    driver = """
const cases = JSON.parse(process.argv[2]);
const M = require(process.argv[3]);
const bad = [];
for (const [inp, want] of cases.fmt) { const g = M.nbFmtMs(inp); if (g !== want) bad.push(['fmt', inp, g, want]); }
for (const [inp, want] of cases.status) {
  const g = M.nbStatusLine(inp);
  for (const t of want) if (g.indexOf(t) < 0) bad.push(['status', inp, g, want]);
}
for (const [inp, want] of cases.cls) { const g = M.nbStatusClass(inp); if (g !== want) bad.push(['cls', inp, g, want]); }
for (const [code, sid, want] of cases.args) {
  const g = M.nbBuildExecArgs(code, sid);
  if (JSON.stringify(g) !== JSON.stringify(want)) bad.push(['args', code, g, want]);
}
for (const [rows, want] of cases.opts) {
  const g = M.nbSessionOptions(rows).map(o => o.label);
  if (JSON.stringify(g) !== JSON.stringify(want)) bad.push(['opts', rows, g, want]);
}
console.log(JSON.stringify({bad: bad}));
"""
    r = _run_node(driver, json.dumps(cases, ensure_ascii=False), _module_path())
    assert r.returncode == 0, "node 跑挂了：%s" % r.stderr
    out = json.loads(r.stdout.strip().splitlines()[-1])
    assert out["bad"] == [], "Notebook 纯函数结果不对：%s" % out["bad"]


@pytest.mark.skipif(not NODE, reason="本机没有 node，跳过页面 JS 实测")
def test_nb_cell_html_renders_code_output_plots_and_escapes():
    cases = {
        "cell": {"id": "r-20261009-015244-bb22", "status": "ok", "ms": "38900",
                 "started": "2026-10-09 01:52:44", "finished": "2026-10-09 01:53:23",
                 "readrds_calls": "1", "objects": "20",
                 "code": 'obj <- RunUMAP(obj, reduction = "harmony")',
                 "output": "UMAP done in 38.9s\n36 cells",
                 "warnings": "", "error": "",
                 "plots": [{"path": "/hw/s/plots/r-20261009-015244-bb22_01.png", "bytes": "7524"}]},
        "err": {"id": "r-bad", "status": "error", "ms": "120",
                "code": 'cat("<script>alert(1)</script>")',
                "output": "", "warnings": "", "error": "object 'obj' not found",
                "plots": []},
        "running": {"busy": True, "current_request": "r-run1", "busy_since": "2026-10-09 02:00:00",
                    "plots_total": "7", "last_result_tail": "line1\nline2\nlast line",
                    "plots_recent": "/hw/s/plots/r-run1_01.png\n/hw/s/plots/r-run1_02.png\n"
                                    "/hw/s/plots/r-old_09.png\n--count--\n7"},
        "pending": [{"id": "r-pending1", "code": "FindMarkers(x)", "at": "02:10:11"}],
    }
    driver = """
const cases = JSON.parse(process.argv[2]);
const M = require(process.argv[3]);
M.setPending(cases.pending);
const out = {
  cell: M.nbCellHtml(cases.cell, 3),
  err: M.nbCellHtml(cases.err, 4),
  running: M.nbRunningHtml(cases.running, M.nbRunningPlots(cases.running, 4)),
  pending: M.nbPendingHtml(),
  analyse: {plots: M.nbPlotsOfCells([cases.cell, cases.err]),
            runplots: M.nbRunningPlots(cases.running, 4)},
};
console.log(JSON.stringify(out));
"""
    r = _run_node(driver, json.dumps(cases, ensure_ascii=False), _module_path())
    assert r.returncode == 0, "node 跑挂了：%s" % r.stderr
    out = json.loads(r.stdout.strip().splitlines()[-1])

    cell = out["cell"]
    assert "nb-cell ok" in cell and "✓ ok" in cell and "38.9 s" in cell
    assert "readRDS 1" in cell and "对象 20" in cell
    assert "RunUMAP" in cell and "UMAP done in 38.9s" in cell
    # 关键：图必须挂成占位符（带路径），由 nbLoadImages 之后换成 <img src="data:...">
    assert 'data-nb-plot="/hw/s/plots/r-20261009-015244-bb22_01.png"' in cell, cell
    assert "nbLoadCodeAt(3)" in cell, "cell 上没有「复用代码」按钮"

    err = out["err"]
    assert "nb-cell err" in err and "✗ error" in err and "object &#39;obj&#39; not found" in err
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in err, "cell 代码没转义（XSS 风险）"
    assert "<script>" not in err

    running = out["running"]
    assert "⏳ 跑着呢" in running and "r-run1" in running
    assert 'data-nb-plot="/hw/s/plots/r-run1_01.png"' in running
    assert "r-old_09.png" not in running, "跑着的卡片里混进了上一个 cell 的图"
    assert "last line" in running

    assert "⏳ 已投递" in out["pending"] and "FindMarkers(x)" in out["pending"]
    assert out["analyse"]["runplots"] == ["/hw/s/plots/r-run1_01.png", "/hw/s/plots/r-run1_02.png"]
    assert out["analyse"]["plots"] == ["/hw/s/plots/r-20261009-015244-bb22_01.png"]