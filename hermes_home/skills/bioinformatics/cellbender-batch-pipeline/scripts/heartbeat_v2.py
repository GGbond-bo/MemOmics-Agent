#!/usr/bin/env python3
"""
heartbeat_v2.1.py — 脱离 Agent 生命周期的独立心跳监控（自动发现活跃样本）
======================================================================
设计目标：不依赖任何 shell 会话，Hermes 被回收也不死。
v2.1: 自动发现活跃样本 — 扫描 cellbender_output/*/cellbender_output.log，
      取最新修改的那个，自动跟随切换，无需硬编码路径。

用法:
  python heartbeat_v2.1.py \
    --task "CellBender_26samples" \
    --output-dir PROJECT_DATA_DIR/cellbender_output \
    --seurat-dir PROJECT_DATA_DIR/seurat_h5 \
    --interval 120 \
    --output PROJECT_DATA_DIR/monitor_v2.log

输出格式:
  [05:16:58] GPU=47%, 4987 MiB, 44°C | 4CL_SD_D4_2=epoch 70/150 | filtered.h5=3 | seurat.h5=3 | growing=True | cycle=2

改进 vs v2:
  1. 自动发现: 每轮扫描所有样本日志，自动跟随最活跃的
  2. --epochs 从日志开头 15 行提取（只在 Command 行出现一次）
  3. 独立输出文件 monitor_v2.log，避免旧心跳污染
  4. MCKP/posterior/chunk/DONE 全阶段检测
"""

import argparse
import os
import re
import subprocess
import time

def _detach_kwargs():
    """P1-14(2026-08-13): 脱离式启动参数 — 平台分支（Linux/macOS 无 CREATE_NO_WINDOW）。"""
    if os.name == "nt":
        return {"creationflags": subprocess.CREATE_NO_WINDOW}
    return {"start_new_session": True}

from datetime import datetime

MONITOR_LOG = None

