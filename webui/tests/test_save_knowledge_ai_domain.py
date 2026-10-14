# -*- coding: utf-8 -*-
"""save_knowledge 的 `domain="ai"` 分域回归（2026-10-11 新增）。

背景：AI / 科研智能体类文献（Biomni、Co-Scientist、DeepRare、ChemGraph …）既不是
物种五级目录（biology）也不是化学条目，此前只能塞进 `common/<dir>/03_测序方法/NA/`
—— 语义错位。本次给 save_knowledge 增加独立 `ai` 域，落盘为
`ai_agent/<subcategory>/<name>.yaml`。

本测试是三条护栏：
1) ai 域落盘路径正确、YAML 顶层字段正确；
2) 子类（direction）仍受路径段白名单约束（防路径穿越），非法输入被拒；
3) 既有铁轨（unverified 拒收）与既有域（biology 五级目录）未被新分支影响。
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest
import yaml

pytestmark = pytest.mark.kb

REPO_ROOT = Path(__file__).resolve().parents[2]


def _load_save_knowledge():
    """按路径加载 save_knowledge（memomics.bio_tools.__init__ 会拉起 hermes-agent 依赖，不能走包导入）。"""
    path = REPO_ROOT / "memomics" / "bio_tools" / "save_knowledge.py"
    spec = importlib.util.spec_from_file_location("memomics_save_knowledge_ai", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def sk():
    return _load_save_knowledge()


@pytest.fixture()
def kb_root(tmp_path, sk, monkeypatch):
    """把知识库根目录指到 tmp_path，避免污染真实知识库。"""
    monkeypatch.setattr(sk, "_kb_root", lambda: str(tmp_path))
    return tmp_path


def _call(sk, **kw):
    kw.setdefault("name", "ai_test_entry")
    kw.setdefault("content", "测试内容")
    return json.loads(sk.save_knowledge(**kw))


# ── 1. 正常路径 ──────────────────────────────────────────────────────────

def test_ai_domain_writes_to_ai_agent_subcategory(sk, kb_root):
    res = _call(sk, domain="ai", direction="frameworks", source="manual")
    assert res["status"] == "success", res
    assert res["mode"] == "ai_yaml"

    entry = Path(res["path"])
    assert entry.exists()
    # 路径必须是 <root>/ai_agent/<subcategory>/<name>.yaml
    assert entry.parent.parent.name == "ai_agent"
    assert entry.parent.name == "frameworks"
    assert entry.name == "ai_test_entry.yaml"

    doc = yaml.safe_load(entry.read_text(encoding="utf-8"))
    assert doc["domain"] == "ai"
    assert doc["subcategory"] == "frameworks"
    assert doc["name"] == "ai_test_entry"
    assert doc["type"] == "kb_entry"


def test_ai_domain_direction_defaults_to_general(sk, kb_root):
    res = _call(sk, name="ai_no_dir", domain="ai", source="manual")
    assert res["status"] == "success", res
    assert Path(res["path"]).parent.name == "general"


def test_ai_domain_normalises_subcategory_case_and_spaces(sk, kb_root):
    """子类名做 lower + 空格/连字符→下划线 归一化（与 common 域一致）。"""
    res = _call(sk, name="ai_norm", domain="ai", direction="Agent Design", source="manual")
    assert res["status"] == "success", res
    assert Path(res["path"]).parent.name == "agent_design"


def test_ai_domain_with_evidence_carries_it(sk, kb_root):
    res = _call(sk, name="ai_ev", domain="ai", direction="benchmarks",
                source="data_driven", evidence="原文：Recall@1 57.18%")
    assert res["status"] == "success", res
    doc = yaml.safe_load(Path(res["path"]).read_text(encoding="utf-8"))
    assert "57.18" in doc["evidence"]


# ── 2. 错误路径 / 边界 ───────────────────────────────────────────────────

@pytest.mark.parametrize("bad", ["a/b", "..", "sub/../evil", "x" * 70])
def test_ai_domain_rejects_illegal_subcategory(sk, kb_root, bad):
    res = _call(sk, name="ai_bad", domain="ai", direction=bad, source="manual")
    assert res["status"] == "error", res
    assert "非法" in res["error"]
    # 不得在 root 之外留下任何东西
    assert not (kb_root / "ai_agent" / "evil").exists()


def test_ai_domain_rejects_illegal_name(sk, kb_root):
    res = _call(sk, name="../../evil", domain="ai", direction="frameworks", source="manual")
    assert res["status"] == "error"


def test_unverified_still_rejected_in_ai_domain(sk, kb_root):
    """铁轨回归：新分支不得绕过 unverified 拒收。"""
    res = _call(sk, name="ai_unver", domain="ai", source="manual", verified="unverified")
    assert res["status"] == "error"
    assert "unverified" in res["error"]


def test_data_driven_without_evidence_still_rejected_in_ai_domain(sk, kb_root):
    """铁轨回归：新分支不得绕过 evidence 强制。"""
    res = _call(sk, name="ai_noev", domain="ai", source="data_driven")
    assert res["status"] == "error"


# ── 3. 既有域不被影响 ────────────────────────────────────────────────────

def test_biology_five_level_path_unchanged(sk, kb_root):
    res = _call(sk, name="bio_reg", domain="biology", species="human",
                tissue="skeletal muscle", direction="aging", source="manual")
    assert res["status"] == "success", res
    assert res["mode"] == "five_level_yaml"
    p = Path(res["path"])
    assert p.parent.parent.parent.parent.parent.name == "Homo_sapiens"
    assert not (kb_root / "ai_agent").exists(), "biology 域不应触碰 ai_agent 目录"


def test_common_domain_path_unchanged(sk, kb_root):
    res = _call(sk, name="common_reg", domain="common", direction="general",
                kb_category="03_测序方法", assay_type="NA", source="manual")
    assert res["status"] == "success", res
    assert res["mode"] == "common_yaml"