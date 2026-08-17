"""
rgcca_design.py — Connection/design matrix construction for the RGCCA skill.

Supports:
  Named modes (both RGCCA-native and descriptive aliases):
    "full"  | "pair"              → 1 − I  (all off-diagonal = 1, diagonal = 0)
    "all"                         → all-ones matrix (including diagonal)
    "star"  | "response"
            | "response-centered" → zeros except response_block row/col = 1

  Explicit dict-of-dicts:
    {"blockA": {"blockB": 1, "blockC": 0}, "blockB": {"blockA": 1, "blockC": 0}, ...}
    Must be square, symmetric, contain only 0/1 values, and cover all block names.

Returns a pandas DataFrame (J × J) with block names as both index and columns.
Also writes the matrix to a CSV file for the R scripts to consume.
"""

from __future__ import annotations

import logging
from typing import Dict, List, Optional, Union

import numpy as np
import pandas as pd

from rgcca_qc import RGCCAConfigError

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Alias maps
# ---------------------------------------------------------------------------

_NAMED_MODES = {
    # descriptive alias → canonical internal name
    "full":             "pair",
    "pair":             "pair",
    "all":              "all",
    "star":             "response",
    "response":         "response",
    "response-centered":"response",
}

VALID_NAMED_MODES = sorted(_NAMED_MODES.keys())


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def build_connection_matrix(
    block_names: List[str],
    design: Union[str, dict],
    response_block: Optional[str] = None,
) -> pd.DataFrame:
    """
    Build the J×J connection matrix.

    Parameters
    ----------
    block_names : list of str
        Ordered list of block names (must match the blocks dict keys).
    design : str or dict
        Named mode string or explicit dict-of-dicts.
    response_block : str or None
        Required when design is "star" / "response" / "response-centered".

    Returns
    -------
    pd.DataFrame
        J×J symmetric matrix with block names as index and columns.
        Values are 0.0 or 1.0.
    """
    J = len(block_names)

    if isinstance(design, str):
        mode_key = design.strip().lower()
        if mode_key not in _NAMED_MODES:
            raise RGCCAConfigError(
                f"Unknown design mode '{design}'. "
                f"Valid named modes: {VALID_NAMED_MODES}. "
                "Alternatively, supply an explicit dict-of-dicts."
            )
        canonical = _NAMED_MODES[mode_key]
        matrix = _build_named(block_names, canonical, response_block)

    elif isinstance(design, dict):
        matrix = _build_explicit(block_names, design)

    else:
        raise RGCCAConfigError(
            f"'design' must be a string (named mode) or a dict-of-dicts. "
            f"Got: {type(design).__name__}"
        )

    _validate_matrix(matrix, block_names)
    logger.info("Connection matrix built (%d×%d):\n%s", J, J, matrix.to_string())
    return matrix


def matrix_to_csv(matrix: pd.DataFrame, path: str) -> None:
    """Write the connection matrix to a CSV file (with row/column names)."""
    matrix.to_csv(path)
    logger.info("Connection matrix written to '%s'", path)


# ---------------------------------------------------------------------------
# Internal builders
# ---------------------------------------------------------------------------

def _build_named(
    block_names: List[str],
    canonical: str,
    response_block: Optional[str],
) -> pd.DataFrame:
    J = len(block_names)

    if canonical == "pair":
        # All off-diagonal = 1, diagonal = 0  (standard "full" graph)
        mat = 1.0 - np.eye(J)

    elif canonical == "all":
        # All connections including self-loops
        mat = np.ones((J, J))

    elif canonical == "response":
        if response_block is None:
            raise RGCCAConfigError(
                "Design mode 'star' / 'response' / 'response-centered' requires "
                "'response_block' to be set in the config."
            )
        if response_block not in block_names:
            raise RGCCAConfigError(
                f"response_block '{response_block}' is not among the block names: "
                f"{block_names}"
            )
        mat = np.zeros((J, J))
        resp_idx = block_names.index(response_block)
        mat[resp_idx, :] = 1.0
        mat[:, resp_idx] = 1.0
        mat[resp_idx, resp_idx] = 0.0  # no self-loop on response

    else:
        raise RGCCAConfigError(f"Internal error: unknown canonical mode '{canonical}'.")

    return pd.DataFrame(mat, index=block_names, columns=block_names)


def _build_explicit(
    block_names: List[str],
    design: dict,
) -> pd.DataFrame:
    """
    Build connection matrix from a dict-of-dicts.
    Missing pairs default to 0. Extra keys (not in block_names) raise an error.
    """
    J = len(block_names)
    name_set = set(block_names)

    # Check for unknown block names in the design dict
    unknown_outer = set(design.keys()) - name_set
    if unknown_outer:
        raise RGCCAConfigError(
            f"Explicit design matrix contains unknown block name(s) as outer keys: "
            f"{sorted(unknown_outer)}. Known blocks: {block_names}"
        )
    for outer_key, inner in design.items():
        if not isinstance(inner, dict):
            raise RGCCAConfigError(
                f"Explicit design: value for block '{outer_key}' must be a dict, "
                f"got {type(inner).__name__}."
            )
        unknown_inner = set(inner.keys()) - name_set
        if unknown_inner:
            raise RGCCAConfigError(
                f"Explicit design matrix: block '{outer_key}' references unknown "
                f"block name(s): {sorted(unknown_inner)}. Known blocks: {block_names}"
            )

    # Build matrix (default 0)
    mat = np.zeros((J, J))
    for i, row_name in enumerate(block_names):
        for j, col_name in enumerate(block_names):
            val = design.get(row_name, {}).get(col_name, 0)
            if val not in (0, 1, 0.0, 1.0):
                raise RGCCAConfigError(
                    f"Explicit design matrix: value at [{row_name}][{col_name}] = {val}. "
                    "Only 0 and 1 are allowed."
                )
            mat[i, j] = float(val)

    return pd.DataFrame(mat, index=block_names, columns=block_names)


def _validate_matrix(matrix: pd.DataFrame, block_names: List[str]) -> None:
    """Validate the final connection matrix: shape, symmetry, diagonal, values."""
    J = len(block_names)

    # Shape
    if matrix.shape != (J, J):
        raise RGCCAConfigError(
            f"Connection matrix shape {matrix.shape} does not match "
            f"number of blocks ({J})."
        )

    # Values
    vals = matrix.values
    if not np.all(np.isin(vals, [0.0, 1.0])):
        bad = np.unique(vals[~np.isin(vals, [0.0, 1.0])])
        raise RGCCAConfigError(
            f"Connection matrix contains non-0/1 values: {bad}"
        )

    # Symmetry
    if not np.allclose(vals, vals.T):
        raise RGCCAConfigError(
            "Connection matrix is not symmetric. "
            "RGCCA requires a symmetric connection matrix."
        )

    # Warn if diagonal is non-zero (unusual but not forbidden for "all" mode)
    diag_vals = np.diag(vals)
    if np.any(diag_vals != 0):
        logger.warning(
            "Connection matrix has non-zero diagonal entries %s. "
            "This is only appropriate for design='all'.",
            np.where(diag_vals != 0)[0].tolist(),
        )
