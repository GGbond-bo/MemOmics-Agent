# ============================================================
# 🔒 MemOmics 审查与辩论机制 + 自进化日志
# ============================================================
# 此脚本由 MemOmics Agent 执行。原脚本永远不被修改。
#
# 执行前必须:
#   1. rail_review(action="pre")  — 检查环境/参数/数据
#   2. skill_evolution(action="query_logs", script_name="本脚本名",
#      species="物种", tissue="组织", direction="方向")
#      → 查同类运行日志，有则参考已有参数和经验，无则按原脚本执行
#   3. debate_analysis(topic, context) — 参数不确定时多角色辩论
#
# 执行后必须:
#   1. rail_review(action="post") — 检查输出/质量/图表
#   2. 如果通过 → skill_evolution(action="record_run",
#      script_name="本脚本名", species="物种", tissue="组织",
#      direction="方向", params_used="参数JSON", result_summary="结果",
#      quality_score=8, notes="经验总结")
#      → 记录成功运行日志，供后续同类型分析参考
#   3. 如果失败 → skill_evolution(action="record_error",
#      script_name="本脚本名", species="物种", tissue="组织",
#      direction="方向", error_message="报错", root_cause="根因",
#      fix_applied="修复方案")
#      → 记录错误日志，修正后重跑
#
# 日志存储: skill 目录下 .run_logs/ 目录，按 物种_组织_方向_日期 命名
# ============================================================

# ============================================================
# 🔒 MemOmics 审查铁律 — 执行本脚本前后的强制步骤
# ============================================================
# 执行前必须: rail_review(action="pre")  — 环境检查 + 参数校验 + 代码审查
# 执行后必须: rail_review(action="post") — 结果质量评估 + 图表检查 + 数值检查
# 参数有争议: debate_analysis(topic=..., context=...) — 多角色辩论
# 执行失败:   skill_evolution(action="record_error") — 记录错误
# 修复成功:   skill_evolution(action="update_script") — 替换脚本
# ============================================================
#!/usr/bin/env python3
"""
Ad-hoc QC output verification — run after scanpy_qc.py completes.

Verifies structural integrity of all QC outputs without hardcoding
dataset-specific cell counts (those change per run). Checks:
  1. Script syntax (py_compile)
  2. All 10 expected output files exist and are non-empty
  3. qc_summary.csv is parseable and internally consistent
     (cells_after < cells_before, pct_removed < 100%, pct_mt_max < threshold)
  4. qc_params.json is parseable and flags match data state
  5. qc_per_sample.csv has samples, all n_cells > 0
  6. qc_filtered.h5ad: shape matches summary, metadata cols present,
     filter constraints respected (n_genes in range, pct_mt < threshold)

USAGE:
    python verify_qc_outputs.py <qc_output_dir> [script_path]

    qc_output_dir  — directory containing figures/ and results/ subdirs
    script_path    — path to the QC script (optional, for syntax check)

EXIT CODE: 0 = all pass, 1 = any fail
"""

import os
import sys
import json
import py_compile

