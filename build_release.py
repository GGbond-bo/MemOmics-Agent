#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MemOmics-Agent 干净打包脚本 v2.0
- 制作不含个人数据/Key/记忆/会话的干净源码副本
- 生成 4 个平台压缩包: Windows(zip) / Linux(tar.gz) / macOS(tar.gz) / Cluster(tar.gz)
- 内置 Miniconda 安装包（从 E:/release/_miniconda/ 复制）
- 安装时优先找系统 Python，没有则用内置 Miniconda
"""
import os
import sys
import shutil
import platform
import tarfile
import zipfile
import json
from pathlib import Path
from datetime import datetime

# ============================================================
# 配置
# ============================================================
SRC = Path(r"E:/MemOmics-Agent")
DST = Path(r"E:/release")
MINICONDA_SRC = DST / "_miniconda"

PLATFORMS = {
    "Windows": {
        "archive_ext": "zip",
        "miniconda_file": "Miniconda3-latest-Windows-x86_64.exe",
        "start_script": "start.bat",
    },
    "Linux": {
        "archive_ext": "tar.gz",
        "miniconda_file": "Miniconda3-latest-Linux-x86_64.sh",
        "start_script": "start.sh",
    },
    "macOS": {
        "archive_ext": "tar.gz",
        "miniconda_file": None,  # macOS 有两个架构，都放进去
        "start_script": "start.sh",
    },
    "Cluster": {
        "archive_ext": "tar.gz",
        "miniconda_file": "Miniconda3-latest-Linux-x86_64.sh",
        "start_script": "start.sh",
    },
}

# 要打包的顶层文件/目录（从 SRC 根目录）
TOP_LEVEL_INCLUDE = [
    "webui",
    "hermes-agent",
    "hermes_home",
    "memomics",
    "requirements.txt",
    "README_INSTALL.md",
    "R_packages.txt",
    "AGENTS.md",
    ".env.example",
]

# hermes_home 里要打包的（白名单模式）
HERMES_HOME_INCLUDE = [
    "SOUL.md",
    "AGENTS.md",
    "skills",
    "config",   # 如果有 config 目录
]

# hermes_home/skills 里要排除的（黑名单）
HERMES_HOME_SKILLS_EXCLUDE = [
    ".curator_backups",
    ".curator_state",
    ".usage.json",
    ".usage.json.lock",
    ".bundled_manifest",
    ".skills_prompt_snapshot.json",
]

# 通用排除模式（所有目录递归时跳过）
EXCLUDE_DIRS = {
    "__pycache__", ".pytest_cache", ".mypy_cache",
    ".venv", "miniconda_env",
    "node_modules", ".git",
    ".trash",
    ".curator_backups",  # skills curator backups
    ".hub",              # skills hub cache
    "logs",           # hermes_home/logs
    "sessions",       # hermes_home/sessions
    "checkpoints",    # hermes_home/checkpoints
    "sandboxes",      # hermes_home/sandboxes
    "cache",          # hermes_home/cache
    "audio_cache",    # hermes_home/audio_cache
    "image_cache",    # hermes_home/image_cache
    "pairing",        # hermes_home/pairing
    "cron",           # hermes_home/cron
    "hooks",          # hermes_home/hooks
    "results",        # 分析结果
    "work",           # 工作目录
    ".reasonix",
    "work",
}

EXCLUDE_FILES = {
    # 敏感文件
    "config.yaml",          # 含 API key
    "provider_keys.json",   # 含 API key
    "model_config.json",    # 含模型配置
    "auth.json",            # 认证
    "auth.lock",
    "state.db",             # 会话数据库
    "state.db-shm",
    "state.db-wal",
    "verification_evidence.db",
    "processes.json",
    "channel_directory.json",
    "models_dev_cache.json",  # 2.9MB 缓存
    ".skills_prompt_snapshot.json",
    # 根目录不需要的
    "SOUL.md",              # 根目录的（不加载，但打包时用 hermes_home 里的）
    "server.log",
    "ckpt.tar.gz.tmp",
}

# 文件扩展名排除
EXCLUDE_EXTS = {
    ".pyc", ".pyo", ".log", ".lock",
    ".tmp", ".bak", ".swp",
}


def should_exclude_dir(dirname: str) -> bool:
    """检查目录是否应排除"""
    return dirname in EXCLUDE_DIRS


def should_exclude_file(filename: str) -> bool:
    """检查文件是否应排除"""
    if filename in EXCLUDE_FILES:
        return True
    ext = Path(filename).suffix.lower()
    if ext in EXCLUDE_EXTS:
        return True
    return False


def copy_tree_clean(src: Path, dst: Path, skip_dirs: set = None, skip_files: set = None):
    """递归复制目录，排除指定内容"""
    skip_dirs = skip_dirs or set()
    skip_files = skip_files or set()
    dst.mkdir(parents=True, exist_ok=True)

    for item in src.iterdir():
        if item.is_dir():
            if should_exclude_dir(item.name) or item.name in skip_dirs:
                continue
            copy_tree_clean(item, dst / item.name, skip_dirs, skip_files)
        else:
            if should_exclude_file(item.name) or item.name in skip_files:
                continue
            shutil.copy2(item, dst / item.name)


def build_clean_hermes_home(src: Path, dst: Path):
    """构建干净的 hermes_home（白名单 + 黑名单）"""
    dst.mkdir(parents=True, exist_ok=True)

    # 1. 复制 SOUL.md 和 AGENTS.md
    for fname in ["SOUL.md", "AGENTS.md"]:
        fsrc = src / fname
        if fsrc.exists():
            shutil.copy2(fsrc, dst / fname)

    # 2. 复制 skills/（排除缓存文件）
    skills_src = src / "skills"
    skills_dst = dst / "skills"
    if skills_src.exists():
        skills_skip = set(HERMES_HOME_SKILLS_EXCLUDE)
        copy_tree_clean(skills_src, skills_dst, skip_files=skills_skip)

    # 3. 写干净的 config.yaml（不含 API key）
    clean_config = """# MemOmics Configuration
