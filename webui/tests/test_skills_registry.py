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
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
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


# ---------- H. frontmatter 解析 / 使用场景噪音 ----------
# 事故（2026-09 极测发现）：SKILL.md 用 `description: >-` 这类块标量时，旧解析器只取冒号右边的
# 字面量（`>`），描述被判成垃圾 → 使用场景退化成「首段兜底」，把 `--- name: ... category: ...`
# 整段 frontmatter 写进索引（15 个技能中招，archr-atac-analysis / debate-core / grill-me 等）。

def test_frontmatter_block_scalar_is_folded():
    md = ("---\n"
          "name: demo-skill\n"
          "description: >-\n"
          "  ArchR scATAC-seq 全流程：环境搭建 → Arrow 加载 → QC。\n"
          "  Signac 作为备选方案。\n"
          "tags: [a, b]\n"
          "---\n\n"
          "## 正文\n真正的内容。\n")
    meta = reg._parse_frontmatter(md)
    assert meta["name"] == "demo-skill"
    assert meta["description"].startswith("ArchR scATAC-seq 全流程")
    assert "Signac 作为备选方案。" in meta["description"], meta["description"]
    assert meta["tags"] == ["a", "b"], meta["tags"]
    usage, src = reg.extract_usage(md, meta, {}, "demo-skill")
    assert not usage.startswith("---"), usage
    assert "description:" not in usage, usage


def test_frontmatter_pipe_scalar_and_unclosed_block():
    """| 块标量同样要拼行；只有开头 `---`（未闭合）时也不能整段放弃。"""
    closed = "---\nname: demo-pipe\ndescription: |\n  第一行说明。\n  第二行说明。\n---\n\n正文。\n"
    assert reg._parse_frontmatter(closed)["description"] == "第一行说明。 第二行说明。"
    unclosed = "---\nname: demo-open\ndescription: 一句话说清什么时候用这个技能。\n\n正文第一段。\n"
    assert reg._parse_frontmatter(unclosed)["description"] == "一句话说清什么时候用这个技能。"


def test_usage_fallback_strips_frontmatter_noise():
    """描述彻底解析不出时，首段兜底也不能把 `---`/`key:` 行写进使用场景。"""
    md = ("---\nname: demo3\ncategory: Whatever\npython_packages:\n  - pandas\n"
          "description: >\n  真的描述在这里，足够长的一句话描述。\n---\n\n"
          "正文第一段，长度足够触发兜底逻辑。\n")
    meta = reg._parse_frontmatter(md)
    meta.pop("description", None)          # 模拟解析失败
    usage, src = reg.extract_usage(md, {}, meta, "demo3")
    assert not usage.startswith("---"), usage
    assert not reg.FM_NOISE_RE.match(usage), usage


def test_live_usage_has_no_frontmatter_noise(entries):
    bad = []
    for e in entries:
        u = (e["usage"] or "").strip()
        if u.startswith("---") or reg.FM_NOISE_RE.match(u):
            bad.append((e["name"], u[:60]))
    assert not bad, "使用场景里混进了 frontmatter 噪音（SKILL.md 的 description 解析失败）: %s" % bad[:10]


def test_live_json_when_to_use_has_no_frontmatter_noise(entries):
    bad = []
    for e in entries:
        p = os.path.join(e["dir"], "skill.json")
        try:
            with open(p, encoding="utf-8") as f:
                data = json.load(f) or {}
        except (OSError, ValueError):
            continue
        u = str(data.get("when_to_use") or "").strip()
        if u.startswith("---") or reg.FM_NOISE_RE.match(u):
            bad.append((e["name"], u[:60]))
    assert not bad, "skill.json 的 when_to_use 是 frontmatter 噪音（跑 --build 回填干净值）: %s" % bad[:10]


# ---------- I. 索引必须能由「已提交源码」复现 ----------

