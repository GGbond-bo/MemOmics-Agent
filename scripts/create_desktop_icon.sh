#!/usr/bin/env bash
# MemOmics 桌面图标创建脚本（macOS）
# 用法: bash create_desktop_icon.sh <repo_root>
# 首次启动时在 ~/Desktop 创建 MemOmics.command（企鹅图标，双击即启动/打开 WebUI）。
# 双击行为：服务已运行 -> 打开浏览器；未运行 -> 启动 start.sh。
# 幂等：已存在且指向同一安装目录则跳过（不覆盖用户手动改过的）。
# 由 start.sh 的 Darwin 分支自动调用；手动运行亦可。
# 目录移动后下次启动会自动重建（内容含安装路径，不一致即重写）。

set -u

APP_DIR="${1:-}"
if [ -z "$APP_DIR" ]; then
    APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
fi
[ -d "$APP_DIR/webui" ] || exit 0          # 不是有效安装目录
[ "$(uname -s)" = "Darwin" ] || exit 0     # 仅 macOS
[ -d "$HOME/Desktop" ] || exit 0

CMD_FILE="$HOME/Desktop/MemOmics.command"
PNG="$APP_DIR/webui/assets/penguin.png"

# 幂等：已存在且内容指向本安装目录 -> 跳过
if [ -f "$CMD_FILE" ] && grep -Fq "$APP_DIR" "$CMD_FILE" 2>/dev/null; then
    exit 0
fi

# 生成启动器：服务已运行 -> 打开浏览器；未运行 -> 启动 start.sh
cat > "$CMD_FILE" <<'EOF'
#!/usr/bin/env bash
# MemOmics — 智能多组学生信分析助手（由 start.sh 自动生成，请勿删除）
cd 'APP_DIR_PLACEHOLDER'
PORT="${MEMOMICS_PORT:-8899}"
if lsof -nP -iTCP:"$PORT" -sTCP:LISTEN >/dev/null 2>&1; then
    open "http://127.0.0.1:$PORT"
else
    exec ./start.sh "$PORT"
fi
EOF
sed -i.bak "s|APP_DIR_PLACEHOLDER|$APP_DIR|" "$CMD_FILE"
rm -f "$CMD_FILE.bak"
chmod +x "$CMD_FILE"

# 企鹅图标（NSWorkspace 设置文件图标；失败不影响功能）
case "$PNG" in *"'"*) PNG="" ;; esac
if [ -f "$PNG" ]; then
    osascript -l JavaScript -e "
ObjC.import('AppKit');
var img = \$.NSImage.alloc.initWithContentsOfFile('$PNG');
if (img) {
    \$.NSWorkspace.sharedWorkspace.setIconForFileOptions(img, '$CMD_FILE', 0);
}
" >/dev/null 2>&1 || true
fi

echo "[桌面图标] 已创建：双击桌面 MemOmics 即可启动"
exit 0
