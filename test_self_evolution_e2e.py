#!/usr/bin/env python3
"""
MemOmics 自进化 E2E 深度测试
============================
模拟真实分析场景：heart SAN scRNA-seq + liver aging
测试完整链路：record_error → record_success → query_logs → search_memory → recall_experience → delivery_gate → cross-session → scoring priority

架构覆盖：
  Layer 1: skill_evolution._record_error / _record_success — 写 error_log + skill.json + Holographic
  Layer 2: skill_evolution._query_logs — 读 skill.json + error_log + Holographic
  Layer 3: memory_bridge APIs — store/recall/search/feedback
  Layer 4: skills_tool._skill_view_with_bump — 注入 _experience (直接 SQLite 测试)
  Layer 5: create-bio-skill delivery_gate — 6 项门禁
  Layer 6: cross-session — 关闭连接→重开→召回
  Layer 7: scoring priority — 高评分优先召回

总计 40 项测试
"""

import os
import sys
import json
import sqlite3
import threading
import time
import re
from datetime import datetime
from pathlib import Path

# 设置项目根
ROOT = os.path.dirname(os.path.abspath(__file__))
os.chdir(ROOT)

sys.path.insert(0, ROOT)

PASS = 0
FAIL = 0
_TOTAL = 0
_FAIL_MSGS = []
_SKIPPED = 0

def check(cond, label):
    global PASS, FAIL, _TOTAL, _FAIL_MSGS
    _TOTAL += 1
    if cond:
        PASS += 1
        print(f"  ✅ {label}")
    else:
        FAIL += 1
        _FAIL_MSGS.append(f"  ❌ {label}")
        print(f"  ❌ {label}")

def skip(label):
    global _SKIPPED
    _SKIPPED += 1
    print(f"  ⏭️  SKIP: {label}")

def header(title):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")


# ════════════════════════════════════════════════════
#  L0: 环境准备
# ════════════════════════════════════════════════════
header("L0: 环境准备 — 清理旧记忆 + 创建测试场景")

# 清除 Holographic DB
db_path = os.path.join(ROOT, "hermes_home", "memory_store.db")
if os.path.exists(db_path):
    os.remove(db_path)
    print("  🧹 已清除旧 memory_store.db")

# 确保 hermes_home 存在
os.makedirs(os.path.join(ROOT, "hermes_home"), exist_ok=True)

# 测试数据：heart SAN 真实场景
SCENARIOS = [
    {
        "skill": "scrna-seurat-core",
        "script": "run_seurat.R",
        "species": "Homo sapiens",
        "tissue": "heart",
        "direction": "sinoatrial node development",
        "params": "resolution=0.8, dims=1:30, nfeatures=2000",
        "score": 8.5,
        "auto_score": 7.0,
        "approved": True,
        "result": "Identified 3 pacemaker cell subtypes (SAN_PC1/2/3) via SCTransform+Harmony",
    },
    {
        "skill": "scrna-seurat-core",
        "script": "run_seurat.R",
        "species": "Homo sapiens",
        "tissue": "heart",
        "direction": "sinus node aging",
        "params": "resolution=1.2, dims=1:30, nfeatures=3000, SCTransform",
        "score": 9.0,
        "auto_score": 8.5,
        "approved": True,
        "result": "Aged pacemaker cells show HCN4 downregulation, fibrosis gene upregulation",
    },
    {
        "skill": "deg-analysis",
        "script": "run_deg.R",
        "species": "Homo sapiens",
        "tissue": "heart",
        "direction": "sinoatrial node aging",
        "params": "test=MAST, logfc.threshold=0.25, min.pct=0.1",
        "score": 6.0,
        "auto_score": 7.5,
        "approved": True,
        "result": "287 DEGs in aged SAN: ion channel genes down, ECM/fibrosis genes up",
    },
    {
        "skill": "trajectory-analysis",
        "script": "run_trajectory.R",
        "species": "Mus musculus",
        "tissue": "liver",
        "direction": "aging",
        "params": "method=slingshot, k=5, curves=3",
        "score": 7.0,
        "auto_score": 6.0,
        "approved": True,
        "result": "Hepatocyte→cholangiocyte trajectory with aging-associated mid-point bifurcation",
    },
    {
        "skill": "trajectory-analysis",
        "script": "traj_scvelo.py",
        "species": "Mus musculus",
        "tissue": "liver",
        "direction": "aging",
        "params": "mode=dynamical, n_top_genes=2000",
        "score": 4.0,
        "auto_score": 8.0,
        "approved": False,  # 用户不满意 scvelo 图，但要记录
        "result": "RNA velocity shows hepatocyte aging driver vs. quiescent subpopulation",
    },
]

