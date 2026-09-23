# -*- coding: utf-8 -*-
"""后台任务契约 + 启动包装器（2026-09-24）。

用户要求：「我想增加后台任务查看的功能，比如后台在跑什么任务，在哪里跑的……
可以让用户查看后台正常跑某一个任务，用的什么环境，PID 号是什么，状态，可以点击
查看当前执行的脚本……把执行任务简要说明，或者把重要参数信息都展示出来。」

设计（三层里的第一层 + 第二层，服务端只读不猜）：
1. 契约落盘：hermes_home/runtime/tasks/<task_id>.json，原子写（tmp + os.replace），
   服务重启后按「PID + 进程创建时间」核对存活：活着接管显示，死了标 interrupted。
2. 打点通道（跨语言）：stdout 标记行 —— R/Python/shell 任何语言写一行就能上报：
      #TASK:STAGE 训练
      #TASK:PROGRESS 0.42 epoch 63/150      （也接受 63/150 形式）
      #TASK:PARAM epochs=150
      #TASK:OUTPUT results/qc/filtered.h5
   进程内也可以直接用 new_task(...) 拿到句柄，效果相同。
3. wrapper：不改分析脚本的启动方式
      python -m memomics.bio_tools.task_run --type qc --title 去背景 --stages 读入,训练,过滤 -- python scripts/qc.py --in data/raw.h5
   wrapper 负责：采集环境（environment.json 的 R/python/cli_tools/gpu）、PID+创建时间、
   日志 tee 到 <session>/log/<task_id>.log、进度解析（百分比/epoch/iteration/N/M）、
   心跳、退出码 -> done/failed、Ctrl-C -> cancelled。

刻意不做的事：不复制/移动用户脚本（脚本仍稳在 results/<sid>/scripts/），不起服务，
不写用户数据以外的目录，包装器自身异常绝不抛给被包装的命令（包装失败 → 原命令照跑）。
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from datetime import datetime, timezone

_THIS = os.path.abspath(__file__)
_REPO = os.path.dirname(os.path.dirname(os.path.dirname(_THIS)))
RUNTIME_DIR = os.environ.get("MEMOMICS_RUNTIME_DIR") or os.path.join(_REPO, "hermes_home", "runtime")
TASKS_DIR = os.environ.get("MEMOMICS_TASKS_DIR") or os.path.join(RUNTIME_DIR, "tasks")
FALLBACK_LOG_DIR = os.path.join(RUNTIME_DIR, "logs")

SCHEMA_VERSION = 1
HEARTBEAT_SEC = 5.0
STALE_SEC = 120.0
LIVE_STATES = ("queued", "running", "paused", "cancelling")
TERMINAL_STATES = ("done", "failed", "cancelled", "interrupted")
TASK_TYPES = ("qc", "cluster", "annotate", "cellbender", "cellchat", "trajectory",
              "enrich", "figure", "table", "literature", "download", "report", "other")

_MARKER_RE = re.compile(r"^\s*#TASK:(STAGE|PROGRESS|PARAM|OUTPUT)\s+(.*)")
_PROGRESS_PATTERNS = (
    (re.compile(r"(\d+(?:\.\d+)?)\s*%"), "percent"),
    (re.compile(r"[Ee]poch\s+(\d+)\s*[/|]\s*(\d+)"), "frac"),
    (re.compile(r"[Ii]teration\s+(\d+)\s*[/|]\s*(\d+)"), "frac"),
    (re.compile(r"(\d+)\s*/\s*(\d+)\s*(?:cells|samples|files|steps|batches|genes)",
                re.I), "frac"),
    (re.compile(r"\[(\d+)\s*/\s*(\d+)\]"), "frac"),
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _atomic_write_json(path: str, payload: dict) -> None:
    """原子写：同目录 tmp + os.replace（照抄 webui/runtime/job_store.py 的做法）。"""
    d = os.path.dirname(path)
    os.makedirs(d, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix="task-", suffix=".tmp", dir=d)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            try:
                os.unlink(tmp)
            except OSError:
                pass


def _read_json(path: str):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _psutil():
    try:
        import psutil  # type: ignore
        return psutil
    except Exception:
        return None


def proc_identity(pid: int) -> dict:
    """进程身份：pid + 名字 + 创建时间（Windows PID 会复用，只存 pid 会认错进程）。"""
    out = {"pid": int(pid), "pname": "", "create_time": None, "cmdline": ""}
    ps = _psutil()
    if ps is None:
        return out
    try:
        p = ps.Process(int(pid))
        out["pname"] = p.name()
        out["create_time"] = float(p.create_time())
        try:
            out["cmdline"] = " ".join(p.cmdline())[:400]
        except Exception:
            pass
    except Exception:
        pass
    return out


def proc_alive(pid, create_time=None) -> bool:
    """存活判定：给了 create_time 就必须匹配（防 PID 复用），否则退回 pid 存在性。"""
    if not pid:
        return False
    ps = _psutil()
    try:
        pid = int(pid)
    except Exception:
        return False
    if ps is None:
        if os.name == "nt":
            # 没有 psutil 时的存活判定。两条纪律：
            #  1) 绝不用 os.kill(pid, 0) —— Windows 上它走 TerminateProcess，
            #     会把"检查存活"变成"真把人家杀了"（CPython 文档明写的行为）。
            #  2) 先问内核 OpenProcess/GetExitCodeProcess，tasklist 只做兜底。
            try:
                import ctypes
                k32 = ctypes.windll.kernel32
                h = k32.OpenProcess(0x1000, False, int(pid))   # QUERY_LIMITED_INFORMATION
                if not h:
                    return False
                try:
                    code = ctypes.c_ulong()
                    if not k32.GetExitCodeProcess(h, ctypes.byref(code)):
                        return False
                    return code.value == 259                    # STILL_ACTIVE
                finally:
                    k32.CloseHandle(h)
            except Exception:
                pass
            try:
                r = subprocess.run(["tasklist", "/FI", "PID eq %d" % pid, "/NH"],
                                   capture_output=True, timeout=15)
                return str(pid) in smart_decode(r.stdout or b"")
            except Exception:
                return False
        try:
            os.kill(pid, 0)
            return True
        except Exception:
            return False
    try:
        p = ps.Process(pid)
        if not p.is_running():
            return False
        if create_time:
            try:
                if abs(float(p.create_time()) - float(create_time)) > 1.0:
                    return False
            except Exception:
                pass
        return True
    except Exception:
        return False


def proc_usage(pid) -> dict:
    """CPU/内存快照（可选，psutil 不在就留空，绝不报假数）。"""
    out = {"cpu_pct": None, "rss_gb": None}
    ps = _psutil()
    if ps is None or not pid:
        return out
    try:
        p = ps.Process(int(pid))
        with p.oneshot():
            out["cpu_pct"] = round(float(p.cpu_percent(interval=None)), 1)
            out["rss_gb"] = round(p.memory_info().rss / (1024 ** 3), 2)
    except Exception:
        pass
    return out


def detect_session_dir(start: str = "") -> str:
    """会话工作目录：优先显式传入/cwd，其次沿路径向上找 memomics-* 结果目录。"""
    start = start or os.getcwd()
    cur = os.path.abspath(start)
    for _ in range(6):
        base = os.path.basename(cur)
        if base.startswith("memomics-") and os.path.isdir(cur):
            return cur
        parent = os.path.dirname(cur)
        if parent == cur:
            break
        cur = parent
    return os.path.abspath(start)


def env_snapshot(python_exe=None, r_exe=None) -> dict:
    """环境快照：读 environment.json（R/python/cli_tools/gpu）+ 实际解释器版本。

    只读配置 + 两次 --version 短调用，面板要能秒开，绝不在这里跑重活。
    """
    env = {"kind": "unknown", "python": None, "r": None, "conda": None,
           "rscript": r_exe or "", "pkgs": {}, "gpu": [], "cli_tools": {},
           "source": "environment.json"}
    try:
        with open(os.path.join(_REPO, "environment.json"), encoding="utf-8-sig") as f:
            cfg = json.load(f)
    except Exception:
        cfg = {}
    paths = cfg.get("paths") or {}
    r_map = paths.get("r") or {}
    if isinstance(r_map, dict) and r_map:
        for ver, info in r_map.items():
            if isinstance(info, dict) and info.get("bin"):
                env["r"] = {"version": str(ver).replace("R-", ""), "bin": info.get("bin"),
                            "lib_user": info.get("lib_user", ""),
                            "pkg_count": info.get("pkg_count"),
                            "key_pkgs": (info.get("key_pkgs") or [])[:12]}
                env["rscript"] = env["rscript"] or info.get("bin", "")
                break
    cli = paths.get("cli_tools")
    if isinstance(cli, dict):
        env["cli_tools"] = {str(k): str(v) for k, v in list(cli.items())[:12]
                            if isinstance(v, str)}
    gpu = cfg.get("gpu")
    if isinstance(gpu, dict):
        for k, v in list(gpu.items())[:3]:
            if isinstance(v, str) and v:
                env["gpu"].append("%s %s" % (k, v))
    env["python"] = python_exe or sys.executable
    env["conda"] = os.environ.get("CONDA_DEFAULT_ENV") or os.environ.get("CONDA_PREFIX") or None
    try:
        r = subprocess.run([env["python"], "-c", "import sys;print(sys.version.split()[0])"],
                           capture_output=True, text=True, timeout=20)
        if r.returncode == 0:
            # 只取版本号：本机 sitecustomize 会往 stdout 打横幅
            # （实测 "[sitecustomize] torch.save patched v4..." 曾把版本号带成两行）
            _txt = (r.stdout or "").strip()
            _ver = re.findall(r"\d+\.\d+\.\d+", _txt)
            env["python_version"] = _ver[-1] if _ver else (
                _txt.splitlines()[-1].strip() if _txt else "")
    except Exception:
        pass
    if env.get("rscript") and os.path.isfile(env["rscript"]):
        try:
            rr = subprocess.run([env["rscript"], "--version"], capture_output=True,
                                text=True, timeout=20)
            txt = [ln.strip() for ln in ((rr.stdout or "") + (rr.stderr or "")).splitlines() if ln.strip()]
            _pick = next((ln for ln in txt if "R version" in ln or "Rscript" in ln), txt[0] if txt else "")
            if _pick:
                env["r_version_line"] = _pick[:80]
        except Exception:
            pass
    if env.get("rscript"):
        env["kind"] = "R"
    elif env["conda"]:
        env["kind"] = "conda"
    else:
        env["kind"] = "python"
    return env


def smart_decode(raw) -> str:
    """按字节解码子进程输出：UTF-8 优先，失败退 GB18030（Windows 上 R/老工具的默认编码）。

    为什么不能直接 text=True：R 与部分工具在 Windows 写 GBK，硬按 UTF-8 解会把
    中文阶段名/参数变成乱码（真机踩过：#TASK:STAGE 训练 -> ѵ��）。
    """
    if isinstance(raw, str):
        return raw
    if not raw:
        return ""
    try:
        return raw.decode("utf-8")
    except Exception:
        pass
    try:
        return raw.decode("gb18030")
    except Exception:
        return raw.decode("utf-8", errors="replace")


def parse_progress_line(line: str):
    """从一行日志里解析 (value, text)；解析不出返回 (None, None)。"""
    s = (line or "").strip()
    if not s or len(s) > 2000:
        return None, None
    for rx, kind in _PROGRESS_PATTERNS:
        m = rx.search(s)
        if not m:
            continue
        try:
            if kind == "percent":
                v = float(m.group(1)) / 100.0
                if 0.0 <= v <= 1.0:
                    return round(v, 4), s[-120:]
            else:
                cur, tot = float(m.group(1)), float(m.group(2))
                if tot > 0 and 0 <= cur <= tot:
                    return round(cur / tot, 4), s[-120:]
        except Exception:
            continue
    return None, None

class Task:
    """一个后台任务的契约句柄（线程安全；每次变更原子落盘）。"""

    def __init__(self, task_id: str, data: dict, path: str = ""):
        self.task_id = task_id
        self.path = path or os.path.join(TASKS_DIR, task_id + ".json")
        self.data = data
        self._lock = threading.RLock()
        self._hb_stop = threading.Event()
        self._hb_thread = None
        self._log_fp = None

    def flush(self) -> None:
        with self._lock:
            self.data["updated_at"] = utc_now()
            # 契约是"两个写者"：任务进程写进度，服务端写取消意图/兜底终态。
            # 落盘前先认领磁盘上的控制字段，否则收尾那次整份覆盖会把 cancel_requested
            # 抹掉（2026-09-24 真机路由取消实测踩到：状态对了但标记没了）。
            try:
                foreign = _read_json(self.path)
                if isinstance(foreign, dict):
                    for k in ("cancel_requested", "cancel_by", "cancel_requested_at"):
                        if foreign.get(k) is not None and self.data.get(k) != foreign.get(k):
                            self.data[k] = foreign[k]
                    if (foreign.get("status") in TERMINAL_STATES
                            and self.data.get("status") not in TERMINAL_STATES):
                        # 服务端已经兜底落终态（15s 升级杀之后）—— 别用内存里的旧状态复活它
                        self.data["status"] = foreign["status"]
                        for k in ("ended_at", "exit_code", "error", "duration_sec", "alive"):
                            if foreign.get(k) is not None:
                                self.data[k] = foreign[k]
            except Exception:
                pass
            try:
                _atomic_write_json(self.path, self.data)
            except Exception:
                pass

    def touch_heartbeat(self, with_usage=True) -> None:
        with self._lock:
            self.data["heartbeat"] = utc_now()
            proc = self.data.setdefault("proc", {})
            if with_usage and proc.get("pid"):
                for k, v in proc_usage(proc["pid"]).items():
                    if v is not None:
                        proc[k] = v
            self.data["alive"] = proc_alive(proc.get("pid"), proc.get("create_time"))
        self.flush()

    def start_heartbeat(self, interval=HEARTBEAT_SEC) -> None:
        if self._hb_thread:
            return

        def _loop():
            while not self._hb_stop.wait(interval):
                try:
                    self.touch_heartbeat()
                except Exception:
                    pass

        self._hb_thread = threading.Thread(target=_loop, name="task-heartbeat", daemon=True)
        self._hb_thread.start()

    def stop_heartbeat(self) -> None:
        self._hb_stop.set()
        self._hb_thread = None

    def open_log(self, log_path: str) -> str:
        try:
            os.makedirs(os.path.dirname(log_path), exist_ok=True)
            self._log_fp = open(log_path, "a", encoding="utf-8", errors="replace")
        except Exception:
            self._log_fp = None
        with self._lock:
            self.data["log"] = log_path
        self.flush()
        return log_path

    def log(self, line: str) -> None:
        if self._log_fp:
            try:
                self._log_fp.write(line if line.endswith("\n") else line + "\n")
                self._log_fp.flush()
            except Exception:
                pass

    @staticmethod
    def _age(iso: str) -> float:
        try:
            t = datetime.fromisoformat(iso)
            if t.tzinfo is None:
                t = t.replace(tzinfo=timezone.utc)
            return max(0.0, (datetime.now(timezone.utc) - t).total_seconds())
        except Exception:
            return 0.0

    def stage(self, name: str, status: str = "running", detail: str = "") -> None:
        with self._lock:
            stages = self.data.setdefault("stages", [])
            now = utc_now()
            for st in stages:
                if st.get("status") == "running" and st.get("name") != name:
                    st["status"] = "done"
                    st["ended_at"] = now
                    st["sec"] = round(self._age(st.get("started_at") or now), 1)
            cur = next((st for st in stages if st.get("name") == name), None)
            if cur is None:
                cur = {"name": name, "status": status, "started_at": now}
                stages.append(cur)
            elif status == "running":
                # 跳到后面的阶段时，把中间的 pending 一并收口，时间线不留空洞
                idx = stages.index(cur)
                for st in stages[:idx]:
                    if st.get("status") in ("pending", "running"):
                        st["status"] = "done"
                        st["ended_at"] = now
            if status == "running" and not cur.get("started_at"):
                # 真 bug（2026-09-24 面板实测）：new_task 预建的 pending 阶段没有 started_at，
                # 收口时 sec 算成 0.0 —— 面板时间线会显示"训练 0.0s"，明明跑了 4 分钟。
                cur["started_at"] = now
            cur["status"] = status
            if detail:
                cur["detail"] = detail[:300]
            if status in ("done", "failed"):
                cur["ended_at"] = now
                cur["sec"] = round(self._age(cur.get("started_at") or now), 1)
            self.data["stage_index"] = stages.index(cur)
            self.data["stage_total"] = max(len(stages), int(self.data.get("stage_total") or 0))
        self.flush()

    def progress(self, value, text: str = "") -> None:
        """value: 0..1 或 "63/150"。"""
        v = value
        if isinstance(v, str) and "/" in v:
            try:
                a, b = v.split("/", 1)
                v = float(a) / float(b)
            except Exception:
                v = None
        try:
            v = float(v)
        except Exception:
            v = None
        if v is not None:
            v = min(1.0, max(0.0, v))
        with self._lock:
            self.data["progress"] = {"value": (round(v, 4) if v is not None else None),
                                     "text": (text or "")[:200], "at": utc_now()}
        self.flush()

    def param(self, key: str, value) -> None:
        with self._lock:
            self.data.setdefault("params", {})[str(key)[:64]] = (
                value if isinstance(value, (int, float, bool)) or value is None
                else str(value)[:300])
        self.flush()

    def output(self, path: str) -> None:
        with self._lock:
            outs = self.data.setdefault("outputs", [])
            if path and path not in outs and len(outs) < 200:
                outs.append(path)
        self.flush()

    def note(self, text: str) -> None:
        with self._lock:
            self.data["summary"] = str(text)[:600]
        self.flush()

    def finish(self, status: str, error: str = "", exit_code=None) -> None:
        with self._lock:
            self.data["status"] = status
            self.data["finished_at"] = utc_now()
            if exit_code is not None:
                self.data["exit_code"] = int(exit_code)
            if error:
                self.data["error"] = str(error)[:1000]
            for st in self.data.get("stages", []):
                if st.get("status") == "running":
                    st["status"] = "done" if status == "done" else "failed"
                    st["ended_at"] = utc_now()
                    st["sec"] = round(self._age(st.get("started_at") or utc_now()), 1)
            self.data["duration_sec"] = round(
                self._age(self.data.get("started_at") or utc_now()), 1)
            self.data["alive"] = False
        self.flush()

    def handle_marker(self, line: str) -> bool:
        """解析 #TASK: 标记行（跨语言打点通道）。返回是否命中。"""
        m = _MARKER_RE.match(line or "")
        if not m:
            return False
        kind, rest = m.group(1), (m.group(2) or "").strip()
        try:
            if kind == "STAGE":
                self.stage(rest[:120] or "stage")
            elif kind == "PROGRESS":
                parts = rest.split(None, 1)
                if parts:
                    self.progress(parts[0], parts[1] if len(parts) > 1 else "")
            elif kind == "PARAM":
                if "=" in rest:
                    k, v = rest.split("=", 1)
                    self.param(k.strip(), v.strip())
            elif kind == "OUTPUT":
                if rest:
                    self.output(rest[:400])
        except Exception:
            pass
        return True


