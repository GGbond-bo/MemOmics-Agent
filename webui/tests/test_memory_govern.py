# -*- coding: utf-8 -*-
"""记忆栏「治理」点了等于没点 —— 体检 + 归档通道回归测试（2026-09-24）

现场（真机 8899 实测，改前）：
    POST /api/memory/govern -> 200 {"ok":true,"stats":{"L1":270,"L2":0,"L3":0}}
    （路由只调 governor.init_index()：重算分数 + 写索引，一条都不搬）
而唯一会搬条目的 run_governance 判据是 score<0.3 才下沉 L2 —— 实测本机 219 条记忆
分数全在 0.3~0.475，达标 0 条 => 即使接上 apply 也永远搬不动。
同时 MEMORY.md 已 29530 字符（限额 30000），写什么都顶格。

这个文件锁死新契约：
  A. survey() 是只读体检：占用/余量、分层、分数分布、可归档候选、预计释放字符。
  B. archive_low_value() 真腾地方：归档到 archive/YYYY-MM.md + 原位置留一行索引，
     动前整档备份；内容永不删除；可重复执行（幂等）；超比例先拒绝。
  C. 只碰"自己标了低价值"的条目：带正式元数据的条目（有 pinned 语义）一律不动；
     短到换索引行反而变长的条目也不动（MIN_FREE_GAIN）。
  D. 路由语义：无 body / mode=dry 只读；mode=apply 需 token；被比例守卫拦返回 409。

纪律：全离线；HERMES_HOME 与 governor 的目录常量都指到 tmp —— 绝不碰真机记忆文件。
"""
import json
import os

import pytest

import server


@pytest.fixture()
def tmp_home(tmp_path, monkeypatch):
    home = tmp_path / "hermes_home"
    (home / "memories").mkdir(parents=True)
    monkeypatch.setattr(server, "HERMES_HOME_DIR", str(home))
    return home


@pytest.fixture()
def gov(tmp_home, monkeypatch):
    """governor 的目录常量全部指到 tmp（函数内部读的是模块全局，patch 后即生效）。"""
    from memomics.memory_governance import governor as G
    mem = tmp_home / "memories"
    monkeypatch.setattr(G, "MEMORIES_DIR", str(mem))
    monkeypatch.setattr(G, "INDEX_PATH", str(mem / "index.json"))
    monkeypatch.setattr(G, "ARCHIVE_DIR", str(mem / "archive"))
    monkeypatch.setattr(G, "MEMORY_FILE", str(mem / "MEMORY.md"))
    monkeypatch.setattr(G, "USER_FILE", str(mem / "USER.md"))
    monkeypatch.setattr(G, "BACKUP_DIR", str(mem / ".backup"))
    return G


@pytest.fixture()
def mem_token(tmp_home):
    return server._memory_api_token()


@pytest.fixture()
def sb():
    """隔离 sandbox provider（不联网）—— 与 test_memory_panel_write.py 同款。"""
    from webui import sandbox as SB
    p = SB.SandboxProvider(name="govp", resolver=lambda h: ["93.184.216.34"], max_audit=500)
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


LIMITS = {"MEMORY.md": 60000, "USER.md": 60000}


