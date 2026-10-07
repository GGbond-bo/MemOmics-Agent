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
import threading
import time

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
    dc._cache_clear()          # 读缓存是模块级的：每个用例从空缓存开始，别互相喂旧数据
    yield tmp_path
    dc._CFG_CACHE["mtime"] = None
    dc._CFG_CACHE["cfg"] = None


def _write_cfg(home, section: dict):
    import yaml
    (home / "config.yaml").write_text(
        yaml.safe_dump({"dcs_cloud": section}, allow_unicode=True), encoding="utf-8")
    dc._CFG_CACHE["mtime"] = None
    dc._CFG_CACHE["cfg"] = None


def _fake_cli_counting(home, payload: dict, exit_code: int = 0):
    """同 _fake_cli，但每次调用都往 calls.txt 追加一行（用来数「CLI 真跑了几次」）。"""
    text = json.dumps(payload, ensure_ascii=True)
    if os.name == "nt":
        path = home / "dcs.cmd"
        path.write_text(
            '@echo off\r\n'
            'echo %%* >> "%%~dp0calls.txt"\r\n'
            'echo %%* > "%%~dp0argv.txt"\r\n'
            'echo %s\r\n'
            'exit /b %d\r\n' % (text, exit_code),
            encoding="ascii")
    else:
        path = home / "dcs"
        path.write_text(
            '#!/bin/sh\n'
            'echo "$*" >> "$(dirname "$0")/calls.txt"\n'
            'echo "$*" > "$(dirname "$0")/argv.txt"\n'
            "echo '%s'\n"
            'exit %d\n' % (text, exit_code),
            encoding="utf-8")
        path.chmod(0o755)
    return str(path)


def _slow_fake_cli_counting(home, payload: dict, delay_s: float = 1.2, exit_code: int = 0):
    """慢速版假 CLI：每次调用先睡 delay_s（模拟云 API 往返），用于并发单飞测试。"""
    text = json.dumps(payload, ensure_ascii=True)
    if os.name == "nt":
        path = home / "dcs.cmd"
        path.write_text(
            '@echo off\r\n'
            'ping -n 2 127.0.0.1 >nul 2>&1\r\n'
            'echo %%* >> "%%~dp0calls.txt"\r\n'
            'echo %%* > "%%~dp0argv.txt"\r\n'
            'echo %s\r\n'
            'exit /b %d\r\n' % (text, exit_code),
            encoding="ascii")
    else:
        path = home / "dcs"
        path.write_text(
            '#!/bin/sh\n'
            'sleep 1\n'
            'echo "$*" >> "$(dirname "$0")/calls.txt"\n'
            'echo "$*" > "$(dirname "$0")/argv.txt"\n'
            "echo '%s'\n"
            'exit %d\n' % (text, exit_code),
            encoding="utf-8")
        path.chmod(0o755)
    return str(path)


def _calls_of(home) -> int:
    p = home / "calls.txt"
    if not p.exists():
        return 0
    return len([l for l in p.read_text(encoding="utf-8", errors="replace").splitlines() if l.strip()])


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


def test_split_raw_cmd_keeps_quoted_args():
    """投递命令带空格参数（-i "sh /work/x.sh"）时的切分口径；JSON 数组优先，老行为不回归。"""
    sp = dc._split_raw_cmd
    assert sp('analysis run -i "sh /work/x.sh" -l vf=32g,num_proc=8') == \
        ["analysis", "run", "-i", "sh /work/x.sh", "-l", "vf=32g,num_proc=8"]
    assert sp('["analysis","run","-i","sh /work/x.sh"]') == \
        ["analysis", "run", "-i", "sh /work/x.sh"]
    assert sp(r"data upload E:\data\x.txt /Files/") == \
        ["data", "upload", r"E:\data\x.txt", "/Files/"]          # 无反斜杠回归
    assert sp('workflow run -n "Copy-scRNA-seq_v3" -o /Files/out') == \
        ["workflow", "run", "-n", "Copy-scRNA-seq_v3", "-o", "/Files/out"]
    assert sp('analysis run -i "unbalanced') == ["analysis", "run", "-i", '"unbalanced']  # 兜底不炸
    assert sp("") == [] and sp(None) == []


