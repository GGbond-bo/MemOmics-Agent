"""MemOmics bioinformatics tools — registered with Hermes tool registry.

This module is auto-discovered by discover_builtin_tools() because it lives
in the tools/ directory and calls registry.register() at module level.

⚠️ 双注册说明：
  Hermes agent 启动时，先执行 discover_builtin_tools()（加载本文件），
  再执行 from memomics import bio_tools（加载 memomics/bio_tools/__init__.py）。
  bio_tools/ 下的子模块也会注册同名工具，且后注册者覆盖先注册者。

  因此以下 6 个工具在本文件中的注册实际会被 bio_tools/ 版本覆盖：
    - scan_data       → 最终生效: bio_tools/data_scanner.py
    - search_knowledge → 最终生效: bio_tools/kb_search.py（v3 增强版）
    - guide_analysis   → 最终生效: bio_tools/module_selector.py
    - check_env        → 最终生效: bio_tools/env_check.py
    - rail_review      → 最终生效: bio_tools/rail_review.py
    - skill_evolution  → 最终生效: bio_tools/skill_evolution.py

  以下 3 个工具是本文件独有的，不会被覆盖：
    - todo_manage
    - memomics_pipeline
    - update_results_dir
"""
import sys
import os
import json
import logging
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)

from tools.registry import registry

# ============================================================================
# scan_data
# ============================================================================
SCAN_DATA_SCHEMA = {
    "name": "scan_data",
    "description": (
        "Scan a bioinformatics data file (h5ad/h5/rds/mtx/csv/10x) and return "
        "metadata: format, estimated cell count, species, tissue, annotation "
        "status, obs columns, available metadata. Use this BEFORE any analysis."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "file_path": {"type": "string", "description": "Path to the data file (h5ad, h5, rds, mtx, csv, 10x folder)"}
        },
        "required": ["file_path"]
    }
}


def _scan_h5ad(path):
    """Scan .h5ad using h5py directly (avoids anndata version conflicts)."""
    try:
        import h5py
        import numpy as np

        with h5py.File(path, 'r') as f:
            # n_obs / n_vars from shape attributes
            n_cells = 0
            n_genes = 0
            if 'X' in f:
                X = f['X']
                if hasattr(X, 'shape'):
                    shape = X.shape
                    # anndata convention: (n_obs, n_vars)
                    n_cells = shape[0] if len(shape) >= 1 else 0
                    n_genes = shape[1] if len(shape) >= 2 else 0
                elif 'data' in X and hasattr(X['data'], 'shape'):
                    # CSR/CSC sparse: try to get dimensions
                    if 'shape' in X.attrs:
                        n_cells, n_genes = X.attrs['shape'][:2]
                    else:
                        # Try indirect indices
                        pass

            # obs columns
            obs_cols = []
            if 'obs' in f:
                obs_grp = f['obs']
                obs_cols = list(obs_grp.keys())
                # Also check for column-index
                if '__categories' in f and 'obs' in f['__categories']:
                    pass  # older format

            # Also try reading from obs index
            if not obs_cols and 'obs' in f and '_index' in f['obs']:
                obs_cols = ['index']

            # Detect species
            species = "unknown"
            for col in obs_cols:
                col_lower = col.lower()
                if 'species' in col_lower or 'organism' in col_lower:
                    try:
                        vals = f['obs'][col][:]
                        if len(vals) > 0:
                            # Decode bytes to string if needed
                            v = vals[0]
                            species = v.decode() if isinstance(v, bytes) else str(v)
                    except Exception:
                        pass
                    break

            # Detect annotation status
            annotated = any(kw in ' '.join(obs_cols).lower() for kw in
                            ['cell_type', 'celltype', 'cluster', 'annotation', 'label', 'identity'])

            # Detect group columns
            group_cols = [c for c in obs_cols if any(kw in c.lower() for kw in
                            ['age', 'condition', 'group', 'sample', 'batch', 'donor', 'stage'])]

        return {"format": "h5ad", "n_cells": int(n_cells), "n_genes": int(n_genes),
                "species": species, "obs_columns": obs_cols,
                "annotated": annotated, "group_columns": group_cols}
    except Exception as e:
        logger.exception("h5ad scan failed")
        return {"format": "h5ad", "error": str(e)}


def _scan_hardware():
    """扫描当前机器硬件配置：CPU/内存/GPU/磁盘"""
    import shutil
    hw = {"cpu_cores": os.cpu_count()}
    # 内存
    try:
        import psutil
        vm = psutil.virtual_memory()
        hw["memory_gb"] = round(vm.total / 1e9, 1)
        hw["memory_available_gb"] = round(vm.available / 1e9, 1)
        du = psutil.disk_usage(os.path.dirname(os.path.abspath(__file__)))
        hw["disk_free_gb"] = round(du.free / 1e9, 1)
    except ImportError:
        # Windows fallback
        try:
            import ctypes
            class MEMORYSTATUSEX(ctypes.Structure):
                _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                            ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                            ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                            ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                            ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]
            stat = MEMORYSTATUSEX()
            stat.dwLength = ctypes.sizeof(stat)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat))
            hw["memory_gb"] = round(stat.ullTotalPhys / 1e9, 1)
            hw["memory_available_gb"] = round(stat.ullAvailPhys / 1e9, 1)
        except Exception:
            hw["memory_gb"] = None
            hw["memory_available_gb"] = None
    # GPU（NVIDIA）
    gpus = []
    try:
        import subprocess
        out = subprocess.run(["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"],
                             capture_output=True, text=True, timeout=5)
        if out.returncode == 0:
            for line in out.stdout.strip().split("\n"):
                parts = [p.strip() for p in line.split(",")]
                if len(parts) >= 2:
                    gpus.append({"name": parts[0], "vram_mb": int(parts[1])})
    except Exception:
        pass
    hw["gpus"] = gpus
    return hw


def scan_data(file_path):
    if not os.path.exists(file_path):
        return json.dumps({"success": False, "error": f"File not found: {file_path}"}, ensure_ascii=False)
    ext = os.path.splitext(file_path)[1].lower()
    size_mb = os.path.getsize(file_path) / (1024 * 1024)
    result = {"file_path": file_path, "file_size_mb": round(size_mb, 1), "extension": ext}
    if ext == '.h5ad':
        result.update(_scan_h5ad(file_path))
    elif ext in ('.h5', '.rds', '.rdata'):
        result["format"] = ext.lstrip('.')
        result["note"] = "Use R/Python to read for detailed metadata"
    else:
        result["format"] = "unknown"
    # 硬件扫描
    result["hardware"] = _scan_hardware()
    result["success"] = True
    return json.dumps(result, ensure_ascii=False, indent=2)


