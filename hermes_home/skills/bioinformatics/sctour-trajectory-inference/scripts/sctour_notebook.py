#!/usr/bin/env python3
"""
scTour 完整工作流 Notebook (Jupyter)
=====================================
将以下代码复制到 Jupyter Notebook (.ipynb) 中，按顺序运行每个 Cell。

# ============================================================
# 🔒 MemOmics 审查铁律 (执行本 Notebook 前必须完成)
# ============================================================
#   1. rail_review(action="pre")     — 检查环境/参数/数据
#   2. skill_evolution(action="query_logs") — 查同类运行日志
#   3. debate_analysis(topic, context) — 参数不确定时多角色辩论
#   4. rail_review(action="post") — 执行后检查输出/质量/图表
# ============================================================

使用方法:
    jupyter notebook
    打开后新建 .ipynb，将各 Cell 按顺序粘贴进去运行即可。
"""

# ╔══════════════════════════════════════════════════════════════╗
# ║  Cell 0: 环境准备 + 导入                                     ║
# ╚══════════════════════════════════════════════════════════════╝

# ## Cell 0: 环境准备 + 导入
# 安装 scTour（如未安装）并导入所有需要的包

# 安装 scTour + scikit-misc（flavor='seurat_v3' 需要）
# !pip install sctour scikit-misc --quiet

import sctour as sct
import scanpy as sc
import anndata as ad
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import torch
import warnings
warnings.filterwarnings('ignore')

# 设置 matplotlib 风格
sc.settings.set_figure_params(dpi=100, frameon=False, color_map='viridis')
sc.settings.verbosity = 1  # 减少输出

print(f"scTour version: {sct.__version__}")
print(f"PyTorch version: {torch.__version__}")
print(f"GPU available: {torch.cuda.is_available()}")
if torch.cuda.is_available():
    print(f"GPU: {torch.cuda.get_device_name(0)}")


# ╔══════════════════════════════════════════════════════════════╗
# ║  Cell 1: 加载数据                                            ║
# ╚══════════════════════════════════════════════════════════════╝

# ## Cell 1: 加载数据
# 从 h5ad 文件加载你的 scRNA-seq 数据
# 修改 DATA_PATH 为你的数据路径

DATA_PATH = "your_data.h5ad"  # ← 改成你的数据路径

adata = sc.read_h5ad(DATA_PATH)
print(f"数据形状: {adata.shape}")
print(f"obs 列: {adata.obs.columns.tolist()}")
print(f"细胞数: {adata.n_obs}")
print(f"基因数: {adata.n_vars}")


# ╔══════════════════════════════════════════════════════════════╗
# ║  Cell 2: 预处理 (Step 1/6)                                   ║
# ╚══════════════════════════════════════════════════════════════╝

# ## Cell 2: 预处理 (Step 1/6)
# 必须: 计算 QC metrics + 选择高变基因 + 子采样

# 获取原始计数矩阵
# 如果数据已经过标准化，需要从 raw 或 layers 中获取原始 counts
if adata.raw is not None:
    counts = adata.raw.X
    print("使用 adata.raw 作为原始计数")
elif 'counts' in adata.layers:
    counts = adata.layers['counts']
    print("使用 adata.layers['counts'] 作为原始计数")
else:
    counts = adata.X
    print("使用 adata.X 作为计数（假设未标准化）")

# 确保 adata.X 是原始计数（scTour Trainer 需要原始 counts）
from scipy.sparse import issparse, csr_matrix
if not issparse(counts):
    counts = csr_matrix(counts)
adata.X = counts

# ★ 必须: 计算 QC metrics（scTour 的 get_time() 需要 'n_genes_by_counts' 列）
sc.pp.calculate_qc_metrics(adata, percent_top=None, log1p=False, inplace=True)
print(f"n_genes_by_counts 范围: {adata.obs['n_genes_by_counts'].min():.0f} - {adata.obs['n_genes_by_counts'].max():.0f}")
print(f"total_counts 范围: {adata.obs['total_counts'].min():.0f} - {adata.obs['total_counts'].max():.0f}")