def test_raw_accepts_json_array_passthrough(_isolate):
    """raw 支持数组/JSON：投递命令原样到达 CLI（不用管引号）。"""
    _write_cfg(_isolate, {"enabled": True,
                          "cli_path": _fake_cli(_isolate, {"exit_code": 0, "message": "ok", "data": {}})})
    dc.save_credential("dcs_pat_abcdef1234567890")
    res = dc.dcs_cloud_handler({"action": "raw", "command": '["workflow","ls","-p","2"]'})
    assert json.loads(res)["status"] == "ok"
    assert "workflow ls" in _argv_of(_isolate)


# ---------------------------------------------------------------------------
# 7) 投递：WDL 流程 / 离线分析任务（2026-10-07，用户："怎么用云平台跑分析、投递任务"）
# ---------------------------------------------------------------------------

def test_flows_and_flow_form_merge_inputs(_isolate):
    """流程列表 + 投递表单：workflow info 的英文 inputs 与 check_parameter 的默认值/必填合并。"""
    _write_cfg(_isolate, {"enabled": True, "cli_path": _fake_cli_dispatch(_isolate, {
        "workflow ls": {"exit_code": 0, "message": "ok", "data": {"page": 1, "total": 2, "records": [
            {"name": "Copy-scRNA-seq_v3", "price": "free", "official_tag": "DCS", "origin": "公共库"},
            {"name": "DUCKS4", "price": "free"}]}},
        "workflow info": {"exit_code": 0, "message": "ok", "data": {
            "name": "Copy-scRNA-seq_v3", "version": "3.3.4",
            "pricing": {"price": "free", "mode": "free"},
            "inputs": [{"name": "SampleID", "type": "String", "required": True, "description": "Sample name"},
                       {"name": "expectcells", "type": "Int", "required": False, "description": "cells"}]}},
        "check_parameter": {"exit_code": 0, "message": "ok", "data": {"wdl_parameter": [
            {"参数名": "expectcells", "类型": "Int", "必填/选填": "必填", "默认值": "3000",
             "说明": "cells"}]}},
    })})
    dc.save_credential("dcs_pat_abcdef1234567890")

    res = json.loads(dc.dcs_cloud_handler({"action": "flows"}))
    assert res["status"] == "ok"
    assert [f["name"] for f in res["flows"]] == ["Copy-scRNA-seq_v3", "DUCKS4"]
    assert res["total"] == 2

    form = json.loads(dc.dcs_cloud_handler({"action": "flow_form", "flow": "Copy-scRNA-seq_v3"}))
    assert form["status"] == "ok"
    assert form["version"] == "3.3.4" and form["pricing"]["price"] == "free"
    by = {i["name"]: i for i in form["inputs"]}
    assert by["SampleID"]["required"] is True and by["SampleID"]["type"] == "String"
    assert by["expectcells"]["default"] == "3000"      # 默认值来自 check_parameter
    assert by["expectcells"]["required"] is True       # 必填口径两处合并


