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
Ad-hoc QC output verification — handles BOTH Python (h5ad) and R (RDS) outputs.

Auto-detects output type by checking which result file exists:
  - qc_filtered.h5ad  → Python/Scanpy path (uses scanpy to load)
  - qc_filtered_seurat.rds → R/Seurat path (skips RDS load on Windows —
    uses qc_metadata.csv for constraint checking instead)

Checks:
  1. All expected output files exist and non-empty (size thresholds adjusted
     for small CSV/JSON files)
  2. qc_summary.csv: parseable, cells_after <= cells_before, pct_removed < 5%,
     pct_mt_max < threshold, n_genes in [min, max] range
  3. qc_params.json: parseable, all filters present, counts match summary
  4. qc_per_sample.csv: has samples, all n_cells > 0, ratio < 100
  5. qc_metadata.csv: row count == cells_after, filter constraints enforced
  6. All PNG files have valid magic bytes (\x89PNG\r\n\x1a\n)
  7. R script syntax valid (parse(file=...) via Rscript) — only for .R scripts

USAGE:
    python verify_qc_outputs_universal.py <qc_output_dir> [script_path]

EXIT CODE: 0 = all pass, 1 = any fail
"""

import os
import sys
import json
import subprocess

def main():
    if len(sys.argv) < 2:
        print("Usage: python verify_qc_outputs_universal.py <qc_output_dir> [script_path]")
        sys.exit(1)

    base = sys.argv[1]
    script_path = sys.argv[2] if len(sys.argv) > 2 else None
    fig_dir = os.path.join(base, "figures")
    res_dir = os.path.join(base, "results")

    checks = {"pass": 0, "fail": 0, "details": []}

    def chk(name, condition, detail=""):
        status = "PASS" if condition else "FAIL"
        checks["pass" if condition else "fail"] += 1
        checks["details"].append(f"[{status}] {name}: {detail}")

    # Detect output type
    rds_path = os.path.join(res_dir, "qc_filtered_seurat.rds")
    h5ad_path = os.path.join(res_dir, "qc_filtered.h5ad")
    is_r_output = os.path.isfile(rds_path)
    is_py_output = os.path.isfile(h5ad_path)

    # ── 1. Expected output files ──
    primary_output = "qc_filtered_seurat.rds" if is_r_output else "qc_filtered.h5ad"
    expected_files = [
        (os.path.join(fig_dir, "qc_violin_before.png"), 1024),
        (os.path.join(fig_dir, "qc_scatter_before.png"), 1024),
        (os.path.join(fig_dir, "qc_violin_after.png"), 1024),
        (os.path.join(fig_dir, "qc_scatter_after.png"), 1024),
        (os.path.join(fig_dir, "qc_violin_by_age_group.png"), 1024),
        (os.path.join(fig_dir, "qc_violin_by_sample.png"), 1024),
        (os.path.join(res_dir, primary_output), 1024),
        (os.path.join(res_dir, "qc_metadata.csv"), 1024),
        (os.path.join(res_dir, "qc_summary.csv"), 50),    # small but valid
        (os.path.join(res_dir, "qc_per_sample.csv"), 100),
        (os.path.join(res_dir, "qc_params.json"), 100),   # small but valid
    ]
    for fpath, min_sz in expected_files:
        exists = os.path.isfile(fpath)
        sz = os.path.getsize(fpath) if exists else 0
        chk(f"File: {os.path.basename(fpath)}", exists and sz >= min_sz, f"{sz} bytes")

    # ── 2. qc_summary.csv ──
    import pandas as pd
    try:
        s = pd.read_csv(os.path.join(res_dir, "qc_summary.csv"))
        d = dict(zip(s["metric"], s["value"]))
        cells_before = int(d["cells_before"])
        cells_after = int(d["cells_after"])
        pct_removed = float(d["pct_removed"])
        pct_mt_max = float(d["pct_mt_max"])
        genes_after = int(d["genes_after"])
        n_genes_min = int(d["n_genes_min"])
        n_genes_max = int(d["n_genes_max"])

        chk("cells_after <= cells_before", cells_after <= cells_before, f"{cells_before}->{cells_after}")
        chk("pct_removed < 5%", pct_removed < 5.0, f"{pct_removed}%")
        chk("pct_mt_max < 15%", pct_mt_max < 15.0, f"{pct_mt_max}%")
        chk("genes_after > 0", genes_after > 0, str(genes_after))
        chk("n_genes_min >= 200", n_genes_min >= 200, str(n_genes_min))
        chk("n_genes_max <= 6000", n_genes_max <= 6000, str(n_genes_max))
    except Exception as e:
        chk("qc_summary.csv parse", False, str(e))
        cells_before = cells_after = genes_after = 0

    # ── 3. qc_params.json ──
    try:
        with open(os.path.join(res_dir, "qc_params.json")) as f:
            p = json.load(f)
        chk("params has filters", "filters" in p)
        chk("params has results", "results" in p)
        chk("params has skipped", "skipped" in p)
        chk("params max_pct_mt=15", p["filters"]["max_pct_mt"] == 15)
        chk("params min_genes=200", p["filters"]["min_genes"] == 200)
        chk("params max_genes=6000", p["filters"]["max_genes"] == 6000)
        r = p["results"]
        chk("params cells match summary",
            r["cells_before"] == cells_before and r["cells_after"] == cells_after,
            f"json={r['cells_before']}->{r['cells_after']}, csv={cells_before}->{cells_after}")
        chk("params genes match summary",
            r["genes_after"] == genes_after, f"json={r['genes_after']}, csv={genes_after}")
    except Exception as e:
        chk("qc_params.json parse", False, str(e))
        p = {"filters": {}}

    # ── 4. qc_per_sample.csv ──
    try:
        ps = pd.read_csv(os.path.join(res_dir, "qc_per_sample.csv"))
        chk("per_sample has rows", len(ps) > 0, f"{len(ps)} samples")
        chk("all n_cells > 0", (ps["n_cells"] > 0).all(), f"min={ps['n_cells'].min()}")
        small = ps[ps["n_cells"] < 200]
        chk("samples < 200 flagged", True, f"{len(small)} samples")
        ratio = ps["n_cells"].max() / ps["n_cells"].min()
        chk("max/min ratio < 100", ratio < 100, f"ratio={ratio:.1f}")
        if "age_group" in ps.columns:
            chk("both groups present", len(ps["age_group"].unique()) >= 2)
    except Exception as e:
        chk("qc_per_sample.csv parse", False, str(e))

    # ── 5. qc_metadata.csv (works for both R and Python outputs) ──
    try:
        meta = pd.read_csv(os.path.join(res_dir, "qc_metadata.csv"))
        chk("metadata nrow == cells_after", len(meta) == cells_after, f"{len(meta)}=={cells_after}")

        # Column names differ: R uses nFeature_RNA/percent.mt, Python uses n_genes_by_counts/pct_counts_mt
        nfeat_col = "nFeature_RNA" if "nFeature_RNA" in meta.columns else "n_genes_by_counts"
        mt_col = "percent.mt" if "percent.mt" in meta.columns else "pct_counts_mt"

        chk(f"metadata has nFeature col ({nfeat_col})", nfeat_col in meta.columns)
        chk(f"metadata has pct_mt col ({mt_col})", mt_col in meta.columns)

        if nfeat_col in meta.columns:
            min_g = p.get("filters", {}).get("min_genes", 200)
            max_g = p.get("filters", {}).get("max_genes", 6000)
            chk(f"metadata nFeature min >= {min_g}", meta[nfeat_col].min() >= min_g, str(meta[nfeat_col].min()))
            chk(f"metadata nFeature max <= {max_g}", meta[nfeat_col].max() <= max_g, str(meta[nfeat_col].max()))
        if mt_col in meta.columns:
            max_mt = p.get("filters", {}).get("max_pct_mt", 15)
            chk(f"metadata pct_mt max < {max_mt}", meta[mt_col].max() < max_mt, f"{meta[mt_col].max():.2f}")
    except Exception as e:
        chk("qc_metadata.csv parse", False, str(e))

    # ── 6. PNG magic bytes ──
    for fname in ["qc_violin_before.png", "qc_scatter_before.png", "qc_violin_after.png",
                   "qc_scatter_after.png", "qc_violin_by_age_group.png", "qc_violin_by_sample.png"]:
        fpath = os.path.join(fig_dir, fname)
        try:
            with open(fpath, "rb") as f:
                magic = f.read(8)
            chk(f"Valid PNG: {fname}", magic == b'\x89PNG\r\n\x1a\n', magic[:8].hex())
        except Exception as e:
            chk(f"PNG read: {fname}", False, str(e))

    # ── 7. Script syntax check ──
    if script_path and os.path.isfile(script_path):
        if script_path.endswith(".R"):
            # R script: use parse(file=...) — NOT -e with shell escaping
            result = subprocess.run(
                ["Rscript", "--vanilla", "-e",
                 f'parse(file=file("{script_path}")); cat("Syntax OK\\n")'],
                capture_output=True, text=True, timeout=30
            )
            chk("R script syntax valid",
                result.returncode == 0 and "Syntax OK" in result.stdout,
                f"exit={result.returncode}")
        elif script_path.endswith(".py"):
            import py_compile
            try:
                py_compile.compile(script_path, doraise=True)
                chk("Python script syntax valid", True, "py_compile OK")
            except py_compile.PyCompileError as e:
                chk("Python script syntax valid", False, str(e))

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
