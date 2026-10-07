# -*- coding: utf-8 -*-
"""☁️ dcs_cloud 连接器回归测试（全程离线：假 CLI + 临时 HERMES_HOME，不用真 PAT）。

首版随「PAT + 官方 dcs CLI 接入 MemOmics」（2026-10-07）落盘。锁死的契约：
  1. 配置来源：config.yaml 的 dcs_cloud: 段，环境变量 MEMOMICS_DCS_* 优先；
  2. PAT 只落 hermes_home/dcs_cloud.json，工具输出只出现掩码、绝无明文；
  3. 未绑定 / 未启用时的报错必须是"可操作指引"（引导去面板绑定），不是裸错误；
  4. 平台业务码翻译：41201/60003 → 重绑 PAT；83003 → 选项目；83006/83007 → 容器动作；
  5. allow_write=false 时写动作（upload / container_open）在碰 CLI 之前就被拒；
  6. check_fn 只看 enabled、不看是否已绑定 —— 工具必须先能被模型"看见"，才谈得上引导用户。
"""
import json
import os
import subprocess
import sys

import pytest

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, _ROOT)

from memomics.connectors import dcs_cloud as dc  # noqa: E402


# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _isolate(monkeypatch, tmp_path):
    """每个用例都在自己的 HERMES_HOME 里跑，并清掉模块级配置缓存。"""
    monkeypatch.setattr(dc, "_hermes_home", lambda: tmp_path)
    monkeypatch.delenv("MEMOMICS_DCS_ENABLED", raising=False)
    dc._CFG_CACHE["mtime"] = None
    dc._CFG_CACHE["cfg"] = None
    yield tmp_path
    dc._CFG_CACHE["mtime"] = None
    dc._CFG_CACHE["cfg"] = None


def _write_cfg(home, section: dict):
    import yaml
    (home / "config.yaml").write_text(
        yaml.safe_dump({"dcs_cloud": section}, allow_unicode=True), encoding="utf-8")
    dc._CFG_CACHE["mtime"] = None
    dc._CFG_CACHE["cfg"] = None


def _fake_cli(home, payload: dict, exit_code: int = 0):
    """造一个假 dcs CLI：把收到的参数记到 argv.txt，再吐固定 JSON。

    只写 ASCII，避免 cmd/sh 的代码页差异干扰解析。
    """
    text = json.dumps(payload, ensure_ascii=True)
    if os.name == "nt":
        path = home / "dcs.cmd"
        # 注意：cmd 里的 %* / %~dp0 要写成 %%* / %%~dp0，否则会被 % 格式化吞掉
        path.write_text(
            '@echo off\r\n'
            'echo %%* > "%%~dp0argv.txt"\r\n'
            'echo %s\r\n'
            'exit /b %d\r\n' % (text, exit_code),
            encoding="ascii")
    else:
        path = home / "dcs"
        path.write_text(
            '#!/bin/sh\n'
            'echo "$*" > "$(dirname "$0")/argv.txt"\n'
            "echo '%s'\n"
            'exit %d\n' % (text, exit_code),
            encoding="utf-8")
        path.chmod(0o755)
    return str(path)


def _argv_of(home):
    try:
        return (home / "argv.txt").read_text(encoding="utf-8", errors="replace").strip()
    except Exception:
        return ""


_AUTH_ERR = {
    "exit_code": 3,
    "message": "not logged in",
    "error": {"type": "auth_failed", "detail": {"business_code": 41201, "message": "not logged in"},
              "hint": "please login", "retryable": False},
    "data": {"error": "not logged in or token expired"},
}


# ---------------------------------------------------------------------------
# 1) 配置
# ---------------------------------------------------------------------------

def test_config_from_file_and_env(_isolate, monkeypatch):
    _write_cfg(_isolate, {"enabled": True, "timeout": 45, "base_url": "https://www.dcs.cloud",
                          "default_project": "P123"})
    cfg = dc.load_config()
    assert cfg["enabled"] is True and cfg["timeout"] == 45 and cfg["default_project"] == "P123"

    monkeypatch.setenv("MEMOMICS_DCS_ENABLED", "false")
    monkeypatch.setenv("MEMOMICS_DCS_TIMEOUT", "7")
    dc._CFG_CACHE["cfg"] = None
    dc._CFG_CACHE["mtime"] = None
    cfg2 = dc.load_config()
    assert cfg2["enabled"] is False and cfg2["timeout"] == 7      # 环境变量优先


def test_config_defaults_are_disabled(_isolate):
    cfg = dc.load_config()          # 没有任何 config.yaml
    assert cfg["enabled"] is False and dc.dcs_cloud_enabled() is False


