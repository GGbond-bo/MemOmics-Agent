#!/usr/bin/env bash
# ============================================================
#  MemOmics-Agent Linux 启动器
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

# === 首次安装检测：config.yaml 不存在时从模板生成 ===
# （升级覆盖解压时保留用户已有 config.yaml/API Key，不被覆盖）
if [ ! -f "$HERMES_HOME/config.yaml" ] && [ -f "$HERMES_HOME/config.yaml.example" ]; then
    cp "$HERMES_HOME/config.yaml.example" "$HERMES_HOME/config.yaml"
    echo "[INFO] 已生成默认 config.yaml（首次安装）。API Key 请在 WebUI 设置页填写。"
fi

# === Step 1: Find Python ===
PYTHON=""
for c in python3 python python3.13 python3.12 python3.11 \
         /usr/bin/python3 /usr/local/bin/python3 \
         "$HOME/miniconda3/bin/python3" "$HOME/anaconda3/bin/python3"; do
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
        INSTALLER="$SCRIPT_DIR/miniconda/Miniconda3-py312_25.1.1-2-Linux-x86_64.sh"
        if [ ! -f "$INSTALLER" ]; then
            echo "[ERROR] miniconda/Miniconda3-py312_25.1.1-2-Linux-x86_64.sh missing!"
            exit 1
        fi
        echo "[INSTALL] Installing Miniconda (1-2 min)..."
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
# 批O5(2026-08-16): 读图组件(OCR=rapidocr_onnxruntime+opencv-headless, 跨平台含Linux)首次装
# 批O7(2026-08-17): 优先随包离线 wheel（vendor/wheels，Python 3.12），无网也能装；失败才走在线
if ! "$VENV_PY" -c "import rapidocr_onnxruntime" 2>/dev/null; then
    echo "[INSTALL] Installing vision/OCR components (约200MB, once)..."
    if [ -d "$SCRIPT_DIR/vendor/wheels" ]; then
        echo "[INFO] Using bundled OCR wheels (offline)..."
        "$VENV_PY" -m pip install --no-index --find-links "$SCRIPT_DIR/vendor/wheels" -r requirements-vision.txt || {
            echo "[WARN] offline wheels failed, trying online..."
            "$VENV_PY" -m pip install -r requirements-vision.txt || echo "[WARN] vision components failed (OCR unavailable, core OK)"
        }
    else
        "$VENV_PY" -m pip install -r requirements-vision.txt || echo "[WARN] vision components failed (OCR unavailable, core OK)"
    fi
else
    echo "[OK] OCR ready"
fi

# === Step 4.5: R 检查（Linux 包不预装 R——给出指引，避免用户开箱即遇 R 报错） ===
# 2026-08-25: 多 R 环境（conda/系统共存）时用 RSCRIPT_PATH 指定主力 R，
# 持久内核会优先用它（persistent_kernel._rscript_path 已支持）。
# 2026-08-29: 分析包策略 —— 核心 Agent 依赖已装完；scanpy 生态等分析包
# 按需安装（Agent 任务中先查用户环境，用户同意才装，SOUL 铁律 29）。
echo "[INFO] 核心依赖就绪（Agent 可正常使用）。"
echo "  Python 分析包（scanpy 生态）按需安装：pip install -r requirements-analysis.txt"
echo "  R 包由 Agent 在任务中检查用户环境后询问安装（清华镜像）"
if ! command -v Rscript &>/dev/null; then
    echo "[WARN] Rscript 未找到 —— R 分析（Seurat/WGCNA 等）不可用，核心 WebUI 不受影响"
    echo "  安装 R（Ubuntu/Debian，tuna 镜像加速包安装）:"
    echo "    sudo apt-get update && sudo apt-get install -y r-base"
    echo "  已有 R 但不在 PATH: export RSCRIPT_PATH=/path/to/Rscript 后再启动"
    echo "  关键 R 包清单见 R_packages.txt；安装 R 包可用清华镜像:"
    echo "    Rscript -e 'options(repos=c(CRAN=\"https://mirrors.tuna.tsinghua.edu.cn/CRAN/\")); install.packages(c(\"Seurat\",\"ggplot2\"))'"
else
    echo "[OK] Rscript found: $(command -v Rscript)"
fi

# === Step 5: Start ===
echo ""
echo "[START] http://localhost:$PORT"
echo ""
exec "$VENV_PY" webui/server.py
