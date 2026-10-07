#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""MemOmics WebUI 重启 / 回滚 runbook（2026-10-01 memomics-afd2d418 实测可用）。

用途：改了仓库代码后，运行中的 WebUI 服务仍加载旧代码 → 需要一次「安全重启 + 生效性验证」。
设计三条：① 默认只读演练（不打 --execute 什么都不动）② --execute 需令牌 --confirm ③ 失败打印日志尾部提示回滚。

用法：
    # 1) 演练（安全，任何时候可跑）：打印探测结果 + 动作序列 + 健康检查
    .venv\\Scripts\\python.exe scripts/restart_service_runbook.py
    # 2) 用户授权后真正重启
    ... scripts/restart_service_runbook.py --execute --confirm RESTART-8899

退出码：0=成功/演练通过；1=失败（未执行 或 已尝试回滚）

⚠️ 调用前先读 references/service-restart-and-deploy-verification.md —— 顺序硬性：
   只读预检 → runbook dry-run → ask_user 拿一次性授权 → 才 --execute。
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import subprocess
import sys
import time
import urllib.request

ROOT = r"E:/MemOmics-Agent"
PORT = 8899
ENGINE = os.path.join(ROOT, "memomics", "bio_tools", "skill_evolution.py")
SMOKE = os.path.join(ROOT, "results", "memomics-afd2d418", "scripts", "smoke_engine_after_restart.py")
LOGDIR = os.path.join(ROOT, "results", "memomics-afd2d418", "log")
TOKEN = "RESTART-8899"


def ts() -> str:
    return dt.datetime.now().strftime("%H:%M:%S")


def log(msg: str) -> None:
    print(f"[{ts()}] {msg}", flush=True)


def discover(include_helpers: bool = True):
    """按 cmdline + 监听端口定位服务进程树。返回 (servers, helpers, listeners).

    ★ 关键：真实服务 = 监听端口的那个进程。同 cmdline 的另一个（包装壳，1 线程/无端口）
      必须与 servers 分开，否则 stop 数错、mtime 对比做两遍。
    """
    import psutil
    servers, helpers, listeners = [], [], {}
    for c in psutil.net_connections(kind="inet"):
        if c.status == psutil.CONN_LISTEN and c.laddr.port == PORT:
            listeners[c.pid] = f"{c.laddr.ip}:{c.laddr.port}"
    for pr in psutil.process_iter(["pid", "name", "cmdline", "create_time"]):
        cl = " ".join(pr.info.get("cmdline") or [])
        if "server.py" not in cl or "webui" not in cl:
            continue
        pid = pr.info["pid"]
        rec = {"pid": pid, "name": pr.info["name"], "started": pr.info["create_time"],
               "listening": listeners.get(pid), "cmdline": cl}
        (servers if listeners.get(pid) else (helpers if include_helpers else [])).append(rec)
    return servers, helpers, listeners


def health(timeout: float = 5.0):
    url = f"http://127.0.0.1:{PORT}/"
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return (r.status == 200), f"HTTP {r.status}"
    except Exception as e:  # noqa: BLE001
        return False, f"{type(e).__name__}: {e}"


def engine_mtime() -> float:
    return os.stat(ENGINE).st_mtime if os.path.exists(ENGINE) else 0.0


def preview():
    """演练：全部只读。"""
    ok = True
    eng = engine_mtime()
    log(f"引擎文件 mtime = {dt.datetime.fromtimestamp(eng):%Y-%m-%d %H:%M:%S}  ({os.path.getsize(ENGINE)} B)")
    servers, helpers, _ = discover()
    if not servers:
        log("⚠️ 未发现监听 %d 的服务进程 —— 服务可能未运行" % PORT)
        ok = False
    for s in servers:
        flag = "晚于引擎 ✅ 无需重启" if s["started"] > eng else "早于引擎 ⚠️ 需重启"
        log(f"服务   PID {s['pid']:<6} {s['name']:<12} 监听 {s['listening']}  "
            f"启动 {dt.datetime.fromtimestamp(s['started']):%m-%d %H:%M:%S}  {flag}")
    for h in helpers:
        log(f"包装壳 PID {h['pid']:<6} {h['name']:<12} 无端口（父壳，随服务树一起停）")
    h_ok, h_msg = health()
    log(f"健康检查 GET http://127.0.0.1:{PORT}/ → {'OK' if h_ok else 'FAIL'}  ({h_msg})")
    log("-" * 68)
    log("【将执行的动作序列（execute 模式）】")
    log(f"  1. 停止：先优雅 taskkill /PID <服务PID>（整棵树 /T），等 8s；未退再 /F")
    log(f"  2. 确认端口 {PORT} 释放（轮询 ≤30s；仍占用则放弃、不改动）")
    log(f"  3. 启动：{os.path.join(ROOT, '.venv/Scripts/python.exe')} webui/server.py（detached，日志 → log/server-runbook-<日期>.log）")
    log(f"           env: HERMES_HOME / PYTHONPATH / MEMOMICS_PORT={PORT} / MEMOMICS_RUN_GATE=1 / PYTHONUTF8=1")
    log("  4. 健康检查：轮询 ≤90s 直到 HTTP 200")
    log(f"  5. 生效性验证：跑 {os.path.basename(SMOKE)} → 期望 [4] 打印「晚于引擎 ✅ 已装载新代码」")
    log("  6. 回滚：健康检查失败 → 打印日志尾部 + 提示手动运行 start.bat")
    log("-" * 68)
    log(f"演练结论：{'通过 —— 可执行 --execute --confirm %s' % TOKEN if ok else '不通过（见上）'}")
    return 0 if ok else 1


