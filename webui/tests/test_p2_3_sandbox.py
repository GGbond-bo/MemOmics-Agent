# -*- coding: utf-8 -*-
"""P2-3 SandboxProvider 聚焦测试（2026-09-23）

分五层：
  A. 默认拒绝与授权生命周期（TTL / revoke / 兄弟前缀 / 只读授权）
  B. 路径逃逸极端（.. / 符号链接与 junction / 相对路径 / NUL / ADS / 保留设备名 / 盘符相对 / 大小写 / UNC）
  C. 网络与反 rebinding（scheme / userinfo / 环回 / 链路本地 / 私网 / 保留段 / 多地址全公网 / 解析翻转 / DNS 失败 / IPv6 zone）
  D. 门与模式（观察不改行为、强制真拦、整体关、审计有界、审计脱敏、线程安全、重置）
  E. 与真实 server/security.py 的集成（默认行为不变；强制模式下多拦一类）

纪律：全离线。DNS 通过注入 resolver 完成，唯一真实解析用 localhost（走 hosts，不出网）。
"""
import os
import subprocess
import threading
import time

import pytest

from conftest import cleanup_session
import server
from webui import sandbox as SB
from webui import security

PUB = "93.184.216.34"          # example.com 的真实公网地址（写死，避免联网）


class FakeClock:
    def __init__(self, t=1_700_000_000.0):
        self.t = t

    def __call__(self):
        return self.t

    def advance(self, dt):
        self.t += dt
        return self.t


class FakeResolver:
    """可编程 DNS：默认返回一个公网地址；表里可放列表、空列表或异常。"""

    def __init__(self, table=None, default=(PUB,)):
        self.table = dict(table or {})
        self.default = tuple(default)
        self.calls = []

    def __call__(self, host):
        self.calls.append(host)
        if host in self.table:
            val = self.table[host]
            if isinstance(val, BaseException):
                raise val
            return list(val)
        return list(self.default)


@pytest.fixture()
def sb():
    """一个隔离的 provider + 一张干净的假 DNS；结束恢复进程级门面。"""
    clock = FakeClock()
    resolver = FakeResolver()
    p = SB.SandboxProvider(name="unit", clock=clock, resolver=resolver, max_audit=100)
    old = SB.set_provider(p)
    try:
        yield p
    finally:
        SB.set_provider(old)
        SB.reset()


def _mk(path):
    os.makedirs(path, exist_ok=True)
    return path


def _make_escape(tmp_path):
    """在 root 里造一条指向 outside 的链接（Windows 无权限时退回 junction）。"""
    outside = _mk(str(tmp_path / "outside"))
    with open(os.path.join(outside, "secret.txt"), "w", encoding="utf-8") as fh:
        fh.write("topsecret")
    root = _mk(str(tmp_path / "root"))
    link = os.path.join(root, "escape")
    how = "symlink"
    try:
        os.symlink(outside, link, target_is_directory=True)
    except Exception:
        how = "junction"
        r = subprocess.run(["cmd", "/c", "mklink", "/J", link, outside],
                           capture_output=True, text=True)
        if r.returncode != 0:
            pytest.skip("本机既不能建符号链接也不能建 junction：%s" % (r.stdout or r.stderr))
    return root, os.path.join(link, "secret.txt"), how


# ====================================================== A. 默认拒绝 / 授权生命周期
def test_a1_default_deny_everything(sb):
    assert sb.check("fs.read", "E:/whatever/a.txt").code == "no_grant"
    assert sb.check("fs.write", "E:/whatever/a.txt").code == "no_grant"
    assert sb.check("net.fetch", "https://example.com/x").code == "no_grant"
    assert sb.check("os.reboot", "x").code == "unknown_action"
    assert sb.check("proc.exec", "rm -rf /").code == "action_not_implemented"
    d = sb.check("fs.read", "E:/whatever/a.txt")
    assert d.allow is False and d.blocked is False        # 观察模式：不算拦
    assert sb.stats()["grants"] == 0