def test_flow_run_guards_write_and_composes_inputs(_isolate):
    """投递 WDL：只读模式直接拒；开写权限后 -i 名=值 / -o 拼装正确；空参数拒。"""
    args = {"action": "flow_run", "flow": "Copy-scRNA-seq_v3",
            "inputs": {"SampleID": "S1", "expectcells": "3000"}, "output_path": "/Files/out"}
    _write_cfg(_isolate, {"enabled": True, "allow_write": False,
                          "cli_path": _fake_cli(_isolate, {"exit_code": 0, "message": "ok",
                                                           "data": {"task_id": "W20261007"}})})
    dc.save_credential("dcs_pat_abcdef1234567890")
    guard = json.loads(dc.dcs_cloud_handler(args))
    assert guard["status"] == "error" and "只读模式" in guard["error"]
    assert "workflow run" not in _argv_of(_isolate)          # 碰都没碰 CLI

    _write_cfg(_isolate, {"enabled": True, "allow_write": True,
                          "cli_path": _fake_cli(_isolate, {"exit_code": 0, "message": "ok",
                                                           "data": {"task_id": "W20261007"}})})
    res = json.loads(dc.dcs_cloud_handler(args))
    assert res["status"] == "ok" and res["task_id"] == "W20261007"
    argv = _argv_of(_isolate)
    assert "workflow run -n Copy-scRNA-seq_v3" in argv
    assert "-i SampleID=S1" in argv and "-i expectcells=3000" in argv and "-o /Files/out" in argv
    assert "workflow run -n Copy-scRNA-seq_v3" in " ".join(res["argv"])

    bad = json.loads(dc.dcs_cloud_handler({"action": "flow_run", "flow": "X", "inputs": {}}))
    assert bad["status"] == "error" and "输入参数" in bad["error"]


def test_analysis_run_and_task_cancel_compose(_isolate):
    """离线作业投递与取消：命令/规格/镜像/挂载/输出；cancel 按 kind 分流。"""
    _write_cfg(_isolate, {"enabled": True, "allow_write": True,
                          "cli_path": _fake_cli(_isolate, {"exit_code": 0, "message": "ok",
                                                           "data": {"task_id": "A1"}})})
    dc.save_credential("dcs_pat_abcdef1234567890")
    bad = json.loads(dc.dcs_cloud_handler({"action": "analysis_run"}))
    assert bad["status"] == "error" and "command" in bad["error"]

    ok = json.loads(dc.dcs_cloud_handler({"action": "analysis_run", "name": "t1",
                                          "command": "sh /work/zhangbo11/x.sh",
                                          "resource": "vf=32g,num_proc=8", "image": "img:latest",
                                          "mount": "/Files/a,/Files/b", "output_path": "/Files/out"}))
    assert ok["status"] == "ok" and ok["task_id"] == "A1"
    argv = _argv_of(_isolate)
    assert "analysis run" in argv
    assert "sh /work/zhangbo11/x.sh" in argv          # Windows 下 argv.txt 里这个参数带引号
    assert "-l vf=32g,num_proc=8" in argv and "--image img:latest" in argv
    assert "-m /Files/a,/Files/b" in argv and "-o /Files/out" in argv

    json.loads(dc.dcs_cloud_handler({"action": "task_cancel", "task_id": "A1", "kind": "analysis"}))
    assert "analysis cancel A1" in _argv_of(_isolate)
    json.loads(dc.dcs_cloud_handler({"action": "task_cancel", "task_id": "W1", "kind": "workflow"}))
    assert "workflow cancel -n W1" in _argv_of(_isolate)

    assert json.loads(dc.dcs_cloud_handler({"action": "task_cancel"}))["status"] == "error"


def test_flow_tasks_and_images_shape(_isolate):
    """WDL 任务列表 + 镜像列表：字段归一化（status/expense/ref）。"""
    _write_cfg(_isolate, {"enabled": True, "cli_path": _fake_cli_dispatch(_isolate, {
        "workflow tasks": {"exit_code": 0, "message": "ok", "data": {"page": 1, "total": 1, "records": [
            {"task_id": "W202607230088006", "status": "运行中", "wf_name": "Copy-scRNA-seq_v3",
             "wf_version": "v3.2.2", "expense": "27.30", "create_user": "zhangbo11"}]}},
        "image ls": {"exit_code": 0, "message": "ok", "data": {"page": 1, "total": 1, "records": [
            {"name": "r441_nebula_probe_d", "tags": "latest", "prog_env": "workflow"}]}},
    })})
    dc.save_credential("dcs_pat_abcdef1234567890")
    t = json.loads(dc.dcs_cloud_handler({"action": "flow_tasks"}))
    assert t["status"] == "ok" and t["tasks"][0]["task_id"] == "W202607230088006"
    assert t["tasks"][0]["status"] == "运行中"
    im = json.loads(dc.dcs_cloud_handler({"action": "images"}))
    assert im["status"] == "ok" and im["images"][0]["ref"] == "r441_nebula_probe_d:latest"


