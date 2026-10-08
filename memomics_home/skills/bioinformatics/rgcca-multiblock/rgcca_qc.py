"""
rgcca_qc.py — Block validation, alignment, and QC reporting for the RGCCA skill.

Checks performed (in order):
  1. Each block is a pandas DataFrame with a numeric dtype (except the sample-ID column).
  2. No duplicated sample IDs within any block.
  3. Sample IDs are consistent across all blocks (set intersection reported).
  4. Missing value counts and fractions per block.
  5. Constant columns (zero variance) per block.
  6. Non-numeric feature columns per block.

Behaviour controlled by config:
  allow_constant_columns: false (default) → raise RGCCAValidationError listing offenders.
  allow_constant_columns: true            → remove constant columns and warn.

Never silently drops samples. Sample alignment is always by intersection + reorder;
if any block is missing samples present in others, a RGCCAValidationError is raised
unless the caller explicitly passes allow_sample_mismatch=True (not exposed in config —
reserved for future use).
"""

from __future__ import annotations

import io
import logging
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Custom exceptions
# ---------------------------------------------------------------------------

class RGCCAValidationError(Exception):
    """Raised when a block fails QC and execution cannot continue."""


class RGCCAConfigError(Exception):
    """Raised when the configuration is invalid or internally inconsistent."""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def load_blocks(
    block_paths: Dict[str, str],
    sample_id_col: Optional[str],
) -> Dict[str, pd.DataFrame]:
    """
    Read each block CSV into a DataFrame indexed by sample ID.

    Parameters
    ----------
    block_paths : dict
        {block_name: path_to_csv}
    sample_id_col : str or None
        Column name holding sample IDs. If None, the row index is used as-is.

    Returns
    -------
    dict of {block_name: DataFrame}
        Each DataFrame is indexed by sample ID; all columns are feature columns.
    """
    blocks: Dict[str, pd.DataFrame] = {}
    for name, path in block_paths.items():
        try:
            df = pd.read_csv(path)
        except Exception as exc:
            raise RGCCAValidationError(
                f"Block '{name}': cannot read CSV at '{path}': {exc}"
            ) from exc

        if sample_id_col is not None:
            if sample_id_col not in df.columns:
                raise RGCCAValidationError(
                    f"Block '{name}': sample_id_col '{sample_id_col}' not found. "
                    f"Available columns: {list(df.columns)}"
                )
            df = df.set_index(sample_id_col)
        else:
            df.index = df.index.astype(str)

        df.index.name = "sample_id"
        blocks[name] = df
        logger.info("Loaded block '%s': %d samples × %d features", name, *df.shape)

    return blocks