registry.register(
    name="scan_data", toolset="memomics", schema=SCAN_DATA_SCHEMA,
    handler=lambda args, **kw: scan_data(args.get("file_path", "")),
    emoji="🔬", max_result_size_chars=50_000,
)

# ============================================================================
# search_knowledge — 委托给 kb_search.py v3（统一版本，避免两套逻辑不同步）
# ============================================================================
# 注意：旧版 SYNONYMS + _expand_query + search_knowledge 已替换为委托调用，
# 统一使用 memomics.bio_tools.kb_search 中的 v3 实现。
# v3 增强：动态路径检测、词边界匹配、文件缓存、direction 参数、扩展同义词表。
# 此处注册会被 bio_tools/kb_search.py 的后注册覆盖，但逻辑一致。

SEARCH_KNOWLEDGE_SCHEMA = {
    "name": "search_knowledge",
    "description": (
        "Search the MemOmics knowledge base for bioinformatics analysis "
        "templates, QC parameters, method recommendations, and biological knowledge. "
        "ALWAYS call this BEFORE writing any analysis code to get the correct "
        "parameters and templates. "
        "Pass species, tissue, and direction for targeted search. "
        "支持中英文语义匹配（如 '人' → 'human', '智人', 'Homo sapiens')."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Search query (e.g. 'QC parameters', 'clustering resolution', 'CellChat')"},
            "species": {"type": "string", "description": "Species (e.g. human, mouse, Homo sapiens, 人)"},
            "tissue": {"type": "string", "description": "Tissue (e.g. skeletal_muscle, brain, heart, 骨骼肌)"},
            "direction": {"type": "string", "description": "Research direction (e.g. aging, ad, development, 衰老)"}
        },
        "required": ["query"]
    }
}


def _search_knowledge_handler(args, **kw):
    """委托给 kb_search.py v3 的统一实现。"""
    try:
        from memomics.bio_tools.kb_search import search_knowledge
        return search_knowledge(
            args.get("query", ""),
            args.get("species", ""),
            args.get("tissue", ""),
            args.get("direction", "")
        )
    except ImportError:
        # kb_search.py 不可用时回退到极简实现
        _memomics_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        kb_path = Path(os.path.join(_memomics_dir, "memomics", "knowledge_base"))
        if not kb_path.exists():
            return json.dumps({"query": args.get("query", ""), "total": 0, "results": [],
                               "error": "知识库目录未找到"}, ensure_ascii=False)
        query_lower = args.get("query", "").lower()
        results = []
        for root, dirs, files in os.walk(kb_path):
            for fname in files:
                if not fname.endswith(('.yaml', '.yml', '.json', '.md')):
                    continue
                fpath = Path(root) / fname
                try:
                    content = fpath.read_text(encoding='utf-8', errors='ignore')
                    if query_lower in content.lower():
                        results.append({"file": str(fpath.relative_to(kb_path)), "score": 1,
                                        "matched_terms": [query_lower], "snippet": content[:500]})
                except Exception:
                    continue
        results.sort(key=lambda x: x["score"], reverse=True)
        return json.dumps({"query": args.get("query", ""), "total": len(results),
                           "results": results[:10]}, ensure_ascii=False, indent=2)


registry.register(
    name="search_knowledge", toolset="memomics", schema=SEARCH_KNOWLEDGE_SCHEMA,
    handler=_search_knowledge_handler,
    emoji="📚", max_result_size_chars=50_000,
)

# ============================================================================
# guide_analysis + MODULES
# ============================================================================
MODULES = {
    "01": {"name": "深度去污染", "icon": "🧹",
           "desc": "CellBender/SoupX/DoubletFinder — 探索性分析不建议",
           "substeps": [
               {"id": "cellbender", "name": "CellBender 去除环境RNA", "skill": "cellbender-remove-background"},
               {"id": "soupx", "name": "SoupX 去污染", "skill": "soupx-decontamination"},
               {"id": "doublet", "name": "DoubletFinder 去双胞", "skill": "doubletfinder"},
           ]},
    "02": {"name": "基础分析", "icon": "📊",
           "desc": "QC → 标准化 → 批次校正 → 降维 → 聚类 → 注释 → Markers",
           "substeps": [
               {"id": "qc", "name": "质控 QC", "skill": "scrna-clustering"},
               {"id": "normalize", "name": "标准化 (SCTransform)", "skill": "scrna-clustering"},
               {"id": "harmony", "name": "批次校正 (Harmony)", "skill": "create_harmony_embeddings_scRNA"},
               {"id": "dimred", "name": "降维 (PCA+UMAP)", "skill": "scrna-clustering"},
               {"id": "cluster", "name": "聚类 (Leiden)", "skill": "scrna-clustering"},
               {"id": "annotate", "name": "细胞注释 (SingleR+markers)", "skill": "annotate_celltype_scRNA"},
               {"id": "markers", "name": "FindAllMarkers", "skill": "deg-analysis"},
           ]},
    "03": {"name": "高级分析", "icon": "🔬",
           "desc": "DEG+富集 / CellChat / 轨迹 / SCENIC — 基础分析完成后推荐",
           "substeps": [
               {"id": "deg", "name": "差异表达+富集 (DEG+GSEA)", "skill": "deg-analysis"},
               {"id": "cellchat", "name": "细胞通讯 (CellChat v2)", "skill": "cellchat-v2"},
               {"id": "trajectory", "name": "轨迹推断 (Monocle3)", "skill": "trajectory-analysis"},
               {"id": "scenic", "name": "SCENIC调控网络", "skill": "grn-pyscenic"},
           ]},
    "04": {"name": "个性化分析", "icon": "🎯",
           "desc": "方向特异分析（衰老/发育/肿瘤/纤维化/运动/比例变化）",
           "substeps": [
               {"id": "custom", "name": "个性化分析（根据研究方向定制）", "skill": "custom-analysis"},
           ]},
}

GUIDE_ANALYSIS_SCHEMA = {
    "name": "guide_analysis",
    "description": "Guide user through selecting analysis modules. Returns modules and combos. Call after scan_data.",
    "parameters": {
        "type": "object",
        "properties": {
            "data_stage": {"type": "string", "enum": ["raw", "annotated"]},
            "redo": {"type": "boolean", "default": False}
        },
        "required": ["data_stage"]
    }
}


