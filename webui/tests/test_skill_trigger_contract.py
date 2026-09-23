# -*- coding: utf-8 -*-
"""触发词契约钉住测试（P0-2a）：contracts/skill_triggers.json 的每一条规则都要有牙。

背景：触发词规则原先只存在于 webui/server.py 的代码里，改语义没有任何护栏：
  · 英文多词触发词走「任一实词命中」，用户说一句 analysis 就命中 6 个无关技能；
  · RED 触发词缓存只在 None 时构建一次，索引重建后新技能永远匹配不到；
  · 中英之间打空格（「CNS 级别」「做 QC」）就漏召回，同一句话两种命运。
本文件把 contracts/skill_triggers.json 变成可执行契约：
  1. 契约文件结构 / 规则值 ↔ 代码常量（MIN_KW_LEN、MAX_KW_LEN、MAX_KW、停用词、豁免表）逐条相等；
  2. 匹配语义按契约断言（中文子串 / 英文实词全中 / 大小写无关 / 中英边界空白归一 / 文献库豁免）；
  3. 关键词质量用棘轮：新增裸通用词（裸英文词 + 裸中文通用词）、违规蔓延、修好却不清台账都必须报错；
  4. 源头也要干净：skill.json / SKILL.md frontmatter / SOUL 必触发表里被 BOILERPLATE 静默丢弃或不生效的裸通用词同样算隐患；
  5. 缓存必须绑定 SKILLS_INDEX 的 mtime（索引重建后立即可见）——旧实现这一条是红的。
2026-09-23 P0-2b：台账 known_violations 已清零（33 条全部修完），蔓延 / 过期两个负向分支改用合成契约继续钉住。
2026-09-23 P0-2c：检查范围由 RED 扩到全等级（YEL 侧实测 32 处裸通用词，全部来自技能名分词回填，已清完并堵住派生口）。
"""
import json
import os
import re
import time

import pytest

import server
import skills_registry as reg

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CONTRACT_PATH = os.path.join(ROOT, 'contracts', 'skill_triggers.json')
MATRIX_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'fixtures', 'skill_routing_matrix.json')
SCHEMA = 'memomics.skill-triggers-contract.v1'


def _load(path):
    with open(path, encoding='utf-8') as f:
        return json.load(f)


CONTRACT = _load(CONTRACT_PATH)
MATRIX = _load(MATRIX_PATH)
RULES = CONTRACT.get('keyword_rules') or {}
MATCHING = CONTRACT.get('matching') or {}
RATCHET = CONTRACT.get('ratchet') or {}
KNOWN = RATCHET.get('known_violations') or {}
EXEMPT = ((CONTRACT.get('exemptions') or {}).get('local_literature') or {})
FORBIDDEN_ASCII = {str(w).lower() for w in (RULES.get('forbidden_bare_ascii_words') or [])}
FORBIDDEN_CJK = {str(w) for w in (RULES.get('forbidden_bare_cjk_words') or [])}
# P0-2b 清零留痕：转正的正向用例文本 / 收敛的过度触发文本，护栏不能跟着清零一起消失
RETIRED_GAP_TEXTS = [
    '线粒体比例太高，帮我把这批细胞过滤掉',
    '帮我复现这篇论文的方法部分',
    '这批数据要不要做批次校正',
    '把跑出来的表格合并成一个 Excel',
    '精读这篇论文，逐段解读一下',
    '从这篇文献里提取实验参数',
    '这个研究方向值得做吗？帮我评估一下可行性',
]
CONVERGED_OVER_TEXTS = [
    '这个 analysis 的 core 思路是什么',
    'Please help me design a plan for my holiday',
]


def _bare_generic(word):
    w = str(word).strip()
    if not w:
        return False
    if w.isascii():
        return ' ' not in w and w.lower() in FORBIDDEN_ASCII
    return w in FORBIDDEN_CJK


def _red_entries():
    red = {e['name']: e for e in reg.scan_skills() if e.get('level') == 'RED'}
    assert len(red) >= 40, 'RED 技能太少（%d），源头断言会形同虚设' % len(red)
    return red


