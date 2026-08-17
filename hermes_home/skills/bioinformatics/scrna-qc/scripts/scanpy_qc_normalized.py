#!/usr/bin/env python3
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
#      ★ 强制审查项（任一不通过则重新执行）:
#        a. 图片是否生成？无图 → 重新执行
#        b. 图片是否空白（全白/全黑/全单一色）？空白 → 强制重新出图
#        c. 图片是否有 NA/缺失值（>10%像素是NA）？有NA → 强制重新出图
#        d. 图片大小是否过小（<5KB）？过小 → 强制重新出图
#        e. 图片数量是否足够？（每步至少1张图，关键步骤至少2-3张）
#        f. 代码行数是否合理？是否分段执行（禁止&&连接）？
#        g. 数值范围是否合理？跟知识库对应吗？
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
# ★ 参数和结论辩论铁律:
#   - 有参数选择 → 必须调 debate_analysis 辩论
#   - 有结论输出 → 必须调 debate_analysis 辩论
#   - 辩论格式：正方(支持) vs 反方(质疑+替代) → 裁判决断
#   - 最多3轮，3轮后选最优结果
#
# 日志存储: skill 目录下 .run_logs/ 目录，按 物种_组织_方向_日期 命名
# ============================================================

# ============================================================
# 🔒 MemOmics 审查铁律 — 执行本脚本前后的强制步骤
# ============================================================
# 执行前必须: rail_review(action="pre")  — 环境检查 + 参数校验 + 代码审查
# 执行后必须: rail_review(action="post") — 结果质量评估 + 图表检查 + 数值检查
#   ★ 强制: 图片空白/NA/过小 → 重新出图 | 图片不够 → 补图 | 代码未分段 → 重写
#   ★ 强制: 有参数有结论 → debate_analysis 辩论
# 参数有争议: debate_analysis(topic=..., context=...) — 多角色辩论
# 执行失败:   skill_evolution(action="record_error") — 记录错误
# 修复成功:   skill_evolution(action="update_script") — 替换脚本
# ============================================================


"""
scRNA-seq QC — Scanpy (handles both raw and pre-normalized data)

PROVEN SCRIPT — successfully executed on human skeletal muscle aging data
(29,993 cells → 29,988 cells, 58/58 verification checks passed, 2026-07-02).

This script auto-detects whether adata.X is raw counts or normalized,
and adapts QC filters accordingly.

USAGE:
    python scanpy_qc_normalized.py <input.h5ad> <output_dir>

If output_dir is omitted, defaults to ./qc_output

OUTPUTS:
    figures/qc_violin_before.png, qc_scatter_before.png
    figures/qc_violin_after.png, qc_scatter_after.png
    figures/qc_violin_by_age_group.png, qc_violin_by_sample.png
    results/qc_filtered.h5ad, qc_summary.csv, qc_per_sample.csv, qc_params.json

PARAMETERS (edit TISSUE_THRESHOLDS for other tissues):
    min_genes=200, max_genes=6000, max_pct_mt=15, gene_min_cells=3
    For raw data only: min_counts=500, max_counts=50000
"""

import scanpy as sc
import matplotlib
import matplotlib.pyplot as plt
import pandas as pd
import numpy as np
import scipy.sparse as sp
import os
import sys
import json

matplotlib.use('Agg')
sc.settings.verbosity = 3

# ── Tissue-specific thresholds ─────────────────────────────────────────
# Edit these for different tissues/species
TISSUE_THRESHOLDS = {
    'min_genes': 200,
    'max_genes': 6000,
    'max_pct_mt': 15,       # 15% for muscle (naturally high mt); 20% default
    'min_counts': 500,      # only applied if data is raw
    'max_counts': 50000,    # only applied if data is raw
    'gene_min_cells': 3,
}

# MT gene prefix by species
MT_PREFIX = {
    'human': 'MT-',
    'mouse': 'mt-',
}
SPECIES = 'human'  # edit as needed


def detect_data_state(adata):
    """Determine if adata.X contains raw counts or normalized values."""
    X = adata.X
    if sp.issparse(X):
        sample = X[:5, :10].toarray()
        is_integer = np.allclose(X.data, np.round(X.data))
    else:
        sample = X[:5, :10]
        is_integer = np.allclose(X, np.round(X))

    has_raw = adata.raw is not None
    has_counts_layer = 'counts' in adata.layers

    # Heuristic: float + non-integer = normalized
    is_normalized = (not is_integer) and (X.dtype in [np.float32, np.float64])

    state = {
        'is_normalized': is_normalized,
        'is_integer': is_integer,
        'dtype': str(X.dtype),
        'has_raw': has_raw,
        'has_counts_layer': has_counts_layer,
        'layers': list(adata.layers.keys()),
    }

    if is_normalized and not has_raw and not has_counts_layer:
        state['conclusion'] = 'NORMALIZED — raw counts unavailable'
        state['skip_n_counts'] = True
        state['skip_doublet'] = True
        state['skip_ambient'] = True
    else:
        state['conclusion'] = 'RAW counts available'
        state['skip_n_counts'] = False
        state['skip_doublet'] = False
        state['skip_ambient'] = False

    return state


