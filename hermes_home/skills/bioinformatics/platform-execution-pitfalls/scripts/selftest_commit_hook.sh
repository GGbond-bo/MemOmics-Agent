#!/bin/sh
# selftest_commit_hook.sh —— .githooks/pre-commit 的非破坏性自检
#
# 用途：改过 .githooks/pre-commit / scripts/check_skills_gate.py / memomics/bio_tools/validate_kb.py
#       之后，验证「技能门禁 + KB 门禁」两条链路真的会跑、真的会拦（而不是只打印一行就放行）。
# 背景：这条链路易静默半失效 —— 踩过两次（2026-10-08）：
#       ① SKILLS_GATE=0 原先在 hook 开头直接 exit 0，连带把 KB 门禁也跳过了；
#       ② `git diff --cached --name-only` 默认给非 ASCII 路径加引号，而 KB 五级目录的类别目录
#          （01_生物学知识/02_质控参数/03_测序方法）全是中文 → `^memomics/knowledge_base/` 锚点
#          永不命中 → KB 门禁一直没触发过。
# 安全：只临时改一个 KB yaml 当靶子并暂存，验完 git reset + git checkout 还原；**不产生提交**。
# 用法：sh hermes_home/skills/bioinformatics/platform-execution-pitfalls/scripts/selftest_commit_hook.sh
set -u

ROOT=$(git rev-parse --show-toplevel 2>/dev/null) || { echo "不在 git 仓库里"; exit 2; }
cd "$ROOT" || exit 2

HOOK=.githooks/pre-commit
[ -f "$HOOK" ] || { echo "缺少 $HOOK —— 先装钩子：python scripts/install_git_hooks.py"; exit 2; }

echo "=== 0. 语法（patch 手滑插进字面 \\r 会让整段报 syntax error）==="
if ! bash -n "$HOOK"; then echo "SYNTAX_FAIL"; exit 1; fi
echo "SYNTAX_OK"

# 靶子：优先中文路径的 KB yaml —— 正好覆盖 quotepath 那条坑。
# -z + tr 是必须的：git 默认给非 ASCII 路径加引号，直接取用会得到带引号的假路径。
TARGET=$(git ls-files -z 'memomics/knowledge_base/*.yaml' | tr '\0' '\n' | head -1)
[ -n "$TARGET" ] || { echo "KB 里没找到 yaml，跳过"; exit 2; }
echo "靶子: $TARGET"

# 前置：靶子必须本来就是干净的，否则还原时会覆盖别人的增量
if [ -n "$(git status --porcelain -- "$TARGET")" ]; then
    echo "靶子文件本来就有未提交改动 —— 为免覆盖他人增量，退出（不动它）。"
    exit 2
fi

restore() {
    git reset -q -- "$TARGET" 2>/dev/null
    git checkout -- "$TARGET" 2>/dev/null
}
trap restore EXIT INT TERM

echo "=== 1. 正向：只关技能门禁，KB 门禁必须仍触发（exit 0）==="
printf '\n# gate-selftest\n' >> "$TARGET" || exit 1
git add -- "$TARGET" || exit 1
if SKILLS_GATE=0 sh "$HOOK" 2>&1 | grep -q 'kb-gate'; then
    echo "PASS: KB 门禁已触发（开关独立 + 路径匹配都正常）"
else
    echo "FAIL: KB 门禁没触发 —— 查两处：① SKILLS_GATE=0 是否又变成开头 exit 0；"
    echo "      ② 变更文件列表是否仍用未加 -z 的 --name-only（中文路径被加引号 → 锚点不命中）"
    exit 1
fi

echo "=== 2. 反向：坏 YAML 必须被拦下（exit != 0）==="
printf '\nbroken_field: [1, 2\n' >> "$TARGET" || exit 1
git add -- "$TARGET" || exit 1
if SKILLS_GATE=0 sh "$HOOK" >/dev/null 2>&1; then
    echo "FAIL: 坏 YAML 竟然放行 —— 门禁只打印不拦截"
    exit 1
fi
echo "PASS: 坏 YAML 被拦下"

echo "=== 全部通过（工作树已由 trap 还原）==="