def _all_entries():
    """P0-2c：通用词规则对全部等级生效，源头断言也必须扫全量（355 行），不能只看 RED。"""
    rows = {e['name']: e for e in reg.scan_skills()}
    assert len(rows) >= 300, '技能总数太少（%d），全等级断言会形同虚设' % len(rows)
    return rows


def _contract_with_ledger(known):
    """合成契约：真实台账已清零，蔓延 / 过期分支用合成台账继续钉住。"""
    contract = json.loads(json.dumps(CONTRACT))
    contract['ratchet']['known_violations'] = dict(known)
    return contract


@pytest.fixture(scope='module')
def matcher():
    return server._match_red_skill_triggers


@pytest.fixture(scope='module')
def all_names():
    return {e['name'] for e in reg.scan_skills()}


# ---------- A. 契约文件本身 ----------

class TestContractFile:
    def test_schema_and_sections(self):
        assert CONTRACT.get('schema') == SCHEMA
        for key in ('why', 'truth_chain', 'keyword_rules', 'matching',
                    'exemptions', 'ratchet', 'evidence'):
            assert CONTRACT.get(key), '契约缺 %s 节' % key

    def test_truth_chain_starts_at_skill_json(self):
        chain = CONTRACT['truth_chain']
        assert 'skill.json' in chain[0], '真相源必须从 skill.json 开始：%s' % chain[0]
        assert any('SKILLS_INDEX' in x for x in chain), '契约必须写明索引是派生物'

    def test_ratchet_is_documented_as_monotone(self):
        rule = RATCHET.get('rule') or ''
        assert '只能减少' in rule, '棘轮语义必须在契约里写明（现：%s）' % rule
        assert KNOWN == {}, (
            '2026-09-23 P0-2b 后台账应为空（存量 33 条全部修完）；'
            '若确有新存量，请连同原因一起留档: %s' % sorted(KNOWN))
        assert RATCHET.get('zero_since'), '台账清零必须有留痕（ratchet.zero_since）'

    def test_known_violations_reference_real_skills(self, all_names):
        bad = sorted({s for owners in KNOWN.values() for s in owners} - all_names)
        assert not bad, '台账引用了不存在的技能（改名/删技能后要同步）: %s' % bad

    def test_known_violations_words_are_declared_forbidden(self):
        declared = FORBIDDEN_ASCII | FORBIDDEN_CJK
        extra = sorted(set(KNOWN) - declared)
        assert not extra, ('台账里的词必须先写进 forbidden_bare_ascii_words / '
                           'forbidden_bare_cjk_words: %s' % extra)

    def test_both_forbidden_lists_are_declared(self):
        assert len(FORBIDDEN_ASCII) >= 30, '裸英文通用词清单被削了？只剩 %d 条' % len(FORBIDDEN_ASCII)
        assert FORBIDDEN_CJK, '裸中文通用词清单不能为空（2026-09-23 P0-2b 上线）'
        assert {'整合', '分析', '设计'} <= FORBIDDEN_CJK, sorted(FORBIDDEN_CJK)


# ---------- B. 代码常量 == 契约规则值 ----------

