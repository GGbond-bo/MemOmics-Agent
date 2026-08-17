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
"""
Export all analysis results for disease drug discovery pipeline.

Exports: annotated h5ad, DE CSVs, pathway CSVs, L-R CSVs, genetic evidence
CSVs, ranked target list, target evidence cards JSON.

Usage:
  from export_results import export_all
  export_all(adata, de_results, pathway_results, lr_results,
              genetic_results, scores, output_dir="results")
"""

import json
import os
import sys

import numpy as np
import pandas as pd


def export_all(adata, de_results, pathway_results, lr_results,
               genetic_results, scores_df, ot_annotations=None,
               target_cards=None, output_dir="results"):
    """Export all analysis results to files.

    Args:
        adata: Annotated AnnData object
        de_results: Dict of {celltype: DE DataFrame}
        pathway_results: Dict with gsea_results, pathway_activity, disease_pathways
        lr_results: Dict with interactions, disease_specific, network_summary
        genetic_results: Dict from collect_genetic_evidence()
        scores_df: DataFrame from score_targets()
        ot_annotations: Dict from query_target_annotations()
        target_cards: List from generate_target_cards()
        output_dir: Output directory

    Returns:
        Dict of exported file paths
    """
    os.makedirs(output_dir, exist_ok=True)
    exported = {}
    n_files = 0

    print(f"Exporting results to {output_dir}/...")

    # 1. Annotated AnnData
    try:
        h5ad_path = os.path.join(output_dir, "adata_analyzed.h5ad")
        # Store analysis summary in .uns
        adata.uns["drug_discovery_analysis"] = {
            "n_celltypes_tested": len(de_results),
            "n_targets_scored": len(scores_df) if scores_df is not None else 0,
            "analysis_type": "disease_drug_discovery",
        }
        adata.write_h5ad(h5ad_path)
        exported["h5ad"] = h5ad_path
        n_files += 1
        print(f"  [{n_files}] AnnData: {h5ad_path}")
    except Exception as e:
        print(f"  WARNING: H5AD export failed: {e}", file=sys.stderr)

    # 2. Differential expression results
    for celltype, df in de_results.items():
        try:
            safe_name = celltype.replace(" ", "_").replace("/", "-")
            csv_path = os.path.join(output_dir, f"de_results_{safe_name}.csv")
            df.to_csv(csv_path)
            exported[f"de_{safe_name}"] = csv_path
            n_files += 1
        except Exception as e:
            print(f"  WARNING: DE export for {celltype} failed: {e}", file=sys.stderr)

    # DE summary across cell types
    try:
        summary_rows = []
        for ct, df in de_results.items():
            padj_col = "padj" if "padj" in df.columns else "pvals_adj"
            fc_col = "log2FoldChange" if "log2FoldChange" in df.columns else "logfoldchanges"
            if padj_col in df.columns:
                n_up = ((df[padj_col] < 0.05) & (df.get(fc_col, 0) > 0.5)).sum()
                n_down = ((df[padj_col] < 0.05) & (df.get(fc_col, 0) < -0.5)).sum()
                n_total = (df[padj_col] < 0.05).sum()
                summary_rows.append({
                    "cell_type": ct,
                    "n_degs": n_total,
                    "n_upregulated": n_up,
                    "n_downregulated": n_down,
                    "n_genes_tested": len(df),
                })
        if summary_rows:
            summary_df = pd.DataFrame(summary_rows)
            csv_path = os.path.join(output_dir, "de_summary.csv")
            summary_df.to_csv(csv_path, index=False)
            exported["de_summary"] = csv_path
            n_files += 1
            print(f"  [{n_files}] DE summary: {csv_path}")
    except Exception as e:
        print(f"  WARNING: DE summary export failed: {e}", file=sys.stderr)

    # 3. Pathway enrichment results
    if pathway_results:
        gsea_results = pathway_results.get("gsea_results", {})
        for ct, df in gsea_results.items():
            if df is not None and not df.empty:
                try:
                    safe_name = ct.replace(" ", "_").replace("/", "-")
                    csv_path = os.path.join(output_dir, f"pathway_enrichment_{safe_name}.csv")
                    df.to_csv(csv_path, index=False)
                    exported[f"pathway_{safe_name}"] = csv_path
                    n_files += 1
                except Exception as e:
                    print(f"  WARNING: Pathway export for {ct} failed: {e}", file=sys.stderr)

        # Pathway activity scores
        activity = pathway_results.get("pathway_activity")
        if activity is not None:
            try:
                csv_path = os.path.join(output_dir, "pathway_activity_scores.csv")
                if isinstance(activity, pd.DataFrame):
                    activity.to_csv(csv_path)
                exported["pathway_activity"] = csv_path
                n_files += 1
                print(f"  [{n_files}] Pathway activity: {csv_path}")
            except Exception as e:
                print(f"  WARNING: Pathway activity export failed: {e}", file=sys.stderr)

    # 4. Ligand-receptor results
    if lr_results:
        interactions = lr_results.get("interactions")
        if interactions is not None and not interactions.empty:
            try:
                csv_path = os.path.join(output_dir, "lr_interactions.csv")
                interactions.to_csv(csv_path, index=False)
                exported["lr_interactions"] = csv_path
                n_files += 1
                print(f"  [{n_files}] L-R interactions: {csv_path}")
            except Exception as e:
                print(f"  WARNING: L-R export failed: {e}", file=sys.stderr)

        disease_specific = lr_results.get("disease_specific")
        if disease_specific is not None and not disease_specific.empty:
            try:
                csv_path = os.path.join(output_dir, "lr_disease_specific.csv")
                disease_specific.to_csv(csv_path, index=False)
                exported["lr_disease_specific"] = csv_path
                n_files += 1
            except Exception as e:
                print(f"  WARNING: Disease L-R export failed: {e}", file=sys.stderr)

    # 5. Genetic evidence results
    if genetic_results:
        for key in ["genebass_hits", "ot_disease_genetics", "twas_associations",
                     "eqtl_evidence", "l2g_scores", "summary"]:
            df = genetic_results.get(key)
            if df is not None and isinstance(df, pd.DataFrame) and not df.empty:
                try:
                    csv_path = os.path.join(output_dir, f"genetic_{key}.csv")
                    df.to_csv(csv_path, index=False)
                    exported[f"genetic_{key}"] = csv_path
                    n_files += 1
                except Exception as e:
                    print(f"  WARNING: Genetic {key} export failed: {e}", file=sys.stderr)

        print(f"  [{n_files}] Genetic evidence CSVs")

    # 6. Ranked target list (primary output)
    if scores_df is not None and not scores_df.empty:
        try:
            csv_path = os.path.join(output_dir, "ranked_targets.csv")
            scores_df.to_csv(csv_path, index=False)
            exported["ranked_targets"] = csv_path
            n_files += 1
            print(f"  [{n_files}] Ranked targets: {csv_path}")
        except Exception as e:
            print(f"  WARNING: Target ranking export failed: {e}", file=sys.stderr)

    # 7. Target evidence cards
    if target_cards:
        try:
            json_path = os.path.join(output_dir, "target_evidence_cards.json")
            with open(json_path, "w") as f:
                json.dump(target_cards, f, indent=2, default=str)
            exported["target_cards"] = json_path
            n_files += 1
            print(f"  [{n_files}] Target cards: {json_path}")
        except Exception as e:
            print(f"  WARNING: Target cards export failed: {e}", file=sys.stderr)

    # 8. Open Targets annotations
    if ot_annotations:
        try:
            json_path = os.path.join(output_dir, "opentargets_annotations.json")
            with open(json_path, "w") as f:
                json.dump(ot_annotations, f, indent=2, default=str)
            exported["ot_annotations"] = json_path
            n_files += 1
        except Exception as e:
            print(f"  WARNING: OT annotations export failed: {e}", file=sys.stderr)

    # 9. Analysis manifest with provenance
    try:
        from datetime import datetime
        manifest = {
            "analysis_type": "scrna_disease_drug_discovery",
            "generated_at": datetime.now().isoformat(),
            "dataset": {
                "n_cells": int(adata.n_obs),
                "n_genes": int(adata.n_vars),
                "n_celltypes": int(adata.obs["cell_type"].nunique()),
                "cell_types": adata.obs["cell_type"].value_counts().to_dict(),
                "conditions": adata.obs["condition"].unique().tolist(),
                "n_samples": int(adata.obs.get("sample_id", pd.Series()).nunique()),
            },
            "methods": {
                "de": "PyDESeq2 (pseudobulk) with Wilcoxon fallback",
                "pathway": "gseapy GSEA with combined ranking: sign(LFC) x -log10(padj)",
                "lr": "liana-py rank_aggregate (CellPhoneDB, NATMI, Connectome, log2FC)",
                "genetic": "Open Targets GWAS/ClinVar + GeneBass + TWAS + eQTL + L2G",
                "scoring": "Multi-omics composite (DE 0.20, pathway 0.15, LR 0.15, specificity 0.10, genetic 0.25, druggability 0.15)",
            },
            "results": {
                "n_targets_scored": len(scores_df) if scores_df is not None else 0,
                "n_high_priority": int((scores_df["priority_tier"] == "HIGH").sum()) if scores_df is not None else 0,
                "n_medium_priority": int((scores_df["priority_tier"] == "MEDIUM").sum()) if scores_df is not None else 0,
                "n_convergent": int(scores_df["has_convergence"].sum()) if scores_df is not None else 0,
                "top_5_targets": scores_df.head(5)[["gene", "composite_score", "priority_tier"]].to_dict("records") if scores_df is not None and len(scores_df) > 0 else [],
            },
            "exported_files": exported,
        }
        manifest_path = os.path.join(output_dir, "analysis_manifest.json")
        with open(manifest_path, "w") as f:
            json.dump(manifest, f, indent=2, default=str)
        n_files += 1
    except Exception as e:
        print(f"  WARNING: Manifest export failed: {e}", file=sys.stderr)

    print(f"\n=== Export Complete ===")
    print(f"Total files exported: {n_files}")
    print(f"Output directory: {os.path.abspath(output_dir)}")

    return exported


if __name__ == "__main__":
    print("Export requires pre-computed analysis results.")
    print("Use via Python import: from export_results import export_all")
