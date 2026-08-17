#!/usr/bin/env python3
"""
Task Guardian — 通用长任务守护（原 cellbender_guardian，2026-08-13 改名通用化）

职责：确保项目的 heartbeat + error_scanner 两个监督脚本始终存活。
不限于 CellBender——任何长任务项目（CellBender/ArchR/集群管线等）都可以
通过 environment.json 的 task_guardian 段配置自己的监督脚本。

server.py 启动时自动拉起本守护（独立进程，不随 server 崩溃）。

配置（environment.json）：
{
  "task_guardian": {
    "project_dir": "PROJECT_DATA_DIR",        // 项目目录（缺省则不启动守护）
    "heartbeat_script": "heartbeat_v2.py",    // 心跳脚本文件名（可选，默认 heartbeat_v2.py）
    "scanner_script": "error_scanner.py",     // 错误扫描脚本文件名（可选，默认 error_scanner.py）
    "task_name": "CellBender_26samples",      // 传给心跳的 --task（可选）
    "check_interval": 60                      // 存活检查间隔秒（可选）
  }
}
兼容旧字段 cellbender_project_dir。

平台支持：Windows / Linux / macOS（P1-14 跨平台化）。
"""
import subprocess, sys, time, os, json

# P1-14: 优先走平台薄层（散点 os.name 判断收敛到 memomics.platform_runtime）；
# 独立部署（无 memomics 包）时降级为本地平台分支
try:
    from memomics.platform_runtime import is_windows as _is_windows
    _HAVE_PLATFORM_RUNTIME = True
except ImportError:
    _HAVE_PLATFORM_RUNTIME = False

CHECK_INTERVAL = 60  # 默认每 60 秒检查一次进程存活
IS_WINDOWS = _is_windows() if _HAVE_PLATFORM_RUNTIME else os.name == "nt"

def _config() -> dict:
    """读 environment.json 的 task_guardian 段（兼容 cellbender_project_dir）。"""
    cfg = {}
    env_json = os.path.join(os.path.dirname(os.path.abspath(__file__)), "environment.json")
    try:
        if os.path.isfile(env_json):
            with open(env_json, encoding="utf-8") as f:
                data = json.load(f)
            tg = data.get("task_guardian") or {}
            if isinstance(tg, dict):
                cfg = dict(tg)
            # 兼容旧字段
            if not cfg.get("project_dir"):
                cfg["project_dir"] = data.get("cellbender_project_dir", "")
    except Exception:
        pass
    if not cfg.get("project_dir"):
        cfg["project_dir"] = os.environ.get("TASK_GUARDIAN_PROJECT_DIR", "")
    return cfg

def _scripts(proj: str, cfg: dict):
    hb_name = cfg.get("heartbeat_script", "heartbeat_v2.py")
    es_name = cfg.get("scanner_script", "error_scanner.py")
    hb = os.path.join(proj, hb_name)
    es = os.path.join(proj, es_name)
    return (hb if os.path.isfile(hb) else ""), (es if os.path.isfile(es) else "")

def is_running(script_name: str) -> bool:
    """进程存活探测 — 平台分支。"""
    try:
        if IS_WINDOWS:
            r = subprocess.run(['tasklist', '/FI', 'IMAGENAME eq python.exe'],
                               capture_output=True, text=True, errors="replace")
            return script_name in r.stdout
        r = subprocess.run(['ps', '-ef'], capture_output=True, text=True, errors="replace")
        return script_name in r.stdout
    except Exception:
        return False

def _detach_kwargs() -> dict:
    """脱离式启动参数 — 平台分支（优先走平台薄层）。"""
    if _HAVE_PLATFORM_RUNTIME:
        from memomics.platform_runtime import detach_options
        return detach_options()
    if IS_WINDOWS:
        return {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
    return {"start_new_session": True}

def start_process(script_path, args):
    cmd = [sys.executable, script_path] + args
    return subprocess.Popen(cmd, **_detach_kwargs(),
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

if __name__ == "__main__":
    cfg = _config()
    proj = cfg.get("project_dir", "")
    if not proj or not os.path.isdir(proj):
        print("[TaskGuardian] task_guardian.project_dir 未配置（environment.json）或目录不存在 — 守护不启动")
        sys.exit(0)

    hb_script, es_script = _scripts(proj, cfg)
    task_name = cfg.get("task_name", "default_task")
    interval = int(cfg.get("check_interval", CHECK_INTERVAL) or CHECK_INTERVAL)

    print(f"[TaskGuardian] project_dir={proj} (platform={'windows' if IS_WINDOWS else 'posix'})")
    print(f"[TaskGuardian] heartbeat: {'OK' if hb_script else 'MISSING'} | scanner: {'OK' if es_script else 'MISSING'} | interval={interval}s")

    hb_args = ["--task", task_name,
               "--output-dir", os.path.join(proj, "cellbender_output"),
               "--seurat-dir", os.path.join(proj, "seurat_h5"),
               "--interval", "120",
               "--output", os.path.join(proj, "monitor_v2.log")]

    es_env = {**os.environ, 'CELLBENDER_PROJECT_DIR': proj, 'ERROR_SCANNER_INTERVAL': '300'}

    hb = None
    es = None

    while True:
        if hb_script and not is_running(os.path.basename(hb_script).replace(".py", "")):
            print(f"[TaskGuardian] Heartbeat dead, restarting...")
            try: hb = start_process(hb_script, hb_args)
            except Exception as e: print(f"[TaskGuardian] Heartbeat start failed: {e}")

        if es_script and not is_running(os.path.basename(es_script).replace(".py", "")):
            print(f"[TaskGuardian] Error scanner dead, restarting...")
            try:
                es = subprocess.Popen([sys.executable, es_script],
                    env=es_env, **_detach_kwargs(),
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except Exception as e: print(f"[TaskGuardian] Error scanner start failed: {e}")

        time.sleep(interval)