def test_submit_actions_are_visible_to_model():
    """契约锁：投递动作必须在 agent 工具 schema 的 enum 里（模型才调得到）。"""
    tool = os.path.join(_ROOT, "memomics", "bio_tools", "cloud_connector.py")
    text = open(tool, encoding="utf-8").read()
    for act in ("flows", "flow_form", "flow_run", "analysis_run", "images",
                "flow_tasks", "flow_task_info", "task_cancel"):
        assert '"%s"' % act in text


# ---------------------------------------------------------------------------
# 8) ⚡ 读缓存 + stale-while-revalidate（2026-10-08：点开面板要等很久 → 云 API 1.6–2.8s/次）
# ---------------------------------------------------------------------------

_PROJECTS_PAYLOAD = {"exit_code": 0, "message": "ok", "data": {
    "page": 1, "total": 2, "projects": [
        {"project_id": "P25Z10200N1075", "project_name": "FSHD", "current": True},
        {"project_id": "E-chip2304017", "project_name": "chip", "is_arrears": True}]}}


def test_read_cache_hit_and_fresh_bypass(_isolate):
    """第二次直接命中缓存（CLI 不再跑）；fresh=true 强制真跑。"""
    _write_cfg(_isolate, {"enabled": True,
                          "cli_path": _fake_cli_counting(_isolate, _PROJECTS_PAYLOAD)})
    dc.save_credential("dcs_pat_abcdef1234567890")

    r1 = json.loads(dc.dcs_cloud_handler({"action": "projects", "page": 1}))
    assert r1["status"] == "ok" and not r1.get("cached")
    assert _calls_of(_isolate) == 1

    t0 = time.time()
    r2 = json.loads(dc.dcs_cloud_handler({"action": "projects", "page": 1}))
    dt = time.time() - t0
    assert r2["cached"] is True and r2["refreshing"] is False and r2["age"] >= 0
    assert r2["projects"]["total"] == 2                     # 数据本身没变
    assert _calls_of(_isolate) == 1                         # 没有再起 CLI
    assert dt < 0.5, "缓存命中不该再等云 API"

    r3 = json.loads(dc.dcs_cloud_handler({"action": "projects", "page": 1, "fresh": True}))
    assert not r3.get("cached") and _calls_of(_isolate) == 2

    # 参数不同 = 不同缓存键，不会串味
    r4 = json.loads(dc.dcs_cloud_handler({"action": "projects", "page": 2}))
    assert not r4.get("cached") and _calls_of(_isolate) == 3


def test_stale_cache_returns_old_then_refreshes_in_background(_isolate):
    """过期不干等：先回旧值（refreshing=True），后台线程把新值写回。"""
    payload = json.loads(json.dumps(_PROJECTS_PAYLOAD))
    _write_cfg(_isolate, {"enabled": True, "cli_path": _fake_cli_counting(_isolate, payload)})
    dc.save_credential("dcs_pat_abcdef1234567890")

    dc.dcs_cloud_handler({"action": "projects", "page": 1})
    key = dc._cache_key_for("projects", {"action": "projects", "page": 1})
    ent = dc._cache_get(key)
    assert ent and ent["t"]
    with dc._CACHE_LOCK:
        ent["t"] -= (dc._CACHE_TTL["projects"] + 10)        # 手动把它变成"过期"

    r = json.loads(dc.dcs_cloud_handler({"action": "projects", "page": 1}))
    assert r["status"] == "ok" and r["cached"] is True and r["refreshing"] is True
    assert r["age"] >= dc._CACHE_TTL["projects"]

    for _ in range(60):                                     # 等后台刷新落地
        time.sleep(0.05)
        ent2 = dc._cache_get(key)
        if ent2 and not ent2.get("refreshing"):
            break
    ent2 = dc._cache_get(key)
    assert ent2 and not ent2.get("refreshing"), "后台刷新没有收尾"
    assert time.time() - ent2["t"] < 2, "后台刷新没有把时间戳刷新"


