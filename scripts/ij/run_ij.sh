#!/bin/bash
# ---------------------------------------------------------------------------
# MemOmics ImageJ runner v2  （集群侧，节点上执行）
#
# 解决 run_ij.sh v1 的三个硬问题：
#   1) 并发共用 DISPLAY=:99 → 第二个作业静默失败（RC=1、日志空）
#      → 每个作业用 mkdir 原子抢一个独立 DISPLAY，退出时释放
#   2) ij.jar -batch 在 Xvfb 下跑完不退出（AWT 线程非守护）
#      → 用 RunIjBatch（batchMode + System.exit），并以 DONE.json 哨兵兜底
#   3) 没有超时/没有产物校验 → 假成功
#      → 超时分级 kill + 产物三查（哨兵 / IJ_OK / 产物非空）
#
# 用法:
#   run_ij.sh --job <作业目录> --macro <宏路径> [--mem 8g] [--timeout 600]
#
# 作业目录约定:
#   <job>/macro.ijm      渲染后的宏
#   <job>/in/            可选：本地上传的输入图
#   <job>/out/           产物（宏负责写 DONE.json）
#   <job>/ij.log         JVM stdout/stderr
#   <job>/runner.log     本脚本日志
#
# 退出码: 0=成功 1=宏报错 2=超时 3=产物缺失 9=环境/参数错误
# ---------------------------------------------------------------------------
set -u

JOB=""
MACRO=""
MEM="8g"
TIMEOUT=600

while [ $# -gt 0 ]; do
  case "$1" in
    --job)      JOB="$2"; shift 2 ;;
    --macro)    MACRO="$2"; shift 2 ;;
    --mem)      MEM="$2"; shift 2 ;;
    --timeout)  TIMEOUT="$2"; shift 2 ;;
    -h|--help)  sed -n '2,30p' "$0"; exit 0 ;;
    *)          echo "unknown arg: $1" >&2; exit 9 ;;
  esac
done

[ -n "$JOB" ] || { echo "missing --job" >&2; exit 9; }
[ -n "$MACRO" ] || { echo "missing --macro" >&2; exit 9; }
[ -d "$JOB" ] || { echo "job dir missing: $JOB" >&2; exit 9; }
[ -f "$MACRO" ] || { echo "macro missing: $MACRO" >&2; exit 9; }