def test_a2_grant_then_revoke_then_expire(sb):
    g = sb.grant("fs.read", "E:/data", ttl_s=100, reason="用户导入")
    assert sb.check("fs.read", "E:/data/a.csv").code == "ok_grant"
    assert sb.check("fs.read", "E:/data/sub/b.csv").code == "ok_grant"
    assert g.hits == 2
    assert sb.revoke(g.token) is True
    assert sb.check("fs.read", "E:/data/a.csv").code == "no_grant"
    g2 = sb.grant("fs.read", "E:/data", ttl_s=10)
    sb._clock.advance(11)                                  # 时钟注入：离线验 TTL
    assert sb.check("fs.read", "E:/data/a.csv").code == "grant_expired"
    assert sb.purge_expired() == 1
    assert sb.stats()["counts"]["expired"] == 1


def test_a3_grant_is_not_a_string_prefix(sb):
    sb.grant("fs.read", "E:/data", ttl_s=100)
    assert sb.check("fs.read", "E:/data2/secret").code == "no_grant"
    assert sb.check("fs.read", "E:/data-old/x").code == "no_grant"
    assert sb.check("fs.read", "E:/data/../data2/x").code == "no_grant"


def test_a4_write_needs_write_semantics(sb):
    sb.grant("fs.write", "E:/out", ttl_s=100, writable=False)
    assert sb.check("fs.write", "E:/out/x.csv").code == "no_grant"   # 只读授权不覆盖写
    assert sb.check("fs.read", "E:/out/x.csv").code == "no_grant"    # 动作不同也不覆盖
    sb.grant("fs.read", "E:/out", ttl_s=100)
    assert sb.check("fs.read", "E:/out/x.csv").code == "ok_grant"


def test_a5_bad_grant_arguments(sb):
    with pytest.raises(ValueError):
        sb.grant("os.reboot", "E:/x")
    with pytest.raises(ValueError):
        sb.grant("fs.read", "")
    with pytest.raises(ValueError):
        sb.grant("fs.read", "E:/x", ttl_s=0)


# ====================================================== B. 路径逃逸极端
def test_b1_dotdot_escape(tmp_path, sb):
    root = _mk(str(tmp_path / "root"))
    outside = _mk(str(tmp_path / "outside"))
    with open(os.path.join(outside, "secret.txt"), "w", encoding="utf-8") as fh:
        fh.write("s")
    d = sb.check("fs.read", os.path.join(root, "..", "outside", "secret.txt"), roots=[root])
    assert d.allow is False and d.code == "path_outside_root"
    assert sb.check("fs.read", os.path.join(root, "a.txt"), roots=[root]).code == "ok_callers_root"


def test_b2_symlink_escape(tmp_path, sb):
    root, escaped, how = _make_escape(tmp_path)
    d = sb.check("fs.read", escaped, roots=[root])
    assert d.allow is False, "符号链接/junction 逃逸没被拦住（%s）" % how
    assert d.code == "path_outside_root"
    # 同样的路径，把 outside 声明成根就应该放行——证明是 realpath 解析而不是按字面拒绝
    outside = os.path.join(str(tmp_path), "outside")
    assert sb.check("fs.read", escaped, roots=[outside]).code == "ok_callers_root"


def test_b3_path_shape_rejects(sb):
    assert sb.check("fs.read", None).code == "path_bad_type"
    assert sb.check("fs.read", "").code == "path_bad_type"
    assert sb.check("fs.read", "   ").code == "path_bad_type"
    assert sb.check("fs.read", 123).code == "path_bad_type"
    assert sb.check("fs.read", "relative/x.txt").code == "path_not_absolute"
    assert sb.check("fs.read", "E:/data/a\x00.txt").code == "path_null_byte"