def new_task(title: str, type: str = "other", session_id: str = "", session_dir: str = "",
             script: str = "", cmd: str = "", stages=None, params=None,
             task_id: str = "", source: str = "wrapper", demo=False) -> Task:
    """建一条任务（原子落盘），返回句柄。"""
    t = (type or "other").strip().lower()
    if t not in TASK_TYPES:
        t = "other"
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    task_id = task_id or ("%s-%s-%s" % (t, stamp, uuid.uuid4().hex[:4]))
    session_dir = session_dir or detect_session_dir()
    base = os.path.basename(session_dir.rstrip("\\/"))
    session_id = session_id or (base if base.startswith("memomics-") else "")
    stage_names = [{"name": str(s), "status": "pending"} for s in (stages or [])]
    if stage_names:
        stage_names[0]["status"] = "running"
        stage_names[0]["started_at"] = utc_now()
    data = {
        "schema_version": SCHEMA_VERSION,
        "task_id": task_id,
        "session_id": session_id,
        "session_dir": session_dir,
        "title": (title or "未命名任务")[:160],
        "type": t,
        "status": "running",
        "source": source,
        "demo": bool(demo),
        "script": script or "",
        "cmd": (cmd or "")[:1000],
        "env": {},
        "proc": {},
        "wrapper": proc_identity(os.getpid()),
        "params": dict(params or {}),
        "stages": stage_names,
        "stage_total": len(stage_names),
        "stage_index": 0,
        "progress": {"value": None, "text": "", "at": utc_now()},
        "log": "",
        "outputs": [],
        "started_at": utc_now(),
        "updated_at": utc_now(),
        "heartbeat": utc_now(),
        "alive": True,
        "pid": os.getpid(),
        "error": "",
    }
    task = Task(task_id, data)
    task.flush()
    return task


