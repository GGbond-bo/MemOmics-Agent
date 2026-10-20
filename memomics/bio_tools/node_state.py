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


def _current_sid() -> str:
    try:
        from memomics.bio_tools.debate_analysis import get_session_sid
        return get_session_sid() or ""
    except Exception:
        return ""


def register_job(job_id: str, **fields) -> dict:
    d = load_jobs()
    rec = dict(fields)
    # 2026-10-18：作业归属会话 —— 几天后换了会话也能对上"这个 DEG 作业是谁投的"
    rec.setdefault("session_id", _current_sid())
    rec.setdefault("submitted_at_str", time.strftime("%Y-%m-%d %H:%M:%S"))
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


def poll_jobs(host="", user="", port=22, key="", extra_opts=None) -> dict:
    """体检 running 作业：pid+lstart 指纹 + exit 文件 + RSS 峰值。

    2026-10-18：按作业自己的 host 分组查（多节点不漏），host 参数只作缺省回退。
    """
    d = load_jobs()
    all_running = {k: v for k, v in (d.get("jobs") or {}).items()
                   if v.get("status") in ("running", "starting") and v.get("pid")}
    if not all_running:
        return {"checked": 0, "jobs": {}}
    _hosts = {}
    for k, v in all_running.items():
        _hosts.setdefault(v.get("host") or host, {})[k] = v
    if len(_hosts) > 1:
        out_all = {"checked": 0, "jobs": {}}
        for _h, _jobs in _hosts.items():
            _r = _poll_one_host(_h, _jobs, user, port, key, extra_opts)
            out_all["checked"] += _r.get("checked", 0)
            out_all["jobs"].update(_r.get("jobs") or {})
        return out_all
    return _poll_one_host(next(iter(_hosts)), all_running, user, port, key, extra_opts)


def _poll_one_host(_h, running, user="", port=22, key="", extra_opts=None) -> dict:
    if not running:
        return {"checked": 0, "jobs": {}}
    lines = ["for p in %s; do" % " ".join(str(v["pid"]) for v in running.values())]
    lines.append('  if kill -0 $p 2>/dev/null; then '
                 'echo "ALIVE|$p|$(ps -o lstart= -p $p 2>/dev/null | tr -s " ")|$(ps -o rss= -p $p 2>/dev/null | tr -d " ")";'
                 ' else echo "DEAD|$p"; fi')
    lines.append("done")
    for k, v in running.items():
        ef = v.get("exit_file") or ""
        if ef:
            lines.append(f'echo "EXIT|{k}|$(cat {ef} 2>/dev/null)"')
    script = "\n".join(lines)
    try:
        p = subprocess.run(_ssh_prefix(_h, user, port, key, extra_opts)
                           + [f"bash -s <<'MMEOF'\n{script}\nMMEOF"],
                           capture_output=True, text=True, timeout=60)
        out = p.stdout or ""
        err = (p.stderr or "")[:200]
        # 2026-10-20 关键修复：**查询失败不等于进程死了**。
        # 之前 ssh 偶发失败 → out 为空 → 所有 running 作业被误判 lost（实测踩到）。
        if p.returncode != 0 and not out.strip():
            _now = time.time()
            for _jid in running:
                update_job(_jid, poll_error=(err or "ssh failed"), poll_error_at=_now, last_check=_now)
            return {"checked": 0, "error": (err or "ssh failed")[:200], "jobs": {}}
    except Exception as exc:
        return {"checked": 0, "error": str(exc)}
    res = {}
    alive = {}
    dead = set()
    exits = {}
    for ln in out.splitlines():
        # 2026-10-20：分隔符必须是 |（lstart 形如 "Tue Oct 20 11:56:04 2026" 含冒号，
        # 用 : 分隔会把 lstart 截断成 "Tue Oct 20 11" → 误判 pid 复用 → 在跑的作业变 lost）
        if ln.startswith("ALIVE|"):
            parts = ln.split("|", 3)
            if len(parts) >= 4:
                alive[parts[1].strip()] = {"lstart": parts[2].strip(), "rss_kb": parts[3].strip()}
        elif ln.startswith("DEAD|"):
            dead.add(ln.split("|", 1)[1].strip())
        elif ln.startswith("EXIT|"):
            parts = ln.split("|", 2)
            if len(parts) >= 3:
                exits[parts[1].strip()] = parts[2].strip()
    now = time.time()
    for jid, rec in running.items():
        pid = str(rec.get("pid"))
        info = alive.get(pid)
        cur = {"status": rec.get("status")}
        if info:
            # pid 复用防护：启动时间指纹必须一致
            _a = " ".join(str(rec.get("lstart") or "").split())
            _b = " ".join(str(info.get("lstart") or "").split())
            _WD = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
            # 只有两侧都是合法 lstart（星期几开头）才比较 —— 噪音/空值一律不做 pid 复用判定
            _comparable = bool(_a and _b and _a.split() and _b.split()
                               and _a.split()[0] in _WD and _b.split()[0] in _WD)
            if _comparable and _a != _b:
                _ex0 = exits.get(jid)
                if _ex0 and _ex0.startswith("EXIT:"):
                    _c0 = _ex0.split("EXIT:", 1)[1].strip()
                    cur = {"status": "done" if _c0 == "0" else "failed",
                           "exit_code": int(_c0) if _c0.lstrip("-").isdigit() else None,
                           "finished_at": now, "poll_error": "lstart 不一致但已读到退出码"}
                else:
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
                       "finished_at": now, "lost_strikes": 0, "poll_error": None}
            else:
                # 连续 2 次都"没进程也没退出码"才判 lost（防网络抖动/OOM 前的瞬态）
                _strikes = int(rec.get("lost_strikes") or 0) + 1
                if _strikes >= 2:
                    cur = {"status": "lost", "lost_strikes": _strikes,
                           "reason": "连续 2 次查不到进程且无退出码（疑似 OOM kill / 机器重启）"}
                else:
                    cur = {"status": rec.get("status") or "running", "lost_strikes": _strikes,
                           "poll_error": "进程未找到（第 1 次，先不下结论）"}
        update_job(jid, **cur)
        res[jid] = cur
    return {"checked": len(running), "jobs": res}


