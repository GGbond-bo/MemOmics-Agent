#!/usr/bin/env bash
# ============================================================
#  MemOmics-Agent Linux 启动器
#  用法: ./start.sh [port]
# ============================================================
set -o pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"
PORT="${1:-${MEMOMICS_PORT:-8899}}"

# === 守护模式（登录节点/服务器后台常驻；2026-09-01） ===
#   ./start.sh 8899 --daemon → nohup 后台运行；日志 log/webui.log，PID log/webui.pid
#   ./start.sh --stop        → 停止后台实例
if [ "$1" = "--stop" ]; then
    if [ -f "$SCRIPT_DIR/log/webui.pid" ]; then
        _pid="$(cat "$SCRIPT_DIR/log/webui.pid")"
        kill "$_pid" 2>/dev/null && echo "[DAEMON] 已停止 PID $_pid" || echo "[DAEMON] PID $_pid 不存在或已退出"
        rm -f "$SCRIPT_DIR/log/webui.pid"
    else
        echo "[DAEMON] 未找到 PID 文件（log/webui.pid）"
    fi
    exit 0
fi
DAEMON=0
for _arg in "$@"; do
    [ "$_arg" = "--daemon" ] && DAEMON=1
done
if [ "$DAEMON" = "1" ]; then
    mkdir -p "$SCRIPT_DIR/log"
    nohup setsid bash "$0" "$PORT" >"$SCRIPT_DIR/log/webui.log" 2>&1 &
    echo "$!" >"$SCRIPT_DIR/log/webui.pid"
    echo "[DAEMON] MemOmics WebUI 后台启动中（日志: log/webui.log，PID: $!）"
    echo "[DAEMON] 查看: tail -f log/webui.log | 停止: ./start.sh --stop"
    exit 0
fi

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
    echo "[WARN] Python 3.10-3.13 not found"
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
# 2026-09-01: 集群环境 R 常经 module load（Lmod/Environment Modules）提供，
# 启动前在登录 shell 尽力探测并导出 RSCRIPT_PATH；找不到不阻塞。
echo "[INFO] 核心依赖就绪（Agent 可正常使用）。"
echo "  Python 分析包（scanpy 生态）按需安装：pip install -r requirements-analysis.txt"
echo "  R 包由 Agent 在任务中检查用户环境后询问安装（清华镜像）"

# === Step 4.5.1: module load R 尽力探测（集群） ===
if ! command -v Rscript &>/dev/null && [ -z "${RSCRIPT_PATH:-}" ]; then
    _r_module="$(bash -lc 'if command -v module >/dev/null 2>&1; then module load R 2>/dev/null; command -v Rscript; fi' 2>/dev/null)"
    if [ -n "$_r_module" ]; then
        export RSCRIPT_PATH="$_r_module"
        echo "[OK] Rscript 经 module load 找到: $RSCRIPT_PATH"
    fi
fi

# === Step 4.6: 项目内 R 库目录（2026-08-29：R 包统一装这里，不污染系统/用户库）===
# Agent 按 SOUL 铁律 29 安装 R 包时用 R_LIBS 指向本目录；持久内核
# （persistent_kernel .libPaths 探测）会自动包含 R_LIBS。
mkdir -p "$SCRIPT_DIR/R_libs"
export R_LIBS="$SCRIPT_DIR/R_libs${R_LIBS:+:$R_LIBS}"
if command -v Rscript &>/dev/null || [ -n "${RSCRIPT_PATH:-}" ]; then
    echo "[OK] Rscript found: ${RSCRIPT_PATH:-$(command -v Rscript)}"
else
    echo "[WARN] Rscript 未找到 —— R 分析（Seurat/WGCNA 等）不可用，核心 WebUI 不受影响"
    echo "  集群 R 经 module 提供: 先 module load R 再启动（本脚本也会自动尝试）"
    echo "  独立安装 R（Ubuntu/Debian，tuna 镜像加速包安装）:"
    echo "    sudo apt-get update && sudo apt-get install -y r-base"
    echo "  已有 R 但不在 PATH: export RSCRIPT_PATH=/path/to/Rscript 后再启动"
    echo "  关键 R 包清单见 R_packages.txt；安装 R 包可用清华镜像:"
    echo "    Rscript -e 'options(repos=c(CRAN=\"https://mirrors.tuna.tsinghua.edu.cn/CRAN/\")); install.packages(c(\"Seurat\",\"ggplot2\"))'"
fi

# === Step 5: Start ===
echo ""
echo "[START] http://localhost:$PORT"
echo ""
exec "$VENV_PY" webui/server.py