def load_task(task_id: str):
    path = os.path.join(TASKS_DIR, os.path.basename(str(task_id)) + ".json")
    data = _read_json(path)
    if not isinstance(data, dict):
        return None
    return Task(data.get("task_id") or task_id, data, path)


def current_task():
    """子进程里拿父 wrapper 的任务句柄（wrapper 会设 MEMOMICS_TASK_ID）。

    没有 wrapper 时返回 None —— 调用方退回打印标记行，两条路都不报错。
    """
    tid = os.environ.get("MEMOMICS_TASK_ID") or ""
    if not tid:
        return None
    return load_task(tid)


def reconcile(data: dict) -> dict:
    """存活核对：进程没了但状态还在跑 → interrupted（服务重启/被外部杀掉都兜得住）。"""
    if not isinstance(data, dict) or data.get("status") not in LIVE_STATES:
        return data
    proc = data.get("proc") or {}
    pid = proc.get("pid") or data.get("pid")
    alive = proc_alive(pid, proc.get("create_time"))
    data["alive"] = bool(alive)
    if alive:
        hb = data.get("heartbeat") or data.get("updated_at") or ""
        data["heartbeat_age_sec"] = round(Task._age(hb), 1)
        data["stalled"] = bool(data["heartbeat_age_sec"] > STALE_SEC)
    else:
        data["status"] = "interrupted"
        data["finished_at"] = data.get("finished_at") or utc_now()
        data["error"] = data.get("error") or "进程已不在（服务重启或任务被外部终止）"
        data["stalled"] = False
        data["duration_sec"] = round(Task._age(data.get("started_at") or utc_now()), 1)
        _atomic_write_json(os.path.join(TASKS_DIR, str(data.get("task_id")) + ".json"), data)
    return data


