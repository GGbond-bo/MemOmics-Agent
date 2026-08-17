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
Ligand-Receptor Interaction Analysis for scRNA-seq Disease Drug Discovery

Runs cell-cell communication analysis using liana-py with multiple scoring
methods (CellPhoneDB, NATMI, Connectome, log2FC), builds consensus rankings,
compares disease vs control conditions, and flags disease-relevant L-R pairs
for drug-target prioritization.

Functions:
  - run_lr_analysis(): Main orchestrator
  - run_liana_methods(): Run liana with multiple methods
  - get_consensus_ranking(): Aggregate into consensus rank
  - compare_conditions(): Disease vs control L-R comparison
  - identify_disease_lr_pairs(): Flag disease-relevant L-R pairs
"""

import os
import sys
import warnings
from pathlib import Path
from typing import Dict, List, Optional, Union

import numpy as np
import pandas as pd


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

LIANA_METHODS = [
    "cellphonedb",
    "natmi",
    "connectome",
    "log2fc",
]

DEFAULT_SSC_LR_PAIRS = [
    ("TGFB1", "TGFBR1"),
    ("TGFB1", "TGFBR2"),
    ("PDGFB", "PDGFRA"),
    ("PDGFA", "PDGFRA"),
    ("IL13", "IL13RA1"),
    ("IL4", "IL4R"),
    ("WNT5A", "FZD2"),
    ("CCL2", "CCR2"),
    ("CXCL12", "CXCR4"),
]

# Additional disease-context ligand/receptor gene sets for broader matching
SSC_LIGAND_GENES = {
    "TGFB1", "TGFB2", "TGFB3", "PDGFA", "PDGFB", "PDGFC", "PDGFD",
    "IL4", "IL13", "IL6", "IL1B", "TNF", "IFNG", "CCL2", "CCL5",
    "CXCL12", "CXCL10", "WNT5A", "WNT3A", "CTGF", "EDN1",
}

SSC_RECEPTOR_GENES = {
    "TGFBR1", "TGFBR2", "PDGFRA", "PDGFRB", "IL4R", "IL13RA1",
    "IL13RA2", "IL6R", "IL1R1", "TNFRSF1A", "IFNGR1", "CCR2",
    "CCR5", "CXCR4", "CXCR3", "FZD2", "FZD5", "EDNRA", "EDNRB",
}

# Ubiquitous housekeeping L-R pairs to de-prioritize in visualization
HOUSEKEEPING_LR = {
    ("VIM", "CD44"), ("B2M", "KLRD1"), ("B2M", "KLRC1"),
    ("B2M", "HFE"), ("B2M", "LILRB1"), ("B2M", "LILRB2"),
    ("HLA-A", "CD8A"), ("HLA-B", "CD8A"), ("HLA-C", "CD8A"),
    ("CALM1", "KCNQ1"), ("CALM1", "TRPC3"),
}


# ---------------------------------------------------------------------------
# Main orchestrator
# ---------------------------------------------------------------------------

def run_lr_analysis(
    adata,
    celltype_key: str = "cell_type",
    condition_key: str = "condition",
    output_dir: Union[str, Path] = "results",
    disease_context: Optional[List[tuple]] = None,
    max_celltypes: int = 20,
    max_cells_per_type: int = 2000,
    n_perms: int = 100,
) -> Dict:
    """
    Run ligand-receptor interaction analysis using liana-py.

    Orchestrates multi-method L-R scoring, consensus ranking, condition
    comparison, and disease-relevant pair flagging.

    Parameters
    ----------
    adata : AnnData
        Annotated single-cell dataset with log-normalized expression.
        Must have cell type labels in ``adata.obs[celltype_key]`` and
        condition labels in ``adata.obs[condition_key]``.
    celltype_key : str, optional
        Column in adata.obs with cell type annotations (default: "cell_type")
    condition_key : str, optional
        Column in adata.obs with condition labels (default: "condition")
    output_dir : str or Path
        Directory for output files (default: "results")
    disease_context : list of tuple, optional
        Known disease-relevant (ligand, receptor) pairs.
        Defaults to SSc-relevant pairs (TGFB1-TGFBR1, PDGFB-PDGFRA, etc.)

    Returns
    -------
    dict
        Keys:
        - "interactions": DataFrame of consensus-ranked L-R interactions
        - "disease_specific": DataFrame of disease-enriched interactions
        - "network_summary": dict with summary statistics
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Validate inputs
    if celltype_key not in adata.obs.columns:
        raise ValueError(
            f"'{celltype_key}' not found in adata.obs. "
            f"Available: {list(adata.obs.columns)}"
        )
    if condition_key not in adata.obs.columns:
        raise ValueError(
            f"'{condition_key}' not found in adata.obs. "
            f"Available: {list(adata.obs.columns)}"
        )

    n_celltypes = adata.obs[celltype_key].nunique()
    conditions = adata.obs[condition_key].unique().tolist()

    print("=" * 60)
    print("Ligand-Receptor Interaction Analysis")
    print("=" * 60)
    print(f"  Cells: {adata.n_obs}")
    print(f"  Cell types: {n_celltypes} ({celltype_key})")
    print(f"  Conditions: {conditions} ({condition_key})")
    print(f"  Output directory: {output_dir}")

    if n_celltypes < 2:
        print("ERROR: L-R analysis requires at least 2 cell types.",
              file=sys.stderr)
        return {
            "interactions": pd.DataFrame(),
            "disease_specific": pd.DataFrame(),
            "network_summary": {"error": "insufficient cell types"},
        }

    # --- Scalability: prepare data for tractable LIANA runtime ---
    # LIANA scales as O(n_celltypes^2 * n_cells * n_perms).
    # With 52 types, 76K cells, 1000 perms: ~17 hours.
    # With 15 types, 30K cells, 100 perms: ~5-10 minutes.
    adata_lr = adata.copy()

    # 1. Merge small/rare cell types to stay under max_celltypes
    if n_celltypes > max_celltypes:
        ct_counts = adata_lr.obs[celltype_key].value_counts()
        # Keep the top max_celltypes by cell count; merge the rest into "Other"
        top_types = ct_counts.head(max_celltypes).index.tolist()
        mask = ~adata_lr.obs[celltype_key].isin(top_types)
        n_merged = mask.sum()
        adata_lr.obs[celltype_key] = adata_lr.obs[celltype_key].where(
            adata_lr.obs[celltype_key].isin(top_types), "Other"
        )
        new_n = adata_lr.obs[celltype_key].nunique()
        print(f"  Scalability: merged {n_celltypes} -> {new_n} cell types "
              f"(max_celltypes={max_celltypes}, {n_merged} cells -> 'Other')")
        n_celltypes = new_n

    # 2. Subsample cells per type for tractable runtime
    if adata_lr.n_obs > max_celltypes * max_cells_per_type:
        import random
        random.seed(42)
        keep_idx = []
        for ct in adata_lr.obs[celltype_key].unique():
            ct_idx = adata_lr.obs.index[adata_lr.obs[celltype_key] == ct].tolist()
            n_keep = min(len(ct_idx), max_cells_per_type)
            keep_idx.extend(random.sample(ct_idx, n_keep))
        adata_lr = adata_lr[keep_idx].copy()
        print(f"  Scalability: subsampled to {adata_lr.n_obs} cells "
              f"(max {max_cells_per_type}/type)")

    # Ensure categorical
    adata_lr.obs[celltype_key] = adata_lr.obs[celltype_key].astype("category")

    print(f"  L-R input: {adata_lr.n_obs} cells, "
          f"{adata_lr.obs[celltype_key].nunique()} cell types, "
          f"{n_perms} permutations")

    # NOTE: LIANA can take 5-30 minutes depending on dataset size.
    # Each step saves partial results so progress is not lost on interruption.

    interactions = pd.DataFrame()
    disease_specific = pd.DataFrame()

    # Step 1 -- Run liana with multiple methods (on the scalability-prepared data)
    print("\n--- Step 1: Run liana multi-method scoring ---")
    try:
        liana_results = run_liana_methods(adata_lr, celltype_key=celltype_key,
                                          n_perms=n_perms)
    except Exception as e:
        print(f"  WARNING: Liana run failed: {e}. Continuing with empty results.",
              file=sys.stderr)
        liana_results = None

    # Step 2 -- Consensus ranking
    print("\n--- Step 2: Consensus ranking ---")
    if liana_results is not None:
        interactions = get_consensus_ranking(liana_results)

    if not interactions.empty:
        out_path = output_dir / "lr_interactions_consensus.csv"
        interactions.to_csv(out_path, index=False)
        print(f"  Saved consensus interactions to {out_path}")

    # Step 3 -- Condition-specific comparison (PRIMARY analysis for disease discovery)
    # Running liana separately on disease vs control identifies interactions
    # enriched in disease rather than the average state across conditions.
    print("\n--- Step 3: Condition-specific L-R analysis ---")
    if len(conditions) >= 2:
        try:
            disease_specific = compare_conditions(
                adata_lr,
                celltype_key=celltype_key,
                condition_key=condition_key,
            )
            if not disease_specific.empty:
                out_path = output_dir / "lr_disease_enriched.csv"
                disease_specific.to_csv(out_path, index=False)
                print(f"  Saved disease-enriched interactions to {out_path}")
                # Use disease-specific as the PRIMARY interactions if available
                if interactions.empty:
                    interactions = disease_specific
        except Exception as e:
            print(f"  WARNING: Condition comparison failed: {e}. "
                  f"Using pooled interactions instead.", file=sys.stderr)
            disease_specific = pd.DataFrame()
    else:
        print("  Skipping condition comparison (need >=2 conditions)")

    # Step 4 -- Flag disease-relevant pairs
    print("\n--- Step 4: Flag disease-relevant L-R pairs ---")
    # Prioritize disease-specific interactions for flagging
    source_df = disease_specific if not disease_specific.empty else interactions
    disease_lr = identify_disease_lr_pairs(
        source_df, disease_context=disease_context,
    )

    if not disease_lr.empty:
        out_path = output_dir / "lr_disease_relevant_pairs.csv"
        disease_lr.to_csv(out_path, index=False)
        print(f"  Saved disease-relevant L-R pairs to {out_path}")

    # Build network summary
    network_summary = _build_network_summary(
        interactions, disease_specific, disease_lr, n_celltypes,
    )
    _print_network_summary(network_summary)

    # Verification message
    n_sig = len(interactions) if not interactions.empty else 0
    n_disease = len(disease_lr) if not disease_lr.empty else 0
    print("\n" + "=" * 60)
    print(f"L-R analysis complete! {n_sig} significant interactions, "
          f"{n_disease} disease-relevant")
    print("=" * 60)

    return {
        "interactions": interactions,
        "disease_specific": disease_specific,
        "network_summary": network_summary,
    }


