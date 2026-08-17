#!/usr/bin/env python3
"""
CellBender Complete Pipeline — Watchdog Runner
================================================
Chains: Stage 1 (raw→h5ad) → Stage 2 (CellBender) → Stage 3 (ptrepack) → Stage 4 (stats)

Usage:
  # 完整 4 阶段（从 raw matrix 开始）
  python run_pipeline.py --base_dir F:/00.RawData --work_dir PROJECT_DATA_DIR

  # 从 Stage 2 开始（h5ad 已就绪）
  python run_pipeline.py --h5ad_dir PROJECT_DATA_DIR/h5ad --work_dir PROJECT_DATA_DIR --skip_stage1

  # 仅跑其中几个样本
  python run_pipeline.py --base_dir F:/00.RawData --work_dir PROJECT_DATA_DIR --samples S1 S2 S3

核心设计:
  - 串行执行，一次一个样本
  - 每个样本验证产出后才切下一个
  - 失败不崩，记录日志后继续下一个
  - 全部日志写在 work_dir/logs/pipeline.log
  - 支持脱离式启动 (start /B)
"""

import os, sys, time, traceback, json, subprocess, argparse, glob, gzip
import shutil
from datetime import datetime
from pathlib import Path


# ============================================================================
# 参数（可通过 --params JSON 覆盖）
# ============================================================================
DEFAULT_PARAMS = {
    # CellBender 官方默认参数（不改）
    "fpr": 0.01,
    "epochs": 150,
    "learning_rate": 1e-4,
    "total_droplets": 25000,
    "expected_cells": 5000,
    "low_count_threshold": 5,
    # ptrepack
    "complevel": 5,
}


# ============================================================================
# 日志工具
# ============================================================================
def write_log(log_file, msg, also_print=True):
    """写日志到文件 + 可选 stdout"""
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    if also_print:
        print(line, flush=True)
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def stage_header(log_file, stage_name, sample, msg=""):
    sep = "=" * 70
    write_log(log_file, "")
    write_log(log_file, sep)
    write_log(log_file, f"[{stage_name}] [{sample}] {msg}")
    write_log(log_file, sep)


# ============================================================================
# 系统检查
# ============================================================================
def check_env(log_file):
    """检查 GPU、CellBender、ptrepack 是否可用"""
    issues = []

    # torch CUDA
    try:
        import torch
        cuda = torch.cuda.is_available()
        if cuda:
            gpu_name = torch.cuda.get_device_name(0)
            vram = torch.cuda.get_device_properties(0).total_memory / 1e9
            write_log(log_file, f"[ENV] GPU: {gpu_name} ({vram:.1f} GB VRAM)")
        else:
            write_log(log_file, "[ENV] WARN: CUDA not available")
            issues.append("CUDA not available")
    except ImportError:
        write_log(log_file, "[ENV] WARN: torch not importable")
        issues.append("torch not available")

    # cellbender
    cb = shutil.which("cellbender")
    if cb:
        write_log(log_file, f"[ENV] cellbender: {cb}")
    else:
        write_log(log_file, "[ENV] WARN: cellbender not in PATH")
        issues.append("cellbender not found in PATH")

    # ptrepack
    pt = shutil.which("ptrepack")
    if pt:
        write_log(log_file, f"[ENV] ptrepack: {pt}")
    else:
        write_log(log_file, "[ENV] WARN: ptrepack not in PATH")
        issues.append("ptrepack not found in PATH")

    return issues


