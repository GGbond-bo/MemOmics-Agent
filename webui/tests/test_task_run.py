# -*- coding: utf-8 -*-
"""task_run（后台任务契约 + wrapper）守卫测试 —— 2026-09-24 新增。

覆盖：契约原子落盘、阶段/进度/参数/产物语义、跨语言标记行、UTF-8/GB18030 解码、
PID 复用防护、服务重启后的 interrupted 收敛、路径穿越、tail 大日志、并发写、
wrapper 真跑命令（成功/失败/取消）、CLI --list/--show。

真机极端场景（8MB 日志、5 并发 wrapper、脏字节、杀子树）在
E:/release/_t1_probe.py 里另跑一遍（38 项全过），这里只留确定性的快速守卫。
"""
import importlib.util
import json
import os
import subprocess
import sys
import threading
import time

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO = os.path.dirname(os.path.dirname(_HERE))
TRCLI = os.path.join(_REPO, "memomics", "bio_tools", "task_run.py")


def _load_task_run():
    """按文件路径加载，绕开 memomics.bio_tools 包的重量级 __init__（它要 tools.registry）。"""
    spec = importlib.util.spec_from_file_location("task_run_under_test", TRCLI)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture()
def tr(tmp_path):
    mod = _load_task_run()
    tasks = tmp_path / "tasks"
    tasks.mkdir()
    mod.TASKS_DIR = str(tasks)
    mod.FALLBACK_LOG_DIR = str(tmp_path / "logs")
    os.makedirs(mod.FALLBACK_LOG_DIR, exist_ok=True)
    return mod