@pytest.mark.skipif(os.name != "nt", reason="Windows 专属路径语义")
def test_b4_windows_quirks(tmp_path, sb):
    root = _mk(str(tmp_path / "root"))
    assert sb.check("fs.read", "C:temp\\x.txt", roots=[root]).code == "path_drive_relative"
    assert sb.check("fs.read", os.path.join(root, "a.txt:evil"), roots=[root]).code == "path_ads"
    for bad in ("NUL", "CON", "COM1", "lpt9.txt", "aux"):
        assert sb.check("fs.read", os.path.join(root, bad), roots=[root]).code == \
            "path_reserved_device", bad


def test_b5_case_and_separator_insensitive_on_windows(tmp_path, sb):
    root = _mk(str(tmp_path / "Data"))
    d = sb.check("fs.read", str(tmp_path / "data" / "x.txt"), roots=[root])
    if os.name == "nt":
        assert d.allow is True, "Windows 大小写不敏感没处理：%s" % d.code
    else:
        assert d.allow is False
    weird = str(root).replace(os.sep, os.sep + os.sep) + os.sep + "." + os.sep + "x.txt"
    assert sb.check("fs.read", weird, roots=[root]).allow is True


def test_b6_home_expansion_and_unc(tmp_path, sb):
    home = os.path.expanduser("~")
    assert sb.check("fs.read", os.path.join("~", "x.txt"), roots=[home]).allow is True
    if os.name == "nt":
        assert sb.check("fs.read", "\\\\server\\share\\x", roots=[home]).code in (
            "path_outside_root", "path_unresolvable")


def test_b7_roots_must_be_real_otherwise_deny(tmp_path, sb):
    assert sb.check("fs.read", str(tmp_path / "a.txt"), roots=[]).code == "no_grant"
    assert sb.check("fs.read", str(tmp_path / "a.txt"), roots=["", None]).code == "no_grant"


# ====================================================== C. 网络 / 反 rebinding
def test_c1_scheme_whitelist(sb):
    for bad in ("ftp://example.com/x", "file:///etc/passwd", "gopher://example.com/",
                "javascript:alert(1)", "data:text/plain,hi", "//example.com/x", ""):
        assert sb.check("net.fetch", bad).code in ("url_bad_scheme", "url_bad_type", "url_no_host"), bad


def test_c2_userinfo_and_missing_host(sb):
    assert sb.check("net.fetch", "http://user:pass@example.com/").code == "url_userinfo"
    assert sb.check("net.fetch", "https://@example.com/").code == "url_userinfo"
    assert sb.check("net.fetch", "http:///nohost").code == "url_no_host"


def test_c3_non_public_literals(sb):
    cases = {
        "http://127.0.0.1:8899/api/version": "url_loopback",
        "http://127.1.2.3/": "url_loopback",
        "http://[::1]/": "url_loopback",
        "http://169.254.169.254/latest/meta-data/": "url_link_local",
        "http://[fe80::1]/": "url_link_local",
        "http://10.0.0.7/": "url_private",
        "http://172.16.5.5/": "url_private",
        "http://192.168.1.1/": "url_private",
        "http://[fd00::1]/": "url_private",
        "http://0.0.0.0/": "url_reserved",
        "http://100.64.0.1/": "url_not_global",
        "http://224.0.0.1/": "url_multicast",
    }
    for url, code in cases.items():
        got = sb.check("net.fetch", url)
        assert got.code == code, "%s → %s（期望 %s）" % (url, got.code, code)
        assert got.allow is False


def test_c4_alternative_ip_encodings(sb):
    sb._resolver.table["2130706433"] = ["127.0.0.1"]
    sb._resolver.table["0x7f000001"] = ["127.0.0.1"]
    sb._resolver.table["0177.0.0.1"] = ["127.0.0.1"]
    assert sb.check("net.fetch", "http://2130706433/").code == "url_loopback"
    assert sb.check("net.fetch", "http://0x7f000001/").code == "url_loopback"
    assert sb.check("net.fetch", "http://0177.0.0.1/").code == "url_loopback"


