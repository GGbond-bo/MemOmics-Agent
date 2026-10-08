# -*- coding: utf-8 -*-
"""large_cache（大输入持久化判定 / 任务标记 / 安全清理）守卫测试 —— 2026-10-08。

覆盖：阈值判定（100MB 线上/线下）、类型识别、大文件指纹（不整读）、标记生命周期
（mark→list→verify→clean）、**三道清理闸**（原始数据保护 / cache_root 约束 / 默认 dry-run）、
远端产物只给命令不假删、CLI 冒烟。

按 test_task_run.py 的约定用 importlib 按文件路径加载，绕开 memomics.bio_tools 包的重量级 __init__。
"""
import importlib.util
import json
import os
import subprocess
import sys

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO = os.path.dirname(os.path.dirname(_HERE))
LC = os.path.join(_REPO, "memomics", "bio_tools", "large_cache.py")


def _load():
    spec = importlib.util.spec_from_file_location("large_cache_under_test", LC)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture()
def lc(tmp_path):
    mod = _load()
    mod.MARKERS_DIR = str(tmp_path / "cache_markers")
    mod.INDEX_FILE = os.path.join(mod.MARKERS_DIR, "index.jsonl")
    return mod


def _big(path, mb):
    """建一个稀疏大文件（不真占盘）。"""
    with open(path, "wb") as f:
        f.truncate(int(mb * 1024 * 1024))
    return str(path)


# ------------------------------------------------------------------ scan

def test_scan_threshold_and_recommendation(lc, tmp_path):
    small = tmp_path / "small.csv"
    small.write_text("a,b\n1,2\n", encoding="utf-8")
    big = _big(tmp_path / "big.rds", 120)
    res = lc.scan([str(small), big], min_mb=100)
    by = {os.path.basename(i["path"]): i for i in res["items"]}
    assert by["small.csv"]["recommend_persist"] is False
    assert by["big.rds"]["recommend_persist"] is True
    assert by["big.rds"]["kind"] == "seurat_or_r_object"
    assert by["big.rds"]["est_cache_size_mb"] > 0        # 给出缓存体积估算
    assert res["recommend"] == [big]
    assert "估算" in by["big.rds"]["est_note"]            # 估算值必须标明


def test_scan_exact_boundary_and_missing(lc, tmp_path):
    """恰好 100MB = 推荐（>= 不是 >）；不存在的路径不炸。"""
    edge = _big(tmp_path / "edge.h5ad", 100)
    res = lc.scan([edge, str(tmp_path / "nope.rds")], min_mb=100)
    assert res["items"][0]["recommend_persist"] is True
    assert res["items"][0]["kind"] == "anndata_h5ad"
    assert res["items"][1]["exists"] is False
    assert res["items"][1]["recommend_persist"] is False


def test_scan_dir_and_custom_min_mb(lc, tmp_path):
    d = tmp_path / "store.zarr"
    d.mkdir()
    (d / "chunk0").write_bytes(b"x" * 2048)
    res = lc.scan([str(d)], min_mb=0.001)
    assert res["items"][0]["is_dir"] is True
    assert res["items"][0]["recommend_persist"] is True
    assert res["items"][0]["size"] >= 2048


def test_fingerprint_is_cheap_and_sensitive(lc, tmp_path):
    """指纹只读首尾 1MB（10GB 也秒回），且能察觉内容变化。"""
    p = _big(tmp_path / "huge.rds", 200)
    fp1 = lc.fingerprint(p)
    assert lc.fingerprint(p) == fp1                       # 稳定
    with open(p, "r+b") as f:                             # 只改尾部
        f.seek(int(199 * 1024 * 1024))
        f.write(b"CHANGED")
    assert lc.fingerprint(p) != fp1                       # 尾部变化也能抓到


# ------------------------------------------------------------------ 标记生命周期

def test_mark_list_show_verify_clean(lc, tmp_path):
    big = _big(tmp_path / "MF_clean.rds", 150)
    cache_root = tmp_path / "cache"
    cache_root.mkdir()
    art = cache_root / "MF_light.rds"
    art.write_bytes(b"y" * 4096)

    m = lc.new_marker("task-1", "MF 长任务", lc.scan([big])["items"],
                      cache_root=str(cache_root), artifacts=[str(art)],
                      note="reductions+meta only")
    assert os.path.exists(lc.marker_path("task-1"))
    assert lc.load_marker("task-1")["title"] == "MF 长任务"

    rows = lc.list_markers()
    assert len(rows) == 1 and rows[0]["_total_bytes"] == 4096
    assert lc.verify(m)["ok"] is True

    r = lc.clean(task_id="task-1", dry_run=True)          # 默认 dry-run
    assert r["ok"] and r["dry_run"] is True
    assert art.exists()                                   # 没真删
    assert r["deleted"][0]["action"] == "would-delete"

    r2 = lc.clean(task_id="task-1", dry_run=False)
    assert not art.exists() and r2["deleted"][0]["action"] == "deleted"
    assert lc.load_marker("task-1")["status"] == "cleaned"  # 标记留痕不物理删
    assert os.path.exists(big)                            # 原始数据毫发无损


