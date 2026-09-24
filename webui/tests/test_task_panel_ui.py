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
    return m.group(0) + "\n\n" + block + "\nmodule.exports = { loadTasks: loadTasks, stopTaskPoll: stopTaskPoll, renderTaskList: renderTaskList, renderTaskDetail: renderTaskDetail, renderResources: renderResources, taskFmtSec: taskFmtSec, taskRetryDelayText: taskRetryDelayText, retryTask: retryTask, taskStatusIcon: taskStatusIcon, taskIconFor: taskIconFor, taskStageLeft: taskStageLeft, taskCleanHint: taskCleanHint, taskDelete: taskDelete, taskCleanup: taskCleanup, taskSubscribe: taskSubscribe, taskUnsubscribe: taskUnsubscribe, taskWsLive: function() { return _taskWsLive; }, openTaskDock: openTaskDock, closeTaskDock: closeTaskDock, toggleTaskDock: toggleTaskDock, toggleTaskScope: toggleTaskScope, syncTaskScopeBtn: syncTaskScopeBtn, taskBadge: taskBadge, taskSessionLabel: taskSessionLabel, dockOpen: function() { return _taskDockOpen; }, scope: function() { return _taskScope; }, taskStatusTone: taskStatusTone, taskStatusText: taskStatusText, taskHeroLine: taskHeroLine, taskCoreParams: taskCoreParams, taskFoldToggle: taskFoldToggle, taskRowHtml: taskRowHtml, liveSectionHtml: liveSectionHtml, liveSessionRowHtml: liveSessionRowHtml, openLiveSession: openLiveSession, bindTaskRowClicks: bindTaskRowClicks, refreshLiveDetail: refreshLiveDetail, renderLiveDetail: renderLiveDetail, liveToolLabel: liveToolLabel, liveBytes: liveBytes, _taskState: _taskState };"


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
        "function taskBadge(c, liveN)",
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


# T15(2026-09-24)：用户实测反馈 —— 阶段 1 跑完就显示 ✅ 完成，其实后面几段根本没跑
HALF_TASK = dict(LIVE_TASK, task_id="qc-half", title="只跑了一段", status="done", pid=None,
                 stage_total=3, stage_pending=2, stage_unfinished=["训练", "出图"],
                 incomplete=True, exit_code=0, duration_sec=9.0,
                 retry_allowed=True, retry_attempt=1, retry_delay_sec=2.0, retry_max=3,
                 retry_note="任务退出码 0，但还有 2 段没跑到（训练、出图），可以重跑",
                 stages=[{"name": "读入", "status": "done", "sec": 2.0},
                         {"name": "训练", "status": "pending", "sec": None},
                         {"name": "出图", "status": "pending", "sec": None}])


@pytest.mark.skipif(not NODE, reason="本机没有 node，跳过页面 JS 实测")
def test_t15_unfinished_stages_never_look_done():
    """没跑完阶段的"成功"任务：列表给 ⚠️、详情顶上摆警告、还能点重试。"""
    mod = _write_module()
    clean = dict(HALF_TASK, incomplete=False, stage_pending=0, stage_unfinished=[],
                 retry_allowed=False, retry_note="")
    drive = HARNESS + """
const P = out.P;
P.renderTaskList({ ok: true, counts: { running: 0, done: 1 }, tasks: [%s] });
const row = out.store['task-list'].innerHTML;
P.renderTaskDetail(%s);
const detail = out.store['task-detail'].innerHTML;
const wired = typeof out.store['task-retry-btn'].onclick;
P.renderTaskDetail(%s);
const cleanHtml = out.store['task-detail'].innerHTML;
console.log(JSON.stringify({ row: row, detail: detail, wired: wired, cleanHtml: cleanHtml,
                             icon: P.taskIconFor(%s), liveIcon: P.taskIconFor(%s),
                             leaves: P.taskStageLeft(%s) }));
""" % (json.dumps(HALF_TASK, ensure_ascii=False),
       json.dumps(HALF_TASK, ensure_ascii=False),
       json.dumps(clean, ensure_ascii=False),
       json.dumps(HALF_TASK, ensure_ascii=False),
       json.dumps(dict(LIVE_TASK), ensure_ascii=False),
       json.dumps(HALF_TASK, ensure_ascii=False))
    r = _run_node(drive, mod)
    assert r.returncode == 0, r.stderr
    got = json.loads(r.stdout.strip().splitlines()[-1])
    # 图标：done + 没跑完 -> ⚠️；还在跑的任务图标不受影响
    assert got["icon"] == "⚠️", got["icon"]
    assert got["liveIcon"] == "🏃", got["liveIcon"]
    assert got["leaves"] == "训练、出图"
    # 列表行：不能只显示 ✅ 完成，要把"还有 2 段没跑到"写在脸上
    row = got["row"]
    assert "⚠️ 只跑了一段" in row, row
    assert "没跑完：声明的 3 段里还有 2 段没跑到（训练、出图）" in row, row
    assert "✅ 只跑了一段" not in row
    # 详情：顶部警告 + 重试按钮 + 为什么能重试
    d = got["detail"]
    assert "没跑完阶段" in d and "还没跑：<b>训练、出图</b>" in d, d
    assert "退出码 0" in d
    assert "task-retry-btn" in d and got["wired"] == "function"
    assert "还有 2 段没跑到（训练、出图），可以重跑" in d
    # 阶段时间线里没跑的必须是 pending 字样，别混成 done
    assert "读入" in d and "训练" in d and "出图" in d
    # 真跑完的任务：警告和重试都不该出现（别把正常任务也搞成黄的）
    assert "没跑完阶段" not in got["cleanHtml"] and "task-retry-btn" not in got["cleanHtml"]