def test_c5_all_resolved_addresses_must_be_public(sb):
    """多地址解析（DNS 轮询 / 双栈）里只要有一个内网地址，整条拒绝——这就是反 rebinding 的根。"""
    sb._resolver.table["evil.example"] = [PUB, "10.0.0.5"]
    d = sb.check("net.fetch", "https://evil.example/x")
    assert d.code == "url_private" and d.allow is False
    assert d.pinned_ips == sorted([PUB, "10.0.0.5"])       # 判定仍把真解析结果带出来
    sb._resolver.table["ok.example"] = [PUB, "2606:4700::1111"]
    sb.grant("net.fetch", "ok.example", ttl_s=100)
    assert sb.check("net.fetch", "https://ok.example/x").code == "ok_grant"


def test_c6_rebinding_after_pin(sb):
    sb.grant("net.fetch", "example.com", ttl_s=1000)
    first = sb.check("net.fetch", "https://example.com/a")
    assert first.allow is True and first.pinned_ips == [PUB]
    sb._resolver.table["example.com"] = ["10.0.0.5"]       # DNS 被换成内网
    second = sb.check("net.fetch", "https://example.com/a", pinned_ips=first.pinned_ips)
    assert second.allow is False and second.code == "url_private"
    sb._resolver.table["example.com"] = ["1.1.1.1"]        # 换成另一个公网地址
    third = sb.check("net.fetch", "https://example.com/a", pinned_ips=first.pinned_ips)
    assert third.allow is False and third.code == "url_rebinding"


def test_c7_dns_failure_and_empty(sb):
    sb._resolver.table["boom.example"] = ValueError("dns exploded")
    sb._resolver.table["empty.example"] = []
    assert sb.check("net.fetch", "https://boom.example/").code == "url_dns_fail"
    assert sb.check("net.fetch", "https://empty.example/").code == "url_dns_fail"


def test_c8_host_matching_and_case(sb):
    sb.grant("net.fetch", "example.com", ttl_s=100)
    assert sb.check("net.fetch", "HTTPS://EXAMPLE.COM/A").code == "ok_grant"
    assert sb.check("net.fetch", "https://example.com./a").code == "ok_grant"
    assert sb.check("net.fetch", "https://a.example.com/a").code == "ok_grant"
    assert sb.check("net.fetch", "https://example.com.evil.com/a").code == "no_grant"
    assert sb.check("net.fetch", "https://notexample.com/a").code == "no_grant"
    sb.grant("net.fetch", "sub.other.com", ttl_s=100)
    assert sb.check("net.fetch", "https://x.sub.other.com/").code == "ok_grant"


def test_c9_ipv6_public_and_zone_id(sb):
    sb.grant("net.fetch", "2606:4700::1111", ttl_s=100)
    assert sb.check("net.fetch", "https://[2606:4700::1111]/x").code == "ok_grant"
    assert sb.check("net.fetch", "https://[fe80::1%25eth0]/x").code == "url_zone_id"


def test_c10_real_resolver_localhost_is_blocked():
    """唯一一条走真解析的用例：localhost 走 hosts 文件，不出网。"""
    p = SB.SandboxProvider(name="real-dns")
    d = p.check("net.fetch", "http://localhost:8899/api/version")
    assert d.allow is False and d.code in ("url_loopback", "url_dns_fail")


def test_c11_audit_strips_query_string():
    p = SB.SandboxProvider(name="redact", resolver=FakeResolver())
    p.gate("net.fetch", "https://example.com/path?token=SUPERSECRET&x=1")
    items = p.audit(5)["items"]
    assert items and "SUPERSECRET" not in items[0]["resource"]
    assert items[0]["resource"].endswith("/path")


