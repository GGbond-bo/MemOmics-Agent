# -*- coding: utf-8 -*-
"""cluster_session（集群常驻 R 会话 / kernel 式持久化）守卫测试 —— 2026-10-09。

覆盖：会话号合法性与 ID 生成、注册表读写（find/latest 语义）、配置合并（全局 < 节点）、
请求/结果文本协议的纯函数（_req_text / _parse_res / _split_sections / _parse_state）、
代码模板（读入/保存/恢复）、daemon 现状（脚本存在 + 关键协议标记 + remote_cluster 的
动作接线与 schema 枚举）、以及**假连接**下的 status / exec 全链路（不碰真 SSH）。

按 test_large_cache.py 的约定用 importlib 按文件路径加载，绕开 memomics.bio_tools 的
包 __init__；cluster_session 依赖的 remote_cluster 用同一份真实文件加载后注入。
"""
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import time
import types

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO = os.path.dirname(os.path.dirname(_HERE))
CS = os.path.join(_REPO, "memomics", "bio_tools", "cluster_session.py")
RC = os.path.join(_REPO, "memomics", "bio_tools", "remote_cluster.py")
DAEMON = os.path.join(_REPO, "memomics_home", "skills", "bioinformatics",
                      "remote-cluster-execution", "scripts", "r_session_daemon.R")


def _load_pair():
    ha = os.path.join(_REPO, "hermes-agent")
    if ha not in sys.path:
        sys.path.insert(0, ha)
    rc_spec = importlib.util.spec_from_file_location("remote_cluster_under_test", RC)
    rc = importlib.util.module_from_spec(rc_spec)
    rc_spec.loader.exec_module(rc)

    pkg = sys.modules.get("memomics.bio_tools")
    if pkg is None:
        pkg = types.ModuleType("memomics.bio_tools")
        pkg.__path__ = []
        sys.modules["memomics.bio_tools"] = pkg
    sys.modules["memomics.bio_tools.remote_cluster"] = rc
    setattr(pkg, "remote_cluster", rc)

    cs_spec = importlib.util.spec_from_file_location("cluster_session_under_test", CS)
    cs = importlib.util.module_from_spec(cs_spec)
    cs_spec.loader.exec_module(cs)
    # 反过来也注入：remote_cluster 的会话转发函数是按模块名延迟导入的，
    # 测试里必须让它拿到这份（共享 monkeypatch 的）cs 实例。
    sys.modules["memomics.bio_tools.cluster_session"] = cs
    setattr(pkg, "cluster_session", cs)
    return cs, rc


@pytest.fixture()
def pair(tmp_path, monkeypatch):
    cs, rc = _load_pair()
    # 注册表落到 tmp，别动用户的 sessions.json
    reg = tmp_path / "sessions.json"
    monkeypatch.setattr(cs, "_sessions_path", lambda: reg)
    return cs, rc


# ------------------------------------------------------------------ ID / 命名


def test_session_id_validation(pair):
    cs, _ = pair
    assert cs._valid_session_id("s-20261009-101500-abcd")
    assert cs._valid_session_id("MuSC.proj_1")
    assert not cs._valid_session_id("")
    assert not cs._valid_session_id("bad/id")
    assert not cs._valid_session_id(".starts-with-dot")
    assert not cs._valid_session_id("x" * 60)

    sid = cs._new_id()
    assert sid.startswith("s-") and cs._valid_session_id(sid)
    assert cs._new_id() != sid
    rid = cs._new_req_id()
    assert rid.startswith("r-") and "-" in rid[2:]


def test_obj_name_from_path(pair):
    cs, _ = pair
    assert cs._obj_name_from_path("/a/b/musc_annotation_umap_clean.rds") == "musc_annotation_umap_clean"
    assert cs._obj_name_from_path("/a/b/MF-exercise 2.RDS") == "MF_exercise_2"
    assert cs._obj_name_from_path("/a/b/23GB.rds") == "obj_23GB"
    assert cs._obj_name_from_path("") == "obj"


# ------------------------------------------------------------------ 注册表


