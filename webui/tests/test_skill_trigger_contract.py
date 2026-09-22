# -*- coding: utf-8 -*-
"""触发词契约钉住测试（P0-2a）：contracts/skill_triggers.json 的每一条规则都要有牙。

背景：触发词规则原先只存在于 webui/server.py 的代码里，改语义没有任何护栏：
  · 英文多词触发词走「任一实词命中」，用户说一句 analysis 就命中 6 个无关技能；
  · RED 触发词缓存只在 None 时构建一次，索引重建后新技能永远匹配不到；
  · 中英之间打空格（「CNS 级别」「做 QC」）就漏召回，同一句话两种命运。
本文件把 contracts/skill_triggers.json 变成可执行契约：
  1. 契约文件结构 / 规则值 ↔ 代码常量（MIN_KW_LEN、MAX_KW_LEN、MAX_KW、停用词、豁免表）逐条相等；
  2. 匹配语义按契约断言（中文子串 / 英文实词全中 / 大小写无关 / 中英边界空白归一 / 文献库豁免）；
  3. 关键词质量用棘轮：新增裸通用词、违规蔓延、修好却不清台账都必须报错；
  4. 缓存必须绑定 SKILLS_INDEX 的 mtime（索引重建后立即可见）——旧实现这一条是红的。
"""
import json
import os
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
        assert KNOWN, '台账不能为空：存量违规要么修掉、要么留档'

    def test_known_violations_reference_real_skills(self, all_names):
        bad = sorted({s for owners in KNOWN.values() for s in owners} - all_names)
        assert not bad, '台账引用了不存在的技能（改名/删技能后要同步）: %s' % bad

    def test_known_violations_words_are_declared_forbidden(self):
        forbidden = {w.lower() for w in RULES.get('forbidden_bare_ascii_words') or []}
        extra = sorted(set(KNOWN) - forbidden)
        assert not extra, '台账里的词必须先写进 forbidden_bare_ascii_words: %s' % extra


# ---------- B. 代码常量 == 契约规则值 ----------

class TestCodeMatchesContract:
    def test_keyword_limits(self):
        assert reg.MIN_KW_LEN == RULES['min_len']
        assert reg.MAX_KW_LEN == RULES['max_len']
        assert reg.MAX_KW == RULES['max_per_skill']

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
        problems = reg.check_keywords(_entries(('zz-new', 'RED', ['core'])))
        assert any('蔓延' in p for p in problems), problems

    def test_stale_ratchet_entry_is_rejected(self):
        problems = reg.check_keywords(_entries(('zz-new', 'RED', ['质控'])))
        assert any('台账过期' in p for p in problems), problems

    def test_shape_rules_have_teeth(self):
        bad = _entries(('zz-short', 'RED', ['x']),
                       ('zz-dup', 'RED', ['质控', '质控']),
                       ('zz-red-empty', 'RED', []),
                       ('zz-many', 'RED', ['词%d' % i for i in range(20)]))
        joined = chr(10).join(reg.check_keywords(bad))
        for want in ('长度越界', '触发词重复', 'RED 技能无触发词', '超上限'):
            assert want in joined, '形状规则漏检 %s:' % want + chr(10) + joined

    def test_non_red_generic_word_is_allowed(self):
        problems = reg.check_keywords(_entries(('zz-yel', 'YEL', ['analysis'])))
        assert not any('通用词' in p for p in problems), (
            '只有 RED 行进自动匹配，YEL/GRN 不该被通用词规则拦下：%s' % problems)

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

    def test_matrix_ratchets_are_non_empty(self):
        assert MATRIX['known_over_triggers'], '过度触发清单不能为空（否则回归无人看守）'
        assert MATRIX['known_gaps'] is not None

    def test_evidence_section_points_at_real_files(self):
        ev = CONTRACT['evidence']
        files = [ev['fixture']] + list(ev['tests']) + [ev['gate']]
        for item in files:
            rel = item.split('（')[0].split(' ')[0]
            assert os.path.exists(os.path.join(ROOT, rel)), '契约引用的文件不存在: %s' % rel
