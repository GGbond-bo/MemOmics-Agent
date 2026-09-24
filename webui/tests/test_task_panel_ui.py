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
import tempfile

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
    return m.group(0) + "\n\n" + block + "\nmodule.exports = { loadTasks: loadTasks, stopTaskPoll: stopTaskPoll, renderTaskList: renderTaskList, renderTaskDetail: renderTaskDetail, renderResources: renderResources, taskFmtSec: taskFmtSec, taskRetryDelayText: taskRetryDelayText, retryTask: retryTask, taskStatusIcon: taskStatusIcon, taskSubscribe: taskSubscribe, taskUnsubscribe: taskUnsubscribe, taskWsLive: function() { return _taskWsLive; }, openTaskDock: openTaskDock, closeTaskDock: closeTaskDock, toggleTaskDock: toggleTaskDock, toggleTaskScope: toggleTaskScope, syncTaskScopeBtn: syncTaskScopeBtn, taskBadge: taskBadge, taskSessionLabel: taskSessionLabel, dockOpen: function() { return _taskDockOpen; }, scope: function() { return _taskScope; }, _taskState: _taskState };"


HARNESS = """
const store = {};
function el(id) {
  if (!store[id]) store[id] = { id: id, innerHTML: '', textContent: '', title: '', className: '', style: { display: 'none' },
    // T13：抽屉靠 classList 开合，影子 DOM 也得有
    classList: { _s: {}, add: function(c) { this._s[c] = true; }, remove: function(c) { delete this._s[c]; },
                 toggle: function(c, on) { if (on) { this._s[c] = true; } else { delete this._s[c]; } },
                 contains: function(c) { return !!this._s[c]; } },
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
// T9：面板用全局 ws 发订阅消息（index.html 里那个聊天连接），这里给个假 socket
global.WebSocket = { OPEN: 1 };
global.ws = { readyState: 1, sent: [], send: function(t) { this.sent.push(t); } };
const out = { timers: function() { return timers.filter(Boolean).length; },
              mss: function() { return timers.filter(Boolean).map(function(t) { return t.ms; }); },
              store: store, P: null };
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


_TMPDIR = None


def _write_module() -> str:
    """把面板那段 JS 落成真实文件，好让 node require 它。

    写系统临时目录，不写仓库（以前写在 tests/ 下，跑一次测试仓库就多一个
    未跟踪的 _t3_panel.js）。整个测试会话共用一个目录，退出时由系统清理。
    """
    global _TMPDIR
    if _TMPDIR is None:
        _TMPDIR = tempfile.mkdtemp(prefix="memomics_t3panel_")
    path = os.path.join(_TMPDIR, "_t3_panel.js")
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
        # T13：入口从左侧导航搬到顶部横栏（"生信分析对话"旁边），变成带实时徽标的胶囊
        'class="chat-nav-chip" id="nav-tasks"',
        'onclick="toggleTaskDock()"',
        'id="task-nav-badge"',
        'data-i18n="nav_tasks"',
        "'nav_tasks':'后台任务'",
        "'nav_tasks':'Background Tasks'",
        'id="task-dock"',
        'id="task-scope-btn"',
        'id="panel-tasks"',
        'id="task-list"',
        'id="task-detail"',
        # 老代码里还有别处会调 switchView('tasks')，必须还能开抽屉
        "if (view === 'tasks') { openTaskDock(); return; }",
        "function openTaskDock()",
        "function closeTaskDock()",
        "function toggleTaskDock()",
        "function toggleTaskScope()",
        "function refreshTaskBadge()",
        "function startTaskBadgePoll()",
        "function taskBadge(c)",
        "function taskRowHtml(t, mine)",
        "function taskSessionLabel(id)",
        "memomics-task-scope",
        "session_title",
        "只看当前会话",
        "当前会话",
        "别的会话",
        "所属会话",
        # T9：面板靠 WS 订阅拿实时推送，切走退订；没订阅上才退回 2 秒轮询
        "type: 'task_subscribe'",
        "type: 'task_unsubscribe'",
        "if (msg.type === 'tasks') {",
        "_taskWsLive = true;",
        "var ms = _taskWsLive ? 8000 : 2000;",
        # T10：列表/详情都要显示「还要多久」（来自阶段历史，带出处）
        "' · 还要 '",
        "t.eta_sec",
        "预计还要",
        "t.eta_basis",
        # T11：任务面板顶部要有资源队列（谁在跑 / 谁在排 / 排第几 / 等了多久）
        'id="task-queue"',
        "function renderResources(res)",
        "'/api/resources'",
        "⏳ 排队 ",
        " · 已等 ",
        "队首已等超 30s",
        # T12：失败任务一键重试（按钮亮/灰都由后端算好的 retry_* 字段决定）
        "function retryTask(id)",
        "'/retry'",
        "task-retry-btn",
        "function taskRetryDelayText(sec)",
        "🔁 重试（第 ",
        "🔁 不能重试：",
    ]:
        assert token in html, "index.html 少了挂载点：" + token
    # 抽屉里的面板不能被"换视图就全隐藏"的那张表连坐（否则切个视图就把抽屉内容藏了）
    assert "'panel-weixin'].forEach(" in html and "'panel-tasks']" not in html
    assert html.count("panel-tasks") >= 4


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
    "eta_sec": 245.0,
    "eta_text": "4:05",
    "eta_basis": "按 12 次同类型历史",
    "eta_source": "history",
    "eta_confidence": "高",
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
    for token in ["4242", "R 4.5.3", "memomics-b145cef6", "训练", "阶段 2/3", "width:55%", "🏃",
                  "还要 4m5s"]:
        assert token in h, "列表里看不到 %s" % token
    # 没有 ETA 的任务（头一回跑、或已结束）不许硬编一个"还要"出来
    no_eta = dict(LIVE_TASK)
    no_eta["eta_sec"] = None
    no_eta["eta_text"] = ""
    drive2 = HARNESS + """