# First run: the WebUI will prompt you to enter your API key.
# Or set MEMOMICS_API_KEY environment variable.

api_base: ""
api_key: ""
max_turns: 200
model: ""
provider: openai
sessions:
  write_json_snapshots: true
skills:
  disabled: []
"""
    (dst / "config.yaml").write_text(clean_config, encoding="utf-8", newline="\n")

    # 4. 写空的 provider_keys.json
    (dst / "provider_keys.json").write_text("{}", encoding="utf-8", newline="\n")

    # 5. 写空的 model_config.json
    clean_model_config = json.dumps({
        "provider": "openai",
        "base_url": "",
        "api_key": "",
        "model": ""
    }, indent=2)
    (dst / "model_config.json").write_text(clean_model_config, encoding="utf-8", newline="\n")

    # 6. 创建空目录（程序运行时需要）
    for d in ["logs", "sessions", "memories", "cache", "checkpoints"]:
        (dst / d).mkdir(exist_ok=True)

    # 7. 写空的 MEMORY.md 和 USER.md
    (dst / "memories" / "MEMORY.md").write_text(
        "# Memory\n\n<!-- MemOmics will accumulate useful facts here. This file starts empty. -->\n",
        encoding="utf-8"
    )
    (dst / "memories" / "USER.md").write_text(
        "# User Profile\n\n<!-- MemOmics will learn about you during conversations. This file starts empty. -->\n",
        encoding="utf-8"
    )


def build_platform(platform_name: str, platform_cfg: dict):
    """构建一个平台的干净副本"""
    pkg_name = f"MemOmics-{platform_name}"
    pkg_dir = DST / pkg_name

    print(f"\n{'='*60}")
    print(f"  构建 {pkg_name}")
    print(f"{'='*60}")

    # 清除旧目录
    if pkg_dir.exists():
        print(f"  清除旧目录: {pkg_dir}")
        shutil.rmtree(pkg_dir, ignore_errors=True)

    pkg_dir.mkdir(parents=True)

    # 1. 复制顶层文件/目录
    for item_name in TOP_LEVEL_INCLUDE:
        src_item = SRC / item_name
        if not src_item.exists():
            print(f"  跳过（不存在）: {item_name}")
            continue

        if src_item.is_dir():
            print(f"  复制目录: {item_name}/")
            # memomics 只打包源码
            if item_name == "memomics":
                copy_tree_clean(src_item, pkg_dir / item_name,
                              skip_dirs={"__pycache__"})
            else:
                copy_tree_clean(src_item, pkg_dir / item_name)
        else:
            print(f"  复制文件: {item_name}")
            shutil.copy2(src_item, pkg_dir / item_name)

    # 2. 构建干净 hermes_home（覆盖上面粗复制的）
    print(f"  构建干净 hermes_home/")
    clean_hermes = pkg_dir / "hermes_home"
    if clean_hermes.exists():
        shutil.rmtree(clean_hermes)
    build_clean_hermes_home(SRC / "hermes_home", clean_hermes)

    # 3. 复制 miniconda 安装包
    miniconda_dst = pkg_dir / "miniconda"
    miniconda_dst.mkdir(exist_ok=True)

    if platform_name == "macOS":
        # macOS 两个架构都放
        for arch_file in ["Miniconda3-latest-MacOSX-arm64.sh",
                          "Miniconda3-latest-MacOSX-x86_64.sh"]:
            src_installer = MINICONDA_SRC / arch_file
            if src_installer.exists():
                print(f"  复制 Miniconda: {arch_file}")
                shutil.copy2(src_installer, miniconda_dst / arch_file)
            else:
                print(f"  ⚠️ Miniconda 缺失: {arch_file}")
    else:
        mc_file = platform_cfg["miniconda_file"]
        if mc_file:
            src_installer = MINICONDA_SRC / mc_file
            if src_installer.exists():
                print(f"  复制 Miniconda: {mc_file}")
                shutil.copy2(src_installer, miniconda_dst / mc_file)
            else:
                print(f"  ⚠️ Miniconda 缺失: {mc_file}")

    # 4. 写启动脚本
    print(f"  写入启动脚本: {platform_cfg['start_script']}")
    write_start_script(platform_name, pkg_dir)

    # 5. 写 README
    write_readme(platform_name, pkg_dir)

    # 6. 打包压缩
    archive_name = f"{pkg_name}.{platform_cfg['archive_ext']}"
    archive_path = DST / archive_name
    print(f"  压缩中: {archive_name} ...")

    if archive_path.exists():
        archive_path.unlink()

    if platform_cfg["archive_ext"] == "zip":
        make_zip(pkg_dir, archive_path)
    else:
        make_tar_gz(pkg_dir, archive_path)

    size_mb = archive_path.stat().st_size / (1024 * 1024)
    print(f"  ✅ 完成: {archive_name} ({size_mb:.1f} MB)")

    return archive_path


def write_start_script(platform_name: str, pkg_dir: Path):
    """写入平台对应的启动脚本"""
    if platform_name == "Windows":
        write_windows_start_bat(pkg_dir)
    elif platform_name == "Linux":
        write_linux_start_sh(pkg_dir)
    elif platform_name == "macOS":
        write_macos_start_sh(pkg_dir)
    elif platform_name == "Cluster":
        write_cluster_start_sh(pkg_dir)


def write_windows_start_bat(pkg_dir: Path):
    script = r"""@echo off