# ---------------------------------------------------------------------------
# 2) 凭据库
# ---------------------------------------------------------------------------

def test_vault_roundtrip_and_mask(_isolate):
    dc.save_credential("dcs_pat_abcdef1234567890", user="zhangsan", user_id="U1")
    rec = dc.read_credential()
    assert rec["pat"] == "dcs_pat_abcdef1234567890"
    assert dc.mask_pat(rec["pat"]).endswith("7890")
    assert "abcdef123456" not in dc.mask_pat(rec["pat"])          # 中间段必须被掩掉
    assert dc.vault_path() == _isolate / "dcs_cloud.json"
    assert dc.clear_credential() is True and dc.read_credential() == {}


def test_vault_read_survives_corrupt_file(_isolate):
    (_isolate / "dcs_cloud.json").write_text("{not json", encoding="utf-8")
    assert dc.read_credential() == {}      # 坏文件不能把工具拖崩


# ---------------------------------------------------------------------------
# 3) CLI 执行与错误翻译
# ---------------------------------------------------------------------------

def test_run_cli_ok_and_flags(_isolate):
    _write_cfg(_isolate, {"enabled": True, "cli_path": _fake_cli(
        _isolate, {"exit_code": 0, "message": "ok", "data": [{"code": "P1"}]})})
    res = dc._run_cli(["project", "ls"], cfg=dc.load_config())
    assert res["ok"] is True and res["data"] == [{"code": "P1"}]
    argv = _argv_of(_isolate)
    assert "--output json" in argv and "--no-history" in argv     # 强制 JSON + 不写历史


def test_run_cli_auth_error_gets_actionable_hint(_isolate):
    _write_cfg(_isolate, {"enabled": True, "cli_path": _fake_cli(_isolate, _AUTH_ERR, exit_code=3)})
    res = dc._run_cli(["project", "ls"], cfg=dc.load_config())
    assert res["ok"] is False and res["exit_code"] == 3
    assert "重新绑定" in (res["hint"] or "")                       # 41201 → 引导重绑 PAT


def test_run_cli_missing_binary_is_structured(_isolate, monkeypatch):
    monkeypatch.setattr(dc.shutil, "which", lambda name: None)
    monkeypatch.setattr(dc, "_candidate_cli_paths", lambda: [])
    _write_cfg(_isolate, {"enabled": True, "cli_path": "E:/nope/dcs.exe"})
    res = dc._run_cli(["project", "ls"], cfg=dc.load_config())
    assert res["ok"] is False and res["error"]["type"] == "cli_missing"
    assert "install_dcs_cli" in (res["hint"] or "")


@pytest.mark.parametrize("code,needle", [
    (83003, "use_project"),
    (83006, "container_open"),
    (83007, "稍等"),
])
def test_business_code_translation(code, needle):
    out = dc._attach_friendly_hint(
        {"ok": False, "exit_code": 1, "hint": "",
         "error": {"type": "x", "detail": {"business_code": code}}})
    assert needle in out["hint"]


def test_clip_truncates_huge_payload():
    payload = {"data": {"items": [{"i": i} for i in range(200)]}}
    out = dc._clip({"max_output_chars": 500}, payload)
    assert out.get("truncated") is True and len(out["data"]["items"]) <= 20


# ---------------------------------------------------------------------------
# 4) handler：未启用 / 未绑定 / 未知动作 / 写保护
# ---------------------------------------------------------------------------

def _call(args):
    return json.loads(dc.dcs_cloud_handler(args))


def test_handler_disabled_blocks_actions(_isolate):
    res = _call({"action": "ls"})
    assert res["status"] == "error" and "未启用" in res["error"]


def test_handler_unbound_guides_to_panel(_isolate):
    _write_cfg(_isolate, {"enabled": True})
    res = _call({"action": "ls"})
    assert res["status"] == "error" and "未绑定" in res["error"]
    assert "面板" in res["hint"]            # 必须告诉用户下一步去哪做


def test_handler_unknown_action(_isolate):
    _write_cfg(_isolate, {"enabled": True})
    res = _call({"action": "teleport"})
    assert res["status"] == "error" and "未知 action" in res["error"]


def test_write_guard_blocks_before_touching_cli(_isolate):
    _write_cfg(_isolate, {"enabled": True, "allow_write": False,
                          "cli_path": _fake_cli(_isolate, {"exit_code": 0, "data": None})})
    dc.save_credential("dcs_pat_abcdef1234567890")
    res = _call({"action": "upload", "path": "E:/a.csv", "target": "/Files/a.csv"})
    assert res["status"] == "error" and "只读模式" in res["error"]
    assert _argv_of(_isolate) == ""          # CLI 根本没被调用