const P = out.P;
P.renderTaskList({ tasks: %s, counts: { running: 1 }, ok: true });
console.log(JSON.stringify({ html: out.store['task-list'].innerHTML }));
""" % json.dumps([no_eta], ensure_ascii=False)
    r2 = _run_node(drive2, mod)
    assert r2.returncode == 0, r2.stderr
    assert "还要" not in json.loads(r2.stdout.strip().splitlines()[-1])["html"], "没 ETA 却显示了「还要」"
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
                  "task-cancel-btn", "取消这个任务", "包装进程 4241", "87.5%", "3.25 GB",
                  "预计还要", "4m5s", "按 12 次同类型历史", "可信度高"]:
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


def test_render_detail_explains_where_outputs_and_scripts_are():
    """产物解析与脚本读取的两种"说不出话"情况，面板都得把话说清楚。"""
    mod = _write_module()
    task = dict(LIVE_TASK)
    task["script_text"] = ""
    task["script_path"] = ""
    task["script_note"] = "脚本在会话目录/仓库之外，面板不读（安全策略）：D:/out/qc.R"
    task["outputs"] = [
        {"path": "t5_qc_box.png", "exists": True, "size": 4698, "abs": "/sess/results/t5_qc_box.png"},
        {"path": "never.csv", "exists": False, "size": None, "abs": "/sess/never.csv"},
    ]
    drive = HARNESS + """
const P = out.P;
P.renderTaskDetail(%s);
console.log(JSON.stringify({ html: out.store['task-detail'].innerHTML }));
""" % json.dumps(task, ensure_ascii=False)
    r = _run_node(drive, mod)
    assert r.returncode == 0, r.stderr
    assert r.stdout, "node 没输出：%s" % r.stderr
    h = json.loads(r.stdout.strip().splitlines()[-1])["html"]
    assert "面板不读" in h and "安全策略" in h and "D:/out/qc.R" in h
    assert "→ /sess/results/t5_qc_box.png" in h and "4698 B" in h
    assert "文件不存在" in h

@pytest.mark.skipif(not NODE, reason="本机没有 node，跳过页面 JS 实测")
def test_render_resources_shows_queue_positions():
    """排队的人要能看见自己排第几、等了多久 —— 空队列也必须说"队列空"。"""
    mod = _write_module()
    drive = HARNESS + """
const P = out.P;
const res = { capacity: { cpu_cores: 8, memory_gb: 16.0, gpu_slots: 1 },
              used: { cpu_cores: 8, memory_gb: 6.0, gpu_slots: 1 },
              available: { cpu_cores: 0, memory_gb: 10.0, gpu_slots: 0 },
              queue: { admission: "cooperative_fifo", active: 1, waiting: 2, head_wait_sec: 41.0, max_wait_sec: 41.0 },
              active: [{ lease_id: "l1", session_id: "memomics-b145cef6", label: "跑 QC <b>", held_sec: 41.0, cpu_cores: 6, memory_gb: 4.0, gpu_slots: 1 }],
              waiting: [{ session_id: "memomics-aaaa1111", position: 1, label: "ATAC 比对", waited_sec: 41.0, cpu_cores: 2, memory_gb: 2.0, gpu_slots: 0 },
                        { session_id: "memomics-bbbb2222", position: 2, label: "", waited_sec: 3.0, cpu_cores: 1, memory_gb: 2.0, gpu_slots: 0 }] };
