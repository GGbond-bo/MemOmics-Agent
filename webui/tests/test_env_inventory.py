# -*- coding: utf-8 -*-
"""环境管理（env_inventory）测试：缓存语义 + 集群聚合 + 渲染 + 工具注册 + 前端接线

设计约束（和实现一致）：
- HTTP 接口只读缓存、绝不探测 —— 这里用"探测就报错"的桩来钉死这条不变量；
- 本机 1 小时 / 集群 10 分钟 的 TTL 语义、pending 语义、force 语义都要能被前端依赖；
- 集群聚合从 remote_cluster 的 nodes/check 输出来（真 SSH 在单测里不可用 → 喂 canned JSON）；
- 缓存目录一律指到 tmp_path 的 hermes_home，绝不碰真实缓存；
- 前端断言是静态文本检查（index.html 无构建步骤，直接读文件）。
"""
import asyncio
import json
import os
import re as _re
import sys

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from memomics.bio_tools import env_inventory as ei  # noqa: E402

pytestmark = pytest.mark.unit

WEBUI = os.path.join(_ROOT, "webui")
INDEX = os.path.join(WEBUI, "index.html")


@pytest.fixture()
def home(tmp_path, monkeypatch):
    """hermes_home -> tmp（缓存彻底隔离，不碰真实缓存、不触发探测）。"""
    h = tmp_path / "hermes_home"
    h.mkdir()
    monkeypatch.setattr(ei, "_hermes_home", lambda: str(h))
    monkeypatch.setattr(ei, "_CACHE_MEM", {"data": None, "mtime": None})
    return str(h)


def _boom(*a, **k):
    raise AssertionError("这条路径不应该真探测")


def _canned_local():
    return {
        "scanned_at": "2026-09-22 10:00:00",
        "duration_s": 4.2,
        "pending": False,
        "environment_json": "E:/MemOmics-Agent/environment.json",
        "hermes_home": "E:/MemOmics-Agent/hermes_home",
        "platform": "Windows 11",
        "system": {
            "hostname": "BOX", "os": "Windows", "os_release": "11", "machine": "AMD64",
            "cpu_logical": 20, "cpu_model": "Ryzen 9",
            "ram": {"total_gb": 55.6, "free_gb": 18.8, "source": "psutil"},
            "gpu": {"ok": True, "gpus": [{"name": "RTX 5070 Ti", "vram_mb": 16303, "driver": "610.62"}]},
            "disks": [{"path": "E:", "free_gb": 303.5, "total_gb": 931.5}],
            "wsl": {"available": True, "distros": [{"name": "Ubuntu", "state": "Running", "version": "2"}]},
        },
        "python": {
            "default": "E:/MemOmics-Agent/.venv/Scripts/python.exe",
            "candidates": [
                {"label": "memomics_venv", "ok": True, "declared": True,
                 "path": "E:/MemOmics-Agent/.venv/Scripts/python.exe", "version": "3.12.10",
                 "packages": {"scanpy": "1.11.0", "anndata": "0.11.3"}, "note": ""},
                {"label": "python312", "ok": True, "declared": True,
                 "path": "C:/Python312/python.exe", "version": "3.12.10",
                 "packages": {}, "note": ""},
            ],
            "shared_libs": [{"path": "D:/Python/site-packages", "exists": False, "source": "environment.json"}],
            "declared_shared": ["D:/Python/site-packages"],
            "declared_shared_mounted": False,
        },
        "r": {
            "default": "C:/Program Files/R/R-4.5.3/bin/x64/Rscript.exe",
            "installs": [
                {"name": "R-4.5.3", "ok": True, "version": "4.5.3", "probed": "full",
                 "path": "C:/Program Files/R/R-4.5.3/bin/x64/Rscript.exe", "pkg_count": 739,
                 "missing_key": ["DESeq2", "edgeR"],
                 "cross_version_pkgs": {"ComplexHeatmap": "C:/Users/x/R/R-4.6.1-library"},
                 "cross_version_libs": ["C:/Users/x/R/R-4.6.1-library"],
                 "lib_paths": ["C:/Users/x/R/R-4.5.3-library"], "libs_injected": 5},
                {"name": "R-4.6.1", "ok": True, "version": "4.6.1", "probed": "light",
                 "path": "C:/Program Files/R/R-4.6.1/bin/x64/Rscript.exe", "note": "只探到版本"},
            ],
        },
        "cli_tools": {
            "items": [
                {"name": "conda", "ok": True, "declared": True, "path": "E:/miniconda3/conda.EXE",
                 "version": "26.3.2", "note": ""},
                {"name": "samtools", "ok": False, "declared": True, "path": "", "version": "",
                 "note": "登记未找到"},
            ],
            "available": ["conda"], "missing": ["samtools"], "declared_unavailable": [],
        },
        "conda": {"available": True, "path": "E:/miniconda3/conda.EXE", "version": "26.3.2",
                  "envs": [{"name": "base", "path": "E:/miniconda3", "python": "3.12.9"}],
                  "broken": False, "canonical_note": "已损坏（zstandard.backend_c 缺失）"},
        "capabilities": {
            "execute_python": {"uses": "E:/MemOmics-Agent/.venv/Scripts/python.exe",
                               "version": "3.12.10", "missing_key": ["pysam", "harmonypy"]},
            "execute_r": {"uses": "C:/Program Files/R/R-4.5.3/bin/x64/Rscript.exe",
                          "version": "4.5.3", "libs": ["C:/Users/x/R/R-4.5.3-library"],
                          "missing_key": ["DESeq2"]},
        },
        "known_issues": {"cellbender_cuda": "需要 CUDA 版 torch"},
        "canonical_notes": {"R_deprecated": "4.6.1 失效，勿再使用"},
        "warnings": ["主力 R 缺 2 个关键包：DESeq2、edgeR"],
    }


