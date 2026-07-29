"""Environment check tool — checks R/Python bio packages and auto-installs missing."""
import json
import subprocess
import sys
import logging
import os
import time

logger = logging.getLogger(__name__)

# === 环境持久化缓存 ===
from pathlib import Path as _Path
from hermes_constants import get_hermes_home as _get_hermes_home
_ENV_CACHE = None
# 缓存文件路径：优先用 HERMES_HOME 环境变量，回退项目根目录
_ENV_CACHE_DIR = os.environ.get("HERMES_HOME", os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "hermes_home"))
_ENV_CACHE_PATH = os.path.join(_ENV_CACHE_DIR, "environment.json")
_CACHE_TTL = 86400  # 24小时过期

def _load_env_cache():
    global _ENV_CACHE
    if _ENV_CACHE is not None:
        return _ENV_CACHE
    try:
        if os.path.exists(_ENV_CACHE_PATH):
            with open(_ENV_CACHE_PATH, "r", encoding="utf-8") as f:
                _ENV_CACHE = json.load(f)
            age = time.time() - _ENV_CACHE.get("cached_at", 0)
            if age < _CACHE_TTL:
                logger.info(f"env_cache loaded ({len(_ENV_CACHE.get('packages',{}))} pkgs, {age:.0f}s old)")
                return _ENV_CACHE
            logger.info(f"env_cache expired ({age:.0f}s old), will refresh")
    except Exception:
        pass
    _ENV_CACHE = {"packages": {}, "paths": {}, "cached_at": 0}
    return _ENV_CACHE

