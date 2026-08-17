#!/usr/bin/env python3
"""
ptrepack 批量压缩 CellBender 产出
压缩后 h5 可直接被 Seurat Read10X_h5() 读取

Usage:
  python ptrepack_all.py --cb_dir PROJECT_DATA_DIR/cellbender_output --out_dir PROJECT_DATA_DIR/seurat_h5
  python ptrepack_all.py --cb_dir ... --out_dir ... --complevel 5 --samples S1 S2 S3
"""

import os, sys, subprocess, argparse, glob, json, time
import shutil


def run(cb_dir, out_dir, sample_names=None, complevel=5, log_file=None):
    """
    批量 ptrepack 压缩。

    Args:
        cb_dir: CellBender output 目录
        out_dir: 输出 seurat h5 目录
        sample_names: 样本列表（None=自动检测 cb_dir 子目录）
        complevel: 压缩级别 1-9
        log_file: 日志（None=自动 out_dir/../logs/ptrepack.log）
    """
    if sample_names is None:
        sample_names = sorted(d for d in os.listdir(cb_dir)
                              if os.path.isdir(os.path.join(cb_dir, d)))

    os.makedirs(out_dir, exist_ok=True)

    if log_file is None:
        log_dir = os.path.join(os.path.dirname(out_dir), "logs")
        os.makedirs(log_dir, exist_ok=True)
        log_file = os.path.join(log_dir, "ptrepack.log")

    # 检测 ptrepack
    ptrepack = shutil.which("ptrepack")
    if not ptrepack:
        print("ERROR: ptrepack not found in PATH. Install tables: pip install tables")
        sys.exit(1)

    results = {}
    total = len(sample_names)

    with open(log_file, "w", encoding="utf-8") as log:
        log.write(f"ptrepack batch — {total} samples | {time.ctime()}\n")
        log.write(f"complevel={complevel}\n")
        log.write("=" * 60 + "\n")

        for i, sname in enumerate(sample_names, 1):
            in_file = os.path.join(cb_dir, sname, "cellbender_output_filtered.h5")
            out_file = os.path.join(out_dir, f"{sname}_filtered_seurat.h5")

            # 检查输入
            if not os.path.exists(in_file):
                msg = f"[{i}/{total}] {sname} — SKIP (no filtered.h5)"
                print(msg); log.write(msg + "\n"); log.flush()
                results[sname] = "skip_no_input"
                continue

            # 检查已压缩
            if os.path.exists(out_file) and os.path.getsize(out_file) > 1000:
                sz_mb = os.path.getsize(out_file) / 1e6
                msg = f"[{i}/{total}] {sname} — SKIP (已存在 {sz_mb:.1f} MB)"
                print(msg); log.write(msg + "\n"); log.flush()
                results[sname] = "skip_existing"
                continue

            t0 = time.time()

            # ptrepack 命令
            cmd = [
                ptrepack,
                f"--complevel={complevel}",
                f"{in_file}:/matrix",
                f"{out_file}:/matrix",
            ]

            env = dict(os.environ)
            env.pop("PYTHONPATH", None)

            proc = subprocess.run(cmd, env=env, capture_output=True, text=True)

            elapsed = time.time() - t0

            if proc.returncode == 0 and os.path.exists(out_file):
                sz_mb = os.path.getsize(out_file) / 1e6
                msg = f"[{i}/{total}] {sname} — OK ({sz_mb:.1f} MB, {elapsed:.0f}s)"
                print(msg); log.write(msg + "\n"); log.flush()
                results[sname] = f"ok ({sz_mb:.1f} MB)"
            else:
                msg = f"[{i}/{total}] {sname} — FAIL ({elapsed:.0f}s)\n  {proc.stderr[:300]}"
                print(msg); log.write(msg + "\n"); log.flush()
                results[sname] = f"fail: {proc.stderr[:100]}"

        # 汇总
        n_ok = sum(1 for v in results.values() if str(v).startswith("ok"))
        n_skip = sum(1 for v in results.values() if str(v).startswith("skip"))
        n_fail = sum(1 for v in results.values() if str(v).startswith("fail"))
        summary = f"\nDONE: {n_ok} ok | {n_skip} skip | {n_fail} fail / {total} total"
        print(summary); log.write(summary + "\n")

    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="批量 ptrepack 压缩 CellBender h5 文件")
    parser.add_argument("--cb_dir", required=True, help="CellBender output 目录")
    parser.add_argument("--out_dir", required=True, help="输出 seurat h5 目录")
    parser.add_argument("--samples", nargs="*", default=None, help="样本列表")
    parser.add_argument("--complevel", type=int, default=5, help="压缩级别 (1-9, 默认5)")
    args = parser.parse_args()

    run(args.cb_dir, args.out_dir, args.samples, args.complevel)