# ---------------------------------------------------------------------------
# Liana multi-method scoring
# ---------------------------------------------------------------------------

def run_liana_methods(
    adata,
    celltype_key: str = "cell_type",
    methods: Optional[List[str]] = None,
    resource_name: str = "consensus",
    n_perms: int = 1000,
    seed: int = 42,
):
    """
    Run liana-py with multiple L-R scoring methods.

    Executes CellPhoneDB, NATMI, Connectome, and log2FC scoring methods
    on the full dataset. Results are stored in ``adata.uns["liana_res"]``.

    Parameters
    ----------
    adata : AnnData
        Log-normalized scRNA-seq data with cell type labels
    celltype_key : str, optional
        Column for cell type annotations (default: "cell_type")
    methods : list of str, optional
        Scoring methods to run (default: cellphonedb, natmi, connectome, log2fc)
    resource_name : str, optional
        L-R resource database (default: "consensus")
    n_perms : int, optional
        Number of permutations for statistical methods (default: 1000)
    seed : int, optional
        Random seed (default: 42)

    Returns
    -------
    object or None
        Liana results object (also stored in adata.uns), or None on failure.
    """
    try:
        import liana as li
    except ImportError:
        print("WARNING: liana-py not installed. Skipping L-R analysis.",
              file=sys.stderr)
        print("  Install with: pip install liana", file=sys.stderr)
        return None

    if methods is None:
        methods = LIANA_METHODS

    print(f"  Methods: {methods}")
    print(f"  Resource: {resource_name}")
    print(f"  Permutations: {n_perms}")

    # Ensure cell type column is categorical
    adata.obs[celltype_key] = adata.obs[celltype_key].astype("category")

    try:
        li.mt.rank_aggregate(
            adata,
            groupby=celltype_key,
            resource_name=resource_name,
            n_perms=n_perms,
            seed=seed,
            verbose=True,
            use_raw=False,
        )

        # liana stores results in adata.uns["liana_res"]
        if "liana_res" in adata.uns:
            liana_res = adata.uns["liana_res"]
            n_interactions = len(liana_res) if hasattr(liana_res, '__len__') else 0
            print(f"  Liana returned {n_interactions} scored interactions")
            return liana_res
        else:
            print("WARNING: liana_res not found in adata.uns after run.",
                  file=sys.stderr)
            return None

    except Exception as e:
        print(f"WARNING: Liana multi-method run failed: {e}",
              file=sys.stderr)
        return None


