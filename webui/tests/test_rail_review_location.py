# -*- coding: utf-8 -*-
"""rail_review 按执行位置审查（本地 / 集群 / 云）—— 2026-10-09。

背景（用户实测事故）：rail_review(pre) 只查**本机** R 包清单，本地缺 RUVSeq 就把
**集群投递**硬拦了（"Missing packages: RUVSeq"），而 ssh23 的 R4.41 里其实装着。
本文件锁死修复后的口径：

  * 本地任务查本机包、集群任务查**集群节点**的包、云平台单独标 unverified；
  * location 显式传入才会硬拦；auto 推断出来的问题只报警告（推断错了不许拦人）；
  * 集群连不上 / 云平台 → **没法核实**（不报 missing，绝不据此拒跑）；
  * 审查结果里必须带 location / location_source / location_line（说清在哪审的）；
  * enforcement 在「审查位置 ≠ 执行位置」时软提醒重审，不硬拦。

全部离线：不碰真 SSH、不跑本机 Rscript、不读写生产缓存（monkeypatch 隔离）。
"""
import importlib
import importlib.util
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from memomics.bio_tools import env_check as ec  # noqa: E402
from memomics.bio_tools import rail_review as rr  # noqa: E402
from memomics.bio_tools import remote_cluster as rc  # noqa: E402
import enforcement as enf  # noqa: E402  (webui 目录由 tests/conftest.py 加入 sys.path)

_REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ==================== 公共 fixture / stub ====================

def _boom(*a, **kw):
    raise AssertionError("不该走到这里（本机 R/Python 检查不该被调用）")


@pytest.fixture
def no_local_probe(monkeypatch):
    """本机探测一律炸掉：证明 scope=cluster/cloud 时真的没碰本机。"""
    monkeypatch.setattr(ec, "_check_r_packages", _boom)
    monkeypatch.setattr(ec, "_check_python_packages", _boom)
    monkeypatch.setattr(ec, "_install_r_package", _boom)
    monkeypatch.setattr(ec, "_install_python_package", _boom)
    return True


def _rc_objects():
    """所有可能的 remote_cluster 模块对象。

    坑（2026-10-09 实测全量跑挂掉两条）：test_cluster_session.py 会把**自己 importlib 加载的**
    remote_cluster 实例塞进 sys.modules["memomics.bio_tools.remote_cluster"]，而 env_check 是
    **调用时**延迟 import 的 —— 于是轮到本文件时，env_check 拿到的是那具"真身"，只 patch
    本文件顶部 import 的那个对象会漏（单跑绿、全量红）。这里把所有副本都打上。
    """
    objs, seen = [], set()
    for obj in (rc, importlib.import_module("memomics.bio_tools.remote_cluster")):
        if id(obj) not in seen:
            seen.add(id(obj))
            objs.append(obj)
    return objs


@pytest.fixture
def patch_rc(monkeypatch):
    def install(attr, fake):
        for obj in _rc_objects():
            monkeypatch.setattr(obj, attr, fake)
    return install


def _cs_objects():
    from memomics.bio_tools import cluster_session as cs0
    objs, seen = [], set()
    for obj in (cs0, importlib.import_module("memomics.bio_tools.cluster_session")):
        if id(obj) not in seen:
            seen.add(id(obj))
            objs.append(obj)
    return objs


@pytest.fixture
def patch_cs(monkeypatch):
    """cluster_session 也可能被别的测试换成 importlib 实例，照样全打。"""
    def install(attr, fake):
        for obj in _cs_objects():
            monkeypatch.setattr(obj, attr, fake)
    return install