def _staged_text(rel_path):
    """取暂存区（即将提交）的文件文本；未跟踪/不在暂存区返回 None。"""
    p = subprocess.run(["git", "show", ":" + rel_path], cwd=ROOT,
                       stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    if p.returncode != 0:
        return None
    return p.stdout.decode("utf-8", "replace")


def _derive(md_text, sj, name, section, soul_map):
    """按 scan_skills 的口径，从「一份源码」推出 (触发级别, 使用场景, 触发词)。

    刻意复刻 scan_skills 的每一步（md frontmatter → json 覆盖 → SOUL 必触发表前置词），
    断言的是「索引真正会显示什么」，而不是「文件里有没有某个键」。
    """
    meta = reg._parse_frontmatter(md_text or "")
    level, _ = reg.resolve_level(name, meta, sj, section, set(soul_map))
    usage, _ = reg.extract_usage(md_text or "", meta, sj, name)
    kws, _ = reg.extract_keywords(md_text or "", meta, sj, name)
    if soul_map.get(name):
        have = []
        for k in list(soul_map[name]) + list(kws):
            if k not in have:
                have.append(k)
        kws = have[:reg.MAX_KW]
    return level, usage, kws


def test_index_is_reproducible_from_committed_metadata(entries):
    """索引行只能由「已提交的元数据」决定 —— 本地回填但没入库的字段必须清零。

    事故（P0-1b / P0-1c）：索引是按工作区渲染的，而 16 个技能的 trigger_keywords /
    when_to_use 只在本地被回填过（有的 skill.json / SKILL.md 甚至从未入 git）。
    用 git worktree 检出同一个提交后，15 行的触发词与使用场景和工作区不同 ——
    门禁在 checkout 里红、工作区却全绿，谁都不知道索引到底以哪份为准。

    判定口径：固定用**工作区的 SKILL.md**（那是人类内容，本地改动算内容漂移不算元数据漂移），
    只比对「工作区 skill.json」与「暂存区 skill.json」派生出的索引三要素是否一致。
    不一致说明这份 json 元数据是索引的真凶，却没进版本库。
    """
    if subprocess.run(["git", "rev-parse", "--git-dir"], cwd=ROOT,
                      stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode != 0:
        pytest.skip("当前目录不是 git 仓库，跳过入库一致性断言")
    soul_map = reg._read_soul_red()
    drift, untracked = [], []
    for e in entries:
        sjp = os.path.join(e["dir"], "skill.json")
        mdp = os.path.join(e["dir"], "SKILL.md")
        sj_raw = _staged_text(os.path.relpath(sjp, ROOT).replace(os.sep, "/"))
        if sj_raw is None:
            untracked.append(e["name"])
            continue
        try:
            sj_staged = json.loads(sj_raw) or {}
        except ValueError:
            drift.append((e["name"], "暂存区 skill.json 解析失败"))
            continue
        try:
            with open(sjp, encoding="utf-8") as f:
                sj_work = json.load(f) or {}
        except (OSError, ValueError):
            sj_work = {}
        md_work = ""
        if os.path.isfile(mdp):
            with open(mdp, encoding="utf-8") as f:
                md_work = f.read()
        a = _derive(md_work, sj_work, e["name"], e["section"], soul_map)
        b = _derive(md_work, sj_staged, e["name"], e["section"], soul_map)
        bad = [k for k, x, y in zip(("level", "usage", "keywords"), a, b) if x != y]
        if bad:
            drift.append((e["name"], "+".join(bad)))
    assert not untracked, "这些技能的 skill.json 还没入 git（全新 checkout 的索引会多行或少行）: %s" % untracked[:12]
    assert not drift, (
        "skill.json 里物化的元数据没进版本库，全新 checkout 的索引会与工作区不一致"
        "（提交这些字段，或删掉本地回填值让索引退回 SKILL.md 口径）: %s" % drift[:12])


# ---------- J. 注册路径写出的元数据必须干净 ----------

def test_auto_generate_skill_json_parses_block_scalar():
    """SKILL.md 用 description: >- 块标量时，生成的 skill.json 描述/使用场景不能是垃圾。

    回归点：auto_register._parse_skill_md 老实现是逐行 key: value，遇到块标量只取到字面量
    >-，缩进续行全部丢掉 —— 生成的 skill.json 里 description 就是 '>-'、when_to_use 为空，
    随后被索引/注入读走。现在 frontmatter 解析统一走 skills_registry._parse_frontmatter。
    """
    import auto_register
    md = ("---\nname: demo-block-scalar\ncategory: GWAS/Genetics\npython_packages:\n  - pandas\n"
          "description: >-\n  ArchR scATAC-seq 全流程：环境搭建 → QC。\n  Signac 作为备选。\n"
          "tags: [a, b]\n---\n\n## 使用场景\n需要在单细胞 ATAC 上跑完整流程时使用。\n")
    tmp = tempfile.mkdtemp(prefix="skill-fm-")
    try:
        with open(os.path.join(tmp, "SKILL.md"), "w", encoding="utf-8") as f:
            f.write(md)
        parsed = auto_register._parse_skill_md(tmp)
        assert parsed["description"].startswith("ArchR scATAC-seq"), \
            "块标量描述没拼行: %r" % parsed.get("description")
        assert auto_register.auto_generate_skill_json(tmp, force=True) is True
        with open(os.path.join(tmp, "skill.json"), encoding="utf-8") as f:
            data = json.load(f)
        desc = str(data.get("description") or "")
        usage = str(data.get("when_to_use") or "")
        assert desc.startswith("ArchR scATAC-seq") and "Signac" in desc, desc
        assert usage and not reg._is_junk_usage(usage), "生成的 when_to_use 是垃圾: %r" % usage
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