def list_jobs(status=None, limit=None, session_id=None, host=None, running_first=False) -> list:
    """列出作业。limit=None = **全量**（老作业不会被截断挤掉）。"""
    d = load_jobs()
    items = []
    for k, v in (d.get("jobs") or {}).items():
        if status and v.get("status") != status:
            continue
        if session_id and v.get("session_id") != session_id:
            continue
        if host and host not in str(v.get("host") or ""):
            continue
        items.append(v)
    if running_first:
        items.sort(key=lambda r: (r.get("status") not in ("running", "queued"),
                                  -float(r.get("created_at") or 0)))
    else:
        items.sort(key=lambda r: r.get("created_at", 0), reverse=True)
    return items if not limit else items[:limit]


def jobs_summary(session_id: str = "", max_items: int = 5) -> str:
    """每回合注入给模型的作业摘要（像 dataset_cache 那样，让它"记得"有作业在跑）。"""
    try:
        items = list_jobs(session_id=session_id or None, running_first=True)
    except Exception:
        return ""
    if not items:
        return ""
    running = [j for j in items if j.get("status") in ("running", "starting")]
    queued = [j for j in items if j.get("status") == "queued"]
    recent = [j for j in items if j.get("status") in ("done", "failed", "lost", "cancelled")]
    now = time.time()
    lines = [f"【集群作业（本会话 {len(items)} 个：运行 {len(running)} / 排队 {len(queued)} / 已结束 {len(recent)}）】"]
    for j in (running + queued + recent)[:max_items]:
        st = j.get("status")
        if st in ("running", "starting"):
            el = (now - float(j.get("started_at") or j.get("created_at") or now)) / 3600.0
            lines.append(f"  • {j['job_id']}  运行中 {el:.1f}h  pid={j.get('pid')}  node={j.get('node') or j.get('host')}"
                         + (f"  peak={j.get('peak_rss_gb')}GB" if j.get("peak_rss_gb") else ""))
        elif st == "queued":
            w = (now - float(j.get("created_at") or now)) / 60.0
            lines.append(f'  • {j["job_id"]}  排队 {w:.0f}min  {(j.get("message") or "")[:60]}')
        else:
            lines.append(f"  • {j['job_id']}  {st}  exit={j.get('exit_code')}  node={j.get('node') or j.get('host')}")
    lines.append("  需要时可 action=\"jobs\" 看全部（scope=all 含其它会话）、action=\"logs\" 看日志尾部、action=\"cancel\" 停止。")
    return "\n".join(lines) + "\n"

# ---------------- 自动放行队列（2026-10-18 用户要求）----------------
MAX_WAIT_SEC = 7200          # 排队超 2 小时 → 标记 needs_decision，等用户拍板


def _ssh_run(host, user="", port=22, key="", extra_opts=None, cmd="echo ok", timeout=120):
    try:
        p = subprocess.run(_ssh_prefix(host, user, port, key, extra_opts) + [f"bash -lc {shlex.quote(cmd)}"],
                           capture_output=True, text=True, timeout=timeout)
        return p.returncode, ((p.stdout or "") + (p.stderr or "")).strip()
    except Exception as exc:
        return 1, f"ssh failed: {exc}"


