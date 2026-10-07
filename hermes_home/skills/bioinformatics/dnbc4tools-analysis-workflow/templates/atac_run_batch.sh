#!/bin/bash
# dnbc4tools 3.1 ATAC 批量比对脚本模板 (华大 DNBelab C4)
# 用法: SLIB=<文库名> bash atac_run_batch.sh   # 只跑指定文库(试点/重跑)
#        bash atac_run_batch.sh                # 全量循环
# 注意: 本脚本在 WSL 内运行 (wsl -e bash -lc "..."), 路径均为 WSL 挂载路径
set -uo pipefail

# ─── 配置区 (按实际环境修改) ───
DNBC=/opt/dnbc4tools3.1/dnbc4tools          # dnbc4tools 3.1 可执行文件
GENOME=/data/GRCh38_ref/GRCh38_atac_index/Homo_sapiens   # ⚠️ 必须含 ref.json 的层(带 /Homo_sapiens)
DATA=/mnt/f/CRGMara1                        # FASTQ 文库根目录 (每子目录一个文库)
OUT=/mnt/f/output                           # 输出根目录
THREADS=16
# ─────────────────────────────

LOG=$OUT/logs
mkdir -p "$OUT" "$LOG"
echo "[$(date)] ======== ATAC 批量比对启动 (v3.1) ========" | tee -a "$LOG/batch.log"

for sample_dir in "$DATA"/*/; do
  sample=$(basename "$sample_dir")
  [ -n "${SLIB:-}" ] && [ "$sample" != "$SLIB" ] && continue

  # 收集 R1/R2 (支持多 lane 逗号合并; _1/_2 后缀拍序配对)
  mapfile -t r1_arr < <(ls "$sample_dir"*_1.fq.gz 2>/dev/null | sort; ls "$sample_dir"*_1.fastq.gz 2>/dev/null | sort)
  mapfile -t r2_arr < <(ls "$sample_dir"*_2.fq.gz 2>/dev/null | sort; ls "$sample_dir"*_2.fastq.gz 2>/dev/null | sort)
  [ ${#r1_arr[@]} -eq 0 ] && { echo "[$(date)] SKIP $sample: 无 R1 文件" | tee -a "$LOG/batch.log"; continue; }
  r1=$(IFS=,; echo "${r1_arr[*]}")
  r2=$(IFS=,; echo "${r2_arr[*]}")

  # 断点续跑: 已产出则跳过
  outdir="$OUT/$sample"
  [ -f "$outdir/output/singlecell.csv" ] && { echo "[$(date)] SKIP $sample: 已完成" | tee -a "$LOG/batch.log"; continue; }

  echo "[$(date)] === 开始 $sample (R1=$r1)" | tee -a "$LOG/batch.log"
  "$DNBC" atac run \
    --name "$sample" \
    --fastq1 "$r1" \
    --fastq2 "$r2" \
    --genomeDir "$GENOME" \
    --outdir "$outdir" \
    --threads "$THREADS" \
    --darkreaction auto \
    > "$LOG/${sample}.log" 2>&1
  rc=$?

  if [ $rc -eq 0 ] && [ -f "$outdir/output/singlecell.csv" ]; then
    echo "[$(date)] OK $sample 完成 (rc=0)" | tee -a "$LOG/batch.log"
  else
    echo "[$(date)] FAIL $sample (rc=$rc) — 日志: $LOG/${sample}.log" | tee -a "$LOG/batch.log"
  fi
done

echo "[$(date)] ======== 全部完成 ========" | tee -a "$LOG/batch.log"