chcp 65001 >nul 2>&1
setlocal enabledelayedexpansion
REM ============================================================
REM   MemOmics-Agent Windows Launcher v2.1
REM   Auto-detect Python -> fallback to bundled miniconda
REM   Usage: start.bat [port]
REM ============================================================
cd /d "%~dp0"

set "PORT=%~1"
if "%PORT%"=="" set "PORT=8899"

echo ============================================================
echo         MemOmics-Agent v2.0 Starting...
echo ============================================================
echo.

REM === Set environment ===
set "HERMES_HOME=%~dp0hermes_home"
set "PYTHONPATH=%~dp0;%~dp0hermes-agent;%PYTHONPATH%"
set "MEMOMICS_PORT=%PORT%"
set "MEMOMICS_HOST=0.0.0.0"

REM === Step 1: Check .venv first ===
if not exist ".venv\Scripts\python.exe" goto :setup_venv

echo [OK] Using existing .venv
set "USE_PY=.venv\Scripts\python.exe"
call !USE_PY! -c "import fastapi, uvicorn, httpx, openai, pydantic; from websockets.exceptions import InvalidState" >nul 2>nul
if !errorlevel! equ 0 goto :start_server
echo [INSTALL] Dependencies missing, installing... (2-3 minutes)
.venv\Scripts\python.exe -m pip install --upgrade pip -q
.venv\Scripts\python.exe -m pip install -r requirements.txt -q
if !errorlevel! neq 0 echo [WARN] Some dependencies failed to install, continuing...
echo [OK] Dependencies installed
goto :start_server

:setup_venv
REM === Step 2: Find system Python 3.11-3.13 ===
set "PYTHON="
for %%c in (python3 python python3.13 python3.12 python3.11) do (
    if not defined PYTHON (
        where %%c >nul 2>&1
        if !errorlevel! equ 0 (
            call %%c -c "import sys; v=sys.version_info; sys.exit(0 if v[0]==3 and v[1]>=11 and v[1]<=13 else 1)" >nul 2>nul
            if !errorlevel! equ 0 (
                set "PYTHON=%%c"
                echo [OK] Found system Python: %%c
            )
        )
    )
)

REM === Step 3: No Python? Use bundled miniconda ===
if defined PYTHON goto :create_venv
echo [WARN] Python 3.11-3.13 not found, using bundled Miniconda...
set "CONDA_PY=%~dp0miniconda_env\python.exe"
if exist "!CONDA_PY!" goto :conda_ready
set "INSTALLER=%~dp0miniconda\Miniconda3-latest-Windows-x86_64.exe"
if not exist "!INSTALLER!" (
    echo [ERROR] Bundled miniconda installer not found!
    pause
    exit /b 1
)
echo [INSTALL] Extracting Miniconda to miniconda_env\ ...
start /wait "" "!INSTALLER!" /S /InstallationType=JustMe /RegisterPython=0 /D=%~dp0miniconda_env
if not exist "!CONDA_PY!" (
    echo [ERROR] Miniconda installation failed!
    pause
    exit /b 1
)
:conda_ready
set "PYTHON=!CONDA_PY!"
echo [OK] Using Miniconda Python

