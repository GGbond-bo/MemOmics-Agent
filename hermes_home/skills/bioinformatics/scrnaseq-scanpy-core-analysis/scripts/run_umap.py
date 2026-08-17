# 铁律：运行记录(query_logs)只是参考，不能跳过 rail_review/debate_analysis 审查
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
============================================================================
UMAP DIMENSIONALITY REDUCTION
============================================================================

This script performs UMAP for visualization.

Functions:
  - run_umap_reduction(): Compute UMAP embedding
  - run_tsne_reduction(): Compute t-SNE embedding (alternative)

Usage:
  from run_umap import run_umap_reduction
  adata = run_umap_reduction(adata, n_neighbors=10)
"""

from typing import Optional


def run_umap_reduction(
    adata: 'AnnData',
    n_neighbors: Optional[int] = None,
    min_dist: float = 0.5,
    spread: float = 1.0,
    random_state: int = 0,
    inplace: bool = True
) -> Optional['AnnData']:
    """
    Compute UMAP embedding.

    Parameters
    ----------
    adata : AnnData
        AnnData object with neighbor graph
    n_neighbors : int, optional
        Number of neighbors (default: use same as neighbor graph)
    min_dist : float, optional
        Minimum distance parameter (default: 0.5)
    spread : float, optional
        Spread parameter (default: 1.0)
    random_state : int, optional
        Random seed (default: 0)
    inplace : bool, optional
        Modify AnnData in place (default: True)

    Returns
    -------
    AnnData or None
        AnnData object with UMAP if inplace=False, else None
    """
    import scanpy as sc

    if not inplace:
        adata = adata.copy()

    if 'neighbors' not in adata.uns:
        raise ValueError("Neighbor graph not found. Run build_neighbor_graph first.")

    print("Running UMAP...")

    # Get n_neighbors from neighbor graph if not specified
    if n_neighbors is None:
        n_neighbors = adata.uns['neighbors']['params']['n_neighbors']

    print(f"  n_neighbors: {n_neighbors}")
    print(f"  min_dist: {min_dist}")
    print(f"  spread: {spread}")

    sc.tl.umap(
        adata,
        min_dist=min_dist,
        spread=spread,
        random_state=random_state
    )

    print("  UMAP complete")

    # Always return adata for convenience
    return adata


def run_tsne_reduction(
    adata: 'AnnData',
    n_pcs: Optional[int] = None,
    perplexity: float = 30,
    early_exaggeration: float = 12,
    learning_rate: float = 1000,
    random_state: int = 0,
    inplace: bool = True
) -> Optional['AnnData']:
    """
    Compute t-SNE embedding (alternative to UMAP).

    Parameters
    ----------
    adata : AnnData
        AnnData object with PCA
    n_pcs : int, optional
        Number of PCs to use (default: None, uses all)
    perplexity : float, optional
        Perplexity parameter (default: 30)
    early_exaggeration : float, optional
        Early exaggeration parameter (default: 12)
    learning_rate : float, optional
        Learning rate (default: 1000)
    random_state : int, optional
        Random seed (default: 0)
    inplace : bool, optional
        Modify AnnData in place (default: True)

    Returns
    -------
    AnnData or None
        AnnData object with t-SNE if inplace=False, else None
    """
    import scanpy as sc

    if not inplace:
        adata = adata.copy()

    if 'pca' not in adata.obsm:
        raise ValueError("PCA not found. Run run_pca_analysis first.")

    print("Running t-SNE...")

    if n_pcs is None:
        n_pcs = adata.obsm['X_pca'].shape[1]
        print(f"  Using all {n_pcs} PCs")
    else:
        print(f"  Using {n_pcs} PCs")

    print(f"  perplexity: {perplexity}")

    sc.tl.tsne(
        adata,
        n_pcs=n_pcs,
        perplexity=perplexity,
        early_exaggeration=early_exaggeration,
        learning_rate=learning_rate,
        random_state=random_state
    )

    print("  t-SNE complete")

    # Always return adata for convenience
    return adata


def run_diffmap(
    adata: 'AnnData',
    n_comps: int = 15,
    inplace: bool = True
) -> Optional['AnnData']:
    """
    Compute diffusion map (alternative dimensionality reduction).

    Useful for trajectory inference and continuous processes.

    Parameters
    ----------
    adata : AnnData
        AnnData object with neighbor graph
    n_comps : int, optional
        Number of diffusion components (default: 15)
    inplace : bool, optional
        Modify AnnData in place (default: True)

    Returns
    -------
    AnnData or None
        AnnData object with diffusion map if inplace=False, else None
    """
    import scanpy as sc

    if not inplace:
        adata = adata.copy()

    if 'neighbors' not in adata.uns:
        raise ValueError("Neighbor graph not found. Run build_neighbor_graph first.")

    print(f"Running diffusion map with {n_comps} components...")

    sc.tl.diffmap(adata, n_comps=n_comps)

    print("  Diffusion map complete")

    # Always return adata for convenience
    return adata