def _write_file(path, entries):
    """写成真机同款结构：头部（# + 注释）+ § 分隔的条目块。

    注意头部后面必须有 § —— parse_entries 按 "\n§\n" 切块，头部所在块以 "# " 开头
    会被整块跳过；缺这个 § 会把第一条真实条目吞进头部（测试里踩过）。
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("# Memory\n<!-- test -->\n\n§\n" + "\n§\n".join(entries) + "\n",
                    encoding="utf-8")


def _entry(imp, name, tail=None):
    """造一条够长的条目（长到换索引行确实能腾出地方）+ 结尾唯一标记。"""
    body = "细节段落" * 24
    return "[imp:%s] %s %s #TAIL-%s#" % (imp, name, body, tail or name)


def _seed(tmp_home):
    """MEMORY.md: 3 条（imp 0.6 / 0.7 / 无标记）；USER.md: 2 条（0.9 / 无标记）。"""
    mem = tmp_home / "memories" / "MEMORY.md"
    usr = tmp_home / "memories" / "USER.md"
    _write_file(mem, [_entry(0.6, "低价值笔记A"), _entry(0.7, "低价值笔记B"),
                      "普通条目C没有标注 " + "细节段落" * 24])
    _write_file(usr, [_entry(0.9, "用户铁律D"), "普通偏好E没有标注 " + "细节段落" * 24])
    return mem, usr


# --- A. survey 只读体检 ----------------------------------------------------

def test_a1_survey_reports_candidates_and_usage(gov, tmp_home):
    mem, usr = _seed(tmp_home)
    sv = gov.survey(0.7, LIMITS)
    assert sv["total_entries"] == 5
    assert sv["files"]["MEMORY.md"]["chars"] == len(mem.read_text(encoding="utf-8"))
    assert sv["files"]["MEMORY.md"]["limit"] == 60000
    assert sv["files"]["MEMORY.md"]["pct"] == round(
        100.0 * len(mem.read_text(encoding="utf-8")) / 60000, 1)
    got = {(c["target"], c["imp"]) for c in sv["candidates"]}
    assert got == {("MEMORY.md", 0.6), ("MEMORY.md", 0.7)}   # 0.9 与无标注不入选
    assert sv["freed_estimate"] > 0
    assert all(c["freed"] >= sv["min_free_gain"] for c in sv["candidates"])
    assert sv["guard"]["ok"] is True
    assert "score<0.3" in sv["note"]


def test_a2_survey_never_writes(gov, tmp_home):
    mem, usr = _seed(tmp_home)
    before_m, before_u = mem.read_bytes(), usr.read_bytes()
    gov.survey(0.7, LIMITS)
    rep = gov.archive_low_value(threshold=0.7, dry_run=True, limits=LIMITS)
    assert rep["dry_run"] is True and rep["freed"] > 0
    assert mem.read_bytes() == before_m and usr.read_bytes() == before_u
    assert not (tmp_home / "memories" / "archive").exists()
    assert not (tmp_home / "memories" / ".backup").exists()


def test_a3_missing_files_do_not_crash(gov, tmp_home):
    sv = gov.survey(0.7, LIMITS)          # tmp 下没有任何 .md
    assert sv["total_entries"] == 0 and sv["candidates"] == []
    rep = gov.archive_low_value(threshold=0.7, dry_run=False, limits=LIMITS)
    assert rep["ok"] is True and rep["archived"] == []


# --- B. apply 真腾地方 -----------------------------------------------------

def test_b1_apply_archives_replaces_and_backs_up(gov, tmp_home):
    mem, usr = _seed(tmp_home)
    before_m = mem.read_text(encoding="utf-8")
    before_bytes = mem.read_bytes()
    rep = gov.archive_low_value(threshold=0.7, dry_run=False, limits=LIMITS)
    assert rep["ok"] is True and rep["dry_run"] is False
    assert [c["imp"] for c in rep["archived"]] == [0.6, 0.7]
    # 原文件：被归档条目整条消失、留一行索引（parse_entries 会跳过它）
    after_m = mem.read_text(encoding="utf-8")
    assert "#TAIL-低价值笔记A#" not in after_m
    assert "#TAIL-低价值笔记B#" not in after_m
    assert "[L3→外置] imp=0.6" in after_m and "[L3→外置] imp=0.7" in after_m
    assert "普通条目C没有标注" in after_m                     # 没标注的一律不动
    # 归档文件：内容一字不少（永不删除）
    arc = sorted((tmp_home / "memories" / "archive").glob("*.md"))
    assert len(arc) == 1
    arc_text = arc[0].read_text(encoding="utf-8")
    assert "#TAIL-低价值笔记A#" in arc_text and "#TAIL-低价值笔记B#" in arc_text
    assert "archived=" in arc_text and "threshold=0.7" in arc_text
    # 备份：改前的文件字节级一致
    baks = list((tmp_home / "memories" / ".backup").glob("*/MEMORY.md"))
    assert baks and baks[0].read_bytes() == before_bytes
    assert list((tmp_home / "memories" / ".backup").glob("*/USER.md"))
    # 释放字符 = 改前 - 改后（真实测量，不是估算）
    assert rep["freed"] == len(before_m) - len(after_m)
    assert rep["freed"] == rep["before"]["MEMORY.md"] - rep["after"]["MEMORY.md"]
    assert rep["after"]["MEMORY.md"] < rep["before"]["MEMORY.md"]
    # 未入选的 USER.md 一个字节不变
    assert rep["after"]["USER.md"] == rep["before"]["USER.md"]


def test_b2_apply_is_idempotent(gov, tmp_home):
    mem, _ = _seed(tmp_home)
    first = gov.archive_low_value(threshold=0.7, dry_run=False, limits=LIMITS)
    snap = mem.read_text(encoding="utf-8")
    assert first["archived"]
    second = gov.archive_low_value(threshold=0.7, dry_run=False, limits=LIMITS)
    assert second["archived"] == [] and second["freed"] == 0
    assert mem.read_text(encoding="utf-8") == snap      # 二次执行零改动


def test_b3_metadata_entries_are_never_archived(gov, tmp_home):
    mem = tmp_home / "memories" / "MEMORY.md"
    # 正式元数据：imp 0.5 很低，但有 pinned 语义，属于 run_governance 的地盘
    _write_file(mem, ["[imp:0.5][used:3][pinned:1][src:memory] 用户铁律（正式元数据）"
                      + "细节段落" * 24])
    assert gov.inline_importance("[imp:0.5][used:3][pinned:1][src:memory] x") is None
    assert gov.survey(0.7, LIMITS)["candidates"] == []
    rep = gov.archive_low_value(threshold=0.9, dry_run=False, limits=LIMITS)
    assert rep["archived"] == []
    assert "用户铁律（正式元数据）" in mem.read_text(encoding="utf-8")


def test_b4_threshold_is_honored(gov, tmp_home):
    _seed(tmp_home)
    assert len(gov.survey(0.7, LIMITS)["candidates"]) == 2
    assert len(gov.survey(0.9, LIMITS)["candidates"]) == 3     # 0.9 的也进来
    assert len(gov.survey(0.5, LIMITS)["candidates"]) == 0


def test_b5_guard_blocks_mass_archive_without_force(gov, tmp_home):
    mem = tmp_home / "memories" / "MEMORY.md"
    _write_file(mem, [_entry(0.7, "全低价值%d" % i) for i in range(5)])
    snap = mem.read_text(encoding="utf-8")
    rep = gov.archive_low_value(threshold=0.7, dry_run=False, limits=LIMITS)
    assert rep["ok"] is False and rep["guard_blocked"] is True
    assert mem.read_text(encoding="utf-8") == snap            # 被守卫拦下，零改动
    assert not (tmp_home / "memories" / ".backup").exists()
    forced = gov.archive_low_value(threshold=0.7, dry_run=False, limits=LIMITS, force=True)
    assert forced["ok"] is True and len(forced["archived"]) == 5


def test_b6_index_line_is_not_an_entry(gov, tmp_home):
    from memomics.memory_governance.memory_score import parse_entries
    mem, _ = _seed(tmp_home)
    gov.archive_low_value(threshold=0.7, dry_run=False, limits=LIMITS)
    entries = parse_entries(mem.read_text(encoding="utf-8"))
    assert len(entries) == 1                                  # 3 条 -> 剩 1 条真实条目
    assert all("[L3→外置]" not in e for e in entries)
    idx = json.loads((tmp_home / "memories" / "index.json").read_text(encoding="utf-8"))
    # 索引覆盖两个文件：MEMORY.md 只剩 1 条真实条目（USER.md 2 条没入选）
    assert len([k for k in idx["entries"] if k.startswith("memory:")]) == 1


def test_b7_short_entries_are_skipped(gov, tmp_home):
    """短条目换索引行反而更长 —— 治理的目的是腾地方，腾不出来就别碰。"""
    mem = tmp_home / "memories" / "MEMORY.md"
    _write_file(mem, ["[imp:0.7] 太短了"])
    sv = gov.survey(0.7, LIMITS)
    assert sv["candidates"] == [] and sv["skipped_too_short"] == 1
    rep = gov.archive_low_value(threshold=0.7, dry_run=False, limits=LIMITS)
    assert rep["archived"] == [] and rep["freed"] == 0
    assert "[L3→外置]" not in mem.read_text(encoding="utf-8")


# --- C. 路由语义 -----------------------------------------------------------

def test_c1_govern_without_body_is_read_only(client, gov, tmp_home):
    mem, _ = _seed(tmp_home)
    snap = mem.read_bytes()
    r = client.post("/api/memory/govern")                     # 老前端就是这样调的
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["mode"] == "dry" and d["ok"] is True
    assert len(d["archived"]) == 2 and d["freed"] > 0
    assert d["usage"]["MEMORY.md"]["limit"] == server._memory_char_limit("MEMORY.md")
    # 面板契约：一次 dry 请求就得能画出占用条 + 候选清单 + 分层
    # （真机踩过：接口只回 archived/freed，面板读 candidates 显示"0 条、没有按钮"）
    assert [c["imp"] for c in d["candidates"]] == [0.6, 0.7]
    assert d["freed_estimate"] == d["freed"] > 0
    assert d["files"]["MEMORY.md"]["limit"] == 60000 and d["files"]["MEMORY.md"]["entries"] == 3
    assert d["layers"].get("L1", 0) == 5 and d["total_entries"] == 5
    assert d["skipped_too_short"] == 0 and d["min_free_gain"] > 0
    assert d["note"] and d["guard"]["ok"] is True
    assert mem.read_bytes() == snap                           # 只读：一个字节没动


def test_c2_apply_requires_token(client, gov, tmp_home, mem_token):
    mem, _ = _seed(tmp_home)
    snap = mem.read_bytes()
    r = client.post("/api/memory/govern", json={"mode": "apply", "threshold": 0.7})
    assert r.status_code == 401
    r = client.post("/api/memory/govern", json={"mode": "apply", "threshold": 0.7},
                    headers={"X-Memory-Token": "deadbeef" * 5})
    assert r.status_code == 401
    assert mem.read_bytes() == snap


def test_c3_apply_with_token_archives(client, gov, tmp_home, mem_token):
    mem, _ = _seed(tmp_home)
    r = client.post("/api/memory/govern", json={"mode": "apply", "threshold": 0.7},
                    headers={"X-Memory-Token": mem_token})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["mode"] == "apply" and len(d["archived"]) == 2 and d["freed"] > 0
    assert d["candidates"] and d["files"] and d["layers"]   # apply 响应同样带体检字段
    assert d["backup"] and os.path.isdir(d["backup"])
    assert list((tmp_home / "memories" / "archive").glob("*.md"))
    assert "[L3→外置]" in mem.read_text(encoding="utf-8")
    assert d["usage"]["MEMORY.md"]["chars"] == len(mem.read_text(encoding="utf-8"))


def test_c4_guard_returns_409(client, gov, tmp_home, mem_token):
    mem = tmp_home / "memories" / "MEMORY.md"
    _write_file(mem, [_entry(0.7, "全低价值%d" % i) for i in range(5)])
    r = client.post("/api/memory/govern", json={"mode": "apply", "threshold": 0.7},
                    headers={"X-Memory-Token": mem_token})
    assert r.status_code == 409
    assert r.json()["guard_blocked"] is True
    assert "[L3→外置]" not in mem.read_text(encoding="utf-8")


def test_c5_get_memory_carries_usage(client, tmp_home):
    _seed(tmp_home)
    d = client.get("/api/memory").json()
    assert set(d["usage"].keys()) == {"MEMORY.md", "USER.md"}
    for name, u in d["usage"].items():
        assert u["limit"] == server._memory_char_limit(name)
        assert u["chars"] > 0 and u["pct"] is not None and u["headroom"] >= 0


def test_c6_govern_apply_passes_the_sandbox_gate(sb, client, gov, tmp_home, mem_token):
    _seed(tmp_home)
    r = client.post("/api/memory/govern", json={"mode": "apply", "threshold": 0.7},
                    headers={"X-Memory-Token": mem_token})
    assert r.status_code == 200, r.text
    hits = [i for i in sb.audit(50)["items"] if i["source"] == "memory.govern"]
    assert hits and hits[-1]["action"] == "fs.write"
    # 观察模式契约：判定照算、blocked=False（真实拦不拦由 enforce 决定）
    assert hits[-1]["blocked"] is False