:create_venv
REM === Step 4: Create venv ===
echo [SETUP] Creating virtual environment...
"%PYTHON%" -m venv .venv
if exist ".venv\Scripts\python.exe" goto :venv_ok
echo [WARN] venv creation failed, using current Python directly
set "USE_PY=!PYTHON!"
goto :check_deps
:venv_ok
echo [OK] Virtual environment created
set "USE_PY=.venv\Scripts\python.exe"

:check_deps
REM === Step 5: Install dependencies ===
call "!USE_PY!" -c "import fastapi, uvicorn, httpx, openai, pydantic; from websockets.exceptions import InvalidState" >nul 2>nul
if !errorlevel! equ 0 goto :deps_ready
echo [INSTALL] Installing dependencies (2-3 minutes)...
"!USE_PY!" -m pip install --upgrade pip -q
"!USE_PY!" -m pip install -r requirements.txt -q
if !errorlevel! neq 0 (
    echo [WARN] Some dependencies failed to install, continuing...
) else (
    echo [OK] Dependencies installed
)
goto :start_server
:deps_ready
echo [OK] Dependencies ready

:start_server
REM === Step 6: Start server ===
echo.
echo [START] MemOmics on port %PORT%...
echo    URL: http://localhost:%PORT%
echo.
"!USE_PY!" webui\server.py

echo.
echo MemOmics stopped.
pause
"""
    (pkg_dir / "start.bat").write_text(script, encoding="utf-8", newline="\r\n")


def write_linux_start_sh(pkg_dir: Path):
    script = r"""#!/usr/bin/env bash
# ============================================================
#  MemOmics-Agent Linux 启动器 v2.0
#  自动检测 Python -> 无则用内置 miniconda
#  用法: ./start.sh [port]
# ============================================================
set -e
cd "$(dirname "$0")"
PORT="${1:-8899}"

echo "============================================================"
echo "       MemOmics-Agent v2.0 Starting...        "
echo "============================================================"
echo ""

export HERMES_HOME="$(pwd)/hermes_home"
export PYTHONPATH="$(pwd):$(pwd)/hermes-agent:${PYTHONPATH}"
export MEMOMICS_PORT="$PORT"
export MEMOMICS_HOST="0.0.0.0"

# === Step 1: Check .venv first ===
VENV_PY="$(pwd)/.venv/bin/python"
if [ -f "$VENV_PY" ]; then
    echo "[OK] Using existing .venv"
    if ! "$VENV_PY" -c "import fastapi, uvicorn, httpx, openai, pydantic; from websockets.exceptions import InvalidState" 2>/dev/null; then
        echo "[INSTALL] Dependencies missing, installing... (2-3 minutes)"
        "$VENV_PY" -m pip install --upgrade pip -q
        "$VENV_PY" -m pip install -r requirements.txt -q || echo "[WARN] Some dependencies failed, continuing..."
        echo "[OK] Dependencies installed"
    else
        echo "[OK] Dependencies ready"
    fi
    echo "[START] MemOmics on port $PORT..."
    echo "   URL: http://localhost:$PORT"
    echo ""
    exec "$VENV_PY" webui/server.py
fi

# === Step 2: Find system Python 3.11-3.13 ===
PYTHON=""
for c in python3 python python3.13 python3.12 python3.11 \
         /usr/bin/python3 /usr/local/bin/python3; do
    if command -v "$c" &>/dev/null || [ -x "$c" ]; then
        if "$c" -c "import sys; sys.exit(0 if sys.version_info >= (3,11) and sys.version_info < (3,14) else 1)" 2>/dev/null; then
            PYTHON="$c"
            echo "[OK] Found system Python: $c ($("$c" --version 2>&1))"
            break
        fi
    fi
done

# === Step 3: No Python? Use bundled miniconda ===
if [ -z "$PYTHON" ]; then
    echo "[WARN] Python 3.11-3.13 not found, using bundled Miniconda..."
    CONDA_PY="$(pwd)/miniconda_env/bin/python"
    if [ ! -f "$CONDA_PY" ]; then
        INSTALLER="$(pwd)/miniconda/Miniconda3-latest-Linux-x86_64.sh"
        if [ ! -f "$INSTALLER" ]; then
            echo "[ERROR] Bundled miniconda installer not found!"
            exit 1
        fi
        echo "[INSTALL] Extracting Miniconda to miniconda_env/ ..."
        bash "$INSTALLER" -b -p "$(pwd)/miniconda_env"
        if [ ! -f "$CONDA_PY" ]; then
            echo "[ERROR] Miniconda installation failed!"
            exit 1
        fi
    fi
    PYTHON="$CONDA_PY"
    echo "[OK] Using Miniconda Python"
