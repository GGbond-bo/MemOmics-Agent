"""
rgcca_runner.py — Main Python orchestrator for the RGCCA multiblock skill.

Entry point:
    run_rgcca(config: dict | str) -> dict

The config may be a Python dict or a path to a JSON file.
All outputs are written to /mnt/results/rgcca_<timestamp>/.

See SKILL.md for the full configuration schema and parameter reference.
"""

from __future__ import annotations

import hashlib
import itertools
import json
import logging
import os
import random
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

# Skill-local imports (same directory)
_SKILL_DIR = Path(__file__).parent
sys.path.insert(0, str(_SKILL_DIR))

from rgcca_qc import (
    RGCCAConfigError,
    RGCCAValidationError,
    load_blocks,
    run_qc,
    verify_alignment,
)
from rgcca_design import build_connection_matrix, matrix_to_csv
from rgcca_compare import rank_runs, validate_ranking_criterion

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("rgcca_runner")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
RESULTS_BASE = Path("/mnt/results")
R_SCRIPTS = {
    "fit":  str(_SKILL_DIR / "rgcca_fit.R"),
    "cv":   str(_SKILL_DIR / "rgcca_tune_cv.R"),
    "perm": str(_SKILL_DIR / "rgcca_tune_perm.R"),
    "plot": str(_SKILL_DIR / "rgcca_plots.R"),
}

VALID_METHODS = {
    "rgcca", "sgcca", "pca", "spca", "pls", "spls", "cca", "ifa", "ra",
    "gcca", "maxvar", "maxvar-b", "maxvar-a", "mfa", "mcia", "mcoa",
    "cpca-1", "cpca-2", "cpca-4", "hpca", "maxbet-b", "maxbet",
    "maxdiff-b", "maxdiff", "sabscor", "ssqcor", "ssqcov-1", "ssqcov-2",
    "ssqcov", "sumcor", "sumcov-1", "sumcov-2", "sumcov", "sabscov-1", "sabscov-2",
}
VALID_SCHEMES    = {"horst", "centroid", "factorial"}
VALID_NA_METHODS = {"na.ignore", "na.omit"}
VALID_SCALE_BLOCK  = {"none", "inertia", "lambda1", "ssq"}
VALID_CV_METRICS   = {"RMSE", "MAE"}  # RGCCA 3.0.3 rgcca_cv() metric argument


# ---------------------------------------------------------------------------
# Custom exception for R subprocess failures
# ---------------------------------------------------------------------------
class RGCCAFitError(Exception):
    """Raised when an Rscript subprocess exits non-zero."""


# ---------------------------------------------------------------------------
# Config loading and validation
# ---------------------------------------------------------------------------

def _load_config(config: dict | str) -> dict:
    if isinstance(config, str):
        with open(config) as f:
            cfg = json.load(f)
    elif isinstance(config, dict):
        cfg = dict(config)
    else:
        raise RGCCAConfigError(
            f"config must be a dict or a path to a JSON file, got {type(config).__name__}."
        )
    return cfg


