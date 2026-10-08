"""
rgcca_compare.py — Load per-run manifests, rank runs, and write comparison outputs.

Public API:
    rank_runs(run_dirs, ranking_criterion, ranking_direction, output_dir,
              cv_results=None, perm_results=None) -> dict
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd

from rgcca_qc import RGCCAConfigError

logger = logging.getLogger(__name__)

# Keys guaranteed to be present in every manifest.json
MANIFEST_METRIC_KEYS = {
    "AVE_inner_mean",
    "AVE_outer_mean",
    "AVE_inner_comp1",
    "AVE_outer_comp1",
    "crit_final",
}
# Keys present only when tuning was run
OPTIONAL_METRIC_KEYS = {
    "cv_metric_mean",
    "perm_best_crit",
}
ALL_METRIC_KEYS = MANIFEST_METRIC_KEYS | OPTIONAL_METRIC_KEYS


def validate_ranking_criterion(criterion: str) -> None:
    """Raise RGCCAConfigError if criterion is not a known metric key."""
    if criterion not in ALL_METRIC_KEYS:
        raise RGCCAConfigError(
            f"ranking_criterion '{criterion}' is not a recognised metric key.\n"
            f"Valid keys: {sorted(ALL_METRIC_KEYS)}\n"
            "Set ranking_criterion to one of these values in your config."
        )


def load_manifest(run_dir: str) -> Optional[dict]:
    """Load manifest.json from a run directory. Returns None if not found."""
    path = Path(run_dir) / "manifest.json"
    if not path.exists():
        logger.warning("No manifest.json in '%s' — skipping.", run_dir)
        return None
    with open(path) as f:
        return json.load(f)


def _flatten_metrics(manifest: dict) -> dict:
    """
    Extract a flat metrics dict from a manifest, including nested AVE values.
    Returns a dict suitable for a DataFrame row.
    """
    m = manifest.get("metrics", {})
    flat = {
        "AVE_inner_mean":  m.get("AVE_inner_mean"),
        "AVE_outer_mean":  m.get("AVE_outer_mean"),
        "AVE_inner_comp1": m.get("AVE_inner_comp1"),
        "AVE_outer_comp1": m.get("AVE_outer_comp1"),
        "crit_final":      m.get("crit_final"),
        "cv_metric_mean":  m.get("cv_metric_mean"),   # None if not present
        "perm_best_crit":  m.get("perm_best_crit"),   # None if not present
    }
    return flat


def _flatten_params(manifest: dict) -> dict:
    """Extract a flat params dict from a manifest for display."""
    p = manifest.get("params_used", {})
    flat = {}
    for key in ("method", "scheme", "scale", "scale_block", "NA_method",
                "superblock", "comp_orth", "seed"):
        flat[key] = p.get(key)
    # Per-block params: join as string
    for key in ("tau", "ncomp", "sparsity"):
        val = p.get(key)
        if val is not None:
            flat[key] = "/".join(str(v) for v in (val if isinstance(val, list) else [val]))
        else:
            flat[key] = None
    return flat


def rank_runs(
    run_dirs: List[str],
    ranking_criterion: str,
    ranking_direction: str,
    output_dir: str,
    cv_results: Optional[dict] = None,
    perm_results: Optional[dict] = None,
) -> dict:
    """
    Load all run manifests, optionally attach CV/permutation metrics, rank, and save.

    Parameters
    ----------
    run_dirs : list of str
        Paths to individual run output directories (each must contain manifest.json).
    ranking_criterion : str
        Metric key to rank by. Must be in ALL_METRIC_KEYS.
    ranking_direction : str
        "max" or "min".
    output_dir : str
        Directory where ranked_runs.csv and ranked_runs_summary.md are written.
    cv_results : dict or None
        Parsed cv_best_params.json content (attached to all rows as context).
    perm_results : dict or None
        Parsed perm_best_params.json content (attached to all rows as context).

    Returns
    -------
    dict with keys:
        ranked_runs_path, summary_path, top_run_dir, top_run_params, top_run_metrics
    """
    validate_ranking_criterion(ranking_criterion)

    if ranking_direction not in ("max", "min"):
        raise RGCCAConfigError(
            f"ranking_direction must be 'max' or 'min', got '{ranking_direction}'."
        )

    rows = []
    for run_dir in run_dirs:
        manifest = load_manifest(run_dir)
        if manifest is None:
            continue

        row = {"run_dir": run_dir, "run_id": Path(run_dir).name}
        row.update(_flatten_params(manifest))
        row.update(_flatten_metrics(manifest))

        # Attach tuning context if available
        if cv_results is not None:
            row["cv_best_params"] = json.dumps(cv_results)
        if perm_results is not None:
            row["perm_best_params"] = json.dumps(perm_results)

        rows.append(row)

    if not rows:
        raise RGCCAConfigError(
            "No valid run manifests found. Cannot rank runs. "
            "Check that at least one run completed successfully."
        )

    df = pd.DataFrame(rows)

    # Check that ranking_criterion column has at least some non-null values
    if df[ranking_criterion].isna().all():
        raise RGCCAConfigError(
            f"ranking_criterion '{ranking_criterion}' is all-null across all runs. "
            "This metric may only be available after CV or permutation tuning. "
            "Choose a different ranking_criterion or enable the relevant tuning."
        )

    # Sort
    ascending = (ranking_direction == "min")
    df_sorted = df.sort_values(ranking_criterion, ascending=ascending, na_position="last")
    df_sorted.insert(0, "rank", range(1, len(df_sorted) + 1))

    # Save ranked CSV
    os.makedirs(output_dir, exist_ok=True)
    csv_path = os.path.join(output_dir, "ranked_runs.csv")
    df_sorted.to_csv(csv_path, index=False)
    logger.info("Ranked runs written to '%s'", csv_path)

    # Build human-readable summary
    top = df_sorted.iloc[0]
    summary_lines = [
        "# RGCCA Run Comparison — Ranked Summary",
        "",
        f"**Total runs evaluated:** {len(df_sorted)}",
        f"**Ranking criterion:** `{ranking_criterion}` ({ranking_direction}imised)",
        "",
        "---",
        "",
        "## Top Run",
        "",
        f"**Run ID:** `{top['run_id']}`",
        f"**Run directory:** `{top['run_dir']}`",
        "",
        "### Parameters",
        "",
    ]
    param_cols = ["method", "scheme", "tau", "ncomp", "sparsity",
                  "scale", "scale_block", "NA_method", "superblock", "comp_orth", "seed"]
    for col in param_cols:
        val = top.get(col)
        if val is not None:
            summary_lines.append(f"- **{col}**: `{val}`")

    summary_lines += [
        "",
        "### Metrics",
        "",
    ]
    metric_cols = ["AVE_inner_mean", "AVE_outer_mean", "AVE_inner_comp1",
                   "AVE_outer_comp1", "crit_final", "cv_metric_mean", "perm_best_crit"]
    for col in metric_cols:
        val = top.get(col)
        if val is not None and not (isinstance(val, float) and pd.isna(val)):
            summary_lines.append(f"- **{col}**: `{val:.6f}`" if isinstance(val, float) else f"- **{col}**: `{val}`")

    summary_lines += [
        "",
        "### Why this run was selected",
        "",
        f"This run achieved the {'highest' if ranking_direction == 'max' else 'lowest'} "
        f"value of `{ranking_criterion}` = "
        f"`{top[ranking_criterion]:.6f}` across all {len(df_sorted)} evaluated "
        f"parameter combinations.",
        "",
    ]

    # Add tuning context if available
    if cv_results is not None:
        summary_lines += [
            "### CV Tuning Best Parameters",
            "",
            f"```json\n{json.dumps(cv_results, indent=2)}\n```",
            "",
        ]
    if perm_results is not None:
        summary_lines += [
            "### Permutation Tuning Best Parameters",
            "",
            f"```json\n{json.dumps(perm_results, indent=2)}\n```",
            "",
        ]

    # All runs table (top 10)
    summary_lines += [
        "---",
        "",
        "## All Runs (top 10 shown)",
        "",
    ]
    display_cols = ["rank", "run_id", "method", "tau", "ncomp", "sparsity",
                    ranking_criterion]
    display_cols = [c for c in display_cols if c in df_sorted.columns]
    summary_lines.append(df_sorted[display_cols].head(10).to_markdown(index=False))

    summary_text = "\n".join(summary_lines) + "\n"
    summary_path = os.path.join(output_dir, "ranked_runs_summary.md")
    with open(summary_path, "w") as f:
        f.write(summary_text)
    logger.info("Run summary written to '%s'", summary_path)

    return {
        "ranked_runs_path":  csv_path,
        "summary_path":      summary_path,
        "top_run_dir":       str(top["run_dir"]),
        "top_run_params":    {c: top.get(c) for c in param_cols},
        "top_run_metrics":   {c: top.get(c) for c in metric_cols
                              if top.get(c) is not None
                              and not (isinstance(top.get(c), float) and pd.isna(top.get(c)))},
        "n_runs":            len(df_sorted),
    }