class TestCodeMatchesContract:
    def test_keyword_limits(self):
        assert reg.MIN_KW_LEN == RULES['min_len']
        assert reg.MAX_KW_LEN == RULES['max_len']
        assert reg.MAX_KW == RULES['max_per_skill']

    def test_keyword_filter_lists_match_contract(self):
        """抽取阶段的「静默丢弃」词表也要单点真源（P0-2b 之前只存在于代码里）。"""
        filters = CONTRACT.get('keyword_filters') or {}
        assert filters.get('boilerplate'), '契约必须声明 boilerplate 词表'
        assert set(reg.BOILERPLATE) == set(filters['boilerplate']), (
            'BOILERPLATE 与契约不一致：代码多 %s / 契约多 %s'
            % (sorted(set(reg.BOILERPLATE) - set(filters['boilerplate'])),
               sorted(set(filters['boilerplate']) - set(reg.BOILERPLATE))))
        assert set(reg.GENERIC_STOP) == set(filters['generic_stop']), (
            'GENERIC_STOP 与契约不一致：代码多 %s / 契约多 %s'
            % (sorted(set(reg.GENERIC_STOP) - set(filters['generic_stop'])),
               sorted(set(filters['generic_stop']) - set(reg.GENERIC_STOP))))

    def test_forbidden_lists_match_contract(self):
        """报错型词表（forbidden）也必须与代码常量逐字相等（P0-2c 起名称分词直接引用它）。"""
        assert set(reg.FORBIDDEN_BARE_ASCII) == FORBIDDEN_ASCII, (
            'FORBIDDEN_BARE_ASCII 与契约不一致：代码多 %s / 契约多 %s'
            % (sorted(set(reg.FORBIDDEN_BARE_ASCII) - FORBIDDEN_ASCII),
               sorted(FORBIDDEN_ASCII - set(reg.FORBIDDEN_BARE_ASCII))))
        assert set(reg.FORBIDDEN_BARE_CJK) == FORBIDDEN_CJK, (
            'FORBIDDEN_BARE_CJK 与契约不一致：代码多 %s / 契约多 %s'
            % (sorted(set(reg.FORBIDDEN_BARE_CJK) - FORBIDDEN_CJK),
               sorted(FORBIDDEN_CJK - set(reg.FORBIDDEN_BARE_CJK))))

    def test_generic_word_rules_apply_to_every_level(self):
        scope = RULES.get('generic_word_rules_apply_to') or ''
        assert '全部' in scope, '契约必须写明通用词规则适用于全部等级：%s' % scope
        assert not RULES.get('red_only_rules_apply_to'), 'P0-2c 起范围不再是 RED 专属'
        assert 'P0-2c' in (RULES.get('forbidden_scope') or ''), (
            'forbidden_scope 必须留下 P0-2c 的范围变更痕迹')

    def test_boilerplate_words_are_dropped_at_extraction(self):
        """机制证明：BOILERPLATE 词在抽取阶段就被丢掉 —— 有效触发词视角永远看不到它们。"""
        got = reg._split_keywords('分析, 可视化, 报告, 质控, deg analysis')
        assert '质控' in got and 'deg analysis' in got, got
        for w in ('分析', '可视化', '报告'):
            assert w not in got, 'BOILERPLATE 词不该穿过抽取阶段: %s -> %s' % (w, got)
        rows = _red_entries()
        leaked = sorted({w for e in rows.values() for w in e['keywords']} & set(reg.BOILERPLATE))
        assert not leaked, 'BOILERPLATE 词漏进了有效触发词: %s' % leaked

    def test_stopwords_are_pinned(self):
        assert set(server._EN_STOPWORDS) == set(MATCHING['stopwords']), (
            'server 的停用词与契约不一致：只改一边会让英文多词匹配行为漂移')

    def test_local_literature_exemption_is_pinned(self):
        assert set(server._LOCAL_LIT_RED_EXEMPT) == set(EXEMPT['excludes'])
        assert tuple(server._LOCAL_LIT_EXEMPT_TRIGGERS) == tuple(EXEMPT['when'])

    def test_matching_semantics_are_declared(self):
        assert MATCHING['case_fold'] is True
        assert MATCHING['cjk'] == 'substring'
        assert MATCHING['cjk_ascii_boundary_space'] == 'ignored'
        assert MATCHING['ascii_multi_word'] == 'all_content_words', (
            '英文多词触发词必须是实词全中，回到任一实词命中就是 P0-2 之前的状态')


# ---------- C. 匹配语义（按契约逐条断言） ----------

SEMANTICS = [
    ('cjk-substring', '我有一份 scRNA-seq 数据，先做质控和双细胞去除', 'scrna-qc', True),
    ('cjk-substring-miss', '我有一份 scRNA-seq 数据，先做质控', 'paper-polish', False),
    ('ascii-multiword-needs-all', '这个 analysis 的 core 思路是什么', 'deg-analysis', False),
    ('ascii-multiword-any-alone', '这个 analysis 的 core 思路是什么', 'survival-analysis', False),
    ('ascii-multiword-full-hit', 'can you do a deg analysis for me', 'deg-analysis', True),
    ('ascii-multiword-partial-is-not-hit', 'could you design a nice poster for my lab',
     'figure-designer', False),
    ('case-fold', 'please run SCANPY on this dataset', 'scrnaseq-scanpy-core-analysis', True),
    ('boundary-space-latin-cjk', '帮我画一个 Figure 1 的柱状图，要 CNS 级别', 'nature-figure', True),
    ('boundary-space-cjk-latin', '这段话太像 AI 写的了', 'human-skill', True),
    ('boundary-space-no-space', '要 CNS级别', 'nature-figure', True),
]