class _FakeRC:
    """假 remote_cluster 模块：喂 canned nodes/check 输出，并记录被问了什么。"""

    def __init__(self, nodes_payload, checks=None):
        self.nodes_payload = nodes_payload
        self.checks = checks or {}
        self.calls = []

    def remote_cluster_handler(self, args):
        self.calls.append(args)
        if args.get("action") == "nodes":
            return json.dumps(self.nodes_payload, ensure_ascii=False)
        return json.dumps(self.checks.get(args.get("node"), {}), ensure_ascii=False)


def _node(name, reachable=True, nproc=64, load1=0.5, **extra):
    base = {"name": name, "host": "10.0.0.1", "user": "bio", "port": 22, "role": "compute",
            "reachable": reachable, "nproc": nproc, "load1": load1,
            "load_per_cpu": (round(load1 / nproc, 4) if (nproc and load1 is not None) else None),
            "idle_guess": bool(reachable and load1 is not None and load1 < 1),
            "workdir": "/home/bio/work", "workdir_ok": True, "scheduler": "slurm", "error": ""}
    base.update(extra)
    return base


def _configured(**extra):
    state = {"configured": True, "enabled": True, "config_path": "X:/hermes_home/config.yaml",
             "scheduler": "slurm", "node_policy": "ask", "default_node": "ssh3",
             "nodes": ["ssh3"], "error": ""}
    state.update(extra)
    return state


def _unconfigured(path="X:/hermes_home/config.yaml"):
    return {"configured": False, "enabled": False, "config_path": path, "scheduler": "auto",
            "node_policy": "ask", "default_node": "", "nodes": [], "error": ""}


# ---------------------------------------------------------------------------
# 缓存语义（前端轮询依赖它：pending / cached / age_s / TTL）
# ---------------------------------------------------------------------------
def test_cache_path_lives_in_hermes_home(home):
    assert ei._cache_path() == os.path.join(home, "env_inventory.json")


def test_cached_local_pending_when_no_cache(home):
    got = ei.cached_local()
    assert got["pending"] is True
    assert got["scanned_at"] == "" and got["age_s"] is None
    assert "env_inventory" in got["hint"] or "扫描" in got["hint"]


def test_cached_local_serves_fresh_cache_without_probing(home, monkeypatch):
    monkeypatch.setattr(ei, "scan_local", _boom)
    ei._write_cache(local=_canned_local(), local_at=ei._now())
    got = ei.cached_local()
    assert got["pending"] is False and got["cached"] is True
    assert isinstance(got["age_s"], (int, float)) and got["age_s"] < 60
    assert got["python"]["default"].endswith("python.exe")


