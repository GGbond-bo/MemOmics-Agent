#!/usr/bin/env bash
# terminal_session_fingerprint.sh
# 终态会话「非进程类」唤醒指纹 —— 一条命令取全，守 E6「round 内 terminal ≤1 条」。
#
# 适用：文献 / 交付物 / 专利 类会话（没有 Rscript/python 分析进程，Step 3 的进程源与 GPU 源
#       全是空跑，为"凑三源"去跑 nvidia-smi/tasklist 只会白烧 token + 触发循环检测）。
# 取三源：① 唤醒源（loopx registry + task_state）② 载体指纹（核心产物 md5）
#        ③ 交付物字节 + mtime，外加「晚于 task_plan mtime 的未记账候选」。
#
# 用法: bash terminal_session_fingerprint.sh <会话目录> [载体相对路径] [交付目录]
#   bash terminal_session_fingerprint.sh E:/MemOmics-Agent/results/memomics-xxxx data/cards.json deliverables
#
# 判读：md5 同值（记"第 N 次同值"）+ 交付物字节/时间戳全同 + 无未记账产出 ⇒ 零写入收敛轮。

SID_DIR="${1:?usage: $0 <session_dir> [artifact_rel=data/cards.json] [deliverables=deliverables]}"
ART="${2:-data/cards.json}"
DELIV="${3:-deliverables}"

cd "$SID_DIR" || { echo "FATAL: cannot cd $SID_DIR"; exit 1; }

echo "== PLAN (baseline = task_plan mtime；⛔ 不是 Runtime State.started_at) =="
ls -l --time-style='+%Y-%m-%d %H:%M' task_plan.md 2>/dev/null || echo "MISSING: task_plan.md"
# ISO 格式直接喂 find -newermt（勿用 awk '{print $6,$7,$8}'——中文区域会给 "8月 9 10:47"）
BASE="$(ls -l --time-style='+%Y-%m-%d %H:%M' task_plan.md 2>/dev/null | awk '{print $6" "$7}')"
echo "baseline = ${BASE:-<none>}"

echo "== WAKEUP-SOURCE =="
echo "-- loopx registry:"
if [ -f .loopx/registry.json ]; then
  grep -m1 '"status"' .loopx/registry.json 2>/dev/null || echo "  (status not matched)"
  grep -m1 '"quota"'  .loopx/registry.json 2>/dev/null || true
  echo "  ↳ status=active ⇒ LoopX 周期唤醒是唤醒源（与完成契约无关，只能由用户改 paused + quota.compute=0 结束）"
else
  echo "  NO_LOOPX (.loopx/registry.json 不存在 ⇒ 唤醒源不是 LoopX)"
fi
echo "-- task_state:"
if [ -f .task_state.json ]; then
  head -c 300 .task_state.json; echo
  echo "  ↳ armed=true + reason 含 user message ⇒ 用户消息武装（合法新任务轮，不是死循环）"
  echo "  ↳ armed=false ⇒ 非用户消息 ⇒ 与上面的 loopx status 合看（E5 三分法）"
else
  echo "  NO_TASKSTATE"
fi

echo "== ARTIFACT-MD5 (内容零漂移的主指纹) =="
if [ -f "$ART" ]; then
  md5sum "$ART"
  ls -l --time-style='+%Y-%m-%d %H:%M' "$ART"
else
  echo "MISSING: $ART  （换一个核心产物路径重跑；md5 比文件个数硬）"
fi

echo "== DELIVERABLES (字节 + mtime 全同 = 未触发重渲染) =="
if [ -d "$DELIV" ]; then
  ls -l --time-style='+%Y-%m-%d %H:%M' "$DELIV" | grep -vE '\.bak|_backup|_old|\barchive' || echo "  (only backups, no live deliverables)"
else
  echo "NO_DIR: $DELIV"
fi

echo "== UNBOOKED-CANDIDATES (晚于 plan mtime 的非系统文件) =="
if [ -n "$BASE" ]; then
  find . -newermt "$BASE" -type f 2>/dev/null \
    | grep -vE '\.loopx|token_usage|system_log|\.log|task_plan|\.memory/|\.task_state\.json|notes\.md|REQUIREMENTS\.md|alerts\.json' \
    | head -10 || true
  echo "  ↳ 空 = 无未记账产出。⚠️ 命中请先自问：是【产物】还是【本会话自己的记账文件】？后者不补账。"
else
  echo "  SKIP: 无可用基线（task_plan.md 不在本目录？）"
fi

echo "== DONE =="
exit 0