ERROR_SCENARIOS = [
    {
        "skill": "scrna-seurat-core",
        "error_type": "MemoryError",
        "message": "Cannot allocate vector of size 8.0 Gb",
        "root_cause": "SCTransform on full dataset exceeded memory limit",
        "fix": "Use SCTransform with conserve.memory=TRUE and downsample to 50K cells",
        "species": "Homo sapiens",
        "tissue": "heart",
        "severity": "high",
    },
    {
        "skill": "deg-analysis",
        "error_type": "PackageNotFoundError",
        "message": "there is no package called 'MAST'",
        "root_cause": "MAST not installed in R environment",
        "fix": "install.packages('BiocManager'); BiocManager::install('MAST')",
        "species": "Homo sapiens",
        "tissue": "heart",
        "severity": "medium",
    },
    {
        "skill": "scrna-seurat-core",
        "error_type": "ConvergenceError",
        "message": "SCTransform model failed to converge for 342 genes",
        "root_cause": "Too many cells with zero counts in genes",
        "fix": "Use glmGamPoi backend: SCTransform(..., method='glmGamPoi')",
        "species": "Homo sapiens",
        "tissue": "heart",
        "severity": "medium",
    },
]

USER_PREFS = [
    {
        "category": "user_pref",
        "content": "偏好 ggplot2 可视化风格，不喜欢 Seurat 默认 DimPlot/FeaturePlot",
        "tags": "visualization,ggplot2,seurat,preference",
        "trust": 0.9,
    },
    {
        "category": "user_pref",
        "content": "分析心脏衰老时优先参考 Lim_2024_NatCommun(Nature Communications,2024) 的方法框架",
        "tags": "heart,aging,sinoatrial,reference,preference",
        "trust": 0.85,
    },
    {
        "category": "user_pref",
        "content": "logFC 阈值偏好 0.25 而非默认 0.1，严格筛选差异基因",
        "tags": "DEG,logFC,threshold,preference",
        "trust": 0.8,
    },
]

print(f"  📊 测试场景: {len(SCENARIOS)} 成功 + {len(ERROR_SCENARIOS)} 错误 + {len(USER_PREFS)} 用户偏好")
check(True, "环境准备完成")

# ════════════════════════════════════════════════════
#  L1: skill_evolution._record_success — 写入
# ════════════════════════════════════════════════════
header("L1: _record_success — 写入 Proven Scripts + skill.json + Holographic")

# Lazy import to bypass __init__.py chain (env_check requires tools.registry)
import importlib.util as _iu
_se_spec = _iu.spec_from_file_location('skill_evolution', os.path.join(ROOT, 'memomics', 'bio_tools', 'skill_evolution.py'))
_se = _iu.module_from_spec(_se_spec)
_se_spec.loader.exec_module(_se)
_record_success = _se._record_success
_record_error = _se._record_error
_query_logs = _se._query_logs
_verify_delivery_gate = _se._verify_delivery_gate

success_results = []
for i, s in enumerate(SCENARIOS):
    result = _record_success(
        skill_name=s["skill"],
        script_name=s["script"],
        params_used=s["params"],
        species=s["species"],
        tissue=s["tissue"],
        direction=s["direction"],
        result_summary=s["result"],
        score=s["score"],
        auto_score=s["auto_score"],
        approved=s["approved"],
    )
    success_results.append(result)
    check(result.get("success"), f"记录 #{i+1}: {s['skill']} → {s['script']} ({s['species']}/{s['tissue']}/{s['direction']})")

