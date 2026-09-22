# -*- coding: utf-8 -*-
"""SKILLS_INDEX.md 注册表回归测试（2026-09-23 使用场景/触发词审计后的护栏）。

背景：索引旧版由 auto_register.py「只追加」维护，导致 355 个技能里 82 个没有索引行、
84 行错列、64 行触发词为空、23 行使用场景是 ">"，触发词退化成分类水词（rna/scrna），
一句「scRNA-seq 数据做质控」能同时命中 19 个 RED skill。以下断言把修复钉死：

A. 完整性：磁盘上每个已注册技能（有 skill.json）在索引里有且只有一行
B. 格式：统一 5 列 + 每节连续编号 + 标题声明的数量与行数一致
C. 内容：使用场景非占位/非垃圾，触发词非空且不是分类水词
D. 幂等：重建结果与磁盘文件逐字一致（check() 为空）
E. 对齐：SOUL.md 必触发表里的技能必须真实存在且索引里是 RED
F. 精度：真实用户话术命中正确的 RED skill，闲聊/无关请求零误触发
"""
import os
import re
import sys
from collections import Counter

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
WEBUI = os.path.join(ROOT, "webui")
if WEBUI not in sys.path:
    sys.path.insert(0, WEBUI)

import skills_registry as reg  # noqa: E402


@pytest.fixture(scope="module")
def entries():
    return reg.scan_skills()


@pytest.fixture(scope="module")
def index_text():
    with open(reg.INDEX_PATH, encoding="utf-8") as f:
        return f.read()


_NON_DATA_FIRST = {"#", "icon", "RED", "YEL", "GRN", "WHT"}   # 表头 + 级别图例行


def _data_rows(text):
    """返回 [(节, 编号, skill, 使用场景, 触发词, 级别)]，跳过表头/图例/分隔行。"""
    rows, sec = [], None
    for line in text.splitlines():
        if line.startswith("## "):
            m = re.match(r"##\s+(\S+).*?\((\d+) skills\)", line)
            sec = m.group(1) if m else sec
            continue
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) != 5 or cells[0] in _NON_DATA_FIRST or set(cells[0]) <= set("-"):
            continue
        rows.append((sec,) + tuple(cells))
    return rows


def _disk_skill_dirs():
    """磁盘上带 skill.json 的技能目录名（与 GET /api/skills/catalog 同一口径）。"""
    names = set()
    for root, dirs, files in os.walk(reg.SKILLS_DIR):
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        if "skill.json" in files:
            names.add(os.path.basename(root))
    return names


# ---------- A. 完整性 ----------

def test_every_registered_skill_has_exactly_one_row(entries, index_text):
    disk = _disk_skill_dirs()
    names = [r[2] for r in _data_rows(index_text)]
    assert disk, "磁盘上没扫到任何 skill.json，测试口径有问题"
    assert set(names) == disk, (
        "索引与磁盘不一致；缺 %s；多 %s"
        % (sorted(disk - set(names))[:10], sorted(set(names) - disk)[:10]))
    dup = [n for n, c in Counter(names).items() if c > 1]
    assert not dup, "索引里有重复技能行: %s" % dup
    assert len(entries) == len(disk)
    assert len(names) >= 300, "技能数骤降，可能扫描逻辑坏了: %d" % len(names)


def test_scan_entries_unique(entries):
    names = [e["name"] for e in entries]
    assert len(names) == len(set(names))


# ---------- B. 格式 ----------

def test_rows_are_uniform_five_cells(index_text):
    for line in index_text.splitlines():
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if cells[0] in _NON_DATA_FIRST or set(cells[0]) <= set("-"):
            continue
        assert len(cells) == 5, "错列（表头 5 列）: %s" % line[:100]
        assert cells[0].isdigit(), "首列应为编号: %s" % line[:100]
        assert cells[4] in ("RED 必触发", "YEL 讨论触发", "GRN 按需触发", "WHT 系统级"), cells[4]


