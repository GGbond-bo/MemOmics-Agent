#!/bin/bash
# watchdog_v3 — 最小可靠串行任务看门狗模板
# 用法：改下面 CONFIG 段的 5 个变量，然后 PowerShell Start-Process 启动
#
# 设计原则：
#   1. 锁文件防多实例
#   2. 串行：检测到 Rscript=0 才启动下一个
#   3. 已完成的自动跳过（检查输出目录是否存在）
#   4. 全完成后自动退出
#   5. 脱离 Hermes 生命周期（PowerShell Start-Process 启动）

# ====== CONFIG — 改这里 ======
OUTDIR="E:/path/to/output_dir"                    # 输出目录（每个样本一个子目录）
LOGDIR="E:/path/to/logs"                          # 样本日志目录
RSCRIPT="/path/to/Rscript.exe"                    # Rscript 全路径
CREATE_SCRIPT="E:/path/to/process_sample.R"       # 单样本处理脚本
WORKDIR="E:/path/to/workdir"                      # 工作目录
MLOG="E:/path/to/monitor.log"                     # 监控日志
LOCKFILE="${MLOG%.log}.watchdog_v3.lock"           # 锁文件

# 剩余样本列表（排除已完成的）
REMAINING=(sample_1 sample_2 sample_3)

TOTAL=${#REMAINING[@]}  # 总样本数
# ====== CONFIG END ======

# 防多实例
if [ -f "$LOCKFILE" ]; then
    echo "[$(date '+%F %T')] watchdog_v3 SKIP: lock exists" >> "$MLOG"
    exit 0
fi
touch "$LOCKFILE"

echo "WATCHDOG_V3 START $(date '+%F %T')" >> "$MLOG"

while true; do
    sleep 60

    # 检查是否有 Rscript 在跑
    RSCRIPT_COUNT=$(powershell -Command "(Get-Process Rscript -ErrorAction SilentlyContinue).Count" 2>/dev/null)
    [ -z "$RSCRIPT_COUNT" ] && RSCRIPT_COUNT=0

    # 检查已完成数
    DONE_COUNT=$(ls -d "$OUTDIR"/*/ 2>/dev/null | wc -l)

    echo "[$(date '+%F %T')] watchdog_v3 procs=$RSCRIPT_COUNT done=$DONE_COUNT/$TOTAL" >> "$MLOG"

    # 没有 Rscript 在跑 → 启动下一个
    if [ "$RSCRIPT_COUNT" -eq 0 ]; then
        for SAMPLE in "${REMAINING[@]}"; do
            SAMPLE_DIR="$OUTDIR/$SAMPLE"
            if [ ! -d "$SAMPLE_DIR" ]; then
                echo "[$(date '+%F %T')] watchdog_v3 LAUNCH $SAMPLE" >> "$MLOG"
                LOGFILE="$LOGDIR/$SAMPLE.log"
                cd "$WORKDIR" && "$RSCRIPT" "$CREATE_SCRIPT" "$SAMPLE" > "$LOGFILE" 2>&1 &
                break
            fi
        done
    fi

    # 全部完成 → 退出
    if [ "$DONE_COUNT" -ge "$TOTAL" ]; then
        echo "[$(date '+%F %T')] watchdog_v3 ALL DONE ($DONE_COUNT/$TOTAL)" >> "$MLOG"
        rm -f "$LOCKFILE"
        exit 0
    fi
done