def guide_analysis(data_stage="raw", redo=False):
    options = [
        {"id": "combo:quick", "label": "⚡ 快速组合 (基础分析)", "description": "02 基础分析"},
        {"id": "combo:standard", "label": "🔍 标准组合 (基础+高级)", "description": "02 基础 + 03 高级"},
    ]
    for mid, minfo in MODULES.items():
        options.append({"id": f"module:{mid}", "label": f"{minfo['icon']} {minfo['name']}", "description": minfo['desc']})
    options.append({"id": "custom", "label": "✏️ 自定义输入", "description": "输入你想做的分析"})
    return json.dumps({"data_stage": data_stage, "redo": redo, "modules": MODULES, "options": options, "message": "请选择要执行的分析模块："}, ensure_ascii=False, indent=2)


registry.register(
    name="guide_analysis", toolset="memomics", schema=GUIDE_ANALYSIS_SCHEMA,
    handler=lambda args, **kw: guide_analysis(args.get("data_stage", "raw"), args.get("redo", False)),
    emoji="📋", max_result_size_chars=20_000,
)

# ============================================================================
# check_env
# ============================================================================
CHECK_ENV_SCHEMA = {
    "name": "check_env",
    "description": "Check R/Python bioinformatics package availability and auto-install missing. Also detects system info (GPU, CPU, memory, disk). Call BEFORE running analysis code.",
    "parameters": {
        "type": "object",
        "properties": {
            "packages": {"type": "array", "items": {"type": "string"}},
            "language": {"type": "string", "enum": ["R", "Python", "both"], "default": "both"},
            "auto_install": {"type": "boolean", "default": True}
        },
        "required": ["packages"]
    }
}

R_PACKAGES_BIO = {
    "Seurat", "SeuratObject", "CellChat", "monocle3", "SCENIC",
    "SoupX", "DoubletFinder", "harmony", "SingleR", "celldex",
    "clusterProfiler", "org.Hs.eg.db", "org.Mm.eg.db", "ComplexHeatmap",
    "ggplot2", "dplyr", "tidyr", "patchwork", "BiocManager", "remotes",
    "scDblFinder", "scran", "scater", "batchelor", "glmGamPoi",
    "enrichplot", "DOSE", "ReactomePA",
}

PYTHON_PACKAGES_BIO = {
    "scanpy", "anndata", "scvi-tools", "scvelo", "cellrank", "pyscenic",
    "squidpy", "scikit-learn", "pandas", "numpy", "matplotlib", "seaborn",
    "plotly", "leidenalg", "louvain", "umap-learn", "statsmodels",
}


def _check_r_packages(packages):
    pkg_str = ", ".join(f'"{p}"' for p in packages)
    r_code = f'pkgs <- c({pkg_str})\nfor (p in pkgs) cat(p, ":", if(requireNamespace(p, quietly=TRUE)) "OK" else "MISSING", "\\n")\n'
    try:
        result = subprocess.run(["Rscript", "-e", r_code], capture_output=True, text=True, timeout=60, encoding="utf-8", errors="replace")
        status = {}
        for line in result.stdout.strip().split("\n"):
            if ":" in line:
                parts = line.strip().split(":")
                if len(parts) == 2:
                    status[parts[0].strip().strip('"')] = parts[1].strip() == "OK"
        return status
    except Exception:
        return {p: False for p in packages}


def _install_r_package(pkg):
    if pkg in R_PACKAGES_BIO:
        r_code = f'if (!requireNamespace("BiocManager", quietly=TRUE)) install.packages("BiocManager", repos="https://cloud.r-project.org")\nBiocManager::install("{pkg}", ask=FALSE, update=FALSE)'
    else:
        r_code = f'install.packages("{pkg}", repos="https://cloud.r-project.org")'
    try:
        subprocess.run(["Rscript", "-e", r_code], capture_output=True, text=True, timeout=600, encoding="utf-8", errors="replace")
        return True
    except Exception:
        return False


