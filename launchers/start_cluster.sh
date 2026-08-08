#!/usr/bin/env bash
# ============================================================
#  MemOmics-Agent 集群启动器 (HPC/SLURM)
#  用法:
#    ./start.sh          交互模式
#    ./start.sh --slurm  生成 SLURM 作业脚本
#    ./start.sh 8899     指定端口
# ============================================================
set -o pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"
PORT="${MEMOMICS_PORT:-8899}"
SLURM_MODE=false

for arg in "$@"; do
    case "$arg" in
        --slurm) SLURM_MODE=true ;;
        [0-9]*)  PORT="$arg" ;;
    esac
done

echo "╔══════════════════════════════════════════════╗"
echo "║  MemOmics-Agent v2.0 (Cluster Edition)      ║"
echo "╚══════════════════════════════════════════════╝"
echo ""

# SLURM mode: generate job script and exit
if [ "$SLURM_MODE" = true ]; then
    cat > "$SCRIPT_DIR/submit_memomics.slurm" << 'SLURMEOF'
#!/bin/bash
#SBATCH --job-name=memomics
#SBATCH --partition=compute
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=16G
#SBATCH --time=24:00:00
#SBATCH --output=memomics_%j.log
cd "$SCRIPT_DIR"
export MEMOMICS_PORT="$PORT"
exec bash "$SCRIPT_DIR/start.sh" "$PORT"
SLURMEOF
    echo "[OK] SLURM script: submit_memomics.slurm"
    echo "  Submit: sbatch submit_memomics.slurm"
    echo "  Queue:  squeue -u \$USER"
    exit 0
fi

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

# Try module load on HPC
if command -v module &>/dev/null; then
    for mod in python/3.12 python/3.11 python/3.13 python python3; do
        module load "$mod" 2>/dev/null && echo "[OK] module load $mod" && break
    done
fi

# === Find Python ===
PYTHON=""
for c in python3 python python3.13 python3.12 python3.11 \
         /usr/bin/python3 /usr/local/bin/python3 \
         "$HOME/miniconda3/bin/python3" "$HOME/anaconda3/bin/python3" \
         "$SCRIPT_DIR/miniconda_env/bin/python"; do
    if command -v "$c" &>/dev/null || [ -x "$c" ]; then
        if "$c" -c "import sys; sys.exit(0 if (3,10) <= sys.version_info < (3,14) else 1)" 2>/dev/null; then
            PYTHON="$c"
            echo "[OK] Found: $c"
            break
        fi
    fi
done

# === Use bundled miniconda ===
if [ -z "$PYTHON" ]; then
    echo "[WARN] Python 3.11-3.13 not found"
    echo "[INFO] Using bundled Miniconda..."

    CONDA_PY="$SCRIPT_DIR/miniconda_env/bin/python"
    if [ ! -f "$CONDA_PY" ]; then
        INSTALLER="$SCRIPT_DIR/miniconda/Miniconda3-latest-Linux-x86_64.sh"
        if [ ! -f "$INSTALLER" ]; then
            echo "[ERROR] miniconda installer missing!"
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

# === Create venv ===
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

# === Install dependencies ===
if ! "$VENV_PY" -c "import fastapi" 2>/dev/null; then
    echo "[INSTALL] Installing dependencies (3-8 min, once)..."
    "$VENV_PY" -m pip install --upgrade pip --quiet 2>/dev/null || true
    "$VENV_PY" -m pip install -r requirements.txt || echo "[WARN] Some packages failed"
else
    echo "[OK] Dependencies ready"
fi

# === Start ===
echo ""
echo "[START] http://localhost:$PORT"
echo "  Remote: ssh -L $PORT:localhost:$PORT user@cluster"
echo ""
exec "$VENV_PY" webui/server.py
