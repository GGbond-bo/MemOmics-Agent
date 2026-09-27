# -*- coding: utf-8 -*-
"""P0-3（2026-09-23）命中可见性 + 显式 /skill-name 调用 契约测试。

用户原话：“继续，完善，极端测试”。P0-3 要解决两件真实痛点：
  1. 命中不可见：用户看到 agent 加载了某个技能，却不知道「为什么是它」——触发词藏在
     SKILLS_INDEX.md 的表格里，命中了哪条、走哪条匹配规则，人和模型都看不到；
  2. 只能靠猜：想指定某个技能，用户只能碰运气把触发词写进句子里；没有 /skill-name 这种
     确定性入口，触发词一改就断链。

五组契约（全部走真实实现，不 mock 匹配器）：
  A. 命中原因   _match_red_skill_hits —— 每个命中都要能说出「命中哪条触发词、走哪条规则」，
                且与 _match_red_skill_triggers 在整张路由矩阵上逐句等价（可见性不许改变路由）
  B. 显式调用   _parse_skill_invocations —— URL/路径/分数/中文标点/前缀歧义/路径穿越要各归其位
  C. 注入层     _build_explicit_skill_block / _build_skill_injection —— 显式调用优先级最高（在置顶、
                RED 之前）、预载 SKILL.md 全文；未知技能给相近建议并禁止编造
  D. 事件与接口 skill_hit / skill_invoke 事件 + /api/skills/resolve（注册顺序不能被子路由吞掉）
  E. 前端       「为什么命中」chip + 「/」自动补全 + 中英双全 + P0-3 区块不许硬编码中文
"""
import difflib
import io
import json
import os
import re
import sqlite3
import sys
import time
import uuid

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
WEBUI = os.path.join(ROOT, "webui")
for _p in (ROOT, WEBUI):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import server  # noqa: E402

FIXTURE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "fixtures", "skill_routing_matrix.json")
REAL_SKILLS = ("scrna-qc", "nature-figure", "archr-atac-analysis")
SK3_KEYS = [
    "sk3_hit_title", "sk3_hit_why", "sk3_rule_substring", "sk3_rule_cjkgap",
    "sk3_rule_shortascii", "sk3_rule_multiword", "sk3_invoke", "sk3_unknown",
    "sk3_ambiguous", "sk3_slash_hint", "sk3_no_match", "sk3_clear", "sk3_unknown_tip", "sk3_overflow",
]


def _load_matrix():
    with open(FIXTURE_PATH, encoding="utf-8") as f:
        return json.load(f)


MATRIX = _load_matrix()


def _html():
    with io.open(os.path.join(ROOT, "webui", "index.html"), encoding="utf-8") as f:
        return f.read()


def _server_src():
    with io.open(os.path.join(ROOT, "webui", "server.py"), encoding="utf-8") as f:
        return f.read()


def _sk3_js_block():
    html = _html()
    i = html.find("// === P0-3(")
    mark = "// === P0-3 end ==="
    j = html.find(mark)
    assert i > 0 and j > i, "P0-3 前端区块找不到"
    return html[i:j + len(mark)]


def _strip_comments(code):
    code = re.sub(r"/\*.*?\*/", "", code, flags=re.S)
    code = re.sub(r"^\s*//.*$", "", code, flags=re.M)
    return re.sub(r"\s+//[^\n]*$", "", code, flags=re.M)


@pytest.fixture()
def tmp_sid():
    sid = "pytest-p03-" + uuid.uuid4().hex[:8]
    try:
        yield sid
    finally:
        server._sessions.pop(sid, None)
        try:
            conn = sqlite3.connect(os.path.join(server.HERMES_HOME_DIR, "state.db"), timeout=10)
            conn.execute("DELETE FROM kv WHERE key=?", ("pinned_skills:" + sid,))
            conn.commit()
            conn.close()
        except Exception:
            pass


def _rule_holds(rule, kw, text):
    """按契约复算一条命中原因是否真的成立（可见性不能只会讲故事）。"""
    t = text.lower()
    k = kw.lower()
    if rule == "substring":
        return k in t
    if rule == "cjk-gap":
        return server._tighten_cjk_ascii(k) in server._tighten_cjk_ascii(t)
    if rule == "short-ascii":
        return server._short_ascii_kw_match(k, t)
    if rule == "multiword":
        words = set(w for w in k.split() if w not in server._EN_STOPWORDS)
        return bool(words) and words <= set(t.split())
    return False