def test_cached_local_stale_beyond_ttl_still_serves_data(home):
    """2026-09-23 改：过期不等于没扫过。

    旧行为是过期就回 pending，面板退回「还没扫过，正在后台扫描」，
    上次扫到的清单（R 版本 / 缺包 / 警告）全部看不见 —— 用户反馈"环境清单没保存住"。
    新行为：有数据就先给数据（stale + age_s），同时 needs_refresh 让后台重扫。
    """
    ei._write_cache(local=_canned_local(), local_at=ei._now() - (ei._LOCAL_TTL + 60))
    got = ei.cached_local()
    assert got.get("pending") is not True, "过期不该丢成 pending"
    assert got["stale"] is True and got["needs_refresh"] is True
    assert got["cached"] is True
    # 关键：内容必须还在，用户还能看到上次扫出来的东西
    assert got["python"]["default"].endswith("python.exe")
    assert got["warnings"] == _canned_local()["warnings"]
    assert got["age_s"] > ei._LOCAL_TTL


def test_cached_local_empty_cache_is_still_pending(home):
    """真没扫过（没有数据）时仍然是 pending —— 别把这条也就此改掉。"""
    assert ei.cached_local()["pending"] is True


# ---------------------------------------------------------------------------
# verify：便宜地"再确认一遍"（指纹没变就不重扫）
# ---------------------------------------------------------------------------
def test_fingerprint_is_cheap_and_never_probes(home, monkeypatch):
    """指纹必须是纯 stat：不跑解释器、不探测（毫秒级）。"""
    monkeypatch.setattr(ei, "_probe_python", _boom)
    monkeypatch.setattr(ei, "_probe_r", _boom)
    monkeypatch.setattr(ei, "_probe_conda", _boom)
    monkeypatch.setattr(ei, "_probe_cli_tools", _boom)
    monkeypatch.setattr(ei, "_run", _boom)
    fp = ei._fingerprint()          # 不许探测
    assert set(fp.keys()) == {"environment_json", "python", "r", "conda"}


def test_verify_rescans_first_time_then_reuses(home, monkeypatch):
    """首次确认要真扫一次；之后指纹没变 → 一次探测都不做。"""
    calls = []
    monkeypatch.setattr(ei, "scan_local",
                        lambda force=False: calls.append(force) or {"scanned_at": "t", "platform": "nt"})
    first = ei.verify()
    assert first["changed"] is True and first["rescanned"] is True
    assert calls == [True]
    calls.clear()
    second = ei.verify()
    assert second["changed"] is False and second["rescanned"] is False
    assert calls == [], "没变就不该重扫"


def test_verify_rescans_when_site_packages_changes(home, monkeypatch):
    """装了个包（site-packages mtime 变）→ 必须被指纹抓到并重扫。"""
    calls = []
    monkeypatch.setattr(ei, "scan_local",
                        lambda force=False: calls.append(force) or {"scanned_at": "t", "platform": "nt"})
    ei.verify()
    calls.clear()
    fp = ei._read_cache().get("fingerprint")
    fp["python"]["site_packages"] = [99999.0, 1]
    ei._write_cache(fingerprint=fp)
    got = ei.verify()
    assert got["changed"] is True and got["rescanned"] is True
    assert any("python" in r for r in got["reasons"])
    assert calls == [True]


def test_verify_survives_scan_failure(home, monkeypatch):
    """重扫失败不能把确认本身弄崩，也不能丢掉旧清单。"""
    ei._write_cache(local=_canned_local(), local_at=ei._now(),
                    fingerprint={"environment_json": "DIFFERENT", "python": None, "r": None, "conda": None})
    monkeypatch.setattr(ei, "scan_local", _boom)
    got = ei.verify()
    assert got["ok"] is True
    assert got["rescanned"] is False
    assert any("重扫失败" in r for r in got["reasons"])
    assert ei.cached_local()["python"]["default"].endswith("python.exe"), "旧清单必须还在"


