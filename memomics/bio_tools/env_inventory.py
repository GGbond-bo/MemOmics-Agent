"""env_inventory — 本机 / 集群环境清点（环境管理 v1，2026-09-22）。

一次调用产出两样东西：

1) 给人看的清单：本机有什么（R / Python / 生信 CLI / GPU / 资源）+ 集群有什么
   （节点 / 调度器 / 队列 / 目录 / 版本）。WebUI「🧩 环境管理」面板和
   「环境报告」（markdown）都用它。
2) 给 agent 用的环境卡片：一段紧凑文本告诉模型"该用哪个解释器、哪些库装在哪、
   能不能投集群、要细看就调 env_inventory 工具"。

刻意复用现有真源，不制造第二套说法：
- 本机：environment.json（全局环境唯一真源：paths.python / paths.r / paths.cli_tools）
  + 真实探测（which / --version / Rscript -e / importlib.metadata）。
- 集群：remote_cluster（同一份 config.yaml 的 remote: 段、同一套 SSH 探针），
  所以面板里看到的和 agent 投作业时用的是同一个配置。

缓存：hermes_home/env_inventory.json（本机 1 小时 / 集群 10 分钟）。
集群探测可能几十秒 —— 绝不在请求里同步等：server 侧起后台线程刷，面板轮询；
force=True / invalidate() 强刷。
"""
import json
import os
import platform
import re
import shutil
import socket
import subprocess
import sys
import threading
import time

_CACHE_VERSION = 1
_LOCAL_TTL = 3600          # 本机清单：1 小时（装机软件一天也难变一次）
_CLUSTER_TTL = 600         # 集群清单：10 分钟（队列/负载变得快）
_KEY_PKG_TIMEOUT = 40      # 单个解释器报包版本的上限
_R_FULL_TIMEOUT = 90       # 主力 R 全量探测（.libPaths + 包数 + 关键包）上限
_CLI_VERSION_TIMEOUT = 6
_MAX_PYTHON_CANDIDATES = 6
_MAX_R_INSTALLS = 6
_MAX_CLUSTER_NODE_CHECKS = 4

# 缺失这些 = 明确记进 warning（"用户以为有、其实没有"最容易踩）
_KEY_PY_PKGS = [
    "numpy", "pandas", "scipy", "scikit-learn", "matplotlib", "seaborn",
    "scanpy", "anndata", "h5py", "statsmodels", "pysam", "harmonypy",
    "scrublet", "leidenalg", "igraph", "umap-learn", "torch", "scvi-tools",
    "cellrank", "muon", "squidpy", "gseapy", "openpyxl", "pyarrow", "psutil",
]
_KEY_R_PKGS = [
    "Seurat", "SeuratObject", "harmony", "ArchR", "Signac", "SingleCellExperiment",
    "SummarizedExperiment", "ggplot2", "dplyr", "tidyr", "data.table", "Matrix",
    "patchwork", "ggrepel", "ggpubr", "pheatmap", "ComplexHeatmap", "circlize",
    "RColorBrewer", "scales", "svglite", "future", "future.apply",
    "DESeq2", "edgeR", "limma", "clusterProfiler", "enrichplot", "fgsea",
    "GSVA", "msigdbr", "org.Hs.eg.db", "org.Mm.eg.db", "BiocManager", "pak",
    "monocle3", "CellChat", "WGCNA", "chromVAR", "motifmatchr", "TFBSTools",
    "BSgenome", "GenomicRanges", "Rsamtools", "reticulate",
]
# 生信 CLI：name -> 版本参数。命令不存在就记 missing（用户一眼看到"我缺什么"）
_CLI_TOOLS = {
    "samtools": ["--version"], "bcftools": ["--version"], "bedtools": ["--version"],
    "bwa": [], "bowtie2": ["--version"], "hisat2": ["--version"],
    "minimap2": ["--version"], "STAR": ["--version"], "salmon": ["--version"],
    "kallisto": ["version"], "subread-align": [], "featureCounts": ["-v"],
    "fastp": ["--version"], "fastqc": ["--version"], "multiqc": ["--version"],
    "trim_galore": ["--version"], "cutadapt": ["--version"],
    "macs2": ["--version"], "macs3": ["--version"],
    "cellranger": ["--version"], "cellranger-atac": ["--version"],
    "dnbc4tools": ["--version"], "snapatac2": ["--version"], "chromap": ["--version"],
    "bismark": ["--version"], "plink2": ["--version"], "gatk": ["--version"],
    "nextflow": ["-version"], "snakemake": ["--version"],
    "singularity": ["--version"], "apptainer": ["--version"], "docker": ["--version"],
    "conda": ["--version"], "mamba": ["--version"], "uv": ["--version"],
    "git": ["--version"],
}


# ===========================================================================
# 基础工具
# ===========================================================================
_NO_WINDOW = 0x08000000 if os.name == "nt" else 0
_BAT_SUFFIX = (".bat", ".cmd")


def _app_root() -> str:
    """仓库根目录（本文件 = <root>/memomics/bio_tools/env_inventory.py）。"""
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _hermes_home() -> str:
    """定位 hermes_home（配置/缓存都在这）。

    webui/server.py 启动时就设了 HERMES_HOME=<root>/hermes_home；但本模块也会在
    server 之外跑（CLI、测试、独立进程），那时 HERMES_HOME 可能是空的，框架的
    get_hermes_home() 会回落到平台默认目录（Windows 上是 LOCALAPPDATA 下的 hermes），
    那里没有本应用的 config.yaml —— 于是集群配置会被读成"未配置"（实测踩过）。
    所以顺序：环境变量 → 仓库自带 hermes_home（存在即用，和生产一致）→ 框架默认
    → 仓库路径兜底。
    """
    env = os.environ.get("HERMES_HOME") or ""
    if env:
        return env
    local = os.path.join(_app_root(), "hermes_home")
    if os.path.isdir(local):
        return local
    try:
        from hermes_constants import get_hermes_home  # type: ignore
        home = get_hermes_home()
        if home:
            return str(home)
    except Exception:
        pass
    return local


def _cache_path() -> str:
    return os.path.join(_hermes_home(), "env_inventory.json")


def _now() -> float:
    return time.time()


def _iso(ts=None) -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ts if ts else _now()))


def _same_path(a: str, b: str) -> bool:
    if not a or not b:
        return False
    try:
        return os.path.normcase(os.path.abspath(a)) == os.path.normcase(os.path.abspath(b))
    except Exception:
        return a == b


def _run(cmd, timeout: int = 8, env=None, cwd=None) -> dict:
    """跑一条探测命令。永不抛异常：失败也是数据（ok=False + error）。

    Windows 上 .bat/.cmd 不能直接 CreateProcess，统一用 cmd /c 包一层；
    带 CREATE_NO_WINDOW，避免 WebUI 进程弹黑框。
    """
    cmd = [str(c) for c in cmd if str(c)]
    if not cmd:
        return {"ok": False, "rc": None, "out": "", "err": "空命令", "cmd": ""}
    resolved = shutil.which(cmd[0]) or cmd[0]
    if os.name == "nt" and resolved.lower().endswith(_BAT_SUFFIX):
        cmd = ["cmd", "/c"] + cmd
    kwargs = {}
    if _NO_WINDOW:
        kwargs["creationflags"] = _NO_WINDOW
    if cwd:
        kwargs["cwd"] = cwd
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout,
                           encoding="utf-8", errors="replace", env=env, **kwargs)
        return {"ok": p.returncode == 0, "rc": p.returncode,
                "out": (p.stdout or "").strip(), "err": (p.stderr or "").strip(),
                "cmd": " ".join(cmd)}
    except subprocess.TimeoutExpired:
        return {"ok": False, "rc": None, "out": "", "err": "超时 %ss" % timeout,
                "cmd": " ".join(cmd), "timeout": True}
    except Exception as exc:
        return {"ok": False, "rc": None, "out": "", "err": "%s: %s" % (type(exc).__name__, exc),
                "cmd": " ".join(cmd)}


def _first_line(text: str, limit: int = 100) -> str:
    for line in (text or "").splitlines():
        line = line.strip()
        if line:
            return line[:limit]
    return ""


def _last_line(text: str, limit: int = 100) -> str:
    """最后一个非空行。

    本机 .venv 装了 sitecustomize，会在任何 python -c 之前打一行横幅，
    所以"版本号"这类输出必须取最后一行，否则拿到的是横幅（实测踩过）。
    """
    lines = [ln.strip() for ln in (text or "").splitlines() if ln.strip()]
    return lines[-1][:limit] if lines else ""


def _version_token(text: str) -> str:
    """从路径/名字里抠版本号（'R-4.5.3' / 'C:/Program Files/R/R-4.5.3' → '4.5.3'）。"""
    m = re.search(r"\d+\.\d+(?:\.\d+)?", str(text or ""))
    return m.group(0) if m else ""


def _read_environment_json() -> dict:
    """读仓库根的 environment.json（全局环境唯一真源）。失败返回 {}。"""
    path = os.path.join(_app_root(), "environment.json")
    try:
        with open(path, encoding="utf-8-sig") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _declared_paths(section: str) -> list:
    """environment.json 的 paths.<section> 摊平成 [(名字, 路径, 备注)]，跳过 default。"""
    env = _read_environment_json()
    block = ((env.get("paths") or {}).get(section) or {})
    out = []
    if isinstance(block, dict):
        for name, val in block.items():
            if name.startswith("_") or name == "default":
                continue
            if isinstance(val, str):
                out.append((name, val, ""))
            elif isinstance(val, dict):
                path = val.get("bin") or val.get("path") or val.get("exe") or ""
                if path:
                    out.append((name, path, str(val.get("note") or "")))
    return out


def _declared_default(section: str) -> str:
    env = _read_environment_json()
    val = ((env.get("paths") or {}).get(section) or {}).get("default")
    return val if isinstance(val, str) else ""


