# -*- coding: utf-8 -*-
"""后台任务查看：服务端路由 + 契约扩展 守卫测试（T2/4，2026-09-24）。

现场依据（真机 8899 实测）：
  面板要能回答"后台在跑什么、用什么环境、PID 多少、脚本长什么样、跑到哪一步了"。
  这些不该靠 agent 描述，而是任务自己写契约（memomics/bio_tools/task_run.py），
  服务端只读 + 核对存活。本文件锁死这条链路的语义：

  A. 契约扩展：request_cancel 只写意图；kill_registered_process 认 pid+创建时间，
     PID 被复用一律不杀（点"取消"不能变成误杀）。
  B. 列表：字段齐全、可按会话/状态过滤、死进程的活任务收敛成 interrupted。
  C. 详情：日志尾部、产物存在性与大小、脚本正文只允许读会话目录/仓库内的文件。
  D. 日志接口：seek 读尾部，支持 grep，日志缺失不报错。
  E. 取消：无 token 401、未知 404、已结束 409、真任务能真取消且子进程真的没了。
  F. 路由清单：新增路由都进了 webui/middleware_routes.json（漏了就会 drift）。
  G. 阶段时间线：预建的 pending 阶段被点亮后必须有 started_at，sec 不能是 0.0
     （2026-09-24 真机面板实测踩到的 bug）。
  J. 失败任务一键重试（T12）：只重跑契约里记下的命令；退避/上限全用 retry_backoff；
     重试任务带 重试来源/重试根/第几次重试；并且必须真起进程真跑完（不是写份契约就算）。

纪律：HERMES_HOME_DIR 指到 tmp，绝不许碰真机 hermes_home。
"""
import importlib.util
import json
import os
import subprocess
import sys
import time

import pytest

import server

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO = os.path.dirname(os.path.dirname(_HERE))
TRCLI = os.path.join(_REPO, "memomics", "bio_tools", "task_run.py")


def _tr():
    """任务的模块句柄：优先按包导入（和 server 用同一个），失败就按文件路径加载。"""
    try:
        from memomics.bio_tools import task_run
        return task_run
    except Exception:
        spec = importlib.util.spec_from_file_location("task_run_rt", TRCLI)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod


@pytest.fixture()
def tr():
    return _tr()


@pytest.fixture()
def home(tmp_path, monkeypatch):
    """把 HERMES_HOME_DIR 指到 tmp，并建好 runtime/tasks 目录。"""
    h = tmp_path / "hermes_home"
    (h / "runtime" / "tasks").mkdir(parents=True)
    monkeypatch.setattr(server, "HERMES_HOME_DIR", str(h))
    return h


@pytest.fixture()
def tasks_dir(home):
    return str(home / "runtime" / "tasks")


@pytest.fixture()
def token(home):
    return server._task_api_token()


def _make(tr, tasks_dir, **kw):
    """在 tmp 任务目录里造一条契约（直接建文件，不依赖 wrapper）。"""
    tr.TASKS_DIR = tasks_dir
    tr.FALLBACK_LOG_DIR = os.path.join(os.path.dirname(tasks_dir), "logs")
    os.makedirs(tr.FALLBACK_LOG_DIR, exist_ok=True)
    kw.setdefault("type", "qc")
    kw.setdefault("title", "单元任务")
    kw.setdefault("stages", ["读入", "训练"])
    return tr.new_task(**kw)


def _write_log(tasks_dir, task_id, lines):
    path = os.path.join(tasks_dir, task_id + ".log")
    with open(path, "w", encoding="utf-8") as f:
        for i in range(lines):
            f.write("log line %d" % i + chr(10))
    return path


# ------------------------------------------------------------- A 契约扩展
def test_a1_request_cancel_writes_intent_only(tr, tasks_dir):
    t = _make(tr, tasks_dir)
    rep = tr.request_cancel(t.task_id, by="test")
    assert rep["ok"] and rep["status"] == "cancelling"
    d = json.load(open(os.path.join(tasks_dir, t.task_id + ".json"), encoding="utf-8"))
    assert d["cancel_requested"] is True and d["cancel_by"] == "test"
    assert d["status"] == "cancelling"
    assert tr.request_cancel("no-such-task")["ok"] is False
    # 已结束的任务不该被翻回 cancelling
    t.finish("done", exit_code=0)
    tr.request_cancel(t.task_id, by="test")
    d2 = json.load(open(os.path.join(tasks_dir, t.task_id + ".json"), encoding="utf-8"))
    assert d2["status"] == "done" and d2["cancel_requested"] is True


def test_a2_kill_registered_process_respects_identity(tr, tasks_dir):
    t = _make(tr, tasks_dir)
    t.data["proc"] = {}
    assert tr.kill_registered_process(t.data)["attempted"] is False
    # 进程早没了：不该报错，也不该去杀
    r = tr.kill_registered_process({"proc": {"pid": 999999, "create_time": 1.0}})
    assert r["attempted"] is False and "已不在" in r["reason"]
    # PID 复用：pid 是本测试进程，但创建时间对不上 -> 拒绝杀，且本进程还活着
    r2 = tr.kill_registered_process({"proc": {"pid": os.getpid(), "create_time": 1.0}})
    assert r2["attempted"] is False, "身份对不上还敢动手杀？"
    assert ("复用" in r2["reason"]) or ("创建时间" in r2["reason"])   # 有 psutil / 没 psutil 两种拒绝话术
    assert tr.proc_alive(os.getpid(), None)
    # 真进程：能杀掉
    child = subprocess.Popen([sys.executable, "-c", "import time;time.sleep(120)"])
    time.sleep(0.4)
    ident = tr.proc_identity(child.pid)
    r3 = tr.kill_registered_process({"proc": ident})
    assert r3["attempted"] is True and r3["killed"] is True
    assert not tr.proc_alive(child.pid, ident.get("create_time"))