def test_verify_force_rescans_even_when_unchanged(home, monkeypatch):
    calls = []
    monkeypatch.setattr(ei, "scan_local",
                        lambda force=False: calls.append(force) or {"scanned_at": "t", "platform": "nt"})
    ei.verify()
    calls.clear()
    got = ei.verify(force_rescan=True)
    assert got["rescanned"] is True and calls == [True]


def test_write_cache_merges_and_stamps_version(home):
    ei._write_cache(local=_canned_local(), local_at=ei._now())
    ei._write_cache(cluster={"configured": True}, cluster_at=ei._now())
    data = ei._read_cache(reload=True)
    assert data["version"] == ei._CACHE_VERSION
    assert data["local"]["system"]["hostname"] == "BOX"
    assert data["cluster"]["configured"] is True


# ---------------------------------------------------------------------------
# 集群：配置态判断必须现算（否则用户刚填完配置面板还显示"未配置"）
# ---------------------------------------------------------------------------
def test_cluster_unconfigured_recomputes_even_when_cache_is_fresh(home, monkeypatch):
    ei._write_cache(cluster={"configured": False, "config_path": "OLD/PATH",
                             "hint": "旧的"}, cluster_at=ei._now())
    monkeypatch.setattr(ei, "cluster_configured", lambda: _unconfigured("NEW/PATH"))
    got = ei.cached_cluster()
    assert got["configured"] is False
    assert got["config_path"] == "NEW/PATH"
    assert got["cached"] is False
    assert "NEW/PATH" in got["hint"] and "enabled: true" in got["hint"]


def test_cluster_configured_fresh_uses_cache(home, monkeypatch):
    monkeypatch.setattr(ei, "scan_cluster", _boom)
    ei._write_cache(cluster={"configured": True, "config_path": "X", "nodes": [{"name": "ssh3"}]},
                    cluster_at=ei._now())
    got = ei.cached_cluster()
    assert got["cached"] is True and got["nodes"][0]["name"] == "ssh3"
    assert isinstance(got["age_s"], (int, float))


def test_cluster_configured_stale_returns_pending_when_no_data(home, monkeypatch):
    """已配置、缓存过期、且**没有任何旧数据** → 才回 pending。"""
    monkeypatch.setattr(ei, "scan_cluster", _boom)
    monkeypatch.setattr(ei, "cluster_configured", lambda: _configured())
    got = ei.cached_cluster()
    assert got["pending"] is True and got["configured"] is True
    assert got["config_path"] == "X:/hermes_home/config.yaml"
    assert got["nodes_configured"] == ["ssh3"]


def test_cluster_configured_stale_serves_last_nodes(home, monkeypatch):
    """2026-09-23：过期但上次探到的节点清单要留着（stale），别丢成 pending。"""
    monkeypatch.setattr(ei, "scan_cluster", _boom)
    monkeypatch.setattr(ei, "cluster_configured", lambda: _configured())
    ei._write_cache(cluster={"configured": True, "nodes": [{"name": "ssh3", "reachable": True}],
                             "resources": {"total_cores": 64}},
                    cluster_at=ei._now() - (ei._CLUSTER_TTL + 60))
    got = ei.cached_cluster()
    assert got.get("pending") is not True
    assert got["stale"] is True and got["needs_refresh"] is True
    # 上次探到的节点与资源必须还在
    assert got["nodes"][0]["name"] == "ssh3"
    assert got["resources"]["total_cores"] == 64
    # 配置态仍然以现算为准（这条不变量不能被污染）
    assert got["config_path"] == "X:/hermes_home/config.yaml"


def test_invalidate_keeps_data_and_marks_force(home):
    """2026-09-23：invalidate 不再删数据。

    以前 invalidate 直接置 None —— 点「🔄 重新扫描」先把旧清单删掉，
    这次万一扫失败（R 全量探测超时 / 集群 SSH 卡住），旧清单就永久没了。
    """
    ei._write_cache(local=_canned_local(), local_at=ei._now())
    ei.invalidate("all")
    data = ei._read_cache(reload=True)
    assert data["local"]["python"]["default"].endswith("python.exe"), "数据不该被删"
    assert data["local_force"] is True and data["cluster_force"] is True
    assert data["local_at"] == 0, "时间戳要清零，这样才会真重扫"
    # 过期视图仍能拿到内容
    got = ei.cached_local()
    assert got["stale"] is True and got["python"]["default"].endswith("python.exe")