# ---------------------------------------------------------------------------
# Consensus ranking
# ---------------------------------------------------------------------------

def get_consensus_ranking(
    liana_results,
    top_n: Optional[int] = None,
) -> pd.DataFrame:
    """
    Aggregate liana multi-method scores into a consensus ranking.

    Combines p-values and scores from multiple methods into a single
    consensus rank and counts how many methods found each interaction
    significant.

    Parameters
    ----------
    liana_results : DataFrame
        Liana results (from adata.uns["liana_res"] or run_liana_methods())
    top_n : int, optional
        Return only top N interactions (default: all)

    Returns
    -------
    DataFrame
        Columns: source, target, ligand_complex, receptor_complex,
        consensus_rank, methods_significant, specificity_rank.
    """
    if liana_results is None:
        return pd.DataFrame()

    # Convert to DataFrame if needed
    if isinstance(liana_results, pd.DataFrame):
        df = liana_results.copy()
    else:
        try:
            df = pd.DataFrame(liana_results)
        except Exception as e:
            print(f"WARNING: Cannot convert liana results to DataFrame: {e}",
                  file=sys.stderr)
            return pd.DataFrame()

    if df.empty:
        return pd.DataFrame()

    # Identify key columns (liana uses various naming conventions)
    source_col = _find_column(df, ["source", "sender", "cell_type_1",
                                    "celltype_1", "cluster_1"])
    target_col = _find_column(df, ["target", "receiver", "cell_type_2",
                                    "celltype_2", "cluster_2"])
    ligand_col = _find_column(df, ["ligand_complex", "ligand", "ligand_gene",
                                    "gene_a"])
    receptor_col = _find_column(df, ["receptor_complex", "receptor",
                                      "receptor_gene", "gene_b"])

    if any(c is None for c in [source_col, target_col, ligand_col, receptor_col]):
        print(f"WARNING: Could not identify required columns in liana results. "
              f"Available: {list(df.columns)}", file=sys.stderr)
        return pd.DataFrame()

    # Build consensus DataFrame
    consensus = pd.DataFrame({
        "source": df[source_col],
        "target": df[target_col],
        "ligand_complex": df[ligand_col],
        "receptor_complex": df[receptor_col],
    })

    # Count methods significant
    # liana stores per-method scores; count those passing threshold
    method_sig_cols = [c for c in df.columns
                       if any(m in c.lower() for m in ["pvalue", "pval", "p_value"])]
    if method_sig_cols:
        sig_counts = (df[method_sig_cols] < 0.05).sum(axis=1)
        consensus["methods_significant"] = sig_counts
    else:
        consensus["methods_significant"] = np.nan

    # Extract aggregate rank if available
    rank_col = _find_column(df, ["magnitude_rank", "specificity_rank",
                                  "rank_aggregate", "aggregate_rank",
                                  "consensus_rank"])
    if rank_col is not None:
        rank_values = df[rank_col].values
        # If rank column is all NaN, fall back to other columns
        if pd.isna(rank_values).all():
            rank_col = None  # Trigger fallback below
            print("  WARNING: consensus_rank column is all NaN, using fallback ranking",
                  file=sys.stderr)
        else:
            consensus["consensus_rank"] = rank_values
    if rank_col is None:
        # Compute rank from available score columns
        score_cols = [c for c in df.columns
                      if any(s in c.lower() for s in ["score", "mean", "magnitude"])]
        if score_cols:
            # Lower rank = more significant
            consensus["consensus_rank"] = df[score_cols[0]].rank(
                ascending=True, method="min"
            ).astype(int)
        else:
            consensus["consensus_rank"] = range(1, len(consensus) + 1)

    # Specificity rank
    spec_col = _find_column(df, ["specificity_rank", "spec_rank"])
    if spec_col is not None:
        consensus["specificity_rank"] = df[spec_col].values
    else:
        consensus["specificity_rank"] = consensus["consensus_rank"]

    # Sort by consensus rank
    consensus = consensus.sort_values("consensus_rank").reset_index(drop=True)

    if top_n is not None:
        consensus = consensus.head(top_n)

    n_unique_pairs = consensus.groupby(
        ["ligand_complex", "receptor_complex"]
    ).ngroups
    print(f"  Consensus ranking: {len(consensus)} interactions, "
          f"{n_unique_pairs} unique L-R pairs")

    return consensus


