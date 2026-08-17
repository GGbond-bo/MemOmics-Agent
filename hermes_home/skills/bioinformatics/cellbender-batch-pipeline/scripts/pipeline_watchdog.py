#!/usr/bin/env python3
"""
Pipeline Watchdog — self-healing CellBender batch orchestrator.
Detached from Hermes lifecycle; survives context compression and session recycling.

Features:
- Auto-discovers completed samples by scanning filtered.h5 files
- Detects running CellBender via GPU > 15% (prevent double-launch)
- Auto ptrepack after each sample (--complevel 5, space-separated!)
- MAX_RETRIES=2 per sample, permanent skip after
- Writes watchdog.log for audit trail

Usage:
    python pipeline_watchdog.py
    
    Detached launch (no terminal dependency):
    start /B python pipeline_watchdog.py
"""

import os, sys, time, json, glob, subprocess, shutil
from datetime import datetime

# === CONFIG ===
BASE_DIR = r"PROJECT_DATA_DIR"
H5AD_DIR = os.path.join(BASE_DIR, "h5ad")
OUTPUT_DIR = os.path.join(BASE_DIR, "cellbender_output")
SEURAT_DIR = os.path.join(BASE_DIR, "seurat_h5")
LOG_FILE = os.path.join(BASE_DIR, "watchdog.log")
STATUS_FILE = os.path.join(BASE_DIR, "pipeline_status.json")

CELLBENDER_PARAMS = {
    "--fpr": "0.01",
    "--epochs": "150",
    "--learning-rate": "1e-4",
    "--total-droplets-included": "25000",
    "--expected-cells": "5000",
    "--low-count-threshold": "5",
    "--cuda": "",
}

MAX_RETRIES = 2
GPU_IDLE_THRESHOLD = 15  # % — below this, consider GPU idle

# Path to cellbender.exe
CELLBENDER_EXE = os.path.join(
    os.path.expanduser("~"),
    "AppData", "Local", "Programs", "Python", "Python312", "Scripts", "cellbender.exe"
)
PTREPACK_EXE = "ptrepack"  # must be in PATH (Python312\Scripts)

# === LOGGING ===
def log(msg: str):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")

# === DISCOVERY ===
def get_all_samples() -> list[str]:
    """Return sorted list of sample names (without _scRNA suffix, without .h5ad)."""
    samples = []
    for f in glob.glob(os.path.join(H5AD_DIR, "*.h5ad")):
        name = os.path.basename(f).replace(".h5ad", "")
        if name.endswith("_scRNA"):
            name = name[:-6]
        samples.append(name)
    return sorted(samples)

def get_completed_samples() -> set[str]:
    """Samples that already have filtered.h5 output."""
    completed = set()
    for d in glob.glob(os.path.join(OUTPUT_DIR, "*")):
        if os.path.isdir(d):
            filtered_files = glob.glob(os.path.join(d, "*_filtered.h5"))
            if filtered_files:
                sample = os.path.basename(d)
                completed.add(sample)
    return completed

def get_seurat_samples() -> set[str]:
    """Samples that already have seurat.h5 (ptrepack done)."""
    done = set()
    for f in glob.glob(os.path.join(SEURAT_DIR, "*_filtered_seurat.h5")):
        name = os.path.basename(f).replace("_filtered_seurat.h5", "")
        if name.endswith("_scRNA"):
            name = name[:-6]
        done.add(name)
    return done

def get_active_cellbender_log() -> str | None:
    """Find the most recently modified cellbender_output.log — the active sample."""
    logs = glob.glob(os.path.join(OUTPUT_DIR, "*", "cellbender_output.log"))
    if not logs:
        return None
    return max(logs, key=os.path.getmtime)

def read_log_tail(path: str, lines: int = 5) -> str:
    """Read last N lines of a file."""
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            all_lines = f.readlines()
            return "".join(all_lines[-lines:]).strip()
    except Exception:
        return ""