P.renderResources(res);
const busy = out.store["task-queue"].innerHTML;
P.renderResources({ capacity: { cpu_cores: 8, memory_gb: 16.0, gpu_slots: 0 }, used: { cpu_cores: 0, memory_gb: 0.0, gpu_slots: 0 },
                   queue: { active: 0, waiting: 0, head_wait_sec: 0, max_wait_sec: 0 }, active: [], waiting: [] });
const idle = out.store["task-queue"].innerHTML;
console.log(JSON.stringify({ busy: busy, idle: idle }));
"""
    r = _run_node(drive, mod)
    assert r.returncode == 0, r.stderr
    got = json.loads(r.stdout.strip().splitlines()[-1])
    busy = got["busy"]
    for token in ["CPU 8/8 核", "内存 6/16 GB", "GPU 1/1", "运行中 1", "⏳ 排队 2",
                  "#1", "#2", "ATAC 比对", "已等 41s", "需 2 核/2 GB",
                  "memomics-aaa", "memomics-bbb", "▶ 跑 QC &lt;b&gt;", "已占用 41s", "队首已等超 30s"]:
        assert token in busy, "队列条看不到 %s：%s" % (token, busy)
    assert "<b>" not in busy, "会话标题没转义 —— 有注入风险"
    idle = got["idle"]
    assert "队列空" in idle and "排队" not in idle.split("队列空")[1][:20]
    assert "队首已等超" not in idle


FAILED_TASK = dict(LIVE_TASK, status="failed", retry_allowed=True, retry_reason="", retry_root="",
                   retry_used=0, retry_attempt=1, retry_delay_sec=2.0, retry_max=3,
                   error="Rscript 退出码 1：找不到 Seurat")


@pytest.mark.skipif(not NODE, reason="本机没有 node，跳过页面 JS 实测")
def test_render_detail_retry_button_and_grey_reason():
    """失败任务：能重试就给按钮（写明第几次/多久后启动），不能重试就把理由写出来。"""
    mod = _write_module()
    drive = HARNESS + """
const P = out.P;
P.renderTaskDetail(%s);
const html = out.store["task-detail"].innerHTML;
const wired = typeof out.store["task-retry-btn"].onclick;
P.renderTaskDetail(%s);
const grey = out.store["task-detail"].innerHTML;
P.renderTaskDetail(%s);
const done = out.store["task-detail"].innerHTML;
console.log(JSON.stringify({ html: html, wired: wired, grey: grey, done: done,
                             delay0: P.taskRetryDelayText(0), delay5: P.taskRetryDelayText(5),
                             delay15: P.taskRetryDelayText(15),
                             retryFn: typeof P.retryTask }));
""" % (
        json.dumps(FAILED_TASK, ensure_ascii=False),
        json.dumps(dict(FAILED_TASK, retry_allowed=False, retry_used=3,
                        retry_reason="已经连着重试 3 次（上限 3 次），先看日志再动手"),
                   ensure_ascii=False),
        json.dumps(dict(LIVE_TASK, status="done", retry_allowed=False, retry_reason="任务没失败（done），不用重试",
                        retry_used=0, retry_attempt=1, retry_delay_sec=2.0, retry_max=3),
                   ensure_ascii=False))
    r = _run_node(drive, mod)
    assert r.returncode == 0, r.stderr
    got = json.loads(r.stdout.strip().splitlines()[-1])
    h = got["html"]
    for token in ["task-retry-btn", "重试（第 1 次", "2s 后启动"]:
        assert token in h, "详情里看不到 %s：%s" % (token, h)
    assert "取消这个任务" not in h, "已失败的任务不该还有取消按钮"
    assert got["wired"] == "function", "重试按钮没接上点击（点了没反应）"
    assert got["retryFn"] == "function"
    assert got["delay0"] == "立即启动" and got["delay5"] == "5s 后启动" and got["delay15"] == "15s 后启动"
    # 用完了：按钮消失、理由留下
    assert "task-retry-btn" not in got["grey"] and "不能重试" in got["grey"]
    assert "已经连着重试 3 次" in got["grey"]
    # 没失败的任务：连"不能重试"那句话都不该出现（免得列表里到处是灰字）
    assert "不能重试" not in got["done"] and "task-retry-btn" not in got["done"]

# T13(2026-09-24)：入口搬到顶部横栏 + 右侧抽屉 + 跨会话不串
CURRENT_SID = "memomics-b145cef6"
OTHER_SID = "memomics-aaaa1111"
MY_TASK = dict(LIVE_TASK, task_id="qc-mine", session_id=CURRENT_SID, session_title="骨骼肌 QC 跑通")
OTHER_TASK = dict(LIVE_TASK, task_id="qc-other", title="别人的 ATAC", session_id=OTHER_SID,
                  session_title="ATAC 比对（另一个会话）", status="queued", pid=None)


@pytest.mark.skipif(not NODE, reason="本机没有 node，跳过页面 JS 实测")
def test_t13_dock_marks_which_session_and_pins_current():
    """不同会话的后台任务必须标清是谁的：当前会话置顶高亮、别的会话压暗，动它之前先说清是哪个会话。"""
    mod = _write_module()
    drive = HARNESS + """