def test_registry_roundtrip_and_latest(pair):
    cs, _ = pair
    assert cs._load_registry() == {}
    cs._registry_upsert({"id": "s-b", "node": "node4", "dir": "/wd/b", "created": "2026-10-09 10:00:00",
                         "last_active": "2026-10-09 10:05:00", "status": "active"})
    cs._registry_upsert({"id": "s-a", "node": "node1", "dir": "/wd/a", "created": "2026-10-09 09:00:00",
                         "last_active": "2026-10-09 11:00:00", "status": "active"})
    cs._registry_upsert({"id": "s-dead", "node": "node1", "dir": "/wd/d", "created": "2026-10-08 09:00:00",
                         "last_active": "2026-10-08 12:00:00", "status": "stopped"})
    reg = cs._load_registry()
    assert set(reg) == {"s-a", "s-b", "s-dead"}
    assert cs.find_session("s-b")["dir"] == "/wd/b"
    assert cs.find_session("nope") is None
    # 最近活跃（未停止优先，stopped 兜底）
    assert cs.latest_session()["id"] == "s-a"
    assert cs.latest_session("node1")["id"] == "s-a"
    assert cs.latest_session("node4")["id"] == "s-b"
    # 全部 stopped 时才回落到 stopped
    cs._registry_touch(cs.find_session("s-a"), status="stopped")
    assert cs.latest_session()["id"] == "s-b"


def test_registry_touch_merges(pair):
    cs, _ = pair
    rec = cs._registry_upsert({"id": "s-x", "node": "node1", "dir": "/wd/x"})
    out = cs._registry_touch(rec, last_status="ok", readrds_calls=1)
    assert out["dir"] == "/wd/x" and out["last_status"] == "ok"
    assert cs.find_session("s-x")["last_status"] == "ok"


# ------------------------------------------------------------------ 配置合并


def test_session_cfg_merge(pair):
    cs, _ = pair
    cfg = {"session": {"env": "R4.3.3", "wait": 60, "roots": ["/opt/conda"]}}
    node = {"session": {"env": "R4.4.1_zb", "rscript": "/x/Rscript"}}
    s = cs._session_cfg(cfg, node)
    assert s["env"] == "R4.4.1_zb"          # 节点级覆盖全局
    assert s["rscript"] == "/x/Rscript"
    assert s["wait"] == 60                   # 未被覆盖的全局值保留
    assert s["roots"] == ["/opt/conda"]
    assert s["load_timeout"] == 1800         # 默认值兜底
    # 空值不许把默认打掉
    assert cs._session_cfg({"session": {"env": "  ", "roots": []}}, None)["env"] == "R4.41"


# ------------------------------------------------------------------ 文本协议


def test_req_text_and_r_escaping(pair):
    cs, _ = pair
    txt = cs._req_text("r-1", "eval", 'x <- "a\\b"\n')
    assert txt.startswith("#MM-REQ id=r-1 op=eval created=")
    assert 'x <- "a\\b"' in txt and txt.endswith("\n")
    assert cs._req_text("r-2", "eval", "y <- 1")[-1] == "\n"
    assert cs._r_str('a"b\\c') == '"a\\"b\\\\c"'


def test_parse_res_sections(pair):
    cs, _ = pair
    text = "\n".join([
        "#MM-RESULT v1", "id: r-1", "status: ok", "ms: 1234", "started: t0", "finished: t1",
        "readrds_calls: 1", "job_index: 2", "rss_kb: 1024", "objects: 7",
        "---OUTPUT---", "hello", "world", "---WARNINGS---", "some warning", "---ERROR---", "",
        "---READS---", "2026-10-09 10:00:00\t123456\t/a/b.rds",
    ])
    r = cs._parse_res(text)
    assert r["status"] == "ok" and r["ms"] == "1234"
    assert r["output"] == "hello\nworld"
    assert r["warnings"] == "some warning"
    assert r["error"] == "" and r["readrds_calls"] == 1 and r["objects"] == 7
    assert r["reads"][0]["path"] == "/a/b.rds"

    bad = cs._parse_res("\n".join(["id: r-2", "status: error", "---OUTPUT---", "",
                                   "---WARNINGS---", "", "---ERROR---", "boom", "---READS---", ""]))
    assert bad["status"] == "error" and bad["error"] == "boom"