# === GPU CHECK ===
def get_gpu_util() -> float:
    """Get GPU utilization %. Returns -1 on failure."""
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=utilization.gpu", "--format=csv,noheader"],
            capture_output=True, text=True, timeout=10
        )
        return float(result.stdout.strip().replace(" %", "").replace("%", ""))
    except Exception:
        return -1

def is_cellbender_running() -> bool:
    """Check if CellBender process is alive + GPU is active."""
    gpu = get_gpu_util()
    if gpu > GPU_IDLE_THRESHOLD:
        return True
    
    # Fallback: check for cellbender process via tasklist
    try:
        result = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq python.exe", "/FO", "CSV", "/NH"],
            capture_output=True, text=True, timeout=10
        )
        # Check if any python process has > 3GB memory (CellBender signature)
        for line in result.stdout.strip().split("\n"):
            if "python.exe" in line.lower():
                parts = line.replace('"', '').split(",")
                if len(parts) >= 5:
                    mem_str = parts[4].strip().replace(" K", "").replace(",", "")
                    try:
                        mem_kb = int(mem_str)
                        if mem_kb > 3_000_000:  # > 3 GB
                            return True
                    except ValueError:
                        pass
    except Exception:
        pass
    return False

# === CELLBENDER EXECUTION ===
def run_cellbender(sample: str) -> bool:
    """Run CellBender for one sample. Returns True if filtered.h5 produced."""
    h5ad_path = os.path.join(H5AD_DIR, f"{sample}_scRNA.h5ad")
    if not os.path.exists(h5ad_path):
        # Try without _scRNA
        h5ad_path = os.path.join(H5AD_DIR, f"{sample}.h5ad")
    if not os.path.exists(h5ad_path):
        log(f"❌ h5ad not found: {sample}")
        return False
    
    out_dir = os.path.join(OUTPUT_DIR, sample)
    os.makedirs(out_dir, exist_ok=True)
    out_h5 = os.path.join(out_dir, "cellbender_output.h5")
    filtered_h5 = os.path.join(out_dir, "cellbender_output_filtered.h5")
    
    # Skip if already done
    if os.path.exists(filtered_h5) and os.path.getsize(filtered_h5) > 10_000_000:
        log(f"⏭️ {sample} already completed, skipping")
        return True
    
    # Clean checkpoint
    ckpt = os.path.join(out_dir, "ckpt.tar.gz")
    if os.path.exists(ckpt):
        os.remove(ckpt)
    
    cmd = [
        CELLBENDER_EXE, "remove-background",
        "--input", h5ad_path,
        "--output", out_h5,
    ]
    for k, v in CELLBENDER_PARAMS.items():
        cmd.append(k)
        if v:
            cmd.append(v)
    
    log(f"🚀 [{sample}] Starting CellBender...")
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    env["TMPDIR"] = "E:/tmp"
    
    try:
        result = subprocess.run(
            cmd,
            env=env,
            timeout=3600,  # 60 min max
            capture_output=False,  # Let stdout go to cellbender_output.log via shell redirect
        )
    except subprocess.TimeoutExpired:
        log(f"⏱️ [{sample}] Timeout (60 min)")
        return False
    
    # Verify output
    if os.path.exists(filtered_h5) and os.path.getsize(filtered_h5) > 10_000_000:
        log(f"✅ [{sample}] CellBender done — {os.path.getsize(filtered_h5)//1024//1024} MB")
        return True
    else:
        log(f"❌ [{sample}] CellBender finished but no filtered.h5")
        return False

