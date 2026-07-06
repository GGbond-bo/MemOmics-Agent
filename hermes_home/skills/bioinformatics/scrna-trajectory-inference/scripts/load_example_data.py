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

"""
Load example data for single-cell trajectory inference.

Provides two functions:
  - load_example_data(): Load pancreas endocrinogenesis dataset (Bastidas-Ponce 2019)
  - load_user_data(path): Load and validate user-provided h5ad/rds file

Example dataset: Pancreatic endocrinogenesis (3,696 cells)
  - Progenitor cells differentiate into alpha, beta, delta, epsilon cells
  - Includes spliced/unspliced counts for RNA velocity
  - Available via scvelo.datasets.pancreas()

Usage:
  from scripts.load_example_data import load_example_data
  adata = load_example_data()
"""

import warnings
from pathlib import Path


def load_example_data():
    """
    Load the pancreatic endocrinogenesis dataset (Bastidas-Ponce et al. 2019).

    Downloads ~15 MB h5ad from scVelo's data repository.
    Contains spliced/unspliced counts for RNA velocity analysis.

    Returns
    -------
    adata : AnnData
        Preprocessed AnnData with:
        - .X : spliced counts (log-normalized)
        - .layers['spliced'], .layers['unspliced'] : raw counts for velocity
        - .obs['clusters'] : cell type annotations (8 types)
        - .obsm['X_umap'] : UMAP embedding
        - .var['highly_variable'] : HVG flags

    Raises
    ------
    RuntimeError
        If download or loading fails.
    """
    try:
        import scvelo as scv
    except ImportError:
        raise RuntimeError(
            "scvelo is required for example data. Install with: pip install scvelo"
        )

    print("Loading pancreatic endocrinogenesis dataset (Bastidas-Ponce 2019)...")
    print("  Downloading from scVelo repository (~15 MB)...")

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        adata = scv.datasets.pancreas()

    # Validate required slots
    _validate_adata(adata, require_velocity_layers=True)

    print(f"✓ Data loaded successfully!")
    print(f"  Cells: {adata.n_obs:,}")
    print(f"  Genes: {adata.n_vars:,}")
    print(f"  Cell types: {adata.obs['clusters'].nunique()}")
    print(f"  Cell type distribution:")
    for ct, count in adata.obs["clusters"].value_counts().items():
        print(f"    - {ct}: {count} cells ({100 * count / adata.n_obs:.1f}%)")
    print(f"  Layers: {list(adata.layers.keys())}")
    print(f"  Embeddings: {list(adata.obsm.keys())}")

    return adata


def load_user_data(path, cluster_key=None):
    """
    Load and validate a user-provided scRNA-seq dataset.

    Supports .h5ad (AnnData) files. The object should be preprocessed
    (normalized, with PCA/UMAP computed and clusters assigned).

    Parameters
    ----------
    path : str or Path
        Path to .h5ad file.
    cluster_key : str, optional
        Column in .obs containing cluster/cell type labels.
        Auto-detected if not specified.

    Returns
    -------
    adata : AnnData
        Validated AnnData object.

    Raises
    ------
    FileNotFoundError
        If the file does not exist.
    ValueError
        If the file format is unsupported or data is invalid.
    """
    import scanpy as sc

    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")

    if path.suffix == ".h5ad":
        print(f"Loading AnnData from {path}...")
        adata = sc.read_h5ad(path)
    else:
        raise ValueError(
            f"Unsupported file format: {path.suffix}. "
            "Expected .h5ad (AnnData). "
            "Convert Seurat objects with SeuratDisk::SaveH5Seurat() + Convert()."
        )

    # Auto-detect cluster key
    if cluster_key is None:
        candidates = [
            "clusters",
            "cell_type",
            "celltype",
            "leiden",
            "louvain",
            "cluster",
            "cell_type_ontology_term_id",
        ]
        for c in candidates:
            if c in adata.obs.columns:
                cluster_key = c
                break

    if cluster_key and cluster_key in adata.obs.columns:
        print(f"  Cluster key: '{cluster_key}' ({adata.obs[cluster_key].nunique()} groups)")
    else:
        print("  Warning: No cluster annotations found. PAGA requires clusters.")

    # Check for velocity layers
    has_velocity = "spliced" in adata.layers and "unspliced" in adata.layers
    if has_velocity:
        print("  RNA velocity layers detected (spliced/unspliced)")
    else:
        print("  No velocity layers — RNA velocity will be skipped")

    _validate_adata(adata, require_velocity_layers=False)

    print(f"✓ Data loaded successfully!")
    print(f"  Cells: {adata.n_obs:,}")
    print(f"  Genes: {adata.n_vars:,}")

    return adata


def _validate_adata(adata, require_velocity_layers=False):
    """
    Validate AnnData has minimum required structure.

    Parameters
    ----------
    adata : AnnData
        Object to validate.
    require_velocity_layers : bool
        If True, require spliced/unspliced layers.

    Raises
    ------
    ValueError
        If validation fails.
    """
    if adata.n_obs < 200:
        raise ValueError(
            f"Too few cells ({adata.n_obs}). Trajectory inference needs >= 200 cells "
            "for meaningful results."
        )

    if adata.n_vars < 100:
        raise ValueError(
            f"Too few genes ({adata.n_vars}). Trajectory inference needs >= 100 genes."
        )

    if require_velocity_layers:
        missing = []
        for layer in ["spliced", "unspliced"]:
            if layer not in adata.layers:
                missing.append(layer)
        if missing:
            raise ValueError(
                f"Missing required layers for RNA velocity: {missing}. "
                "These are needed for scVelo analysis."
            )
