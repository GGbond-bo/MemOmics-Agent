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

# ============================================================
# 🔒 MemOmics 审查铁律 — 执行本脚本前后的强制步骤
# ============================================================
# 执行前必须: rail_review(action="pre")  — 环境检查 + 参数校验 + 代码审查
# 执行后必须: rail_review(action="post") — 结果质量评估 + 图表检查 + 数值检查
# 参数有争议: debate_analysis(topic=..., context=...) — 多角色辩论
# 执行失败:   skill_evolution(action="record_error") — 记录错误
# 修复成功:   skill_evolution(action="record_run") — 记录成功
# ============================================================

"""
scTour Trajectory Inference — Core Training + Inference Script

Runs the complete scTour pipeline:
1. Data preprocessing (QC metrics + HVG selection)
2. Model training (VAE + Neural ODE)
3. Pseudotime inference
4. Latent space inference
5. Vector field inference
6. Model saving

Based on scTour v1.0.0 API.
Reference: Li Q. (2023) Genome Biology. https://doi.org/10.1186/s13059-023-02988-9
"""

import os
import sys
import argparse
import warnings
import numpy as np
import pandas as pd
import scanpy as sc
import sctour as sct
from datetime import datetime

warnings.filterwarnings('ignore')


def run_sctour_inference(
    input_h5ad: str,
    output_dir: str = "sctour_results",
    # Preprocessing
    n_top_genes: int = 1000,
    hvg_flavor: str = "seurat_v3",
    # Model parameters
    percent: float = None,
    n_latent: int = 5,
    n_ode_hidden: int = 25,
    n_vae_hidden: int = 128,
    batch_norm: bool = False,
    ode_method: str = "euler",
    loss_mode: str = "nb",
    alpha_recon_lec: float = 0.5,
    alpha_recon_lode: float = 0.5,
    alpha_kl: float = 1.0,
    nepoch: int = None,
    batch_size: int = 1024,
    lr: float = 1e-3,
    wt_decay: float = 1e-6,
    random_state: int = 0,
    val_frac: float = 0.1,
    use_gpu: bool = None,  # None=auto-detect (GPU if available, else CPU)
    # Latent space parameters
    alpha_z: float = 0.5,
    alpha_predz: float = 0.5,
    # Output
    save_model: bool = True,
    model_prefix: str = "sctour_model",
):
    """
    Run complete scTour inference pipeline.

    Parameters
    ----------
    input_h5ad : str
        Path to input AnnData (.h5ad) file.
    output_dir : str
        Directory to save outputs.
    n_top_genes : int
        Number of highly variable genes to select.
    hvg_flavor : str
        Flavor for HVG selection ('seurat_v3', 'seurat', 'cell_ranger').
    percent : float or None
        Percentage of cells for training. Auto if None (>10000 → 0.2, else 0.9).
    n_latent : int
        Dimensionality of latent space.
    n_ode_hidden : int
        Hidden layer size for latent ODE function.
    n_vae_hidden : int
        Hidden layer size for VAE.
    loss_mode : str
        Loss function: 'mse', 'nb', or 'zinb'.
    alpha_recon_lec : float
        Weight for encoder reconstruction error.
    alpha_recon_lode : float
        Weight for ODE reconstruction error. Must sum to 1 with alpha_recon_lec.
    nepoch : int or None
        Number of epochs. Auto-computed if None.
    random_state : int
        Random seed for reproducibility.
    save_model : bool
        Whether to save the trained model.
    model_prefix : str
        Prefix for saved model files.

    Returns
    -------
    dict with keys:
        - 'adata': AnnData with inferred pseudotime, latent space, vector field
        - 'tnode': Trained scTour Trainer object
        - 'output_dir': Output directory path
    """
    # ================================================================
    # Validate parameters
    # ================================================================
    if not (0 <= alpha_recon_lec <= 1):
        raise ValueError(f"alpha_recon_lec must be in [0, 1], got {alpha_recon_lec}")
    if not (0 <= alpha_recon_lode <= 1):
        raise ValueError(f"alpha_recon_lode must be in [0, 1], got {alpha_recon_lode}")
    if abs(alpha_recon_lec + alpha_recon_lode - 1.0) > 1e-6:
        raise ValueError(
            f"alpha_recon_lec ({alpha_recon_lec}) + alpha_recon_lode ({alpha_recon_lode}) "
            f"must equal 1.0"
        )
    if loss_mode not in ['mse', 'nb', 'zinb']:
        raise ValueError(f"loss_mode must be 'mse', 'nb', or 'zinb', got '{loss_mode}'")

    # ================================================================
    # Create output directories
    # ================================================================
    os.makedirs(output_dir, exist_ok=True)
    data_dir = os.path.join(output_dir, "data")
    results_dir = os.path.join(output_dir, "results")
    os.makedirs(data_dir, exist_ok=True)
    os.makedirs(results_dir, exist_ok=True)

    print("=" * 60)
    print(f"scTour Inference Pipeline — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    # ================================================================
    # Step 1: Load data
    # ================================================================
    print("\n=== Step 1: Load Data ===")
    print(f"  Loading: {input_h5ad}")
    adata = sc.read(input_h5ad)
    print(f"  ✓ Loaded: {adata.n_obs} cells, {adata.n_vars} genes")

    # ================================================================
    # Step 2: Preprocessing
    # ================================================================
    print("\n=== Step 2: Preprocessing ===")

    # Calculate QC metrics (REQUIRED by scTour)
    print("  Computing QC metrics...")
    sc.pp.calculate_qc_metrics(adata, percent_top=None, log1p=False, inplace=True)
    print(f"  ✓ QC metrics computed: n_genes_by_counts added to .obs")

    # Select highly variable genes
    print(f"  Selecting top {n_top_genes} highly variable genes (flavor={hvg_flavor})...")
    sc.pp.highly_variable_genes(adata, flavor=hvg_flavor, n_top_genes=n_top_genes, subset=True)
    print(f"  ✓ HVG selection: {adata.n_vars} genes retained")

    # Convert to float32 to avoid PyTorch dtype mismatch
    # AnnData defaults to float64 (Double), PyTorch models use float32 (Float)
    # Without this: RuntimeError: mat1 and mat2 must have the same dtype, but got Double and Float
    from scipy.sparse import issparse
    if issparse(adata.X):
        adata.X.data = adata.X.data.astype('float32')
    else:
        adata.X = adata.X.astype('float32')
    print(f"  ✓ Dtype converted: {adata.X.dtype}")

    # ================================================================
    # Step 3: Train scTour model
    # ================================================================
    print("\n=== Step 3: Train scTour Model ===")
    print(f"  Parameters:")
    print(f"    loss_mode: {loss_mode}")
    print(f"    alpha_recon_lec: {alpha_recon_lec}, alpha_recon_lode: {alpha_recon_lode}")
    print(f"    n_latent: {n_latent}, n_ode_hidden: {n_ode_hidden}, n_vae_hidden: {n_vae_hidden}")
    print(f"    percent: {percent} (auto={percent is None})")
    print(f"    nepoch: {nepoch} (auto={nepoch is None})")
    print(f"    batch_size: {batch_size}, lr: {lr}, random_state: {random_state}")
    # Auto-detect GPU: if use_gpu is None, check CUDA availability
    if use_gpu is None:
        try:
            import torch
            use_gpu = torch.cuda.is_available()
        except ImportError:
            use_gpu = False
        if use_gpu:
            print(f"    use_gpu: True (CUDA detected — using GPU)")
        else:
            print(f"    use_gpu: False (no CUDA — using CPU, training will be slower)")
    else:
        print(f"    use_gpu: {use_gpu} (user-specified)")

    tnode = sct.train.Trainer(
        adata=adata,
        percent=percent,
        n_latent=n_latent,
        n_ode_hidden=n_ode_hidden,
        n_vae_hidden=n_vae_hidden,
        batch_norm=batch_norm,
        ode_method=ode_method,
        loss_mode=loss_mode,
        alpha_recon_lec=alpha_recon_lec,
        alpha_recon_lode=alpha_recon_lode,
        alpha_kl=alpha_kl,
        nepoch=nepoch,
        batch_size=batch_size,
        lr=lr,
        wt_decay=wt_decay,
        random_state=random_state,
        val_frac=val_frac,
        use_gpu=use_gpu,
    )

    print(f"  Training for {tnode.nepoch} epochs...")
    tnode.train()
    print(f"  ✓ Training completed")

    # ================================================================
    # Step 4: Infer pseudotime
    # ================================================================
    print("\n=== Step 4: Infer Pseudotime ===")
    adata.obs['ptime'] = tnode.get_time()
    print(f"  ✓ Pseudotime inferred: range [{adata.obs['ptime'].min():.4f}, {adata.obs['ptime'].max():.4f}]")
    print(f"    mean={adata.obs['ptime'].mean():.4f}, std={adata.obs['ptime'].std():.4f}")

    # ================================================================
    # Step 5: Infer latent space
    # ================================================================
    print("\n=== Step 5: Infer Latent Space ===")
    print(f"  alpha_z={alpha_z}, alpha_predz={alpha_predz}")
    mix_zs, zs, pred_zs = tnode.get_latentsp(alpha_z=alpha_z, alpha_predz=alpha_predz)
    adata.obsm['X_TNODE'] = mix_zs
    adata.obsm['X_TNODE_z'] = zs
    adata.obsm['X_TNODE_predz'] = pred_zs
    print(f"  ✓ Latent space inferred: shape={mix_zs.shape}")

    # ================================================================
    # Step 6: Infer vector field
    # ================================================================
    print("\n=== Step 6: Infer Vector Field ===")
    adata.obsm['X_VF'] = tnode.get_vector_field(
        adata.obs['ptime'].values,
        adata.obsm['X_TNODE']
    )
    print(f"  ✓ Vector field inferred: shape={adata.obsm['X_VF'].shape}")

    # ================================================================
    # Step 7: Save model (optional)
    # ================================================================
    if save_model:
        print("\n=== Step 7: Save Model ===")
        model_dir = os.path.join(data_dir, "model")
        os.makedirs(model_dir, exist_ok=True)
        tnode.save_model(model_dir, model_prefix)
        print(f"  ✓ Model saved to: {model_dir}/{model_prefix}.pth")

    # ================================================================
    # Step 8: Save results
    # ================================================================
    print("\n=== Step 8: Save Results ===")

    # Save pseudotime
    ptime_df = pd.DataFrame({
        'cell': adata.obs_names,
        'pseudotime': adata.obs['ptime'].values
    })
    ptime_path = os.path.join(results_dir, "pseudotime.csv")
    ptime_df.to_csv(ptime_path, index=False)
    print(f"  ✓ Pseudotime saved: {ptime_path}")

    # Save AnnData with all inferred data
    adata_out_path = os.path.join(data_dir, "adata_with_sctour.h5ad")
    adata.write(adata_out_path)
    print(f"  ✓ Anndata saved: {adata_out_path}")

    # Save summary
    summary_path = os.path.join(results_dir, "sctour_summary.csv")
    summary = pd.DataFrame({
        'parameter': [
            'n_cells', 'n_genes', 'n_top_genes', 'loss_mode',
            'alpha_recon_lec', 'alpha_recon_lode', 'alpha_z', 'alpha_predz',
            'n_latent', 'nepoch', 'batch_size', 'lr', 'random_state',
            'pseudotime_min', 'pseudotime_max', 'pseudotime_mean', 'pseudotime_std'
        ],
        'value': [
            adata.n_obs, adata.n_vars, n_top_genes, loss_mode,
            alpha_recon_lec, alpha_recon_lode, alpha_z, alpha_predz,
            n_latent, tnode.nepoch, batch_size, lr, random_state,
            adata.obs['ptime'].min(), adata.obs['ptime'].max(),
            adata.obs['ptime'].mean(), adata.obs['ptime'].std()
        ]
    })
    summary.to_csv(summary_path, index=False)
    print(f"  ✓ Summary saved: {summary_path}")

    print("\n" + "=" * 60)
    print("scTour Inference Pipeline — COMPLETE")
    print(f"  Output directory: {output_dir}")
    print(f"  Cells analyzed: {adata.n_obs}")
    print(f"  Pseudotime range: [{adata.obs['ptime'].min():.4f}, {adata.obs['ptime'].max():.4f}]")
    print("=" * 60)

    return {
        'adata': adata,
        'tnode': tnode,
        'output_dir': output_dir,
    }


def main():
    parser = argparse.ArgumentParser(
        description="scTour Trajectory Inference — Core Training + Inference"
    )
    parser.add_argument("--input", required=True, help="Path to input AnnData (.h5ad)")
    parser.add_argument("--output_dir", default="sctour_results", help="Output directory")
    parser.add_argument("--n_top_genes", type=int, default=1000, help="Number of HVGs (scTour official: 1000)")
    parser.add_argument("--loss_mode", default="nb", choices=["mse", "nb", "zinb"])
    parser.add_argument("--alpha_recon_lec", type=float, default=0.5)
    parser.add_argument("--alpha_recon_lode", type=float, default=0.5)
    parser.add_argument("--alpha_z", type=float, default=0.5)
    parser.add_argument("--alpha_predz", type=float, default=0.5)
    parser.add_argument("--n_latent", type=int, default=5)
    parser.add_argument("--n_ode_hidden", type=int, default=25)
    parser.add_argument("--n_vae_hidden", type=int, default=128)
    parser.add_argument("--percent", type=float, default=None)
    parser.add_argument("--nepoch", type=int, default=None)
    parser.add_argument("--batch_size", type=int, default=1024)
    parser.add_argument("--lr", type=float, default=1e-3)
    parser.add_argument("--random_state", type=int, default=0)
    parser.add_argument("--no_gpu", action="store_true", help="Disable GPU")
    parser.add_argument("--no_save_model", action="store_true", help="Don't save model")

    args = parser.parse_args()

    run_sctour_inference(
        input_h5ad=args.input,
        output_dir=args.output_dir,
        n_top_genes=args.n_top_genes,
        loss_mode=args.loss_mode,
        alpha_recon_lec=args.alpha_recon_lec,
        alpha_recon_lode=args.alpha_recon_lode,
        alpha_z=args.alpha_z,
        alpha_predz=args.alpha_predz,
        n_latent=args.n_latent,
        n_ode_hidden=args.n_ode_hidden,
        n_vae_hidden=args.n_vae_hidden,
        percent=args.percent,
        nepoch=args.nepoch,
        batch_size=args.batch_size,
        lr=args.lr,
        random_state=args.random_state,
        use_gpu=None if not args.no_gpu else False,  # None=auto-detect
        save_model=not args.no_save_model,
    )


if __name__ == "__main__":
    main()