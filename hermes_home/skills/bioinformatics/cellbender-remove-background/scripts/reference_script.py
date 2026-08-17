
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


# =============================================================================
# CellBender remove-background — Complete Pipeline (Proven Reference Script)
# =============================================================================
# Source: User's actual CellBender run on 15 monkey skeletal muscle samples
#         (CRR278961-CRR279047, DNB platform)
# Date: 2025-06-15
# Review score: N/A (user-verified, manually imported)
#
# This script implements the COMPLETE 4-stage CellBender pipeline:
#   Stage 1: Read DNB raw matrix → h5ad
#   Stage 2: Convert h5ad → CellRanger mtx format (CellBender input)
#   Stage 3: Run CellBender remove-background (called via subprocess/PowerShell)
#   Stage 4: ptrepack compress → Seurat-readable h5
#
# All parameters are from the user's verified production run.
# =============================================================================

import os
import sys
import subprocess
import shutil
from pathlib import Path

import scanpy as sc
import anndata
import pandas as pd
import numpy as np
from scipy.io import mmwrite

anndata.settings.allow_write_nullable_strings = True


# =============================================================================
# Stage 1: Read DNB raw matrix → h5ad
# =============================================================================
def read_raw_to_h5ad(base_dir, sample_names, output_dir):
    """Read DNB raw matrix (rawmatrix/) and save as h5ad.

    DNB (MGI/BGI) data format:
        {sample}/rawmatrix/
        ├── matrix.mtx     (genes × cells, sparse)
        ├── barcodes.tsv   (cell barcodes)
        └── features.tsv   (gene symbols)

    Args:
        base_dir: Directory containing sample folders
        sample_names: List of sample IDs (e.g., ["CRR278961", "CRR278962"])
        output_dir: Directory to save h5ad files

    Returns:
        dict: {sample_name: (n_cells, n_genes)} for each sample
    """
    os.makedirs(output_dir, exist_ok=True)
    results = {}

    for sname in sample_names:
        mtx_dir = os.path.join(base_dir, sname, "rawmatrix")
        print(f"\n{'='*60}")
        print(f"[{sname}] Reading: {mtx_dir}")

        adata = sc.read_10x_mtx(mtx_dir, var_names='gene_symbols',
                                cache=False, gex_only=True)

        # Add sample prefix to barcodes to prevent cross-sample collisions
        adata.obs_names = [f"{sname}_{x}" for x in adata.obs_names]
        adata.obs["sample"] = sname

        out_path = os.path.join(output_dir, f"{sname}.h5ad")
        adata.write(out_path)
        print(f"[{sname}] -> Saved: {out_path}")
        print(f"       Shape: {adata.shape}")
        results[sname] = (adata.n_obs, adata.n_vars)

    return results


# =============================================================================
# Stage 2: Convert h5ad → CellRanger mtx format (CellBender input)
# =============================================================================
def convert_h5ad_to_mtx(base_dir, sample_names, cellbender_dir):
    """Convert h5ad files to CellRanger matrix.mtx format for CellBender.

    CellBender expects 10x-style matrix directory:
        {output}/{sample}/input_mtx/
        ├── matrix.mtx     (genes × cells, sparse, CSC format)
        ├── barcodes.tsv   (cell barcodes, no header)
        └── features.tsv   (3 columns: id, symbol, type)

    Args:
        base_dir: Directory containing h5ad files
        sample_names: List of sample IDs
        cellbender_dir: Base directory for CellBender outputs

    Returns:
        dict: {sample_name: input_mtx_path} for each sample
    """
    input_paths = {}

    for sname in sample_names:
        h5ad_path = os.path.join(base_dir, "h5ad", f"{sname}.h5ad")
        print(f"[{sname}] Reading: {h5ad_path}")
        adata = sc.read(h5ad_path)

        out_dir = os.path.join(cellbender_dir, sname, "input_mtx")
        os.makedirs(out_dir, exist_ok=True)

        # Write matrix.mtx (transpose: genes × cells)
        mmwrite(os.path.join(out_dir, "matrix.mtx"), adata.X.T)
        print(f"  matrix.mtx written ({adata.n_vars} genes x {adata.n_obs} cells)")

        # Write barcodes.tsv (no header, one column)
        pd.Series(adata.obs_names).to_csv(
            os.path.join(out_dir, "barcodes.tsv"),
            header=False, index=False
        )

        # Write features.tsv (3 columns: id, symbol, type)
        features = pd.DataFrame({
            'id': adata.var_names,
            'symbol': adata.var_names,
            'type': 'Gene Expression'
        })
        features.to_csv(os.path.join(out_dir, "features.tsv"),
                        sep='\t', header=False, index=False)

        input_paths[sname] = out_dir
        print(f"  -> {out_dir}")

    return input_paths


