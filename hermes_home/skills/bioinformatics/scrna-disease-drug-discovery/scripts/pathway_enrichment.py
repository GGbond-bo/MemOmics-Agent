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
Pathway Enrichment Analysis for scRNA-seq Disease Drug Discovery

Runs pathway activity scoring (decoupler + PROGENy/MSigDB) and gene set
enrichment analysis (gseapy) on differential expression results, then flags
disease-relevant pathways for downstream drug-target prioritization.

Functions:
  - run_pathway_analysis(): Main orchestrator
  - run_decoupler_pathway_activity(): Per-cell pathway activity via decoupler
  - run_gsea_per_celltype(): GSEA on ranked DE genes per cell type
  - identify_disease_pathways(): Flag disease-relevant pathway hits
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

DEFAULT_DISEASE_KEYWORDS = [
    "TGF", "fibrosis", "collagen", "ECM", "extracellular matrix",
    "WNT", "PDGF", "IL4", "IL13", "inflammatory", "interferon",
    "immune", "JAK", "STAT",
]

DEFAULT_GENE_SET_COLLECTIONS = [
    "MSigDB_Hallmark_2020",
    "Reactome_2022",
    "KEGG_2021_Human",
]

MOUSE_GENE_SET_COLLECTIONS = [
    "MSigDB_Hallmark_2020",
    "Reactome_2022",
    "KEGG_2019_Mouse",
]


# ---------------------------------------------------------------------------
# Main orchestrator
# ---------------------------------------------------------------------------

