#!/usr/bin/env bash
# 唤醒幂等核验探针 —— 一条命令回答「这批步骤是不是已经跑完了」
# 用法： bash wakeup_idempotent_probe.sh <results/<sid> 目录>
# 全只读，不改任何东西；退出码 0 = 四问全过（视为已完结，不重跑分析）
set -u
SID_DIR="${1:-.}"
cd "$SID_DIR" || { echo "❌ 目录不存在: $SID_DIR"; exit 2; }
fail=0

echo "== 会话目录: $(pwd)"

echo "== ① task_plan 进度"
if [ -f task_plan.md ]; then
  und=$(grep -c '^- \[ \]' task_plan.md || true)
  don=$(grep -c '^- \[x\]' task_plan.md || true)
  echo "   未勾选=$und  已完成=$don"
  [ "${und:-0}" -ne 0 ] && { echo "   ⚠️ 仍有未勾选项 → 不是收尾态"; fail=1; }
else
  echo "   ⚠️ 无 task_plan.md"; fail=1
fi

echo "== ② 产物"
figs=$(ls figures 2>/dev/null | wc -l | tr -d ' ')
tabs=$(ls results/*.csv 2>/dev/null | wc -l | tr -d ' ')
zero=$(find . -type f -size 0 2>/dev/null | wc -l | tr -d ' ')
echo "   figures=$figs  results_csv=$tabs  0字节=$zero"
[ "${figs:-0}" -eq 0 ] && { echo "   ⚠️ 无图 → rail_review(post) 必不过"; fail=1; }
[ "${zero:-0}" -ne 0 ] && { echo "   ⚠️ 存在 0 字节文件"; find . -type f -size 0; fail=1; }

echo "== ③ 辩论归档（两层：conclusions=会话摘要，log=裁决本体）"
ls -1 conclusions/debate_*.json 2>/dev/null | sed 's/^/   摘要: /'
ls -1 log/debate_*.json 2>/dev/null | sed 's/^/   裁决: /' || echo "   （无 log/debate_*.json）"
if [ -z "$(ls -1 log/debate_*.json 2>/dev/null)" ] && [ -z "$(ls -1 conclusions/debate_*.json 2>/dev/null)" ]; then
  echo "   ⚠️ 两份都不存在 → 辩论确实没做；只有 conclusions 缺就是读错文件，别误判"
fi

echo "== ④ run_record / 内核残留"
echo "   run_record: $(ls -1 log/run_record_*.json 2>/dev/null | wc -l | tr -d ' ') 条"

echo
if [ "$fail" -eq 0 ]; then
  echo "✅ 四问全过：视为已完结 —— 只复跑 rail_review(post) 交差，不重跑分析、不重辩同一 topic"
else
  echo "❌ 有未过项（见上方 ⚠️）：只补该缺陷，不要整体重跑"
fi
exit "$fail"