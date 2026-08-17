#!/usr/bin/env bash
# ============================================================
# watchdog-serial.sh — 独立自动重启看门狗（standalone auto-restart watchdog）
# 适用：run_serial.sh（串行调度器）可能静默死亡时，需要一个脱离 Hermes 生命周期的
#       看门狗来自动重启调度器。2026-08-07 memomics-1135ed52 端到端验证通过：
#       watchdog 检测 procs=0 + done<TOTAL → 自动启动 run_serial_v2.sh (PID 27369)
#       → hc11 18:08:56 启动 → 18:11:40 推进 25%。批处理无人干预自愈。
#
# 与 monitor-serial-loop.sh 的分工：
#   monitor-serial-loop.sh = 只报状态（写 monitor.log + alerts.json），不重启
#   watchdog-serial.sh     = 只做重启决策（检测到停滞 → 重启 sanctioned 调度器）
#   ⛔ 不要把这个重启逻辑塞进 monitor 内部——曾导致"自动重启钩子硬编码旧脚本名"
#      级联崩溃（见 references/auto-restart-hook-stale-script.md）
#
# 每项目改 6 个变量：DONE_DIR / TOTAL / RUN_SCRIPT / MON_LOG / PROC_NAME / SCRIPT_DIR
# ============================================================

# ---------- 每项目必改 ----------
DONE_DIR="/e/专利/Human_Hippocampus_ATAC/ArchR_Arrow_QC_Filtered"   # DONE_MARK 目录（含 {s}/{s}_filtered_cells.csv）
TOTAL=40                                                             # 总样本数
RUN_SCRIPT="run_serial_v2.sh"                                        # ⚠️ 必须是当前 sanctioned 版本，不是旧名！
SCRIPT_DIR="/e/MEMOMICS_HOME/results/memomics-1135ed52/batch"       # 调度器所在目录
MON_LOG="$SCRIPT_DIR/monitor.log"                                    # 追加写入同一 monitor.log 或独立 watchdog.log
PROC_NAME="Rscript"                                                  # worker 进程名（唯一 token：Rscript/python/cellbender）
# ----------------------------------

COOLDOWN=300   # 启动调度器后冷却秒数（防启动瞬间 procs 未起又触发重复重启）
POLL=120       # 轮询间隔秒数（用户要求 2 分钟）

# 可靠进程计数：简单形 Get-Process（tasklist //FI 在 git-bash 静默空，见 SKILL 铁规 0）
count_procs() {
    powershell.exe -NoProfile -Command "(Get-Process $PROC_NAME -ErrorAction SilentlyContinue | Measure-Object).Count" 2>/dev/null | tr -d '\r'
}

# 可靠完成计数：DONE_MARK（.arrow 根目录计数会虚高——saveArchRProject 嵌套副本，见 SKILL 铁规 4）
count_done() {
    ls "$DONE_DIR"/*/*_filtered_cells.csv 2>/dev/null | wc -l
}

# 防重复重启：pgrep 双保险（检查调度器是否已在跑）
scheduler_running() {
    ps -ef 2>/dev/null | grep -E "$RUN_SCRIPT" | grep -v grep | grep -q . 
}

last_restart_ts=0
log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" >> "$MON_LOG"; }

log "WATCHDOG START $(date '+%Y-%m-%d %H:%M:%S') (proc=$PROC_NAME total=$TOTAL cooldown=${COOLDOWN}s)"

while true; do
    procs=$(count_procs)
    done_count=$(count_done)
    now=$(date +%s)

    log "watchdog procs=$procs done=$done_count/$TOTAL"

    if [ -z "$procs" ] || [ -z "$done_count" ]; then
        log "watchdog WARN: probe returned empty (procs='$procs' done='$done_count') — 探测失效≠无进程，本轮不重启"
        sleep "$POLL"; continue
    fi

    if [ "$done_count" -ge "$TOTAL" ]; then
        log "watchdog COMPLETE done=$done_count/$TOTAL — 全部完成，退出"
        break
    fi

    if [ "$procs" -eq 0 ] && [ "$done_count" -lt "$TOTAL" ]; then
        elapsed=$(( now - last_restart_ts ))
        if [ "$elapsed" -lt "$COOLDOWN" ]; then
            log "watchdog procs=0 done=$done_count/$TOTAL — 冷却期内（${elapsed}s<${COOLDOWN}s），等待"
        elif scheduler_running; then
            log "watchdog procs=0 done=$done_count/$TOTAL — 调度器已在跑（pgrep 命中），不重复启动"
        else
            log "watchdog procs=0 done=$done_count/$TOTAL — START $RUN_SCRIPT"
            ( cd "$SCRIPT_DIR" && nohup bash "$RUN_SCRIPT" >> "$SCRIPT_DIR/run_serial_auto.out" 2>&1 & )
            last_restart_ts=$(date +%s)
            # 20s 后验证 worker 出现
            sleep 20
            new_procs=$(count_procs)
            if [ -n "$new_procs" ] && [ "$new_procs" -gt 0 ]; then
                log "watchdog OK: worker detected (procs=$new_procs)"
            else
                log "watchdog WARN: no worker after 20s — 可能启动失败或仍在预热，下轮再看"
            fi
            continue
        fi
    fi

    sleep "$POLL"
done