global.currentSid = %s;                        // 页面里 currentSid 是全局变量
const P = out.P;
P.openTaskDock();
const opened = { open: P.dockOpen(), openClass: out.store['task-dock'].classList.contains('open'),
                 body: out.store['panel-tasks'].style.display, mss: out.mss() };
P.renderTaskList({ ok: true, sandbox: 'observe', counts: { running: 1, queued: 1, done: 0, failed: 0 },
                   tasks: %s });
const all = out.store['task-list'].innerHTML;
const badge = out.store['task-nav-badge'].textContent;
const tip = out.store['nav-tasks'].title;
const toldMine = P.taskSessionLabel('qc-mine');
const toldOther = P.taskSessionLabel('qc-other');
P.toggleTaskScope();
const scopeTxt = out.store['task-scope-btn'].textContent;
const scopeVal = P.scope();
const onlyMine = out.store['task-list'].innerHTML;
P.renderTaskList({ ok: true, counts: { running: 1, queued: 1, done: 0, failed: 0 }, tasks: [%s] });
const emptyMine = out.store['task-list'].innerHTML;
P.closeTaskDock();
const closed = { open: P.dockOpen(), openClass: out.store['task-dock'].classList.contains('open'),
                 body: out.store['panel-tasks'].style.display, mss: out.mss() };
console.log(JSON.stringify({ opened: opened, all: all, badge: badge, tip: tip, toldMine: toldMine,
                             toldOther: toldOther, scopeTxt: scopeTxt, scopeVal: scopeVal,
                             onlyMine: onlyMine, emptyMine: emptyMine, closed: closed }));
""" % (json.dumps(CURRENT_SID), json.dumps([MY_TASK, OTHER_TASK], ensure_ascii=False),
       json.dumps(OTHER_TASK, ensure_ascii=False))
    r = _run_node(drive, mod)
    assert r.returncode == 0, r.stderr
    assert r.stdout, "node 没输出：%s" % r.stderr
    got = json.loads(r.stdout.strip().splitlines()[-1])

    # 抽屉开合：开着 → classList 开 + 面板可见 + 走 2s 面板轮询；关着 → 反过来 + 20s 徽标轮询
    assert got["opened"]["open"] is True and got["opened"]["openClass"] is True
    assert got["opened"]["body"] == "", "抽屉开了 #panel-tasks 还是 display:none —— 老轮询逻辑会以为面板没开"
    assert 2000 in got["opened"]["mss"], "抽屉开着没起面板轮询：%s" % got["opened"]["mss"]
    assert got["closed"]["open"] is False and got["closed"]["openClass"] is False
    assert got["closed"]["body"] == "none"
    assert got["closed"]["mss"] == [20000], "抽屉关了要只剩 20s 的徽标轮询，实际 %s" % got["closed"]["mss"]

    # 会话标清楚：当前会话在前、别的会话在后，别的会话卡片压暗
    allh = got["all"]
    assert "💬 当前会话" in allh and "骨骼肌 QC 跑通" in allh
    assert "💬 别的会话" in allh and "ATAC 比对（另一个会话）" in allh
    assert allh.index("💬 当前会话") < allh.index("💬 别的会话"), "当前会话没排到最前"
    assert "task-row other" in allh, "别的会话的卡片没压暗 —— 用户分不出哪条是自己的"
    assert allh.index("task-row other") > allh.index("💬 别的会话")
    assert "task-row other" not in allh[:allh.index("💬 别的会话")], "当前会话的卡片不该被压暗"
    assert "qc-other" in allh and "qc-mine" in allh, "两个会话的任务都得看得见（不藏）"

    # 顶栏徽标/提示不能骗人
    assert "🏃1" in got["badge"] and "⏳1" in got["badge"], "徽标没显示在跑/在排：%r" % got["badge"]
    assert "跑 1" in got["tip"] and "排队 1" in got["tip"]

    # 动别的会话的任务之前必须知道是谁的
    assert got["toldMine"] == "", "自己的任务不该弹跨会话警告：%r" % got["toldMine"]
    assert "不是当前会话" in got["toldOther"] and "ATAC 比对（另一个会话）" in got["toldOther"]

    # 只看当前会话
    assert got["scopeVal"] == "current" and "只看当前会话" in got["scopeTxt"]
    assert "qc-mine" in got["onlyMine"] and "qc-other" not in got["onlyMine"], "「只看当前会话」没生效"
    assert "切到「全部会话」" in got["emptyMine"], "自己没任务时要指路，不能一片空白"

# T13 边界（极端输入不能把抽屉搞崩 / 不能漏标会话）
def test_t13_edge_cases_no_sid_injection_and_many_sessions():
    """没会话 id、标题里带 HTML、五十个会话、当前会话未知 —— 都得稳。"""
    mod = _write_module()
    evil = dict(LIVE_TASK, task_id="qc-evil", session_id="memomics-evil",
                session_title="<img src=x onerror=alert(1)>会话名", status="done")
    orphan = dict(LIVE_TASK, task_id="qc-orphan", session_id="", session_title="", status="done")
    many = [dict(LIVE_TASK, task_id="qc-%02d" % i, session_id="memomics-s%02d" % i,
                 session_title="会话 %02d" % i, status="done") for i in range(50)]
    drive = HARNESS + """