# ---------------------------------------------------------------------------
# Condition comparison
# ---------------------------------------------------------------------------

def compare_conditions(
    adata,
    celltype_key: str = "cell_type",
    condition_key: str = "condition",
    disease_label: Optional[str] = None,
    control_label: Optional[str] = None,
    methods: Optional[List[str]] = None,
    resource_name: str = "consensus",
) -> pd.DataFrame:
    """
    Run liana separately on disease and control subsets to find enriched
    interactions.

    Compares consensus scores between conditions and identifies L-R
    interactions that are significantly stronger in the disease state.

    Parameters
    ----------
    adata : AnnData
        Full dataset with condition labels
    celltype_key : str, optional
        Cell type column (default: "cell_type")
    condition_key : str, optional
        Condition column (default: "condition")
    disease_label : str, optional
        Label for disease condition. Auto-detected if None.
    control_label : str, optional
        Label for control condition. Auto-detected if None.
    methods : list of str, optional
        Liana methods to run (default: same as run_liana_methods)
    resource_name : str, optional
        L-R resource (default: "consensus")

    Returns
    -------
    DataFrame
        Disease-enriched interactions with columns: source, target,
        ligand_complex, receptor_complex, disease_rank, control_rank,
        rank_diff, enrichment.
    """
    try:
        import liana as li
    except ImportError:
        print("WARNING: liana-py not installed.", file=sys.stderr)
        return pd.DataFrame()

    conditions = adata.obs[condition_key].unique().tolist()
    if len(conditions) < 2:
        print("  Cannot compare conditions: need at least 2 conditions.")
        return pd.DataFrame()

    # Auto-detect disease/control labels
    if disease_label is None or control_label is None:
        disease_label, control_label = _detect_condition_labels(conditions)
        print(f"  Auto-detected: disease='{disease_label}', "
              f"control='{control_label}'")

    # Subset by condition
    disease_adata = adata[adata.obs[condition_key] == disease_label].copy()
    control_adata = adata[adata.obs[condition_key] == control_label].copy()

    print(f"  Disease subset: {disease_adata.n_obs} cells")
    print(f"  Control subset: {control_adata.n_obs} cells")

    # Check minimum cell types in each subset
    for label, subset in [("disease", disease_adata), ("control", control_adata)]:
        n_types = subset.obs[celltype_key].nunique()
        if n_types < 2:
            print(f"  WARNING: {label} subset has only {n_types} cell type(s). "
                  f"Skipping condition comparison.", file=sys.stderr)
            return pd.DataFrame()

    # Run liana on each condition
    print(f"  Running liana on disease subset ({disease_label})...")
    disease_res = run_liana_methods(
        disease_adata, celltype_key=celltype_key, methods=methods,
        resource_name=resource_name,
    )

    print(f"  Running liana on control subset ({control_label})...")
    control_res = run_liana_methods(
        control_adata, celltype_key=celltype_key, methods=methods,
        resource_name=resource_name,
    )

    if disease_res is None or control_res is None:
        print("  Condition comparison failed: one or both runs returned None.")
        return pd.DataFrame()

    # Get consensus rankings for each
    disease_ranked = get_consensus_ranking(disease_res)
    control_ranked = get_consensus_ranking(control_res)

    if disease_ranked.empty or control_ranked.empty:
        return pd.DataFrame()

    # Merge on interaction identity
    merge_keys = ["source", "target", "ligand_complex", "receptor_complex"]

    merged = disease_ranked[merge_keys + ["consensus_rank"]].merge(
        control_ranked[merge_keys + ["consensus_rank"]],
        on=merge_keys,
        how="outer",
        suffixes=("_disease", "_control"),
    )

    # Fill missing ranks with worst rank + 1
    max_rank = max(
        merged["consensus_rank_disease"].max(),
        merged["consensus_rank_control"].max(),
    )
    merged["consensus_rank_disease"] = merged["consensus_rank_disease"].fillna(
        max_rank + 1
    )
    merged["consensus_rank_control"] = merged["consensus_rank_control"].fillna(
        max_rank + 1
    )

    # Compute rank difference (negative = enriched in disease)
    merged["rank_diff"] = (
        merged["consensus_rank_disease"] - merged["consensus_rank_control"]
    )

    # Label enrichment direction
    merged["enrichment"] = "none"
    merged.loc[merged["rank_diff"] < -10, "enrichment"] = "disease_enriched"
    merged.loc[merged["rank_diff"] > 10, "enrichment"] = "control_enriched"

    # Rename for clarity
    merged = merged.rename(columns={
        "consensus_rank_disease": "disease_rank",
        "consensus_rank_control": "control_rank",
    })

    # Sort by disease enrichment (most enriched first)
    merged = merged.sort_values("rank_diff").reset_index(drop=True)

    disease_enriched = merged[merged["enrichment"] == "disease_enriched"]
    print(f"  Found {len(disease_enriched)} disease-enriched interactions "
          f"out of {len(merged)} total")

    return merged


