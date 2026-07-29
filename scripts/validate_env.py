#!/usr/bin/env python3
"""
MemOmics 全局环境验证器
读取 E:/MemOmics-Agent/environment.json → 验证每个路径 → MISSING时自动重新探测 → 更新JSON
exit 0: 全部OK
exit 1: 有缺失但已自动修复
exit 2: 有关键缺失无法修复
用法: python validate_env.py [--verbose] [--dry-run]
"""

import json, os, sys, shutil, subprocess
from pathlib import Path

ENV_FILE = Path("E:/MemOmics-Agent/environment.json")

def check_exists(path_str):
    """检查文件/目录是否存在"""
    if not path_str:
        return False
    p = Path(path_str)
    return p.exists()

def find_r_installations():
    """自动探测所有R安装"""
    results = {}
    r_base = Path("C:/Program Files/R")
    if r_base.exists():
        for d in r_base.iterdir():
            if d.is_dir() and d.name.startswith("R-"):
                rscript = d / "bin/x64/Rscript.exe"
                if rscript.exists():
                    results[d.name] = str(rscript)
    return results

def find_cellbender():
    """多级回退查找cellbender"""
    # 1. shutil.which
    cb = shutil.which("cellbender")
    if cb:
        return cb
    # 2. 已知位置
    known = Path("C:/Users/23136/AppData/Local/Programs/Python/Python312/Scripts/cellbender.exe")
    if known.exists():
        return str(known)
    # 3. pip show
    try:
        result = subprocess.run(["pip", "show", "cellbender"], capture_output=True, text=True, timeout=10)
        for line in result.stdout.split("\n"):
            if line.startswith("Location:"):
                loc = line.split(":", 1)[1].strip()
                cb_path = Path(loc) / "cellbender" / "__init__.py"
                if cb_path.exists():
                    # Find the script
                    scripts_dir = Path(loc).parent / "Scripts" / "cellbender.exe"
                    if scripts_dir.exists():
                        return str(scripts_dir)
    except:
        pass
    return None

def find_ptrepack():
    """多级回退查找ptrepack"""
    cb = shutil.which("ptrepack")
    if cb:
        return cb
    known = Path("C:/Users/23136/AppData/Local/Programs/Python/Python312/Scripts/ptrepack.exe")
    if known.exists():
        return str(known)
    return None

def validate_and_fix(env_data, verbose=False, dry_run=False):
    """验证environment.json，修复缺失路径"""
    changes = []
    all_ok = True
    critical_missing = False

    # --- 验证 R ---
    r_section = env_data.get("paths", {}).get("r", {})
    for r_ver, r_info in list(r_section.items()):
        if r_ver == "default":
            continue
        bin_path = r_info.get("bin", "")
        if not check_exists(bin_path):
            if verbose:
                print(f"[MISSING] R {r_ver}: {bin_path}")
            # 尝试自动探测
            found = find_r_installations()
            if r_ver in found:
                if verbose:
                    print(f"  → 修复: {found[r_ver]}")
                changes.append(f"R {r_ver}: {bin_path} → {found[r_ver]}")
                r_info["bin"] = found[r_ver]
            else:
                all_ok = False
                changes.append(f"R {r_ver}: NOT FOUND, cannot auto-fix")

    # 验证 default R
    default_r = r_section.get("default", "")
    if not check_exists(default_r):
        found = find_r_installations()
        if found:
            newest = sorted(found.keys(), reverse=True)[0]
            new_default = found[newest]
            if verbose:
                print(f"[MISSING] default R: {default_r}")
                print(f"  → 修复: {new_default}")
            changes.append(f"default R: {default_r} → {new_default}")
            env_data["paths"]["r"]["default"] = new_default
        else:
            critical_missing = True
            changes.append("default R: NOT FOUND — CRITICAL")

    # --- 验证 Python ---
    py_section = env_data.get("paths", {}).get("python", {})
    for py_key, py_path in list(py_section.items()):
        if not check_exists(py_path):
            if verbose:
                print(f"[MISSING] Python {py_key}: {py_path}")
            all_ok = False
            changes.append(f"Python {py_key}: NOT FOUND")

    # --- 验证 CLI tools ---
    cli = env_data.get("paths", {}).get("cli_tools", {})
    
    # cellbender
    cb_path = cli.get("cellbender", {}).get("exe", "")
    if not check_exists(cb_path):
        if verbose:
            print(f"[MISSING] cellbender: {cb_path}")
        found = find_cellbender()
        if found:
            changes.append(f"cellbender: {cb_path} → {found}")
            cli["cellbender"]["exe"] = found
        else:
            all_ok = False
            critical_missing = True
            changes.append("cellbender: NOT FOUND — CRITICAL")

    # ptrepack
    ptr_path = cli.get("ptrepack", {}).get("exe", "")
    if not check_exists(ptr_path):
        if verbose:
            print(f"[MISSING] ptrepack: {ptr_path}")
        found = find_ptrepack()
        if found:
            changes.append(f"ptrepack: {ptr_path} → {found}")
            cli["ptrepack"]["exe"] = found
        else:
            all_ok = False
            changes.append("ptrepack: NOT FOUND")

    # --- 写入修复后的JSON ---
    if changes and not dry_run:
        env_data["_last_updated"] = subprocess.run(["date", "+%Y-%m-%dT%H:%M:%S"], 
                                                     capture_output=True, text=True).stdout.strip()
        with open(ENV_FILE, 'w', encoding='utf-8') as f:
            json.dump(env_data, f, indent=2, ensure_ascii=False)

    return all_ok, critical_missing, changes

def main():
    verbose = "--verbose" in sys.argv
    dry_run = "--dry-run" in sys.argv

    if not ENV_FILE.exists():
        print(f"[FATAL] environment.json not found at {ENV_FILE}")
        print("  Run environment discovery: python scripts/discover_env.py")
        sys.exit(2)

    with open(ENV_FILE, 'r', encoding='utf-8') as f:
        env_data = json.load(f)

    all_ok, critical_missing, changes = validate_and_fix(env_data, verbose=verbose, dry_run=dry_run)

    if dry_run:
        print(f"[DRY-RUN] Would fix {len(changes)} issues: {changes}")
    elif changes:
        print(f"[FIXED] {len(changes)} issues:")
        for c in changes:
            print(f"  • {c}")
    else:
        print(f"[OK] All paths verified")

    if critical_missing:
        print("[FATAL] Critical tools missing — install required")
        sys.exit(2)
    elif not all_ok:
        print("[WARN] Some non-critical paths missing")
        sys.exit(1)
    else:
        sys.exit(0)

if __name__ == "__main__":
    main()