def test_section_numbering_and_counts(index_text):
    sec, n, rows = None, 0, 0
    for line in index_text.splitlines():
        if line.startswith("## "):
            if sec is not None:
                assert rows == n, "分节 %s 声明 %d 个但只有 %d 行" % (sec, n, rows)
            m = re.match(r"##\s+(\S+).*?\((\d+) skills\)", line)
            assert m, "分节标题格式不对: %s" % line
            sec, n, rows = m.group(1), int(m.group(2)), 0
            continue
        if line.startswith("|") and re.match(r"\|\s*\d+\s*\|", line):
            rows += 1
            assert line.strip().strip("|").split("|")[0].strip() == str(rows), \
                "分节 %s 第 %d 行编号不是 %d: %s" % (sec, rows, rows, line[:60])
    if sec is not None:
        assert rows == n, "分节 %s 声明 %d 个但只有 %d 行" % (sec, n, rows)


def test_all_15_sections_present(index_text):
    got = [m.group(1) for m in re.finditer(r"^##\s+(\S+).*?\(\d+ skills\)", index_text, re.M)]
    assert got == [s for s, _ in reg.SECTIONS], "分节顺序/名称被改动: %s" % got


# ---------- C. 内容质量 ----------
# 断言对象是注册表的内存条目（scan_skills），不是磁盘文件：全量跑时前段有用例会临时
# 改写 skill.json 并触发索引重建（索引是生成物），逐字读文件会让内容断言随用例顺序飘。
# 「文件 == 内存渲染」由 D 组单独把关。

def test_no_junk_or_placeholder_usage(entries):
    bad = []
    for e in entries:
        u = (e["usage"] or "").strip()
        if u in reg.JUNK_USAGE or len(u) < 6 or reg.PLACEHOLDER_RE.search(u):
            bad.append((e["name"], u[:40]))
    assert not bad, "使用场景缺失/占位/垃圾: %s" % bad[:10]


def test_keywords_non_empty_and_bounded(entries):
    bad = []
    for e in entries:
        kws = [k.strip() for k in e["keywords"] if k.strip() and k.strip() != "-"]
        if not kws or len(kws) > reg.MAX_KW:
            bad.append((e["name"], len(kws)))
            continue
        for k in kws:
            if len(k) < reg.MIN_KW_LEN or len(k) > reg.MAX_KW_LEN:
                bad.append((e["name"], k))
    assert not bad, "触发词为空或长度越界: %s" % bad[:10]


def test_red_rows_are_not_all_boilerplate(entries):
    bad = []
    for e in entries:
        if e["level"] != "RED":
            continue
        kws = [k.strip().lower() for k in e["keywords"] if k.strip()]
        if not kws or all(k in reg.BOILERPLATE for k in kws):
            bad.append(e["name"])
    assert not bad, "RED 行只有分类水词（会一触一大片）: %s" % bad[:10]


def test_red_keywords_have_no_duplicates_within_row(entries):
    for e in entries:
        kws = [k.strip().lower() for k in e["keywords"] if k.strip()]
        assert len(kws) == len(set(kws)), "同一行触发词重复: %s -> %s" % (e["name"], kws)


# ---------- D. 幂等 / 一致性 ----------

def test_index_matches_disk_exactly():
    """索引必须与磁盘同源。

    若运行中的 8899 心跳抢先重建过索引（它有独立的定时扫描），
    允许重建一次再判定；重建后仍不一致才是真 bug。
    """
    problems = reg.check()
    if problems:
        reg.build(write=True)
        problems = reg.check()
    assert problems == [], "索引与磁盘不同步（跑 python -m webui.skills_registry --build）: %s" % problems[:3]


def test_render_is_convergent(entries):
    """渲染必须是磁盘文件的不动点：build 之后，立刻重渲染应得到同样内容。

    历史 bug：build() 先渲染、后回填 skill.json，而渲染优先读 skill.json，
    于是写出的索引当场落后于磁盘，check() 永远报「不同步」、构建不收敛。
    """
    want = reg.render_index(entries)
    cur = open(reg.INDEX_PATH, encoding="utf-8").read()
    assert cur.strip() == want.strip(), "build 之后索引仍与渲染结果不一致（构建不收敛）"