def _save_env_cache():
    global _ENV_CACHE
    if _ENV_CACHE is None:
        return
    try:
        _ENV_CACHE["cached_at"] = time.time()
        os.makedirs(os.path.dirname(_ENV_CACHE_PATH), exist_ok=True)
        with open(_ENV_CACHE_PATH, "w", encoding="utf-8") as f:
            json.dump(_ENV_CACHE, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.warning(f"env_cache save failed: {e}")

def _find_r_executable():
    """查找 R 可执行文件路径，缓存结果"""
    cache = _load_env_cache()
    cached = cache.get("paths", {}).get("R")
    if cached and os.path.isfile(cached):
        try:
            r = subprocess.run([cached, "--version"], capture_output=True, text=True, timeout=10)
            if r.returncode == 0:
                return cached
        except Exception:
            pass
    # 搜索常见路径
    candidates = [
        r"C:\Program Files\R\R-4.3.2\bin\Rscript.exe",
        r"C:\Program Files\R\R-4.3.3\bin\Rscript.exe",
        r"C:\Program Files\R\R-4.4\bin\Rscript.exe",
        r"C:\R\R-4.3.2\bin\Rscript.exe",
    ]
    for p in candidates:
        if os.path.isfile(p):
            cache.setdefault("paths", {})["R"] = p
            _save_env_cache()
            return p
    # 回退 PATH
    return "Rscript"

def _find_python_executable():
    """返回当前 Python 路径，缓存"""
    cache = _load_env_cache()
    cached = cache.get("paths", {}).get("python")
    py = sys.executable
    if cached != py:
        cache.setdefault("paths", {})["python"] = py
        _save_env_cache()
    return py

SCHEMA = {
    "name": "check_env",
    "description": (
        "Check R/Python bioinformatics package availability and auto-install "
        "missing ones. Call this BEFORE running analysis code (pre-review). "
        "Supports R packages (Seurat, CellChat, monocle3, etc.) and Python "
        "packages (scanpy, scvi-tools, etc.)."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "packages": {
                "type": "array",
                "items": {"type": "string"},
                "description": "List of packages to check (e.g. ['Seurat', 'CellChat', 'scanpy'])"
            },
            "language": {
                "type": "string",
                "enum": ["R", "Python", "both"],
                "default": "both"
            },
            "auto_install": {
                "type": "boolean",
                "default": True,
                "description": "Auto-install missing packages"
            }
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
    "enrichplot", "DOSE", "ReactomePA", "decontreco",
}

PYTHON_PACKAGES_BIO = {
    "scanpy", "anndata", "scvi-tools", "scvelo", "cellrank", "pyscenic",
    "squidpy", "scikit-learn", "pandas", "numpy", "matplotlib", "seaborn",
    "plotly", "leidenalg", "louvain", "umap-learn", "statsmodels",
    "scvi", "scirpy", "spatialdata",
}


def _check_r_packages(packages):
    """Check R package availability — uses cached R path if available"""
    r_bin = _find_r_executable()
    pkg_str = ", ".join(f'"{p}"' for p in packages)
    r_code = f"""
pkgs <- c({pkg_str})
installed <- sapply(pkgs, function(p) {{
    requireNamespace(p, quietly = TRUE)
}})
for (p in names(installed)) {{
    cat(p, ":", if(installed[p]) "OK" else "MISSING", "\n")
}}
"""
    try:
        result = subprocess.run(
            [r_bin, "-e", r_code],
            capture_output=True, text=True, timeout=60,
            encoding="utf-8", errors="replace"
        )
        lines = result.stdout.strip().split("\n")
        status = {}
        for line in lines:
            if ":" in line:
                parts = line.strip().split(":")
                if len(parts) == 2:
                    pkg = parts[0].strip().strip('"')
                    stat = parts[1].strip()
                    status[pkg] = stat == "OK"
        return status
    except Exception as e:
        logger.exception("R package check failed")
        return {p: False for p in packages}


def _check_python_packages(packages):
    """Check Python package availability."""
    status = {}
    for p in packages:
        try:
            __import__(p.replace("-", "_"))
            status[p] = True
        except ImportError:
            status[p] = False
    return status


def _install_r_package(pkg):
    """Install an R package."""
    if pkg in R_PACKAGES_BIO:
        # Bioconductor packages
        r_code = f'''
if (!requireNamespace("BiocManager", quietly = TRUE))
    install.packages("BiocManager", repos="https://cloud.r-project.org")
BiocManager::install("{pkg}", ask=FALSE, update=FALSE)
'''
    else:
        r_code = f'install.packages("{pkg}", repos="https://cloud.r-project.org")'
    try:
        subprocess.run(
            ["Rscript", "-e", r_code],
            capture_output=True, text=True, timeout=600,
            encoding="utf-8", errors="replace"
        )
        return True
    except Exception:
        return False


def _install_python_package(pkg):
    """Install a Python package."""
    try:
        subprocess.run(
            [sys.executable, "-m", "pip", "install", pkg],
            capture_output=True, text=True, timeout=300,
            encoding="utf-8", errors="replace"
        )
        return True
    except Exception:
        return False


def check_env(packages, language="both", auto_install=True):
    """Check and optionally install packages. Uses persisted cache to skip re-checks."""
    cache = _load_env_cache()
    cached_pkgs = cache.get("packages", {})
    result = {"installed": {}, "missing": {}, "installed_now": {}, "from_cache": {}}

    r_pkgs = [p for p in packages if p in R_PACKAGES_BIO or language in ("R", "both")]
    py_pkgs = [p for p in packages if p in PYTHON_PACKAGES_BIO or language in ("Python", "both")]
    r_pkgs = [p for p in r_pkgs if p not in PYTHON_PACKAGES_BIO]
    py_pkgs = [p for p in py_pkgs if p not in R_PACKAGES_BIO]

    # 先用缓存——24小时内检查过的包直接返回
    _needs_check_r = []
    _needs_check_py = []
    for pkg in r_pkgs:
        if pkg in cached_pkgs:
            result["installed"][pkg] = "R"
            result["from_cache"][pkg] = "R"
        else:
            _needs_check_r.append(pkg)
    for pkg in py_pkgs:
        if pkg in cached_pkgs:
            result["installed"][pkg] = "Python"
            result["from_cache"][pkg] = "Python"
        else:
            _needs_check_py.append(pkg)

    # 只检查缓存里没有的包
    if _needs_check_r and language in ("R", "both"):
        r_status = _check_r_packages(_needs_check_r)
        for pkg, ok in r_status.items():
            if ok:
                result["installed"][pkg] = "R"
            else:
                result["missing"][pkg] = "R"
                if auto_install:
                    if _install_r_package(pkg):
                        result["installed_now"][pkg] = "R"

    if py_pkgs and language in ("Python", "both"):
        py_status = _check_python_packages(_needs_check_py if _needs_check_py else py_pkgs)
        for pkg, ok in py_status.items():
            if ok:
                result["installed"][pkg] = "Python"
            else:
                result["missing"][pkg] = "Python"
                if auto_install:
                    if _install_python_package(pkg):
                        result["installed_now"][pkg] = "Python"

    # Re-check after install
    if auto_install and result["installed_now"]:
        recheck_r = [p for p in result["installed_now"] if result["installed_now"][p] == "R"]
        recheck_py = [p for p in result["installed_now"] if result["installed_now"][p] == "Python"]
        if recheck_r:
            r_status = _check_r_packages(recheck_r)
            for pkg, ok in r_status.items():
                if ok:
                    result["installed"][pkg] = "R"
                    del result["missing"][pkg]
        if recheck_py:
            py_status = _check_python_packages(recheck_py)
            for pkg, ok in py_status.items():
                if ok:
                    result["installed"][pkg] = "Python"
                    del result["missing"][pkg]

    # 保存到缓存——24小时内不再重复检查
    for pkg in result["installed"]:
        if pkg not in cached_pkgs:
            cached_pkgs[pkg] = result["installed"][pkg]
    for pkg in result["installed_now"]:
        cached_pkgs[pkg] = result["installed_now"][pkg]
    cache["packages"] = cached_pkgs
    _save_env_cache()

    return result


def check_env_handler(packages, language="both", auto_install=True):
    """Handler for check_env tool."""
    result = check_env(packages, language, auto_install)
    return json.dumps(result, ensure_ascii=False, indent=2)


def _register():
    from tools.registry import registry
    registry.register(
        name="check_env",
        toolset="memomics",
        schema=SCHEMA,
        handler=lambda args, **kw: check_env_handler(
            args.get("packages", []),
            args.get("language", "both"),
            args.get("auto_install", True)
        ),
        emoji="🔧",
        max_result_size_chars=20_000,
    )

_register()