# ★ 必须: 选择高变基因（scTour 官方教程要求，减少噪声 + 加速训练）
N_TOP_GENES = 1000  # 高变基因数，推荐 1000-2000
print(f"选择 {N_TOP_GENES} 个高变基因 (Seurat v3)...")
sc.pp.highly_variable_genes(adata, flavor='seurat_v3', n_top_genes=N_TOP_GENES, subset=True)
print(f"高变基因筛选后: {adata.shape}")

# ★ 必须: 转换为 float32（避免 PyTorch dtype 不匹配）
# AnnData 默认 float64 (Double)，PyTorch 模型用 float32 (Float)
# 不转换会报错: RuntimeError: mat1 and mat2 must have the same dtype, but got Double and Float
from scipy.sparse import issparse
if issparse(adata.X):
    adata.X.data = adata.X.data.astype('float32')
else:
    adata.X = adata.X.astype('float32')
print(f"数据类型已转换: {adata.X.dtype}")

# 可选: 对超大数据进行子采样以提高速度
N_MAX_CELLS = 50000  # 如果细胞数过多，随机子采样
if adata.n_obs > N_MAX_CELLS:
    print(f"⚠️ 细胞数 {adata.n_obs} > {N_MAX_CELLS}，随机子采样 {N_MAX_CELLS} 个细胞")
    sc.pp.subsample(adata, n_obs=N_MAX_CELLS)
    print(f"子采样后: {adata.n_obs} 细胞")


# ╔══════════════════════════════════════════════════════════════╗
# ║  Cell 3: 训练模型 (Step 2/6)                                 ║
# ╚══════════════════════════════════════════════════════════════╝

# ## Cell 3: 训练 scTour 模型 (Step 2/6)
# ⚠️ 这是最耗时的步骤，可能需要 10-60 分钟
#
# 关键参数说明:
#   alpha_recon_lec: 重构损失中编码器部分的权重 (默认 0.5)
#   alpha_recon_lode: 重构损失中解码器部分的权重 (默认 0.5)
#     → alpha_recon_lec + alpha_recon_lode 必须等于 1.0
#   loss_mode: 'mse' | 'nb' | 'zinb'
#     → scRNA-seq 推荐 'zinb'（零膨胀负二项）
#   n_latent: 潜在空间维度 (默认 128, 范围 64-256)
#   epochs: 训练轮数 (默认 1000, 可根据数据量调整)
#   batch_size: 批次大小 (默认 256)

# ============ 可调参数 ============
ALPHA_RECON_LEC = 0.5          # 编码器重构权重
ALPHA_RECON_LODE = 0.5         # 解码器重构权重 → 必须满足 lec + lode = 1.0
ALPHA_Z = 0.5                  # 潜在空间正则化权重
ALPHA_PREDZ = 0.5              # 预测潜在空间权重
LOSS_MODE = 'zinb'             # 损失函数: 'mse' | 'nb' | 'zinb'
N_LATENT = 128                 # 潜在空间维度
EPOCHS = 2000                  # 训练轮数
BATCH_SIZE = 256               # 批次大小
LEARNING_RATE = 1e-3           # 学习率
# ================================

assert abs(ALPHA_RECON_LEC + ALPHA_RECON_LODE - 1.0) < 1e-6, \
    "alpha_recon_lec + alpha_recon_lode 必须等于 1.0!"

print("=" * 60)
print("scTour 训练参数:")
print(f"  loss_mode:       {LOSS_MODE}")
print(f"  n_latent:        {N_LATENT}")
print(f"  epochs:          {EPOCHS}")
print(f"  batch_size:      {BATCH_SIZE}")
print(f"  alpha_recon_lec: {ALPHA_RECON_LEC}")
print(f"  alpha_recon_lode:{ALPHA_RECON_LODE}")
print(f"  alpha_z:         {ALPHA_Z}")
print(f"  alpha_predz:     {ALPHA_PREDZ}")
print("=" * 60)

# 初始化模型
tnode = sct.train.Trainer(
    adata,
    loss_mode=LOSS_MODE,
    alpha_recon_lec=ALPHA_RECON_LEC,
    alpha_recon_lode=ALPHA_RECON_LODE,
    alpha_z=ALPHA_Z,
    alpha_predz=ALPHA_PREDZ,
    n_latent=N_LATENT,
    batch_size=BATCH_SIZE,
    lr=LEARNING_RATE,
    device='cuda' if torch.cuda.is_available() else 'cpu',
)

