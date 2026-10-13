#!/usr/bin/env bash
# tex_log_root_cause.sh — 从被 NUL 污染 / 超长的 XeLaTeX(MiKTeX) 日志里定位「真因」
#
# 为什么需要它（2026-10-12 实测教训）：
#   1) MiKTeX 递归失控时日志被 NUL(`^^@`) 灌成几十 MB（实测 12.9 MB / 15.9 万行），直接 read_file 必炸；
#   2) 更坑的是：清洗后**第一个 `!` 报错往往不是根因**。实测第 76 行
#      `! Transform components aren't all known.` 是 MiKTeX 用 METAFONT 现场生成 `othello` 的 OT.mf
#      抛的无害噪声（伴随 `Running miktex-mf.exe` / `Font metrics written on OT.tfm`），
#      据它排查会完全跑偏；真正的根因（`fontspec Error: The font "FontAwesome" cannot be found`）
#      在**第 4322 行**。
#      ⇒ 必须**按语义 grep**，不要抓第一个 `!`。
#
# 用法:
#   bash tex_log_root_cause.sh <log 文件> [语义正则(可省)]
# 例:
#   bash tex_log_root_cause.sh results/miktex_compile_test/cv-01.compile.log
set -uo pipefail

LOG="${1:?用法: tex_log_root_cause.sh <log 文件> [语义正则]}"
PAT="${2:-fontspec Error|cannot be found|Undefined control sequence|LaTeX Error|! Package .* Error|File .* not found|TeX capacity exceeded|Emergency stop|Missing}"

[ -f "$LOG" ] || { echo "❌ 日志不存在: $LOG"; exit 2; }

CLEAN="$(mktemp)"
tr -d '\000' < "$LOG" | grep -v '^\^@' > "$CLEAN"

echo "清洗后行数: $(wc -l < "$CLEAN")    (原文件 $(wc -c < "$LOG") 字节)"
echo
echo "=== ① 语义错误（真正候选根因，按出现顺序 —— 从这里开始排查）==="
grep -n -E "$PAT" "$CLEAN" | head -25 || echo "(无)"
echo
echo "=== ② 首个 \`! \` 行 —— 仅供定位位置；常为 METAFONT/字体生成噪声，勿直接当根因 ==="
grep -n '^! ' "$CLEAN" | head -5 || echo "(无)"
echo
echo "=== ③ METAFONT 现场生成噪声行数（>0 说明 ② 极可能是噪声）==="
grep -c -E "Running miktex-mf\.exe|Font metrics written on" "$CLEAN"
echo
echo "=== ④ 字体解析线索（Path= / .otf / .ttf / 字体目录宏）==="
grep -n -E "\.otf|\.ttf|Path=|FontsDir|FontsPackageDir|theabsdir|OSFONTDIR" "$CLEAN" | head -15 || echo "(无)"
echo
echo "=== ⑤ 递归 / 容量失控证据（症状，不是原因）==="
grep -n -E "wrong@fontshape|TeX capacity exceeded|pool size|No room for a new" "$CLEAN" | head -5 || echo "(无)"
echo
echo "提示：先看 ①，别被 ② 带偏。字体类报错 → 转 SKILL.md §六 与 references/cv01-fontawesome-case.md"

rm -f "$CLEAN"