# ============================================================================
# Stage 1: Raw matrix → h5ad
# ============================================================================
def run_stage1(base_dir, h5ad_dir, log_file, sample_names=None, skip=False):
    """如果 skip=True 则跳过 Stage 1"""
    if skip:
        write_log(log_file, "[Stage1] SKIPPED（h5ad 已就绪）")
        # 检测已有 h5ad 数量
        h5ads = sorted(glob.glob(os.path.join(h5ad_dir, "*.h5ad")))
        samples_found = [os.path.basename(f).replace(".h5ad", "") for f in h5ads]
        write_log(log_file, f"[Stage1] 已发现 {len(h5ads)} 个 h5ad: {samples_found}")
        return samples_found if sample_names is None else sample_names

    write_log(log_file, "[Stage1] ===== 开始: Raw matrix -> h5ad =====")

    # 调用 stage1_to_h5ad.py
    script = os.path.join(os.path.dirname(__file__), "stage1_to_h5ad.py")
    log1 = os.path.join(os.path.dirname(log_file), "stage1.log")

    cmd = [sys.executable, script,
           "--base_dir", base_dir,
           "--out_dir", h5ad_dir,
           "--log_file", log1]
    if sample_names:
        cmd += ["--samples"] + sample_names

    write_log(log_file, f"[Stage1] CMD: {' '.join(cmd)}")
    proc = subprocess.run(cmd, capture_output=True, text=True)
    write_log(log_file, f"[Stage1] exit={proc.returncode}")

    # 解析结果
    if proc.stdout:
        write_log(log_file, proc.stdout.strip())

    # 获取 h5ad 列表
    h5ads = sorted(glob.glob(os.path.join(h5ad_dir, "*.h5ad")))
    if not h5ads:
        write_log(log_file, "[Stage1] ERROR: 没有生成任何 h5ad！")
        write_log(log_file, f"stderr: {proc.stderr[:2000]}")
        return []

    samples_ok = [os.path.basename(f).replace(".h5ad", "") for f in h5ads]
    write_log(log_file, f"[Stage1] Done: {len(samples_ok)} h5ads ready")
    return samples_ok


# ============================================================================
# Stage 2: CellBender remove-background
# ============================================================================
def run_stage2(sample_names, h5ad_dir, cb_output_dir, log_file, params):
    """串行跑 CellBender，一次一个样本。"""
    write_log(log_file, "[Stage2] ===== 开始: CellBender remove-background =====")
    write_log(log_file, f"[Stage2] params: {json.dumps(params, indent=2)}")
    write_log(log_file, f"[Stage2] samples: {sample_names}")
    write_log(log_file, f"[Stage2] output: {cb_output_dir}")

    results = {}
    total = len(sample_names)

    for i, sname in enumerate(sample_names, 1):
        stage_header(log_file, "Stage2", sname,
                     f"[{i}/{total}] 开始")

        in_file = os.path.join(h5ad_dir, f"{sname}.h5ad")
        out_dir = os.path.join(cb_output_dir, sname)
        out_file = os.path.join(out_dir, "cellbender_output.h5")
        filtered_file = os.path.join(out_dir, "cellbender_output_filtered.h5")
        run_log = os.path.join(out_dir, "cellbender_run.log")

        # 验证输入
        if not os.path.exists(in_file):
            write_log(log_file, f"[Stage2] [{sname}] SKIP: h5ad not found: {in_file}", also_print=True)
            results[sname] = {"status": "skip", "reason": "h5ad not found"}
            continue

        # 检查是否已有产出
        if os.path.exists(filtered_file) and os.path.getsize(filtered_file) > 1000:
            sz_mb = os.path.getsize(filtered_file) / 1e6
            write_log(log_file, f"[Stage2] [{sname}] SKIP: 已有产出 ({sz_mb:.1f} MB)")
            results[sname] = {"status": "skip", "reason": "already done"}
            continue

        os.makedirs(out_dir, exist_ok=True)

        # 清理旧 checkpoint
        ckpt = os.path.join(out_dir, "ckpt.tar.gz")
        if os.path.exists(ckpt):
            os.remove(ckpt)

        t0 = time.time()

        # 构建命令
        cmd = [
            "cellbender", "remove-background",
            "--input", in_file,
            "--output", out_file,
            "--fpr", str(params["fpr"]),
            "--epochs", str(params["epochs"]),
            "--learning-rate", str(params["learning_rate"]),
            "--total-droplets-included", str(params["total_droplets"]),
            "--expected-cells", str(params["expected_cells"]),
            "--low-count-threshold", str(params["low_count_threshold"]),
            "--cuda",
        ]

        write_log(log_file, f"[Stage2] [{sname}] CMD: {' '.join(cmd)}")

        # 清除 PYTHONPATH 防止污染
        env = dict(os.environ)
        env.pop("PYTHONPATH", None)

        # 启动 CellBender
        with open(run_log, "w", encoding="utf-8") as rl:
            write_log(log_file, f"[Stage2] [{sname}] {"="*50}")
            write_log(log_file, f"[Stage2] [{sname}] CellBender 训练开始 ...")

            proc = subprocess.run(
                cmd, env=env, cwd=out_dir,
                stdout=rl, stderr=subprocess.STDOUT,
                text=True,
            )

        elapsed = time.time() - t0

        # 验证产出
        has_output = os.path.exists(out_file) and os.path.getsize(out_file) > 1000
        has_filtered = os.path.exists(filtered_file) and os.path.getsize(filtered_file) > 1000

        if has_filtered:
            sz_mb = os.path.getsize(filtered_file) / 1e6
            write_log(log_file, f"[Stage2] [{sname}] OK — filtered.h5: {sz_mb:.1f} MB ({elapsed/60:.1f} min)")
            results[sname] = {"status": "ok", "elapsed_min": elapsed/60}
        elif has_output:
            sz_mb = os.path.getsize(out_file) / 1e6
            write_log(log_file, f"[Stage2] [{sname}] PARTIAL — output.h5 在但无 filtered ({sz_mb:.1f} MB)")
            results[sname] = {"status": "partial", "elapsed_min": elapsed/60}
        else:
            # 读最后几行日志
            last_lines = ""
            try:
                with open(run_log, "r", encoding="utf-8") as f:
                    lines = f.readlines()
                    last_lines = "".join(lines[-30:])
            except:
                pass
            write_log(log_file, f"[Stage2] [{sname}] FAIL — 无产出 ({elapsed:.0f}s)")
            write_log(log_file, f"[Stage2] [{sname}] 最后 30 行日志:\n{last_lines}")
            results[sname] = {"status": "fail", "elapsed_sec": elapsed}

        # 串行：等一小让 GPU 释放
        write_log(log_file, f"[Stage2] [{sname}] 等待 GPU 释放 ...")
        time.sleep(5)

    # 汇总
    n_ok = sum(1 for v in results.values() if v.get("status") == "ok")
    n_skip = sum(1 for v in results.values() if v.get("status") == "skip")
    n_fail = sum(1 for v in results.values() if v.get("status") == "fail")
    write_log(log_file, f"[Stage2] Done: {n_ok} ok | {n_skip} skip | {n_fail} fail / {total} total")
    return results