def test_scan_local_clears_force_flag(home, monkeypatch):
    """扫成功后必须清 force，否则 _fresh 永远为假 → 每轮都重扫。"""
    ei.invalidate("local")
    monkeypatch.setattr(ei, "_probe_system", lambda: {})
    monkeypatch.setattr(ei, "_probe_python", lambda: {})
    monkeypatch.setattr(ei, "_probe_r", lambda: {})
    monkeypatch.setattr(ei, "_probe_cli_tools", lambda: {})
    monkeypatch.setattr(ei, "_probe_conda", lambda: {})
    ei.scan_local(force=True)
    assert ei._read_cache(reload=True).get("local_force") is False


def test_scan_cluster_unconfigured_hint_and_cache(home, monkeypatch):
    monkeypatch.setattr(ei, "cluster_configured", lambda: _unconfigured())
    monkeypatch.setattr(ei, "_cluster_module", _boom)
    got = ei.scan_cluster(force=True)
    assert got["configured"] is False and got["nodes"] == []
    assert "config.yaml" in got["hint"]
    assert ei._read_cache(reload=True)["cluster"]["configured"] is False


def test_scan_cluster_aggregates_nodes_and_resources(home, monkeypatch):
    nodes_payload = {
        "status": "ok", "summary": "1/2 可达",
        "nodes": [_node("ssh3", nproc=64), _node("ssh5", reachable=False, nproc=None,
                                                 error="connection timed out")],
        "reachable": ["ssh3"], "idle_now": ["ssh3"],
    }
    checks = {"ssh3": {"status": "ok", "scheduler": "slurm", "workdir": "/home/bio/work",
                       "remote_home": "/home/bio",
                       "bins": {"Rscript": "/usr/bin/Rscript", "python3": "/usr/bin/python3"},
                       "output": "== versions ==\npython 3.11.2\n"}}
    fake = _FakeRC(nodes_payload, checks)
    monkeypatch.setattr(ei, "cluster_configured", lambda: _configured(nodes=["ssh3", "ssh5"]))
    monkeypatch.setattr(ei, "_cluster_module", lambda: fake)
    got = ei.scan_cluster(force=True)
    res = got["resources"]
    assert got["configured"] is True and got["cached"] is False
    assert res["total_cores"] == 64
    assert res["reachable_nodes"] == 1 and res["configured_nodes"] == 2
    assert res["idle_now"] == ["ssh3"] and res["schedulers"] == ["slurm"]
    assert res["workdirs"] == ["/home/bio/work"]
    assert got["per_node"]["ssh3"]["bins"]["Rscript"] == "/usr/bin/Rscript"
    assert isinstance(got["per_node"]["ssh3"]["versions"], dict)
    assert any("ssh5" in w and "连不上" in w for w in got["warnings"])
    assert [c["action"] for c in fake.calls] == ["nodes", "check"]
    assert ei._read_cache(reload=True)["cluster"]["resources"]["total_cores"] == 64


def test_scan_cluster_skips_extra_nodes_beyond_limit(home, monkeypatch):
    names = ["n%d" % i for i in range(ei._MAX_CLUSTER_NODE_CHECKS + 2)]
    nodes_payload = {"status": "ok", "nodes": [_node(n) for n in names],
                     "reachable": names, "idle_now": names, "summary": "all"}
    fake = _FakeRC(nodes_payload, {n: {"status": "ok", "bins": {}, "output": ""} for n in names})
    monkeypatch.setattr(ei, "cluster_configured", lambda: _configured(nodes=names))
    monkeypatch.setattr(ei, "_cluster_module", lambda: fake)
    got = ei.scan_cluster(force=True)
    checked = [c for c in fake.calls if c.get("action") == "check"]
    assert len(checked) == ei._MAX_CLUSTER_NODE_CHECKS
    skipped = [v for v in got["per_node"].values() if v.get("skipped")]
    assert len(skipped) == 2