def main():
    if len(sys.argv) < 2:
        print("Usage: python verify_qc_outputs.py <qc_output_dir> [script_path]")
        sys.exit(1)

    base = sys.argv[1]
    script_path = sys.argv[2] if len(sys.argv) > 2 else None

    checks = {"pass": 0, "fail": 0, "details": []}

    def check(name, condition, detail=""):
        status = "PASS" if condition else "FAIL"
        checks["pass" if condition else "fail"] += 1
        checks["details"].append(f"[{status}] {name}: {detail}")

    # ── 1. Script syntax ──
    if script_path and os.path.isfile(script_path):
        try:
            py_compile.compile(script_path, doraise=True)
            check("Script syntax", True, "py_compile OK")
        except py_compile.PyCompileError as e:
            check("Script syntax", False, str(e))

    # ── 2. Expected output files ──
    expected_files = [
        "figures/qc_violin_before.png",
        "figures/qc_scatter_before.png",
        "figures/qc_violin_after.png",
        "figures/qc_scatter_after.png",
        "figures/qc_violin_by_age_group.png",
        "figures/qc_violin_by_sample.png",
        "results/qc_filtered.h5ad",
        "results/qc_summary.csv",
        "results/qc_per_sample.csv",
        "results/qc_params.json",
    ]
    for f in expected_files:
        fp = os.path.join(base, f)
        exists = os.path.isfile(fp)
        size = os.path.getsize(fp) if exists else 0
        check(f"File exists: {f}", exists and size > 0, f"{size} bytes")

    # ── 3. qc_summary.csv ──
    import pandas as pd
    import numpy as np

    try:
        s = pd.read_csv(os.path.join(base, "results", "qc_summary.csv"))
        d = dict(zip(s["metric"], s["value"]))

        cells_before = int(d.get("cells_before", 0))
        cells_after = int(d.get("cells_after", 0))
        pct_removed = float(d.get("pct_removed", 100))
        pct_mt_max = float(d.get("pct_mt_max", 100))
        genes_after = int(d.get("genes_after", 0))

        check("cells_after < cells_before", cells_after < cells_before,
              f"{cells_before} -> {cells_after}")
        check("pct_removed < 5%", pct_removed < 5.0, f"{pct_removed}%")
        check("pct_mt_max < 15%", pct_mt_max < 15.0, f"{pct_mt_max}%")
        check("genes_after > 0", genes_after > 0, str(genes_after))
    except Exception as e:
        check("qc_summary.csv parse", False, str(e))

    # ── 4. qc_params.json ──
    try:
        with open(os.path.join(base, "results", "qc_params.json")) as f:
            p = json.load(f)
        check("params has filters", "filters" in p, str(list(p.keys())))
        check("params has results", "results" in p, str(list(p.keys())))

        max_mt = p.get("filters", {}).get("max_pct_mt", 0)
        check("params max_pct_mt=15", max_mt == 15, str(max_mt))

        r = p.get("results", {})
        if "cells_before" in r and "cells_after" in r:
            check("params cells_after <= cells_before",
                  r["cells_after"] <= r["cells_before"],
                  f"{r['cells_before']} -> {r['cells_after']}")
    except Exception as e:
        check("qc_params.json parse", False, str(e))

    # ── 5. qc_per_sample.csv ──
    try:
        ps = pd.read_csv(os.path.join(base, "results", "qc_per_sample.csv"))
        check("per_sample has rows", len(ps) > 0, f"{len(ps)} samples")
        check("all n_cells > 0", (ps["n_cells"] > 0).all(),
              f"min={ps['n_cells'].min()}")
        # Flag samples with < 200 cells (statistically unreliable)
        small = ps[ps["n_cells"] < 200]
        if len(small) > 0:
            check("samples < 200 cells (warning)", True,
                  f"{len(small)} samples: {', '.join(small['sample_id'].tolist())}")
        # Check max/min ratio
        ratio = ps["n_cells"].max() / ps["n_cells"].min()
        check("max/min cell ratio < 100", ratio < 100,
              f"ratio={ratio:.1f}" if ratio >= 100 else f"ratio={ratio:.1f}")
    except Exception as e:
        check("qc_per_sample.csv parse", False, str(e))

    # ── 6. qc_filtered.h5ad ──
    try:
        import scanpy as sc
        adata = sc.read_h5ad(os.path.join(base, "results", "qc_filtered.h5ad"))

        # Shape matches summary
        check("h5ad n_obs matches summary", adata.n_obs == cells_after,
              f"h5ad={adata.n_obs}, summary={cells_after}")
        check("h5ad n_vars matches summary", adata.n_vars == genes_after,
              f"h5ad={adata.n_vars}, summary={genes_after}")

        # Metadata columns preserved
        for col in ["celltype", "age_group", "sample_id"]:
            if col in [c for c in adata.obs.columns]:
                check(f"has obs['{col}']", True)
            # Don't fail if a column is absent — not all datasets have all cols

        # QC annotations present
        check("has var['mt']", "mt" in adata.var.columns)
        check("has obs n_genes_by_counts", "n_genes_by_counts" in adata.obs.columns)
        check("has obs pct_counts_mt", "pct_counts_mt" in adata.obs.columns)

        # Filter constraints respected
        min_g = p.get("filters", {}).get("min_genes", 200)
        max_g = p.get("filters", {}).get("max_genes", 6000)
        max_mt_param = p.get("filters", {}).get("max_pct_mt", 15)

        check(f"n_genes >= {min_g}",
              adata.obs["n_genes_by_counts"].min() >= min_g,
              f"min={adata.obs['n_genes_by_counts'].min()}")
        check(f"n_genes <= {max_g}",
              adata.obs["n_genes_by_counts"].max() <= max_g,
              f"max={adata.obs['n_genes_by_counts'].max()}")
        check(f"pct_mt < {max_mt_param}%",
              adata.obs["pct_counts_mt"].max() < max_mt_param,
              f"max={adata.obs['pct_counts_mt'].max():.2f}")
    except Exception as e:
        check("h5ad load + verify", False, str(e))

    # ── Summary ──
    total = checks["pass"] + checks["fail"]
    print("=" * 60)
    print(f"VERIFICATION SUMMARY: {checks['pass']}/{total} checks passed")
    print(f"  PASS: {checks['pass']}")
    print(f"  FAIL: {checks['fail']}")
    print("=" * 60)
    for d in checks["details"]:
        print(d)

    if checks["fail"] > 0:
        print("\n⚠️  Some checks FAILED — review above.")
        sys.exit(1)
    else:
        print("\n✅ All checks PASSED.")
        sys.exit(0)


if __name__ == "__main__":
    main()