def test_write_action_clears_cache(_isolate):
    """切项目（写）之后，被它影响的列表必须重拉，不能继续吃旧缓存。"""
    _write_cfg(_isolate, {"enabled": True, "allow_write": True,
                          "cli_path": _fake_cli_counting(_isolate, _PROJECTS_PAYLOAD)})
    dc.save_credential("dcs_pat_abcdef1234567890")
    dc.dcs_cloud_handler({"action": "projects", "page": 1})
    key = dc._cache_key_for("projects", {"action": "projects", "page": 1})
    assert dc._cache_get(key) is not None

    dc.dcs_cloud_handler({"action": "use_project", "project": "P25Z10200N1075"})
    assert dc._cache_get(key) is None, "写动作没清缓存"

    r = json.loads(dc.dcs_cloud_handler({"action": "projects", "page": 1}))
    assert not r.get("cached") and _calls_of(_isolate) >= 3


def test_concurrent_reads_share_one_cli_run(_isolate):
    """单飞：悬停预热与紧接着点开是同一个请求 → 只跑一次 CLI，后来者共享结果。

    没有单飞的话，这两个并发请求会各起一次 CLI（各等 1.6–2.8s 的云往返）。
    """
    _write_cfg(_isolate, {"enabled": True,
                          "cli_path": _slow_fake_cli_counting(_isolate, _PROJECTS_PAYLOAD)})
    dc.save_credential("dcs_pat_abcdef1234567890")
    out = {}

    def call(tag):
        out[tag] = json.loads(dc.dcs_cloud_handler({"action": "projects", "page": 1}))

    t1 = threading.Thread(target=call, args=("a",))
    t2 = threading.Thread(target=call, args=("b",))
    t1.start()
    time.sleep(0.3)          # 让 a 先把"飞行"挂上
    t2.start()
    t1.join(60)
    t2.join(60)
    assert out["a"]["status"] == "ok" and out["b"]["status"] == "ok"
    assert _calls_of(_isolate) == 1, "并发读没有单飞（跑了 %d 次 CLI）" % _calls_of(_isolate)
    assert out["b"].get("shared") or out["b"].get("cached"), "后来者没有共享到结果"


def test_errors_are_not_cached(_isolate):
    """失败结果不入缓存（否则一次网络抖动会被记住 45 秒）。"""
    _write_cfg(_isolate, {"enabled": True,
                          "cli_path": _fake_cli_counting(
                              _isolate, {"exit_code": 1, "error": {"type": "biz", "detail": {"business_code": 41201,
                                       "message": "token expired"}}}, exit_code=1)})
    dc.save_credential("dcs_pat_abcdef1234567890")
    r1 = json.loads(dc.dcs_cloud_handler({"action": "projects", "page": 1}))
    r2 = json.loads(dc.dcs_cloud_handler({"action": "projects", "page": 1}))
    assert r1["status"] == "error" and r2["status"] == "error"
    assert not r1.get("cached") and not r2.get("cached")
    assert _calls_of(_isolate) == 2, "错误被缓存住了"


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


