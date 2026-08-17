#!/bin/bash
# monitor-serial-loop.sh — 自包含后台监控循环（脱离子会话，可挂 terminal(background=true)）
# 用途: 监控脱离式串行批处理（run_serial.sh / cmd.exe /c 启动的 R/Python worker）
# 每 N 秒三源检查: ①PowerShell进程数 ②DONE_MARK计数 ③最新日志mtime
# 异常(进程0 + 日志停更超阈值) → 写 alerts.json; 全部完成 → 写 COMPLETE 退出(触发 notify_on_complete)
# 2026-08-07 memomics-1135ed52 实测: GSE278576 40样本 ArchR 串行, 5/5 逻辑判定 + 3/3 循环行为验证通过

# ============ 每项目必改 ============
DONE_DIR="/e/专利/Human_Hippocampus_ATAC/ArchR_Arrow_QC_Filtered"   # DONE_MARK 根目录(含 {s}/{s}_filtered_cells.csv 的样本=完成)
LOG_DIR="/e/MEMOMICS_HOME/results/<SESSION>/batch/logs"            # 批处理逐样本日志目录
MON_LOG="/e/MEMOMICS_HOME/results/<SESSION>/batch/monitor.log"     # 监控日志(循环追加)
ALERT_FILE="/e/MEMOMICS_HOME/results/<SESSION>/batch/alerts.json"  # 告警文件(异常写/恢复清)
TOTAL=40              # 总样本数
STALL_MIN=12          # 日志停更分钟数阈值(>且无进程=停滞)
POLL_SEC=180          # 轮询间隔(秒)
PROC_NAME="Rscript"   # worker 进程名(查 CellBender 改 python)
# ===================================

echo "MONITOR START $(date '+%Y-%m-%d %H:%M:%S')" >> "$MON_LOG"

while true; do
  TS=$(date '+%Y-%m-%d %H:%M:%S')
  NOW=$(date +%s)

  # ① 进程数 — 用 PowerShell Measure-Object .Count（本环境实测可靠，tasklist //FI 与 Where-Object -match 曾静默返回空）
  PROC_COUNT=$(powershell.exe -NoProfile -Command "(Get-Process $PROC_NAME -ErrorAction SilentlyContinue | Measure-Object).Count" 2>/dev/null | tr -d '\r')
  [ -z "$PROC_COUNT" ] && PROC_COUNT=0

  # ② 产出数 — DONE_MARK 计数(唯一可靠进度, 数 .arrow 会虚高, 见铁规4)
  DONE_COUNT=$(ls "$DONE_DIR"/*/*_filtered_cells.csv 2>/dev/null | wc -l)

  # ③ 最新日志 mtime 年龄
  LATEST_LOG=$(ls -t "$LOG_DIR"/*.log 2>/dev/null | head -1)
  if [ -n "$LATEST_LOG" ]; then
    LOG_MTIME=$(stat -c %Y "$LATEST_LOG" 2>/dev/null)
    LOG_AGE=$(( (NOW - LOG_MTIME) / 60 ))
    LOG_NAME=$(basename "$LATEST_LOG")
  else
    LOG_AGE=999; LOG_NAME="none"
  fi

  echo "[$TS] done=$DONE_COUNT/$TOTAL procs=$PROC_COUNT log=$LOG_NAME age=${LOG_AGE}m" >> "$MON_LOG"

  # 停滞判定: 未完成 + 无进程 + 日志停更超阈值
  ALERT=""
  if [ "$DONE_COUNT" -lt "$TOTAL" ] && [ "$PROC_COUNT" -eq 0 ] && [ "$LOG_AGE" -gt "$STALL_MIN" ]; then
    ALERT="STALL: no $PROC_NAME, log $LOG_NAME frozen ${LOG_AGE}m, done=$DONE_COUNT/$TOTAL"
  elif [ "$DONE_COUNT" -lt "$TOTAL" ] && [ "$PROC_COUNT" -eq 0 ] && [ -z "$LATEST_LOG" ]; then
    ALERT="STALL: no log files at all, done=$DONE_COUNT/$TOTAL"
  fi

  if [ -n "$ALERT" ]; then
    echo "[$TS] ALERT: $ALERT" >> "$MON_LOG"
    echo "{\"time\":\"$TS\",\"severity\":\"high\",\"message\":\"$ALERT\",\"done\":$DONE_COUNT,\"total\":$TOTAL}" > "$ALERT_FILE"
  elif [ -f "$ALERT_FILE" ]; then
    rm -f "$ALERT_FILE"   # 恢复后清除 alert
  fi

  # 完成判定: 全部 DONE → 写 COMPLETE + 退出(notify_on_complete 触发)
  if [ "$DONE_COUNT" -ge "$TOTAL" ]; then
    echo "[$TS] COMPLETE: all $TOTAL samples done" >> "$MON_LOG"
    echo "{\"time\":\"$TS\",\"severity\":\"info\",\"message\":\"ALL $TOTAL SAMPLES COMPLETE\",\"done\":$DONE_COUNT,\"total\":$TOTAL}" > "$ALERT_FILE"
    break
  fi

  sleep "$POLL_SEC"
done
echo "MONITOR EXIT $(date '+%Y-%m-%d %H:%M:%S')" >> "$MON_LOG"