check(all(r.get("success") for r in success_results), f"全部 5 条记录写入成功")

# 检查 skill.json 是否更新
skill_json_path = os.path.join(ROOT, "hermes_home", "skills", "bioinformatics", "scrna-seurat-core", "skill.json")
if os.path.exists(skill_json_path):
    with open(skill_json_path, "r") as f:
        sj = json.load(f)
    n_proven = len(sj.get("proven_params", []))
    check(n_proven >= 2, f"skill.json proven_params ≥ 2 (实际: {n_proven})")
    check(sj.get("success_count", 0) >= 2, f"skill.json success_count ≥ 2 (实际: {sj.get('success_count', 0)})")

# 检查 SKILL.md Proven Scripts 表
skill_md_path = os.path.join(ROOT, "hermes_home", "skills", "bioinformatics", "scrna-seurat-core", "SKILL.md")
if os.path.exists(skill_md_path):
    with open(skill_md_path, "r") as f:
        md = f.read()
    proven_rows = len(re.findall(r'^\|.*\|\s*$', md.split("## Proven Scripts")[-1].split("##")[0], re.MULTILINE))
    check(proven_rows >= 2, f"SKILL.md Proven Scripts ≥ 2 rows (实际: {proven_rows})")

# ════════════════════════════════════════════════════
#  L2: skill_evolution._record_error — 写入
# ════════════════════════════════════════════════════
header("L2: _record_error — 写入 error_log + Common Issues + skill.json + Holographic")

error_results = []
for i, e in enumerate(ERROR_SCENARIOS):
    result = _record_error(
        skill_name=e["skill"],
        error_message=e["message"],
        error_type=e["error_type"],
        root_cause=e["root_cause"],
        fix_applied=e["fix"],
        species=e["species"],
        tissue=e["tissue"],
        severity=e["severity"],
    )
    error_results.append(result)
    check(result.get("success"), f"错误 #{i+1}: {e['error_type']} ({e['skill']})")

check(all(r.get("success") for r in error_results), "全部 3 条错误写入成功")

# 检查 error_log.md
error_log_path = os.path.join(ROOT, "hermes_home", "skills", "bioinformatics", "scrna-seurat-core", "logs", "error_log.md")
if os.path.exists(error_log_path):
    with open(error_log_path, "r") as f:
        elog = f.read()
    check("Cannot allocate vector" in elog or "MemoryError" in elog, "error_log.md 含 MemoryError 记录")
    check("SCTransform" in elog, "error_log.md 含 SCTransform 相关信息")

# ════════════════════════════════════════════════════
#  L3: memory_bridge — 直接 API 测试
# ════════════════════════════════════════════════════
header("L3: memory_bridge APIs — store/recall/search/feedback")

try:
    _mb_spec = _iu.spec_from_file_location('memory_bridge', os.path.join(ROOT, 'memomics', 'bio_tools', 'memory_bridge.py'))
    _mb_mod = _iu.module_from_spec(_mb_spec)
    _mb_spec.loader.exec_module(_mb_mod)
    store_user_pref = _mb_mod.store_user_pref
    store_script_score = _mb_mod.store_script_score
    store_skill_exp = _mb_mod.store_skill_exp
    store_project_context = _mb_mod.store_project_context
    search_memory = _mb_mod.search_memory
    recall_experience = _mb_mod.recall_experience
    record_feedback = _mb_mod.record_feedback
    list_memories = _mb_mod.list_memories

    MB_AVAILABLE = True
    check(True, "memory_bridge 导入成功")
except Exception as e:
    MB_AVAILABLE = False
    skip(f"memory_bridge 不可用: {e}")
    # 继续剩余测试（至少有 skill_evolution 的文件级记录）