# ==================== A. 命中原因 ====================

def test_a1_every_hit_says_which_keyword_and_which_rule():
    text = "我有一份 scRNA-seq 数据，先做质控和双细胞去除"
    hits = server._match_red_skill_hits(text)
    assert hits, "这句必须命中 scrna-qc（矩阵回归用例）"
    names = [h["name"] for h in hits]
    assert "scrna-qc" in names
    for h in hits:
        assert h["name"] and h["keyword"] and h["rule"], "命中必须带 name/keyword/rule: %r" % (h,)
        assert _rule_holds(h["rule"], h["keyword"], text), \
            "命中原因不成立: %r（这句话里找不到该触发词，可见性在骗人）" % (h,)
    qc = [h for h in hits if h["name"] == "scrna-qc"][0]
    assert qc["keyword"].lower() in text.lower(), "scrna-qc 的原因必须是句子里真实出现的词"
    assert qc["rule"] in ("substring", "cjk-gap", "short-ascii", "multiword")


def test_a2_reason_keyword_comes_from_the_index_triggers():
    text = "我有一份 scRNA-seq 数据，先做质控和双细胞去除"
    hits = server._match_red_skill_hits(text)
    assert hits
    triggers = dict(server._RED_TRIGGER_CACHE or [])
    assert triggers, "命中后应已构建 RED 触发词缓存"
    for h in hits:
        pool = [str(x).lower() for x in (triggers.get(h["name"]) or [])]
        assert str(h["keyword"]).lower() in pool, \
            "%s 的命中词 %r 不在索引触发词里: %s" % (h["name"], h["keyword"], pool[:8])


def test_a3_hits_are_equivalent_to_names_on_the_full_matrix():
    """可见性只许增加解释，不许改变路由：整张矩阵逐句比对。"""
    texts = []
    for key in ("cases", "distractors", "edge_cases", "known_gaps", "known_over_triggers"):
        for it in MATRIX.get(key) or []:
            if isinstance(it, dict) and isinstance(it.get("text"), str):
                texts.append(it["text"])
    assert len(texts) >= 70, "矩阵文本太少: %d" % len(texts)
    bad = []
    for t in texts:
        names = server._match_red_skill_triggers(t)
        hits = [h["name"] for h in server._match_red_skill_hits(t)]
        if names != hits:
            bad.append((t[:40], names[:4], hits[:4]))
    assert not bad, "命中原因与命中名单不一致（顺序也要一致）: %s" % bad[:5]


def test_a4_empty_and_nonsense_text_has_no_reason():
    assert server._match_red_skill_hits("") == []
    assert server._match_red_skill_hits("   ") == []
    assert server._match_red_skill_hits("zzqqxx") == []
    assert server._match_red_skill_triggers("zzqqxx") == []


def test_a5_local_literature_exemption_keeps_reasons_consistent():
    text = "帮我总结文献库里的这篇论文"
    hits = server._match_red_skill_hits(text)
    names = [h["name"] for h in hits]
    assert names == server._match_red_skill_triggers(text), "豁免后也要与名单一致"
    assert "literature-review" not in names, "本地文献库操作应豁免文献类 RED 技能"
    for h in hits:
        assert h["name"] not in server._LOCAL_LIT_RED_EXEMPT


# ==================== B. 显式 /skill-name 解析 ====================

def test_b1_parses_real_names_and_is_case_insensitive():
    inv = server._parse_skill_invocations("/scrna-qc 帮我看看这批数据")
    assert inv["resolved"] == [{"token": "scrna-qc", "name": "scrna-qc"}]
    assert inv["unknown"] == [] and inv["ambiguous"] == []
    up = server._parse_skill_invocations("/SCRNA-QC 帮我看看")
    assert [x["name"] for x in up["resolved"]] == ["scrna-qc"], "技能名大小写不敏感"
    mid = server._parse_skill_invocations("先用 /archr-atac-analysis，再讲结论")
    assert [x["name"] for x in mid["resolved"]] == ["archr-atac-analysis"]
    assert inv["raw"] == ["scrna-qc"]