def check_env_handler(packages, language="both", auto_install=True):
    """问题1: 扩展为全面环境检测 — 除了生信包，还检测 GPU/CPU/内存/磁盘/平台。"""
    r_pkgs = [p for p in packages if p in R_PACKAGES_BIO or language in ("R", "both")]
    py_pkgs = [p for p in packages if p in PYTHON_PACKAGES_BIO or language in ("Python", "both")]
    r_pkgs = [p for p in r_pkgs if p not in PYTHON_PACKAGES_BIO]
    py_pkgs = [p for p in py_pkgs if p not in R_PACKAGES_BIO]
    result = {"installed": {}, "missing": {}, "installed_now": {}, "system": {}}

    # === 问题1: 系统环境全面检测 ===
    import shutil as _shutil, platform as _platform
    try:
        import psutil
        result["system"]["cpu_cores"] = psutil.cpu_count(logical=False) or 0
        result["system"]["memory_gb"] = round(psutil.virtual_memory().total / 1024**3, 1)
        result["system"]["memory_available_gb"] = round(psutil.virtual_memory().available / 1024**3, 1)
        result["system"]["disk_free_gb"] = round(psutil.disk_usage(os.getcwd()).free / 1024**3, 1)
    except Exception:
        pass
    result["system"]["platform"] = _platform.platform()
    result["system"]["python_version"] = sys.version.split()[0]
    # R 版本
    r_path = _shutil.which("Rscript")
    if r_path:
        try:
            rv = subprocess.run(["Rscript", "-e", "cat(R.version$major, R.version$minor, sep='.')"],
                                capture_output=True, text=True, timeout=10)
            result["system"]["r_version"] = rv.stdout.strip()
        except Exception:
            result["system"]["r_version"] = "unknown"
    else:
        result["system"]["r_version"] = "not installed"
    # GPU 检测 — 多路径 + torch.cuda 备用
    gpu_info = {"detected": False, "name": "", "vram_mb": 0, "method": ""}
    gpu_paths = [
        _shutil.which("nvidia-smi"),
        r"C:\\Windows\\System32\\nvidia-smi.exe",
        r"C:\\Program Files\\NVIDIA Corporation\\NVSMI\\nvidia-smi.exe",
        "/usr/bin/nvidia-smi",
        "/usr/local/bin/nvidia-smi",
    ]
    nvidia_smi = next((p for p in gpu_paths if p and os.path.isfile(p)), None)
    if nvidia_smi:
        try:
            gv = subprocess.run([nvidia_smi, "--query-gpu=name,memory.total", "--format=csv,noheader"],
                                capture_output=True, text=True, timeout=10)
            if gv.returncode == 0 and gv.stdout.strip():
                parts = [p.strip() for p in gv.stdout.strip().split("\n")[0].split(",")]
                gpu_info["detected"] = True
                gpu_info["name"] = parts[0]
                gpu_info["vram_mb"] = int(parts[1]) if len(parts) > 1 and parts[1].replace(" MiB", "").strip().isdigit() else 0
                gpu_info["method"] = "nvidia-smi"
        except Exception:
            pass
    if not gpu_info["detected"]:
        try:
            import torch
            if torch.cuda.is_available():
                gpu_info["detected"] = True
                gpu_info["name"] = torch.cuda.get_device_name(0)
                gpu_info["vram_mb"] = int(torch.cuda.get_device_properties(0).total_memory // 1024 // 1024)
                gpu_info["method"] = "torch.cuda"
        except Exception:
            pass
    result["system"]["gpu"] = gpu_info
    if r_pkgs and language in ("R", "both"):
        r_status = _check_r_packages(r_pkgs)
        for pkg, ok in r_status.items():
            if ok:
                result["installed"][pkg] = "R"
            else:
                result["missing"][pkg] = "R"
                if auto_install and _install_r_package(pkg):
                    result["installed_now"][pkg] = "R"
    if py_pkgs and language in ("Python", "both"):
        for p in py_pkgs:
            try:
                __import__(p.replace("-", "_"))
                result["installed"][p] = "Python"
            except ImportError:
                result["missing"][p] = "Python"
                if auto_install:
                    try:
                        subprocess.run([sys.executable, "-m", "pip", "install", p], capture_output=True, text=True, timeout=300)
                        result["installed_now"][p] = "Python"
                    except Exception:
                        pass
    if auto_install and result["installed_now"]:
        recheck_r = [p for p in result["installed_now"] if result["installed_now"][p] == "R"]
        if recheck_r:
            r_status = _check_r_packages(recheck_r)
            for pkg, ok in r_status.items():
                if ok:
                    result["installed"][pkg] = "R"
                    result["missing"].pop(pkg, None)
    return json.dumps(result, ensure_ascii=False, indent=2)


registry.register(
    name="check_env", toolset="memomics", schema=CHECK_ENV_SCHEMA,
    handler=lambda args, **kw: check_env_handler(args.get("packages", []), args.get("language", "both"), args.get("auto_install", True)),
    emoji="🔧", max_result_size_chars=20_000,
)

# ============================================================================
# rail_review
# ============================================================================
RAIL_REVIEW_SCHEMA = {
    "name": "rail_review",
    "description": "Rail review (铁轨审查). PRE: check env/packages before analysis. POST: check result quality after analysis. MUST call before and after each analysis subtask.",
    "parameters": {
        "type": "object",
        "properties": {
            "phase": {"type": "string", "enum": ["pre", "post"]},
            "module_id": {"type": "string"},
            "method_name": {"type": "string"},
            "output_dir": {"type": "string"},
            "code_executed": {"type": "string"},
            "required_packages": {"type": "array", "items": {"type": "string"}}
        },
        "required": ["phase", "module_id"]
    }
}


def rail_review(phase, module_id, method_name="", output_dir="", code_executed="", required_packages=None):
    if phase == "pre":
        issues, missing_packages = [], []
        if required_packages:
            r_status = _check_r_packages([p for p in required_packages if p in R_PACKAGES_BIO])
            for pkg, ok in r_status.items():
                if not ok:
                    missing_packages.append(pkg)
                    issues.append(f"Missing R package: {pkg}")
        should_proceed = len(issues) == 0
        return json.dumps({"phase": "pre", "module_id": module_id, "should_proceed": should_proceed, "issues": issues, "missing_packages": missing_packages}, ensure_ascii=False, indent=2)
    else:
        issues, warnings = [], []
        figure_count, result_files = 0, []
        if output_dir and os.path.exists(output_dir):
            for root, dirs, files in os.walk(output_dir):
                for f in files:
                    if f.lower().endswith(('.png', '.jpg', '.pdf', '.svg', '.tiff')):
                        figure_count += 1
                    elif f.lower().endswith(('.csv', '.tsv', '.rds', '.h5ad', '.txt', '.json')):
                        result_files.append(f)
            if figure_count == 0:
                warnings.append("No figures found in output directory")
            if not result_files:
                warnings.append("No result files found in output directory")
        elif output_dir:
            issues.append(f"Output directory not found: {output_dir}")
        if code_executed:
            code_lines = code_executed.strip().split('\n')
            if len(code_lines) < 10:
                warnings.append(f"Code is very short ({len(code_lines)} lines)")
            if len(code_lines) > 500:
                warnings.append(f"Code is very long ({len(code_lines)} lines)")
        passed = len(issues) == 0
        return json.dumps({"phase": "post", "module_id": module_id, "method_name": method_name or "unknown", "passed": passed, "issues": issues, "warnings": warnings, "figure_count": figure_count, "result_files": result_files}, ensure_ascii=False, indent=2)


registry.register(
    name="rail_review", toolset="memomics", schema=RAIL_REVIEW_SCHEMA,
    handler=lambda args, **kw: rail_review(args.get("phase", "pre"), args.get("module_id", ""), args.get("method_name", ""), args.get("output_dir", ""), args.get("code_executed", ""), args.get("required_packages")),
    emoji="🛡️", max_result_size_chars=20_000,
)

# ============================================================================
# debate_analysis — 多角色辩论审查
# ============================================================================
DEBATE_ANALYSIS_SCHEMA = {
    "name": "debate_analysis",
    "description": "多角色辩论审查：对分析参数/方法/结论进行正方3编辑+反方4编辑+裁判辩论。适用于参数不确定、方法有争议、结论需验证的场景。",
    "parameters": {
        "type": "object",
        "properties": {
            "topic": {"type": "string", "description": "辩论主题：参数选择/方法决策/结论验证"},
            "context": {"type": "string", "description": "分析上下文：当前数据、已执行步骤、待决策点"},
            "options": {"type": "array", "items": {"type": "string"}, "description": "备选方案列表，如 ['resolution=0.4','resolution=0.6','resolution=0.8']"},
            "output_dir": {"type": "string", "description": "归档目录，辩论结果保存到 {output_dir}/debate_{timestamp}.json"}
        },
        "required": ["topic", "context"]
    }
}


def debate_analysis(topic, context, options=None, output_dir=""):
    """Generate a structured multi-role debate framework. The calling LLM should
    play each role and produce the debate, then the judge synthesizes.
    Returns a JSON debate specification that the agent must follow."""
    import datetime

    roles = {
        "pro": [
            {"id": "bio_pro", "name": "生物学编辑(正)", "perspective": "从生物学意义角度支持最佳方案", "kb": "biology"},
            {"id": "stat_pro", "name": "统计学编辑(正)", "perspective": "从统计效力角度支持最佳方案", "kb": "statistics"},
            {"id": "bioinfo_pro", "name": "生信编辑(正)", "perspective": "从计算可行性角度支持最佳方案", "kb": "bioinfo"},
        ],
        "con": [
            {"id": "bio_con", "name": "生物学编辑(反)", "perspective": "从生物学角度质疑方案，提出替代解释", "kb": "biology"},
            {"id": "stat_con", "name": "统计学编辑(反)", "perspective": "从统计角度寻找漏洞和假设违反", "kb": "statistics"},
            {"id": "bioinfo_con", "name": "生信编辑(反)", "perspective": "从计算角度指出潜在错误和边界条件", "kb": "bioinfo"},
            {"id": "history_con", "name": "历史经验编辑(反)", "perspective": "从历史运行记录找相似失败案例和陷阱", "kb": "history_errors"},
        ],
    }

    debate_spec = {
        "topic": topic,
        "context": context[:3000],
        "options": options or [],
        "roles": roles,
        "rules": [
            "每个编辑独立发言，互不可见对方的论点",
            "正方从各自专业角度推荐最佳方案并论证",
            "反方从各自专业角度找出方案漏洞和风险",
            "所有编辑发言需引用具体数据、文献或历史证据",
            "裁判看到全部7方论点后给出最终裁决+置信度(高/中/低)",
            "最终输出包含：推荐方案、置信度、理由、风险提示",
        ],
        "timestamp": datetime.datetime.now().isoformat(),
        "status": "pending"
    }

    # Archive if output_dir is provided
    archive_path = ""
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        archive_path = os.path.join(output_dir, f"debate_{ts}.json")
        with open(archive_path, "w", encoding="utf-8") as f:
            json.dump(debate_spec, f, ensure_ascii=False, indent=2)

    prompt = f"""🗣️ **多角色辩论：{topic}**

请依次扮演以下 7 个角色进行辩论，每个角色独立发言（用 --- 分隔）：

## 正方（3 位）
1. **生物学编辑(正)**：[从生物学意义论证最佳方案]
2. **统计学编辑(正)**：[从统计效力论证最佳方案]
3. **生信编辑(正)**：[从计算可行性论证最佳方案]

## 反方（4 位）
4. **生物学编辑(反)**：[从生物学角度质疑，提出替代解释]
5. **统计学编辑(反)**：[从统计角度找漏洞和假设违反]
6. **生信编辑(反)**：[从计算角度指出边界条件和潜在错误]
7. **历史经验编辑(反)**：[从历史运行记录找相似失败案例]

## 裁判
8. **裁判**：综合以上7方论点，给出最终裁决（推荐方案 + 置信度 + 理由 + 风险提示）

---
**背景**：{context[:2000]}
**选项**：{json.dumps(options or [], ensure_ascii=False)}

请开始辩论："""

    result = {
        "debate_prompt": prompt,
        "roles_count": 8,
        "archive_path": archive_path,
        "instruction": "必须严格执行以上辩论流程，每个角色独立输出，裁判最后综合裁决。不得跳过任何角色。"
    }

    return json.dumps(result, ensure_ascii=False, indent=2)


registry.register(
    name="debate_analysis", toolset="memomics", schema=DEBATE_ANALYSIS_SCHEMA,
    handler=lambda args, **kw: debate_analysis(args.get("topic", ""), args.get("context", ""), args.get("options"), args.get("output_dir", "")),
    emoji="🗣️", max_result_size_chars=50_000,
)

# ============================================================================
# todo_manage
# ============================================================================
TODO_MANAGE_SCHEMA = {
    "name": "todo_manage",
    "description": "Manage analysis todos/subtasks. Create from selected modules, update status, list. Each todo maps to a skill.",
    "parameters": {
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": ["create", "update", "list", "reset"]},
            "modules": {"type": "array", "items": {"type": "string"}},
            "todo_id": {"type": "string"},
            "status": {"type": "string", "enum": ["pending", "running", "completed", "failed"]},
            "result_summary": {"type": "string"}
        },
        "required": ["action"]
    }
}

