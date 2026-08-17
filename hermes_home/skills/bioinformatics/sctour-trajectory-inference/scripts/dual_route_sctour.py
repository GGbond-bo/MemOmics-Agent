"""
Dual-Route scTour Analysis — 双路线独立 scTour 工作流
当数据中包含两条方向完全不同的独立生物学过程时，用此脚本拆分分析。

适用场景：SMF 亚群分析（去神经化路线 vs 应激→成熟路线）
          或任何包含两个独立过程的数据集。

使用方法：
  1. 修改 DATA 路径指向你的 h5ad 文件
  2. 修改 zone_a 和 zone_b 为你的亚群列表
  3. 修改 output_dir 为输出路径
  4. 运行：PYTHONPATH="" python dual_route_sctour.py

输出：
  routeA/ 和 routeB/ 目录下各含 2 个配置（run1_balanced, run2_encoder）
  每个配置含：figures/ (UMAP + 向量场 + 箱线图 + 年龄梯度 + Zone1内部)
              results/ (pseudotime.csv + zone_stats.csv + latent_space.npy)
"""
import scanpy as sc
import sctour as sct
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import os, json, time, warnings
warnings.filterwarnings('ignore')
from scipy.sparse import issparse
from scipy.stats import spearmanr

# ========== 配置区 ==========
DATA = "path/to/your_data.h5ad"  # 修改此处
OUTPUT_DIR = "results/scTour"
ZONE_A = ['zone1', 'zone2', 'NMJ', 'zone5', 'zone6']  # 路线A亚群
ZONE_B = ['zone3', 'zone4', 'zone5']                    # 路线B亚群
ZONE_A_ORDER = ['zone6', 'zone5', 'zone1', 'zone2', 'NMJ']  # 显示顺序
ZONE_B_ORDER = ['zone3', 'zone4', 'zone5']
N_TOP_GENES = 1500
NEPOCH = 200
CONFIGS = [
    {"name": "run1_balanced", "alpha_recon_lec": 0.5, "alpha_recon_lode": 0.5, "n_latent": 5},
    {"name": "run2_encoder", "alpha_recon_lec": 0.8, "alpha_recon_lode": 0.2, "n_latent": 8},
]
# ============================