def test_scan_cluster_nodes_error_is_graceful(home, monkeypatch):
    fake = _FakeRC({"status": "error", "error": "ssh 密钥不存在"})
    monkeypatch.setattr(ei, "cluster_configured", lambda: _configured())
    monkeypatch.setattr(ei, "_cluster_module", lambda: fake)
    got = ei.scan_cluster(force=True)
    assert "ssh 密钥不存在" in got["error"]
    assert got["hint"] and got["nodes"] == []


# ---------------------------------------------------------------------------
# 渲染：人看的 markdown + 给 agent 的紧凑卡片
# ---------------------------------------------------------------------------
def test_render_markdown_pending_notice(home):
    text = ei.render_markdown(cache_only=True)
    assert text.startswith("# 环境报告")
    assert "还没生成" in text


def test_render_markdown_full_report(home):
    ei._write_cache(local=_canned_local(), local_at=ei._now())
    ei._write_cache(cluster={"configured": False, "hint": "集群未启用：在 X 写 enabled: true"},
                    cluster_at=ei._now())
    text = ei.render_markdown(cache_only=True)
    assert "# 环境报告（MemOmics 环境管理）" in text
    assert "- 缓存文件：" in text and "env_inventory.json" in text
    for section in ("## 本机资源", "## Python", "## R", "## 生信 CLI 工具", "## conda"):
        assert section in text
    assert "R-4.5.3" in text and "ComplexHeatmap" in text
    assert "## 给 Agent 的环境卡片" in text
    assert "```" not in text  # 报告里只用 ~~~ 围栏，别把 markdown 代码块套死


def test_agent_digest_pending_points_at_tool(home):
    text = ei.agent_digest()
    assert "env_inventory" in text


def test_agent_digest_is_compact_and_mentions_capabilities(home):
    ei._write_cache(local=_canned_local(), local_at=ei._now())
    text = ei.agent_digest()
    assert text.startswith("## 本机环境")
    assert "3.12.10" in text and "4.5.3" in text
    assert "env_inventory" in text or "复用" in text
    assert len(text) < 2600


def test_capabilities_flags_are_booleans(home):
    local = _canned_local()
    caps = local["capabilities"]
    assert isinstance(caps["execute_python"]["missing_key"], list)
    assert isinstance(caps["execute_r"]["missing_key"], list)


# ---------------------------------------------------------------------------
# 工具入口（agent 侧）：action 分发 + 失败兜底
# ---------------------------------------------------------------------------
def test_handler_actions_dispatch(home, monkeypatch):
    monkeypatch.setattr(ei, "scan_local", lambda force=False: {"scanned_at": "t", "fake": "local"})
    monkeypatch.setattr(ei, "scan_cluster", lambda force=False, node="": {"fake": "cluster", "node": node})
    monkeypatch.setattr(ei, "build_report", lambda force=False, **k: {"fake": "report", "force": force})
    monkeypatch.setattr(ei, "render_markdown", lambda *a, **k: "# md")
    monkeypatch.setattr(ei, "invalidate", lambda scope="all": {"cleared": scope})

    local = json.loads(ei.env_inventory_handler("local"))
    assert local["action"] == "local" and local["local"]["fake"] == "local"

    cluster = json.loads(ei.env_inventory_handler("cluster", "ssh3"))
    assert cluster["cluster"]["node"] == "ssh3"

    refresh = json.loads(ei.env_inventory_handler("refresh"))
    assert refresh["action"] == "refresh" and refresh["force"] is True

    md = json.loads(ei.env_inventory_handler("markdown"))
    assert md["markdown"] == "# md"

    default = json.loads(ei.env_inventory_handler(""))
    assert default["action"] == "overview" and default["fake"] == "report"

    upper = json.loads(ei.env_inventory_handler("LOCAL"))
    assert upper["action"] == "local"


def test_handler_never_raises(home, monkeypatch):
    monkeypatch.setattr(ei, "scan_local", _boom)
    got = json.loads(ei.env_inventory_handler("local"))
    assert got["ok"] is False and got["status"] == "error"
    assert "AssertionError" in got["error"]


def test_schema_shape():
    assert ei.SCHEMA["name"] == "env_inventory"
    enum = ei.SCHEMA["parameters"]["properties"]["action"]["enum"]
    assert set(enum) == {"overview", "local", "cluster", "refresh", "markdown", "verify"}
    assert "🧩" in ei.SCHEMA["description"] or "环境" in ei.SCHEMA["description"]
    assert ei.SCHEMA["parameters"]["properties"]["node"]["default"] == ""