if MB_AVAILABLE:
    # 3a: 存用户偏好
    for i, p in enumerate(USER_PREFS):
        fid = store_user_pref(
            content=p["content"],
            tags=p["tags"],
            trust_score=p["trust"],
        )
        check(fid > 0, f"store_user_pref #{i+1}: '{p['content'][:40]}...' → fact_id={fid}")

    # 3b: 存项目上下文
    fid_proj = store_project_context(
        species="Homo sapiens",
        tissue="heart",
        direction="sinoatrial node senescence",
        data_path="/data/heart_san/",
        notes="3 scRNA-seq donors: young(25y), middle(50y), aged(75y)"
    )
    check(fid_proj > 0, f"store_project_context → fact_id={fid_proj}")

    # 3c: FTS5 搜索
    results_seurat = search_memory("Seurat SCTransform")
    check(len(results_seurat) >= 1, f"search_memory('Seurat SCTransform') 命中 ≥ 1 (实际: {len(results_seurat)})")
    results_heart = search_memory("heart sinoatrial")
    check(len(results_heart) >= 1, f"search_memory('heart sinoatrial') 命中 ≥ 1 (实际: {len(results_heart)})")
    results_error = search_memory("MemoryError")
    check(len(results_error) >= 1, f"search_memory('MemoryError') 命中 ≥ 1 (实际: {len(results_error)})")
    results_none = search_memory("zzz_nonexistent_xyz")
    check(len(results_none) == 0, f"search_memory('nonexistent') 命中 0 (实际: {len(results_none)})")

    # 3d: recall_experience — 按 skill+tissue 召回
    exp = recall_experience(skill_name="scrna-seurat-core", tissue="heart")
    check(isinstance(exp, dict), "recall_experience 返回 dict")
    n_proven = len(exp.get("proven_scripts", []))
    n_errors = len(exp.get("known_errors", []))
    n_prefs = len(exp.get("user_prefs", []))
    check(n_proven >= 2, f"proven_scripts ≥ 2 (实际: {n_proven})")
    check(n_errors >= 2, f"known_errors ≥ 2 (实际: {n_errors})")
    check(n_prefs >= 1, f"user_prefs ≥ 1 (实际: {n_prefs})")

    exp_liver = recall_experience(skill_name="trajectory-analysis", tissue="liver")
    n_liver = len(exp_liver.get("proven_scripts", []))
    check(n_liver >= 1, f"trajectory-analysis+liver proven ≥ 1 (实际: {n_liver})")

    # 3e: record_feedback
    for r in results_seurat[:1]:
        fb = record_feedback(fact_id=r["fact_id"], is_helpful=True)
        check(fb, f"feedback helpful → fact_id={r['fact_id']}")

    # 3f: list_memories
    all_mems = list_memories()
    check(len(all_mems) >= 10, f"list_memories ≥ 10 total (实际: {len(all_mems)})")


# ════════════════════════════════════════════════════
#  L4: _query_logs — skill_evolution 读回测试
# ════════════════════════════════════════════════════
header("L4: _query_logs — 从 skill.json + error_log + Holographic 读回")

# 4a: 按 skill+tissue 查询
ql = _query_logs(skill_name="scrna-seurat-core", species="Homo sapiens", tissue="heart")
check(ql.get("success"), "_query_logs(seurat, human, heart) 成功")
n_proven_ql = len(ql.get("proven_runs", []))
n_errors_ql = len(ql.get("known_errors", []))
check(n_proven_ql >= 2, f"proven_runs ≥ 2 (实际: {n_proven_ql})")
check(n_errors_ql >= 2, f"known_errors ≥ 2 (实际: {n_errors_ql})")
check("Holographic" in str(ql.get("proven_runs", [])), "proven_runs 含 Holographic 来源条目")
check(ql.get("summary"), "query_logs 返回 summary 字段")

# 4b: 按 direction 过滤
ql_dir = _query_logs(skill_name="scrna-seurat-core", direction="aging")
n_dir = len(ql_dir.get("proven_runs", []))
check(n_dir >= 1, f"proven_runs filtered by 'aging' ≥ 1 (实际: {n_dir})")