def run_sctour_route(adata, route_name, zones, zone_order, out_dir, gene_gradient_genes=None):
    """Run scTour for one route with multiple configs. Supports checkpoint resume."""
    print(f"\n{'='*60}")
    print(f"路线{route_name}: {zones} ({adata.shape[0]} cells)")
    print(f"{'='*60}")
    
    if issparse(adata.X):
        adata.X = adata.X.toarray().astype('float32')
    else:
        adata.X = adata.X.astype('float32')
    
    n_cells = adata.shape[0]
    nepoch = min(round(10000 / n_cells * 400), NEPOCH)
    
    for cfg in CONFIGS:
        name = cfg["name"]
        run_dir = f"{out_dir}/{name}"
        os.makedirs(f"{run_dir}/figures", exist_ok=True)
        os.makedirs(f"{run_dir}/results", exist_ok=True)
        
        # === 检查点恢复：如果结果已存在且非空，跳过 ===
        csv_path = f"{run_dir}/results/pseudotime.csv"
        if os.path.isfile(csv_path) and os.path.getsize(csv_path) > 100:
            print(f"  ⏭ {name}: 已存在 pseudotime.csv ({os.path.getsize(csv_path)} bytes)，跳过")
            continue
        
        adata_run = adata.copy()
        t0 = time.time()
        tnode = sct.train.Trainer(adata_run, loss_mode='nb',
            alpha_recon_lec=cfg['alpha_recon_lec'],
            alpha_recon_lode=cfg['alpha_recon_lode'],
            n_latent=cfg['n_latent'], nepoch=nepoch,
            batch_size=1024, lr=1e-3, random_state=0,
            use_gpu=n_cells > 50000)  # CPU for <50k, GPU for >50k
        tnode.train()
        print(f"  {name}: {time.time()-t0:.0f}s")
        
        adata_run.obs['ptime'] = tnode.get_time()
        mix_zs, zs, pred_zs = tnode.get_latentsp(alpha_z=0.5, alpha_predz=0.5)
        adata_run.obsm['X_TNODE'] = mix_zs
        adata_run.obsm['X_VF'] = tnode.get_vector_field(
            adata_run.obs['ptime'].values, adata_run.obsm['X_TNODE'])
        
        # 保存结果
        result_df = pd.DataFrame({
            'cell_barcode': adata_run.obs_names,
            'ptime': adata_run.obs['ptime'].values,
            'subcluster': adata_run.obs['subcluster'].values,
            'type': adata_run.obs['type'].values if 'type' in adata_run.obs else '',
            'age': adata_run.obs['age'].values if 'age' in adata_run.obs else 0,
        })
        result_df.to_csv(f"{run_dir}/results/pseudotime.csv", index=False)
        np.save(f"{run_dir}/results/latent_space.npy", mix_zs)
        
        # 分组统计
        stats = []
        for zone in zone_order:
            mask = adata_run.obs['subcluster'] == zone
            if mask.sum() > 0:
                pt = adata_run.obs.loc[mask, 'ptime']
                age_col = 'age' if 'age' in adata_run.obs else None
                stats.append({
                    'zone': zone, 'mean_ptime': pt.mean(), 'std_ptime': pt.std(),
                    'median_ptime': pt.median(), 'n_cells': len(pt),
                    'mean_age': adata_run.obs.loc[mask, 'age'].mean() if age_col else 0
                })
        stats_df = pd.DataFrame(stats)
        stats_df.to_csv(f"{run_dir}/results/zone_stats.csv", index=False)
        
        # 年龄梯度 Spearman 验证
        if 'age' in adata_run.obs.columns:
            mean_pt = [stats_df[stats_df['zone']==z]['mean_ptime'].values[0] for z in zone_order if z in stats_df['zone'].values]
            mean_ag = [stats_df[stats_df['zone']==z]['mean_age'].values[0] for z in zone_order if z in stats_df['zone'].values]
            if len(mean_pt) >= 3:
                rho, p_val = spearmanr(mean_pt, mean_ag)
                print(f"  Age gradient: spearman_rho={rho:.3f}, p={p_val:.4f}")
        
        # 条件锚点分析（Condition Anchoring）：按条件分组统计伪时间
        if 'type' in adata_run.obs.columns:
            cond_stats = result_df.groupby(['type', 'subcluster'])['ptime'].agg(['mean','median','std','count']).round(3)
            cond_stats.to_csv(f"{run_dir}/results/condition_stats.csv")
            print(f"  Condition anchoring saved to condition_stats.csv")
            if 'zone1' in result_df['subcluster'].values:
                z1_cond = result_df[result_df['subcluster']=='zone1'].groupby('type')['ptime'].mean()
                for cond, pt in z1_cond.items():
                    marker = " ⚠️ 最低" if pt == z1_cond.min() else ""
                    print(f"  Condition anchor [{cond}] Zone1: ptime={pt:.3f}{marker}")
        
        # 可视化
        sc.pp.neighbors(adata_run, use_rep='X_TNODE', n_neighbors=15)
        sc.tl.umap(adata_run, min_dist=0.1)
        
        # UMAP
        fig, axes = plt.subplots(1, 3, figsize=(18, 5))
        sc.pl.umap(adata_run, color='ptime', cmap='viridis', ax=axes[0], show=False)
        sc.pl.umap(adata_run, color='subcluster', ax=axes[1], show=False)
        sc.pl.umap(adata_run, color='type' if 'type' in adata_run.obs else 'subcluster', ax=axes[2], show=False)
        plt.tight_layout()
        plt.savefig(f"{run_dir}/figures/umap_overview.png", dpi=150, bbox_inches='tight')
        plt.close()
        
        # 向量场
        fig, ax = plt.subplots(figsize=(10, 8))
        sct.vf.plot_vector_field(adata_run, zs_key='X_TNODE', vf_key='X_VF',
            use_rep_neigh='X_TNODE', t_key='ptime', color='subcluster', ax=ax, show=False, stream_density=1.5)
        plt.savefig(f"{run_dir}/figures/vector_field.png", dpi=150, bbox_inches='tight')
        plt.close()
        
        # 箱线图
        fig, ax = plt.subplots(figsize=(10, 6))
        data_list = [adata_run.obs.loc[adata_run.obs['subcluster']==z, 'ptime'].values for z in zone_order if (adata_run.obs['subcluster']==z).sum() > 0]
        labels = [z for z in zone_order if (adata_run.obs['subcluster']==z).sum() > 0]
        bp = ax.boxplot(data_list, tick_labels=labels, patch_artist=True)
        colors = ['#4ECDC4','#FF6B6B','#FFA07A','#45B7D1','#98D8C8','#DDA0DD']
        for patch, c in zip(bp['boxes'], colors[:len(labels)]): patch.set_facecolor(c)
        ax.set_title(f'{name}: Pseudotime by Zone')
        plt.savefig(f"{run_dir}/figures/pseudotime_boxplot.png", dpi=150, bbox_inches='tight')
        plt.close()
        
        # 年龄梯度双轴图
        if 'age' in adata_run.obs.columns:
            fig, ax1 = plt.subplots(figsize=(10, 6))
            x = np.arange(len(labels))
            mean_pt = [stats_df[stats_df['zone']==z]['mean_ptime'].values[0] for z in labels]
            mean_ag = [stats_df[stats_df['zone']==z]['mean_age'].values[0] for z in labels]
            ax1.bar(x - 0.2, mean_pt, 0.35, color='#45B7D1', alpha=0.8)
            ax1.set_ylabel('Mean Pseudotime', color='#45B7D1')
            ax1.tick_params(axis='y', labelcolor='#45B7D1')
            ax2 = ax1.twinx()
            ax2.plot(x, mean_ag, 'o-', color='#FF6B6B', linewidth=2, markersize=8)
            ax2.set_ylabel('Mean Age', color='#FF6B6B')
            ax1.set_xticks(x); ax1.set_xticklabels(labels)
            fig.tight_layout()
            fig.savefig(f"{run_dir}/figures/age_gradient.png", dpi=150, bbox_inches='tight')
            plt.close()
        
        # 单个亚群内部梯度分析（如 Zone1 内部 MYH7→RUNX1→COL19A1）
        if gene_gradient_genes and any(z in adata_run.obs['subcluster'].values for z in ['zone1']):
            target_zone = [z for z in ['zone1'] if z in adata_run.obs['subcluster'].values]
            if target_zone:
                z1 = adata_run[adata_run.obs['subcluster'] == target_zone[0]]
                if z1.shape[0] > 10:
                    valid_genes = [g for g in gene_gradient_genes if g in z1.var_names]
                    if valid_genes:
                        fig, ax = plt.subplots(figsize=(10, 5))
                        for g in valid_genes:
                            expr = z1[:, g].X.toarray().ravel() if hasattr(z1[:,g].X, 'toarray') else z1[:,g].X.ravel()
                            order = np.argsort(z1.obs['ptime'].values)
                            ax.plot(z1.obs['ptime'].values[order], expr[order], '.', markersize=1, alpha=0.3, label=g)
                        ax.set_xlabel('Pseudotime')
                        ax.set_ylabel('Expression')
                        ax.set_title(f'{name}: {target_zone[0]} internal gene gradient')
                        ax.legend()
                        plt.savefig(f"{run_dir}/figures/zone1_gene_gradient.png", dpi=150, bbox_inches='tight')
                        plt.close()

# ========== 主程序 ==========
adata = sc.read(DATA)
if 'counts' in adata.layers:
    adata.X = adata.layers['counts'].copy().astype('float32')
if 'n_genes_by_counts' not in adata.obs.columns:
    sc.pp.calculate_qc_metrics(adata, percent_top=None, log1p=False, inplace=True)

# 路线A
route_a = adata[adata.obs['subcluster'].isin(ZONE_A)].copy()
sc.pp.highly_variable_genes(route_a, flavor='seurat_v3', n_top_genes=N_TOP_GENES, subset=True)
run_sctour_route(route_a, "A", ZONE_A, ZONE_A_ORDER, f"{OUTPUT_DIR}/routeA",
                 gene_gradient_genes=['MYH7', 'RUNX1', 'COL19A1'])

# 路线B
route_b = adata[adata.obs['subcluster'].isin(ZONE_B)].copy()
sc.pp.highly_variable_genes(route_b, flavor='seurat_v3', n_top_genes=N_TOP_GENES, subset=True)
run_sctour_route(route_b, "B", ZONE_B, ZONE_B_ORDER, f"{OUTPUT_DIR}/routeB")

print("\n✅ 双路线 scTour 分析完成！")