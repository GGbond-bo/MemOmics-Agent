# -*- coding: utf-8 -*-
"""P2-4 渐进强制（分动作上线）聚焦测试（2026-09-23）

背景：沙箱默认是观察模式（判定照算、账照记，一律不拦人）。"上线"不是把总开关一开了事——
先把**写与删**这类危险动作真拦起来，读类和本机探测继续观察。这个文件测的就是这条路径：

  A. 强制配置解析：=1/true/yes/on/all/* 语义不变；动作名与通配；两个环境变量取并集；
     拼错的动作名必须**看得见**（enforce_unknown），不能静默退化成观察模式；整体关闭优先。
  B. 按动作开门：强制 fs.write 时 fs.write 越界真拦、fs.read 越界只记账（would_deny）；
     模式自述 partial；判定里的 mode 落在**这一次的 action** 上。
  C. netguard 跟着动作走：只强制 fs.* 时出网仍走老路径（不钉 IP、不拦）；
     强制 net.fetch 才拦，且被拦时一个字节都不发出去。
  D. 真实调用点：上传/改动回滚/会话数据删除/重命名结果目录（含用户指定目录）——
     观察模式零变更（老行为），强制后该拦的真拦，且**绝不半途写坏/删掉东西**。
  E. 运维逃生舱：MEMOMICS_SANDBOX_GRANT_DIRS 声明的目录可写可删，授权进审计；观察模式不动。
  F. 端到端：/api/sandbox/audit 能看见模式与强制动作；越界删除回 403 而不是 500。

纪律：全离线；每个用例自己把环境变量收干净（monkeypatch 自动还原）。
"""
import asyncio
import os
import shutil

import pytest

from conftest import cleanup_session
import server
from webui import netguard
from webui import sandbox as SB

ALL_ACTIONS = set(SB.ACTIONS)


@pytest.fixture()
def sb():
    """隔离 provider（不联网：注入假 DNS 与假时钟）+ 干净的强制环境。"""
    p = SB.SandboxProvider(name="p24", resolver=lambda h: ["93.184.216.34"], max_audit=500)
    old = SB.set_provider(p)
    for k in ("MEMOMICS_SANDBOX", "MEMOMICS_SANDBOX_ENFORCE",
              "MEMOMICS_SANDBOX_ENFORCE_ACTIONS", "MEMOMICS_SANDBOX_GRANT_DIRS"):
        os.environ.pop(k, None)
    try:
        yield p
    finally:
        SB.set_provider(old)
        SB.reset()
        for k in ("MEMOMICS_SANDBOX", "MEMOMICS_SANDBOX_ENFORCE",
                  "MEMOMICS_SANDBOX_ENFORCE_ACTIONS", "MEMOMICS_SANDBOX_GRANT_DIRS"):
            os.environ.pop(k, None)


@pytest.fixture()
def no_proxy(sb):
    """去掉开发机上的 HTTPS_PROXY，免得出网判定被代理路径带偏。"""
    saved = {}
    for k in ("HTTPS_PROXY", "https_proxy", "HTTP_PROXY", "http_proxy", "ALL_PROXY", "all_proxy"):
        if k in os.environ:
            saved[k] = os.environ.pop(k)
    try:
        yield
    finally:
        os.environ.update(saved)


def _mk(path):
    os.makedirs(path, exist_ok=True)
    return path


# ====================================================== A. 强制配置解析
@pytest.mark.parametrize("token", ["1", "true", "yes", "on", "all", "*", "TRUE", " yes "])
def test_a1_all_tokens_mean_everything(sb, monkeypatch, token):
    """老语义必须原样保留：=1 就是"全部都拦"，不许因为渐进上线而变味。"""
    monkeypatch.setenv("MEMOMICS_SANDBOX_ENFORCE", token)
    assert set(SB.enforce_actions()) == ALL_ACTIONS
    assert SB.sandbox_mode() == "enforce"
    assert SB.enforce_action("fs.read") and SB.enforce_action("net.fetch")
    assert SB.enforce_unknown() == []