def _declared_cli_tools() -> list:
    """environment.json 的 paths.cli_tools → [{name, path, note, declared}]。

    条目有三种写法（见 environment.json）：{"exe": ...} / {"bin": ...} /
    {"conda": ..., "memomics_venv": ...}。多解释器那种优先取本应用在用的
    memomics_venv，其次 conda —— 之前只认 bin/path，导致 cellbender/ptrepack
    被误报"未安装"。
    """
    env = _read_environment_json()
    block = ((env.get("paths") or {}).get("cli_tools") or {})
    out = []
    if isinstance(block, dict):
        for name, val in block.items():
            path, note = "", ""
            if isinstance(val, dict):
                note = str(val.get("note") or "")
                for key in ("exe", "bin", "path", "memomics_venv", "conda", "python"):
                    cand = val.get(key)
                    if isinstance(cand, str) and cand.strip():
                        path = cand.strip()
                        break
            elif isinstance(val, str):
                path = val
            out.append({"name": name, "path": path, "note": note, "declared": True})
    return out


def _declared_shared_libs() -> list:
    """environment.json 备忘里声明的共享库（_canonical.python_shared_lib 的 PYTHONPATH=...）。

    本机这份声明说 "PYTHONPATH=D:/Python/site-packages，.venv 缺的包靠它补"。
    实际是否挂载要实测（见 _probe_python 的 declared_shared_mounted），
    不挂载就得说清楚，否则用户会以为这些包能用。
    """
    out = []
    for value in (_declared_notes() or {}).values():
        text = str(value or "")
        if "PYTHONPATH=" not in text:
            continue
        for chunk in text.split("PYTHONPATH=")[1:]:
            path = chunk.split("（")[0].split("(")[0].strip().rstrip("；;，,")
            if path and path not in out:
                out.append(path)
    return out


def _declared_notes() -> dict:
    """environment.json 的 _canonical 备忘（哪些环境是主力、哪些别碰）。"""
    env = _read_environment_json()
    canon = env.get("_canonical") or {}
    return {k: v for k, v in canon.items() if isinstance(v, str) and not k.startswith("_")}


# ===========================================================================
# 缓存
# ===========================================================================
_CACHE_LOCK = threading.RLock()
_CACHE_MEM = {"data": None, "mtime": None}


def _read_cache(reload: bool = False) -> dict:
    with _CACHE_LOCK:
        path = _cache_path()
        try:
            mtime = os.path.getmtime(path)
        except OSError:
            mtime = None
        if not reload and _CACHE_MEM["data"] is not None and _CACHE_MEM["mtime"] == mtime:
            return _CACHE_MEM["data"]
        data = {}
        if mtime is not None:
            try:
                with open(path, encoding="utf-8-sig") as fh:
                    loaded = json.load(fh)
                if isinstance(loaded, dict):
                    data = loaded
            except Exception:
                data = {}
        data.setdefault("version", _CACHE_VERSION)
        _CACHE_MEM["data"] = data
        _CACHE_MEM["mtime"] = mtime
        return data


def _write_cache(**updates) -> dict:
    """合并写回缓存（原子替换）；写失败不影响调用方。"""
    with _CACHE_LOCK:
        data = dict(_read_cache(reload=True))
        data.update(updates)
        data["version"] = _CACHE_VERSION
        path = _cache_path()
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            tmp = path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(data, fh, ensure_ascii=False, indent=1)
            os.replace(tmp, path)
        except Exception:
            pass
        try:
            _CACHE_MEM["mtime"] = os.path.getmtime(path)
        except OSError:
            _CACHE_MEM["mtime"] = None
        _CACHE_MEM["data"] = data
        return data


def _forced(scope: str) -> bool:
    """被 invalidate() 标过"下次要真扫"——不算新鲜，但数据仍在。"""
    return bool(_read_cache().get(scope + "_force"))


def _fresh(scope: str, ttl: int) -> bool:
    data = _read_cache()
    if data.get(scope + "_force"):
        return False
    ts = float(data.get(scope + "_at") or 0)
    return bool(data.get(scope)) and (_now() - ts) < ttl


def _stale_view(scope: str) -> dict:
    """过期/被标脏但**仍有数据**时的降级视图。

    2026-09-23 修「环境清单不能持久保存」：以前只要过了 TTL（本机 1 小时），
    cached_*() 就丢掉全部内容只回 pending，面板退回「还没扫过，正在后台扫描」，
    上次扫到的 R 版本/缺包/警告全部不可见——用户看到的就是"没保存住"。
    现在：有数据就先给数据（标 stale + 年龄），同时 needs_refresh 让后台去重扫，
    扫完自动替换。用户永远能看到上一次的清单。
    """
    data = dict(_read_cache().get(scope) or {})
    if not data:
        return {}
    data["cached"] = True
    data["stale"] = True
    data["needs_refresh"] = True
    data["age_s"] = _age(scope)
    return data


def _age(scope: str):
    ts = float(_read_cache().get(scope + "_at") or 0)
    return round(_now() - ts, 1) if ts else None


def invalidate(scope: str = "all") -> dict:
    """标脏：让下次扫描真的重探（scope = local | cluster | all）。

    2026-09-23 修「重扫失败会把清单弄丢」：以前这里直接把 local/cluster 置 None
    ——点了「🔄 重新扫描」先把上次扫好的清单删掉，这次万一扫失败（R 全量探测超时、
    集群 SSH 卡住），旧清单就**永久没了**，且不是"过期"而是"被删"。
    现在只清时间戳 + 立 *_force 标记（数据留着），重扫成功后由 _write_cache 原子替换；
    重扫失败则旧数据原样保留、只记错误。
    """
    scope = (scope or "all").lower()
    updates = {}
    for name in (("local", "cluster") if scope == "all" else (scope,)):
        if name not in ("local", "cluster"):
            continue
        updates[name + "_at"] = 0
        updates[name + "_force"] = True
    return _write_cache(**updates)


# ===========================================================================
# 本机探测
# ===========================================================================
def _decode_wsl(raw: bytes) -> str:
    """wsl.exe 的输出是 UTF-16LE，直接 utf-8 解会变成一堆 NUL。"""
    if not raw:
        return ""
    if raw.count(b"\x00") > len(raw) // 4:
        for enc in ("utf-16-le", "utf-16"):
            try:
                return raw.decode(enc, "replace")
            except Exception:
                continue
    return raw.decode("utf-8", "replace")


def _probe_wsl() -> dict:
    if os.name != "nt":
        in_wsl = "microsoft" in (platform.release() or "").lower()
        return {"available": True, "native_linux": True,
                "distros": ([{"name": platform.node(), "state": "运行中（当前就是 Linux）"}]
                            if in_wsl else [])}
    exe = shutil.which("wsl")
    if not exe:
        return {"available": False, "distros": [],
                "note": "未安装 WSL（需要 Linux 工具链时可 wsl --install）"}
    try:
        p = subprocess.run([exe, "-l", "-v"], capture_output=True, timeout=15)
        text = _decode_wsl(p.stdout or b"")
    except Exception as exc:
        return {"available": True, "distros": [], "note": "wsl -l -v 失败: %s" % exc}
    distros = []
    for line in text.splitlines()[1:]:
        line = line.replace("*", " ").strip()
        if not line or line.startswith("-"):
            continue
        parts = line.split()
        if not parts:
            continue
        if len(parts) >= 2 and parts[1].lower() in ("running", "stopped", "installed",
                                                    "运行中", "已停止", "正在运行"):
            distros.append({"name": parts[0], "state": parts[1],
                            "version": parts[2] if len(parts) > 2 else ""})
        else:
            distros.append({"name": parts[0], "state": "", "version": ""})
    return {"available": True, "distros": distros,
            "note": "" if distros else "WSL 已安装但没有任何发行版（wsl --install -d Ubuntu）"}


def _probe_gpu() -> dict:
    exe = shutil.which("nvidia-smi")
    if not exe:
        return {"ok": False, "gpus": [],
                "note": "未检测到 NVIDIA 驱动（CPU 模式；torch 需要 CPU 版才跑得动）"}
    res = _run([exe, "--query-gpu=name,memory.total,driver_version", "--format=csv,noheader"],
               timeout=12)
    gpus = []
    if res["ok"]:
        for line in res["out"].splitlines():
            parts = [p.strip() for p in line.split(",")]
            if parts and parts[0]:
                gpus.append({"name": parts[0],
                             "vram_mb": parts[1] if len(parts) > 1 else "",
                             "driver": parts[2] if len(parts) > 2 else ""})
    return {"ok": bool(gpus), "gpus": gpus,
            "note": "" if gpus else (res["err"] or "nvidia-smi 无输出")}


def _ram_gb() -> dict:
    try:
        import psutil  # type: ignore
        vm = psutil.virtual_memory()
        return {"total_gb": round(vm.total / 1024 ** 3, 1),
                "free_gb": round(vm.available / 1024 ** 3, 1), "source": "psutil"}
    except Exception:
        pass
    if os.name != "nt" and os.path.exists("/proc/meminfo"):
        try:
            info = {}
            with open("/proc/meminfo") as fh:
                for line in fh:
                    k, _, v = line.partition(":")
                    info[k.strip()] = v.strip()
            total = float(info.get("MemTotal", "0").split()[0]) / 1024 ** 2
            avail = float(info.get("MemAvailable", "0").split()[0]) / 1024 ** 2
            return {"total_gb": round(total, 1), "free_gb": round(avail, 1),
                    "source": "/proc/meminfo"}
        except Exception:
            pass
    return {"total_gb": None, "free_gb": None, "source": ""}