# 训练
print("\n开始训练...")
tnode.train(num_epochs=EPOCHS)
print("训练完成!")


# ╔══════════════════════════════════════════════════════════════╗
# ║  Cell 4: 提取伪时间 (Step 3/6)                               ║
# ╚══════════════════════════════════════════════════════════════╝

# ## Cell 4: 提取伪时间 (Step 3/6)
# 从训练好的模型中提取每个细胞的伪时间值

# 获取伪时间 (scTour v1.0.0 API: tnode.get_time())
# 注意: 需要 adata.obs['n_genes_by_counts'] 列（已在预处理中创建）
adata.obs['pseudotime'] = tnode.get_time()

# 查看伪时间分布
print(f"伪时间范围: {adata.obs['pseudotime'].min():.4f} - {adata.obs['pseudotime'].max():.4f}")
print(f"伪时间均值:  {adata.obs['pseudotime'].mean():.4f}")
print(f"伪时间中位数:{adata.obs['pseudotime'].median():.4f}")

# 快速可视化伪时间分布
fig, ax = plt.subplots(1, 2, figsize=(10, 4))
ax[0].hist(adata.obs['pseudotime'], bins=50, color='steelblue', edgecolor='white')
ax[0].set_xlabel('Pseudotime')
ax[0].set_ylabel('Cell Count')
ax[0].set_title('Pseudotime Distribution')

ax[1].boxplot(adata.obs['pseudotime'].values, vert=True)
ax[1].set_ylabel('Pseudotime')
ax[1].set_title('Pseudotime Boxplot')
plt.tight_layout()
plt.show()


# ╔══════════════════════════════════════════════════════════════╗
# ║  Cell 5: 提取潜在空间 (Step 4/6)                             ║
# ╚══════════════════════════════════════════════════════════════╝

# ## Cell 5: 提取潜在空间嵌入 (Step 4/6)
# 获取 scTour 学习的潜在空间表示

# 获取潜在空间嵌入 (scTour v1.0.0 API: tnode.get_latentsp())
# 返回 3-tuple: (mix_zs, zs, pred_zs)
#   mix_zs = 加权组合潜在空间 ← 用于下游分析
#   zs     = 编码器推导的潜在空间
#   pred_zs = ODE 求解器推导的潜在空间
mix_zs, zs, pred_zs = tnode.get_latentsp(alpha_z=ALPHA_Z, alpha_predz=ALPHA_PREDZ)

# 存入 adata（使用加权组合潜在空间）
adata.obsm['X_sctour'] = mix_zs
print(f"潜在空间形状: {adata.obsm['X_sctour'].shape}")
print(f"维度: {adata.obsm['X_sctour'].shape[1]}")

# 用潜在空间做 UMAP（可选，用于可视化）
sc.pp.neighbors(adata, use_rep='X_sctour', n_neighbors=30)
sc.tl.umap(adata)
print("UMAP 完成 (基于 scTour 潜在空间)")


# ╔══════════════════════════════════════════════════════════════╗
# ║  Cell 6: 向量场 (Step 5/6)                                   ║
# ╚══════════════════════════════════════════════════════════════╝

# ## Cell 6: 计算向量场 (Step 5/6)
# 在潜在空间中计算向量场，揭示发育/分化方向

# 计算向量场 (scTour v1.0.0 API: tnode.get_vector_field(T, Z))
# 参数: T = 伪时间数组, Z = 潜在空间矩阵
adata.obsm['X_sctour_vector_field'] = tnode.get_vector_field(
    adata.obs['pseudotime'].values,
    adata.obsm['X_sctour'],
)

print(f"向量场形状: {adata.obsm['X_sctour_vector_field'].shape}")

# 计算向量场强度（用于可视化着色）
vf_magnitude = np.linalg.norm(adata.obsm['X_sctour_vector_field'], axis=1)
adata.obs['vector_field_magnitude'] = vf_magnitude
print(f"向量场强度范围: {vf_magnitude.min():.4f} - {vf_magnitude.max():.4f}")