# ---------------------------------------------------------------------------
# Disease-relevant L-R pair identification
# ---------------------------------------------------------------------------

def identify_disease_lr_pairs(
    interactions: pd.DataFrame,
    disease_context: Optional[List[tuple]] = None,
    match_mode: str = "both",
) -> pd.DataFrame:
    """
    Flag SSc-relevant L-R pairs from interaction results.

    Matches known disease-relevant ligand-receptor pairs against the scored
    interaction table. Supports exact pair matching and partial gene matching.

    Parameters
    ----------
    interactions : DataFrame
        L-R interaction results with ligand/receptor columns
    disease_context : list of tuple, optional
        Known (ligand, receptor) pairs. Defaults to SSc-relevant pairs:
        TGFB1-TGFBR1, TGFB1-TGFBR2, PDGFB-PDGFRA, PDGFA-PDGFRA,
        IL13-IL13RA1, IL4-IL4R, WNT5A-FZD2, CCL2-CCR2, CXCL12-CXCR4.
    match_mode : str, optional
        "exact" for exact pair match, "partial" for any gene match,
        "both" for either (default: "both")

    Returns
    -------
    DataFrame
        Filtered interactions matching disease-relevant L-R pairs,
        with added 'match_type' column.
    """
    if interactions is None or interactions.empty:
        print("  No interactions to filter.")
        return pd.DataFrame()

    if disease_context is None:
        disease_context = DEFAULT_SSC_LR_PAIRS

    # Identify ligand/receptor columns
    ligand_col = _find_column(interactions, [
        "ligand_complex", "ligand", "ligand_gene", "gene_a",
    ])
    receptor_col = _find_column(interactions, [
        "receptor_complex", "receptor", "receptor_gene", "gene_b",
    ])

    if ligand_col is None or receptor_col is None:
        print(f"WARNING: Cannot find ligand/receptor columns. "
              f"Available: {list(interactions.columns)}", file=sys.stderr)
        return pd.DataFrame()

    # Build lookup sets
    exact_pairs = set(disease_context)
    ligand_genes = {pair[0] for pair in disease_context} | SSC_LIGAND_GENES
    receptor_genes = {pair[1] for pair in disease_context} | SSC_RECEPTOR_GENES

    matches = []

    for idx, row in interactions.iterrows():
        lig = str(row[ligand_col]).strip()
        rec = str(row[receptor_col]).strip()

        # Handle complex notation (e.g., "TGFB1_TGFB2")
        lig_genes = set(lig.replace("_", " ").replace(":", " ").split())
        rec_genes = set(rec.replace("_", " ").replace(":", " ").split())

        match_type = None

        if match_mode in ("exact", "both"):
            # Check exact pair matches
            for pair_lig, pair_rec in exact_pairs:
                if pair_lig in lig_genes and pair_rec in rec_genes:
                    match_type = "exact_pair"
                    break

        if match_type is None and match_mode in ("partial", "both"):
            # Check partial gene matches
            if lig_genes & ligand_genes or rec_genes & receptor_genes:
                match_type = "partial_gene"

        if match_type is not None:
            row_dict = row.to_dict()
            row_dict["match_type"] = match_type
            matches.append(row_dict)

    if matches:
        result = pd.DataFrame(matches)
        # Sort: exact matches first, then by rank if available
        sort_cols = ["match_type"]
        if "consensus_rank" in result.columns:
            sort_cols.append("consensus_rank")
        elif "disease_rank" in result.columns:
            sort_cols.append("disease_rank")
        result = result.sort_values(sort_cols).reset_index(drop=True)

        n_exact = (result["match_type"] == "exact_pair").sum()
        n_partial = (result["match_type"] == "partial_gene").sum()
        print(f"  Flagged {len(result)} disease-relevant L-R interactions "
              f"({n_exact} exact pairs, {n_partial} partial gene matches)")
    else:
        result = pd.DataFrame()
        print("  No disease-relevant L-R pairs found in results.")

    return result


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _find_column(df: pd.DataFrame, candidates: List[str]) -> Optional[str]:
    """Find the first matching column name from a list of candidates."""
    for col in candidates:
        if col in df.columns:
            return col
    return None