def _disk_gb(path: str) -> dict:
    try:
        usage = shutil.disk_usage(path)
        return {"path": path, "free_gb": round(usage.free / 1024 ** 3, 1),
                "total_gb": round(usage.total / 1024 ** 3, 1), "ok": True}
    except Exception as exc:
        return {"path": path, "free_gb": None, "total_gb": None, "ok": False,
                "error": str(exc)[:120]}


def _watch_dirs() -> list:
    """值得盯着剩余空间的目录：程序盘 + environment.json 里提到的盘 + 集群本地根。"""
    cands = [_app_root()]
    for section in ("python", "r", "cli_tools"):
        for _name, path, _note in _declared_paths(section):
            cands.append(path)
    try:
        from memomics.bio_tools import remote_cluster as _rc
        cands.append(str(_rc._load_remote_config().get("local_root") or ""))
    except Exception:
        pass
    seen, out = set(), []
    for path in cands:
        if not path:
            continue
        norm = os.path.normcase(os.path.abspath(path))
        root = (os.path.splitdrive(norm)[0] + os.sep) if os.name == "nt" else "/"
        if root in seen:
            continue
        target = root if os.path.isdir(root) else os.path.dirname(norm)
        if not os.path.isdir(target):
            continue
        seen.add(root)
        out.append(target)
        if len(out) >= 5:
            break
    return out


def _probe_system() -> dict:
    return {
        "os": platform.system(), "os_release": platform.release(),
        "platform": platform.platform(), "machine": platform.machine(),
        "hostname": socket.gethostname(), "cpu_logical": os.cpu_count(),
        "cpu_model": (platform.processor() or "").strip()[:120],
        "ram": _ram_gb(),
        "disks": [_disk_gb(d) for d in _watch_dirs()],
        "gpu": _probe_gpu(),
        "wsl": _probe_wsl(),
        "python_running": sys.version.split()[0],
        "python_running_exe": sys.executable,
    }


def _py_pkg_probe_script(names) -> str:
    return ("import json\n"
            "import importlib.metadata as m\n"
            "out = {}\n"
            "for n in %r:\n"
            "    try:\n"
            "        out[n] = m.version(n)\n"
            "    except Exception:\n"
            "        out[n] = None\n"
            "print(json.dumps(out))\n" % (list(names),))


def _probe_one_python(exe: str, label: str, note: str = "") -> dict:
    item = {"label": label, "path": exe, "note": note, "exists": os.path.exists(exe),
            "ok": False, "version": "", "packages": {}, "missing_key": [], "error": ""}
    if not item["exists"]:
        item["error"] = "路径不存在"
        return item
    ver = _run([exe, "-c", "import sys;print(sys.version.split()[0])"], timeout=20)
    if not ver["ok"]:
        item["error"] = _first_line(ver["err"]) or "解释器无法运行"
        return item
    item["version"] = _last_line(ver["out"]) or ver["out"].strip()
    item["ok"] = True
    pkgs = _run([exe, "-c", _py_pkg_probe_script(_KEY_PY_PKGS)], timeout=_KEY_PKG_TIMEOUT)
    if pkgs["ok"]:
        try:
            found = json.loads(pkgs["out"].splitlines()[-1])
            item["packages"] = {k: v for k, v in found.items() if v}
            item["missing_key"] = [k for k, v in found.items() if not v]
        except Exception as exc:
            item["error"] = "包清单解析失败: %s" % exc
    else:
        item["error"] = _first_line(pkgs["err"]) or "包探测失败"
    meta = _run([exe, "-c",
                 "import json,sys,site;print(json.dumps({'prefix':sys.prefix,"
                 "'base':getattr(sys,'base_prefix',sys.prefix),"
                 "'site':[p for p in site.getsitepackages() if p]}))"], timeout=20)
    if meta["ok"]:
        try:
            info = json.loads(meta["out"].splitlines()[-1])
            item["prefix"] = info.get("prefix", "")
            item["in_venv"] = bool(info.get("base")) and info.get("base") != info.get("prefix")
            item["site_packages"] = info.get("site", [])
        except Exception:
            pass
    return item


def _probe_python() -> dict:
    candidates, seen = [], set()

    def add(exe, label, note=""):
        if not exe:
            return
        key = os.path.normcase(os.path.abspath(exe))
        if key in seen:
            return
        seen.add(key)
        candidates.append((exe, label, note))

    add(_declared_default("python"), "environment.json 主力（agent execute_python 用它）")
    for name, path, note in _declared_paths("python"):
        add(path, "environment.json: %s" % name, note)
    add(sys.executable, "WebUI 服务进程解释器")
    for name in ("python", "python3", "py"):
        add(shutil.which(name), "PATH 上的 %s" % name)
    items = [_probe_one_python(exe, label, note)
             for exe, label, note in candidates[:_MAX_PYTHON_CANDIDATES]]
    default = _declared_default("python") or sys.executable
    shared = [p for p in (os.environ.get("PYTHONPATH") or "").split(os.pathsep) if p]
    for _name, path, _note in _declared_paths("python"):
        if "site-packages" in path.lower() and path not in shared:
            shared.append(path)
    declared_shared = [p for p in _declared_shared_libs() if p not in shared]
    shared_out = [{"path": p, "exists": os.path.isdir(p), "source": "PYTHONPATH / environment.json"}
                  for p in shared[:6]]
    shared_out += [{"path": p, "exists": os.path.isdir(p),
                    "source": "_canonical.python_shared_lib（声明）"}
                   for p in declared_shared[:4]]
    # 声明的共享库到底有没有被主力解释器看见？实测一次 sys.path，别猜。
    mounted = None
    probe_exe = default if os.path.exists(default) else (sys.executable or "")
    if declared_shared and probe_exe:
        res = _run([probe_exe, "-c", "import sys,json;print(json.dumps(list(sys.path)))"],
                   timeout=20)
        if res["ok"]:
            try:
                paths = json.loads(_last_line(res["out"]) or "[]")
            except Exception:
                paths = []
            mounted = any(_same_path(p, d) for p in paths for d in declared_shared)
    return {"default": default, "candidates": items, "shared_libs": shared_out,
            "pythonpath": os.environ.get("PYTHONPATH", ""),
            "declared_shared": declared_shared, "declared_shared_mounted": mounted}


def _declared_r_libs(version_hint: str = "") -> list:
    """environment.json 里声明的 R 库目录（lib_user / lib_site），给探测注入 R_LIBS。

    version_hint 给定时只取同版本的库。之前把 R-4.6.1 的库也注入 R-4.5.3 的探测，
    导致 .libPaths 混进 ABI 不同的包目录、包数和缺失清单都不可信（实测踩到）。
    """
    block = ((_read_environment_json().get("paths") or {}).get("r") or {})
    libs, hinted = [], []
    hint = _version_token(version_hint)
    for name, val in block.items():
        if not isinstance(val, dict):
            continue
        same_version = bool(hint) and _version_token(name) == hint
        for field in ("lib_user", "lib_site"):
            path = val.get(field) or ""
            if not path:
                continue
            if path not in libs:
                libs.append(path)
            if same_version and path not in hinted:
                hinted.append(path)
    chosen = hinted or libs
    return [p for p in chosen if os.path.isdir(p)]


def _r_env() -> dict:
    """给 R 探测注入与 execute_r / check_env 完全一致的库路径。

    execute_r 走 persistent_kernel._r_lib_env()、check_env 走自己的 _r_lib_env()，
    两者都是"把 environment.json 里所有版本的 lib_user/lib_site 全注入 R_LIBS"，
    所以探测也必须全注入，否则会出现"面板说缺包、agent 执行却成功"的矛盾。
    """
    env = dict(os.environ)
    libs = _declared_r_libs()
    if libs:
        existing = env.get("R_LIBS")
        env["R_LIBS"] = os.pathsep.join(libs + ([existing] if existing else []))
    return env


def _r_install_candidates() -> list:
    """environment.json 声明的 R + 文件系统里发现的 R。返回 [(名字, Rscript 路径, 备注)]。"""
    out, seen = [], set()

    def add(name, path, note=""):
        if not path:
            return
        key = os.path.normcase(os.path.abspath(path))
        if key in seen:
            return
        seen.add(key)
        out.append((name, path, note))

    for name, path, note in _declared_paths("r"):
        add(name, path, note)
    if os.name == "nt":
        roots = ["C:/Program Files/R", os.path.join(os.environ.get("LOCALAPPDATA", ""), "R"),
                 os.path.join(os.path.expanduser("~"), "R")]
    else:
        roots = ["/usr/lib/R", "/usr/local/lib/R", "/opt/R",
                 os.path.join(os.path.expanduser("~"), "R")]
    for root in roots:
        if not root or not os.path.isdir(root):
            continue
        try:
            children = sorted(os.listdir(root))
        except Exception:
            continue
        for child in children:
            base = os.path.join(root, child)
            for rel in ("bin/x64/Rscript.exe", "bin/Rscript"):
                cand = os.path.join(base, rel)
                if os.path.exists(cand):
                    add(child, cand, "文件系统扫描发现（未在 environment.json 登记）")
    add("PATH 上的 Rscript", shutil.which("Rscript"), "PATH 默认（可能不是主力版本）")
    return out[:_MAX_R_INSTALLS]


_R_FULL_EXPR = (
    "cat(paste(.libPaths(), collapse='|'), '\\n');"
    "ip <- rownames(installed.packages()); cat(length(ip), '\\n');"
    "pkgs <- c(%s);"
    "m <- vapply(pkgs, function(p) requireNamespace(p, quietly=TRUE), logical(1));"
    "cat(paste(pkgs[!m], collapse=','), '\\n');"
    "loc <- vapply(pkgs, function(p) { r <- tryCatch(find.package(p, quiet=TRUE),"
    " error=function(e) ''); if (length(r) && nzchar(r[1])) r[1] else '' }, character(1));"
    "cat(paste(pkgs[nzchar(loc)], loc[nzchar(loc)], sep='=', collapse='|'))"
)