def list_tasks(session_id: str = "", states=None, limit: int = 200, refresh=False) -> list:
    """列出任务（只读；refresh=True 时顺带核对存活并把死任务落成 interrupted）。"""
    if not os.path.isdir(TASKS_DIR):
        return []
    items = []
    for fn in os.listdir(TASKS_DIR):
        if not fn.endswith(".json"):
            continue
        data = _read_json(os.path.join(TASKS_DIR, fn))
        if not isinstance(data, dict) or not data.get("task_id"):
            continue
        if session_id and data.get("session_id") != session_id:
            continue
        items.append(data)
    items.sort(key=lambda d: d.get("started_at") or "", reverse=True)
    items = items[:max(1, int(limit))]
    if refresh:
        for d in items:
            reconcile(d)
    if states:
        items = [d for d in items if d.get("status") in states]
    return items


def tail_log(path: str, lines: int = 200, max_bytes: int = 256 * 1024) -> str:
    """读日志尾部（seek 尾部，不整读几百 MB 的 CellBender 日志）。"""
    try:
        if not path or not os.path.isfile(path):
            return ""
        size = os.path.getsize(path)
        with open(path, "rb") as f:
            if size > max_bytes:
                f.seek(size - max_bytes)
                f.readline()
            raw = f.read()
        text = raw.decode("utf-8", errors="replace")
        rows = text.splitlines()
        return "\n".join(rows[-max(1, int(lines)):])
    except Exception as e:
        return "（日志读取失败：%s）" % e