def run_qc(
    blocks: Dict[str, pd.DataFrame],
    allow_constant_columns: bool = False,
) -> Tuple[Dict[str, pd.DataFrame], str]:
    """
    Validate and align all blocks. Returns cleaned blocks and a QC report string.

    Parameters
    ----------
    blocks : dict
        {block_name: DataFrame} as returned by load_blocks().
    allow_constant_columns : bool
        If False (default), raise on constant columns.
        If True, remove them with a warning.

    Returns
    -------
    (aligned_blocks, qc_report_text)
    """
    report = io.StringIO()
    report.write("=" * 70 + "\n")
    report.write("RGCCA QC REPORT\n")
    report.write("=" * 70 + "\n\n")

    # ------------------------------------------------------------------
    # 1. Non-numeric columns
    # ------------------------------------------------------------------
    report.write("--- Non-numeric feature check ---\n")
    non_numeric_errors: List[str] = []
    for name, df in blocks.items():
        bad_cols = [c for c in df.columns if not pd.api.types.is_numeric_dtype(df[c])]
        if bad_cols:
            msg = (
                f"Block '{name}' contains {len(bad_cols)} non-numeric column(s): "
                f"{bad_cols}. Convert or remove them before running RGCCA."
            )
            report.write(f"  ERROR: {msg}\n")
            non_numeric_errors.append(msg)
        else:
            report.write(f"  Block '{name}': all {df.shape[1]} columns numeric. OK\n")

    if non_numeric_errors:
        raise RGCCAValidationError(
            "Non-numeric columns detected:\n" + "\n".join(non_numeric_errors)
        )

    # ------------------------------------------------------------------
    # 2. Duplicated sample IDs within each block
    # ------------------------------------------------------------------
    report.write("\n--- Duplicated sample ID check ---\n")
    dup_errors: List[str] = []
    for name, df in blocks.items():
        dups = df.index[df.index.duplicated()].tolist()
        if dups:
            msg = (
                f"Block '{name}' has {len(dups)} duplicated sample ID(s): {dups[:20]}"
                + (" ..." if len(dups) > 20 else "")
                + ". Remove or deduplicate before running RGCCA."
            )
            report.write(f"  ERROR: {msg}\n")
            dup_errors.append(msg)
        else:
            report.write(f"  Block '{name}': no duplicated IDs. OK\n")

    if dup_errors:
        raise RGCCAValidationError(
            "Duplicated sample IDs detected:\n" + "\n".join(dup_errors)
        )

    # ------------------------------------------------------------------
    # 3. Sample ID alignment across blocks
    # ------------------------------------------------------------------
    report.write("\n--- Sample ID alignment ---\n")
    block_names = list(blocks.keys())
    id_sets = {name: set(df.index) for name, df in blocks.items()}
    common_ids = set.intersection(*id_sets.values())

    for name, ids in id_sets.items():
        report.write(f"  Block '{name}': {len(ids)} samples\n")

    report.write(f"  Common samples across all blocks: {len(common_ids)}\n")

    missing_per_block: Dict[str, List[str]] = {}
    for name, ids in id_sets.items():
        missing = sorted(common_ids - ids)  # samples in common but not in this block
        extra = sorted(ids - common_ids)    # samples in this block but not in common
        if extra:
            missing_per_block[name] = extra
            report.write(
                f"  Block '{name}': {len(extra)} sample(s) not present in all other "
                f"blocks: {extra[:10]}" + (" ..." if len(extra) > 10 else "") + "\n"
            )

    if len(common_ids) == 0:
        raise RGCCAValidationError(
            "No common sample IDs found across all blocks. "
            "Check that sample ID formats match (e.g. 'S01' vs 'S1' vs '1')."
        )

    # Samples present in some but not all blocks → error
    all_ids = set.union(*id_sets.values())
    partial_ids = all_ids - common_ids
    if partial_ids:
        detail_lines = []
        for pid in sorted(partial_ids)[:30]:
            present_in = [n for n, ids in id_sets.items() if pid in ids]
            detail_lines.append(f"    '{pid}' present in: {present_in}")
        raise RGCCAValidationError(
            f"{len(partial_ids)} sample ID(s) are present in some blocks but not all. "
            "All blocks must share exactly the same sample IDs.\n"
            "Mismatched IDs (first 30):\n" + "\n".join(detail_lines)
            + "\nCorrectve action: filter each block to the common sample set before "
            "calling RGCCA, or set allow_sample_mismatch=True (not yet supported)."
        )

    # Align order: sort common IDs for reproducibility
    aligned_ids = sorted(common_ids)
    report.write(f"  Aligned sample order: {len(aligned_ids)} samples (sorted).\n")

    aligned_blocks: Dict[str, pd.DataFrame] = {
        name: df.loc[aligned_ids].copy() for name, df in blocks.items()
    }

    # ------------------------------------------------------------------
    # 4. Missingness
    # ------------------------------------------------------------------
    report.write("\n--- Missingness report ---\n")
    for name, df in aligned_blocks.items():
        n_missing = df.isnull().sum().sum()
        frac = n_missing / df.size
        report.write(
            f"  Block '{name}': {n_missing} missing values "
            f"({frac:.2%} of {df.size} cells)\n"
        )
        if n_missing > 0:
            per_col = df.isnull().sum()
            top_cols = per_col[per_col > 0].sort_values(ascending=False).head(10)
            report.write(f"    Top missing columns: {top_cols.to_dict()}\n")

    # ------------------------------------------------------------------
    # 5. Constant columns (zero variance)
    # ------------------------------------------------------------------
    report.write("\n--- Constant column check ---\n")
    constant_errors: List[str] = []
    for name, df in aligned_blocks.items():
        const_cols = [c for c in df.columns if df[c].nunique(dropna=True) <= 1]
        if const_cols:
            msg = (
                f"Block '{name}' has {len(const_cols)} constant column(s): "
                f"{const_cols[:30]}" + (" ..." if len(const_cols) > 30 else "")
            )
            if allow_constant_columns:
                logger.warning("%s — removing them.", msg)
                report.write(f"  WARNING (auto-removed): {msg}\n")
                aligned_blocks[name] = df.drop(columns=const_cols)
            else:
                report.write(f"  ERROR: {msg}\n")
                constant_errors.append(
                    msg + "\nCorrective action: remove these columns or set "
                    "allow_constant_columns: true in the config."
                )
        else:
            report.write(f"  Block '{name}': no constant columns. OK\n")

    if constant_errors:
        raise RGCCAValidationError(
            "Constant columns detected (allow_constant_columns=false):\n"
            + "\n".join(constant_errors)
        )

    # ------------------------------------------------------------------
    # 6. Final summary
    # ------------------------------------------------------------------
    report.write("\n--- Final block dimensions (after QC) ---\n")
    for name, df in aligned_blocks.items():
        report.write(f"  Block '{name}': {df.shape[0]} samples × {df.shape[1]} features\n")

    report.write("\nQC PASSED\n")
    report.write("=" * 70 + "\n")

    return aligned_blocks, report.getvalue()


def verify_alignment(blocks: Dict[str, pd.DataFrame]) -> None:
    """
    Final sanity check: confirm all blocks have identical index in identical order.
    Raises RGCCAValidationError if not. Called just before writing block CSVs to disk.
    """
    names = list(blocks.keys())
    ref_index = blocks[names[0]].index
    for name in names[1:]:
        if not blocks[name].index.equals(ref_index):
            raise RGCCAValidationError(
                f"Block '{name}' index does not match block '{names[0]}' after alignment. "
                "This is an internal error — please report it."
            )
