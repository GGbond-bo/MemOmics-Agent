# -*- coding: utf-8 -*-
"""#2/#3 改造（2026-08-21）离线单测：
- #2 持久要求记忆：REQUIREMENTS.md 提取/去重/上限/digest 固定携带/rollup 同带
- #3 脚本落盘：scripts/ 清单提示
全部离线，不触发真实 memory_store 写入（autouse monkeypatch）。
"""
import os

import pytest

import server

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def _no_real_memory_write(monkeypatch):
    import memomics.bio_tools.memory_bridge as mb
    monkeypatch.setattr(mb, "store_user_pref", lambda *a, **k: -1)


def _mk_session(tmp_path):
    (tmp_path / "scripts").mkdir(parents=True, exist_ok=True)
    return {"id": "req-unit-test", "results_dir": str(tmp_path)}


class TestRequirementPersistence:
    def test_extract_path_and_requirement(self, tmp_path):
        s = _mk_session(tmp_path)
        server._extract_and_store_requirements(s, "以后做图必须带 P 值，数据路径 E:/骨骼肌锻炼/MF_AUCell_meta.csv。配色也统一一点。")
        p = os.path.join(str(tmp_path), "REQUIREMENTS.md")
        assert os.path.isfile(p)
        txt = open(p, encoding="utf-8").read()
        assert "必须带 P 值" in txt
        assert "E:/骨骼肌锻炼/MF_AUCell_meta.csv" in txt
        assert "统一" in txt

    def test_dedupe(self, tmp_path):
        s = _mk_session(tmp_path)
        for _ in range(3):
            server._extract_and_store_requirements(s, "记住输出必须带 P 值。")
        txt = open(os.path.join(str(tmp_path), "REQUIREMENTS.md"), encoding="utf-8").read()
        assert txt.count("必须带 P 值") == 1

    def test_read_requirements_paths(self, tmp_path):
        s = _mk_session(tmp_path)
        server._extract_and_store_requirements(s, "颜色统一。")
        server._extract_and_store_requirements(s, "路径 E:/data/x.csv 别忘了。")
        reqs = server._read_requirements(s, limit=8)
        assert reqs and any("E:/data/x.csv" in r for r in reqs)

    def test_digest_contains_requirements(self, tmp_path):
        s = _mk_session(tmp_path)
        server._extract_and_store_requirements(s, "记住每次出图都要带图注。")
        d = server._build_memory_digest(s, "随便")
        assert "会话要求" in d and "每次出图都要带图注" in d

    def test_chat_text_not_spam(self, tmp_path):
        s = _mk_session(tmp_path)
        server._extract_and_store_requirements(s, "你好呀")
        assert not os.path.isfile(os.path.join(str(tmp_path), "REQUIREMENTS.md"))

    def test_skip_assistant_directed_instructions(self, tmp_path):
        """回归(2026-08-21)：“发给助手的指令”不得污染持久要求。
        如自检消息('只用一句话回复…不要调用任何工具')带'不要/记住'本会命中标记，应被过滤；真要求照存。"""
        s = _mk_session(tmp_path)
        server._extract_and_store_requirements(
            s, "系统自检：只用一句话回复'通过'，不要调用任何工具。以后做图必须带 P 值。")
        txt = ""
        p = os.path.join(str(tmp_path), "REQUIREMENTS.md")
        if os.path.isfile(p):
            txt = open(p, encoding="utf-8").read()
        assert "只用一句话回复" not in txt, "助手指令不得入库"
        assert "不要调用任何工具" not in txt
        assert "必须带 P 值" in txt, "真正的用户要求应照存"


class TestScriptsReuse:
    def test_scripts_digest_lists_existing(self, tmp_path):
        s = _mk_session(tmp_path)
        (tmp_path / "scripts" / "fig_v1.py").write_text("x", encoding="utf-8")
        (tmp_path / "scripts" / "fig_v2.R").write_text("y", encoding="utf-8")
        dig = server._build_scripts_digest(s, limit=5)
        assert "scripts/" in dig and ("fig_v1.py" in dig or "fig_v2.R" in dig)

    def test_scripts_digest_empty_when_none(self, tmp_path):
        s = _mk_session(tmp_path)
        assert server._build_scripts_digest(s, limit=5) == ""


class TestRollupCarriesRequirements:
    def test_checkpoint_has_requirements_section(self, tmp_path, monkeypatch):
        s = _mk_session(tmp_path)
        server._extract_and_store_requirements(s, "记住所有图必须用 CNS 配色。")
        hist = [{"role": "user", "content": f"消息 {i}"} for i in range(20)]
        monkeypatch.setenv("MEMOMICS_ROLLUP_BUDGET", "10")
        monkeypatch.setenv("MEMOMICS_ROLLUP_TAIL", "3")
        out = server._maybe_rollup_history(s, hist)
        assert any(m["role"] == "system" and "持久用户要求/路径" in m["content"] for m in out)