# ╔══════════════════════════════════════════════════════════════╗
# ║  Cell 7: 可视化 - UMAP (Step 6/6, Part 1)                    ║
# ╚══════════════════════════════════════════════════════════════╝

# ## Cell 7: 可视化 - UMAP 嵌入 (Step 6/6, Part 1)
# 用 scTour 潜在空间 UMAP 展示细胞分布

# 按细胞类型着色（如果有注释）
color_by = None
if 'cell_type' in adata.obs.columns:
    color_by = 'cell_type'
elif 'CellType' in adata.obs.columns:
    color_by = 'CellType'
elif 'celltype' in adata.obs.columns:
    color_by = 'celltype'
elif 'cluster' in adata.obs.columns:
    color_by = 'cluster'

if color_by:
    sc.pl.umap(adata, color=color_by, title=f'scTour UMAP - {color_by}',
               frameon=False, legend_loc='right margin')
else:
    sc.pl.umap(adata, title='scTour UMAP', frameon=False)

# 按批次/样本着色（如果有）
batch_col = None
for col in ['batch', 'sample', 'Sample', 'sample_id', 'orig.ident']:
    if col in adata.obs.columns:
        batch_col = col
        break

if batch_col:
    sc.pl.umap(adata, color=batch_col, title=f'scTour UMAP - {batch_col}',
               frameon=False, legend_loc='right margin')


# ╔══════════════════════════════════════════════════════════════╗
# ║  Cell 8: 可视化 - 伪时间 (Step 6/6, Part 2)                  ║
# ╚══════════════════════════════════════════════════════════════╝

# ## Cell 8: 可视化 - 伪时间着色 (Step 6/6, Part 2)
# 在 UMAP 上展示伪时间，越亮的细胞处于越晚的发育阶段

# 伪时间 UMAP
sc.pl.umap(adata, color='pseudotime', title='scTour Pseudotime',
           frameon=False, cmap='viridis')

# 也可以尝试其他色彩映射
sc.pl.umap(adata, color='pseudotime', title='scTour Pseudotime (plasma)',
           frameon=False, cmap='plasma')


# ╔══════════════════════════════════════════════════════════════╗
# ║  Cell 9: 可视化 - 向量场 (Step 6/6, Part 3)                  ║
# ╚══════════════════════════════════════════════════════════════╝

# ## Cell 9: 可视化 - 向量场 (Step 6/6, Part 3)
# 在 UMAP 上叠加向量场，显示细胞的发育/分化方向

# 将向量场映射到 UMAP 空间
# 注意: 向量场定义在潜在空间中，需要映射到 UMAP 坐标
from sklearn.neighbors import NearestNeighbors

# 用 KNN 将潜在空间向量场插值到 UMAP 网格上
n_grid = 30  # 网格密度
umap_coords = adata.obsm['X_umap']
vf_latent = adata.obsm['X_sctour_vector_field']

# 创建网格
x_min, x_max = umap_coords[:, 0].min(), umap_coords[:, 0].max()
y_min, y_max = umap_coords[:, 1].min(), umap_coords[:, 1].max()
x_grid = np.linspace(x_min, x_max, n_grid)
y_grid = np.linspace(y_min, y_max, n_grid)
xx, yy = np.meshgrid(x_grid, y_grid)
grid_points = np.column_stack([xx.ravel(), yy.ravel()])

# 用 KNN 将向量场从潜在空间插值到网格
nn = NearestNeighbors(n_neighbors=10)
nn.fit(umap_coords)
distances, indices = nn.kneighbors(grid_points)

# 对每个网格点，用邻居的加权平均向量
vf_grid = np.zeros((n_grid * n_grid, 2))
for i in range(n_grid * n_grid):
    weights = 1.0 / (distances[i] + 1e-8)
    weights = weights / weights.sum()
    # 取向量场的前两个维度（映射到 UMAP 空间）
    vf_grid[i] = np.sum(vf_latent[indices[i], :2] * weights[:, np.newaxis], axis=0)

vf_grid_x = vf_grid[:, 0].reshape(n_grid, n_grid)
vf_grid_y = vf_grid[:, 1].reshape(n_grid, n_grid)

# 绘图
fig, ax = plt.subplots(figsize=(10, 8))