def run_ptrepack(sample: str) -> bool:
    """Run ptrepack for one sample. Returns True on success."""
    filtered_h5 = os.path.join(OUTPUT_DIR, sample, "cellbender_output_filtered.h5")
    seurat_h5 = os.path.join(SEURAT_DIR, f"{sample}_scRNA_filtered_seurat.h5")
    
    os.makedirs(SEURAT_DIR, exist_ok=True)
    
    if os.path.exists(seurat_h5) and os.path.getsize(seurat_h5) > 10_000_000:
        log(f"⏭️ [{sample}] ptrepack already done")
        return True
    
    if not os.path.exists(filtered_h5):
        log(f"❌ [{sample}] No filtered.h5 to ptrepack")
        return False
    
    # NOTE: --complevel 5 (space, NOT equals!)
    cmd = [PTREPACK_EXE, "--complevel", "5", filtered_h5, seurat_h5]
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        if result.returncode == 0 and os.path.exists(seurat_h5):
            log(f"✅ [{sample}] ptrepack done — {os.path.getsize(seurat_h5)//1024//1024} MB")
            return True
        else:
            log(f"❌ [{sample}] ptrepack failed: {result.stderr[:200]}")
            return False
    except Exception as e:
        log(f"❌ [{sample}] ptrepack exception: {e}")
        return False

# === MAIN WATCHDOG LOOP ===
def main():
    log("=" * 60)
    log("🛡️ Pipeline Watchdog started")
    
    # Load retry state
    retries = {}
    if os.path.exists(STATUS_FILE):
        with open(STATUS_FILE) as f:
            state = json.load(f)
            retries = state.get("retries", {})
    
    all_samples = get_all_samples()
    log(f"Found {len(all_samples)} total samples")
    
    while True:
        completed = get_completed_samples()
        seurat_done = get_seurat_samples()
        pending = [s for s in all_samples if s not in completed]
        need_ptrepack = [s for s in completed if s not in seurat_done]
        
        log(f"📊 filtered={len(completed)}/{len(all_samples)} | seurat={len(seurat_done)} | pending={len(pending)}")
        
        # If all done, exit
        if not pending and not need_ptrepack:
            log("🎉 ALL DONE! All samples have filtered.h5 + seurat.h5")
            status = {"retries": retries, "completed": list(completed), "status": "done"}
            with open(STATUS_FILE, "w") as f:
                json.dump(status, f, indent=2)
            break
        
        # Do ptrepack for completed samples missing seurat.h5
        for sample in need_ptrepack[:3]:  # batch at most 3
            log(f"📦 [{sample}] Running ptrepack (missing seurat.h5)...")
            run_ptrepack(sample)
        
        # If no pending samples, wait for ptrepack to finish, then loop
        if not pending:
            time.sleep(60)
            continue
        
        # Check if CellBender is running
        if is_cellbender_running():
            active_log = get_active_cellbender_log()
            if active_log:
                sample = os.path.basename(os.path.dirname(active_log))
                tail = read_log_tail(active_log, 3)
                log(f"⏳ [{sample}] CellBender running (GPU={get_gpu_util()}%). Latest: {tail[:100]}")
            else:
                log(f"⏳ CellBender running but no log found (GPU={get_gpu_util()}%)")
            time.sleep(120)
            continue
        
        # GPU idle, launch next sample
        sample = pending[0]
        retry_count = retries.get(sample, 0)
        
        if retry_count >= MAX_RETRIES:
            log(f"🚫 [{sample}] Permanently skipped (retries={retry_count})")
            # Mark as "completed" to avoid blocking pipeline
            # Create a placeholder so it's not picked up again
            placeholder = os.path.join(OUTPUT_DIR, sample, ".permanently_skipped")
            os.makedirs(os.path.dirname(placeholder), exist_ok=True)
            with open(placeholder, "w") as f:
                f.write(f"skipped after {retry_count} retries")
            continue
        
        if retry_count > 0:
            log(f"🔄 [{sample}] Retry {retry_count}/{MAX_RETRIES}")
        
        success = run_cellbender(sample)
        
        if success:
            # Auto ptrepack
            run_ptrepack(sample)
            retries[sample] = 0  # reset on success
        else:
            retries[sample] = retry_count + 1
            log(f"⚠️ [{sample}] Failed (retry {retries[sample]}/{MAX_RETRIES})")
        
        # Save retry state
        status = {"retries": retries, "completed": list(get_completed_samples()), "status": "running"}
        with open(STATUS_FILE, "w") as f:
            json.dump(status, f, indent=2)
        
        time.sleep(10)  # brief pause between samples

if __name__ == "__main__":
    main()
