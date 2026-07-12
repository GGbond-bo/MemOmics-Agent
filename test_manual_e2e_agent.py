#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
MemOmics-Agent 手动端到端验收测试
模拟真实 agent 的多轮会话，验证 skill 触发 → 加载 → 执行全链路
"""
import os, re, json, sys

HERMES_HOME = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'hermes_home')
SKILLS_DIR = os.path.join(HERMES_HOME, 'skills', 'bioinformatics')

# Shared with skill_evolution._CN_GENERIC - bigrams matching these are skipped during L1 matching
_BIGRAM_STOPS = {
    '分析', '分类', '数据', '工具', '方法', '结果', '样本', '处理',
    '检测', '模型', '深度', '推断', '学习', '时间', '细胞',
}

class MockAgent:
    def __init__(self):
        self.session_id = 'test-session-001'
        self.trigger_rules = self._load_trigger_rules()
        self.keyword_index = self._build_keyword_index()
        print(f'[Agent] Session {self.session_id} started')
        print(f'[Agent] Loaded {len(self.trigger_rules)} L1 trigger rules')
        print(f'[Agent] Built {len(self.keyword_index)} keyword index entries')
    
    def _load_trigger_rules(self):
        rules = []
        with open(os.path.join(HERMES_HOME, 'SOUL.md'), 'r', encoding='utf-8') as f:
            text = f.read()
        for m in re.finditer(r'\|\s*(.+?)\s*\|\s*(.+?)\s*\|', text):
            kws = re.findall(r'"([^"]+)"', m.group(1))
            svs = re.findall(r'skill_view\("([^"]+)"\)', m.group(2))
            if kws and svs:
                rules.append((kws, svs))
        return rules
    
    def _build_keyword_index(self):
        index = {}
        for dirpath, dirnames, filenames in os.walk(SKILLS_DIR):
            for f in filenames:
                fpath = os.path.join(dirpath, f)
                if f == 'skill.json':
                    try:
                        data = json.load(open(fpath, 'r', encoding='utf-8'))
                    except:
                        continue
                    skill_name = data.get('name', '') or os.path.basename(dirpath)
                    tags = data.get('metadata', {}).get('hermes', {}).get('tags', [])
                    keywords = data.get('metadata', {}).get('hermes', {}).get('keywords', [])
                    all_kw = set(tags + keywords + [skill_name])
                    for kw in all_kw:
                        kw_lower = kw.lower().strip()
                        if kw_lower:
                            index.setdefault(kw_lower, []).append(skill_name)
        return index
    
    def skill_view(self, skill_name):
        skill_path = os.path.join(SKILLS_DIR, skill_name)
        if not os.path.isdir(skill_path):
            return {'error': f'Skill {skill_name} NOT FOUND', 'loaded': False}
        result = {'name': skill_name, 'loaded': True, 'path': skill_path}
        
        json_path = os.path.join(skill_path, 'skill.json')
        if os.path.exists(json_path):
            result['skill_json'] = json.load(open(json_path, 'r', encoding='utf-8'))
        
        md_path = os.path.join(skill_path, 'SKILL.md')
        if os.path.exists(md_path):
            content = open(md_path, 'r', encoding='utf-8').read()
            result['skill_md_lines'] = len(content.split('\n'))
            result['skill_md_size'] = len(content)
            result['has_scripts_dir'] = os.path.isdir(os.path.join(skill_path, 'scripts'))
            if result['has_scripts_dir']:
                result['scripts'] = os.listdir(os.path.join(skill_path, 'scripts'))
            result['has_references'] = bool(re.search(r'##\s+(?:References|参考资料|Citations)', content, re.I))
            result['has_code'] = bool(re.search(r'```(?:python|r|bash)', content))
            result['has_rail_review'] = 'rail_review' in content.lower()
            result['has_debate'] = 'debate_analysis' in content.lower()
            result['has_provenance'] = bool(re.search(r'(?:Source|Origin|来源|Provenance)', content, re.I))
            result['has_loop_verification'] = bool(re.search(r'(?:验证|铁轨|rail|loop|Loop Gate)', content, re.I))
        
        return result
    
    def process(self, message):
        print(f'\n[User] {message}')
        matched = None
        
        # L1: Trigger table
        msg_lower = message.lower()
        # Error keywords have top priority - check before normal matching
        for err_kw in ["报错", "error", "出错", "怎么修", "不工作", "跑不了", "fix", "debug"]:
            if err_kw.lower() in msg_lower:
                return self.skill_view("error-recovery")
        for keywords, skill_names in self.trigger_rules:
            for kw in keywords:
                if kw.lower() in msg_lower:
                    matched = ('L1-exact', skill_names[0], kw)
                    break
                if len(kw) == 4 and re.match(r'^[\u4e00-\u9fff]+$', kw):
                    for i in range(len(kw)-1):
                        bg = kw[i:i+2]
                        if bg not in _BIGRAM_STOPS and bg in message:
                            matched = ('L1-bigram', skill_names[0], bg)
                            break
            if matched:
                break
        
        # L2: Keyword index
        if not matched:
            scores = {}
            for kw, snames in self.keyword_index.items():
                if kw in msg_lower:
                    for sn in snames:
                        scores[sn] = scores.get(sn, 0) + 1
            if scores:
                best = max(scores, key=scores.get)
                matched = ('L2-index', best, f'score={scores[best]}')
        
        if not matched:
            print(f'  XX No match (L1+L2)')
            return None
        
        level, skill_name, detail = matched
        print(f'  >> [{level}] skill_view("{skill_name}")  [{detail}]')
        
        result = self.skill_view(skill_name)
        if result.get('error'):
            print(f'  !! {result["error"]}')
            return None
        
        status = []
        if result.get('skill_json'):
            desc = result['skill_json'].get('description', '')[:80]
            status.append(f'SKILL.md={result["skill_md_lines"]}L')
        if result.get('has_scripts_dir'):
            status.append(f'scripts={result["scripts"]}')
        if result.get('has_code'):
            status.append('has_code')
        if result.get('has_references'):
            status.append('has_refs')
        if result.get('has_rail_review'):
            status.append('rail_review')
        if result.get('has_debate'):
            status.append('debate')
        
        print(f'  OK {", ".join(status)}')
        if result.get('skill_json'):
            print(f'    desc: {desc}')
        
        return result


def main():
    agent = MockAgent()
    
    test_cases = [
        # (prompt, expected_skill, category)
        # === L1 exact matches ===
        ("Seurat标准分析流程", "scrnaseq-seurat-core-analysis", "L1-Seurat"),
        ("用Scanpy做单细胞分析", "scrnaseq-scanpy-core-analysis", "L1-Scanpy"),
        ("先做一下QC质控", "scrna-qc", "L1-QC"),
        ("对细胞进行聚类分群", "scrna-clustering", "L1-cluster"),
        ("做拟时序分析看发育轨迹", "trajectory-analysis", "L1-trajectory"),
        ("pseudotime trajectory inference", "trajectory-analysis", "L1-trajectory-EN"),
        ("用Monocle3做伪时间分析", "trajectory-analysis", "L1-Monocle"),
        ("用scTour做深度伪时间推断", "sctour-trajectory-inference", "L1-scTour"),
        ("VAE轨迹分析向量场", "sctour-trajectory-inference", "L1-VAE"),
        ("sctour pseudotime analysis", "sctour-trajectory-inference", "L1-scTour-EN"),
        ("差异表达分析找DEG", "deg-analysis", "L1-DEG"),
        ("differential expression between groups", "deg-analysis", "L1-DEG-EN"),
        ("做GO和KEGG富集分析", "functional-enrichment", "L1-enrichment"),
        ("pathway enrichment analysis", "functional-enrichment", "L1-enrichment-EN"),
        ("用CellChat做细胞通讯", "cellchat-v2", "L1-CellChat"),
        ("细胞间的通讯网络分析", "cellchat-v2", "L1-通讯"),
        ("做生存分析看预后", "survival-analysis", "L1-survival"),
        ("KM survival curve", "survival-analysis", "L1-survival-EN"),
        ("空间转录组分析", "spatial-transcriptomics", "L1-spatial"),
        ("多组学数据整合", "multi-omics-integration", "L1-multiomics"),
        ("做孟德尔随机化分析", "mendelian-randomization-twosamplemr", "L1-MR"),
        ("GWAS联合MR分析", "mendelian-randomization-twosamplemr", "L1-GWAS"),
        ("CellBender去除背景", "cellbender-remove-background", "L1-CellBender"),
        ("生成发表级CNS图", "cns-visualization", "L1-visualization"),
        ("数据可视化", "cns-visualization", "L1-viz"),
        
        # === L2 fuzzy ===
        ("细胞分化发育的轨迹是什么", "trajectory-analysis", "L2-分化"),
        ("哪些基因变化最显著", "deg-analysis", "L2-基因变化"),
        ("细胞之间怎么互相通讯的", "cellchat-v2", "L2-通讯模糊"),
        ("病人的生存预后怎么样", "survival-analysis", "L2-预后模糊"),
        ("先大致看看数据的特点", "scrna-eda", "L2-EDA"),
        
        # === error-recovery ===
        ("跑Seurat的时候报错了", "error-recovery", "L1-error-CN"),
        ("error: subscript out of bounds", "error-recovery", "L1-error-EN"),
        ("这个怎么修代码不工作了", "error-recovery", "L1-error-fix"),
        ("debug this problem", "error-recovery", "L1-error-debug"),
        
        # === scrna-eda ===
        ("帮我看看这个单细胞数据长什么样", "scrna-eda", "L1-EDA-看看"),
        ("EDA一下把数据概览做出来", "scrna-eda", "L1-EDA-概览"),
        ("data exploration overview", "scrna-eda", "L1-EDA-EN"),
    ]
    
    print(f'\n{"="*60}')
    print(f'TOTAL: {len(test_cases)} test prompts')
    print(f'{"="*60}')
    
    passed = 0
    failed = 0
    errors = []
    
    for i, (prompt, expected, category) in enumerate(test_cases):
        print(f'\n--- [{i+1}/{len(test_cases)}] {category} ---')
        result = agent.process(prompt)
        
        if result and result['name'] == expected:
            passed += 1
        elif result:
            # Hit but wrong skill
            errors.append((category, prompt, expected, result['name']))
            print(f'  ** MISMATCH: expected {expected}, got {result["name"]}')
            failed += 1
        else:
            errors.append((category, prompt, expected, 'NO_MATCH'))
            print(f'  ** NO MATCH: expected {expected}')
            failed += 1
    
    # === Simulate new session ===
    print(f'\n{"="*60}')
    print(f'NEW SESSION (simulated)')
    print(f'{"="*60}')
    agent2 = MockAgent()
    agent2.session_id = 'test-session-002'
    print(f'[Agent] Session {agent2.session_id} started')
    
    new_session_tests = [
        ("我要做scTour的深度伪时间轨迹推断", "sctour-trajectory-inference"),
        ("跑一下CellChat看看细胞间通讯", "cellchat-v2"),
        ("用Seurat做标准单细胞分析流程", "scrnaseq-seurat-core-analysis"),
        ("做差异基因DEG分析", "deg-analysis"),
        ("报错了帮我看看怎么修", "error-recovery"),
        ("先看看数据长什么样EDA一下", "scrna-eda"),
    ]
    
    for prompt, expected in new_session_tests:
        print(f'\n--- [New Session] ---')
        result = agent2.process(prompt)
        if result and result['name'] == expected:
            passed += 1
        elif result:
            errors.append(('NEW_SESSION', prompt, expected, result['name']))
            print(f'  ** MISMATCH: expected {expected}, got {result["name"]}')
            failed += 1
        else:
            errors.append(('NEW_SESSION', prompt, expected, 'NO_MATCH'))
            print(f'  ** NO MATCH: expected {expected}')
            failed += 1
    
    # === Summary ===
    total = passed + failed
    rate = passed / total * 100 if total else 0
    
    print(f'\n{"="*60}')
    print(f'FINAL RESULT')
    print(f'{"="*60}')
    print(f'Total: {total} | Passed: {passed} | Failed: {failed} | Rate: {rate:.1f}%')
    
    if errors:
        print(f'\nErrors ({len(errors)}):')
        for cat, prompt, exp, got in errors:
            print(f'  [{cat}] "{prompt[:40]}..." expected={exp} got={got}')
    
    return 0 if failed == 0 else 1

if __name__ == '__main__':
    sys.exit(main())
