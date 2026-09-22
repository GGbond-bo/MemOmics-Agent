# -*- coding: utf-8 -*-
"""Skill 路由回归矩阵（P0-1 门禁）：多场景 × 多意图 × 真实用户口径。

背景：触发词路由（server._match_red_skill_triggers）决定了「用户这句话能不能用上该用的技能」，
但旧护栏只有 8 条 ROUTING_CASES + 5 条闲聊干扰项（test_skills_registry.py 的 F 组），
覆盖不到 355 个技能里的绝大多数，也钉不住三种真实故障：
  · 漏召回：触发词写死成一种说法（"精读论文"），用户换个说法就断链；
  · 过度触发：英文单词级回退让 analysis / core / design / plan 命中一排无关技能；
  · 边界：空串、纯标点、emoji、控制字符、超长重复、全角输入不能崩、命中要有界。

本文件把矩阵数据外置到 fixtures/skill_routing_matrix.json（用户口径可评审、可追加），
断言分三类：
  1. 正向：cases 必须命中 must_hit，且总命中数不超过 max_hits（防再次「一句命中 19 个」）；
  2. 负向：distractors 零命中；known_over_triggers 是「已确认的过度触发」精确钉住，
     一旦收敛或扩大都必须改这份清单（防止悄悄变坏或悄悄变好而无记录）；
  3. 棘轮：known_gaps 是「已确认的漏召回」，一旦被修好就 fail 并要求提升为 cases。
另有覆盖率断言：每个 RED 技能至少被一条 case 覆盖（新 RED 技能必须补用例或登记豁免），
以及确定性 / 缓存与索引一致 / 性能上限三条不变量。

改触发词或改索引后，本文件必须继续通过 —— scripts/check_skills_gate.py 与
.githooks/pre-commit 会跑它。
"""
import json
import os
import sys
import time

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
WEBUI = os.path.join(ROOT, "webui")
if WEBUI not in sys.path:
    sys.path.insert(0, WEBUI)

import skills_registry as reg  # noqa: E402

FIXTURE_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "fixtures", "skill_routing_matrix.json")
SCHEMA = "memomics.skill-routing-matrix.v1"
# 全局命中上限：任何一句用户输入命中的 RED 技能都不该超过这个数（修复前实测 19）
HARD_HIT_CEILING = 8
# 性能上限：矩阵全量跑一轮（约 1100 次匹配）的秒数上限
PERF_BUDGET_SECONDS = 5.0


def _load_matrix():
    with open(FIXTURE_PATH, encoding="utf-8") as f:
        return json.load(f)


MATRIX = _load_matrix()
CASES = MATRIX["cases"]
DISTRACTORS = MATRIX["distractors"]
EDGE_CASES = MATRIX["edge_cases"]
KNOWN_GAPS = MATRIX["known_gaps"]
KNOWN_OVER = MATRIX["known_over_triggers"]
COVERAGE_EXEMPT = MATRIX.get("coverage_exempt") or []


def _ids(items):
    return [it["id"] for it in items]


@pytest.fixture(scope="module")
def matcher():
    try:
        import server  # noqa: F401  （webui/server.py，重依赖）
    except Exception as exc:  # pragma: no cover - 环境缺依赖时跳过
        pytest.skip("server 无法导入: %s" % exc)
    return server._match_red_skill_triggers


@pytest.fixture(scope="module")
def entries():
    return reg.scan_skills()


@pytest.fixture(scope="module")
def all_names(entries):
    return {e["name"] for e in entries}


@pytest.fixture(scope="module")
def red_names(entries):
    return {e["name"] for e in entries if e["level"] == "RED"}


# ---------- A. fixture 自检（数据坏了要立刻说清坏在哪） ----------

def test_fixture_schema_and_ids():
    assert MATRIX["schema"] == SCHEMA, "fixture schema 不匹配: %s" % MATRIX.get("schema")
    ids = ([c["id"] for c in CASES] + [c["id"] for c in EDGE_CASES]
           + [c["id"] for c in KNOWN_GAPS] + [c["id"] for c in KNOWN_OVER])
    dup = sorted({i for i in ids if ids.count(i) > 1})
    assert not dup, "fixture 里 id 重复: %s" % dup
    assert len(CASES) >= 50, "正向用例太少（%d），覆盖率断言会形同虚设" % len(CASES)
    assert len(DISTRACTORS) >= 5, "干扰项太少（%d）" % len(DISTRACTORS)