# =============================================================================
# Stage 3: Run CellBender remove-background
# =============================================================================
def run_cellbender(sample_names, h5ad_dir, cellbender_dir,
                   cellbender_exe=None, cuda=True, epochs=150,
                   learning_rate=0.0001, training_fraction=0.9,
                   low_count_threshold=20, projected_ambient_threshold=5,
                   checkpoint_mins=120, force_checkpoint=None):
    """Run CellBender remove-background for each sample.

    CRITICAL: Must unset PYTHONPATH before running CellBender to avoid
    package conflicts from other Python installations.

    CellBender parameters (verified on 15 monkey muscle samples):
        --projected-ambient-count-threshold 5  (fast mode, ~3500 genes)
        --learning-rate 0.0001                 (stable convergence)
        --training-fraction 0.9                (90% train, 10% test)
        --low-count-threshold 20               (drop <20 UMI barcodes)
        --epochs 150                           (~8 min on RTX 5070 Ti)
        --cuda                                 (GPU required)

    Args:
        sample_names: List of sample IDs
        h5ad_dir: Directory with input h5ad files (CellBender can read h5ad directly)
        cellbender_dir: Base output directory
        cellbender_exe: Path to cellbender executable
        cuda: Use GPU acceleration
        force_checkpoint: Path to checkpoint for resume (optional)

    Returns:
        dict: {sample_name: {"success": bool, "output": str}} for each
    """
    if cellbender_exe is None:
        cellbender_exe = shutil.which("cellbender") or "cellbender"

    results = {}

    for sname in sample_names:
        in_file = os.path.join(h5ad_dir, f"{sname}.h5ad")
        out_dir = os.path.join(cellbender_dir, sname)
        out_file = os.path.join(out_dir, "cellbender_output.h5")
        log_file = os.path.join(out_dir, "run.log")

        os.makedirs(out_dir, exist_ok=True)

        # Clean old checkpoint to avoid hash mismatch
        ckpt = os.path.join(out_dir, "ckpt.tar.gz")
        if os.path.exists(ckpt) and not force_checkpoint:
            os.remove(ckpt)

        # Build command
        cmd = [cellbender_exe, "remove-background",
               "--input", in_file,
               "--output", out_file,
               "--projected-ambient-count-threshold", str(projected_ambient_threshold),
               "--learning-rate", str(learning_rate),
               "--training-fraction", str(training_fraction),
               "--low-count-threshold", str(low_count_threshold),
               "--epochs", str(epochs),
               "--checkpoint-mins", str(checkpoint_mins)]

        if cuda:
            cmd.append("--cuda")

        if force_checkpoint:
            cmd.extend(["--checkpoint", force_checkpoint,
                        "--force-use-checkpoint"])

        print(f"\n{'='*60}")
        print(f"[{sname}] CellBender starting")
        print(f"  Input:  {in_file}")
        print(f"  Output: {out_file}")
        print(f"  Command: {' '.join(cmd[:6])}...")

        # CRITICAL: Remove PYTHONPATH to avoid package pollution
        env = dict(os.environ)
        env.pop("PYTHONPATH", None)

        with open(log_file, "w") as logf:
            proc = subprocess.run(
                cmd, env=env, cwd=out_dir,
                stdout=logf, stderr=subprocess.STDOUT
            )

        # Verify success by output file existence (NOT exit code)
        success = os.path.exists(out_file)
        results[sname] = {"success": success, "output": out_file,
                          "exit_code": proc.returncode}

        print(f"[{sname}] Success: {success} (exit: {proc.returncode})")

    return results