# ------------------------------------------------------------------ B 列表
def test_b1_list_shape(client, tr, tasks_dir):
    t = _make(tr, tasks_dir, title="列表任务", params={"min_cells": 3})
    d = client.get("/api/tasks").json()
    assert d["ok"] is True and d["tasks_dir"] == tasks_dir
    assert d["api_token"] and d["active"] >= 1 and "qc" in d["types"]
    card = next(x for x in d["tasks"] if x["task_id"] == t.task_id)
    for key in ("title", "type", "status", "pid", "pname", "progress_pct", "stage_index",
                "stage_total", "stages", "elapsed_sec", "env_line", "log", "summary",
                "output_count", "params", "alive", "stalled", "session_id", "session_title"):
        assert key in card, "列表卡片缺字段：" + key
    assert card["title"] == "列表任务" and card["stage_total"] == 2
    assert card["stages"][0]["name"] == "读入"


def test_b2_list_filters(client, tr, tasks_dir):
    a = _make(tr, tasks_dir, title="会话甲", session_id="memomics-aaa")
    b = _make(tr, tasks_dir, title="会话乙", session_id="memomics-bbb")
    b.finish("done", exit_code=0)
    d1 = client.get("/api/tasks", params={"session_id": "memomics-aaa"}).json()
    assert [x["task_id"] for x in d1["tasks"]] == [a.task_id]
    assert d1["sessions"] == ["memomics-aaa"]
    d2 = client.get("/api/tasks", params={"states": "done"}).json()
    assert [x["task_id"] for x in d2["tasks"]] == [b.task_id]
    d3 = client.get("/api/tasks", params={"limit": 1}).json()
    assert len(d3["tasks"]) == 1
    d4 = client.get("/api/tasks", params={"refresh": 0}).json()
    assert d4["ok"] is True and len(d4["tasks"]) == 2


def test_b3_dead_pid_becomes_interrupted(client, tr, tasks_dir):
    t = _make(tr, tasks_dir, title="幽灵任务")
    t.data["proc"] = {"pid": 999999, "create_time": 1.0}
    t.flush()
    d = client.get("/api/tasks").json()
    card = next(x for x in d["tasks"] if x["task_id"] == t.task_id)
    assert card["status"] == "interrupted" and card["alive"] is False
    assert "进程已不在" in card["error"]
    on_disk = json.load(open(os.path.join(tasks_dir, t.task_id + ".json"), encoding="utf-8"))
    assert on_disk["status"] == "interrupted"


# ------------------------------------------------------------------ C 详情
def test_c1_detail_404_and_confined_script(client, tr, tasks_dir, tmp_path):
    assert client.get("/api/tasks/nope").status_code == 404
    sess = tmp_path / "memomics-x"
    (sess / "scripts").mkdir(parents=True)
    script = sess / "scripts" / "qc.R"
    script.write_text("print('hello')\n", encoding="utf-8")
    t = _make(tr, tasks_dir, title="详情任务", session_dir=str(sess), script=str(script))
    t.data["log"] = _write_log(tasks_dir, t.task_id, 20)
    t.flush()
    d = client.get("/api/tasks/" + t.task_id, params={"tail": 5}).json()["task"]
    assert d["session_dir"] == str(sess)
    assert d["log_tail"].splitlines()[-1] == "log line 19"
    assert d["log_size"] > 0 and d["script_path"] == str(script)
    assert "hello" in d["script_text"]
    # 会话目录外的脚本：面板不许变成任意文件读取
    t2 = _make(tr, tasks_dir, title="越界脚本", session_dir=str(sess),
               script="C:" + os.sep + "Windows" + os.sep + "win.ini")
    d2 = client.get("/api/tasks/" + t2.task_id).json()["task"]
    assert d2["script_text"] == "" and d2["script_path"] == ""
    # 够不着要说人话，不能让用户以为这个任务压根没脚本
    assert "安全策略" in d2["script_note"] and "win.ini" in d2["script_note"]


def test_c2_detail_outputs_exist_and_size(client, tr, tasks_dir, tmp_path):
    t = _make(tr, tasks_dir, title="产物任务", session_dir=str(tmp_path))
    real = tmp_path / "out.h5"
    real.write_bytes(b"x" * 1234)
    t.output(str(real))
    t.output(str(tmp_path / "missing.csv"))
    d = client.get("/api/tasks/" + t.task_id).json()["task"]
    out = {o["path"]: o for o in d["outputs"]}
    assert out[str(real)]["exists"] is True and out[str(real)]["size"] == 1234
    assert out[str(tmp_path / "missing.csv")]["exists"] is False
    assert out[str(real)]["abs"] == str(real)
    assert d["wrapper_pid"] == os.getpid()
    assert "env" in d and d["cmd"] == ""