# ============================================================================
# Stage 3: ptrepack 压缩
# ============================================================================
def run_stage3(sample_names, cb_output_dir, seurat_dir, log_file, params):
    """ptrepack 压缩 CellBender 过滤后的 h5 文件"""
    write_log(log_file, "[Stage3] ===== 开始: ptrepack 压缩 =====")

    results = {}
    total = len(sample_names)

    for i, sname in enumerate(sample_names, 1):
        in_file = os.path.join(cb_output_dir, sname, "cellbender_output_filtered.h5")
        out_file = os.path.join(seurat_dir, f"{sname}_filtered_seurat.h5")

        if not os.path.exists(in_file):
            write_log(log_file, f"[Stage3] [{sname}] SKIP: no filtered.h5")
            results[sname] = {"status": "skip"}
            continue

        if os.path.exists(out_file) and os.path.getsize(out_file) > 1000:
            write_log(log_file, f"[Stage3] [{sname}] SKIP: 已压缩")
            results[sname] = {"status": "skip"}
            continue

        os.makedirs(seurat_dir, exist_ok=True)
        t0 = time.time()

        # ptrepack 命令
        cmd = [
            "ptrepack",
            f"--complevel={params['complevel']}",
            f"{in_file}:/matrix",
            f"{out_file}:/matrix",
        ]

        env = dict(os.environ)
        env.pop("PYTHONPATH", None)

        proc = subprocess.run(cmd, env=env, capture_output=True, text=True)
        elapsed = time.time() - t0

        if proc.returncode == 0 and os.path.exists(out_file):
            sz_mb = os.path.getsize(out_file) / 1e6
            write_log(log_file, f"[Stage3] [{sname}] OK ({sz_mb:.1f} MB, {elapsed:.0f}s)")
            results[sname] = {"status": "ok", "size_mb": sz_mb}
        else:
            write_log(log_file, f"[Stage3] [{sname}] FAIL: {proc.stderr[:500]}")
            results[sname] = {"status": "fail", "error": proc.stderr[:500]}

    n_ok = sum(1 for v in results.values() if v.get("status") == "ok")
    write_log(log_file, f"[Stage3] Done: {n_ok}/{total} compressed")
    return results