@pytest.fixture
def fake_local_r(monkeypatch):
    """本机 R 清单：RUVSeq 缺（复现用户场景）。"""
    status = {"RUVSeq": False, "Seurat": True, "CellChat": True}

    def fake(pkgs, *a, **kw):
        return {p: status.get(p, False) for p in pkgs}

    monkeypatch.setattr(ec, "_check_r_packages", fake)
    monkeypatch.setattr(ec, "_check_python_packages",
                        lambda pkgs, *a, **kw: {p: False for p in pkgs})
    monkeypatch.setattr(ec, "_install_r_package", lambda p, *a, **kw: False)
    monkeypatch.setattr(ec, "_install_python_package", lambda p, *a, **kw: False)
    monkeypatch.setattr(ec, "_load_env_cache", lambda: {"packages": {}})
    monkeypatch.setattr(ec, "_save_env_cache", lambda: None)
    return status


@pytest.fixture
def cluster_ok(patch_rc):
    """伪造集群包清单：ssh23/R4.41 上 RUVSeq 有、CellChat 没有。"""
    inv = {"status": "ok", "node": "ssh23", "env": "R4.41",
           "rscript": "/hwfssz3/.../envs/R4.41/bin/Rscript", "r_version": "R version 4.4.1",
           "count": 412, "checked_at": "2026-10-09 12:00:00", "cached": False,
           "installed": ["RUVSeq"], "missing": ["CellChat"], "unverified": []}

    def fake(**kw):
        want = list(kw.get("packages") or [])
        out = dict(inv)
        out["installed"] = [p for p in want if p in ("RUVSeq", "Seurat")]
        out["missing"] = [p for p in want if p not in ("RUVSeq", "Seurat")]
        return out

    patch_rc("r_packages_check", fake)
    return inv


@pytest.fixture
def cluster_down(patch_rc):
    def fake(**kw):
        return {"status": "error", "node": "ssh23", "env": "R4.41",
                "error": "连不上节点或探测 Rscript 失败：timed out",
                "hint": "先用 action='nodes' 看节点连通性", "packages": [],
                "installed": [], "missing": [], "unverified": [], "count": None}

    patch_rc("r_packages_check", fake)
    return fake


# ==================== env_check：按位置查包 ====================

class TestEnvCheckScope:
    def test_cluster_scope_uses_cluster_inventory(self, no_local_probe, cluster_ok):
        res = ec.check_env(["RUVSeq", "CellChat"], language="R", auto_install=False,
                           scope="cluster", node="ssh23", env="R4.41")
        assert res["scope"] == "cluster" and res["source"] == "cluster"
        assert list(res["installed"]) == ["RUVSeq"]
        assert list(res["missing"]) == ["CellChat"]
        assert res["node"] == "ssh23" and res["env"] == "R4.41"
        assert res["reachable"] is True and res["checked_at"]

    def test_cluster_scope_unreachable_is_unverified_not_missing(self, no_local_probe, cluster_down):
        res = ec.check_env(["RUVSeq"], language="R", auto_install=False,
                           scope="cluster", node="ssh23", env="R4.41")
        assert res["missing"] == {}, "连不上集群 ≠ 缺包（不许报 missing）"
        assert res["unverified"] == ["RUVSeq"]
        assert res["reachable"] is False and "timed out" in res["error"]

    def test_cluster_scope_never_auto_installs(self, monkeypatch, cluster_ok):
        calls = []
        monkeypatch.setattr(ec, "_install_r_package", lambda p, *a, **kw: calls.append(p) or True)
        res = ec.check_env(["RUVSeq"], language="R", auto_install=True,
                           scope="cluster", node="ssh23", env="R4.41")
        assert calls == [], "集群侧只读：不许装包"
        assert list(res["installed"]) == ["RUVSeq"]

    def test_cloud_scope_never_blocks(self, no_local_probe, patch_rc):
        patch_rc("r_packages_check", _boom)  # 云平台时不许去 ssh
        res = ec.check_env(["Seurat", "RUVSeq"], auto_install=True, scope="cloud")
        assert res["missing"] == {}
        assert sorted(res["unverified"]) == ["RUVSeq", "Seurat"]
        assert res["source"] == "cloud" and res["reachable"] is False

    def test_local_scope_regression(self, fake_local_r):
        res = ec.check_env(["RUVSeq", "Seurat"], auto_install=False, scope="local")
        assert list(res["missing"]) == ["RUVSeq"], "本地缺 RUVSeq 仍要如实报（本地任务的门禁不变）"
        assert res["scope"] == "local" and res["source"] == "local"
        assert res["unverified"] == []

    def test_local_scope_is_default(self, fake_local_r):
        res = ec.check_env(["RUVSeq"], auto_install=False)
        assert res["scope"] == "local" and list(res["missing"]) == ["RUVSeq"]

    def test_cluster_scope_python_names_unverified(self, no_local_probe, patch_rc):
        patch_rc("r_packages_check", lambda **kw: {
            "status": "ok", "node": "ssh23", "env": "R4.41", "count": 400,
            "installed": [], "missing": [], "unverified": ["scanpy"],
            "checked_at": "2026-10-09 12:00:00", "cached": False, "r_version": ""})
        res = ec.check_env(["scanpy"], language="R", auto_install=False,
                           scope="cluster", node="ssh23", env="R4.41")
        assert res["missing"] == {} and res["unverified"] == ["scanpy"]


