# -*- coding: utf-8 -*-
"""节点实时状态 + 弹性水位线 + 作业并发/状态跟踪（2026-10-18，用户口径）。

设计原则（用户明确）：
  · 不搞硬性配额，**默认全部放行**；只有实时观测到资源紧张才自动排队并提醒
  · 静态规格（CPU/内存总量）与实时状态（可用/load/进程数）分开：前者归 cluster_envs.json，
    后者每次提交前现采（20-30s 缓存），因为共享节点水位会随别人突变
  · 拿不准（探测失败/autofs 读不到）→ 返回 need_confirm，让模型问用户，不替用户决定

三区：green 自由跑 / yellow 跑但提醒 / red 排队 / unknown 问用户
"""
from __future__ import annotations

import json
import os
import shlex
import subprocess
import threading
import time

_TTL = float(os.environ.get("MEMOMICS_NODE_STATE_TTL", "25"))
_state_cache = {}          # host -> (ts, dict)
_lock = threading.Lock()

GREEN_RATIO = 0.30         # 剩余 > 总量 30% → 绿
YELLOW_RATIO = 0.10        # 10%~30% → 黄；<10% → 红
LOAD_YELLOW = 0.8          # load/核数
LOAD_RED = 1.2
DISK_SAFETY = 1.5          # 磁盘需求倍数


def _home() -> str:
    return os.environ.get("MEMOMICS_HOME") or os.path.expanduser("~")


def _ssh_prefix(host, user="", port=22, key="", extra_opts=None):
    opts = ["-o", "BatchMode=yes", "-o", "ConnectTimeout=12", "-p", str(port or 22)]
    if key:
        opts += ["-i", key]
    opts += list(extra_opts or [])
    target = f"{user}@{host}" if user else host
    return ["ssh", *opts, target]


# ---------------- 实时采样（一条 ssh 拿全）----------------
_PROBE = r'''
echo "CPU=$(nproc 2>/dev/null || echo 0)"
echo "MEM_TOTAL_KB=$(awk '/^MemTotal:/{print $2}' /proc/meminfo)"
echo "MEM_AVAIL_KB=$(awk '/^MemAvailable:/{print $2}' /proc/meminfo)"
echo "LOAD=$(cut -d' ' -f1 /proc/loadavg)"
echo "NPROC_R=$(pgrep -c -x R 2>/dev/null || echo 0)"
echo "NPROC_PY=$(pgrep -c -f 'python|Rscript' 2>/dev/null || echo 0)"
echo "DISK_METHOD=stat"
echo "DISK_AVAIL_KB=$(stat -f -c %a '__WORKDIR__' 2>/dev/null || echo)"
'''


def probe(host, user="", port=22, key="", extra_opts=None, workdir="~") -> dict:
    """一条 ssh 采一次实时状态。失败返回 {"ok": False, "error": ...}（上层据此走 unknown）。"""
    if not host:
        return {"ok": False, "error": "未配置 host"}
    script = _PROBE.replace("__WORKDIR__", workdir or "~")   # 不用 % 格式化：脚本里有 %a
    try:
        p = subprocess.run(_ssh_prefix(host, user, port, key, extra_opts)
                           + [f"bash -s <<'MMEOF'\n{script}\nMMEOF"],
                           capture_output=True, text=True, timeout=45)
    except Exception as exc:
        return {"ok": False, "error": f"采样失败: {exc}"}
    out = (p.stdout or "") + "\n" + (p.stderr or "")
    if p.returncode != 0 and "CPU=" not in out:
        return {"ok": False, "error": f"采样命令失败: {(p.stderr or '')[:200]}"}

    def _num(key, cast=float, default=0):
        for line in out.splitlines():
            if line.startswith(key + "="):
                v = line.split("=", 1)[1].strip()
                try:
                    return cast(v)
                except Exception:
                    return default
        return default

    total_kb = _num("MEM_TOTAL_KB")
    avail_kb = _num("MEM_AVAIL_KB")
    disk_kb = _num("DISK_AVAIL_KB", default=0)
    st = {
        "ok": True, "ts": time.time(), "host": host, "workdir": workdir,
        "cpu": int(_num("CPU", int, 0) or 0),
        "mem_total_gb": round(total_kb / 1048576.0, 1),
        "mem_avail_gb": round(avail_kb / 1048576.0, 1),
        "load1": round(_num("LOAD"), 3),
        "procs_R": int(_num("NPROC_R", int, 0)),
        "procs_py": int(_num("NPROC_PY", int, 0)),
        # stat -f 返回「可用块数」，不是字节；拿不到就给 None（不确定）
        "disk_avail_gb": round(disk_kb * 4096 / 1073741824.0, 1) if disk_kb else None,
    }
    if not st["mem_total_gb"]:
        return {"ok": False, "error": "读不到内存信息", "raw": out[:300]}
    return st