def test_registered_into_memomics_toolset():
    from tools.registry import registry
    tools = getattr(registry, "tools", None) or getattr(registry, "_tools", None)
    assert isinstance(tools, dict)
    entry = tools.get("env_inventory")
    assert entry is not None, "env_inventory 没注册进 registry"
    toolset = getattr(entry, "toolset", None) or (entry.get("toolset") if isinstance(entry, dict) else None)
    assert toolset == "memomics"


def test_toolset_static_list_contains_env_inventory():
    path = os.path.join(_ROOT, "hermes-agent", "toolsets.py")
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    assert '"env_inventory"' in text


def test_bio_tools_package_imports_env_inventory():
    path = os.path.join(_ROOT, "memomics", "bio_tools", "__init__.py")
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    assert "env_inventory" in text


# ---------------------------------------------------------------------------
# WebUI 接口：只读缓存、绝不探测、report.md 可下载
# ---------------------------------------------------------------------------
def _prime_cache_configured(home):
    ei._write_cache(local=_canned_local(), local_at=ei._now())
    ei._write_cache(cluster={"configured": True, "enabled": True, "config_path": "X:/config.yaml",
                             "nodes": [], "per_node": {}, "resources": {"total_cores": 64},
                             "warnings": []}, cluster_at=ei._now())


def test_api_inventory_is_cache_only(home, monkeypatch):
    import server
    _prime_cache_configured(home)
    monkeypatch.setattr(ei, "scan_local", _boom)
    monkeypatch.setattr(ei, "scan_cluster", _boom)
    monkeypatch.setattr(server, "_ENV_INV_STATE",
                        {"status": "idle", "scope": "", "started_at": 0, "finished_at": 0, "error": ""})
    payload = asyncio.run(server.env_inventory_api(refresh=0, cluster=1, scope=""))
    assert payload["ok"] is True and payload["pending"] is False
    assert payload["cache_path"] == os.path.join(home, "env_inventory.json")
    assert payload["local"]["python"]["default"].endswith("python.exe")
    assert payload["cluster"]["resources"]["total_cores"] == 64
    assert payload["warnings"]
    assert payload["agent_digest"].startswith("## 本机环境")
    assert payload["state"]["status"] == "idle"


def test_api_pending_kicks_background_refresh(home, monkeypatch):
    import server
    monkeypatch.setattr(ei, "scan_local", _boom)
    monkeypatch.setattr(ei, "scan_cluster", _boom)
    # 已配置但没有缓存 -> cached_cluster 只回 pending，绝不在这里调 scan_cluster
    monkeypatch.setattr(ei, "cluster_configured", lambda: _configured())
    calls = []
    monkeypatch.setattr(server, "_env_inv_refresh", lambda scope="all": calls.append(scope) or True)
    payload = asyncio.run(server.env_inventory_api(refresh=1, cluster=1, scope="cluster"))
    assert payload["pending"] is True
    assert calls == ["cluster"]
    assert payload["state"]["triggered"] is True


def test_api_cluster_zero_skips_cluster(home, monkeypatch):
    import server
    ei._write_cache(local=_canned_local(), local_at=ei._now())
    monkeypatch.setattr(ei, "scan_local", _boom)
    monkeypatch.setattr(ei, "scan_cluster", _boom)
    payload = asyncio.run(server.env_inventory_api(refresh=0, cluster=0, scope=""))
    assert payload["cluster"] == {}
    assert payload["pending"] is False


def test_report_md_endpoint_and_download_header(home, monkeypatch):
    import server
    _prime_cache_configured(home)
    monkeypatch.setattr(ei, "scan_local", _boom)
    resp = asyncio.run(server.env_report_md(download=0))
    body = resp.body.decode("utf-8")
    assert resp.media_type == "text/markdown; charset=utf-8"
    assert "# 环境报告" in body and "## 给 Agent 的环境卡片" in body
    assert "content-disposition" not in {k.lower() for k in resp.headers}
    resp2 = asyncio.run(server.env_report_md(download=1))
    assert "attachment" in resp2.headers["content-disposition"]


