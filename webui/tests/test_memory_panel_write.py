# -*- coding: utf-8 -*-
"""记忆栏「追加 / 覆盖」写不进去 —— 限额真相源修复回归测试（2026-09-23）

现场（真机 8899 实测，改前）：
    POST /api/memory/write {"mode":"append","content":"一行"} -> 413
    {"error":"超出记忆限额：29557/10000 字符…","current":29530,"limit":10000}
MEMORY.md 已 29530 字符、USER.md 已 22039 字符，而 server.py 把限额**硬编码**成
10000（注释还声称"与 config.yaml 保持一致"），config.yaml 里其实写的是 30000。
=> 记忆栏的「追加」「覆盖」在这台机器上 100% 失败：用户说"添加没有用"。

这个文件锁死这条规则：**限额只认 config.yaml**，且绝不退回一个小数字。

  A. 限额解析：config 优先、读不到退默认 30000、0/垃圾值退默认、真机 config 值一致。
  B. 真实写入路径：老代码必 413 的场景现在要 200；超限额要 413 且**一个字节都不写**。
  C. 既有安全边界不回退：token 鉴权、只允许 .md。
  D. P2-4 沙箱接线：写/删动作过门；观察模式零变更，强制后越界 403 且不落盘。

纪律：全离线；临时 HERMES_HOME —— 绝不碰真机 memories/MEMORY.md、USER.md。
"""
import os

import pytest

import server
from webui import sandbox as SB


@pytest.fixture()
def tmp_home(tmp_path, monkeypatch):
    """临时 HERMES_HOME（token 与 memories/ 都落在 tmp，不碰真机记忆）。"""
    home = tmp_path / "hermes_home"
    (home / "memories").mkdir(parents=True)
    monkeypatch.setattr(server, "HERMES_HOME_DIR", str(home))
    return home


@pytest.fixture()
def mem_token(tmp_home):
    return server._memory_api_token()


@pytest.fixture()
def sb():
    """隔离 provider（不联网：假 DNS）+ 干净的强制环境。"""
    p = SB.SandboxProvider(name="memp", resolver=lambda h: ["93.184.216.34"], max_audit=500)
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


def _write(client, token, target, content, mode="append"):
    return client.post("/api/memory/write",
                       json={"target": target, "content": content, "mode": mode},
                       headers={"X-Memory-Token": token})


# --- A. 限额真相源 ---------------------------------------------------------

def test_a1_limit_comes_from_config(monkeypatch):
    monkeypatch.setattr(server, "_hermes_config_read",
                        lambda: ({"memory": {"memory_char_limit": 30000,
                                             "user_char_limit": 21000}}, {}))
    assert server._memory_char_limit("MEMORY.md") == 30000
    assert server._memory_char_limit("USER.md") == 21000


def test_a2_unreadable_config_falls_back_to_default_not_10k(monkeypatch):
    def _boom():
        raise RuntimeError("config.yaml 读不到")
    monkeypatch.setattr(server, "_hermes_config_read", _boom)
    # 关键：兜底值必须够大，绝不能退回曾经把写入全挡死的 10000
    assert server._memory_char_limit("MEMORY.md") == server._MEMORY_DEFAULT_LIMIT
    assert server._memory_char_limit("MEMORY.md") > 10000


def test_a3_zero_or_garbage_limit_falls_back(monkeypatch):
    monkeypatch.setattr(server, "_hermes_config_read",
                        lambda: ({"memory": {"memory_char_limit": 0}}, {}))
    assert server._memory_char_limit("MEMORY.md") == server._MEMORY_DEFAULT_LIMIT
    monkeypatch.setattr(server, "_hermes_config_read",
                        lambda: ({"memory": {"memory_char_limit": "abc"}}, {}))
    assert server._memory_char_limit("MEMORY.md") == server._MEMORY_DEFAULT_LIMIT
    monkeypatch.setattr(server, "_hermes_config_read", lambda: ({}, {}))
    assert server._memory_char_limit("USER.md") == server._MEMORY_DEFAULT_LIMIT


def test_a4_real_config_matches_real_limit():
    """真机回归：真 config.yaml 的 memory_char_limit 必须等于接口实际限额。"""
    cfg_path = os.path.join(server.HERMES_HOME_DIR, "config.yaml")
    if not os.path.isfile(cfg_path):
        pytest.skip("无 config.yaml（CI/安装包环境）")
    cfg, _raw = server._hermes_config_read()
    want = int(((cfg or {}).get("memory") or {}).get("memory_char_limit", 0) or 0)
    if want <= 0:
        pytest.skip("config.yaml 没写 memory_char_limit")
    assert server._memory_char_limit("MEMORY.md") == want
    # 这条就是当初的病灶：硬编码 10000 远小于 config 声明的值
    assert want > 10000


# --- B. 真实写入路径 -------------------------------------------------------

def test_b1_append_works_on_a_file_already_over_10k(client, tmp_home, mem_token):
    """老代码必 413 的场景（文件 29530 字符 + 小追加）现在必须成功。"""
    p = tmp_home / "memories" / "MEMORY.md"
    p.write_text("条" * 29530, encoding="utf-8")
    r = _write(client, mem_token, "MEMORY.md", "新增一行", "append")
    assert r.status_code == 200, r.text
    assert r.json()["ok"] is True
    assert "新增一行" in p.read_text(encoding="utf-8")
    assert r.json()["size"] == os.path.getsize(str(p))


