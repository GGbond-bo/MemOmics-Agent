# Heartbeat Monitor — 长任务心跳监控脚本
"""
独立后台进程，不依赖 Agent 线程。即使 Agent 阻塞/压缩/重启，心跳也持续记录。

用法:
  python heartbeat.py --task "CellBender pipeline" --dir "F:/CellBender_v2" --interval 120

输出:
  monitor.log — 每 N 秒追加一行 JSON，Agent 可随时读取汇报进度
"""

import argparse, json, os, sys, time, subprocess, glob
from datetime import datetime

def get_gpu_info():
    """获取 GPU 使用率和显存"""
    try:
        r = subprocess.run(["nvidia-smi", "--query-gpu=utilization.gpu,memory.used,memory.total,temperature.gpu",
                            "--format=csv,noheader,nounits"], capture_output=True, text=True, timeout=10)
        parts = [p.strip() for p in r.stdout.strip().split(",")]
        return {"gpu_util": parts[0] if len(parts)>0 else "?",
                "vram_used": parts[1] if len(parts)>1 else "?",
                "vram_total": parts[2] if len(parts)>2 else "?",
                "temp": parts[3] if len(parts)>3 else "?"}
    except Exception:
        return None

def count_output_files(directory, pattern="*.h5"):
    """统计输出目录中的产出文件"""
    try:
        files = glob.glob(os.path.join(directory, "**", pattern), recursive=True)
        return len(files)
    except Exception:
        return -1

def read_tail(filepath, lines=3):
    """读取文件最后几行"""
    try:
        if not os.path.exists(filepath): return ""
        with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
            all_lines = f.readlines()
        return "".join(all_lines[-lines:]).strip()
    except Exception:
        return ""

def get_pipeline_epoch(log_path):
    """从 pipeline 日志中提取 epoch 进度（CellBender 等训练任务）"""
    tail = read_tail(log_path, 5)
    if not tail:
        return None
    import re
    # CellBender: "Epoch XXX/YYY"
    m = re.search(r"Epoch\s+(\d+)/(\d+)", tail)
    if m: return f"{m.group(1)}/{m.group(2)}"
    # 通用进度: "Progress: XX%"
    m = re.search(r"Progress:\s*(\d+\.?\d*)%", tail)
    if m: return f"{m.group(1)}%"
    # "Processing sample X/26"
    m = re.search(r"(?:Processing|Sample)\s+(\d+)/(\d+)", tail)
    if m: return f"{m.group(1)}/{m.group(2)}"
    return None

def main():
    parser = argparse.ArgumentParser(description="MemOmics heartbeat monitor")
    parser.add_argument("--task", required=True, help="Task name for logging")
    parser.add_argument("--dir", required=True, help="Output directory to monitor")
    parser.add_argument("--interval", type=int, default=120, help="Check interval in seconds")
    parser.add_argument("--log", default="pipeline.log", help="Pipeline log filename (in --dir)")
    parser.add_argument("--pattern", default="*.h5", help="Output file pattern to count")
    parser.add_argument("--gpu", action="store_true", default=True, help="Monitor GPU")
    parser.add_argument("--pid", type=int, default=0, help="Main process PID to monitor")
    args = parser.parse_args()

    monitor_path = os.path.join(args.dir, "monitor.log")
    log_path = os.path.join(args.dir, args.log)
    started = datetime.now()

    print(f"[heartbeat] Task: {args.task}")
    print(f"[heartbeat] Monitor dir: {args.dir}")
    print(f"[heartbeat] Interval: {args.interval}s")
    print(f"[heartbeat] Log: {monitor_path}")

    iteration = 0
    while True:
        iteration += 1
        now = datetime.now()
        elapsed = (now - started).total_seconds()

        entry = {
            "ts": now.strftime("%Y-%m-%d %H:%M:%S"),
            "task": args.task,
            "iteration": iteration,
            "elapsed_min": round(elapsed / 60, 1),
        }

        # GPU
        if args.gpu:
            gpu = get_gpu_info()
            if gpu: entry["gpu"] = gpu

        # 产出文件数
        n_files = count_output_files(args.dir, args.pattern)
        entry["output_files"] = n_files

        # Pipeline 进度
        epoch = get_pipeline_epoch(log_path)
        if epoch: entry["epoch"] = epoch

        # 进程存活
        if args.pid > 0:
            try: os.kill(args.pid, 0); entry["process_alive"] = True
            except OSError: entry["process_alive"] = False

        # 写入 monitor.log
        try:
            with open(monitor_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except Exception as e:
            print(f"[heartbeat] Write error: {e}", flush=True)

        time.sleep(args.interval)

if __name__ == "__main__":
    main()