# ==================== rail_review：位置感知的 pre / post ====================

class TestRailReviewLocation:
    def _pre(self, **kw):
        kw.setdefault("skill_name", "deg-analysis")
        return json.loads(rr.rail_review("pre", kw.pop("module_id", "deg"), **kw))

    def test_pre_local_still_blocks_locally(self, fake_local_r):
        r = self._pre(required_packages=["RUVSeq"], location="local")
        assert r["should_proceed"] is False
        assert any(i.startswith("Missing packages (本机)") for i in r["issues"])
        assert r["location"] == "local" and r["location_source"] == "explicit"
        assert "本机" in r["location_line"]

    def test_pre_cluster_missing_blocks_with_location(self, no_local_probe, cluster_ok):
        r = self._pre(required_packages=["CellChat"], location="cluster",
                      node="ssh23", env="R4.41")
        assert r["should_proceed"] is False
        assert any("Missing packages (集群 ssh23/R4.41): CellChat" == i for i in r["issues"])
        assert r["location"] == "cluster" and r["env_source"] == "cluster"
        assert r["node"] == "ssh23" and r["env"] == "R4.41"

    def test_pre_cluster_passes_even_when_local_missing(self, fake_local_r, cluster_ok):
        """用户场景：本地缺 RUVSeq，但集群有 → 不许拦集群任务。"""
        r = self._pre(required_packages=["RUVSeq"], location="cluster",
                      node="ssh23", env="R4.41")
        assert r["should_proceed"] is True, r
        assert r["issues"] == []
        assert any("✅ 包齐（集群 ssh23/R4.41）" in w for w in r["warnings"])

    def test_pre_cluster_unreachable_is_unverified_not_block(self, no_local_probe, cluster_down):
        r = self._pre(required_packages=["RUVSeq"], location="cluster",
                      node="ssh23", env="R4.41")
        assert r["should_proceed"] is True, "读不到集群清单 = 没法核实，不许拦"
        assert r["missing_packages"] == []
        assert any("没法核实" in w for w in r["warnings"])
        assert "没法核实" in r["location_line"]

    def test_pre_auto_inferred_cluster_only_warns(self, no_local_probe, cluster_ok, monkeypatch):
        monkeypatch.setattr(rr, "_cluster_context", lambda *a, **kw: {
            "node": "ssh23", "env": "R4.41", "session_id": "s-20261009-x", "status": "alive",
            "last_active": "2026-10-09 11:46:00", "age_hours": 0.2})
        r = self._pre(required_packages=["CellChat"])
        assert r["location"] == "cluster" and r["location_source"] == "inferred"
        assert r["should_proceed"] is True, "推断出来的缺包只报警告"
        assert r["issues"] == []
        assert any("自动推断" in w or "位置是" in w for w in r["warnings"])
        assert "自动推断" in r["location_line"]

    def test_pre_auto_without_context_is_local(self, fake_local_r, monkeypatch):
        monkeypatch.setattr(rr, "_cluster_context", lambda *a, **kw: None)
        r = self._pre(required_packages=["RUVSeq"])
        assert r["location"] == "local" and r["location_source"] == "inferred"
        assert r["should_proceed"] is True, "推断成本地时缺包也不硬拦（只警告）"
        assert any("位置是" in w for w in r["warnings"])

    def test_pre_cloud_never_ssh_and_never_blocks(self, no_local_probe, patch_rc):
        patch_rc("r_packages_check", _boom)
        r = self._pre(required_packages=["Seurat", "cellranger"], location="cloud")
        assert r["should_proceed"] is True
        assert r["missing_packages"] == []
        assert sorted(r["unverified"]) == ["Seurat", "cellranger"]
        assert r["location"] == "cloud" and "云平台" in r["location_line"]

    def test_pre_skill_gate_still_blocks(self, fake_local_r):
        r = self._pre(required_packages=["Seurat"], location="local", skill_name="")
        assert r["should_proceed"] is False
        assert any("SKILL_NOT_LOADED" in i for i in r["issues"])

    def test_pre_result_has_location_fields(self, no_local_probe, cluster_ok):
        r = self._pre(required_packages=["RUVSeq"], location="cluster",
                      node="ssh23", env="R4.41")
        for key in ("location", "location_source", "location_line", "location_basis",
                    "node", "env", "env_source", "checked_at", "packages_checked",
                    "should_proceed", "issues", "warnings", "missing_packages", "unverified"):
            assert key in r, key

    def test_post_review_stamps_location(self, tmp_path, monkeypatch):
        monkeypatch.setattr(rr, "_cluster_context", lambda *a, **kw: None)
        r = json.loads(rr.rail_review("post", "deg", output_dir="", code_executed="",
                                      location="cluster", node="ssh23", env="R4.41"))
        assert r["phase"] == "post" and r["location"] == "cluster"
        assert "集群 ssh23/R4.41" in r["location_line"]

    def test_post_review_cluster_zero_figure_message_hints_pull(self, tmp_path):
        d = tmp_path / "out"
        d.mkdir()
        (d / "x.txt").write_text("hi", encoding="utf-8")
        r = json.loads(rr.rail_review("post", "clustering", output_dir=str(d),
                                      code_executed="x <- 1\ntryCatch(1, error=function(e) 1)",
                                      location="cluster", node="ssh23", env="R4.41"))
        assert r["passed"] is False
        joined = " ".join(r["issues"])
        assert "pull" in joined and "集群执行" in joined, joined

    def test_post_review_local_zero_figure_message_unchanged(self, tmp_path):
        d = tmp_path / "out2"
        d.mkdir()
        (d / "x.txt").write_text("hi", encoding="utf-8")
        r = json.loads(rr.rail_review("post", "clustering", output_dir=str(d),
                                      code_executed="x <- 1\ntryCatch(1, error=function(e) 1)",
                                      location="local"))
        assert r["location"] == "local"
        assert any("未生成任何图片" in i and "pull" not in i for i in r["issues"])