def _detect_condition_labels(conditions: List[str]) -> tuple:
    """Auto-detect disease and control labels from condition names.

    Returns (disease_label, control_label).
    """
    disease_keywords = [
        "ssc", "sclerosis", "disease", "dcSSc", "lcSSc",
        "treated", "tumor", "cancer", "patient",
    ]
    control_keywords = [
        "healthy", "control", "normal", "HC", "untreated",
        "baseline", "WT", "wildtype",
    ]

    disease_label = None
    control_label = None

    for cond in conditions:
        cond_lower = str(cond).lower()
        if any(kw.lower() in cond_lower for kw in control_keywords):
            control_label = cond
        elif any(kw.lower() in cond_lower for kw in disease_keywords):
            disease_label = cond

    # Fallback: first condition = disease, second = control
    if disease_label is None:
        remaining = [c for c in conditions if c != control_label]
        disease_label = remaining[0] if remaining else conditions[0]
    if control_label is None:
        remaining = [c for c in conditions if c != disease_label]
        control_label = remaining[0] if remaining else conditions[-1]

    return disease_label, control_label


def _build_network_summary(
    interactions: pd.DataFrame,
    disease_specific: pd.DataFrame,
    disease_lr: pd.DataFrame,
    n_celltypes: int,
) -> Dict:
    """Build a summary dict of the L-R network analysis."""
    summary = {
        "n_celltypes": n_celltypes,
        "n_total_interactions": len(interactions) if not interactions.empty else 0,
        "n_unique_lr_pairs": 0,
        "n_unique_sources": 0,
        "n_unique_targets": 0,
        "n_disease_enriched": 0,
        "n_disease_relevant": len(disease_lr) if not disease_lr.empty else 0,
        "top_source_celltypes": [],
        "top_target_celltypes": [],
    }

    if not interactions.empty:
        if "ligand_complex" in interactions.columns and "receptor_complex" in interactions.columns:
            summary["n_unique_lr_pairs"] = interactions.groupby(
                ["ligand_complex", "receptor_complex"]
            ).ngroups
        if "source" in interactions.columns:
            summary["n_unique_sources"] = interactions["source"].nunique()
            summary["top_source_celltypes"] = (
                interactions["source"].value_counts().head(5).index.tolist()
            )
        if "target" in interactions.columns:
            summary["n_unique_targets"] = interactions["target"].nunique()
            summary["top_target_celltypes"] = (
                interactions["target"].value_counts().head(5).index.tolist()
            )

    if not disease_specific.empty and "enrichment" in disease_specific.columns:
        summary["n_disease_enriched"] = (
            disease_specific["enrichment"] == "disease_enriched"
        ).sum()

    return summary