def _ssh_upload(host, user, port, key, extra_opts, remote_path, payload: bytes, timeout=120) -> bool:
    """把脚本内容写到集群（cat 覆盖写，避免引号/编码问题）。"""
    try:
        p = subprocess.run(_ssh_prefix(host, user, port, key, extra_opts)
                           + [f"bash -lc {shlex.quote('mkdir -p $(dirname ' + remote_path + ') && cat > ' + remote_path + ' && chmod +x ' + remote_path + ' && echo WROTE')}"],
                           input=payload, capture_output=True, timeout=timeout)
        return b"WROTE" in (p.stdout or b"")
    except Exception:
        return False


def start_queued_job(rec: dict) -> dict:
    """真正启动一个排队中的作业（nohup + 写 exit 文件 + 记 pid/lstart）。"""
    if rec.get("need_upload") and rec.get("code") is not None:
        _ok = _ssh_upload(rec.get("host"), rec.get("user", ""), rec.get("port", 22),
                          rec.get("key", ""), rec.get("extra_opts") or [],
                          rec.get("script") or "", str(rec.get("code") or "").encode("utf-8"))
        if not _ok:
            return {"ok": False, "error": "排队作业脚本上传失败"}
        update_job(rec["job_id"], need_upload=False)
    exe = rec.get("exe") or ""
    script = rec.get("script") or ""
    log = rec.get("log") or (script + ".log")
    exitf = rec.get("exit_file") or (script + ".exit")
    wd = rec.get("workdir") or "~"
    if not (exe and script):
        return {"ok": False, "error": "队列记录缺少 exe/script"}
    inner = f"cd {wd} && {exe} {script} > {log} 2>&1; echo EXIT:$? > {exitf}"
    cmd = ("nohup bash -c " + shlex.quote(inner) +
           " >/dev/null 2>&1 & echo PID:$! && sleep 1 && ps -o lstart= -p $!")
    rc, out = _ssh_run(rec.get("host"), rec.get("user", ""), rec.get("port", 22),
                       rec.get("key", ""), rec.get("extra_opts") or [], cmd, timeout=120)
    import re as _re
    m = _re.search(r"PID:\s*(\d+)", out or "")
    if not m:
        return {"ok": False, "error": "启动失败", "raw": (out or "")[:300]}
    pid = m.group(1)
    lines = [x for x in (out or "").splitlines() if x.strip() and not x.startswith("PID:")]
    lstart = " ".join(lines[0].split()) if lines else ""
    return {"ok": True, "pid": pid, "lstart": lstart}


def promote_queued(limit: int = 2, max_wait_sec: int = MAX_WAIT_SEC) -> dict:
    """把排队作业按顺序放行：绿/黄区就启动，红区保持排队，超时标记 needs_decision。

    触发时机（不引入后台线程）：任何 jobs / submit 调用时顺带推进一次。
    """
    d = load_jobs()
    queued = [v for v in (d.get("jobs") or {}).values() if v.get("status") == "queued"]
    if not queued:
        return {"ok": True, "started": [], "still_queued": 0}
    queued.sort(key=lambda r: r.get("created_at", 0))
    started, blocked = [], None
    now = time.time()
    for rec in queued:
        if len(started) >= limit or blocked:
            break
        wait = now - float(rec.get("created_at") or now)
        if wait > max_wait_sec:
            update_job(rec["job_id"], needs_decision=True,
                       message=f"已排队 {int(wait // 60)} 分钟仍未放行，需要你决定：继续等 / 换节点 / force")
            continue
        st = node_state(rec.get("host"), rec.get("user", ""), rec.get("port", 22),
                        rec.get("key", ""), rec.get("extra_opts") or [],
                        rec.get("workdir") or "~")
        v = decide(st, float(rec.get("mem_gb") or 8.0), float(rec.get("disk_gb") or 20.0))
        if v["zone"] in ("green", "yellow", "unknown"):
            res = start_queued_job(rec)
            if res.get("ok"):
                update_job(rec["job_id"], status="running", pid=res["pid"], lstart=res["lstart"],
                           started_at=now, waited_sec=round(wait, 1), zone=v["zone"])
                started.append({"job_id": rec["job_id"], "pid": res["pid"], "waited_sec": round(wait, 1)})
            else:
                update_job(rec["job_id"], message=f"启动失败: {res.get('error')}")
                blocked = rec["job_id"]
        else:
            blocked = rec["job_id"]
            update_job(rec["job_id"], last_check_zone=v["zone"],
                       message=v.get("message") or "")
    return {"ok": True, "started": started,
            "still_queued": len([v for v in (load_jobs().get("jobs") or {}).values()
                                 if v.get("status") == "queued"]),
            "blocked_by": blocked}


def queue_job(job_id: str, **fields) -> dict:
    """登记一个排队作业（含启动所需规格，供 promote 使用）。"""
    return register_job(job_id, status="queued", **fields)