_TODOS = {}


def _create_todos(modules):
    todos = []
    tid = 0
    for mid in modules:
        if mid not in MODULES:
            continue
        for substep in MODULES[mid]["substeps"]:
            tid += 1
            todo = {"id": f"todo_{tid}", "module_id": mid, "module_name": MODULES[mid]["name"],
                    "substep_id": substep["id"], "substep_name": substep["name"],
                    "skill": substep.get("skill", ""), "status": "pending", "result_summary": ""}
            todos.append(todo)
            _TODOS[todo["id"]] = todo
    return todos


def todo_manage(action, modules=None, todo_id="", status="", result_summary=""):
    if action == "create":
        todos = _create_todos(modules or [])
        return json.dumps({"action": "create", "total": len(todos), "todos": todos}, ensure_ascii=False, indent=2)
    elif action == "update":
        if todo_id in _TODOS:
            _TODOS[todo_id]["status"] = status or _TODOS[todo_id]["status"]
            if result_summary:
                _TODOS[todo_id]["result_summary"] = result_summary
            return json.dumps({"action": "update", "todo": _TODOS[todo_id]}, ensure_ascii=False, indent=2)
        return json.dumps({"error": f"Todo {todo_id} not found"}, ensure_ascii=False)
    elif action == "list":
        return json.dumps({"action": "list", "todos": list(_TODOS.values())}, ensure_ascii=False, indent=2)
    elif action == "reset":
        _TODOS.clear()
        return json.dumps({"action": "reset", "message": "All todos cleared"}, ensure_ascii=False)
    return json.dumps({"error": f"Unknown action: {action}"}, ensure_ascii=False)


registry.register(
    name="todo_manage", toolset="memomics", schema=TODO_MANAGE_SCHEMA,
    handler=lambda args, **kw: todo_manage(args.get("action", "list"), args.get("modules"), args.get("todo_id", ""), args.get("status", ""), args.get("result_summary", "")),
    emoji="✅", max_result_size_chars=20_000,
)