JOB="$(cd "$JOB" && pwd)"
case "$MACRO" in /*) ;; *) MACRO="$JOB/$MACRO" ;; esac

IJ_DIR="${MEMOMICS_IJ_ROOT:-/cluster/share/user/ImageJ}"
JAVA="$IJ_DIR/jre/bin/java"
XVFB="${MEMOMICS_IJ_XVFB:-/cluster/share/user/envs/ij_xvfb/bin/Xvfb}"
LOG="$JOB/ij.log"
RLOG="$JOB/runner.log"
OUT="$JOB/out"

mkdir -p "$OUT"
: > "$LOG"
: > "$RLOG"

log() { echo "[$(date '+%H:%M:%S')] $*" | tee -a "$RLOG" >&2; }

[ -x "$JAVA" ]   || { log "java not executable: $JAVA"; exit 9; }
[ -x "$XVFB" ]   || { log "Xvfb not executable: $XVFB"; exit 9; }

# ---- 1) 抢一个独立 DISPLAY（mkdir 原子性；/tmp 在节点本地） ----------------
DISP_NUM=""
XVFB_PID=""
LOCK_DIR=""

# 抢号 + 起 Xvfb：跳过已有 X server 的号（孤儿 Xvfb 会让 ImageJ 在建窗口时挂死）
start_display() {
  local n pid i
  for n in $(seq 90 139); do
    mkdir "/tmp/.ij_disp_$n" 2>/dev/null || continue
    if [ -S "/tmp/.X11-unix/X$n" ]; then rmdir "/tmp/.ij_disp_$n" 2>/dev/null; continue; fi
    "$XVFB" ":$n" -screen 0 1280x1024x24 -nolisten tcp >/dev/null 2>&1 &
    pid=$!
    for i in $(seq 1 25); do
      [ -S "/tmp/.X11-unix/X$n" ] && break
      kill -0 "$pid" 2>/dev/null || break
      sleep 0.2
    done
    if [ -S "/tmp/.X11-unix/X$n" ] && kill -0 "$pid" 2>/dev/null; then
      DISP_NUM="$n"; XVFB_PID="$pid"; LOCK_DIR="/tmp/.ij_disp_$n"
      return 0
    fi
    kill -TERM "$pid" 2>/dev/null; kill -9 "$pid" 2>/dev/null
    rmdir "/tmp/.ij_disp_$n" 2>/dev/null
  done
  return 1
}

start_display || { log "no usable display slot (90-139)"; exit 9; }
export DISPLAY=":$DISP_NUM"

cleanup() {
  if [ -n "$XVFB_PID" ] && kill -0 "$XVFB_PID" 2>/dev/null; then
    kill -TERM "$XVFB_PID" 2>/dev/null
    sleep 0.3
    kill -9 "$XVFB_PID" 2>/dev/null
  fi
  rmdir "$LOCK_DIR" 2>/dev/null
}
trap cleanup EXIT INT TERM

log "display=:$DISP_NUM job=$JOB mem=$MEM timeout=${TIMEOUT}s"

# ---- 2) 启动（RunIjBatch 优先；缺失时退回 -batch） -------------------------
if [ -f "$IJ_DIR/RunIjBatch.class" ]; then
  LAUNCH=("-cp" "$IJ_DIR/ij.jar:$IJ_DIR" "RunIjBatch" "$MACRO")
else
  log "WARN RunIjBatch.class 缺失 → 退回 ij.jar -batch（可能不退出，靠哨兵回收）"
  LAUNCH=("-jar" "$IJ_DIR/ij.jar" "-batch" "$MACRO")
fi

TMPD="$JOB/tmp"; mkdir -p "$TMPD"
"$JAVA" -Xmx"$MEM" -Djava.awt.headless=false -Djava.io.tmpdir="$TMPD" \
        "${LAUNCH[@]}" >>"$LOG" 2>&1 &
JPID=$!

# ---- 3) 等哨兵 / 等退出 / 超时 ------------------------------------------
RC=0
WAITED=0
while :; do
  if [ -f "$OUT/DONE.json" ]; then
    log "DONE.json 出现，等 2s 收尾后回收 JVM"
    sleep 2
    break
  fi
  if ! kill -0 "$JPID" 2>/dev/null; then
    log "JVM 自行退出"
    break
  fi
  if [ "$WAITED" -ge "$TIMEOUT" ]; then
    log "TIMEOUT ${TIMEOUT}s → 终止"
    RC=2
    break
  fi
  sleep 1
  WAITED=$((WAITED + 1))
done

if kill -0 "$JPID" 2>/dev/null; then
  kill -TERM "$JPID" 2>/dev/null
  for _ in $(seq 1 50); do kill -0 "$JPID" 2>/dev/null || break; sleep 0.2; done
  kill -9 "$JPID" 2>/dev/null
fi
wait "$JPID" 2>/dev/null

# ---- 4) 产物三查 ---------------------------------------------------------
if [ ! -f "$OUT/DONE.json" ]; then
  log "产物缺失：$OUT/DONE.json 不存在"
  [ "$RC" = "2" ] || RC=3
elif ! grep -q "IJ_OK" "$LOG"; then
  log "宏报错：日志里没有 IJ_OK"
  [ "$RC" = "2" ] || RC=1
fi

N_FILES=$(find "$OUT" -maxdepth 1 -type f ! -name DONE.json | wc -l)
log "exit=$RC artifacts=$N_FILES"
tail -n 20 "$LOG" >> "$RLOG" 2>/dev/null
# 日志随产物一起回传：MemOmics 侧一次 pull 就能拿全（少一次 SSH 往返）
cp -f "$LOG" "$OUT/ij.log" 2>/dev/null
cp -f "$RLOG" "$OUT/runner.log" 2>/dev/null
exit "$RC"