def _probe_one_r(name: str, exe: str, note: str, full: bool) -> dict:
    item = {"name": name, "path": exe, "note": note, "exists": os.path.exists(exe),
            "ok": False, "version": "", "lib_paths": [], "pkg_count": None,
            "missing_key": [], "probed": "light", "libs_injected": [], "libs_same_version": [],
            "pkg_libs": {}, "cross_version_pkgs": {}, "cross_version_libs": [], "error": ""}
    if not item["exists"]:
        item["error"] = "路径不存在"
        return item
    ver = _run([exe, "-e", "cat(R.version$major, R.version$minor, sep='.')"], timeout=60,
               env=_r_env())
    if ver["ok"] and ver["out"]:
        item["version"] = ver["out"].splitlines()[-1].strip()
        item["ok"] = True
    else:
        item["error"] = _first_line(ver["err"]) or "Rscript 无法运行"
        return item
    if not full:
        return item
    item["libs_injected"] = _declared_r_libs()
    item["libs_same_version"] = _declared_r_libs(item["version"])
    expr = _R_FULL_EXPR % ", ".join('"%s"' % p for p in _KEY_R_PKGS)
    res = _run([exe, "-e", expr], timeout=_R_FULL_TIMEOUT, env=_r_env())
    if not res["ok"]:
        item["error"] = _first_line(res["err"]) or "全量探测失败"
        return item
    lines = [ln.strip() for ln in res["out"].splitlines() if ln.strip()]
    if lines:
        item["lib_paths"] = [p for p in lines[0].split("|") if p]
    if len(lines) > 1:
        try:
            item["pkg_count"] = int(lines[1])
        except ValueError:
            pass
    if len(lines) > 2:
        item["missing_key"] = [p for p in lines[2].split(",") if p]
    if len(lines) > 3:
        pkg_libs = {}
        for pair in lines[3].split("|"):
            if "=" in pair:
                name, lib = pair.split("=", 1)
                name, lib = name.strip(), lib.strip()
                if not (name and lib):
                    continue
                # find.package() 回的是 <lib>/<pkg>，这里归一到库根目录，
                # 才能跟 R_LIBS / .libPaths() 里的路径对上（用户要的就是"包在哪个库"）。
                if os.path.basename(lib.replace("\\", "/").rstrip("/")) == name:
                    lib = os.path.dirname(lib.replace("\\", "/"))
                pkg_libs[name] = lib
        item["pkg_libs"] = pkg_libs
        # 跨版本库里的包：能 requireNamespace 成功，但 ABI 未必兼容（本机 4.6.1 的库就是这样）
        mine = _version_token(item["version"])
        other = {p: l for p, l in pkg_libs.items()
                 if _version_token(l) and mine and _version_token(l) != mine}
        item["cross_version_pkgs"] = other
        item["cross_version_libs"] = sorted({l for l in other.values()})
    item["probed"] = "full"
    return item


def _probe_r() -> dict:
    default = _declared_default("r") or (shutil.which("Rscript") or "")
    installs = []
    for name, path, note in _r_install_candidates():
        installs.append(_probe_one_r(name, path, note, full=_same_path(path, default)))
    return {"default": default, "installs": installs, "key_packages": list(_KEY_R_PKGS),
            "declared_libs": _declared_r_libs()}


def _probe_cli_tools() -> dict:
    declared = {t["name"]: t for t in _declared_cli_tools()}
    items = []
    for name, ver_args in _CLI_TOOLS.items():
        items.append(_probe_one_cli(name, ver_args, declared.get(name) or {}))
    known = {i["name"] for i in items}
    for name, info in declared.items():
        if name in known:
            continue
        # environment.json 额外登记的工具（cellbender / ptrepack / pip ...）：也试版本
        items.append(_probe_one_cli(name, ("--version",), info))
    available = [i["name"] for i in items if i["ok"]]
    return {"items": items, "available": available,
            "missing": [i["name"] for i in items if not i["ok"] and not i["declared"]],
            "declared_unavailable": [i["name"] for i in items if not i["ok"] and i["declared"]]}


def _probe_one_cli(name: str, ver_args, info: dict) -> dict:
    """探测单个 CLI：声明路径优先，其次 PATH；跑一次 --version。

    ok=False 分两种：声明过但找不到（declared_unavailable，说明声明写错或没装）和
    纯没装（missing）。两者混在一起报会让人以为满屏都是问题。
    """
    declared = bool(info)
    path = str(info.get("path") or "") or (shutil.which(name) or "")
    item = {"name": name, "path": path, "version": "", "ok": False,
            "declared": declared, "note": str(info.get("note") or "")}
    if not path:
        item["note"] = item["note"] or "未安装 / 不在 PATH"
        return item
    if not os.path.exists(path):
        item["note"] = item["note"] or ("声明的路径不存在: %s" % path)
        return item
    item["ok"] = True
    if ver_args:
        res = _run([path] + list(ver_args), timeout=_CLI_VERSION_TIMEOUT)
        item["version"] = _first_line((res["out"] or "") or (res["err"] or ""), 90)
        if not item["version"] and not res["ok"]:
            item["note"] = item["note"] or ("版本探测失败: %s"
                                            % (_first_line(res["err"]) or "未知原因"))
    return item


def _probe_conda() -> dict:
    exe = shutil.which("conda")
    out = {"available": bool(exe), "path": exe or "", "version": "", "envs": [],
           "note": "", "broken": False,
           # environment.json 的 _canonical 备忘（本机写着"已损坏：zstandard.backend_c 缺失"）。
           # conda --version 是能过的，所以必须把备忘一起报出来，否则会误判成"conda 好用"。
           "canonical_note": str((_declared_notes() or {}).get("conda") or "")}
    if not exe:
        out["note"] = "未安装 conda（不装也能用：本机走 venv + environment.json 声明的路径）"
        return out
    ver = _run([exe, "--version"], timeout=20)
    if ver["ok"]:
        out["version"] = ver["out"].strip()
    else:
        out["broken"] = True
        out["note"] = "conda 命令存在但执行失败：%s" % (_first_line(ver["err"]) or "未知原因")
    res = _run([exe, "env", "list", "--json"], timeout=30)
    if res["ok"]:
        try:
            data = json.loads(res["out"])
            for path in (data.get("envs") or [])[:8]:
                name = os.path.basename(str(path).rstrip("\\/")) or str(path)
                entry = {"name": name, "path": path}
                py = os.path.join(path, "python.exe" if os.name == "nt" else "bin/python")
                if os.path.exists(py):
                    v = _run([py, "-c", "import sys;print(sys.version.split()[0])"], timeout=15)
                    if v["ok"]:
                        entry["python"] = _last_line(v["out"])
                out["envs"].append(entry)
        except Exception as exc:
            out["note"] = out["note"] or ("conda env list 解析失败: %s" % exc)
    else:
        out["broken"] = True
        out["note"] = out["note"] or ("conda env list 失败：%s" % (_first_line(res["err"]) or "未知"))
    return out


_ALERT_MARKERS = ("损坏", "失效", "勿再", "勿依赖", "孤儿", "已从 PATH")


def _declared_known_issues() -> dict:
    """environment.json 的 known_issues（本机已知坑：cellbender 必须 --cuda、TMPDIR 等）。"""
    block = _read_environment_json().get("known_issues") or {}
    return {str(k): str(v) for k, v in block.items()} if isinstance(block, dict) else {}


def _canonical_alerts() -> list:
    """把 environment.json _canonical 备忘里带"坑"字样的条目标成警告。

    本机写着：conda 已损坏 / R-4.4.2·4.6.0·4.6.1 勿再使用 / D:/Python312 孤儿 /
    旧 R 库勿再写入 —— 这些是用户最该知道的事，不该埋在备忘里当背景。
    """
    out = []
    for key, value in (_declared_notes() or {}).items():
        text = str(value or "")
        if any(marker in text for marker in _ALERT_MARKERS):
            out.append("environment.json 标注（%s）：%s" % (key, text))
    return out


def _local_warnings(local: dict) -> list:
    warn = []
    r_block = local.get("r") or {}
    r_default = r_block.get("default") or ""
    r_installs = r_block.get("installs") or []
    r_entry = next((i for i in r_installs if _same_path(i.get("path", ""), r_default)), {})
    if not r_default:
        warn.append("没有可用的 R（execute_r 会失败）：装 R 4.x，把路径写进 "
                    "environment.json 的 paths.r.default")
    elif not r_entry.get("ok"):
        warn.append("主力 R 不可用：%s（%s）" % (r_default, r_entry.get("error", "未知")))
    else:
        if r_entry.get("cross_version_libs"):
            warn.append("主力 R 的库路径里混着其它版本的库（%s）：%s 这些包是从那儿加载的，"
                        "跨版本 ABI 不保证（environment.json 也把 4.6.1 标成失效）"
                        % ("、".join(r_entry["cross_version_libs"]),
                           "、".join(sorted(r_entry.get("cross_version_pkgs") or {})[:6])))
        missing = r_entry.get("missing_key") or []
        if missing:
            head = "、".join(missing[:8]) + ("…" if len(missing) > 8 else "")
            warn.append("主力 R 缺 %d 个关键包：%s（用到时 check_env 会自动装）"
                        % (len(missing), head))
    py_block = local.get("python") or {}
    py_default = py_block.get("default") or ""
    py_items = py_block.get("candidates") or []
    py_entry = next((i for i in py_items if _same_path(i.get("path", ""), py_default)), {})
    if not py_default:
        warn.append("没有指定的 Python：environment.json 的 paths.python.default 为空")
    elif not py_entry.get("ok"):
        warn.append("主力 Python 不可用：%s（%s）" % (py_default, py_entry.get("error", "未知")))
    elif py_entry.get("missing_key"):
        warn.append("主力 Python 缺 %d 个关键包：%s" % (
            len(py_entry["missing_key"]), "、".join(py_entry["missing_key"][:8])))
    py_block2 = local.get("python") or {}
    declared_shared = py_block2.get("declared_shared") or []
    if declared_shared and py_block2.get("declared_shared_mounted") is False:
        warn.append("environment.json 声明的共享库 %s 没被主力 Python 挂载（实测 sys.path 里没有）："
                    "靠它补的包现在其实用不了，缺包请直接装进 .venv"
                    % "、".join(declared_shared))
    cli = local.get("cli_tools") or {}
    if cli.get("declared_unavailable"):
        warn.append("environment.json 登记但找不到的工具（路径写错或没装）：%s"
                    % "、".join(cli["declared_unavailable"][:10]))
    conda = local.get("conda") or {}
    if conda.get("broken"):
        warn.append("conda 命令存在但执行失败：%s（别把依赖装在 conda 环境里）" % conda.get("note", ""))
    for disk in (local.get("system") or {}).get("disks") or []:
        if disk.get("ok") and (disk.get("free_gb") or 0) < 10:
            warn.append("磁盘 %s 剩余仅 %sGB，跑单细胞/ATAC 大文件很容易写满"
                        % (disk.get("path"), disk.get("free_gb")))
    if not (local.get("system") or {}).get("gpu", {}).get("ok"):
        note = (local.get("system") or {}).get("gpu", {}).get("note", "")
        warn.append("没有可用 CUDA GPU：torch/scVI 只能 CPU 跑（大模型训练会很慢）%s"
                    % ("；" + note if note else ""))
    # environment.json 标注的"别碰"放最后：先报会影响当前任务的问题，再报背景备注。
    for alert in _canonical_alerts():
        if alert not in warn:
            warn.append(alert)
    return warn