# Register memomics_pipeline tool
from agent.memomics_pipeline import memomics_pipeline, TOOL_SCHEMA as PIPELINE_SCHEMA

registry.register(
    name="memomics_pipeline", toolset="memomics", schema=PIPELINE_SCHEMA,
    handler=lambda args, **kw: memomics_pipeline(
        args.get("action", "parse"),
        args.get("user_input", ""),
        args.get("selected_modules"),
        args.get("direction_info"),
    ),
    emoji="🔬", max_result_size_chars=20_000,
)

logger.info("MemOmics tools registered: scan_data, search_knowledge, guide_analysis, check_env, rail_review, todo_manage, memomics_pipeline, update_results_dir")

# ============================================================================
# update_results_dir — scan_data 后用 物种_组织_方向_日期 重命名结果目录
# ============================================================================
UPDATE_RESULTS_DIR_SCHEMA = {
    "name": "update_results_dir",
    "description": (
        "Rename the session results directory to a human-readable name: "
        "species_tissue_direction_YYYYMMDD. "
        "MUST call this AFTER scan_data returns species/tissue info, "
        "and AFTER user confirms the analysis direction. "
        "This makes results easy to find on disk. "
        "问题3: 如果用户指定了保存路径（如桌面），设置 output_root，结果会同时复制到用户路径，results/ 下保留备份。"
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "species": {"type": "string", "description": "Species, e.g. human, mouse, rat"},
            "tissue": {"type": "string", "description": "Tissue/organ, e.g. muscle, brain, liver"},
            "direction": {"type": "string", "description": "Research direction, e.g. aging, cancer, development"},
            "output_root": {"type": "string", "description": "用户指定的保存路径（如桌面），结果会复制到此路径，同时 results/ 下保留备份。留空则只存 results/。"}
        },
        "required": ["species", "tissue", "direction"]
    }
}

import httpx as _httpx

def update_results_dir(species: str, tissue: str, direction: str, output_root: str = "") -> str:
    """调用 server API 重命名当前会话的结果目录。"""
    import os as _os
    # 从线程级上下文获取 sid（纯线程隔离，无 os.environ 竞态）
    from memomics.bio_tools.debate_analysis import get_session_sid
    sid = get_session_sid()
    if not sid:
        return '{"ok": false, "error": "No active session"}'
    port = _os.environ.get("MEMOMICS_PORT", "8899")
    try:
        resp = _httpx.post(
            f"http://127.0.0.1:{port}/api/sessions/{sid}/rename-results",
            json={"species": species, "tissue": tissue, "direction": direction, "output_root": output_root},
            timeout=10
        )
        return resp.text
    except Exception as e:
        return f'{{"ok": false, "error": "API call failed: {e}"}}'

def _update_results_dir_handler(args, **kw):
    """从 dispatch kwargs 获取 session_id，设置线程级上下文。
    修复：保留已有 results_dir 不覆盖，并在 API 成功后更新线程上下文。"""
    import json as _json
    sid = kw.get("session_id", "")
    if sid:
        from memomics.bio_tools.debate_analysis import set_session_context, get_session_results_dir
        # 保留已有的 results_dir，不要覆盖为空（否则后续工具找不到日志目录）
        existing = get_session_results_dir()
        set_session_context(sid=sid, results_dir=existing or "")
    result_str = update_results_dir(
        args.get("species", ""), args.get("tissue", ""),
        args.get("direction", ""), args.get("output_root", "")
    )
    # API 成功后，解析新的 results_dir 并更新线程上下文
    if sid:
        try:
            resp = _json.loads(result_str)
            if resp.get("ok") and resp.get("results_dir"):
                from memomics.bio_tools.debate_analysis import set_session_context
                set_session_context(sid=sid, results_dir=resp["results_dir"])
        except Exception:
            pass
    return result_str

registry.register(
    name="update_results_dir", toolset="memomics", schema=UPDATE_RESULTS_DIR_SCHEMA,
    handler=_update_results_dir_handler,
    emoji="📁", max_result_size_chars=5_000,
)

# ============================================================================
# skill_evolution — 自进化：运行日志 + 错误日志（原脚本永远不动）
# ============================================================================
SKILL_EVOLUTION_SCHEMA = {
    "name": "skill_evolution",
    "description": (
        "MemOmics 自进化核心工具。原脚本永远不被修改，所有经验以运行日志形式累积。\n"
        "必须调用的时机：\n"
        "1. 跑脚本前 → query_logs（查同类运行日志，参考已有经验，避免重复踩坑）\n"
        "2. rail_review(post) 通过 → record_run（记录成功运行日志：参数/结果/质量）\n"
        "3. rail_review(post) 失败 → record_error（记录错误日志：报错/根因/修复方案）\n"
        "原脚本不会被替换。每个 skill 的 .run_logs/ 下按 物种_组织_方向 命名存储日志。"
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": ["record_run", "record_error", "query_logs"], "description": "record_run=记录成功运行日志, record_error=记录错误日志, query_logs=查询同类运行日志"},
            "skill_name": {"type": "string", "description": "skill 目录名，如 scrna-qc, scrna-clustering"},
            "script_name": {"type": "string", "description": "脚本名，如 normalize_data.R, qc.R"},
            "species": {"type": "string", "description": "物种，如 人类, 恒河猴, 小鼠"},
            "tissue": {"type": "string", "description": "组织，如 骨骼肌, 大脑, 肝脏"},
            "direction": {"type": "string", "description": "研究方向，如 衰老, 神经退行, 发育"},
            "params_used": {"type": "string", "description": "[record_run] 使用的参数，JSON string"},
            "result_summary": {"type": "string", "description": "[record_run] 运行结果摘要"},
            "quality_score": {"type": "number", "description": "[record_run] 质量评分 0-10"},
            "notes": {"type": "string", "description": "[record_run] 备注/经验总结"},
            "error_message": {"type": "string", "description": "[record_error] 报错信息"},
            "root_cause": {"type": "string", "description": "[record_error] 根因分析"},
            "fix_applied": {"type": "string", "description": "[record_error] 修复方案"}
        },
        "required": ["action", "skill_name", "script_name"]
    }
}

import time as _time

def _skill_evolution_dir(skill_name: str) -> str:
    """获取 skill 目录路径"""
    base = os.path.join(os.environ.get("HERMES_HOME", ""), "skills", "bioinformatics", skill_name)
    return base