def test_b2_ignores_urls_paths_fractions_and_app_commands():
    for text in (
        "看下 https://example.com/a/b?q=/scrna-qc 这个链接",
        "打开 work/papers/abc.pdf",
        "E:/work/data/run.csv 在这",
        "C:\\Users\\23136\\data\\x.h5ad",
        "A/B 测试 and/or 二选一",
        "2026/09/23 发布的新版本",
        "1/2 的样本",
        "//scrna-qc 是双斜杠",
        "用 /papers 命令看文献库",
        "/etc/passwd 是什么",
        "把 /data/raw 目录扫一遍",
        "/usr/local/bin 在哪",
        "/" + "a" * 200,
        "/" + "9" * 81,
    ):
        inv = server._parse_skill_invocations(text)
        assert inv["resolved"] == [], "不该把路径/命令当技能: %r -> %r" % (text, inv)
        assert inv["unknown"] == [], "路径/分数/应用命令不该进 unknown: %r -> %r" % (text, inv)


def test_b3_traversal_and_unknown_are_rejected():
    for text in ("/../etc/passwd", "/..", "/", "//", "/1234567"):
        inv = server._parse_skill_invocations(text)
        assert inv["resolved"] == [], "路径穿越/纯数字不该被解析: %r" % text
    inv = server._parse_skill_invocations("/no-such-skill-xyz 帮我跑")
    assert inv["resolved"] == []
    assert inv["unknown"] == ["no-such-skill-xyz"]
    assert server._find_skill_dir("no-such-skill-xyz") is None


def test_b4_ambiguous_prefix_lists_candidates_and_does_not_guess():
    inv = server._parse_skill_invocations("/analy 帮我看看")
    assert inv["resolved"] == [], "前缀有歧义时不许猜一个"
    assert len(inv["ambiguous"]) == 1
    amb = inv["ambiguous"][0]
    assert amb["token"] == "analy"
    assert len(amb["candidates"]) > 1, "歧义必须给出候选"
    assert len(amb["candidates"]) <= server._EXPLICIT_CANDIDATE_MAX
    assert inv["unknown"] == [], "歧义不是未知（要分开告诉用户）"


def test_b4c_separator_variant_gets_suggestions():
    """极端：把分隔符全省掉的写法（/getgenesetenrichmentanalysis）也要能给出建议。

    这条专门盯「只有分隔符归一化才救得回来」的场景：difflib 相似度 0.63 够不到 0.75，
    没有分隔符前缀匹配就真的石沉大海（用户不会记得名字里是 - 还是 _）。
    """
    tok = "getgenesetenrichmentanalysis"
    target = "get_gene_set_enrichment_analysis_supported_database_list"
    plain = difflib.get_close_matches(tok, list(server._skill_name_index().keys()), n=5, cutoff=0.75)
    assert target not in plain, "前提变了：difflib 已经能直接命中，这条测试失去意义"
    sug = server._suggest_skills(tok)
    assert target in sug, "分隔符变体拿不到建议: %r" % (sug,)
    assert 0 < len(sug) <= server._EXPLICIT_CANDIDATE_MAX
    inv = server._parse_skill_invocations("/%s 跑一下" % tok)
    assert inv["resolved"] == [] and inv["unknown"] == [tok], inv


def test_b4d_unknown_is_never_silently_dropped_on_a_live_path():
    """极端：任何「用户明确打了斜杠」的 token，要么 resolved，要么 unknown/ambiguous，不许凭空消失。"""
    for text in ("/scrna-qc", "/singlecell", "/analy", "/zzqqxx", "/nature-figure 帮我画图",
                 "/scrna-qc /nature-figure /deg-analysis /scrna-eda /scrna-clustering 都跑一遍"):
        inv = server._parse_skill_invocations(text)
        n_raw = len(inv["raw"])
        n_out = (len(inv["resolved"]) + len(inv["unknown"]) + len(inv["ambiguous"])
                 + len(inv["overflow"]))
        assert n_raw == n_out, "token 被静默吞掉: %r -> %r" % (text, inv)