@pytest.mark.skipif(not NODE, reason="本机没有 node，跳过页面 JS 实测")
def test_t16_cleanup_hint_and_row_delete_button():
    """列表要回答"怎么清、什么时候自动清"，已结束的行要有 🗑，在跑的行不许有。"""
    mod = _write_module()
    done = dict(HALF_TASK, status="done", incomplete=False, stage_pending=0,
                stage_unfinished=[], retry_allowed=False, retry_note="", duration_sec=12.0)
    payload = {"ok": True, "counts": {"running": 1, "queued": 0, "done": 1, "failed": 1},
               "cleanup": {"ttl_hours": 12.0, "auto": True, "swept": 0, "env": "MEMOMICS_TASK_TTL_HOURS"},
               "tasks": [LIVE_TASK, done]}
    drive = HARNESS + """
const P = out.P;
P.renderTaskList(%s);
console.log(JSON.stringify({ rows: out.store['task-list'].innerHTML,
                             hint: out.store['task-clean-bar'].innerHTML }));
const off = %s;
P.renderTaskList(off);
console.log(JSON.stringify({ hint: out.store['task-clean-bar'].innerHTML }));
const none = { ok: true, counts: { running: 2, done: 0, failed: 0 }, cleanup: off.cleanup, tasks: [] };
P.renderTaskList(none);
console.log(JSON.stringify({ hint: out.store['task-clean-bar'].innerHTML }));
""" % (json.dumps(payload, ensure_ascii=False),
       json.dumps({"ok": True, "counts": {"running": 0, "done": 1, "failed": 1},
                   "cleanup": {"ttl_hours": 0.0, "auto": False, "swept": None,
                               "env": "MEMOMICS_TASK_TTL_HOURS"},
                   "tasks": [done]}, ensure_ascii=False))
    r = _run_node(drive, mod)
    assert r.returncode == 0, r.stderr
    outs = [json.loads(x) for x in r.stdout.strip().splitlines()[-3:]]
    rows, hint = outs[0]["rows"], outs[0]["hint"]
    # 提示行：可清理几条 + 多久自动清
    assert "可清理 2 条" in hint and "完成 1" in hint and "失败 1" in hint, hint
    assert "结束超 12 小时自动清理" in hint and "taskCleanup()" in hint, hint
    # 🗑 只给已结束的行
    assert rows.count("task-del-btn") == 1, rows.count("task-del-btn")
    assert 'data-del="' + done["task_id"] + '"' in rows
    assert 'data-del="' + LIVE_TASK["task_id"] + '"' not in rows, "在跑的任务也给了删除按钮"
    # 关掉自动清理要说清楚，不能装作没这回事
    off_hint = outs[1]["hint"]
    assert "自动清理关着" in off_hint and "MEMOMICS_TASK_TTL_HOURS=0" in off_hint, off_hint
    assert "可清理 2 条" in off_hint
    none_hint = outs[2]["hint"]
    assert "没有可清理的" in none_hint and "taskCleanup()" not in none_hint, none_hint


