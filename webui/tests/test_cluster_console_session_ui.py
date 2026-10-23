# -*- coding: utf-8 -*-
"""集群控制台「🧠 会话」入口守卫（webui/index.html）—— 2026-10-09。

这一层跑不了真浏览器，所以：
- 静态断言：七个 session_* 模式在 CLUSTER_MODES / 下拉 order 里都在，渲染器覆盖
  会话 payload 的关键字段（readrds_calls / last_result_tail / ckpt_recent / sessions）；
- 把 clusterTokens / clusterBuildArgs / clusterRenderResult 从 index.html **原样抽出来**，
  用 node 带桩跑真实代码：断言七个模式构造的 payload 正确（含「session_exec 留空 → 退化看状态」、
  「session_restore 只给检查点名 → 用最近会话号」这类真实交互）；
- node 不在就 skip（CI 上没有 node 也不该因此红）。
"""
import json
import os
import re
import shutil
import subprocess
import tempfile

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
INDEX = os.path.join(ROOT, "webui", "index.html")
NODE = shutil.which("node")

SESSION_MODES = ["session_start", "session_exec", "session_status", "session_save",
                 "session_restore", "session_stop", "session_list"]


def _html() -> str:
    with open(INDEX, encoding="utf-8") as f:
        return f.read()


def _fn(html: str, name: str) -> str:
    m = re.search(r"function %s\([^)]*\) \{.*?\n\}" % re.escape(name), html, re.S)
    assert m, "index.html 里找不到 %s —— 集群控制台会话入口被改坏或删了" % name
    return m.group(0)


def _console_js() -> str:
    html = _html()
    return "\n\n".join([
        "var _clusterLastSession = '', _clusterLastJob = '';",
        _fn(html, "clusterTokens"),
        _fn(html, "clusterBuildArgs"),
        _fn(html, "clusterRenderResult"),
        "module.exports = {clusterTokens: clusterTokens, clusterBuildArgs: clusterBuildArgs, "
        "clusterRenderResult: clusterRenderResult, "
        "setLast: function(s, j) { _clusterLastSession = s; _clusterLastJob = j; }, "
        "getLast: function() { return {session: _clusterLastSession, job: _clusterLastJob}; }};",
    ])


_TMPDIR = None


def _module_path() -> str:
    global _TMPDIR
    if _TMPDIR is None:
        _TMPDIR = tempfile.mkdtemp(prefix="memomics_ccsession_")
    path = os.path.join(_TMPDIR, "_cc_session.js")
    with open(path, "w", encoding="utf-8") as f:
        f.write(_console_js())
    return path


def _run_node(js: str, *args):
    tmp = os.path.join(HERE, "_cc_session_driver.js")
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


def test_console_has_seven_session_modes_with_hints():
    html = _html()
    for mode in SESSION_MODES:
        assert re.search(r"\b%s:\s*\{ opt:" % mode, html), "CLUSTER_MODES 少了 %s" % mode
    # 下拉顺序里也要有（openClusterConsole 的 order 数组），否则页面上选不到
    m = re.search(r"var order = \[(.*?)\];", html, re.S)
    assert m, "index.html 里找不到模式下拉的 order 数组"
    order = m.group(1)
    for mode in SESSION_MODES:
        assert "'%s'" % mode in order, "下拉 order 少了 %s" % mode
    assert order.index("'session_start'") > order.index("'jobs'"), "会话模式应排在下拉末尾（新功能别插队）"


def test_render_covers_session_payload_fields():
    html = _html()
    for token in ("readrds_calls", "last_result_tail", "ckpt_recent", "r.alive === false",
                  "r.sessions", "daemon_status", "r.rss_h"):
        assert token in html, "会话渲染缺字段：%s" % token
    assert "last_result_tail: 1" in html, "会话渲染的 skip 表漏了 last_result_tail（会重复打印 JSON）"


def test_restore_branch_accepts_checkpoint_name_only():
    """2026-10-09 实测修复：session_restore 只给一个 token 时是**检查点名**，不能当会话号。"""
    body = _fn(_html(), "clusterBuildArgs")
    assert "first.indexOf('s-') !== 0" in body, "session_restore 少了「s- 前缀才当会话号」的判定"
    assert "sb.name = first" in body, "session_restore 没把单 token 当检查点名"


