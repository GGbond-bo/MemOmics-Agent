#!/usr/bin/env bash
# MemOmics 更新覆盖脚本（macOS / Linux，2026-10-09）
# 用法: chmod +x update_macos_linux.sh && ./update_macos_linux.sh [-y]
# 特点：自动定位安装目录（不依赖文件夹名字）→ 只覆盖代码 → 跳过用户数据 → 不删除任何文件。
set -euo pipefail

PKG="$(cd "$(dirname "$0")" && pwd)"
YES=0
[ "${1:-}" = "-y" ] && YES=1

if [ ! -f "$PKG/webui/server.py" ]; then
  echo "[X] 本脚本必须放在更新包（MemOmics 文件夹）内运行 —— 当前目录没有 webui/server.py"
  echo "    当前目录: $PKG"
  exit 1
fi

is_install() {
  [ -n "${1:-}" ] && [ -f "$1/webui/server.py" ] && { [ -d "$1/memomics_home" ] || [ -f "$1/VERSION" ]; }
}

echo "=== MemOmics 更新覆盖（自动匹配安装目录） ==="
echo "  更新包目录: $PKG"

# 1) 找候选安装目录（浅层扫描常见位置）
CAND=""
count=0
found=()
for base in "$(dirname "$PKG")" "$HOME/Desktop" "$HOME/Downloads" "$HOME/Documents" "$HOME" /opt /srv "$PWD"; do
  [ -d "$base" ] || continue
  for d in "$base"/*/; do
    d="${d%/}"
    [ -d "$d" ] || continue
    if is_install "$d"; then found+=("$d"); fi
  done
  if is_install "$base"; then found+=("$base"); fi
done
# 去重
uniq_found=()
for f in "${found[@]:-}"; do
  [ -n "$f" ] || continue
  dup=0
  for u in "${uniq_found[@]:-}"; do [ "$u" = "$f" ] && dup=1; done
  [ "$dup" = 0 ] && uniq_found+=("$f")
done
found=("${uniq_found[@]:-}")

# .install_path 记录的路径优先
INSTALL=""
for f in "${found[@]:-}"; do
  ap="$f/memomics_home/.install_path"
  if [ -f "$ap" ]; then
    rec="$(tr -d '\r\n' < "$ap")"
    if is_install "$rec"; then INSTALL="$(cd "$rec" && pwd)"; echo "  按 memomics_home/.install_path 记录的安装目录: $INSTALL"; break; fi
  fi
done
if [ -z "$INSTALL" ]; then
  n="${#found[@]}"
  if [ "$n" = "1" ]; then
    INSTALL="${found[0]}"; echo "  找到 1 个候选安装目录: $INSTALL"
  elif [ "$n" -gt 1 ]; then
    echo "  找到多个候选安装目录（请选择）:"
    i=1
    for f in "${found[@]}"; do echo "   [$i] $f"; i=$((i+1)); done
    printf "  输入编号（回车=取消）: "; read -r sel || true
    [ -z "$sel" ] && { echo "已取消"; exit 0; }
    INSTALL="${found[$((sel-1))]}"
  else
    echo "  没有自动找到安装目录。"
    echo "  提示：安装目录 = 运行 start.sh 所在的文件夹（里面能看到 webui、memomics_home）"
    printf "  请粘贴安装目录路径（回车=取消）: "; read -r manual || true
    [ -z "$manual" ] && { echo "已取消"; exit 0; }
    is_install "$manual" || { echo "[X] 该目录不像 MemOmics 安装目录: $manual"; exit 1; }
    INSTALL="$(cd "$manual" && pwd)"
  fi
fi

echo ""
echo "  更新包: $PKG"
echo "  安装目录: $INSTALL"
echo "  说明：只覆盖代码与产品文件；memomics_home 的配置/记忆/会话、results、.venv 等用户数据不动。"
if [ "$YES" = "0" ]; then
  printf "  确认开始覆盖？(y/N) "; read -r ok || true
  case "$ok" in y|Y) ;; *) echo "已取消"; exit 0 ;; esac
fi

# 2) 覆盖（tar 管道，跳过用户数据；不删除目标里的任何文件）
EXC=(
  --exclude='./memomics_home' --exclude='./results' --exclude='./uploads' --exclude='./log'
  --exclude='./.venv' --exclude='./venv' --exclude='./python' --exclude='./miniconda'
  --exclude='./miniconda_env' --exclude='./runtime' --exclude='./node_modules' --exclude='./.git'
  --exclude='./.backups' --exclude='./__pycache__' --exclude='./.env' --exclude='./.install_path'
)
tar -C "$PKG" -cf - "${EXC[@]}" . | tar -C "$INSTALL" -xf -

# 3) 技能库是发布内容，单独同步（memomics_home 其余用户数据一律不动）
if [ -d "$PKG/memomics_home/skills" ]; then
  mkdir -p "$INSTALL/memomics_home/skills"
  tar -C "$PKG/memomics_home" -cf - skills | tar -C "$INSTALL/memomics_home" -xf -
fi
for f in SKILLS_INDEX.md; do
  [ -f "$PKG/memomics_home/$f" ] && cp -f "$PKG/memomics_home/$f" "$INSTALL/memomics_home/$f"
done

VER="$(cat "$INSTALL/VERSION" 2>/dev/null | tr -d '\r\n' || true)"
echo ""
echo "[OK] 覆盖完成，安装目录版本号: $VER"
echo "     请关闭 MemOmics 后重新启动（./start.sh）使新代码生效。"
echo "     首次启动会自动把旧的 hermes_home 数据目录迁移为 memomics_home（只搬不删）。"