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

# === 首次安装检测：config.yaml 不存在时从模板生成 ===
# （升级覆盖解压时保留用户已有 config.yaml/API Key，不被覆盖）
if [ ! -f "$HERMES_HOME/config.yaml" ] && [ -f "$HERMES_HOME/config.yaml.example" ]; then
    cp "$HERMES_HOME/config.yaml.example" "$HERMES_HOME/config.yaml"
    echo "[INFO] 已生成默认 config.yaml（首次安装）。API Key 请在 WebUI 设置页填写。"
fi

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
            arm64)  INSTALLER="$SCRIPT_DIR/miniconda/Miniconda3-py312_25.1.1-2-MacOSX-arm64.sh" ;;
            x86_64) INSTALLER="$SCRIPT_DIR/miniconda/Miniconda3-py312_25.1.1-2-MacOSX-x86_64.sh" ;;
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
# 2026-09-01 加固: 用户常设全局 PYTHONPATH 会污染 venv 创建（ensurepip 失效→产出无 pip
# 的残缺 .venv）。引导期一律 env -u PYTHONPATH 执行。
_mkvenv() { env -u PYTHONPATH "$1" -m venv .venv; }
if [ ! -f ".venv/bin/python" ]; then
    echo "[SETUP] Creating .venv..."
    if _mkvenv "$PYTHON"; then
        echo "[OK] .venv created"
    else
        echo "[WARN] venv 创建失败，改用 Python 直接运行（依赖装入 base 环境）"
        VENV_PY="$PYTHON"
    fi
fi

if [ -z "$VENV_PY" ] && [ -f ".venv/bin/python" ]; then
    VENV_PY=".venv/bin/python"
elif [ -z "$VENV_PY" ]; then
    VENV_PY="$PYTHON"
fi

# === Step 3.5: 残缺 .venv 自愈 ===
# 2026-09-01: .venv/bin/python 存在≠健康（旧包残留 / ensurepip 失败 → 无 pip）：
# 先 ensurepip 修复，失败则重建（旧目录保留为 .venv.broken），再不行回退 base python。
if [ "$VENV_PY" != "$PYTHON" ] && [ -f "$VENV_PY" ]; then
    if ! env -u PYTHONPATH "$VENV_PY" -m pip --version >/dev/null 2>&1; then
        echo "[WARN] .venv 缺少 pip（旧包残留或 ensurepip 被污染），尝试修复..."
        if env -u PYTHONPATH "$VENV_PY" -m ensurepip --upgrade >/dev/null 2>&1 && \
           env -u PYTHONPATH "$VENV_PY" -m pip --version >/dev/null 2>&1; then
            echo "[OK] pip 已修复"
        else
            echo "[WARN] ensurepip 修复失败，重建 .venv（旧环境移到 .venv.broken）..."
            rm -rf .venv.broken; mv .venv .venv.broken 2>/dev/null || rm -rf .venv
            if _mkvenv "$PYTHON"; then
                VENV_PY=".venv/bin/python"
                echo "[OK] .venv 已重建（.venv.broken 可手动删除）"
            else
                echo "[WARN] 重建失败，改用 Python 直接运行"
                VENV_PY="$PYTHON"
            fi
        fi
    fi
fi

# === Step 4: Dependencies ===
if ! "$VENV_PY" -c "import fastapi" 2>/dev/null; then
    echo "[INSTALL] Installing dependencies (3-8 min, once)..."
    env -u PYTHONPATH "$VENV_PY" -m pip install --upgrade pip --quiet 2>/dev/null || true
    env -u PYTHONPATH "$VENV_PY" -m pip install -r requirements.txt || echo "[WARN] Some packages failed"
else
    echo "[OK] Dependencies ready"
fi
# 批O5(2026-08-16): 读图组件(OCR=rapidocr_onnxruntime+opencv-headless, 跨平台含macOS)首次装
# 批O7(2026-08-17): 优先随包离线 wheel（vendor/wheels，Python 3.12），无网也能装；失败才走在线
if ! "$VENV_PY" -c "import rapidocr_onnxruntime" 2>/dev/null; then
    echo "[INSTALL] Installing vision/OCR components (约200MB, once)..."
    if [ -d "$SCRIPT_DIR/vendor/wheels" ]; then
        echo "[INFO] Using bundled OCR wheels (offline)..."
        env -u PYTHONPATH "$VENV_PY" -m pip install --no-index --find-links "$SCRIPT_DIR/vendor/wheels" -r requirements-vision.txt || {
            echo "[WARN] offline wheels failed, trying online..."
            env -u PYTHONPATH "$VENV_PY" -m pip install -r requirements-vision.txt || echo "[WARN] vision components failed (OCR unavailable, core OK)"
        }
    else
        env -u PYTHONPATH "$VENV_PY" -m pip install -r requirements-vision.txt || echo "[WARN] vision components failed (OCR unavailable, core OK)"
    fi
else
    echo "[OK] OCR ready"
fi

# === Step 5: Start ===
# 2026-09-01: 依赖终检 — 安装声称成功但 fastapi 仍不可用时给出可操作指引，而非裸 traceback
if ! "$VENV_PY" -c "import fastapi" 2>/dev/null; then
    echo "[ERROR] 依赖未就绪（fastapi 不可用），安装失败。"
    echo "  请检查网络后重跑: bash start.sh"
    echo "  或手动安装: env -u PYTHONPATH $VENV_PY -m pip install -r requirements.txt"
    exit 1
fi
echo ""
echo "[START] http://localhost:$PORT"
echo ""
exec "$VENV_PY" webui/server.py