def test_b4b_longest_real_skill_name_still_resolves():
    """极端：本机最长技能名（60 字符）也要能被斜杠命令精确命中，长度过滤不许误伤真实技能。"""
    idx = server._skill_name_index()
    longest = sorted(idx.values(), key=len)[-1]
    assert len(longest) == 60, "最长技能名变了：%r" % longest
    inv = server._parse_skill_invocations("/%s 帮我跑一遍" % longest)
    assert [x["name"] for x in inv["resolved"]] == [longest], inv
    assert inv["unknown"] == [] and inv["ambiguous"] == []


def test_b5_unique_prefix_resolves():
    inv = server._parse_skill_invocations("/academic-researc 帮我查文献")
    assert [x["name"] for x in inv["resolved"]] == ["academic-research"]
    # 动态复核：随便挑一个「唯一前缀」，解析器都必须能补全
    idx = server._skill_name_index()
    low = sorted(idx.keys())
    uniq = None
    for n in low:
        for k in range(max(4, len(n) - 6), len(n)):
            pre = n[:k]
            if pre in idx:
                continue
            if sum(1 for m in low if m.startswith(pre)) == 1:
                uniq = (pre, n)
                break
        if uniq:
            break
    assert uniq, "索引里找不到唯一前缀，测试前提不成立"
    inv2 = server._parse_skill_invocations("/%s x" % uniq[0])
    assert [x["name"] for x in inv2["resolved"]] == [uniq[1]], \
        "唯一前缀 %r 应补全为 %r，实际 %r" % (uniq[0], uniq[1], inv2)


def test_b6_dedup_order_and_cap():
    inv = server._parse_skill_invocations("/scrna-qc 先质控 /nature-figure 再画图 /scrna-qc")
    assert [x["name"] for x in inv["resolved"]] == ["scrna-qc", "nature-figure"], \
        "重复点名要去重且保持先后顺序"
    many = " ".join("/" + n for n in ("scrna-qc", "nature-figure", "archr-atac-analysis",
                                      "deg-analysis", "scrna-eda", "scrna-clustering"))
    inv2 = server._parse_skill_invocations(many)
    assert len(inv2["resolved"]) == server._EXPLICIT_MAX, "显式调用必须有数量上限"
    assert [x["name"] for x in inv2["resolved"]] == ["scrna-qc", "nature-figure",
                                                     "archr-atac-analysis", "deg-analysis"]


def test_b6b_over_cap_tokens_are_reported_not_swallowed():
    """极端：一句话塞 5 个技能（上限 4）——多出来的必须如实上报，不许静默丢弃。

    用户以为点名了 5 个，实际只生效 4 个；这种事瞒着用户比报错更糟。
    """
    names = ["scrna-qc", "nature-figure", "deg-analysis", "scrna-eda", "scrna-clustering"]
    inv = server._parse_skill_invocations(" ".join("/" + n for n in names) + " 都跑一遍")
    assert [x["name"] for x in inv["resolved"]] == names[:server._EXPLICIT_MAX]
    assert inv["overflow"] == ["scrna-clustering"], inv
    blk = server._build_explicit_skill_block(inv, "zh")
    assert "scrna-clustering" in blk, "超出上限的技能必须告诉模型（用户以为点名生效了）"
    assert str(server._EXPLICIT_MAX) in blk
    en = server._build_explicit_skill_block(inv, "en")
    assert "scrna-clustering" in en and "batch" in en


def test_b7_typo_gets_close_matches():
    inv = server._parse_skill_invocations("/scrna-qcc 帮我做质控")
    assert inv["resolved"] == [] and inv["unknown"] == ["scrna-qcc"]
    sug = server._suggest_skills("scrna-qcc")
    assert "scrna-qc" in sug, "拼错一个字要给相近建议: %r" % sug
    assert len(sug) <= server._EXPLICIT_CANDIDATE_MAX
    assert server._suggest_skills("zzqqxx-no-such") == [], "完全不像就别硬凑"


def test_b8_variants_and_chinese_punctuation():
    assert [x["name"] for x in server._parse_skill_invocations("/scrna_qc 跑一下")["resolved"]] \
        == ["scrna-qc"], "下划线写法应等价（技能名用连字符）"
    for text in ("/archr-atac-analysis，帮我跑", "/nature-figure。画图", "/scrna-qc：先质控",
                 "/deg-analysis！"):
        inv = server._parse_skill_invocations(text)
        assert len(inv["resolved"]) == 1 and inv["unknown"] == [], \
            "中文标点/全角冒号后面的技能名要解析出来: %r -> %r" % (text, inv)