@pytest.mark.parametrize("case", CASES, ids=_ids(CASES))
def test_case_shape(case):
    assert case["text"].strip(), "用例文本为空: %s" % case["id"]
    assert case["must_hit"], "用例没有 must_hit: %s" % case["id"]
    assert len(case["must_hit"]) <= case["max_hits"], (
        "用例自相矛盾：must_hit %d 个 > max_hits %d（%s）"
        % (len(case["must_hit"]), case["max_hits"], case["id"]))
    assert case["max_hits"] <= HARD_HIT_CEILING, (
        "用例 %s 的 max_hits=%d 超过全局上限 %d" % (case["id"], case["max_hits"], HARD_HIT_CEILING))


def test_fixture_references_real_skills(all_names):
    bad = []
    for case in CASES:
        bad += [n for n in case["must_hit"] if n not in all_names]
    for gap in KNOWN_GAPS:
        if gap["would_be"] not in all_names:
            bad.append(gap["would_be"])
    for over in KNOWN_OVER:
        bad += [n for n in over["hits"] if n not in all_names]
    assert not bad, "fixture 引用了不存在的技能（改名/删技能后要同步）: %s" % sorted(set(bad))


# ---------- B. 正向：多场景 × 多意图 ----------

@pytest.mark.parametrize("case", CASES, ids=_ids(CASES))
def test_case_hits_expected_skill(matcher, case):
    hits = matcher(case["text"])
    missing = [n for n in case["must_hit"] if n not in hits]
    assert not missing, "「%s」(%s) 没命中 %s，实际命中=%s" % (
        case["text"], case["intent"], missing, hits)
    assert len(hits) <= case["max_hits"], "「%s」命中过多（%d > %d）: %s" % (
        case["text"], len(hits), case["max_hits"], hits)


def test_multi_intent_cases_carry_at_least_three_intents():
    multi = [c for c in CASES if c["intent"] == "多意图"]
    assert len(multi) >= 4, "多意图场景太少: %d" % len(multi)
    for c in multi:
        assert len(c["must_hit"]) >= 3, "多意图用例 %s 只覆盖 %d 个技能" % (c["id"], len(c["must_hit"]))


# ---------- C. 负向：闲聊与无关请求零误触发 ----------

@pytest.mark.parametrize("text", DISTRACTORS, ids=[t[:12] for t in DISTRACTORS])
def test_distractors_trigger_nothing(matcher, text):
    hits = matcher(text)
    assert hits == [], "闲聊/无关请求误触发 RED skill: 「%s」-> %s" % (text, hits)


@pytest.mark.parametrize("item", KNOWN_OVER, ids=_ids(KNOWN_OVER))
def test_known_over_triggers_are_pinned(matcher, item):
    """已确认的过度触发：精确钉住命中集合，任何变化都必须改这份清单并说明原因。

    收敛（变少）是好事，但也要在这里登记，否则「无意中不再命中该用的技能」会没人发现。
    """
    hits = sorted(matcher(item["text"]))
    assert hits == sorted(item["hits"]), (
        "「%s」的过度触发结果变了。\n  期望=%s\n  实际=%s\n"
        "若是收敛（P0-2 触发词契约化）→ 更新 fixture 里 %s 的 hits（或删掉该条）。\n"
        "若是扩散（更多无关技能被命中）→ 这是回归，请修触发词。"
        % (item["text"], sorted(item["hits"]), hits, item["id"]))


# ---------- D. 棘轮：已确认的漏召回 ----------

@pytest.mark.parametrize("gap", KNOWN_GAPS, ids=_ids(KNOWN_GAPS))
def test_known_gaps_are_not_silently_closed(matcher, gap):
    """已登记的漏召回：一旦命中，说明缺口修好了 —— 请把它提升为正向用例。"""
    hits = matcher(gap["text"])
    assert gap["would_be"] not in hits, (
        "缺口 %s 已被修复：「%s」现在命中 %s。\n"
        "请把这条从 known_gaps 移到 cases（写成 must_hit=%s + max_hits），保留 ratchet 的意义。"
        % (gap["id"], gap["text"], hits, [gap["would_be"]]))


# ---------- E. 边界与极端输入 ----------

@pytest.mark.parametrize("edge", EDGE_CASES, ids=_ids(EDGE_CASES))
def test_edge_inputs_are_safe_and_bounded(matcher, edge):
    hits = matcher(edge["text"])
    assert len(hits) <= HARD_HIT_CEILING, "边界输入命中过多（%d）: %s -> %s" % (
        len(hits), edge["id"], hits)
    if edge["expect"] == "empty":
        assert hits == [], "边界输入不该命中任何技能: %s -> %s" % (edge["id"], hits)
    else:
        limit = edge.get("max_hits", HARD_HIT_CEILING)
        assert len(hits) <= limit, "边界输入 %s 命中 %d > %d: %s" % (edge["id"], len(hits), limit, hits)


