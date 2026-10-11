#!/usr/bin/env bash
# ChineseResearchLaTeX 包装脚本（MemOmics 侧）
# 用法：
#   crl.sh check                          # 健康检查：repo / python / XeLaTeX / 包状态
#   crl.sh install                        # 幂等安装（Gitee 镜像，不删已有目录）
#   crl.sh build  <project-dir>           # 按产品线自动派发官方构建工具（PDF）
#   crl.sh docx   <project-dir>           # paper-* / thesis-* 导出 Word
#   crl.sh words  <tex...>                # 可见字数统计（paper 线）
#   crl.sh list                           # 列出模板与上游技能
#   crl.sh pkgs                           # 安装/更新 LaTeX 公共包到 TEXMFHOME（需 TeX 发行版）
set -u

REPO="${CRL_ROOT:-/e/MemOmics-Agent/third_party/CRL}"
PY="${PYTHON:-python}"
GITEE=https://gitee.com/huangwb8/ChineseResearchLaTeX.git

die () { echo "❌ $*" >&2; exit 1; }

need_repo () { [ -d "$REPO/projects" ] || die "未找到仓库：$REPO（先跑 crl.sh install）"; }

cmd_check () {
  echo "=== 仓库 ==="
  if [ -d "$REPO/.git" ]; then
    echo "路径: $REPO"
    (cd "$REPO" && git log -1 --format='版本: commit=%h date=%ad')
  else
    echo "路径: $REPO（缺失）"
  fi
  echo "=== Python ==="; "$PY" -V 2>&1
  echo "=== TeX 工具链 ==="
  for t in xelatex latexmk kpsewhich mktexlsr texhash initexmf; do
    p=$(command -v "$t" 2>/dev/null || true)
    printf '  %-10s %s\n' "$t" "${p:-✗ 未找到}"
  done
  echo "=== 模板 ==="
  [ -d "$REPO/projects" ] && ls "$REPO/projects" | tr '\n' ' ' && echo
  echo "=== 上游技能数 ==="
  [ -d "$REPO/skills" ] && ls "$REPO/skills" | grep -v '\.md$' | wc -l
  if ! command -v xelatex >/dev/null 2>&1; then
    echo
    echo "⚠️  未检测到 TeX 发行版：可以读改 .tex 与写作，但【编译 PDF / 装公共包 / 导出 DOCX】会被阻断。"
    echo "    选项：① 装 TeX Live/MiKTeX（4–7 GB，需用户同意）② 上传 Overleaf 包在网页端编译 ③ 走 DOCX 路线（academic-thesis-docx）"
  fi
}

cmd_install () {
  local parent; parent=$(dirname "$REPO")
  mkdir -p "$parent"; cd "$parent" || die "无法进入 $parent"
  if [ -d "$REPO/projects" ]; then echo "✅ 已存在，跳过克隆：$REPO"; return 0; fi
  local tmp="$REPO.gitee.tmp"
  echo "--- 从 Gitee 镜像克隆（GitHub git 协议本机不可用）"
  GIT_SSL_BACKEND=openssl GIT_TERMINAL_PROMPT=0 timeout 600 git clone --depth 1 "$GITEE" "$tmp" \
    || die "克隆失败：$GITEE"
  mv "$tmp" "$REPO" || die "移动失败：$tmp -> $REPO"
  echo "✅ 安装完成：$REPO"
  (cd "$REPO" && git log -1 --format='commit=%h date=%ad')
}

dispatch () {  # $1=project-dir  → echo 官方工具命令
  local p="$1" base; base=$(basename "$p")
  case "$base" in
    NSFC_*|GDNSF_*|GXNSF_*) echo "packages/bensz-nsfc/scripts/nsfc_project_tool.py" ;;
    paper-*)                echo "packages/bensz-paper/scripts/paper_project_tool.py" ;;
    thesis-*)               echo "packages/bensz-thesis/scripts/thesis_project_tool.py" ;;
    cv-*)                   echo "packages/bensz-cv/scripts/cv_project_tool.py" ;;
    *) die "未知产品线：$base（应形如 NSFC_*/paper-*/thesis-*/cv-*）" ;;
  esac
}

cmd_build () {
  need_repo
  local p="${1:-}" ; [ -n "$p" ] || die "用法：crl.sh build <project-dir>"
  local tool; tool=$(dispatch "$p")
  if [ "$(basename "$p")" = "cv-01" ] || [ "${p#*/}" = "${p#*cv-}" ]; then :; fi
  cd "$REPO" || die "无法进入仓库"
  case "$(basename "$p")" in
    cv-*)  echo "+ $PY $tool build --project-dir $p --variant all"; "$PY" "$tool" build --project-dir "$p" --variant all ;;
    *)     echo "+ $PY $tool build --project-dir $p";              "$PY" "$tool" build --project-dir "$p" ;;
  esac
}

cmd_docx () {
  need_repo
  local p="${1:-}" ; [ -n "$p" ] || die "用法：crl.sh docx <project-dir>（仅 paper-* / thesis-*）"
  local tool; tool=$(dispatch "$p")
  cd "$REPO" || die "无法进入仓库"
  echo "+ $PY $tool docx --project-dir $p"
  "$PY" "$tool" docx --project-dir "$p"
}

cmd_words () {
  need_repo
  [ "$#" -ge 1 ] || die "用法：crl.sh words <tex...>"
  cd "$REPO" || die "无法进入仓库"
  "$PY" packages/bensz-paper/scripts/paper_project_tool.py count-words "$@"
}

cmd_pkgs () {
  need_repo
  cd "$REPO" || die "无法进入仓库"
  echo "+ $PY scripts/install.py install --mirror gitee ${*:-}"
  "$PY" scripts/install.py install --mirror gitee "$@"
}

cmd_list () {
  need_repo
  echo "=== projects/ ==="; ls "$REPO/projects"
  echo "=== packages/ ==="; ls "$REPO/packages"
  echo "=== skills/ ==="; ls "$REPO/skills" | grep -v '\.md$'
}

case "${1:-check}" in
  check)   cmd_check ;;
  install) cmd_install ;;
  build)   shift; cmd_build   "$@" ;;
  docx)    shift; cmd_docx    "$@" ;;
  words)   shift; cmd_words   "$@" ;;
  pkgs)    shift; cmd_pkgs    "$@" ;;
  list)    cmd_list ;;
  *) die "未知子命令：$1（check|install|build|docx|words|pkgs|list）" ;;
esac