def test_b9_name_index_is_cached_and_rebuilt_when_dirs_change(monkeypatch):
    idx1 = server._skill_name_index()
    assert idx1 and idx1.get("scrna-qc") == "scrna-qc"
    assert server._skill_name_index() is idx1, "目录没变就该命中缓存（每句话都要解析，不能每次扫盘）"
    monkeypatch.setattr(server, "_skill_name_sig", lambda: ("sentinel", 1))
    idx2 = server._skill_name_index()
    assert idx2 is not idx1, "目录签名变了必须重建"
    assert idx2.get("scrna-qc") == "scrna-qc"


def test_b10_scan_is_fast_enough_for_every_message():
    texts = ["帮我做质控" * 20, "/scrna-qc 帮我做质控和聚类", "a" * 4000]
    t0 = time.time()
    for i in range(150):
        for t in texts:
            server._match_red_skill_hits(t)
            server._parse_skill_invocations(t)
    cost = time.time() - t0
    assert cost < 6.0, "命中原因+斜杠解析太慢：450 次共 %.2fs" % cost


# ==================== C. 注入层 ====================

def test_c1_explicit_block_preloads_full_md_and_forbids_skip():
    inv = server._parse_skill_invocations("/nature-figure 帮我画个发表级配图")
    blk = server._build_explicit_skill_block(inv, "zh")
    assert blk and "nature-figure" in blk
    assert "<<<EXPLICIT_SKILL_MD_BEGIN>>>" in blk and "<<<EXPLICIT_SKILL_MD_END>>>" in blk, \
        "显式调用要预载 SKILL.md 全文"
    assert "skill_view(name='nature-figure')" in blk, "必须要求模型先 skill_view"
    assert "显式" in blk
    assert server._build_explicit_skill_block(server._parse_skill_invocations("没有斜杠"), "zh") == ""


def test_c2_explicit_outranks_pinned_and_red():
    text = "/nature-figure 我要按 CNS 级别画发表级配图，先做质控"
    inj = server._build_skill_injection("visualization", "bio", "zh", text, pinned=["scrna-qc"])
    i_exp = inj.find("<<<EXPLICIT_SKILL_MD_BEGIN>>>")
    i_pin = inj.find("<<<PINNED_SKILL_MD_BEGIN>>>")
    i_red = inj.find("检测到用户消息命中以下必触发技能")
    assert i_exp >= 0, "显式调用块必须在注入里"
    assert i_pin > i_exp, "显式调用优先于置顶（用户点名的东西最大）"
    assert i_red > i_pin > i_exp, "RED 自动命中排在最后: exp=%d pin=%d red=%d" % (i_exp, i_pin, i_red)
    assert "nature-figure" in inj[:i_exp + 400]


def test_c3_unknown_skill_forbids_invention_and_offers_neighbours():
    inv = server._parse_skill_invocations("/scrna-qcc 帮我做质控")
    blk = server._build_explicit_skill_block(inv, "zh")
    assert "scrna-qcc" in blk and "scrna-qc" in blk, "未知技能要带上相近建议"
    assert "没有" in blk or "不存在" in blk, "要说清本机没有这个技能"
    assert "不要" in blk and "编" in blk, "必须禁止模型假装加载/编造流程"
    assert "<<<EXPLICIT_SKILL_MD_BEGIN>>>" not in blk, "未知技能没有 SKILL.md 可预载"


def test_c4_ambiguous_block_asks_user_to_confirm():
    inv = server._parse_skill_invocations("/analy 帮我看看")
    blk = server._build_explicit_skill_block(inv, "zh")
    assert "analy" in blk and "歧义" in blk
    assert "确认" in blk, "歧义时必须让用户确认，不许自动选一个"
    assert "<<<EXPLICIT_SKILL_MD_BEGIN>>>" not in blk