def kill_tree(pid) -> dict:
    """只杀 wrapper 起的那棵子树（先 SIGTERM，宽限后强杀）。绝不按名字杀全机进程。"""
    out = {"term": False, "kill": False, "method": ""}
    if not pid:
        return out
    ps = _psutil()
    if ps is not None:
        try:
            p = ps.Process(int(pid))
            kids = p.children(recursive=True)
            for c in kids:
                try:
                    c.terminate()
                except Exception:
                    pass
            try:
                p.terminate()
                out["term"] = True
                out["method"] = "psutil"
            except Exception:
                pass
            gone, alive = ps.wait_procs([p] + kids, timeout=10)
            for a in alive:
                try:
                    a.kill()
                    out["kill"] = True
                except Exception:
                    pass
            return out
        except Exception:
            pass
    try:
        if os.name == "nt":
            subprocess.run(["taskkill", "/PID", str(int(pid)), "/T", "/F"],
                           capture_output=True, text=True, timeout=30)
            out["kill"] = True
            out["method"] = "taskkill"
        else:
            os.kill(int(pid), signal.SIGTERM)
            time.sleep(5)
            try:
                os.kill(int(pid), signal.SIGKILL)
                out["kill"] = True
            except Exception:
                pass
            out["term"] = True
            out["method"] = "os.kill"
    except Exception:
        pass
    return out

