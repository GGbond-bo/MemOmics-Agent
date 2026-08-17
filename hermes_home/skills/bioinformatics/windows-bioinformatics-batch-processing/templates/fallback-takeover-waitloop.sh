#!/bin/bash
# fallback_takeover_waitloop.sh — wait-loop 兜底接管：批处理收尾期 watchdog+guardian 双双失效时自动补跑剩余样本
# 场景：主循环已 ALL DONE，还剩 1 个样本（如失败需重试的 hc19）无人补跑；
#       watchdog 心跳停更（monitor.log mtime 冻结），guardian 也不在进程列表。
# 设计原则（本模板 2026-08-07 memomics-1135ed52 唤醒 #36 实测量产）：
#   - WAIT-LOOP：先等当前 in-flight 样本完成（输出目录出现），再决定是否接管 —— 绝不抢先启动
#   - 与 watchdog 共用同一 LOCKDIR（mkdir 原子锁 + 死 PID 自愈）：watchdog 恢复持锁 → 本脚本 SKIP，绝无双启动
#   - watchdog 心跳新鲜（<HEARTBEAT_STALE_S）→ 继续等，由 watchdog 处理
#   - watchdog 心跳停更（>=HEARTBEAT_STALE_S）→ 才接管锁 → 启动剩余样本
#   - 绝不 kill 任何进程；不重跑已完成样本（输出目录存在即跳过）
# 用法：改 CONFIG 段 7 个变量 → bash -n 语法检查 → 后台启动 →
#       部署前行为级验证（mock 三分支：已存在 / 心跳停更接管 / 心跳活跃等待）

# ═══ CONFIG ═══
OUTDIR="E:/OUTPUT_DIR"                          # DONE_MARK 输出根目录（含 GSM*/ 子目录）
LOGDIR="E:/BATCH/logs"                          # 逐样本日志目录
RSCRIPT="C:/Program Files/R/R-x.y.z/bin/x64/Rscript.exe"
CREATE_SCRIPT="E:/BATCH/create_sample.R"        # 单样本处理脚本（参数 = 样本名）
WORKDIR="E:/BATCH"                              # 运行工作目录
MLOG="E:/BATCH/monitor.log"                     # 心跳日志（watchdog 每轮 append，mtime = watchdog 活体）
LOCKDIR="E:/BATCH/.watchdog.lockdir"            # 必须与 watchdog 同一锁目录！
INFLIGHT_SAMPLE="GSM12345678_hc9"               # 正在跑的样本（等它输出目录出现）
REMAIN_SAMPLE="GSM12345679_hc19"                # 需要补跑的剩余样本
HEARTBEAT_STALE_S=180                            # 心跳停更多少秒算 watchdog 失效（watchdog 每 60s 写 → 3x 间隔）
# ═══════════

echo "[$(date '+%F %T')] fallback START (pid $$) wait-loop" >> "$MLOG"

# 剩余样本已存在 → 直接退出
if [ -d "$OUTDIR/$REMAIN_SAMPLE" ]; then
    echo "[$(date '+%F %T')] fallback: $REMAIN_SAMPLE 已有输出，退出" >> "$MLOG"; exit 0
fi

# ── Phase 1: 等 in-flight 样本完成（最多 180 轮 = 180min）──
i=0
while [ ! -d "$OUTDIR/$INFLIGHT_SAMPLE" ]; do
    i=$((i+1))
    [ $i -ge 180 ] && { echo "[$(date '+%F %T')] fallback ERROR: $INFLIGHT_SAMPLE 180min 未完成，放弃兜底" >> "$MLOG"; exit 1; }
    sleep 60
done
echo "[$(date '+%F %T')] fallback: $INFLIGHT_SAMPLE 输出目录已出现" >> "$MLOG"

# 给 watchdog 一个机会窗口启动剩余样本（2min）
sleep 120
[ -d "$OUTDIR/$REMAIN_SAMPLE" ] && { echo "[$(date '+%F %T')] fallback: $REMAIN_SAMPLE 已被处理，退出" >> "$MLOG"; exit 0; }

# ── Phase 2: 心跳新鲜则等 watchdog，停更才接管 ──
acquired=0
while [ $acquired -eq 0 ]; do
    ML_MTIME=$(stat -c %Y "$MLOG" 2>/dev/null || echo 0)
    AGE=$(( $(date +%s) - ML_MTIME ))
    if [ "$AGE" -lt "$HEARTBEAT_STALE_S" ]; then
        echo "[$(date '+%F %T')] fallback: watchdog 心跳活跃 (age=${AGE}s)，等其处理 $REMAIN_SAMPLE（60s 后复查）" >> "$MLOG"
        sleep 60
        if [ -d "$OUTDIR/$REMAIN_SAMPLE" ] || pgrep -f "$REMAIN_SAMPLE" >/dev/null 2>&1; then
            echo "[$(date '+%F %T')] fallback: watchdog 已处理 $REMAIN_SAMPLE，退出" >> "$MLOG"; exit 0
        fi
        i=$((i+1))
        [ $i -ge 30 ] && { echo "[$(date '+%F %T')] fallback: watchdog 活跃但 30min 未处理，接管" >> "$MLOG"; break; }
        continue
    fi
    # watchdog 失效（心跳停更）→ 接管锁（mkdir 原子锁；已判失效可强制清理 stale 锁）
    while ! mkdir "$LOCKDIR" 2>/dev/null; do
        rm -rf "$LOCKDIR" 2>/dev/null; sleep 2
    done
    echo $$ > "$LOCKDIR/pid"
    acquired=1
done

trap 'rm -rf "$LOCKDIR"; echo "[$(date "+%F %T")] fallback EXIT 释放锁" >> "$MLOG"' EXIT INT TERM HUP

# ── Phase 3: 补跑剩余样本 ──
[ -d "$OUTDIR/$REMAIN_SAMPLE" ] && { echo "[$(date '+%F %T')] fallback: $REMAIN_SAMPLE 已有输出，退出" >> "$MLOG"; exit 0; }
echo "[$(date '+%F %T')] fallback LAUNCH $REMAIN_SAMPLE" >> "$MLOG"
cd "$WORKDIR" && "$RSCRIPT" "$CREATE_SCRIPT" "$REMAIN_SAMPLE" > "$LOGDIR/$REMAIN_SAMPLE.log" 2>&1
RC=$?
if [ $RC -eq 0 ] && [ -d "$OUTDIR/$REMAIN_SAMPLE" ]; then
    echo "[$(date '+%F %T')] fallback: $REMAIN_SAMPLE OK exit=$RC" >> "$MLOG"
else
    echo "[$(date '+%F %T')] fallback: $REMAIN_SAMPLE FAILED exit=$RC" >> "$MLOG"
fi
exit $RC