def test_a2_action_names_and_wildcards(sb, monkeypatch):
    monkeypatch.setenv("MEMOMICS_SANDBOX_ENFORCE", "fs.write")
    assert set(SB.enforce_actions()) == {"fs.write"}
    assert SB.sandbox_mode() == "partial"

    monkeypatch.setenv("MEMOMICS_SANDBOX_ENFORCE", "fs.write, fs.delete ,net.fetch")
    assert set(SB.enforce_actions()) == {"fs.write", "fs.delete", "net.fetch"}

    monkeypatch.setenv("MEMOMICS_SANDBOX_ENFORCE", "fs.*")
    assert set(SB.enforce_actions()) == set(SB.FS_ACTIONS)

    monkeypatch.setenv("MEMOMICS_SANDBOX_ENFORCE", "net.*")
    assert set(SB.enforce_actions()) == set(SB.NET_ACTIONS)
    assert not SB.enforce_action("fs.read"), "net.* 不该顺带把文件动作也强开了"


def test_a3_off_values_are_observe(sb, monkeypatch):
    for token in ("", "0", "false", "no", "off"):
        monkeypatch.setenv("MEMOMICS_SANDBOX_ENFORCE", token)
        assert SB.enforce_actions() == frozenset()
        assert SB.sandbox_mode() == "observe"
        assert not SB.enforce_enabled()


def test_a4_two_env_names_union(sb, monkeypatch):
    monkeypatch.setenv("MEMOMICS_SANDBOX_ENFORCE", "fs.write")
    monkeypatch.setenv("MEMOMICS_SANDBOX_ENFORCE_ACTIONS", "fs.delete")
    assert set(SB.enforce_actions()) == {"fs.write", "fs.delete"}


def test_a5_typo_is_visible_not_silent(sb, monkeypatch):
    """动作名拼错：绝不允许悄悄变成观察模式还不吭声。"""
    monkeypatch.setenv("MEMOMICS_SANDBOX_ENFORCE", "fs.wirte")
    assert SB.enforce_actions() == frozenset()
    assert SB.sandbox_mode() == "observe"
    assert SB.enforce_unknown() == ["fs.wirte"]

    monkeypatch.setenv("MEMOMICS_SANDBOX_ENFORCE", "fs.write,os.reboot")
    assert set(SB.enforce_actions()) == {"fs.write"}, "认出来的词仍然生效"
    assert SB.enforce_unknown() == ["os.reboot"]


def test_a6_disable_wins_over_enforce(sb, monkeypatch):
    monkeypatch.setenv("MEMOMICS_SANDBOX_ENFORCE", "1")
    monkeypatch.setenv("MEMOMICS_SANDBOX", "0")
    assert SB.enforce_actions() == frozenset()
    assert SB.sandbox_mode() == "disabled"
    assert SB.enforce_unknown() == [], "整体关了就不该再报配置问题"
    monkeypatch.setenv("MEMOMICS_SANDBOX", "1")
    assert SB.sandbox_mode() == "enforce"


# ====================================================== B. 按动作开门
def test_b1_same_path_different_action(sb, tmp_path, monkeypatch):
    """同一条越界路径：强制了的动作真拦，没强制的动作只记账。"""
    root = _mk(str(tmp_path / "root"))
    outside = os.path.join(str(tmp_path), "outside.txt")
    monkeypatch.setenv("MEMOMICS_SANDBOX_ENFORCE", "fs.write")

    dw = SB.gate("fs.write", outside, roots=[root], source="test")
    assert dw.allow is False and dw.blocked is True and dw.mode == "enforce"
    assert dw.code == "path_outside_root"

    dr = SB.gate("fs.read", outside, roots=[root], source="test")
    assert dr.allow is False and dr.blocked is False and dr.mode == "observe"

    ok = SB.gate("fs.write", os.path.join(root, "a.txt"), roots=[root], source="test")
    assert ok.allow is True and ok.blocked is False and ok.code == "ok_callers_root"

    counts = sb.audit(50)["counts"]
    assert counts["blocked"] == 1 and counts["would_deny"] == 1 and counts["allow"] == 1


def test_b2_decision_mode_is_per_action(sb, monkeypatch):
    monkeypatch.setenv("MEMOMICS_SANDBOX_ENFORCE", "fs.write,net.fetch")
    assert SB.check("fs.write", "E:/x.txt").mode == "enforce"
    assert SB.check("net.fetch", "https://example.com/a").mode == "enforce"
    assert SB.check("fs.read", "E:/x.txt").mode == "observe"
    assert SB.check("net.local", "http://127.0.0.1:1/x").mode == "observe"


def test_b3_audit_and_stats_expose_enforced_actions(sb, monkeypatch):
    monkeypatch.setenv("MEMOMICS_SANDBOX_ENFORCE", "fs.delete,fs.wirte")
    body = sb.audit(1, codes=True)
    assert body["mode"] == "partial"
    assert body["enforce_actions"] == ["fs.delete"]
    assert body["enforce_unknown"] == ["fs.wirte"]
    st = sb.stats()
    assert st["enforce_actions"] == ["fs.delete"] and st["mode"] == "partial"