def test_b2_over_limit_is_413_and_writes_nothing(client, tmp_home, mem_token):
    p = tmp_home / "memories" / "MEMORY.md"
    p.write_text("条" * 29990, encoding="utf-8")
    before = p.read_text(encoding="utf-8")
    r = _write(client, mem_token, "MEMORY.md", "x" * 40, "append")
    assert r.status_code == 413
    b = r.json()
    assert b["limit"] == server._MEMORY_DEFAULT_LIMIT
    assert b["current"] == 29990
    assert "config.yaml" in b["error"]          # 报错要能指路，不能只说"超限"
    assert p.read_text(encoding="utf-8") == before   # 一个字节都没写


def test_b3_overwrite_up_to_limit_works(client, tmp_home, mem_token):
    """覆盖路径同样受限额管：20000 字符（老代码 413）现在要成功且内容精确。"""
    p = tmp_home / "memories" / "MEMORY.md"
    p.write_text("旧" * 50000, encoding="utf-8")
    r = _write(client, mem_token, "MEMORY.md", "新" * 20000, "overwrite")
    assert r.status_code == 200, r.text
    assert p.read_text(encoding="utf-8") == "新" * 20000


def test_b4_config_limit_really_governs(monkeypatch, client, tmp_home, mem_token):
    """把 config 改成 5000：6000 要 413、4000 要 200 —— 证明数值真的跟着 config 走。"""
    monkeypatch.setattr(server, "_hermes_config_read",
                        lambda: ({"memory": {"memory_char_limit": 5000}}, {}))
    r = _write(client, mem_token, "MEMORY.md", "y" * 6000, "overwrite")
    assert r.status_code == 413 and r.json()["limit"] == 5000
    r = _write(client, mem_token, "MEMORY.md", "y" * 4000, "overwrite")
    assert r.status_code == 200
    assert "y" * 4000 in (tmp_home / "memories" / "MEMORY.md").read_text(encoding="utf-8")


def test_b5_append_then_read_back(client, tmp_home, mem_token):
    """端到端：写进去的内容，GET /api/memory 立刻能读到（页面刷新即见）。"""
    assert _write(client, mem_token, "MEMORY.md", "记忆：今天在做记忆栏", "append").status_code == 200
    assert _write(client, mem_token, "USER.md", "偏好：先给结论", "append").status_code == 200
    d = client.get("/api/memory").json()
    assert "偏好：先给结论" in d["user"]
    names = [e["name"] for e in d["entries"]]
    assert "USER.md" in names and "MEMORY.md" in names


# --- C. 既有安全边界不回退 ------------------------------------------------

def test_c1_token_required(client, tmp_home):
    assert client.post("/api/memory/write",
                       json={"target": "MEMORY.md", "content": "x", "mode": "append"}).status_code == 401
    assert _write(client, "deadbeef" * 5, "MEMORY.md", "x", "append").status_code == 401
    assert not (tmp_home / "memories" / "MEMORY.md").exists()


def test_c2_only_md_files(client, tmp_home, mem_token):
    assert _write(client, mem_token, "config.yaml", "x", "overwrite").status_code == 400
    assert not (tmp_home / "memories" / "config.yaml").exists()


# --- D. P2-4 沙箱接线 -----------------------------------------------------

def test_d1_write_passes_the_gate_and_denies_outside_roots(sb, monkeypatch, client, tmp_home, mem_token):
    # 观察模式：正常写，判定记账
    assert _write(client, mem_token, "MEMORY.md", "观察模式写入", "append").status_code == 200
    # 观察模式契约：判定照算（越界 allow=False）、但 blocked=False —— 一个字节都不拦
    hits = [i for i in sb.audit(50)["items"] if i["source"] == "memory.write"]
    assert hits and hits[-1]["action"] == "fs.write" and hits[-1]["blocked"] is False
    # 强制 fs.write 且临时 HERMES_HOME 在真根之外 -> 403 且不落盘
    os.environ["MEMOMICS_SANDBOX_ENFORCE"] = "fs.write"
    p = tmp_home / "memories" / "USER.md"
    r = _write(client, mem_token, "USER.md", "不该落盘", "overwrite")
    assert r.status_code == 403, r.text
    assert "sandbox denied" in r.json()["error"]
    assert "不该落盘" not in (p.read_text(encoding="utf-8") if p.exists() else "")
    blocked = [i for i in sb.audit(50)["items"] if i["source"] == "memory.write" and i["blocked"]]
    assert blocked and blocked[-1]["action"] == "fs.write" and blocked[-1]["allow"] is False


def test_d2_delete_passes_the_gate_and_denies_outside_roots(sb, monkeypatch, client, tmp_home, mem_token):
    p = tmp_home / "memories" / "USER.md"
    p.write_text("待删", encoding="utf-8")
    # 观察模式：照删，判定记账
    assert client.delete("/api/memory/USER.md",
                         headers={"X-Memory-Token": mem_token}).status_code == 200
    hits = [i for i in sb.audit(50)["items"] if i["source"] == "memory.delete"]
    assert hits and hits[-1]["action"] == "fs.delete"
    # 强制 fs.delete 且越界 -> 403，文件必须还在
    p.write_text("保住", encoding="utf-8")
    os.environ["MEMOMICS_SANDBOX_ENFORCE"] = "fs.delete"
    r = client.delete("/api/memory/USER.md", headers={"X-Memory-Token": mem_token})
    assert r.status_code == 403 and p.read_text(encoding="utf-8") == "保住"
    blocked = [i for i in sb.audit(50)["items"] if i["source"] == "memory.delete" and i["blocked"]]
    assert blocked and blocked[-1]["allow"] is False and p.exists()
