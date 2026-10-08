# -*- coding: utf-8 -*-
"""集群常驻 R 会话（kernel 式持久化）—— 2026-10-09

背景（用户原话）
----------------
「我希望的持久化，是我读取了这个 rds 数据，这个数据就应该一直在。例如我读取 MuSC 的
rds，现在要跑 umap，你只是弄了 10.9MB 精简缓存，但是我还想继续做 findmarker、cellchat
其他分析呢？」——方案 A 的 light.rds 只是**绘图/参数扫描用的快照**（不含表达量矩阵），
FindMarkers/CellChat/轨迹分析仍然要回读原文件。本模块给的是「像 kernel 一样」的
**常驻 R 进程**：读一次，之后所有分析都在同一个进程内存里接着做。

结构
----
* 远端：`memomics_home/skills/bioinformatics/remote-cluster-execution/scripts/r_session_daemon.R`
  —— 纯 base R 的常驻守护进程（无 Rserve / 无 socket 端口 / 无三方包），用 setsid 脱离
  会话启动；请求与结果走**文件队列**：
      queue/<id>.req.R  →（daemon 原子认领）→  run/  →  done/<id>.res.txt
  心跳在 state.txt（pid/status/readrds 计数/rss），事件流水在 session.log。
* 本机：本模块负责 部署 daemon → 拉起 → 投递代码 → 等待结果 → 收产物 → 落账
  （`memomics_home/remote/sessions.json`）+ 落任务标记（large_cache）。
* 入口：`remote_cluster` 工具的 `session_*` 动作（WebUI 控制台与 agent 共用同一条路径）。

事实纪律（2026-10-09 实测，别再猜）
----------------------------------
* R4.41 里**没有 Rserve、没有 qs**；jsonlite 有，但本方案连它都不用（纯文本协议）。
* 登录节点不跑重活；SGE qmaster 不通 → 与既有作业链路一致，用 setsid 后台常驻。
* 共享机器不开公网端口：daemon 与投递方在**同一节点**上，靠共享目录里的文件通信。
* 会话对象在内存里；检查点（mm_save）落 ckpt/*.rds（默认压缩）。两者互补：
  内存让它「活着」，检查点让它在进程死掉/换节点后还能回来。
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import posixpath
import random
import re
import shlex
import string
from datetime import datetime
from pathlib import Path

from memomics.bio_tools import remote_cluster as rc

SESSION_VERSION = "1"
_MAX_SESSION_ID = 48

# 会话默认参数（可被 config.yaml 的 remote.session 覆盖；节点级 remote.nodes.<名字>.session 再覆盖）
_SESSION_DEFAULTS = {
    "env": "R4.41",                 # 默认 conda 环境名（本集群 RNA 分析用 R4.41）
    "rscript": "",                  # 直接给 Rscript 绝对路径（最高优先）
    "roots": ["~/miniconda3", "~/anaconda3", "/opt/conda"],  # 按 <root>/envs/<env>/bin/Rscript 找
    "dir": "",                      # 会话根目录；空 = <workdir>/memomics_cache/sessions
    "load_timeout": 1800,           # session_start 读入 input 的等待上限（秒）
    "wait": 1200,                   # session_exec 默认等待上限（秒）
    "save_wait": 3600,              # session_save 默认等待上限（秒，检查点可能很大）
    "max_sessions": 2,              # 同节点并行常驻会话的建议上限（超了只提示，不硬拦）
}

# ---------------------------------------------------------------------------
# 身份证 / 目录 / 注册表
# ---------------------------------------------------------------------------


def _sessions_path() -> Path:
    base = rc._get_config_path().parent / "remote"
    base.mkdir(parents=True, exist_ok=True)
    return base / "sessions.json"


def _load_registry() -> dict:
    path = _sessions_path()
    if not path.exists():
        return {}
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save_registry(reg: dict) -> None:
    path = _sessions_path()
    tmp = path.parent / (path.name + ".tmp")
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(reg, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    os.replace(tmp, path)


def _registry_upsert(rec: dict) -> dict:
    reg = _load_registry()
    old = reg.get(rec.get("id") or "")
    if not isinstance(old, dict):
        old = {}
    old.update(rec)
    old["updated"] = rc._now()
    reg[old["id"]] = old
    _save_registry(reg)
    return old


def _registry_touch(rec: dict, **fields) -> dict:
    rec = dict(rec)
    rec.update(fields)
    rec["last_active"] = rc._now()
    return _registry_upsert(rec)


def find_session(session_id: str = "") -> dict | None:
    """按 id 找会话记录；不给 id = 最近活跃的一条（全节点）。"""
    reg = _load_registry()
    if session_id:
        rec = reg.get(str(session_id))
        return dict(rec) if isinstance(rec, dict) else None
    return latest_session()


def latest_session(node: str = "") -> dict | None:
    """最近活跃的会话；给定 node 时只看那台。优先未停止的。"""
    rows = [dict(v) for v in _load_registry().values() if isinstance(v, dict)]
    if node:
        rows = [r for r in rows if str(r.get("node") or "") == str(node)]
    active = [r for r in rows if str(r.get("status") or "") != "stopped"]
    pool = active or rows
    if not pool:
        return None
    return max(pool, key=lambda r: str(r.get("last_active") or r.get("created") or ""))


def _new_id(prefix: str = "s") -> str:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    rand = "".join(random.choice(string.ascii_lowercase + string.digits) for _ in range(4))
    return "%s-%s-%s" % (prefix, stamp, rand)


def _new_req_id() -> str:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    rand = "".join(random.choice(string.ascii_lowercase + string.digits) for _ in range(6))
    return "r-%s-%s" % (stamp, rand)


def _valid_session_id(sid: str) -> bool:
    return bool(re.match(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,%d}$" % (_MAX_SESSION_ID - 1), str(sid or "")))


# ---------------------------------------------------------------------------
# 配置合并 / R 脚本定位
# ---------------------------------------------------------------------------


def _session_cfg(cfg: dict, node: dict | None = None) -> dict:
    out = dict(_SESSION_DEFAULTS)
    for src in (cfg.get("session"), (node or {}).get("session")):
        if not isinstance(src, dict):
            continue
        for key, val in src.items():
            if val is None:
                continue
            if isinstance(val, (list, tuple)):
                out[key] = [str(x) for x in val if str(x).strip()]
            elif str(val).strip() != "":
                out[key] = val
    return out


def _daemon_script_path() -> Path:
    root = rc._memomics_root()
    return (root / "memomics_home" / "skills" / "bioinformatics"
            / "remote-cluster-execution" / "scripts" / "r_session_daemon.R")


def _daemon_source_text() -> str:
    path = _daemon_script_path()
    if not path.exists():
        raise RuntimeError("找不到 daemon 脚本（仓库里缺文件）：%s" % path)
    return path.read_text(encoding="utf-8").replace("\r\n", "\n")


# ---------------------------------------------------------------------------
# 远端小工具（全部走既有 SSH 引擎）
# ---------------------------------------------------------------------------


def _exec_full(conn, command: str, timeout: int = 120) -> dict:
    """全保真执行：结果要被解析/落盘时用它（bounded_capture 会截断）。"""
    return conn.execute(command, timeout=timeout)


def _exec_disp(conn, command: str, timeout: int = 120) -> dict:
    """给模型看的执行（允许有界截断）。"""
    return rc._exec_env(conn, command, timeout=timeout)


def _remote_md5(conn, path: str) -> str:
    res = _exec_full(conn, "md5sum %s 2>/dev/null | awk '{print $1}'" % shlex.quote(path),
                     timeout=60)
    out = [l.strip() for l in (res.get("output") or "").splitlines() if l.strip()]
    return out[0] if out else ""


def _remote_write(conn, path: str, text: str, mode: str = "600", timeout: int = 300) -> dict:
    """把文本写到远端（base64 分块，绕开所有引号/换行/编码坑），并 md5 校验。"""
    data = text.encode("utf-8")
    b64 = base64.b64encode(data).decode("ascii")
    parent = posixpath.dirname(path.rstrip("/")) or "."
    out = ""

    def _fail(msg):
        return {"ok": False, "bytes": len(data), "md5": hashlib.md5(data).hexdigest(),
                "remote_md5": "", "path": path, "output": rc._truncate(msg, 2000)}

    mk = _exec_full(conn, "mkdir -p %s" % shlex.quote(parent), timeout=60)
    if mk.get("returncode") not in (0, None):
        return _fail((mk.get("output") or "").strip() or "mkdir 失败")
    # 分块单独发（每块一条命令）：绕开 ssh 命令行长度限制，也不受引号/换行/编码影响
    chunk = 8000
    first = True
    for i in range(0, len(b64), chunk):
        part = b64[i:i + chunk]
        cmd = ("printf %%s %s | base64 -d %s %s"
               % (shlex.quote(part), ">" if first else ">>", shlex.quote(path)))
        res = _exec_full(conn, cmd, timeout=timeout)
        if res.get("returncode") is None:
            return _fail("写入超时（第 %d 块）" % (i // chunk + 1))
        if res.get("returncode") != 0:
            return _fail((res.get("output") or "").strip() or "写入失败（第 %d 块）" % (i // chunk + 1))
        first = False
    fin = _exec_full(conn, "chmod %s %s && md5sum %s | awk '{print $1}'"
                     % (mode, shlex.quote(path), shlex.quote(path)), timeout=60)
    lines = [l.strip() for l in (fin.get("output") or "").splitlines() if l.strip()]
    remote_md5 = lines[-1] if lines else ""
    local_md5 = hashlib.md5(data).hexdigest()
    ok = fin.get("returncode") == 0 and remote_md5 == local_md5
    if not ok:
        out = "md5 校验不过（本地 %s / 远端 %s）" % (local_md5, remote_md5 or "?")
    return {"ok": ok, "bytes": len(data), "md5": local_md5, "remote_md5": remote_md5,
            "path": path, "output": out}


def _deploy_daemon(conn, bin_dir: str, timeout: int = 300) -> dict:
    """把 daemon 脚本放到共享 bin/ 下（md5 相同就不重复传）。"""
    text = _daemon_source_text()
    path = posixpath.join(bin_dir, "r_session_daemon.R")
    local_md5 = hashlib.md5(text.encode("utf-8")).hexdigest()
    if _remote_md5(conn, path) == local_md5:
        return {"deployed": False, "md5": local_md5, "path": path}
    res = _remote_write(conn, path, text, mode="700", timeout=timeout)
    res["deployed"] = True
    if not res.get("ok"):
        raise RuntimeError("daemon 脚本推送失败（md5 校验不过）：%s" % (res.get("output") or ""))
    return res


def _probe_rscript(conn, sess: dict, env: str, explicit: str = "") -> dict:
    """在节点上找一个能用的 Rscript（优先显式路径，其次 conda envs，最后 PATH）。"""
    env = str(env or sess.get("env") or "R4.41").strip()
    cands: list = []
    for c in (explicit, sess.get("rscript")):
        if str(c or "").strip():
            cands.append(str(c).strip())
    roots = sess.get("roots") or []
    if isinstance(roots, str):
        roots = [x.strip() for x in roots.replace(";", ",").split(",") if x.strip()]
    for r in roots:
        r = str(r).strip().rstrip("/")
        if r:
            cands.append(posixpath.join(r, "envs", env, "bin", "Rscript"))
    seen, uniq = set(), []
    for c in cands:
        if c not in seen:
            seen.add(c)
            uniq.append(c)
    checks = " ".join(rc._sh_path(c) for c in uniq)
    cmd = ("set +e; for c in %s; do if [ -x \"$c\" ]; then echo \"FOUND:$c\"; "
           "\"$c\" -e 'cat(R.version.string, \"\\n\")' 2>&1 | head -n 1; exit 0; fi; done; "
           "if command -v Rscript >/dev/null 2>&1; then echo \"FOUND:$(command -v Rscript)\"; "
           "Rscript -e 'cat(R.version.string, \"\\n\")' 2>&1 | head -n 1; "
           "else echo NO_RSCRIPT; fi" % checks)
    res = _exec_full(conn, cmd, timeout=90)
    out = (res.get("output") or "").strip()
    found, version = "", ""
    for line in out.splitlines():
        line = line.strip()
        if line.startswith("FOUND:"):
            found = line[len("FOUND:"):].strip()
        elif line.startswith("R version"):
            version = line
    return {"ok": bool(found), "rscript": found, "version": version,
            "env": env, "candidates": uniq, "raw": rc._truncate(out, 1200)}


def _node_for(cfg: dict, node_name: str):
    """选节点 → (node_cfg, name, err_json)。"""
    return rc._select_node(cfg, node_name or "")


def _default_session_root(node: dict) -> str:
    wd = str(node.get("workdir") or "~").rstrip("/")
    return posixpath.join(wd, "memomics_cache", "sessions")


def _shared_bin_dir(node: dict) -> str:
    wd = str(node.get("workdir") or "~").rstrip("/")
    return posixpath.join(wd, "memomics_cache", "bin")


# ---------------------------------------------------------------------------
# 代码 / 请求 / 结果：纯函数（离线可单测）
# ---------------------------------------------------------------------------


def _r_str(value) -> str:
    """R 字符串字面量（先转义反斜杠再转义引号）。"""
    s = str(value if value is not None else "")
    return '"%s"' % s.replace("\\", "\\\\").replace('"', '\\"')


def _obj_name_from_path(path: str, fallback: str = "obj") -> str:
    base = posixpath.basename(str(path or "").rstrip("/"))
    base = re.sub(r"\.(rds|rda|rdata)$", "", base, flags=re.I)
    name = re.sub(r"[^0-9A-Za-z._]", "_", base) or fallback
    if not re.match(r"^[A-Za-z.]", name):
        name = "obj_" + name
    return name[:48]


def _req_text(rid: str, op: str, code: str) -> str:
    body = str(code or "")
    if not body.endswith("\n"):
        body += "\n"
    return "#MM-REQ id=%s op=%s created=%s\n%s" % (rid, op, rc._now(), body)


def _save_code(name: str = "", objects=None) -> str:
    obj_arg = "NULL"
    objs = [str(o).strip() for o in (objects or []) if str(o).strip()]
    if objs:
        obj_arg = "c(%s)" % ", ".join(_r_str(o) for o in objs)
    return "mm_save(name = %s, objects = %s)" % (_r_str(name) if str(name or "").strip() else "NULL",
                                                 obj_arg)


def _restore_code(path: str = "") -> str:
    return "mm_restore(%s)" % (_r_str(path) if str(path or "").strip() else "")


def _load_code(input_path: str, obj_name: str) -> str:
    code = (
        "inp <- {INP}\n"
        "if (!file.exists(inp)) stop(\"输入文件不存在: \", inp)\n"
        ".mm_t0 <- Sys.time()\n"
        "{OBJ} <- readRDS(inp)\n"
        "cat(sprintf(\"已读入 %s -> %s（%.1f 秒）\\n\", inp, \"{OBJ}\", "
        "as.numeric(difftime(Sys.time(), .mm_t0, units = \"secs\"))))\n"
        "cat(\"维度/类型: \", paste(dim({OBJ}), collapse = \" x \"), \"  \", "
        "paste(class({OBJ}), collapse = \"/\"), \"\\n\", sep = \"\")\n"
        "cat(\"readRDS 审计：本会话累计 \", .mm_reads_count(), \" 次\\n\", sep = \"\")\n"
    )
    return code.replace("{INP}", _r_str(input_path)).replace("{OBJ}", str(obj_name))


_MARKERS = ("---OUTPUT---", "---WARNINGS---", "---ERROR---", "---READS---")


def _parse_res(text: str) -> dict:
    """解析 daemon 写的 done/<id>.res.txt（头部 key:value + 四个分段）。"""
    header, sections = {}, {}
    cur, buf = None, []
    for line in (text or "").splitlines():
        if line.strip() in _MARKERS:
            if cur is not None:
                sections[cur] = "\n".join(buf)
            cur, buf = line.strip(), []
            continue
        if cur is None:
            if ":" in line:
                k, v = line.split(":", 1)
                header[k.strip()] = v.strip()
        else:
            buf.append(line)
    if cur is not None:
        sections[cur] = "\n".join(buf)

    reads = []
    for ln in (sections.get("---READS---") or "").splitlines():
        parts = ln.split("\t")
        if len(parts) >= 3:
            reads.append({"time": parts[0].strip(), "bytes": parts[1].strip(),
                          "path": parts[2].strip()})
    err = (sections.get("---ERROR---") or "").strip()
    try:
        calls = int(header.get("readrds_calls") or 0)
    except Exception:
        calls = 0
    try:
        objects = int(header.get("objects") or 0)
    except Exception:
        objects = 0
    return {
        "header": header,
        "status": header.get("status") or ("error" if err else "ok"),
        "ms": header.get("ms") or "",
        "readrds_calls": calls,
        "objects": objects,
        "rss_kb": header.get("rss_kb") or "",
        "output": (sections.get("---OUTPUT---") or "").rstrip("\n"),
        "warnings": (sections.get("---WARNINGS---") or "").strip(),
        "error": err,
        "reads": reads,
        "raw": text,
    }


def _parse_state(text: str) -> dict:
    out = {}
    for line in (text or "").splitlines():
        line = line.strip()
        if not line or line.startswith("=") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        out[k.strip()] = v.strip()
    return out


def _split_sections(text: str) -> dict:
    """把 `==STATE==` 这类标记切成字典（status 输出用）。"""
    out, cur, buf = {}, None, []
    for line in (text or "").splitlines():
        s = line.strip()
        if s.startswith("==") and s.endswith("==") and len(s) > 4:
            if cur is not None:
                out[cur] = "\n".join(buf)
            cur, buf = s.strip("=").strip(), []
        else:
            buf.append(line)
    if cur is not None:
        out[cur] = "\n".join(buf)
    return out


# ---------------------------------------------------------------------------
# 请求投递 / 等待
# ---------------------------------------------------------------------------


def _submit(conn, sdir: str, code: str, op: str = "eval") -> dict:
    """投递一个请求：先写 staging/（daemon 不扫这里），再原子 mv 进 queue/。

    ⚠️ 2026-10-09 实踩：直接往 queue/ 里分块写，daemon 会在写一半时把文件认领走
    （rename 到 run/ 并执行），投递方的 chmod/md5 就会「找不到文件」而报投递失败——
    其实请求已经跑了。staging + rename 后，daemon 看到的永远是完整文件。
    """
    rid = _new_req_id()
    stage = posixpath.join(sdir, "staging", "%s.req.R" % rid)
    final = posixpath.join(sdir, "queue", "%s.req.R" % rid)
    text = _req_text(rid, op, code)
    res = _remote_write(conn, stage, text, mode="600")
    if not res.get("ok"):
        return {"ok": False, "id": rid, "error": "请求文件写入失败：%s" % (res.get("output") or "")}
    mv = _exec_full(conn, "mv %s %s" % (shlex.quote(stage), shlex.quote(final)), timeout=60)
    if mv.get("returncode") != 0:
        return {"ok": False, "id": rid,
                "error": "请求入队失败：%s" % ((mv.get("output") or "").strip() or "mv 非 0 退出")}
    return {"ok": True, "id": rid, "path": final, "stage": stage}


def _await_res(conn, sdir: str, rid: str, wait: int) -> dict:
    """等结果文件出现（远端一个 ssh 命令自己轮询，不刷屏）；wait<=0 不等待。"""
    res_path = posixpath.join(sdir, "done", "%s.res.txt" % rid)
    n = max(1, int(wait))
    cmd = ("for i in $(seq 1 %d); do [ -f %s ] && break; sleep 1; done; "
           "if [ -f %s ]; then cat %s; else echo MM_NOTREADY; fi"
           % (n, shlex.quote(res_path), shlex.quote(res_path), shlex.quote(res_path)))
    r = _exec_full(conn, cmd, timeout=n + 60)
    out = r.get("output") or ""
    if "---OUTPUT---" not in out and "MM_NOTREADY" in out:
        return {"ready": False, "raw": out}
    parsed = _parse_res(out)
    parsed["ready"] = True
    parsed["res_path"] = res_path
    return parsed


def _wait_seconds(args: dict, sess: dict, default_key: str = "wait", cap: int = 86400) -> int:
    fallback = sess.get(default_key, _SESSION_DEFAULTS.get(default_key, 1200))
    raw = args.get("wait")
    if raw in (None, ""):
        raw = fallback
    try:
        wait = int(float(raw))
    except Exception:
        try:
            wait = int(float(fallback))
        except Exception:
            wait = 1200
    return max(0, min(wait, cap))


def _resolve_session(cfg: dict, args: dict):
    """会话动作共用：找到记录 + 连它所在的节点 → (rec, node_cfg, node_name, err)。"""
    sid = str(args.get("session_id") or "").strip()
    node_hint = str(args.get("node") or "").strip()
    rec = find_session(sid) if sid else latest_session(node_hint)
    if not rec:
        return None, None, "", rc._err(
            ("没找到会话 %r。" % sid) if sid else "这台节点上还没有常驻会话记录。",
            hint=("用 action='session_list' 看现有会话；要新建用 "
                  "action='session_start'（可带 input=<rds 路径> 读一次大文件）。"
                  "会话记录在本机（memomics_home/remote/sessions.json），重启本机不会丢。"))
    node, node_name, err = _node_for(cfg, rec.get("node") or node_hint)
    if err:
        return None, None, "", err
    return rec, node, node_name, None


# ---------------------------------------------------------------------------
# 动作：session_start
# ---------------------------------------------------------------------------


def action_start(cfg: dict, args: dict) -> str:
    node, node_name, err = _node_for(cfg, str(args.get("node") or "").strip())
    if err:
        return err
    sess = _session_cfg(cfg, node)
    env = str(args.get("env") or sess.get("env") or "R4.41").strip()

    sid = str(args.get("session_id") or "").strip() or _new_id()
    if not _valid_session_id(sid):
        return rc._err("session_id 非法（只允许字母数字 . _ -，≤%d 字符）: %r" % (_MAX_SESSION_ID, sid))
    root = str(args.get("session_root") or sess.get("dir") or "").strip() or _default_session_root(node)
    sdir = posixpath.join(root.rstrip("/"), sid)
    bin_dir = _shared_bin_dir(node)

    input_path = str(args.get("input") or args.get("path") or "").strip()
    obj_name = str(args.get("object") or "").strip() or _obj_name_from_path(input_path)
    title = str(args.get("title") or "").strip() or (posixpath.basename(input_path.rstrip("/")) or sid)
    restore = str(args.get("restore") or "").strip()

    conn = rc._get_conn(node)

    # 0) 会话目录已有活着的 daemon？直接回报，不重复拉起
    pre = ("cd %s && L=%s/daemon.lock; "
           "if [ -f \"$L/pid\" ]; then P=$(cat \"$L/pid\"); "
           "if kill -0 \"$P\" 2>/dev/null; then echo MM_ALIVE:$P; else echo MM_STALE:$P; rm -rf \"$L\"; fi; "
           "else echo MM_FREE; fi; rm -f %s"
           % (shlex.quote(sdir), shlex.quote(sdir), shlex.quote(posixpath.join(sdir, "state.txt"))))
    pre_res = _exec_full(conn, "mkdir -p %s && %s" % (shlex.quote(sdir), pre), timeout=90)
    pre_out = (pre_res.get("output") or "")
    if "MM_ALIVE:" in pre_out:
        alive_pid = pre_out.split("MM_ALIVE:", 1)[1].split()[0].strip()
        rec = _registry_touch(_registry_upsert({
            "id": sid, "node": node_name, "dir": sdir, "env": env,
            "created": rc._now(), "status": "active", "pid": alive_pid,
        }), status="active", pid=alive_pid)
        return rc._ok({
            "status": "exists", "session_id": sid, "node": node_name, "dir": sdir,
            "pid": alive_pid,
            "summary": "该会话目录下已有常驻 R 进程在跑（pid=%s），没有重复拉起。" % alive_pid,
            "note": "直接用 action='session_exec' 投代码；要重启用 session_stop 再 session_start。",
        })

    # 1) daemon 脚本就位 + Rscript 定位
    try:
        deploy = _deploy_daemon(conn, bin_dir)
    except RuntimeError as exc:
        return rc._err(str(exc), node=node_name)
    probe = _probe_rscript(conn, sess, env, str(args.get("rscript") or "").strip())
    if not probe.get("ok"):
        return rc._err(
            "节点 %s 上没找到可用的 Rscript（env=%s）。" % (node_name, env),
            node=node_name, candidates=probe.get("candidates"),
            raw=probe.get("raw"),
            hint=("给一个绝对路径：action='session_start', rscript='/path/to/envs/R4.41/bin/Rscript'；"
                  "或在 config.yaml 的 remote.session 里写 rscript/roots/env；"
                  "装新环境请到 ssh0（唯一有外网的节点）装进自己的 env 目录。"))
    rscript = probe["rscript"]

    # 2) 拉起 daemon（setsid 优先，-f 有的发行版不支持；nohup 兜底），等 state.txt 出现
    daemon_path = posixpath.join(bin_dir, "r_session_daemon.R")
    log_path = posixpath.join(sdir, "session.log")
    state_path = posixpath.join(sdir, "state.txt")
    inner = "%s %s --dir %s --rscript %s" % (shlex.quote(rscript), shlex.quote(daemon_path),
                                             shlex.quote(sdir), shlex.quote(rscript))
    launch = "\n".join([
        "cd %s || exit 1" % shlex.quote(sdir),
        "if command -v setsid >/dev/null 2>&1; then "
        "if setsid -f true >/dev/null 2>&1; then LAUNCH='setsid -f'; else LAUNCH='setsid'; fi; "
        "else LAUNCH=''; fi",
        ("if [ -n \"$LAUNCH\" ]; then $LAUNCH nohup %s >> %s 2>&1 < /dev/null & "
         "else nohup %s >> %s 2>&1 < /dev/null & fi"
         % (inner, shlex.quote(log_path), inner, shlex.quote(log_path))),
        "for i in $(seq 1 30); do [ -s %s ] && break; sleep 1; done" % shlex.quote(state_path),
        "cat %s 2>/dev/null" % shlex.quote(state_path),
        "echo '==LOG=='",
        "tail -n 20 %s 2>/dev/null" % shlex.quote(log_path),
    ])
    launch_res = _exec_full(conn, launch, timeout=120)
    launch_out = launch_res.get("output") or ""
    state = _parse_state(launch_out.split("==LOG==")[0])
    if not state.get("pid"):
        return rc._err(
            "daemon 启动后 30 秒内没写出 state.txt（节点 %s）。" % node_name,
            node=node_name, dir=sdir, log_tail=rc._truncate(launch_out, 3000),
            hint="看 log_tail 里的 R 报错；常见：Rscript 路径不对 / 该目录权限 / setsid 不可用。")
    pid = str(state.get("pid"))
    verify = _exec_full(conn, (
        'P=$(sed -n "s/^pid=//p" %s | head -n1); '
        'if [ -n "$P" ] && kill -0 "$P" 2>/dev/null; then '
        'ps -p "$P" -o pid,rss,etime,stat,args 2>/dev/null | tail -n +2 | head -n2; '
        'echo MM_ALIVE; else echo MM_DEAD; fi'
        % shlex.quote(state_path)), timeout=60)
    verify_out = (verify.get("output") or "").strip()
    if "MM_ALIVE" not in verify_out:
        return rc._err("daemon 进程没活下来（state 有 pid=%s 但进程不存在）。" % pid,
                       node=node_name, dir=sdir, log_tail=rc._truncate(launch_out, 3000))

    rec = _registry_upsert({
        "id": sid, "node": node_name, "host": node.get("host"), "user": node.get("user"),
        "dir": sdir, "root": root, "bin_dir": bin_dir, "env": env, "rscript": rscript,
        "r_version": probe.get("version") or state.get("r_version") or "",
        "input": input_path, "object": obj_name or "", "title": title,
        "created": rc._now(), "last_active": rc._now(), "last_cmd_at": "",
        "status": "active", "pid": pid, "version": SESSION_VERSION,
        "daemon_md5": deploy.get("md5") or "",
    })
    payload = {
        "status": "ok", "session_id": sid, "node": node_name, "dir": sdir,
        "pid": pid, "rscript": rscript, "r_version": rec["r_version"], "env": env,
        "daemon": {"deployed": bool(deploy.get("deployed")), "path": daemon_path},
        "ps": verify_out,
        "state": state,
    }

    # 3) 输入文件：体积/内存提示 + 任务标记（持久化动作本身就是「要不要持久化」的答案）
    input_note = ""
    if input_path:
        size_res = _exec_full(conn, "stat -c %%s %s 2>/dev/null" % shlex.quote(input_path), timeout=60)
        try:
            input_bytes = int((size_res.get("output") or "0").strip() or 0)
        except Exception:
            input_bytes = 0
        if not input_bytes:
            return rc._ok(dict(payload, warning="input 路径在节点上不存在或不是文件：%s" % input_path,
                               hint="确认路径后重发；也可以先不读文件，用 session_exec 自己读。"))
        try:
            min_mb = float(cfg.get("persist_min_mb") or 100)
        except Exception:
            min_mb = 100.0
        mem_res = _exec_full(conn, "free -g 2>/dev/null | awk '/Mem:/{print $2\" \"$7}'", timeout=60)
        mem_parts = (mem_res.get("output") or "").strip().split()
        mem_note = ""
        try:
            total_gb, avail_gb = float(mem_parts[0]), float(mem_parts[1])
            need_gb = input_bytes / 1073741824.0
            mem_note = "节点内存：总 %.0fGB / 可用 %.0fGB；输入 %.2fGB。" % (total_gb, avail_gb, need_gb)
            if need_gb > 0.6 * max(avail_gb, 0.1):
                mem_note += " ⚠️ 输入偏大，读入后可能远超文件体积（Seurat 常 3~5 倍），注意 OOM。"
        except Exception:
            mem_note = ""
        try:
            from memomics.bio_tools import large_cache as lc
            lc.new_marker(
                task_id=sid, title="常驻会话 · %s" % title,
                inputs=[{"path": input_path, "size": input_bytes,
                         "size_h": rc._human_bytes(input_bytes),
                         "kind": "seurat_or_r_object"}],
                cache_root=sdir,
                artifacts=[sdir, posixpath.join(sdir, "ckpt")],
                remote=True,
                note="集群常驻 R 会话：读一次进内存，后续 FindMarkers/CellChat/参数扫描复用；不是精简缓存。",
                cache_scope="内存常驻对象（活着的 R 进程）+ 可选检查点 ckpt/*.rds",
                session_dir=sdir,
                not_included=[],
            )
            input_note = "已落任务标记（large_cache task_id=%s）。" % sid
        except Exception as exc:  # 标记失败不该拦住分析
            input_note = "任务标记没落上（%s），不影响会话。" % exc

        # 4) 同步读入（这就是「读一次」）
        code = _load_code(input_path, obj_name)
        sub = _submit(conn, sdir, code, op="load")
        if not sub.get("ok"):
            return rc._ok(dict(payload, warning=sub.get("error") or "请求投递失败"))
        wait = int(float(args.get("load_timeout") or sess.get("load_timeout") or 1800))
        parsed = _await_res(conn, sdir, sub["id"], wait)
        if not parsed.get("ready"):
            _registry_touch(rec, loading=True)
            return rc._ok(dict(payload, status="loading", request_id=sub["id"],
                               summary="会话已起，但 %d 秒内没读完输入（大文件正常）。" % wait,
                               hint="用 action='session_status', session_id='%s' 看进度（daemon 还在读）。" % sid,
                               mem_note=mem_note))
        payload["load"] = {
            "request_id": sub["id"], "status": parsed["status"],
            "seconds": round(int(parsed.get("ms") or 0) / 1000.0, 1),
            "output": rc._truncate(parsed.get("output") or "", 6000),
            "error": parsed.get("error") or "",
            "readrds_calls": parsed.get("readrds_calls"),
        }
        payload["object"] = obj_name
        if parsed["status"] == "error":
            payload["status"] = "error"
            payload["error"] = "读入失败：%s" % (parsed.get("error") or "")
        _registry_touch(rec, last_status=parsed["status"])

    if restore:
        code = _restore_code("" if restore.lower() in ("latest", "1", "true", "最新") else restore)
        sub = _submit(conn, sdir, code, op="restore")
        if sub.get("ok"):
            parsed = _await_res(conn, sdir, sub["id"], int(float(args.get("wait") or 600)))
            payload["restore"] = {
                "status": parsed.get("status") if parsed.get("ready") else "running",
                "output": rc._truncate((parsed.get("output") or ""), 4000),
                "error": (parsed.get("error") or "") if parsed.get("ready") else "",
            }

    if input_note:
        payload["marker_note"] = input_note
    if input_path:
        payload.setdefault("mem_note", mem_note)
        payload["summary"] = ("会话 %s 已在节点 %s 常驻（pid=%s）；已经读过一次 %s，"
                              "后续 session_exec 直接复用内存里的对象，不再回读文件。"
                              % (sid, node_name, pid, input_path))
    else:
        payload["summary"] = ("会话 %s 已在节点 %s 常驻（pid=%s）。投代码用 action='session_exec'。"
                              % (sid, node_name, pid))

    # 同节点会话数提示（不硬拦）
    try:
        others = [r for r in _load_registry().values()
                  if isinstance(r, dict) and r.get("node") == node_name
                  and r.get("id") != sid and str(r.get("status") or "") != "stopped"]
        if len(others) >= int(sess.get("max_sessions") or 2):
            payload["advisory"] = ("该节点还有 %d 个未停止的常驻会话（建议上限 %s/台）；"
                                   "不用的记得 session_stop，别白占内存。"
                                   % (len(others), sess.get("max_sessions")))
    except Exception:
        pass
    return rc._ok(payload)


# ---------------------------------------------------------------------------
# 动作：session_exec / save / restore
# ---------------------------------------------------------------------------


def _run_code_action(cfg: dict, args: dict, code: str, op: str, default_wait_key: str,
                     ok_payload=None) -> str:
    rec, node, node_name, err = _resolve_session(cfg, args)
    if err:
        return err
    sess = _session_cfg(cfg, node)
    conn = rc._get_conn(node)
    sub = _submit(conn, rec["dir"], code, op=op)
    if not sub.get("ok"):
        return rc._err(sub.get("error") or "请求投递失败", session_id=rec.get("id"), node=node_name)
    wait = _wait_seconds(args, sess, default_key=default_wait_key)
    if rc._truthy(args.get("async")):
        wait = 0
    base = {
        "session_id": rec.get("id"), "node": node_name, "request_id": sub["id"],
        "dir": rec.get("dir"),
    }
    if wait <= 0:
        _registry_touch(rec, last_cmd_at=rc._now(), last_status="queued")
        return rc._ok(dict(base, status="accepted",
                           hint=("请求已投递（不等待）。用 action='session_status', session_id='%s' "
                                 "看进度；结果文件在 done/%s.res.txt。" % (rec.get("id"), sub["id"]))))
    parsed = _await_res(conn, rec["dir"], sub["id"], wait)
    if not parsed.get("ready"):
        _registry_touch(rec, last_cmd_at=rc._now(), last_status="running")
        return rc._ok(dict(base, status="running",
                           summary="%d 秒内还没出结果（可能还在跑）。" % wait,
                           hint=("用 action='session_status', session_id='%s' 看 busy 状态；"
                                 "长命令下次可以用 async=true。" % rec.get("id"))))
    ms = 0
    try:
        ms = int(float(parsed.get("ms") or 0))
    except Exception:
        ms = 0
    payload = dict(base)
    payload.update({
        "status": parsed["status"],
        "seconds": round(ms / 1000.0, 1),
        "output": rc._truncate(parsed.get("output") or "", cfg.get("max_output_chars") or 20000),
        "warnings": rc._truncate(parsed.get("warnings") or "", 4000),
        "error": parsed.get("error") or "",
        "readrds": {"calls": parsed.get("readrds_calls"),
                    "recent": parsed.get("reads", [])[-5:]},
        "session_objects": parsed.get("objects"),
        "rss_kb": parsed.get("rss_kb"),
        "res_path": parsed.get("res_path"),
    })
    if ok_payload:
        payload.update(ok_payload(parsed))
    _registry_touch(rec, last_cmd_at=rc._now(), last_status=parsed["status"],
                    readrds_calls=parsed.get("readrds_calls"))
    if payload.get("status") == "ok" and parsed.get("readrds_calls") is not None:
        payload["readrds_note"] = ("本会话累计 readRDS %s 次"
                                   % parsed.get("readrds_calls"))
    return rc._ok(payload)


def action_exec(cfg: dict, args: dict) -> str:
    code = str(args.get("code") or args.get("command") or "")
    if not code.strip():
        return action_status(cfg, args)   # 空输入 = 看状态（WebUI 控制台的贴心默认）
    return _run_code_action(cfg, args, code, op="eval", default_wait_key="wait")


def action_save(cfg: dict, args: dict) -> str:
    name = str(args.get("name") or "").strip()
    objects = args.get("objects") or []
    if isinstance(objects, str):
        objects = [o.strip() for o in objects.replace(",", " ").split() if o.strip()]
    code = _save_code(name, objects)

    def _extra(parsed):
        ckpt = ""
        for line in (parsed.get("output") or "").splitlines():
            if line.startswith("MM_CKPT:"):
                ckpt = line[len("MM_CKPT:"):].strip()
        out = {"ckpt": ckpt}
        return out

    return _run_code_action(cfg, args, code, op="save", default_wait_key="save_wait",
                            ok_payload=_extra)


def action_restore(cfg: dict, args: dict) -> str:
    path = str(args.get("name") or args.get("restore") or "").strip()
    if path.lower() in ("latest", "最新"):
        path = ""
    code = _restore_code(path)
    return _run_code_action(cfg, args, code, op="restore", default_wait_key="save_wait")


# ---------------------------------------------------------------------------
# 动作：session_status / stop / list
# ---------------------------------------------------------------------------


def _status_command(sdir: str) -> str:
    q = shlex.quote
    st = posixpath.join(sdir, "state.txt")
    return "\n".join([
        "cd %s 2>/dev/null || { echo '==STATE=='; echo 'dir_missing=1'; exit 0; }" % q(sdir),
        "echo '==STATE=='", "cat %s 2>/dev/null" % q(st),
        "echo '==PS=='",
        'P=$(sed -n "s/^pid=//p" %s 2>/dev/null | head -n1)' % q(st),
        ('if [ -n "$P" ] && kill -0 "$P" 2>/dev/null; then '
         'ps -p "$P" -o pid,rss,etime,stat,args 2>/dev/null | tail -n +2 | head -n2; echo MM_ALIVE; '
         'else echo MM_DEAD; fi'),
        "echo '==QUEUE=='",
        "ls -1 queue/*.req.R 2>/dev/null | head -n 20; echo '--run--'; ls -1 run/*.req.R 2>/dev/null | head -n 20",
        "echo '==DONE=='", "ls -1t done/*.res.txt 2>/dev/null | head -n 5",
        "echo '==LASTRES=='",
        "tail -n 40 $(ls -1t done/*.res.txt 2>/dev/null | head -n1) 2>/dev/null",
        "echo '==CKPT=='", "ls -lht ckpt/*.rds 2>/dev/null | head -n 5",
        "echo '==LOG=='", "tail -n 12 session.log 2>/dev/null",
    ])


def _rss_h(state: dict) -> str:
    try:
        kb = int(float(state.get("rss_kb") or -1))
    except Exception:
        kb = -1
    return rc._human_bytes(kb * 1024) if kb > 0 else ""


def action_status(cfg: dict, args: dict) -> str:
    sid = str(args.get("session_id") or args.get("command") or "").strip()
    rec, node, node_name, err = _resolve_session(cfg, dict(args, session_id=sid) if sid else args)
    if err:
        return err
    conn = rc._get_conn(node)
    sdir = str(rec.get("dir") or "")
    res = _exec_disp(conn, _status_command(sdir), timeout=90)
    out = res.get("output") or ""
    sec = _split_sections(out)
    state = _parse_state(sec.get("STATE") or "")
    ps_txt = (sec.get("PS") or "").strip()
    alive = "MM_ALIVE" in ps_txt
    busy = str(state.get("status") or "") == "busy"
    payload = {
        "status": "ok" if alive else "stopped",
        "session_id": rec.get("id"), "node": node_name, "dir": sdir,
        "alive": alive, "daemon_status": state.get("status") or ("unknown" if alive else "stopped"),
        "busy": busy, "current_request": "" if state.get("current", "-") == "-" else state.get("current"),
        "pid": state.get("pid") or rec.get("pid") or "",
        "r_version": state.get("r_version") or rec.get("r_version") or "",
        "started": state.get("started") or "",
        "updated": state.get("updated") or "",
        "uptime_note": "心跳 updated 超过 10 秒没动 = daemon 可能卡住或死了",
        "jobs_done": state.get("jobs_done") or "0",
        "readrds_calls": state.get("readrds_calls") or "0",
        "objects": state.get("objects") or "0",
        "rss_h": _rss_h(state),
        "ps": ps_txt,
        "queue": (sec.get("QUEUE") or "").strip(),
        "done_recent": (sec.get("DONE") or "").strip(),
        "last_result_tail": rc._truncate((sec.get("LASTRES") or "").strip(), 4000),
        "ckpt_recent": (sec.get("CKPT") or "").strip(),
        "log_tail": rc._truncate((sec.get("LOG") or "").strip(), 3000),
        "input": rec.get("input") or "", "object": rec.get("object") or "",
    }
    _registry_touch(rec, status="active" if alive else "stopped",
                    pid=payload["pid"] or rec.get("pid"),
                    readrds_calls=state.get("readrds_calls") or rec.get("readrds_calls"))
    if not alive:
        payload["hint"] = ("daemon 进程不在了。对象已经没了，但 ckpt/ 里的检查点还在——"
                           "可以 action='session_start', session_id='%s', restore='latest' 拉回来"
                           "（不用重读 input）。" % rec.get("id"))
    return rc._ok(payload)


def action_stop(cfg: dict, args: dict) -> str:
    rec, node, node_name, err = _resolve_session(cfg, args)
    if err:
        return err
    sess = _session_cfg(cfg, node)
    conn = rc._get_conn(node)
    sdir = str(rec.get("dir") or "")
    out = {"session_id": rec.get("id"), "node": node_name, "dir": sdir}

    if rc._truthy(args.get("save")):
        code = _save_code(str(args.get("name") or "").strip(), None)
        sub = _submit(conn, sdir, code, op="save")
        if sub.get("ok"):
            parsed = _await_res(conn, sdir, sub["id"], _wait_seconds(args, sess, "save_wait"))
            out["save"] = {"status": parsed.get("status") if parsed.get("ready") else "running",
                           "output": rc._truncate((parsed.get("output") or ""), 3000)}

    sub = _submit(conn, sdir, "mm_quit()", op="quit")
    if not sub.get("ok"):
        return rc._err(sub.get("error") or "退出请求投递失败", **out)
    _await_res(conn, sdir, sub["id"], 90)

    # 二次确认 + 兜底 kill（daemon 卡在长任务里时 mm_quit 要等它跑完）
    state_path = posixpath.join(sdir, "state.txt")
    check = _exec_full(conn, (
        'P=$(sed -n "s/^pid=//p" %s 2>/dev/null | head -n1); '
        'if [ -n "$P" ] && kill -0 "$P" 2>/dev/null; then '
        'echo MM_STILL_ALIVE:$P; kill -TERM "$P" 2>/dev/null; sleep 2; '
        'if kill -0 "$P" 2>/dev/null; then kill -KILL "$P" 2>/dev/null; sleep 1; fi; '
        'if kill -0 "$P" 2>/dev/null; then echo MM_KILL_FAILED:$P; else echo MM_KILLED:$P; fi; '
        'else echo MM_DEAD; fi' % shlex.quote(state_path)), timeout=90)
    chk = (check.get("output") or "").strip()
    out["exit"] = ("killed" if "MM_KILLED" in chk else
                   ("kill_failed" if "MM_KILL_FAILED" in chk else "clean"))
    out["detail"] = chk
    _registry_touch(rec, status="stopped")
    out["status"] = "ok"
    out["summary"] = ("会话 %s 已停止（%s）。内存里的对象随之释放；要留住结果请确认 ckpt/ 里有检查点。"
                      % (rec.get("id"), out["exit"]))
    return rc._ok(out)


def action_list(cfg: dict, args: dict) -> str:
    reg = _load_registry()
    rows = []
    for sid, rec in reg.items():
        if not isinstance(rec, dict):
            continue
        rows.append({
            "id": rec.get("id") or sid,
            "node": rec.get("node") or "",
            "title": rec.get("title") or "",
            "env": rec.get("env") or "",
            "r_version": rec.get("r_version") or "",
            "input": rec.get("input") or "",
            "object": rec.get("object") or "",
            "dir": rec.get("dir") or "",
            "created": rec.get("created") or "",
            "last_active": rec.get("last_active") or "",
            "status": rec.get("status") or "unknown",
            "pid": rec.get("pid") or "",
            "last_status": rec.get("last_status") or "",
            "readrds_calls": rec.get("readrds_calls"),
        })
    rows.sort(key=lambda r: str(r.get("last_active") or r.get("created") or ""), reverse=True)

    live = rc._truthy(args.get("live"))
    if live:
        for row in rows[:5]:
            try:
                rec, node, node_name, err = _resolve_session(cfg, {"session_id": row["id"]})
                if err or not rec:
                    continue
                conn = rc._get_conn(node)
                res = _exec_disp(conn, _status_command(rec.get("dir") or ""), timeout=90)
                out_text = res.get("output") if isinstance(res, dict) else str(res)
                sec = _split_sections(out_text or "")
                state = _parse_state(sec.get("STATE") or "")
                ps_txt = (sec.get("PS") or "")
                row["alive"] = "MM_ALIVE" in ps_txt
                row["daemon_status"] = state.get("status") or ""
                row["readrds_calls"] = state.get("readrds_calls") or row.get("readrds_calls")
                row["rss_h"] = _rss_h(state)
            except Exception as exc:
                row["live_error"] = str(exc)
    payload = {
        "status": "ok",
        "count": len(rows),
        "sessions": rows,
        "registry": str(_sessions_path()),
        "note": ("常驻会话是本机的账本 + 集群上的真进程；status 是账本里的快照，"
                 "加 live=true 会逐台连上去核实活没活。不用的会话记得 session_stop。"),
    }
    return rc._ok(payload)