# ====================================================== C. netguard 跟着动作走
class _FakeResp:
    def __init__(self):
        self.status = 200
        self.headers = {}
        self.url = "https://example.com/x"

    def read(self, n=None):
        return b"{}"


def test_c1_write_enforced_does_not_touch_egress(sb, monkeypatch, no_proxy):
    """只强制写类动作时，出网必须完全走老路径（不钉 IP、也不拦）。"""
    called = []
    monkeypatch.setattr(netguard, "_plain_request",
                        lambda *a, **k: (called.append(a[0]), _FakeResp())[1])
    monkeypatch.setenv("MEMOMICS_SANDBOX_ENFORCE", "fs.write,fs.delete")
    before = netguard.counters()["pinned"]
    r = netguard.fetch("https://example.com/x", action="net.fetch", source="test.c1")
    assert called and r.status == 200
    assert netguard.counters()["pinned"] == before, "没强制的动作不该改走出网通道"


def test_c2_net_fetch_enforced_denies_before_any_io(sb, monkeypatch, no_proxy):
    called = []
    monkeypatch.setattr(netguard, "_plain_request",
                        lambda *a, **k: (called.append(a[0]), _FakeResp())[1])
    monkeypatch.setenv("MEMOMICS_SANDBOX_ENFORCE", "net.fetch")
    with pytest.raises(SB.SandboxDenied) as ei:
        netguard.fetch("https://example.com/x", action="net.fetch", source="test.c2")
    assert ei.value.code == "no_grant"
    assert called == [], "被拦时一个字节都不能发出去"


def test_c3_loopback_probe_survives(sb, monkeypatch):
    """net.local（本机服务发现）没被强制，强制 net.fetch 也不该连坐。"""
    monkeypatch.setenv("MEMOMICS_SANDBOX_ENFORCE", "net.fetch")
    local = SB.gate("net.local", "http://127.0.0.1:11434/v1/models", source="test.c3")
    assert local.allow is True and local.blocked is False and local.code == "ok_local"
    fetch = SB.gate("net.fetch", "http://127.0.0.1:11434/v1/models", source="test.c3")
    assert fetch.allow is False and fetch.blocked is True


# ====================================================== D. 真实调用点
_PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 32


def test_d1_upload_observe_unchanged(client, sb, tmp_path, monkeypatch):
    """观察模式（默认）：上传照旧成功，但审计里必须留下一条 fs.write 判定。"""
    monkeypatch.delenv("MEMOMICS_SANDBOX_ENFORCE", raising=False)
    r = client.post("/api/upload", files={"file": ("p24.png", _PNG, "image/png")})
    assert r.status_code == 200, r.text
    name = r.json()["name"]
    path = os.path.join(server._uploads_dir, name)
    try:
        assert os.path.isfile(path)
        items = sb.audit(50)["items"]
        assert any(i["action"] == "fs.write" and i["source"] == "upload.image" for i in items)
        assert sb.audit(50)["counts"]["blocked"] == 0
    finally:
        try:
            os.remove(path)
        except Exception:
            pass


def test_d2_upload_enforced_still_writes_inside_root(client, sb, monkeypatch):
    monkeypatch.setenv("MEMOMICS_SANDBOX_ENFORCE", "fs.write,fs.delete")
    r = client.post("/api/upload", files={"file": ("p24b.png", _PNG, "image/png")})
    assert r.status_code == 200, r.text
    path = os.path.join(server._uploads_dir, r.json()["name"])
    try:
        assert os.path.isfile(path)
        code = [i["code"] for i in sb.audit(20)["items"]
                if i["action"] == "fs.write" and i["source"] == "upload.image"]
        assert code and code[0] == "ok_callers_root"
    finally:
        try:
            os.remove(path)
        except Exception:
            pass


def test_d3_upload_denied_returns_403_and_writes_nothing(client, sb, monkeypatch):
    """真的被拦时：403 + 盘上不多出任何东西（拒绝发生在 open() 之前）。"""
    monkeypatch.setenv("MEMOMICS_SANDBOX_ENFORCE", "fs.write")
    monkeypatch.setattr(server, "_sandbox_precheck",
                        lambda action, path, roots, source="server":
                        "path_outside_root (单测强制拒绝)" if action == "fs.write" else "")
    before = set(os.listdir(server._uploads_dir)) if os.path.isdir(server._uploads_dir) else set()
    r = client.post("/api/upload", files={"file": ("p24c.png", _PNG, "image/png")})
    assert r.status_code == 403 and "sandbox denied" in r.json()["error"]
    after = set(os.listdir(server._uploads_dir)) if os.path.isdir(server._uploads_dir) else set()
    assert before == after, "被拒绝的写入落盘了"


