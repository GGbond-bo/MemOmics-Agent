# -*- coding: utf-8 -*-
"""产出资产清单测试（2026-08-25）：扫描分类/排除/去重/digest/索引刷新。

解决：输出文件组织（应进子目录）+ 资产复用（输入/输出/脚本/图片清单 digest 携带）。
"""
import json
import os
import time

import pytest

pytestmark = pytest.mark.unit


@pytest.fixture(scope="module")
def server():
    import server as _s
    return _s


def _seed_outputs(rd):
    """构造典型产出目录结构（含应归位与应排除的文件）。"""
    for sub in ("figures", "results", "scripts", "data", "log", "review"):
        os.makedirs(os.path.join(rd, sub), exist_ok=True)
    files = {
        "figures/umap.png": b"PNG",
        "figures/pca_plot.pdf": b"PDF",
        "results/cluster_stats.csv": b"a,b\n1,2\n",
        "results/deg_table.tsv": b"g\tfc\n",
        "scripts/run_cluster.R": b"library(Seurat)\n",
        "scripts/plot_umap.py": b"import scanpy\n",
        "data/obj.rds": b"RDS",
        "log/pipeline.log": b"done\n",
        # 根目录散落文件（应被扫描到，但 digest 提示归位）
        "umi_plot.png": b"PNG",
        "raw_out.csv": b"x\n",
        # 应排除的账本/中间文件
        "task_plan.md": b"# Goal\n",
        "REQUIREMENTS.md": b"data in E:/data\n",
        ".task_state.json": b"{}",
        "token_usage.jsonl": b"[]",
        "review/assets.json": b"{}",
        "review/evidence.jsonl": b"",
        "x.tmp": b"tmp",
    }
    for rel, data in files.items():
        p = os.path.join(rd, rel)
        with open(p, "wb") as f:
            f.write(data)
    # 时间戳错开（最新在前排序可测）
    for i, rel in enumerate(files):
        p = os.path.join(rd, rel)
        t = time.time() - i
        os.utime(p, (t, t))


def test_scan_classifies_and_excludes(server, tmp_path):
    rd = str(tmp_path / "r")
    _seed_outputs(rd)
    assets = server._scan_output_assets(rd)
    rels = {a["rel"] for a in assets}
    assert "figures/umap.png" in rels
    assert "results/cluster_stats.csv" in rels
    assert "scripts/run_cluster.R" in rels
    assert "data/obj.rds" in rels
    assert "log/pipeline.log" in rels
    assert "umi_plot.png" in rels, "根目录产出也应被记录（digest 提示归位）"
    # 排除账本/中间
    for banned in ("task_plan.md", "REQUIREMENTS.md", ".task_state.json",
                   "token_usage.jsonl", "review/assets.json", "review/evidence.jsonl",
                   "x.tmp"):
        assert banned not in rels, f"{banned} 不应出现在资产清单"
    # 分类正确
    by_rel = {a["rel"]: a["cat"] for a in assets}
    assert by_rel["figures/umap.png"] == "figure"
    assert by_rel["results/cluster_stats.csv"] == "table"
    assert by_rel["scripts/run_cluster.R"] == "script"
    assert by_rel["data/obj.rds"] == "data"
    assert by_rel["log/pipeline.log"] == "log"
    # 最新在前
    assert assets[0]["mtime"] >= assets[-1]["mtime"]


def test_save_and_digest(server, tmp_path):
    rd = str(tmp_path / "r2")
    _seed_outputs(rd)
    sess = {"id": "a1", "results_dir": rd, "todos": [], "messages": []}
    server._save_assets_index(sess)
    idx = os.path.join(rd, "review", "assets.json")
    assert os.path.isfile(idx)
    data = json.load(open(idx, encoding="utf-8"))
    assert data["updated_at"] and len(data["assets"]) >= 8
    # digest 从索引读（不重新扫描）
    dig = server._build_output_assets_digest(sess)
    assert "会话产出资产" in dig
    assert "figures/umap.png" in dig
    assert "📊" in dig, "图应有图标标注"
    assert "task_plan" not in dig


def test_digest_fallback_scan_without_index(server, tmp_path):
    """无 assets.json 时现扫兜底。"""
    rd = str(tmp_path / "r3")
    os.makedirs(os.path.join(rd, "figures"), exist_ok=True)
    with open(os.path.join(rd, "figures", "a.png"), "wb") as f:
        f.write(b"P")
    sess = {"id": "a2", "results_dir": rd, "todos": [], "messages": []}
    dig = server._build_output_assets_digest(sess)
    assert "figures/a.png" in dig


def test_empty_and_missing_dir(server, tmp_path):
    rd = str(tmp_path / "r4")
    sess = {"id": "a3", "results_dir": rd, "todos": [], "messages": []}
    assert server._build_output_assets_digest(sess) == ""
    assert server._build_output_assets_digest({"id": "x", "results_dir": ""}) == ""
    server._save_assets_index(sess)  # 不炸


def test_ephemeral_output_rules_present(server):
    """ephemeral 输出归位铁律存在（输出组织链路）。"""
    # 检查注入代码里的规则文本（server 源码级回归护栏）
    src = open(os.path.join(os.path.dirname(server.__file__), "server.py"),
               encoding="utf-8").read()
    assert "输出归位铁律" in src
    assert "figures/" in src and "results/" in src and "scripts/" in src
    assert "回合结束时，向用户汇报本次产出的**文件清单**" in src