def request_cancel(task_id: str, by: str = "api") -> dict:
    """面板/服务端专用：只写"取消意图"（原子落盘），不碰进程。

    写 cancel_requested=True + status="cancelling"。wrapper 在退出路径读到该标记后，
    终态落成 cancelled（而不是 failed）；杀进程由调用方按 pid+创建时间核对后再做。
    """
    t = load_task(task_id)
    if t is None:
        return {"ok": False, "error": "任务不存在：%s" % task_id}
    t.data["cancel_requested"] = True
    t.data["cancel_by"] = by
    t.data["cancel_requested_at"] = utc_now()
    if (t.data.get("status") or "") in LIVE_STATES:
        t.data["status"] = "cancelling"
    t.flush()
    return {"ok": True, "task_id": t.data.get("task_id"), "status": t.data.get("status"),
            "cancel_requested_at": t.data["cancel_requested_at"]}


def kill_registered_process(data: dict, key: str = "proc") -> dict:
    """按契约里登记的 pid + 创建时间杀那棵子树；身份不符（PID 被复用）一律不杀。

    返回 {attempted, killed, pid, reason, detail}。永远只杀登记过的那一个 pid 树，
    绝不按进程名匹配 —— 面板点"取消"不能变成误杀别人的任务。
    """
    rec = (data or {}).get(key) or {}
    pid = rec.get("pid")
    ctime = rec.get("create_time")
    if not pid:
        return {"attempted": False, "killed": False, "pid": None, "reason": "契约里没有登记 PID"}
    # 先只看"pid 还在不在"，再看"是不是同一个进程" —— 两件事必须分开说：
    # proc_alive(pid, ctime) 会把"PID 复用"也报成"已不在"，话术会骗人（真机测试暴露）。
    if not proc_alive(pid):
        return {"attempted": False, "killed": False, "pid": pid, "reason": "进程已不在（无需杀）"}
    ident = proc_identity(pid)
    if ctime and not ident.get("create_time"):
        # 没有 psutil 就没法核对创建时间：宁可不动手，也不赌 PID 没被复用
        return {"attempted": False, "killed": False, "pid": pid,
                "reason": "拿不到创建时间，无法确认身份（防 PID 复用），拒绝杀"}
    if ctime and ident.get("create_time"):
        try:
            if abs(float(ident["create_time"]) - float(ctime)) > 1.0:
                return {"attempted": False, "killed": False, "pid": pid,
                        "reason": "PID 已被复用（创建时间不符），拒绝杀"}
        except (TypeError, ValueError):
            pass
    detail = kill_tree(pid)
    time.sleep(0.2)
    dead = not proc_alive(pid, ctime)
    return {"attempted": True, "killed": dead, "pid": pid,
            "reason": "已杀" if dead else "仍在运行（可能已自行退出或权限不足）", "detail": detail}


# ---------------------------------------------------------------------------
# 打点便捷函数：脚本里 import 就能用（有 wrapper 直接更新契约，没 wrapper 打标记行）
# ---------------------------------------------------------------------------

def mark_stage(name: str) -> None:
    t = current_task()
    if t is not None:
        t.stage(name)
        return
    print("#TASK:STAGE %s" % name, flush=True)


def mark_progress(value, text: str = "") -> None:
    t = current_task()
    if t is not None:
        t.progress(value, text)
        return
    print("#TASK:PROGRESS %s %s" % (value, text), flush=True)


def mark_param(key: str, value) -> None:
    t = current_task()
    if t is not None:
        t.param(key, value)
        return
    print("#TASK:PARAM %s=%s" % (key, value), flush=True)


def mark_output(path: str) -> None:
    t = current_task()
    if t is not None:
        t.output(path)
        return
    print("#TASK:OUTPUT %s" % path, flush=True)


# ---------------------------------------------------------------------------
# wrapper：跑真实命令 + 全程打点
# ---------------------------------------------------------------------------

def _default_log_path(session_dir: str, task_id: str) -> str:
    for cand in (os.path.join(session_dir, "log"), FALLBACK_LOG_DIR):
        try:
            os.makedirs(cand, exist_ok=True)
            return os.path.join(cand, task_id + ".log")
        except Exception:
            continue
    return os.path.join(FALLBACK_LOG_DIR, task_id + ".log")