# ============================================================================
# Stage 4: 统计表（前后对比）
# ============================================================================
def run_stage4(sample_names, h5ad_dir, cb_output_dir, stats_dir, log_file):
    """生成 CellBender 前后对比统计表"""
    write_log(log_file, "[Stage4] ===== 开始: 对比统计 =====")
    os.makedirs(stats_dir, exist_ok=True)

    import h5py
    import numpy as np

    rows = []
    for sname in sample_names:
        row = {"sample": sname}

        # 之前 (h5ad)
        h5ad_path = os.path.join(h5ad_dir, f"{sname}.h5ad")
        if os.path.exists(h5ad_path):
            try:
                import anndata
                ad = anndata.read(h5ad_path, backed="r")
                row["before_cells"] = ad.n_obs
                row["before_genes"] = ad.n_vars
                if hasattr(ad.X, "nnz"):
                    row["before_nnz"] = ad.X.nnz
                    row["before_sparsity"] = f"{100 * (1 - ad.X.nnz / (ad.n_obs * ad.n_vars)):.1f}%"
            except Exception as e:
                row["before_error"] = str(e)

        # 之后 (filtered.h5 from CellBender)
        cb_file = os.path.join(cb_output_dir, sname, "cellbender_output_filtered.h5")
        if os.path.exists(cb_file):
            try:
                with h5py.File(cb_file, "r") as f:
                    # CellBender 的 h5 格式：/matrix 下的 data, indices, indptr, shape
                    if "matrix" in f:
                        grp = f["matrix"]
                        shape = grp["shape"][:]
                        row["after_cells"] = int(shape[0])
                        row["after_genes"] = int(shape[1])
                        nnz = len(grp["data"])
                        row["after_nnz"] = nnz
                        row["after_sparsity"] = f"{100 * (1 - nnz / (shape[0] * shape[1])):.1f}%"

                        # 移除比例
                        if "before_cells" in row and row["before_cells"] > 0:
                            pct = 100 * (row["before_cells"] - shape[0]) / row["before_cells"]
                            row["cell_removal_pct"] = f"{pct:.1f}%"
            except Exception as e:
                row["after_error"] = str(e)

        rows.append(row)
        write_log(log_file, f"[Stage4] [{sname}] 前:{row.get('before_cells','?')} 后:{row.get('after_cells','?')}")

    # 写 CSV
    import csv
    stats_file = os.path.join(stats_dir, "cellbender_stats.tsv")
    if rows:
        fieldnames = list(rows[0].keys())
        with open(stats_file, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, delimiter="\t")
            writer.writeheader()
            writer.writerows(rows)
        write_log(log_file, f"[Stage4] 统计表 -> {stats_file} ({len(rows)} samples)")

    # 写简洁版
    brief = []
    for r in rows:
        brief.append(f"  {r['sample']:30s}  "
                      f"前={str(r.get('before_cells','?')):>8s} cells  "
                      f"后={str(r.get('after_cells','?')):>8s} cells  "
                      f"移除={r.get('cell_removal_pct','?'):>6s}")
    write_log(log_file, "[Stage4] ===== 统计摘要 =====")
    for b in brief:
        write_log(log_file, b)

    return stats_file