# 先画 UMAP 上的细胞
if color_by and color_by in adata.obs.columns:
    # 按细胞类型着色
    categories = adata.obs[color_by].astype('category')
    for cat in categories.cat.categories:
        mask = categories == cat
        ax.scatter(umap_coords[mask, 0], umap_coords[mask, 1],
                   s=2, alpha=0.5, label=cat, rasterized=True)
else:
    # 按伪时间着色
    scat = ax.scatter(umap_coords[:, 0], umap_coords[:, 1],
                      s=2, c=adata.obs['pseudotime'], cmap='viridis',
                      alpha=0.6, rasterized=True)
    plt.colorbar(scat, ax=ax, label='Pseudotime', shrink=0.5)

# 叠加向量场流线
stream = ax.streamplot(xx, yy, vf_grid_x, vf_grid_y,
                       color='black', density=1.5, linewidth=0.5,
                       arrowsize=0.5, arrowstyle='->')

ax.set_xlabel('UMAP 1')
ax.set_ylabel('UMAP 2')
ax.set_title('scTour Vector Field on UMAP')

if color_by and color_by in adata.obs.columns:
    n_cats = len(categories.cat.categories)
    if n_cats <= 15:
        ax.legend(bbox_to_anchor=(1.05, 1), loc='upper left', fontsize=7,
                  markerscale=3, frameon=False)

plt.tight_layout()
plt.show()


# ╔══════════════════════════════════════════════════════════════╗
# ║  Cell 10: 可视化 - 多面板综合图 (Step 6/6, Part 4)           ║
# ╚══════════════════════════════════════════════════════════════╝

# ## Cell 10: 多面板综合图 (Step 6/6, Part 4)
# 将所有可视化放在一张图中

fig, axes = plt.subplots(2, 2, figsize=(16, 14))

# 1. 细胞类型
ax = axes[0, 0]
if color_by and color_by in adata.obs.columns:
    categories = adata.obs[color_by].astype('category')
    for cat in categories.cat.categories:
        mask = categories == cat
        ax.scatter(umap_coords[mask, 0], umap_coords[mask, 1],
                   s=1, alpha=0.6, label=cat, rasterized=True)
    n_cats = len(categories.cat.categories)
    if n_cats <= 15:
        ax.legend(bbox_to_anchor=(1.05, 1), loc='upper left', fontsize=6,
                  markerscale=4, frameon=False)
ax.set_title('Cell Types')
ax.set_xlabel('UMAP 1')
ax.set_ylabel('UMAP 2')

# 2. 伪时间
ax = axes[0, 1]
scat = ax.scatter(umap_coords[:, 0], umap_coords[:, 1],
                  s=1, c=adata.obs['pseudotime'], cmap='viridis',
                  alpha=0.6, rasterized=True)
plt.colorbar(scat, ax=ax, label='Pseudotime', shrink=0.8)
ax.set_title('Pseudotime')
ax.set_xlabel('UMAP 1')
ax.set_ylabel('UMAP 2')

# 3. 向量场
ax = axes[1, 0]
scat = ax.scatter(umap_coords[:, 0], umap_coords[:, 1],
                  s=1, c=adata.obs['pseudotime'], cmap='viridis',
                  alpha=0.4, rasterized=True)
ax.streamplot(xx, yy, vf_grid_x, vf_grid_y,
              color='black', density=1.5, linewidth=0.5,
              arrowsize=0.5, arrowstyle='->')
ax.set_title('Vector Field')
ax.set_xlabel('UMAP 1')
ax.set_ylabel('UMAP 2')

# 4. 批次/样本（如果有）
ax = axes[1, 1]
if batch_col and batch_col in adata.obs.columns:
    batches = adata.obs[batch_col].astype('category')
    for b in batches.cat.categories:
        mask = batches == b
        ax.scatter(umap_coords[mask, 0], umap_coords[mask, 1],
                   s=1, alpha=0.6, label=b, rasterized=True)
    n_batches = len(batches.cat.categories)
    if n_batches <= 15:
        ax.legend(bbox_to_anchor=(1.05, 1), loc='upper left', fontsize=6,
                  markerscale=4, frameon=False)
    ax.set_title(f'Batch: {batch_col}')