def test_d4_revert_gate_blocks_before_touching_the_file(sb, monkeypatch):
    """改动回滚：被拦时文件内容必须原封不动（绝不半途写坏）。"""
    probe = os.path.join(server._SERVER_ROOT, "_p24_revert_probe.txt")
    with open(probe, "w", encoding="utf-8", newline="") as fh:
        fh.write("after-text")
    rec = {"id": "c1", "path": probe, "revertible": True, "reverted": False,
           "_before_exists": True, "_before_text": "before-text",
           "sha_after": server._sha12("after-text")}
    session = {"changes": [rec]}
    monkeypatch.setattr(server, "_session_emit", lambda *a, **k: None)
    monkeypatch.setenv("MEMOMICS_SANDBOX_ENFORCE", "fs.write")
    try:
        ok_code, ok_body = server._revert_file_change(session, "c1")
        assert ok_code == 200 and ok_body.get("ok") is True
        with open(probe, encoding="utf-8") as fh:
            assert fh.read() == "before-text"
        assert any(i["action"] == "fs.write" and i["source"] == "changes.revert"
                   for i in sb.audit(50)["items"])

        # 再来一次：这次让门明确拒绝，文件必须保持 "before-text" 不变
        with open(probe, "w", encoding="utf-8", newline="") as fh:
            fh.write("after-text")
        rec2 = dict(rec, reverted=False, revertible=True)
        session["changes"] = [rec2]
        monkeypatch.setattr(server, "_sandbox_precheck",
                            lambda action, path, roots, source="server":
                            "path_outside_root (单测强制拒绝)")
        code, body = server._revert_file_change(session, "c1")
        assert code == 403 and "sandbox denied" in body["error"]
        with open(probe, encoding="utf-8") as fh:
            assert fh.read() == "after-text", "被拦的回滚改动了文件"
    finally:
        try:
            os.remove(probe)
        except Exception:
            pass


def test_d5_session_data_delete_is_gated(sb, monkeypatch):
    """会话数据删除：目标在 results/ 内 -> 放行并留痕；被拦 -> 如实报 failed 且目录还在。"""
    sid = "memomics-0a1b2c3d"
    target = os.path.join(server.RESULTS_DIR, sid)
    monkeypatch.setenv("MEMOMICS_SANDBOX_ENFORCE", "fs.delete")

    _mk(target)
    with open(os.path.join(target, "r.txt"), "w", encoding="utf-8") as fh:
        fh.write("x")
    out = asyncio.run(server._purge_session_results(sid))
    assert any(p.endswith(sid) for p in out["deleted"]), out
    assert not os.path.isdir(target)
    codes = [i["code"] for i in sb.audit(50)["items"] if i["action"] == "fs.delete"]
    assert "ok_callers_root" in codes

    _mk(target)
    monkeypatch.setattr(server, "_sandbox_precheck",
                        lambda action, path, roots, source="server":
                        "path_outside_root (单测强制拒绝)")
    out2 = asyncio.run(server._purge_session_results(sid))
    assert out2["deleted"] == [] and out2["failed"], out2
    assert "sandbox denied" in out2["failed"][0]["error"]
    assert os.path.isdir(target), "被拦的删除仍然把目录删了"
    shutil.rmtree(target, ignore_errors=True)


def _rename_target(sid):
    """服务端生成的目录名：species_tissue_direction_YYYYMMDD_短ID（都小写）。"""
    from datetime import datetime
    short = sid.split("-")[-1] if "-" in sid else sid[:6]
    return "homo_brain_rna_%s_%s" % (datetime.now().strftime("%Y%m%d"), short)