# ==================== remote_cluster：r_packages 动作 ====================

class TestRemoteRPackages:
    def test_action_reports_installed_and_missing(self, cluster_ok):
        out = json.loads(rc._action_r_packages({}, {"action": "r_packages", "node": "ssh23",
                                                    "env": "R4.41",
                                                    "packages": ["RUVSeq", "CellChat"]}))
        assert out["status"] == "ok"
        assert out["installed"] == ["RUVSeq"] and out["missing"] == ["CellChat"]
        assert out["node"] == "ssh23" and out["env"] == "R4.41"
        assert out["count"] == 412

    def test_action_unreachable_returns_error_with_hint(self, cluster_down):
        out = json.loads(rc._action_r_packages({}, {"action": "r_packages", "node": "ssh23",
                                                    "packages": ["RUVSeq"]}))
        assert out["status"] == "error"
        assert "timed out" in out["error"]
        assert "nodes" in (out.get("hint") or ""), "报错必须给可操作的下一步"

    def test_python_names_not_reported_missing(self, patch_rc):
        patch_rc("r_inventory", lambda **kw: {
            "ok": True, "node": "ssh23", "env": "R4.41", "count": 400, "cached": False,
            "packages": ["Seurat"], "checked_at": "now", "r_version": "", "rscript": "x"})
        out = rc.r_packages_check(packages=["scanpy", "Seurat"], node="ssh23", env="R4.41")
        assert out["missing"] == [] and out["unverified"] == ["scanpy"]
        assert out["installed"] == ["Seurat"]

    def test_full_flag_includes_all_packages(self, patch_rc):
        patch_rc("r_inventory", lambda **kw: {
            "ok": True, "node": "ssh23", "env": "R4.41", "count": 3, "cached": True,
            "packages": ["A", "B", "C"], "checked_at": "now", "r_version": "", "rscript": "x"})
        out = rc.r_packages_check(packages=["A"], full=True)
        assert out["packages"] == ["A", "B", "C"]

    def test_r_packages_registered_in_action_table_and_schema(self):
        assert "r_packages" in rc._ACTIONS
        enum = rc.SCHEMA["parameters"]["properties"]["action"]["enum"]
        assert "r_packages" in enum
        assert "packages" in rc.SCHEMA["parameters"]["properties"]

    def test_server_whitelist_has_r_packages(self):
        p = os.path.join(_REPO, "webui", "server.py")
        with open(p, encoding="utf-8") as f:
            text = f.read()
        assert '"r_packages"' in text.split("_CLUSTER_ACTIONS = ", 1)[1].split("\n", 1)[0]