def test_parse_state_and_sections(pair):
    cs, _ = pair
    st = cs._parse_state("pid=123\nstatus=busy\ncurrent=r-9\nrss_kb=524288\nfoo\n=xx\n")
    assert st["pid"] == "123" and st["status"] == "busy" and st["current"] == "r-9"
    assert "foo" not in st
    out = cs._split_sections("==STATE==\npid=1\n==PS==\nline; MM_ALIVE\n==QUEUE==\n--run--\n")
    assert "pid=1" in out["STATE"] and "MM_ALIVE" in out["PS"] and "--run--" in out["QUEUE"]


# ------------------------------------------------------------------ 代码模板


def test_load_code_template(pair):
    cs, _ = pair
    code = cs._load_code('/hw/PS/a/b/musc.rds', "musc")
    assert 'inp <- "/hw/PS/a/b/musc.rds"' in code
    assert "musc <- readRDS(inp)" in code          # 走会话层 readRDS（会被审计）
    assert ".mm_reads_count()" in code
    assert "stop(" in code                          # 文件不存在要停，别静默
    assert "\\n" in code                            # R 侧换行是转义后的字面量


def test_save_restore_code(pair):
    cs, _ = pair
    assert cs._save_code("ck1", ["a", "b"]) == 'mm_save(name = "ck1", objects = c("a", "b"))'
    assert cs._save_code("", None) == "mm_save(name = NULL, objects = NULL)"
    assert cs._restore_code("") == "mm_restore()"
    assert cs._restore_code("ck1.rds") == 'mm_restore("ck1.rds")'
    assert cs._wait_seconds({"wait": 5}, {"wait": 1200}) == 5
    assert cs._wait_seconds({}, {"wait": 1200}) == 1200
    assert cs._wait_seconds({"wait": "abc"}, {"wait": 90}) == 90
    assert cs._wait_seconds({"wait": -3}, {"wait": 90}) == 0


# ------------------------------------------------------------------ daemon 现状 + 工具接线


def test_daemon_script_present_and_protocol_markers():
    assert os.path.exists(DAEMON), "daemon 脚本不见了：%s" % DAEMON
    src = open(DAEMON, encoding="utf-8").read()
    for token in ("#MM-RESULT v2", "---OUTPUT---", "---READS---", "queue", "done",
                  "daemon.lock", "readRDS <- function", "mm_save <- function",
                  "mm_restore <- function", "mm_quit", "setsid",
                  # 抓图（Notebook 总端）：默认设备改写 + 每表达式收尾 + 图清单分段
                  "options(device = .mm_device)", ".mm_close_own_device", ".mm_eval_code",
                  "---PLOTS---", "mm_plots <- function", "plots_total"):
        assert token in src, "daemon 少了协议标记：%s" % token
    assert "\r\n" not in src, "daemon 脚本必须是 LF（CRLF 会让远端 R 报 \\r 语法错）"


def test_daemon_plot_flush_is_per_expression():
    """抓图的关键：每个顶层表达式后关掉我们开的设备，否则一个 cell 里第二张图会覆盖第一张。"""
    src = open(DAEMON, encoding="utf-8").read()
    body = re.search(r"\.mm_eval_code <- function.*?\n\}", src, re.S)
    assert body, "daemon 里找不到 .mm_eval_code"
    text = body.group(0)
    assert ".mm_close_own_device()" in text, ".mm_eval_code 丢了逐表达式收尾 → 会只剩最后一张图"
    assert "withVisible(eval(" in text, ".mm_eval_code 丢了 print.eval 语义（可见值要打印）"
    dev = re.search(r"\.mm_device <- function.*?\n\}", src, re.S)
    assert dev and "plots$dev <- grDevices::dev.cur()" in dev.group(0), \
        ".mm_device 没记住自己开的设备号（会导致误关用户自己的设备）"


def test_daemon_restore_resolves_bare_name_with_rds_suffix():
    """2026-10-09 实测事故：mm_restore("名字") 只补了 ckpt/ 前缀、没补 .rds → 「检查点不存在」。

    客户端 _restore_code 传的就是裸名字，所以解析必须落在 R 侧（用户手敲 mm_restore("名字") 同理）。
    """
    src = open(DAEMON, encoding="utf-8").read()
    body = re.search(r"mm_restore <- function.*?\n\}", src, re.S)
    assert body, "daemon 里找不到 mm_restore 函数体"
    text = body.group(0)
    assert 'paste0(cand, ".rds")' in text, "mm_restore 丢了「裸名字 → 补 .rds」兜底"
    assert "which.max(file.mtime(files))" in text, "mm_restore 丢了「空参 → 最新检查点」分支"