def test_every_matrix_text_is_bounded(matcher):
    """全局上限：矩阵里任何一句话都不能命中超过 HARD_HIT_CEILING 个 RED 技能。"""
    texts = ([c["text"] for c in CASES] + list(DISTRACTORS)
             + [e["text"] for e in EDGE_CASES] + [g["text"] for g in KNOWN_GAPS]
             + [o["text"] for o in KNOWN_OVER])
    worst = max((len(matcher(t)), t) for t in texts)
    assert worst[0] <= HARD_HIT_CEILING, "命中数 %d 超过上限 %d：「%s」" % (
        worst[0], HARD_HIT_CEILING, worst[1])


def test_matcher_never_returns_unknown_skill(matcher, all_names):
    """命中项必须是索引里真实存在的技能名（防索引行错列后吐出垃圾 token）。"""
    for case in CASES:
        for name in matcher(case["text"]):
            assert name in all_names, "命中了一个不存在的技能名: %r（用例 %s）" % (name, case["id"])


# ---------- F. 覆盖率：新 RED 技能必须有用例 ----------

def test_every_red_skill_is_covered(red_names):
    covered = set()
    for case in CASES:
        covered |= set(case["must_hit"])
    exempt = set(COVERAGE_EXEMPT)
    unknown_exempt = sorted(exempt - red_names)
    assert not unknown_exempt, "coverage_exempt 里不是 RED 技能（或已改名）: %s" % unknown_exempt
    missing = sorted(red_names - covered - exempt)
    assert not missing, (
        "有 %d 个 RED 技能没有任何路由用例：%s\n"
        "请在 fixtures/skill_routing_matrix.json 的 cases 里补一条真实用户口径的用例；"
        "确属无法测试的（如纯运行期技能）写进 coverage_exempt 并给理由。" % (len(missing), missing))


def test_coverage_exempt_is_documented():
    for name in COVERAGE_EXEMPT:
        assert isinstance(name, str) and name.strip(), "coverage_exempt 条目必须是技能名: %r" % (name,)
    assert len(COVERAGE_EXEMPT) <= 5, "豁免太多（%d），覆盖率断言会失去意义" % len(COVERAGE_EXEMPT)


# ---------- G. 不变量：确定性 / 缓存与索引一致 / 性能 ----------

def test_matcher_is_deterministic(matcher):
    for case in CASES[:15]:
        first = matcher(case["text"])
        assert matcher(case["text"]) == first, "同一输入两次结果不一致: %s" % case["id"]


def test_red_trigger_cache_covers_every_red_index_row(matcher):
    """匹配器的 RED 缓存必须与索引里的 RED 行一一对应。

    索引被重建（新技能 / 改触发词）后若缓存仍是旧的，路由会静默用过期触发词 ——
    这条断言就是那种漂移的报警器。
    """
    matcher("质控")  # 触发缓存构建
    import server
    cached = {name for name, _ in (server._RED_TRIGGER_CACHE or [])}
    rows = set()
    with open(reg.INDEX_PATH, encoding="utf-8") as f:
        for line in f:
            if not line.startswith("|"):
                continue
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if len(cells) != 5:
                continue
            if cells[0] in ("#", "icon", "RED", "YEL", "GRN", "WHT") or set(cells[0]) <= set("-"):
                continue
            if "RED" in cells[4]:
                rows.add(cells[1])
    assert cached == rows, (
        "匹配器 RED 缓存与索引 RED 行不一致：\n  只在缓存=%s\n  只在索引=%s"
        % (sorted(cached - rows), sorted(rows - cached)))


def test_matcher_performance_ceiling(matcher):
    texts = [c["text"] for c in CASES]
    matcher(texts[0])  # 预热（首次包含索引读取与缓存构建，不计入）
    start = time.perf_counter()
    rounds = 20
    for _ in range(rounds):
        for t in texts:
            matcher(t)
    elapsed = time.perf_counter() - start
    calls = rounds * len(texts)
    assert elapsed < PERF_BUDGET_SECONDS, "路由匹配变慢：%d 次调用用了 %.2fs（上限 %.1fs）" % (
        calls, elapsed, PERF_BUDGET_SECONDS)