class TestInventoryCache:
    """r_inventory：一次 ssh 读全量清单 → 缓存命中不再连（离线假连接）。"""

    def _fake_conn(self):
        class C:
            def __init__(self):
                self.calls = 0

            def execute(self, cmd, **kw):
                self.calls += 1
                assert "installed.packages()" in cmd
                return {"output": "#MM-PKGS v1\nSeurat\nRUVSeq\nedgeR\n", "exit_code": 0}

        return C()

    def test_inventory_reads_and_caches(self, monkeypatch, tmp_path, patch_cs):
        conn = self._fake_conn()
        monkeypatch.setattr(rc, "_pkgs_cache_dir", lambda: str(tmp_path / "pkgs"))
        monkeypatch.setattr(rc, "_select_node", lambda cfg, node: ({"host": "h", "_name": "ssh23"},
                                                                   "ssh23", None))
        monkeypatch.setattr(rc, "_get_conn", lambda node_cfg, *a, **kw: conn)
        monkeypatch.setattr(rc, "_load_remote_config", lambda: {"session": {"env": "R4.41"}})

        patch_cs("_session_cfg", lambda cfg, node=None: {"env": "R4.41"})
        patch_cs("_probe_rscript",
                 lambda c, sess, env, explicit="": {"ok": True, "rscript": "/opt/R4.41/bin/Rscript",
                                                    "version": "R version 4.4.1"})
        patch_cs("_exec_full", lambda c, cmd, timeout=120: c.execute(cmd))

        first = rc.r_inventory(node="ssh23", env="R4.41")
        assert first["ok"] and first["cached"] is False
        assert first["packages"] == ["RUVSeq", "Seurat", "edgeR"] or first["packages"] == sorted(first["packages"])
        assert set(first["packages"]) == {"Seurat", "RUVSeq", "edgeR"}
        assert first["count"] == 3 and first["r_version"].startswith("R version")

        calls_before = conn.calls
        second = rc.r_inventory(node="ssh23", env="R4.41")
        assert second["ok"] and second["cached"] is True
        assert conn.calls == calls_before, "缓存命中不该再连节点"
        assert second["packages"] == first["packages"]

        third = rc.r_inventory(node="ssh23", env="R4.41", force=True)
        assert third["cached"] is False and conn.calls == calls_before + 1

    def test_inventory_reports_bad_output(self, monkeypatch, tmp_path, patch_cs):
        monkeypatch.setattr(rc, "_pkgs_cache_dir", lambda: str(tmp_path / "pkgs2"))
        monkeypatch.setattr(rc, "_select_node", lambda cfg, node: ({"host": "h", "_name": "ssh23"},
                                                                   "ssh23", None))
        monkeypatch.setattr(rc, "_get_conn", lambda node_cfg, *a, **kw: object())
        monkeypatch.setattr(rc, "_load_remote_config", lambda: {})
        patch_cs("_session_cfg", lambda cfg, node=None: {})
        patch_cs("_probe_rscript",
                 lambda c, sess, env, explicit="": {"ok": True, "rscript": "/x/Rscript"})
        patch_cs("_exec_full",
                 lambda c, cmd, timeout=120: {"output": "bash: /x/Rscript: No such file"})
        inv = rc.r_inventory(node="ssh23", env="R4.41", force=True)
        assert inv["ok"] is False and "读取失败" in inv["error"]