def test_remote_cluster_wiring(pair):
    cs, rc = pair
    for act in ("session_start", "session_exec", "session_save", "session_restore",
                "session_status", "session_stop", "session_list",
                "session_cells", "session_plot"):
        assert act in rc._ACTIONS, "remote_cluster 没接动作：%s" % act
        assert act in rc.SCHEMA["parameters"]["properties"]["action"]["enum"]
    assert "session" in rc._DEFAULT_CFG
    # 转发函数真的存在且能指向 cluster_session
    assert callable(rc._action_session_status)
    assert callable(rc._action_session_cells) and callable(rc._action_session_plot)
    # 会话动作的节点解析：账本里没有会话时给出可操作提示，而不是 needs_node 糊脸
    out = json.loads(rc.remote_cluster_handler({"action": "session_status"}))
    assert out["status"] == "error" and "session_list" in out.get("hint", "")


# ------------------------------------------------------------------ 假连接全链路


class _FakeConn:
    def __init__(self, output="", rc_=0):
        self.output = output
        self.rc_ = rc_
        self.commands = []

    def execute(self, command, **kwargs):
        self.commands.append(command)
        return {"output": self.output, "returncode": self.rc_}


def _wire_status(cs, rc, monkeypatch, output):
    fake = _FakeConn(output=output)
    monkeypatch.setattr(rc, "_select_node",
                        lambda cfg, req: ({"workdir": "/wd", "host": "h", "user": "u"},
                                          req or "node4", None))
    monkeypatch.setattr(rc, "_get_conn", lambda cfg: fake)
    monkeypatch.setattr(rc, "_exec_env", lambda conn, cmd, timeout=None: conn.execute(cmd))
    return fake


def test_action_status_alive(pair, monkeypatch):
    cs, rc = pair
    cs._registry_upsert({"id": "s-1", "node": "node4", "dir": "/wd/sess/s-1", "status": "active"})
    out_text = "\n".join([
        "==STATE==", "pid=4242", "status=idle", "started=2026-10-09 10:00:00",
        "updated=2026-10-09 10:10:00", "jobs_done=3", "readrds_calls=1", "objects=5", "rss_kb=1048576",
        "r_version=R version 4.4.1 (2024-06-14)",
        "==PS==", "4242 1048576 00:10  Ss  Rscript daemon.R", "MM_ALIVE",
        "==QUEUE==", "--run--", "==DONE==", "done/r-1.res.txt", "==CKPT==", "ckpt/latest.rds",
        "==LASTRES==", "id: r-1", "status: ok", "RunUMAP done in 42.0s",
        "==LOG==", "[t] end r-1 status=ok readrds=1",
    ])
    _wire_status(cs, rc, monkeypatch, out_text)
    payload = json.loads(cs.action_status({}, {"session_id": "s-1"}))
    assert payload["status"] == "ok" and payload["alive"] is True
    assert payload["pid"] == "4242" and payload["readrds_calls"] == "1"
    assert payload["rss_h"] and payload["jobs_done"] == "3"
    assert "RunUMAP done" in payload["last_result_tail"]
    # 注册表被顺手刷新
    assert cs.find_session("s-1")["status"] == "active"


def test_action_status_dead_gives_recovery_hint(pair, monkeypatch):
    cs, rc = pair
    cs._registry_upsert({"id": "s-2", "node": "node1", "dir": "/wd/sess/s-2", "status": "active"})
    out_text = "\n".join(["==STATE==", "pid=1", "status=stopped", "readrds_calls=2", "objects=0",
                          "==PS==", "MM_DEAD", "==QUEUE==", "--run--", "==DONE==", "==CKPT==",
                          "ckpt/c1.rds", "==LOG==", "[t] daemon exit"])
    _wire_status(cs, rc, monkeypatch, out_text)
    payload = json.loads(cs.action_status({}, {"session_id": "s-2"}))
    assert payload["status"] == "stopped" and payload["alive"] is False
    assert "restore" in payload["hint"] and cs.find_session("s-2")["status"] == "stopped"