class TestMatcherSemantics:
    @pytest.mark.parametrize('name,text,skill,expected', SEMANTICS, ids=[s[0] for s in SEMANTICS])
    def test_semantics(self, matcher, name, text, skill, expected):
        hits = matcher(text)
        assert (skill in hits) is expected, '%s：「%s」-> %s（期望 %s 命中=%s）' % (
            name, text, hits, skill, expected)

    def test_empty_inputs_return_empty(self, matcher):
        for text in ('', '   ', None, chr(10) + chr(9)):
            assert matcher(text) == [], '空输入必须返回空列表: %r' % (text,)

    def test_literature_library_exemption(self, matcher):
        hits = matcher('总结文献库里的这篇论文')
        blocked = set(EXEMPT['excludes'])
        assert not (set(hits) & blocked), (
            '本地文献库操作不该触发全局文献类 RED 技能：%s' % sorted(set(hits) & blocked))

    def test_hits_follow_index_order(self, matcher):
        hits = matcher('帮我做质控、批次校正，再画一个 Figure 1')
        order = [n for n, _ in (server._RED_TRIGGER_CACHE or [])]
        assert order, '匹配后缓存必须已构建'
        assert hits == [n for n in order if n in hits], (
            '命中顺序必须与索引行序一致（可复现）: %s' % hits)

    def test_hits_are_bounded_by_contract_ceiling(self, matcher):
        ceiling = MATCHING['max_hits_ceiling']
        for case in MATRIX['cases']:
            hits = matcher(case['text'])
            assert len(hits) <= ceiling, '「%s」命中 %d > 契约上限 %d: %s' % (
                case['text'], len(hits), ceiling, hits)


# ---------- D. 关键词质量棘轮（registry.check_keywords） ----------

def _entries(*items):
    return [{'name': n, 'level': lv, 'keywords': list(kw)} for n, lv, kw in items]