def test_c5_english_block_and_no_leak_into_normal_turns():
    inv = server._parse_skill_invocations("/nature-figure make a figure")
    en = server._build_explicit_skill_block(inv, "en")
    assert en and "nature-figure" in en
    head = en.split("<<<EXPLICIT_SKILL_MD_BEGIN>>>")[0]
    assert not re.search(r"[\u4e00-\u9fff]", head), "英文块的指令部分不该有中文（预载的 SKILL.md 原文不算）"
    zh = server._build_explicit_skill_block(inv, "zh")
    assert zh != en
    plain = server._build_skill_injection("visualization", "bio", "zh", "帮我画个图")
    assert "EXPLICIT_SKILL_MD" not in plain, "没写 /skill 就不该出现显式调用块"


def test_c6_explicit_block_stays_within_budget():
    many = " ".join("/" + n for n in ("scrna-qc", "nature-figure", "archr-atac-analysis",
                                      "deg-analysis", "scrna-eda", "scrna-clustering"))
    inv = server._parse_skill_invocations(many)
    blk = server._build_explicit_skill_block(inv, "zh")
    assert blk.count("<<<EXPLICIT_SKILL_MD_BEGIN>>>") == len(inv["resolved"])
    per = server._EXPLICIT_FULLTEXT_BUDGET
    assert len(blk) <= len(inv["resolved"]) * (per + 4000) + 4000, \
        "显式调用块的体积必须有界: %d" % len(blk)


# ==================== D. 事件与接口 ====================

def test_d1_red_hit_emit_carries_reasons(tmp_sid, monkeypatch):
    sent = []
    monkeypatch.setattr(server, "_session_emit", lambda s, m: sent.append(m))
    sess = {"id": tmp_sid}
    hits = server._red_hit_emit(sess, "先做质控和双细胞去除")
    assert hits, "这句应命中 scrna-qc"
    assert sent and sent[0]["type"] == "skill_hit"
    assert sent[0]["skills"] and sent[0]["skills"][0]["keyword"]
    assert sent[0]["skills"][0]["rule"] in ("substring", "cjk-gap", "short-ascii", "multiword")
    assert sess.get("_red_hits") == sent[0]["skills"], "会话要留下本回合命中，刷新/重连能复现"
    assert server._red_hit_emit(sess, "zzqqxx") == []
    assert len(sent) == 1, "没命中就不该发事件"


def test_d2_skill_invoke_emit_covers_resolved_unknown_ambiguous(tmp_sid, monkeypatch):
    sent = []
    monkeypatch.setattr(server, "_session_emit", lambda s, m: sent.append(m))
    sess = {"id": tmp_sid}
    inv = server._parse_skill_invocations("/scrna-qc 质控 /no-such-skill-xyz 跑 /analy 看")
    payload = server._skill_invoke_emit(sess, inv)
    assert payload and payload["resolved"] == [{"token": "scrna-qc", "name": "scrna-qc"}]
    assert payload["unknown"] == ["no-such-skill-xyz"]
    assert [a["token"] for a in payload["ambiguous"]] == ["analy"]
    assert sent and sent[0]["type"] == "skill_invoke"
    assert server._skill_invoke_emit(sess, server._parse_skill_invocations("普通一句话")) is None
    assert len(sent) == 1, "没有显式调用就不发事件"


def test_d2b_overflow_rides_along_the_invoke_event(tmp_sid, monkeypatch):
    sent = []
    monkeypatch.setattr(server, "_session_emit", lambda s, m: sent.append(m))
    inv = server._parse_skill_invocations(
        "/scrna-qc /nature-figure /deg-analysis /scrna-eda /scrna-clustering 都跑一遍")
    payload = server._skill_invoke_emit({"id": tmp_sid}, inv)
    assert payload and payload["overflow"] == ["scrna-clustering"], payload
    assert sent and sent[0]["type"] == "skill_invoke" and sent[0]["overflow"] == ["scrna-clustering"]


def test_d3_resolve_endpoint_and_route_order(client):
    paths = [getattr(r, "path", "") for r in server.app.routes]
    assert "/api/skills/resolve" in paths, "缺 /api/skills/resolve"
    assert "/api/skills/{name}" in paths
    assert paths.index("/api/skills/resolve") < paths.index("/api/skills/{name}"), \
        "resolve 必须注册在 /api/skills/{name} 之前，否则会被当成技能名吞掉"
    d = client.get("/api/skills/resolve", params={"q": "/scrna-qc 帮我做质控"}).json()
    assert d["resolved"] == [{"token": "scrna-qc", "name": "scrna-qc"}]
    assert d["skill"] and d["skill"]["name"] == "scrna-qc"
    assert d["skill"]["trigger_keywords"], "接口要给前端展示理由（触发词）"
    bad = client.get("/api/skills/resolve", params={"q": "/scrna-qcc x"}).json()
    assert bad["resolved"] == [] and bad["unknown"] == ["scrna-qcc"]
    assert "scrna-qc" in bad["suggestions"]