def test_action_exec_through_fake_conn(pair, monkeypatch):
    cs, rc = pair
    cs._registry_upsert({"id": "s-3", "node": "node4", "dir": "/wd/sess/s-3", "status": "active"})
    fake = _FakeConn(output="")
    monkeypatch.setattr(rc, "_select_node",
                        lambda cfg, req: ({"workdir": "/wd", "host": "h", "user": "u"},
                                          req or "node4", None))
    monkeypatch.setattr(rc, "_get_conn", lambda cfg: fake)
    posted = {}

    def _fake_write(conn, path, text, mode="600", timeout=300):
        posted["path"] = path
        posted["text"] = text
        return {"ok": True, "bytes": len(text), "md5": "x", "remote_md5": "x", "path": path}

    monkeypatch.setattr(cs, "_remote_write", _fake_write)
    monkeypatch.setattr(cs, "_await_res", lambda conn, sdir, rid, wait: {
        "ready": True, "status": "ok", "ms": "2500", "output": "markers done", "warnings": "",
        "error": "", "readrds_calls": 1, "objects": 6, "reads": [], "rss_kb": "2048",
        "res_path": "/wd/sess/s-3/done/%s.res.txt" % rid,
    })
    payload = json.loads(cs.action_exec({}, {"session_id": "s-3", "code": "FindMarkers(musc)"}))
    assert payload["status"] == "ok" and payload["seconds"] == 2.5
    assert payload["readrds"] == {"calls": 1, "recent": []}
    assert payload["output"] == "markers done"
    assert posted["path"].startswith("/wd/sess/s-3/staging/")   # 先写 staging（daemon 不扫）
    assert "FindMarkers(musc)" in posted["text"]
    mv_cmds = [c for c in fake.commands if c.startswith("mv ")]
    assert mv_cmds and "/queue/" in mv_cmds[0] and "/staging/" in mv_cmds[0]  # 再原子入队
    # 注册表记了这次执行
    assert cs.find_session("s-3")["last_status"] == "ok"


def test_action_exec_async_returns_immediately(pair, monkeypatch):
    cs, rc = pair
    cs._registry_upsert({"id": "s-4", "node": "node4", "dir": "/wd/sess/s-4", "status": "active"})
    monkeypatch.setattr(rc, "_select_node",
                        lambda cfg, req: ({"workdir": "/wd", "host": "h"}, req or "node4", None))
    monkeypatch.setattr(rc, "_get_conn", lambda cfg: _FakeConn())
    monkeypatch.setattr(cs, "_remote_write",
                        lambda conn, path, text, mode="600", timeout=300: {"ok": True, "path": path})
    monkeypatch.setattr(cs, "_await_res",
                        lambda *a, **k: pytest.fail("async 不该等待结果"))
    payload = json.loads(cs.action_exec({}, {"session_id": "s-4", "code": "Sys.sleep(600)",
                                             "async": True}))
    assert payload["status"] == "accepted" and payload["request_id"]


def test_action_list_sorted(pair):
    cs, _ = pair
    cs._registry_upsert({"id": "s-old", "node": "node1", "title": "old", "created": "2026-10-01 00:00:00",
                         "last_active": "2026-10-01 00:00:00"})
    cs._registry_upsert({"id": "s-new", "node": "node4", "title": "new", "created": "2026-10-09 00:00:00",
                         "last_active": "2026-10-09 00:00:00"})
    payload = json.loads(cs.action_list({}, {}))
    assert payload["count"] == 2 and payload["sessions"][0]["id"] == "s-new"
    assert "session_stop" in payload["note"]


def test_action_list_live_uses_output_text(pair, monkeypatch):
    """live=true 要连上去核实（回归：曾把 _exec_disp 的 dict 当字符串 splitlines 炸掉）。"""
    cs, rc = pair
    cs._registry_upsert({"id": "s-live", "node": "node4", "dir": "/wd/sess/s-live",
                         "last_active": "2026-10-09 00:00:00"})
    out_text = "\n".join(["==STATE==", "pid=77", "status=idle", "readrds_calls=3", "objects=4",
                          "rss_kb=2048", "==PS==", "77 2048 00:01 Ss R", "MM_ALIVE",
                          "==QUEUE==", "--run--", "==DONE==", "==CKPT==", "==LOG=="])
    _wire_status(cs, rc, monkeypatch, out_text)
    payload = json.loads(cs.action_list({}, {"live": True}))
    row = payload["sessions"][0]
    assert row["alive"] is True and row["daemon_status"] == "idle"
    assert row["readrds_calls"] == "3" and row["rss_h"]
    assert "live_error" not in row


