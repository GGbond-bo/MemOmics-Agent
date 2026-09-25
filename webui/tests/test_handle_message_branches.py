# -*- coding: utf-8 -*-
"""handleMessage 顶层分支表回归（2026-09-26）

起因：tool_complete 在 handleMessage 的 else-if 链里写了两次 —— 第二个分支
（"工具完成 → 结果面板自动刷新"）永远走不到，那个刷新从来没生效过。
new_figure 也是同样情况（写了两次，第二处是死代码）。

判据：顶层链分支的写法固定是行首两个空格 + "} else if (msg.type === 'x')"；
嵌套在别的 if 里的分支缩进更深，不算重复。这样只盯链上真会互相遮蔽的分支。
"""
import os
import re

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
HTML_PATH = os.path.join(ROOT, "webui", "index.html")
CHAIN_RE = re.compile(r"^  \} else if \(msg\.type === '([a-z_]+)'\)", re.M)


def _html():
    with open(HTML_PATH, encoding="utf-8") as f:
        return f.read()


def _chain_types(html):
    return CHAIN_RE.findall(html)


def test_no_duplicate_chain_branches():
    types = _chain_types(_html())
    dupes = {t: types.count(t) for t in set(types) if types.count(t) > 1}
    assert not dupes, f"else-if 链上有重复分支（后面的永远走不到）: {dupes}"


def test_tool_complete_single_branch_with_all_behaviours():
    html = _html()
    types = _chain_types(html)
    assert types.count("tool_complete") == 1
    i = html.index("} else if (msg.type === 'tool_complete')")
    seg = html[i:i + 1400]
    assert "_fmtToolResult" in seg, "时间线 done 摘要丢了"
    assert "renderDebateCard" in seg, "辩论卡片丢了"
    assert "refreshResults()" in seg, "结果面板自动刷新（原本是死代码）丢了"


def test_new_figure_single_branch():
    types = _chain_types(_html())
    assert types.count("new_figure") == 1, "new_figure 又写成两个分支了"
    i = _html().index("} else if (msg.type === 'new_figure')")
    assert "handleNewFigure" in _html()[i:i + 300]


def test_chain_is_still_well_formed():
    """链上至少还要有这些关键分支 —— 防止大段误删。"""
    types = set(_chain_types(_html()))
    for t in ("tool_start", "tool_complete", "tool_progress", "complete", "error",
              "cancelled", "notice", "ask_form", "status"):
        assert t in types, f"handleMessage 丢了分支: {t}"
