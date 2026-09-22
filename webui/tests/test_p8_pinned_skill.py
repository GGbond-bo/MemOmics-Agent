# -*- coding: utf-8 -*-
"""P8(2026-09-23) 置顶 skill 契约测试。

用户原话："这么多 skill，能不能在交互框那里增加一个 skills 标识，用来标识使用某个 skill？
功能就是为用户提供选择，该会话使用该 skill。不是不使用其他 skill，而是合适的使用场景优先使用这个 skill。
我要画图，我要按照 CNS 级别绘制，但是你可能触发的是别的科研 skill，但是用户添加了这个 skill，
即便触发了其他的 skill，也要优先这个 skill 来做。还有，所有 skills 在 webUI 都能查看，
所有 skill 的文件内容，脚本等等。"

四组契约（全部走真实实现，不 mock）：
  A. 元数据层  _skill_meta / _find_skill_dir —— 目录穿越必须拒，查不到的 skill 返回 {}
  B. 注入层    _build_pinned_skill_block / _build_skill_injection —— 置顶块永远在前；
               命中触发词才预载完整 SKILL.md（软优先 vs 硬预载）
  C. 接口层    /api/skills/catalog（必须早于 /api/skills/{name} 注册）、
               /api/skills/{name}/files、/api/sessions/{sid}/skills（会话级置顶 + 上限 + 缺失标记）
  D. 前端      输入框 chip 条 + 选择器 + 「用没用」可视化（skill_used / skill_expect / p8_audit）
               + skill 文件树点开即看；新增键中英双全；P8 区块不许硬编码中文
"""
import io
import os
import re
import sqlite3
import sys
import uuid

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import server  # noqa: E402

P8_SKILL = "nature-figure"
P8_KEYS = [
    "sk_pick", "sk_pick_title", "sk_none", "sk_title", "sk_sub", "sk_search", "sk_clear",
    "sk_done", "sk_loading", "sk_used_times", "sk_not_used", "sk_expected", "sk_unpin",
    "sk_pin", "sk_pinned_n", "sk_hint_n", "sk_no_match", "sk_max", "sk_disabled", "sk_kw",
    "sk_no_session", "sk_missed", "sk_files",
]


def _html():
    with io.open(os.path.join(server.MEMOMICS_DIR, "webui", "index.html"), encoding="utf-8") as f:
        return f.read()


def _server_src():
    with io.open(os.path.join(server.MEMOMICS_DIR, "webui", "server.py"), encoding="utf-8") as f:
        return f.read()


def _p8_js_block():
    """P8 前端区块（选择器 + chip + 使用可视化）"""
    html = _html()
    i = html.find("// === P8(")
    j = html.find("// === Skill ", i)
    assert i > 0 and j > i, "P8 前端区块找不到"
    return html[i:j]


def _strip_comments(code):
    code = re.sub(r"/\*.*?\*/", "", code, flags=re.S)
    code = re.sub(r"^\s*//.*$", "", code, flags=re.M)
    return re.sub(r"\s+//[^\n]*$", "", code, flags=re.M)


@pytest.fixture()
def tmp_sid():
    """测试专用会话 id：用完把 kv 里的置顶行删掉，不留脏数据"""
    sid = "pytest-p8-" + uuid.uuid4().hex[:8]
    try:
        yield sid
    finally:
        server._PINNED_SKILLS_CACHE.pop(sid, None)
        server._sessions.pop(sid, None)
        try:
            conn = sqlite3.connect(os.path.join(server.HERMES_HOME_DIR, "state.db"), timeout=10)
            conn.execute("DELETE FROM kv WHERE key=?", ("pinned_skills:" + sid,))
            conn.commit()
            conn.close()
        except Exception:
            pass


# ==================== A. 元数据层 ====================

def test_p8_skill_meta_reads_real_skill_and_unknown_is_empty():
    m = server._skill_meta(P8_SKILL)
    assert m, "nature-figure 元数据读不到"
    assert m["name"] == P8_SKILL
    assert m["category"], "缺少分类"
    assert m["trigger_keywords"], "缺少触发词（置顶块靠它判断要不要预载）"
    assert os.path.isdir(os.path.join(server.MEMOMICS_DIR, m["dir"].replace("/", os.sep))) or os.path.isdir(m["dir"])
    assert server._skill_meta("no-such-skill-xyz") == {}