# ------------------------------------------------------------------ large_cache 标记的会话语义


def test_new_marker_not_included_override(tmp_path):
    lc_path = os.path.join(_REPO, "memomics", "bio_tools", "large_cache.py")
    spec = importlib.util.spec_from_file_location("large_cache_under_test2", lc_path)
    lc = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(lc)
    lc.MARKERS_DIR = str(tmp_path / "markers")
    lc.INDEX_FILE = os.path.join(lc.MARKERS_DIR, "index.jsonl")

    m = lc.new_marker("sess-1", "常驻会话", ["/hw/a.rds"], remote=True,
                      cache_root="/hw/sess", cache_scope="内存常驻对象", not_included=[])
    assert m["not_included"] == []                     # 会话不背「没矩阵」的锅
    m2 = lc.new_marker("light-1", "精简缓存", ["/hw/a.rds"], remote=True, cache_root="/hw/c")
    assert m2["not_included"] == ["expression_matrix", "counts", "scale.data"]  # 默认不变


# ------------------------------------------------------------------ Notebook 总端（cell 视图 + 抓图）
# 设计见 references/persistent-r-session.md：session_cells 一次 ssh 拉回最近 N 个 cell，
# session_plot 按 base64 取一张图内联；图由 daemon 的默认设备改写自动落到 plots/。


def test_parse_res_plots_section(pair):
    cs, _rc = pair
    text = "\n".join([
        "#MM-RESULT v2", "id: r-9", "status: ok", "ms: 1234", "started: 2026-10-09 10:00:00",
        "finished: 2026-10-09 10:00:01", "readrds_calls: 1", "objects: 5",
        "plots: 2", "plots_skipped: 0",
        "---OUTPUT---", "hello", "---WARNINGS---", "", "---ERROR---", "",
        "---READS---", "2026-10-09 09:59:00\t661800000\t/hw/MuSC.rds",
        "---PLOTS---",
        "/hw/sess/s-9/plots/r-9_01.png\t7524",
        "/hw/sess/s-9/plots/r-9_02.png\t15733",
    ])
    parsed = cs._parse_res(text)
    assert [p["path"].rsplit("/", 1)[-1] for p in parsed["plots"]] == ["r-9_01.png", "r-9_02.png"]
    assert parsed["plots"][0]["bytes"] == "7524"
    assert parsed["plots_skipped"] == "0"
    assert parsed["readrds_calls"] == 1 and parsed["objects"] == 5
    # 没有图时是空列表（老版本结果文件同样能解析）
    plain = cs._parse_res("id: r-1\nstatus: ok\n---OUTPUT---\nx\n---READS---\n")
    assert plain["plots"] == []


def test_cells_command_targets_recent_results(pair):
    cs, _rc = pair
    cmd = cs._cells_command("/hw/sess/s-9", 6)
    assert "cd /hw/sess/s-9" in cmd
    assert "ls -1t done/*.res.txt" in cmd and "head -n 6" in cmd      # 只要最近的
    for marker in ("==CELL== ", "==CODE==", "==OUTPUT==", "==PLOTS==", "==END=="):
        assert marker in cmd
    # 上限钳制：不会有人拉 1000 个 cell 把 ssh 打爆
    assert "head -n 60" in cs._cells_command("/x", 1000)


def test_cells_from_output_parses_and_strips_header(pair):
    cs, _rc = pair
    out = "\n".join([
        "==CELL== r-2", "status: ok", "ms: 38900", "started: 2026-10-09 01:52:44",
        "finished: 2026-10-09 01:53:23", "readrds_calls: 1", "objects: 20",
        "==CODE==", "#MM-REQ v1 op=eval id=r-2", 'obj <- RunUMAP(obj, reduction = "harmony")',
        "==OUTPUT==", "UMAP done in 38.9s", "==WARNINGS==", "", "==ERROR==", "", "==PLOTS==",
        "/hw/s/plots/r-2_01.png\t7524",
        "==CELL== r-1", "status: error", "ms: 16300", "readrds_calls: 1", "objects: 5",
        "==CODE==", "#MM-REQ v1 op=eval id=r-1", 'obj <- readRDS("/hw/MuSC.rds")',
        "==OUTPUT==", "read ok", "==WARNINGS==", "some warning", "==ERROR==", "boom", "==PLOTS==",
        "==END==",
    ])
    cells = cs._cells_from_output(out, 10)
    assert [c["id"] for c in cells] == ["r-2", "r-1"]
    assert cells[0]["status"] == "ok" and cells[0]["ms"] == "38900"
    assert cells[0]["plots"][0]["bytes"] == "7524" and cells[0]["readrds_calls"] == "1"
    assert cells[1]["status"] == "error" and cells[1]["error"] == "boom"
    assert cells[1]["plots"] == []
    # 请求头注释（投递方写的 #MM-REQ）不该出现在展示的代码里
    assert all("#MM-REQ" not in c["code"] for c in cells)
    assert "RunUMAP" in cells[0]["code"] and "readRDS" in cells[1]["code"]