fi

# === Step 4: Create venv ===
echo "[SETUP] Creating virtual environment..."
"$PYTHON" -m venv .venv || {
    echo "[WARN] venv creation failed, using current Python directly"
    VENV_PY="$PYTHON"
}
if [ -f ".venv/bin/python" ]; then
    VENV_PY="$(pwd)/.venv/bin/python"
    echo "[OK] Virtual environment created"
fi

# === Step 5: Install dependencies ===
if ! "$VENV_PY" -c "import fastapi, uvicorn, httpx, openai, pydantic; from websockets.exceptions import InvalidState" 2>/dev/null; then
    echo "[INSTALL] Installing dependencies (2-3 minutes)..."
    "$VENV_PY" -m pip install --upgrade pip -q
    "$VENV_PY" -m pip install -r requirements.txt -q || echo "[WARN] Some dependencies failed, continuing..."
    echo "[OK] Dependencies installed"
else
    echo "[OK] Dependencies ready"
fi

# === Step 6: Start server ===
echo ""
echo "[START] MemOmics on port $PORT..."
echo "   URL: http://localhost:$PORT"
echo ""
exec "$VENV_PY" webui/server.py
"""
    (pkg_dir / "start.sh").write_text(script, encoding="utf-8", newline="\n")
    os.chmod(pkg_dir / "start.sh", 0o755)


def write_macos_start_sh(pkg_dir: Path):
    script = r"""#!/usr/bin/env bash
# ============================================================
#  MemOmics-Agent macOS 启动器 v2.0
#  支持 Apple Silicon (arm64) 和 Intel (x86_64)
#  用法: ./start.sh [port]
# ============================================================
set -e
cd "$(dirname "$0")"
PORT="${1:-8899}"

echo "============================================================"
echo "       MemOmics-Agent v2.0 Starting...        "
echo "============================================================"
echo ""

export HERMES_HOME="$(pwd)/hermes_home"
export PYTHONPATH="$(pwd):$(pwd)/hermes-agent:${PYTHONPATH}"
export MEMOMICS_PORT="$PORT"
export MEMOMICS_HOST="0.0.0.0"

# === Step 1: Check .venv first ===
VENV_PY="$(pwd)/.venv/bin/python"
if [ -f "$VENV_PY" ]; then
    echo "[OK] Using existing .venv"
    if ! "$VENV_PY" -c "import fastapi, uvicorn, httpx, openai, pydantic; from websockets.exceptions import InvalidState" 2>/dev/null; then
        echo "[INSTALL] Dependencies missing, installing... (2-3 minutes)"
        "$VENV_PY" -m pip install --upgrade pip -q
        "$VENV_PY" -m pip install -r requirements.txt -q || echo "[WARN] Some dependencies failed, continuing..."
        echo "[OK] Dependencies installed"
    else
        echo "[OK] Dependencies ready"
    fi
    echo "[START] MemOmics on port $PORT..."
    echo "   URL: http://localhost:$PORT"
    echo ""
    exec "$VENV_PY" webui/server.py
fi

# === Step 2: Find system Python 3.11-3.13 ===
PYTHON=""
for c in python3 python python3.13 python3.12 python3.11 \
         /usr/bin/python3 /usr/local/bin/python3 /opt/homebrew/bin/python3; do
    if command -v "$c" &>/dev/null || [ -x "$c" ]; then
        if "$c" -c "import sys; sys.exit(0 if sys.version_info >= (3,11) and sys.version_info < (3,14) else 1)" 2>/dev/null; then
            PYTHON="$c"
            echo "[OK] Found system Python: $c ($("$c" --version 2>&1))"
            break
        fi
    fi
done

# === Step 3: No Python? Use bundled miniconda ===
if [ -z "$PYTHON" ]; then
    echo "[WARN] Python 3.11-3.13 not found, using bundled Miniconda..."
    CONDA_PY="$(pwd)/miniconda_env/bin/python"
    if [ ! -f "$CONDA_PY" ]; then
        ARCH="$(uname -m)"
        [ -z "$ARCH" ] && ARCH="$(arch 2>/dev/null)"
        case "$ARCH" in
            arm64)  INSTALLER="$(pwd)/miniconda/Miniconda3-latest-MacOSX-arm64.sh" ;;
            x86_64) INSTALLER="$(pwd)/miniconda/Miniconda3-latest-MacOSX-x86_64.sh" ;;
            *) echo "[ERROR] Unsupported macOS arch: $ARCH"; exit 1 ;;
        esac
        if [ ! -f "$INSTALLER" ]; then
            echo "[ERROR] Bundled miniconda installer not found: $INSTALLER"
            exit 1
        fi
        echo "[INSTALL] Extracting Miniconda ($ARCH) to miniconda_env/ ..."
        bash "$INSTALLER" -b -p "$(pwd)/miniconda_env"
        if [ ! -f "$CONDA_PY" ]; then
            echo "[ERROR] Miniconda installation failed!"
            exit 1
        fi
    fi
    PYTHON="$CONDA_PY"
    echo "[OK] Using Miniconda Python"