def _capabilities(local: dict) -> dict:
    """告诉用户/agent「这些能力现在能不能用、具体用哪个」。"""
    py_block = local.get("python") or {}
    r_block = local.get("r") or {}
    py_default = py_block.get("default") or ""
    r_default = r_block.get("default") or ""
    py_entry = next((i for i in py_block.get("candidates") or []
                     if _same_path(i.get("path", ""), py_default)), {})
    r_entry = next((i for i in r_block.get("installs") or []
                    if _same_path(i.get("path", ""), r_default)), {})
    cli = local.get("cli_tools") or {}
    gpu = (local.get("system") or {}).get("gpu") or {}
    conda_raw = local.get("conda") or {}
    return {
        "execute_r": {"ok": bool(r_entry.get("ok")), "uses": r_default,
                      "version": r_entry.get("version", ""),
                      "libs": r_entry.get("lib_paths", []),
                      "pkg_count": r_entry.get("pkg_count")},
        "execute_python": {"ok": bool(py_entry.get("ok")), "uses": py_default,
                           "version": py_entry.get("version", ""),
                           "key_pkgs": len(py_entry.get("packages") or {}),
                           "missing_key": list(py_entry.get("missing_key") or [])[:10],
                           "shared_libs": [s["path"] for s in py_block.get("shared_libs") or []
                                           if s.get("exists")],
                           "declared_shared_mounted": py_block.get("declared_shared_mounted")},
        "terminal": {"ok": True, "shell": "cmd / pwsh" if os.name == "nt" else "bash"},
        "gpu": {"ok": bool(gpu.get("ok")),
                "devices": [g.get("name") for g in gpu.get("gpus") or []]},
        "cluster": {"ok": None, "note": "见 cluster 段"},
        "conda": {"ok": bool(conda_raw.get("available") and not conda_raw.get("broken")),
                  "envs": [e.get("name") for e in conda_raw.get("envs") or []],
                  "note": conda_raw.get("canonical_note") or conda_raw.get("note") or ""},
        "cli_ready": {"count": len(cli.get("available") or []),
                      "highlights": (cli.get("available") or [])[:12]},
    }


def scan_local(force: bool = False) -> dict:
    """本机环境清点（默认走 1 小时缓存）。"""
    if not force and _fresh("local", _LOCAL_TTL):
        data = dict(_read_cache().get("local") or {})
        if data:
            data["cached"] = True
            data["age_s"] = _age("local")
            return data
    started = _now()
    local = {
        "scanned_at": _iso(), "platform": os.name,
        "environment_json": os.path.join(_app_root(), "environment.json"),
        "system": _probe_system(),
        "python": _probe_python(),
        "r": _probe_r(),
        "cli_tools": _probe_cli_tools(),
        "conda": _probe_conda(),
        "canonical_notes": _declared_notes(),
        "canonical_alerts": _canonical_alerts(),
        "known_issues": _declared_known_issues(),
        "hermes_home": _hermes_home(),
    }
    local["capabilities"] = _capabilities(local)
    local["warnings"] = _local_warnings(local)
    local["duration_s"] = round(_now() - started, 1)
    local["cached"] = False
    # 2026-09-23：扫完清掉 force 标记，否则 _fresh 永远为假 → 每轮都重扫
    _write_cache(local=local, local_at=_now(), local_force=False)
    return local


# ===========================================================================
# 集群探测（复用 remote_cluster：同一份配置、同一套 SSH 探针）
# ===========================================================================
def _cluster_module():
    from memomics.bio_tools import remote_cluster as _rc
    return _rc


def _config_path() -> str:
    """remote_cluster 真正会读的那份配置（agent 投作业用的是它）。

    HERMES_HOME 没设时 get_hermes_home() 会回落到平台默认目录，remote_cluster
    就会指到 C:/Users/<user>/AppData/Local/hermes/config.yaml —— 那里根本没有
    本应用的集群配置（实测踩到：面板会显示一个不存在的路径让用户去改）。
    所以：优先用"已存在的 config.yaml"，其次用本应用 hermes_home 下的路径。
    """
    path = ""
    try:
        path = str(_cluster_module()._get_config_path())
    except Exception:
        path = ""
    home = _hermes_home()
    cand = os.path.join(home, "config.yaml") if home else ""
    if cand and os.path.isfile(cand):
        return cand
    if path and os.path.isfile(path):
        return path
    return cand or path


def cluster_configured() -> dict:
    """只看配置，不连网。"""
    try:
        rc = _cluster_module()
        cfg = rc._load_remote_config()
        table = rc._node_table(cfg) or {}
        enabled = bool(rc.remote_cluster_enabled())
    except Exception as exc:
        return {"configured": False, "enabled": False, "nodes": [],
                "error": "%s: %s" % (type(exc).__name__, exc)}
    config_path = _config_path()
    return {"configured": bool(table) and enabled, "enabled": enabled,
            "nodes": sorted(table), "scheduler": (cfg or {}).get("scheduler", ""),
            "workdir": (cfg or {}).get("workdir", ""),
            "default_node": (cfg or {}).get("default_node", ""),
            "node_policy": (cfg or {}).get("node_policy", ""),
            "hermes_home": _hermes_home(), "config_path": config_path}


def _cluster_hint(state: dict) -> str:
    if not state.get("enabled"):
        return ("集群未启用：在 %s 的 remote: 段写 enabled: true + host/user/key/workdir，"
                "或直接打开 WebUI 的「🖧 远端集群」面板填表保存"
                "（agent 的 remote_cluster 工具读同一份配置）"
                % state.get("config_path", "hermes_home/config.yaml"))
    if not state.get("nodes"):
        return ("集群已启用但没有登记节点：config.yaml 的 remote: 段填 host（单节点）"
                "或 nodes: 段登记多台机器（ssh3: {} / ssh5: {}）")
    return ""


def _cluster_versions(output: str) -> dict:
    """从自检输出里抠 python/R 版本行（check 输出的 == versions == 段）。"""
    out = {}
    text = output or ""
    if "== versions ==" in text:
        text = text.split("== versions ==", 1)[1]
    for line in text.splitlines():
        line = line.strip()
        low = line.lower()
        if low.startswith("python") and "python" not in out:
            out["python"] = line[:120]
        elif (low.startswith("r version") or low.startswith("rscript")) and "r" not in out:
            out["r"] = line[:120]
    return out


