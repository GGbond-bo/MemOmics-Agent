#!/usr/bin/env python3
"""
ptrepack 批量转换：h5py 直接复制 /matrix group（绕过 ptrepack CLI）
适用场景：ptrepack CLI 不可用 / MSYS 路径转换 / HDF5 checksum 损坏

v2.0 (2026-07-27): 新增动态工具路径探测 + task_plan.md Environment 段读取
  不再硬编码 ptrepack 路径 — 三级探测（which → sysconfig → pip show）

用法: python ptrepack_h5py_batch.py [--dry-run]
配置: 修改下面的 SRC_DIR / DST_DIR / COMPLEVEL
"""
import h5py, os, shutil, shlex, subprocess, sys, json, re
from pathlib import Path

# ======== 配置 ========
SRC_DIR = Path("PROJECT_DATA_DIR/cellbender_output")
DST_DIR = Path("PROJECT_DATA_DIR/seurat_h5")
COMPLEVEL = 5
DRY_RUN = "--dry-run" in sys.argv
# =====================

# ── 工具路径动态探测 ──
def find_tool(name, pip_package=None):
    """三级探测：which → sysconfig → pip show"""
    import sysconfig as _sc

    # Level 1: PATH
    path = shutil.which(name)
    if path:
        return (path, "shutil.which")

    # Level 2: Python Scripts 目录
    scripts_dir = _sc.get_path("scripts")
    for ext in ["", ".exe", ".cmd", ".bat"]:
        candidate = os.path.join(scripts_dir, name + ext)
        if os.path.exists(candidate):
            return (candidate, "sysconfig.get_path('scripts')")

    # Level 3: 从 pip package 推导
    if pip_package:
        try:
            result = subprocess.run(
                [sys.executable, "-m", "pip", "show", pip_package],
                capture_output=True, text=True, timeout=10,
            )
            for line in result.stdout.splitlines():
                if line.startswith("Location:"):
                    loc = line.split(":", 1)[1].strip()
                    parent = os.path.dirname(loc)
                    scripts_candidate = os.path.join(parent, "Scripts", name + ".exe")
                    if os.path.exists(scripts_candidate):
                        return (scripts_candidate, "pip show Location")
        except Exception:
            pass

    return (None, "not found")


def try_read_env_from_task_plan(task_plan_dir):
    """尝试从 task_plan.md 的 ## Environment 段解析工具路径"""
    for fname in ["task_plan.md", "TASK_PLAN.md"]:
        tp = Path(task_plan_dir) / fname
        if not tp.exists():
            continue
        content = tp.read_text(encoding="utf-8", errors="ignore")
        # 解析 Markdown 表格: | ptrepack | C:\... | sysconfig |
        env = {}
        in_env = False
        for line in content.splitlines():
            if line.startswith("## Environment"):
                in_env = True
                continue
            if in_env and line.startswith("##"):
                break
            if in_env and line.startswith("|") and not line.startswith("|---"):
                parts = [p.strip() for p in line.split("|") if p.strip()]
                if len(parts) >= 2:
                    env[parts[0]] = parts[1]
        return env
    return {}


# ── 探测工具路径 ──
def detect_environment():
    """探测所有工具路径，打印结果"""
    tools = {}
    for name, pkg in [("ptrepack", "tables"), ("cellbender", "cellbender")]:
        path, source = find_tool(name, pkg)
        tools[name] = {"path": path, "source": source}
        status = f"✅ {path}" if path else f"❌ NOT FOUND"
        print(f"[ENV] {name}: {status} (via {source})")

    tools["python"] = {"path": sys.executable, "source": "sys.executable"}
    print(f"[ENV] python: {sys.executable}")
    return tools


# ── 主逻辑 ──
print("=" * 60)
print("ptrepack_h5py_batch.py v2.1")
print(f"SRC: {SRC_DIR}")
print(f"DST: {DST_DIR}")
print(f"DRY_RUN: {DRY_RUN}")
print("=" * 60)

# 探测环境
env = detect_environment()
print()

# 尝试从 task_plan.md 读（如果存在）
if SRC_DIR.parent.exists():
    tp_env = try_read_env_from_task_plan(str(SRC_DIR.parent))
    if tp_env:
        print(f"[ENV] task_plan.md Environment: {tp_env}")
        # 如果探测失败但 task_plan 有，用 task_plan 的值
        for tool in ["ptrepack", "cellbender"]:
            if not env[tool]["path"] and tool in tp_env:
                env[tool]["path"] = tp_env[tool]
                env[tool]["source"] = "task_plan.md"
                print(f"[ENV] {tool}: fallback to task_plan.md → {tp_env[tool]}")
        print()

# 决定策略
ptrepack_path = env.get("ptrepack", {}).get("path")
use_h5py = True  # v2.0 默认用 h5py（已验证比 ptrepack CLI 更可靠）
if ptrepack_path and not DRY_RUN:
    # 探测到 ptrepack → 可以尝试 CLI，但 h5py 作为首选（绕过 MSYS/HDF5 checksum 损坏）
    print(f"[INFO] ptrepack found at: {ptrepack_path}")
    print(f"[INFO] Using h5py direct copy (handles MSYS path + HDF5 checksum corruption)")
else:
    print(f"[INFO] ptrepack not found or DRY_RUN — using h5py only")

print()

DST_DIR.mkdir(parents=True, exist_ok=True)

samples = sorted([d for d in os.listdir(SRC_DIR) if os.path.isdir(os.path.join(SRC_DIR, d))])

total, skipped, done, failed = 0, 0, 0, 0
for sample in samples:
    total += 1
    sample_dir = SRC_DIR / sample
    # Auto-discover filtered.h5 using glob (handles any --output naming convention)
    # Examples: cellbender_output_filtered.h5, {sample}_raw_output_filtered.h5
    filtered_files = sorted(sample_dir.glob("*_filtered.h5"))
    if not filtered_files:
        print(f"[FAIL] {sample} — 无 *_filtered.h5 文件 (检查子目录命名)")
        failed += 1
        continue
    src = filtered_files[0]  # 取第一个匹配项
    # Remove _scRNA suffix for output filename
    dst_name = sample.replace("_scRNA", "") + "_filtered_seurat.h5"
    dst = DST_DIR / dst_name

    if dst.exists() and dst.stat().st_size > 1000:
        print(f"[SKIP] {dst_name} — 已存在 ({dst.stat().st_size / 1024 / 1024:.0f} MB)")
        skipped += 1
        continue
    if not src.exists():
        print(f"[FAIL] {sample} — filtered.h5 不存在")
        failed += 1
        continue

    if DRY_RUN:
        print(f"[DRY-RUN] {src} → {dst}")
        continue

    try:
        with h5py.File(src, 'r') as f_src, h5py.File(dst, 'w') as f_dst:
            # Copy /matrix group (contains data, indices, indptr, features, barcodes, shape)
            f_src.copy('/matrix', f_dst, name='matrix')
        size_mb = dst.stat().st_size / 1024 / 1024
        print(f"[OK] {dst_name} — {size_mb:.0f} MB")
        done += 1
    except Exception as e:
        print(f"[FAIL] {sample} — {e}")
        if dst.exists():
            dst.unlink()
        failed += 1

print(f"\n=== Done: {done} | Skipped: {skipped} | Failed: {failed} | Total: {total} ===")
