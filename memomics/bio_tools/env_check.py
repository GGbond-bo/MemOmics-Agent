"""Environment check tool — checks R/Python bio packages and auto-installs missing."""
import json
import subprocess
import sys
import logging
import os

logger = logging.getLogger(__name__)

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
    """Check R package availability."""
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
            ["Rscript", "-e", r_code],
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
    """Check and optionally install packages."""
    r_pkgs = [p for p in packages if p in R_PACKAGES_BIO or language in ("R", "both")]
    py_pkgs = [p for p in packages if p in PYTHON_PACKAGES_BIO or language in ("Python", "both")]

    # Remove overlap
    r_pkgs = [p for p in r_pkgs if p not in PYTHON_PACKAGES_BIO]
    py_pkgs = [p for p in py_pkgs if p not in R_PACKAGES_BIO]

    result = {"installed": {}, "missing": {}, "installed_now": {}}

    if r_pkgs and language in ("R", "both"):
        r_status = _check_r_packages(r_pkgs)
        for pkg, ok in r_status.items():
            if ok:
                result["installed"][pkg] = "R"
            else:
                result["missing"][pkg] = "R"
                if auto_install:
                    if _install_r_package(pkg):
                        result["installed_now"][pkg] = "R"

    if py_pkgs and language in ("Python", "both"):
        py_status = _check_python_packages(py_pkgs)
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