@pytest.mark.skipif(not NODE, reason="本机没有 node，跳过页面 JS 实测")
def test_t16_delete_only_for_finished_and_wired():
    """详情：已结束给「删掉这条记录」并且真的接上了事件；在跑的不给。"""
    mod = _write_module()
    done = dict(HALF_TASK, status="done", incomplete=False, stage_pending=0, stage_unfinished=[],
                retry_allowed=False, retry_note="", duration_sec=12.0)
    drive = HARNESS + """
const P = out.P;
P.renderTaskDetail(%s);
const doneHtml = out.store['task-detail'].innerHTML;
const wired = typeof out.store['task-del-btn'].onclick;
P.renderTaskDetail(%s);
const liveHtml = out.store['task-detail'].innerHTML;
console.log(JSON.stringify({ doneHtml: doneHtml, wired: wired, liveHtml: liveHtml }));
""" % (json.dumps(done, ensure_ascii=False), json.dumps(LIVE_TASK, ensure_ascii=False))
    r = _run_node(drive, mod)
    assert r.returncode == 0, r.stderr
    got = json.loads(r.stdout.strip().splitlines()[-1])
    assert "task-del-btn" in got["doneHtml"] and "删掉这条记录" in got["doneHtml"]
    assert got["wired"] == "function", "删除按钮没接事件（点了没反应）"
    assert "task-del-btn" not in got["liveHtml"], "在跑的任务也给了删除按钮 —— 会误导用户"


@pytest.mark.skipif(not NODE, reason="本机没有 node，跳过页面 JS 实测")
def test_t16_delete_and_cleanup_talk_to_the_right_api():
    """删除/清理真的打到 DELETE /api/tasks/{id} 和 POST /api/tasks/cleanup，带 token，会话范围跟着筛选走。"""
    mod = _write_module()
    drive = HARNESS + """
const P = out.P;
const calls = [];
const confirms = [];
global.fetch = function(url, opts) {
  calls.push({ url: url, method: (opts && opts.method) || 'GET', headers: (opts && opts.headers) || {}, body: (opts && opts.body) || '' });
  return Promise.resolve({ json: function() { return Promise.resolve({ ok: true, deleted_count: 2, kept_count: 1 }); } });
};
global.confirm = function(msg) { confirms.push(msg); return true; };
global.currentSid = 'memomics-mine';
P._taskState.token = 'TOK-16';
P.renderTaskList({ ok: true, counts: { done: 1, failed: 1, running: 1 }, tasks: [%s] });
P.taskDelete('qc-2026 a/b');
P.taskCleanup();
P.toggleTaskScope();
P.taskCleanup();
setTimeout(function() {
  console.log(JSON.stringify({ calls: calls, confirms: confirms, scope: P.scope() }));
}, 80);
""" % json.dumps(dict(HALF_TASK, status="done"), ensure_ascii=False)
    r = _run_node(drive, mod)
    assert r.returncode == 0, r.stderr
    got = json.loads(r.stdout.strip().splitlines()[-1])
    calls = got["calls"]
    dele = [c for c in calls if c["method"] == "DELETE"]
    assert len(dele) == 1, calls
    assert dele[0]["url"].endswith("/qc-2026%20a%2Fb"), dele[0]["url"]
    assert dele[0]["headers"]["X-Task-Token"] == "TOK-16"
    posts = [c for c in calls if c["method"] == "POST" and "cleanup" in c["url"]]
    assert len(posts) == 2, calls
    assert posts[0]["url"].endswith("/api/tasks/cleanup")
    assert posts[0]["headers"]["X-Task-Token"] == "TOK-16"
    assert json.loads(posts[0]["body"]) == {"session_id": ""}, posts[0]["body"]
    assert json.loads(posts[1]["body"]) == {"session_id": "memomics-mine"}, posts[1]["body"]
    assert got["scope"] == "current"
    # 两处确认都要把"产出文件不动""在跑的不删"说在前面，别让人以为删了数据
    assert any("产出" in m for m in got["confirms"]), got["confirms"]
    assert any("正在跑" in m for m in got["confirms"]), got["confirms"]