# ==================== enforcement：位置对不上 → 软提醒 ====================

class TestEnforcementLocationHint:
    def _mk(self, tmp_path):
        emitted = []
        cbs = enf.create_enforcement_callbacks(
            {"id": "loc_test", "results_dir": str(tmp_path)},
            lambda s, m: emitted.append(m))
        es = enf.get_enforcement("loc_test")
        es.analysis_level = "analysis"
        return cbs, es, emitted

    def _review_pre(self, cbs, location, node=""):
        cbs["tool_start_callback"]("r1", "rail_review", {"phase": "pre"})
        payload = json.dumps({"phase": "pre", "should_proceed": True, "location": location,
                              "node": node, "location_line": "📍 审查位置：%s" % location})
        cbs["tool_complete_callback"]("r1", "rail_review", {"phase": "pre"}, payload)

    def _msgs(self, emitted, needle):
        return [m for m in emitted if needle in str(m.get("message") or "")]

    def test_state_records_pre_location(self, tmp_path):
        cbs, es, emitted = self._mk(tmp_path)
        self._review_pre(cbs, "cluster", node="ssh23")
        assert es.rail_pre_location == "cluster"
        assert es.rail_pre_line.startswith("📍")
        assert es.to_dict()["rail_pre_location"] == "cluster"

    def test_remote_exec_after_local_pre_warns_not_blocks(self, tmp_path, monkeypatch):
        cbs, es, emitted = self._mk(tmp_path)
        self._review_pre(cbs, "local")
        ret = cbs["tool_start_callback"]("c2", "remote_cluster",
                                         {"action": "submit", "node": "ssh23", "script_path": "x.sh"})
        assert not (isinstance(ret, dict) and ret.get("blocked")), "位置对不上只提醒，不拦"
        hit = self._msgs(emitted, "集群**执行")
        assert hit, [m.get("message") for m in emitted]
        assert "location='cluster'" in hit[-1]["message"]

    def test_local_exec_after_cluster_pre_warns(self, tmp_path):
        cbs, es, emitted = self._mk(tmp_path)
        self._review_pre(cbs, "cluster", node="ssh23")
        cbs["tool_start_callback"]("c3", "terminal", {"command": "Rscript -e '1+1'"})
        hit = self._msgs(emitted, "但这次在**本机**跑")
        assert hit, [m.get("message") for m in emitted]

    def test_matching_location_no_hint(self, tmp_path):
        cbs, es, emitted = self._mk(tmp_path)
        self._review_pre(cbs, "cluster", node="ssh23")
        cbs["tool_start_callback"]("c4", "remote_cluster", {"action": "submit", "node": "ssh23"})
        assert not self._msgs(emitted, "审查位置"), [m.get("message") for m in emitted]

    def test_no_pre_review_no_hint(self, tmp_path):
        cbs, es, emitted = self._mk(tmp_path)
        cbs["tool_start_callback"]("c5", "remote_cluster", {"action": "submit", "node": "ssh23"})
        assert not self._msgs(emitted, "审查位置")