def test_status_reports_not_bound_with_hint(_isolate):
    _write_cfg(_isolate, {"enabled": True})
    res = _call({"action": "status"})
    assert res["status"] == "ok" and res["bound"] is False and "访问令牌" in res["hint"]


def test_bind_rejects_bad_format_without_writing_vault(_isolate):
    _write_cfg(_isolate, {"enabled": True})
    res = _call({"action": "bind", "pat": "not-a-pat"})
    assert res["status"] == "error" and dc.read_credential() == {}


def test_bind_failure_does_not_store_pat(_isolate):
    _write_cfg(_isolate, {"enabled": True, "cli_path": _fake_cli(_isolate, _AUTH_ERR, exit_code=3)})
    res = _call({"action": "bind", "pat": "dcs_pat_badbadbadbadbad"})
    assert res["status"] == "error" and dc.read_credential() == {}


def test_bind_success_stores_masked_only_in_output(_isolate):
    payload = {"exit_code": 0, "message": "ok",
               "data": {"user_id": "U9", "username": "tester", "token_expires_at": "2027-01-01"}}
    _write_cfg(_isolate, {"enabled": True, "cli_path": _fake_cli(_isolate, payload)})
    raw = dc.dcs_cloud_handler({"action": "bind", "pat": "dcs_pat_secretsecret1234"})
    res = json.loads(raw)
    assert res["status"] == "ok" and res["bound"] is True
    assert "secretsecret" not in raw                      # 明文 PAT 绝不进工具输出
    assert dc.read_credential()["pat"] == "dcs_pat_secretsecret1234"


def test_raw_forbids_credential_subcommands(_isolate):
    _write_cfg(_isolate, {"enabled": True})
    dc.save_credential("dcs_pat_abcdef1234567890")
    for cmd in ("auth login", "logout", "config set base_url x"):
        res = _call({"action": "raw", "command": cmd})
        assert res["status"] == "error"
    res = _call({"action": "raw", "command": "rm -rf /"})
    assert res["status"] == "error" and "只放行" in res["error"]


# ---------------------------------------------------------------------------
# 5) 模型可见性：模块被 __init__ 导入后，registry 里必须有 dcs_cloud
# ---------------------------------------------------------------------------

def test_registry_contains_dcs_cloud():
    code = (
        "import json, sys\n"
        "sys.path.insert(0, %r)\n"
        "sys.path.insert(0, %r)\n"
        "import memomics.bio_tools\n"
        "from tools.registry import registry\n"
        "print(json.dumps(sorted(registry.get_tool_names_for_toolset('memomics'))))\n"
    ) % (_ROOT, os.path.join(_ROOT, "hermes-agent"))
    proc = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=300, cwd=_ROOT)
    assert proc.returncode == 0, (proc.stderr or "")[-800:]
    names = json.loads((proc.stdout or "").strip().splitlines()[-1])
    assert "dcs_cloud" in names, "dcs_cloud 没注册进 registry（模型看不到它）：%s" % (names,)


# ---------------------------------------------------------------------------
# 6) context：开工前确认上下文（用户要求：不替他默认项目、先把问题列出来）
#    以及 /api/dcs/pick 的默认目录解析（不弹窗那条路径）
# ---------------------------------------------------------------------------

def _fake_cli_dispatch(home, table: dict):
    """多命令假 CLI：按命令行里出现的关键字选 payload（context 要连着跑 3 条命令）。"""
    (home / "payloads.json").write_text(json.dumps(table, ensure_ascii=True), encoding="utf-8")
    script = home / "fake_dcs.py"
    script.write_text(
        "import json, sys\n"
        "args = ' '.join(sys.argv[1:])\n"
        "table = json.load(open(%r, encoding='utf-8'))\n"
        "for key, payload in table.items():\n"
        "    if key in args:\n"
        "        print(json.dumps(payload)); sys.exit(0)\n"
        "print(json.dumps({'exit_code': 0, 'message': 'ok', 'data': {}}))\n"
        % str(home / "payloads.json"), encoding="utf-8")
    if os.name == "nt":
        path = home / "dcs2.cmd"
        path.write_text(
            '@echo off\r\n'
            'echo %%* > "%%~dp0argv.txt"\r\n'
            '"%s" "%s" %%*\r\n' % (sys.executable, script),
            encoding="ascii")
    else:
        path = home / "dcs2"
        path.write_text(
            '#!/bin/sh\n'
            'echo "$*" > "$(dirname "$0")/argv.txt"\n'
            '"%s" "%s" "$@"\n' % (sys.executable, script),
            encoding="utf-8")
        path.chmod(0o755)
    return str(path)


