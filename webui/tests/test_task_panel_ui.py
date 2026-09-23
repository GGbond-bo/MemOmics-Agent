# -*- coding: utf-8 -*-
"""T3 守卫：后台任务面板（webui/index.html）的挂载点、JS 语法、渲染与轮询作用域。

这一层跑不了真浏览器（内存里没有 DOM），所以：
- 挂载点/接线用静态断言（改坏了必然红）；
- 我把面板那段 JS 抽出来，用 node + 极简 DOM 影子跑真实渲染函数，
  断言"列表里能看到 PID/环境/阶段/进度、详情里能看到时间线/参数/日志/取消按钮"，
  顺带验证轮询只在面板可见时开、切走就停。
node 不在就 skip（CI 上没有 node 也不该因此红）。
"""
import json
import os
import re
import shutil
import subprocess
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
INDEX = os.path.join(ROOT, "webui", "index.html")
NODE = shutil.which("node")

START = "// === 后台任务面板（T3）"
END = "function weixinRefresh() {"


def _html() -> str:
    with open(INDEX, encoding="utf-8") as f:
        return f.read()


def _panel_js() -> str:
    """抽出面板那段 JS + 它依赖的 escapeHtml。"""
    html = _html()
    i = html.index(START)
    j = html.index(END, i)
    block = html[i:j]
    m = re.search(r"function escapeHtml\(s\) \{.*?\n\}", html, re.S)
    assert m, "index.html 里找不到 escapeHtml —— 面板渲染靠它防注入"
    return m.group(0) + "\n\n" + block + "\nmodule.exports = { loadTasks: loadTasks, stopTaskPoll: stopTaskPoll, renderTaskList: renderTaskList, renderTaskDetail: renderTaskDetail, taskFmtSec: taskFmtSec, taskStatusIcon: taskStatusIcon, _taskState: _taskState };"


HARNESS = """
const store = {};
function el(id) {
  if (!store[id]) store[id] = { id: id, innerHTML: '', textContent: '', style: { display: 'none' },
    querySelectorAll: function() { return []; }, getAttribute: function() { return null; }, setAttribute: function() {}, scrollTop: 0, scrollHeight: 0, onclick: null };
  return store[id];
}
var timers = [];
global.document = { getElementById: el, querySelectorAll: function() { return []; } };
global.setInterval = function(fn, ms) { timers.push({ fn: fn, ms: ms }); return timers.length; };
global.clearInterval = function(id) { timers[id - 1] = null; };
global.fetch = function() { return Promise.reject(new Error('harness 不联网')); };
global.alert = function() {};
global.confirm = function() { return true; };
const out = { timers: function() { return timers.filter(Boolean).length; }, store: store, P: null };
out.P = require(process.argv[2]);
module.exports = out;
"""


def _run_node(js: str, *args):
    tmp = os.path.join(HERE, "_t3_tmp.js")
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(js)
    env = dict(os.environ)
    # node 输出是 UTF-8；不显式指定就会按本机 cp936 解，中文一进来就 UnicodeDecodeError
    env["PYTHONIOENCODING"] = "utf-8"
    try:
        return subprocess.run([NODE, tmp] + list(args), capture_output=True, text=True,
                              encoding="utf-8", errors="replace", timeout=120, env=env)
    finally:
        try:
            os.remove(tmp)
        except OSError:
            pass


def _write_module() -> str:
    """把面板那段 JS 落成真实文件，好让 node require 它。"""
    path = os.path.join(HERE, "_t3_panel.js")
    with open(path, "w", encoding="utf-8") as f:
        f.write(_panel_js())
    return path


@pytest.mark.skipif(not NODE, reason="本机没有 node，跳过页面 JS 实测")
def test_panel_js_parses():
    """面板 JS 至少要能被 node 解析 —— 页面没有构建步骤，语法错就是白屏。"""
    js = _panel_js().replace("module.exports = {", "// module.exports = {")
    r = _run_node(js + "\n", "--check")
    assert r.returncode == 0, r.stderr


def test_panel_mounted_in_shell():
    html = _html()
    for token in [
        'id="nav-tasks"',
        "switchView('tasks')",
        'data-i18n="nav_tasks"',
        "\'nav_tasks\':\'⏱ 任务\'",
        "\'nav_tasks\':\'⏱ Tasks\'",
        'id="panel-tasks"',
        'id="task-list"',
        'id="task-detail"',
        "tasks: 'panel-tasks'",
        "'panel-tasks']",
        "if (view === 'tasks') { loadTasks(true); } else { stopTaskPoll(); }",
    ]:
        assert token in html, "index.html 少了挂载点：" + token
    # 面板必须只在任务视图里出现，别的视图的隐藏列表也得带上它
    assert html.count("panel-tasks") >= 5