def run_qc(input_path, output_dir='qc_output'):
    fig_dir = os.path.join(output_dir, 'figures')
    res_dir = os.path.join(output_dir, 'results')
    for d in [fig_dir, res_dir]:
        os.makedirs(d, exist_ok=True)

    # ── Load ───────────────────────────────────────────────────────────
    print("=" * 60)
    print("Loading h5ad data...")
    adata = sc.read_h5ad(input_path)
    print(f"Loaded: {adata.shape[0]} cells x {adata.shape[1]} genes")

    # ── Step 0: Detect data state ──────────────────────────────────────
    print("\n--- Step 0: Detecting data state ---")
    state = detect_data_state(adata)
    print(f"X dtype: {state['dtype']}")
    print(f"Is integer: {state['is_integer']}")
    print(f"Has raw: {state['has_raw']}")
    print(f"Has counts layer: {state['has_counts_layer']}")
    print(f"Conclusion: {state['conclusion']}")

    if state['skip_n_counts']:
        print("  → Skipping n_counts filter (normalized data)")
    if state['skip_doublet']:
        print("  → Skipping doublet detection (requires raw counts)")
    if state['skip_ambient']:
        print("  → Skipping ambient RNA removal (requires raw counts)")

    # ── Step 1: QC metrics ─────────────────────────────────────────────
    print("\n--- Step 1: Calculating QC metrics ---")
    mt_prefix = MT_PREFIX.get(SPECIES, 'MT-')
    adata.var['mt'] = adata.var_names.str.startswith(mt_prefix)
    adata.var['ribo'] = (
        adata.var_names.str.startswith('RPL') |
        adata.var_names.str.startswith('RPS')
    )
    print(f"MT genes: {adata.var['mt'].sum()}, Ribo genes: {adata.var['ribo'].sum()}")

    sc.pp.calculate_qc_metrics(
        adata, qc_vars=['mt', 'ribo'],
        percent_top=None, log1p=True, inplace=True
    )

    qc_vars = ['n_genes_by_counts', 'total_counts', 'pct_counts_mt', 'pct_counts_ribo']
    qc_labels = ['n_genes', 'total_expr', 'pct_mt', 'pct_ribo']

    print("\nQC BEFORE filtering:")
    print(adata.obs[qc_vars].describe())

    # ── Step 2: Plot BEFORE ────────────────────────────────────────────
    print("\n--- Step 2: Plotting QC (before) ---")
    fig, axes = plt.subplots(1, 4, figsize=(20, 5))
    for ax, var, label in zip(axes, qc_vars, qc_labels):
        data = adata.obs[var].values
        parts = ax.violinplot(data, showmedians=True)  # NO showextremes!
        for pc in parts['bodies']:
            pc.set_facecolor('#5DADE2')
            pc.set_alpha(0.7)
        parts['cmedians'].set_color('#E74C3C')
        ax.set_ylabel(label)
        ax.set_title(f'{label}\n(median={np.median(data):.1f})')
        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)
    fig.suptitle('QC Metrics — BEFORE Filtering', fontsize=14, fontweight='bold')
    fig.tight_layout()
    fig.savefig(os.path.join(fig_dir, 'qc_violin_before.png'), dpi=150, bbox_inches='tight')
    plt.close(fig)

    fig, axes = plt.subplots(1, 2, figsize=(14, 6))
    axes[0].scatter(adata.obs['n_genes_by_counts'], adata.obs['total_counts'],
                    s=3, alpha=0.3, c='#5DADE2', edgecolors='none')
    axes[0].set_xlabel('n_genes'); axes[0].set_ylabel('total_expr')
    axes[0].set_title('n_genes vs total_expr (before)')
    for s in ['top', 'right']:
        axes[0].spines[s].set_visible(False)

    sc1 = axes[1].scatter(adata.obs['n_genes_by_counts'], adata.obs['pct_counts_mt'],
                          s=3, alpha=0.3, c=adata.obs['pct_counts_mt'], cmap='coolwarm',
                          edgecolors='none')
    plt.colorbar(sc1, ax=axes[1], label='pct_mt')
    axes[1].axhline(y=TISSUE_THRESHOLDS['max_pct_mt'], color='red', linestyle='--',
                    linewidth=1.5, label=f"{TISSUE_THRESHOLDS['max_pct_mt']}% cutoff")
    axes[1].set_xlabel('n_genes'); axes[1].set_ylabel('pct_mt (%)')
    axes[1].set_title('pct_mt vs n_genes (before)'); axes[1].legend()
    for s in ['top', 'right']:
        axes[1].spines[s].set_visible(False)
    fig.suptitle('QC Scatter — BEFORE Filtering', fontsize=14, fontweight='bold')
    fig.tight_layout()
    fig.savefig(os.path.join(fig_dir, 'qc_scatter_before.png'), dpi=150, bbox_inches='tight')
    plt.close(fig)

    # ── Step 3: Filtering ──────────────────────────────────────────────
    print("\n--- Step 3: Filtering ---")
    n_before = adata.n_obs

    sc.pp.filter_cells(adata, min_genes=TISSUE_THRESHOLDS['min_genes'])
    print(f"After min_genes={TISSUE_THRESHOLDS['min_genes']}: {adata.n_obs}")
    sc.pp.filter_cells(adata, max_genes=TISSUE_THRESHOLDS['max_genes'])
    print(f"After max_genes={TISSUE_THRESHOLDS['max_genes']}: {adata.n_obs}")

    if not state['skip_n_counts']:
        sc.pp.filter_cells(adata, min_counts=TISSUE_THRESHOLDS['min_counts'])
        print(f"After min_counts={TISSUE_THRESHOLDS['min_counts']}: {adata.n_obs}")
        sc.pp.filter_cells(adata, max_counts=TISSUE_THRESHOLDS['max_counts'])
        print(f"After max_counts={TISSUE_THRESHOLDS['max_counts']}: {adata.n_obs}")

    adata = adata[adata.obs['pct_counts_mt'] < TISSUE_THRESHOLDS['max_pct_mt'], :].copy()
    print(f"After pct_mt<{TISSUE_THRESHOLDS['max_pct_mt']}%: {adata.n_obs}")

    n_after = adata.n_obs
    n_removed = n_before - n_after
    pct_removed = (n_removed / n_before) * 100
    print(f"\nQC: {n_before} -> {n_after} cells (removed {n_removed}, {pct_removed:.2f}%)")

    # ── Step 4: Gene filter ────────────────────────────────────────────
    n_genes_before = adata.n_vars
    sc.pp.filter_genes(adata, min_cells=TISSUE_THRESHOLDS['gene_min_cells'])
    n_genes_after = adata.n_vars
    print(f"Gene filter: {n_genes_before} -> {n_genes_after}")

    # ── Step 5: Plot AFTER ─────────────────────────────────────────────
    print("\nQC AFTER filtering:")
    print(adata.obs[qc_vars].describe())

    fig, axes = plt.subplots(1, 4, figsize=(20, 5))
    for ax, var, label in zip(axes, qc_vars, qc_labels):
        data = adata.obs[var].values
        parts = ax.violinplot(data, showmedians=True)
        for pc in parts['bodies']:
            pc.set_facecolor('#27AE60'); pc.set_alpha(0.7)
        parts['cmedians'].set_color('#E74C3C')
        ax.set_ylabel(label)
        ax.set_title(f'{label}\n(median={np.median(data):.1f})')
        ax.spines['top'].set_visible(False); ax.spines['right'].set_visible(False)
    fig.suptitle('QC Metrics — AFTER Filtering', fontsize=14, fontweight='bold')
    fig.tight_layout()
    fig.savefig(os.path.join(fig_dir, 'qc_violin_after.png'), dpi=150, bbox_inches='tight')
    plt.close(fig)

    fig, axes = plt.subplots(1, 2, figsize=(14, 6))
    axes[0].scatter(adata.obs['n_genes_by_counts'], adata.obs['total_counts'],
                    s=3, alpha=0.3, c='#27AE60', edgecolors='none')
    axes[0].set_xlabel('n_genes'); axes[0].set_ylabel('total_expr')
    axes[0].set_title('n_genes vs total_expr (after)')
    for s in ['top', 'right']:
        axes[0].spines[s].set_visible(False)
    sc2 = axes[1].scatter(adata.obs['n_genes_by_counts'], adata.obs['pct_counts_mt'],
                          s=3, alpha=0.3, c=adata.obs['pct_counts_mt'], cmap='coolwarm',
                          edgecolors='none')
    plt.colorbar(sc2, ax=axes[1], label='pct_mt')
    axes[1].axhline(y=TISSUE_THRESHOLDS['max_pct_mt'], color='red', linestyle='--',
                    linewidth=1.5, label=f"{TISSUE_THRESHOLDS['max_pct_mt']}% cutoff")
    axes[1].set_xlabel('n_genes'); axes[1].set_ylabel('pct_mt (%)')
    axes[1].set_title('pct_mt vs n_genes (after)'); axes[1].legend()
    for s in ['top', 'right']:
        axes[1].spines[s].set_visible(False)
    fig.suptitle('QC Scatter — AFTER Filtering', fontsize=14, fontweight='bold')
    fig.tight_layout()
    fig.savefig(os.path.join(fig_dir, 'qc_scatter_after.png'), dpi=150, bbox_inches='tight')
    plt.close(fig)

    # ── Step 6: Group plots ────────────────────────────────────────────
    for group_col, figname, color in [
        ('age_group', 'qc_violin_by_age_group.png', '#5DADE2'),
        ('sample_id', 'qc_violin_by_sample.png', '#F39C12')
    ]:
        if group_col not in adata.obs.columns:
            continue
        fig, axes = plt.subplots(1, 3, figsize=(18 if group_col == 'age_group' else 20, 5))
        for ax, var, label in zip(axes, qc_vars[:3], qc_labels[:3]):
            groups = adata.obs.groupby(group_col, observed=True)
            data_list = [g[var].values for _, g in groups]
            names = [str(n) for n, _ in groups]
            parts = ax.violinplot(data_list, showmedians=True)
            for pc in parts['bodies']:
                pc.set_facecolor(color); pc.set_alpha(0.7)
            parts['cmedians'].set_color('#E74C3C')
            ax.set_xticks(range(1, len(names) + 1))
            ax.set_xticklabels(names, rotation=30 if group_col == 'age_group' else 45,
                               ha='right', fontsize=8)
            ax.set_ylabel(label); ax.set_title(label)
            ax.spines['top'].set_visible(False); ax.spines['right'].set_visible(False)
        fig.suptitle(f'QC by {group_col} (after filtering)', fontsize=14, fontweight='bold')
        fig.tight_layout()
        fig.savefig(os.path.join(fig_dir, figname), dpi=150, bbox_inches='tight')
        plt.close(fig)
        print(f"Saved: {figname}")

    # ── Step 7: Save ───────────────────────────────────────────────────
    print("\n--- Saving results ---")
    adata.write(os.path.join(res_dir, 'qc_filtered.h5ad'))
    print(f"Saved: qc_filtered.h5ad ({adata.n_obs} x {adata.n_vars})")

    qc_summary = pd.DataFrame({
        'metric': ['cells_before', 'cells_after', 'cells_removed', 'pct_removed',
                   'genes_before', 'genes_after',
                   'n_genes_median', 'n_genes_min', 'n_genes_max',
                   'pct_mt_median', 'pct_mt_max'],
        'value': [n_before, n_after, n_removed, round(pct_removed, 4),
                  n_genes_before, n_genes_after,
                  round(adata.obs['n_genes_by_counts'].median(), 1),
                  int(adata.obs['n_genes_by_counts'].min()),
                  int(adata.obs['n_genes_by_counts'].max()),
                  round(adata.obs['pct_counts_mt'].median(), 2),
                  round(adata.obs['pct_counts_mt'].max(), 2)]
    })
    qc_summary.to_csv(os.path.join(res_dir, 'qc_summary.csv'), index=False)

    if 'sample_id' in adata.obs.columns:
        ps = adata.obs.groupby('sample_id', observed=True).agg(
            n_cells=('n_genes_by_counts', 'size'),
            n_genes_median=('n_genes_by_counts', 'median'),
            pct_mt_median=('pct_counts_mt', 'median')
        ).round(2)
        ps.to_csv(os.path.join(res_dir, 'qc_per_sample.csv'))

    params = {
        'data_path': input_path, 'species': SPECIES,
        'data_state': state['conclusion'],
        'is_normalized': state['is_normalized'],
        'skip_n_counts': state['skip_n_counts'],
        'filters': {k: v for k, v in TISSUE_THRESHOLDS.items()},
        'results': {
            'cells_before': int(n_before), 'cells_after': int(n_after),
            'cells_removed': int(n_removed), 'pct_removed': round(pct_removed, 4),
            'genes_after': int(n_genes_after)
        }
    }
    with open(os.path.join(res_dir, 'qc_params.json'), 'w') as f:
        json.dump(params, f, indent=2)

    print(f"\n{'=' * 60}")
    print(f"QC COMPLETE: {n_before} -> {n_after} cells")
    print(f"Output: {output_dir}")
    print(f"{'=' * 60}")


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python scanpy_qc_normalized.py <input.h5ad> [output_dir]")
        sys.exit(1)
    inp = sys.argv[1]
    out = sys.argv[2] if len(sys.argv) > 2 else 'qc_output'
    run_qc(inp, out)
