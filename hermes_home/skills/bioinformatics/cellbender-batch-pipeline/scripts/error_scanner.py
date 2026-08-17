#!/usr/bin/env python3
"""
error_scanner.py — 独立错误扫描守护进程

职责：扫描所有 CellBender 日志，检测已知错误模式，自动修复或写 alerts.json。
与 pipeline_watchdog.py 和 heartbeat_v2.py 完全独立。

启动方式（脱离式）：
  subprocess.Popen + CREATE_NO_WINDOW

已知错误模式（2026-07-26 更新）：
  ptrepack_complevel_equals: '--complevel=5' → '--complevel 5'
  ckpt_unpack_failed: 'Failed to unpack existing tarball'
  filtered_h5_missing: exit_code=0 but no filtered.h5
  watchdog_max_retries: MAX_RETRIES reached → SKIP
  mckp_array_memory_error: _ArrayMemoryError in MCKP estimator
  torch_load_weights_only: torch.load weights_only=True incompatibility
"""
import json
import os
import re
import subprocess
import sys
import time

def _detach_kwargs():
    """P1-14(2026-08-13): 脱离式启动参数 — 平台分支（Linux/macOS 无 CREATE_NO_WINDOW）。"""
    if os.name == "nt":
        return {"creationflags": subprocess.CREATE_NO_WINDOW}
    return {"start_new_session": True}

from datetime import datetime
from glob import glob
from pathlib import Path

# === Configuration ===
PROJECT_DIR = os.environ.get("CELLBENDER_PROJECT_DIR", "PROJECT_DATA_DIR")
SCAN_INTERVAL = int(os.environ.get("ERROR_SCANNER_INTERVAL", "300"))  # 5 minutes
ALERTS_FILE = os.path.join(PROJECT_DIR, "alerts.json")

KNOWN_ERRORS = {
    "ptrepack_complevel_equals": {
        "pattern": r"--complevel=\d.*returned non-zero exit status",
        "fix": "patch watchdog.py: '--complevel=N' → '--complevel N'",
        "auto_fix": True,
        "fix_action": "patch_complevel",
    },
    "ckpt_unpack_failed": {
        "pattern": r"Failed to unpack existing tarball",
        "fix": "delete ckpt.tar.gz in failed sample dir + retry",
        "auto_fix": False,
    },
    "filtered_h5_missing": {
        "pattern": r"exit_code=0.*filtered\.h5 missing",
        "fix": "check posterior.h5 → run ptrepack directly",
        "auto_fix": True,
        "fix_action": "manual_ptrepack",
    },
    "watchdog_max_retries": {
        "pattern": r"MAX_RETRIES.*SKIP",
        "fix": "manual intervention needed — analyze sample-specific failure",
        "auto_fix": False,
    },
    "mckp_array_memory_error": {
        "pattern": r"_ArrayMemoryError.*Unable to allocate",
        "fix": "clear zombies → raise low-count-threshold to 20 → retry",
        "auto_fix": False,
    },
    "torch_load_weights_only": {
        "pattern": r"Weights only load failed|UnpicklingError.*weights_only",
        "fix": "delete ckpt.tar.gz + restart training from scratch",
        "auto_fix": True,
        "fix_action": "clear_ckpt",
    },
    "cellbender_command_not_found": {
        "pattern": r"cellbender: command not found",
        "fix": "use full path: cellbender.exe in Python312/Scripts",
        "auto_fix": True,
        "fix_action": "use_full_path",
    },
    "torch_save_weakref": {
        "pattern": r"TypeError.*weakref.*pickle|TypeError.*weakref.ReferenceType",
        "fix": "CellBender checkpoint.py needs _safe_torch_save patch",
        "auto_fix": False,
    },
    "no_cuda_available": {
        "pattern": r"CUDA.*not available|torch\.cuda\.is_available.*False",
        "fix": "check GPU drivers + CUDA toolkit installation",
        "auto_fix": False,
    },
}


def scan_all_logs():
    """Scan ALL CellBender log files, not just watchdog.log."""
    log_files = []
    
    # Primary: cellbender_output/*/cellbender_output.log
    cellbender_logs = glob(
        os.path.join(PROJECT_DIR, "cellbender_output", "*", "cellbender_output.log")
    )
    log_files.extend(cellbender_logs)
    
    # Secondary: watchdog.log
    watchdog_log = os.path.join(PROJECT_DIR, "watchdog.log")
    if os.path.exists(watchdog_log):
        log_files.append(watchdog_log)
    
    # Pipeline status
    pipeline_status = os.path.join(PROJECT_DIR, "pipeline_status.json")
    
    return sorted(log_files, key=os.path.getmtime, reverse=True)


