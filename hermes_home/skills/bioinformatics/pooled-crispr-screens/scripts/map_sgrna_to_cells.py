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

# ============================================================
# 🔒 MemOmics 审查铁律 — 执行本脚本前后的强制步骤
# ============================================================
# 执行前必须: rail_review(action="pre")  — 环境检查 + 参数校验 + 代码审查
# 执行后必须: rail_review(action="post") — 结果质量评估 + 图表检查 + 数值检查
# 参数有争议: debate_analysis(topic=..., context=...) — 多角色辩论
# 执行失败:   skill_evolution(action="record_error") — 记录错误
# 修复成功:   skill_evolution(action="update_script") — 替换脚本
# ============================================================
"""
Map sgRNA Identities to Cells

This module maps sgRNA assignments to cell barcodes, filtering for cells with
single unambiguous sgRNA assignment.
"""

import pandas as pd
import anndata as ad
from typing import Optional


def map_sgrna_to_adata(
    adata: ad.AnnData,
    sgrna_mapping_file: str,
    sgrna_delimiter: str = "_",
    gene_position: int = 0
) -> ad.AnnData:
    """
    Map sgRNA identities to cells and extract target gene names.

    Parameters
    ----------
    adata : AnnData
        AnnData object with cell barcodes as obs_names
    sgrna_mapping_file : str
        Path to TSV file with columns: [cell_barcode, sgRNA_id]
        No header expected, tab-delimited
    sgrna_delimiter : str, default="_"
        Delimiter to split sgRNA ID to extract gene name
        (e.g., "GENE_sgRNA1" -> split by "_" -> "GENE")
    gene_position : int, default=0
        Position of gene name after splitting sgRNA ID

    Returns
    -------
    adata : AnnData
        Filtered AnnData with only mapped cells, adds:
        - adata.obs['sgRNA']: sgRNA identifier
        - adata.obs['gene']: target gene name

    Example
    -------
    >>> adata = map_sgrna_to_adata(
    ...     adata,
    ...     "mapped_single_sgRNA_to_cell_lib1.txt",
    ...     sgrna_delimiter="_"
    ... )
    >>> print(f"Mapping rate: {adata.n_obs}/{adata_original.n_obs}")
    """
    original_n_cells = adata.n_obs

    # Load sgRNA mapping file (no header, tab-delimited)
    # Column 0: cell barcode, Column 1: sgRNA ID
    df_sg_map = pd.read_table(
        sgrna_mapping_file,
        header=None,
        index_col=0
    )

    print(f"Loaded {len(df_sg_map)} sgRNA-cell mappings from {sgrna_mapping_file}")

    # Merge with adata.obs to keep only cells with sgRNA assignment
    mapped = adata.obs.merge(
        df_sg_map,
        left_index=True,
        right_index=True,
        how='inner'
    )

    mapped_cells = mapped.index

    # Filter adata to mapped cells only
    adata = adata[adata.obs.index.isin(mapped_cells), :].copy()

    # Add sgRNA column
    adata.obs['sgRNA'] = mapped[1]

    # Extract gene name from sgRNA ID
    adata.obs['gene'] = adata.obs['sgRNA'].apply(
        lambda x: x.split(sgrna_delimiter)[gene_position]
    )

    mapping_rate = adata.n_obs / original_n_cells * 100

    print(f"  Retained {adata.n_obs}/{original_n_cells} cells with sgRNA mapping ({mapping_rate:.1f}%)")
    print(f"  Unique sgRNAs: {adata.obs['sgRNA'].nunique()}")
    print(f"  Unique genes: {adata.obs['gene'].nunique()}")
    print("✓ sgRNA mapping complete")

    return adata


def check_mapping_quality(adata: ad.AnnData) -> pd.DataFrame:
    """
    Calculate mapping quality metrics.

    Parameters
    ----------
    adata : AnnData
        AnnData with 'gene' and 'sgRNA' in obs

    Returns
    -------
    stats : DataFrame
        Summary statistics: cells per gene, cells per sgRNA
    """
    stats = pd.DataFrame({
        'cells_per_gene': adata.obs.groupby('gene').size(),
        'sgrnas_per_gene': adata.obs.groupby('gene')['sgRNA'].nunique()
    })

    print("\nMapping Quality Metrics:")
    print(f"  Mean cells per gene: {stats['cells_per_gene'].mean():.1f}")
    print(f"  Median cells per gene: {stats['cells_per_gene'].median():.1f}")
    print(f"  Genes with <20 cells: {(stats['cells_per_gene'] < 20).sum()}")
    print(f"  Genes with <10 cells: {(stats['cells_per_gene'] < 10).sum()}")

    return stats