def test_p8_find_skill_dir_blocks_traversal():
    for bad in ("../../etc", "..", "", "   ", "a/../../b", "../webui"):
        assert server._find_skill_dir(bad) is None, "路径穿越没拦住: %r" % bad
    assert server._find_skill_dir(P8_SKILL) is not None


# ==================== B. 注入层 ====================

def test_p8_pinned_block_is_soft_priority_and_hard_preloads_on_trigger():
    hot = server._build_pinned_skill_block([P8_SKILL], "我要按 CNS 级别画发表级配图，准备投 Nature", "zh")
    assert hot and P8_SKILL in hot
    assert "<<<PINNED_SKILL_MD_BEGIN>>>" in hot, "命中触发词时应预载完整 SKILL.md"
    cold = server._build_pinned_skill_block([P8_SKILL], "帮我把这个 csv 做个差异表达分析", "zh")
    assert cold and P8_SKILL in cold, "没命中触发词也要保留软优先块（优先≠独占）"
    assert "<<<PINNED_SKILL_MD_BEGIN>>>" not in cold
    assert server._build_pinned_skill_block([], "随便说点什么", "zh") == ""


def test_p8_pinned_block_bilingual_and_unknown_skill_flagged():
    en = server._build_pinned_skill_block([P8_SKILL], "please make a publication figure for Nature", "en")
    assert en and P8_SKILL in en
    zh = server._build_pinned_skill_block([P8_SKILL], "画图", "zh")
    assert zh != en, "中英双语置顶块应不同"
    ghost = server._build_pinned_skill_block(["no-such-skill-xyz"], "画图", "zh")
    assert "no-such-skill-xyz" in ghost, "缺失的置顶 skill 也要告诉模型（不要瞎编）"
    assert "未找到" in ghost, "要明说找不到，模型才不会被诱导假装加载"
    assert "no-such-skill-xyz" in server._build_pinned_skill_block(["no-such-skill-xyz"], "x", "en")


def test_p8_injection_puts_pinned_prefix_first():
    user = "我要按 CNS 级别画发表级配图，投 Nature"
    with_pin = server._build_skill_injection("visualization", "bio", "zh", user, pinned=[P8_SKILL])
    without = server._build_skill_injection("visualization", "bio", "zh", user, pinned=[])
    assert "<<<PINNED_SKILL_MD_BEGIN>>>" in with_pin
    assert "<<<PINNED_SKILL_MD_BEGIN>>>" not in without
    assert with_pin.endswith(without), "置顶块必须拼接在原注入内容之前，不能挤掉原有内容"
    chat = server._build_skill_injection("chat", "", "zh", "只是打个招呼", pinned=[P8_SKILL])
    assert P8_SKILL in chat, "chat 意图下也要带置顶块"


def test_p8_pinned_skills_cap_and_usage_note(tmp_sid, monkeypatch):
    names = ["nature-figure", "academic-figure-skill", "cns-visualization", "figure-designer",
             "nature-reader", "nature-reviewer", "nature-shared"]
    got = server._pinned_skills_set(tmp_sid, names)
    assert len(got) == server._PINNED_MAX, "置顶数量必须封顶"
    assert got == names[:server._PINNED_MAX]
    assert server._pinned_skills_get(tmp_sid) == got, "置顶要能读回来（会话级）"
    sent = []
    monkeypatch.setattr(server, "_session_emit", lambda s, m: sent.append(m))
    sess = {"id": tmp_sid}
    server._sessions[tmp_sid] = sess          # 真实链路里 tool_start 传的就是 _sessions 里那个 dict
    server._skill_usage_note(tmp_sid, P8_SKILL, sess)
    assert sent and sent[0]["type"] == "skill_used" and sent[0]["skill"] == P8_SKILL
    assert server._skill_usage_get(tmp_sid)[P8_SKILL] == 1
    server._skill_usage_note(tmp_sid, P8_SKILL, sess)
    assert server._skill_usage_get(tmp_sid)[P8_SKILL] == 2, "同一技能多次加载要累计（前端显示 N 次）"
    server._pinned_skills_set(tmp_sid, [])