# ------------------------------------------------------------------ node 实测


@pytest.mark.skipif(not NODE, reason="本机没有 node，跳过页面 JS 实测")
def test_build_args_for_session_modes():
    cases = {
        "last_session": "s-20261009-014300-vq48",
        "last_job": "job-1",
        "build": [
            {"mode": "session_start", "text": "", "want": {"action": "session_start"}},
            {"mode": "session_start", "text": "/data/MuSC.rds",
             "want": {"action": "session_start", "input": "/data/MuSC.rds"}},
            {"mode": "session_exec", "text": "", "want": {"action": "session_status"}},
            {"mode": "session_exec", "text": "library(Seurat)\ncat(1)\n",
             "want": {"action": "session_exec", "code": "library(Seurat)\ncat(1)\n"}},
            {"mode": "session_status", "text": "",
             "want": {"action": "session_status", "session_id": "s-20261009-014300-vq48"}},
            {"mode": "session_status", "text": "s-other",
             "want": {"action": "session_status", "session_id": "s-other"}},
            {"mode": "session_save", "text": "s-other musc-markers",
             "want": {"action": "session_save", "session_id": "s-other", "name": "musc-markers"}},
            {"mode": "session_restore", "text": "musc-markers-small",
             "want": {"action": "session_restore", "session_id": "s-20261009-014300-vq48",
                      "name": "musc-markers-small"}},
            {"mode": "session_restore", "text": "s-other ck1",
             "want": {"action": "session_restore", "session_id": "s-other", "name": "ck1"}},
            {"mode": "session_stop", "text": "",
             "want": {"action": "session_stop", "session_id": "s-20261009-014300-vq48"}},
            {"mode": "session_list", "text": "", "want": {"action": "session_list"}},
        ],
        "render": {"result": {"status": "ok", "session_id": "s-20261009-014300-vq48", "node": "node4",
                              "alive": True, "daemon_status": "idle", "pid": "109595", "rss_h": "3.0GB",
                              "objects": "20", "jobs_done": "10", "readrds_calls": "1",
                              "r_version": "R version 4.4.1 (2024-06-14)",
                              "input": "/data/MuSC.rds", "object": "MuSC_exercise_clean_dele_cluster_umap",
                              "last_result_tail": "status: ok\nFindMarkers 用时 3.6 秒"}},
    }
    driver = """
const cases = JSON.parse(process.argv[2]);
const M = require(process.argv[3]);
const lines = [];
global.clusterPrint = function (t, c) { lines.push(String(t)); };
M.setLast(cases.last_session, cases.last_job);
const bad = [];
for (const c of cases.build) {
  const got = M.clusterBuildArgs(c.mode, c.text);
  if (JSON.stringify(got) !== JSON.stringify(c.want)) bad.push({mode: c.mode, text: c.text, got: got, want: c.want});
}
M.clusterRenderResult('session_status', cases.render);
console.log(JSON.stringify({bad: bad, rendered: lines.join('\\n')}));
"""
    r = _run_node(driver, json.dumps(cases, ensure_ascii=False), _module_path())
    assert r.returncode == 0, "node 跑挂了：%s" % r.stderr
    out = json.loads(r.stdout.strip().splitlines()[-1])
    assert out["bad"] == [], "session_* 构造的 payload 不对：%s" % out["bad"]
    rendered = out["rendered"]
    for token in ("s-20261009-014300-vq48", "pid 109595", "readRDS 审计：本会话累计 1 次",
                  "FindMarkers 用时 3.6 秒", "daemon：idle"):
        assert token in rendered, "会话渲染结果里看不到 %r：\n%s" % (token, rendered)


@pytest.mark.skipif(not NODE, reason="本机没有 node，跳过页面 JS 实测")
def test_no_last_session_does_not_invent_session_id():
    driver = """
const M = require(process.argv[2]);
M.setLast('', '');
const got = M.clusterBuildArgs('session_status', '');
console.log(JSON.stringify(got));
"""
    r = _run_node(driver, _module_path())
    assert r.returncode == 0, r.stderr
    assert json.loads(r.stdout.strip().splitlines()[-1]) == {"action": "session_status"}, \
        "没有最近会话号时不能编一个 session_id（交给后端给可操作提示）"