def _print_network_summary(summary: Dict):
    """Print a formatted network summary."""
    print("\n--- Network Summary ---")
    print(f"  Total scored interactions: {summary['n_total_interactions']}")
    print(f"  Unique L-R pairs: {summary['n_unique_lr_pairs']}")
    print(f"  Sender cell types: {summary['n_unique_sources']}")
    print(f"  Receiver cell types: {summary['n_unique_targets']}")
    print(f"  Disease-enriched interactions: {summary['n_disease_enriched']}")
    print(f"  Disease-relevant L-R pairs: {summary['n_disease_relevant']}")
    if summary["top_source_celltypes"]:
        print(f"  Top senders: {', '.join(summary['top_source_celltypes'])}")
    if summary["top_target_celltypes"]:
        print(f"  Top receivers: {', '.join(summary['top_target_celltypes'])}")


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Ligand-receptor interaction analysis for scRNA-seq disease studies"
    )
    parser.add_argument(
        "--adata", required=True,
        help="Path to annotated AnnData (.h5ad) file",
    )
    parser.add_argument(
        "--celltype-key", default="cell_type",
        help="Column name for cell type annotations (default: cell_type)",
    )
    parser.add_argument(
        "--condition-key", default="condition",
        help="Column name for condition labels (default: condition)",
    )
    parser.add_argument(
        "--output-dir", default="results/ligand_receptor",
        help="Output directory (default: results/ligand_receptor)",
    )
    parser.add_argument(
        "--methods", nargs="+", default=None,
        choices=["cellphonedb", "natmi", "connectome", "log2fc",
                 "singlecellsignalr", "cellchat"],
        help="Liana scoring methods (default: cellphonedb natmi connectome log2fc)",
    )
    parser.add_argument(
        "--resource", default="consensus",
        help="L-R resource database (default: consensus)",
    )
    args = parser.parse_args()

    import scanpy as sc

    # Load AnnData
    print(f"Loading AnnData from {args.adata}...")
    adata = sc.read_h5ad(args.adata)
    print(f"  {adata.n_obs} cells, {adata.n_vars} genes")
    print(f"  Cell types: {adata.obs[args.celltype_key].nunique()}")
    print(f"  Conditions: {adata.obs[args.condition_key].unique().tolist()}")

    # Run analysis
    results = run_lr_analysis(
        adata,
        celltype_key=args.celltype_key,
        condition_key=args.condition_key,
        output_dir=args.output_dir,
    )

    print(f"\nDone. Results saved to {args.output_dir}")
