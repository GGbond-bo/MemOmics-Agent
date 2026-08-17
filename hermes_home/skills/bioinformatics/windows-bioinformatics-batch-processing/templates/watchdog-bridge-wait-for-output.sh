#!/bin/bash
# watchdog-bridge-wait-for-output.sh — 锁死锁/监控层死亡时的兜底恢复脚本
# 用途: watchdog 主循环卡死(mkdir 锁死锁)或 run_serial 已 ALL DONE 时，
#       等目标样本输出目录(DONE_MARK)出现 → 自动补跑剩余样本。
# 背景: worker 的父进程是 deadlock watchdog → 不能杀 watchdog(会丢 worker 进度)
#       → 用本 bridge 独立兜底，脱离 Hermes 生命周期。
# 部署: powershell Start-Process -WindowStyle Hidden -FilePath bash.exe \
#         -ArgumentList '<本脚本绝对路径>'      (不用 nohup/&, 见铁规 2)
# 部署后立即验证 5 项: bash -n / 进程存活(Get-CimInstance CommandLine) /
#       START 心跳 / worker 不受影响 / 磁盘进度不变 (铁规 13.5 行为级验证)
# ---------------------------------------------------------------------
# ── CONFIG (每项目改这里) ──────────────────────────────────────────────
OUTDIR="E:/专利/Human_Hippocampus_ATAC/ArchR_Arrow_QC_Filtered"   # DONE_MARK 输出目录
WAIT_SAMPLE="GSM8549648_hc73"                                      # 等待完成的样本目录名
RUN_SAMPLE="GSM8549649_hc19"                                       # 要补跑的剩余样本名
LOGDIR="MEMOMICS_HOME/results/<session>/batch/logs"             # 样本日志目录
RSCRIPT="C:/Program Files/R/R-4.5.3/bin/x64/Rscript.exe"            # R 可执行
CREATE_SCRIPT="MEMOMICS_HOME/results/<session>/create_arrow_qc.R" # 样本处理脚本
WORKDIR="MEMOMICS_HOME/results/<session>"                       # 工作目录
BRIDGE_LOG="$LOGDIR/../bridge.log"                                  # 桥接心跳日志
SETTLE_SEC=30            # DONE_MARK 出现后等文件 settle 的秒数
TIMEOUT_MIN=180          # 超时分钟数(大样本留足余量)
HEARTBEAT_EVERY=15       # 每 N 轮写一次心跳
# ─────────────────────────────────────────────────────────────────────

echo "[$(date '+%F %T')] bridge START: waiting for $WAIT_SAMPLE output dir" >> "$BRIDGE_LOG"

# 幂等: 目标样本已完成 → 直接退出
if [ -d "$OUTDIR/$RUN_SAMPLE" ]; then
    echo "[$(date '+%F %T')] $RUN_SAMPLE already done, exit" >> "$BRIDGE_LOG"
    exit 0
fi

# 主循环: 等 WAIT_SAMPLE 的 DONE_MARK 输出目录出现
for i in $(seq 1 "$TIMEOUT_MIN"); do
    if [ -d "$OUTDIR/$WAIT_SAMPLE" ]; then
        echo "[$(date '+%F %T')] $WAIT_SAMPLE output dir detected, launching $RUN_SAMPLE (settle ${SETTLE_SEC}s)" >> "$BRIDGE_LOG"
        sleep "$SETTLE_SEC"
        # 二次幂等: 检查是否已被其他机制(如 watchdog 恢复)启动
        if [ -d "$OUTDIR/$RUN_SAMPLE" ]; then
            echo "[$(date '+%F %T')] $RUN_SAMPLE already launched by another mechanism, exit" >> "$BRIDGE_LOG"
            exit 0
        fi
        cd "$WORKDIR" && "$RSCRIPT" "$CREATE_SCRIPT" "$RUN_SAMPLE" > "$LOGDIR/$RUN_SAMPLE.log" 2>&1
        echo "[$(date '+%F %T')] $RUN_SAMPLE LAUNCHED exit=$?" >> "$BRIDGE_LOG"
        exit 0
    fi
    # 心跳(每 HEARTBEAT_EVERY 轮 = 分钟写一次, 供唤醒轮次检查 bridge 活体)
    if [ $((i % HEARTBEAT_EVERY)) -eq 0 ]; then
        echo "[$(date '+%F %T')] bridge heartbeat: $WAIT_SAMPLE not done yet (i=$i)" >> "$BRIDGE_LOG"
    fi
    sleep 60
done

echo "[$(date '+%F %T')] bridge TIMEOUT (${TIMEOUT_MIN}min) $WAIT_SAMPLE not done, exit" >> "$BRIDGE_LOG"
exit 1