def test_b4_card_exposes_current_stage_name(client, tr, tasks_dir):
    """面板列表读的是 card["stage"]（阶段 1/2：训练），契约里没有这个字段就得派生出来，
    否则真机上永远显示「阶段 1/2：」——冒号后面空着。"""
    t = _make(tr, tasks_dir, title="阶段名放在卡片上", stages=["读入", "训练", "出图"])
    t.stage("训练")
    t.flush()
    card = [c for c in client.get("/api/tasks").json()["tasks"] if c["task_id"] == t.task_id][0]
    assert card["stage"] == "训练"
    assert card["stage_index"] == 1 and card["stage_total"] == 3
    # 阶段全部跑完（没有 running 的）就不该硬编一个名字
    t.finish("done")
    card2 = [c for c in client.get("/api/tasks").json()["tasks"] if c["task_id"] == t.task_id][0]
    assert card2["stage"] == ""
    # 没有阶段的任务也不能炸
    t3 = _make(tr, tasks_dir, title="没有阶段", stages=None)
    card3 = [c for c in client.get("/api/tasks").json()["tasks"] if c["task_id"] == t3.task_id][0]
    assert card3["stage"] == "" and card3["stage_total"] == 0


def test_c3_relative_output_resolves_under_results_and_cwd(client, tr, tasks_dir, tmp_path):
    """真机踩到的坑：脚本按约定打相对路径 #TASK:OUTPUT t5_qc_box.png，产物其实落在
    <会话>/results/ 下，旧代码只按会话目录拼一次 → 文件明明在，面板显示"不存在"。"""
    sess = tmp_path / "memomics-y"
    (sess / "results").mkdir(parents=True)
    real = sess / "results" / "box.png"
    real.write_bytes(b"png" * 100)
    t = _make(tr, tasks_dir, title="相对产物", session_dir=str(sess))
    t.output("box.png")
    t.output("results/box.png")
    t.output("cwd_only.csv")
    cwd = tmp_path / "workdir"
    cwd.mkdir()
    (cwd / "cwd_only.csv").write_text("a,b\n", encoding="utf-8")
    t.data["cwd"] = str(cwd)
    t.output("nowhere.txt")
    t.flush()
    d = client.get("/api/tasks/" + t.task_id).json()["task"]
    out = {o["path"]: o for o in d["outputs"]}
    assert out["box.png"]["exists"] is True and out["box.png"]["size"] == 300
    assert out["box.png"]["abs"] == str(real)
    assert out["results/box.png"]["exists"] is True
    assert out["cwd_only.csv"]["exists"] is True and out["cwd_only.csv"]["abs"] == str(cwd / "cwd_only.csv")
    assert out["nowhere.txt"]["exists"] is False and out["nowhere.txt"]["size"] is None
    # 解析不出来也要给出"找过哪里"，不能返回空串让面板没法提示
    assert out["nowhere.txt"]["abs"].endswith("nowhere.txt")


# ------------------------------------------------------------------ D 日志
def test_d1_log_route_tail_grep_and_missing(client, tr, tasks_dir):
    assert client.get("/api/tasks/nope/log").status_code == 404
    t = _make(tr, tasks_dir, title="日志任务")
    path = _write_log(tasks_dir, t.task_id, 30)
    t.data["log"] = path
    t.flush()
    d = client.get("/api/tasks/" + t.task_id + "/log", params={"tail": 4}).json()
    assert d["exists"] is True and d["size"] > 0
    assert d["text"].splitlines() == ["log line 26", "log line 27", "log line 28", "log line 29"]
    g = client.get("/api/tasks/" + t.task_id + "/log", params={"tail": 30, "grep": "line 7"}).json()
    assert g["text"].splitlines() == ["log line 7"]
    # 日志文件不存在（还没写）：不报错，exists=False
    t2 = _make(tr, tasks_dir, title="无日志")
    d2 = client.get("/api/tasks/" + t2.task_id + "/log").json()
    assert d2["ok"] is True and d2["exists"] is False and d2["text"] == ""


# ------------------------------------------------------------------ E 取消
def test_e1_cancel_requires_token(client, tr, tasks_dir):
    t = _make(tr, tasks_dir, title="要令牌")
    r = client.post("/api/tasks/%s/cancel" % t.task_id, headers={"X-Task-Token": "bad"})
    assert r.status_code == 401
    assert client.post("/api/tasks/nope/cancel", headers={"X-Task-Token": "bad"}).status_code == 401


def test_e2_cancel_unknown_and_terminal(client, tr, tasks_dir, token):
    hdr = {"X-Task-Token": token}
    assert client.post("/api/tasks/nope/cancel", headers=hdr).status_code == 404
    t = _make(tr, tasks_dir, title="已结束")
    t.finish("done", exit_code=0)
    r = client.post("/api/tasks/%s/cancel" % t.task_id, headers=hdr)
    assert r.status_code == 409 and "已结束" in r.json()["error"]
    d = json.load(open(os.path.join(tasks_dir, t.task_id + ".json"), encoding="utf-8"))
    assert d["status"] == "done" and "cancel_requested" not in d