def test_d6_rename_results_user_root(client, new_session, sb, tmp_path, monkeypatch):
    """用户指定 output_root 的拷贝/删除：观察模式照旧（老洞），强制后拦下且一个文件都不动。"""
    sid = new_session
    out_root = _mk(str(tmp_path / "user_out"))
    body = {"species": "Homo", "tissue": "Brain", "direction": "RNA",
            "output_root": out_root}

    # 观察模式：老行为原样（该目录会被真的删掉重建），但审计必须记下 would_deny
    victim = _mk(os.path.join(out_root, _rename_target(sid)))
    with open(os.path.join(victim, "keep.txt"), "w", encoding="utf-8") as fh:
        fh.write("keep")
    monkeypatch.delenv("MEMOMICS_SANDBOX_ENFORCE", raising=False)
    r1 = client.post("/api/sessions/%s/rename-results" % sid, json=body)
    assert r1.status_code != 403, r1.text
    assert not os.path.exists(os.path.join(victim, "keep.txt")), "观察模式不该改变老行为"
    assert sb.audit(80)["counts"]["would_deny"] >= 1
    assert sb.audit(80)["counts"]["blocked"] == 0

    # 强制 fs.write + fs.delete：同一个请求必须被拦，且用户目录一个字节都不许动
    sb.reset()
    victim2 = _mk(os.path.join(out_root, _rename_target(sid)))
    with open(os.path.join(victim2, "keep.txt"), "w", encoding="utf-8") as fh:
        fh.write("keep2")
    snapshot = sorted(os.listdir(out_root))
    monkeypatch.setenv("MEMOMICS_SANDBOX_ENFORCE", "fs.write,fs.delete")
    results_before = server._sessions[sid]["results_dir"]
    r2 = client.post("/api/sessions/%s/rename-results" % sid, json=body)
    assert r2.status_code == 403, r2.text
    assert "sandbox denied" in r2.json()["error"]
    assert os.path.isfile(os.path.join(victim2, "keep.txt"))
    assert sorted(os.listdir(out_root)) == snapshot
    assert server._sessions[sid]["results_dir"] == results_before, "被拦的请求不该改会话状态"
    blocked = [i for i in sb.audit(80, codes=True)["items"] if i["blocked"]]
    assert blocked and any(i["action"] in ("fs.write", "fs.delete") for i in blocked)
    cleanup_session(sid)


# ====================================================== E. 运维逃生舱
def test_e1_grant_dirs_env(sb, tmp_path, monkeypatch):
    out_root = _mk(str(tmp_path / "declared"))
    monkeypatch.setenv("MEMOMICS_SANDBOX_ENFORCE", "fs.write,fs.delete")
    monkeypatch.setenv("MEMOMICS_SANDBOX_GRANT_DIRS", out_root)
    server._sandbox_env_grants()
    server._sandbox_env_grants()          # 幂等：第二次不该多出授权
    gl = SB.grants()
    assert {(g["action"], os.path.normcase(g["resource"])) for g in gl} == {
        ("fs.write", os.path.normcase(out_root)), ("fs.delete", os.path.normcase(out_root))}
    assert all(g["reason"] and g["ttl_left"] > 0 for g in gl)

    inside = os.path.join(out_root, "x.txt")
    assert server._sandbox_precheck("fs.write", inside, [server.RESULTS_DIR]) == ""
    other = os.path.join(str(tmp_path), "not_declared", "y.txt")
    assert server._sandbox_precheck("fs.write", other, [server.RESULTS_DIR]) != ""


def test_e2_grant_dirs_is_noop_in_observe(sb, tmp_path, monkeypatch):
    monkeypatch.setenv("MEMOMICS_SANDBOX_GRANT_DIRS", _mk(str(tmp_path / "d")))
    server._sandbox_env_grants()
    assert SB.grants() == []


def test_e3_precheck_never_raises(sb, monkeypatch):
    """沙箱内部炸了也必须放行——安全组件绝不能把正常功能打挂。"""
    def _boom(*a, **k):
        raise RuntimeError("boom")
    monkeypatch.setattr(SB, "gate", _boom)
    assert server._sandbox_precheck("fs.write", "E:/x", ["E:/"]) == ""


# ====================================================== F. 端到端
def test_f1_audit_endpoint_reports_partial(client, sb, monkeypatch):
    monkeypatch.setenv("MEMOMICS_SANDBOX_ENFORCE", "fs.write,fs.delete")
    r = client.get("/api/sandbox/audit", params={"limit": 1, "codes": 1})
    assert r.status_code == 200
    b = r.json()
    assert b["mode"] == "partial"
    assert b["enforce_actions"] == ["fs.delete", "fs.write"]
    assert b["enforce_unknown"] == []
    assert b["netguard"]["version"].startswith("p2-3b")
    assert "counts" in b and "codes" in b


def test_f2_observe_mode_is_the_default(client, sb):
    r = client.get("/api/sandbox/audit", params={"limit": 1})
    assert r.status_code == 200
    b = r.json()
    assert b["mode"] == "observe" and b["enforce"] is False and b["enforce_actions"] == []