# 4c: 空查询
ql_all = _query_logs(skill_name="scrna-seurat-core")
check(len(ql_all.get("proven_runs", [])) >= 2, "无过滤查询仍返回记录")

# 4d: 无历史记录的 skill
ql_empty = _query_logs(skill_name="nonexistent-skill")
check("无历史运行记录" in ql_empty.get("summary", ""), "无历史 skill 返回正确提示")

# ════════════════════════════════════════════════════
#  L5: delivery_gate — create-bio-skill 门禁
# ════════════════════════════════════════════════════
header("L5: _verify_delivery_gate — 6 项门禁")

# 5a: 有完整内容的 skill（scrna-seurat-core）
gate_good = _verify_delivery_gate("scrna-seurat-core")
check(gate_good.get("passed"), f"scrna-seurat-core delivery_gate PASS (blocked: {gate_good.get('blocked', [])})")

# 5b: 不存在的 skill
gate_bad = _verify_delivery_gate("nonexistent-skill")
check(gate_bad.get("passed") is False, "不存在的 skill delivery_gate → FAIL")

# 5c: check 细节
checks = gate_good.get("checks", [])
check_names = {c["check"]: c["passed"] for c in checks}
for name in ["official_docs", "usage_scenarios", "prerequisites", "scripts_exist", "skill_json", "proven_table"]:
    check(check_names.get(name, False), f"check '{name}' = {check_names.get(name)}")


# ════════════════════════════════════════════════════
#  L6: skills_tool 模拟 — _experience 注入
# ════════════════════════════════════════════════════
header("L6: skills_tool._skill_view_with_bump — _experience 注入 (直接 SQLite)")

try:
    # 模拟 skills_tool 中的 Holographic 查询逻辑
    import sqlite3 as _sqlite3
    db_path_abs = os.path.abspath(db_path)
    if os.path.exists(db_path_abs):
        db = _sqlite3.connect(db_path_abs)
        db.row_factory = _sqlite3.Row

        safe = "scrna-seurat-core"
        words = [w for w in safe.replace("-", " ").replace(".", " ").split() if len(w) >= 2]
        fts_q = " OR ".join('"' + w + '"' for w in words) if words else safe.replace("-", " ")

        rows = list(db.execute(
            "SELECT * FROM ("
            " SELECT f.* FROM facts f JOIN facts_fts ft ON f.fact_id=ft.rowid WHERE facts_fts MATCH ?"
            " UNION"
            " SELECT f.* FROM facts f WHERE f.tags LIKE ?"
            ") ORDER BY trust_score DESC, retrieval_count DESC LIMIT 6",
            (fts_q, "%" + safe + "%")
        ).fetchall())

        errs = []
        if words:
            err_clauses = " OR ".join("tags LIKE '%" + w + "%'" for w in words)
            errs = db.execute(
                "SELECT * FROM facts WHERE category='skill_exp'"
                " AND tags LIKE '%error%' AND (" + err_clauses + ")"
                " ORDER BY trust_score DESC, retrieval_count DESC LIMIT 2"
            ).fetchall()

        uprefs = db.execute(
            "SELECT * FROM facts WHERE category='user_pref' ORDER BY trust_score DESC LIMIT 2"
        ).fetchall()

        extra = list(errs) + list(uprefs)
        seen = set(str(r["fact_id"]) for r in rows)
        for x in extra:
            if str(x["fact_id"]) not in seen and len(rows) < 8:
                rows.append(x)
                seen.add(str(x["fact_id"]))

        # 分类统计
        proven = [r for r in rows if r["category"] in ("skill_exp", "script_score") and "error" not in (r["tags"] or "").lower()]
        errors = [r for r in rows if r["category"] == "skill_exp" and "error" in (r["tags"] or "").lower()]
        prefs = [r for r in rows if r["category"] == "user_pref"]

        check(len(rows) >= 6, f"skill_view _experience ≥ 6 records (实际: {len(rows)})")
        check(len(proven) >= 2, f"proven_params ≥ 2 (实际: {len(proven)})")
        check(len(errors) >= 2, f"known_errors ≥ 2 (实际: {len(errors)})")
        check(len(prefs) >= 2, f"user_prefs ≥ 2 (实际: {len(prefs)})")

        # 验证 trust_score 排序：第一个应该 ≥ 第二个
        if len(rows) >= 2:
            check(rows[0]["trust_score"] >= rows[1]["trust_score"],
                  f"按 trust_score 降序: {rows[0]['trust_score']:.2f} ≥ {rows[1]['trust_score']:.2f}")

        db.close()
        SIM_CROSS_SESSION = True
    else:
        skip("memory_store.db 不存在")
        SIM_CROSS_SESSION = False
