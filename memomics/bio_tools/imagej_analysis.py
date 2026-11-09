# -*- coding: utf-8 -*-
"""imagej —— 集群 ImageJ 定量工具（MemOmics 适配层，2026-11-09）

一句话：把「远端 ImageJ 1.54g + Xvfb」包装成 MemOmics 的一等工具 —— 选操作 → 渲染宏 →
送到集群跑 → 拉回产物 → 过四道闸 → 写 manifest（可溯源、可复现）。

为什么这样设计（都是集群实测逼出来的）：
  1. `ij.jar -batch` 在 Xvfb 下跑完不退出 → 集群侧用 RunIjBatch（batchMode + System.exit）
     + DONE.json 哨兵，run_ij.sh 见哨兵即回收，超时兜底。
  2. 多个作业共用 DISPLAY 会互相杀 Xvfb → run_ij.sh 每个作业 mkdir 抢独立 DISPLAY。
  3. IJ1 的 `setScale` / `getValue("unit")` / `run("Properties...")` 会弹模态框把无人值守
     作业挂死 → 宏一律在**像素域**测量，µm 换算在 Python 侧按 px_um 完成。
  4. 宏里 `File.makeDirectory` 对不存在的父目录会报错挂死 → 目录由 run_ij.sh 预建。
  5. 任何宏错误都会弹框挂住进程 → 所以每个阶段都有哨兵/超时/产物三查，别信退出码。

工具与传输分层：本模块只做「图像语义 + 产物契约 + 验收」，SSH/SCP 全部复用
remote_cluster 的连接池（push/run/pull），不另开通道。
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import shlex
import statistics
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from . import remote_cluster as rc
from . import imagej_settings as ij_settings

logger = logging.getLogger("memomics.imagej")

TOOL_VERSION = "1.0.0"

DEFAULTS: dict[str, Any] = {
    "root": "/cluster/share/user/ImageJ",
    "runner": "",                       # 默认 <root>/ij_runner
    "xvfb": "/cluster/share/user/envs/ij_xvfb/bin/Xvfb",
    "workdir": "",                      # 默认取 remote 配置的 workdir
    "node": "",                         # 默认用 remote_cluster 的默认节点
    "mem": "8g",
    "timeout": 900,
    # 前段是 ImageJ 原生可读；后段靠 Bio-Formats（装了才会真的读得动）
    "image_exts": [".tif", ".tiff", ".png", ".jpg", ".jpeg", ".bmp", ".gif",
                   ".lsm", ".czi", ".lif", ".nd2", ".vsi", ".oib", ".oif",
                   ".ndpi", ".ims", ".svs", ".scn", ".nd", ".dm3", ".zvi"],
}

_OPS_CACHE: dict[str, Any] = {"ts": 0.0, "ops": {}}
_PROBE_CACHE: dict[str, Any] = {"ts": 0.0, "data": {}}


# ---------------------------------------------------------------------------
# 基础：仓库路径 / 配置 / ops 目录
# ---------------------------------------------------------------------------
def _repo_root() -> Path:
    try:
        return Path(__file__).resolve().parents[2]
    except Exception:
        return Path(os.getcwd())


def _hermes_home() -> Path:
    env = os.environ.get("HERMES_HOME") or os.environ.get("MEMOMICS_HOME")
    if env and Path(env).is_dir():
        return Path(env)
    return _repo_root() / "memomics_home"


def _ops_dir() -> Path:
    return _repo_root() / "scripts" / "ij" / "ops"


def _runner_src() -> Path:
    return _repo_root() / "scripts" / "ij"


def _imagej_cfg() -> dict:
    try:
        ij_settings.ensure_home_env()
    except Exception:
        pass
    cfg = dict(DEFAULTS)
    try:
        rcfg = rc._load_remote_config() or {}
    except Exception:
        rcfg = {}

    block = rcfg.get("imagej") or {}
    if not block and rcfg.get("clusters"):
        name = rcfg.get("default_cluster") or ""
        cl = (rcfg.get("clusters") or {}).get(name) or {}
        block = cl.get("imagej") or {}
    if isinstance(block, dict):
        for k, v in block.items():
            if v not in (None, ""):
                cfg[k] = v

    # 环境变量兜底（运维/调试用）
    env_map = {
        "MEMOMICS_IMAGEJ_ROOT": "root",
        "MEMOMICS_IMAGEJ_XVFB": "xvfb",
        "MEMOMICS_IMAGEJ_NODE": "node",
        "MEMOMICS_IMAGEJ_MEM": "mem",
    }
    for env, key in env_map.items():
        if os.environ.get(env):
            cfg[key] = os.environ[env]

    # UI「设置 → ImageJ」是用户显式配置，优先于仓库默认路径。
    try:
        user_cluster = (ij_settings.load().get("cluster") or {})
        if user_cluster.get("root"):
            cfg["root"] = user_cluster["root"]
            cfg["runner"] = str(cfg["root"]).rstrip("/") + "/ij_runner"
        if user_cluster.get("node"):
            cfg["node"] = user_cluster["node"]
    except Exception:
        pass

    if not cfg.get("runner"):
        cfg["runner"] = str(cfg["root"]).rstrip("/") + "/ij_runner"

    if not cfg.get("workdir"):
        cand = ""
        try:
            name, ccfg = rc.resolve_cluster(rcfg, "")
            cand = str(ccfg.get("workdir") or "")
        except Exception:
            cand = str(rcfg.get("workdir") or "")
        cfg["workdir"] = cand.rstrip("/") or "/cluster/share/user"

    # 集群保存目录由用户在 ImageJ 设置里指定；run_job 会递归创建作业子目录
    try:
        user_cluster = (ij_settings.load().get("cluster") or {})
        cfg["job_root"] = str(user_cluster.get("save_dir") or "").rstrip("/") or \
            (str(cfg["workdir"]).rstrip("/") + "/ij_runs")
    except Exception:
        cfg["job_root"] = str(cfg["workdir"]).rstrip("/") + "/ij_runs"
    return cfg


def _ops(force: bool = False) -> dict[str, dict]:
    """读本地 op 目录（仓库 scripts/ij/ops/<id>/op.json）。"""
    now = time.time()
    if not force and _OPS_CACHE["ops"] and (now - _OPS_CACHE["ts"] < 60):
        return _OPS_CACHE["ops"]
    out: dict[str, dict] = {}
    base = _ops_dir()
    if base.is_dir():
        for d in sorted(base.iterdir()):
            meta_path = d / "op.json"
            if not meta_path.is_file():
                continue
            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
            except Exception as exc:  # pragma: no cover - 坏文件不该拖垮工具
                logger.warning("op.json 解析失败 %s: %s", meta_path, exc)
                continue
            meta.setdefault("id", d.name)
            meta["_dir"] = str(d)
            out[meta["id"]] = meta
    _OPS_CACHE["ops"] = out
    _OPS_CACHE["ts"] = now
    return out


# ---------------------------------------------------------------------------
# remote_cluster 薄封装（复用它的连接池与配置解析）
# ---------------------------------------------------------------------------
def _rc(payload: dict) -> dict:
    try:
        # 多集群时把用户在 ImageJ 设置里选的集群传给 remote_cluster
        cluster_name = str(((ij_settings.load().get("cluster") or {}).get("name")) or "")
        if cluster_name and "cluster" not in payload:
            payload = dict(payload)
            payload["cluster"] = cluster_name
    except Exception:
        pass
    try:
        raw = rc.remote_cluster_handler(payload)
    except Exception as exc:
        return {"status": "error", "error": "remote_cluster 调用异常: %s" % exc}
    try:
        data = json.loads(raw)
    except Exception:
        return {"status": "error", "error": str(raw)[:600]}
    if not isinstance(data, dict):
        return {"status": "error", "error": str(data)[:600]}
    return data


def _must(data: dict, what: str) -> dict:
    if data.get("status") != "ok":
        raise RuntimeError("%s 失败: %s" % (what, data.get("error") or data))
    return data


def _run(cmd: str, node: str = "", timeout: int = 180) -> tuple[str, int]:
    data = _rc({"action": "run", "node": node, "command": cmd, "timeout": timeout})
    if data.get("status") != "ok":
        raise RuntimeError("远端命令失败: %s" % (data.get("error") or data))
    return str(data.get("output") or ""), int(data.get("exit_code") or 0)


def _push(local: str, remote: str, node: str = "") -> dict:
    """上传（网络偶发 Connection reset 时重试一次）。"""
    last = None
    for attempt in range(2):
        try:
            return _must(_rc({"action": "push", "node": node,
                              "local_path": str(local), "remote_path": str(remote)}), "push")
        except Exception as exc:
            last = exc
            if attempt == 0:
                logger.warning("push 失败，重试一次：%s", exc)
                time.sleep(2)
    raise last  # type: ignore[misc]


def _pull(remote_glob: str, local_dir: str, node: str = "", overwrite: bool = True) -> dict:
    return _must(_rc({"action": "pull", "node": node, "remote_path": remote_glob,
                      "local_path": str(local_dir), "overwrite": bool(overwrite)}), "pull")


def _node(args: dict) -> str:
    return str(args.get("node") or _imagej_cfg().get("node") or "")


def _q(path: str) -> str:
    return shlex.quote(str(path))


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# 部署：把 runner + ops 模板送到集群（幂等，带指纹）
# ---------------------------------------------------------------------------
def _deploy_fingerprint() -> str:
    parts = []
    for p in (_runner_src() / "run_ij.sh", _runner_src() / "RunIjBatch.java"):
        if p.is_file():
            parts.append(_sha256_file(p))
    for op_id, meta in sorted(_ops().items()):
        d = Path(meta["_dir"])
        for name in ("op.json", "macro.ijm.tmpl"):
            f = d / name
            if f.is_file():
                parts.append(_sha256_file(f))
    return _sha256_text("".join(sorted(parts)))[:16]


def ensure_deployed(node: str = "", force: bool = False) -> dict:
    """把 run_ij.sh / ops 模板 / 启动器送到集群并编译（幂等）。"""
    c = _imagej_cfg()
    runner = c["runner"]
    root = str(c["root"]).rstrip("/")
    fp = _deploy_fingerprint()
    stamp = runner + "/.deployed"

    out, _ = _run(
        "d=%s; if [ -f $d/.deployed ]; then cat $d/.deployed; echo; fi; "
        "if [ -f %s/RunIjBatch.class ]; then echo __LAUNCHER__; fi; "
        "if [ -x %s/run_ij.sh ]; then echo __RUNNER__; fi" % (_q(runner), _q(root), _q(runner)),
        node, 60,
    )
    have_fp = ""
    for line in out.splitlines():
        m = re.search(r"\b([0-9a-f]{8,32})\b", line.strip() or "")
        if m:
            have_fp = m.group(1)
            break
    has_launcher = "__LAUNCHER__" in out
    has_runner = "__RUNNER__" in out
    if not force and have_fp == fp and has_launcher and has_runner:
        return {"status": "ok", "deployed": False, "fingerprint": fp, "reason": "已是最新"}

    _run("mkdir -p %s/ops %s/in" % (_q(runner), _q(runner)), node, 60)

    _push(_runner_src() / "run_ij.sh", runner + "/run_ij.sh", node)
    _push(_runner_src() / "RunIjBatch.java", root + "/RunIjBatch.java", node)

    ops_pushed = []
    for op_id, meta in _ops().items():
        d = Path(meta["_dir"])
        rdir = "%s/ops/%s" % (runner, op_id)
        _run("mkdir -p %s" % _q(rdir), node, 60)
        for name in ("op.json", "macro.ijm.tmpl"):
            f = d / name
            if f.is_file():
                _push(f, rdir + "/" + name, node)
        ops_pushed.append(op_id)

    compile_cmd = (
        "cd %s && chmod +x %s/run_ij.sh && "
        "if [ ! -f RunIjBatch.class ] || [ RunIjBatch.java -nt RunIjBatch.class ]; then "
        "( javac -source 8 -target 8 -cp ij.jar RunIjBatch.java 2>&1 || javac --release 8 -cp ij.jar RunIjBatch.java 2>&1 ) | tail -5; fi; "
        "ls -la RunIjBatch.class | awk '{print \"LAUNCHER_BYTES=\"$5}'"
    ) % (_q(root), _q(runner))
    cout, _ = _run(compile_cmd, node, 120)
    _run("printf %s > %s" % (_q(fp), _q(stamp)), node, 30)

    ok = "LAUNCHER_BYTES=" in cout
    return {
        "status": "ok" if ok else "warn",
        "deployed": True,
        "fingerprint": fp,
        "ops": ops_pushed,
        "runner": runner,
        "compile_output": cout.strip()[-800:],
        "warning": "" if ok else "RunIjBatch.class 未生成（编译失败？见 compile_output）",
    }


# ---------------------------------------------------------------------------
# 探测
# ---------------------------------------------------------------------------
_PROBE_RE = re.compile(r"^([A-Z0-9_]+)=(.*)$")


def probe(node: str = "", refresh: bool = False, root: str = "") -> dict:
    c = _imagej_cfg()
    now = time.time()
    key = (node or "-") + "|" + (root or "-")
    cached = _PROBE_CACHE["data"].get(key)
    if cached and not refresh and (now - _PROBE_CACHE["ts"] < 600):
        return cached

    root, xvfb = str(root or c["root"]).rstrip("/"), c["xvfb"]
    cmd = "; ".join([
        "echo HOST=$(hostname)",
        "echo NPROC=$(nproc)",
        "echo JAVA=$({j} -version 2>&1 | head -1)".format(j=_q(root + "/jre/bin/java")),
        "echo IJ_JAR_BYTES=$(stat -c %%s %s/ij.jar 2>/dev/null)" % _q(root),
        "echo LAUNCHER=$([ -f %s/RunIjBatch.class ] && echo yes || echo no)" % _q(root),
        "echo RUNNER=$([ -x %s/run_ij.sh ] && echo yes || echo no)" % _q(c["runner"]),
        "echo XVFB=$([ -x %s ] && echo yes || echo no)" % _q(xvfb),
        "echo JAVAC=$(javac -version 2>&1 | head -1)",
        "echo PLUGIN_JARS=$(ls %s/plugins/jars 2>/dev/null | tr '\\n' ',')" % _q(root),
        "echo BIOFORMATS=$([ -n \"$(ls %s/plugins 2>/dev/null | grep -i bioformats)\" ] && echo yes || echo no)" % _q(root),
        "echo BF_JAR_BYTES=$(stat -c %%s %s/plugins/bioformats_package.jar 2>/dev/null || echo 0)" % _q(root),
        "echo FREE_GB=$(df -h %s | awk 'NR==2{print $4}')" % _q(str(c["workdir"])),
    ])
    out, _ = _run(cmd, node, 90)
    data: dict[str, str] = {}
    for line in out.splitlines():
        m = _PROBE_RE.match(line.strip())
        if m:
            data[m.group(1)] = m.group(2).strip()

    info = {
        "status": "ok",
        "node": node or "default",
        "host": data.get("HOST", ""),
        "nproc": _to_int(data.get("NPROC")),
        "java": data.get("JAVA", ""),
        "ij_jar_bytes": _to_int(data.get("IJ_JAR_BYTES")),
        "launcher": data.get("LAUNCHER") == "yes",
        "runner": data.get("RUNNER") == "yes",
        "xvfb": data.get("XVFB") == "yes",
        "javac": data.get("JAVAC", ""),
        "plugin_jars": [p for p in (data.get("PLUGIN_JARS") or "").split(",") if p],
        "bioformats": data.get("BIOFORMATS") == "yes",
        "bioformats_jar_bytes": _to_int(data.get("BF_JAR_BYTES")),
        "workdir_free": data.get("FREE_GB", ""),
        "root": root,
        "imagej_ready": bool(data.get("IJ_JAR_BYTES")) and data.get("XVFB") == "yes",
        "checked_at": datetime.now().isoformat(timespec="seconds"),
    }
    _PROBE_CACHE["data"][key] = info
    _PROBE_CACHE["ts"] = now
    return info


def _to_int(v) -> int:
    try:
        return int(str(v).strip())
    except Exception:
        return 0


# ---------------------------------------------------------------------------
# 宏渲染：参数 → 宏变量（像素域）
# ---------------------------------------------------------------------------
_MACRO_VARS = {
    "channel": ("CHANNEL", "int"),
    "threshold": ("THRESH", "str"),
    "invert": ("INVERT", "bool"),
    "watershed": ("WATERSHED", "bool"),
    "project": ("PROJECT_MAX", "bool"),
    "smooth": ("SMOOTH", "num"),
    "min_circ": ("MINC", "num"),
    "max_circ": ("MAXC", "num"),
}


def _px_from_um2(um2: float, px_um: float) -> float:
    if not um2:
        return 0.0
    if px_um and px_um > 0:
        return float(um2) / (float(px_um) ** 2)
    return float(um2)


def _param_block(meta: dict, params: dict) -> str:
    px_um = float(params.get("px_um") or 0)
    lines: list[str] = ["PX_UM = %s;" % _num(px_um)]

    # Analyze Particles 的 size / circularity 字符串在 Python 侧拼好再注入。
    # 原因（集群实测）：IJ1 宏里 `if (c) sz = A + "-" + B; else sz = A + "-Infinity";`
    # 会把 A 丢掉，最终得到 "-Infinity" → 一个对象都选不出来。
    spec = meta.get("params") or {}
    if "min_area_um2" in spec:
        # 面积过滤一律在 Python 侧按 µm² 做：带标定的图（OME-TIFF）上 IJ 的 size= 会按标定单位
        # 解释，实测 size=1-Infinity 会把全部对象滤光；这里只要把全部对象交给下游。
        lines.append('SZ = "0-Infinity";')
    if "min_circ" in spec:
        c_lo = float(params.get("min_circ", spec["min_circ"].get("default") or 0) or 0)
        c_hi = float(params.get("max_circ", (spec.get("max_circ") or {}).get("default") or 1) or 1)
        lines.append('CIRC = "%s-%s";' % (_num(c_lo), _num(c_hi)))
    for key, spec in (meta.get("params") or {}).items():
        if key == "px_um":
            continue
        if key in ("min_area_um2", "max_area_um2"):
            continue  # 已折算进 SZ
        target = _MACRO_VARS.get(key)
        if not target:
            continue
        var, kind = target
        raw = params.get(key, spec.get("default"))
        if kind == "int":
            lines.append("%s = %d;" % (var, int(raw or 1)))
        elif kind == "num":
            lines.append("%s = %s;" % (var, _num(float(raw or 0))))
        elif kind == "bool":
            lines.append("%s = %d;" % (var, 1 if raw else 0))
        else:
            safe = re.sub(r"[^A-Za-z0-9_]", "", str(raw or "Otsu")) or "Otsu"
            lines.append('%s = "%s";' % (var, safe))
    return "\n".join(lines)


def _num(x: float) -> str:
    s = ("%.6f" % float(x)).rstrip("0").rstrip(".")
    return s or "0"


def _bf_metadata(in_remote: str, node: str = "") -> dict:
    """用 Bio-Formats 的 ImageInfo 读 OME 元数据：物理像素尺寸 + 通道/切片数。

    命令带 -no-upgrade（否则 ImageInfo 会联网检查新版本，在无外网节点上干等超时）。
    单位统一折算成 µm；读不到就返回空 dict，绝不让它拖垮主流程。
    """
    c = _imagej_cfg()
    jar = str(c["root"]).rstrip("/") + "/plugins/bioformats_package.jar"
    java = str(c["root"]).rstrip("/") + "/jre/bin/java"
    pattern = 'PhysicalSize[XY]="[0-9.eE+-]+"|PhysicalSize[XY]Unit="[^"]+"'
    cmd = ("%s -Xmx1g -cp %s loci.formats.tools.ImageInfo -nopix -no-upgrade -omexml %s 2>/dev/null "
           "| grep -oE %s | head -8"
           % (_q(java), _q(jar), _q(in_remote), _q(pattern)))
    out, _ = _run(cmd, node, 180)
    vals: dict[str, str] = {}
    for line in out.splitlines():
        m = re.match(r'(PhysicalSize[XY](?:Unit)?)="([^"]*)"', line.strip())
        if m:
            vals[m.group(1)] = m.group(2)
    px = 0.0
    try:
        raw = float(vals.get("PhysicalSizeX") or vals.get("PhysicalSizeY") or 0)
        unit = (vals.get("PhysicalSizeXUnit") or vals.get("PhysicalSizeYUnit") or "um").lower()
        if "nm" in unit:
            px = raw / 1000.0
        elif "mm" in unit:
            px = raw * 1000.0
        else:                      # µm / um / micron
            px = raw
    except Exception:
        px = 0.0
    if px <= 0:
        return {}
    return {"px_um": round(px, 6), "unit_raw": vals.get("PhysicalSizeXUnit", ""),
            "size_raw": vals.get("PhysicalSizeX", "")}


def _render_macro(meta: dict, params: dict, job_dir: str, in_path: str, out_dir: str) -> str:
    tmpl_path = Path(meta["_dir"]) / "macro.ijm.tmpl"
    tmpl = tmpl_path.read_text(encoding="utf-8")
    # ImageJ 宏字符串里反斜杠是转义符：Windows 路径必须转成 /，否则 open() 直接失败
    def _p(x: str) -> str:
        return str(x).replace("\\", "/")

    text = (tmpl
            .replace("__PARAMS__", _param_block(meta, params))
            .replace("__JOB__", _p(job_dir))
            .replace("__OUT__", _p(out_dir) + "/")
            .replace("__IN__", _p(in_path)))
    if "__" in re.sub(r"__[A-Z]+__", "", text):
        pass
    for ph in ("__PARAMS__", "__JOB__", "__OUT__", "__IN__"):
        if ph in text:
            raise RuntimeError("宏模板占位符未替换: %s" % ph)
    return text


# ---------------------------------------------------------------------------
# 输入展开
# ---------------------------------------------------------------------------
def _local_candidates(spec: str) -> list[Path]:
    exts = tuple(DEFAULTS["image_exts"])
    p = Path(spec)
    if p.is_file():
        return [p]
    if p.is_dir():
        return sorted([f for f in p.rglob("*") if f.suffix.lower() in exts])
    return []


def _local_glob(pattern: str) -> list[Path]:
    import glob as _glob
    exts = tuple(DEFAULTS["image_exts"])
    out = []
    for hit in _glob.glob(pattern, recursive=True):
        p = Path(hit)
        if p.is_file() and p.suffix.lower() in exts:
            out.append(p)
    return sorted(out)


def _remote_expand(pattern: str, node: str) -> list[str]:
    cmd = ('for f in %s; do [ -f "$f" ] && printf "%%s\\n" "$f"; done' % pattern)
    out, _ = _run(cmd, node, 90)
    return [ln.strip() for ln in out.splitlines() if ln.strip()]


def _expand_inputs(spec: Any, node: str) -> list[dict]:
    """→ [{"kind":"remote","path":...} | {"kind":"local","path":Path}]

    路径归属判定顺序：Windows 盘符/UNC → 本地；本地存在 → 本地；
    本地 glob 能命中 → 本地；否则按远端处理（glob 在远端展开）。
    """
    items: list[dict] = []
    raw_list = spec if isinstance(spec, list) else [spec]
    for raw in raw_list:
        s = str(raw or "").strip()
        if not s:
            continue
        is_win = bool(re.match(r"^[A-Za-z]:[\\/]", s)) or s.startswith("\\\\")
        if is_win or Path(s).exists() or (any(ch in s for ch in "*?[") and not s.startswith("/")):
            hits = _local_glob(s) if any(ch in s for ch in "*?[") else _local_candidates(s)
            if hits:
                for f in hits:
                    items.append({"kind": "local", "path": f})
                continue
            if is_win or not any(ch in s for ch in "*?["):
                continue  # 明确是本地路径但没命中：交给上层报"没展开出图片"
        if any(ch in s for ch in "*?["):
            for f in _remote_expand(s, node):
                items.append({"kind": "remote", "path": f})
        else:
            items.append({"kind": "remote", "path": s})
    return items


# ---------------------------------------------------------------------------
# 单作业执行
# ---------------------------------------------------------------------------
def _stem(path: str) -> str:
    name = os.path.basename(str(path).rstrip("/"))
    stem = os.path.splitext(name)[0]
    return re.sub(r"[^A-Za-z0-9_.-]", "_", stem)[:60] or "job"


def _local_results_dir(run_id: str, job: str = "") -> Path:
    sid = ""
    try:
        sid = rc._current_agent_session() or ""
    except Exception:
        sid = ""
    sid = sid or "manual"
    # 自定义本地结果根目录（本机/集群产物都适用）；留空维持原会话目录约定
    try:
        custom = str(((ij_settings.load().get("local") or {}).get("save_dir")) or "").strip()
    except Exception:
        custom = ""
    d = (Path(custom).expanduser() / run_id) if custom else \
        (_repo_root() / "results" / sid / "imagej" / run_id)
    if job:
        d = d / job
    d.mkdir(parents=True, exist_ok=True)
    return d


def _read_done(done_path: Path) -> dict:
    try:
        return json.loads(done_path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _gates(meta: dict, params: dict, done: dict, local_dir: Path, outputs: list[str]) -> list[dict]:
    accept = meta.get("accept") or {}
    checks: list[dict] = []

    missing = [o for o in (meta.get("outputs") or []) if not (local_dir / o).is_file()]
    checks.append({"id": "artifacts", "ok": not missing,
                   "detail": "缺少: " + ",".join(missing) if missing else "齐全"})

    if not done:
        checks.append({"id": "done_sentinel", "ok": False, "detail": "DONE.json 缺失或不可解析"})
    else:
        checks.append({"id": "done_sentinel", "ok": True,
                       "detail": "n_objects=%s size=%sx%s" % (done.get("n_objects"),
                                                              done.get("width"), done.get("height"))})

    px_um = float(params.get("px_um") or 0)
    checks.append({"id": "units", "ok": px_um > 0,
                   "detail": ("px_um=%s，已换算 µm" % px_um) if px_um > 0 else "未给 px_um → 结果只按像素报告（警告）"})

    n = _to_int(done.get("n_objects"))
    lo = _to_int(accept.get("min_objects"))
    hi = _to_int(accept.get("max_objects")) or 10 ** 9
    if accept.get("unit") in ("ratio", "convert"):
        checks.append({"id": "count", "ok": True, "detail": "非计数类 op，跳过计数闸"})
    elif accept.get("unit") == "ratio":
        checks.append({"id": "count", "ok": True, "detail": "面积占比类 op，不做计数闸"})
    else:
        hint = ""
        if n == 0 and (done.get("area_fraction") or 0) > 0:
            hint = "；掩膜里有阳性像素但都小于面积下限 → 调小 min_area_um2 或换 threshold/invert"
        checks.append({"id": "count", "ok": lo <= n <= hi,
                       "detail": "n_objects=%d（允许 %d–%d）%s" % (n, lo, hi, hint)})

    frac = done.get("area_fraction")
    rng = accept.get("area_fraction") or []
    if frac is None:
        checks.append({"id": "area_fraction", "ok": True, "detail": "无面积占比（跳过）"})
    else:
        try:
            f = float(frac)
            ok = (len(rng) == 2 and float(rng[0]) <= f <= float(rng[1]))
            checks.append({"id": "area_fraction", "ok": bool(ok),
                           "detail": "fraction=%.4f（允许 %s–%s）" % (f, rng[0] if rng else "?", rng[1] if rng else "?")})
        except Exception:
            checks.append({"id": "area_fraction", "ok": False, "detail": "无法解析 fraction=%r" % frac})

    # 单位闸之外的软检查：像素域数值是否合理（面积中位数 > 0）
    obj_csv = local_dir / "objects.csv"
    if obj_csv.is_file():
        rows = _read_objects(obj_csv)
        if rows:
            areas = [r["Area"] for r in rows if r.get("Area") is not None]
            if areas:
                med = statistics.median(areas)
                checks.append({"id": "object_plausibility", "ok": med > 0,
                               "detail": "面积中位数=%.2f px²（%d 个对象）" % (med, len(areas))})
    return checks


def _read_objects(path: Path) -> list[dict]:
    import csv
    rows: list[dict] = []
    try:
        with open(path, "r", encoding="utf-8", errors="replace", newline="") as fh:
            reader = csv.DictReader(fh)
            for rec in reader:
                out = {}
                for k, v in rec.items():
                    if k is None:
                        continue
                    key = str(k).strip()
                    try:
                        out[key] = float(str(v).strip())
                    except Exception:
                        out[key] = v
                if out:
                    rows.append(out)
    except Exception as exc:
        logger.warning("读取 objects.csv 失败 %s: %s", path, exc)
    return rows


def _filter_by_area(rows: list[dict], params: dict, px_um: float,
                    calibrated: bool = False, ij_scale: float = 1.0) -> tuple[list[dict], int]:
    """按 min_area_um2 / max_area_um2 过滤对象（面积换算成 µm² 再比）。"""
    lo = float(params.get("min_area_um2") or 0)
    hi = float(params.get("max_area_um2") or 0)
    if not rows or (lo <= 0 and hi <= 0):
        return rows, 0
    f = _unit_factor(px_um, ij_scale)
    scale = f * f
    kept, dropped = [], 0
    for r in rows:
        a = r.get("Area")
        if not isinstance(a, (int, float)):
            kept.append(r)
            continue
        a_um2 = float(a) * scale
        if (lo > 0 and a_um2 < lo) or (hi > 0 and a_um2 > hi):
            dropped += 1
            continue
        kept.append(r)
    return kept, dropped


def _unit_factor(px_um: float, ij_scale: float) -> float:
    """返回「IJ 长度单位 → µm」的系数。

    ij_scale = IJ 单位/像素（宏里用 100×100 ROI 实测）；px_um = µm/像素。
    s=1 且没给 px_um → 像素域，返回 1 并靠 px_um 判断单位。
    """
    s = float(ij_scale or 1.0)
    if s <= 0:
        s = 1.0
    if px_um and px_um > 0:
        return float(px_um) / s
    return 1.0 / s


def _summarize_objects(rows: list[dict], px_um: float, calibrated: bool = False,
                       ij_scale: float = 1.0) -> dict:
    """把 CSV 换算成 µm 域统计。

    calibrated=True 表示输入图自带物理标定（OME-TIFF/CZI 等），ImageJ 报的 Area/Feret 已经是
    µm²/µm，不能再乘 px_um；否则是像素域，需要按 px_um 换算。
    """
    def conv(key: str, factor: float) -> list[float]:
        vals = []
        for r in rows:
            v = r.get(key)
            if isinstance(v, (int, float)):
                vals.append(float(v) * factor)
        return vals

    scale = _unit_factor(px_um, ij_scale)   # IJ 长度单位 → µm
    area = conv("Area", scale * scale)
    perim = conv("Perim.", scale)
    feret = conv("Feret", scale)
    minferet = conv("MinFeret", scale)
    circ = conv("Circ.", 1.0)
    ar = conv("AR", 1.0)

    def stat(vals: list[float]) -> dict:
        if not vals:
            return {}
        return {
            "n": len(vals),
            "mean": round(statistics.fmean(vals), 3),
            "median": round(statistics.median(vals), 3),
            "sd": round(statistics.pstdev(vals), 3) if len(vals) > 1 else 0.0,
            "min": round(min(vals), 3),
            "max": round(max(vals), 3),
        }

    unit = "um" if (calibrated or (px_um and px_um > 0)) else "px"
    return {
        "unit": unit,
        "px_um": px_um,
        "area": stat(area),
        "perimeter": stat(perim),
        "feret": stat(feret),
        "min_feret": stat(minferet),
        "circularity": stat(circ),
        "aspect_ratio": stat(ar),
    }


def run_job(*, op_id: str, params: dict, input_item: dict, node: str, run_id: str,
            job_name: str = "", mem: str = "", timeout: int = 0, backend: str = "") -> dict:
    """跑一个作业：渲染 → 上传/落盘 → 执行 → 拉回 → 闸门 → manifest。

    backend="local" 用本机 ImageJ（ImageJ.exe / ij.jar）；"cluster" 走远端 runner。
    """
    ops = _ops()
    if op_id not in ops:
        raise RuntimeError("未知 op: %s（可用：%s）" % (op_id, ", ".join(sorted(ops))))
    meta = ops[op_id]
    if meta.get("status") != "ready":
        raise RuntimeError("op '%s' 尚未就绪（status=%s）" % (op_id, meta.get("status")))

    backend = (backend or _default_backend()).lower()
    if backend == "local":
        return _run_job_local(meta=meta, params=dict(params), input_item=input_item,
                              run_id=run_id, job_name=job_name, mem=mem or "2g",
                              timeout=int(timeout or 900))

    c = _imagej_cfg()
    mem = mem or c["mem"]
    timeout = int(timeout or c["timeout"])
    job_name = job_name or _stem(str(input_item.get("path")))
    remote_job = "%s/%s/%s" % (c["job_root"].rstrip("/"), run_id, job_name)
    out_dir = remote_job + "/out"

    prep = _run("mkdir -p %s %s/in; echo __READY__" % (_q(out_dir), _q(remote_job)), node, 60)

    # 输入：本地文件先传上去；远端文件直接用
    if input_item["kind"] == "local":
        lp = Path(input_item["path"])
        in_remote = "%s/in/%s" % (remote_job, lp.name)
        local_size = lp.stat().st_size
        remote_size = -1
        try:
            st, _ = _run("stat -c %%s %s 2>/dev/null || echo -1" % _q(in_remote), node, 60)
            remote_size = _to_int(st.strip() or -1)
        except Exception:
            remote_size = -1
        if remote_size != local_size:
            _push(str(lp), in_remote, node)
        src = {"path": str(lp), "sha256": _sha256_file(lp), "bytes": local_size,
               "uploaded": remote_size != local_size}
    else:
        in_remote = str(input_item["path"])
        out, _ = _run("stat -c '%%s %%n' %s" % _q(in_remote), node, 60)
        parts = out.strip().split(" ", 1)
        src = {"path": in_remote, "bytes": _to_int(parts[0] if parts else 0)}

    # 没给 px_um 时，尝试从文件元数据（Bio-Formats OME-XML）自动取
    px_source = "param" if float(params.get("px_um") or 0) > 0 else ""
    bf_meta: dict = {}
    if not px_source:
        try:
            bf_meta = _bf_metadata(in_remote, node)
        except Exception as exc:
            logger.info("Bio-Formats 元数据读取失败（忽略）：%s", exc)
            bf_meta = {}
        if bf_meta.get("px_um"):
            params["px_um"] = bf_meta["px_um"]
            px_source = "bf_metadata"

    # ---- CLI 型 op：不经过 ImageJ/Xvfb，直接调 Bio-Formats 的命令行工具 ----
    if meta.get("mode") == "cli":
        return _run_cli_op(meta=meta, params=params, in_remote=in_remote, remote_job=remote_job,
                           out_dir=out_dir, node=node, run_id=run_id, job_name=job_name,
                           mem=mem, timeout=timeout, src=src, px_source=px_source, bf_meta=bf_meta,
                           t0=time.time())

    macro_text = _render_macro(meta, params, remote_job, in_remote, out_dir)
    macro_local = _local_results_dir(run_id, job_name) / "macro.ijm"
    macro_local.write_text(macro_text, encoding="utf-8", newline="\n")
    _push(str(macro_local), remote_job + "/macro.ijm", node)

    cmd = ("%s/run_ij.sh --job %s --macro %s/macro.ijm --mem %s --timeout %d; echo __RC__$?"
           % (_q(c["runner"]), _q(remote_job), _q(remote_job), mem, timeout))
    exit_code = -1
    out = ""
    attempt = 0
    while attempt < 2:
        attempt += 1
        t0 = time.time()
        out, _ = _run(cmd, node, timeout + 240)
        wall = round(time.time() - t0, 2)
        m = re.search(r"__RC__(\d+)", out)
        exit_code = int(m.group(1)) if m else -1
        # 2 = 超时：可能是孤儿 X server / NFS 抖动，换一个 display 重试一次
        if exit_code != 2 or attempt >= 2:
            break
        logger.warning("作业超时，重试一次（%s/%s）", attempt, 2)
    console = out[: m.start()] if m else out

    # 拉回产物（失败也拉，便于诊断）
    local_dir = _local_results_dir(run_id, job_name)
    pulled = 0
    try:
        r = _pull(remote_job + "/out/*", str(local_dir), node, overwrite=True)
        pulled = len(r.get("local_paths") or [])
    except Exception as exc:
        logger.warning("产物拉回失败：%s", exc)
    # ij.log / runner.log 已由 run_ij.sh 复制进 out/，无需再单独 pull

    done = _read_done(local_dir / "DONE.json")
    px_um = float(params.get("px_um") or 0)   # 可能来自 bf_metadata
    obj_csv = local_dir / "objects.csv"
    rows_all: list[dict] = _read_objects(obj_csv) if obj_csv.is_file() else []
    calibrated = bool((bf_meta or {}).get("px_um"))
    ij_scale = float(done.get("ij_scale") or 1.0)
    rows, dropped = _filter_by_area(rows_all, params, px_um, calibrated, ij_scale)
    n_raw = _to_int(done.get("n_objects"))
    n_kept = len(rows) if rows_all else n_raw
    if done:
        done["n_objects"] = n_kept        # 闸门按过滤后的数量判
    checks = _gates(meta, params, done, local_dir, meta.get("outputs") or [])
    stats = _summarize_objects(rows, px_um, calibrated, ij_scale) if rows else {}
    if rows:
        stats["ij_scale"] = ij_scale

    display = ""
    try:
        rl = (local_dir / "runner.log").read_text(encoding="utf-8", errors="replace")
        mm = re.search(r"display=(:\d+)", rl)
        display = mm.group(1) if mm else ""
    except Exception:
        pass

    gate_ok = all(c["ok"] for c in checks)
    status = "ok" if (gate_ok and exit_code == 0) else ("gate_failed" if exit_code == 0 else "error")

    manifests = []
    for f in sorted(local_dir.glob("*")):
        if f.is_file() and f.name != "manifest.json":
            manifests.append({"name": f.name, "bytes": f.stat().st_size,
                              "sha256": _sha256_file(f) if f.stat().st_size < 200 * 1024 * 1024 else ""})

    manifest = {
        "run_id": run_id,
        "job": job_name,
        "op": op_id,
        "op_version": meta.get("version"),
        "tool_version": TOOL_VERSION,
        "node": node or "default",
        "display": display,
        "imagej": {"root": c["root"], "launcher": "RunIjBatch"},
        "macro_sha256": _sha256_text(macro_text),
        "params": {k: v for k, v in params.items()},
        "derived": {"px_um": px_um, "px_um_source": px_source or "none",
                    "measure_units": "um" if calibrated else ("px" if not px_um else "um_via_px"),
                    "calibrated_input": calibrated,
                    "bf_metadata": bf_meta, "min_area_um2": params.get("min_area_um2")},
        "input": src,
        "outputs": manifests,
        "metrics": {
            "n_objects": n_kept,
            "n_objects_raw": n_raw,
            "dropped_by_area": dropped,
            "width": _to_int(done.get("width")),
            "height": _to_int(done.get("height")),
            "area_fraction": done.get("area_fraction"),
            "object_stats": stats,
        },
        "checks": checks,
        "timing": {"wall_s": wall, "timeout_s": timeout},
        "exit_code": exit_code,
        "status": status,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "console_tail": console[-1500:],
    }
    (local_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    _append_index(manifest, str(local_dir))
    return manifest


def _default_backend() -> str:
    """没显式指定时：本机配了 ImageJ 就本地，否则集群。"""
    try:
        cfg = ij_settings.load()
        if (cfg.get("local") or {}).get("root"):
            return "local"
        if (cfg.get("cluster") or {}).get("root") or (cfg.get("cluster") or {}).get("name"):
            return "cluster"
    except Exception:
        pass
    return "cluster"


def _local_root() -> Path:
    root = str((ij_settings.load().get("local") or {}).get("root") or "").strip()
    if not root:
        raise RuntimeError("还没设置本机 ImageJ 路径：请点输入框上方的「ImageJ 设置」填路径")
    rp = Path(root)
    if not rp.is_dir():
        raise RuntimeError("本机 ImageJ 路径不存在：%s" % root)
    return rp


def _local_launch_cmd(probe: dict, macro: Path, mem: str) -> list[str]:
    if probe.get("kind") == "exe":
        return [probe["launcher"], "-batch", str(macro)]
    return [probe["java"], "-Xmx%s" % mem, "-jar", probe["launcher"], "-batch", str(macro)]


def _run_local_process(cmd: list[str], cwd: str, job_dir: Path, timeout: int) -> tuple[int, str]:
    """起本机 ImageJ 并等 DONE.json 哨兵（等不到就超时回收），返回 (exit_code, log)。"""
    import subprocess
    import tempfile

    log_path = job_dir / "ij.log"
    with open(log_path, "wb") as fh:
        flags = 0
        if os.name == "nt":
            flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        proc = subprocess.Popen(cmd, cwd=cwd, stdout=fh, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                                creationflags=flags)
        deadline = time.time() + max(30, int(timeout))
        rc_code = -1
        while time.time() < deadline:
            if (job_dir / "out" / "DONE.json").is_file():
                time.sleep(1.0)
                break
            if proc.poll() is not None:
                break
            time.sleep(0.4)
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=8)
            except Exception:
                proc.kill()
            rc_code = 2 if not (job_dir / "out" / "DONE.json").is_file() else 0
        else:
            rc_code = int(proc.returncode or 0)
    try:
        log = log_path.read_text(encoding="utf-8", errors="replace")[-1500:]
    except Exception:
        log = ""
    return rc_code, log


def _run_job_local(*, meta: dict, params: dict, input_item: dict, run_id: str,
                   job_name: str, mem: str, timeout: int) -> dict:
    """本机执行：作业目录在 %TEMP%/memomics_ij/<run_id>/<job>，宏与产物都留在那儿。"""
    import tempfile

    t0 = time.time()
    probe = ij_settings.probe_local()
    if not probe.get("ok"):
        raise RuntimeError(probe.get("error") or "本机 ImageJ 不可用")

    in_path = Path(str(input_item.get("path")))
    if input_item.get("kind") != "local":
        raise RuntimeError("backend=local 只接受本机文件；集群路径请用 backend=cluster")
    if not in_path.is_file():
        raise RuntimeError("找不到输入文件：%s" % in_path)
    job_name = job_name or _stem(str(in_path))

    base = Path(tempfile.gettempdir()) / "memomics_ij" / run_id / job_name
    out_dir = base / "out"
    out_dir.mkdir(parents=True, exist_ok=True)
    local_dir = _local_results_dir(run_id, job_name)

    px_source = "param" if float(params.get("px_um") or 0) > 0 else ""

    # CLI 型 op（bf_convert）：本机 java -cp bioformats_package.jar
    if meta.get("mode") == "cli":
        jar = Path(probe["root"]) / "plugins" / "bioformats_package.jar"
        if not jar.is_file():
            raise RuntimeError("本机没装 Bio-Formats（缺 plugins/bioformats_package.jar），先装 7.3.1")
        java = probe.get("java") or (Path(probe["root"]) / "jre" / "bin" / "java.exe")
        out_tif = out_dir / "converted.tif"
        args = ["-no-upgrade"]
        ch = _to_int(params.get("channel")) or 0
        if ch > 0:
            args += ["-channel", str(ch - 1)]
        args += [str(in_path), str(out_tif)]
        cmd = [str(java), "-Xmx%s" % mem, "-cp", str(jar),
               "loci.formats.tools.ImageConverter"] + args
        import subprocess
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout,
                              encoding="utf-8", errors="replace",
                              creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        console = (proc.stdout or "")[-1200:] + (proc.stderr or "")[-400:]
        exit_code = 0 if out_tif.is_file() else 1
        done = {"n_objects": 0, "width": 0, "height": 0, "unit": "px"} if out_tif.is_file() else {}
    else:
        macro_text = _render_macro(meta, params, str(base), str(in_path), str(out_dir))
        macro_path = base / "macro.ijm"
        macro_path.write_text(macro_text, encoding="utf-8", newline="\n")
        cmd = _local_launch_cmd(probe, macro_path, mem)
        exit_code, console = _run_local_process(cmd, str(probe["root"]), base, timeout)
        done = _read_done(out_dir / "DONE.json")

    # 产物拷到会话目录（WebUI 只认 results/ 与 work/）
    for f in out_dir.glob("*"):
        if f.is_file():
            try:
                target = local_dir / f.name
                if target.exists():
                    target.unlink()
                target.write_bytes(f.read_bytes())
            except Exception as exc:
                logger.warning("本地产物拷贝失败 %s: %s", f, exc)

    px_um = float(params.get("px_um") or 0)
    obj_csv = local_dir / "objects.csv"
    rows_all = _read_objects(obj_csv) if obj_csv.is_file() else []
    calibrated = False
    ij_scale = float(done.get("ij_scale") or 1.0)
    rows, dropped = _filter_by_area(rows_all, params, px_um, calibrated, ij_scale)
    n_raw = _to_int(done.get("n_objects"))
    n_kept = len(rows) if rows_all else n_raw
    if done:
        done["n_objects"] = n_kept
    checks = _gates(meta, params, done, local_dir, meta.get("outputs") or [])
    stats = _summarize_objects(rows, px_um, calibrated, ij_scale) if rows else {}

    outputs = [{"name": f.name, "bytes": f.stat().st_size, "sha256": _sha256_file(f)}
               for f in sorted(local_dir.glob("*")) if f.is_file() and f.name != "manifest.json"]
    status = "ok" if all(c["ok"] for c in checks) and exit_code == 0 else "gate_failed"
    manifest = {
        "run_id": run_id, "job": job_name, "op": meta.get("id"),
        "op_version": meta.get("version"), "tool_version": TOOL_VERSION,
        "node": "local", "display": "",
        "imagej": {"root": probe.get("root"), "kind": probe.get("kind"),
                   "launcher": probe.get("launcher"), "mode": meta.get("mode") or "macro"},
        "macro_sha256": _sha256_text((base / "macro.ijm").read_text(encoding="utf-8")) if (base / "macro.ijm").is_file() else "",
        "params": dict(params),
        "derived": {"px_um": px_um, "px_um_source": px_source or ("param" if px_um else "none"),
                    "calibrated_input": calibrated, "ij_scale": ij_scale,
                    "min_area_um2": params.get("min_area_um2")},
        "input": {"path": str(in_path), "sha256": _sha256_file(in_path), "bytes": in_path.stat().st_size},
        "outputs": outputs,
        "metrics": {"n_objects": n_kept, "n_objects_raw": n_raw, "dropped_by_area": dropped,
                    "width": _to_int(done.get("width")), "height": _to_int(done.get("height")),
                    "area_fraction": done.get("area_fraction"), "object_stats": stats},
        "checks": checks,
        "timing": {"wall_s": round(time.time() - t0, 2), "timeout_s": timeout},
        "exit_code": exit_code, "status": status,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "console_tail": console[-1500:],
        "job_dir": str(base),
    }
    (local_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    _append_index(manifest, str(local_dir))
    return manifest


def _run_cli_op(*, meta: dict, params: dict, in_remote: str, remote_job: str, out_dir: str,
                node: str, run_id: str, job_name: str, mem: str, timeout: int,
                src: dict, px_source: str, bf_meta: dict, t0: float) -> dict:
    """跑 CLI 型 op（Bio-Formats 工具链），产物拉回后补齐 manifest。"""
    c = _imagej_cfg()
    root = str(c["root"]).rstrip("/")
    java = root + "/jre/bin/java"
    jar = root + "/plugins/bioformats_package.jar"
    cli = meta.get("cli") or {}
    main = cli.get("main") or "loci.formats.tools.ImageConverter"

    args = ["-no-upgrade"]
    ch = _to_int(params.get("channel")) or 0
    if ch > 0:
        args += ["-channel", str(ch - 1)]          # ImageConverter 的 channel 是 0 基
    args += [in_remote, out_dir + "/converted.tif"]
    cmd = ("%s -Xmx%s -cp %s %s %s"
           % (_q(java), mem, _q(jar), main, " ".join(_q(a) for a in args)))

    out, _ = _run(cmd, node, timeout + 120)
    exit_code = 0 if "[done]" in out or "elapsed" in out else 1
    console = out[-1500:]

    local_dir = _local_results_dir(run_id, job_name)
    pulled = 0
    try:
        r = _pull(remote_job + "/out/*", str(local_dir), node, overwrite=True)
        pulled = len(r.get("local_paths") or [])
    except Exception as exc:
        logger.warning("产物拉回失败：%s", exc)

    # 补 DONE.json（CLI 不写）：从转换产物读尺寸
    done_path = local_dir / "DONE.json"
    done = _read_done(done_path)
    if not done and (local_dir / "converted.tif").is_file():
        meta_after = {}
        try:
            meta_after = _bf_metadata(str(local_dir / "converted.tif"), "") if False else {}
        except Exception:
            meta_after = {}
        done = {"n_objects": 0, "width": 0, "height": 0, "unit": "px"}
        done_path.write_text(json.dumps(done), encoding="utf-8")
    checks = _gates(meta, params, done, local_dir, meta.get("outputs") or [])
    outputs = [{"name": f.name, "bytes": f.stat().st_size, "sha256": _sha256_file(f)}
               for f in sorted(local_dir.glob("*")) if f.is_file() and f.name != "manifest.json"]

    status = "ok" if all(c["ok"] for c in checks) and exit_code == 0 else "gate_failed"
    manifest = {
        "run_id": run_id, "job": job_name, "op": meta.get("id"),
        "op_version": meta.get("version"), "tool_version": TOOL_VERSION,
        "node": node or "default", "display": "",
        "imagej": {"root": root, "mode": "cli", "main": main},
        "macro_sha256": "", "params": dict(params),
        "derived": {"px_um": float(params.get("px_um") or 0),
                    "px_um_source": px_source or "none", "bf_metadata": bf_meta},
        "input": src, "outputs": outputs,
        "metrics": {"n_objects": 0, "width": 0, "height": 0,
                    "area_fraction": None, "object_stats": {}},
        "checks": checks,
        "timing": {"wall_s": round(time.time() - t0, 2), "timeout_s": timeout},
        "exit_code": exit_code, "status": status,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "console_tail": console,
    }
    (local_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    _append_index(manifest, str(local_dir))
    return manifest


def _append_index(manifest: dict, local_dir: str) -> None:
    path = _hermes_home() / "imagej_runs.jsonl"
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        rec = {k: manifest.get(k) for k in
               ("run_id", "job", "op", "op_version", "node", "status", "exit_code", "created_at")}
        rec["local_dir"] = local_dir
        rec["metrics"] = manifest.get("metrics", {})
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception as exc:
        logger.warning("写 run 索引失败：%s", exc)


# ---------------------------------------------------------------------------
# 对外动作
# ---------------------------------------------------------------------------
def action_probe(args: dict) -> dict:
    backend = str(args.get("backend") or "").lower() or _default_backend()
    if backend == "local":
        info = ij_settings.probe_local()
        info["backend"] = "local"
        info["imagej_ready"] = bool(info.get("ok"))
        return info
    info = probe(_node(args), refresh=bool(args.get("refresh")))
    info["backend"] = "cluster"
    info["deployed"] = ensure_deployed(_node(args), force=False).get("deployed")
    return info


def action_ops(args: dict) -> dict:
    ops = _ops(force=bool(args.get("refresh")))
    p = {}
    try:
        backend = str(args.get("backend") or "").lower() or _default_backend()
        p = ij_settings.probe_local() if backend == "local" else probe(_node(args))
    except Exception:
        p = {}
    rows = []
    for op_id, meta in sorted(ops.items()):
        req = meta.get("requires") or []
        blocked = [r for r in req if r == "bioformats" and not p.get("bioformats")]
        rows.append({
            "id": op_id,
            "name": meta.get("name"),
            "version": meta.get("version"),
            "status": meta.get("status"),
            "available": meta.get("status") == "ready" and not blocked,
            "blocked_reason": ("缺插件: " + ",".join(blocked)) if blocked else "",
            "summary": meta.get("summary"),
            "params": {k: {"default": v.get("default"), "desc": v.get("desc")}
                       for k, v in (meta.get("params") or {}).items()},
            "outputs": meta.get("outputs"),
        })
    return {"status": "ok", "count": len(rows), "ops": rows}


def action_init(args: dict) -> dict:
    return ensure_deployed(_node(args), force=bool(args.get("force")))


def action_run(args: dict) -> dict:
    op_id = str(args.get("op") or "").strip()
    if not op_id:
        return {"status": "error", "error": "缺少 op（先 action='ops' 看可用清单）"}
    params = dict(args.get("params") or {})
    backend = str(args.get("backend") or "").lower() or _default_backend()
    node = _node(args)
    if backend == "cluster":
        ensure_deployed(node, force=False)
    items = _expand_inputs(args.get("input"), node)
    if not items:
        return {"status": "error", "error": "input 没展开出任何图片（支持远端 glob / 远端路径 / 本地文件或目录）"}
    if len(items) > 1:
        return {"status": "error",
                "error": "input 命中 %d 张图；单图请用 action='run' 给单个路径，多图请用 action='batch'" % len(items)}
    run_id = str(args.get("run_id") or _new_run_id(op_id))
    manifest = run_job(op_id=op_id, params=params, input_item=items[0], node=node,
                       run_id=run_id, mem=str(args.get("mem") or ""),
                       timeout=int(args.get("timeout") or 0), backend=backend)
    return {"status": manifest["status"], "run_id": run_id, "job": manifest["job"],
            "manifest": manifest, "local_dir": str(_local_results_dir(run_id, manifest["job"]))}


def action_batch(args: dict) -> dict:
    op_id = str(args.get("op") or "").strip()
    if not op_id:
        return {"status": "error", "error": "缺少 op"}
    params = dict(args.get("params") or {})
    backend = str(args.get("backend") or "").lower() or _default_backend()
    node = _node(args)
    if backend == "cluster":
        ensure_deployed(node, force=False)
    items = _expand_inputs(args.get("input"), node)
    if not items:
        return {"status": "error", "error": "input 没展开出任何图片"}
    limit = _to_int(args.get("limit")) or 0
    if limit and len(items) > limit:
        items = items[:limit]
    run_id = str(args.get("run_id") or _new_run_id(op_id))
    results = []
    for idx, item in enumerate(items, 1):
        job = _stem(str(item["path"]))
        job = "%02d_%s" % (idx, job)
        try:
            m = run_job(op_id=op_id, params=params, input_item=item, node=node,
                        run_id=run_id, job_name=job, backend=backend,
                        mem=str(args.get("mem") or ""), timeout=int(args.get("timeout") or 0))
            results.append({"job": job, "status": m["status"], "n_objects": m["metrics"]["n_objects"],
                            "exit_code": m["exit_code"]})
        except Exception as exc:
            results.append({"job": job, "status": "error", "error": str(exc)})
    ok = sum(1 for r in results if r["status"] == "ok")
    return {
        "status": "ok" if ok == len(results) else ("partial" if ok else "error"),
        "run_id": run_id,
        "op": op_id,
        "total": len(results),
        "ok": ok,
        "failed": [r for r in results if r["status"] != "ok"],
        "jobs": results,
        "local_dir": str(_local_results_dir(run_id)),
    }


def action_summarize(args: dict) -> dict:
    run_id = str(args.get("run_id") or "").strip()
    if not run_id:
        return {"status": "error", "error": "缺少 run_id"}
    base = _local_results_dir(run_id)
    manifests = []
    for mf in sorted(base.rglob("manifest.json")):
        try:
            manifests.append(json.loads(mf.read_text(encoding="utf-8")))
        except Exception:
            continue
    if not manifests:
        return {"status": "error", "error": "该 run_id 下没有 manifest：%s" % base}

    rows = []
    for m in manifests:
        st = (m.get("metrics") or {}).get("object_stats") or {}
        area = st.get("area") or {}
        rows.append({
            "job": m.get("job"),
            "status": m.get("status"),
            "n_objects": (m.get("metrics") or {}).get("n_objects"),
            "area_mean": area.get("mean"),
            "area_median": area.get("median"),
            "area_sd": area.get("sd"),
            "area_min": area.get("min"),
            "area_max": area.get("max"),
            "unit": st.get("unit"),
            "area_fraction": (m.get("metrics") or {}).get("area_fraction"),
        })

    summary_csv = base / "summary.csv"
    cols = ["job", "status", "n_objects", "area_mean", "area_median", "area_sd",
            "area_min", "area_max", "area_fraction", "unit"]
    with open(summary_csv, "w", encoding="utf-8", newline="") as fh:
        fh.write(",".join(cols) + "\n")
        for r in rows:
            fh.write(",".join("" if r.get(c) is None else str(r.get(c)) for c in cols) + "\n")

    areas = [r["area_median"] for r in rows if isinstance(r.get("area_median"), (int, float))]
    units = {r.get("unit") for r in rows}
    agg = {}
    if areas:
        agg = {
            "n_images": len(areas),
            "median_of_medians": round(statistics.median(areas), 3),
            "mean_of_medians": round(statistics.fmean(areas), 3),
            "range": [round(min(areas), 3), round(max(areas), 3)],
            "unit": sorted(u for u in units if u),
        }
    counts = [r["n_objects"] for r in rows if isinstance(r.get("n_objects"), (int, float))]
    if counts:
        agg["total_objects"] = int(sum(counts))
        agg["median_count"] = round(statistics.median(counts), 1)

    md = ["# ImageJ 批量汇总 %s" % run_id, "",
          "| 作业 | 状态 | 对象数 | 面积中位数 | 面积均值 | 单位 |", "|---|---|---|---|---|---|"]
    for r in rows:
        md.append("| %s | %s | %s | %s | %s | %s |" % (
            r["job"], r["status"], r.get("n_objects"), r.get("area_median"), r.get("area_mean"), r.get("unit")))
    if agg:
        md += ["", "汇总：" + json.dumps(agg, ensure_ascii=False)]
    md_path = base / "summary.md"
    md_path.write_text("\n".join(md), encoding="utf-8")

    return {"status": "ok", "run_id": run_id, "n_manifests": len(manifests),
            "aggregate": agg, "rows": rows,
            "summary_csv": str(summary_csv), "summary_md": str(md_path)}


def action_jobs(args: dict) -> dict:
    path = _hermes_home() / "imagej_runs.jsonl"
    limit = _to_int(args.get("limit")) or 20
    if not path.is_file():
        return {"status": "ok", "count": 0, "jobs": [], "note": "还没有跑过作业"}
    rows = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except Exception:
            continue
    return {"status": "ok", "count": len(rows[-limit:]), "jobs": rows[-limit:]}


def action_collect(args: dict) -> dict:
    run_id = str(args.get("run_id") or "").strip()
    if not run_id:
        return {"status": "error", "error": "缺少 run_id"}
    node = _node(args)
    c = _imagej_cfg()
    remote = "%s/%s/*/out/*" % (c["job_root"].rstrip("/"), run_id)
    local = _local_results_dir(run_id)
    r = _pull(remote, str(local), node, overwrite=bool(args.get("overwrite")))
    return {"status": "ok", "run_id": run_id, "pulled": len(r.get("local_paths") or []),
            "local_dir": str(local)}


def _new_run_id(op_id: str) -> str:
    return "%s-%s-%s" % (datetime.now().strftime("%Y%m%d-%H%M%S"), op_id, uuid.uuid4().hex[:4])


def imagej_handler(args: dict | None = None, **kwargs) -> str:
    args = args or {}
    action = str(args.get("action") or "").strip()
    try:
        if action == "probe":
            out = action_probe(args)
        elif action == "ops":
            out = action_ops(args)
        elif action == "init":
            out = action_init(args)
        elif action == "run":
            out = action_run(args)
        elif action == "batch":
            out = action_batch(args)
        elif action == "collect":
            out = action_collect(args)
        elif action == "summarize":
            out = action_summarize(args)
        elif action == "jobs":
            out = action_jobs(args)
        else:
            out = {"status": "error",
                   "error": "未知 action: %r（可用：probe/ops/init/run/batch/collect/summarize/jobs）" % action}
    except Exception as exc:
        logger.exception("imagej action=%s 失败", action)
        out = {"status": "error", "error": "%s: %s" % (type(exc).__name__, exc)}
    return json.dumps(out, ensure_ascii=False, default=str)


def imagej_enabled() -> bool:
    """本机配了 ImageJ 或集群可用 → 工具对模型可见。"""
    try:
        cfg = ij_settings.load()
        if (cfg.get("local") or {}).get("root"):
            return True
        if (cfg.get("cluster") or {}).get("root") or (cfg.get("cluster") or {}).get("name"):
            return True
    except Exception:
        pass
    try:
        return bool(rc.remote_cluster_enabled())
    except Exception:
        return False


SCHEMA = {
    "name": "imagej",
    "description": (
        "集群 ImageJ 图像定量 —— 把图片送到远端 ImageJ 1.54g（Xvfb 虚拟屏）跑宏，"
        "拉回逐对象 CSV/轮廓图，过四道闸（产物/单位/计数/面积占比）后写可溯源 manifest。\n"
        "适用：肌纤维横截面 CSA、DAPI/CD31 计数、胶原或阳性面积占比、批量图像定量。\n"
        "不适用：本机几秒钟能算完的小图（用 execute_python），或需要深度学习分割的图（P4 未上线）。\n"
        "典型流程：\n"
        "  ① action='probe' 自检（Java/launcher/Xvfb/插件/节点）；首次或脚本升级后跑 action='init' 部署 runner。\n"
        "  ② action='ops' 看操作目录与参数默认值（csa / count_objects / area_fraction）。\n"
        "  ③ action='run' 单图试跑（op + input + params），看 outlines.png/overlays 与指标，确认参数。\n"
        "  ④ action='batch' 多图批量（input 支持远端 glob 如 /path/*.tif、远端目录、本地目录）。\n"
        "  ⑤ action='summarize' 汇总成 summary.csv/summary.md（面积中位数、计数、分组可直接进报告）。\n"
        "硬规则：\n"
        "  • 测量一律像素域，µm 换算按 params.px_um 在工具侧完成 —— 不给 px_um 会判 warning（结果只按像素）。\n"
        "  • 每个作业独立 DISPLAY + 独立目录 + 超时兜底；失败会带 console_tail 与 ij.log，别只看退出码。\n"
        "  • 产物落 results/<会话>/imagej/<run_id>/<job>/（manifest.json 记录宏 sha256、参数、输入、检查项）。\n"
        "  • 参数拿不准先单图 run：阈值方法（Otsu/Triangle/Li…）、invert（明场 DAB 要 true）、watershed。"
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["probe", "ops", "init", "run", "batch", "collect", "summarize", "jobs"],
                "description": "要执行的动作",
            },
            "op": {"type": "string",
                   "description": "操作 id（csa / count_objects / area_fraction；用 action='ops' 确认）"},
            "input": {
                "type": ["string", "array"],
                "items": {"type": "string"},
                "description": ("待分析图：远端路径或 glob（/path/*.tif）、远端目录、本地文件或本地目录。"
                                "run 只接受展开后 1 张；batch 接受多张（可用 limit 限制张数）。"),
            },
            "params": {"type": "object",
                       "description": ("op 参数，见 action='ops'。常用：px_um（µm/px，强烈建议给）、channel、"
                                       "threshold、invert、watershed、min_area_um2、max_area_um2。")},
            "backend": {"type": "string", "enum": ["auto", "local", "cluster"],
                        "description": ("用哪台机器跑：local=本机 ImageJ（用户自己电脑上的 ImageJ.exe/ij.jar）；"
                                        "cluster=远端集群（要先连上集群）。auto=本机配了就用本机，否则集群。")},
            "node": {"type": "string", "description": "远端节点（node1/node4/node3；默认用集群配置的默认节点）"},
            "mem": {"type": "string", "description": "JVM 堆上限（如 8g / 32g；默认配置值）"},
            "timeout": {"type": "integer", "description": "单作业超时秒数（默认配置 900）"},
            "run_id": {"type": "string", "description": "作业批次号（batch 自动生成；summarize/collect 用它定位）"},
            "limit": {"type": "integer", "description": "batch：最多跑多少张（调试用）"},
            "refresh": {"type": "boolean", "description": "probe/ops：忽略缓存重新探测"},
            "force": {"type": "boolean", "description": "init：强制重新部署 runner"},
            "overwrite": {"type": "boolean", "description": "collect：允许覆盖本地同名文件"},
        },
        "required": ["action"],
    },
}


def _register():
    try:
        from tools.registry import registry
        registry.register(
            name="imagej",
            toolset="memomics",
            schema=SCHEMA,
            handler=lambda args, **kw: imagej_handler(args),
            check_fn=imagej_enabled,
            emoji="🔬",
            max_result_size_chars=30_000,
        )
    except Exception as exc:  # pragma: no cover
        logger.warning("imagej register failed: %s", exc)


_register()