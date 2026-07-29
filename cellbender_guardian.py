#!/usr/bin/env python3
"""
CellBender 监控守护 — 确保 heartbeat + error_scanner 始终存活
在 server.py 启动时自动调用，独立进程不随 server 崩溃
"""
import subprocess, sys, time, os

HEARTBEAT_SCRIPT = r"F:\CellBender_v2\heartbeat_v2.py"
ERROR_SCANNER_SCRIPT = r"F:\CellBender_v2\error_scanner.py"
CHECK_INTERVAL = 60  # 每60秒检查一次进程存活

def is_running(script_name):
    try:
        r = subprocess.run(['tasklist', '/FI', f'IMAGENAME eq python.exe'], 
                          capture_output=True, text=True)
        return script_name in r.stdout
    except:
        return False

def start_process(script_path, args):
    cmd = [sys.executable, script_path] + args
    return subprocess.Popen(cmd, creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

if __name__ == "__main__":
    print(f"[Guardian] Starting CellBender monitoring daemon...")
    
    hb_args = ["--task", "CellBender_26samples",
               "--output-dir", r"F:\CellBender_v2\cellbender_output",
               "--seurat-dir", r"F:\CellBender_v2\seurat_h5",
               "--interval", "120",
               "--output", r"F:\CellBender_v2\monitor_v2.log"]
    
    es_env = {**os.environ, 'CELLBENDER_PROJECT_DIR': r'F:\CellBender_v2', 'ERROR_SCANNER_INTERVAL': '300'}
    
    hb = None
    es = None
    
    while True:
        if not is_running("heartbeat_v2"):
            print(f"[Guardian] Heartbeat dead, restarting...")
            try: hb = start_process(HEARTBEAT_SCRIPT, hb_args)
            except Exception as e: print(f"[Guardian] Heartbeat start failed: {e}")
        
        if not is_running("error_scanner"):
            print(f"[Guardian] Error scanner dead, restarting...")
            try:
                es = subprocess.Popen([sys.executable, ERROR_SCANNER_SCRIPT],
                    env=es_env, creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except Exception as e: print(f"[Guardian] Error scanner start failed: {e}")
        
        time.sleep(CHECK_INTERVAL)