class TestKeywordRatchet:
    def test_live_corpus_passes_all_keyword_rules(self):
        problems = reg.check_keywords()
        assert problems == [], '现存技能触发词违反契约:' + chr(10) + '  ' + (chr(10) + '  ').join(problems[:20])

    def test_new_bare_generic_word_is_rejected(self):
        problems = reg.check_keywords(_entries(('zz-new', 'RED', ['analysis'])))
        assert any('新增裸通用词' in p for p in problems), problems

    def test_violation_spread_is_rejected(self):
        contract = _contract_with_ledger({'core': ['zz-other']})
        problems = reg.check_keywords(_entries(('zz-new', 'RED', ['core'])), contract=contract)
        assert any('蔓延' in p for p in problems), problems
        assert not any('新增裸通用词' in p for p in problems), (
            '台账里已有该词时只该报「蔓延」: %s' % problems)

    def test_stale_ratchet_entry_is_rejected(self):
        contract = _contract_with_ledger({'core': ['zz-other']})
        problems = reg.check_keywords(_entries(('zz-new', 'RED', ['质控'])), contract=contract)
        assert any('台账过期' in p for p in problems), problems

    def test_bare_cjk_generic_word_is_rejected(self):
        problems = reg.check_keywords(_entries(('zz-new', 'RED', ['整合'])))
        assert any('新增裸通用词' in p and '整合' in p for p in problems), problems

    def test_cjk_domain_phrases_are_allowed(self):
        problems = reg.check_keywords(_entries(
            ('zz-new', 'RED', ['多组学整合', '差异分析', '批次校正', '线粒体'])))
        assert not any('通用词' in p for p in problems), (
            '中文领域短语不该被通用词规则拦下：%s' % problems)

    def test_mixed_cjk_ascii_keyword_is_allowed(self):
        problems = reg.check_keywords(_entries(('zz-new', 'RED', ['QC质控', 'scrna-qc'])))
        assert not any('通用词' in p for p in problems), problems

    def test_short_ascii_acronym_rule_matches_contract(self):
        """短缩写边界长度必须与契约一致（改语义必须同时改契约）。"""
        rule = (CONTRACT.get('matching') or {}).get('short_ascii_boundary') or {}
        assert rule.get('max_len') == server._SHORT_ASCII_KW_MAX, (
            '短缩写边界长度与契约不一致：契约 %s / 代码 %s'
            % (rule.get('max_len'), server._SHORT_ASCII_KW_MAX))

    def test_short_ascii_acronym_does_not_match_inside_words(self):
        """P0-2b 极端测试实抓：纯子串匹配把英文词片段当成了缩写触发词。"""
        cases = [
            ('science 课上学了什么', 'nature-figure'),
            ('conscious 是什么意思', 'nature-figure'),
            ('scissors 在哪买', 'nature-figure'),
            ('帮我实现这个 algorithm', 'functional-enrichment'),
            ('mrna 表达量怎么看', 'mendelian-randomization-twosamplemr'),
            ('degree 是什么意思', 'deg-analysis'),
        ]
        for text, skill in cases:
            hits = server._match_red_skill_triggers(text)
            assert skill not in hits, '%s 误触发 %s: %s' % (text, skill, hits)

    def test_short_ascii_acronym_still_hits_when_standalone(self):
        """加了字母边界也不能伤召回：缩写独立出现（含汉字紧贴）必须照常命中。"""
        cases = [
            ('帮我做 SCI 级别的图', 'nature-figure'),
            ('SCI配图怎么弄', 'nature-figure'),
            ('QC 前先看看', 'scrna-qc'),
            ('先做一下QC', 'scrna-qc'),
            ('帮我做个 PPT', 'ppt-generator'),
            ('GO 富集分析', 'functional-enrichment'),
        ]
        for text, skill in cases:
            assert skill in server._match_red_skill_triggers(text), text

    def test_live_sources_have_no_bare_generic_words(self):
        """源头断言：比「有效触发词」更严 —— 被 BOILERPLATE 静默丢弃、被 16 条上限截断的尾巴都是隐患。

        实测（P0-2b）：scipilot-figure-skill/skill.json 写的「可视化」被 BOILERPLATE 静默丢掉，
        有效触发词里根本没有它，check_keywords 也就永远不会报 —— 只有查源头才发现。

        P0-2c：范围由 RED 扩到全等级 —— YEL/GRN 的触发词是「置顶技能自动触发」(_skill_trigger_hit)
        与 skill 目录搜索的直接输入，一个 cell / design 同样会让技能在无关句子里被命中。
        """
        leaks = []
        for name, e in sorted(_all_entries().items()):
            sj = os.path.join(e['dir'], 'skill.json')
            if os.path.isfile(sj):
                with open(sj, encoding='utf-8') as f:
                    data = json.load(f)
                for w in (data.get('trigger_keywords') or []):
                    if _bare_generic(w):
                        leaks.append('%s/skill.json -> %s' % (name, w))
            md = os.path.join(e['dir'], 'SKILL.md')
            if os.path.isfile(md):
                with open(md, encoding='utf-8') as f:
                    text = f.read()
                m = re.search(r'trigger_keywords\s*[:：]\s*(\[[^\]]*\])', text)
                if m:
                    try:
                        words = json.loads(m.group(1))
                    except ValueError:
                        words = [x.strip().strip('"') for x in m.group(1).strip('[]').split(',')]
                    for w in words:
                        if _bare_generic(w):
                            leaks.append('%s/SKILL.md -> %s' % (name, w))
        for name, words in sorted((reg._read_soul_red() or {}).items()):
            for w in (words or []):
                if _bare_generic(w):
                    leaks.append('SOUL.md 必触发表 -> %s (%s)' % (w, name))
        assert not leaks, ('源头还有裸通用词（会被 BOILERPLATE 静默丢弃 / 被 16 条上限截断，有效触发词视角看不见）:'
                           + chr(10) + '  ' + (chr(10) + '  ').join(leaks))

    def test_shape_rules_have_teeth(self):
        bad = _entries(('zz-short', 'RED', ['x']),
                       ('zz-dup', 'RED', ['质控', '质控']),
                       ('zz-red-empty', 'RED', []),
                       ('zz-many', 'RED', ['词%d' % i for i in range(20)]))
        joined = chr(10).join(reg.check_keywords(bad))
        for want in ('长度越界', '触发词重复', 'RED 技能无触发词', '超上限'):
            assert want in joined, '形状规则漏检 %s:' % want + chr(10) + joined

    def test_non_red_generic_word_is_rejected(self):
        """P0-2c：翻转 —— YEL/GRN 的裸通用词同样必须报错。

        P0-2b 时这里断言「放行」（只有 RED 进自动匹配）；实测 YEL 侧藏了 32 处
        （cell/design/core/remove…），它们会被置顶技能触发和目录搜索直接吃掉，所以范围扩到全等级。
        """
        for level, word in (('YEL', 'analysis'), ('GRN', 'cell'), ('YEL', 'design')):
            problems = reg.check_keywords(_entries(('zz-nonred', level, [word])))
            assert any('通用词' in p and 'zz-nonred' in p for p in problems), (
                '%s 的裸通用词 %s 必须被拦下（P0-2c 之前放行）: %s' % (level, word, problems))

    def test_name_derivation_never_emits_bare_generic_words(self):
        """根因回归（P0-2c）：脏数据的来源是「技能名分词 → 回填 skill.json」，必须堵在派生口。"""
        for name in ('design_primer', 'soupx-remove-background', 'debate-core', 'nature-shared',
                     'analyze_cell_senescence_and_apoptosis', 'core-remove-cell'):
            toks = reg._token_keywords(name)
            bad = [t for t in toks if _bare_generic(t)]
            assert not bad, '%s 的名称分词仍然产出裸通用词: %s' % (name, bad)
        # 名字本身（含空格的短语形态）不受影响，否则技能连自己的名字都搜不到
        kw = reg._name_keywords('design_primer', {})
        assert 'design primer' in kw, kw

    def test_cleaned_yel_skills_keep_domain_phrases(self):
        """清理不能把召回一起清掉：删掉的裸词必须在同一条触发词里有领域短语兜底。"""
        rows = _all_entries()
        want = {
            'design_primer': 'design primer',
            'sgrna-design': 'sgrna design',
            'doubletfinder-remove-doublets': 'remove doublets',
            'public-data-download': 'public data download',
            'quantify_and_cluster_cell_motility': 'cell motility',
            'web-research': '网络调研',
            'soupx-remove-background': '环境rna',
        }
        for name, phrase in sorted(want.items()):
            e = rows.get(name)
            assert e, '技能不见了: %s' % name
            kws = [str(k).lower() for k in e['keywords']]
            assert phrase.lower() in kws, '%s 丢了兜底短语 %s（现有 %s）' % (name, phrase, kws)

    def test_every_level_shares_one_ruler(self):
        """极端：三种等级同一把尺子；同时确认规则没有被做成「见到 cell 就报错」。"""
        for level in ('RED', 'YEL', 'GRN'):
            for word in ('cell', 'design', 'core', 'remove'):
                problems = reg.check_keywords(_entries(('zz-%s' % level.lower(), level, [word])))
                assert any('通用词' in p for p in problems), (
                    '%s 的 %s 没被拦下: %s' % (level, word, problems))
        ok = reg.check_keywords(_entries(('zz-phrase', 'YEL',
                                          ['cell motility', '环境rna', 'deg analysis', 'golden gate'])))
        assert not [p for p in ok if '通用词' in p], (
            '领域短语不该被通用词规则误伤: %s' % ok)
        # 中文侧同理：整条就是通用动词才报错，「多组学整合」这类短语放行
        bad = reg.check_keywords(_entries(('zz-cjk-bad', 'YEL', ['整合'])))
        assert any('通用词' in p for p in bad), bad
        good = reg.check_keywords(_entries(('zz-cjk-ok', 'YEL', ['多组学整合'])))
        assert not [p for p in good if '通用词' in p], good

    def test_check_wires_keyword_rules(self, monkeypatch):
        monkeypatch.setattr(reg, 'check_keywords', lambda *a, **k: ['人造问题'])
        assert '人造问题' in reg.check(), 'check() 必须包含关键词契约检查（门禁才有牙）'