# T17(2026-09-24)：用户实测反馈 —— "展示面板重点不突出，看不到关键信息"
@pytest.mark.skipif(not NODE, reason="本机没有 node，跳过页面 JS 实测")
def test_t17_detail_puts_the_answer_first():
    """详情第一屏只留三件事：这是什么任务、跑成什么样、核心参数。命令/PID/日志都收进折叠区。"""
    mod = _write_module()
    live = dict(LIVE_TASK, params={"样本数": "12", "最小基因数": "200", "重试来源": "qc-x", "重试根": "r"})
    failed = dict(FAILED_TASK, duration_sec=9.0, exit_code=3)
    done = dict(LIVE_TASK, status="done", pid=None, duration_sec=723.0, progress_pct=100,
                eta_sec=None, stages=[{"name": "读入", "status": "done", "sec": 2.8},
                                      {"name": "训练", "status": "done", "sec": 700.0},
                                      {"name": "收尾", "status": "done", "sec": 20.0}])
    drive = HARNESS + """
const P = out.P;
P.renderTaskDetail(%s);
const live = out.store['task-detail'].innerHTML;
P.renderTaskDetail(%s);
const failed = out.store['task-detail'].innerHTML;
P.renderTaskDetail(%s);
const done = out.store['task-detail'].innerHTML;
console.log(JSON.stringify({ live: live, failed: failed, done: done,
  tone: [P.taskStatusTone('done'), P.taskStatusTone('failed'), P.taskStatusTone('running'), P.taskStatusTone('queued')],
  text: [P.taskStatusText('done'), P.taskStatusText('running'), P.taskStatusText('queued')] }));
""" % (json.dumps(live, ensure_ascii=False), json.dumps(failed, ensure_ascii=False),
       json.dumps(done, ensure_ascii=False))
    r = _run_node(drive, mod)
    assert r.returncode == 0, r.stderr
    got = json.loads(r.stdout.strip().splitlines()[-1])

    # 状态：颜色 + 人话，不再让人先翻译 done/failed
    assert got["tone"] == ["#4a8f4a", "#c0504d", "var(--primary)", "#e0a030"], got["tone"]
    assert got["text"][:3] == ["✅ 完成", "🏃 正在跑", "⏳ 排队中"], got["text"]

    # 在跑：标题 + 结论一句话 + 进度条
    h = got["live"]
    assert 'class="task-hero-title"' in h and 'class="task-hero-pill"' in h, h[:400]
    assert "🏃 正在跑" in h
    assert "正在跑「训练」（第 2/3 段） · 55% · 已跑 2m5s · 还要约 4m5s" in h, h[:600]
    assert 'class="task-hero-bar"' in h and "width:55%" in h
    # 核心参数加粗放大；重试来源这种记账信息不许占第一屏
    assert 'class="task-key-v">12<' in h, "核心参数没加粗放大"
    assert h.index("样本数") < h.index("其余参数（2）") and h.index("重试来源") > h.index("其余参数（2）")
    # 第一屏就该是"没跑的折叠着"：在跑的任务里日志和技术细节都收着
    assert 'task-fold" open' not in h, "在跑的任务第一屏就摊开了折叠区"
    assert "技术细节（命令 · 进程 · 路径 · 脚本）" in h and "日志尾部" in h

    # 失败：日志自动摊开（那才是最该看的），结论直接说失败原因
    f = got["failed"]
    assert "失败（退出码 3）：Rscript 退出码 1：找不到 Seurat" in f, f[:600]
    assert "taskFoldToggle('log'" in f and 'task-fold" open' in f, "失败任务没把日志摊开"
    assert "🔁 重试（第 1 次 · 2s 后启动）" in f

    # 跑完：不用点开就知道全跑完了、用了多久
    d = got["done"]
    assert "3/3 段全跑完 · 用时 12m3s" in d, d[:600]
    assert "task-del-btn" in d and "task-cancel-btn" not in d


@pytest.mark.skipif(not NODE, reason="本机没有 node，跳过页面 JS 实测")
def test_t17_folds_keep_user_choice_across_polls():
    """用户点开的技术细节，不能被 2 秒一次的自动重画收回去；换任务才重置。"""
    mod = _write_module()
    drive = HARNESS + """
const P = out.P;
P.renderTaskDetail(%s);
const before = out.store['task-detail'].innerHTML;
P.taskFoldToggle('tech', true);                    // 用户点开"技术细节"
P.renderTaskDetail(%s);                            // 2 秒后轮询重画（innerHTML 整个换掉）
const after = out.store['task-detail'].innerHTML;
P.renderTaskDetail(%s);                            // 换一条任务
const switched = out.store['task-detail'].innerHTML;
console.log(JSON.stringify({ before: before, after: after, switched: switched }));
""" % (json.dumps(LIVE_TASK, ensure_ascii=False), json.dumps(LIVE_TASK, ensure_ascii=False),
       json.dumps(dict(LIVE_TASK, task_id="qc-other-0001"), ensure_ascii=False))
    r = _run_node(drive, mod)
    assert r.returncode == 0, r.stderr
    got = json.loads(r.stdout.strip().splitlines()[-1])
    assert 'task-fold" open' not in got["before"], "一开始就把折叠区摊开了"
    assert "open ontoggle=\"taskFoldToggle('tech'" in got["after"], "用户点开的折叠区被重画收回去了"
    assert "open ontoggle=\"taskFoldToggle('tech'" not in got["switched"], "换任务还留着上一条的展开状态"