def run_command(cmd, type: str = "other", title: str = "", stages=None, params=None,
                session_dir: str = "", session_id: str = "", script: str = "",
                echo: bool = True, demo: bool = False) -> int:
    """跑一条命令并全程打点；返回被包装命令的退出码（包装自身失败也要让原命令跑）。"""
    session_dir = session_dir or detect_session_dir()
    task = new_task(title=title or " ".join(str(c) for c in cmd[:2]), type=type,
                    session_id=session_id, session_dir=session_dir, script=script,
                    cmd=" ".join(str(c) for c in cmd), stages=stages, params=params,
                    demo=demo)
    try:
        task.data["env"] = env_snapshot()
    except Exception:
        pass
    log_path = _default_log_path(session_dir, task.task_id)
    task.open_log(log_path)
    task.start_heartbeat()
    child_env = dict(os.environ)
    child_env["MEMOMICS_TASK_ID"] = task.task_id
    child_env["PYTHONUNBUFFERED"] = "1"
    child_env["PYTHONIOENCODING"] = "utf-8"
    child_env.setdefault("PYTHONUTF8", "1")

    state = {"cancelled": False, "last_progress_at": 0.0, "child": None}

    def _on_signal(signum, frame):
        state["cancelled"] = True
        c = state.get("child")
        if c is not None:
            try:
                c.terminate()
            except Exception:
                pass

    old_handlers = {}
    for sig in (getattr(signal, "SIGINT", None), getattr(signal, "SIGTERM", None)):
        if sig is None:
            continue
        try:
            old_handlers[sig] = signal.signal(sig, _on_signal)
        except Exception:
            pass

    rc = None
    err_tail = []
    try:
        proc = subprocess.Popen([str(c) for c in cmd], stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                                bufsize=0, env=child_env, cwd=os.getcwd())
        state["child"] = proc
        ident = proc_identity(proc.pid)
        with task._lock:
            task.data["proc"] = ident
            task.data["pid"] = ident.get("pid")
            task.data["wrapper"] = proc_identity(os.getpid())
        task.flush()
        task.touch_heartbeat()      # 立刻采一次 CPU/内存：面板刚打开时不该是空的
        try:
            for raw in iter(proc.stdout.readline, b""):
                line = smart_decode(raw)
                task.log(line)
                if echo:
                    try:
                        sys.stdout.write(line)
                        sys.stdout.flush()
                    except Exception:
                        pass
                hit = False
                try:
                    hit = task.handle_marker(line)
                except Exception:
                    hit = False
                if not hit:
                    val, text = parse_progress_line(line)
                    now = time.time()
                    if val is not None:
                        prev = (task.data.get("progress") or {}).get("value")
                        gap = now - state["last_progress_at"]
                        if gap >= 0.2 and (gap >= 1.0 or prev is None or val - prev >= 0.02):
                            state["last_progress_at"] = now
                            task.progress(val, text)
                if line.strip():
                    err_tail.append(line.strip()[-200:])
                    if len(err_tail) > 5:
                        err_tail.pop(0)
        except KeyboardInterrupt:
            state["cancelled"] = True
        rc = proc.wait()
    except FileNotFoundError as e:
        rc = 127
        task.log("[wrapper] 命令不存在：%s（命令：%s）" % (e, " ".join(str(c) for c in cmd[:4])))
        if echo:
            print("[wrapper] 命令不存在：%s（命令：%s）" % (e, " ".join(str(c) for c in cmd[:4])))
    except Exception as e:
        rc = 126
        task.log("[wrapper] 包装失败：%s" % e)
        if echo:
            print("[wrapper] 包装失败：%s" % e)
    finally:
        for sig, h in old_handlers.items():
            try:
                signal.signal(sig, h)
            except Exception:
                pass

    disk = _read_json(task.path) or {}
    cancelled = bool(state["cancelled"] or disk.get("cancel_requested")
                     or disk.get("status") == "cancelling")
    if cancelled:
        task.finish("cancelled", error="用户取消", exit_code=rc)
        status = "cancelled"
    elif rc == 0:
        task.finish("done", exit_code=0)
        status = "done"
    else:
        task.finish("failed", error="退出码 %s：%s" % (rc, " / ".join(err_tail[-2:])),
                    exit_code=rc)
        status = "failed"
    task.stop_heartbeat()
    if task._log_fp:
        try:
            task._log_fp.close()
        except Exception:
            pass
    if echo:
        print("[task] %s %s rc=%s 用时 %ss 日志 %s" %
              (task.task_id, status, rc, task.data.get("duration_sec"), log_path))
    return rc if rc is not None else 1


def run_demo(stages, sec_per_stage: float = 3.0, title: str = "演示任务（不跑真活）",
             type: str = "other", session_dir: str = "") -> int:
    """演示/自检用：不跑真分析，但走完全部契约字段，方便面板与极端测试。"""
    session_dir = session_dir or detect_session_dir()
    stage_list = list(stages) or ["准备", "执行", "收尾"]
    task = new_task(title=title, type=type, session_dir=session_dir, demo=True,
                    source="demo", cmd="demo", stages=stage_list,
                    params={"每阶段秒数": sec_per_stage, "阶段数": len(stage_list)})
    task.data["env"] = {"kind": "demo", "python": sys.executable, "source": "demo"}
    with task._lock:
        task.data["proc"] = proc_identity(os.getpid())
        task.data["pid"] = os.getpid()
    task.touch_heartbeat()      # 立刻采一次 CPU/内存：面板刚打开时不该是空的
    task.open_log(_default_log_path(session_dir, task.task_id))
    task.start_heartbeat()
    task.log("[demo] 阶段：%s" % "、".join(stage_list))
    ticks = max(3, int(sec_per_stage / 0.5))
    n_stage = len(stage_list)
    for si, name in enumerate(stage_list):
        task.stage(name)
        for i in range(ticks):
            time.sleep(0.5)
            # 整任务进度单调递增（每阶段清零会变成锯齿，面板上看着像倒退）
            done = (si + (i + 1) / float(ticks)) / float(n_stage)
            task.progress(done, "%s %d/%d（总 %d%%）" % (name, i + 1, ticks, round(100 * done)))
            task.log("[demo] %s %d/%d" % (name, i + 1, ticks))
    out_dir = os.path.join(session_dir, "results")
    out_file = os.path.join(out_dir, "demo_out.txt")
    try:
        os.makedirs(out_dir, exist_ok=True)
        with open(out_file, "w", encoding="utf-8") as f:
            f.write(("演示任务产物：验证面板能列出真实存在的产物（%s）" % task.task_id) + chr(10))
    except OSError:
        pass
    task.output(out_file)
    task.note("演示任务：验证面板能显示阶段/进度/日志/产物，不代表任何真实分析。")
    task.finish("done", exit_code=0)
    task.stop_heartbeat()
    if task._log_fp:
        task._log_fp.close()
    print("[task] %s done（演示）用时 %ss" % (task.task_id, task.data.get("duration_sec")))
    return 0