def run_pathway_analysis(
    adata,
    de_results: Dict[str, pd.DataFrame],
    species: str = "human",
    output_dir: Union[str, Path] = "results",
    disease_keywords: Optional[List[str]] = None,
    gene_set_collections: Optional[List[str]] = None,
) -> Dict:
    """
    Run pathway enrichment analysis combining decoupler and GSEA.

    Orchestrates per-cell pathway activity scoring and per-cell-type gene
    set enrichment, then flags disease-relevant pathways for downstream
    drug-target prioritization.

    Parameters
    ----------
    adata : AnnData
        Annotated single-cell dataset (log-normalized in .X)
    de_results : dict
        Dictionary mapping cell type names to DE results DataFrames.
        Each DataFrame must have columns 'gene' (or index) and a ranking
        metric such as 'log2FoldChange' or 'stat'.
    species : str, optional
        Species for gene set selection: "human" or "mouse" (default: "human")
    output_dir : str or Path
        Directory to write output CSV files (default: "results")
    disease_keywords : list of str, optional
        Keywords for flagging disease-relevant pathways.
        Defaults to SSc-related terms (TGF, fibrosis, collagen, etc.)
    gene_set_collections : list of str, optional
        Gene set libraries for gseapy. Defaults to Hallmark, Reactome, KEGG.

    Returns
    -------
    dict
        Keys:
        - "pathway_activity": DataFrame of per-cell pathway activity scores
        - "gsea_results": dict of {celltype: DataFrame} with GSEA output
        - "disease_pathways": list of flagged disease-relevant pathway records
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print("Pathway Enrichment Analysis")
    print("=" * 60)
    print(f"  Species: {species}")
    print(f"  Cell types with DE results: {len(de_results)}")
    print(f"  Output directory: {output_dir}")

    # Step 1 -- Per-cell pathway activity via decoupler
    print("\n--- Step 1: Decoupler pathway activity scoring ---")
    pathway_activity = run_decoupler_pathway_activity(adata, species=species)

    if pathway_activity is not None:
        out_path = output_dir / "pathway_activity_scores.csv"
        pathway_activity.to_csv(out_path)
        print(f"  Saved pathway activity scores to {out_path}")

    # Step 2 -- GSEA per cell type
    print("\n--- Step 2: GSEA per cell type ---")
    gsea_results = run_gsea_per_celltype(
        de_results,
        species=species,
        gene_set_collections=gene_set_collections,
    )

    for celltype, gsea_df in gsea_results.items():
        safe_name = celltype.replace(" ", "_").replace("/", "-")
        out_path = output_dir / f"gsea_{safe_name}.csv"
        gsea_df.to_csv(out_path, index=False)
    print(f"  Saved GSEA results for {len(gsea_results)} cell types")

    # Step 3 -- Flag disease-relevant pathways
    print("\n--- Step 3: Identify disease-relevant pathways ---")
    disease_pathways = identify_disease_pathways(
        gsea_results, disease_keywords=disease_keywords,
    )

    if disease_pathways:
        disease_df = pd.DataFrame(disease_pathways)
        out_path = output_dir / "disease_relevant_pathways.csv"
        disease_df.to_csv(out_path, index=False)
        print(f"  Saved disease-relevant pathways to {out_path}")

    # Summary counts
    total_enriched = sum(
        len(df[df["FDR"] < 0.05]) if "FDR" in df.columns else 0
        for df in gsea_results.values()
    )
    n_celltypes = len(gsea_results)

    print("\n" + "=" * 60)
    print(f"Pathway analysis complete! {total_enriched} enriched pathways "
          f"across {n_celltypes} cell types")
    print("=" * 60)

    return {
        "pathway_activity": pathway_activity,
        "gsea_results": gsea_results,
        "disease_pathways": disease_pathways,
    }


# ---------------------------------------------------------------------------
# Decoupler pathway activity
# ---------------------------------------------------------------------------

def run_decoupler_pathway_activity(
    adata,
    species: str = "human",
    model: str = "progeny",
) -> Optional[pd.DataFrame]:
    """
    Per-cell pathway activity scoring using decoupler.

    Uses the PROGENy model (14 canonical signaling pathways) by default,
    with MSigDB Hallmark as a fallback.  Scores are stored in
    ``adata.obsm["progeny_scores"]`` as a side effect.

    Parameters
    ----------
    adata : AnnData
        Log-normalized scRNA-seq data
    species : str, optional
        "human" or "mouse" (default: "human")
    model : str, optional
        Pathway model to use: "progeny" or "hallmark" (default: "progeny")

    Returns
    -------
    DataFrame or None
        Cell x pathway activity matrix, or None on failure.
    """
    try:
        import decoupler as dc
    except ImportError:
        print("WARNING: decoupler not installed. Skipping pathway activity.",
              file=sys.stderr)
        print("  Install with: pip install decoupler", file=sys.stderr)
        return None

    print(f"  Running decoupler pathway activity ({model}, {species})...")

    try:
        if model == "progeny":
            # Load PROGENy model (top 300 genes per pathway)
            organism = "human" if species == "human" else "mouse"
            # decoupler API changed: get_progeny was removed in newer versions
            try:
                net = dc.get_progeny(organism=organism, top=300)
            except AttributeError:
                try:
                    net = dc.get_resource("progeny", organism=organism)
                    # Filter to top 300 by weight if needed
                    if len(net) > 300 * 14:
                        net = net.groupby("source").apply(
                            lambda x: x.nlargest(300, "weight", keep="first")
                        ).reset_index(drop=True)
                except Exception:
                    print("  WARNING: Could not load PROGENy model. "
                          "Falling back to GSEA-only pathway analysis.",
                          file=sys.stderr)
                    return None
            print(f"  PROGENy model loaded: {net['source'].nunique()} pathways, "
                  f"{len(net)} gene-pathway associations")

            # Run multivariate linear model (MLM) activity inference
            dc.run_mlm(
                mat=adata,
                net=net,
                source="source",
                target="target",
                weight="weight",
                verbose=True,
            )
            activity_key = "mlm_estimate"

        elif model == "hallmark":
            # Use MSigDB Hallmark gene sets
            try:
                msigdb = dc.get_resource("MSigDB", organism=species)
            except Exception:
                try:
                    msigdb = dc.get_resource("msigdb", organism=species)
                except Exception:
                    print("  WARNING: Could not load MSigDB. "
                          "Falling back to GSEA-only.", file=sys.stderr)
                    return None
            hallmark = msigdb[msigdb["collection"] == "hallmark"]
            print(f"  Hallmark gene sets: {hallmark['geneset'].nunique()} sets")

            dc.run_ora(
                mat=adata,
                net=hallmark,
                source="geneset",
                target="genesymbol",
                verbose=True,
            )
            activity_key = "ora_estimate"

        else:
            print(f"WARNING: Unknown model '{model}'. Use 'progeny' or 'hallmark'.",
                  file=sys.stderr)
            return None

        # Extract activity scores
        if activity_key in adata.obsm:
            activity_df = adata.obsm[activity_key].copy()
            if isinstance(activity_df, pd.DataFrame):
                print(f"  Pathway activity matrix: {activity_df.shape[0]} cells x "
                      f"{activity_df.shape[1]} pathways")
                return activity_df
            else:
                # Convert array to DataFrame
                activity_df = pd.DataFrame(
                    activity_df,
                    index=adata.obs_names,
                )
                return activity_df
        else:
            print(f"WARNING: Activity key '{activity_key}' not found in adata.obsm.",
                  file=sys.stderr)
            return None

    except Exception as e:
        print(f"WARNING: Decoupler pathway activity failed: {e}",
              file=sys.stderr)
        return None


# ---------------------------------------------------------------------------
# GSEA per cell type
# ---------------------------------------------------------------------------

def run_gsea_per_celltype(
    de_results: Dict[str, pd.DataFrame],
    species: str = "human",
    gene_set_collections: Optional[List[str]] = None,
    ranking_metric: str = "combined",
    fdr_threshold: float = 0.25,
    min_size: int = 10,
    max_size: int = 500,
    permutation_num: int = 1000,
    seed: int = 42,
) -> Dict[str, pd.DataFrame]:
    """
    GSEA on ranked DE genes per cell type using gseapy.

    Ranks genes by the specified metric from DE results (default:
    log2FoldChange) and runs pre-ranked GSEA against Hallmark, Reactome,
    and KEGG gene sets.

    Parameters
    ----------
    de_results : dict
        {cell_type: DataFrame} with DE results.  Must contain a gene
        identifier column and a ranking metric column.
    species : str, optional
        "human" or "mouse" (default: "human")
    gene_set_collections : list of str, optional
        Gene set library names recognised by gseapy.
        Defaults to Hallmark, Reactome, KEGG for the given species.
    ranking_metric : str, optional
        Column name to rank genes (default: "log2FoldChange").
        Falls back to "stat" or "score" if not found.
    fdr_threshold : float, optional
        FDR cutoff for reporting (default: 0.25, GSEA standard)
    min_size : int, optional
        Minimum gene set size (default: 10)
    max_size : int, optional
        Maximum gene set size (default: 500)
    permutation_num : int, optional
        Number of permutations (default: 1000)
    seed : int, optional
        Random seed for reproducibility (default: 42)

    Returns
    -------
    dict
        {cell_type: DataFrame} where each DataFrame has columns:
        Term, NES, FDR, Leading_edge, gene_set_library.
    """
    try:
        import gseapy as gp
    except ImportError:
        print("WARNING: gseapy not installed. Skipping GSEA.",
              file=sys.stderr)
        print("  Install with: pip install gseapy", file=sys.stderr)
        return {}

    if gene_set_collections is None:
        if species == "mouse":
            gene_set_collections = MOUSE_GENE_SET_COLLECTIONS
        else:
            gene_set_collections = DEFAULT_GENE_SET_COLLECTIONS

    gsea_results = {}

    for celltype, de_df in de_results.items():
        # --- Quality gate: skip cell types with failed/degenerate DE ---
        df_check = de_df.copy()
        if "gene" in df_check.columns and not isinstance(df_check.index[0], str):
            df_check = df_check.set_index("gene")
        padj_col = next((c for c in ["padj", "pvals_adj"] if c in df_check.columns), None)
        if padj_col is not None:
            n_sig = (df_check[padj_col] < 0.05).sum()
            if n_sig == 0:
                print(f"  Skipping GSEA for {celltype}: 0 significant DEGs "
                      f"(GSEA on zero-signal DE is unreliable)")
                continue
            if n_sig < 5:
                print(f"  WARNING: {celltype} has only {n_sig} significant DEGs — "
                      f"GSEA results may be unreliable", file=sys.stderr)

        print(f"  Running GSEA for {celltype}...")

        # Prepare ranked gene list
        ranked = _prepare_ranked_genes(de_df, ranking_metric)
        if ranked is None or len(ranked) < 50:
            print(f"    Skipping {celltype}: insufficient ranked genes "
                  f"({0 if ranked is None else len(ranked)})")
            continue

        celltype_frames = []

        for gene_set_lib in gene_set_collections:
            try:
                pre_res = gp.prerank(
                    rnk=ranked,
                    gene_sets=gene_set_lib,
                    min_size=min_size,
                    max_size=max_size,
                    permutation_num=permutation_num,
                    seed=seed,
                    verbose=False,
                    no_plot=True,
                )

                res_df = pre_res.res2d.copy()
                if res_df.empty:
                    continue

                # Standardize column names
                res_df = _standardize_gsea_columns(res_df)
                res_df["gene_set_library"] = gene_set_lib
                res_df["cell_type"] = celltype
                celltype_frames.append(res_df)

            except Exception as e:
                print(f"    WARNING: GSEA failed for {celltype} / {gene_set_lib}: {e}",
                      file=sys.stderr)
                continue

        if celltype_frames:
            combined = pd.concat(celltype_frames, ignore_index=True)
            # Sort by absolute NES (most enriched first)
            combined = combined.sort_values("NES", key=abs, ascending=False)

            # Cap extreme NES values (artifacts from small cell populations)
            nes_max = combined["NES"].abs().max()
            if nes_max > 10:
                print(f"    WARNING: {celltype} produced |NES| > 10 "
                      f"(max={nes_max:.1f}) — likely artifact from small sample size. "
                      f"Filtering to |NES| <= 5.", file=sys.stderr)
                combined = combined[combined["NES"].abs() <= 5]

            gsea_results[celltype] = combined

            n_sig = (combined["FDR"].astype(float) < fdr_threshold).sum()
            print(f"    {celltype}: {len(combined)} terms tested, "
                  f"{n_sig} significant (FDR < {fdr_threshold})")

            # Incremental save for OOM resilience
            try:
                out_dir = os.environ.get("SCRNA_RESULTS_DIR", "results")
                os.makedirs(out_dir, exist_ok=True)
                safe_name = str(celltype).replace(" ", "_").replace("/", "-")
                path = os.path.join(out_dir, f"pathway_enrichment_{safe_name}.csv")
                combined.to_csv(path, index=False)
                print(f"    Saved: {path}")
            except Exception as e:
                print(f"    WARNING: Failed to save pathway results: {e}",
                      file=sys.stderr)
        else:
            print(f"    {celltype}: no GSEA results returned")

    return gsea_results


# ---------------------------------------------------------------------------
# Disease pathway identification
# ---------------------------------------------------------------------------

def identify_disease_pathways(
    gsea_results: Dict[str, pd.DataFrame],
    disease_keywords: Optional[List[str]] = None,
    fdr_threshold: float = 0.05,
) -> List[Dict]:
    """
    Flag disease-relevant pathways from GSEA results.

    Searches pathway/term names for disease-related keywords and returns
    those that pass the FDR threshold.

    Parameters
    ----------
    gsea_results : dict
        {cell_type: DataFrame} from run_gsea_per_celltype()
    disease_keywords : list of str, optional
        Keywords to match against pathway names (case-insensitive).
        Defaults to SSc-related terms: TGF, fibrosis, collagen, ECM,
        WNT, PDGF, IL4, IL13, inflammatory, interferon, immune, JAK, STAT.
    fdr_threshold : float, optional
        FDR cutoff for significance (default: 0.05)

    Returns
    -------
    list of dict
        Each dict has keys: cell_type, Term, NES, FDR, Leading_edge,
        gene_set_library, matched_keyword.
    """
    if disease_keywords is None:
        disease_keywords = DEFAULT_DISEASE_KEYWORDS

    if not gsea_results:
        print("  No GSEA results to filter.")
        return []

    # Build case-insensitive patterns
    keywords_lower = [kw.lower() for kw in disease_keywords]

    flagged = []

    for celltype, gsea_df in gsea_results.items():
        if gsea_df.empty:
            continue

        # Ensure FDR is numeric
        gsea_df = gsea_df.copy()
        gsea_df["FDR"] = pd.to_numeric(gsea_df["FDR"], errors="coerce")

        # Filter by FDR
        sig_df = gsea_df[gsea_df["FDR"] < fdr_threshold]

        for _, row in sig_df.iterrows():
            term = str(row.get("Term", "")).lower()
            matched = [kw for kw in keywords_lower if kw in term]
            if matched:
                flagged.append({
                    "cell_type": celltype,
                    "Term": row.get("Term", ""),
                    "NES": row.get("NES", np.nan),
                    "FDR": row.get("FDR", np.nan),
                    "Leading_edge": row.get("Leading_edge", ""),
                    "gene_set_library": row.get("gene_set_library", ""),
                    "matched_keyword": ", ".join(matched),
                })

    # Sort by absolute NES
    flagged.sort(key=lambda x: abs(x.get("NES", 0)), reverse=True)

    print(f"  Flagged {len(flagged)} disease-relevant pathway hits "
          f"(FDR < {fdr_threshold})")
    if flagged:
        # Print top hits
        for hit in flagged[:5]:
            direction = "UP" if hit["NES"] > 0 else "DOWN"
            print(f"    [{hit['cell_type']}] {hit['Term']} "
                  f"(NES={hit['NES']:.2f}, {direction}, FDR={hit['FDR']:.1e})")
        if len(flagged) > 5:
            print(f"    ... and {len(flagged) - 5} more")

    return flagged


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _prepare_ranked_genes(
    de_df: pd.DataFrame,
    ranking_metric: str = "combined",
) -> Optional[pd.DataFrame]:
    """Prepare a ranked gene list for GSEA pre-rank from DE results.

    Ranking metrics:
      - "combined" (default): sign(log2FC) × -log10(padj) — balances
        significance and effect size. Genes with padj=1 get metric ≈ 0.
      - "log2FoldChange": raw fold-change (legacy, not recommended for
        cell types with weak DE).

    Returns a two-column DataFrame (gene, metric) sorted by metric,
    or None if preparation fails.
    """
    df = de_df.copy()

    # Identify gene column
    gene_col = None
    if "gene" in df.columns:
        gene_col = "gene"
    elif df.index.name == "gene" or df.index.name is None:
        df = df.reset_index()
        gene_col = df.columns[0]
    else:
        gene_col = df.index.name
        df = df.reset_index()

    if gene_col is None:
        print(f"    WARNING: Could not find gene column. "
              f"Available: {list(df.columns)}", file=sys.stderr)
        return None

    # Compute ranking metric
    if ranking_metric == "combined":
        # Combined stat: sign(log2FC) × -log10(padj)
        fc_col = next((c for c in ["log2FoldChange", "logfoldchanges", "lfc"]
                        if c in df.columns), None)
        padj_col = next((c for c in ["padj", "pvals_adj", "p_val_adj"]
                          if c in df.columns), None)

        if fc_col and padj_col:
            lfc = pd.to_numeric(df[fc_col], errors="coerce").fillna(0)
            padj = pd.to_numeric(df[padj_col], errors="coerce").fillna(1.0)
            # Clip padj to avoid -log10(0) = inf
            padj = padj.clip(lower=1e-300)
            df["_combined_metric"] = np.sign(lfc) * (-np.log10(padj))
            metric_col = "_combined_metric"
        else:
            # Fallback to log2FC if padj not available
            metric_col = fc_col
            if metric_col is None:
                print(f"    WARNING: No fold-change column found.", file=sys.stderr)
                return None
    else:
        # Direct metric column lookup
        metric_col = None
        for candidate in [ranking_metric, "log2FoldChange", "stat", "score",
                          "logfoldchanges", "lfc"]:
            if candidate in df.columns:
                metric_col = candidate
                break
        if metric_col is None:
            print(f"    WARNING: Could not find metric column. "
                  f"Available: {list(df.columns)}", file=sys.stderr)
            return None

    ranked = df[[gene_col, metric_col]].copy()
    ranked.columns = ["gene", "metric"]
    ranked["metric"] = pd.to_numeric(ranked["metric"], errors="coerce")
    ranked = ranked.dropna(subset=["metric"])
    ranked = ranked.drop_duplicates(subset=["gene"], keep="first")
    ranked = ranked.sort_values("metric", ascending=False)
    ranked = ranked.set_index("gene")

    return ranked


def _standardize_gsea_columns(res_df: pd.DataFrame) -> pd.DataFrame:
    """Standardize gseapy result column names to Term, NES, FDR, Leading_edge."""
    col_map = {}

    # Term / pathway name
    for c in ["Term", "term", "Name", "name", "pathway"]:
        if c in res_df.columns:
            col_map[c] = "Term"
            break

    # NES
    for c in ["NES", "nes"]:
        if c in res_df.columns:
            col_map[c] = "NES"
            break

    # FDR
    for c in ["FDR q-val", "fdr", "FDR", "NOM p-val", "FWER p-val",
              "pval", "padj"]:
        if c in res_df.columns:
            col_map[c] = "FDR"
            break

    # Leading edge
    for c in ["Lead_genes", "lead_genes", "Leading_edge", "leading_edge",
              "genes"]:
        if c in res_df.columns:
            col_map[c] = "Leading_edge"
            break

    res_df = res_df.rename(columns=col_map)
    return res_df


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Pathway enrichment analysis for scRNA-seq disease studies"
    )
    parser.add_argument(
        "--adata", required=True,
        help="Path to annotated AnnData (.h5ad) file",
    )
    parser.add_argument(
        "--de-dir", required=True,
        help="Directory containing per-cell-type DE result CSVs "
             "(e.g., Fibroblast_deseq2_results.csv)",
    )
    parser.add_argument(
        "--species", default="human", choices=["human", "mouse"],
        help="Species for gene set selection (default: human)",
    )
    parser.add_argument(
        "--output-dir", default="results/pathway_enrichment",
        help="Output directory (default: results/pathway_enrichment)",
    )
    parser.add_argument(
        "--disease-keywords", nargs="+", default=None,
        help="Keywords to flag disease-relevant pathways",
    )
    parser.add_argument(
        "--gene-sets", nargs="+", default=None,
        help="Gene set library names for gseapy",
    )
    args = parser.parse_args()

    import scanpy as sc

    # Load AnnData
    print(f"Loading AnnData from {args.adata}...")
    adata = sc.read_h5ad(args.adata)
    print(f"  {adata.n_obs} cells, {adata.n_vars} genes")

    # Load DE results
    de_dir = Path(args.de_dir)
    if not de_dir.exists():
        print(f"ERROR: DE results directory not found: {de_dir}",
              file=sys.stderr)
        sys.exit(1)

    de_results = {}
    for csv_file in sorted(de_dir.glob("*_deseq2_results.csv")):
        celltype = csv_file.stem.replace("_deseq2_results", "")
        de_results[celltype] = pd.read_csv(csv_file)
        print(f"  Loaded DE results for {celltype}: "
              f"{len(de_results[celltype])} genes")

    if not de_results:
        # Try loading any CSV as fallback
        for csv_file in sorted(de_dir.glob("*.csv")):
            celltype = csv_file.stem
            de_results[celltype] = pd.read_csv(csv_file)
            print(f"  Loaded DE results for {celltype}: "
                  f"{len(de_results[celltype])} genes")

    if not de_results:
        print("ERROR: No DE result files found.", file=sys.stderr)
        sys.exit(1)

    # Run analysis
    results = run_pathway_analysis(
        adata,
        de_results,
        species=args.species,
        output_dir=args.output_dir,
        disease_keywords=args.disease_keywords,
        gene_set_collections=args.gene_sets,
    )

    print(f"\nDone. Results saved to {args.output_dir}")
