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

#!/usr/bin/env python3
"""Query CZI CELLxGENE Census for cell-type expression of biomarker panel genes.

Usage:
    python3 scripts/query_cellxgene.py GENE1 GENE2 ... --output results/celltype_expression.csv

Returns mean expression per cell type in large intestine tissue (normal + UC).
"""

import argparse
import sys
import os


def query_census(genes, output_path, tissue="large intestine"):
    """Query CELLxGENE Census for cell-type expression."""
    import cellxgene_census
    import pandas as pd
    import numpy as np

    print(f"  Querying CZI CELLxGENE Census for {len(genes)} genes in '{tissue}'...")
    print(f"  Genes: {', '.join(genes)}")

    gene_filter = "feature_name in ['" + "', '".join(genes) + "']"
    obs_filter = f"tissue_general == '{tissue}' and is_primary_data == True"

    with cellxgene_census.open_soma() as census:
        # Query for human data
        adata = cellxgene_census.get_anndata(
            census=census,
            organism="Homo sapiens",
            var_value_filter=gene_filter,
            obs_value_filter=obs_filter,
            obs_column_names=["cell_type", "tissue", "disease", "assay", "dataset_id"],
        )

    print(f"  Retrieved {adata.n_obs} cells x {adata.n_vars} genes")

    if adata.n_obs == 0:
        print("  WARNING: No cells found. Writing empty output.")
        pd.DataFrame(columns=["cell_type", "gene", "mean_expression", "pct_expressing",
                               "n_cells", "disease"]).to_csv(output_path, index=False)
        return

    # Aggregate by cell_type and disease status
    results = []
    adata.obs["disease_group"] = adata.obs["disease"].apply(
        lambda x: "UC" if "ulcerative" in str(x).lower() else
                  ("normal" if x == "normal" else "other_IBD")
    )

    for disease_grp in ["normal", "UC", "other_IBD"]:
        mask_disease = adata.obs["disease_group"] == disease_grp
        if mask_disease.sum() == 0:
            continue

        sub = adata[mask_disease]
        cell_types = sub.obs["cell_type"].unique()

        for ct in cell_types:
            mask_ct = sub.obs["cell_type"] == ct
            n_cells = mask_ct.sum()
            if n_cells < 10:  # Skip very rare cell types
                continue

            ct_data = sub[mask_ct].X
            if hasattr(ct_data, "toarray"):
                ct_data = ct_data.toarray()
            ct_data = np.array(ct_data, dtype=np.float64)

            gene_names = sub.var["feature_name"].values if "feature_name" in sub.var.columns else sub.var_names

            for j, gene in enumerate(gene_names):
                expr = ct_data[:, j]
                results.append({
                    "cell_type": ct,
                    "gene": gene,
                    "mean_expression": float(np.mean(expr)),
                    "pct_expressing": float(np.mean(expr > 0) * 100),
                    "n_cells": int(n_cells),
                    "disease": disease_grp
                })

    df = pd.DataFrame(results)

    # Sort by gene, then mean expression descending
    if len(df) > 0:
        df = df.sort_values(["gene", "mean_expression"], ascending=[True, False])

    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    df.to_csv(output_path, index=False)
    print(f"  Saved: {output_path} ({len(df)} rows, {df['cell_type'].nunique()} cell types)")
    return df


def main():
    parser = argparse.ArgumentParser(description="Query CZI CELLxGENE for cell-type expression")
    parser.add_argument("genes", nargs="+", help="Gene symbols to query")
    parser.add_argument("--output", "-o", required=True, help="Output CSV path")
    parser.add_argument("--tissue", default="large intestine", help="Tissue to query")
    args = parser.parse_args()

    query_census(args.genes, args.output, args.tissue)


if __name__ == "__main__":
    main()