# ====================================================== D. 门 / 模式 / 审计
def test_d1_observe_never_blocks_enforce_does(sb, monkeypatch):
    monkeypatch.delenv("MEMOMICS_SANDBOX_ENFORCE", raising=False)
    d = sb.gate("fs.read", "E:/nope/secret")
    assert d.allow is False and d.blocked is False
    assert sb.stats()["counts"]["would_deny"] == 1
    monkeypatch.setenv("MEMOMICS_SANDBOX_ENFORCE", "1")
    d2 = sb.gate("fs.read", "E:/nope/secret")
    assert d2.blocked is True and d2.mode == "enforce"
    assert sb.stats()["counts"]["blocked"] == 1
    with pytest.raises(SB.SandboxDenied) as ei:
        sb.require("fs.read", "E:/nope/secret")
    assert ei.value.code == "no_grant"


def test_d2_module_can_be_disabled(sb, monkeypatch):
    monkeypatch.setenv("MEMOMICS_SANDBOX", "0")
    assert SB.enabled() is False
    d = sb.gate("fs.read", "E:/nope/secret")
    assert d.allow is True and d.code == "disabled" and d.blocked is False
    assert sb.stats()["counts"]["disabled"] == 1
    monkeypatch.setenv("MEMOMICS_SANDBOX", "1")
    assert SB.enabled() is True


def test_d3_audit_is_bounded_and_newest_first():
    p = SB.SandboxProvider(name="ring", resolver=FakeResolver(), max_audit=10)
    for i in range(50):
        p.gate("fs.read", "E:/x/%d.txt" % i)
    body = p.audit(100, codes=True)
    assert body["total"] == 10 and body["max"] == 10
    assert body["items"][0]["resource"].endswith("49.txt")
    assert body["items"][-1]["resource"].endswith("40.txt")
    # items 是有界环形缓冲（只留最近 10 条），codes 是**全生命周期**累计计数——
    # 两者故意不同：排查"现在发生了什么"看 items，看"整体拦了多少"看 codes。
    assert body["codes"]["no_grant"] == 50
    assert p.audit(5)["items"][0]["seq"] == 50


def test_d4_audit_records_context(sb):
    sb.grant("fs.read", "E:/data", ttl_s=100, reason="导入")
    sb.gate("fs.read", "E:/data/a.csv", sid="memomics-abcd1234", source="security.resolve_within_roots")
    item = sb.audit(1)["items"][0]
    assert item["allow"] is True and item["code"] == "ok_grant"
    assert item["sid"] == "memomics-abcd1234"
    assert item["source"] == "security.resolve_within_roots"
    assert item["grant"].startswith("fsread-")
    assert item["dur_ms"] >= 0 and item["mode"] == "observe"


def test_d5_thread_safety():
    p = SB.SandboxProvider(name="mt", resolver=FakeResolver(), max_audit=5000)
    p.grant("fs.read", "E:/data", ttl_s=1000)
    errors = []
    barrier = threading.Barrier(8)

    def worker(idx):
        try:
            barrier.wait(timeout=10)
            for i in range(200):
                if i % 3:
                    p.gate("fs.read", "E:/data/%d-%d.txt" % (idx, i))
                else:
                    p.gate("fs.read", "E:/nope/%d-%d.txt" % (idx, i))
        except Exception as exc:            # pragma: no cover
            errors.append(repr(exc))

    ths = [threading.Thread(target=worker, args=(i,)) for i in range(8)]
    for t in ths:
        t.start()
    for t in ths:
        t.join(timeout=60)
    assert not errors, errors
    c = p.stats()["counts"]
    assert c["allow"] + c["deny"] == 1600
    assert c["would_deny"] == p.audit(5000, codes=True)["codes"].get("no_grant", 0)
    assert p.audit(5000)["total"] == 1600