def scan_cluster(force: bool = False, node: str = "") -> dict:
    """集群环境清点：连通性 + 调度器 + 资源 + 已装工具/版本。

    实测耗时 = 详查节点数 × 探针时间（每节点上限 60s），所以默认走 10 分钟缓存，
    刷新交给后台线程。未配置时纯本地判断，毫秒级返回。
    """
    state = cluster_configured()
    if not force and not node and _fresh("cluster", _CLUSTER_TTL):
        data = dict(_read_cache().get("cluster") or {})
        if data:
            data["cached"] = True
            data["age_s"] = _age("cluster")
            return data
    base = {
        "scanned_at": _iso(), "configured": state.get("configured", False),
        "enabled": state.get("enabled", False), "config_path": state.get("config_path", ""),
        "scheduler": state.get("scheduler", ""), "node_policy": state.get("node_policy", ""),
        "default_node": state.get("default_node", ""), "nodes_configured": state.get("nodes", []),
        "nodes": [], "per_node": {}, "resources": {}, "warnings": [],
    }
    if not state.get("configured"):
        base["hint"] = _cluster_hint(state)
        base["cached"] = False
        if not node and not state.get("error"):
            _write_cache(cluster=base, cluster_at=_now(), cluster_force=False)
        return base
    try:
        rc = _cluster_module()
        raw_nodes = rc.remote_cluster_handler({"action": "nodes", "node": node} if node
                                             else {"action": "nodes"})
        nodes_payload = json.loads(raw_nodes)
    except Exception as exc:
        base["error"] = "%s: %s" % (type(exc).__name__, exc)
        base["hint"] = "集群探测失败（配置或网络问题），可到「🖧 远端集群」面板跑一次自检"
        return base
    if not isinstance(nodes_payload, dict) or nodes_payload.get("status") == "error":
        base["error"] = str((nodes_payload or {}).get("error") or "nodes 探测没有返回结果")
        base["hint"] = "在「🖧 远端集群」面板跑一次自检，看具体是密钥、网络还是目录问题"
        return base
    nodes = nodes_payload.get("nodes") or []
    base["nodes"] = nodes
    base["reachable"] = nodes_payload.get("reachable")
    base["idle_now"] = nodes_payload.get("idle_now") or []
    base["summary"] = nodes_payload.get("summary", "")
    per_node = {}
    checks = 0
    for item in nodes:
        name = str(item.get("name") or "")
        if not item.get("reachable") or not name:
            continue
        if checks >= _MAX_CLUSTER_NODE_CHECKS:
            per_node[name] = {"skipped": "节点较多，只详查前 %d 个（可在「🖧 远端集群」面板单独查）"
                                         % _MAX_CLUSTER_NODE_CHECKS}
            continue
        checks += 1
        try:
            payload = json.loads(rc.remote_cluster_handler({"action": "check", "node": name}))
        except Exception as exc:
            per_node[name] = {"error": "%s: %s" % (type(exc).__name__, exc)}
            continue
        if not isinstance(payload, dict) or payload.get("status") == "error":
            per_node[name] = {"error": str((payload or {}).get("error") or "check 失败")}
            continue
        output = payload.get("output") or ""
        per_node[name] = {
            "scheduler": payload.get("scheduler", ""),
            "workdir": payload.get("workdir", ""),
            "remote_home": payload.get("remote_home", ""),
            "bins": payload.get("bins") or {},
            "output": output[:4000],
            "versions": _cluster_versions(output),
        }
    base["per_node"] = per_node
    cores = [i.get("nproc") or 0 for i in nodes if i.get("reachable")]
    base["resources"] = {
        "total_cores": sum(cores) or None,
        "reachable_nodes": len(cores), "configured_nodes": len(nodes),
        "idle_now": base.get("idle_now") or [],
        "workdirs": sorted({str(i.get("workdir")) for i in nodes if i.get("workdir")}),
        "schedulers": sorted({str(i.get("scheduler")) for i in nodes
                              if i.get("scheduler") and i.get("scheduler") != "none"}),
    }
    for item in nodes:
        if not item.get("reachable"):
            base["warnings"].append("节点 %s 连不上：%s"
                                    % (item.get("name"), str(item.get("error") or "")[:160]))
        elif item.get("workdir_ok") is False:
            base["warnings"].append("节点 %s 的工作目录不存在（%s）"
                                    % (item.get("name"), item.get("workdir")))
    if not base.get("idle_now") and base.get("reachable"):
        base["warnings"].append("所有节点负载都不低（load/核数 ≥ 0.6），投作业前先看队列")
    base["cached"] = False
    if not node:
        _write_cache(cluster=base, cluster_at=_now(), cluster_force=False)
    return base


# ===========================================================================
# 汇总 / 渲染
# ===========================================================================
# ===========================================================================
# 指纹：便宜的"再确认一遍"（2026-09-23）
# ===========================================================================
# 用户诉求：环境清单要能持久保存，下次分析时不重扫、只**确认一遍**——
# 变了就重扫、缺包就补，没变就直接复用（复用 1 小时 TTL 的清单）。
#
# 全量探测 10~45 秒（R 全量最贵）不能每次分析都跑；但只看"装没装东西"用
# 几个 mtime 就够：pip / install.packages / conda 装包都会动这些目录的 mtime。
_FP_STAT_TIMEOUT = 1.0


def _fp_stat(path: str):
    """一个路径的 (mtime, size)；不存在给 None。绝不抛异常。"""
    try:
        st = os.stat(path)
        return [round(st.st_mtime, 1), st.st_size]
    except OSError:
        return None


def _fingerprint() -> dict:
    """当前环境的廉价指纹：几个 stat 就出结果（毫秒级），用来判断"变没变"。

    刻意**不**包含包版本号——那要跑解释器（慢）。装/卸包一定会动
    site-packages 的 mtime，所以"装了新包"必然被这个指纹抓到。
    """
    env_json = os.path.join(_app_root(), "environment.json")
    fp = {
        "environment_json": _fp_stat(env_json),
        "python": None,
        "r": None,
        "conda": None,
    }
    # 主力 Python：解释器 + 它的 site-packages（装包会动 mtime）
    try:
        py_block = (_read_environment_json() or {}).get("paths", {}).get("python", {}) or {}
        py = py_block.get("default") or _declared_default("python") or sys.executable or ""
        if py:
            sp = None
            try:
                sp = os.path.join(os.path.dirname(os.path.abspath(py)), "..", "Lib", "site-packages")
                if not os.path.isdir(sp):
                    sp = os.path.join(os.path.dirname(os.path.abspath(py)), "..", "lib")
            except Exception:
                sp = None
            fp["python"] = {"exe": _fp_stat(py), "site_packages": _fp_stat(os.path.normpath(sp))
                            if sp else None, "path": py}
    except Exception:
        pass
    # 主力 R：解释器 + 已声明的库目录
    try:
        r_default = _declared_default("r") or (_r_env().get("default") or "")
        if r_default:
            libs = []
            for d in _declared_r_libs(""):
                libs.append([d, _fp_stat(d)])
            fp["r"] = {"exe": _fp_stat(r_default), "libs": libs, "path": r_default}
    except Exception:
        pass
    # conda：只看已知位置的存在性/时间（绝不调 _probe_conda —— 那会真去跑 conda --version）
    try:
        cands = []
        env_root = os.environ.get("CONDA_PREFIX") or ""
        if env_root:
            cands.append(env_root)
        for rel in ("miniconda3", "anaconda3", "miniconda", "miniforge3"):
            cands.append(os.path.join(os.path.expanduser("~"), rel))
            cands.append(os.path.join("C:\\", rel))
            cands.append(os.path.join(_app_root(), rel))
        # 显式声明的 conda 环境目录优先
        for p in _declared_paths("conda_envs") or []:
            cands.append(str(p))
        seen = []
        for c in cands:
            c = os.path.normpath(str(c))
            if c and c not in seen:
                seen.append(c)
        fp["conda"] = [[c, _fp_stat(os.path.join(c, "envs"))] for c in seen]
    except Exception:
        pass
    return fp


def verify(force_rescan: bool = False) -> dict:
    """分析前/面板打开时的"确认一遍"：指纹没变就直接复用清单，变了才重扫。

    返回 {"ok", "changed", "reasons", "age_s", "stale", "rescanned", "digest"}。
    这是给"下次遇到分析再确认一遍"用的：毫秒级，不陪 R 全量探测。
    """
    cache = _read_cache()
    old_fp = cache.get("fingerprint")
    now_fp = _fingerprint()
    reasons = []
    if old_fp is None:
        reasons.append("还没有指纹（首次）")
    else:
        for key in ("environment_json", "python", "r", "conda"):
            if old_fp.get(key) != now_fp.get(key):
                reasons.append("%s 变了" % key)
    changed = bool(reasons)
    rescanned = False
    if force_rescan or changed:
        # 变了才真扫（走 scan_local 全量）；没变时一个探测都不做
        try:
            scan_local(force=True)
            _write_cache(fingerprint=now_fp)
            rescanned = True
        except Exception as exc:
            reasons.append("重扫失败：%s" % exc)
    elif not _read_cache().get("fingerprint"):
        _write_cache(fingerprint=now_fp)
    local = cached_local()
    out = {"ok": True, "changed": changed, "reasons": reasons, "rescanned": rescanned,
           "age_s": local.get("age_s"), "stale": bool(local.get("stale")),
           "scanned_at": local.get("scanned_at")}
    try:
        out["digest"] = agent_digest()
    except Exception:
        out["digest"] = ""
    return out


def cached_local() -> dict:
    """只读缓存的本机清单，绝不探测（HTTP 接口用）。

    没有缓存就返回 pending —— 本机首扫 10~40 秒（R 全量探测最慢），
    让请求等这个数字是不可接受的，交给后台线程 + 前端轮询。

    2026-09-23：过期但**有数据**时不再回 pending，而是回旧数据 + needs_refresh
    （见 _stale_view）——清单要能持久看到，不能一过 TTL 就"假装没扫过"。
    """
    if _fresh("local", _LOCAL_TTL):
        data = dict(_read_cache().get("local") or {})
        if data:
            data["cached"] = True
            data["age_s"] = _age("local")
            return data
    stale = _stale_view("local")
    if stale:
        return stale
    return {"pending": True, "scanned_at": "", "age_s": None,
            "hint": "本机环境还没清点过（首次约 10~40 秒，主要在等 R 全量探测）；已在后台扫描"}


def cached_cluster() -> dict:
    """只读缓存的集群段，绝不 SSH（HTTP 接口用）。

    未配置时是纯本地判断（读 config.yaml，毫秒级），每次现算；已配置且缓存新鲜
    才用缓存，过期则返回 pending 由调用方起后台刷新 —— 一次 nodes/check 探测
    可能要几十秒，不能在 HTTP 请求里等。

    2026-09-23：集群**配置态**永远现算（那条不变量不变）；但配置态成立、
    缓存只是过期时，先回上次的节点清单 + needs_refresh，不再丢成 pending。
    """
    if _fresh("cluster", _CLUSTER_TTL):
        data = dict(_read_cache().get("cluster") or {})
        if data and data.get("configured"):
            data["cached"] = True
            data["age_s"] = _age("cluster")
            return data
    state = cluster_configured()
    if not state.get("configured"):
        # 未配置是纯本地判断（读 config.yaml，不 SSH，毫秒级）：必须现算，
        # 否则用户在「🖧 远端集群」面板刚填完配置，这里还要等 TTL 才认。
        return scan_cluster(force=True)
    stale = _stale_view("cluster")
    if stale and stale.get("configured"):
        stale["config_path"] = state.get("config_path") or stale.get("config_path", "")
        stale["enabled"] = state.get("enabled", stale.get("enabled"))
        stale["nodes_configured"] = state.get("nodes") or stale.get("nodes_configured") or []
        return stale
    return {"pending": True, "configured": True, "enabled": state.get("enabled", False),
            "config_path": state.get("config_path", ""),
            "nodes_configured": state.get("nodes", []),
            "hint": "集群正在后台刷新（要逐个 SSH 探测节点），稍后自动更新"}