@pytest.mark.skipif(not NODE, reason="本机没有 node，跳过页面 JS 实测")
def test_t17_row_status_is_human_and_colored():
    """列表行也别再显示 done / running 这种英文状态词。"""
    mod = _write_module()
    drive = HARNESS + """
const P = out.P;
const done = P.taskRowHtml(%s, true);
const run = P.taskRowHtml(%s, true);
const q = P.taskRowHtml(%s, true);
console.log(JSON.stringify({ done: done, run: run, q: q }));
""" % (json.dumps(dict(LIVE_TASK, status="done"), ensure_ascii=False),
       json.dumps(LIVE_TASK, ensure_ascii=False),
       json.dumps(dict(LIVE_TASK, status="queued", pid=None), ensure_ascii=False))
    r = _run_node(drive, mod)
    assert r.returncode == 0, r.stderr
    got = json.loads(r.stdout.strip().splitlines()[-1])
    assert "✅ 完成 · " in got["done"] and ">done<" not in got["done"], got["done"][:400]
    assert "#4a8f4a" in got["done"], "完成的任务状态没上色"
    assert "🏃 正在跑 · " in got["run"] and "var(--primary)" in got["run"]
    assert "⏳ 排队中 · " in got["q"] and "#e0a030" in got["q"]

@pytest.mark.skipif(not NODE, reason="本机没有 node，跳过页面 JS 实测")
def test_t17_extreme_payloads_do_not_break_the_panel():
    """极端载荷：字段缺光 / 状态没见过 / 参数和产物爆量 / 标题带脚本 —— 面板不许崩、不许漏 undefined。"""
    mod = _write_module()
    cases = {
        "empty": {},
        "weird_status": dict(LIVE_TASK, status="weird", stage=None, stages=[], stage_total=0),
        # 26 个占位名 + 4 个真参数：真参数必须挤进第一屏，占位名一个都不许露头
        "fat": dict(LIVE_TASK, status="done", duration_sec=61.0, progress_pct=100,
                    params=dict([("参数%02d" % i, "v%d" % i) for i in range(26)] +
                                [("样本数", "12"), ("细胞数", "8000"),
                                 ("组织", "骨骼肌"), ("最小基因数", "200")]),
                    outputs=[{"path": "results/o%02d.png" % i, "exists": i % 2 == 0,
                              "size": i * 100} for i in range(60)]),
        "only_retry_params": dict(LIVE_TASK, params={"重试来源": "a", "重试根": "b", "第几次重试": "2"}),
        "no_log_no_outputs": dict(LIVE_TASK, log_tail=None, log=None, outputs=[], stages=[], stage_total=0),
        "xss": dict(LIVE_TASK, title='<img src=x onerror=alert(1)>',
                    params={"样本数": '<script>alert(2)</script>'},
                    outputs=[{"path": '<b>evil</b>', "exists": True, "size": 1}]),
        "nulls": dict(LIVE_TASK, title="", task_id="qc-null-0001", pid=None, cpu_pct=None, rss_gb=None,
                      elapsed_sec=None, duration_sec=None, exit_code=None, eta_sec=None,
                      progress_pct=None, stage=None, stages=[], stage_total=0, status="interrupted"),
    }
    drive = HARNESS + """
const P = out.P;
const cases = JSON.parse(process.argv[3]);
const res = {};
Object.keys(cases).forEach(function(k) {
  try { P.renderTaskDetail(cases[k]); res[k] = { html: out.store['task-detail'].innerHTML, err: '' }; }
  catch (e) { res[k] = { html: '', err: String(e && e.message || e) }; }
});
console.log(JSON.stringify(res));
"""
    r = _run_node(drive, mod, json.dumps(cases, ensure_ascii=False))
    assert r.returncode == 0, r.stderr
    got = json.loads(r.stdout.strip().splitlines()[-1])

    for k, v in got.items():
        assert not v["err"], "%s 渲染崩了：%s" % (k, v["err"])
        h = v["html"]
        assert h, "%s 什么都没渲染出来" % k
        for bad in ("undefined", ">null<", "NaN"):
            assert bad not in h, "%s 的界面里漏出了 %s" % (k, bad)

    # 没见过的状态：照原样显示，不装作完成
    assert "weird" in got["weird_status"]["html"]

    # 爆量：核心参数最多 4 个，其余进折叠区；60 个产物一个不丢
    fat = got["fat"]["html"]
    assert fat.count('class="task-key"') == 4, fat.count('class="task-key"')
    _grid = fat[fat.index("task-key-grid"):fat.index("产物（")]
    for _k in ("样本数", "细胞数", "组织", "最小基因数"):
        assert _k in _grid, "真参数被挤出第一屏：" + _k
    assert "参数00" not in _grid and "参数25" not in _grid, "占位名占了第一屏"
    assert "其余参数（26）" in fat
    assert fat.count('class="task-out"') == 60
    assert "产物（60）" in fat

    # 只有记账参数时：不画空的关键参数区
    only = got["only_retry_params"]["html"]
    assert "关键参数" not in only and "其余参数（3）" in only

    # 没有阶段/没有日志也要有话说
    plain = got["no_log_no_outputs"]["html"]
    assert "阶段时间线" not in plain and "（暂无日志）" in plain

    # 注入必须被转义
    xss = got["xss"]["html"]
    assert "<img" not in xss and "<script" not in xss and "<b>evil</b>" not in xss
    assert "&lt;script&gt;" in xss

    # 全空字段：不崩，且说得出"正在跑"之外的中断结论
    n = got["nulls"]["html"]
    assert "⚠️ 中断" in n and "进程没了（中断）" in n

