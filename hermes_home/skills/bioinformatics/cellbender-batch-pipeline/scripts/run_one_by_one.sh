#!/bin/bash
# run_one_by_one.sh — 最简 CellBender 串行循环
# 替代 run_pipeline.py 的可靠方案
#
# 为什么不用 run_pipeline.py:
#   - Python subprocess 进程树挂在 Hermes 会话下 → 回收 → pipeline 死
#   - CellBender 孤儿继续跑但不会自动切下一个
#   - 同一会话内 3 次部署 3 次死亡
#
# 为什么用 bash 循环:
#   - [ -f filtered.h5 ] skip 不依赖任何进程状态，纯文件判断
#   - bash 进程死了也不丢进度（文件判断保证断点续跑）
#   - 每样本跑完立刻 ptrepack，不留给后续 Stage

set -e

H5AD_DIR="${H5AD_DIR:-PROJECT_DATA_DIR/h5ad}"
OUT_DIR="${OUT_DIR:-PROJECT_DATA_DIR/cellbender_output}"
SEURAT_DIR="${SEURAT_DIR:-PROJECT_DATA_DIR/seurat_h5}"
LOG_DIR="${LOG_DIR:-PROJECT_DATA_DIR/logs}"
CELLBENDER="${CELLBENDER:-/c/Users/USERNAME/AppData/Local/Programs/Python/Python312/Scripts/cellbender.exe}"
PTREPACK="${PTREPACK:-/c/Users/USERNAME/AppData/Local/Programs/Python/Python312/Scripts/ptrepack.exe}"
PIPELINE_LOG="$LOG_DIR/one_by_one.log"

mkdir -p "$LOG_DIR" "$SEURAT_DIR"

# 脱离式启动: start /B bash run_one_by_one.sh
# 或 terminal(background=true, notify_on_complete=true)

for H5AD in "$H5AD_DIR"/*.h5ad; do
    SAMPLE=$(basename "$H5AD" .h5ad)
    FILTERED="$OUT_DIR/$SAMPLE/cellbender_output_filtered.h5"
    SEURAT="$SEURAT_DIR/${SAMPLE}_filtered_seurat.h5"

    # Skip if filtered.h5 exists
    if [ -f "$FILTERED" ] && [ -s "$FILTERED" ]; then
        echo "[SKIP] $SAMPLE — filtered.h5 exists"
        # Still ptrepack if seurat h5 missing
        if [ ! -f "$SEURAT" ]; then
            PYTHONPATH="" "$PTREPACK" --complevel=5 "${FILTERED}:/matrix" "${SEURAT}:/matrix"
        fi
        continue
    fi

    echo "=== $(date) — $SAMPLE START ==="
    rm -f "$OUT_DIR/$SAMPLE/ckpt.tar.gz"

    PYTHONPATH="" "$CELLBENDER" remove-background \
        --input "$H5AD" \
        --output "$OUT_DIR/$SAMPLE/cellbender_output.h5" \
        --fpr 0.01 --epochs 150 --learning-rate 0.0001 \
        --total-droplets-included 25000 --expected-cells 5000 \
        --low-count-threshold 5 --cuda

    if [ -f "$FILTERED" ] && [ -s "$FILTERED" ]; then
        echo "=== $(date) — $SAMPLE OK ==="
        PYTHONPATH="" "$PTREPACK" --complevel=5 "${FILTERED}:/matrix" "${SEURAT}:/matrix"
    else
        echo "=== $(date) — $SAMPLE FAILED (no filtered.h5) ==="
    fi
done

echo "=== $(date) — ALL DONE ==="