def _skill_run_logs_dir(skill_name: str) -> str:
    """获取 skill 的 .run_logs 目录路径"""
    return os.path.join(_skill_evolution_dir(skill_name), ".run_logs")

def _skill_evolution_file(skill_name: str) -> str:
    """获取 skill 的 .evolution.json 路径（索引文件）"""
    return os.path.join(_skill_evolution_dir(skill_name), ".evolution.json")

def _make_log_tag(species: str, tissue: str, direction: str) -> str:
    """生成日志标识：物种_组织_方向"""
    parts = []
    for v in [species, tissue, direction]:
        v = (v or "").strip()
        if v:
            parts.append(v)
    return "_".join(parts) if parts else "通用"

def skill_evolution(action: str, skill_name: str, script_name: str = "", **kwargs) -> str:
    """自进化核心函数。原脚本永远不动，经验以日志形式累积。"""
    skill_dir = _skill_evolution_dir(skill_name)

    if not os.path.isdir(skill_dir):
        return json.dumps({"ok": False, "error": f"Skill not found: {skill_name}"}, ensure_ascii=False)

    species = kwargs.get("species", "")
    tissue = kwargs.get("tissue", "")
    direction = kwargs.get("direction", "")
    tag = _make_log_tag(species, tissue, direction)
    ts = _time.strftime("%Y-%m-%d %H:%M:%S")
    date_str = _time.strftime("%Y%m%d")

    # 确保日志目录存在
    logs_dir = _skill_run_logs_dir(skill_name)
    os.makedirs(logs_dir, exist_ok=True)

    # 索引文件
    evo_file = _skill_evolution_file(skill_name)
    evo_data = {"run_logs": [], "error_logs": []}
    if os.path.isfile(evo_file):
        try:
            with open(evo_file, encoding="utf-8") as f:
                evo_data = json.load(f)
        except Exception:
            pass

    if action == "query_logs":
        """查询同类运行日志，返回匹配的日志供参考"""
        script_base = os.path.splitext(script_name)[0] if script_name else ""
        matched = []
        # 优先精确匹配 物种+组织+方向
        for entry in evo_data.get("run_logs", []):
            entry_tag = _make_log_tag(entry.get("species", ""), entry.get("tissue", ""), entry.get("direction", ""))
            if tag != "通用" and entry_tag == tag:
                matched.append({**entry, "match_type": "精确匹配"})
        # 其次匹配组织相同
        if not matched and tissue:
            for entry in evo_data.get("run_logs", []):
                if entry.get("tissue", "") == tissue:
                    matched.append({**entry, "match_type": "组织匹配"})
        # 再次匹配物种相同
        if not matched and species:
            for entry in evo_data.get("run_logs", []):
                if entry.get("species", "") == species:
                    matched.append({**entry, "match_type": "物种匹配"})
        # 最后匹配脚本相同
        if not matched and script_base:
            for entry in evo_data.get("run_logs", []):
                if script_base in entry.get("script_name", ""):
                    matched.append({**entry, "match_type": "脚本匹配"})
        # 错误日志也一起返回
        matched_errors = []
        for entry in evo_data.get("error_logs", []):
            entry_tag = _make_log_tag(entry.get("species", ""), entry.get("tissue", ""), entry.get("direction", ""))
            if tag != "通用" and entry_tag == tag:
                matched_errors.append(entry)
            elif tissue and entry.get("tissue", "") == tissue:
                matched_errors.append(entry)
        # 按时间倒序
        matched.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
        matched_errors.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
        result = {
            "ok": True,
            "action": "query_logs",
            "skill": skill_name,
            "script": script_name,
            "query_tag": tag,
            "run_logs_found": len(matched),
            "error_logs_found": len(matched_errors),
            "run_logs": matched[:5],
            "error_logs": matched_errors[:5],
            "hint": "参考已有运行日志中的参数和经验，避免重复踩坑" if matched else "暂无同类运行日志，按原脚本和知识库执行"
        }
        return json.dumps(result, ensure_ascii=False)

    elif action == "record_run":
        """记录成功运行日志"""
        if not script_name:
            return json.dumps({"ok": False, "error": "script_name required"}, ensure_ascii=False)
        entry = {
            "timestamp": ts,
            "date": date_str,
            "script_name": script_name,
            "species": species,
            "tissue": tissue,
            "direction": direction,
            "tag": tag,
            "params": kwargs.get("params_used", ""),
            "result_summary": kwargs.get("result_summary", ""),
            "quality_score": kwargs.get("quality_score", 0),
            "notes": kwargs.get("notes", ""),
        }
        evo_data.setdefault("run_logs", []).append(entry)
        # 写索引
        try:
            with open(evo_file, "w", encoding="utf-8") as f:
                json.dump(evo_data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            return json.dumps({"ok": False, "error": f"Write index failed: {e}"}, ensure_ascii=False)
        # 写日志文件
        log_filename = f"{os.path.splitext(script_name)[0]}_{tag}_{date_str}.log"
        log_path = os.path.join(logs_dir, log_filename)
        log_content = (
            f"# MemOmics 运行日志\n"
            f"# 时间: {ts}\n"
            f"# Skill: {skill_name}\n"
            f"# 脚本: {script_name}\n"
            f"# 物种: {species}\n"
            f"# 组织: {tissue}\n"
            f"# 方向: {direction}\n"
            f"# 标识: {tag}\n"
            f"# 质量评分: {kwargs.get('quality_score', 0)}/10\n"
            f"# 参数: {kwargs.get('params_used', '')}\n"
            f"# 结果: {kwargs.get('result_summary', '')}\n"
            f"# 备注: {kwargs.get('notes', '')}\n"
        )
        try:
            with open(log_path, "w", encoding="utf-8") as f:
                f.write(log_content)
        except Exception:
            pass
        return json.dumps({
            "ok": True, "action": "record_run", "skill": skill_name, "script": script_name,
            "tag": tag, "log_file": log_filename,
            "total_run_logs": len(evo_data.get("run_logs", [])),
            "_evolution_event": {"type": "run_log", "skill": skill_name, "script": script_name, "tag": tag, "score": kwargs.get("quality_score", 0)}
        }, ensure_ascii=False)

    elif action == "record_error":
        """记录错误日志"""
        if not script_name:
            return json.dumps({"ok": False, "error": "script_name required"}, ensure_ascii=False)
        entry = {
            "timestamp": ts,
            "date": date_str,
            "script_name": script_name,
            "species": species,
            "tissue": tissue,
            "direction": direction,
            "tag": tag,
            "error": kwargs.get("error_message", ""),
            "root_cause": kwargs.get("root_cause", ""),
            "fix_applied": kwargs.get("fix_applied", ""),
        }
        evo_data.setdefault("error_logs", []).append(entry)
        # 写索引
        try:
            with open(evo_file, "w", encoding="utf-8") as f:
                json.dump(evo_data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            return json.dumps({"ok": False, "error": f"Write index failed: {e}"}, ensure_ascii=False)
        # 写错误日志文件
        err_filename = f"{os.path.splitext(script_name)[0]}_{tag}_{date_str}.err"
        err_path = os.path.join(logs_dir, err_filename)
        err_content = (
            f"# MemOmics 错误日志\n"
            f"# 时间: {ts}\n"
            f"# Skill: {skill_name}\n"
            f"# 脚本: {script_name}\n"
            f"# 物种: {species}\n"
            f"# 组织: {tissue}\n"
            f"# 方向: {direction}\n"
            f"# 标识: {tag}\n"
            f"# 错误: {kwargs.get('error_message', '')}\n"
            f"# 根因: {kwargs.get('root_cause', '')}\n"
            f"# 修复: {kwargs.get('fix_applied', '')}\n"
        )
        try:
            with open(err_path, "w", encoding="utf-8") as f:
                f.write(err_content)
        except Exception:
            pass
        return json.dumps({
            "ok": True, "action": "record_error", "skill": skill_name, "script": script_name,
            "tag": tag, "log_file": err_filename,
            "total_error_logs": len(evo_data.get("error_logs", [])),
            "_evolution_event": {"type": "error_log", "skill": skill_name, "script": script_name, "tag": tag, "error": kwargs.get("error_message", "")[:100]}
        }, ensure_ascii=False)

    return json.dumps({"ok": False, "error": f"Unknown action: {action}"}, ensure_ascii=False)


def _skill_evolution_dispatch(args, **kw):
    """统一委托到 bio_tools/skill_evolution.py 的实现，避免两套存储格式冲突。
    
    bio_tools 版本支持 5 个 action：record_error, record_success, record_run,
    query_logs, update_script。存储到 SKILL.md / skill.json / error_log.md。
    """
    try:
        import importlib.util as _iu
        import os as _os
        _sep = _iu.spec_from_file_location(
            "skill_evolution",
            _os.path.join(_os.path.dirname(_os.path.abspath(__file__)),
                          "..", "..", "memomics", "bio_tools", "skill_evolution.py")
        )
        se = _iu.module_from_spec(_sep)
        _sep.loader.exec_module(se)
    except Exception:
        return skill_evolution(
            args.get("action", ""), args.get("skill_name", ""),
            script_name=args.get("script_name", ""),
            species=args.get("species", ""),
            tissue=args.get("tissue", ""),
            direction=args.get("direction", ""),
            params_used=args.get("params_used", ""),
            result_summary=args.get("result_summary", ""),
            quality_score=args.get("quality_score", 0),
            notes=args.get("notes", ""),
            error_message=args.get("error_message", ""),
            root_cause=args.get("root_cause", ""),
            fix_applied=args.get("fix_applied", ""),
        )
    return se.skill_evolution(
        action=args.get("action", ""),
        skill_name=args.get("skill_name", ""),
        script_name=args.get("script_name", ""),
        species=args.get("species", ""),
        tissue=args.get("tissue", ""),
        direction=args.get("direction", ""),
        params_used=args.get("params_used", ""),
        result_summary=args.get("result_summary", ""),
        score=args.get("quality_score", 0) or args.get("score", 0),
        error_message=args.get("error_message", ""),
        error_type=args.get("error_type", ""),
        root_cause=args.get("root_cause", ""),
        fix_applied=args.get("fix_applied", ""),
        fix_code=args.get("fix_code", ""),
        fixed_script_path=args.get("fixed_script_path", ""),
        reason=args.get("reason", ""),
        severity=args.get("severity", ""),
    )


registry.register(
    name="skill_evolution", toolset="memomics", schema=SKILL_EVOLUTION_SCHEMA,
    handler=lambda args, **kw: _skill_evolution_dispatch(args, **kw),
    emoji="🧬", max_result_size_chars=5_000,
)

# === 微信消息推送 ===
# 注册 send_message 为 Agent 可调用工具，支持分析启动/完成通知和进度推送
# 底层使用 Hermes 的 send_message_tool 共享传输层，但只开放 weixin 平台
try:
    from tools.send_message_tool import send_message_tool, SEND_MESSAGE_SCHEMA
    registry.register(
        name="send_message", toolset="memomics", schema=SEND_MESSAGE_SCHEMA,
        handler=send_message_tool,
        emoji="📱", max_result_size_chars=2_000,
    )
except ImportError:
    pass

# === 截屏工具（使用 mss 库，无需 cua-driver）===
SCREENSHOT_SCHEMA = {
    "name": "screenshot",
    "description": (
        "Capture a screenshot of the entire screen or a specific monitor and save as PNG. "
        "Uses the lightweight mss library (already installed). "
        "Returns the path to the saved screenshot file."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "output_dir": {
                "type": "string",
                "description": "Directory to save the screenshot. Defaults to current results_dir."
            },
            "monitor": {
                "type": "integer",
                "description": "Monitor index (1=primary, 2=secondary, etc). Default 1."
            },
        },
        "required": []
    }
}

def _handle_screenshot(args):
    try:
        import mss
        import mss.tools
        from datetime import datetime
        
        monitor = args.get("monitor", 1)
        output_dir = args.get("output_dir", "")
        
        with mss.mss() as sct:
            if monitor > len(sct.monitors):
                monitor = 1
            img = sct.grab(sct.monitors[monitor])
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"screenshot_{timestamp}.png"
            if output_dir and os.path.isdir(output_dir):
                filepath = os.path.join(output_dir, filename)
            else:
                filepath = os.path.join(os.getcwd(), filename)
            mss.tools.to_png(img.rgb, img.size, output=filepath)
            return json.dumps({"ok": True, "path": filepath.replace(chr(92), "/"), "size": img.size, "file": filename})
    except Exception as e:
        return json.dumps({"ok": False, "error": str(e)})

registry.register(
    name="screenshot", toolset="memomics", schema=SCREENSHOT_SCHEMA,
    handler=lambda args, **kw: _handle_screenshot(args),
    emoji="📸", max_result_size_chars=2_000,
)
