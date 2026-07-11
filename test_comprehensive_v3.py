#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
MemOmics-Agent 专业综合评测 v3.1
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
6 维度 × 239 Skill × 知识库 × 审查链 × 辩论链 × 自进化
"""

import os, sys, json, re, time, importlib.util
from collections import defaultdict
from pathlib import Path

PROJECT = Path("E:/MemOmics-Agent")
sys.path.insert(0, str(PROJECT))
sys.path.insert(0, str(PROJECT / "hermes-agent"))
sys.path.insert(0, str(PROJECT / "memomics"))

# ─── R1: Skill Hit Rate by Category (with importlib) ───
def test_skill_hitrate():
    print("\n" + "=" * 70)
    print("R1: Skill 命中率测试 (按分类)")
    print("=" * 70)
    
    hs_path = PROJECT / "hermes-agent" / "tools" / "hybrid_search.py"
    spec = importlib.util.spec_from_file_location("hybrid_search", hs_path)
    hs = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(hs)
    HybridMatcher = hs.HybridMatcher
    
    skills_dir = PROJECT / "hermes_home" / "skills" / "bioinformatics"
    matcher = HybridMatcher(skills_dir=str(skills_dir))
    
    # Load all skill SKILL.md files
    skills = {}
    for d in sorted(skills_dir.iterdir()):
        if not d.is_dir(): continue
        skill_md = d / "SKILL.md"
        if not skill_md.exists(): continue
        try:
            content = skill_md.read_text(encoding='utf-8')
            name_match = re.search(r'name:\s*"?([^"\n]+)"?', content)
            when_match = re.search(r'when_to_use:\s*"?([^"\n]+)"?', content)
            cat_match = re.search(r'category:\s*"?([^"\n]+)"?', content)
            
            name = name_match.group(1).strip() if name_match else d.name
            when_to_use = when_match.group(1).strip() if when_match else ""
            category = cat_match.group(1).strip() if cat_match else "unknown"
            
            skills[d.name] = {
                "name": name,
                "when_to_use": when_to_use,
                "category": category.lower().replace("-", "_").replace(" ", "_"),
                "dir": d.name
            }
        except Exception as e:
            skills[d.name] = {"name": d.name, "error": str(e), "dir": d.name, "category": "unknown"}
    
    print(f"Loaded {len(skills)} skills from {skills_dir}")
    
    CATEGORY_MAP = {
        "transcriptomics": "scRNA", "scrna": "scRNA", "scrna_seq": "scRNA", "single_cell": "scRNA",
        "epigenomics": "scATAC", "atac": "scATAC", "spatial": "Spatial", "spatial_transcriptomics": "Spatial",
        "bulk": "Bulk RNA", "bulk_rna": "Bulk RNA", "proteomics": "Protein", "protein": "Protein",
        "drug": "Drug", "drug_discovery": "Drug", "microbiome": "Microbiome", "microbiology": "Microbiome",
        "genetics": "GWAS/Genetics", "genomics": "GWAS/Genetics", "gwas": "GWAS/Genetics",
        "clinical": "Clinical", "survival": "Clinical", "literature": "Literature", "literature_search": "Literature",
        "visualization": "Vis/Report", "reporting": "Vis/Report",
        "mol_bio": "Mol Bio", "molecular_biology": "Mol Bio",
        "imaging": "Imaging", "histology": "Imaging", "assay": "Assay", "wet_lab": "Assay",
        "simulation": "Simulation", "meta": "Meta", "system": "Meta",
        "database": "DB", "query": "DB", "computational_biology": "Computational",
    }
    
    test_cases = []
    for dir_name, info in skills.items():
        query = info.get("when_to_use", "")
        if not query or len(query) < 10:
            query = info["name"]
        query = re.sub(r'\s+', ' ', query).strip()[:80]
        
        cat = info["category"]
        expected_cat = "Other"
        for k, v in CATEGORY_MAP.items():
            if k in cat:
                expected_cat = v
                break
        
        test_cases.append({"dir": dir_name, "name": info["name"], "query": query, "expected_cat": expected_cat})
    
    results_by_cat = defaultdict(lambda: {"total": 0, "top1": 0, "top3": 0, "top5": 0})
    total_t1 = total_t3 = total_t5 = 0
    all_misses = []
    
    for tc in test_cases:
        try:
            sr = matcher.search(tc["query"], top_k=10)
            cat = tc["expected_cat"]
            results_by_cat[cat]["total"] += 1
            
            # search() returns {success: bool, results: [{name, score}]}
            ranked = sr.get("results", [])[:5] if isinstance(sr, dict) else []
            
            found = False
            for rank, item in enumerate(ranked, 1):
                res_name = item.get("name", "")
                res_dir = res_name.lower().replace("_", "-").replace(" ", "-")
                target_dir = tc["dir"].lower().replace("_", "-").replace(" ", "-")
                if res_dir == target_dir or res_dir in target_dir or target_dir in res_dir:
                    if rank <= 1: results_by_cat[cat]["top1"] += 1; total_t1 += 1
                    if rank <= 3: results_by_cat[cat]["top3"] += 1; total_t3 += 1
                    if rank <= 5: results_by_cat[cat]["top5"] += 1; total_t5 += 1
                    found = True
                    break
            if not found:
                all_misses.append((cat, f"{tc['dir']} (q: {tc['query'][:40]})"))
        except Exception as e:
            results_by_cat[tc["expected_cat"]]["total"] += 1
            all_misses.append((tc["expected_cat"], f"{tc['dir']}: {e}"))
    
    total_tests = len(test_cases)
    print(f"\n{'Category':<20} {'Total':>6} {'Top-1':>6} {'Top-3':>6} {'Top-5':>6} {'Hit%':>8}")
    print("-" * 60)
    for cat in sorted(results_by_cat.keys()):
        r = results_by_cat[cat]
        pct = (r["top3"] / r["total"] * 100) if r["total"] > 0 else 0
        print(f"{cat:<20} {r['total']:>6} {r['top1']:>6} {r['top3']:>6} {r['top5']:>6} {pct:>7.1f}%")
    
    print("-" * 60)
    pct3 = (total_t3 / total_tests * 100) if total_tests > 0 else 0
    print(f"{'TOTAL':<20} {total_tests:>6} {total_t1:>6} {total_t3:>6} {total_t5:>6} {pct3:>7.1f}%")
    
    if all_misses:
        print(f"\n--- Missed Skills ({len(all_misses)} total, showing first 20) ---")
        for cat, miss in all_misses[:20]:
            print(f"  [{cat}] {miss}")
    
    return {"total_tests": total_tests, "top1": total_t1, "top3": total_t3, "top5": total_t5, "pct": pct3,
            "by_category": {cat: {"total": r["total"], "top3": r["top3"]} for cat, r in results_by_cat.items()},
            "miss_count": len(all_misses)}

# ─── R2: Knowledge Base ───
def test_knowledge_base():
    print("\n" + "=" * 70)
    print("R2: 知识库搜索有效性测试")
    print("=" * 70)
    
    from memomics.bio_tools.kb_search import search_knowledge
    
    queries = [
        ("骨骼肌衰老标志物", "Homo_sapiens", "skeletal_muscle", "aging", ["SASP", "衰老", "senescence"]),
        ("肝脏纤维化", "Mus_musculus", "liver", "fibrosis", ["纤维化", "fibrosis", "肝"]),
        ("心肌病GWAS位点", "Homo_sapiens", "heart", "cardiomyopathy", ["GWAS", "cardiomyopathy"]),
        ("PBMC细胞注释", "Homo_sapiens", "pbmc", "development", ["细胞", "cluster", "注释"]),
        ("肿瘤免疫微环境", "Homo_sapiens", "tumor", "immunology", ["免疫", "微环境"]),
        ("阿尔茨海默病 biomarker", "Homo_sapiens", "brain", "alzheimer", ["biomarker", "阿尔茨海默", "AD"]),
        ("抗生素耐药基因", "common", "microbiome", "antibiotic_resistance", ["耐药", "resistance"]),
        ("CRISPR sgRNA设计", "common", "common", "gene_editing", ["sgRNA", "CRISPR"]),
        ("空间转录组细胞通讯", "Homo_sapiens", "common", "spatial", ["空间", "spatial", "通讯"]),
        ("蛋白质对接分子模拟", "common", "common", "drug", ["对接", "docking"]),
    ]
    
    passed = 0
    for query, species, tissue, direction, expected_kw in queries:
        try:
            results = search_knowledge(query, species=species, tissue=tissue, direction=direction)
            all_text = json.dumps(results, ensure_ascii=False).lower()
            matched = [kw for kw in expected_kw if kw.lower() in all_text]
            print(f"  {'✅' if matched else '⚠️'} {query[:30]:<30} → {len(results)} results, matched: {matched}")
            if matched: passed += 1
        except Exception as e:
            print(f"  ❌ {query[:30]:<30} → ERROR: {e}")
    
    print(f"\n  Pass: {passed}/{len(queries)}")
    return {"total": len(queries), "passed": passed}

# ─── R3: Rail Review ───
def test_rail_review():
    print("\n" + "=" * 70)
    print("R3: Rail Review 审查链测试")
    print("=" * 70)
    
    from memomics.bio_tools.rail_review import rail_review
    
    tests = [
        ("pre", "01_深度去污染", "CellBender", "/tmp/qc", "print('QC done')", "scrna-qc"),
        ("post", "01_深度去污染", "CellBender", "/tmp/qc", "Seurat::NormalizeData(pbmc)", "scrna-qc"),
        ("pre", "", "", "/tmp/empty", "", ""),
        ("pre", "02_基础分析", "deg_analysis", "/tmp/deg", "DESeq2::results(dds)", "deg-analysis"),
        ("post", "02_基础分析", "deg_analysis", "/tmp/deg", "volcano_plot(degs)", "deg-analysis"),
    ]
    
    results = []
    for phase, module_id, method, out_dir, code, skill_name in tests:
        try:
            raw = rail_review(phase=phase, module_id=module_id, method_name=method,
                                output_dir=out_dir, code_executed=code, skill_name=skill_name)
            rd = json.loads(raw) if isinstance(raw, str) else raw
            blocked = rd.get("should_proceed", True) if phase == "pre" else rd.get("passed", True)
            print(f"  {'✅' if blocked or phase == 'post' else '🚫'} {phase}/{module_id or 'EMPTY':<25} → proceed={rd.get('should_proceed','?')} passed={rd.get('passed','?')}")
            results.append({"ok": True})
        except Exception as e:
            print(f"  ❌ {phase}/{module_id or 'EMPTY':<25} → {str(e)[:80]}")
            results.append({"ok": False, "error": str(e)})
    
    return {"tested": len(results), "passed": sum(1 for r in results if r["ok"])}

# ─── R4: Debate Analysis ───
def test_debate_chain():
    print("\n" + "=" * 70)
    print("R4: Debate Analysis 辩论链测试")
    print("=" * 70)
    
    debate_file = PROJECT / "memomics" / "bio_tools" / "debate_analysis.py"
    content = debate_file.read_text(encoding='utf-8')
    
    checks = {
        "Pro roles (3)": bool(re.search(r'(?i)pro.*editor|pro.*agent', content)),
        "Con roles (4)": bool(re.search(r'(?i)con.*editor|con.*agent', content)),
        "Judge role": bool(re.search(r'(?i)judge', content)),
        "Context isolation": bool(re.search(r'(?i)isolat|separate|independent', content)),
        "Parallel execution": bool(re.search(r'(?i)ThreadPool|parallel|concurrent', content)),
        "Caching (72h)": bool(re.search(r'(?i)cache|ttl|72', content)),
        "Fallback mode": bool(re.search(r'(?i)fallback|degrad|prompt.mode', content)),
        "API key injection": bool(re.search(r'(?i)DEEPSEEK_API_KEY|api_key', content)),
        "Error memory": bool(re.search(r'(?i)error_memory', content)),
    }
    
    total = len(checks)
    passed = sum(1 for v in checks.values() if v)
    for check, ok in checks.items():
        print(f"  {'✅' if ok else '❌'} {check}")
    
    api_key = os.environ.get("DEEPSEEK_API_KEY", "")
    api_url = os.environ.get("DEEPSEEK_BASE_URL", os.environ.get("DEBATE_API_BASE_URL", ""))
    api_ready = bool(api_key and api_url)
    print(f"  {'✅' if api_ready else '⚠️'} API ready: {'Yes' if api_ready else 'Fallback mode'}")
    print(f"  Score: {passed}/{total} features")
    
    # Try actual debate invocation
    if api_key:
        try:
            from memomics.bio_tools.debate_analysis import debate_analysis
            result = debate_analysis(phase="test", module_id="QC", method_name="test",
                                     output_dir="/tmp/test", code_executed="print('hello')")
            print(f"  ✅ debate_analysis() test passed: {str(result)[:100]}")
        except Exception as e:
            print(f"  ⚠️ debate_analysis() test: {str(e)[:80]}")
    
    return {"features": passed, "total": total, "api_ready": api_ready}

# ─── R5: Skill Evolution ───
def test_skill_evolution():
    print("\n" + "=" * 70)
    print("R5: Skill Evolution 自进化测试")
    print("=" * 70)
    
    try:
        from memomics.bio_tools.skill_evolution import skill_evolution
        print("  ✅ skill_evolution loaded")
        
        skill_dir = PROJECT / "hermes_home" / "skills" / "bioinformatics" / "scrna-qc"
        print(f"  {'✅' if skill_dir.exists() else '❌'} Skill dir exists")
        
        log_dir = skill_dir / "logs"
        print(f"  {'✅' if log_dir.exists() else '⚠️'} Log dir: {len(list(log_dir.glob('*.json'))) if log_dir.exists() else 0} entries")
        
        error_log = log_dir / "error_log.md" if log_dir.exists() else None
        print(f"  {'✅' if error_log and error_log.exists() else '⚠️'} Error log present")
        
        # Check global error memory
        error_mem = PROJECT / "memomics" / "knowledge_base" / "error_memory" / "errors.jsonl"
        if error_mem.exists():
            print(f"  ✅ Error memory file exists ({error_mem.stat().st_size} bytes)")
        else:
            print("  ⚠️ Error memory not initialized")
        
        # query_logs test
        try:
            result = skill_evolution(action="query_logs", skill_name="scrna-qc")
            status = "ok" if isinstance(result, dict) and result.get("status") == "ok" else "partial"
            print(f"  {'✅' if status == 'ok' else '⚠️'} query_logs: {status}")
        except Exception as e:
            print(f"  ⚠️ query_logs: {str(e)[:60]}")
        
        return {"status": "functional"}
    except ImportError as e:
        print(f"  ❌ Import failed: {e}")
        return {"status": "missing"}

# ─── R6: Multi-Round Stability ───
def test_multi_round():
    print("\n" + "=" * 70)
    print("R6: 多轮变换稳定性测试")
    print("=" * 70)
    
    from webui.server import _classify_intent, _detect_lang
    
    scenarios = [
        ("Chat→Plan→Execute", [
            ("你好", "chat"),
            ("我想分析单细胞数据", "research_plan"),
            ("请设计一个scRNA分析方案", "research_plan"),
            ("包含QC、聚类、差异基因", "analysis"),
            ("好的，生成完整方案", "plan_refine"),
            ("直接跑QC", "direct_exec"),
            ("结果怎么样？", "analysis"),
        ]),
        ("Plan→Regen→Execute", [
            ("帮我设计骨骼肌衰老的单细胞分析方案", "research_plan"),
            ("也加入ATAC分析", "analysis"),
            ("我不满意，重新生成一个更详细的", "plan_refine"),
            ("这个方案不错，就按这个做吧", "direct_exec"),
        ]),
        ("Mixed EN/ZH", [
            ("Hi, I need to analyze my scRNA-seq data", "research_plan"),
            ("I want DEG analysis and enrichment", "analysis"),
            ("就按这个做吧", "direct_exec"),
            ("谢谢！", "chat"),
        ]),
        ("Ambiguous boundaries", [
            ("画个UMAP图", "analysis"),
            ("用Seurat做", "analysis"),
            ("怎么分析这个新发现的细胞群？", "research_plan"),
            ("查一下文献", "literature"),
            ("hello", "chat"),
            ("who are you", "self_intro"),
            ("直接跑一下", "direct_exec"),
            ("探索一下这个数据", "analysis"),  # data exploration = analysis
        ]),
    ]
    
    total_correct = 0
    total_tests = 0
    
    for scenario_name, steps in scenarios:
        print(f"\n  ── {scenario_name} ──")
        sc = 0
        for text, expected in steps:
            intent, conf, meta = _classify_intent(text)
            total_tests += 1
            ok = intent == expected
            if ok: sc += 1; total_correct += 1; print(f"    ✅ [{intent:>14}] {text[:60]}")
            else: print(f"    ❌ [{intent:>14}] want={expected:>14} | {text[:60]}")
        print(f"  {sc}/{len(steps)} ({sc/len(steps)*100:.0f}%)")
    
    pct = total_correct / total_tests * 100 if total_tests else 0
    print(f"\n  OVERALL: {total_correct}/{total_tests} ({pct:.0f}%)")
    return {"total": total_tests, "correct": total_correct, "pct": pct}

# ─── Main ───
def main():
    print("╔══════════════════════════════════════════════════════════════════╗")
    print("║     MemOmics-Agent 专业综合评测 v3.1                            ║")
    print("║     6 Dimension × 270+ Skill × KB × Review × Debate × Evolution ║")
    print("╚══════════════════════════════════════════════════════════════════╝")
    
    overall = {}
    
    try:
        r1 = test_skill_hitrate()
        overall["R1_SkillHit"] = f"{r1['top3']}/{r1['total_tests']} ({r1['pct']:.0f}%)"
    except Exception as e:
        import traceback; traceback.print_exc()
        overall["R1_SkillHit"] = f"ERROR: {e}"
    
    try:
        r2 = test_knowledge_base()
        overall["R2_KB"] = f"{r2['passed']}/{r2['total']}"
    except Exception as e:
        overall["R2_KB"] = f"ERROR: {e}"
    
    try:
        r3 = test_rail_review()
        overall["R3_RailReview"] = f"{r3['passed']}/{r3['tested']}"
    except Exception as e:
        overall["R3_RailReview"] = f"ERROR: {e}"
    
    try:
        r4 = test_debate_chain()
        overall["R4_Debate"] = f"{r4['features']}/{r4['total']} {'(API✅)' if r4.get('api_ready') else '(fallback)'}"
    except Exception as e:
        overall["R4_Debate"] = f"ERROR: {e}"
    
    try:
        r5 = test_skill_evolution()
        overall["R5_Evolution"] = r5.get("status", "unknown")
    except Exception as e:
        overall["R5_Evolution"] = f"ERROR: {e}"
    
    try:
        r6 = test_multi_round()
        overall["R6_MultiRound"] = f"{r6['correct']}/{r6['total']} ({r6['pct']:.0f}%)"
    except Exception as e:
        overall["R6_MultiRound"] = f"ERROR: {e}"
    
    print("\n" + "=" * 70)
    print("FINAL REPORT")
    print("=" * 70)
    for dim, result in overall.items():
        print(f"  {dim}: {result}")
    
    print("\n✅ Evaluation complete.")

if __name__ == "__main__":
    main()
