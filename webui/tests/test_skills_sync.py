# -*- coding: utf-8 -*-
"""SKILLS_INDEX 自愈（auto_register.sync_new_skills）回归测试。

2026-09-24 真机事故：wave4 真机测试期间，磁盘上多出一个技能目录
（hermes_home/skills/bioinformatics/trajectory-conclusion-validation），SKILLS_INDEX.md 里没有它的行。
SKILLS_INDEX.md 是唯一会被注入 system prompt 的技能清单 —— 缺行等于模型永远看不到这个技能；
同一条漂移还会让 webui/tests/test_skills_registry.py 的「索引行集合 == 磁盘技能集合」两条断言直接红。
根因：索引只在进程启动 scan_and_register_all() 和「注册技能」工具里重建，agent 会话中途用 write
直接造出来的技能要等下一次重启才进索引。
"""
import json
import os

import pytest

from webui import auto_register, skills_registry


def _write_skill(root: str, name: str) -> str:
    """造一个最小可用技能目录（skill.json + SKILL.md）。"""
    d = os.path.join(root, name)
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "skill.json"), "w", encoding="utf-8") as f:
        json.dump({"id": name, "name": name, "description": "测试技能 " + name,
                   "category": "bioinformatics",
                   "trigger_keywords": ["测试触发一", "测试触发二", "测试触发三", "测试触发四"]},
                  f, ensure_ascii=False)
    with open(os.path.join(d, "SKILL.md"), "w", encoding="utf-8") as f:
        f.write("# " + name + chr(10) + chr(10) + "测试用技能。" + chr(10))
    return d


def _write_index(path: str, names) -> None:
    """手写一份只含 names 的索引（行格式：| 序号 | 技能名 | 用法 | 触发词 | 等级 |）。"""
    out = ["| # | 技能 | 用法 | 触发词 | 等级 |", "|---|------|------|--------|------|"]
    for i, n in enumerate(names, 1):
        out.append("| %d | %s | 测试 | 测试触发一, 测试触发二 | GRN 按需触发 |" % (i, n))
    with open(path, "w", encoding="utf-8", newline=chr(10)) as f:
        f.write(chr(10).join(out) + chr(10))


@pytest.fixture()
def sandbox(tmp_path, monkeypatch):
    """把技能目录 + 索引都指到临时目录，避免碰真实 hermes_home。"""
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()
    index = tmp_path / "SKILLS_INDEX.md"
    monkeypatch.setattr(auto_register, "SKILLS_BIO_DIR", str(skills_dir), raising=False)
    # 关键：auto_register._registry() 优先 `import skills_registry`（webui/ 在 sys.path 上），
    # pytest 里又可能是 `webui.skills_registry` —— 两个模块对象，必须打在生产代码真正用的那个上，
    # 否则 rebuild 会去写真实 hermes_home/SKILLS_INDEX.md（第一次写这条测试时就这么脏过一次）。
    reg = auto_register._registry()
    assert reg is not None, "skills_registry 不可用"
    monkeypatch.setattr(reg, "SKILLS_DIR", str(skills_dir))
    monkeypatch.setattr(reg, "INDEX_PATH", str(index))
    assert str(tmp_path) in reg.INDEX_PATH, "索引必须落在临时目录，不能碰真实索引"
    assert str(tmp_path) in reg.SKILLS_DIR, "技能根目录必须落在临时目录"
    return skills_dir, index


def test_sync_adds_missing_skill_row(sandbox):
    """磁盘上有、索引里没有 → 自愈重建，缺的技能必须有行。"""
    skills_dir, index = sandbox
    _write_skill(str(skills_dir), "alpha-skill")
    _write_skill(str(skills_dir), "beta-skill")
    _write_index(str(index), ["alpha-skill"])          # 模拟漂移：beta 没进索引
    assert "beta-skill" not in index.read_text(encoding="utf-8")

    info = auto_register.sync_new_skills(verbose=True)
    assert info["ok"] is True, info
    assert info["rebuilt"] is True
    assert info["missing"] == ["beta-skill"]
    text = index.read_text(encoding="utf-8")
    assert "alpha-skill" in text and "beta-skill" in text


def test_sync_is_noop_when_index_is_complete(sandbox):
    """索引不缺行时不能白重建（每个回合都会调用一次）。"""
    skills_dir, index = sandbox
    _write_skill(str(skills_dir), "alpha-skill")
    auto_register.sync_new_skills()                     # 首次：建索引
    before = index.read_text(encoding="utf-8")
    info = auto_register.sync_new_skills()              # 第二次：应当直接返回
    assert info["ok"] is True and info["rebuilt"] is False and info["missing"] == []
    assert index.read_text(encoding="utf-8") == before


def test_sync_generates_missing_skill_json(sandbox):
    """第二种漂移：只有 SKILL.md 没有 skill.json —— 选择器选得到、模型触发不到。"""
    skills_dir, index = sandbox
    d = skills_dir / "gamma-skill"
    d.mkdir()
    (d / "SKILL.md").write_text("# gamma-skill" + chr(10) + chr(10) + "只有 md，没有 json。" + chr(10), encoding="utf-8")
    assert not (d / "skill.json").exists()

    info = auto_register.sync_new_skills(verbose=True)
    assert info["ok"] is True, info
    assert info["json_generated"] == ["gamma-skill"]
    assert (d / "skill.json").is_file(), "应当补出 skill.json"
    assert "gamma-skill" in index.read_text(encoding="utf-8")


def test_sync_ignores_skills_outside_product_surface(sandbox):
    """技能面（SKILLS_BIO_DIR）之外的 SKILL.md-only 目录不许补 json ——
    那批是 Hermes 自带的技能，故意不进索引；补了会把 83 个无关技能灌进模型触发面。
    """
    skills_dir, index = sandbox
    outside = skills_dir.parent / "other-category" / "arxiv"
    outside.mkdir(parents=True)
    (outside / "SKILL.md").write_text("# arxiv" + chr(10), encoding="utf-8")
    info = auto_register.sync_new_skills()
    assert info["ok"] is True, info
    assert info["json_generated"] == []
    assert not (outside / "skill.json").exists(), "技能面之外的目录不该被补 skill.json"


def test_sync_reports_not_initialized(monkeypatch):
    """未 init() 时必须明确报错，而不是静默改坏真实索引。"""
    monkeypatch.setattr(auto_register, "SKILLS_BIO_DIR", None, raising=False)
    info = auto_register.sync_new_skills()
    assert info["ok"] is False and "not initialized" in info["error"]


def test_turn_end_hook_is_wired():
    """回合结束必须调用自愈 —— 否则 agent 中途造出来的技能又要等重启。"""
    server_py = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "server.py")
    with open(server_py, encoding="utf-8") as f:
        src = f.read()
    assert "auto_register.sync_new_skills()" in src