def test_digest_block_is_cache_only_and_safe(home, monkeypatch):
    import server
    ei._write_cache(local=_canned_local(), local_at=ei._now())
    block = server._env_digest_block()
    assert block.startswith("\n\n## 本机环境")
    monkeypatch.setattr(ei, "agent_digest", _boom)
    assert server._env_digest_block() == ""


def test_create_agent_prompt_includes_digest():
    with open(os.path.join(WEBUI, "server.py"), encoding="utf-8") as fh:
        text = fh.read()
    assert "_env_digest_block()" in text
    assert "ephemeral_system_prompt=" in text
    assert "+ _env_digest_block()" in text


# ---------------------------------------------------------------------------
# 前端接线（静态断言：index.html 无构建步骤）
# ---------------------------------------------------------------------------
def _read_index():
    with open(INDEX, encoding="utf-8") as fh:
        return fh.read()


def test_frontend_nav_entry_and_i18n():
    text = _read_index()
    assert 'id="nav-env-mgr"' in text
    assert 'data-i18n="nav_env_mgr"' in text
    assert "openEnvManager()" in text
    assert text.count("'nav_env_mgr'") == 2  # zh + en 各一处
    assert "showEnvCheck" not in text  # 旧的环境检测入口已下线


def test_frontend_modal_wiring():
    text = _read_index()
    for token in ("'env-manager'", "em-box", "em-tab", "/api/env/inventory?refresh=",
                  "'/api/env/report.md'", "?download=1", "emViewCluster", "emViewAgent",
                  "openClusterConsole()", "EM_I18N", "emT("):
        assert token in text, token
    assert "setTimeout(function () { emLoad(false); }, 3000)" in text


def test_frontend_stale_and_verify_wired():
    """2026-09-23：面板要能显示过期清单 + 有「确认环境」按钮。"""
    text = _read_index()
    for token in ("emStaleNote", "emVerify()", "/api/env/verify", "em_verify_tip",
                  "em_verify_same", "em_verify_changed", "em-stale"):
        assert token in text, token
    # 过期提示不能靠 pending 分支（那样等于又回到"没扫过"）
    assert "loc.stale ? 'busy' : 'ok'" in text
    assert "if (local.stale) out += emStaleNote(local);" in text
    # cluster 那个 out 必须先声明再拼接（TDZ 回归）
    seg = text[text.index("function emViewCluster(cl)"):]
    seg = seg[:seg.index("var rows =")]
    assert seg.index("var out = ''") < seg.index("emStaleNote"), "out 要先声明"


def test_frontend_i18n_has_stale_and_verify_keys():
    text = _read_index()
    start = text.index("var EM_I18N = {")
    end = text.index("function emT(k)", start)
    block = text[start:end]
    for key in ("em_stale", "em_stale_tip", "em_verify", "em_verify_tip",
                "em_verify_same", "em_verify_changed", "em_verify_fail"):
        # 键是对象字面量（无引号）：em_stale: / em_verify_same: 各出现两次（zh + en）
        assert block.count(key + ":") == 2, "%s 必须中英各一处" % key


def test_api_verify_endpoint_exists():
    with open(os.path.join(WEBUI, "server.py"), encoding="utf-8") as fh:
        text = fh.read()
    assert '@app.post("/api/env/verify")' in text
    # verify 会真扫（10~45 秒）→ 必须挪出事件循环
    assert "await asyncio.to_thread(mod.verify)" in text


def test_frontend_cluster_tab_explains_how_to_configure():
    text = _read_index()
    assert "em_cluster_off" in text and "em_cluster_open" in text
    assert "em_node_detail" in text and "em_cluster_res" in text


def test_frontend_env_i18n_keys_are_identical():
    text = _read_index()
    start = text.index("var EM_I18N = {")
    end = text.index("function emT(k)", start)
    block = text[start:end]
    zh = block[block.index("zh: {"):block.index("en: {")]
    en = block[block.index("en: {"):]
    keys_zh = set(_re.findall(r"^\s*(em_[a-z_]+):", zh, _re.M))
    keys_en = set(_re.findall(r"^\s*(em_[a-z_]+):", en, _re.M))
    assert keys_zh == keys_en and len(keys_zh) >= 20
