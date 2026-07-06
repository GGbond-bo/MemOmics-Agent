#!/usr/bin/env bash
# ============================================================
#  MemOmics-Agent 集群终端启动器
#  适用于 HPC/SLURM/服务器集群环境
#  特性: 支持 module load、conda activate、SLURM 作业提交
#  用法:
#    交互模式:  ./start_cluster.sh
#    SLURM 模式: ./start_cluster.sh --slurm
#    指定端口:   ./start_cluster.sh 8899
# ============================================================
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"
PORT="${MEMOMICS_PORT:-8899}"
SLURM_MODE=false

# 解析参数
for arg in "$@"; do
    case "$arg" in
        --slurm) SLURM_MODE=true ;;
        [0-9]*)  PORT="$arg" ;;
    esac
done

echo "╔══════════════════════════════════════════════╗"
echo "║  MemOmics-Agent v1.0 (Cluster Edition)      ║"
echo "╚══════════════════════════════════════════════╝"
echo ""

# === Step 0: SLURM 模式 ===
if [ "$SLURM_MODE" = true ]; then
    echo "📝 生成 SLURM 作业脚本..."
    cat > "$SCRIPT_DIR/submit_memomics.slurm" << SLURMEOF
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
exec bash "$SCRIPT_DIR/start_cluster.sh" "$PORT"
SLURMEOF
    echo "✅ SLURM 脚本已生成: submit_memomics.slurm"
    echo "   提交作业: sbatch submit_memomics.slurm"
    echo "   查看队列: squeue -u \$USER"
    exit 0
fi

# === Step 1: 尝试 module load ===
if command -v module &>/dev/null; then
    echo "🔍 尝试加载 Python 模块..."
    for mod in python/3.12 python/3.11 python/3.13 python python3; do
        if module avail "$mod" 2>&1 | grep -q "$mod"; then
            module load "$mod" 2>/dev/null && echo "  ✅ module load $mod" && break
        fi
    done
fi

# === Step 2: Find Python 3.11-3.13 ===
PYTHON=""
for c in python3 python python3.13 python3.12 python3.11 \
         /usr/bin/python3 /usr/local/bin/python3 \
         "$HOME/miniconda3/bin/python3" "$HOME/anaconda3/bin/python3" \
         "$SCRIPT_DIR/miniconda_env/bin/python"; do
    if command -v "$c" &>/dev/null || [ -x "$c" ]; then
        if "$c" -c "import sys; sys.exit(0 if sys.version_info >= (3,11) and sys.version_info < (3,14) else 1)" 2>/dev/null; then
            PYTHON="$c"
            echo "✅ 找到 Python: $c ($("$c" --version 2>&1))"
            break
        fi
    fi
done

# === Step 3: No Python? Use bundled miniconda ===
if [ -z "$PYTHON" ]; then
    echo "⚠️ 未找到 Python 3.11-3.13，使用内置 Miniconda..."
    CONDA_PYTHON="$SCRIPT_DIR/miniconda_env/bin/python"
    if [ ! -f "$CONDA_PYTHON" ]; then
        INSTALLER="$SCRIPT_DIR/miniconda/Miniconda3-latest-Linux-x86_64.sh"
        if [ ! -f "$INSTALLER" ]; then
            echo "❌ 内置 miniconda 安装包未找到!"
            echo "   请从 https://docs.conda.io 下载 Miniconda3-latest-Linux-x86_64.sh"
            echo "   放到 $SCRIPT_DIR/miniconda/ 目录下"
            exit 1
        fi
        echo "📦 安装 Miniconda 到 miniconda_env/ ..."
        bash "$INSTALLER" -b -p "$SCRIPT_DIR/miniconda_env"
        if [ ! -f "$CONDA_PYTHON" ]; then
            echo "❌ Miniconda 安装失败!"
            exit 1
        fi
    fi
    PYTHON="$CONDA_PYTHON"
    echo "✅ 使用 Miniconda Python: $PYTHON"
fi

# === Step 4: Create venv (用户家目录，避免节点存储限制) ===
VENV_DIR="$HOME/.memomics_venv"
VENV_PYTHON="$VENV_DIR/bin/python"
if [ ! -f "$VENV_PYTHON" ]; then
    echo "🔧 创建虚拟环境 (~/​.memomics_venv)..."
    "$PYTHON" -m venv "$VENV_DIR" || {
        echo "⚠️ venv 创建失败，直接使用当前 Python"
        VENV_PYTHON="$PYTHON"
    }
    echo "✅ 虚拟环境已创建"
fi

# === Step 5: Install dependencies ===
if ! "$VENV_PYTHON" -c "import fastapi" 2>/dev/null; then
    echo "📥 安装依赖包..."
    "$VENV_PYTHON" -m pip install --upgrade pip -q
    "$VENV_PYTHON" -m pip install -r requirements.txt -q || echo "⚠️ 部分依赖安装失败，尝试继续..."
    echo "✅ 依赖安装完成"
else
    echo "✅ 依赖已就绪"
fi

# === Step 6: Start server ===
echo ""
echo "🚀 启动 MemOmics-Agent (端口 $PORT)..."
echo "   浏览器访问: http://localhost:$PORT"
echo "   集群远程: ssh -L $PORT:localhost:$PORT user@cluster"
echo ""
export MEMOMICS_PORT="$PORT"
exec "$VENV_PYTHON" webui/server.py