def test_render_is_idempotent(entries):
    a = reg.render_index(entries)
    b = reg.render_index(reg.scan_skills())
    assert a == b, "两次重建结果不同（扫描器不确定，会导致索引反复抖动）"


def test_build_without_write_does_not_touch_file():
    with open(reg.INDEX_PATH, "rb") as f:
        before = f.read()
    reg.build(write=False)
    with open(reg.INDEX_PATH, "rb") as f:
        assert f.read() == before


# ---------- E. SOUL.md 对齐 ----------

def test_soul_trigger_targets_exist_and_are_red(entries):
    soul = reg._read_soul_red()
    assert len(soul) >= 30, "SOUL.md 必触发表没解析出目标（表被改坏了？）"
    by_name = {e["name"]: e for e in entries}
    missing = sorted(n for n in soul if n not in by_name)
    assert not missing, "SOUL.md 必触发表引用了不存在的 skill: %s" % missing
    not_red = sorted(n for n in soul if by_name[n]["level"] != "RED")
    assert not not_red, "SOUL 必触发表里的 skill 在索引里不是 RED: %s" % not_red


def test_soul_red_keywords_reach_index(entries):
    """人工写在 SOUL 必触发表里的词必须在索引行里出现（对齐 RED 自动触发）。"""
    soul = reg._read_soul_red()
    by_name = {e["name"]: e for e in entries}
    gaps = []
    for name, words in soul.items():
        if name not in by_name or not words:
            continue
        kws = [k.lower() for k in by_name[name]["keywords"]]
        if not any(w.lower() in kws for w in words):
            gaps.append((name, words[:3], by_name[name]["keywords"][:3]))
    assert not gaps, "SOUL 必触发表触发词没进索引: %s" % gaps[:6]


# ---------- F. 路由精度 ----------

# (用户原话, 必须命中的 skill, 命中数上限)
# 上限是防「水词泛滥」回归：修复前「scRNA-seq 数据做质控」会命中 19 个 RED skill。
# 画图类放宽到 4：带 figure 的英文触发词会词级命中 4 个出图 skill，这正是 SOUL.md
# 「画图 Skill 选择策略」存在的意义，各 skill 行内已写明路由（CNS 级才用 nature-figure）。
ROUTING_CASES = [
    ("我有一份 scRNA-seq 数据，先做质控和双细胞去除", "scrna-qc", 3),
    ("把这些基因做 GO/KEGG 富集分析", "functional-enrichment", 3),
    ("帮我把这段文字翻译成英文", "paper-polish", 2),
    ("给我做个空间转录组分析", "spatial-transcriptomics", 3),
    ("做个拟时序轨迹分析", "trajectory-analysis", 3),
    ("帮我写修回信", "nature-response", 3),
    ("生成一个 html 报告", "bioinformatics-html-report", 3),
    ("帮我画一个 Figure 1 的柱状图，要 CNS 级别", "nature-figure", 4),
]

DISTRACTORS = [
    "今天天气怎么样",
    "谢谢",
    "帮我下载这篇文献",
    "帮我写个 Python 脚本处理数据",
    "我今天心情不错，随便聊聊",
]


@pytest.fixture(scope="module")
def matcher():
    try:
        import server  # noqa: F401  （webui/server.py，重依赖）
    except Exception as exc:  # pragma: no cover - 环境缺依赖时跳过
        pytest.skip("server 无法导入: %s" % exc)
    return server._match_red_skill_triggers


@pytest.mark.parametrize("text,expected,limit", ROUTING_CASES)
def test_expected_skill_is_triggered(matcher, text, expected, limit):
    hits = matcher(text)
    assert expected in hits, "「%s」没命中 %s（命中=%s）" % (text, expected, hits)
    assert len(hits) <= limit, "「%s」命中过多（%d 个）: %s" % (text, len(hits), hits)


@pytest.mark.parametrize("text", DISTRACTORS)
def test_distractors_trigger_nothing(matcher, text):
    assert matcher(text) == [], "闲聊/无关请求误触发: %s -> %s" % (text, matcher(text))