def test_d7_mode_is_self_describing(sb, monkeypatch):
    monkeypatch.delenv("MEMOMICS_SANDBOX_ENFORCE", raising=False)
    assert SB.sandbox_mode() == "observe"
    assert sb.audit(1)["mode"] == "observe" and sb.stats()["mode"] == "observe"
    monkeypatch.setenv("MEMOMICS_SANDBOX_ENFORCE", "1")
    assert SB.sandbox_mode() == "enforce" and sb.audit(1)["mode"] == "enforce"
    monkeypatch.setenv("MEMOMICS_SANDBOX", "0")
    assert SB.sandbox_mode() == "disabled" and sb.stats()["mode"] == "disabled"


def test_d6_reset_and_grant_listing(sb):
    g = sb.grant("fs.read", "E:/data", ttl_s=100, reason="r")
    assert sb.grants()[0]["token"] == g.token
    sb.gate("fs.read", "E:/data/a")
    sb.reset()
    assert sb.stats()["grants"] == 0 and sb.stats()["audited"] == 0
    assert sb.stats()["counts"]["allow"] == 0
    body = sb.audit(10)
    assert body["items"] == [] and body["grants"] == []


# ====================================================== E. 与真实 server / security.py 集成
def test_e1_security_helper_behaviour_unchanged(tmp_path, sb, monkeypatch):
    monkeypatch.delenv("MEMOMICS_SANDBOX_ENFORCE", raising=False)
    root = _mk(str(tmp_path / "root"))
    inside = os.path.join(root, "a.txt")
    with open(inside, "w", encoding="utf-8") as fh:
        fh.write("hi")
    assert str(security.resolve_within_roots(inside, [root])) == os.path.realpath(inside)
    with pytest.raises(security.UnsafePathError):
        security.resolve_within_roots(os.path.join(str(tmp_path), "nope.txt"), [root])
    with pytest.raises(security.UnsafePathError):
        security.resolve_relative_path(root, "../nope.txt")
    body = sb.audit(20, codes=True)
    assert body["total"] >= 3, "沙箱没观察到任何真实调用"
    assert body["codes"].get("path_outside_root", 0) >= 1


def test_e2_enforce_blocks_new_class_but_observe_does_not(tmp_path, sb, monkeypatch):
    """同一路径：观察模式照旧放行（行为零变更），强制模式被拦（新增防护）。"""
    root = _mk(str(tmp_path / "root"))
    weird = os.path.join(root, "NUL")            # 根内，但是 Windows 保留设备名
    monkeypatch.delenv("MEMOMICS_SANDBOX_ENFORCE", raising=False)
    assert str(security.resolve_within_roots(weird, [root]))     # 观察：不拦
    monkeypatch.setenv("MEMOMICS_SANDBOX_ENFORCE", "1")
    with pytest.raises(security.UnsafePathError):
        security.resolve_within_roots(weird, [root])             # 强制：拦
    assert sb.audit(5, codes=True)["codes"].get("path_reserved_device", 0) >= 1


def test_e3_real_endpoints_still_work(client, tmp_path, sb):
    """/api/file/read 与 /api/papers 的老路径在默认设置下完全不变。"""
    inside = None
    for cand in (server.WORK_DIR, server.RESULTS_DIR, server.MEMOMICS_DIR):
        try:
            os.makedirs(cand, exist_ok=True)
            p = os.path.join(cand, "_p23_probe.txt")
            with open(p, "w", encoding="utf-8") as fh:
                fh.write("p23")
            inside = p
            break
        except Exception:
            continue
    if inside is None:                                  # pragma: no cover
        pytest.skip("没有可写的根目录")
    try:
        r = client.get("/api/file/read", params={"path": inside})
        assert r.status_code == 200 and r.json()["content"] == "p23"
        r2 = client.get("/api/file/read", params={"path": os.path.join(str(tmp_path), "x.txt")})
        assert r2.status_code == 403                    # 老行为：根外一律 403
        body = sb.audit(50)
        assert body["total"] >= 2, "真实端点调用没有进沙箱审计"
    finally:
        try:
            os.remove(inside)
        except Exception:
            pass