# ------------------------------------------- T18 会话级"正在跑"（2026-09-24 用户实测反馈）
# 用户原话：「后台任务那里看不到后台正在运行的任务，也无法点击」——
# 机器上真有会话在跑分析（会话活的，但没有走 task_run 契约），面板却是空的。
# 契约任务之外必须把活着的会话画出来，并且点得动（切到那条会话看进度）。
LIVE_SESSION = {
    "sid": "memomics-live01", "title": "骨骼肌 QC", "ask": "帮我看下这批数据的质控",
    "msg_count": 3, "last_active": "2026-09-24 16:20:00", "elapsed_sec": 725,
    "last_tool": "execute_r", "tool_age_sec": 12, "stalled": False,
    "todos_total": 6, "todos_done": 2, "doing": "按样本汇总 QC 指标", "next": "聚类",
    "bg_running": False, "proc": {"pid": 12345, "rss_mb": 812},
}


def test_t18_running_sessions_are_visible_and_clickable():
    """活会话要看得见、点得动；没活会话时不许冒空壳。"""
    html = _html()
    assert "d.live_sessions" in html, "面板没读服务端的活会话字段"
    assert "data-live-sid" in html and "openLiveSession" in html, "活会话行没接点击"
    assert "querySelectorAll('.task-live-row')" in html, "活会话行没绑定点击"
    # 2026-09-24 二次反馈后：点活会话先开"详情"（参数/环境/产物），想去对话再点按钮
    assert "fetch('/api/live_session/'" in html, "点活会话没去拉详情接口"
    assert "renderLiveDetail" in html and "_taskState.live" in html, "活会话详情没接线"
    # 活会话行不能混进 .task-row：任务行的点击绑定会把 onclick 抢成 openTaskDetail，
    # 而 openTaskDetail 对会话 id 只会 404 —— 点了没反应就是这么来的。
    assert 'class="task-live-row"' in html, "活会话行混了 task-row 的 class"
    if not NODE:
        pytest.skip("本机没有 node，跳过页面 JS 实测")
    mod = _write_module()
    drive = HARNESS + """
const P = out.P;
P.renderTaskList({ tasks: [], counts: {}, ok: true, live_sessions: [%s] });
console.log(JSON.stringify({ html: out.store['task-list'].innerHTML, counts: out.store['task-counts'].textContent }));
""" % json.dumps(LIVE_SESSION, ensure_ascii=False)
    r = _run_node(drive, mod)
    assert r.returncode == 0, r.stderr
    got = json.loads(r.stdout.strip().splitlines()[-1])
    h = got["html"]
    for token in ["memomics-live01", "骨骼肌 QC", "已跑 12m5s", "在做 R 长脚本（execute_r），已 12s",
                  "计划 2/6 步",
                  "PID 12345", "812 MB", "当前步骤：按样本汇总 QC 指标", "分析进行中", "data-live-sid"]:
        assert token in h, "面板里看不到 %s" % token
    assert "还没有后台任务" not in h, "有会话在跑，却提示「还没有后台任务」"
    assert "会话进行中 1" in got["counts"], got["counts"]

    stuck = dict(LIVE_SESSION)
    stuck["stalled"] = True
    stuck["last_tool"] = "search_knowledge"      # 普通工具：沉默 400s 才算不对劲
    stuck["tool_age_sec"] = 400
    stuck["tool_expect_sec"] = 180
    stuck["title"] = "<script>alert(1)</script>"
    drive2 = HARNESS + """
const P = out.P;
console.log(JSON.stringify({ row: P.liveSessionRowHtml(%s) }));
""" % json.dumps(stuck, ensure_ascii=False)
    r2 = _run_node(drive2, mod)
    assert r2.returncode == 0, r2.stderr
    row = json.loads(r2.stdout.strip().splitlines()[-1])["row"]
    assert "没动静" in row, "卡住的会话没标出来"
    assert "<script>alert(1)</script>" not in row and "&lt;script&gt;" in row, "标题没转义"

    # 慢工具不该被误报成卡住：真机实测 debate_analysis 一跑 4-7 分钟、长 R 脚本十几分钟
    slow = dict(LIVE_SESSION)
    slow["last_tool"] = "debate_analysis"
    slow["tool_age_sec"] = 232
    slow["tool_expect_sec"] = 900
    slow["stalled"] = False
    drive4 = HARNESS + """
const P = out.P;
console.log(JSON.stringify({ row: P.liveSessionRowHtml(%s) }));
""" % json.dumps(slow, ensure_ascii=False)
    r4 = _run_node(drive4, mod)
    row4 = json.loads(r4.stdout.strip().splitlines()[-1])["row"]
    assert "多角色辩论" in row4 and "已 3m52s" in row4, row4[:300]
    assert "没动静" not in row4, "辩论跑 4 分钟被误报成卡住"
    assert "慢是正常的" in row4

    drive3 = HARNESS + """
const P = out.P;
console.log(JSON.stringify({ a: P.liveSectionHtml([]), b: P.liveSectionHtml(undefined) }));
"""
    r3 = _run_node(drive3, mod)
    got3 = json.loads(r3.stdout.strip().splitlines()[-1])
    assert got3["a"] == "" and got3["b"] == "", "没活会话却画了个空分组"