def test_p8_expect_emit_only_when_pinned_skill_trigger_hits(tmp_sid, monkeypatch):
    server._pinned_skills_set(tmp_sid, [P8_SKILL])
    sent = []
    monkeypatch.setattr(server, "_session_emit", lambda s, m: sent.append(m))
    sess = {"id": tmp_sid}
    hit = server._pinned_expect_emit(sess, "我要按 CNS 级别画发表级配图")
    assert [x["name"] for x in hit] == [P8_SKILL]
    assert hit[0]["hits"], "要带上命中的触发词，前端才能解释为什么要求加载"
    assert sent and sent[0]["type"] == "skill_expect"
    assert server._pinned_expect_emit(sess, "今天天气不错") == []
    server._pinned_skills_set(tmp_sid, [])


# ==================== C. 接口层 ====================

def test_p8_catalog_route_registered_before_skill_detail():
    paths = [getattr(r, "path", "") for r in server.app.routes]
    assert "/api/skills/catalog" in paths, "缺 /api/skills/catalog"
    assert "/api/skills/{name}" in paths
    assert paths.index("/api/skills/catalog") < paths.index("/api/skills/{name}"), \
        "catalog 必须注册在 /api/skills/{name} 之前，否则会被当成 skill 名吞掉"


def test_p8_catalog_endpoint_lists_skills_with_triggers(client):
    r = client.get("/api/skills/catalog")
    assert r.status_code == 200
    d = r.json()
    assert d["total"] > 100, "skill 目录太小: %s" % d["total"]
    assert d["pinned_max"] == server._PINNED_MAX
    item = [x for x in d["skills"] if x["name"] == P8_SKILL]
    assert item, "目录里没有 %s" % P8_SKILL
    assert item[0]["trigger_keywords"], "目录项要带触发词，用户才知道钉它值不值"
    q = client.get("/api/skills/catalog", params={"q": P8_SKILL}).json()
    assert 0 < q["total"] < d["total"], "搜索没生效"


def test_p8_skill_files_endpoint_exposes_full_tree(client):
    r = client.get("/api/skills/%s/files" % P8_SKILL)
    assert r.status_code == 200
    d = r.json()
    rels = [x["rel"] for x in d["files"]]
    assert d["total"] > 20, "skill 文件树太小"
    assert "SKILL.md" in rels, "SKILL.md 必须在文件树里（用户要求能看全部文件内容）"
    assert any(x.endswith(".py") or x.endswith(".R") for x in rels), "脚本也要能看"
    assert client.get("/api/skills/no-such-skill-xyz/files").status_code in (200, 404)


def test_p8_session_pin_endpoints_roundtrip(client, tmp_sid):
    d0 = client.get("/api/sessions/%s/skills" % tmp_sid).json()
    assert d0["pinned"] == [] and d0["pinned_max"] == server._PINNED_MAX
    r = client.post("/api/sessions/%s/skills" % tmp_sid,
                    json={"skills": [P8_SKILL, "no-such-skill-xyz"]})
    assert r.status_code == 200
    pinned = r.json()["pinned"]
    assert [x["name"] for x in pinned] == [P8_SKILL, "no-such-skill-xyz"]
    assert [x["missing"] for x in pinned] == [False, True], "不存在的 skill 要标 missing，前端好提示"
    d1 = client.get("/api/sessions/%s/skills" % tmp_sid).json()
    assert [x["name"] for x in d1["pinned"]] == [P8_SKILL, "no-such-skill-xyz"]
    assert isinstance(d1["used"], dict) and isinstance(d1["used_names"], list)
    cleared = client.post("/api/sessions/%s/skills" % tmp_sid, json={"skills": []}).json()
    assert cleared["pinned"] == []


# ==================== D. 前端 ====================

def test_p8_frontend_input_bar_and_picker_markup():
    html = _html()
    for token in ('id="chat-skill-bar"', 'id="sk-pick-btn"', 'id="sk-chips"', 'id="skp-mask"',
                  'id="skp-search"', 'id="skp-body"', 'class="chat-skill-bar"',
                  ".chat-skill-bar", ".sk-chip", ".skp-item", ".sk-tree-f"):
        assert token in html, "输入框技能选择器缺少: %s" % token
    bar = html.find('id="chat-skill-bar"')
    inp = html.find('id="chat-input"')
    assert bar > inp, "chip 条必须在输入框区域里面（用户要求「在交互框那里」）"