# ---------- E. 缓存必须随索引 mtime 失效（旧实现在这里失败） ----------

def _fake_index(kw):
    rows = ['# MemOmics SKILLS_INDEX', '', '## 09_内置 (1 skills)', '',
            '| # | Skill | 使用场景 | 触发词 | Trigger |', '|---|---|---|---|---|',
            '| 1 | zz-cache-probe | 缓存热更新探针 | %s | RED 必触发 |' % kw]
    return chr(10).join(rows) + chr(10)


class TestTriggerCacheInvalidation:
    def test_cache_follows_index_mtime(self, tmp_path, monkeypatch):
        idx = tmp_path / 'SKILLS_INDEX.md'
        idx.write_text(_fake_index('cacheprobeold'), encoding='utf-8')
        monkeypatch.setattr(server, 'SKILLS_INDEX_PATH', str(idx))
        for attr in ('_SKILLS_INDEX_CACHE', '_SKILLS_INDEX_MTIME',
                     '_RED_TRIGGER_CACHE', '_RED_TRIGGER_CACHE_MTIME'):
            monkeypatch.setattr(server, attr, None)
        assert server._match_red_skill_triggers('cacheprobeold 怎么用') == ['zz-cache-probe']
        assert server._RED_TRIGGER_CACHE_MTIME == server._SKILLS_INDEX_MTIME, (
            '缓存必须记录它对应的索引 mtime，否则重建后无法判断是否过期')
        idx.write_text(_fake_index('cacheprobenew'), encoding='utf-8')
        stamp = time.time() + 5
        os.utime(str(idx), (stamp, stamp))
        hits = server._match_red_skill_triggers('cacheprobenew 怎么用')
        assert hits == ['zz-cache-probe'], (
            '索引重建后新触发词没生效（缓存没随 mtime 失效）：%s' % hits)
        assert server._match_red_skill_triggers('cacheprobeold 怎么用') == [], '索引重建后旧触发词必须失效'


