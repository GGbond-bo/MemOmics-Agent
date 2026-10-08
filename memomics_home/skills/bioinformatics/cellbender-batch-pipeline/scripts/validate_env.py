#!/usr/bin/env python3
"""
validate_env.py — Three-stage environment validation for MemOmics

Usage:
    python validate_env.py [--env path/to/environment.json] [--fix] [--json]

Stage 1: Read cached paths from environment.json
Stage 2: Validate each path (shutil.which + os.path.exists)
Stage 3: Auto-fix broken paths (re-probe) → update environment.json

Exit codes:
    0 = all OK
    1 = some paths missing/fixed (use --json for details)
    2 = critical tool missing, unfixable
"""

import json
import os
import shutil
import sys
import sysconfig
import subprocess
from datetime import datetime
from pathlib import Path

# Tool name → (which_name, fallback_suffix, probe_functions)
TOOL_DEFS = {
    "python": {
        "which": "python",
        "fallback_fn": lambda: sys.executable,
    },
    "cellbender": {
        "which": "cellbender.exe",
        "fallback_fn": lambda: _find_scripts("cellbender.exe"),
    },
    "ptrepack": {
        "which": "ptrepack.exe",
        "fallback_fn": lambda: _find_scripts("ptrepack.exe"),
    },
    "Rscript": {
        "which": "Rscript.exe",
        "fallback_fn": lambda: _find_rscript(),
    },
    "pip": {
        "which": "pip.exe",
        "fallback_fn": lambda: _find_scripts("pip.exe"),
    },
}


def _find_scripts(name):
    """Find executable in Python Scripts directory."""
    scripts = sysconfig.get_path("scripts")
    path = os.path.join(scripts, name)
    if os.path.exists(path):
        return path
    # pip show fallback
    pkg = name.replace(".exe", "")
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pip", "show", "-f", pkg],
            capture_output=True, text=True, timeout=30
        )
        for line in result.stdout.split("\n"):
            if line.strip().endswith(name):
                return line.strip()
    except Exception:
        pass
    return None


def _find_rscript():
    """Find Rscript on Windows."""
    which = shutil.which("Rscript.exe")
    if which:
        return which
    # Common locations
    for ver in ["4.5.3", "4.5", "4.4", "4.3"]:
        for drive in ["C:", "E:"]:
            path = f"{drive}/Program Files/R/R-{ver}/bin/x64/Rscript.exe"
            if os.path.exists(path):
                return path
    return None


def validate(env_path, auto_fix=False):
    """Run three-stage validation. Returns (results, all_ok, unfixable)."""
    results = {}

    # Stage 1: Read cached paths
    cached = {}
    if os.path.exists(env_path):
        with open(env_path) as f:
            data = json.load(f)
            cached = data.get("paths", {})

    # Stage 2+3: Validate + fix
    all_ok = True
    unfixable = False

    for name, defn in TOOL_DEFS.items():
        cached_path = cached.get(name)

        # Validate cached path
        if cached_path and os.path.exists(cached_path):
            results[name] = {"status": "OK", "path": cached_path}
            continue

        # Probe from which
        found = shutil.which(defn["which"])
        if found and os.path.exists(found):
            results[name] = {"status": "FIXED" if cached_path else "PROBED", "path": found, "note": "via shutil.which"}
            cached[name] = found
            all_ok = False
            continue

        # Fallback probe
        found = defn["fallback_fn"]()
        if found and os.path.exists(found):
            results[name] = {"status": "FIXED" if cached_path else "PROBED", "path": found, "note": "via fallback"}
            cached[name] = found
            all_ok = False
            continue

        # Unfixable
        results[name] = {"status": "MISSING", "path": None}
        unfixable = True

    # Write back if auto-fix and cache changed
    if auto_fix:
        data = {
            "paths": cached,
            "last_validated": datetime.now().isoformat(),
            "validated_by": "validate_env.py (auto-fix)",
        }
        with open(env_path, "w") as f:
            json.dump(data, f, indent=2)

    return results, all_ok, unfixable


def main():
    import argparse
    parser = argparse.ArgumentParser(description="MemOmics Environment Validator")
    parser.add_argument("--env", default="environment.json", help="Path to environment.json")
    parser.add_argument("--fix", action="store_true", help="Auto-fix broken paths and update environment.json")
    parser.add_argument("--json", action="store_true", help="Output results as JSON")
    args = parser.parse_args()

    results, all_ok, unfixable = validate(args.env, auto_fix=args.fix)

    if args.json:
        print(json.dumps({"results": results, "all_ok": all_ok, "unfixable": unfixable}, indent=2))
    else:
        for name, r in results.items():
            icon = {"OK": "✅", "FIXED": "🔧", "PROBED": "🔍", "MISSING": "❌"}[r["status"]]
            print(f"  {icon} {name}: {r['path'] or 'NOT FOUND'}")

    if unfixable:
        sys.exit(2)
    elif not all_ok:
        sys.exit(1)
    else:
        sys.exit(0)


if __name__ == "__main__":
    main()