# ------------------------------------------- T19 活会话详情：参数 / 环境 / 产物 / 辩论
# 用户原话（2026-09-24）："我点击后台任务之后，没办法看到该任务的详细信息，比如参数，主要环境等等。"
# 面板必须自己回答"拿什么参数、在什么环境里跑的、出了什么产物"，而不是只把人丢进对话里。
LIVE_DETAIL = {
    "ok": True, "sid": "memomics-live01", "title": "骨骼肌 QC", "ask": "帮我看下这批数据的质控",
    "live": True, "is_running": True, "elapsed_sec": 725, "msg_count": 3,
    "current": {"sid": "memomics-live01", "last_tool": "execute_r", "tool_age_sec": 12,
                "tool_expect_sec": 1800, "stalled": False, "proc": {"pid": 12345, "rss_mb": 812},
                "elapsed_sec": 725},
    "todos": [{"title": "读数据", "status": "completed"}, {"title": "算 QC 指标", "status": "in_progress"}],
    "tools": [{"ts": "2026-09-24T16:20:01", "tool": "execute_r",
               "args": 'obj <- readRDS("E:/release/_memtest/data/MF_2000.rds")',
               "result": '{"status": "success", "output": "51227 x 2132"}'}],
    "stats": {"tool_calls": 7, "tools": {"execute_r": 2}, "skills": ["scrna-qc"],
              "rail_pre": 1, "rail_post": 0, "debate_calls": 0, "files_written": 1},
    "debates": [{"file": "debate_x.json", "topic": "MT 阈值 15% 是否为空操作", "verdict": "need_more_info",
                 "confidence": "low", "decision": "先补阈值敏感性分析再定去留", "next_actions": 3,
                 "mtime": 1.0}],
    "artifacts": [{"rel": "results/qc_metrics_summary.csv", "size": 4096, "mtime": 1.0},
                  {"rel": "figures/qc_violin.png", "size": 204800, "mtime": 1.0}],
    "env": {"python": "E:/MemOmics-Agent/.venv/Scripts/python.exe", "cwd": "E:/MemOmics-Agent",
            "r_version": "R-4.5.3", "rscript": "C:/Program Files/R/R-4.5.3/bin/x64/Rscript.exe",
            "r_lib_user": "E:/R-libs/R-4.5.3", "r_pkg_count": 258, "r_key_pkgs": ["Seurat", "harmony"],
            "memomics_env": {"MEMOMICS_PORT": "8899"}, "env_updated": "2026-09-24"},
    "paths": {"session_dir": "E:/MemOmics-Agent/results/memomics-live01",
              "system_log": "E:/MemOmics-Agent/results/memomics-live01/log/system_log.jsonl",
              "tasks_dir": "C:/hermes_home/runtime/tasks"},
    "task": None,
}