else:
    # 如果没有批次信息，显示向量场强度
    scat = ax.scatter(umap_coords[:, 0], umap_coords[:, 1],
                      s=1, c=adata.obs['vector_field_magnitude'],
                      cmap='magma', alpha=0.6, rasterized=True)
    plt.colorbar(scat, ax=ax, label='|Vector Field|', shrink=0.8)
    ax.set_title('Vector Field Magnitude')
ax.set_xlabel('UMAP 1')
ax.set_ylabel('UMAP 2')

plt.suptitle('scTour Trajectory Inference — Full Workflow', fontsize=14, y=1.02)
plt.tight_layout()
plt.show()


# ╔══════════════════════════════════════════════════════════════╗
# ║  Cell 11: 保存结果 (可选)                                    ║
# ╚══════════════════════════════════════════════════════════════╝

# ## Cell 11: 保存结果
# 保存包含伪时间、潜在空间和向量场的 AnnData 对象

OUTPUT_PATH = "sctour_results.h5ad"  # ← 修改为你的输出路径

# 保存
adata.write_h5ad(OUTPUT_PATH)
print(f"结果已保存至: {OUTPUT_PATH}")
print(f"包含的 obsm 键: {list(adata.obsm.keys())}")
print(f"包含的 obs 新列: pseudotime, vector_field_magnitude")


# ╔══════════════════════════════════════════════════════════════╗
# ║  Cell 12: 按细胞类型统计伪时间 (可选)                         ║
# ╚══════════════════════════════════════════════════════════════╝

# ## Cell 12: 按细胞类型统计伪时间 (可选)
# 查看不同细胞类型在伪时间轴上的分布

if color_by and color_by in adata.obs.columns:
    # 统计每个细胞类型的伪时间
    pt_stats = adata.obs.groupby(color_by)['pseudotime'].agg(['mean', 'std', 'median', 'count'])
    pt_stats = pt_stats.sort_values('mean')
    print("各细胞类型伪时间统计 (按均值排序):")
    print(pt_stats.to_string())

    # 箱线图
    fig, ax = plt.subplots(figsize=(max(6, len(pt_stats) * 0.4), 4))
    order = pt_stats.index.tolist()
    adata.obs[color_by] = pd.Categorical(adata.obs[color_by], categories=order, ordered=True)
    adata.obs.boxplot(column='pseudotime', by=color_by, ax=ax, rot=45, fontsize=8)
    ax.set_title('Pseudotime by Cell Type')
    ax.set_xlabel('')
    ax.set_ylabel('Pseudotime')
    plt.tight_layout()
    plt.show()


# ╔══════════════════════════════════════════════════════════════╗
# ║  Cell 13: 参数调优建议 (参考)                                 ║
# ╚══════════════════════════════════════════════════════════════╝

# ## 参数调优参考
#
# ### 如果伪时间分布过于集中（没有区分度）:
#   - 降低 alpha_recon_lec，提高 alpha_recon_lode
#     → 例如: alpha_recon_lec=0.3, alpha_recon_lode=0.7
#   - 增加 n_latent → 128 → 256
#   - 增加 epochs → 2000 → 3000
#
# ### 如果训练不收敛:
#   - 降低学习率 → 1e-3 → 1e-4
#   - 尝试 loss_mode='nb' 替代 'zinb'
#   - 增加 batch_size → 256 → 512
#
# ### 如果向量场太杂乱:
#   - 增加 alpha_z 和 alpha_predz → 0.5 → 1.0
#   - 增加 n_latent 让潜在空间有更多自由度
#   - 减少 streamplot 的 density 参数
#
# ### 如果是发育生物学数据:
#   - alpha_recon_lec=0.3, alpha_recon_lode=0.7 (强调潜在时间连续性)
#   - n_latent=128
#   - loss_mode='zinb'
#
# ### 如果是疾病/衰老数据:
#   - alpha_recon_lec=0.5, alpha_recon_lode=0.5 (平衡)
#   - n_latent=64-128 (避免过拟合)
#   - loss_mode='zinb' 或 'nb'

print("✅ scTour 完整工作流 Notebook 结束")
print("参考: scTour 论文 https://doi.org/10.1038/s41467-022-34435-3")