def log(msg: str) -> None:
    ts = datetime.now().strftime("%H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    if MONITOR_LOG:
        try:
            with open(MONITOR_LOG, "a", encoding="utf-8") as f:
                f.write(line + "\n")
                f.flush()
        except Exception:
            pass

def get_gpu() -> tuple[str, str, str]:
    try:
        r = subprocess.run(
            ["nvidia-smi", "--query-gpu=utilization.gpu,memory.used,temperature.gpu",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=10,
            **_detach_kwargs()
        )
        if r.returncode == 0:
            parts = r.stdout.strip().split(", ")
            if len(parts) >= 3:
                return parts[0], parts[1], parts[2]
    except Exception:
        pass
    return "?", "?", "?"

def get_process_count() -> int:
    try:
        r = subprocess.run(["tasklist", "/FI", "IMAGENAME eq python.exe"],
            capture_output=True, text=True, timeout=10,
            **_detach_kwargs())
        return r.stdout.count("python.exe")
    except Exception:
        return -1

def find_active_log(output_dir: str) -> tuple[str, str, float]:
    """扫描 output_dir/*/ 下的日志文件，返回最新修改的 (sample, path, mtime)
    v2.2: 去掉1小时cutoff + 支持 *_raw_output.log 命名"""
    best_path, best_sample, best_mtime = "", "", 0.0
    if not os.path.isdir(output_dir):
        return "", "", 0.0
    try:
        for entry in os.listdir(output_dir):
            d = os.path.join(output_dir, entry)
            if not os.path.isdir(d): continue
            # 兼容两种日志命名: cellbender_output.log 和 *_raw_output.log
            for fname in os.listdir(d):
                if fname == "cellbender_output.log" or fname.endswith("_raw_output.log"):
                    lp = os.path.join(d, fname)
                    mt = os.path.getmtime(lp)
                    if mt > best_mtime:
                        best_mtime, best_path, best_sample = mt, lp, entry
    except Exception:
        pass
    return best_sample, best_path, best_mtime

def parse_log_status(log_path: str) -> tuple[int, int, str, str]:
    if not log_path or not os.path.exists(log_path):
        return -1, -1, "", ""
    try:
        with open(log_path, "r", encoding="utf-8", errors="ignore") as f:
            all_lines = f.readlines()
        lines = all_lines[-50:]
        cur_ep, tot_ep, ts, meaning = -1, -1, "", ""
        for line in all_lines[:15]:
            m = re.search(r'--epochs\s+(\d+)', line)
            if m: tot_ep = int(m.group(1)); break
        for line in lines:
            m = re.search(r'\[epoch\s+(\d+)\]', line)
            if m: cur_ep = int(m.group(1))
            m = re.search(r'(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})', line)
            if m: ts = m.group(1)
            m = re.search(r'Working on chunk \((\d+)/(\d+)\)', line)
            if m: meaning = f"chunk {m.group(1)}/{m.group(2)}"
            if 'Succeeded in writing posterior' in line: meaning = "posterior_done"
            if 'Computing target noise counts' in line: meaning = "computing_mckp"
            m = re.search(r'Saved (output.*?\.h5)', line)
            if m: meaning = m.group(1)
            if re.search(r'(Total elapsed|remove-background: Done)', line): meaning = "DONE"
            if 'Loading data from' in line: meaning = "loading_data"
        if meaning: pass
        elif cur_ep > 0 and tot_ep > 0 and cur_ep >= tot_ep: meaning = "train_done(post-MCKP)"
        elif cur_ep > 0:
            meaning = f"epoch {cur_ep}/{tot_ep}" if tot_ep > 0 else f"epoch {cur_ep}/?"
        return cur_ep, tot_ep, ts, meaning
    except Exception:
        return -1, -1, "", ""

def count_files(d: str, p: str) -> int:
    if not os.path.isdir(d): return 0
    c = 0
    try:
        for _, _, fs in os.walk(d):
            for f in fs:
                if p in f or f.endswith(p): c += 1
    except Exception: pass
    return c

def main():
    global MONITOR_LOG
    p = argparse.ArgumentParser(description="独立心跳监控 v2.1 (自动发现)")
    p.add_argument("--task", required=True)
    p.add_argument("--output-dir", required=True)
    p.add_argument("--seurat-dir", default=None)
    p.add_argument("--interval", type=int, default=120)
    p.add_argument("--output", required=True)
    a = p.parse_args()
    MONITOR_LOG = a.output
    od, sd, iv = a.output_dir, a.seurat_dir or "", a.interval
    os.makedirs(os.path.dirname(MONITOR_LOG), exist_ok=True) if os.path.dirname(MONITOR_LOG) else None
    log(f"=== heartbeat_v2.1 (auto-discover) ===")
    log(f"任务: {a.task} | 目录: {od} | Seurat: {sd or 'N/A'} | 间隔: {iv}s | PID: {os.getpid()}")
    cyc, stale, las, lls = 0, 0, "", 0
    while True:
        try:
            cyc += 1
            gu, gv, gt = get_gpu()
            py = get_process_count()
            samp, lp, _ = find_active_log(od)
            fn = count_files(od, "_filtered.h5")
            mn = count_files(od, "_metrics.csv")
            sn = count_files(sd, "_filtered_seurat.h5") if sd else 0
            _, _, _, mean = parse_log_status(lp)
            grow = False
            if lp:
                try:
                    cs = os.path.getsize(lp)
                    grow = (cs > lls and samp == las) or (samp != las)
                    lls = cs
                except Exception: pass
            if samp:
                st = f"{samp}={mean}" if mean else f"{samp}=idle"
            else:
                st = "no_active_sample"
            gl = f"GPU={gu}%, {gv} MiB"
            if gt != "?": gl += f", {gt}°C"
            log(f"{gl} | {st} | filtered.h5={fn} | metrics={mn} | seurat.h5={sn} | py={py} | growing={grow} | cycle={cyc}")
            if not grow and samp == las and mean not in ("DONE", ""):
                stale += 1
                if stale >= 3: log(f"⚠️ {stale} 轮未增长, 可能僵死 ({samp})")
            else: stale = 0
            las = samp
        except Exception as e:
            log(f"❌ heartbeat loop error: {e} — continuing")
        time.sleep(iv)

if __name__ == "__main__":
    main()
