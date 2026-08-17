#!/bin/bash
# ============================================================================
# verify_wakeup.sh — MemOmics 唤醒三源验证脚本（wakeup-progress-check skill）
#
# 为什么存在：唤醒核查反复用手打 tasklist 变体（//FI / //FO CSV / 2>/dev/null
# 组合）导致假阴性（#9/#11/#25/#35/#43/#44/#46/#62/#65/#76/#82 十余次实证）。
# 把唯一可靠命令固化为脚本，Agent 跑脚本而不是从记忆里拼命令。
#
# 用法：
#   bash scripts/verify_wakeup.sh <会话目录> [基线时间]
#     例：bash scripts/verify_wakeup.sh MEMOMICS_HOME/results/memomics-1c1890da "2026-08-09 10:45"
#   基线时间缺省 = <会话目录>/task_plan.md 的 mtime
#
# 输出：三源报告（进程/GPU/磁盘）+ 判定提醒。空输出≠无进程，先质疑过滤器。
# ============================================================================
set -u

DIR="${1:-.}"
BASELINE="${2:-}"

# ---- MSYS 路径转换（find 需要 unix 风格路径，E:/x → /e/x） ----
if command -v cygpath >/dev/null 2>&1; then
  DIR_FS=$(cygpath -u "$DIR" 2>/dev/null || echo "$DIR")
else
  DIR_FS=$(echo "$DIR" | sed -E 's|^([A-Za-z]):|/\L\1|')
fi

echo "===== [源1] 进程源 — plain tasklist（唯一可靠命令；禁 //FI //FO CSV 变体） ====="
tasklist 2>/dev/null | grep -iE 'python\.exe|Rscript\.exe|node\.exe' || echo "NO_ANALYSIS_PROC (0 命中)"
echo ""
echo "  期望: 5 系统组件基线(webui×2 + guardian×2 + _kernel_worker.R) + 2 node = 7 行"
echo "  ⚠️ 若 0 命中但会话正通过 webui 运行 → 过滤器假阴性！复核: tasklist 2>/dev/null | head -30"
echo ""

echo "===== [源2] GPU 源 ====="
nvidia-smi --query-gpu=utilization.gpu,memory.used,memory.total --format=csv,noheader 2>/dev/null
echo "--- compute-apps (C+G=桌面应用; Compute=分析进程; [Insufficient Permissions] 不可判类型) ---"
nvidia-smi --query-compute-apps=pid,process_name,used_memory --format=csv 2>/dev/null | grep -v 'Insufficient Permissions' || echo "NO_COMPUTE_APPS"
echo ""

echo "===== [源3] 磁盘源 — find -newermt（排除 .loopx/jsonl/log/task_plan 系统文件） ====="
if [ -z "$BASELINE" ]; then
  BASELINE=$(ls -l "$DIR/task_plan.md" 2>/dev/null | awk '{print $6,$7,$8}')
fi
if [ -z "$BASELINE" ]; then
  echo "WARN: 未找到 task_plan.md 且未给基线时间 → 跳过磁盘源"
else
  echo "基线: $BASELINE"
  find "$DIR_FS" -newermt "$BASELINE" -type f 2>/dev/null | grep -vE '\.loopx|token_usage|system_log|\.log|task_plan' || echo "无新产出（终态候选）"
fi
echo ""

echo "===== 判定提醒 ====="
echo "1. 三源一致才下结论；进程源 0 命中 → 先 plain 复核再写 '无匹配'"
echo "2. 终态唤醒记录必须写全 5 基线组件清单（或引用前条），不得只写 '无命中'"
echo "3. 追加记录前: read_file 清点 '## 🏁 唤醒 #N 记录' 块数; ≥5 先合并旧 4 条再追加"
echo "4. 唤醒第一步 = skill_view(wakeup-progress-check)，禁止凭 memory 跑三源"