def node_state(host, user="", port=22, key="", extra_opts=None, workdir="~",
               force: bool = False) -> dict:
    """带缓存的实时状态（默认 25s）。共享节点水位会突变量，缓存不能太长。"""
    key_c = f"{host}|{workdir}"
    now = time.time()
    with _lock:
        hit = _state_cache.get(key_c)
        if hit and not force and (now - hit[0]) < _TTL:
            d = dict(hit[1])
            d["cached"] = True
            d["age"] = round(now - hit[0], 1)
            return d
    st = probe(host, user, port, key, extra_opts, workdir)
    with _lock:
        _state_cache[key_c] = (now, st)
    st["cached"] = False
    return st


# ---------------- 需求估算 ----------------
_MEM_FACTOR = {".rds": 3.5, ".rda": 3.5, ".h5ad": 2.5, ".h5": 2.5, ".csv": 3.0,
               ".tsv": 3.0, ".txt": 2.5, ".bam": 0.6, ".bw": 0.6, ".bigwig": 0.6,
               ".loom": 2.5, ".mtx": 2.5}


def estimate_mem_gb(paths=None, declared=None, history_peak_gb=None, default=8.0) -> dict:
    """估一个作业要多少内存（GB）。优先级：声明 > 历史峰值×1.3 > 输入文件×系数 > 默认。"""
    if declared:
        return {"mem_gb": float(declared), "source": "declared"}
    if history_peak_gb:
        return {"mem_gb": round(float(history_peak_gb) * 1.3, 1), "source": "history"}
    total = 0.0
    used = []
    for p in (paths or []):
        try:
            sz = os.path.getsize(p) / 1073741824.0
        except Exception:
            continue
        ext = os.path.splitext(str(p))[1].lower()
        f = _MEM_FACTOR.get(ext, 2.0)
        total += sz * f
        used.append((os.path.basename(str(p)), round(sz, 2), f))
    if total:
        return {"mem_gb": round(max(total, 2.0), 1), "source": "files", "detail": used}
    return {"mem_gb": float(default), "source": "default"}


# ---------------- 三区判定 ----------------
def decide(st: dict, req_mem_gb: float, req_disk_gb: float = 0.0,
           green: float = GREEN_RATIO, yellow: float = YELLOW_RATIO) -> dict:
    """弹性水位线：绿=跑，黄=跑+提醒，红=排队+建议，unknown=问用户。"""
    if not st.get("ok"):
        return {"zone": "unknown", "allowed": False, "need_confirm": True,
                "reason": st.get("error") or "采样失败",
                "message": "拿不到节点实时状态，要不要照样提交？（可能把节点拖慢）"}
    total = st.get("mem_total_gb") or 0
    avail = st.get("mem_avail_gb") or 0
    load = st.get("load1") or 0
    cpus = max(st.get("cpu") or 1, 1)
    remain = avail - req_mem_gb
    ratio = (remain / total) if total else 0
    load_ratio = load / cpus
    disk = st.get("disk_avail_gb")

    base = {"node": st.get("host"), "mem_total_gb": total, "mem_avail_gb": avail,
            "req_mem_gb": req_mem_gb, "remain_gb": round(remain, 1),
            "remain_ratio": round(ratio, 3), "load1": load, "cpus": cpus,
            "load_ratio": round(load_ratio, 3), "procs_R": st.get("procs_R"),
            "procs_py": st.get("procs_py")}

    if disk is not None and req_disk_gb and disk < req_disk_gb * DISK_SAFETY:
        return {**base, "zone": "red", "allowed": False, "reason": "disk",
                "message": (f"{st.get('host')} 磁盘剩余 {disk:.0f}GB < 需求 {req_disk_gb * DISK_SAFETY:.0f}GB，"
                            "先清理产物或换节点")}
    if remain < 0 or ratio < yellow or load_ratio > LOAD_RED:
        return {**base, "zone": "red", "allowed": False, "reason":
                ("mem" if (remain < 0 or ratio < yellow) else "load"),
                "message": (f"{st.get('host')} 现在紧张：可用 {avail:.0f}GB / 总 {total:.0f}GB，"
                            f"本作业要 {req_mem_gb:.0f}GB，load {load:.2f}/{cpus}核，"
                            f"已有 {st.get('procs_R', 0)} 个 R 进程"),
                "options": ["等待（可稍后重试）", "换节点", "force=true 强行提交（会互相拖慢）"]}
    if ratio < green or load_ratio > LOAD_YELLOW:
        return {**base, "zone": "yellow", "allowed": True,
                "advisory": (f"{st.get('host')} 开始吃紧：剩余 {ratio * 100:.0f}%（{remain:.0f}GB），"
                             f"后续作业可能排队")}
    return {**base, "zone": "green", "allowed": True,
            "advisory": f"{st.get('host')} 余量充足：剩余 {ratio * 100:.0f}%（{remain:.0f}GB），load {load:.2f}"}