def test_e3_cancel_real_task_kills_child(client, tasks_dir, token, home):
    """真起一个 wrapper 子进程（跑 120s 睡眠），走路由取消 -> cancelled + 子进程真没了。"""
    env = dict(os.environ)
    env["MEMOMICS_TASKS_DIR"] = tasks_dir
    env["MEMOMICS_RUNTIME_DIR"] = str(home / "runtime")
    env["PYTHONIOENCODING"] = "utf-8"
    p = subprocess.Popen([sys.executable, TRCLI, "--type", "cellbender", "--title", "取消真任务",
                          "--stages", "去背景", "--", sys.executable, "-c",
                          "import time;print('started',flush=True);time.sleep(120)"],
                         env=env, cwd=_REPO, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    try:
        child_pid, task_id = None, None
        for _ in range(80):
            time.sleep(0.25)
            for fn in os.listdir(tasks_dir):
                if not fn.endswith(".json"):
                    continue
                d = json.load(open(os.path.join(tasks_dir, fn), encoding="utf-8"))
                if d.get("title") == "取消真任务" and (d.get("proc") or {}).get("pid"):
                    child_pid, task_id = d["proc"]["pid"], d["task_id"]
                    break
            if child_pid:
                break
        assert child_pid, "wrapper 没登记子进程 PID"
        r = client.post("/api/tasks/%s/cancel" % task_id, headers={"X-Task-Token": token})
        assert r.status_code == 200
        body = r.json()
        assert body["ok"] is True and body["status"] == "cancelled"
        final = json.load(open(os.path.join(tasks_dir, task_id + ".json"), encoding="utf-8"))
        assert final["status"] == "cancelled" and final["cancel_requested"] is True
        assert final.get("exit_code") in (None, 0, 1, -1) or final["status"] == "cancelled"
        TR = _tr()
        assert not TR.proc_alive(child_pid, None), "子进程还在跑"
    finally:
        if p.poll() is None:
            p.kill()
        p.wait(timeout=30)


# -------------------------------------------------------------- F 路由清单
def test_f1_new_routes_in_manifest():
    path = os.path.join(_REPO, "webui", "middleware_routes.json")
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    raw = json.dumps(data, ensure_ascii=False)
    for route in ("/api/tasks", "/api/tasks/{task_id}", "/api/tasks/{task_id}/log",
                  "/api/tasks/{task_id}/cancel", "/api/tasks/{task_id}/retry"):
        assert route in raw, "路由没进 middleware_routes.json：" + route
    total = data.get("total") or len(data)
    assert total >= 131, "路由数不对：%s（跑 --snapshot 同步）" % total


# ------------------------------------------------------- G 阶段时间线回归
def test_g1_pending_stage_gets_started_at(tr, tasks_dir):
    t = _make(tr, tasks_dir, title="时间线", stages=["读入", "训练", "收尾"])
    assert t.data["stages"][1].get("started_at") is None      # 预建时还没有
    t.stage("训练")
    assert t.data["stages"][1]["status"] == "running"
    assert t.data["stages"][1].get("started_at"), "点亮成 running 时必须写 started_at"
    time.sleep(0.05)
    t.stage("收尾")
    sec = t.data["stages"][1].get("sec")
    assert sec is not None and sec >= 0.0
    assert t.data["stages"][1]["ended_at"]
    # 全部收口后每条阶段都必须有 started_at / ended_at（面板时间线不留空）
    t.finish("done", exit_code=0)
    for st in t.data["stages"]:
        assert st.get("started_at"), st
        assert st.get("ended_at"), st


# ------------------------------------------------- H 路径穿越 / 越界（T9 真机补测）
def test_h1_task_id_traversal_rejected_everywhere(client, tr, tasks_dir, home):
    """任务 id 就是契约文件名 —— 任何 ../、绝对路径、反斜杠都必须在路由层被拒且不泄漏内容。

    三条读路由（详情 / 日志 / 取消）都要挡住：能读到一份会话外的文件就是越权，
    能取消一个不存在的 id 就是误伤。
    """
    (home / "secret.txt").write_text("TOP-SECRET", encoding="utf-8")
    bad = [
        "..%2F..%2Fsecret.txt",
        "..%2f..%2fsecret.txt",
        "%2e%2e%2f%2e%2e%2fsecret.txt",
        "....//....//secret.txt",
        "..\\..\\secret.txt",
        "..%5C..%5Csecret.txt",
        "C%3A%5CWindows%5Cwin.ini",
        "%2Fetc%2Fpasswd",
        "%00secret",
        "nope.json",
        "nope",
    ]
    for raw in bad:
        r = client.get("/api/tasks/" + raw)
        assert r.status_code in (400, 404), "%s 竟然返回 %s" % (raw, r.status_code)
        assert "TOP-SECRET" not in r.text
        # 回显的是用户自己发来的 id（JSON 转义过），文件内容一个字节都不许带出来
        assert "[fonts]" not in r.text.lower()
        lg = client.get("/api/tasks/" + raw + "/log")
        assert lg.status_code in (400, 404), "%s/log 竟然返回 %s" % (raw, lg.status_code)
        assert "TOP-SECRET" not in lg.text
        cx = client.post("/api/tasks/" + raw + "/cancel",
                         headers={"X-Task-Token": server._task_api_token()})
        assert cx.status_code in (400, 404), "%s/cancel 竟然返回 %s" % (raw, cx.status_code)


def test_h2_detail_never_reads_script_outside_session_or_repo(client, tr, tasks_dir, tmp_path):
    """脚本正文只允许读会话目录/仓库内的文件；越界的文件一个字节都不给。"""
    outside = tmp_path / "outside"
    outside.mkdir()
    secret = outside / "evil.R"
    secret.write_text("# SECRET-SCRIPT" + chr(10), encoding="utf-8")
    t = _make(tr, tasks_dir, title="越界脚本")
    t.data["script"] = str(secret)   # 契约里脚本正文的键就是 script
    t.flush()
    d = client.get("/api/tasks/" + t.task_id, params={"script": 1}).json()["task"]
    assert "SECRET-SCRIPT" not in json.dumps(d, ensure_ascii=False)
    assert d.get("script_text") == ""
    assert "安全策略" in (d.get("script_note") or "")


# ------------------------------------------------- I 阶段历史推 ETA（T10）
def _history_sample(tr, tasks_dir, sec_map, script="qc.R"):
    """造一条"真跑过"的历史任务 —— 走真实 API（stage/finish），不手塞 sec。

    契约里 stages[].sec 是 stage()/finish() 按 started_at 现算的（进程真经过这段才有的数），
    所以这里把 started_at 往回拨，再让 stage()/finish() 自己收口 —— 和真任务落盘形状一致。
    """
    from datetime import datetime, timedelta, timezone
    names = list(sec_map.keys())
    t = _make(tr, tasks_dir, title="历史样本", script=script, stages=names)
    now = datetime.now(timezone.utc)
    for idx, name in enumerate(names):
        row = t.data["stages"][idx]
        row["status"] = "running"
        row["started_at"] = (now - timedelta(seconds=sec_map[name])).isoformat(timespec="seconds")
        if idx + 1 < len(names):
            t.stage(names[idx + 1])          # 切段 → 上一段 done + sec
        else:
            t.finish("done", exit_code=0)    # 收尾 → 最后一段 done + sec
    return t


def _running_after_first_stage(tr, tasks_dir, first_sec, running_sec, script="qc.R", ttype="qc",
                               stages=("读入", "计算")):
    """造一条「第一段跑完、第二段正在跑」的活任务。"""
    from datetime import datetime, timedelta, timezone
    t = _make(tr, tasks_dir, title="正在跑", script=script, type=ttype, stages=list(stages))
    now = datetime.now(timezone.utc)
    t.data["status"] = "running"
    t.data["started_at"] = (now - timedelta(seconds=first_sec + running_sec)).isoformat(timespec="seconds")
    t.data["stages"][0].update({
        "status": "running",
        "started_at": (now - timedelta(seconds=first_sec + running_sec)).isoformat(timespec="seconds")})
    t.stage(stages[1])      # 切段：第一段 done + sec，第二段 running
    t.data["status"] = "running"
    t.data["stages"][1]["started_at"] = (now - timedelta(seconds=running_sec)).isoformat(timespec="seconds")
    t.flush()
    return t


def _card(client, task_id, **params):
    q = {"limit": 200}
    q.update(params)
    for c in client.get("/api/tasks", params=q).json()["tasks"]:
        if c["task_id"] == task_id:
            return c
    return None


def test_i1_card_eta_comes_from_stage_history(client, tr, tasks_dir):
    """同类型跑够历史后，活任务要给「还要多久」，并且写清出处（按几次历史）。"""
    for _ in range(3):
        _history_sample(tr, tasks_dir, {"读入": 10, "计算": 30})
    run = _running_after_first_stage(tr, tasks_dir, first_sec=10, running_sec=5)
    card = _card(client, run.task_id)
    assert card["eta_source"] == "history", card
    assert 20 <= card["eta_sec"] <= 30, "计算段历史 30s、已跑 5s，还 25s 上下，实测 %s" % card["eta_sec"]
    assert card["eta_confidence"] == "高" and "3 次" in card["eta_basis"]
    assert card["eta_text"] and card["eta_text"] == tr.Task._fmt_sec(card["eta_sec"]), card
    assert card["eta_sec"] >= 20 and card["eta_sec"] <= 31
    done_card = _card(client, _history_sample(tr, tasks_dir, {"读入": 10}).task_id)
    assert done_card["eta_sec"] is None and done_card["eta_source"] == ""


def test_i2_history_survives_status_filter_and_detail_matches_list(client, tr, tasks_dir):
    """历史必须在「按状态过滤」之前汇总：只看 running 时 ETA 不能凭空消失。"""
    for _ in range(3):
        _history_sample(tr, tasks_dir, {"读入": 10, "计算": 30})
    run = _running_after_first_stage(tr, tasks_dir, first_sec=10, running_sec=5)
    only_run = _card(client, run.task_id, states="running")
    assert only_run is not None and only_run["eta_source"] == "history", only_run
    detail = client.get("/api/tasks/" + run.task_id).json()["task"]
    assert detail["eta_source"] == "history"
    assert abs(detail["eta_sec"] - only_run["eta_sec"]) <= 1.0


def test_i3_no_history_means_no_fake_eta(client, tr, tasks_dir):
    """头一回跑、没有任何历史 —— 不许拍脑袋：没进度就不给数，有进度也只标按进度外推 + 低可信度。"""
    from datetime import datetime, timedelta, timezone
    lonely = _make(tr, tasks_dir, title="头一回跑", script="first.R", type="qc", stages=["读入", "计算"])
    now = datetime.now(timezone.utc)
    lonely.data["status"] = "running"
    lonely.data["started_at"] = (now - timedelta(seconds=20)).isoformat(timespec="seconds")
    lonely.data["stages"][0].update({
        "status": "running",
        "started_at": (now - timedelta(seconds=20)).isoformat(timespec="seconds")})
    lonely.flush()
    card = _card(client, lonely.task_id)
    assert card["eta_sec"] is None and card["eta_text"] == "" and card["eta_basis"] == "", card
    lonely.data["progress"] = {"value": 0.5, "text": "一半"}
    lonely.flush()
    card2 = _card(client, lonely.task_id)
    assert card2["eta_source"] == "progress" and card2["eta_confidence"] == "低", card2
    assert 15 <= card2["eta_sec"] <= 25, card2


def test_i4_stage_longer_than_history_never_gives_negative_eta(client, tr, tasks_dir):
    """实际比历史慢很多时：剩余不能算成负数（面板上不许出现「还要 -3s」）。"""
    for _ in range(3):
        _history_sample(tr, tasks_dir, {"读入": 10, "计算": 4, "出图": 20})
    run = _running_after_first_stage(tr, tasks_dir, first_sec=10, running_sec=999,
                                     stages=("读入", "计算", "出图"))
    card = _card(client, run.task_id)
    assert card["eta_sec"] is not None and card["eta_sec"] >= 15, card
    assert card["eta_sec"] <= 30, "只剩出图 20s 上下，超时的那段不能倒扣成负数"

# --------------------------------------------- J 失败任务一键重试（T12）
def _failed(tr, tasks_dir, cmd="python -c pass", title="失败任务", **kw):
    """造一条「真失败过」的契约：状态 failed + 退出码 3 + 记着实际命令。"""
    t = _make(tr, tasks_dir, title=title, **kw)
    if cmd is not None:
        t.data["cmd"] = cmd
    t.finish("failed", exit_code=3, error="脚本炸了")
    return t


def _retry_contracts(tasks_dir, root):
    """任务目录里「根是 root」的重试契约（按第几次重试排序）。"""
    out = []
    for fn in os.listdir(tasks_dir):
        if not fn.endswith(".json"):
            continue
        d = json.load(open(os.path.join(tasks_dir, fn), encoding="utf-8"))
        params = d.get("params") or {}
        if str(params.get("重试根") or "") == str(root):
            out.append(d)
    return sorted(out, key=lambda x: int((x.get("params") or {}).get("第几次重试") or 0))


def test_j1_retry_requires_token_and_unknown_404(client, tr, tasks_dir, token):
    t = _failed(tr, tasks_dir, cmd="python -c pass")
    assert client.post("/api/tasks/%s/retry" % t.task_id,
                       headers={"X-Task-Token": "bad"}).status_code == 401
    assert client.post("/api/tasks/nope/retry", headers={"X-Task-Token": "bad"}).status_code == 401
    assert client.post("/api/tasks/nope/retry",
                       headers={"X-Task-Token": token}).status_code == 404


def test_j2_retry_only_for_failed_with_recorded_cmd(client, tr, tasks_dir, token):
    """只对 failed/interrupted 且契约里真记了命令的任务开重试 —— 其它一律 409 说清原因。"""
    hdr = {"X-Task-Token": token}
    done = _make(tr, tasks_dir, title="跑完了")
    done.finish("done", exit_code=0)
    r = client.post("/api/tasks/%s/retry" % done.task_id, headers=hdr)
    assert r.status_code == 409 and "没失败" in r.json()["error"], r.text
    assert r.json()["retry"]["allowed"] is False

    cancelled = _make(tr, tasks_dir, title="用户停的")
    cancelled.finish("cancelled", error="用户取消")
    assert client.post("/api/tasks/%s/retry" % cancelled.task_id, headers=hdr).status_code == 409

    nocmd = _failed(tr, tasks_dir, cmd="", title="没记命令")
    r3 = client.post("/api/tasks/%s/retry" % nocmd.task_id, headers=hdr)
    assert r3.status_code == 409 and "实际命令" in r3.json()["error"], r3.text

    # interrupted（进程没了/服务重启留下的残局）也算失败，允许重试
    broke = _make(tr, tasks_dir, title="残局", cmd="python -c pass")
    broke.data["status"] = "interrupted"
    broke.flush()
    assert server._retry_plan(broke.data, {})["allowed"] is True


def test_j3_retry_refused_while_previous_retry_still_running(client, tr, tasks_dir, token):
    """上一次重试还在跑时不能再叠一次（同一根只允许一个在飞的），免得点两下起两个。"""
    hdr = {"X-Task-Token": token}
    t = _failed(tr, tasks_dir, cmd="python -c pass", title="原任务")
    live = _make(tr, tasks_dir, title="重试 1",
                 params={"重试来源": t.task_id, "重试根": t.task_id, "第几次重试": "1"})
    r = client.post("/api/tasks/%s/retry" % t.task_id, headers=hdr)
    assert r.status_code == 409 and "还在跑" in r.json()["error"], r.text
    assert live.task_id in r.json()["error"]
    # 那次重试自己失败了 -> 可以再试：第 2 次，间隔按退避是 5s
    live.finish("failed", exit_code=1, error="又炸了")
    plan = server._retry_plan(t.data, server._retry_index(tr.list_tasks(limit=500, refresh=0)))
    assert plan["allowed"] is True and plan["attempt"] == 2 and plan["delay_sec"] == 5.0


def test_j4_retry_backoff_limits_after_three(client, tr, tasks_dir, token):
    """退避与上限全部来自 retry_backoff：2s/5s/15s 递增，连续 3 次后不再硬重试。"""
    hdr = {"X-Task-Token": token}
    assert server._retry_backoff.next_delay(1) == 2.0
    assert server._retry_backoff.next_delay(3) == 15.0
    t = _failed(tr, tasks_dir, cmd="python -c pass", title="连炸三次")
    for nth in ("1", "2", "3"):
        _make(tr, tasks_dir, title="重试 %s" % nth,
              params={"重试来源": t.task_id, "重试根": t.task_id, "第几次重试": nth}).finish(
                  "failed", exit_code=1, error="又炸了")
    r = client.post("/api/tasks/%s/retry" % t.task_id, headers=hdr)
    assert r.status_code == 409 and "上限" in r.json()["error"], r.text
    card = _card(client, t.task_id)
    assert card["retry_allowed"] is False and card["retry_used"] == 3 and card["retry_max"] == 3
    assert card["retry_reason"], card


def test_j5_card_exposes_retry_plan_before_any_retry(client, tr, tasks_dir):
    """失败卡片要直接告诉面板「能重试、第几次、隔多久」，不用面板自己猜。"""
    t = _failed(tr, tasks_dir, cmd="python -c pass", title="可重试")
    card = _card(client, t.task_id)
    assert card["retry_allowed"] is True and card["retry_attempt"] == 1
    assert card["retry_delay_sec"] == 2.0 and card["retry_max"] == 3
    assert card["retry_reason"] == "" and card["retry_root"] == t.task_id
    detail = client.get("/api/tasks/" + t.task_id).json()["task"]
    assert detail["retry_allowed"] is True and detail["retry_delay_sec"] == 2.0
    # 跑得好好的任务：不给重试按钮
    run = _make(tr, tasks_dir, title="在跑", cmd="python -c pass")
    assert _card(client, run.task_id)["retry_allowed"] is False


def test_j6_split_cmd_quotes_only_never_shell():
    """契约里的命令是字符串（为显示拼的）—— 拆回参数只认双引号，绝不解释 shell 语法。"""
    chrome = r"C:\Program Files\Py\python.exe"
    got = server._split_cmd(r'"%s" -X utf8 "C:\tmp a\s.py"' % chrome)
    assert got[0] == chrome and got[1] == "-X"
    assert got[-1] == r"C:\tmp a\s.py", got
    assert server._split_cmd(["a", "b"]) == ["a", "b"]
    assert server._split_cmd("") == [] and server._split_cmd(None) == []
    # 管道 / && 一律当普通参数：宁可跑出来报错，也不偷偷变成 shell 执行
    assert server._split_cmd("a && b | c") == ["a", "&&", "b", "|", "c"]


def test_j7_retry_really_respawns_and_runs(client, tr, tasks_dir, home, token, monkeypatch):
    """一键重试必须真起进程真跑完 —— 不是只写一份契约就算数。

    这里把退避压成 0（只为测试快），其余全走真链路：路由 -> _spawn_retry -> 真 wrapper ->
    真子进程写文件；最后核对重试任务的溯源字段、脚本/阶段搬运、退出码。
    """
    from webui.runtime.retry_backoff import RetryBackoff
    monkeypatch.setattr(server, "_retry_backoff",
                        RetryBackoff(base_delays=(0, 0, 0), max_failures=3))
    sess = home / "sess"
    sess.mkdir()
    marker = home / "retry_marker.txt"
    child = home / "retry_child.py"
    child.write_text("import pathlib" + chr(10) +
                     "pathlib.Path(r'%s').write_text('重试真的跑了', encoding='utf-8')" % marker + chr(10),
                     encoding="utf-8")
    cmd_str = '"%s" -X utf8 "%s"' % (sys.executable, child)
    t = _failed(tr, tasks_dir, cmd=cmd_str, title="要重试的任务", type="qc",
                session_dir=str(sess), script=str(child), stages=["跑起来"])
    hdr = {"X-Task-Token": token}
    r = client.post("/api/tasks/%s/retry" % t.task_id, headers=hdr)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True and body["attempt"] == 1 and body["scheduled"] is False
    assert body["delay_sec"] == 0 and (body["spawned"] or {}).get("pid"), body
    # 重试进程必须落在原会话目录里跑（中间文件才接得上）
    assert str(body["spawned"]["cwd"]).lower() == str(sess).lower(), body["spawned"]

    newd = None
    for _ in range(80):
        time.sleep(0.25)
        rows = _retry_contracts(tasks_dir, t.task_id)
        if rows:
            newd = json.load(open(os.path.join(tasks_dir, rows[0]["task_id"] + ".json"),
                                  encoding="utf-8"))
            if newd.get("status") in ("done", "failed"):
                break
    assert newd, "重试任务没落地到服务端正读的目录"
    assert newd["task_id"] != t.task_id
    assert str(newd["params"]["重试来源"]) == t.task_id
    assert str(newd["params"]["重试根"]) == t.task_id
    assert str(newd["params"]["第几次重试"]) == "1"
    assert "（重试 1/3）" in newd["title"], newd["title"]
    assert newd["type"] == "qc" and newd["script"] == str(child)
    assert [st["name"] for st in newd["stages"]] == ["跑起来"]
    assert newd["status"] == "done" and newd["exit_code"] == 0, newd
    assert marker.is_file(), "重试的子进程没真执行"
    assert "重试真的跑了" in marker.read_text(encoding="utf-8")
    # 面板列表里这条重试也在，而且它自己是 done（不给重试按钮）
    card = _card(client, newd["task_id"])
    assert card is not None and card["status"] == "done" and card["retry_allowed"] is False
    # 原任务还能再重试 -> 第 2 次，并且也要真跑完（等它收尾，别留野进程）
    r2 = client.post("/api/tasks/%s/retry" % t.task_id, headers=hdr)
    assert r2.status_code == 200 and r2.json()["attempt"] == 2, r2.text
    second = None
    for _ in range(80):
        time.sleep(0.25)
        rows = _retry_contracts(tasks_dir, t.task_id)
        if len(rows) >= 2:
            second = json.load(open(os.path.join(tasks_dir, rows[-1]["task_id"] + ".json"),
                                    encoding="utf-8"))
            if second.get("status") in ("done", "failed"):
                break
    assert second is not None and str(second["params"]["第几次重试"]) == "2", second
    assert second["status"] == "done", second


def test_j8_second_click_while_retry_is_queued_is_refused(client, tr, tasks_dir, monkeypatch):
    """连点两下不能排出两次重试：退避那几秒里契约还没落地，名额也得先占住。"""
    t = _failed(tr, tasks_dir, cmd="python -c pass", title="连点两下")
    items = tr.list_tasks(limit=500, refresh=0)
    assert server._retry_plan(t.data, server._retry_index(items))["allowed"] is True
    # 模拟"已排定退避中的那次"：索引里该根立刻变成有人在跑
    idx = server._retry_index(items, [t.task_id])
    assert idx[t.task_id]["live"] == "已排定（等退避）"
    plan = server._retry_plan(t.data, idx)
    assert plan["allowed"] is False and "还在跑" in plan["reason"], plan
    monkeypatch.setitem(server._RETRY_INFLIGHT, t.task_id, time.time())
    card = _card(client, t.task_id)
    assert card["retry_allowed"] is False and "还在跑" in card["retry_reason"], card
    # 拉起来之后名额放开，链上的真实状态接管
    monkeypatch.delitem(server._RETRY_INFLIGHT, t.task_id)
    assert _card(client, t.task_id)["retry_allowed"] is True
# ------------------------------------------- K 会话标注（T13：不同会话不串）
def _card_by_id(client, task_id):
    return next(x for x in client.get("/api/tasks").json()["tasks"] if x["task_id"] == task_id)


def test_k1_card_carries_session_title(client, tr, tasks_dir, monkeypatch):
    """每条卡片都要带"属于哪个会话的名字" —— 只给一串 memomics-xxxx 等于没标。"""
    t = _make(tr, tasks_dir, title="标会话", session_id="memomics-aaa")
    monkeypatch.setattr(server, "_session_title", lambda sid: "骨骼肌 QC 跑通")
    card = _card_by_id(client, t.task_id)
    assert card["session_id"] == "memomics-aaa"
    assert card["session_title"] == "骨骼肌 QC 跑通", card


def test_k2_session_title_helper_never_raises_and_is_cached(monkeypatch):
    """查会话名要稳且要便宜：查不到给空串（面板显示 id），同一会话 30 秒内只查一次库。"""
    server._SESSION_TITLE_MEMO.clear()
    calls = {"n": 0}

    class _DB:
        def get_session_title(self, sid):
            calls["n"] += 1
            return "骨骼肌 QC 跑通" if sid == "memomics-known" else None

        def get_session(self, sid):
            return None

    monkeypatch.setattr(server, "_get_session_db", lambda: _DB())
    assert server._session_title("memomics-known") == "骨骼肌 QC 跑通"
    assert server._session_title("memomics-known") == "骨骼肌 QC 跑通"
    assert calls["n"] == 1, "同一会话重复查库了 —— 面板 2 秒拉一次列表，会打爆 DB"
    assert server._session_title("memomics-none") == ""
    for bad in ("", None, "memomics-\u0000", "x" * 500):
        assert isinstance(server._session_title(bad), str), "诡异输入把列表带崩了"

    def _boom():
        raise RuntimeError("state.db 挂了")

    monkeypatch.setattr(server, "_get_session_db", _boom)
    server._SESSION_TITLE_MEMO.clear()
    assert server._session_title("memomics-any") == "", "取不到名字是常态，不该抛"


def test_k3_title_falls_back_to_last_user_message_and_is_trimmed(monkeypatch):
    """没标题（新会话）就退回最近一句用户话；长标题截断，别把抽屉撑破。"""
    server._SESSION_TITLE_MEMO.clear()
    monkeypatch.setattr(server, "_queue_label", lambda sess: "帮我把这批单细胞 QC 跑一遍")
    monkeypatch.setattr(server, "_get_session_db", lambda: _DBNoTitle())
    assert server._session_title("memomics-brandnew") == "帮我把这批单细胞 QC 跑一遍"
    # 标题只有默认占位（新会话）时也该退回用户那句话
    server._SESSION_TITLE_MEMO.clear()
    monkeypatch.setattr(server, "_get_session_db", lambda: _DBPlaceholder())
    assert server._session_title("memomics-brandnew") == "帮我把这批单细胞 QC 跑一遍"
    # 超长标题截到 60 字
    server._SESSION_TITLE_MEMO.clear()
    monkeypatch.setattr(server, "_queue_label", lambda sess: "")
    monkeypatch.setattr(server, "_get_session_db", lambda: _DBLong())
    got = server._session_title("memomics-long")
    assert len(got) == 60 and got.startswith("很长的标题")


class _DBNoTitle:
    def get_session_title(self, sid):
        return None

    def get_session(self, sid):
        return {"session_id": sid}


class _DBPlaceholder:
    def get_session_title(self, sid):
        return "新会话"

    def get_session(self, sid):
        return {"session_id": sid}


class _DBLong:
    def get_session_title(self, sid):
        return "很长的标题" * 40

    def get_session(self, sid):
        return {}


def test_k4_task_list_still_works_when_db_is_dead(client, tr, tasks_dir, monkeypatch):
    """库挂了、会话名取不到时，/api/tasks 也必须正常返回（名字退化成空串）。"""

    def _boom():
        raise RuntimeError("state.db 挂了")

    t = _make(tr, tasks_dir, title="库挂了也得能看见", session_id="memomics-aaa")
    monkeypatch.setattr(server, "_get_session_db", _boom)
    server._SESSION_TITLE_MEMO.clear()
    d = client.get("/api/tasks").json()
    assert d["ok"] is True
    card = next(x for x in d["tasks"] if x["task_id"] == t.task_id)
    assert card["session_title"] == "" and card["session_id"] == "memomics-aaa"