def scan_log(log_path):
    """Scan a single log file for known error patterns."""
    try:
        with open(log_path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
    except (IOError, OSError):
        return []
    
    alerts = []
    for error_id, error_info in KNOWN_ERRORS.items():
        matches = re.findall(error_info["pattern"], content, re.IGNORECASE)
        if matches:
            mtime = datetime.fromtimestamp(os.path.getmtime(log_path))
            alerts.append({
                "error_id": error_id,
                "log_path": log_path,
                "log_mtime": mtime.isoformat(),
                "match_count": len(matches),
                "fix": error_info["fix"],
                "auto_fix": error_info["auto_fix"],
                "fix_action": error_info.get("fix_action"),
                "detected_at": datetime.now().isoformat(),
            })
    
    return alerts


def patch_complevel(alerts_file=ALERTS_FILE):
    """Auto-fix: '--complevel=N' → '--complevel N' in pipeline_watchdog.py."""
    watchdog_path = os.path.join(PROJECT_DIR, "scripts", "pipeline_watchdog.py")
    if not os.path.exists(watchdog_path):
        return False, "pipeline_watchdog.py not found"
    
    with open(watchdog_path, "r") as f:
        content = f.read()
    
    original = content
    content = re.sub(r"--complevel=(\d+)", r"--complevel \1", content)
    
    if content == original:
        return False, "no change needed"
    
    with open(watchdog_path, "w") as f:
        f.write(content)
    
    return True, "patched --complevel=X → --complevel X"


def clear_ckpt(log_path):
    """Auto-fix: delete ckpt.tar.gz from the failed sample directory."""
    sample_dir = os.path.dirname(log_path)
    ckpt_path = os.path.join(sample_dir, "ckpt.tar.gz")
    
    if os.path.exists(ckpt_path):
        os.remove(ckpt_path)
        return True, f"removed {ckpt_path}"
    return False, "no ckpt.tar.gz found"


def manual_ptrepack(log_path):
    """Auto-fix: manually run ptrepack on completed samples that lack seurat.h5."""
    sample_name = os.path.basename(os.path.dirname(log_path))
    filtered_h5 = os.path.join(PROJECT_DIR, "cellbender_output", sample_name, 
                                f"cellbender_output_filtered.h5")
    output_h5 = os.path.join(PROJECT_DIR, "seurat_h5", 
                             f"{sample_name}_filtered_seurat.h5")
    
    if not os.path.exists(filtered_h5):
        return False, f"filtered.h5 not found: {filtered_h5}"
    
    if os.path.exists(output_h5) and os.path.getsize(output_h5) > 10000000:
        return False, f"seurat.h5 already exists: {output_h5}"
    
    cmd = [
        "ptrepack",
        "--complevel", "5",
        filtered_h5,
        f"{sample_name}_filtered_seurat.h5"
    ]
    
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120,
                           cwd=os.path.join(PROJECT_DIR, "seurat_h5"))
    
    if result.returncode == 0 and os.path.exists(output_h5):
        return True, f"ptrepack success: {output_h5}"
    else:
        return False, f"ptrepack failed: {result.stderr[:200]}"


def apply_auto_fixes(alerts):
    """Apply auto-fixes for errors that have auto_fix=True."""
    results = []
    for alert in alerts:
        if not alert["auto_fix"]:
            results.append({**alert, "status": "requires_manual"})
            continue
        
        action = alert.get("fix_action")
        if action == "patch_complevel":
            success, msg = patch_complevel()
        elif action == "clear_ckpt":
            success, msg = clear_ckpt(alert["log_path"])
        elif action == "manual_ptrepack":
            success, msg = manual_ptrepack(alert["log_path"])
        else:
            success, msg = False, f"unknown fix_action: {action}"
        
        results.append({**alert, "status": "auto_fixed" if success else "fix_failed", 
                       "fix_msg": msg})
    
    return results


def write_alerts(alerts):
    """Write alerts to JSON file with deduplication."""
    # Load existing
    existing = []
    if os.path.exists(ALERTS_FILE):
        try:
            with open(ALERTS_FILE, "r") as f:
                existing = json.load(f)
        except json.JSONDecodeError:
            existing = []
    
    # Deduplicate: skip if same error_id + log_path already exists
    existing_keys = {(a["error_id"], a["log_path"]) for a in existing}
    new_alerts = [a for a in alerts if (a["error_id"], a["log_path"]) not in existing_keys]
    
    all_alerts = existing + new_alerts
    
    with open(ALERTS_FILE, "w") as f:
        json.dump(all_alerts, f, indent=2, ensure_ascii=False)
    
    return len(new_alerts)


def run_once():
    """Single scan cycle — returns alert count."""
    log_files = scan_all_logs()
    all_alerts = []
    
    for log_file in log_files:
        alerts = scan_log(log_file)
        if alerts:
            all_alerts.extend(alerts)
    
    # Apply auto-fixes
    all_alerts = apply_auto_fixes(all_alerts)
    
    # Write to disk
    new_count = write_alerts(all_alerts)
    
    print(f"[{datetime.now().isoformat()}] Scanned {len(log_files)} logs, "
          f"found {len(all_alerts)} alerts, {new_count} new")
    
    return len(all_alerts)


def run_daemon():
    """Run in daemon mode — continuously scan every SCAN_INTERVAL seconds."""
    print(f"[{datetime.now().isoformat()}] Error Scanner daemon started, "
          f"interval={SCAN_INTERVAL}s, dir={PROJECT_DIR}")
    
    cycle = 0
    while True:
        cycle += 1
        alert_count = run_once()
        elapsed = cycle * SCAN_INTERVAL
        print(f"[{datetime.now().isoformat()}] Cycle {cycle} complete, "
              f"{alert_count} active alerts, elapsed {elapsed}s")
        time.sleep(SCAN_INTERVAL)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--once":
        run_once()
    else:
        run_daemon()
