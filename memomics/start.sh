#!/usr/bin/env bash
# MemOmics-Agent Startup Script (Linux / macOS / Server / Windows-Git-Bash)
# Usage: ./start.sh [port]
#   ./start.sh          # default port 8899
#   ./start.sh 9000     # custom port
#   ./start.sh 9000 --no-venv  # skip venv (use current env)

set -e

# === Configuration ===
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"
PORT="${1:-${MEMOMICS_PORT:-8899}}"
VENV_DIR=".venv"
NO_VENV=false
[[ "${2:-}" == "--no-venv" ]] && NO_VENV=true

echo "╔══════════════════════════════════════════════╗"
echo "║       MemOmics-Agent v2.0 Starting...        ║"
echo "╚══════════════════════════════════════════════╝"
echo ""

# === Check Python (broad detection, verify it's Python 3.11+) ===
PYTHON=""
PYTHON_DIAG=""

# Build candidate list: PATH commands + common install locations
CANDIDATES="python3 python python3.13 python3.12 python3.11"
# Add common install locations (Linux/macOS/Windows)
CANDIDATES="$CANDIDATES /usr/bin/python3 /usr/local/bin/python3 /opt/homebrew/bin/python3"
CANDIDATES="$CANDIDATES /usr/bin/python /usr/local/bin/python"
# conda / miniconda / anaconda
for _p in "$HOME/miniconda3/bin/python3" "$HOME/anaconda3/bin/python3" "$HOME/miniconda3/bin/python" "$HOME/anaconda3/bin/python"; do
    [ -x "$_p" ] && CANDIDATES="$CANDIDATES $_p"
done
# Windows Git Bash / native paths
for _p in "/c/Python313/python.exe" "/c/Python312/python.exe" "/c/Python311/python.exe" \
          "/c/Program Files/Python313/python.exe" "/c/Program Files/Python312/python.exe" "/c/Program Files/Python311/python.exe" \
          "/c/Users/$USER/AppData/Local/Programs/Python/Python313/python.exe" \
          "/c/Users/$USER/AppData/Local/Programs/Python/Python312/python.exe" \
          "/c/Users/$USER/AppData/Local/Programs/Python/Python311/python.exe"; do
    [ -x "$_p" ] && CANDIDATES="$CANDIDATES $_p"
done

for candidate in $CANDIDATES; do
    # Check if executable exists
    if [ -x "$candidate" ] || command -v "$candidate" &>/dev/null; then
        # Check if it's Python 3
        if "$candidate" -c "import sys; sys.exit(0 if sys.version_info >= (3,0) else 1)" 2>/dev/null; then
            # Check version range 3.11-3.13
            if "$candidate" -c "import sys; sys.exit(0 if sys.version_info >= (3,11) and sys.version_info < (3,14) else 1)" 2>/dev/null; then
                PYTHON="$candidate"
                break
            else
                _v=$("$candidate" -c "import sys; print('{}.{}'.format(sys.version_info.major, sys.version_info.minor))" 2>/dev/null)
                PYTHON_DIAG="$PYTHON_DIAG\n   ⚠️  $candidate: Python $_v (need 3.11-3.13)"
            fi
        else
            _v=$("$candidate" --version 2>&1 || echo "unknown")
            PYTHON_DIAG="$PYTHON_DIAG\n   ⚠️  $candidate: $_v (not Python 3)"
        fi
    fi
done