fi

# === Step 4: Create venv ===
echo "[SETUP] Creating virtual environment..."
"$PYTHON" -m venv .venv || {
    echo "[WARN] venv creation failed, using current Python directly"
    VENV_PY="$PYTHON"
}
if [ -f ".venv/bin/python" ]; then
    VENV_PY="$(pwd)/.venv/bin/python"
    echo "[OK] Virtual environment created"
fi

# === Step 5: Install dependencies ===
if ! "$VENV_PY" -c "import fastapi, uvicorn, httpx, openai, pydantic; from websockets.exceptions import InvalidState" 2>/dev/null; then
    echo "[INSTALL] Installing dependencies (2-3 minutes)..."
    "$VENV_PY" -m pip install --upgrade pip -q
    "$VENV_PY" -m pip install -r requirements.txt -q || echo "[WARN] Some dependencies failed, continuing..."
    echo "[OK] Dependencies installed"
else
    echo "[OK] Dependencies ready"
fi

# === Step 6: Start server ===
echo ""
echo "[START] MemOmics on port $PORT..."
echo "   URL: http://localhost:$PORT"
echo ""
exec "$VENV_PY" webui/server.py
"""
    (pkg_dir / "start.sh").write_text(script, encoding="utf-8", newline="\n")
    os.chmod(pkg_dir / "start.sh", 0o755)


def write_cluster_start_sh(pkg_dir: Path):
    script = r"""#!/usr/bin/env bash
# ============================================================
#  MemOmics-Agent 集群终端启动器 v2.0
#  适用于 HPC/SLURM/服务器集群环境
#  用法:
#    交互模式:  ./start.sh
#    SLURM 模式: ./start.sh --slurm
#    指定端口:   ./start.sh 8899
# ============================================================
set -e
cd "$(dirname "$0")"
PORT="${MEMOMICS_PORT:-8899}"
SLURM_MODE=false

for arg in "$@"; do
    case "$arg" in
        --slurm) SLURM_MODE=true ;;
        [0-9]*)  PORT="$arg" ;;
    esac
done

echo "============================================================"
echo "  MemOmics-Agent v2.0 (Cluster Edition)       "
echo "============================================================"
echo ""

export HERMES_HOME="$(pwd)/hermes_home"
export PYTHONPATH="$(pwd):$(pwd)/hermes-agent:${PYTHONPATH}"
export MEMOMICS_PORT="$PORT"
export MEMOMICS_HOST="0.0.0.0"

# === Step 0: SLURM 模式 ===
if [ "$SLURM_MODE" = true ]; then
    echo "[SLURM] Generating SLURM job script..."
    cat > "$(pwd)/submit_memomics.slurm" << SLURMEOF
#!/bin/bash
#SBATCH --job-name=memomics
#SBATCH --partition=compute
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=16G
#SBATCH --time=24:00:00
#SBATCH --output=memomics_%j.log

cd "$(pwd)"
export MEMOMICS_PORT="$PORT"
exec bash "$(pwd)/start.sh" "$PORT"
SLURMEOF
    echo "[OK] SLURM script generated: submit_memomics.slurm"
    echo "   提交作业: sbatch submit_memomics.slurm"
    exit 0
fi

# === Step 1: 尝试 module load ===
if command -v module &>/dev/null; then
    echo "[SEARCH] Trying to load Python module..."
    for mod in python/3.12 python/3.11 python/3.13 python python3; do
        if module avail "$mod" 2>&1 | grep -q "$mod"; then
            module load "$mod" 2>/dev/null && echo "  [OK] module load $mod" && break
        fi
    done
fi

# === Step 2: Find system Python 3.11-3.13 ===
PYTHON=""
for c in python3 python python3.13 python3.12 python3.11 \
         /usr/bin/python3 /usr/local/bin/python3 \
         "$HOME/miniconda3/bin/python3" "$HOME/anaconda3/bin/python3" \
         "$(pwd)/miniconda_env/bin/python"; do
    if command -v "$c" &>/dev/null || [ -x "$c" ]; then
        if "$c" -c "import sys; sys.exit(0 if sys.version_info >= (3,11) and sys.version_info < (3,14) else 1)" 2>/dev/null; then
            PYTHON="$c"
            echo "[OK] Found Python: $c ($("$c" --version 2>&1))"
            break
        fi
    fi