def test_clean_protects_source_even_if_declared_as_artifact(lc, tmp_path):
    """把原始数据误写进 artifacts → 必须被闸门拒绝，用户数据不可删。"""
    big = _big(tmp_path / "raw.rds", 101)
    cache_root = tmp_path / "cache"
    cache_root.mkdir()
    lc.new_marker("task-2", "误配", lc.scan([big])["items"],
                  cache_root=str(cache_root), artifacts=[big])
    r = lc.clean(task_id="task-2", dry_run=False)
    assert os.path.exists(big), "原始数据被删了 —— 保护闸失效"
    assert any("原始数据保护" in s["reason"] for s in r["skipped"])


def test_clean_refuses_artifact_outside_cache_root(lc, tmp_path):
    """artifact 不在声明的 cache_root 内 → 拒绝（防手滑删别处）。"""
    big = _big(tmp_path / "x.rds", 101)
    cache_root = tmp_path / "cache"
    cache_root.mkdir()
    outside = tmp_path / "elsewhere" / "junk.bin"
    outside.parent.mkdir()
    outside.write_bytes(b"z" * 128)
    lc.new_marker("task-3", "越界", lc.scan([big])["items"],
                  cache_root=str(cache_root), artifacts=[str(outside)])
    r = lc.clean(task_id="task-3", dry_run=False)
    assert outside.exists()
    assert any("不在声明的 cache_root 内" in s["reason"] for s in r["skipped"])


def test_clean_no_cache_root_refuses(lc, tmp_path):
    """未声明 cache_root → 整体拒绝（不许猜删除范围）。"""
    big = _big(tmp_path / "y.rds", 101)
    stray = tmp_path / "cached.bin"
    stray.write_bytes(b"q" * 64)
    lc.new_marker("task-4", "无根", lc.scan([big])["items"], artifacts=[str(stray)])
    r = lc.clean(task_id="task-4", dry_run=False)
    assert os.path.exists(big) and stray.exists()
    assert any("未声明 cache_root" in s["reason"] for s in r["skipped"])


def test_clean_remote_only_prints_command(lc, tmp_path):
    """远端产物不在本机假删，只给命令（由 remote_cluster 执行）。"""
    big = _big(tmp_path / "remote.rds", 120)
    lc.new_marker("task-5", "集群任务", lc.scan([big])["items"],
                  cache_root="/hwfssz3/PS_JLU/zhangbo/cache",
                  artifacts=["/hwfssz3/PS_JLU/zhangbo/cache/light.rds"], remote=True)
    r = lc.clean(task_id="task-5", dry_run=False)
    assert any("rm -rf" in c for c in r["remote_commands"])
    assert not any(d["action"] == "deleted" for d in r["deleted"])


def test_clean_stale_and_all(lc, tmp_path):
    a = _big(tmp_path / "a.rds", 101)
    for tid in ("s1", "s2"):
        root = tmp_path / tid
        root.mkdir()
        (root / "c.bin").write_bytes(b"c" * 64)
        lc.new_marker(tid, tid, lc.scan([a])["items"], cache_root=str(root),
                      artifacts=[str(root / "c.bin")])
    assert lc.clean(task_id="", all_markers=False, stale_days=0, dry_run=True)["deleted"] == []
    r_all = lc.clean(task_id="", all_markers=True, dry_run=True)
    assert len(r_all["deleted"]) == 2
    # 不给阈值就不判 stale；把 updated_at 改老 → 才算过期
    # （注意：不能走 save_marker——它按语义会重新盖 updated_at，这里要直接改文件）
    assert len(lc.list_markers(stale_days=0)) == 2
    for tid in ("s1", "s2"):
        p = lc.marker_path(tid)
        with open(p, encoding="utf-8") as f:
            m = json.load(f)
        m["updated_at"] = "2020-01-01T00:00:00+00:00"
        with open(p, "w", encoding="utf-8") as f:
            json.dump(m, f, ensure_ascii=False)
    aged = lc.list_markers(stale_days=1)
    assert len(aged) == 2 and all(m["_stale"] is True for m in aged)
    assert len(lc.clean(task_id="", stale_days=1, dry_run=True)["deleted"]) == 2


def test_marker_id_sanitised(lc):
    with pytest.raises(ValueError):
        lc.marker_path("../../etc/passwd")


# ------------------------------------------------------------------ CLI