# =============================================================================
# Stage 4: ptrepack compress → Seurat-readable h5
# =============================================================================
def compress_for_seurat(sample_names, cellbender_dir, seurat_dir,
                        ptrepack_exe=None, complevel=5):
    """Compress CellBender filtered output for Seurat Read10X_h5().

    CellBender output h5 uses uncompressed PyTables format. Seurat's
    Read10X_h5() may fail or be slow on large files. ptrepack recompresses
    with complevel=5, producing a Seurat-compatible h5 file.

    Args:
        sample_names: List of sample IDs
        cellbender_dir: Directory with CellBender outputs
        seurat_dir: Output directory for compressed files
        ptrepack_exe: Path to ptrepack executable
        complevel: Compression level (1-9, default 5)

    Returns:
        dict: {sample_name: {"success": bool, "output": str}} for each
    """
    if ptrepack_exe is None:
        ptrepack_exe = shutil.which("ptrepack") or "ptrepack"

    os.makedirs(seurat_dir, exist_ok=True)
    results = {}

    for sname in sample_names:
        in_file = os.path.join(cellbender_dir, sname, "cellbender_output_filtered.h5")
        out_file = os.path.join(seurat_dir, f"{sname}_filtered_seurat.h5")

        if not os.path.exists(in_file):
            print(f"[{sname}] SKIP: {in_file} not found")
            results[sname] = {"success": False, "error": "input not found"}
            continue

        cmd = [ptrepack_exe, f"--complevel={complevel}",
               f"{in_file}:/matrix", f"{out_file}:/matrix"]

        # Remove PYTHONPATH
        env = dict(os.environ)
        env.pop("PYTHONPATH", None)

        print(f"[{sname}] ptrepack --complevel {complevel} ...")
        proc = subprocess.run(cmd, env=env,
                              capture_output=True, text=True)

        success = os.path.exists(out_file)
        results[sname] = {"success": success, "output": out_file}
        print(f"  -> {out_file} [{'OK' if success else 'ERROR'}]")

    return results


