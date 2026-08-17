#!/bin/bash
# verify_watcher.sh — 验证输出-watcher 脚本的三分支逻辑（DONE / PROC_DIED / TIMEOUT）
# 用法: bash verify_watcher.sh <watcher_script_path>
# 返回: exit 0 = 全部 PASS; exit 1 = 有 FAIL
# 2026-08-08 唤醒 #1 实测: 运行时验证只证明"进程活着"，不证明 watcher 逻辑正确；
# 本脚本在临时目录 mock 三分支，验证完自清理，不污染真实工作目录。
set -u
WATCHER="${1:?用法: bash verify_watcher.sh <watcher_script_path>}"
[ -f "$WATCHER" ] || { echo "❌ watcher 不存在: $WATCHER"; exit 1; }

TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
PASS=0; FAIL=0

echo "== A. watcher 语法 =="
if bash -n "$WATCHER" 2>&1; then echo "  ✅ bash -n 通过"; PASS=$((PASS+1)); else echo "  ❌ 语法错误"; FAIL=$((FAIL+1)); fi

echo "== B. 分支1: 产出文件出现 → DONE + exit 0 =="
mkdir -p "$TMP/mock"
# 预置期望产出文件（按 watcher 里检查的产出名替换；缺省常见三件套）
for f in human_proj_annotated.rds human_cluster_annotation.csv human_umap_celltype.png; do
  touch "$TMP/mock/$f" 2>/dev/null || true
done
sed "s|OUT=/[^ ]*|OUT=$TMP/mock|" "$WATCHER" > "$TMP/mock_watcher.sh" 2>/dev/null \
  || sed "s|OUT=[^ ]*|OUT=$TMP/mock|" "$WATCHER" > "$TMP/mock_watcher.sh"
OUT1=$(bash "$TMP/mock_watcher.sh" 2>&1); RC1=$?
if echo "$OUT1" | grep -q "DONE" && [ "$RC1" -eq 0 ]; then
  echo "  ✅ 产出检测分支正确 (exit=$RC1): $(echo "$OUT1" | head -1)"; PASS=$((PASS+1))
else
  echo "  ❌ 产出分支失败 RC=$RC1 (若 watcher 检查别的产出名，先 touch 对应文件再跑)"; FAIL=$((FAIL+1))
fi

echo "== C. 分支2: 无进程且无产出 → PROC_DIED + exit 1 =="
mkdir -p "$TMP/mock2"
sed "s|OUT=/[^ ]*|OUT=$TMP/mock2|; s|sleep [0-9]*|sleep 1|" "$WATCHER" > "$TMP/mock_watcher2.sh" 2>/dev/null \
  || sed "s|OUT=[^ ]*|OUT=$TMP/mock2|; s|sleep [0-9]*|sleep 1|" "$WATCHER" > "$TMP/mock_watcher2.sh"
OUT2=$(bash "$TMP/mock_watcher2.sh" 2>&1); RC2=$?
if echo "$OUT2" | grep -q "PROC_DIED\|DIED" && [ "$RC2" -eq 1 ]; then
  echo "  ✅ 进程死分支正确 (exit=$RC2)"; PASS=$((PASS+1))
else
  echo "  ❌ 进程死分支失败 RC=$RC2 (若 watcher 用别的死进程标识，改 grep 模式)"; FAIL=$((FAIL+1))
fi

echo "== D. 超时分支逻辑 =="
if grep -q "TIMEOUT" "$WATCHER"; then
  echo "  ✅ 超时分支存在"; PASS=$((PASS+1))
else
  echo "  ❌ 超时分支缺失"; FAIL=$((FAIL+1))
fi

echo ""
echo "PASS=$PASS FAIL=$FAIL"
[ "$FAIL" -eq 0 ] && exit 0 || exit 1
