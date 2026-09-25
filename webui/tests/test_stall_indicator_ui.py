# -*- coding: utf-8 -*-
"""状态条静默指示：静态接线 + 前端行为回归（2026-09-26）

用户反馈「MemOmics 有时候会卡住，长时间不输出内容」。后端已补进度上报
（见 test_debate_progress.py），前端这一层要保证：
1) 状态条真的会写「⏳ 已 N 秒无新输出」；
2) 那个 N 每秒自己会走（ticker 间隔 1000ms，不是 15 秒）；
3) _lastActivityTs 有正式声明、且所有"界面有新内容"的事件都给它盖时间戳。
行为测试在 stall_indicator_frontend.cjs（把 index.html 真实函数抠出来跑）。
"""
import os
import re
import subprocess
import sys

import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
HTML_PATH = os.path.join(ROOT, "webui", "index.html")
CJS_PATH = os.path.join(ROOT, "webui", "tests", "stall_indicator_frontend.cjs")


@pytest.fixture(scope="module")
def html():
    with open(HTML_PATH, encoding="utf-8") as f:
        return f.read()


def test_silent_seconds_helper_exists(html):
    assert "function _silentSeconds(" in html
    assert "_silentSeconds(now) >= 60" in html, "ticker 里没用静默秒数判断"


def test_status_bar_shows_silence(html):
    i = html.index("function updateLiveStatus(")
    body = html[i:i + 1600]
    assert "⏳ 已 " in body and "秒无新输出" in body
    assert "silent >= 120" in body, "静默 2 分钟要标红"


def test_activity_ts_is_declared(html):
    """以前 _lastActivityTs 是隐式全局，只在 tool_progress 里赋值。"""
    assert re.search(r"var _lastActivityTs = 0;", html), "必须正式声明"
    assert "_lastActivityTs = Date.now();" in html


def test_all_content_events_stamp_activity(html):
    m = re.search(r"var _ACTIVITY_TYPES = \{([^}]*)\};", html)
    assert m, "找不到 _ACTIVITY_TYPES"
    for t in ("delta", "reasoning", "thinking", "tool_start", "tool_progress",
              "progress", "tool_complete", "status"):
        assert t + ": 1" in m.group(1), f"{t} 不算活动 → 静默计时会误报"
    assert "_ACTIVITY_TYPES[msg.type]" in html, "handleMessage 里没盖时间戳"


def test_ticker_runs_every_second(html):
    i = html.index("function _startLiveStatusTicker(")
    body = html[i:i + 900]
    assert "}, 1000);" in body, "间隔必须是 1 秒，否则静默数字自己不走"
    assert "}, 15000);" not in body


def test_tool_progress_honours_status(html):
    i = html.index("} else if (msg.type === 'tool_progress') {")
    body = html[i:i + 700]
    assert "msg.status || 'pending'" in body, "后端报的 done 被丢了"
    assert "substring(0,80)" in body


def test_frontend_behaviour_suite_green():
    proc = subprocess.run([("node.exe" if os.name == "nt" else "node"), CJS_PATH],
                          cwd=ROOT, capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=180)
    out = (proc.stdout or "") + (proc.stderr or "")
    assert proc.returncode == 0, out[-3000:]
    m = re.search(r"(\d+) pass / (\d+) fail", out)
    assert m and int(m.group(2)) == 0, out[-2000:]
    assert int(m.group(1)) >= 18