# ============================================================================
# 主流程
# ============================================================================
def run_pipeline(base_dir=None, h5ad_dir=None, work_dir=None,
                 sample_names=None, params=None, skip_stage1=False,
                 only_stage=None):
    """
    完整 pipeline 入口。

    Args:
        base_dir: raw matrix 根目录（内含样本子目录）
        h5ad_dir: h5ad 目录（如果已转换好）
        work_dir: 工作目录（存放脚本、日志、产出）
        sample_names: 指定样本（默认自动检测）
        params: CellBender 参数覆盖
        skip_stage1: 是否跳过 Stage 1（h5ad 已就绪）
        only_stage: 仅跑某阶段，"2"/"3"/"4"
    """
    if work_dir is None:
        work_dir = os.getcwd()

    if params is None:
        params = {}
    merged_params = {**DEFAULT_PARAMS, **params}

    # 目录
    if h5ad_dir is None:
        h5ad_dir = os.path.join(work_dir, "h5ad")
    cb_output_dir = os.path.join(work_dir, "cellbender_output")
    seurat_dir = os.path.join(work_dir, "seurat_h5")
    stats_dir = os.path.join(work_dir, "summary")
    log_dir = os.path.join(work_dir, "logs")

    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, "pipeline.log")

    # 清空旧日志（每次全新启动）
    with open(log_file, "w", encoding="utf-8") as f:
        f.write(f"CellBender Pipeline — {time.ctime()}\n")
        f.write(f"work_dir={work_dir}\n")
        f.write(f"params={json.dumps(merged_params, indent=2)}\n")
        f.write("=" * 70 + "\n")

    write_log(log_file, f"Base dir:     {base_dir or '(N/A)'}")
    write_log(log_file, f"H5ad dir:     {h5ad_dir}")
    write_log(log_file, f"Work dir:     {work_dir}")
    write_log(log_file, f"CellBender:   {cb_output_dir}")
    write_log(log_file, f"Seurat H5:    {seurat_dir}")
    write_log(log_file, f"Stats:        {stats_dir}")
    write_log(log_file, f"Log:          {log_file}")

    # 环境检查
    issues = check_env(log_file)
    if issues:
        write_log(log_file, f"WARN: 环境问题: {issues}")

    # Stage 1
    if only_stage is None or only_stage == "1":
        sample_names = run_stage1(base_dir or "", h5ad_dir, log_file,
                                  sample_names, skip=skip_stage1)
        if not sample_names:
            write_log(log_file, "[PIPELINE] Stage 1 无产出，终止")
            return False
        write_log(log_file, f"[PIPELINE] 样本列表 ({len(sample_names)}): {sample_names}")
    elif sample_names is None:
        # 自动检测 h5ad
        h5ads = sorted(glob.glob(os.path.join(h5ad_dir, "*.h5ad")))
        sample_names = [os.path.basename(f).replace(".h5ad", "") for f in h5ads]
        write_log(log_file, f"[PIPELINE] 自动检测到 {len(sample_names)} 个 h5ad")

    # Stage 2: CellBender
    if only_stage is None or only_stage == "2":
        run_stage2(sample_names, h5ad_dir, cb_output_dir, log_file, merged_params)

    # Stage 3: ptrepack
    if only_stage is None or only_stage == "3":
        run_stage3(sample_names, cb_output_dir, seurat_dir, log_file, merged_params)

    # Stage 4: 统计
    if only_stage is None or only_stage == "4":
        run_stage4(sample_names, h5ad_dir, cb_output_dir, stats_dir, log_file)

    write_log(log_file, "=" * 70)
    write_log(log_file, "[PIPELINE] 全部完成！")
    write_log(log_file, f"  日志:     {log_file}")
    write_log(log_file, f"  CellBender: {cb_output_dir}")
    write_log(log_file, f"  Seurat:   {seurat_dir}")
    write_log(log_file, f"  统计:     {stats_dir}/cellbender_stats.tsv")
    return True


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="CellBender 完整流水线：raw matrix -> h5ad -> CellBender -> ptrepack -> stats")
    parser.add_argument("--base_dir", default=None,
                        help="原始数据根目录（内含样本子目录/output/raw_matrix/）")
    parser.add_argument("--h5ad_dir", default=None,
                        help="h5ad 目录（如果已转换好）")
    parser.add_argument("--work_dir", required=True,
                        help="工作目录（存放 h5ad/cellbender_output/seurat_h5/summary/logs）")
    parser.add_argument("--samples", nargs="*", default=None,
                        help="指定样本列表")
    parser.add_argument("--params", default=None,
                        help='JSON 字符串覆盖参数，如 \'{"epochs":200}\'')
    parser.add_argument("--skip_stage1", action="store_true",
                        help="跳过 Stage 1（h5ad 已就绪）")
    parser.add_argument("--only_stage", default=None,
                        help='仅跑某阶段: "1", "2", "3", "4"')
    args = parser.parse_args()

    params = json.loads(args.params) if args.params else {}

    run_pipeline(
        base_dir=args.base_dir,
        h5ad_dir=args.h5ad_dir,
        work_dir=args.work_dir,
        sample_names=args.samples,
        params=params,
        skip_stage1=args.skip_stage1,
        only_stage=args.only_stage,
    )