# ---------------------------------------------------------------------------
# 7) 下载队列（2026-10-07）：进度 / 完成态 / 多文件队列
#    用户原话：「下载文件的时候，没有进度表，没有完成显示，我要下载多个文件，没有队列展示」
#    锁死的契约：串行（一次只跑一个）、有中间进度百分比、完成/失败/取消三态可辨、
#    失败带可操作指引、刷新页面不丢（任务登记在进程内存）、取消能真杀掉进程。
# ---------------------------------------------------------------------------

_FAKE_DL = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "fake_dcs_download.py")


@pytest.fixture
def _dl_queue(monkeypatch, tmp_path):
    """把队列的 CLI 调用换成「假下载器」：真进程、真落盘、分块写、带进度行。"""
    dc.dl_reset()
    monkeypatch.setattr(dc, "resolve_cli", lambda cfg=None: "fake-dcs-cli")
    real_spawn = dc._dl_spawn
    monkeypatch.setattr(
        dc, "_dl_spawn",
        lambda argv: real_spawn([sys.executable, "-X", "utf8", _FAKE_DL] + list(argv)[1:]))
    yield tmp_path
    dc.dl_reset()


def _dl_wait_idle(timeout: float = 40.0):
    """等队列跑空；返回 (最后一帧, 观察到的中间进度, 跑过的状态集, 最大并发)。"""
    mids, states, max_running = [], set(), 0
    snap = dc.dl_list()
    deadline = time.time() + timeout
    while time.time() < deadline:
        snap = dc.dl_list()
        counts = snap["counts"]
        max_running = max(max_running, counts["running"])
        for j in snap["jobs"]:
            states.add(j["state"])
            if j["state"] == "running" and j["pct"] is not None:
                mids.append(j["pct"])
        if counts["total"] and counts["active"] == 0:
            break
        time.sleep(0.15)
    return snap, mids, states, max_running


def test_dl_queue_runs_serially_and_reports_progress(_dl_queue, monkeypatch):
    monkeypatch.setenv("FAKE_SIZE", "1048576")
    monkeypatch.setenv("FAKE_DELAY", "0.25")
    target = str(_dl_queue / "out")
    start = dc.dl_start({"items": [
        {"path": "/Files/a.bin", "name": "a.bin", "size": 1048576, "target": target},
        {"path": "/Files/b.bin", "name": "b.bin", "size": 1048576, "target": target},
        {"path": "/Files/c.bin", "name": "c.bin", "size": 1048576, "target": target},
    ]})
    assert start["status"] == "ok" and len(start["ids"]) == 3

    snap, mids, states, max_running = _dl_wait_idle()
    assert max_running == 1, "队列必须串行：任何时刻只允许一个任务在跑"
    assert any(0 < p < 100 for p in mids), "必须报出中间进度（不是只有 0/100）"
    assert {"queued", "running", "done"} <= states
    jobs = snap["jobs"]
    assert len(jobs) == 3 and all(j["state"] == "done" for j in jobs)
    for j in jobs:
        assert j["pct"] == 100 and j["got"] == 1048576
        assert os.path.isfile(os.path.join(target, j["name"]))
        assert j["message"].startswith("已下载到 ")          # 完成态有明确文案
    assert [j["name"] for j in reversed(jobs)] == ["a.bin", "b.bin", "c.bin"]   # 按入队顺序


def test_dl_cancel_running_job_records_partial(_dl_queue, monkeypatch):
    monkeypatch.setenv("FAKE_SIZE", str(8 * 1024 * 1024))
    monkeypatch.setenv("FAKE_DELAY", "0.8")
    target = str(_dl_queue / "out2")
    size = 8 * 1024 * 1024
    jid = dc.dl_start({"path": "/Files/slow.bin", "name": "slow.bin",
                       "size": size, "target": target})["id"]

    got = 0
    for _ in range(80):
        time.sleep(0.15)
        job = [j for j in dc.dl_list()["jobs"] if j["id"] == jid][0]
        if job["state"] == "running" and job["got"] > 0:
            got = job["got"]
            break
    assert got > 0, "取消前应该已经有一部分字节落盘"

    assert dc.dl_cancel({"id": jid})["status"] == "ok"
    job = None
    for _ in range(80):
        time.sleep(0.15)
        job = [j for j in dc.dl_list()["jobs"] if j["id"] == jid][0]
        if job["state"] == "cancelled":
            break
    assert job is not None and job["state"] == "cancelled"
    assert job["got"] >= got and "取消" in job["message"]
    assert dc.dl_cancel({"id": jid})["status"] == "ok"        # 重复取消不炸


