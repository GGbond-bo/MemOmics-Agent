#!/usr/bin/env bash
# ============================================================
#  MemOmics-Agent Linux 启动器
#  自动检测 Python -> 无则用内置 miniconda 创建环境
#  用法: ./start.sh [port]
# ============================================================
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"
PORT="${1:-${MEMOMICS_PORT:-8899}}"
VENV_DIR=".venv"
CONDA_DIR="miniconda_env"

echo "╔══════════════════════════════════════════════╗"
echo "║       MemOmics-Agent v1.0 Starting...        ║"
echo "╚══════════════════════════════════════════════╝"
echo ""

# === Step 1: Find Python 3.11-3.13 ===
PYTHON=""
for c in python3 python python3.13 python3.12 python3.11 \
         /usr/bin/python3 /usr/local/bin/python3 \
         "$HOME/miniconda3/bin/python3" "$HOME/anaconda3/bin/python3"; do
    if command -v "$c" &>/dev/null || [ -x "$c" ]; then
        if "$c" -c "import sys; sys.exit(0 if sys.version_info >= (3,11) and sys.version_info < (3,14) else 1)" 2>/dev/null; then
            PYTHON="$c"
            echo "✅ 找到系统 Python: $c ($("$c" --version 2>&1))"
            break
        fi
    fi
done

# === Step 2: No Python? Use bundled miniconda ===
if [ -z "$PYTHON" ]; then
    echo "⚠️ 未找到 Python 3.11-3.13，使用内置 Miniconda..."
    CONDA_PYTHON="$SCRIPT_DIR/$CONDA_DIR/bin/python"
    if [ ! -f "$CONDA_PYTHON" ]; then
        INSTALLER="$SCRIPT_DIR/miniconda/Miniconda3-latest-Linux-x86_64.sh"
        if [ ! -f "$INSTALLER" ]; then
            echo "❌ 内置 miniconda 安装包未找到!"
            echo "   请从 https://docs.conda.io 下载 Miniconda3-latest-Linux-x86_64.sh"
            echo "   放到 $SCRIPT_DIR/miniconda/ 目录下"
            exit 1
        fi
        echo "📦 安装 Miniconda 到 $CONDA_DIR ..."
        bash "$INSTALLER" -b -p "$SCRIPT_DIR/$CONDA_DIR"
        if [ ! -f "$CONDA_PYTHON" ]; then
            echo "❌ Miniconda 安装失败!"
            exit 1
        fi
    fi
    PYTHON="$CONDA_PYTHON"
    echo "✅ 使用 Miniconda Python: $PYTHON ($($PYTHON --version 2>&1))"
fi

# === Step 3: Create venv ===
VENV_PYTHON="$SCRIPT_DIR/$VENV_DIR/bin/python"
if [ ! -f "$VENV_PYTHON" ]; then
    echo "🔧 创建虚拟环境..."
    "$PYTHON" -m venv "$VENV_DIR" || {
        echo "⚠️ venv 创建失败，直接使用当前 Python"
        VENV_PYTHON="$PYTHON"
    }
    echo "✅ 虚拟环境已创建"
fi

# === Step 4: Install dependencies ===
if ! "$VENV_PYTHON" -c "import fastapi" 2>/dev/null; then
    echo "📥 安装依赖包..."
    "$VENV_PYTHON" -m pip install --upgrade pip -q
    "$VENV_PYTHON" -m pip install -r requirements.txt -q || echo "⚠️ 部分依赖安装失败，尝试继续..."
    echo "✅ 依赖安装完成"
else
    echo "✅ 依赖已就绪"
fi

# === Step 5: Start server ===
echo ""
echo "🚀 启动 MemOmics-Agent (端口 $PORT)..."
echo "   浏览器访问: http://localhost:$PORT"
echo ""
export MEMOMICS_PORT="$PORT"
exec "$VENV_PYTHON" webui/server.py