# =============================================================================
# Main: Complete pipeline
# =============================================================================
def run_complete_pipeline(base_dir, sample_names,
                          cellbender_dir=None, seurat_dir=None,
                          **cellbender_kwargs):
    """Run the complete 4-stage CellBender pipeline.

    Stage 1: Read DNB raw matrix -> h5ad
    Stage 2: (Optional) Convert h5ad -> mtx (CellBender reads h5ad directly)
    Stage 3: Run CellBender remove-background
    Stage 4: ptrepack compress for Seurat

    Args:
        base_dir: Project directory with sample folders
        sample_names: List of sample IDs
        cellbender_dir: CellBender output directory (default: base_dir/cellbender)
        seurat_dir: Seurat output directory (default: base_dir/cellbender_seurat)
        **cellbender_kwargs: Additional CellBender parameters

    Returns:
        dict: Complete results for all stages
    """
    if cellbender_dir is None:
        cellbender_dir = os.path.join(base_dir, "cellbender")
    if seurat_dir is None:
        seurat_dir = os.path.join(base_dir, "cellbender_seurat")

    h5ad_dir = os.path.join(base_dir, "h5ad")

    results = {"stage1_read": {}, "stage2_convert": {},
               "stage3_cellbender": {}, "stage4_compress": {}}

    # Stage 1: Read raw -> h5ad
    print("\n" + "="*60)
    print("STAGE 1: Read DNB raw matrix -> h5ad")
    print("="*60)
    results["stage1_read"] = read_raw_to_h5ad(base_dir, sample_names, h5ad_dir)

    # Stage 2: (Optional) Convert h5ad -> mtx
    # CellBender can read h5ad directly, so this is optional
    # Uncomment if your data needs mtx conversion:
    # results["stage2_convert"] = convert_h5ad_to_mtx(
    #     base_dir, sample_names, cellbender_dir)

    # Stage 3: Run CellBender
    print("\n" + "="*60)
    print("STAGE 3: CellBender remove-background")
    print("="*60)
    results["stage3_cellbender"] = run_cellbender(
        sample_names, h5ad_dir, cellbender_dir, **cellbender_kwargs)

    # Stage 4: Compress for Seurat
    print("\n" + "="*60)
    print("STAGE 4: ptrepack compress for Seurat")
    print("="*60)
    results["stage4_compress"] = compress_for_seurat(
        sample_names, cellbender_dir, seurat_dir)

    # Summary
    print("\n" + "="*60)
    print("PIPELINE COMPLETE — Summary")
    print("="*60)
    for sname in sample_names:
        cb = results["stage3_cellbender"].get(sname, {})
        sr = results["stage4_compress"].get(sname, {})
        print(f"  {sname}: CellBender={'OK' if cb.get('success') else 'FAIL'}"
              f"  Seurat={'OK' if sr.get('success') else 'FAIL'}")

    return results


# =============================================================================
# Known issues and patches (from user's production experience)
# =============================================================================
# 1. PYTHONPATH pollution: Must unset PYTHONPATH before every CellBender/ptrepack
#    call. Other Python installations (e.g., D:\Python\) have incompatible
#    zstandard/zarr versions that crash CellBender.
#
# 2. Checkpoint hash mismatch: Delete ckpt.tar.gz before a fresh run.
#    Resume with --checkpoint --force-use-checkpoint if needed.
#
# 3. HTML report failure: CellBender's HTML report may fail (jupyter nbconvert
#    issues). This does NOT affect the core output (cellbender_output.h5).
#    Success should be judged by output file existence, NOT exit code.
#
# 4. Cross-drive os.replace: On Windows, CellBender's report.py uses
#    os.replace() which fails across drives (C: temp -> E: output).
#    Patch: os.replace -> shutil.move (already applied to conda env).
#
# 5. torch.save weakref: PyTorch 2.12 cannot pickle weakref.ReferenceType.
#    Patch: Use dill as fallback for checkpoint save/load.
#
# 6. GPU memory: 12GB VRAM (RTX 5070 Ti) can only run ONE sample at a time.
#    Serial execution is mandatory; parallel will OOM.
#
# 7. pandas Series.nonzero(): pandas 2.x returns Series, not numpy array.
#    Patch: Add .to_numpy() to 14 assignments in report.py.
#
# For full patch details, see: E:/cellbender/wiki/patches.md
# =============================================================================

if __name__ == "__main__":
    # Example: Run complete pipeline on monkey skeletal muscle data
    BASE_DIR = r"E:\monkey"
    SAMPLES = [
        "CRR278961", "CRR278962", "CRR278963", "CRR278964",
        "CRR278998", "CRR279006", "CRR279013", "CRR279014",
        "CRR279022", "CRR279023", "CRR279024", "CRR279038",
        "CRR279041", "CRR279045", "CRR279047",
    ]

    run_complete_pipeline(
        base_dir=BASE_DIR,
        sample_names=SAMPLES,
        cuda=True,
        epochs=150,
        learning_rate=0.0001,
        training_fraction=0.9,
        low_count_threshold=20,
        projected_ambient_threshold=5,
        checkpoint_mins=120,
    )
