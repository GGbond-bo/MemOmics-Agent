#!/usr/bin/env bash
# ============================================================
#  MemOmics-Agent macOS 启动器
#  支持 Apple Silicon (arm64) / Intel (x86_64)
#  用法: ./start.sh [port]
# ============================================================
set -o pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"
PORT="${1:-${MEMOMICS_PORT:-8899}}"

echo "╔══════════════════════════════════════════════╗"
echo "║       MemOmics-Agent v2.0 Starting...        ║"
echo "╚══════════════════════════════════════════════╝"
echo ""

export HERMES_HOME="$SCRIPT_DIR/hermes_home"
export PYTHONPATH="$SCRIPT_DIR:$SCRIPT_DIR/hermes-agent:${PYTHONPATH:-}"
export MEMOMICS_PORT="$PORT"
export MEMOMICS_HOST="0.0.0.0"

# === Step 1: Find Python ===
PYTHON=""
for c in python3 python python3.13 python3.12 python3.11 \
         /usr/bin/python3 /usr/local/bin/python3 /opt/homebrew/bin/python3; do
    if command -v "$c" &>/dev/null || [ -x "$c" ]; then
        if "$c" -c "import sys; sys.exit(0 if (3,10) <= sys.version_info < (3,14) else 1)" 2>/dev/null; then
            PYTHON="$c"
            echo "[OK] Found: $c"
            break
        fi
    fi
done

# === Step 2: No Python? Use bundled miniconda ===
if [ -z "$PYTHON" ]; then
    echo "[WARN] Python 3.11-3.13 not found"
    echo "[INFO] Using bundled Miniconda..."

    CONDA_PY="$SCRIPT_DIR/miniconda_env/bin/python"
    if [ ! -f "$CONDA_PY" ]; then
        ARCH=$(uname -m)
        case "$ARCH" in
            arm64)  INSTALLER="$SCRIPT_DIR/miniconda/Miniconda3-latest-MacOSX-arm64.sh" ;;
            x86_64) INSTALLER="$SCRIPT_DIR/miniconda/Miniconda3-latest-MacOSX-x86_64.sh" ;;
            *)      echo "[ERROR] Unsupported arch: $ARCH"; exit 1 ;;
        esac
        if [ ! -f "$INSTALLER" ]; then
            echo "[ERROR] miniconda installer missing: $INSTALLER"
            exit 1
        fi
        echo "[INSTALL] Installing Miniconda ($ARCH, 1-2 min)..."
        bash "$INSTALLER" -b -p "$SCRIPT_DIR/miniconda_env"
        if [ ! -f "$CONDA_PY" ]; then
            echo "[ERROR] Miniconda install failed!"
            exit 1
        fi
    fi
    PYTHON="$CONDA_PY"
    echo "[OK] Miniconda ready"
fi

# === Step 3: Create venv ===
if [ ! -f ".venv/bin/python" ]; then
    echo "[SETUP] Creating .venv..."
    if "$PYTHON" -m venv .venv 2>/dev/null; then
        echo "[OK] .venv created"
    else
        echo "[WARN] venv failed, using Python directly"
        VENV_PY="$PYTHON"
    fi
fi

if [ -z "$VENV_PY" ] && [ -f ".venv/bin/python" ]; then
    VENV_PY=".venv/bin/python"
elif [ -z "$VENV_PY" ]; then
    VENV_PY="$PYTHON"
fi

# === Step 4: Dependencies ===
if ! "$VENV_PY" -c "import fastapi" 2>/dev/null; then
    echo "[INSTALL] Installing dependencies (3-8 min, once)..."
    "$VENV_PY" -m pip install --upgrade pip --quiet 2>/dev/null || true
    "$VENV_PY" -m pip install -r requirements.txt || echo "[WARN] Some packages failed"
else
    echo "[OK] Dependencies ready"
fi

# === Step 5: Start ===
echo ""
echo "[START] http://localhost:$PORT"
echo ""
exec "$VENV_PY" webui/server.py
