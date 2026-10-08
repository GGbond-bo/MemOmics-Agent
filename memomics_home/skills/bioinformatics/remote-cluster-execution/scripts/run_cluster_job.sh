#!/bin/bash
# ============================================================================
# 方案 A 作业投递包装（SGE/Slurm 通用）—— 2026-10-08
# 职责：显式定义解释器（铁规 2）+ 打 #TASK 点 + 日志落工作盘 + 调用检查点模板
#
# 用法：bash run_cluster_job.sh <INPUT.rds> <WORKDIR> [额外参数...]
# 环境变量（默认取 environment.json.cluster.policy 锁定的工作环境）：
#   CONDA_ROOT=/hwfssz3/PS_JLU/zhangxiao6/software/miniconda3
#   ENV_NAME=R4.41                 # RNA→R4.41 / ATAC→R4.3.3（只读，禁装包）
#   STAGE=checkpoint_job.R         # 同目录下的 R 脚本
# ============================================================================
set -euo pipefail

INPUT="${1:?用法: run_cluster_job.sh <INPUT.rds> <WORKDIR> [参数...]}"
WORKDIR="${2:?用法: run_cluster_job.sh <INPUT.rds> <WORKDIR> [参数...]}"
shift 2 || true

CONDA_ROOT="${CONDA_ROOT:-/hwfssz3/PS_JLU/zhangxiao6/software/miniconda3}"
ENV_NAME="${ENV_NAME:-R4.41}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
STAGE="${STAGE:-checkpoint_job.R}"

mkdir -p "$WORKDIR/log"
LOG="$WORKDIR/log/job_$(date +%Y%m%d_%H%M%S).log"

echo "#TASK:STAGE env" | tee -a "$LOG"
echo "#TASK:PARAM node=$(hostname)" | tee -a "$LOG"

# 铁规 2：集群系统 PATH 里通常没有 Rscript，必须显式定义解释器
export PATH="$CONDA_ROOT/envs/$ENV_NAME/bin:$PATH"
RSCRIPT="$CONDA_ROOT/envs/$ENV_NAME/bin/Rscript"
[ -x "$RSCRIPT" ] || { echo "❌ 找不到 Rscript: $RSCRIPT" | tee -a "$LOG"; exit 2; }
echo "#TASK:PARAM rscript=$RSCRIPT" | tee -a "$LOG"
echo "#TASK:PARAM input_mb=$(du -m "$INPUT" | cut -f1)" | tee -a "$LOG"

echo "#TASK:STAGE run" | tee -a "$LOG"
set +e
"$RSCRIPT" "$SCRIPT_DIR/$STAGE" "$INPUT" "$WORKDIR" "$@" 2>&1 | tee -a "$LOG"
RC=${PIPESTATUS[0]}
set -e

if [ "$RC" -eq 0 ]; then
  echo "#TASK:PROGRESS 1.0 job ok" | tee -a "$LOG"
  echo "✅ 完成（exit=0）日志: $LOG"
else
  echo "❌ 失败（exit=$RC）日志: $LOG —— 检查点保留，修好重投会跳过已完成阶段"
fi
exit "$RC"