# ---------------- 作业登记与状态跟踪 ----------------
def _jobs_path() -> str:
    return os.path.join(_home(), "cluster_jobs.json")


def load_jobs() -> dict:
    try:
        with open(_jobs_path(), "r", encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {"jobs": {}}
    except Exception:
        return {"jobs": {}}


def save_jobs(d: dict) -> None:
    try:
        os.makedirs(os.path.dirname(_jobs_path()), exist_ok=True)
        tmp = _jobs_path() + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False, indent=1)
        os.replace(tmp, _jobs_path())
    except Exception:
        pass


def register_job(job_id: str, **fields) -> dict:
    d = load_jobs()
    rec = dict(fields)
    rec.update({"job_id": job_id, "created_at": time.time(),
                "status": fields.get("status", "queued")})
    d.setdefault("jobs", {})[job_id] = rec
    save_jobs(d)
    return rec


def update_job(job_id: str, **fields) -> None:
    d = load_jobs()
    rec = (d.get("jobs") or {}).get(job_id)
    if not rec:
        return
    rec.update(fields)
    save_jobs(d)


def poll_jobs(host, user="", port=22, key="", extra_opts=None) -> dict:
    """一条 ssh 批量体检所有 running 作业：pid+lstart 指纹 + exit 文件 + RSS 峰值。"""
    d = load_jobs()
    running = {k: v for k, v in (d.get("jobs") or {}).items()
               if v.get("status") in ("running", "starting") and v.get("pid")}
    if not running:
        return {"checked": 0, "jobs": {}}
    lines = ["for p in %s; do" % " ".join(str(v["pid"]) for v in running.values())]
    lines.append('  if kill -0 $p 2>/dev/null; then '
                 'echo "ALIVE:$p:$(ps -o lstart= -p $p 2>/dev/null | tr -s " "):$(ps -o rss= -p $p 2>/dev/null | tr -d " ")";'
                 ' else echo "DEAD:$p"; fi')
    lines.append("done")
    for k, v in running.items():
        ef = v.get("exit_file") or ""
        if ef:
            lines.append(f'echo "EXIT:{k}:$(cat {ef} 2>/dev/null)"')
    script = "\n".join(lines)
    try:
        p = subprocess.run(_ssh_prefix(host, user, port, key, extra_opts)
                           + [f"bash -s <<'MMEOF'\n{script}\nMMEOF"],
                           capture_output=True, text=True, timeout=60)
        out = p.stdout or ""
    except Exception as exc:
        return {"checked": 0, "error": str(exc)}
    res = {}
    alive = {}
    dead = set()
    exits = {}
    for ln in out.splitlines():
        if ln.startswith("ALIVE:"):
            _, pid, lstart, rss = ln.split(":", 3)
            alive[pid] = {"lstart": lstart.strip(), "rss_kb": rss.strip()}
        elif ln.startswith("DEAD:"):
            dead.add(ln.split(":", 1)[1].strip())
        elif ln.startswith("EXIT:"):
            _, jid, val = ln.split(":", 2)
            exits[jid] = val.strip()
    now = time.time()
    for jid, rec in running.items():
        pid = str(rec.get("pid"))
        info = alive.get(pid)
        cur = {"status": rec.get("status")}
        if info:
            # pid 复用防护：启动时间指纹必须一致
            if rec.get("lstart") and info["lstart"] and rec["lstart"] != info["lstart"]:
                cur = {"status": "lost", "reason": "pid 被复用（lstart 不一致）"}
            else:
                rss_gb = round(int(info["rss_kb"] or 0) / 1048576.0, 2) if info["rss_kb"].isdigit() else None
                peak = max(float(rec.get("peak_rss_gb") or 0), rss_gb or 0)
                cur = {"status": "running", "rss_gb": rss_gb, "peak_rss_gb": peak}
        else:
            ex = exits.get(jid)
            if ex and ex.startswith("EXIT:"):
                code = ex.split("EXIT:", 1)[1].strip()
                cur = {"status": "done" if code == "0" else "failed",
                       "exit_code": int(code) if code.lstrip("-").isdigit() else None,
                       "finished_at": now}
            else:
                cur = {"status": "lost", "reason": "进程消失且无退出码（可能被 OOM kill / 机器重启）"}
        update_job(jid, **cur)
        res[jid] = cur
    return {"checked": len(running), "jobs": res}


def list_jobs(status=None, limit=30) -> list:
    d = load_jobs()
    items = []
    for k, v in (d.get("jobs") or {}).items():
        if status and v.get("status") != status:
            continue
        items.append(v)
    items.sort(key=lambda r: r.get("created_at", 0), reverse=True)
    return items[:limit]