def _validate_config(cfg: dict) -> None:
    """Raise RGCCAConfigError for any missing or invalid top-level config keys."""
    required = ["blocks", "design", "parameter_grid", "ranking_criterion"]
    for key in required:
        if key not in cfg:
            raise RGCCAConfigError(
                f"Required config key '{key}' is missing. "
                f"Required keys: {required}"
            )

    if not isinstance(cfg["blocks"], dict) or len(cfg["blocks"]) < 2:
        raise RGCCAConfigError(
            "'blocks' must be a dict with at least 2 entries: {block_name: path_to_csv}."
        )

    if not isinstance(cfg["parameter_grid"], list) or len(cfg["parameter_grid"]) == 0:
        raise RGCCAConfigError(
            "'parameter_grid' must be a non-empty list of parameter dicts."
        )

    # Validate ranking_criterion early
    validate_ranking_criterion(cfg["ranking_criterion"])

    direction = cfg.get("ranking_direction", "max")
    if direction not in ("max", "min"):
        raise RGCCAConfigError(
            f"ranking_direction must be 'max' or 'min', got '{direction}'."
        )

    # Validate response_block if given
    response_block = cfg.get("response_block")
    if response_block is not None and response_block not in cfg["blocks"]:
        raise RGCCAConfigError(
            f"response_block '{response_block}' is not among the block names: "
            f"{list(cfg['blocks'].keys())}"
        )

    # Validate preprocessing keys
    prep = cfg.get("preprocessing", {})
    if "scale_block" in prep and prep["scale_block"] not in VALID_SCALE_BLOCK:
        raise RGCCAConfigError(
            f"preprocessing.scale_block '{prep['scale_block']}' is invalid. "
            f"Valid values: {sorted(VALID_SCALE_BLOCK)}"
        )
    if "NA_method" in prep and prep["NA_method"] not in VALID_NA_METHODS:
        raise RGCCAConfigError(
            f"preprocessing.NA_method '{prep['NA_method']}' is invalid. "
            f"Valid values: {sorted(VALID_NA_METHODS)}"
        )

    # Validate CV metric
    cv_cfg = cfg.get("tuning", {}).get("cv", {})
    if cv_cfg.get("enabled", False):
        metric = cv_cfg.get("metric", "RMSE")
        if metric not in VALID_CV_METRICS:
            raise RGCCAConfigError(
                f"tuning.cv.metric '{metric}' is not valid for RGCCA 3.0.3. "
                f"Valid values: {sorted(VALID_CV_METRICS)}"
            )

    # Validate each grid entry
    for i, entry in enumerate(cfg["parameter_grid"]):
        for method_val in entry.get("method", ["rgcca"]):
            if method_val.lower() not in VALID_METHODS:
                raise RGCCAConfigError(
                    f"parameter_grid[{i}].method '{method_val}' is not a valid RGCCA method. "
                    f"Valid methods: {sorted(VALID_METHODS)}"
                )
        for scheme_val in entry.get("scheme", ["factorial"]):
            if scheme_val.lower() not in VALID_SCHEMES:
                raise RGCCAConfigError(
                    f"parameter_grid[{i}].scheme '{scheme_val}' is invalid. "
                    f"Valid schemes: {sorted(VALID_SCHEMES)}"
                )


# ---------------------------------------------------------------------------
# Parameter grid expansion
# ---------------------------------------------------------------------------

def _expand_grid(parameter_grid: list) -> List[dict]:
    """
    Expand each grid entry (dict of lists) into all Cartesian combinations,
    then deduplicate across all entries.
    """
    all_combos = []
    for entry in parameter_grid:
        # Each value must be a list; wrap scalars
        normalised = {k: (v if isinstance(v, list) else [v]) for k, v in entry.items()}
        keys = list(normalised.keys())
        for combo in itertools.product(*[normalised[k] for k in keys]):
            all_combos.append(dict(zip(keys, combo)))

    # Deduplicate by JSON-serialised representation
    seen = set()
    unique = []
    for combo in all_combos:
        key = json.dumps(combo, sort_keys=True)
        if key not in seen:
            seen.add(key)
            unique.append(combo)

    logger.info("Parameter grid: %d unique combinations.", len(unique))
    return unique


def _run_id_for(params: dict, idx: int) -> str:
    """Generate a stable run ID from index + parameter hash."""
    h = hashlib.md5(json.dumps(params, sort_keys=True).encode()).hexdigest()[:8]
    return f"run_{idx:04d}_{h}"


# ---------------------------------------------------------------------------
# Rscript subprocess helper
# ---------------------------------------------------------------------------

def _run_rscript(script: str, args: List[str], label: str) -> None:
    """
    Run an R script via Rscript subprocess. Raises RGCCAFitError on non-zero exit.
    Streams stdout/stderr to the Python logger in real time.
    """
    cmd = ["Rscript", "--vanilla", script] + args
    logger.info("[%s] Running: %s", label, " ".join(cmd))

    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    output_lines = []
    for line in proc.stdout:
        line = line.rstrip()
        output_lines.append(line)
        logger.info("[%s] %s", label, line)
    proc.wait()

    if proc.returncode != 0:
        raise RGCCAFitError(
            f"Rscript exited with code {proc.returncode} for [{label}].\n"
            f"Last 20 lines of output:\n"
            + "\n".join(output_lines[-20:])
            + "\nCorrective actions:\n"
            "  1. Check that RGCCA is installed: Rscript -e \"packageVersion('RGCCA')\"\n"
            "  2. Verify block CSV files are readable and numeric.\n"
            "  3. Check parameter values are valid for the chosen method.\n"
            "  4. Inspect the full output above for the R error message."
        )


# ---------------------------------------------------------------------------
# Block CSV writer
# ---------------------------------------------------------------------------