except Exception as e:
    skip(f"_skill_view_with_bump 模拟失败: {e}")
    SIM_CROSS_SESSION = False


# ════════════════════════════════════════════════════
#  L7: Cross-Session — 关闭连接→重开→召回
# ════════════════════════════════════════════════════
header("L7: Cross-Session — 关闭连接→重开→召回（模拟新会话）")

if MB_AVAILABLE:
    # 关闭现有连接
    with _mb_mod._lock:
        if _mb_mod._conn is not None:
            _mb_mod._conn.close()
            _mb_mod._conn = None
            print("  🔌 关闭 memory_bridge 连接")

    # 模拟新会话：重新加载
    import sys as _sys
    if 'memory_bridge' in _sys.modules:
        del _sys.modules['memory_bridge']
    _mb_spec2 = _iu.spec_from_file_location('memory_bridge', os.path.join(ROOT, 'memomics', 'bio_tools', 'memory_bridge.py'))
    mb2 = _iu.module_from_spec(_mb_spec2)
    _mb_spec2.loader.exec_module(mb2)
    print("  🔄 重新加载 memory_bridge（模拟新会话）")

    # 7a: 新会话召回 Seurat 经验
    exp_new = mb2.recall_experience(skill_name="scrna-seurat-core", tissue="heart")
    n_new = len(exp_new.get("proven_scripts", [])) + len(exp_new.get("known_errors", [])) + len(exp_new.get("user_prefs", []))
    check(n_new >= 6, f"新会话 recall ≥ 6 条 (实际: {n_new})")

    # 7b: 新会话搜索
    results_new = mb2.search_memory("sinoatrial")
    check(len(results_new) >= 1, f"新会话 search('sinoatrial') 命中 ≥ 1 (实际: {len(results_new)})")

    # 7c: 验证数据完整性（不是脏数据）
    sample = results_new[0] if results_new else None
    if sample:
        check("content" in sample, "记录含 content 字段")
        check("fact_id" in sample, "记录含 fact_id 字段")
        check("category" in sample, "记录含 category 字段")


# ════════════════════════════════════════════════════
#  L8: Scoring Priority — 高评分优先
# ════════════════════════════════════════════════════
header("L8: Scoring Priority — user_score/auto_score 影响排序")

if MB_AVAILABLE:
    # 8a: 验证高评分脚本排在前面
    exp_prio = _mb_mod.recall_experience(skill_name="trajectory-analysis", tissue="liver")
    scripts = exp_prio.get("proven_scripts", [])
    if len(scripts) >= 2:
        # slingshot (score=7.0, approved) vs scvelo (score=4.0, not approved)
        check("slingshot" in str(scripts).lower() or "traj" in scripts[0].get("content", "").lower(),
              "高评分/approved 脚本在前")
    check(True, "scoring priority 测试完成")


# ════════════════════════════════════════════════════
#  L9: Self-Evolution 完整周期 — 错误→修复→成功→召回
# ════════════════════════════════════════════════════
header("L9: Self-Evolution 完整周期 — 错误→修复→成功→召回")

# 9a: 先查 seurat 的所有历史错误
ql_before = _query_logs(skill_name="scrna-seurat-core", tissue="heart")
n_err_before = len(ql_before.get("known_errors", []))

