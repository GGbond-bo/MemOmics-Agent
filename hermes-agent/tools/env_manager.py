# -*- coding: utf-8 -*-
"""环境事务管理（P1-5）：env plan/apply/rollback + 环境指纹溯源

借鉴 OpenAI4S 的 env 事务语义：环境变更"构建 → 验证 → 原子切换"，
apply 前后各写指纹快照，rollback 用 pre 快照的固定版本重建。

- plan:     dry-run，输出将执行的操作清单（不执行）
- apply:    创建/更新环境，前后写 hermes_home/envs/<name>.pre|post.json
- rollback: 用 pre 指纹的固定版本重建环境
- fingerprint: 环境指纹（conda list --json 精简）→ 供 analysis_manifest 溯源

注意：真实 conda 操作分钟级，测试只覆盖纯逻辑（快照/plan/错误路径）。
"""
import json
import os
import shutil
import subprocess

_HERMES_HOME = os.path.normpath(os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "..", "hermes_home"))
ENVS_DIR = os.path.join(_HERMES_HOME, "envs")


def _conda_bin():
    for cand in (shutil.which("conda"), shutil.which("micromamba"), shutil.which("mamba")):
        if cand:
            return cand
    return None


def _snapshot_path(name, tag):
    os.makedirs(ENVS_DIR, exist_ok=True)
    return os.path.join(ENVS_DIR, f"{_sanitize(name)}.{tag}.json")


def _sanitize(name: str) -> str:
    import re
    return re.sub(r"[^\w\-.]", "_", name or "unknown")


def _save_snapshot(name, tag, data):
    with open(_snapshot_path(name, tag), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _load_snapshot(name, tag):
    p = _snapshot_path(name, tag)
    if not os.path.isfile(p):
        return None
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def list_envs() -> list:
    """conda env list --json → [{name, path}]；无 conda 返回 []"""
    bin_ = _conda_bin()
    if not bin_:
        return []
    try:
        r = subprocess.run([bin_, "env", "list", "--json"], capture_output=True, text=True, timeout=30)
        if r.returncode != 0:
            return []
        d = json.loads(r.stdout)
        return [{"name": e.get("name", ""), "path": e.get("path", "")}
                for e in d.get("envs", []) if isinstance(e, dict)]
    except Exception:
        return []


def fingerprint(env_name: str) -> dict:
    """环境指纹：{conda_env, python, packages{name: version}, available}"""
    bin_ = _conda_bin()
    if not bin_:
        return {"conda_env": env_name, "python": "", "packages": {}, "available": False}
    try:
        r = subprocess.run([bin_, "list", "-n", env_name, "--json"],
                           capture_output=True, text=True, timeout=60)
        if r.returncode != 0:
            return {"conda_env": env_name, "python": "", "packages": {}, "available": False}
        pkgs = {}
        for p in json.loads(r.stdout):
            if p.get("name"):
                pkgs[p["name"]] = p.get("version", "")
        return {"conda_env": env_name, "python": pkgs.get("python", ""),
                "packages": pkgs, "available": True}
    except Exception as e:
        return {"conda_env": env_name, "python": "", "packages": {},
                "available": False, "error": str(e)}


def env_plan(name: str, packages=None, action="create") -> dict:
    """dry-run：输出将执行的操作清单（不执行任何命令）"""
    exists = any(e["name"] == name for e in list_envs())
    if action == "create" and exists:
        action = "update"
    cmd = [f"{_conda_bin() or 'conda'}", "create" if action == "create" else "install",
           "-n", name, "-y"] + (packages or [])
    return {
        "env": name, "exists": exists, "action": action, "dry_run": True,
        "apply_command": cmd,
        "ops": [{"op": action, "env": name, "packages": packages or [],
                 "note": "环境已存在，将更新" if (action == "update" and exists) else ""}],
        "rollback_available": _load_snapshot(name, "pre") is not None,
    }


def env_apply(name: str, packages=None, action="create", timeout=1800) -> dict:
    """创建/更新环境；前后写指纹快照。返回 {ok, pre, post, error}"""
    bin_ = _conda_bin()
    if not bin_:
        return {"ok": False, "error": "conda/mamba/micromamba 不可用", "env": name}
    exists = any(e["name"] == name for e in list_envs())
    if action == "create" and exists:
        action = "update"
    pre = fingerprint(name)
    _save_snapshot(name, "pre", pre)
    cmd = ([bin_, "create" if action == "create" else "install", "-n", name, "-y"] + (packages or []))
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        post = fingerprint(name)
        _save_snapshot(name, "post", post)
        return {"ok": False, "env": name, "action": action, "pre": pre, "post": post,
                "error": f"操作超时（>{timeout}s）"}
    ok = r.returncode == 0
    post = fingerprint(name)
    _save_snapshot(name, "post", post)
    return {"ok": ok, "env": name, "action": action, "pre": pre, "post": post,
            "error": None if ok else (r.stderr or r.stdout)[-500:]}


def env_rollback(name: str, timeout=3600) -> dict:
    """用 pre 指纹的固定版本重建环境（conda install 固定版本）"""
    pre = _load_snapshot(name, "pre")
    if not pre or not pre.get("packages"):
        return {"ok": False, "env": name, "error": "无 pre 快照，无法回滚"}
    bin_ = _conda_bin()
    if not bin_:
        return {"ok": False, "env": name, "error": "conda/mamba/micromamba 不可用"}
    pkgs = [f"{k}={v}" for k, v in pre["packages"].items() if k != "python"]
    if pre.get("python"):
        pkgs.append(f"python={pre['python']}")
    cmd = [bin_, "install", "-n", name, "-y"] + pkgs
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return {"ok": False, "env": name, "error": f"回滚超时（>{timeout}s）"}
    return {"ok": r.returncode == 0, "env": name,
            "rollback_to": pre.get("conda_env", name),
            "error": None if r.returncode == 0 else (r.stderr or r.stdout)[-500:]}