def _write_blocks_to_dir(blocks: Dict[str, pd.DataFrame], blocks_dir: str) -> None:
    """Write each aligned block DataFrame to a CSV in blocks_dir."""
    os.makedirs(blocks_dir, exist_ok=True)
    for name, df in blocks.items():
        path = os.path.join(blocks_dir, f"{name}.csv")
        df.to_csv(path)
    logger.info("Wrote %d block CSV(s) to '%s'.", len(blocks), blocks_dir)


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def run_rgcca(config: dict | str) -> dict:
    """
    Run the full RGCCA pipeline.

    Parameters
    ----------
    config : dict or str
        Configuration dict or path to a JSON config file.
        See SKILL.md for the full schema.

    Returns
    -------
    dict with keys:
        output_dir, config_path, qc_report_path, design_matrix_path,
        run_manifest_path, ranked_runs_path, summary_path,
        top_run, n_runs, tuning
    """
    # ------------------------------------------------------------------
    # 0. Load and validate config
    # ------------------------------------------------------------------
    cfg = _load_config(config)
    _validate_config(cfg)

    seed = int(cfg.get("seed", 42))
    random.seed(seed)
    np.random.seed(seed)

    # ------------------------------------------------------------------
    # 1. Create output directory
    # ------------------------------------------------------------------
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_root = RESULTS_BASE / f"rgcca_{timestamp}"
    out_root.mkdir(parents=True, exist_ok=True)
    runs_dir   = out_root / "runs"
    tuning_dir = out_root / "tuning"
    runs_dir.mkdir(exist_ok=True)
    tuning_dir.mkdir(exist_ok=True)

    logger.info("Output directory: %s", out_root)

    # Save resolved config
    config_path = out_root / "config_used.json"
    with open(config_path, "w") as f:
        json.dump(cfg, f, indent=2, default=str)

    # ------------------------------------------------------------------
    # 2. Load blocks
    # ------------------------------------------------------------------
    logger.info("Loading blocks...")
    blocks = load_blocks(
        block_paths=cfg["blocks"],
        sample_id_col=cfg.get("sample_id_col"),
    )

    # ------------------------------------------------------------------
    # 3. QC
    # ------------------------------------------------------------------
    logger.info("Running QC...")
    allow_const = bool(cfg.get("allow_constant_columns", False))
    blocks, qc_report = run_qc(blocks, allow_constant_columns=allow_const)
    verify_alignment(blocks)

    qc_path = out_root / "qc_report.txt"
    qc_path.write_text(qc_report)
    logger.info("QC report written to '%s'.", qc_path)
    print(qc_report)

    # ------------------------------------------------------------------
    # 4. Build design matrix
    # ------------------------------------------------------------------
    logger.info("Building connection matrix...")
    block_names = list(blocks.keys())
    connection_matrix = build_connection_matrix(
        block_names=block_names,
        design=cfg["design"],
        response_block=cfg.get("response_block"),
    )
    design_path = str(out_root / "design_matrix.csv")
    matrix_to_csv(connection_matrix, design_path)
    logger.info("Connection matrix:\n%s", connection_matrix.to_string())

    # ------------------------------------------------------------------
    # 5. Write aligned blocks to a shared temp directory
    #    (reused by all runs and tuning scripts)
    # ------------------------------------------------------------------
    blocks_dir = str(out_root / "tmp_blocks")
    _write_blocks_to_dir(blocks, blocks_dir)

    # Determine response block index (1-based for R)
    response_block = cfg.get("response_block")
    response_idx = (block_names.index(response_block) + 1) if response_block else None

    # ------------------------------------------------------------------
    # 6. Expand parameter grid
    # ------------------------------------------------------------------
    prep = cfg.get("preprocessing", {})
    base_params = {
        "scale":       prep.get("scale", True),
        "scale_block": prep.get("scale_block", "inertia"),
        "NA_method":   prep.get("NA_method", "na.ignore"),
    }
    if response_idx is not None:
        base_params["response_idx"] = response_idx

    grid = _expand_grid(cfg["parameter_grid"])

    # ------------------------------------------------------------------
    # 7. Fit each run
    # ------------------------------------------------------------------
    run_dirs = []
    run_manifest_entries = []

    for i, params in enumerate(grid, start=1):
        run_id  = _run_id_for(params, i)
        run_dir = str(runs_dir / run_id)
        os.makedirs(run_dir, exist_ok=True)
        plots_dir = os.path.join(run_dir, "plots")
        os.makedirs(plots_dir, exist_ok=True)

        # Merge base params into run params (run params take precedence)
        full_params = {**base_params, **params}

        # Write run params JSON
        params_path = os.path.join(run_dir, "config_run.json")
        with open(params_path, "w") as f:
            json.dump(full_params, f, indent=2)

        logger.info("--- Run %d/%d: %s ---", i, len(grid), run_id)

        # Fit
        try:
            _run_rscript(
                R_SCRIPTS["fit"],
                [
                    "--blocks_dir", blocks_dir,
                    "--connection",  design_path,
                    "--params",      params_path,
                    "--out_dir",     run_dir,
                    "--seed",        str(seed),
                ],
                label=f"fit/{run_id}",
            )
        except RGCCAFitError as e:
            logger.error("Run %s FAILED: %s", run_id, str(e)[:500])
            # Write a failure marker so the manifest is still trackable
            with open(os.path.join(run_dir, "FAILED.txt"), "w") as f:
                f.write(str(e))
            continue

        # Plots
        plot_cfg = cfg.get("plots", {})
        plot_config_path = os.path.join(run_dir, "plot_config.json")
        plot_cfg_full = {
            "n_mark": plot_cfg.get("n_mark", 10),
            "comp":   plot_cfg.get("comp", [1, 2]),
        }
        with open(plot_config_path, "w") as f:
            json.dump(plot_cfg_full, f)

        try:
            _run_rscript(
                R_SCRIPTS["plot"],
                [
                    "--blocks_dir",  blocks_dir,
                    "--connection",  design_path,
                    "--params",      params_path,
                    "--plot_config", plot_config_path,
                    "--out_dir",     plots_dir,
                    "--seed",        str(seed),
                ],
                label=f"plot/{run_id}",
            )
        except RGCCAFitError as e:
            logger.warning("Plot generation failed for %s: %s", run_id, str(e)[:300])

        run_dirs.append(run_dir)
        run_manifest_entries.append({
            "run_id":  run_id,
            "run_dir": run_dir,
            "params":  full_params,
        })

    if not run_dirs:
        raise RGCCAFitError(
            "All RGCCA runs failed. Check the error messages above. "
            "Common causes: invalid parameter combinations, R package issues, "
            "or block data problems not caught by QC."
        )

    # ------------------------------------------------------------------
    # 8. CV tuning
    # ------------------------------------------------------------------
    cv_results = None
    tuning_cfg = cfg.get("tuning", {})
    cv_cfg = tuning_cfg.get("cv", {})

    if cv_cfg.get("enabled", False):
        logger.info("Running CV tuning...")
        cv_config_path = str(tuning_dir / "cv_config.json")
        base_params_path = str(tuning_dir / "base_params.json")

        cv_payload = {
            "par_type":         cv_cfg.get("par_type", "tau"),
            "par_value":        cv_cfg.get("par_value", [0, 0.5, 1]),
            "k":                cv_cfg.get("k", 5),
            "n_run":            cv_cfg.get("n_run", 1),
            "metric":           cv_cfg.get("metric", "cor"),
            "prediction_model": cv_cfg.get("prediction_model", "lm"),
        }
        if response_idx is not None:
            cv_payload["response_idx"] = response_idx

        with open(cv_config_path, "w") as f:
            json.dump(cv_payload, f, indent=2)
        with open(base_params_path, "w") as f:
            json.dump({**base_params, **grid[0]}, f, indent=2)

        try:
            _run_rscript(
                R_SCRIPTS["cv"],
                [
                    "--blocks_dir",  blocks_dir,
                    "--connection",  design_path,
                    "--cv_params",   cv_config_path,
                    "--base_params", base_params_path,
                    "--out_dir",     str(tuning_dir),
                    "--seed",        str(seed),
                ],
                label="cv_tuning",
            )
            cv_best_path = tuning_dir / "cv_best_params.json"
            if cv_best_path.exists():
                with open(cv_best_path) as f:
                    cv_results = json.load(f)
                logger.info("CV best params: %s", cv_results)
        except RGCCAFitError as e:
            logger.warning("CV tuning failed: %s", str(e)[:500])

    # ------------------------------------------------------------------
    # 9. Permutation tuning
    # ------------------------------------------------------------------
    perm_results = None
    perm_cfg = tuning_cfg.get("permutation", {})

    if perm_cfg.get("enabled", False):
        logger.info("Running permutation tuning...")
        perm_config_path = str(tuning_dir / "perm_config.json")
        base_params_path = str(tuning_dir / "base_params_perm.json")

        perm_payload = {
            "par_type":  perm_cfg.get("par_type", "tau"),
            "par_value": perm_cfg.get("par_value", [0, 0.5, 1]),
            "n_perms":   perm_cfg.get("n_perms", 100),
        }

        with open(perm_config_path, "w") as f:
            json.dump(perm_payload, f, indent=2)
        with open(base_params_path, "w") as f:
            json.dump({**base_params, **grid[0]}, f, indent=2)

        try:
            _run_rscript(
                R_SCRIPTS["perm"],
                [
                    "--blocks_dir",  blocks_dir,
                    "--connection",  design_path,
                    "--perm_params", perm_config_path,
                    "--base_params", base_params_path,
                    "--out_dir",     str(tuning_dir),
                    "--seed",        str(seed),
                ],
                label="perm_tuning",
            )
            perm_best_path = tuning_dir / "perm_best_params.json"
            if perm_best_path.exists():
                with open(perm_best_path) as f:
                    perm_results = json.load(f)
                logger.info("Permutation best params: %s", perm_results)
        except RGCCAFitError as e:
            logger.warning("Permutation tuning failed: %s", str(e)[:500])

    # ------------------------------------------------------------------
    # 10. Rank runs
    # ------------------------------------------------------------------
    logger.info("Ranking %d completed run(s)...", len(run_dirs))
    ranking_result = rank_runs(
        run_dirs=run_dirs,
        ranking_criterion=cfg["ranking_criterion"],
        ranking_direction=cfg.get("ranking_direction", "max"),
        output_dir=str(out_root),
        cv_results=cv_results,
        perm_results=perm_results,
    )

    # ------------------------------------------------------------------
    # 11. Write global run manifest
    # ------------------------------------------------------------------
    manifest_path = out_root / "run_manifest.json"
    with open(manifest_path, "w") as f:
        json.dump(
            {
                "timestamp":         timestamp,
                "seed":              seed,
                "n_runs_attempted":  len(grid),
                "n_runs_completed":  len(run_dirs),
                "ranking_criterion": cfg["ranking_criterion"],
                "ranking_direction": cfg.get("ranking_direction", "max"),
                "runs":              run_manifest_entries,
                "cv_results":        cv_results,
                "perm_results":      perm_results,
            },
            f,
            indent=2,
            default=str,
        )

    # ------------------------------------------------------------------
    # 12. Print summary
    # ------------------------------------------------------------------
    top = ranking_result["top_run_params"]
    metrics = ranking_result["top_run_metrics"]
    print("\n" + "=" * 70)
    print("RGCCA ANALYSIS COMPLETE")
    print("=" * 70)
    print(f"Output directory : {out_root}")
    print(f"Runs completed   : {len(run_dirs)} / {len(grid)}")
    print(f"Ranking criterion: {cfg['ranking_criterion']} ({cfg.get('ranking_direction','max')})")
    print(f"\nTop run: {ranking_result['top_run_dir']}")
    print(f"  method={top.get('method')}, scheme={top.get('scheme')}, "
          f"tau={top.get('tau')}, ncomp={top.get('ncomp')}, sparsity={top.get('sparsity')}")
    for k, v in metrics.items():
        print(f"  {k} = {v:.6f}" if isinstance(v, float) else f"  {k} = {v}")
    print("=" * 70 + "\n")

    return {
        "output_dir":          str(out_root),
        "config_path":         str(config_path),
        "qc_report_path":      str(qc_path),
        "design_matrix_path":  design_path,
        "run_manifest_path":   str(manifest_path),
        "ranked_runs_path":    ranking_result["ranked_runs_path"],
        "summary_path":        ranking_result["summary_path"],
        "top_run":             ranking_result,
        "n_runs":              len(run_dirs),
        "tuning": {
            "cv_results":   cv_results,
            "perm_results": perm_results,
        },
    }


# ---------------------------------------------------------------------------
# CLI convenience
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Run RGCCA multiblock analysis from a JSON config file."
    )
    parser.add_argument("config", help="Path to JSON config file.")
    parsed = parser.parse_args()

    result = run_rgcca(parsed.config)
    print(json.dumps(result, indent=2, default=str))