done

# === Step 3: No Python? Use bundled miniconda ===
if [ -z "$PYTHON" ]; then
    echo "[WARN] Python 3.11-3.13 not found, using bundled Miniconda..."
    CONDA_PY="$(pwd)/miniconda_env/bin/python"
    if [ ! -f "$CONDA_PY" ]; then
        INSTALLER="$(pwd)/miniconda/Miniconda3-latest-Linux-x86_64.sh"
        if [ ! -f "$INSTALLER" ]; then
            echo "[ERROR] Bundled miniconda installer not found!"
            exit 1
        fi
        echo "[INSTALL] Extracting Miniconda to miniconda_env/ ..."
        bash "$INSTALLER" -b -p "$(pwd)/miniconda_env"
        if [ ! -f "$CONDA_PY" ]; then
            echo "[ERROR] Miniconda installation failed!"
            exit 1
        fi
    fi
    PYTHON="$CONDA_PY"
    echo "[OK] Using Miniconda Python"
fi

# === Step 4: Create venv (用户家目录，避免节点存储限制) ===
VENV_DIR="$HOME/.memomics_venv"
VENV_PY="$VENV_DIR/bin/python"
if [ ! -f "$VENV_PY" ]; then
    echo "[SETUP] Creating virtual environment (~/.memomics_venv)..."
    "$PYTHON" -m venv "$VENV_DIR" || {
        echo "[WARN] venv creation failed, using current Python directly"
        VENV_PY="$PYTHON"
    }
    echo "[OK] Virtual environment created"
fi

# === Step 5: Install dependencies ===
if ! "$VENV_PY" -c "import fastapi, uvicorn, httpx, openai, pydantic; from websockets.exceptions import InvalidState" 2>/dev/null; then
    echo "[INSTALL] Installing dependencies (2-3 minutes)..."
    "$VENV_PY" -m pip install --upgrade pip -q
    "$VENV_PY" -m pip install -r requirements.txt -q || echo "[WARN] Some dependencies failed, continuing..."
    echo "[OK] Dependencies installed"
else
    echo "[OK] Dependencies ready"
fi

# === Step 6: Start server ===
echo ""
echo "[START] MemOmics-Agent on port $PORT..."
echo "   URL: http://localhost:$PORT"
echo "   集群远程: ssh -L $PORT:localhost:$PORT user@cluster"
echo ""
exec "$VENV_PY" webui/server.py
"""
    (pkg_dir / "start.sh").write_text(script, encoding="utf-8", newline="\n")
    os.chmod(pkg_dir / "start.sh", 0o755)


def write_readme(platform_name: str, pkg_dir: Path):
    """写入 README"""
    if platform_name == "Windows":
        content = """# MemOmics-Agent v2.0 (Windows)

## 快速开始

1. 解压本目录到任意位置
2. 双击运行 `start.bat`
3. 浏览器访问 http://localhost:8899

## 环境要求

- **无需预装 Python** - 启动器优先检测系统 Python 3.11-3.13
- 如果系统没有 Python，会自动用内置 Miniconda 创建环境
- 首次启动会自动安装依赖（约 2-3 分钟）

## 首次配置

启动后在浏览器中配置：
1. 选择 API 提供商
2. 输入 API Key
3. 选择模型
4. 点击「开始使用」

## 自定义端口

```bat
start.bat 9000
```

## 目录结构

```
MemOmics-Windows/
├── start.bat              # 启动脚本
├── webui/                 # Web 界面
├── hermes-agent/          # Hermes 框架
├── hermes_home/           # 配置和技能
│   ├── SOUL.md            # 系统人格
│   ├── skills/            # 生信技能库
│   └── config.yaml        # 配置（首次需填写 API Key）
├── memomics/              # 分析模块
│   └── knowledge_base/    # 知识库
├── miniconda/             # 内置 Miniconda 安装包
└── requirements.txt       # Python 依赖
```
"""
    elif platform_name == "Cluster":
        content = """# MemOmics-Agent v2.0 (Cluster Edition)

## 集群/HPC 环境快速开始

### 交互模式

1. 解压: `tar xzf MemOmics-Cluster.tar.gz`
2. 进入目录: `cd MemOmics-Cluster`
3. 运行: `./start.sh`
4. SSH 端口转发: `ssh -L 8899:localhost:8899 user@cluster`
5. 本地浏览器访问 http://localhost:8899

### SLURM 作业模式

```bash
./start.sh --slurm            # 生成 SLURM 脚本
sbatch submit_memomics.slurm  # 提交作业
```

