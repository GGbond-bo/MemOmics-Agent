"""Data scanner tool — scans bioinformatics data files and returns metadata."""
import json
import os
import logging

logger = logging.getLogger(__name__)

SCHEMA = {
    "name": "scan_data",
    "description": (
        "Scan a bioinformatics data file (h5ad/h5/rds/mtx/csv/10x) and return "
        "metadata: format, estimated cell count, species, tissue, annotation "
        "status, obs columns, available metadata. Use this BEFORE any analysis "
        "to understand the data."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "file_path": {
                "type": "string",
                "description": "Path to the data file (h5ad, h5, rds, mtx, csv, 10x folder)"
            }
        },
        "required": ["file_path"]
    }
}


def _scan_h5ad(path):
    """Scan .h5ad file using anndata."""
    try:
        import anndata as ad
        adata = ad.read_h5ad(path, backed='r')
        n_cells = adata.n_obs
        n_genes = adata.n_vars
        obs_cols = list(adata.obs.columns)
        # Detect species from obs columns
        species = "unknown"
        for col in obs_cols:
            col_lower = col.lower()
            if 'species' in col_lower or 'organism' in col_lower:
                vals = adata.obs[col].unique()[:3]
                species = str(vals[0]) if len(vals) > 0 else "unknown"
                break
        # Detect annotation status
        annotated = any(kw in ' '.join(obs_cols).lower() for kw in
                        ['cell_type', 'celltype', 'cluster', 'annotation', 'label', 'identity'])
        # Detect age/condition groups
        group_cols = [c for c in obs_cols if any(kw in c.lower() for kw in
                        ['age', 'condition', 'group', 'sample', 'batch', 'donor', 'stage'])]
        adata.file.close()
        return {
            "format": "h5ad",
            "n_cells": int(n_cells),
            "n_genes": int(n_genes),
            "species": species,
            "obs_columns": obs_cols,
            "annotated": annotated,
            "group_columns": group_cols,
        }
    except Exception as e:
        logger.exception("h5ad scan failed")
        return {"format": "h5ad", "error": str(e)}


def _scan_file(path):
    """Generic file scanner."""
    ext = os.path.splitext(path)[1].lower()
    size_mb = os.path.getsize(path) / (1024 * 1024)
    result = {"file_path": path, "file_size_mb": round(size_mb, 1), "extension": ext}

    if ext == '.h5ad':
        result.update(_scan_h5ad(path))
    elif ext in ('.h5', '.rds', '.rdata'):
        result["format"] = ext.lstrip('.')
        result["note"] = "Use R/Python to read this file for detailed metadata"
    elif ext in ('.csv', '.tsv'):
        result["format"] = ext.lstrip('.')
    else:
        result["format"] = "unknown"

    return result


def scan_data(file_path: str) -> str:
    """Scan data file and return JSON metadata."""
    if not os.path.exists(file_path):
        return json.dumps({"success": False, "error": f"File not found: {file_path}"}, ensure_ascii=False)

    try:
        result = _scan_file(file_path)
        result["success"] = True
        return json.dumps(result, ensure_ascii=False, indent=2)
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False)


def _register():
    try:
        from tools.registry import registry
    except ImportError:
        return  # 非 Hermes 运行时跳过注册
    registry.register(
        name="scan_data",
        toolset="memomics",
        schema=SCHEMA,
        handler=lambda args, **kw: scan_data(args.get("file_path", "")),
        emoji="🔬",
        max_result_size_chars=50_000,
    )

_register()
