# -*- coding: utf-8 -*-
"""大输入（≥100MB）持久化判定 + 任务标记 + 安全清理（2026-10-08，方案 A 配套）。

用户要求（原话，2026-10-08）：
  「检测到执行读取数据分析，弹窗询问用户要不要持久化，大于 100M 的内容，都要推荐持久化。
    比如 RDS、h5ad，一些超大表格也是一样，并做好任务标记，方便清理。」

本模块只做「判定 → 记账 → 清理」三件事，**不解析数据本身**：

  1. ``scan``  给一批输入路径 → 报大小/类型/指纹；≥ ``--min-mb``（默认 100）的条目
               ``recommend_persist=True``，供 agent 弹 ``ask_user`` 询问用户。
  2. ``mark``  把「读了什么、缓存/检查点放哪、谁建的、何时过期、怎么清」写成一个
               **任务标记**：``<runtime>/cache_markers/<task_id>.json``（原子写），
               并追加登记到 ``cache_markers/index.jsonl`` → ``list`` 一眼看全、``clean`` 一把清。
  3. ``clean`` 按标记删除**缓存/检查点产物**，绝不碰原始数据（硬保护见 ``_is_protected``）。

刻意不做的事：
  - **不解析 rds/h5ad**（那要 R / scanpy，属作业内的事）。缓存「怎么建」由作业脚本负责，
    模板见 skill ``remote-cluster-execution`` → ``scripts/checkpoint_job.R``；本模块只记账。
  - **不在本机访问远端**：远端产物只打印清理命令（由 ``remote_cluster`` 执行），
    不在本机假装删掉了。
  - 不写数据目录以外的地方；删错东西比不删更贵，所以清理有三道闸（原始数据保护 /
    缓存根约束 / 默认 dry-run）。

CLI::

    python -m memomics.bio_tools.large_cache scan <path...> [--min-mb 100] [--json]
    python -m memomics.bio_tools.large_cache mark --task-id ID --title T --input P --cache-root D
                                                  [--artifact P] [--remote] [--note N] [--ttl-days 14]
    python -m memomics.bio_tools.large_cache list [--json] [--stale-days 14]
    python -m memomics.bio_tools.large_cache show <task_id>
    python -m memomics.bio_tools.large_cache verify <task_id> [--json]
    python -m memomics.bio_tools.large_cache clean <task_id> | --all | --stale-days 14
                                                  [--dry-run] [--force]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
import tempfile
from datetime import datetime, timezone

_THIS = os.path.abspath(__file__)
_REPO = os.path.dirname(os.path.dirname(os.path.dirname(_THIS)))
RUNTIME_DIR = os.environ.get("MEMOMICS_RUNTIME_DIR") or os.path.join(
    _REPO, "memomics_home", "runtime")
MARKERS_DIR = os.environ.get("MEMOMICS_CACHE_MARKERS_DIR") or os.path.join(
    RUNTIME_DIR, "cache_markers")
INDEX_FILE = os.path.join(MARKERS_DIR, "index.jsonl")
DEFAULT_MIN_MB = 100.0
DEFAULT_TTL_DAYS = 14
SCHEMA_VERSION = 1

# 扩展名 → 类型（用于给「缓存怎么建」提建议；未知 → generic）
_KIND = {
    ".rds": "seurat_or_r_object", ".rda": "r_object", ".rdata": "r_object", ".qs": "qs_object",
    ".h5ad": "anndata_h5ad", ".h5": "hdf5_10x", ".hdf5": "hdf5", ".loom": "loom",
    ".zarr": "zarr_store", ".mtx": "matrix_market",
    ".bam": "alignment_bam", ".cram": "alignment_cram",
    ".fastq": "reads_fastq", ".fq": "reads_fastq",
    ".csv": "table_csv", ".tsv": "table_tsv", ".txt": "table_txt",
    ".parquet": "table_parquet", ".feather": "table_feather", ".gz": "compressed",
}
# 缓存体积经验占比（估算值，非测量值；用于提示用户「缓存大概多大」）
_CACHE_RATIO = {
    "seurat_or_r_object": 0.05, "r_object": 0.05, "qs_object": 0.05,
    "anndata_h5ad": 0.05, "hdf5_10x": 0.05, "hdf5": 0.05, "loom": 0.05,
    "zarr_store": 0.05, "matrix_market": 0.05,
    "table_csv": 0.20, "table_tsv": 0.20, "table_txt": 0.20,
    "table_parquet": 0.20, "table_feather": 0.20,
}
_CACHE_RATIO_DEFAULT = 0.10


# ---------------------------------------------------------------- 工具

def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def human(n) -> str:
    """1.5 GB 这种人读单位。"""
    try:
        n = float(n)
    except (TypeError, ValueError):
        return "-"
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(n) < 1024.0 or unit == "TB":
            return f"{n:.1f} {unit}" if unit != "B" else f"{int(n)} B"
        n /= 1024.0
    return f"{n:.1f} TB"


def _atomic_write_json(path: str, data: dict) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(os.path.abspath(path)), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass


def fingerprint(path: str, chunk: int = 1 << 20) -> str:
    """大文件指纹：size + 首尾各 1MB 的 sha256 —— 不整读 10GB，秒级返回。

    同 size 同首尾 = 认为同一份（足够判「输入有没有被改动」；不做全量哈希是有意的）。
    """
    st = os.stat(path)
    h = hashlib.sha256()
    h.update(str(st.st_size).encode())
    with open(path, "rb") as f:
        h.update(f.read(chunk))
        if st.st_size > chunk:
            f.seek(max(0, st.st_size - chunk))
            h.update(f.read(chunk))
    return "sha256:" + h.hexdigest()[:32]


def classify(path: str, is_dir: bool = False) -> str:
    if is_dir:
        return _KIND.get(os.path.splitext(path.rstrip("/\\"))[1].lower(), "directory")
    return _KIND.get(os.path.splitext(path)[1].lower(), "other")


def _dir_size(path: str) -> int:
    total = 0
    for root, _dirs, files in os.walk(path):
        for fn in files:
            try:
                total += os.path.getsize(os.path.join(root, fn))
            except OSError:
                pass
    return total


# ---------------------------------------------------------------- scan

def scan(paths, min_mb: float = DEFAULT_MIN_MB) -> dict:
    """判定哪些输入该建议持久化。返回 {"items": [...], "recommend": [...]}。"""
    items = []
    for p in paths:
        p = os.path.abspath(p)
        if not os.path.exists(p):
            items.append({"path": p, "exists": False, "size": 0, "size_h": "-",
                          "recommend_persist": False, "reason": "路径不存在"})
            continue
        is_dir = os.path.isdir(p)
        try:
            size = _dir_size(p) if is_dir else os.path.getsize(p)
        except OSError as e:
            items.append({"path": p, "exists": True, "size": 0, "size_h": "-",
                          "recommend_persist": False, "reason": f"读取失败: {e}"})
            continue
        kind = classify(p, is_dir)
        mb = size / (1024.0 * 1024.0)
        rec = mb >= float(min_mb)
        ratio = _CACHE_RATIO.get(kind, _CACHE_RATIO_DEFAULT)
        entry = {
            "path": p,
            "exists": True,
            "is_dir": is_dir,
            "size": size,
            "size_h": human(size),
            "size_mb": round(mb, 1),
            "kind": kind,
            "mtime": datetime.fromtimestamp(os.path.getmtime(p), timezone.utc)
            .isoformat(timespec="seconds"),
            "recommend_persist": rec,
            "reason": (f"{human(size)} ≥ 阈值 {min_mb:g}MB → 建议持久化（缓存/检查点），"
                       f"避免每次重读" if rec else
                       f"{human(size)} < 阈值 {min_mb:g}MB → 无需持久化"),
            "est_cache_size_mb": round(mb * ratio, 1) if rec else 0,
            "est_note": "缓存体积为经验估算（非实测），实际取决于保留哪些字段",
        }
        if not is_dir:
            try:
                entry["fingerprint"] = fingerprint(p)
            except OSError as e:
                entry["fingerprint"] = f"unavailable: {e}"
        items.append(entry)
    return {
        "schema": SCHEMA_VERSION,
        "min_mb": float(min_mb),
        "scanned_at": utc_now(),
        "items": items,
        "recommend": [i["path"] for i in items if i.get("recommend_persist")],
    }


# ---------------------------------------------------------------- 远端 scan（2026-10-08 铁规 10 集群侧补全）

def scan_remote(paths, node: str = "", min_mb: float = DEFAULT_MIN_MB) -> dict:
    """集群侧的 scan：经 remote_cluster run 批量 stat/du，产出与 scan 同构的 items。

    不取指纹（远端首尾 1MB 要经 SSH 搬回来，收益不抵成本；size+mtime 已够判「变没变」）。
    远端命令走 scan_only=True 内部通道 —— 那是 remote_cluster 持久化硬闸的自家查体积动作，
    不该被硬闸自己拦下。
    """
    if not paths:
        return {"schema": SCHEMA_VERSION, "min_mb": float(min_mb), "scanned_at": utc_now(),
                "items": [], "recommend": [], "remote": True}
    import shlex
    # standalone CLI 场景：服务器进程里 HERMES_HOME/MEMOMICS_HOME 已就位；裸 shell 里没有，
    # remote_cluster 会掉到平台默认 home（找不着仓库的 remote 配置）——指回仓库的 memomics_home
    # （2026-10-08 起 config.yaml 在 memomics_home/，不在 hermes_home/）
    _mh = os.path.join(_REPO, "memomics_home")
    if os.path.isfile(os.path.join(_mh, "config.yaml")):
        if not os.environ.get("MEMOMICS_HOME"):
            os.environ["MEMOMICS_HOME"] = _mh
        if not os.environ.get("HERMES_HOME"):
            os.environ["HERMES_HOME"] = _mh
    try:
        from memomics.bio_tools import remote_cluster as rc
    except ImportError:
        # 直跑文件（python memomics/bio_tools/large_cache.py）时仓库根不在 sys.path
        if _REPO not in sys.path:
            sys.path.insert(0, _REPO)
        from memomics.bio_tools import remote_cluster as rc
    quoted = " ".join(shlex.quote(str(p)) for p in paths[:20])
    cmd = ("for p in " + quoted + "; do "
           "if [ -d \"$p\" ]; then "
           "echo \"DIR $(du -sb \"$p\" 2>/dev/null | cut -f1) $(stat -c '%Y' \"$p\" 2>/dev/null) $p\"; "
           "elif [ -f \"$p\" ]; then "
           "echo \"FILE $(stat -c '%s %Y' \"$p\" 2>/dev/null) $p\"; "
           "else echo \"MISS 0 0 $p\"; fi; done")
    args = {"action": "run", "command": cmd, "scan_only": True}
    if node:
        args["node"] = node
    raw = rc.remote_cluster_handler(args)
    try:
        res = json.loads(raw)
    except Exception:
        res = {}
    if res.get("status") == "error":
        raise RuntimeError("远端 scan 失败：%s" % res.get("error"))
    items = []
    for line in (res.get("output") or "").splitlines():
        line = line.strip()
        if not line or line.startswith("[") or line.startswith("=="):
            continue
        parts = line.split(None, 3)
        if len(parts) < 4 or parts[0] not in ("FILE", "DIR", "MISS"):
            continue
        tag, size_s, mtime_s, pth = parts[0], parts[1], parts[2], parts[3].strip()
        is_dir = tag == "DIR"
        try:
            size = int(size_s)
        except ValueError:
            size = 0
        if tag == "MISS":
            items.append({"path": pth, "exists": False, "size": 0, "size_h": "-",
                          "recommend_persist": False, "reason": "远端路径不存在", "remote": True})
            continue
        kind = classify(pth, is_dir)
        mb = size / (1024.0 * 1024.0)
        rec = mb >= float(min_mb)
        ratio = _CACHE_RATIO.get(kind, _CACHE_RATIO_DEFAULT)
        try:
            mtime_iso = datetime.fromtimestamp(int(mtime_s), timezone.utc).isoformat(timespec="seconds")
        except ValueError:
            mtime_iso = ""
        items.append({
            "path": pth, "exists": True, "is_dir": is_dir, "size": size,
            "size_h": human(size), "size_mb": round(mb, 1), "kind": kind,
            "mtime": mtime_iso, "remote": True,
            "recommend_persist": rec,
            "reason": (f"{human(size)} ≥ 阈值 {min_mb:g}MB → 建议持久化（缓存/检查点），"
                       f"避免每次重读" if rec else
                       f"{human(size)} < 阈值 {min_mb:g}MB → 无需持久化"),
            "est_cache_size_mb": round(mb * ratio, 1) if rec else 0,
            "est_note": "缓存体积为经验估算（非实测），实际取决于保留哪些字段",
            "fingerprint": "remote:未取（size+mtime 已够判变更）",
        })
    return {
        "schema": SCHEMA_VERSION, "min_mb": float(min_mb), "scanned_at": utc_now(),
        "items": items, "recommend": [i["path"] for i in items if i.get("recommend_persist")],
        "remote": True, "node": node,
    }


def marked_remote_paths() -> set:
    """账本里所有 active 远端标记覆盖的输入路径（裸路径集合；同一集群共享文件系统，
    按路径判即可）。供 remote_cluster 的持久化硬闸查询。"""
    out = set()
    for m in list_markers():
        if not m.get("remote"):
            continue
        if m.get("status") not in (None, "active"):
            continue
        for it in m.get("inputs", []):
            p = it.get("path")
            if p:
                out.add(str(p))
    return out


# ---------------------------------------------------------------- 任务标记

def marker_path(task_id: str) -> str:
    """标记路径。**严格拒绝**路径穿越（不靠『过滤掉分隔符』——那会把
    '../../etc/passwd' 变成 '....etcpasswd' 静默写进标记目录，属于掩耳盗铃）。"""
    tid = str(task_id)
    if (not tid or tid in (".", "..") or tid.startswith(".")
            or any(c in tid for c in "/\\") or tid != os.path.basename(tid)):
        raise ValueError("task_id 非法（不得含路径分隔符/.. / 以 . 开头）")
    safe = "".join(c for c in tid if c.isalnum() or c in "-_.")
    if not safe or safe != tid:
        raise ValueError("task_id 非法（只允许字母数字 - _ .）")
    return os.path.join(MARKERS_DIR, safe + ".json")


def save_marker(marker: dict) -> str:
    path = marker_path(marker["task_id"])
    marker["updated_at"] = utc_now()
    _atomic_write_json(path, marker)
    try:  # 索引是「方便看」，坏了不影响主标记 → 静默降级
        os.makedirs(MARKERS_DIR, exist_ok=True)
        with open(INDEX_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps({
                "task_id": marker["task_id"], "title": marker.get("title", ""),
                "updated_at": marker["updated_at"],
                "inputs": [i.get("path") for i in marker.get("inputs", [])],
                "cache_root": marker.get("cache_root", ""),
                "remote": bool(marker.get("remote")),
                "expires_at": marker.get("expires_at", ""),
            }, ensure_ascii=False) + "\n")
    except OSError:
        pass
    return path


def new_marker(task_id: str, title: str, inputs, cache_root: str = "",
               artifacts=None, remote: bool = False, note: str = "",
               ttl_days: int = DEFAULT_TTL_DAYS, session_dir: str = "",
               cache_scope: str = "") -> dict:
    """建一个任务标记（并落盘）。inputs: scan 的 items 或裸路径列表。

    ``cache_scope`` / ``not_included`` 是 2026-10-08 L2 辩论席位一致点名的溯源缺口：
    用户看到「有缓存」会以为全量都缓存了，而精简缓存**不含表达量矩阵**（DE/CellChat/
    轨迹仍需回读原文件）。所以标记里显式声明缓存范围与**未包含**的内容。
    """
    ins = []
    for it in inputs or []:
        if isinstance(it, dict):
            ins.append({k: it.get(k) for k in
                        ("path", "size", "size_h", "kind", "fingerprint", "mtime")
                        if it.get(k) is not None})
        else:
            # 远端路径不能 os.path.abspath（Windows 上会拼出 E:\...\/hwfssz3 这种怪胎）——原样保留
            ins.append({"path": str(it) if remote else os.path.abspath(str(it))})
    exp = None
    if ttl_days and int(ttl_days) > 0:
        from datetime import timedelta
        exp = (datetime.now(timezone.utc) + timedelta(days=int(ttl_days))).isoformat(
            timespec="seconds")
    marker = {
        "schema": SCHEMA_VERSION,
        "task_id": task_id,
        "title": title,
        "created_at": utc_now(),
        "updated_at": utc_now(),
        "session_dir": session_dir,
        "remote": bool(remote),
        "inputs": ins,
        "cache_root": str(cache_root) if remote else (os.path.abspath(cache_root) if cache_root else ""),
        "artifacts": [(str(a) if remote else os.path.abspath(a)) for a in (artifacts or [])],
        "expires_at": exp or "",
        "ttl_days": int(ttl_days),
        "note": note,
        "cache_scope": cache_scope or "未声明（缓存内容以作业脚本为准）",
        "not_included": ["expression_matrix", "counts", "scale.data"],
        "cleanup_cmd": "python -m memomics.bio_tools.large_cache clean " + str(task_id),
        "status": "active",
    }
    save_marker(marker)
    return marker


def load_marker(task_id: str) -> dict | None:
    p = marker_path(task_id)
    if not os.path.exists(p):
        return None
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def list_markers(stale_days: int = 0) -> list:
    if not os.path.isdir(MARKERS_DIR):
        return []
    out = []
    now = datetime.now(timezone.utc)
    for fn in sorted(os.listdir(MARKERS_DIR)):
        if not fn.endswith(".json"):
            continue
        try:
            with open(os.path.join(MARKERS_DIR, fn), encoding="utf-8") as f:
                m = json.load(f)
        except (OSError, json.JSONDecodeError):
            continue
        rows = []
        for a in m.get("artifacts", []):
            ex = os.path.exists(a)
            rows.append({"path": a, "exists": ex,
                         "size": os.path.getsize(a) if (ex and os.path.isfile(a)) else 0})
        m["_artifact_rows"] = rows
        m["_total_bytes"] = sum(r["size"] for r in rows)
        m["_total_h"] = human(m["_total_bytes"])
        m["_missing"] = [r["path"] for r in rows if not r["exists"]]
        if stale_days:
            try:
                age = (now - datetime.fromisoformat(m["updated_at"])).days
                m["_age_days"] = age
                m["_stale"] = age >= int(stale_days)
            except (KeyError, ValueError):
                m["_age_days"] = -1
                m["_stale"] = False
        out.append(m)
    return out


def verify(marker: dict) -> dict:
    """标记自证：产物在不在、输入指纹变没变。"""
    problems, checks = [], []
    for a in marker.get("artifacts", []):
        ok = os.path.exists(a)
        checks.append({"artifact": a, "exists": ok,
                       "size_h": human(os.path.getsize(a)) if ok and os.path.isfile(a) else "-"})
        if not ok:
            problems.append(f"产物缺失: {a}")
    for it in marker.get("inputs", []):
        p, want = it.get("path"), it.get("fingerprint")
        if not p:
            continue
        if not os.path.exists(p):
            problems.append(f"输入缺失: {p}")
            continue
        if want:
            try:
                got = fingerprint(p)
            except OSError as e:
                problems.append(f"输入指纹不可读: {p} ({e})")
                continue
            if got != want:
                problems.append(f"输入已变更（缓存应失效）: {p}")
    return {"task_id": marker.get("task_id"), "ok": not problems,
            "checks": checks, "problems": problems}


# ---------------------------------------------------------------- 清理（三道闸）

def _is_protected(target: str, marker: dict) -> str:
    """返回非空字符串 = 拒绝理由。三道闸：原始数据 / 缓存根 / 存在性。"""
    t = os.path.abspath(target)
    for it in marker.get("inputs", []):
        ip = it.get("path")
        if ip and os.path.abspath(ip) == t:
            return "命中原始数据保护（原始输入永不删除）"
    root = marker.get("cache_root") or ""
    if not root:
        return "标记未声明 cache_root，拒绝猜测删除范围"
    root_abs = os.path.abspath(root)
    if not (t == root_abs or t.startswith(root_abs + os.sep)):
        return f"不在声明的 cache_root 内（{root_abs}）"
    return ""


def clean(task_id: str = "", all_markers: bool = False, stale_days: int = 0,
          dry_run: bool = True, force: bool = False) -> dict:
    targets = []
    if task_id:
        m = load_marker(task_id)
        if not m:
            return {"ok": False, "error": f"找不到标记: {task_id}", "deleted": [], "skipped": []}
        targets = [m]
    else:
        for m in list_markers(stale_days=stale_days):
            if all_markers or m.get("_stale"):
                targets.append(m)

    deleted, skipped, remote_cmds = [], [], []
    for m in targets:
        tid = m.get("task_id", "?")
        arts = m.get("artifacts", []) or [m.get("cache_root", "")] 
        for a in arts:
            if not a:
                continue
            reason = _is_protected(a, m)
            if reason:
                skipped.append({"task_id": tid, "path": a, "reason": reason})
                continue
            # 远端产物先行判定：本机看不见集群文件系统，不能因为 os.path.exists=False
            # 就静默跳过（那会让用户以为已经清理了）。一律只给命令。
            if m.get("remote"):
                remote_cmds.append(f"rm -rf '{a}'   # 远端产物，由 remote_cluster run 执行")
                if not dry_run:
                    skipped.append({"task_id": tid, "path": a,
                                    "reason": "远端路径不在本机删（仅给出命令）"})
                continue
            if not os.path.exists(a):
                skipped.append({"task_id": tid, "path": a, "reason": "已不存在"})
                continue
            try:
                sz = _dir_size(a) if os.path.isdir(a) else os.path.getsize(a)
            except OSError:
                sz = 0
            if dry_run and not force:
                deleted.append({"task_id": tid, "path": a, "size_h": human(sz),
                                "action": "would-delete"})
                continue
            try:
                if os.path.isdir(a):
                    shutil.rmtree(a)
                else:
                    os.remove(a)
                deleted.append({"task_id": tid, "path": a, "size_h": human(sz),
                                "action": "deleted"})
            except OSError as e:
                skipped.append({"task_id": tid, "path": a, "reason": f"删除失败: {e}"})
        # 标记本身：非 dry-run 且产物已处理 → 归档（status=cleaned），不物理删（留痕好追溯）
        if not dry_run and tid != "?":
            m["status"] = "cleaned"
            m["cleaned_at"] = utc_now()
            try:
                save_marker(m)
            except OSError:
                pass
    return {"ok": True, "dry_run": bool(dry_run and not force),
            "deleted": deleted, "skipped": skipped, "remote_commands": remote_cmds,
            "note": "原始数据受保护，永不删除；远端产物只给命令，不在本机假装删除。"}


# ---------------------------------------------------------------- CLI

def _cmd_scan(a) -> int:
    res = scan_remote(a.paths, node=a.node, min_mb=a.min_mb) if a.remote else scan(a.paths, a.min_mb)
    if a.json:
        print(json.dumps(res, ensure_ascii=False, indent=2))
    else:
        for i in res["items"]:
            flag = "★推荐持久化" if i.get("recommend_persist") else "  无需"
            print(f"{flag}  {i.get('size_h', '-'):>10}  {i.get('kind', '-'):<20} {i.get('path')}")
        print(f"\n共 {len(res['items'])} 项，建议持久化 {len(res['recommend'])} 项"
              f"（阈值 {res['min_mb']:g}MB）")
        for p in res["recommend"]:
            print(f"  → {p}")
    return 0


def _cmd_mark(a) -> int:
    inputs = []
    for p in (a.input or []):
        if a.remote:
            # 远端路径本机不 stat/abspath（体积交给 scan --remote 查）；原样记账
            inputs.append({"path": str(p)})
        else:
            sc = scan([p], a.min_mb)["items"][0]
            inputs.append(sc)
    m = new_marker(a.task_id, a.title or a.task_id, inputs, cache_root=a.cache_root,
                   artifacts=a.artifact or [], remote=a.remote, note=a.note or "",
                   ttl_days=a.ttl_days, session_dir=a.session_dir or "",
                   cache_scope=a.cache_scope or "")
    print(f"标记已落盘: {marker_path(m['task_id'])}")
    print(f"  输入 {len(m['inputs'])} 项 / 产物 {len(m['artifacts'])} 项 / "
          f"cache_root={m['cache_root'] or '-'} / 过期 {m['expires_at'] or 'never'}")
    print(f"  清理命令: {m['cleanup_cmd']}")
    return 0


def _cmd_list(a) -> int:
    ms = list_markers(stale_days=a.stale_days)
    if a.json:
        print(json.dumps(ms, ensure_ascii=False, indent=2))
        return 0
    if not ms:
        print("没有任务标记。")
        return 0
    for m in ms:
        stale = "  [过期]" if m.get("_stale") else ""
        rr = "(远端)" if m.get("remote") else ""
        print(f"- {m.get('task_id')}  {m.get('status','?'):<8}{rr}{stale}")
        print(f"    {m.get('title','')}  产物 {m.get('_total_h','-')}"
              f"  缺失 {len(m.get('_missing', []))} 项")
        print(f"    清理: {m.get('cleanup_cmd','')}")
    print(f"\n共 {len(ms)} 个标记。")
    return 0


def _cmd_show(a) -> int:
    m = load_marker(a.task_id)
    if not m:
        print(f"找不到标记: {a.task_id}")
        return 2
    print(json.dumps(m, ensure_ascii=False, indent=2))
    return 0


def _cmd_verify(a) -> int:
    m = load_marker(a.task_id)
    if not m:
        print(f"找不到标记: {a.task_id}")
        return 2
    r = verify(m)
    if a.json:
        print(json.dumps(r, ensure_ascii=False, indent=2))
    else:
        print(("✅ 自证通过" if r["ok"] else "❌ 自证失败") + f"  task_id={r['task_id']}")
        for c in r["checks"]:
            print(f"  {'OK ' if c['exists'] else 'MISS'}  {c['size_h']:>10}  {c['artifact']}")
        for p in r["problems"]:
            print(f"  问题: {p}")
    return 0 if r["ok"] else 2


def _cmd_clean(a) -> int:
    r = clean(task_id=a.task_id or "", all_markers=a.all_markers,
              stale_days=a.stale_days, dry_run=not a.yes, force=a.force)
    if a.json:
        print(json.dumps(r, ensure_ascii=False, indent=2))
    else:
        mode = "DRY-RUN（未真删，加 --yes 才动手）" if r.get("dry_run") else "已执行删除"
        print(f"{mode}：将处理 {len(r['deleted'])} 项 / 跳过 {len(r['skipped'])} 项")
        for d in r["deleted"]:
            print(f"  {d['action']:<14} {d['size_h']:>10}  {d['path']}")
        for s in r["skipped"]:
            print(f"  skip({s['reason']})  {s['path']}")
        for c in r.get("remote_commands", []):
            print(f"  远端待清: {c}")
    return 0 if r.get("ok") else 2


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="large_cache",
                                description="大输入(≥100MB)持久化判定 / 任务标记 / 安全清理")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("scan", help="扫输入体积，标出建议持久化的项")
    s.add_argument("paths", nargs="+")
    s.add_argument("--remote", action="store_true",
                   help="路径在集群上：经 remote_cluster 远端 stat（需先配好 remote 段）")
    s.add_argument("--node", default="", help="远端节点名（--remote 时用；留空 = 默认节点）")
    s.add_argument("--min-mb", type=float, default=float(
        os.environ.get("MEMOMICS_CACHE_MIN_MB", DEFAULT_MIN_MB)))
    s.add_argument("--json", action="store_true")
    s.set_defaults(func=_cmd_scan)

    s = sub.add_parser("mark", help="写任务标记（方便以后清理）")
    s.add_argument("--task-id", required=True)
    s.add_argument("--title", default="")
    s.add_argument("--input", action="append", default=[])
    s.add_argument("--cache-root", default="")
    s.add_argument("--cache-scope", default="",
                   help='缓存范围声明，如 "reductions+metadata（不含表达量矩阵）"')
    s.add_argument("--artifact", action="append", default=[])
    s.add_argument("--remote", action="store_true", help="产物在远端集群")
    s.add_argument("--note", default="")
    s.add_argument("--ttl-days", type=int, default=DEFAULT_TTL_DAYS)
    s.add_argument("--session-dir", default="")
    s.add_argument("--min-mb", type=float, default=DEFAULT_MIN_MB)
    s.set_defaults(func=_cmd_mark)

    s = sub.add_parser("list", help="列出全部标记")
    s.add_argument("--json", action="store_true")
    s.add_argument("--stale-days", type=int, default=0)
    s.set_defaults(func=_cmd_list)

    s = sub.add_parser("show", help="看单个标记原文")
    s.add_argument("task_id")
    s.set_defaults(func=_cmd_show)

    s = sub.add_parser("verify", help="标记自证（产物在不在/输入变没变）")
    s.add_argument("task_id")
    s.add_argument("--json", action="store_true")
    s.set_defaults(func=_cmd_verify)

    s = sub.add_parser("clean", help="清理（默认 dry-run）")
    s.add_argument("task_id", nargs="?", default="")
    s.add_argument("--all", dest="all_markers", action="store_true")
    s.add_argument("--stale-days", type=int, default=0)
    s.add_argument("--yes", action="store_true", help="真删（不加 = dry-run）")
    s.add_argument("--force", action="store_true", help="忽略 dry-run 直接删")
    s.add_argument("--json", action="store_true")
    s.set_defaults(func=_cmd_clean)
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())