## 特性

- 自动检测 `module load` 系统
- 支持 SLURM 作业调度
- 虚拟环境存放在 `~/.memomics_venv`（避免节点存储限制）
- 内置 Miniconda（无需 root 权限）
- 优先使用系统 Python，无则用内置 Miniconda
"""
    else:
        content = f"""# MemOmics-Agent v2.0 ({platform_name})

## 快速开始

1. 解压: `tar xzf MemOmics-{platform_name}.tar.gz`
2. 进入目录: `cd MemOmics-{platform_name}`
3. 运行: `./start.sh`
4. 浏览器访问 http://localhost:8899

## 环境要求

- **无需预装 Python** - 启动器优先检测系统 Python 3.11-3.13
- 如果系统没有 Python，会自动用内置 Miniconda 创建环境
- 首次启动会自动安装依赖（约 2-3 分钟）

## 自定义端口

```bash
./start.sh 9000
```
"""
    (pkg_dir / "README.md").write_text(content, encoding="utf-8", newline="\n")


def make_zip(src_dir: Path, archive_path: Path):
    """制作 zip 压缩包"""
    with zipfile.ZipFile(archive_path, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for root, dirs, files in os.walk(src_dir):
            for f in files:
                file_path = Path(root) / f
                arcname = file_path.relative_to(src_dir.parent)
                zf.write(file_path, arcname)


def make_tar_gz(src_dir: Path, archive_path: Path):
    """制作 tar.gz 压缩包"""
    with tarfile.open(archive_path, 'w:gz') as tf:
        tf.add(src_dir, arcname=src_dir.name)


def verify_clean(pkg_dir: Path):
    """验证打包目录不含敏感数据"""
    print(f"\n  🔍 安全验证...")
    issues = []

    sensitive_files = [
        "hermes_home/config.yaml",
        "hermes_home/provider_keys.json",
        "hermes_home/model_config.json",
        "hermes_home/state.db",
        "hermes_home/auth.json",
    ]

    for sf in sensitive_files:
        fp = pkg_dir / sf
        if fp.exists():
            content = fp.read_text(encoding="utf-8", errors="ignore")
            if "sk-" in content or "api_key" in content.lower() and '""' not in content and "{}" not in content:
                issues.append(f"  ⚠️ {sf} 可能含敏感数据")

    # 检查是否有会话/日志
    for d in ["hermes_home/sessions", "hermes_home/logs", "hermes_home/cache"]:
        dp = pkg_dir / d
        if dp.exists() and any(dp.iterdir()):
            issues.append(f"  ⚠️ {d}/ 不为空")

    # 检查是否含 bioinformatics-core
    bc = pkg_dir / "hermes_home/skills/bioinformatics-core"
    if bc.exists():
        issues.append(f"  ⚠️ hermes_home/skills/bioinformatics-core/ 仍存在（应删除）")

    bs = pkg_dir / "hermes_home/skills/bioinformatics-specialized"
    if bs.exists():
        issues.append(f"  ⚠️ hermes_home/skills/bioinformatics-specialized/ 仍存在（应删除）")

    if issues:
        print("  ❌ 发现问题:")
        for i in issues:
            print(i)
        return False
    else:
        print("  ✅ 无敏感数据泄漏")
        return True


def main():
    print("=" * 60)
    print("  MemOmics-Agent v2.0 打包工具")
    print(f"  时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  源目录: {SRC}")
    print(f"  输出目录: {DST}")
    print("=" * 60)

    # 检查源目录
    if not SRC.exists():
        print(f"❌ 源目录不存在: {SRC}")
        sys.exit(1)

    # 检查 miniconda 源
    if not MINICONDA_SRC.exists():
        print(f"⚠️ Miniconda 源目录不存在: {MINICONDA_SRC}")
        print("  将跳过内置 Miniconda")

    # 逐平台构建
    archives = []
    for plat_name, plat_cfg in PLATFORMS.items():
        try:
            archive = build_platform(plat_name, plat_cfg)

            # 验证
            pkg_dir = DST / f"MemOmics-{plat_name}"
            if not verify_clean(pkg_dir):
                print(f"  ⚠️ {plat_name} 安全验证未通过，但压缩包已生成")

            archives.append(archive)
        except Exception as e:
            print(f"  ❌ {plat_name} 打包失败: {e}")
            import traceback
            traceback.print_exc()

    # 汇总
    print(f"\n{'='*60}")
    print("  打包完成汇总")
    print(f"{'='*60}")
    for a in archives:
        if a and a.exists():
            size_mb = a.stat().st_size / (1024 * 1024)
            print(f"  ✅ {a.name}  ({size_mb:.1f} MB)")
        else:
            print(f"  ❌ 缺失")
    print()


if __name__ == "__main__":
    main()