def build_report(force: bool = False, cluster: bool = True, cache_only: bool = False) -> dict:
    """完整环境报告（本机 + 集群 + 警告 + 给 agent 的摘要）。

    cache_only=True：只用缓存，不触发任何探测（WebUI 接口用，保证秒回）。
    """
    local = cached_local() if cache_only else scan_local(force=force)
    if cache_only:
        cluster_data = cached_cluster() if cluster else None
    else:
        cluster_data = scan_cluster(force=force) if cluster else None
    warnings = list(local.get("warnings") or [])
    if cluster_data:
        warnings += list(cluster_data.get("warnings") or [])
        if not cluster_data.get("configured"):
            warnings.append("集群未配置/未启用：%s" % (cluster_data.get("hint") or ""))
    report = {
        "ok": True, "version": _CACHE_VERSION, "scanned_at": _iso(),
        "local_at": local.get("scanned_at"), "local_age_s": local.get("age_s"),
        "cluster_age_s": (_age("cluster") if cluster_data else None),
        "local": local, "cluster": cluster_data, "warnings": warnings,
        "cache_path": _cache_path(),
    }
    report["agent_digest"] = agent_digest(report)
    return report


def _fmt_pkg_brief(pkgs: dict, picks) -> str:
    return " / ".join("%s %s" % (name, pkgs[name]) for name in picks if name in pkgs)


def _entry_by_path(items, path) -> dict:
    return next((i for i in items or [] if _same_path(i.get("path", ""), path)), {})


def agent_digest(report: dict = None) -> str:
    """给模型的紧凑环境卡片（≤2500 字）。只用缓存，绝不触发探测。"""
    if report is None:
        data = _read_cache()
        if not data.get("local") or (data.get("local") or {}).get("pending"):
            return ("## 环境\n还没有环境清单：需要知道本机 R/Python/工具或集群资源时，"
                    "调 env_inventory 工具（action=overview 或 refresh）拿一次，约 10 秒。")
        report = {"local": data.get("local"), "cluster": data.get("cluster")}
    local = report.get("local") or {}
    if local.get("pending") or not local:
        return ("## 环境\n本机清单还没生成（后台正在扫）。需要马上知道环境时调 "
                "env_inventory 工具（action=overview 或 refresh）。")
    lines = ["## 本机环境（env_inventory，%s）" % (local.get("scanned_at") or "未知时间")]
    caps = local.get("capabilities") or {}
    py = caps.get("execute_python") or {}
    shared = " / ".join(py.get("shared_libs") or [])
    lines.append("- Python（execute_python 就用它）：%s %s%s" % (
        py.get("uses") or "未指定", py.get("version") or "",
        ("（共享库 " + shared + "）") if shared else ""))
    py_entry = _entry_by_path((local.get("python") or {}).get("candidates"), py.get("uses"))
    brief = _fmt_pkg_brief(py_entry.get("packages") or {},
                           ("scanpy", "anndata", "torch", "scvi-tools", "pysam", "harmonypy"))
    if brief:
        lines.append("  · 已装：%s" % brief)
    r = caps.get("execute_r") or {}
    r_entry = _entry_by_path((local.get("r") or {}).get("installs"), r.get("uses"))
    lines.append("- R（execute_r 就用它）：%s R %s；库 %s%s" % (
        r.get("uses") or "未安装", r.get("version") or "",
        " / ".join(r.get("libs") or []) or "（R 没装或不可用）",
        ("；已装包 %s 个" % r_entry.get("pkg_count")) if r_entry.get("pkg_count") else ""))
    if r_entry.get("missing_key"):
        lines.append("  · 缺关键包：%s" % "、".join(r_entry["missing_key"][:10]))
    if r_entry.get("cross_version_libs"):
        lines.append("  · ⚠️ 这些包是从别的 R 版本库加载的（ABI 不保证）：%s"
                     % "、".join(sorted(r_entry.get("cross_version_pkgs") or {})[:6]))
    cli = local.get("cli_tools") or {}
    if cli.get("available"):
        lines.append("- 生信 CLI 可用（%d）：%s"
                     % (len(cli["available"]), "、".join(cli["available"][:14])))
    if cli.get("missing"):
        lines.append("  · 常用但没装：%s" % "、".join(cli["missing"][:12]))
    if cli.get("declared_unavailable"):
        lines.append("  · environment.json 登记了但找不到：%s"
                     % "、".join(cli["declared_unavailable"][:8]))
    sysinfo = local.get("system") or {}
    ram = sysinfo.get("ram") or {}
    disks = [d for d in (sysinfo.get("disks") or []) if d.get("ok")][:2]
    gpu = sysinfo.get("gpu") or {}
    lines.append("- 资源：CPU %s 核 · 内存 %sGB%s%s" % (
        sysinfo.get("cpu_logical") or "?",
        ram.get("total_gb") if ram.get("total_gb") else "?",
        (" · 磁盘 " + "、".join("%s 剩 %sGB" % (d.get("path"), d.get("free_gb")) for d in disks))
        if disks else "",
        (" · GPU " + "、".join(g.get("name") or "" for g in gpu.get("gpus") or []))
        if gpu.get("ok") else " · 无 GPU"))
    cluster = report.get("cluster")
    if cluster:
        if cluster.get("configured"):
            res = cluster.get("resources") or {}
            lines.append("- 集群：%s/%s 节点可连 · 核数合计 %s · 调度器 %s · 空闲节点 %s" % (
                res.get("reachable_nodes") or 0, res.get("configured_nodes") or 0,
                res.get("total_cores") or "?", "、".join(res.get("schedulers") or []) or "?",
                "、".join(cluster.get("idle_now") or []) or "无"))
            lines.append("  · 投作业用 remote_cluster（submit/status/logs）；"
                         "详细环境调 env_inventory(action=cluster)")
        else:
            lines.append("- 集群：未配置（%s）" % (cluster.get("hint") or ""))
    issues = local.get("known_issues") or {}
    if issues:
        pairs = list(issues.items())[:2]
        lines.append("- 已知坑（environment.json）：%s"
                     % "；".join("%s = %s" % (k, str(v)[:70]) for k, v in pairs))
    for warn in (report.get("warnings") or local.get("warnings") or [])[:5]:
        lines.append("- ⚠️ %s" % warn)
    lines.append("需要更细的清单（每个解释器的包版本、每个节点的目录/工具、集群队列）→ 调 "
                 "env_inventory 工具（action=overview / local / cluster / refresh / markdown）。")
    return "\n".join(lines)


def _md_table(headers, rows) -> str:
    out = ["| " + " | ".join(headers) + " |",
           "| " + " | ".join("---" for _ in headers) + " |"]
    for row in rows:
        out.append("| " + " | ".join("" if c is None else str(c) for c in row) + " |")
    return "\n".join(out)