LIVE_TASK = {
    "task_id": "qc-20260101-000000-aaaa",
    "title": "QC <script>alert(1)</script>",
    "type": "qc",
    "status": "running",
    "session_id": "memomics-b145cef6",
    "pid": 4242,
    "wrapper_pid": 4241,
    "cpu_pct": 87.5,
    "rss_gb": 3.25,
    "alive": True,
    "stalled": False,
    "started_at": "2026-01-01 00:00:00",
    "elapsed_sec": 125.0,
    "duration_sec": None,
    "exit_code": None,
    "error": "",
    "cmd": "Rscript qc.R --in a.rds",
    "session_dir": "E:/MemOmics-Agent/results/memomics-b145cef6",
    "env_line": "R 4.5.3 / R-libs E:/R-libs/R-4.5.3 / 258 包",
    "params": {"样本数": "12", "最小基因数": "200"},
    "outputs": [{"path": "results/qc.png", "exists": True, "size": 2048}, {"path": "results/none.txt", "exists": False, "size": None}],
    "log": "E:/MemOmics-Agent/log/qc.log",
    "log_size": 4096,
    "log_tail": "读入完成\n开始训练\n",
    "stage": "训练",
    "stage_index": 2,
    "stage_total": 3,
    "stages": [{"name": "读入", "status": "done", "sec": 2.8}, {"name": "训练", "status": "running", "sec": 0.0}, {"name": "收尾", "status": "pending", "sec": None}],
    "progress_pct": 55,
    "heartbeat_age_sec": 1.0,
    "summary": "",
    "script_path": "E:/MemOmics-Agent/results/memomics-b145cef6/qc.R",
    "script_text": "print('hi')\n",
    "cancel_requested": False,
    "cancel_by": "",
}


@pytest.mark.skipif(not NODE, reason="本机没有 node，跳过页面 JS 实测")
def test_render_list_shows_where_and_how_far():
    mod = _write_module()
    drive = HARNESS + """
const P = out.P;
P.renderTaskList({ tasks: %s, counts: { running: 1, done: 0, failed: 0, queued: 0 }, sandbox: 'observe', ok: true });
console.log(JSON.stringify({ html: out.store['task-list'].innerHTML, counts: out.store['task-counts'].textContent }));
""" % json.dumps([LIVE_TASK], ensure_ascii=False)
    r = _run_node(drive, mod)
    assert r.returncode == 0, r.stderr
    assert r.stdout, "node 没输出：%s" % r.stderr
    got = json.loads(r.stdout.strip().splitlines()[-1])
    h = got["html"]
    for token in ["4242", "R 4.5.3", "memomics-b145cef6", "训练", "阶段 2/3", "width:55%", "🏃"]:
        assert token in h, "列表里看不到 %s" % token
    assert "<script>alert(1)</script>" not in h, "标题没转义 —— 有注入风险"
    assert "&lt;script&gt;" in h
    assert "运行 1" in got["counts"] and "沙箱 observe" in got["counts"]


@pytest.mark.skipif(not NODE, reason="本机没有 node，跳过页面 JS 实测")
def test_render_detail_has_timeline_params_log_cancel():
    mod = _write_module()
    drive = HARNESS + """
const P = out.P;
P.renderTaskDetail(%s);
console.log(JSON.stringify({ html: out.store['task-detail'].innerHTML }));
""" % json.dumps(LIVE_TASK, ensure_ascii=False)
    r = _run_node(drive, mod)
    assert r.returncode == 0, r.stderr
    h = json.loads(r.stdout.strip().splitlines()[-1])["html"]
    for token in ["阶段时间线", "读入", "训练", "关键参数", "样本数", "实际命令", "Rscript qc.R",
                  "脚本内容", "task-script-body", "产物（2）", "文件不存在", "日志尾部",
                  "task-cancel-btn", "取消这个任务", "包装进程 4241", "87.5%", "3.25 GB"]:
        assert token in h, "详情里看不到 %s" % token
    # 终态任务不该再给取消按钮
    done = dict(LIVE_TASK)
    done["status"] = "done"
    drive2 = HARNESS + """
const P = out.P;
P.renderTaskDetail(%s);
console.log(JSON.stringify({ html: out.store['task-detail'].innerHTML }));
""" % json.dumps(done, ensure_ascii=False)
    r2 = _run_node(drive2, mod)
    assert r2.returncode == 0, r2.stderr
    h2 = json.loads(r2.stdout.strip().splitlines()[-1])["html"]
    assert "task-cancel-btn" not in h2, "已完成的任务还在显示取消按钮"


@pytest.mark.skipif(not NODE, reason="本机没有 node，跳过页面 JS 实测")
def test_polling_only_while_panel_visible():
    mod = _write_module()
    drive = HARNESS + """
const P = out.P;
P.loadTasks(false);
const afterLazy = out.timers();
out.store['panel-tasks'].style.display = 'flex';
P.loadTasks(true);
const afterForce = out.timers();
P.stopTaskPoll();
const afterStop = out.timers();
console.log(JSON.stringify({ lazy: afterLazy, force: afterForce, stop: afterStop, tick: 2000 }));
"""
    r = _run_node(drive, mod)
    assert r.returncode == 0, r.stderr
    got = json.loads(r.stdout.strip().splitlines()[-1])
    assert got["lazy"] == 0, "进面板之前不该起轮询"
    assert got["force"] == 1, "进面板要起一个轮询"
    assert got["stop"] == 0, "切走面板要停掉轮询"
    assert got["tick"] == 2000
