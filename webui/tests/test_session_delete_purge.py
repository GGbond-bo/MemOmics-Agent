# -*- coding: utf-8 -*-
"""会话删除 = 数据删除（用户要求 2026-09-13）

回归目标：
- DELETE /api/sessions/{sid} 之后 results/<sid>/ 物理消失（含 figures/ 等子目录数据）
- rename 后的 <物种_组织_方向_日期_短ID> 目录同样被删
- 结果目录之外的路径（用户 output_root / 桌面镜像）一律不动
- results/ 根目录自身、别的会话目录永不被删（归属校验）
"""
import os

import pytest

import server
from conftest import cleanup_session

pytestmark = pytest.mark.integration


def _mk(path: str, text: str = "x") -> str:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    return path


def test_owned_results_dir_guard():
    """归属校验：results/ 根、外部路径、别的会话目录都必须被拒绝"""
    sid = "memomics-deadbeef"
    short = sid.split("-")[-1]
    assert server._owned_results_dir(sid, os.path.join(server.RESULTS_DIR, sid)) is True
    assert server._owned_results_dir(sid, os.path.join(server.RESULTS_DIR, f"human_brain_atac_20260913_{short}")) is True
    assert server._owned_results_dir(sid, server.RESULTS_DIR) is False
    assert server._owned_results_dir(sid, os.path.dirname(server.RESULTS_DIR)) is False
    assert server._owned_results_dir(sid, os.path.join(server.RESULTS_DIR, "memomics-00112233")) is False
    assert server._owned_results_dir(sid, "") is False


def test_delete_session_removes_results_data(client, new_session):
    """删除会话：结果目录连同里面的数据一并物理删除"""
    sid = new_session
    base = os.path.join(server.RESULTS_DIR, sid)
    _mk(os.path.join(base, "figures", "pca.png"), "png-bytes")
    _mk(os.path.join(base, "results", "de.tsv"), "gene\tlogfc\n")
    _mk(os.path.join(base, "token_usage.jsonl"), "{}\n")
    assert os.path.isdir(base)

    r = client.delete(f"/api/sessions/{sid}")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert not os.path.exists(base), "会话删除后结果目录必须物理消失"
    assert any(p.endswith(sid) for p in body["results_dirs_deleted"])
    assert body["results_dirs_failed"] == []


def test_delete_removes_renamed_results_dir(client, new_session):
    """rename_results_dir 改名后的目录（含短 ID）同样被删"""
    sid = new_session
    short = sid.split("-")[-1]
    renamed = os.path.join(server.RESULTS_DIR, f"human_brain_atac_20260913_{short}")
    _mk(os.path.join(renamed, "log", "run.log"), "log")
    server._sessions[sid]["results_dir"] = renamed  # 模拟 rename 后的内存态

    body = client.delete(f"/api/sessions/{sid}").json()
    assert body["ok"] is True
    assert not os.path.exists(renamed), "改名后的会话目录也必须被删"


def test_delete_keeps_external_output_root(client, new_session, tmp_path):
    """results/ 之外的目录（桌面/自定义 output_root）绝不能被删"""
    sid = new_session
    ext = tmp_path / "desktop_output"
    _mk(str(ext / "results" / "keep.tsv"), "keep")
    inside = os.path.join(server.RESULTS_DIR, sid)
    _mk(os.path.join(inside, "data", "x.bin"), "x")
    server._sessions[sid]["output_root"] = str(ext)
    server._sessions[sid]["results_dir"] = str(ext)  # 异常指向：必须被归属校验拒绝

    body = client.delete(f"/api/sessions/{sid}").json()
    assert body["ok"] is True
    assert (ext / "results" / "keep.tsv").is_file(), "results/ 之外的目录绝不能被删"
    assert not os.path.exists(inside), "results/ 内的会话目录仍应被删"
    assert any(str(ext).replace("\\", "/") in p for p in body["external_dirs_kept"])


def test_delete_purges_dir_when_session_not_in_memory(client):
    """内存里已无该会话（旧会话/重启后），磁盘目录照样按 sid 清干净"""
    sid = "memomics-5a5a5a5a"
    base = os.path.join(server.RESULTS_DIR, sid)
    _mk(os.path.join(base, "figures", "f1.png"), "f")
    server._sessions.pop(sid, None)
    try:
        body = client.delete(f"/api/sessions/{sid}").json()
        assert body["ok"] is True
        assert not os.path.exists(base)
    finally:
        cleanup_session(sid)