def execute():
    import psutil
    servers, helpers, _ = discover()
    if not servers:
        log("没有正在运行的服务 → 直接进入启动步骤")
    eng = engine_mtime()
    if servers and all(s["started"] > eng for s in servers):
        log("所有服务启动时间均晚于引擎文件 → 无需重启，退出")
        return 0

    # --- 1/2 停止（先服务、后壳） ---
    for s in servers:
        log(f"停止服务树 PID {s['pid']} …")
        subprocess.run(["taskkill", "/PID", str(s["pid"]), "/T"], capture_output=True)
    for h in helpers:
        if not psutil.pid_exists(h["pid"]):
            continue
        subprocess.run(["taskkill", "/PID", str(h["pid"]), "/T"], capture_output=True)
    t0 = time.time()
    while time.time() - t0 < 30:
        _, _, listeners = discover()
        if not listeners:
            break
        time.sleep(1)
        if time.time() - t0 > 8:
            for pid in list(listeners):
                log(f"仍未退出 → taskkill /F /T /PID {pid}")
                subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)], capture_output=True)
            listeners = {}
            break
    if discover()[2]:
        log("端口未释放，放弃重启（不改动）")
        return 1
    log(f"端口 {PORT} 已释放（{time.time() - t0:.1f}s）")

    # --- 3 启动 ---
    os.makedirs(LOGDIR, exist_ok=True)
    logf = os.path.join(LOGDIR, f"server-runbook-{dt.datetime.now():%Y%m%d_%H%M%S}.log")
    py = os.path.join(ROOT, ".venv", "Scripts", "python.exe")
    if not os.path.exists(py):
        log(f"未找到 {py}")
        return 1
    env = dict(os.environ)
    env.update({"HERMES_HOME": os.path.join(ROOT, "hermes_home"),
                "PYTHONPATH": os.pathsep.join([ROOT, os.path.join(ROOT, "hermes-agent")]),
                "MEMOMICS_PORT": str(PORT), "MEMOMICS_RUN_GATE": "1", "PYTHONUTF8": "1"})
    log(f"启动 {py} webui/server.py（日志 → {logf}）")
    with open(logf, "ab") as fh:
        subprocess.Popen([py, os.path.join("webui", "server.py")], cwd=ROOT, env=env,
                         stdout=fh, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                         creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
                         | getattr(subprocess, "DETACHED_PROCESS", 0))

    # --- 4 健康检查 ---
    ok = False
    t0 = time.time()
    while time.time() - t0 < 90:
        h_ok, _ = health()
        if h_ok:
            ok = True
            break
        time.sleep(3)
    if not ok:
        log("90s 内健康检查未通过 → 回滚：打印日志尾部")
        try:
            tail = open(logf, encoding="utf-8", errors="replace").read().splitlines()[-25:]
            for L in tail:
                log("   | " + L)
        except Exception as e:  # noqa: BLE001
            log(f"   读日志失败 {e}")
        log("   请手动运行 start.bat 恢复服务")
        return 1
    log(f"✅ 健康检查通过（{time.time() - t0:.1f}s）")

    # --- 5 生效性验证 ---
    if os.path.exists(SMOKE):
        log("跑 smoke 生效性验证 …")
        r = subprocess.run([py, SMOKE], capture_output=True, text=True, cwd=ROOT, timeout=300)
        for L in (r.stdout or "").splitlines():
            log("   | " + L)
        if "晚于引擎 ✅" in (r.stdout or ""):
            log("✅ 改动已装载（服务进程晚于引擎文件）")
        else:
            log("⚠️ smoke 未显示「晚于引擎 ✅」，请人工确认")
    rep = {"when": dt.datetime.now().isoformat(), "engine_mtime": eng, "log": logf,
           "health_ok": ok, "servers": discover()[0]}
    json.dump(rep, open(os.path.join(LOGDIR, "last_restart_report.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="MemOmics WebUI 重启/回滚 runbook")
    ap.add_argument("--execute", action="store_true", help="真正执行重启（需配合 --confirm）")
    ap.add_argument("--confirm", default="", help=f"授权令牌（{TOKEN}）")
    a = ap.parse_args()
    log("=" * 68)
    log("MemOmics WebUI 重启 runbook" + ("（EXECUTE）" if a.execute else "（DRY-RUN 安全演练）"))
    log("=" * 68)
    if not a.execute:
        return preview()
    if a.confirm != TOKEN:
        log(f"拒绝了：--execute 需要 --confirm {TOKEN}（用户一次性授权）")
        return 1
    return execute()


if __name__ == "__main__":
    sys.exit(main())