def test_t19_live_detail_shows_params_environment_and_artifacts():
    """详情页要摊开：入参原文、R/Python 环境、产物清单、辩论裁决；按钮能进会话。"""
    if not NODE:
        pytest.skip("本机没有 node，跳过页面 JS 实测")
    mod = _write_module()
    drive = HARNESS + """
const P = out.P;
const calls = [], switched = [];
global.fetch = function(u) {
  calls.push(String(u));
  return Promise.resolve({ json: function() { return Promise.resolve(%s); } });
};
global.switchSession = function(sid) { switched.push(sid); };
P.openLiveSession('memomics-live01');
setTimeout(function() {
  var box = out.store['task-detail'];
  var go = out.store['live-goto-chat'];
  if (go && go.onclick) go.onclick();
  console.log(JSON.stringify({ calls: calls, switched: switched, live: P._taskState.live,
                               tab: P._taskState.id, html: box.innerHTML }));
}, 50);
""" % json.dumps(LIVE_DETAIL, ensure_ascii=False)
    r = _run_node(drive, mod)
    assert r.returncode == 0, r.stderr
    got = json.loads(r.stdout.strip().splitlines()[-1])
    assert got["calls"] and "/api/live_session/memomics-live01" in got["calls"][0], got["calls"]
    assert got["live"] == "memomics-live01" and got["tab"] is None, "详情页没把状态切到活会话"
    h = got["html"]
    for token in ["你的要求", "帮我看下这批数据的质控", "运行参数", "readRDS",
                  "MF_2000.rds", "主要环境", "R-4.5.3", "Rscript", "E:/R-libs/R-4.5.3", "Seurat",
                  "MEMOMICS_PORT", "产物（2 个文件）", "results/qc_metrics_summary.csv", "4.0 KB",
                  "辩论记录（1 次）", "need_more_info", "先补阈值敏感性分析再定去留",
                  "切到会话", "PID 12345", "工具调用 7 次", "铁轨审查"]:
        assert token in h, "详情里看不到 %s" % token
    assert got["switched"] == ["memomics-live01"], "「切到会话」没真的切过去"
    # 读不到详情要说人话，不许留空白页
    drive2 = HARNESS + """
const P = out.P;
P.renderLiveDetail({ ok: false, error: 'boom' });
console.log(JSON.stringify({ html: out.store['task-detail'].innerHTML }));
"""
    r2 = _run_node(drive2, mod)
    assert r2.returncode == 0, r2.stderr
    h2 = json.loads(r2.stdout.strip().splitlines()[-1])["html"]
    assert "读不到会话详情" in h2 and "boom" in h2
    # 注入必须转义
    drive3 = HARNESS + """
const P = out.P;
var d = %s; d.title = '<img src=x onerror=alert(1)>';
P.renderLiveDetail(d);
console.log(JSON.stringify({ html: out.store['task-detail'].innerHTML }));
""" % json.dumps(LIVE_DETAIL, ensure_ascii=False)
    r3 = _run_node(drive3, mod)
    assert r3.returncode == 0, r3.stderr
    h3 = json.loads(r3.stdout.strip().splitlines()[-1])["html"]
    assert "<img" not in h3 and "&lt;img" in h3