_CONTEXT_TABLE = {
    "config show": {"exit_code": 0, "message": "ok", "data": {
        "current_user": "tester", "current_project": "P1", "current_region": "BGI-X",
        "data_cwd": "/Files", "base_url": "https://www.dcs.cloud",
        "copilot_base_url": "https://genpilot-release.dcs.cloud",
        "available_regions": ["BGI-X", "BGI-Y"]}},
    "project ls": {"exit_code": 0, "message": "ok", "data": {
        "page": 1, "page_size": 20, "total": 2, "projects": [
            {"project_id": "P1", "project_name": "甲项目", "region": "BGI-X",
             "current": True, "is_arrears": False},
            {"project_id": "P2", "project_name": "乙项目", "region": "BGI-X",
             "current": False, "is_arrears": True}]}},
    "data ls": {"exit_code": 0, "message": "ok", "data": {
        "path": "/Files", "page": 1, "page_size": 20, "total": 3, "items": [
            {"name": "Muscle", "is_directory": True},
            {"name": "fastq", "is_directory": True},
            {"name": "readme.txt", "is_directory": False}]}},
}


def test_context_assembles_session_projects_and_data_root(_isolate):
    _write_cfg(_isolate, {"enabled": True, "cli_path": _fake_cli_dispatch(_isolate, _CONTEXT_TABLE),
                          "download_dir": "E:/data/dcs"})
    dc.save_credential("dcs_pat_abcdef1234567890")
    res = _call({"action": "context"})
    assert res["status"] == "ok"
    assert res["session"]["current_project"] == "P1"
    assert res["session"]["copilot_base_url"].startswith("https://genpilot")
    assert [p["project_id"] for p in res["projects"]] == ["P1", "P2"]
    assert [p["project_id"] for p in res["projects"] if p["is_arrears"]] == ["P2"]
    assert res["data_root"]["dirs"] == ["Muscle", "fastq"]
    assert res["download_dir"] == "E:/data/dcs"
    assert res["projects_total"] == 2


def test_context_carries_the_grill_checklist(_isolate):
    """用户明确要求：执行前必须问清（项目/数据/参数/输出/费用），且不替用户默认项目。"""
    _write_cfg(_isolate, {"enabled": True, "cli_path": _fake_cli_dispatch(_isolate, _CONTEXT_TABLE)})
    dc.save_credential("dcs_pat_abcdef1234567890")
    res = _call({"action": "context"})
    blob = " ".join(res["questions"]) + " ".join(res["rules"])
    for must in ("项目", "数据在哪", "参数", "输出", "费用"):
        assert must in blob, "确认清单少了「%s」：%s" % (must, blob)
    assert any("不替用户默认项目" in r or "不替用户默认" in r for r in res["rules"]), res["rules"]
    assert len(res["questions"]) >= 5 and len(res["rules"]) >= 4


def test_context_skips_file_listing_when_asked(_isolate):
    _write_cfg(_isolate, {"enabled": True, "cli_path": _fake_cli_dispatch(_isolate, _CONTEXT_TABLE)})
    dc.save_credential("dcs_pat_abcdef1234567890")
    res = _call({"action": "context", "with_files": False})
    assert res["status"] == "ok" and "data_root" not in res


def test_pick_initial_points_at_a_real_dir(_isolate):
    """不弹窗的默认目录解析（dry_run 走这条路）——必须是真实存在的目录。"""
    server = pytest.importorskip("server")
    assert os.path.isdir(server._dcs_pick_initial("dir", "")), server._dcs_pick_initial("dir", "")
    here = str(_isolate)
    assert server._dcs_pick_initial("dir", here) == here
    (_isolate / "config.yaml").write_text("dcs_cloud: {}\n", encoding="utf-8")
    assert server._dcs_pick_initial("file", str(_isolate / "config.yaml")) == here


def test_server_action_whitelist_matches_connector(_isolate):
    """server._DCS_ACTIONS 与连接器 _ACTIONS 必须一致 —— context 就这么漏过一次（HTTP 报未知 action）。"""
    server = pytest.importorskip("server")
    assert set(server._DCS_ACTIONS) == set(dc._ACTIONS), (
        "server 独有: %s；连接器独有: %s"
        % (sorted(set(server._DCS_ACTIONS) - set(dc._ACTIONS)),
           sorted(set(dc._ACTIONS) - set(server._DCS_ACTIONS))))