# ---------- F. 契约 ↔ 回归矩阵一致性 ----------

class TestMatrixConsistency:
    def test_matrix_ceiling_not_looser_than_contract(self):
        ceiling = MATCHING['max_hits_ceiling']
        for case in MATRIX['cases']:
            assert case['max_hits'] <= ceiling, '用例 %s 的 max_hits=%d 比契约全局上限 %d 还松' % (
                case['id'], case['max_hits'], ceiling)
        for edge in MATRIX['edge_cases']:
            assert edge.get('max_hits', ceiling) <= ceiling

    def test_matrix_ratchets_are_converged(self):
        """P0-2b：7 条缺口修好、2 条过度触发收敛 → 两个棘轮清单清零。

        护栏不能跟着清零一起消失：转正的文本必须在 cases 里（must_hit 钉住），
        收敛的文本必须在 distractors 里（零命中断言接管）。
        """
        assert MATRIX['known_gaps'] == [], '缺口清单应已清零: %s' % MATRIX['known_gaps']
        assert MATRIX['known_over_triggers'] == [], '过度触发清单应已清零: %s' % MATRIX['known_over_triggers']
        texts = {c['text'] for c in MATRIX['cases']}
        missing = sorted(t for t in RETIRED_GAP_TEXTS if t not in texts)
        assert not missing, '转正的缺口文本必须留在 cases 里: %s' % missing
        dist = {d['text'] if isinstance(d, dict) else d for d in MATRIX['distractors']}
        missing = sorted(t for t in CONVERGED_OVER_TEXTS if t not in dist)
        assert not missing, '收敛的过度触发文本必须留在 distractors 里: %s' % missing

    def test_evidence_section_points_at_real_files(self):
        ev = CONTRACT['evidence']
        files = [ev['fixture']] + list(ev['tests']) + [ev['gate']]
        for item in files:
            rel = item.split('（')[0].split(' ')[0]
            assert os.path.exists(os.path.join(ROOT, rel)), '契约引用的文件不存在: %s' % rel