def _cmd_list(args) -> int:
    items = list_tasks(session_id=args.session_id or "", refresh=True, limit=args.limit)
    if args.json:
        print(json.dumps(items, ensure_ascii=False, indent=2))
        return 0
    if not items:
        print("（没有任务记录：%s）" % TASKS_DIR)
        return 0
    for d in items:
        pr = d.get("progress") or {}
        pct = "%.0f%%" % (100 * pr["value"]) if isinstance(pr.get("value"), (int, float)) else "-"
        print("%-28s %-9s %-10s %6s  pid=%-7s %s  %s" % (
            d.get("task_id"), d.get("status"), d.get("type"), pct,
            (d.get("proc") or {}).get("pid") or "-", d.get("title", "")[:40],
            ((d.get("progress") or {}).get("text") or "")[:40]))
    return 0


def _cmd_show(args) -> int:
    t = load_task(args.show)
    if t is None:
        print("任务不存在：%s" % args.show)
        return 2
    data = reconcile(t.data)
    if args.tail:
        data = dict(data)
        data["log_tail"] = tail_log((data.get("log") or ""), args.tail)
    print(json.dumps(data, ensure_ascii=False, indent=2))
    return 0


def main(argv=None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    p = argparse.ArgumentParser(
        prog="python -m memomics.bio_tools.task_run",
        description="后台任务契约 + wrapper：把一条长命令登记成可观战的任务。")
    p.add_argument("--type", default="other", help="任务类型：%s" % ",".join(TASK_TYPES))
    p.add_argument("--title", default="", help="任务名（面板显示）")
    p.add_argument("--stages", default="", help="阶段名，逗号分隔，如 读入,训练,过滤")
    p.add_argument("--param", action="append", default=[], help="重要参数 k=v，可重复")
    p.add_argument("--script", default="", help="主脚本路径（面板里可查看）")
    p.add_argument("--session-dir", default="", help="会话目录（默认自动探测）")
    p.add_argument("--session-id", default="", help="会话 id（默认取目录名）")
    p.add_argument("--quiet", action="store_true", help="不回显子进程输出（仍写日志）")
    p.add_argument("--demo", nargs="?", const="", default=None,
                   help="演示模式：阶段:秒数 逗号分隔（不带值 = 默认三阶段），不跑真活")
    p.add_argument("--list", action="store_true", help="列出任务")
    p.add_argument("--show", default="", help="查看某任务契约（JSON）")
    p.add_argument("--tail", type=int, default=0, help="配合 --show 附日志尾部行数")
    p.add_argument("--json", action="store_true", help="--list 输出 JSON")
    p.add_argument("--limit", type=int, default=200)
    p.add_argument("cmd", nargs=argparse.REMAINDER, help="-- 之后的真实命令")
    args = p.parse_args(argv)

    if args.list:
        return _cmd_list(args)
    if args.show:
        return _cmd_show(args)
    if args.demo is not None:
        spec = args.demo or "读入:3,训练:3,收尾:3"
        stages, sec = [], 3.0
        for part in spec.split(","):
            part = part.strip()
            if not part:
                continue
            if ":" in part:
                nm, _, s = part.partition(":")
                try:
                    sec = float(s)
                except Exception:
                    print("[task] --demo 解析失败：%r（应为 阶段:秒数，如 读入:3,训练:5）" % part)
                    return 2
                stages.append(nm.strip() or ("阶段%d" % (len(stages) + 1)))
            else:
                stages.append(part)
        if not stages:
            print("[task] --demo 没解析出阶段：%r" % spec)
            return 2
        return run_demo(stages, sec, title=args.title or "演示任务（不跑真活）",
                        type=args.type, session_dir=args.session_dir)

    cmd = list(args.cmd)
    if cmd and cmd[0] == "--":
        cmd = cmd[1:]
    if not cmd:
        p.print_help()
        return 2
    params = {}
    for kv in args.param:
        if "=" in kv:
            k, v = kv.split("=", 1)
            params[k.strip()] = v.strip()
    stages = [s.strip() for s in args.stages.split(",") if s.strip()]
    return run_command(cmd, type=args.type, title=args.title, stages=stages, params=params,
                       session_dir=args.session_dir, session_id=args.session_id,
                       script=args.script, echo=not args.quiet)


if __name__ == "__main__":
    sys.exit(main())