const P = out.P;
const payload = { ok: true, counts: { running: 0, queued: 0, done: 52, failed: 0 },
                  tasks: %s };
// 1) 有当前会话
global.currentSid = 'memomics-s07';
P.renderTaskList(payload);
const withSid = out.store['task-list'].innerHTML;
const badge = out.store['task-nav-badge'].textContent;
const tip = out.store['nav-tasks'].title;
// 2) 当前会话未知（比如刚打开页面还没选中会话）：不许把任务藏起来
global.currentSid = null;
P.renderTaskList(payload);
const noSid = out.store['task-list'].innerHTML;
// 3) 筛选「只看当前会话」但当前会话未知：退化成全看，不能白屏
P.toggleTaskScope();
P.renderTaskList(payload);
const noSidFiltered = out.store['task-list'].innerHTML;
P.renderTaskList({ ok: true, counts: { running: 0 }, tasks: [] });
const emptyAll = out.store['task-list'].innerHTML;
console.log(JSON.stringify({ withSid: withSid, noSid: noSid, noSidFiltered: noSidFiltered,
                             emptyAll: emptyAll, badge: badge, tip: tip }));
""" % json.dumps([evil, orphan] + many, ensure_ascii=False)
    r = _run_node(drive, mod)
    assert r.returncode == 0, r.stderr
    got = json.loads(r.stdout.strip().splitlines()[-1])
    h = got["withSid"]
    # 会话名里的 HTML 必须被转义（会话名来自用户输入，不能当 HTML 塞进抽屉）
    assert "<img src=x onerror=alert(1)>" not in h, "会话名没转义 —— 有注入风险"
    assert "&lt;img src=x onerror=alert(1)&gt;" in h
    # 没有会话 id 的任务归到"未知会话"，绝不能算成"当前会话"
    assert "未知会话" in h
    assert h.index("未知会话") > h.index("💬 当前会话")
    # 五十个会话都分组渲染出来，且当前会话（s07）在别的会话前面
    assert "会话 49" in h and "会话 00" in h
    assert h.index("会话 07") < h.index("会话 00"), "当前会话没排到最前"
    # 当前会话未知：两条任务照样看得见，不因为它没归组就消失
    assert "qc-evil" in got["noSid"] and "qc-orphan" in got["noSid"]
    # 当前会话未知 + 「只看当前会话」：退化成全看，不能白屏
    assert "qc-evil" in got["noSidFiltered"] and "还没有后台任务" not in got["noSidFiltered"]
    # 真的没任务时给的是"还没有"，不是报错
    assert "还没有后台任务" in got["emptyAll"]
    # 全闲且有失败时才用 ❌ 顶班；这里 done=52 没有失败 -> 徽标空
    assert got["badge"] == "", "没在跑没排队没失败时徽标应该空着：%r" % got["badge"]
    assert "跑 0" in got["tip"]