def test_webui_picker_and_prompt_index_agree():
    """WebUI 置顶选择器（server.list_skills）与注入索引必须是同一批技能。

    只允许两个既有的已登记差异（子集判定，修好任一个都不算回归）：
      · _debates：运行期辩论数据目录（skills/bioinformatics/_debates/），带一个 SKILL.md
        就被选择器当成技能列出；它没有 skill.json，所以不进注入索引。
      · translate-book：Hermes 自带 productivity 类技能，选择器不扫这个根目录，
        但它有完整 skill.json，所以进注入索引（且 trigger_level=RED）。
    差异一旦超出这两个，说明两侧口径又漂了。
    """
    try:
        import asyncio

        import server
        base = asyncio.run(server.list_skills())
    except Exception as exc:  # pragma: no cover
        pytest.skip("server.list_skills 不可用: %s" % exc)
    pick = {s["name"] for s in base["skills"]}
    idx = {e["name"] for e in reg.scan_skills()}
    assert len(pick) >= 300 and len(idx) >= 300, (len(pick), len(idx))
    assert (pick - idx) <= {"_debates"}, "WebUI 有索引里没有的技能: %s" % sorted(pick - idx)
    assert (idx - pick) <= {"translate-book"}, "索引有 WebUI 看不到的技能: %s" % sorted(idx - pick)


# ---------- G. auto_register 已改为整表重建 ----------

def test_auto_register_delegates_to_registry(entries):
    import auto_register
    entry = next(e for e in entries if e["has_md"])
    before = reg.check()
    assert before == []
    assert auto_register.auto_register_to_index(entry["dir"]) is False, \
        "已注册技能不应被当成新技能"
    assert reg.check() == [], "auto_register 重建后索引与磁盘不一致"


def test_auto_generate_skill_json_keeps_metadata_clean(entries):
    """auto_generate_skill_json(force=True) 重生成 skill.json 后，该技能的路由口径不许变脏。

    回归点（本次审计发现的真 bug）：它把 SKILL.md frontmatter 里的 trigger_keywords
    原样搬进 skill.json —— 逗号粘连的长句、>24 字的英文短语、分类水词全进——
    索引随即出现「一格 19 个词」的脏行，正是「注册触发场景没写好」的来源。
    现在生成路径统一过 skills_registry.normalize_meta()。
    """
    import json
    import auto_register
    entry = next((e for e in entries if e["name"] == "academic-paper-reviewer"), None)
    if entry is None:
        pytest.skip("academic-paper-reviewer 不在磁盘上")
    raw = auto_register._parse_skill_md(entry["dir"]).get("trigger_keywords") or []
    assert len(raw) > reg.MAX_KW, "样本技能的原文触发词不够长，测不出限长: %d" % len(raw)
    p = os.path.join(entry["dir"], "skill.json")
    with open(p, "rb") as f:
        backup = f.read()
    try:
        assert auto_register.auto_generate_skill_json(entry["dir"], force=True) is True
        with open(p, encoding="utf-8") as f:
            data = json.load(f)
        kws = data.get("trigger_keywords") or []
        assert kws, "自动生成后触发词为空"
        assert len(kws) <= reg.MAX_KW, "自动生成未限长: %d 个 %s" % (len(kws), kws)
        assert all(reg.MIN_KW_LEN <= len(k) <= reg.MAX_KW_LEN for k in kws), \
            "自动生成触发词长度越界: %s" % kws
        assert not any("," in k or "、" in k for k in kws), "自动生成触发词含逗号粘连: %s" % kws
        after = next(e for e in reg.scan_skills() if e["name"] == entry["name"])
        assert after["keywords"] == entry["keywords"], \
            "重生成 skill.json 改变了该技能的触发词: %s -> %s" % (entry["keywords"], after["keywords"])
        assert after["usage"] == entry["usage"], "重生成 skill.json 改变了使用场景"
        assert after["level"] == entry["level"], "重生成 skill.json 改变了触发级别"
    finally:
        with open(p, "wb") as f:
            f.write(backup)
