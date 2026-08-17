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
Multi-omics composite drug target prioritization.

Integrates transcriptomic evidence (DE, pathways, L-R interactions) with
genetic evidence (GeneBass, TWAS, eQTL, L2G) and druggability (Open Targets)
into a composite target score. Targets with convergent multi-omics evidence
receive highest priority.

Usage:
  from target_scoring import score_targets
  scores = score_targets(de_results, pathway_results, lr_results,
                          genetic_results, ot_annotations)
"""

import json
import math
import sys
from collections import defaultdict

import numpy as np
import pandas as pd


# ---------------------------------------------------------------------------
# Scoring weights
# ---------------------------------------------------------------------------

COMPONENT_WEIGHTS = {
    "differential_expression": 0.20,
    "pathway_centrality": 0.15,
    "lr_involvement": 0.15,
    "celltype_specificity": 0.10,
    "genetic_evidence": 0.25,
    "druggability": 0.15,
}

# Convergence bonus: targets with BOTH genetic AND transcriptomic evidence
CONVERGENCE_MULTIPLIER = 1.2

# Priority tier thresholds
TIER_HIGH = 0.55
TIER_MEDIUM = 0.35

# Default disease context for SSc
SSC_DISEASE_CONTEXT = {
    "name": "systemic sclerosis",
    "relevant_cell_types": [
        "fibroblast", "myofibroblast", "macrophage", "monocyte",
        "endothelial", "T cell", "Th2", "Th17", "dendritic",
    ],
    "relevant_pathways": [
        "TGF", "TGFB", "transforming growth factor",
        "WNT", "Wnt",
        "PDGF", "platelet-derived growth factor",
        "fibrosis", "fibro",
        "collagen", "ECM", "extracellular matrix",
        "IL4", "IL-4", "IL13", "IL-13",
        "JAK-STAT",
        "endothelin",
        "EMT", "epithelial mesenchymal", "mesenchymal transition",
        "TNF", "NF-kB", "NFkB",
    ],
    "relevant_lr_pairs": [
        ("TGFB1", "TGFBR1"), ("TGFB1", "TGFBR2"), ("TGFB2", "TGFBR1"),
        ("PDGFB", "PDGFRA"), ("PDGFA", "PDGFRA"), ("PDGFC", "PDGFRA"),
        ("IL13", "IL13RA1"), ("IL4", "IL4R"),
        ("WNT5A", "FZD2"), ("WNT3A", "FZD1"),
        ("CCL2", "CCR2"), ("CXCL12", "CXCR4"),
        ("EDN1", "EDNRA"), ("EDN1", "EDNRB"),
        ("IL6", "IL6R"), ("IL6", "IL6ST"),
        ("CTGF", "TGFBR1"), ("CTGF", "ITGAV"),
    ],
}


# ---------------------------------------------------------------------------
# Component scoring functions
# ---------------------------------------------------------------------------

def _score_de(gene, de_results, disease_context):
    """Score a gene based on differential expression evidence."""
    scores = []
    cell_types_de = []

    for celltype, df in de_results.items():
        if gene not in df.index:
            continue
        row = df.loc[gene]
        padj = row.get("padj", 1.0)
        log2fc = row.get("log2FoldChange", row.get("logfoldchanges", 0.0))

        if padj is None or np.isnan(padj):
            continue
        if padj >= 1.0:
            continue

        # Base score from significance and effect size
        sig_score = min(-np.log10(max(padj, 1e-300)) / 10.0, 1.0)
        fc_weight = min(abs(log2fc) / 3.0, 1.0)  # Saturate at |log2FC| = 3
        gene_score = sig_score * 0.6 + fc_weight * 0.4

        # Boost for disease-relevant cell types
        ct_lower = celltype.lower()
        is_relevant = any(
            rc.lower() in ct_lower
            for rc in disease_context.get("relevant_cell_types", [])
        )
        if is_relevant:
            gene_score = min(gene_score * 1.2, 1.0)

        scores.append(gene_score)
        if padj < 0.05:
            cell_types_de.append(celltype)

    if not scores:
        return 0.0, 0, []

    # Multi-cell-type bonus
    base_score = max(scores)
    n_celltypes = len(cell_types_de)
    if n_celltypes > 1:
        base_score = min(base_score * (1 + 0.1 * (n_celltypes - 1)), 1.0)

    return base_score, n_celltypes, cell_types_de


def _score_pathway(gene, pathway_results, disease_context):
    """Score a gene based on pathway centrality using NES-weighted scoring."""
    if not pathway_results:
        return 0.0, []

    gsea_results = pathway_results.get("gsea_results", {})
    relevant_keywords = disease_context.get("relevant_pathways", [])

    # Collect |NES| values for pathways containing this gene
    pathway_nes = []  # (term, |NES|, is_disease_relevant)
    disease_pathways = []

    for celltype, gsea_df in gsea_results.items():
        if gsea_df is None or gsea_df.empty:
            continue

        nes_col = next((c for c in ["NES", "nes"] if c in gsea_df.columns), None)

        for _, row in gsea_df.iterrows():
            term = str(row.get("Term", row.get("term", "")))
            fdr = row.get("FDR q-val", row.get("FDR", row.get("fdr", row.get("padj", 1.0))))
            leading_edge = str(row.get("Lead_genes", row.get("Leading_edge", row.get("leading_edge", ""))))

            if fdr > 0.05:
                continue

            # Check if gene is in this pathway's leading edge
            if gene in leading_edge or gene.upper() in leading_edge.upper():
                nes_val = abs(float(row.get(nes_col, 1.0))) if nes_col else 1.0

                # Check if disease-relevant
                is_relevant = any(
                    kw.lower() in term.lower()
                    for kw in relevant_keywords
                )
                pathway_nes.append((term, nes_val, is_relevant))
                if is_relevant:
                    disease_pathways.append(term)

    if not pathway_nes:
        return 0.0, []

    # NES-weighted scoring (smoother than count-based)
    # Base: sum of |NES| values, normalized by a soft cap
    total_nes = sum(nes for _, nes, _ in pathway_nes)
    disease_nes = sum(nes for _, nes, rel in pathway_nes if rel)

    # Soft normalization: tanh-like curve that saturates gradually
    # total_nes of ~5 gives ~0.5, ~10 gives ~0.7, ~20 gives ~0.85
    base_score = min(total_nes / (total_nes + 8.0), 0.6)  # Saturates at 0.6
    disease_boost = min(disease_nes / (disease_nes + 5.0), 0.4) if disease_nes > 0 else 0.0

    return min(base_score + disease_boost, 1.0), list(set(disease_pathways))


def _score_lr(gene, lr_results, disease_context):
    """Score a gene based on ligand-receptor involvement."""
    if not lr_results:
        return 0.0, []

    interactions = lr_results.get("interactions")
    if interactions is None or interactions.empty:
        return 0.0, []

    # Find interactions involving this gene as ligand or receptor
    gene_upper = gene.upper()
    gene_interactions = []

    ligand_col = _find_column(interactions, ["ligand", "ligand_complex"])
    receptor_col = _find_column(interactions, ["receptor", "receptor_complex"])

    if ligand_col is None or receptor_col is None:
        return 0.0, []

    for _, row in interactions.iterrows():
        ligand = str(row.get(ligand_col, "")).upper()
        receptor = str(row.get(receptor_col, "")).upper()

        if gene_upper in ligand or gene_upper in receptor:
            gene_interactions.append(row)

    if not gene_interactions:
        return 0.0, []

    # Score based on interaction count and disease relevance
    n_interactions = len(gene_interactions)
    base_score = min(n_interactions / 20.0, 0.5)

    # Check for disease-relevant L-R pairs
    relevant_pairs = disease_context.get("relevant_lr_pairs", [])
    disease_lr = []
    for row in gene_interactions:
        ligand = str(row.get(ligand_col, "")).upper()
        receptor = str(row.get(receptor_col, "")).upper()
        for l, r in relevant_pairs:
            if (l.upper() in ligand and r.upper() in receptor) or \
               (r.upper() in ligand and l.upper() in receptor):
                disease_lr.append(f"{ligand}-{receptor}")

    disease_boost = min(len(set(disease_lr)) * 0.2, 0.5)

    return min(base_score + disease_boost, 1.0), disease_lr


def _score_celltype_specificity(gene, de_results, disease_context):
    """Score a gene based on cell-type specificity of disease effect."""
    relevant_types = disease_context.get("relevant_cell_types", [])
    effects = {}

    for celltype, df in de_results.items():
        if gene not in df.index:
            continue
        row = df.loc[gene]
        padj = row.get("padj", 1.0)
        log2fc = row.get("log2FoldChange", row.get("logfoldchanges", 0.0))

        if padj is None or np.isnan(padj) or padj >= 0.05:
            continue

        effects[celltype] = abs(log2fc)

    if not effects:
        return 0.0

    # Compute specificity (tau-like)
    if len(effects) == 1:
        specificity = 1.0
    else:
        max_effect = max(effects.values())
        if max_effect == 0:
            return 0.0
        normalized = [v / max_effect for v in effects.values()]
        specificity = (len(normalized) - sum(normalized)) / (len(normalized) - 1)

    # Weight by disease-relevant cell type involvement
    relevant_effect = 0.0
    for ct, effect in effects.items():
        ct_lower = ct.lower()
        if any(rc.lower() in ct_lower for rc in relevant_types):
            relevant_effect = max(relevant_effect, effect)

    if relevant_effect > 0:
        relevance_weight = min(relevant_effect / 2.0, 1.0)
    else:
        relevance_weight = 0.3  # Some credit even if not in "relevant" types

    return min(specificity * 0.5 + relevance_weight * 0.5, 1.0)


def _score_genetic(gene, genetic_results):
    """Score a gene based on genetic evidence."""
    if not genetic_results:
        return 0.0, False, None

    summary = genetic_results.get("summary")
    if summary is None or summary.empty:
        return 0.0, False, None

    if gene not in summary.index and gene not in summary.get("gene", pd.Series()).values:
        return 0.0, False, None

    # Get row for this gene
    if "gene" in summary.columns:
        gene_rows = summary[summary["gene"] == gene]
        if gene_rows.empty:
            return 0.0, False, None
        row = gene_rows.iloc[0]
    else:
        row = summary.loc[gene]

    score = row.get("genetic_score", 0.0)
    has_evidence = score > 0
    direction = row.get("direction", None)

    return float(score), has_evidence, direction


# ---------------------------------------------------------------------------
# Main scoring function
# ---------------------------------------------------------------------------

def score_targets_simple(results, disease_context=None):
    """Simplified scoring API — pass a single results dict.

    This is the RECOMMENDED way to call target scoring. Pass a dict with
    the outputs from Steps 2a-2e.

    Args:
        results: Dict with keys:
            "de": dict of {celltype: DataFrame} from run_pseudobulk_de()
                  Each DataFrame has columns: gene, log2FoldChange, padj, baseMean
            "pathway": dict from run_pathway_analysis()
                  Must have key "gsea_results" = {celltype: GSEA DataFrame}
            "lr": dict from run_lr_analysis()
                  Must have key "interactions" = DataFrame of L-R pairs
            "genetic": dict from collect_genetic_evidence()
                  Must have key "summary" = DataFrame with gene, genetic_score columns
            "ot_annotations": dict from query_target_annotations() (optional)
                  Keys are gene names, values have "druggability_score". Auto-queried if omitted.
        disease_context: Disease context dict (default: SSc)

    Returns:
        DataFrame with columns: gene, composite_score, priority_tier,
        de_score, pathway_score, lr_score, specificity_score,
        genetic_score, druggability_score, has_convergence, cross_compartment

    Example:
        scores = score_targets_simple({
            "de": de_results,        # from run_pseudobulk_de()
            "pathway": pathway_results,  # from run_pathway_analysis()
            "lr": lr_results,        # from run_lr_analysis()
            "genetic": genetic_results,  # from collect_genetic_evidence()
        })
    """
    return score_targets(
        de_results=results.get("de", results.get("de_results", {})),
        pathway_results=results.get("pathway", results.get("pathway_results", {})),
        lr_results=results.get("lr", results.get("lr_results", {})),
        genetic_results=results.get("genetic", results.get("genetic_results")),
        ot_annotations=results.get("ot_annotations"),
        disease_context=disease_context,
    )


def score_targets(de_results, pathway_results, lr_results,
                  genetic_results=None, ot_annotations=None,
                  disease_context=None, top_n=100,
                  auto_query_druggability=True):
    """Compute multi-omics composite target scores.

    Args:
        de_results: Dict of {celltype: DE DataFrame}
        pathway_results: Dict with gsea_results, pathway_activity, disease_pathways
        lr_results: Dict with interactions, disease_specific, network_summary
        genetic_results: Dict from collect_genetic_evidence() or None
        ot_annotations: Dict from query_target_annotations() or None
        disease_context: Disease context dict (default: SSc)
        top_n: Maximum number of targets to score in detail

    Returns:
        DataFrame with columns: gene, de_score, pathway_score, lr_score,
        specificity_score, genetic_score, druggability_score, composite_score,
        priority_tier, has_convergence, de_celltypes, disease_pathways,
        disease_lr_pairs, genetic_direction
    """
    if disease_context is None:
        disease_context = SSC_DISEASE_CONTEXT

    # Normalize DE DataFrames: ensure gene names are the index
    de_results_indexed = {}
    for celltype, df in de_results.items():
        df = df.copy()
        # If gene names are in a column (not the index), set as index
        if "gene" in df.columns and not isinstance(df.index[0], str):
            df = df.set_index("gene")
        elif df.index.dtype != object and df.index.dtype.kind != 'U':
            # Index is numeric — try to convert
            pass
        de_results_indexed[celltype] = df
    de_results = de_results_indexed

    # Collect all candidate genes from DE results
    all_genes = set()
    for celltype, df in de_results.items():
        padj_col = "padj" if "padj" in df.columns else "pvals_adj"
        if padj_col not in df.columns:
            continue
        sig_genes = df[df[padj_col] < 0.05].index.tolist()
        all_genes.update(sig_genes)

    # Also include genes from genetic evidence
    if genetic_results and "summary" in genetic_results:
        gen_summary = genetic_results["summary"]
        if not gen_summary.empty:
            if "gene" in gen_summary.columns:
                genetic_genes = gen_summary[
                    gen_summary.get("genetic_score", pd.Series(dtype=float)) > 0
                ]["gene"].tolist()
            else:
                genetic_genes = gen_summary[
                    gen_summary.get("genetic_score", pd.Series(dtype=float)) > 0
                ].index.tolist()
            all_genes.update(genetic_genes)

    # Ensure all gene names are strings
    all_genes = {str(g) for g in all_genes if pd.notna(g)}

    # Check if L-R data is available and non-trivial
    _lr_available = (
        lr_results is not None
        and lr_results.get("interactions") is not None
        and not lr_results["interactions"].empty
    )
    if not _lr_available:
        print("  NOTE: L-R interactions unavailable — redistributing L-R weight to other components")

    # Auto-query druggability from Open Targets if not provided
    # NOTE: Limited to 20 genes (not 50) to avoid timeout — each gene takes
    # ~1-2 seconds (search + target query + rate limiting). 50 genes = ~90s
    # which can exceed Biomni's execution timeout.
    if ot_annotations is None and auto_query_druggability and len(all_genes) > 0:
        try:
            from query_opentargets import query_target_annotations
            query_genes = sorted(all_genes)[:20]
            print(f"  Auto-querying Open Targets druggability for {len(query_genes)} genes...")
            ot_annotations = query_target_annotations(query_genes, verbose=False)
        except Exception as e:
            print(f"  WARNING: Auto druggability query failed ({e}). "
                  f"Using default druggability scores.", file=sys.stderr)
            ot_annotations = {}

    # Build cross-compartment L-R lookup for GWAS-LR bridging
    _lr_partners = {}  # gene -> set of L-R partner genes
    if _lr_available:
        interactions = lr_results["interactions"]
        ligand_col = _find_column(interactions, ["ligand", "ligand_complex"])
        receptor_col = _find_column(interactions, ["receptor", "receptor_complex"])
        if ligand_col and receptor_col:
            for _, row in interactions.iterrows():
                lig = str(row.get(ligand_col, "")).upper()
                rec = str(row.get(receptor_col, "")).upper()
                for gene_name in lig.split("_"):
                    _lr_partners.setdefault(gene_name, set()).add(rec)
                for gene_name in rec.split("_"):
                    _lr_partners.setdefault(gene_name, set()).add(lig)

    # ===================================================================
    # PRE-BUILD LOOKUPS for O(1) per-gene scoring (fixes 10+ min timeout)
    # Without these, scoring 1,200 genes scans 500M+ DataFrame rows.
    # With lookups: ~1.2M operations total, completes in <5 seconds.
    # ===================================================================

    # 1. DE lookup: gene -> {celltype: (padj, log2fc)}
    print("  Building DE lookup...")
    _de_lookup = {}
    relevant_types = disease_context.get("relevant_cell_types", [])
    for ct, df in de_results.items():
        padj_col = "padj" if "padj" in df.columns else "pvals_adj"
        fc_col = "log2FoldChange" if "log2FoldChange" in df.columns else "logfoldchanges"
        if padj_col not in df.columns or fc_col not in df.columns:
            continue
        for gene_name in df.index:
            padj = df.at[gene_name, padj_col]
            lfc = df.at[gene_name, fc_col]
            if pd.isna(padj) or padj >= 1.0:
                continue
            _de_lookup.setdefault(str(gene_name), {})[ct] = (float(padj), float(lfc))

    # 2. Pathway lookup: gene -> [(term, nes, is_disease_relevant)]
    print("  Building pathway lookup...")
    _pathway_lookup = {}
    gsea_results = pathway_results.get("gsea_results", {}) if pathway_results else {}
    relevant_keywords = disease_context.get("relevant_pathways", [])
    for ct, gsea_df in gsea_results.items():
        if gsea_df is None or gsea_df.empty:
            continue
        nes_col = next((c for c in ["NES", "nes"] if c in gsea_df.columns), None)
        fdr_col = next((c for c in ["FDR q-val", "FDR", "fdr", "padj"] if c in gsea_df.columns), None)
        le_col = next((c for c in ["Lead_genes", "Leading_edge", "leading_edge"] if c in gsea_df.columns), None)
        if not all([nes_col, fdr_col, le_col]):
            continue
        for _, row in gsea_df.iterrows():
            fdr = float(row.get(fdr_col, 1.0))
            if fdr > 0.05:
                continue
            nes_val = abs(float(row.get(nes_col, 0)))
            term = str(row.get("Term", row.get("term", "")))
            is_relevant = any(kw.lower() in term.lower() for kw in relevant_keywords)
            leading_edge = str(row.get(le_col, ""))
            # Parse genes from leading edge
            for gene_name in leading_edge.replace(";", ",").split(","):
                gene_name = gene_name.strip()
                if gene_name:
                    _pathway_lookup.setdefault(gene_name, []).append((term, nes_val, is_relevant))
                    if gene_name.upper() != gene_name:
                        _pathway_lookup.setdefault(gene_name.upper(), []).append((term, nes_val, is_relevant))

    # 3. L-R lookup: gene -> count of interactions + disease relevance
    print("  Building L-R lookup...")
    _lr_lookup = {}  # gene -> {"n_interactions": int, "disease_lr": [str]}
    if _lr_available:
        interactions_df = lr_results["interactions"]
        ligand_col = _find_column(interactions_df, ["ligand", "ligand_complex"])
        receptor_col = _find_column(interactions_df, ["receptor", "receptor_complex"])
        relevant_pairs = disease_context.get("relevant_lr_pairs", [])
        if ligand_col and receptor_col:
            for _, row in interactions_df.iterrows():
                lig = str(row.get(ligand_col, "")).upper()
                rec = str(row.get(receptor_col, "")).upper()
                # Index by all gene components
                for gene_name in set(lig.split("_") + rec.split("_")):
                    if not gene_name:
                        continue
                    entry = _lr_lookup.setdefault(gene_name, {"n": 0, "disease": []})
                    entry["n"] += 1
                    for l, r in relevant_pairs:
                        if (l.upper() in lig and r.upper() in rec) or \
                           (r.upper() in lig and l.upper() in rec):
                            entry["disease"].append(f"{lig}-{rec}")

    # 4. Genetic lookup: gene -> (genetic_score, has_evidence, direction)
    _genetic_lookup = {}
    if genetic_results and genetic_results.get("summary") is not None:
        gen_summary = genetic_results["summary"]
        if not gen_summary.empty:
            for _, row in gen_summary.iterrows():
                g = str(row.get("gene", ""))
                score = float(row.get("genetic_score", 0))
                direction = row.get("direction")
                _genetic_lookup[g] = (score, score > 0, direction)
                _genetic_lookup[g.upper()] = (score, score > 0, direction)

    print(f"  Lookups built: {len(_de_lookup)} DE, {len(_pathway_lookup)} pathway, "
          f"{len(_lr_lookup)} L-R, {len(_genetic_lookup)} genetic")
    print(f"Scoring {len(all_genes)} candidate genes...")

    # Score each gene using O(1) lookups
    results = []
    for gene in sorted(all_genes):
        # --- DE score (from lookup) ---
        de_info = _de_lookup.get(gene, {})
        de_scores_list = []
        de_celltypes = []
        for ct, (padj, lfc) in de_info.items():
            sig_score = min(-np.log10(max(padj, 1e-300)) / 10.0, 1.0)
            fc_weight = min(abs(lfc) / 3.0, 1.0)
            gene_score = sig_score * 0.6 + fc_weight * 0.4
            ct_lower = ct.lower()
            if any(rc.lower() in ct_lower for rc in relevant_types):
                gene_score = min(gene_score * 1.2, 1.0)
            de_scores_list.append(gene_score)
            if padj < 0.05:
                de_celltypes.append(ct)
        de_score = max(de_scores_list) if de_scores_list else 0.0
        n_de_ct = len(de_celltypes)
        if n_de_ct > 1:
            de_score = min(de_score * (1 + 0.1 * (n_de_ct - 1)), 1.0)

        # --- Pathway score (from lookup) ---
        pw_info = _pathway_lookup.get(gene, []) or _pathway_lookup.get(gene.upper(), [])
        if pw_info:
            total_nes = sum(nes for _, nes, _ in pw_info)
            disease_nes = sum(nes for _, nes, rel in pw_info if rel)
            pathway_score = min(total_nes / (total_nes + 8.0), 0.6)
            disease_boost = min(disease_nes / (disease_nes + 5.0), 0.4) if disease_nes > 0 else 0.0
            pathway_score = min(pathway_score + disease_boost, 1.0)
            disease_pathways = list(set(t for t, _, rel in pw_info if rel))[:5]
        else:
            pathway_score = 0.0
            disease_pathways = []

        # --- L-R score (from lookup) ---
        lr_info = _lr_lookup.get(gene.upper(), {"n": 0, "disease": []})
        n_lr = lr_info["n"]
        disease_lr = list(set(lr_info["disease"]))
        if n_lr > 0:
            lr_score = min(n_lr / 20.0, 0.5) + min(len(set(disease_lr)) * 0.2, 0.5)
            lr_score = min(lr_score, 1.0)
        else:
            lr_score = 0.0

        # --- Specificity score ---
        specificity_score = _score_celltype_specificity(gene, de_results, disease_context)

        # --- Genetic score (from lookup) ---
        # --- Specificity score (from DE lookup) ---
        if de_info and len(de_info) > 0:
            sig_effects = {ct: abs(lfc) for ct, (padj, lfc) in de_info.items() if padj < 0.05}
            if len(sig_effects) == 0:
                specificity_score = 0.0
            elif len(sig_effects) == 1:
                specificity_score = 1.0
            else:
                max_eff = max(sig_effects.values())
                if max_eff == 0:
                    specificity_score = 0.0
                else:
                    norm = [v / max_eff for v in sig_effects.values()]
                    specificity_score = (len(norm) - sum(norm)) / (len(norm) - 1)
            # Weight by disease-relevant cell type
            relevant_effect = max((abs(lfc) for ct, (padj, lfc) in de_info.items()
                                   if padj < 0.05 and any(rc.lower() in ct.lower() for rc in relevant_types)), default=0)
            relevance_weight = min(relevant_effect / 2.0, 1.0) if relevant_effect > 0 else 0.3
            specificity_score = min(specificity_score * 0.5 + relevance_weight * 0.5, 1.0)
        else:
            specificity_score = 0.0

        gen_info = _genetic_lookup.get(gene, _genetic_lookup.get(gene.upper(), (0.0, False, None)))
        genetic_score, has_genetic, genetic_direction = gen_info

        # Druggability from Open Targets
        druggability_score = 0.2  # Default
        if ot_annotations and gene in ot_annotations:
            druggability_score = ot_annotations[gene].get("druggability_score", 0.2)

        # Check if genetic evidence is available at all
        has_genetic_data = genetic_results is not None and genetic_results.get("summary") is not None

        # Compute composite score with adaptive reweighting
        weights = COMPONENT_WEIGHTS.copy()

        # Drop components with no data and redistribute weight
        if not has_genetic_data:
            weights.pop("genetic_evidence", None)
            genetic_score = 0.0
        if not _lr_available:
            weights.pop("lr_involvement", None)
            lr_score = 0.0

        # Renormalize weights to sum to 1.0
        total_w = sum(weights.values())
        if total_w > 0:
            weights = {k: v / total_w for k, v in weights.items()}

        composite = (
            weights.get("differential_expression", 0) * de_score +
            weights.get("pathway_centrality", 0) * pathway_score +
            weights.get("lr_involvement", 0) * lr_score +
            weights.get("celltype_specificity", 0) * specificity_score +
            weights.get("genetic_evidence", 0) * genetic_score +
            weights.get("druggability", 0) * druggability_score
        )

        # Convergence bonus
        has_transcriptomic = de_score > 0.3
        has_convergence = has_transcriptomic and has_genetic
        if has_convergence:
            composite *= CONVERGENCE_MULTIPLIER

        # Cross-compartment bonus: GWAS gene has L-R partners that are DE,
        # or DE gene has L-R partners with genetic evidence
        cross_compartment = False
        if _lr_partners and genetic_results and genetic_results.get("summary") is not None:
            gene_upper = gene.upper()
            partners = _lr_partners.get(gene_upper, set())
            if partners:
                gen_summary = genetic_results["summary"]
                gen_genes = set()
                if "gene" in gen_summary.columns:
                    gen_genes = set(gen_summary[gen_summary.get("genetic_score", pd.Series(dtype=float)) > 0]["gene"].str.upper())
                # Case 1: This gene has DE, its L-R partner has genetic evidence
                if de_score > 0.2:
                    if partners & gen_genes:
                        cross_compartment = True
                        composite *= 1.1  # 10% boost
                # Case 2: This gene has genetic evidence, its L-R partner has DE
                if has_genetic:
                    de_genes_upper = {str(g).upper() for ct_df in de_results.values()
                                      for g in ct_df.index if ct_df.get("padj", pd.Series()).get(g, 1.0) < 0.05} if de_results else set()
                    if partners & de_genes_upper:
                        cross_compartment = True
                        composite *= 1.1

        # Priority tier
        if composite >= TIER_HIGH:
            tier = "HIGH"
        elif composite >= TIER_MEDIUM:
            tier = "MEDIUM"
        else:
            tier = "LOW"

        results.append({
            "gene": gene,
            "de_score": round(de_score, 3),
            "pathway_score": round(pathway_score, 3),
            "lr_score": round(lr_score, 3),
            "specificity_score": round(specificity_score, 3),
            "genetic_score": round(genetic_score, 3),
            "druggability_score": round(druggability_score, 3),
            "composite_score": round(composite, 3),
            "priority_tier": tier,
            "has_convergence": has_convergence,
            "cross_compartment": cross_compartment,
            "n_de_celltypes": n_de_ct,
            "de_celltypes": "; ".join(de_celltypes),
            "disease_pathways": "; ".join(disease_pathways[:5]),
            "disease_lr_pairs": "; ".join(disease_lr[:5]),
            "genetic_direction": genetic_direction,
        })

    # Create DataFrame and sort
    scores_df = pd.DataFrame(results)
    scores_df = scores_df.sort_values("composite_score", ascending=False)
    scores_df = scores_df.reset_index(drop=True)

    # Summary statistics
    n_high = (scores_df["priority_tier"] == "HIGH").sum()
    n_medium = (scores_df["priority_tier"] == "MEDIUM").sum()
    n_convergent = scores_df["has_convergence"].sum()

    print(f"\u2713 Target scoring complete! {len(scores_df)} targets scored, "
          f"{n_high} HIGH, {n_medium} MEDIUM, {n_convergent} with convergent evidence")

    # Incremental save for OOM resilience
    import os
    out_dir = os.environ.get("SCRNA_RESULTS_DIR", "results")
    os.makedirs(out_dir, exist_ok=True)
    try:
        path = os.path.join(out_dir, "ranked_targets.csv")
        scores_df.to_csv(path, index=False)
        print(f"  Saved: {path}")
    except Exception as e:
        print(f"  WARNING: Failed to save ranked_targets.csv: {e}", file=sys.stderr)

    return scores_df


def generate_target_cards(scores_df, ot_annotations=None, top_n=20):
    """Generate evidence cards for top targets.

    Args:
        scores_df: Output from score_targets()
        ot_annotations: Open Targets annotation dict
        top_n: Number of top targets to generate cards for

    Returns:
        List of dicts with per-target evidence summaries
    """
    cards = []
    top_targets = scores_df.head(top_n)

    for _, row in top_targets.iterrows():
        gene = row["gene"]
        card = {
            "gene": gene,
            "composite_score": row["composite_score"],
            "priority_tier": row["priority_tier"],
            "has_convergence": row["has_convergence"],
            "evidence_summary": {
                "differential_expression": {
                    "score": row["de_score"],
                    "n_celltypes": row["n_de_celltypes"],
                    "celltypes": row["de_celltypes"],
                },
                "pathway_centrality": {
                    "score": row["pathway_score"],
                    "disease_pathways": row["disease_pathways"],
                },
                "lr_involvement": {
                    "score": row["lr_score"],
                    "disease_pairs": row["disease_lr_pairs"],
                },
                "genetic_evidence": {
                    "score": row["genetic_score"],
                    "direction": row["genetic_direction"],
                },
                "druggability": {
                    "score": row["druggability_score"],
                },
            },
        }

        # Add Open Targets details
        if ot_annotations and gene in ot_annotations:
            ann = ot_annotations[gene]
            card["open_targets"] = {
                "approved_name": ann.get("approved_name"),
                "tractability": ann.get("tractability"),
                "known_drugs": [
                    {"name": d["name"], "phase": d["phase"]}
                    for d in ann.get("known_drugs", [])[:5]
                ],
                "pathways": [p["name"] for p in ann.get("pathways", [])[:5]],
            }

        cards.append(card)

    return cards


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------

def _find_column(df, candidates):
    """Find the first matching column name."""
    for col in candidates:
        if col in df.columns:
            return col
    return None


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Score drug targets")
    parser.add_argument("--de-results", help="JSON file with DE results")
    parser.add_argument("--pathway-results", help="JSON file with pathway results")
    parser.add_argument("--lr-results", help="JSON file with L-R results")
    parser.add_argument("--genetic-results", help="JSON file with genetic results")
    parser.add_argument("--ot-annotations", help="JSON file with OT annotations")
    parser.add_argument("--output", help="Output CSV file")
    args = parser.parse_args()

    print("Target scoring requires pre-computed analysis results.")
    print("Use via Python import: from target_scoring import score_targets")