def test_dl_failure_translates_business_code(_dl_queue, monkeypatch):
    monkeypatch.setenv("FAKE_SIZE", "4096")
    monkeypatch.setenv("FAKE_DELAY", "0.05")
    target = str(_dl_queue / "out3")
    dc.dl_start({"path": "/Files/fail.bin", "name": "fail.bin", "size": 4096, "target": target})
    snap, _mids, _states, _mr = _dl_wait_idle()
    job = snap["jobs"][0]
    assert job["state"] == "failed"
    assert "请先选择项目" in job["message"]
    assert "项目" in job["hint"], "业务码 83003 必须翻译成可操作指引（先选项目）"


def test_dl_retry_then_clear(_dl_queue, monkeypatch):
    monkeypatch.setenv("FAKE_SIZE", "4096")
    monkeypatch.setenv("FAKE_DELAY", "0.05")
    target = str(_dl_queue / "out4")
    first = dc.dl_start({"path": "/Files/fail.bin", "name": "fail.bin",
                         "size": 4096, "target": target})
    _dl_wait_idle()
    retried = dc.dl_retry({"id": first["id"]})
    assert retried["status"] == "ok" and retried["id"] != first["id"], "重试应是新任务"
    _dl_wait_idle()
    assert len(dc.dl_list()["jobs"]) == 2

    cleared = dc.dl_clear({})
    assert cleared["removed"] == 2 and dc.dl_list()["jobs"] == []
    assert dc.dl_retry({"id": "不存在"})["status"] == "error"
    assert dc.dl_reveal({"id": "不存在"})["status"] == "error"


def test_dl_start_validates_input(_dl_queue):
    assert dc.dl_start({})["status"] == "error"               # 缺 path
    assert "path" in dc.dl_start({})["error"]
    blocker = _dl_queue / "blocker"
    blocker.write_text("x", encoding="utf-8")
    bad = dc.dl_start({"path": "/Files/x.bin", "target": str(blocker / "sub")})
    assert bad["status"] == "error" and "建不出来" in bad["error"]


def test_dl_start_defaults_to_download_dir(_dl_queue):
    """不给 target 时落到配置的 download_dir（不留空、不写仓库）。"""
    home = _dl_queue
    _write_cfg(home, {"enabled": True, "download_dir": str(home / "dlroot")})
    monkey_res = dc.dl_start({"path": "/Files/x.bin", "name": "x.bin", "size": 1})
    assert monkey_res["status"] == "ok"
    job = dc.dl_list()["jobs"][0]
    assert job["target"] == str(home / "dlroot")
    dc.dl_cancel({"id": job["id"]})
    dc.dl_reset()


def test_dl_http_routes_are_registered():
    """队列接口必须注册进 server.py，且进了中间件路由快照（前端轮询它们）。"""
    srv = open(os.path.join(_ROOT, "webui", "server.py"), encoding="utf-8").read()
    snap = json.load(open(os.path.join(_ROOT, "webui", "middleware_routes.json"), encoding="utf-8"))
    for name in ("dl/start", "dl/list", "dl/cancel", "dl/retry", "dl/clear", "dl/reveal"):
        assert ('@app.post("/api/dcs/%s")' % name) in srv, "server.py 缺路由 " + name
        assert ('/api/dcs/%s' % name) in snap, "中间件快照缺路由 " + name