if [ -z "$PYTHON" ]; then
    echo "⚠️  Python 3.11-3.13 not found."
    if [ -n "$PYTHON_DIAG" ]; then
        echo "   Found these Python versions but none suitable:"
        echo -e "$PYTHON_DIAG"
    fi
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "  尝试自动安装 Python (via Miniconda)"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""

    # 确定安装脚本路径
    CONDA_INSTALLER=""
    CONDA_HOME="$HOME/miniconda3"

    # 方式1: 本地已有 miniconda 安装包（离线场景）
    for f in \
        "$SCRIPT_DIR/Miniconda3-latest-Linux-x86_64.sh" \
        "$SCRIPT_DIR/Miniconda3-latest-Linux-aarch64.sh" \
        "$SCRIPT_DIR/Miniconda3-latest-MacOSX-x86_64.sh" \
        "$SCRIPT_DIR/Miniconda3-latest-MacOSX-arm64.sh" \
        "$SCRIPT_DIR/Miniconda3-latest-Windows-x86_64.exe" \
        "$SCRIPT_DIR/miniconda*.sh" \
        "$HOME/Downloads/Miniconda3-latest-*.sh" \
        "$HOME/Miniconda3-latest-*.sh"; do
        if [ -f "$f" ]; then
            CONDA_INSTALLER="$f"
            echo "📦 找到本地 Miniconda 安装包: $f"
            break
        fi
    done

    # 方式2: 已有 conda，但没有合适的 Python 环境
    if [ -z "$CONDA_INSTALLER" ]; then
        if command -v conda &>/dev/null; then
            echo "📦 检测到 conda，创建 memomics 环境..."
            conda create -n memomics python=3.12 -y 2>&1 | tail -5
            if [ -f "$CONDA_HOME/envs/memomics/bin/python" ]; then
                PYTHON="$CONDA_HOME/envs/memomics/bin/python"
            else
                # 尝试找到 conda 的 base python
                CONDA_BASE=$(conda info --base 2>/dev/null)
                if [ -n "$CONDA_BASE" ] && [ -f "$CONDA_BASE/bin/python" ]; then
                    PYTHON="$CONDA_BASE/bin/python"
                fi
            fi
        fi
    fi

    # 方式3: 在线下载 miniconda
    if [ -z "$PYTHON" ] && [ -z "$CONDA_INSTALLER" ]; then
        echo "🌐 尝试在线下载 Miniconda..."
        OS=$(uname -s)
        ARCH=$(uname -m)
        URL=""
        case "$OS" in
            Linux)
                case "$ARCH" in
                    x86_64) URL="https://mirrors.tuna.tsinghua.edu.cn/anaconda/miniconda/Miniconda3-latest-Linux-x86_64.sh" ;;
                    aarch64|arm64) URL="https://mirrors.tuna.tsinghua.edu.cn/anaconda/miniconda/Miniconda3-latest-Linux-aarch64.sh" ;;
                esac
                ;;
            Darwin)
                case "$ARCH" in
                    x86_64) URL="https://mirrors.tuna.tsinghua.edu.cn/anaconda/miniconda/Miniconda3-latest-MacOSX-x86_64.sh" ;;
                    arm64) URL="https://mirrors.tuna.tsinghua.edu.cn/anaconda/miniconda/Miniconda3-latest-MacOSX-arm64.sh" ;;
                esac
                ;;
        esac

        if [ -n "$URL" ]; then
            CONDA_INSTALLER="/tmp/miniconda_installer.sh"
            echo "   下载: $URL"
            if command -v wget &>/dev/null; then
                wget -q "$URL" -O "$CONDA_INSTALLER" 2>&1 | tail -3
            elif command -v curl &>/dev/null; then
                curl -sL "$URL" -o "$CONDA_INSTALLER" 2>&1 | tail -3
            fi
            if [ ! -s "$CONDA_INSTALLER" ]; then
                CONDA_INSTALLER=""
                echo "   ❌ 下载失败"
            fi
        else
            echo "   ❌ 不支持的平台: $OS $ARCH"
        fi
    fi

    # 执行安装
    if [ -n "$CONDA_INSTALLER" ] && [ -z "$PYTHON" ]; then
        echo "📦 安装 Miniconda 到 $CONDA_HOME ..."
        bash "$CONDA_INSTALLER" -b -p "$CONDA_HOME" 2>&1 | tail -5
        if [ -f "$CONDA_HOME/bin/python" ]; then
            PYTHON="$CONDA_HOME/bin/python"
            echo "✅ Miniconda 安装成功"
            # 创建 memomics 环境
            echo "📦 创建 memomics 环境 (Python 3.12)..."
            "$CONDA_HOME/bin/conda" create -n memomics python=3.12 -y 2>&1 | tail -3
            if [ -f "$CONDA_HOME/envs/memomics/bin/python" ]; then
                PYTHON="$CONDA_HOME/envs/memomics/bin/python"
            fi
        fi
    fi

    if [ -z "$PYTHON" ]; then
        echo ""
        echo "❌ 无法自动安装 Python。请手动安装:"
        echo ""
        echo "   方法1: 用 download_miniconda.sh 在有网的机器上下载安装包"
        echo "          然后把安装包放到 MemOmics-Agent 目录下，重新运行 ./start.sh"
        echo ""
        echo "   方法2: 直接安装"
        echo "          conda create -n memomics python=3.12 && conda activate memomics"
        echo ""
        echo "   方法3: 从官网下载 Python 3.12"
        echo "          https://www.python.org/downloads/"
        echo ""
        exit 1
    fi
fi

PY_VERSION=$($PYTHON -c "import sys; print('{}.{}'.format(sys.version_info.major, sys.version_info.minor))")
PY_FULL=$($PYTHON --version 2>&1)
echo "🐍 Python: $PY_VERSION ($PY_FULL) [$PYTHON]"