def test_cli_smoke(tmp_path):
    big = _big(tmp_path / "cli.rds", 110)
    env = dict(os.environ)
    # CLI 输出含中文（reason 等）：父进程 text=True 默认按 locale(GBK) 解码会炸，
    # 显式 utf-8 才与子进程 print 的实际编码一致（2026-10-08 实踩）
    kw = dict(capture_output=True, text=True, encoding="utf-8", errors="replace", env=env)
    p = subprocess.run([sys.executable, LC, "scan", big, "--json"], **kw)
    assert p.returncode == 0, p.stderr
    data = json.loads(p.stdout)
    assert data["recommend"] == [big]

    root = tmp_path / "croot"
    root.mkdir()
    p2 = subprocess.run([sys.executable, LC, "mark", "--task-id", "cli1",
                         "--title", "CLI", "--input", big, "--cache-root", str(root)],
                        **kw)
    assert p2.returncode == 0, p2.stderr
    assert "cleanup_cmd" in p2.stdout or "clean" in p2.stdout

    p3 = subprocess.run([sys.executable, LC, "list"], **kw)
    assert p3.returncode == 0


# ------------------------------------------------------------------ 远端（铁规 10 硬闸配套，2026-10-08）

def _load_rc():
    """按文件路径加载 remote_cluster（绕开包 __init__；_register 需要 hermes-agent 在 sys.path）。"""
    rc_path = os.path.join(_REPO, "memomics", "bio_tools", "remote_cluster.py")
    ha = os.path.join(_REPO, "hermes-agent")
    if ha not in sys.path:
        sys.path.insert(0, ha)
    spec = importlib.util.spec_from_file_location("remote_cluster_under_test", rc_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_marker_remote_paths_not_mangled(lc):
    """remote=True 时输入/产物/cache_root 原样记账（不许被 abspath 拼成 Windows 怪胎）。"""
    m = lc.new_marker("t-remote", "远端任务", ["/hwfssz3/PS_JLU/zhangbo/x.rds"],
                      remote=True, cache_root="/hwfssz3/PS_JLU/zhangbo/cache",
                      artifacts=["/hwfssz3/PS_JLU/zhangbo/cache/x.qs"])
    assert m["inputs"][0]["path"] == "/hwfssz3/PS_JLU/zhangbo/x.rds"
    assert m["cache_root"] == "/hwfssz3/PS_JLU/zhangbo/cache"
    assert m["artifacts"][0] == "/hwfssz3/PS_JLU/zhangbo/cache/x.qs"
    # 远端 active 标记进查询集合；本机标记不进
    assert "/hwfssz3/PS_JLU/zhangbo/x.rds" in lc.marked_remote_paths()
    lc.new_marker("t-local", "本机", [], remote=False)
    assert not any(p.startswith("t-local") for p in lc.marked_remote_paths())
    # cleaned 的远端标记不再算数
    mm = lc.load_marker("t-remote")
    mm["status"] = "cleaned"
    lc.save_marker(mm)
    assert "/hwfssz3/PS_JLU/zhangbo/x.rds" not in lc.marked_remote_paths()


def test_persist_gate_paths_extraction():
    rc = _load_rc()
    # 读语句里的数据路径被抓；巡检行（ls/stat/du 开头）里的不算
    cmd = 'readRDS("/hwfssz3/PS_JLU/zhangbo/MuSC.rds")\nls -lh /hwfssz3/PS_JLU/zhangbo/other.rds'
    assert rc._persist_gate_paths(cmd) == ["/hwfssz3/PS_JLU/zhangbo/MuSC.rds"]
    assert rc._persist_gate_paths("stat -c '%s' /a/b.rds") == []
    assert rc._persist_gate_paths("echo hello") == []
    # --input=/c/d.bam 形式 + 去重
    p2 = rc._persist_gate_paths("run --input=/c/d.bam --input=/c/d.bam")
    assert p2 == ["/c/d.bam"]


def test_persist_gate_decide():
    rc = _load_rc()
    big = [{"path": "/a/big.rds", "size": 200 * 1048576}]
    payload = rc._persist_gate_decide(big, set(), "ssh3", 100)
    assert payload["status"] == "needs_persist"
    assert payload["big_inputs"][0]["path"] == "/a/big.rds"
    assert "scan --remote" in payload["flow"][0]
    # 账本已覆盖 → 放行；无大件 → 放行
    assert rc._persist_gate_decide(big, {"/a/big.rds"}, "ssh3", 100) is None
    assert rc._persist_gate_decide([], set(), "ssh3", 100) is None


def test_persist_gate_wired_into_run_submit():
    """run/submit 入口静态接线断言（真 SSH 在单测里不可用）。"""
    with open(os.path.join(_REPO, "memomics", "bio_tools", "remote_cluster.py"),
              encoding="utf-8") as fh:
        src = fh.read()
    assert src.count("gate = _persist_gate(cfg, args, command)") == 2
    assert "def _persist_gate(" in src and "status\": \"needs_persist\"" in src or "needs_persist" in src