def test_d4_turn_start_wiring_in_server_source():
    src = _server_src()
    assert "# === P0-3(" in src and "# === P0-3 end ===" in src
    assert "_red_hit_emit(session, user_text)" in src, "回合开始要发命中原因事件"
    assert "_skill_invoke_emit(" in src, "回合开始要发显式调用事件"
    assert "explicit=" in src and "_parse_skill_invocations(user_text)" in src, \
        "注入时要带上显式调用解析结果"
    # 2026-09-26: 自我介绍"快速回复"（绕过 LLM 的固定文案）已整体删除，
    # 显式点名不会再被它吃掉 —— 这里改成断言那条路径彻底不存在。
    assert "_SELF_INTRO_ZH" not in src and "_SELF_INTRO_EN" not in src, \
        "固定自我介绍文案应已删除"
    assert "跳过 agent 调用" not in src, "不应再有绕过 LLM 的快速回复分支"
    assert "_inj_intent = _intent" in src, "self_intro 也要照常构建注入并走 agent"


# ==================== E. 前端 ====================

def test_e1_frontend_markup_and_functions():
    html = _html()
    for token in ('id="sk3-hits"', 'id="sk3-slash"', 'id="sk3-slash-list"', ".sk3-hit", ".sk3-slash"):
        assert token in html, "命中可见性缺少: %s" % token
    i_bar = html.find('id="chat-skill-bar"')
    i_hits = html.find('id="sk3-hits"')
    assert i_hits > i_bar > 0, "命中解释要挂在输入框技能条里（和置顶 chip 同一区域）"
    for fn in ("function onSkillHit", "function onSkillInvoke", "function _sk3RenderHits",
               "function _sk3SlashMaybe", "function _sk3SlashKey", "function _sk3InsertSlash",
               "function _sk3CloseSlash", "function _sk3RuleName"):
        assert fn in html, "缺前端函数: %s" % fn


def test_e2_frontend_handles_skill_events():
    html = _html()
    assert "msg.type === 'skill_hit'" in html and "onSkillHit(msg.skills" in html
    assert "msg.type === 'skill_invoke'" in html and "onSkillInvoke(msg" in html
    assert "_sk3SlashMaybe()" in html, "输入框要触发 / 自动补全"
    assert "/api/skills/resolve" in html, "前端要能问解析结果（歧义/未知/建议）"
    assert "_p8Catalog" in html or "/api/skills/catalog" in html, "补全列表复用技能目录"


def test_e3_i18n_keys_in_both_dicts():
    html = _html()
    i = html.find("var I18N = {")
    j = html.find("var UI_LANG", i)
    block = html[i:j]
    zh_i, en_i = block.find("zh: {"), block.find("en: {")
    zh = set(re.findall(r"'([A-Za-z0-9_]+)'\s*:", block[zh_i:en_i]))
    en = set(re.findall(r"'([A-Za-z0-9_]+)'\s*:", block[en_i:]))
    for k in SK3_KEYS:
        assert k in zh, "zh 字典缺键: %s" % k
        assert k in en, "en 字典缺键: %s" % k
    for k in SK3_KEYS:
        assert any(p % k in html for p in ("t('%s')", "tf('%s'", 'data-i18n="%s"',
                                            'data-i18n-ph="%s"', 'data-i18n-title="%s"')), \
            "P0-3 键 %s 定义了却没用上" % k


def test_e4_js_block_has_no_hardcoded_chinese():
    body = _strip_comments(_sk3_js_block())
    cjk = re.compile(r"[\u4e00-\u9fff]")
    bad = [ln.strip()[:120] for ln in body.split("\n") if cjk.search(ln)]
    assert not bad, "P0-3 区块还有硬编码中文：\n" + "\n".join(bad)

