"""Data scanner tool — scans bioinformatics data files and returns metadata.

批 C（2026-08-15）：元数据落库 — 每次扫描后把结果持久化到
results/<sid>/datasets/<name>.meta.json 并更新 index.json（数据清单），
含 sha256/mtime → 支撑数据溯源与版本追踪。
"""
import hashlib
import json
import os
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

_HASH_MAX_BYTES = 500 * 1024 * 1024  # 超过 500MB 跳过全文件哈希
_ROWS_MAX_BYTES = 50 * 1024 * 1024   # 超过 50MB 不逐行计数

SCHEMA = {
    "name": "scan_data",
    "description": (
        "Scan a bioinformatics data file (h5ad/h5/rds/mtx/csv/10x) and return "
        "metadata: format, estimated cell count, species, tissue, annotation "
        "status, obs columns, available metadata. Use this BEFORE any analysis "
        "to understand the data. 每次扫描都会把元数据落库（sha256+维度+时间戳），"
        "action=inventory 可列出全部已登记数据。"
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "file_path": {
                "type": "string",
                "description": "Path to the data file (h5ad, h5, rds, mtx, csv, 10x folder)"
            },
            "action": {
                "type": "string",
                "enum": ["scan", "inventory"],
                "description": "scan=扫描文件(默认); inventory=列出已登记的数据清单"
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
    size_bytes = os.path.getsize(path)
    size_mb = size_bytes / (1024 * 1024)
    result = {"file_path": path, "file_size_mb": round(size_mb, 1), "extension": ext}

    if ext == '.h5ad':
        result.update(_scan_h5ad(path))
    elif ext in ('.h5', '.rds', '.rdata'):
        result["format"] = ext.lstrip('.')
        result["note"] = "Use R/Python to read this file for detailed metadata"
    elif ext in ('.csv', '.tsv', '.txt'):
        result["format"] = ext.lstrip('.')
        _scan_table_dims(path, size_bytes, result)
    else:
        result["format"] = "unknown"

    # 溯源字段：sha256 + 修改时间
    result["mtime"] = datetime.fromtimestamp(os.path.getmtime(path)).strftime("%Y-%m-%d %H:%M:%S")
    if size_bytes <= _HASH_MAX_BYTES:
        result["sha256"] = _sha256_of(path)
    else:
        result["sha256"] = "skipped (file > 500MB)"
    return result


def _sha256_of(path):
    h = hashlib.sha256()
    try:
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(1024 * 1024), b""):
                h.update(chunk)
    except Exception:
        return ""
    return h.hexdigest()


def _scan_table_dims(path, size_bytes, result):
    """csv/tsv: 读取表头与行列数（大文件跳行计数）。"""
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            header = f.readline().rstrip("\n")
            sep = "\t" if path.lower().endswith(".tsv") else ","
            result["columns"] = header.split(sep)[:50]
            if size_bytes <= _ROWS_MAX_BYTES:
                n_rows = sum(1 for _ in f)
                result["n_rows"] = n_rows
            else:
                result["n_rows"] = "not counted (file > 50MB)"
    except Exception as e:
        result["note"] = f"table dims read failed: {str(e)[:120]}"


def _persist_metadata(file_path, result):
    """元数据落库：results/<sid>/datasets/<name>.meta.json + index.json 清单。"""
    try:
        from memomics.bio_tools.debate_analysis import get_session_results_dir
        rd = get_session_results_dir()
        base_dir = os.path.join(rd, "datasets") if rd else ""
        if not base_dir:
            hh = os.environ.get("HERMES_HOME")
            base_dir = os.path.join(hh, "datasets") if hh else ""
        if not base_dir:
            return {"registered": False, "error": "no results dir"}
        os.makedirs(base_dir, exist_ok=True)
        stem = os.path.splitext(os.path.basename(file_path))[0]
        meta = dict(result)
        meta["scanned_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        meta_file = os.path.join(base_dir, f"{stem}.meta.json")
        with open(meta_file, "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)
        # index.json 数据清单
        index_file = os.path.join(base_dir, "index.json")
        index = []
        if os.path.isfile(index_file):
            try:
                index = json.load(open(index_file, encoding="utf-8"))
            except Exception:
                index = []
        # 按 sha256 或路径去重
        if not any(e.get("sha256") and e["sha256"] == meta.get("sha256")
                   or e.get("file_path") == meta.get("file_path") for e in index):
            index.append({k: meta.get(k) for k in
                          ("file_path", "format", "file_size_mb", "sha256", "mtime",
                           "n_cells", "n_genes", "species", "scanned_at")})
            with open(index_file, "w", encoding="utf-8") as f:
                json.dump(index, f, ensure_ascii=False, indent=2)
        return {"registered": True, "datasets_dir": base_dir,
                "meta_file": meta_file, "index_file": index_file,
                "inventory_count": len(index)}
    except Exception as e:
        logger.warning(f"metadata persist failed: {e}")
        return {"registered": False, "error": str(e)[:200]}


def _inventory():
    """列出已登记的数据清单。"""
    out = []
    try:
        from memomics.bio_tools.debate_analysis import get_session_results_dir
        rd = get_session_results_dir()
        candidates = [os.path.join(rd, "datasets")] if rd else []
        hh = os.environ.get("HERMES_HOME")
        if hh:
            candidates.append(os.path.join(hh, "datasets"))
        for d in candidates:
            if d and os.path.isdir(d):
                idx = os.path.join(d, "index.json")
                if os.path.isfile(idx):
                    try:
                        out.append({"datasets_dir": d, "count": len(json.load(open(idx, encoding="utf-8")))})
                    except Exception:
                        pass
    except Exception:
        pass
    return out


def scan_data(file_path: str = "", action: str = "scan") -> str:
    """Scan data file and return JSON metadata. scan 会落库，inventory 列出清单。"""
    if action == "inventory":
        return json.dumps({"success": True, "inventory": _inventory()}, ensure_ascii=False, indent=2)
    if not os.path.exists(file_path):
        return json.dumps({"success": False, "error": f"File not found: {file_path}"}, ensure_ascii=False)

    try:
        result = _scan_file(file_path)
        result["success"] = True
        result["persisted"] = _persist_metadata(file_path, result)
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
        handler=lambda args, **kw: scan_data(args.get("file_path", ""), args.get("action", "scan")),
        emoji="🔬",
        max_result_size_chars=50_000,
    )

_register()