def render_markdown(report: dict = None, force: bool = False, cache_only: bool = False) -> str:
    """人看的 markdown 环境报告（可直接贴给同事/存档）。

    cache_only=True：只用缓存（WebUI 的 /api/env/report.md 用它，保证秒回）。
    """
    if report is None:
        report = build_report(force=force, cache_only=cache_only)
    local = report.get("local") or {}
    if local.get("pending") or not local:
        return ("# 环境报告\n\n本机清单还没生成（后台正在扫，首次约 10~40 秒）。"
                "稍后刷新，或在对话里让 agent 调 env_inventory(action=refresh)。\n")
    sysinfo = local.get("system") or {}
    ram = sysinfo.get("ram") or {}
    age = local.get("age_s") or report.get("local_age_s") or 0
    out = ["# 环境报告（MemOmics 环境管理）", "",
           "- 生成时间：%s" % report.get("scanned_at", _iso()),
           "- 本机清单：%s（缓存 %.0f 秒前）" % (local.get("scanned_at", "?"), age or 0),
           "- 缓存文件：%s" % (report.get("cache_path") or _cache_path()),
           "- hermes_home：%s" % local.get("hermes_home", ""),
           "- 平台：%s %s（%s）" % (sysinfo.get("os", ""), sysinfo.get("os_release", ""),
                                  sysinfo.get("machine", "")), ""]
    if report.get("warnings"):
        out += ["## ⚠️ 需要注意", ""]
        out += ["- %s" % w for w in report["warnings"]]
        out.append("")
    out += ["## 本机资源", "",
            _md_table(["项目", "值"], [
                ["主机名", sysinfo.get("hostname", "")],
                ["CPU", "%s 核 %s" % (sysinfo.get("cpu_logical") or "?",
                                     sysinfo.get("cpu_model") or "")],
                ["内存", "%sGB（可用 %sGB）" % (ram.get("total_gb") or "?",
                                              ram.get("free_gb") or "?")],
                ["GPU", "、".join(g.get("name") or ""
                                 for g in (sysinfo.get("gpu") or {}).get("gpus") or []) or "无"],
                ["WSL", "、".join(d.get("name") or ""
                                 for d in (sysinfo.get("wsl") or {}).get("distros") or []) or "无"],
            ]), ""]
    if sysinfo.get("disks"):
        out += [_md_table(["磁盘", "剩余", "总量"],
                          [[d.get("path"), "%sGB" % d.get("free_gb"),
                            "%sGB" % d.get("total_gb")] for d in sysinfo["disks"]]), ""]
    py_rows = []
    for i in (local.get("python") or {}).get("candidates") or []:
        if i.get("ok"):
            state = ("缺 %d 个关键包" % len(i.get("missing_key") or [])) if i.get("missing_key") else "✓"
        else:
            state = "✗ " + (i.get("error") or "")
        py_rows.append([i.get("label"), i.get("path"), i.get("version") or "-",
                        len(i.get("packages") or {}), state])
    out += ["## Python", "", _md_table(["角色", "解释器", "版本", "已装关键包", "状态"], py_rows), ""]
    py_block = local.get("python") or {}
    shared = py_block.get("shared_libs") or []
    if shared:
        line = "共享库（PYTHONPATH，给 venv 补包）：%s" % "、".join(
            "%s%s" % (s["path"], "" if s.get("exists") else "（不存在）") for s in shared)
        if py_block.get("declared_shared") and py_block.get("declared_shared_mounted") is not None:
            line += "；声明的共享库%s被主力解释器挂载（实测 sys.path）" % (
                "已" if py_block.get("declared_shared_mounted") else "**没有**")
        out += [line, ""]
    r_rows = []
    for item in (local.get("r") or {}).get("installs") or []:
        if item.get("missing_key"):
            state = "缺 " + "、".join((item.get("missing_key") or [])[:6])
        elif item.get("ok"):
            state = "✓（全量探测）" if item.get("probed") == "full" else "✓（仅版本）"
        else:
            state = "✗ " + (item.get("error") or "")
        r_rows.append([item.get("name"), item.get("path"), item.get("version") or "-",
                       item.get("pkg_count") or "-", state])
    out += ["## R", "", _md_table(["名称", "Rscript", "版本", "包数", "状态"], r_rows), ""]
    libs = [i for i in (local.get("r") or {}).get("installs") or [] if i.get("lib_paths")]
    if libs:
        out += ["库路径（注入 R_LIBS 的，与 execute_r / check_env 一致）："
                + "；".join("%s = %s" % (i.get("name"), "、".join(i["lib_paths"]))
                            for i in libs), ""]
    cross = [i for i in (local.get("r") or {}).get("installs") or [] if i.get("cross_version_libs")]
    if cross:
        out += ["跨版本加载的包（从别的 R 版本库加载，ABI 不保证，别当主力依赖）：", ""]
        for i in cross:
            out.append("- **%s**：%s" % (i.get("name"), "、".join(
                "%s ← %s" % (p, l)
                for p, l in sorted((i.get("cross_version_pkgs") or {}).items())[:10])))
        out.append("")
    cli = (local.get("cli_tools") or {}).get("items") or []
    if cli:
        out += ["## 生信 CLI 工具", "",
                _md_table(["工具", "状态", "路径", "版本", "说明"],
                          [[i.get("name"),
                            "✓" if i.get("ok") else ("✗ 登记未找到" if i.get("declared") else "✗"),
                            i.get("path") or "-", i.get("version") or "-",
                            (i.get("note") or "")[:60]] for i in cli]), ""]
    conda = local.get("conda") or {}
    conda_note = conda.get("canonical_note") or conda.get("note") or ""
    out += ["## conda", "",
            "- 可用：%s%s" % ("是" if conda.get("available") and not conda.get("broken") else "否",
                            ("；" + conda_note) if conda_note else ""),
            "- 环境：%s" % ("、".join("%s(%s)" % (e.get("name"), e.get("python") or "?")
                                    for e in conda.get("envs") or []) or "无"), ""]
    issues = local.get("known_issues") or {}
    if issues:
        out += ["## 已知坑（environment.json known_issues）", ""]
        out += ["- **%s**：%s" % (k, v) for k, v in issues.items()]
        out.append("")
    notes = local.get("canonical_notes") or {}
    if notes:
        out += ["## environment.json 备忘（全局环境唯一真源）", ""]
        out += ["- **%s**：%s" % (k, v) for k, v in notes.items()]
        out.append("")
    cluster = report.get("cluster")
    if cluster:
        out += ["## 集群", ""]
        if cluster.get("configured"):
            res = cluster.get("resources") or {}
            out += ["- 可连节点：%s/%s；核数合计 %s；调度器 %s；空闲节点：%s" % (
                res.get("reachable_nodes"), res.get("configured_nodes"), res.get("total_cores"),
                "、".join(res.get("schedulers") or []) or "?",
                "、".join(cluster.get("idle_now") or []) or "无"),
                "- 工作目录：%s" % ("、".join(res.get("workdirs") or []) or "-"), ""]
            out += [_md_table(["节点", "主机", "核数", "负载(1m)", "空闲", "工作目录",
                               "剩余空间", "调度器"],
                              [[n.get("name"), n.get("host") or n.get("remote_hostname") or "-",
                                n.get("nproc") or "-",
                                n.get("load1") if n.get("load1") is not None else "-",
                                "是" if n.get("idle_guess") else ("否" if n.get("reachable") else "-"),
                                n.get("workdir") or "-", n.get("workdir_df") or "-",
                                n.get("scheduler") or "-"]
                               for n in cluster.get("nodes") or []]), ""]
            for name, info in (cluster.get("per_node") or {}).items():
                if info.get("error") or info.get("skipped"):
                    out.append("- %s：%s" % (name, info.get("error") or info.get("skipped")))
                    continue
                bins = {k: v for k, v in (info.get("bins") or {}).items() if v}
                ver = info.get("versions") or {}
                out.append("- **%s**：调度器 %s；工作目录 %s；可用命令 %s%s" % (
                    name, info.get("scheduler") or "?",
                    info.get("workdir") or info.get("remote_home") or "?",
                    "、".join(sorted(bins)[:16]) or "无",
                    ("；" + "；".join("%s = %s" % (k, v) for k, v in ver.items())) if ver else ""))
            out.append("")
        else:
            out += ["- 未配置：%s" % (cluster.get("hint") or ""),
                    "- 配置位置：%s（或 WebUI 的「🖧 远端集群」面板）"
                    % cluster.get("config_path", ""), ""]
    out += ["## 给 Agent 的环境卡片", "", "~~~", agent_digest(report), "~~~", ""]
    return "\n".join(out)


# ===========================================================================
# 工具入口（agent 可调用）
# ===========================================================================
SCHEMA = {
    "name": "env_inventory",
    "description": (
        "清点本机与集群的可用环境（用户问「我有什么环境/资源」、或你要决定用哪个 "
        "Python/R 解释器、哪些库、能不能投集群、集群什么队列/资源时先调它）。"
        "action=overview（默认：本机+集群+警告+给模型的摘要）/ local（本机明细：每个"
        "解释器版本与已装包、R 各版本与库路径与缺失关键包、生信 CLI 工具、conda、GPU、"
        "磁盘）/ cluster（集群节点、核数、负载、调度器、目录、已装工具与版本）/ "
        "refresh（强制重新探测：本机约 5-20 秒，集群每节点最长 60 秒）/ "
        "verify（**便宜地再确认一遍**：毫秒级，指纹没变就直接复用清单，变了才重扫 —— "
        "分析开工前用它，代替无脑重扫）/ "
        "markdown（人看的报告）。结果有缓存（本机 1 小时 / 集群 10 分钟），不会每次都真探测。"
        "本机清单缓存在 <hermes_home>/env_inventory.json，WebUI 的「🧩 环境管理」面板"
        "与它同源 —— 用户看到的和你用的是同一份。"
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["overview", "local", "cluster", "refresh", "markdown", "verify"],
                "description": "要哪部分（默认 overview）；verify = 便宜地确认环境有没有变（毫秒级，变了才重扫）",
                "default": "overview",
            },
            "node": {
                "type": "string",
                "description": "只查某个集群节点（名字见 cluster 结果；留空=全部）",
                "default": "",
            },
        },
    },
}


def env_inventory_handler(action: str = "overview", node: str = "", **kwargs) -> str:
    _ = kwargs
    action = (action or "overview").strip().lower()
    try:
        if action == "verify":
            payload = dict(verify(), local=cached_local())
        elif action == "local":
            payload = {"ok": True, "local": scan_local(force=False)}
        elif action == "cluster":
            payload = {"ok": True, "cluster": scan_cluster(force=False, node=node)}
        elif action == "refresh":
            invalidate("all")
            payload = build_report(force=True)
        elif action == "markdown":
            payload = {"ok": True, "markdown": render_markdown()}
        else:
            payload = build_report(force=False)
        payload["action"] = action
        return json.dumps(payload, ensure_ascii=False)
    except Exception as exc:
        return json.dumps({"ok": False, "status": "error", "action": action,
                           "error": "%s: %s" % (type(exc).__name__, exc)},
                          ensure_ascii=False)


def _register():
    from tools.registry import registry
    registry.register(
        name="env_inventory",
        toolset="memomics",
        schema=SCHEMA,
        handler=lambda args, **kw: env_inventory_handler(
            args.get("action", "overview"), args.get("node", ""), **kw),
        emoji="🧩",
        max_result_size_chars=60_000,
    )


try:
    _register()
except Exception:  # 脱离 hermes 运行时（单测 / CLI）不注册，不影响 import
    pass


def _main(argv=None) -> int:
    import argparse
    parser = argparse.ArgumentParser(description="MemOmics 环境清点（环境管理）")
    parser.add_argument("--json", action="store_true", help="输出 JSON（默认 markdown）")
    parser.add_argument("--refresh", action="store_true", help="忽略缓存重新探测")
    parser.add_argument("--no-cluster", action="store_true", help="跳过集群探测")
    parser.add_argument("--out", default="", help="写入文件（默认打印到 stdout）")
    args = parser.parse_args(argv)
    if args.json:
        text = json.dumps(build_report(force=args.refresh, cluster=not args.no_cluster),
                          ensure_ascii=False, indent=2)
    else:
        text = render_markdown(force=args.refresh)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(text)
        print("已写入 %s（%d 字）" % (args.out, len(text)))
    else:
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(_main())