def test_p8_frontend_functions_present():
    html = _html()
    for fn in ("function loadPinnedSkills", "function renderSkillChips", "function openSkillPicker",
               "function renderSkillPicker", "function togglePinSkill", "function savePinnedSkills",
               "function onSkillUsed", "function onSkillExpect", "function _p8Audit",
               "function openSkillFile", "function _p8OnLangChange"):
        assert fn in html, "缺前端函数: %s" % fn


def test_p8_frontend_handles_skill_events_and_audits_every_turn_end():
    html = _html()
    assert "msg.type === 'skill_used'" in html and "onSkillUsed(msg.skill)" in html
    assert "msg.type === 'skill_expect'" in html and "onSkillExpect(msg.skills" in html
    assert html.count("_p8Audit()") >= 3, "回合结束（complete/cancelled）都要核对置顶技能用没用"
    assert "'p8_audit': '⚠️'" in html or "'p8_audit'" in html, "审计行要有独立时间和图标"
    assert "skill_view" in html and "🧩" in html, "工具时间线要能看出 skill_view 被调用"


def test_p8_frontend_switchsession_reloads_pins():
    html = _html()
    i = html.find("currentSid = sid;")
    assert i > 0
    seg = html[i:i + 500]
    assert "loadPinnedSkills(sid)" in seg, "切会话/刷新恢复会话时必须重新拉该会话的置顶 skill"


def test_p8_frontend_skill_detail_shows_file_tree_into_own_viewer():
    html = _html()
    i = html.find("function _rvHost")
    assert i > 0, "查看器宿主映射找不到"
    host_fn = html[i:i + 400]
    assert "host === 'skills'" in host_fn and "'panel-skills'" in host_fn, \
        "skill 文件要在 skill 面板内打开（不能挤进结果面板）"
    assert "openFileViewer(path, rel, 'skills')" in html
    i = html.find("function viewSkill")
    assert i > 0
    seg = html[i:i + 1500]
    assert "/files" in seg, "skill 详情要拉完整文件树"
    assert "sk-tree" in seg
    assert "#panel-skills.rv-open" in html, "文件查看器要能在 skill 面板内铺满"


def test_p8_frontend_i18n_keys_in_both_dicts():
    html = _html()
    i = html.find("var I18N = {")
    j = html.find("var UI_LANG", i)
    block = html[i:j]
    zh_i, en_i = block.find("zh: {"), block.find("en: {")
    zh = set(re.findall(r"'([A-Za-z0-9_]+)'\s*:", block[zh_i:en_i]))
    en = set(re.findall(r"'([A-Za-z0-9_]+)'\s*:", block[en_i:]))
    for k in P8_KEYS:
        assert k in zh, "zh 字典缺键: %s" % k
        assert k in en, "en 字典缺键: %s" % k
    for k in P8_KEYS:
        assert any(p % k in html for p in ("t('%s')", "tf('%s'", 'data-i18n="%s"',
                                              'data-i18n-ph="%s"', 'data-i18n-title="%s"')), \
            "P8 键 %s 定义了却没用上" % k


def test_p8_js_block_has_no_hardcoded_chinese():
    """P8 区块里文案必须走 t()/tf()，否则切英文界面残留中文。"""
    body = _strip_comments(_p8_js_block())
    cjk = re.compile(r"[\u4e00-\u9fff]")
    bad = [ln.strip()[:120] for ln in body.split("\n") if cjk.search(ln)]
    assert not bad, "P8 区块还有硬编码中文：\n" + "\n".join(bad)


def test_p8_backend_audit_and_usage_wiring():
    src = _server_src()
    assert "# === P8(" in src and "# === P8 end ===" in src
    assert "_pinned_expect_emit(session, user_text)" in src, "回合开始要发 skill_expect"
    assert 'tool_name == "skill_view"' in src and "_skill_usage_note(" in src, \
        "skill_view 真被调用时要记 usage（这是「你保证触发了吗」的唯一硬证据）"
    assert "pinned=_pinned_skills_get(session" in src, "注入时要把会话置顶 skill 传进去"