def _read(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------- A 契约本体
def test_a1_new_task_writes_atomic_json(tr):
    t = tr.new_task("QC 任务", type="qc", stages=["读入", "训练"], params={"min_cells": 3})
    path = os.path.join(tr.TASKS_DIR, t.task_id + ".json")
    assert os.path.isfile(path)
    d = _read(path)
    assert d["task_id"] == t.task_id and d["status"] == "running" and d["type"] == "qc"
    assert [s["name"] for s in d["stages"]] == ["读入", "训练"]
    assert d["stages"][0]["status"] == "running" and d["stages"][1]["status"] == "pending"
    assert d["params"] == {"min_cells": 3} and d["pid"] == os.getpid()
    assert not [f for f in os.listdir(tr.TASKS_DIR) if f.endswith(".tmp")]


def test_a2_stage_advance_and_jump_closes_previous(tr):
    t = tr.new_task("阶段语义", stages=["A", "B", "C"])
    t.stage("B")
    names = [s["name"] for s in t.data["stages"]]
    assert names == ["A", "B", "C"]
    assert t.data["stages"][0]["status"] == "done"
    assert t.data["stages"][1]["status"] == "running" and t.data["stages"][2]["status"] == "pending"
    t.stage("C")
    assert [s["status"] for s in t.data["stages"]] == ["done", "done", "running"]
    t.finish("done")
    assert [s["status"] for s in t.data["stages"]] == ["done", "done", "done"]
    assert t.data["stage_total"] == 3 and t.data["stage_index"] == 2


def test_a3_progress_forms_and_clamp(tr):
    t = tr.new_task("进度")
    t.progress(0.42, "half")
    assert t.data["progress"]["value"] == 0.42
    t.progress("63/150", "epoch")
    assert abs(t.data["progress"]["value"] - 0.42) < 0.01
    t.progress(2.0)
    assert t.data["progress"]["value"] == 1.0
    t.progress(-1)
    assert t.data["progress"]["value"] == 0.0
    t.progress("不是数", "文本留着")
    assert t.data["progress"]["value"] is None and t.data["progress"]["text"] == "文本留着"
    t.progress("3/0")
    assert t.data["progress"]["value"] is None


def test_a4_param_output_note(tr):
    t = tr.new_task("字段")
    t.param("epochs", 150)
    t.param("note", "长" * 500)
    assert t.data["params"]["epochs"] == 150 and len(t.data["params"]["note"]) == 300
    t.output("a.h5")
    t.output("a.h5")
    t.output("")
    assert t.data["outputs"] == ["a.h5"]
    t.note("一句话说明")
    assert t.data["summary"] == "一句话说明"


def test_a5_finish_writes_auto_summary_without_guessing(tr):
    """实测 22 个真任务 summary 全空（只有脚本自己调 note() 才有），面板「任务小结」
    那一行永远不出现。收尾必须用真数据拼一句：完成 · 2/2 段 · N 个产物。"""
    t = tr.new_task("小结", stages=["读入", "训练"])
    t.stage("读入")
    t.stage("训练")
    t.output("x.csv")
    t.output("y.png")
    t.finish("done", exit_code=0)
    smy = t.data["summary"]
    assert smy.startswith("完成"), smy
    assert "2/2 段" in smy and "2 个产物" in smy, smy
    assert "退出码" not in smy, "成功的任务不必提退出码（噪音）：" + smy


def test_a6_explicit_note_wins_over_auto_summary(tr):
    t = tr.new_task("小结优先")
    t.note("脚本自己写的小结")
    t.finish("done")
    assert t.data["summary"] == "脚本自己写的小结"


def test_a7_failure_summary_carries_exit_code_and_partial_stage(tr):
    t = tr.new_task("失败小结", stages=["读入", "训练", "出图"])
    t.stage("读入")
    t.stage("训练")
    t.finish("failed", error="boom", exit_code=3)
    smy = t.data["summary"]
    assert smy.startswith("失败") and "1/3 段" in smy and "退出码 3" in smy, smy


# ------------------------------------------------------- B 跨语言标记 / 解码
def test_b1_smart_decode_utf8_gbk_invalid(tr):
    assert tr.smart_decode("已解码".encode("utf-8")) == "已解码"
    assert tr.smart_decode("训练完成".encode("gb18030")) == "训练完成"
    bad = tr.smart_decode(b"good" + bytes([255, 254]) + b"junk")
    assert bad.startswith("good") and "junk" in bad


def test_b2_parse_progress_patterns(tr):
    assert tr.parse_progress_line("progress 45%")[0] == 0.45
    assert tr.parse_progress_line("Epoch 30/150 loss=0.4")[0] == pytest.approx(0.2)
    assert tr.parse_progress_line("Iteration 5|10")[0] == 0.5
    assert tr.parse_progress_line("processed 250/1000 cells")[0] == 0.25
    assert tr.parse_progress_line("[3/10] writing")[0] == 0.3
    assert tr.parse_progress_line("nothing here") == (None, None)
    assert tr.parse_progress_line("x" * 3000) == (None, None)


def test_b3_marker_handle(tr):
    t = tr.new_task("标记", stages=["读入", "训练"])
    assert t.handle_marker("#TASK:STAGE 训练") is True
    assert t.handle_marker("#TASK:PARAM epochs=150") is True
    assert t.handle_marker("#TASK:OUTPUT results/out.h5") is True
    assert t.handle_marker("#TASK:PROGRESS 0.66 收尾中") is True
    assert t.handle_marker("普通日志行") is False
    assert t.data["stages"][1]["status"] == "running"
    assert t.data["params"]["epochs"] == "150"
    assert t.data["outputs"] == ["results/out.h5"]
    assert t.data["progress"]["value"] == 0.66


# ------------------------------------------ C 存活核对 / 重启收敛 / 路径安全
def test_c1_reconcile_dead_pid_persists_interrupted(tr):
    t = tr.new_task("死进程")
    t.data["proc"] = {"pid": 999999, "create_time": 1.0}
    t.flush()
    out = tr.reconcile(t.data)
    assert out["status"] == "interrupted" and out["alive"] is False
    assert "进程已不在" in out["error"]
    assert _read(t.path)["status"] == "interrupted"


def test_c2_reconcile_alive_pid_and_pid_reuse_guard(tr):
    t = tr.new_task("活进程")
    ident = tr.proc_identity(os.getpid())
    t.data["proc"] = dict(ident)
    t.flush()
    out = tr.reconcile(dict(t.data))
    assert out["status"] == "running" and out["alive"] is True
    assert out.get("stalled") is False
    if ident.get("create_time"):
        stale = dict(t.data)
        stale["proc"] = {"pid": os.getpid(), "create_time": 1.0}
        assert tr.reconcile(stale)["status"] == "interrupted"


def test_c3_reconcile_leaves_terminal_states_alone(tr):
    t = tr.new_task("已结束")
    t.data["proc"] = {"pid": 999999, "create_time": 1.0}
    t.finish("done", exit_code=0)
    out = tr.reconcile(t.data)
    assert out["status"] == "done" and out["exit_code"] == 0


def test_c4_load_task_rejects_traversal_and_unknown(tr):
    assert tr.load_task("../../../../Windows/win.ini") is None
    assert tr.load_task("..") is None
    assert tr.load_task("no-such-task") is None
    t = tr.new_task("正常")
    assert tr.load_task(t.task_id).task_id == t.task_id


# ------------------------------------------------------------- D 日志 tail
def test_d1_tail_log_small_missing_big(tr, tmp_path):
    assert tr.tail_log(str(tmp_path / "nope.log"), 10) == ""
    small = tmp_path / "small.log"
    small.write_text("a" + chr(10) + "b" + chr(10) + "c" + chr(10), encoding="utf-8")
    assert tr.tail_log(str(small), 2).splitlines() == ["b", "c"]
    big = tmp_path / "big.log"
    with open(big, "w", encoding="utf-8") as f:
        for i in range(50000):
            f.write("line %d filler" % i + chr(10))
    t0 = time.time()
    tail = tr.tail_log(str(big), 3)
    assert time.time() - t0 < 1.0
    assert tail.splitlines()[-1] == "line 49999 filler"
    assert len(tail.splitlines()) == 3


# --------------------------------------------------------------- E wrapper
def _run_cli(tr, args, timeout=180):
    env = dict(os.environ)
    env["MEMOMICS_TASKS_DIR"] = tr.TASKS_DIR
    env["MEMOMICS_RUNTIME_DIR"] = os.path.dirname(tr.TASKS_DIR)
    env["PYTHONIOENCODING"] = "utf-8"
    return subprocess.run([sys.executable, TRCLI] + args, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", env=env, timeout=timeout,
                          cwd=_REPO)


def _find(tr, title):
    for fn in os.listdir(tr.TASKS_DIR):
        if fn.endswith(".json"):
            d = _read(os.path.join(tr.TASKS_DIR, fn))
            if d.get("title") == title:
                return d
    raise AssertionError("没找到任务契约：" + title)


def test_e1_run_command_success_with_markers(tr, tmp_path):
    script = ("print('#TASK:STAGE 训练');print('#TASK:PARAM epochs=150');"
              "print('#TASK:OUTPUT out.h5');print('Epoch 30/150 loss=0.4')")
    r = _run_cli(tr, ["--type", "qc", "--title", "E1 成功", "--stages", "读入,训练",
                      "--param", "min_cells=3", "--session-dir", str(tmp_path), "--",
                      sys.executable, "-c", script])
    assert r.returncode == 0, r.stderr[-400:]
    d = _find(tr, "E1 成功")
    assert d["status"] == "done" and d["exit_code"] == 0
    assert d["params"]["min_cells"] == "3" and d["params"]["epochs"] == "150"
    assert d["outputs"] == ["out.h5"]
    assert d["stages"][1]["status"] == "done" and len(d["stages"]) == 2
    assert os.path.isfile(d["log"]) and os.path.getsize(d["log"]) > 20
    assert tr.tail_log(d["log"], 5)


def test_e2_run_command_failure_propagates(tr, tmp_path):
    r = _run_cli(tr, ["--type", "table", "--title", "E2 失败", "--session-dir", str(tmp_path),
                      "--", sys.executable, "-c",
                      "import sys;print('boom');sys.stderr.write('bad thing');sys.exit(3)"])
    assert r.returncode == 3
    d = _find(tr, "E2 失败")
    assert d["status"] == "failed" and d["exit_code"] == 3
    assert "bad thing" in d["error"] or "boom" in d["error"]


def test_e3_cancel_flag_yields_cancelled_status(tr, tmp_path):
    env = dict(os.environ)
    env["MEMOMICS_TASKS_DIR"] = tr.TASKS_DIR
    env["MEMOMICS_RUNTIME_DIR"] = os.path.dirname(tr.TASKS_DIR)
    p = subprocess.Popen([sys.executable, TRCLI, "--type", "cellbender", "--title", "E3 取消",
                          "--session-dir", str(tmp_path), "--", sys.executable, "-c",
                          "import time;print('started',flush=True);time.sleep(120)"],
                         env=env, cwd=_REPO, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    try:
        child_pid = None
        for _ in range(60):
            time.sleep(0.5)
            try:
                d = _find(tr, "E3 取消")
            except AssertionError:
                continue
            child_pid = (d.get("proc") or {}).get("pid")
            if child_pid:
                break
        assert child_pid, "wrapper 没记到子进程 PID"
        cur = _read(os.path.join(tr.TASKS_DIR, d["task_id"] + ".json"))
        cur["cancel_requested"] = True
        cur["status"] = "cancelling"
        with open(os.path.join(tr.TASKS_DIR, d["task_id"] + ".json"), "w", encoding="utf-8") as f:
            json.dump(cur, f, ensure_ascii=False)
        tr.kill_tree(child_pid)
        p.wait(timeout=60)
        time.sleep(0.5)
        final = _read(os.path.join(tr.TASKS_DIR, d["task_id"] + ".json"))
        assert final["status"] == "cancelled", final.get("status")
        assert not tr.proc_alive(child_pid, None)
    finally:
        if p.poll() is None:
            p.kill()


def test_e4_env_snapshot_shape(tr):
    env = tr.env_snapshot()
    assert env["kind"] in ("R", "python", "conda")
    assert env["python"] and os.path.isfile(env["python"])
    if env.get("rscript"):
        assert os.path.isfile(env["rscript"])


# --------------------------------------------------------- F 并发 / 杀子树
def test_f1_concurrent_new_task_no_corruption(tr):
    ids = []

    def worker(i):
        t = tr.new_task("并发%d" % i, stages=["A"])
        t.progress(i / 10.0)
        ids.append(t.task_id)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(4)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert len(set(ids)) == 4
    files = [f for f in os.listdir(tr.TASKS_DIR) if f.endswith(".json")]
    assert len(files) == 4
    for f in files:
        _read(os.path.join(tr.TASKS_DIR, f))
    assert not [f for f in os.listdir(tr.TASKS_DIR) if f.endswith(".tmp")]


def test_f2_kill_tree_kills_only_that_child(tr):
    child = subprocess.Popen([sys.executable, "-c", "import time;time.sleep(120)"])
    time.sleep(0.5)
    assert tr.proc_alive(child.pid, None)
    out = tr.kill_tree(child.pid)
    assert out["term"] or out["kill"]
    time.sleep(0.5)
    assert not tr.proc_alive(child.pid, None)
    assert tr.proc_alive(os.getpid(), None)          # 自己没被误杀


# ------------------------------------------------------------------ G CLI
def test_g1_cli_list_and_show(tr, capsys):
    t = tr.new_task("CLI 列表", type="figure")
    assert tr.main(["--list"]) == 0
    out = capsys.readouterr().out
    assert t.task_id in out and "CLI 列表" in out
    assert tr.main(["--show", t.task_id]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["task_id"] == t.task_id


def test_g2_cli_requires_command(tr, capsys):
    assert tr.main([]) == 2


# ------------------------------------- H 阶段没跑完就不许说「完成」（T15，用户实测反馈）
# 原始现象：脚本用 --stages 声明 3 段，只跑到第 1 段就 exit 0，契约写 done、
# 面板给个 ✅ 完成 —— 用户看到的就是「阶段 1 跑完就算完成」。
def test_h1_finish_records_stages_never_reached(tr):
    t = tr.new_task("三段只跑一段", type="qc", stages=["读入", "训练", "过滤"])
    t.finish("done", exit_code=0)
    d = t.data
    assert d["status"] == "done" and d["exit_code"] == 0      # 退出码 0 是事实
    assert d["incomplete"] is True                            # 没跑完也是事实
    # new_task 会把第 1 段置成 running，finish(done) 把它收口成 done —— 所以"没跑到"的是后两段
    assert d["stage_unfinished"] == ["训练", "过滤"]
    assert [s["status"] for s in d["stages"]] == ["done", "pending", "pending"]
    assert "完成" in d["summary"] and "2 段没跑到" in d["summary"]
    assert "1/3 段" in d["summary"]


def test_h2_all_stages_done_is_not_flagged(tr):
    t = tr.new_task("两段都跑完", stages=["读入", "训练"])
    t.stage("读入", "done")
    t.stage("训练", "done")
    t.finish("done", exit_code=0)
    assert not t.data.get("incomplete")
    assert not t.data.get("stage_unfinished")
    assert t.data["summary"].startswith("完成 ")
    assert "没跑到" not in t.data["summary"]


def test_h3_failed_stays_failed_not_incomplete(tr):
    """失败本来就不叫完成，别再叠一层「没跑完」把话说乱。"""
    t = tr.new_task("炸了", stages=["A", "B"])
    t.finish("failed", exit_code=3, error="脚本炸了")
    assert t.data["status"] == "failed"
    assert t.data["stage_unfinished"] == ["B"]           # A 是 running，收口成 failed 了
    assert not t.data.get("incomplete")
    assert t.data["summary"].startswith("失败")


def test_h4_no_stage_declared_never_flagged(tr):
    """没声明阶段的普通任务（绝大多数）不能被误伤成「没跑完」。"""
    t = tr.new_task("随手跑一条命令", type="other")
    t.finish("done", exit_code=0)
    assert not t.data.get("incomplete") and not t.data.get("stage_unfinished")
    assert t.data["summary"] == "完成" or t.data["summary"].startswith("完成 · ")


def test_h5_cancelled_records_leftover_but_keeps_its_own_wording(tr):
    t = tr.new_task("跑到一半被停", stages=["A", "B", "C"])
    t.stage("A", "done")
    t.stage("B")
    t.finish("cancelled", error="用户取消")
    assert t.data["status"] == "cancelled"
    assert t.data["incomplete"] is True
    assert t.data["stage_unfinished"] == ["C"]
    assert t.data["summary"].startswith("已取消")           # 取消就是取消，不写"完成"


def test_h6_marker_channel_also_flags(tr):
    """跨语言打点通道（#TASK:STAGE）走同一条路：只打了一段照样算没跑完。"""
    t = tr.new_task("标记行只打一段", stages=["读入", "比对", "出图"])
    assert t.handle_marker("#TASK:STAGE 读入") is True
    t.finish("done", exit_code=0)
    assert t.data["incomplete"] is True
    assert t.data["stage_unfinished"] == ["比对", "出图"]
    assert t.data["stages"][0]["status"] == "done"