# === Create venv if needed ===
if [ ! -d "$VENV_DIR" ]; then
    echo "📦 Creating virtual environment..."
    $PYTHON -m venv "$VENV_DIR"
fi

# === Activate venv ===
if [ -f "$VENV_DIR/bin/activate" ]; then
    source "$VENV_DIR/bin/activate"
elif [ -f "$VENV_DIR/Scripts/activate" ]; then
    source "$VENV_DIR/Scripts/activate"
fi

# === Install dependencies ===
# Check if critical deps are installed; if not, install
NEED_INSTALL=false

if [ "$NO_VENV" = true ]; then
    # Using system Python, check deps
    python -c "import fastapi, uvicorn, httpx, openai, psutil, rich" 2>/dev/null || NEED_INSTALL=true
else
    python -c "import fastapi, uvicorn, httpx, openai, psutil, rich" 2>/dev/null || NEED_INSTALL=true
fi

if [ "$NEED_INSTALL" = true ]; then
    echo "📦 Installing dependencies (first run, may take a few minutes)..."
    pip install --upgrade pip -q 2>/dev/null || true
    pip install -r requirements.txt 2>&1 | tail -5
    echo "✅ Dependencies installed."
    echo ""
else
    echo "✅ Dependencies already installed."
fi

# === Check R (optional but recommended for bioinformatics) ===
RSCRIPT=""
for _r in Rscript Rscript /usr/bin/Rscript /usr/local/bin/Rscript /opt/homebrew/bin/Rscript; do
    if command -v "$_r" &>/dev/null || [ -x "$_r" ]; then
        RSCRIPT="$_r"
        break
    fi
done
if [ -n "$RSCRIPT" ]; then
    R_VERSION=$("$RSCRIPT" -e 'cat(R.version$major, R.version$minor, sep=".")' 2>/dev/null)
    if [ -n "$R_VERSION" ]; then
        echo "📊 R: $R_VERSION [$RSCRIPT]"
    else
        echo "⚠️  R found but could not get version."
        RSCRIPT=""
    fi
fi
if [ -z "$RSCRIPT" ]; then
    echo "⚠️  R not found. R-based analysis (Seurat/CellChat/etc.) will not work."
    echo "   Install R 4.3+ from: https://cran.r-project.org/"
    echo "   After installing R, restart this script."
fi

# === Check GPU (optional) ===
if command -v nvidia-smi &>/dev/null; then
    GPU_INFO=$(nvidia-smi --query-gpu=name,memory.total --format=csv,noheader,nounits 2>/dev/null | head -1)
    if [ -n "$GPU_INFO" ]; then
        GPU_NAME=$(echo "$GPU_INFO" | cut -d',' -f1 | xargs)
        GPU_MEM=$(echo "$GPU_INFO" | cut -d',' -f2 | xargs)
        echo "🎮 GPU: $GPU_NAME (${GPU_MEM}MB)"
    fi
else
    echo "ℹ️  No NVIDIA GPU detected (optional — CPU-only analysis works fine)"
fi

# === Platform info ===
OS_INFO=$(uname -s 2>/dev/null || echo "unknown")
ARCH_INFO=$(uname -m 2>/dev/null || echo "unknown")
echo "💻 Platform: $OS_INFO $ARCH_INFO"
if [ -f /proc/1/cgroup ] && grep -qE 'docker|kubepods|containerd' /proc/1/cgroup 2>/dev/null; then
    echo "🐳 Running in container"
elif [ -f /.dockerenv ] 2>/dev/null; then
    echo "🐳 Running in Docker"
fi

# === Set environment ===
export HERMES_HOME="$SCRIPT_DIR/hermes_home"
export PYTHONPATH="$SCRIPT_DIR:$SCRIPT_DIR/hermes-agent:${PYTHONPATH:-}"
export MEMOMICS_PORT="$PORT"
# Bind to 0.0.0.0 on servers (accessible remotely), localhost on desktop
export MEMOMICS_HOST="${MEMOMICS_HOST:-0.0.0.0}"

# === Detect if running on server (SSH session) ===
if [ -n "$SSH_CONNECTION" ] || [ -n "$SSH_TTY" ]; then
    echo "🖥️  SSH session detected — binding to 0.0.0.0 (accessible via $(hostname 2>/dev/null || echo 'server'))"
    echo "   Access from your browser: http://$(hostname -I 2>/dev/null | awk '{print $1}' || echo 'server-ip'):$PORT"
fi

# === Start server ===
echo ""
echo "🚀 Starting MemOmics WebUI on port $PORT..."
echo "   URL: http://localhost:$PORT"
echo "   Press Ctrl+C to stop"
echo ""

python webui/server.py