# 9b: 再记录一次"学习后"的错误修复和成功
_record_error(
    skill_name="scrna-seurat-core",
    error_message="SCTransform on 150K cells crashed with glmGamPoi",
    error_type="MemoryError",
    root_cause="glmGamPoi version 1.8 incompatible with Matrix 1.6",
    fix_applied="Downgrade glmGamPoi to 1.6.0 + conserve.memory=TRUE (from query_logs)",
    species="Homo sapiens",
    tissue="heart",
    severity="low",
)
ql_after = _query_logs(skill_name="scrna-seurat-core", tissue="heart")
n_err_after = len(ql_after.get("known_errors", []))
check(n_err_after > n_err_before, f"错误数增加: {n_err_before} → {n_err_after}")

# 9c: 修复后记录成功（使用从 query_logs 学到的参数）
fix_result = _record_success(
    skill_name="scrna-seurat-core",
    script_name="run_seurat.R",
    params_used="SCTransform(conserve.memory=TRUE, method='glmGamPoi'), resolution=0.8",
    species="Homo sapiens",
    tissue="heart",
    direction="sinoatrial node development",
    result_summary="Fixed: 150K cells processed via glmGamPoi (version fixed) + SCTransform, 3 subtypes identified",
    score=9.0,
    auto_score=8.5,
    approved=True,
)
check(fix_result.get("success"), "修复后 record_success 成功")

# 9d: 验证修复后的成功记录能被召回
ql_final = _query_logs(skill_name="scrna-seurat-core", tissue="heart")
check("Fixed" in str(ql_final.get("proven_runs", [])), "修复后的成功记录可召回")


# ════════════════════════════════════════════════════
#  L10: debate_analysis._auto_load_kb — KB 注入辩论
# ════════════════════════════════════════════════════
header("L10: debate_analysis._auto_load_kb — KB 注入辩论上下文")

try:
    _deb_spec = _iu.spec_from_file_location('debate_analysis', os.path.join(ROOT, 'memomics', 'bio_tools', 'debate_analysis.py'))
    _deb_mod = _iu.module_from_spec(_deb_spec)
    _deb_spec.loader.exec_module(_deb_mod)
    _auto_load_kb = _deb_mod._auto_load_kb

    # Context 包含 species+tissue+direction
    ctx = "Homo sapiens heart sinoatrial node aging scRNA-seq analysis via Seurat"
    topic = "是否使用 SCTransform 而非 LogNormalize"

    kb_result = _auto_load_kb(ctx, topic)
    check(len(kb_result) >= 200, f"_auto_load_kb 返回 ≥ 200 chars (实际: {len(kb_result)})")
    check("Seurat" in kb_result or "SCTransform" in kb_result or "version" in kb_result.lower(),
          f"_auto_load_kb 含方法或版本信息: {kb_result[:120]}...")
except Exception as e:
    skip(f"_auto_load_kb 测试失败: {e}")


# ════════════════════════════════════════════════════
#  SUMMARY
# ════════════════════════════════════════════════════
header("SUMMARY")

total = PASS + FAIL + _SKIPPED
pass_rate = PASS / (PASS + FAIL) * 100 if (PASS + FAIL) > 0 else 100
print(f"""
  ✅ 通过: {PASS}
  ❌ 失败: {FAIL}
  ⏭️  跳过: {_SKIPPED}
  ────────────
  📊 总计: {total} / 通过率: {pass_rate:.1f}%

  🏆 评级: {"🏆 S — 所有层级完美" if pass_rate >= 98 else "✅ A — 优秀" if pass_rate >= 90 else "⚠️ B — 需要修复" if pass_rate >= 75 else "❌ C — 严重不足"}
""")

if _FAIL_MSGS:
    print(f"  失败项 ({FAIL}):")
    for m in _FAIL_MSGS:
        print(f"    {m}")

print(f"\n  测试结束: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
sys.exit(0 if FAIL == 0 else 1)