def test_action_cells_reverses_to_notebook_order(pair, monkeypatch):
    cs, rc = pair
    cs._registry_upsert({"id": "s-nb", "node": "node4", "dir": "/wd/sess/s-nb", "status": "active"})
    out = "\n".join([
        "==CELL== r-2", "status: ok", "ms: 39000", "readrds_calls: 1", "objects: 20",
        "==CODE==", 'obj <- RunUMAP(obj)', "==OUTPUT==", "umap ok",
        "==WARNINGS==", "", "==ERROR==", "", "==PLOTS==", "/wd/sess/s-nb/plots/r-2_01.png\t900",
        "==CELL== r-1", "status: ok", "ms: 16000", "readrds_calls: 1", "objects: 5",
        "==CODE==", 'obj <- readRDS("/hw/MuSC.rds")', "==OUTPUT==", "read ok",
        "==WARNINGS==", "", "==ERROR==", "", "==PLOTS==",
        "==END==",
    ])
    fake = _wire_status(cs, rc, monkeypatch, out)
    payload = json.loads(cs.action_cells({}, {"session_id": "s-nb", "limit": 4}))
    assert payload["status"] == "ok" and payload["session_id"] == "s-nb"
    assert [c["id"] for c in payload["cells"]] == ["r-1", "r-2"], "notebook 顺序应是旧的在上"
    assert payload["count"] == 2 and payload["cells"][1]["plots"][0]["path"].endswith("r-2_01.png")
    assert any("head -n 4" in c for c in fake.commands), "limit 没透传到远端命令"
    # 会话目录不在时给可操作报错（而不是空 notebook）
    fake2 = _wire_status(cs, rc, monkeypatch, "MM_NO_DIR")
    err = json.loads(cs.action_cells({}, {"session_id": "s-nb"}))
    assert err["status"] == "error" and "session_list" in err["error"]


def test_action_plot_returns_data_uri_and_guards(pair, monkeypatch):
    cs, rc = pair
    cs._registry_upsert({"id": "s-plot", "node": "node4", "dir": "/wd/sess/s-plot",
                         "status": "active"})
    b64 = "iVBORw0KGgoAAAANSUhEUg=="
    fake = _wire_status(cs, rc, monkeypatch, "MM_BYTES:1234\nMM_NAME:r-9_01.png\n" + b64)
    payload = json.loads(cs.action_plot({}, {"session_id": "s-plot", "path": "plots/r-9_01.png"}))
    assert payload["status"] == "ok"
    assert payload["mime"] == "image/png" and payload["b64"] == b64
    assert payload["data_uri_prefix"] == "data:image/png;base64,"
    cmd = fake.commands[0]
    assert 'case "$F" in "$D"/*)' in cmd, "缺少「只允许会话目录内」的闸门"
    assert "MM_TOOBIG" in cmd and "base64 -w0" in cmd
    assert "4000000" in cmd, "默认体积上限没进命令"


def test_action_plot_error_paths(pair, monkeypatch):
    cs, rc = pair
    cs._registry_upsert({"id": "s-plot2", "node": "node4", "dir": "/wd/sess/s-plot2",
                         "status": "active"})
    cases = [
        ("MM_OUTSIDE", "拒绝"),
        ("MM_MISSING", "不存在"),
        ("MM_BADTYPE", "只支持"),
        ("MM_TOOBIG:9999999", "太大"),
    ]
    for out, expect in cases:
        _wire_status(cs, rc, monkeypatch, out)
        payload = json.loads(cs.action_plot({}, {"session_id": "s-plot2", "path": "plots/x.png"}))
        assert payload["status"] == "error", out
        assert expect in (payload.get("error") or ""), (out, payload.get("error"))
    # 没给 path：直接告诉怎么用，不发命令
    fake = _wire_status(cs, rc, monkeypatch, "")
    payload = json.loads(cs.action_plot({}, {"session_id": "s-plot2"}))
    assert payload["status"] == "error" and "plots/" in payload["error"]
    assert fake.commands == []


# ------------------------------------------------------------------ daemon 抓图：本机真跑一遍 R
RSCRIPT = shutil.which("Rscript") or shutil.which("Rscript.exe")


@pytest.mark.integration
@pytest.mark.sessions
@pytest.mark.skipif(not RSCRIPT, reason="本机没有 Rscript，跳过 daemon 抓图实测")
def test_daemon_plot_capture_end_to_end(tmp_path):
    """真起一个 daemon（本机 Rscript），投两个请求：画图那个要落 PNG 且清单进结果。

    这是抓图链路的唯一真相来源：R 的默认设备是复用的，如果不在每个表达式后收尾，
    「画两张图」只会留下最后一张 —— 静态标记检查不出这个，必须真跑 R。
    """
    work = str(tmp_path / "sess")
    for d in ("queue", "run", "done", "ckpt", "out", "staging", "plots"):
        os.makedirs(os.path.join(work, d), exist_ok=True)
    log = open(os.path.join(work, "daemon.out.log"), "wb")
    proc = subprocess.Popen([RSCRIPT, DAEMON, "--dir", work], stdout=log,
                            stderr=subprocess.STDOUT, cwd=work)
    try:
        def state():
            try:
                txt = open(os.path.join(work, "state.txt"), encoding="utf-8", errors="replace").read()
            except OSError:
                return {}
            return dict(ln.split("=", 1) for ln in txt.splitlines() if "=" in ln)

        deadline = time.time() + 90
        while time.time() < deadline and state().get("status") not in ("idle", "busy"):
            time.sleep(0.3)
        assert state().get("pid"), "daemon 没起来（看 session.log）"

        def run_cell(rid, code, timeout=120):
            stage = os.path.join(work, "staging", rid + ".req.R")
            with open(stage, "w", encoding="utf-8", newline="\n") as f:
                f.write("#MM-REQ 1 op=eval id=%s\n" % rid + code + "\n")
            os.replace(stage, os.path.join(work, "queue", rid + ".req.R"))
            res = os.path.join(work, "done", rid + ".res.txt")
            end = time.time() + timeout
            while time.time() < end:
                if os.path.exists(res):
                    return open(res, encoding="utf-8", errors="replace").read()
                time.sleep(0.3)
            raise AssertionError("等结果超时：" + rid)

        t1 = run_cell("r-e2e-1", 'plot(1:10, main = "a")\nhist(rnorm(100))\ncat("two plots done\\n")')
        p1 = cs_parse_plots(t1)
        assert len(p1) == 2, "两个表达式应该落两张图（被覆盖 = 只剩 1 张）：%r" % (p1,)
        assert "two plots done" in t1
        t2 = run_cell("r-e2e-2", 'cat("no plot\\n")')
        assert cs_parse_plots(t2) == [], "第二个 cell 不该继承上一个 cell 的图"
        files = sorted(f for f in os.listdir(os.path.join(work, "plots")) if f.endswith(".png"))
        assert len(files) == 2, files
        for f in files:
            raw = open(os.path.join(work, "plots", f), "rb").read(8)
            assert raw == b"\x89PNG\r\n\x1a\n", "%s 不是合法 PNG" % f
            assert os.path.getsize(os.path.join(work, "plots", f)) > 1000
        assert state().get("plots_total") == "2"
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=15)
        except Exception:
            proc.kill()
        log.close()


def cs_parse_plots(res_text):
    """从结果文本里读 ---PLOTS--- 分段（测试自己的小解析器，别依赖被测代码）。"""
    out, grab = [], False
    for ln in res_text.splitlines():
        if ln.strip() == "---PLOTS---":
            grab = True
            continue
        if ln.strip().startswith("---") and grab:
            grab = False
        if grab and ln.strip():
            out.append(ln.split("\t")[0])
    return out